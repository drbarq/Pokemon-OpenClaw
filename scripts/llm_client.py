#!/usr/bin/env python3
"""
Pokemon Red — AI Client for the Emulator Server

Use this instead of directly running PyBoy. The emulator runs persistently
on the server, and this client sends commands via HTTP.

Usage:
    from llm_client import get_state, press, screenshot, save, load, fight, navigate

    state = get_state()
    press(["up", "up", "a"], reasoning="Walking to door and interacting")
    screenshot("current.png")
    save("checkpoint_1")
    fight(move_index=0, reasoning="Using Tackle on wild Rattata")
"""

import base64
import json
import requests
from typing import Any, Dict, List, Optional

SERVER = "http://localhost:3456"


def get_state() -> Dict[str, Any]:
    """Get current game state."""
    r = requests.get(f"{SERVER}/api/state", timeout=10)
    r.raise_for_status()
    return r.json()


def press(buttons: List[str], hold: int = 8, wait: int = 16,
          reasoning: str = "") -> Dict[str, Any]:
    """Send button presses to emulator.
    
    Args:
        buttons: List of button names (up/down/left/right/a/b/start/select)
        hold: Frames to hold each button
        wait: Frames to wait after releasing
        reasoning: Why this action (logged for review)
    
    Returns:
        Server response with game state after presses
    """
    r = requests.post(f"{SERVER}/api/press", json={
        "buttons": buttons,
        "hold": hold,
        "wait": wait,
        "reasoning": reasoning,
    }, timeout=30)
    r.raise_for_status()
    return r.json()


def screenshot(save_path: Optional[str] = None) -> bytes:
    """Get current screenshot as PNG bytes.
    
    Args:
        save_path: If provided, save the image to this file path
    
    Returns:
        PNG image bytes
    """
    r = requests.get(f"{SERVER}/api/screenshot", timeout=10)
    r.raise_for_status()
    if save_path:
        with open(save_path, 'wb') as f:
            f.write(r.content)
    return r.content


def command(cmd: str, **kwargs) -> Dict[str, Any]:
    """Send a command to the emulator (save/load/speed).
    
    Args:
        cmd: Command name
        **kwargs: Additional parameters
    """
    r = requests.post(f"{SERVER}/api/command", json={"command": cmd, **kwargs}, timeout=10)
    r.raise_for_status()
    return r.json()


def save(name: str) -> Dict[str, Any]:
    """Save emulator state."""
    return command("save", name=name)


def load(name: str) -> Dict[str, Any]:
    """Load emulator state."""
    return command("load", name=name)


def set_speed(turbo: bool = True) -> Dict[str, Any]:
    """Set emulator speed. turbo=True for max speed, False for normal."""
    return command("speed", turbo=turbo)


def run_away(reasoning: str = "") -> Dict[str, Any]:
    """Try to flee from battle.

    Opens battle menu, selects RUN (down+right from FIGHT), then mashes A
    through the result text.
    """
    press(["a"], reasoning=reasoning or "Trying to flee")
    # Navigate to RUN: down from FIGHT, then right
    press(["down"], hold=6, wait=20)
    press(["right"], hold=6, wait=20)
    press(["a"], hold=6, wait=20)
    # Mash through result text
    for _ in range(8):
        press(["a"], hold=4, wait=15)
    return get_state()


def snapshot() -> Dict[str, Any]:
    """Get game state + screenshot + formatted summary for the LLM.

    Returns dict with keys: state, screenshot_b64, summary
    """
    state_resp = get_state()
    state = state_resp.get("data", {})

    # Get screenshot as base64 PNG
    png_bytes = screenshot()
    screenshot_b64 = base64.b64encode(png_bytes).decode()

    # Build human-readable summary
    lines = []
    pos = state.get("position", {})
    lines.append(f"Location: {pos.get('map_name', '?')} ({pos.get('x')}, {pos.get('y')}) facing {pos.get('facing', '?')}")

    party = state.get("party", [])
    if party:
        for p in party:
            moves_str = ", ".join(
                f"{m['name']}({m['pp']}pp)" for m in p.get("moves", []) if m.get("name", "---") != "---"
            )
            lines.append(f"  {p['name']} Lv{p.get('level','?')} {p['hp']}/{p['max_hp']}HP — {moves_str}")

    if state.get("in_battle"):
        lines.append("IN BATTLE!")
        battle = state.get("battle")
        if battle and battle.get("enemy"):
            e = battle["enemy"]
            lines.append(f"  Enemy: {e.get('name','???')} Lv{e.get('level','?')} {e.get('hp','?')}HP")

    return {
        "state": state,
        "screenshot_b64": screenshot_b64,
        "summary": "\n".join(lines),
    }


def get_quest() -> Dict[str, Any]:
    """Get current quest data from the server."""
    try:
        r = requests.get(f"{SERVER}/api/quest", timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError:
        return {"status": "no_quest"}


def complete_quest_step(lesson: Optional[str] = None) -> Dict[str, Any]:
    """Advance quest step, optionally add a lesson."""
    r = requests.post(f"{SERVER}/api/quest/complete", json={"lesson": lesson}, timeout=10)
    r.raise_for_status()
    return r.json()


def get_knowledge() -> Dict[str, Any]:
    """Get knowledge base from the server."""
    r = requests.get(f"{SERVER}/api/knowledge", timeout=10)
    r.raise_for_status()
    return r.json()


def add_lesson(lesson: str) -> Dict[str, Any]:
    """Add a lesson learned to the knowledge base."""
    r = requests.post(f"{SERVER}/api/knowledge/lesson", json={"lesson": lesson}, timeout=10)
    r.raise_for_status()
    return r.json()


def list_destinations() -> Dict[str, Any]:
    """List available navigation destinations."""
    r = requests.get(f"{SERVER}/api/destinations", timeout=10)
    r.raise_for_status()
    return r.json()


def fight(move_index: int = 0, reasoning: str = "") -> Dict[str, Any]:
    """Execute a battle turn.
    
    Args:
        move_index: 0-3, which move to select (0=top-left, 1=top-right, 2=bottom-left, 3=bottom-right)
        reasoning: Why this move
    
    Returns:
        Game state after the turn
    """
    # Press A to open fight menu
    press(["a"], reasoning=reasoning)
    # Select FIGHT
    press(["a"], hold=6, wait=20)
    # Navigate to the right move
    if move_index == 1:
        press(["right"])
    elif move_index == 2:
        press(["down"])
    elif move_index == 3:
        press(["down", "right"])
    # Select the move
    press(["a"], hold=6, wait=20)
    # Mash through battle animations
    for _ in range(12):
        press(["a"], hold=4, wait=15)
    return get_state()


def navigate(destination: str) -> Dict[str, Any]:
    """Navigate to a named destination using server-side pathfinding.
    
    Args:
        destination: Place name like "Viridian Pokecenter", "Route 1", etc.
                     Special: "nearest_pokecenter" to auto-heal
    """
    r = requests.post(f"{SERVER}/api/navigate", json={
        "destination": destination
    }, timeout=60)
    r.raise_for_status()
    return r.json()


def go_heal() -> Dict[str, Any]:
    """Navigate to nearest Pokemon Center and heal."""
    return navigate("nearest_pokecenter")


def mash_a(times: int = 5, wait: int = 16) -> Dict[str, Any]:
    """Mash A button to advance dialogue."""
    result = None
    for _ in range(times):
        result = press(["a"], hold=4, wait=wait, reasoning="Advancing dialogue")
    return result


def walk(direction: str, steps: int = 1, reasoning: str = "") -> Dict[str, Any]:
    """Walk in a direction for N steps."""
    buttons = [direction.lower()] * steps
    return press(buttons, hold=8, wait=8, reasoning=reasoning or f"Walking {direction} {steps} steps")


# Quick aliases
def up(n=1): return walk("up", n)
def down(n=1): return walk("down", n)
def left(n=1): return walk("left", n)
def right(n=1): return walk("right", n)


if __name__ == "__main__":
    # Quick test
    print("Testing emulator server connection...")
    try:
        state = get_state()
        print(f"Status: {state.get('status')}")
        if state.get("data"):
            pos = state["data"].get("position", {})
            print(f"Location: {pos.get('map_name')} ({pos.get('x')}, {pos.get('y')})")
            party = state["data"].get("party", [])
            for p in party:
                print(f"  {p['name']} Lv{p['level']} [{p['hp']}/{p['max_hp']}]")
        print("✅ Connected!")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print(f"   Is the server running? Start with:")
        print(f"   python scripts/emulator_server.py --save outside_after_parcel")
