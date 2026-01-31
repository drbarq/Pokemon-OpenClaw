#!/usr/bin/env python3
"""
Pokemon Red — Autonomous Play Session
Runs N turns of gameplay, saving screenshots and state to disk.
Designed to be run as a background process by OpenClaw.

Usage:
  python scripts/play_session.py PokemonRed.gb --turns 20 --save-name mysave
  python scripts/play_session.py PokemonRed.gb --minutes 5 --save-name mysave
"""

import os
import sys
import json
import time
import argparse
import base64
import io
from pathlib import Path
from datetime import datetime

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.game import PokemonGame


def screenshot_to_base64(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def run_session(rom_path: str, save_name: str = "current",
                turns: int = 20, minutes: float = None,
                output_dir: str = "session_output"):
    """Run an autonomous play session."""
    
    out = Path(output_dir)
    out.mkdir(exist_ok=True)
    
    game = PokemonGame(rom_path, headless=True, speed=0)
    if not game.start():
        print("ERROR: Could not start game")
        return
    
    # Try to load existing save
    save_path = Path("saves") / f"{save_name}.state"
    if save_path.exists():
        game.load_state(save_name)
        print(f"Loaded save: {save_name}")
    else:
        print(f"No save found at {save_path}, starting fresh")
        # Skip past boot screens
        game.tick(300)
    
    start_time = time.time()
    turn_log = []
    
    # Determine end condition
    max_turns = turns
    if minutes:
        max_turns = 999999  # effectively infinite, time-limited
    
    print(f"Starting session: {'%.1f minutes' % minutes if minutes else f'{turns} turns'}")
    print(f"Initial state:")
    print(game.format_state_for_ai())
    print("=" * 50)
    
    for turn in range(max_turns):
        # Check time limit
        if minutes and (time.time() - start_time) > minutes * 60:
            print(f"Time limit reached ({minutes} minutes)")
            break
        
        # 1. Capture current state
        screenshot = game.screenshot(save=True, filename=f"turn_{turn:04d}.png")
        state_text = game.format_state_for_ai()
        state_json = game.get_full_state()
        
        # 2. Write turn data for AI to analyze
        turn_data = {
            "turn": turn,
            "timestamp": datetime.now().isoformat(),
            "state": state_json,
            "state_text": state_text,
            "screenshot_path": f"screenshots/turn_{turn:04d}.png",
            "screenshot_b64": screenshot_to_base64(screenshot),
        }
        
        # Save turn data
        turn_file = out / f"turn_{turn:04d}.json"
        with open(turn_file, "w") as f:
            json.dump(turn_data, f, indent=2)
        
        # 3. Write latest state (always overwritten)
        with open(out / "latest.json", "w") as f:
            json.dump(turn_data, f, indent=2)
        screenshot.save(str(out / "latest.png"))
        
        # 4. Check if AI has left a decision file
        decision_file = out / "decision.json"
        if decision_file.exists():
            try:
                with open(decision_file) as f:
                    decision = json.load(f)
                buttons = decision.get("buttons", [])
                reasoning = decision.get("reasoning", "")
                notepad = decision.get("notepad", "")
                
                print(f"Turn {turn}: {buttons} — {reasoning}")
                
                # Execute buttons
                game.press_buttons(buttons)
                
                # Log
                turn_log.append({
                    "turn": turn,
                    "buttons": buttons,
                    "reasoning": reasoning,
                    "position": state_json["position"],
                })
                
                # Remove decision file (consumed)
                decision_file.unlink()
                
                # Save notepad
                if notepad:
                    with open(out / "notepad.md", "w") as f:
                        f.write(notepad)
                
            except Exception as e:
                print(f"Error reading decision: {e}")
        else:
            # No decision yet — wait and write "waiting" status
            with open(out / "status.txt", "w") as f:
                f.write(f"waiting_for_decision\nturn={turn}\n{state_text}")
            
            # Wait a bit for decision to appear
            for _ in range(10):  # Wait up to 10 seconds
                time.sleep(1)
                if decision_file.exists():
                    break
            else:
                # No decision arrived — skip this turn
                print(f"Turn {turn}: No decision, advancing 60 frames")
                game.tick(60)
                continue
            
            # Re-check for decision
            if decision_file.exists():
                continue  # Will be processed next iteration
    
    # Save final state
    game.save_state(save_name)
    game.screenshot(save=True, filename="session_final.png")
    
    # Write session summary
    summary = {
        "session_end": datetime.now().isoformat(),
        "total_turns": len(turn_log),
        "duration_seconds": time.time() - start_time,
        "final_state": game.get_full_state(),
        "final_state_text": game.format_state_for_ai(),
        "turn_log": turn_log,
    }
    with open(out / "session_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print("=" * 50)
    print(f"Session complete: {len(turn_log)} turns in {time.time() - start_time:.0f}s")
    print(game.format_state_for_ai())
    
    game.stop()


def run_auto_session(rom_path: str, save_name: str = "current",
                     turns: int = 20, output_dir: str = "session_output"):
    """
    Run a fully autonomous session — AI decides inline (no file polling).
    Outputs a log of screenshots + states + decisions for review.
    """
    out = Path(output_dir)
    out.mkdir(exist_ok=True)
    
    game = PokemonGame(rom_path, headless=True, speed=0)
    if not game.start():
        print("ERROR: Could not start game")
        return
    
    save_path = Path("saves") / f"{save_name}.state"
    if save_path.exists():
        game.load_state(save_name)
        print(f"Loaded save: {save_name}")
    
    # Load notepad if exists
    notepad = ""
    notepad_file = out / "notepad.md"
    if notepad_file.exists():
        notepad = notepad_file.read_text()
    
    print(f"Running {turns} turns autonomously...")
    print(game.format_state_for_ai())
    print("=" * 50)
    
    turn_log = []
    
    for turn in range(turns):
        # Capture
        screenshot = game.screenshot(save=True, filename=f"turn_{turn:04d}.png")
        state = game.get_full_state()
        state_text = game.format_state_for_ai()
        
        # Write for external analysis
        turn_data = {
            "turn": turn,
            "state_text": state_text,
            "state": state,
            "screenshot_b64": screenshot_to_base64(screenshot),
            "notepad": notepad,
            "recent_actions": turn_log[-10:],  # last 10 actions
        }
        with open(out / "latest.json", "w") as f:
            json.dump(turn_data, f, indent=2)
        screenshot.save(str(out / "latest.png"))
        
        turn_log.append({
            "turn": turn,
            "state_text": state_text,
            "position": state["position"],
        })
        
        # Advance some frames (the AI will make decisions externally)
        game.tick(30)
    
    # Save
    game.save_state(save_name)
    
    summary = {
        "turns": turns,
        "final_state": game.format_state_for_ai(),
        "turn_log": turn_log,
    }
    with open(out / "session_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print("=" * 50)
    print(f"Session done. Final state:")
    print(game.format_state_for_ai())
    
    game.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pokemon Red — Play Session")
    parser.add_argument("rom", help="Path to ROM file")
    parser.add_argument("--save-name", default="current", help="Save state name")
    parser.add_argument("--turns", type=int, default=20, help="Number of turns")
    parser.add_argument("--minutes", type=float, help="Time limit in minutes")
    parser.add_argument("--output", default="session_output", help="Output directory")
    parser.add_argument("--auto", action="store_true", help="Auto mode (no decision polling)")
    args = parser.parse_args()
    
    if args.auto:
        run_auto_session(args.rom, args.save_name, args.turns, args.output)
    else:
        run_session(args.rom, args.save_name, args.turns, args.minutes, args.output)
