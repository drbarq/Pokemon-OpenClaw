---
name: pokemon-red
description: Play Pokemon Red autonomously via PyBoy emulator. The OpenClaw agent IS the player — starts the emulator server, sees screenshots, reads game state from RAM, and makes decisions via HTTP API. Use when an agent wants to play Pokemon Red, battle, explore, grind levels, or compete with other agents. Requires Python 3.10+, pyboy, and a legally obtained Pokemon Red ROM.
---

# Pokemon Red — OpenClaw Skill

The distributable skill is in `skill/`. See `skill/SKILL.md` for full agent instructions.

## Quick Start

```bash
# Install deps
pip install pyboy pillow numpy fastapi uvicorn requests

# Start server
python scripts/emulator_server.py --save ready --port 3456

# Agent plays via HTTP API — no ai_player.py needed
# curl localhost:3456/api/state, /api/screenshot, /api/navigate, /api/press
```

## Repo Structure

```
scripts/
  emulator_server.py  — PyBoy + FastAPI server (the game engine)
  game.py             — Low-level PyBoy wrapper (RAM reading, input)
  navigator.py        — Named-destination pathfinding
  pathfinder.py       — A* on scanned maps
  map_scanner.py      — Offline map scanning tool
skill/
  SKILL.md            — Agent instructions (the skill)
  references/         — Game strategy guide
game_state/
  quest.json          — Quest progress
  knowledge.json      — Lessons learned, map data
  maps/               — Scanned map JSON files (15 maps)
saves/                — Emulator save states
dashboard/            — Retro Game Boy web UI at localhost:3456
```
