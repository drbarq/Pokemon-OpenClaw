#!/usr/bin/env python3
"""
Pokemon Red -- AI Player Loop

Autonomous agent that plays Pokemon Red by:
1. Taking a snapshot (game state + screenshot)
2. Sending it to Claude with the system prompt + context
3. Parsing the JSON response for an action
4. Dispatching the action via the emulator server HTTP API
5. Repeating forever

Usage:
    ANTHROPIC_API_KEY=sk-... python scripts/ai_player.py
    ANTHROPIC_API_KEY=sk-... python scripts/ai_player.py --model claude-sonnet-4-20250514 --delay 1.0
"""

import argparse
import json
import os
import re
import sys
import time
import traceback
from collections import deque
from pathlib import Path

import anthropic

# Add scripts dir to path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import llm_client

PROJECT_ROOT = SCRIPT_DIR.parent
INSTRUCTIONS_FILE = PROJECT_ROOT / "instructions_openclaw.md"


def load_system_prompt() -> str:
    """Load the system prompt from instructions_openclaw.md."""
    if INSTRUCTIONS_FILE.exists():
        return INSTRUCTIONS_FILE.read_text()
    print(f"WARNING: {INSTRUCTIONS_FILE} not found, using fallback prompt")
    return "You are an AI playing Pokemon Red. Respond with a single JSON object containing action, reasoning, and notepad fields."


# ============================================================
# AI Player
# ============================================================

class AIPlayer:
    def __init__(self, model: str = "claude-sonnet-4-20250514", delay: float = 1.0):
        self.client = anthropic.Anthropic()
        self.model = model
        self.delay = delay
        self.system_prompt = load_system_prompt()

        # Persistent notepad -- Claude writes notes to itself across turns
        self.notepad = ""
        self.turn_count = 0

        # Stuck detection: track recent positions
        self.position_history: deque = deque(maxlen=10)

    def build_messages(self, snap: dict, quest: dict, knowledge: dict) -> list:
        """Build the message list for the Anthropic API call."""
        state = snap["state"]
        summary = snap["summary"]
        screenshot_b64 = snap["screenshot_b64"]

        # Quest context
        quest_lines = []
        quest_data = quest.get("data", quest)
        if quest_data.get("current_quest"):
            current_id = quest_data["current_quest"]
            step_idx = quest_data.get("quest_step", 0)
            for q in quest_data.get("quest_log", []):
                if q["id"] == current_id:
                    quest_lines.append(f"Quest: {q['name']}")
                    if step_idx < len(q["steps"]):
                        step = q["steps"][step_idx]
                        quest_lines.append(f"Current step ({step_idx}/{len(q['steps'])}): {step['desc']}")
                        if step.get("hint"):
                            quest_lines.append(f"Hint: {step['hint']}")
                    break

        # Knowledge / lessons
        lessons = []
        if isinstance(knowledge, dict):
            kdata = knowledge.get("data", knowledge)
            lessons = kdata.get("lessons_learned", [])
            # Also include battle strategy
            strat = kdata.get("battle_strategy", {})
            if strat:
                lessons.append(f"Battle strategy: {json.dumps(strat)}")

        # Stuck detection
        pos = state.get("position", {})
        pos_key = (pos.get("map_name"), pos.get("x"), pos.get("y"))
        self.position_history.append(pos_key)
        stuck_warning = ""
        if len(self.position_history) >= 4:
            recent = list(self.position_history)[-4:]
            if len(set(recent)) == 1:
                stuck_warning = (
                    "\n!! WARNING: You have been at the SAME position for 4+ turns. "
                    "You are STUCK. Try a completely different approach. !!\n"
                )

        # Build the text context
        context_parts = [
            f"=== Turn {self.turn_count} ===",
            "",
            f"Game State:\n{summary}",
            "",
        ]

        if quest_lines:
            context_parts.append("Quest:\n" + "\n".join(quest_lines))
            context_parts.append("")

        if lessons:
            context_parts.append("Lessons Learned:\n" + "\n".join(f"- {l}" for l in lessons[-15:]))
            context_parts.append("")

        if self.notepad:
            context_parts.append(f"Your Notepad (from previous turns):\n{self.notepad}")
            context_parts.append("")

        if stuck_warning:
            context_parts.append(stuck_warning)

        context_parts.append(
            'Respond with a single JSON object. Include a "notepad" field with notes for your future self.'
        )

        context_text = "\n".join(context_parts)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": context_text,
                    },
                ],
            }
        ]
        return messages

    def call_llm(self, messages: list) -> dict:
        """Call the Anthropic API and parse the JSON response."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self.system_prompt,
            messages=messages,
        )

        raw_text = response.content[0].text.strip()

        # Try to parse JSON directly
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass

        # Fallback: extract JSON from markdown code blocks or surrounding text
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Last resort: return a no-op with the raw text for debugging
        print(f"  [WARN] Could not parse LLM response: {raw_text[:200]}")
        return {"action": "buttons", "buttons": ["b"], "reasoning": "Parse error fallback", "notepad": self.notepad}

    def dispatch(self, decision: dict) -> dict:
        """Execute the AI's decision via the emulator server."""
        action = decision.get("action", "buttons")
        reasoning = decision.get("reasoning", "")

        if action == "buttons":
            buttons = decision.get("buttons", ["b"])
            if not isinstance(buttons, list):
                buttons = [str(buttons)]
            # Cap at 10 buttons per turn
            buttons = buttons[:10]
            return llm_client.press(buttons, reasoning=reasoning)

        elif action == "fight":
            move_index = decision.get("move_index", 0)
            return llm_client.fight(move_index=move_index, reasoning=reasoning)

        elif action == "run":
            return llm_client.run_away(reasoning=reasoning)

        elif action == "navigate":
            destination = decision.get("destination", "")
            return llm_client.navigate(destination)

        elif action == "heal":
            return llm_client.go_heal()

        elif action == "complete_step":
            lesson = decision.get("lesson")
            return llm_client.complete_quest_step(lesson=lesson)

        elif action == "save":
            return llm_client.save("ai_checkpoint")

        else:
            print(f"  [WARN] Unknown action: {action}, pressing B as fallback")
            return llm_client.press(["b"], reasoning=f"Unknown action fallback: {action}")

    def step(self) -> dict:
        """Execute one turn of the AI loop."""
        self.turn_count += 1
        print(f"\n{'='*50}")
        print(f"Turn {self.turn_count}")
        print(f"{'='*50}")

        # 1. Snapshot
        snap = llm_client.snapshot()
        print(f"  State: {snap['summary'][:120]}")

        # 2. Get quest & knowledge
        quest = llm_client.get_quest()
        knowledge = llm_client.get_knowledge()

        # 3. Build prompt & call LLM
        messages = self.build_messages(snap, quest, knowledge)
        print(f"  Calling {self.model}...")
        decision = self.call_llm(messages)

        action = decision.get("action", "?")
        reasoning = decision.get("reasoning", "")
        print(f"  Action: {action}")
        print(f"  Reasoning: {reasoning[:100]}")

        # 4. Update notepad
        new_notepad = decision.get("notepad", "")
        if new_notepad:
            self.notepad = str(new_notepad)[:2000]  # Cap notepad size

        # 5. Dispatch
        result = self.dispatch(decision)

        # 6. Auto-save every 50 turns
        if self.turn_count % 50 == 0:
            print(f"  [Auto-save at turn {self.turn_count}]")
            try:
                llm_client.save(f"ai_auto_{self.turn_count}")
            except Exception as e:
                print(f"  [Auto-save failed: {e}]")

        return result

    def run(self):
        """Main loop -- runs forever until interrupted."""
        print("Pokemon Red AI Player starting...")
        print(f"  Model: {self.model}")
        print(f"  Delay: {self.delay}s between turns")
        print(f"  Server: {llm_client.SERVER}")
        print()

        # Verify server connection
        try:
            state = llm_client.get_state()
            if state.get("status") != "ok":
                print(f"Server not ready: {state}")
                sys.exit(1)
            print("Connected to emulator server!")
            pos = state.get("data", {}).get("position", {})
            print(f"  Location: {pos.get('map_name')} ({pos.get('x')}, {pos.get('y')})")
        except Exception as e:
            print(f"Cannot connect to server at {llm_client.SERVER}: {e}")
            print("Start the server first: python scripts/emulator_server.py --save ready --port 3456")
            sys.exit(1)

        while True:
            try:
                self.step()
            except anthropic.APIStatusError as e:
                print(f"  [API Error: {e.status_code}] Retrying in 10s...")
                time.sleep(10)
                continue
            except anthropic.APIConnectionError:
                print("  [Connection Error] Retrying in 10s...")
                time.sleep(10)
                continue
            except KeyboardInterrupt:
                print("\nStopping AI player...")
                try:
                    llm_client.save("ai_interrupted")
                    print("  Saved state as 'ai_interrupted'")
                except Exception:
                    pass
                break
            except Exception as e:
                print(f"  [Error] {e}")
                traceback.print_exc()
                print("  Continuing in 5s...")
                time.sleep(5)
                continue

            time.sleep(self.delay)


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Pokemon Red AI Player")
    parser.add_argument("--model", default="claude-sonnet-4-20250514",
                        help="Anthropic model to use")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds to wait between turns")
    parser.add_argument("--server", default=None,
                        help="Emulator server URL (default: http://localhost:3456)")
    args = parser.parse_args()

    if args.server:
        llm_client.SERVER = args.server

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    player = AIPlayer(model=args.model, delay=args.delay)
    player.run()


if __name__ == "__main__":
    main()
