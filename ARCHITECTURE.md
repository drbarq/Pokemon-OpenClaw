# ARCHITECTURE.md — Pokemon Red AI Player

## Project Root: `~/Code/pokemon-openclaw/`

## How It Works (The Full Picture)

### Three layers:
1. **Emulator Server** — Persistent PyBoy running in background, streaming video, accepting HTTP commands
2. **Navigation System** — Pre-scanned maps + A* pathfinding so the AI doesn't waste time finding doors
3. **AI Player** — A sub-agent (spawned from OpenClaw) that reads game state, makes decisions, and sends commands

### Flow:
```
[Sub-Agent AI Brain]
    │
    │  HTTP calls (press buttons, get state, navigate)
    ▼
[Emulator Server - localhost:3456]
    │
    │  Runs PyBoy in background thread
    │  Streams MJPEG video to dashboard
    │  Executes button presses
    │  Reads RAM for game state
    ▼
[PyBoy Emulator]
    │
    │  Pokemon Red ROM
    ▼
[Dashboard - localhost:3456]
    │  Live Game Boy video stream
    │  Activity feed from gameplay.jsonl
    │  Party/state info from /api/state
```

---

## File Map

### Core Scripts (what actually runs)

| File | Purpose |
|------|---------|
| `scripts/emulator_server.py` | **THE SERVER.** Persistent FastAPI app that runs PyBoy, streams MJPEG, accepts commands. Start with: `python scripts/emulator_server.py --save ready --port 3456` |
| `scripts/llm_client.py` | **AI CLIENT.** Python library the sub-agent uses to control the server. `from scripts.llm_client import *` then `press()`, `navigate()`, `fight()`, `get_state()`, etc. |
| `scripts/game.py` | **PyBoy wrapper.** Low-level: button presses, RAM reading, screenshots. Used by emulator_server internally. |
| `scripts/pathfinder.py` | **A* pathfinding.** Reads map JSONs, computes shortest paths. `find_path()`, `find_route()` for cross-map routing. |
| `scripts/navigator.py` | **High-level navigation.** Named destinations ("Viridian Pokecenter"), wraps pathfinder + executes button sequences. |
| `scripts/map_scanner.py` | **Map scanner.** BFS flood-fill that discovers walkable tiles and doors. Run once per map, saves JSON. |

### Legacy Scripts (from earlier iterations, NOT used by current system)

| File | Purpose | Status |
|------|---------|--------|
| `scripts/llm_player.py` | Old AI player that ran PyBoy directly (not via server) | **DEPRECATED** — use `llm_client.py` instead |
| `scripts/play_session.py` | Old file-polling approach for AI decisions | **DEPRECATED** |
| `scripts/play_manual.py` | Manual keyboard play | Still works standalone |
| `scripts/grind_route1.py` | Hardcoded Route 1 grinding | **DEPRECATED** |
| `scripts/grind_v2.py` | Improved grinding script | **DEPRECATED** |
| `scripts/play_step.py` | Single-step play | **DEPRECATED** |
| `dashboard/server.py` | Old dashboard server (replaced by emulator_server) | **DEPRECATED** |

### Dashboard

| File | Purpose |
|------|---------|
| `dashboard/index.html` | Dashboard UI. Served by emulator_server at `/`. Game Boy retro theme, MJPEG stream, activity feed, party info, stats. |

### Game State

| File | Purpose |
|------|---------|
| `game_state/STRATEGY_GUIDE.md` | **72KB comprehensive guide.** Team recs, route plan, gym strategies, hidden items, grinding spots, secrets, Moltbook moments. THE AI SHOULD READ THIS. |
| `game_state/quest.json` | Quest tracker. Current objective, step index, lessons learned, map knowledge. AI updates this as it progresses. |
| `game_state/knowledge.json` | Persistent knowledge base. Door coordinates, map transitions, movement lessons. |
| `game_state/maps/*.json` | **15 pre-scanned map files.** Each contains walkable tile grid, wall locations, warp/door locations. Used by pathfinder. |

### Map Files (in `game_state/maps/`)

| Map File | Tiles | Notable Warps |
|----------|-------|---------------|
| `pallet_town.json` | 204 | Oak's Lab, Player's House, Rival's House, Route 1 exits |
| `oaks_lab.json` | 79 | Exit to Pallet Town |
| `players_house_1f.json` | 47 | Exit, stairs to 2F |
| `players_house_2f.json` | 47 | Stairs to 1F |
| `rivals_house.json` | 44 | Exit to Pallet Town |
| `route_1.json` | 350 | Pallet Town south, Viridian City north |
| `viridian_city.json` | 601 | Pokecenter, Mart, Gym, Route 1 south, Route 2 north, Route 22 west |
| `viridian_pokecenter.json` | 54 | Exit to Viridian City |
| `viridian_mart.json` | 30 | Exit to Viridian City |
| `viridian_school.json` | 45 | Exit |
| `viridian_house.json` | 42 | Exit |
| `route_2.json` | 244 | Viridian City south, Viridian Forest north |
| `route_22.json` | 148 | Viridian City east |
| `unknown_0x32.json` | 48 | Viridian Forest Gate |
| `unknown_0x33.json` | 676 | Viridian Forest |

### Save States (in `saves/`)

| Save | Description |
|------|-------------|
| `ready.state` | **FRESH START.** Squirtle Lv6, 21/21 HP, Pallet Town (9,13). Right after picking Squirtle and beating rival. |
| `outside_after_parcel.state` | After delivering Oak's Parcel. Pokedex obtained. Pallet Town. |
| `progress_22.state` | Squirtle Lv10, Bubble learned, Route 1. |
| Various `llm_*.state` | Auto-saves from previous play sessions. |

### Other Docs

| File | Purpose |
|------|---------|
| `README.md` | Project overview and setup instructions |
| `PROJECT_PLAN.md` | Original project plan |
| `RESEARCH.md` | Research notes from building this |
| `SKILL.md` | OpenClaw skill definition (for publishing to ClawdHub) |
| `skill/SKILL.md` | Duplicate skill file |

### Logs (in `logs/`)

| File | Purpose |
|------|---------|
| `logs/gameplay.jsonl` | **Activity log.** One JSON line per decision. Dashboard reads this for the activity feed. |
| `logs/server.log` | Emulator server stdout/stderr |
| `logs/screenshots/` | Screenshots from gameplay (latest.png updated by server) |
| `logs/archive/` | Archived logs from previous sessions |

---

## How to Start Everything

### 1. Start the emulator server
```bash
cd ~/Code/pokemon-openclaw
source .venv/bin/activate
nohup python scripts/emulator_server.py --save ready --port 3456 > logs/server.log 2>&1 &
```
Dashboard at http://localhost:3456 — live MJPEG video + activity feed.

### 2. Start an AI player (from OpenClaw)
Spawn a sub-agent that uses `scripts/llm_client.py` to send commands:
```python
from scripts.llm_client import *

state = get_state()          # Read game state
press(["up","a"])             # Press buttons  
navigate("Viridian Mart")    # A* pathfinding
fight(move_index=0)           # Battle
go_heal()                     # Find Pokecenter and heal
save("checkpoint_01")         # Save state
screenshot("current.png")    # Capture frame
```

### 3. Scan new maps (when entering unmapped areas)
```bash
python scripts/map_scanner.py --save current_save_name --chain
```

---

## What SHOULD Happen (Expected Behavior)

### The AI player sub-agent should:
1. **Read the strategy guide** (`game_state/STRATEGY_GUIDE.md`) for the current game phase
2. **Use `navigate()`** for all movement — NOT manual button presses for walking
3. **Use `fight()`** for battles — handles menu navigation automatically
4. **Use `go_heal()`** when HP is low
5. **Check `get_state()`** frequently to know position, HP, battle status
6. **Look at screenshots** (via image tool) to understand what's on screen when stuck
7. **Save regularly** with `save("progress_XX")`
8. **Update quest.json** when completing objectives
9. **Log interesting moments** in reasoning strings for the dashboard/Moltbook

### The emulator server should:
1. Run PyBoy continuously, ticking at ~60fps
2. Stream MJPEG video at ~15fps to the dashboard
3. Execute button presses synchronously (returns state after press completes)
4. Log every button press to `gameplay.jsonl`
5. Not crash (currently sometimes dies under load — needs investigation)

### The dashboard should:
1. Show live Game Boy video via `<img src="/stream">`
2. Show current party with HP bars and moves
3. Show activity feed with color-coded actions
4. Show stats (decisions, battles, level, maps visited)
5. Auto-update every 1.5 seconds

### Known Issues
- Emulator server sometimes gets SIGKILL'd — run with `nohup` and monitor
- `navigate()` may fail on unmapped areas — need to scan first
- Battle detection can be flaky — the AI should check `in_battle` in state
- Move names show as "Move_91" instead of "Bubble" — RAM name lookup incomplete
- The AI sub-agent sometimes tries interactive Python (pty) which gets killed — must use one-shot scripts
- Quest.json needs manual reset when starting from a different save

### What's NOT Built Yet
- Moltbook integration (their API was down)
- ClawdHub skill publishing (ClawdHub CLI is fixed, just haven't published yet)
- Automatic respawn of AI player when sub-agent times out
- Pokemon catching logic (we only have fight/run, no ball throwing)
- Team management (switching Pokemon, using items)
