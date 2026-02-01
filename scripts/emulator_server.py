#!/usr/bin/env python3
"""
Pokemon Red — Persistent Emulator Server

Single FastAPI server that:
- Runs PyBoy in a background thread, continuously ticking
- Streams frames as MJPEG to the dashboard
- Accepts button presses via HTTP POST
- Reads game state via HTTP GET
- Serves the dashboard HTML
- Handles save/load commands

Usage:
    python scripts/emulator_server.py --save outside_after_parcel --port 3456
"""

import argparse
import io
import json
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse, FileResponse

# Add scripts dir to path so we can import game, pathfinder, etc.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from game import PokemonGame, MAP_NAMES

PROJECT_ROOT = SCRIPT_DIR.parent
ROM_PATH = PROJECT_ROOT / "PokemonRed.gb"
SAVES_DIR = PROJECT_ROOT / "saves"
LOGS_DIR = PROJECT_ROOT / "logs"
GAMEPLAY_LOG = LOGS_DIR / "gameplay.jsonl"
SCREENSHOTS_DIR = LOGS_DIR / "screenshots"
DASHBOARD_HTML = PROJECT_ROOT / "dashboard" / "index.html"
MAPS_DIR = PROJECT_ROOT / "game_state" / "maps"

# Ensure directories exist
LOGS_DIR.mkdir(exist_ok=True)
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# ============================================================
# Emulator Manager — runs PyBoy in a background thread
# ============================================================

class EmulatorManager:
    """Thread-safe wrapper around PokemonGame that runs continuously."""

    def __init__(self, rom_path: str, save_name: Optional[str] = None, turbo: bool = False):
        self.game = PokemonGame(
            rom_path=rom_path,
            headless=True,
            speed=0 if turbo else 1,
            save_dir=str(SAVES_DIR),
            screenshot_dir=str(SCREENSHOTS_DIR),
        )
        self.save_name = save_name
        self.turbo = turbo

        # Thread safety
        self.lock = threading.Lock()
        self.button_queue: Queue = Queue()
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Shared frame buffer (JPEG bytes)
        self.frame_lock = threading.Lock()
        self.current_frame: Optional[bytes] = None
        self.frame_event = threading.Event()
        self.frame_counter = 0

        # Cached state
        self.state_lock = threading.Lock()
        self.cached_state: Dict[str, Any] = {}
        self.state_counter = 0

        # Decision counter for logging
        self.decision_counter = 0

        # Speed control
        self.target_fps = 60
        self.frame_capture_interval = 4  # Capture every N frames for MJPEG

    def start(self) -> bool:
        """Start the emulator and background thread."""
        if not self.game.start():
            return False

        if self.save_name:
            if not self.game.load_state(self.save_name):
                print(f"Warning: Could not load save '{self.save_name}', starting fresh")

        # Initial tick to render first frame
        self.game.tick(1)
        self._capture_frame()
        self._update_state()

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print(f"🎮 Emulator thread started (turbo={self.turbo})")
        return True

    def stop(self):
        """Stop the emulator thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.game.stop()
        print("🛑 Emulator stopped")

    def _run_loop(self):
        """Main emulator loop — runs in background thread."""
        tick_count = 0
        last_time = time.monotonic()

        while self.running:
            # Process button queue
            self._process_buttons()

            # Tick the emulator
            with self.lock:
                try:
                    self.game.tick(1, render=True)
                except Exception as e:
                    print(f"Tick error: {e}")
                    time.sleep(0.01)
                    continue

            tick_count += 1

            # Capture frame periodically (every N ticks for ~15fps MJPEG)
            if tick_count % self.frame_capture_interval == 0:
                self._capture_frame()

            # Update state less frequently (every 15 ticks)
            if tick_count % 15 == 0:
                self._update_state()

            # Frame pacing (only when not in turbo mode)
            if not self.turbo:
                target_dt = 1.0 / self.target_fps
                now = time.monotonic()
                elapsed = now - last_time
                if elapsed < target_dt:
                    time.sleep(target_dt - elapsed)
                last_time = time.monotonic()

    def _process_buttons(self):
        """Drain button queue and execute presses.
        
        If a battle triggers mid-navigation, flush remaining queued commands
        so the agent can handle the battle before continuing.
        """
        try:
            while True:
                cmd = self.button_queue.get_nowait()
                buttons = cmd.get("buttons", [])
                hold = cmd.get("hold", 8)
                wait = cmd.get("wait", 16)
                reasoning = cmd.get("reasoning", "")

                # Check if we were NOT in battle before this command
                with self.lock:
                    was_in_battle = self.game.get_full_state().get("in_battle", False)

                # Record state before action
                with self.lock:
                    before_state = self.game.get_player_position()

                # Execute button presses
                with self.lock:
                    self.game.press_buttons(buttons, hold_frames=hold, wait_frames=wait)

                # Capture frame after action
                self._capture_frame()

                # Record state after action
                with self.lock:
                    after_state = self.game.get_full_state()

                # If a battle just started, flush the remaining queue
                # so the agent can detect and handle the battle
                if not was_in_battle and after_state.get("in_battle", False):
                    flushed = 0
                    try:
                        while True:
                            flushed_cmd = self.button_queue.get_nowait()
                            # Signal flushed commands as complete so sync callers don't hang
                            fe = flushed_cmd.get("_done_event")
                            if fe:
                                flushed_cmd["_result"] = after_state
                                fe.set()
                            flushed += 1
                    except Empty:
                        pass
                    if flushed > 0:
                        print(f"  ⚔️ Battle detected! Flushed {flushed} queued commands")

                # Log the action
                self._log_action(buttons, hold, wait, reasoning, before_state, after_state)

                # Signal command complete
                done_event = cmd.get("_done_event")
                if done_event:
                    cmd["_result"] = after_state
                    done_event.set()

        except Empty:
            pass

    def _capture_frame(self):
        """Capture current screen as JPEG and store in shared buffer."""
        try:
            with self.lock:
                img = self.game.pyboy.screen.image

            # Scale from 160x144 to 480x432
            img = img.resize((480, 432), resample=0)  # NEAREST for pixel art

            # Convert RGBA to RGB for JPEG compatibility
            if img.mode == "RGBA":
                img = img.convert("RGB")

            # Convert to JPEG
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            jpeg_bytes = buf.getvalue()

            with self.frame_lock:
                self.current_frame = jpeg_bytes
                self.frame_counter += 1

            # Signal new frame available
            self.frame_event.set()
            self.frame_event.clear()

        except Exception as e:
            print(f"Frame capture error: {e}")

    def _update_state(self):
        """Update cached game state."""
        try:
            with self.lock:
                state = self.game.get_full_state()
            with self.state_lock:
                self.cached_state = state
                self.state_counter += 1
        except Exception as e:
            print(f"State update error: {e}")

    def _log_action(self, buttons, hold, wait, reasoning, before, after):
        """Write action to gameplay.jsonl."""
        self.decision_counter += 1
        pos = after.get("position", {})
        entry = {
            "decision": self.decision_counter,
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": ", ".join(buttons),
            "reasoning": reasoning,
            "before": {
                "x": before.get("x"),
                "y": before.get("y"),
                "map": before.get("map_name", ""),
            },
            "position": pos,
            "moved": (before.get("x") != pos.get("x") or before.get("y") != pos.get("y")
                      or before.get("map_name") != pos.get("map_name")),
            "in_battle": after.get("in_battle", False),
            "battle": after.get("battle"),
            "party_hp": [
                {"name": p["name"], "hp": p["hp"], "max_hp": p["max_hp"],
                 "level": p["level"], "moves": [m["name"] for m in p.get("moves", [])]}
                for p in after.get("party", [])
            ],
            "screenshot": f"decision_{self.decision_counter:04d}.png",
        }

        try:
            with open(GAMEPLAY_LOG, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"Log write error: {e}")

        # Save screenshot
        try:
            with self.lock:
                img = self.game.pyboy.screen.image
            img_path = SCREENSHOTS_DIR / f"decision_{self.decision_counter:04d}.png"
            img.save(str(img_path))
            # Also save as latest.png
            latest_path = SCREENSHOTS_DIR / "latest.png"
            img.save(str(latest_path))
        except Exception as e:
            print(f"Screenshot save error: {e}")

    def get_frame(self) -> Optional[bytes]:
        """Get current JPEG frame."""
        with self.frame_lock:
            return self.current_frame

    def get_state(self) -> Dict[str, Any]:
        """Get cached game state."""
        with self.state_lock:
            return dict(self.cached_state)

    def get_fresh_state(self) -> Dict[str, Any]:
        """Force a fresh state read."""
        self._update_state()
        return self.get_state()

    def get_screenshot_png(self) -> bytes:
        """Get current screen as PNG bytes."""
        with self.lock:
            img = self.game.pyboy.screen.image
        img = img.resize((480, 432), resample=0)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def press_buttons(self, buttons: List[str], hold: int = 8, wait: int = 16,
                      reasoning: str = "", sync: bool = True) -> Dict[str, Any]:
        """Queue button presses. If sync=True, wait for completion."""
        done_event = threading.Event() if sync else None
        cmd = {
            "buttons": buttons,
            "hold": hold,
            "wait": wait,
            "reasoning": reasoning,
            "_done_event": done_event,
            "_result": None,
        }
        self.button_queue.put(cmd)

        if sync and done_event:
            done_event.wait(timeout=30)
            return cmd.get("_result", {})
        return {"status": "queued"}

    def save_state(self, name: str) -> bool:
        """Save emulator state."""
        try:
            with self.lock:
                self.game.save_state(name)
            return True
        except Exception as e:
            print(f"Save error: {e}")
            return False

    def load_state(self, name: str) -> bool:
        """Load emulator state."""
        try:
            with self.lock:
                result = self.game.load_state(name)
            if result:
                self._capture_frame()
                self._update_state()
            return result
        except Exception as e:
            print(f"Load error: {e}")
            return False

    def set_speed(self, turbo: bool):
        """Toggle turbo mode."""
        self.turbo = turbo
        with self.lock:
            self.game.pyboy.set_emulation_speed(0 if turbo else 1)


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(title="Pokemon Red Emulator Server")
emu: Optional[EmulatorManager] = None


# --- Dashboard ---

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve dashboard HTML."""
    if DASHBOARD_HTML.exists():
        return HTMLResponse(DASHBOARD_HTML.read_text())
    return HTMLResponse("<h1>Dashboard not found</h1>")


# --- MJPEG Stream ---

@app.get("/stream")
async def mjpeg_stream():
    """Stream Game Boy frames as MJPEG."""
    def generate():
        last_counter = -1
        while True:
            if emu is None:
                time.sleep(0.1)
                continue

            frame = emu.get_frame()
            if frame and emu.frame_counter != last_counter:
                last_counter = emu.frame_counter
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame
                    + b"\r\n"
                )
            time.sleep(1.0 / 15)  # ~15fps

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# --- API Endpoints ---

@app.get("/api/state")
async def api_state():
    """Return current game state."""
    if emu is None:
        return JSONResponse({"status": "not_running"}, status_code=503)
    state = emu.get_state()
    return JSONResponse({"status": "ok", "data": state})


@app.get("/api/screenshot")
async def api_screenshot():
    """Return current screen as PNG."""
    if emu is None:
        return JSONResponse({"status": "not_running"}, status_code=503)
    png_bytes = emu.get_screenshot_png()
    return Response(content=png_bytes, media_type="image/png",
                    headers={"Cache-Control": "no-cache, no-store"})


@app.get("/api/latest-screenshot")
async def api_latest_screenshot():
    """Alias for /api/screenshot with no-cache headers."""
    return await api_screenshot()


@app.post("/api/press")
async def api_press(request: Request):
    """Execute button presses on the emulator.
    
    Body: {"buttons": ["up","up","a"], "hold": 8, "wait": 16, "reasoning": "..."}
    """
    if emu is None:
        return JSONResponse({"status": "not_running"}, status_code=503)

    body = await request.json()
    buttons = body.get("buttons", [])
    hold = body.get("hold", 8)
    wait = body.get("wait", 16)
    reasoning = body.get("reasoning", "")

    if not buttons:
        return JSONResponse({"status": "error", "message": "No buttons provided"}, status_code=400)

    # Validate buttons
    valid = {"up", "down", "left", "right", "a", "b", "start", "select"}
    for b in buttons:
        if b.lower() not in valid:
            return JSONResponse({"status": "error", "message": f"Invalid button: {b}"}, status_code=400)

    result = emu.press_buttons(
        [b.lower() for b in buttons],
        hold=hold, wait=wait, reasoning=reasoning, sync=True
    )
    return JSONResponse({"status": "ok", "state": result})


@app.post("/api/command")
async def api_command(request: Request):
    """Execute a command (save/load/speed).
    
    Body: {"command": "save", "name": "checkpoint"}
          {"command": "load", "name": "checkpoint"}
          {"command": "speed", "turbo": true}
    """
    if emu is None:
        return JSONResponse({"status": "not_running"}, status_code=503)

    body = await request.json()
    cmd = body.get("command", "")

    if cmd == "save":
        name = body.get("name", "quicksave")
        ok = emu.save_state(name)
        return JSONResponse({"status": "ok" if ok else "error", "save": name})

    elif cmd == "load":
        name = body.get("name", "quicksave")
        ok = emu.load_state(name)
        return JSONResponse({"status": "ok" if ok else "error", "save": name})

    elif cmd == "speed":
        turbo = body.get("turbo", False)
        emu.set_speed(turbo)
        return JSONResponse({"status": "ok", "turbo": turbo})

    else:
        return JSONResponse({"status": "error", "message": f"Unknown command: {cmd}"}, status_code=400)


@app.get("/api/history")
async def api_history(limit: int = Query(default=50, ge=1, le=500)):
    """Return last N gameplay log entries."""
    if not GAMEPLAY_LOG.exists() or GAMEPLAY_LOG.stat().st_size == 0:
        return JSONResponse({"status": "waiting", "data": []})

    lines = []
    try:
        with open(GAMEPLAY_LOG, "rb") as f:
            f.seek(0, 2)
            pos = f.tell()
            buffer = b""
            while pos > 0 and len(lines) < limit + 1:
                chunk = min(8192, pos)
                pos -= chunk
                f.seek(pos)
                buffer = f.read(chunk) + buffer
                lines = buffer.split(b"\n")
        result = [l.decode("utf-8", errors="replace") for l in lines if l.strip()]
        result = result[-limit:]
    except Exception:
        result = []

    entries = []
    for line in result:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return JSONResponse({"status": "ok" if entries else "waiting", "data": entries})


QUEST_FILE = PROJECT_ROOT / "game_state" / "quest.json"
KNOWLEDGE_FILE = PROJECT_ROOT / "game_state" / "knowledge.json"


@app.get("/api/quest")
async def api_quest():
    """Return current quest data from game_state/quest.json."""
    if not QUEST_FILE.exists():
        return JSONResponse({"status": "no_quest"}, status_code=404)
    try:
        data = json.loads(QUEST_FILE.read_text())
        return JSONResponse({"status": "ok", "data": data})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/quest/complete")
async def api_quest_complete(request: Request):
    """Advance quest step, optionally add a lesson learned.

    Body: {"lesson": "optional lesson text"}
    """
    if not QUEST_FILE.exists():
        return JSONResponse({"status": "no_quest"}, status_code=404)

    body = await request.json()
    lesson = body.get("lesson")

    try:
        q = json.loads(QUEST_FILE.read_text())
        current_id = q["current_quest"]
        step_idx = q["quest_step"]

        for quest in q["quest_log"]:
            if quest["id"] == current_id:
                if step_idx < len(quest["steps"]):
                    quest["steps"][step_idx]["done"] = True
                q["quest_step"] = step_idx + 1

                # If quest is complete, advance to next quest
                if q["quest_step"] >= len(quest["steps"]):
                    idx = next(i for i, qst in enumerate(q["quest_log"]) if qst["id"] == current_id)
                    if idx + 1 < len(q["quest_log"]):
                        q["current_quest"] = q["quest_log"][idx + 1]["id"]
                        q["quest_step"] = 0
                break

        if lesson:
            q.setdefault("lessons_learned", []).append(lesson)

        QUEST_FILE.write_text(json.dumps(q, indent=2))
        return JSONResponse({"status": "ok", "data": q})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/api/knowledge")
async def api_knowledge():
    """Return knowledge.json contents."""
    if not KNOWLEDGE_FILE.exists():
        return JSONResponse({"status": "ok", "data": {}})
    try:
        data = json.loads(KNOWLEDGE_FILE.read_text())
        return JSONResponse({"status": "ok", "data": data})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/knowledge/lesson")
async def api_knowledge_lesson(request: Request):
    """Add a lesson learned to knowledge.json.

    Body: {"lesson": "text"}
    """
    body = await request.json()
    lesson = body.get("lesson", "")
    if not lesson:
        return JSONResponse({"status": "error", "message": "No lesson provided"}, status_code=400)

    try:
        k = json.loads(KNOWLEDGE_FILE.read_text()) if KNOWLEDGE_FILE.exists() else {}
        k.setdefault("lessons_learned", []).append(lesson)
        KNOWLEDGE_FILE.write_text(json.dumps(k, indent=2))

        # Also add to quest file for backwards compat
        if QUEST_FILE.exists():
            q = json.loads(QUEST_FILE.read_text())
            q.setdefault("lessons_learned", []).append(lesson)
            QUEST_FILE.write_text(json.dumps(q, indent=2))

        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/api/destinations")
async def api_destinations():
    """List available navigation destinations."""
    try:
        from navigator import DESTINATIONS
        dests = {name: {"map": m, "x": x, "y": y} for name, (m, x, y) in DESTINATIONS.items()}
        return JSONResponse({"status": "ok", "data": dests})
    except ImportError:
        return JSONResponse({"status": "error", "message": "Navigator not available"}, status_code=500)


@app.get("/api/maps")
async def api_maps():
    """List which maps have been scanned (pathfinding available)."""
    scanned = []
    if MAPS_DIR.exists():
        for p in sorted(MAPS_DIR.glob("*.json")):
            name = p.stem.replace("_", " ").title()
            try:
                data = json.loads(p.read_text())
                tiles = len(data.get("walkable", []))
                warps = len(data.get("warps", []))
                scanned.append({"file": p.name, "name": name, "tiles": tiles, "warps": warps})
            except Exception:
                scanned.append({"file": p.name, "name": name, "tiles": 0, "warps": 0})
    return JSONResponse({"status": "ok", "count": len(scanned), "maps": scanned})


@app.get("/api/screenshot/{filename}")
async def api_screenshot_file(filename: str):
    """Serve a specific screenshot by filename."""
    path = SCREENSHOTS_DIR / filename
    if not path.exists():
        # Fallback to project screenshots dir
        path = PROJECT_ROOT / "screenshots" / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="image/png")


@app.get("/api/screenshots")
async def api_screenshots_list():
    """List available screenshots."""
    screenshots = []
    for d in [SCREENSHOTS_DIR, PROJECT_ROOT / "screenshots"]:
        if d.exists():
            for p in d.glob("*.png"):
                screenshots.append({"name": p.name, "mtime": p.stat().st_mtime})
    screenshots.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"data": screenshots[:50]})


def _resolve_destination(destination: str):
    """Resolve a destination name to (map, x, y). Returns None on failure."""
    try:
        from navigator import DESTINATIONS
    except ImportError:
        DESTINATIONS = {}
    
    dest_lower = destination.lower().strip()
    if dest_lower in DESTINATIONS:
        return DESTINATIONS[dest_lower]
    
    # Fuzzy match
    matches = [k for k in DESTINATIONS if dest_lower in k or k in dest_lower]
    if matches:
        return DESTINATIONS[matches[0]]
    
    # Legacy fallback
    known = {
        "nearest_pokecenter": ("Viridian City", 23, 26),
        "viridian_pokecenter": ("Viridian City", 23, 26),
        "oak_lab": ("Pallet Town", 12, 12),
        "pallet_town": ("Pallet Town", 9, 12),
        "viridian_city": ("Viridian City", 20, 17),
        "pewter_city": ("Pewter City", 15, 12),
        "route_1": ("Pallet Town", 10, 0),
        "route_2": ("Route 2", 3, 15),
    }
    key = destination.lower().replace(" ", "_")
    if key in known:
        return known[key]
    
    return None


def _navigate_sync(destination: str) -> dict:
    """Synchronous navigate implementation — runs in threadpool."""
    from pathfinder import find_route

    resolved = _resolve_destination(destination)
    if not resolved:
        try:
            from navigator import DESTINATIONS
            known = sorted(DESTINATIONS.keys())
        except ImportError:
            known = []
        return {"status": "error", "message": f"Unknown destination '{destination}'. Known: {known}"}

    dest_map, dest_x, dest_y = resolved
    state = emu.get_fresh_state()
    pos = state.get("position", {})
    current_map = pos.get("map_name", "")
    x, y = pos.get("x", 0), pos.get("y", 0)

    try:
        route = find_route(current_map, x, y, dest_map, dest_x, dest_y)
    except Exception as e:
        return {"status": "error", "message": f"Pathfinding error: {e}"}

    if not route:
        return {"status": "error", "message": f"No route from {current_map} ({x},{y}) to {dest_map} ({dest_x},{dest_y})"}

    try:
        total_steps = sum(len(steps) for _, steps in route)
        steps_taken = 0

        for map_name, steps in route:
            if not steps:
                continue
            for step in steps:
                emu.press_buttons([step], hold=8, wait=16, reasoning=f"Navigate: {map_name} → {dest_map}", sync=True)
                steps_taken += 1

                fresh = emu.get_fresh_state()
                if fresh.get("in_battle", False):
                    return {
                        "status": "battle",
                        "message": f"Wild encounter after {steps_taken}/{total_steps} steps!",
                        "steps_taken": steps_taken,
                        "steps_remaining": total_steps - steps_taken,
                        "destination": destination,
                        "state": fresh,
                    }

        final = emu.get_fresh_state()
        final_pos = final.get("position", {})
        final_map = final_pos.get("map_name", "")

        if final_map == dest_map:
            return {
                "status": "arrived",
                "message": f"Arrived at {dest_map}! ({final_pos.get('x')},{final_pos.get('y')})",
                "steps_taken": steps_taken,
                "state": final,
            }
        else:
            return {
                "status": "stuck",
                "message": f"Navigation ended at {final_map} ({final_pos.get('x')},{final_pos.get('y')}) instead of {dest_map}",
                "steps_taken": steps_taken,
                "state": final,
            }
    except Exception as e:
        return {"status": "error", "message": f"Navigation error: {str(e)}"}


@app.get("/api/route")
async def api_route(request: Request):
    """Ask the pathfinder for directions. Returns step-by-step route from current position.
    
    Query params: ?destination=Viridian City
    
    Returns the next steps as a list of button presses. The LLM executes one at a time.
    """
    if emu is None:
        return JSONResponse({"status": "not_running"}, status_code=503)

    destination = request.query_params.get("destination", "")
    if not destination:
        return JSONResponse({"status": "error", "message": "No destination"}, status_code=400)

    try:
        from pathfinder import find_route
    except ImportError:
        return JSONResponse({"status": "error", "message": "Pathfinder not available"}, status_code=500)

    resolved = _resolve_destination(destination)
    if not resolved:
        try:
            from navigator import DESTINATIONS
            known = sorted(DESTINATIONS.keys())
        except ImportError:
            known = []
        return JSONResponse({"status": "error", "message": f"Unknown destination '{destination}'. Known: {known}"})

    dest_map, dest_x, dest_y = resolved
    state = emu.get_fresh_state()
    pos = state.get("position", {})
    current_map = pos.get("map_name", "")
    x, y = pos.get("x", 0), pos.get("y", 0)

    try:
        route = find_route(current_map, x, y, dest_map, dest_x, dest_y)
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Pathfinding error: {e}"})

    if not route:
        return JSONResponse({"status": "error", "message": f"No route from {current_map} ({x},{y}) to {dest_map} ({dest_x},{dest_y})"})

    # Flatten into a single step list with map annotations
    all_steps = []
    for map_name, steps in route:
        all_steps.extend(steps)

    return JSONResponse({
        "status": "ok",
        "from": {"map": current_map, "x": x, "y": y},
        "to": {"map": dest_map, "x": dest_x, "y": dest_y},
        "steps": all_steps,
        "total": len(all_steps),
        "segments": [{"map": m, "steps": len(s)} for m, s in route],
    })

# Startup
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Pokemon Red Emulator Server")
    parser.add_argument("--port", type=int, default=3456, help="Server port")
    parser.add_argument("--save", type=str, default=None, help="Save state to load on startup")
    parser.add_argument("--turbo", action="store_true", help="Run emulator at max speed")
    parser.add_argument("--rom", type=str, default=str(ROM_PATH), help="Path to ROM file")
    args = parser.parse_args()

    global emu
    print(f"🎮 Starting Pokemon Red Emulator Server")
    print(f"   ROM: {args.rom}")
    print(f"   Save: {args.save or 'none'}")
    print(f"   Port: {args.port}")
    print(f"   Turbo: {args.turbo}")

    emu = EmulatorManager(
        rom_path=args.rom,
        save_name=args.save,
        turbo=args.turbo,
    )

    if not emu.start():
        print("❌ Failed to start emulator")
        sys.exit(1)

    print(f"✅ Emulator running! Dashboard: http://localhost:{args.port}")

    try:
        uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
    finally:
        emu.stop()


if __name__ == "__main__":
    main()
