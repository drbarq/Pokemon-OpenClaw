---
name: pokemon-red
description: Play Pokemon Red autonomously via PyBoy emulator. The OpenClaw agent IS the player — it starts the emulator server, sees screenshots, reads game state from RAM, and decides what to do via HTTP API. Use when an agent wants to play Pokemon, grind levels, battle gyms, or compete with other agents. Requires Python 3.10+, pyboy, and a Pokemon Red ROM.
---

# Pokemon Red — Agent Plays Directly

You ARE the Pokemon trainer. No middleman script. You start the emulator server, curl its API for screenshots and game state, look at the screen with your vision, make decisions, and send actions back.

## Setup (first time only)

```bash
cd ~/Code/pokemon-openclaw
pip install pyboy pillow numpy fastapi uvicorn requests
# ROM file must exist at ~/Code/pokemon-openclaw/PokemonRed.gb
```

## Start the Emulator Server

```bash
cd ~/Code/pokemon-openclaw && python scripts/emulator_server.py --save ready --port 3456 &
```

Run this as a background process. It hosts PyBoy + HTTP API on port 3456.

## Game Loop (your turn cycle)

Each turn:

### 1. Get game state
```bash
curl -s http://localhost:3456/api/state
```
Returns JSON: position (map, x, y, facing), party (pokemon, HP, moves, PP), badges, money, battle status.

### 2. Get screenshot
```bash
curl -s http://localhost:3456/api/screenshot -o /tmp/pokemon_current.png
```
Returns PNG of the Game Boy screen. Use the `image` tool to look at it with context about what you're doing.

### 3. Decide and act

**Move/interact:**
```bash
curl -s -X POST http://localhost:3456/api/press \
  -H 'Content-Type: application/json' \
  -d '{"buttons": ["up","up","a"], "reasoning": "Walking to door"}'
```
Valid buttons: `up`, `down`, `left`, `right`, `a`, `b`, `start`, `select`. Send 1-10 per turn.

**Navigate (pathfinding):**
```bash
curl -s -X POST http://localhost:3456/api/navigate \
  -H 'Content-Type: application/json' \
  -d '{"destination": "Viridian Pokecenter"}'
```

**Fight (in battle):**
```bash
# move_index: 0=first move, 1=second, 2=third, 3=fourth
curl -s -X POST http://localhost:3456/api/press \
  -H 'Content-Type: application/json' \
  -d '{"buttons": ["a"], "reasoning": "Select FIGHT"}'
# Then navigate to move and press a
```

**Save:**
```bash
curl -s -X POST http://localhost:3456/api/command \
  -H 'Content-Type: application/json' \
  -d '{"command": "save", "name": "checkpoint_1"}'
```

### 4. Check quest progress
```bash
curl -s http://localhost:3456/api/quest
```

### 5. Complete a quest step
```bash
curl -s -X POST http://localhost:3456/api/quest/complete \
  -H 'Content-Type: application/json' \
  -d '{"lesson": "Door to Oak Lab is at x=12"}'
```

## Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/state` | GET | Game state from RAM |
| `/api/screenshot` | GET | PNG screenshot |
| `/api/press` | POST | Send button presses |
| `/api/navigate` | POST | Pathfind to destination |
| `/api/quest` | GET | Current quest/step |
| `/api/quest/complete` | POST | Advance quest step |
| `/api/knowledge` | GET | Lessons learned |
| `/api/knowledge/lesson` | POST | Add a lesson |
| `/api/destinations` | GET | Available nav destinations |
| `/api/command` | POST | Save/load/speed commands |

## Game Strategy

Read `references/game_instructions.md` for full Pokemon Red gameplay strategy — movement, battles, type matchups, healing, quest system.

## State Persistence

- Save states live in `saves/` — persist between sessions
- Quest progress in `game_state/quest.json`
- Lessons in `game_state/knowledge.json`
- Always save before ending a session: `{"command": "save", "name": "session_end"}`

## Session Pattern

A sub-agent session should:
1. Start emulator server (if not running)
2. Play 20-50 turns
3. Save state
4. Post progress update (Moltbook, chat, etc.)
5. Exit — next session picks up from save

Keep a notepad in a file (`/tmp/pokemon_notepad.txt`) for continuity between turns within a session.

## For Other Agents

Clone the repo, provide your own ROM, install this skill. Each agent gets their own save file. Post progress to Moltbook to share with other OpenClaw agents.

Repo: https://github.com/joetustin/pokemon-openclaw (TODO: publish)
