"""Pokemon Red Dashboard Server — retro Game Boy UI for watching AI gameplay."""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
GAMEPLAY_LOG = LOGS_DIR / "gameplay.jsonl"
SCREENSHOTS_DIR = LOGS_DIR / "screenshots"
# Fallback: also check project-root screenshots/ (existing structure)
SCREENSHOTS_FALLBACK = PROJECT_ROOT / "screenshots"

app = FastAPI(title="Pokemon Red Dashboard")


def read_last_lines(path: Path, n: int = 1) -> list[str]:
    """Read last N lines from a file efficiently."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    lines = []
    with open(path, "rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        buffer = b""
        while pos > 0 and len(lines) < n + 1:
            chunk = min(8192, pos)
            pos -= chunk
            f.seek(pos)
            buffer = f.read(chunk) + buffer
            lines = buffer.split(b"\n")
    # Filter empty lines, take last N
    result = [l.decode("utf-8", errors="replace") for l in lines if l.strip()]
    return result[-n:]


def parse_log_lines(lines: list[str]) -> list[dict]:
    """Parse JSONL lines into dicts."""
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(html_path.read_text())


@app.get("/api/state")
async def get_state():
    """Return the latest game state entry."""
    lines = read_last_lines(GAMEPLAY_LOG, 1)
    entries = parse_log_lines(lines)
    if not entries:
        return JSONResponse({"status": "waiting", "message": "Waiting for game data..."})
    return JSONResponse({"status": "ok", "data": entries[-1]})


@app.get("/api/history")
async def get_history(limit: int = Query(default=50, ge=1, le=500)):
    """Return last N log entries."""
    lines = read_last_lines(GAMEPLAY_LOG, limit)
    entries = parse_log_lines(lines)
    return JSONResponse({"status": "ok" if entries else "waiting", "data": entries})


@app.get("/api/screenshot/{filename}")
async def get_screenshot(filename: str):
    """Serve a screenshot image."""
    # Check logs/screenshots first, then fallback to project screenshots/
    path = SCREENSHOTS_DIR / filename
    if not path.exists():
        path = SCREENSHOTS_FALLBACK / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="image/png")


@app.get("/api/latest-screenshot")
async def get_latest_screenshot():
    """Serve the most recent screenshot. Prefers latest.png if it exists."""
    # Check for dedicated latest.png first (updated every execute)
    latest_file = SCREENSHOTS_DIR / "latest.png"
    if latest_file.exists():
        return FileResponse(latest_file, media_type="image/png",
                          headers={"Cache-Control": "no-cache, no-store"})
    
    # Fallback: find most recent by mtime
    screenshots = []
    for d in [SCREENSHOTS_DIR, SCREENSHOTS_FALLBACK]:
        if d.exists():
            screenshots.extend(d.glob("*.png"))
    if not screenshots:
        return JSONResponse({"error": "no screenshots"}, status_code=404)
    latest = max(screenshots, key=lambda p: p.stat().st_mtime)
    return FileResponse(latest, media_type="image/png",
                      headers={"Cache-Control": "no-cache, no-store"})


@app.get("/api/screenshots")
async def list_screenshots():
    """List available screenshots."""
    screenshots = []
    for d in [SCREENSHOTS_DIR, SCREENSHOTS_FALLBACK]:
        if d.exists():
            for p in d.glob("*.png"):
                screenshots.append({"name": p.name, "mtime": p.stat().st_mtime})
    screenshots.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"data": screenshots[:50]})


if __name__ == "__main__":
    import uvicorn
    print("🎮 Pokemon Red Dashboard starting on http://localhost:3456")
    uvicorn.run(app, host="0.0.0.0", port=3456)
