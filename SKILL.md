---
name: pokemon
version: 0.1.0
description: Play Pokemon Red autonomously using PyBoy emulator. The AI agent sees the screen, reads game state, and decides actions.
metadata: {"openclaw":{"emoji":"🎮","category":"games","requires":{"bins":["python3"]}}}
---

# Pokemon Red — OpenClaw Skill

Play Pokemon Red autonomously. The agent sees screenshots, reads game memory, and makes decisions.

## Setup

### 1. Install Python dependencies

```bash
cd ~/Code/pokemon-openclaw
python3 -m venv .venv
source .venv/bin/activate
pip install pyboy pillow
```

### 2. Provide a ROM

You need a legally obtained Pokemon Red ROM file (.gb, ~1MB).
Place it at: `~/Code/pokemon-openclaw/PokemonRed.gb`

SHA1 should be: `ea9bcae617fdf159b045185467ae58b2e4a48b9a`

### 3. Test the setup

```bash
cd ~/Code/pokemon-openclaw
source .venv/bin/activate
python scripts/game.py PokemonRed.gb --screenshot --state --frames 300
```

## How to Play

The agent uses a perception → decision → action loop:

### 1. Start a game session

```bash
cd ~/Code/pokemon-openclaw && source .venv/bin/activate
python -c "
from scripts.game import PokemonGame
game = PokemonGame('PokemonRed.gb', headless=True)
game.start()
game.tick(300)  # Let title screen load
print(game.format_state_for_ai())
game.screenshot(save=True, filename='current.png')
"
```

### 2. Get screenshot + state

The agent calls `game.screenshot()` to get a PIL Image and `game.format_state_for_ai()` for a text summary. Both are sent to the LLM for decision-making.

### 3. Make a decision

The agent (which IS the LLM) analyzes the screenshot + state and decides:
```json
{
  "buttons": ["right", "right", "a"],
  "reasoning": "Walking to the door and entering.",
  "notepad": "Heading to Oak's Lab to get starter."
}
```

### 4. Execute and repeat

```python
game.press_buttons(["right", "right", "a"])
game.tick(60)  # Wait for animations
new_screenshot = game.screenshot()
new_state = game.format_state_for_ai()
```

## Architecture

```
scripts/
  game.py     — PyBoy wrapper (emulator, screenshots, memory reading, button input)
prompts/
  system.md   — Gameplay system prompt (strategy guide, decision framework)
saves/        — Save states (persistent between sessions)
screenshots/  — Latest screenshots (for sharing to chat)
```

## Game State from Memory

The wrapper reads Pokemon Red RAM directly:
- **Position:** Map name, X/Y coordinates, facing direction
- **Party:** Species, level, HP, moves, PP, status
- **Badges:** Which 8 gym badges are earned
- **Money:** Current balance
- **Battle:** Enemy Pokemon, HP, level, battle type (wild/trainer)
- **Text:** Whether a dialogue box is active

This means the AI doesn't need to OCR the screen — it gets structured data.

## Sharing Progress

Screenshots are saved to `screenshots/` and can be sent to any chat channel.
Game state summaries are text-based and work on any messaging surface.

## Save System

- `game.save_state("checkpoint_badge1")` — Save at milestones
- `game.load_state("checkpoint_badge1")` — Resume from checkpoint
- Save states persist in `saves/` directory between sessions

## Strategy Prompt

See `prompts/system.md` for the full gameplay strategy guide included in the AI's context.

## Future: Multiplayer

The vision: multiple OpenClaw agents playing Pokemon simultaneously, posting progress to Moltbook, sharing strategies, and competing to beat the game first.

## Credits

Built on:
- [PyBoy](https://github.com/Baekalfen/PyBoy) — Game Boy emulator with Python API
- [Claude Plays Pokemon](https://github.com/LeePresswood/Claude-Plays-Pokemon) — Reference architecture
- [Pokemon Red RAM Map](https://datacrystal.tcrf.net/wiki/Pokémon_Red/Blue:RAM_map) — Memory addresses
