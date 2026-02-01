---
name: pokemon-red
description: Play Pokemon Red autonomously via PyBoy emulator. The OpenClaw agent IS the player — starts the emulator server, sees screenshots, reads game state from RAM, and makes decisions via HTTP API. One move at a time. The AI decides every button press.
---

# Pokemon Red — You Are the Trainer

You play Pokemon Red directly. One button press at a time. You see the screen, read the state, decide what to press, press it, see what happened, decide again. You are the player.

## Setup (first time)

```bash
git clone https://github.com/drbarq/Pokemon-OpenClaw.git
cd Pokemon-OpenClaw
pip install pyboy pillow numpy fastapi uvicorn requests
# Place your legally obtained ROM at ./PokemonRed.gb
```

## Start a Session

```bash
cd ~/Code/pokemon-openclaw && python scripts/emulator_server.py --save ready --port 3456
```

## The Loop

Every turn is the same:

### 1. Look
```bash
# Get game state (position, HP, battle status, party)
curl -s http://localhost:3456/api/state

# Get screenshot
curl -s http://localhost:3456/api/screenshot -o /tmp/pokemon.png
```
Use the `image` tool to look at the screenshot. **Always look before acting.**

### 2. Think

Based on what you see:
- Where am I? Where do I need to go?
- Am I in a battle? What should I do?
- Is my HP low? Should I heal?
- Is there an NPC or item nearby?

If you need directions, **ask the pathfinder**:
```bash
curl -s "http://localhost:3456/api/route?destination=Viridian+City"
```
Returns a list of steps: `["right", "right", "up", "up", ...]`
This is your GPS — follow it one step at a time, or ignore it if you see something better to do.

Check available destinations:
```bash
curl -s http://localhost:3456/api/destinations
```

### 3. Act — ONE button press

```bash
curl -s -X POST http://localhost:3456/api/press \
  -H 'Content-Type: application/json' \
  -d '{"buttons": ["up"], "reasoning": "Following route north to Viridian"}'
```

**ONE button per turn.** Valid: `up`, `down`, `left`, `right`, `a`, `b`, `start`, `select`

The response includes the game state after the press, so you immediately know what happened.

### 4. Repeat

Go back to step 1. Every turn you look, think, press one button.

## Battles

When `in_battle` is true in state:
- Press `a` to select FIGHT
- Press `a` to select your first move (Tackle)
- Press `a` through animations and text
- Check state — if `in_battle` is still true, keep going
- One `a` press per turn. Watch what happens between each one.

Don't blindly mash. Look at the screen. Is the menu up? Is text scrolling? Is the battle over?

## Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/state` | GET | Position, party, badges, battle status |
| `/api/screenshot` | GET | PNG of current screen |
| `/api/press` | POST | Press ONE button, get state back |
| `/api/route` | GET | Ask pathfinder for directions to a destination |
| `/api/destinations` | GET | List all known destinations |
| `/api/maps` | GET | Which maps have pathfinding data |
| `/api/quest` | GET | Current quest objective |
| `/api/quest/complete` | POST | Mark step done + save lesson |
| `/api/command` | POST | Save/load/speed commands |

## Strategy

1. **One move at a time.** No multi-button sequences. Press, observe, decide.
2. **Use the pathfinder as GPS.** Ask for route, follow one step at a time. Re-query after battles or detours.
3. **Check quest.** Always know your objective.
4. **Manage HP.** Below 30% → consider healing. Below 15% → head to pokecenter.
5. **Ignore text_active.** That flag is broken (always true). Look at the screenshot instead.
6. **Save often.** `{"command": "save", "name": "checkpoint_name"}`

## Session Pattern

1. Start emulator (if not running)
2. Check quest + state
3. Play turns: look → think → press one button → repeat
4. Save state before exiting
5. Report: location, level, quest progress, battles fought
