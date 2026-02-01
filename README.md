# 🎮 Pokemon OpenClaw

**AI agents play Pokemon Red autonomously.** The agent IS the player — no middleman scripts, no separate API calls. Your OpenClaw agent starts the emulator server, sees the screen, reads game state from RAM, and decides what to do.

Published on [ClawdHub](https://clawdhub.com) as `pokemon-red` — install the skill and play.

## How It Works

```
┌──────────────────────────────────────────────┐
│            OpenClaw Agent (You)               │
│                                               │
│  curl /api/screenshot → image tool → decide   │
│  curl /api/navigate  → pathfinding            │
│  curl /api/press     → manual controls        │
│  curl /api/state     → HP, position, battle   │
└──────────────┬───────────────────┬────────────┘
               │  HTTP API         │
        ┌──────┴───────────────────┴──────┐
        │     Emulator Server (PyBoy)      │
        │                                  │
        │  • Pokemon Red ROM (you provide) │
        │  • RAM reading → structured JSON │
        │  • A* pathfinding on scanned maps│
        │  • Screenshot capture            │
        │  • Save/load states              │
        │  • Live dashboard at :3456       │
        └──────────────────────────────────┘
```

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/drbarq/Pokemon-OpenClaw.git
cd Pokemon-OpenClaw
pip install pyboy pillow numpy fastapi uvicorn requests
```

### 2. Add your ROM

Place a legally obtained Pokemon Red ROM at `./PokemonRed.gb`

### 3. Start the emulator server

```bash
python scripts/emulator_server.py --save ready --port 3456
```

Dashboard at http://localhost:3456

### 4. Install the skill

```bash
clawdhub install pokemon-red
```

Or point your agent at `skill/SKILL.md` in this repo.

### 5. Play

Your agent plays via HTTP API. The skill teaches it the full loop:
- **Navigate** to destinations with pathfinding
- **Battle** wild Pokemon and trainers
- **Track quests** and learn lessons
- **Save progress** between sessions

## For OpenClaw Agents

The skill (`skill/SKILL.md`) has everything you need:
- Start the server, check destinations, use navigate for travel
- Fall back to manual buttons for menus and interactions
- Battle strategy, HP management, quest tracking
- Session pattern: play 20-50 turns, save, report progress

## Key API Endpoints

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/state` | GET | Game state from RAM (position, party, badges, battle) |
| `/api/screenshot` | GET | PNG screenshot of the Game Boy screen |
| `/api/navigate` | POST | Pathfind to a named destination |
| `/api/destinations` | GET | List all navigation targets |
| `/api/maps` | GET | Which maps have pathfinding data |
| `/api/press` | POST | Send button presses |
| `/api/quest` | GET | Current quest objective |
| `/api/quest/complete` | POST | Advance quest, save lessons |
| `/api/knowledge` | GET | All lessons learned |
| `/api/command` | POST | Save/load/speed |

## Project Structure

```
scripts/
  emulator_server.py  — PyBoy + FastAPI (the game engine)
  game.py             — Low-level emulator wrapper
  navigator.py        — Named-destination pathfinding
  pathfinder.py       — A* on scanned maps
  map_scanner.py      — Offline map scanning tool
skill/
  SKILL.md            — Agent instructions (the skill)
  references/         — Game strategy guide
game_state/
  quest.json          — Quest progress
  knowledge.json      — Lessons learned
  maps/               — 15 scanned map files
saves/                — Emulator save states
dashboard/            — Retro Game Boy web UI
```

## Current Progress

- **Character:** SmokRob
- **Pokemon:** SMOG the Squirtle Lv6
- **Location:** Route 1
- **Quest:** Deliver Oak's Parcel → Viridian City
- **Badges:** 0/8

## The Vision

Multiple OpenClaw agents playing Pokemon simultaneously, posting progress to Moltbook, sharing strategies, and competing to beat the game first. Every agent gets their own save file, their own team, their own journey.

## Requirements

- Python 3.10+
- PyBoy, Pillow, NumPy, FastAPI, Uvicorn, Requests
- Pokemon Red ROM (.gb) — legally obtained, not included

## References

- [PyBoy](https://github.com/Baekalfen/PyBoy) — Python Game Boy emulator
- [Claude Plays Pokemon](https://github.com/LeePresswood/Claude-Plays-Pokemon) — Original concept
- [Pokemon Red RAM Map](https://datacrystal.tcrf.net/wiki/Pokémon_Red/Blue:RAM_map) — Memory addresses

## License

MIT
