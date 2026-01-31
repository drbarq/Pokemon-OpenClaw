# Pokemon OpenClaw - Research & Build Plan

## Goal
Build an OpenClaw skill that lets the AI agent play Pokemon Red autonomously.
The agent sees the game screen, decides actions, and sends button presses.
Eventually: multiplayer collaboration between OpenClaw instances, publishable as a ClawdHub skill.

## Reference Projects

### 1. Claude Plays Pokemon (LeePresswood)
- **Repo:** github.com/LeePresswood/Claude-Plays-Pokemon (cloned to reference-claude-plays/)
- Uses mGBA emulator + Anthropic API (Claude vision)
- Screenshot → Claude analyzes → decides button press → executes → repeat
- Supports Haiku for routine, Sonnet for strategy
- Python, public domain license
- **Architecture:** src/agent/ (vision.py, memory.py) + src/emulator/ (capture.py, input.py)

### 2. LLM-Pokemon-Red (martoast)  
- **Repo:** github.com/martoast/LLM-Pokemon-Red (cloned to reference-llm-pokemon/)
- mGBA + Lua script + Python controller + Gemini vision
- 43 stars, active

### 3. PyBoy (Baekalfen)
- `pip install pyboy` — Game Boy emulator with clean Python API
- Headless mode, screenshot capture, button input, memory access
- 395x realtime speed, parallel instances
- **This is the best emulator backbone** — no need for mGBA + Lua

### 4. PokemonRedExperiments (PWhiddy) — 7.8K stars
- RL approach using PyBoy + PPO
- Has multiplayer live training broadcast
- Different paradigm (neural net, not LLM) but good reference for game state tracking

## Architecture for OpenClaw Skill

### Core Loop
1. PyBoy runs Pokemon Red headless
2. Every N frames, capture screenshot
3. Send screenshot to the LLM (via OpenClaw's own vision — no separate API needed)
4. LLM decides: button press + reasoning + notepad update
5. Execute button press via PyBoy API
6. Post screenshot to chat channel so human can watch
7. Repeat

### Key Advantage Over Existing Projects
- OpenClaw already HAS an LLM with vision — we don't need separate API calls
- The agent IS the player — it can use its own tool ecosystem
- Screenshots can go straight to Signal/Discord/Telegram
- Human can chat with the agent mid-game to give strategy advice
- Save states, memory files for game progress tracking

### Dependencies
- Python 3.10+
- PyBoy (`pip install pyboy`)
- Pokemon Red ROM (user must provide legally)
- Pillow (screenshot processing)

### Skill Structure
```
pokemon/
├── SKILL.md          # OpenClaw skill definition
├── scripts/
│   ├── game.py       # PyBoy wrapper — headless emulator control
│   ├── state.py      # Game state tracking (badges, team, location)
│   └── memory.py     # Persistent game memory/notepad
├── prompts/
│   └── system.md     # Pokemon gameplay system prompt
├── saves/            # Save states directory
└── screenshots/      # Latest screenshots
```

### Game State Tracking (from PyBoy memory)
- Player position & map ID
- Pokemon team (species, HP, level, moves)
- Badges collected
- Items in bag
- Current objective/quest state

## TODO
- [ ] Study both reference repos in detail
- [ ] Test PyBoy installation on macOS M4
- [ ] Build minimal proof of concept (screenshot + button press loop)
- [ ] Design the OpenClaw skill interface
- [ ] Build game state reader from memory addresses
- [ ] Create system prompt for Pokemon gameplay
- [ ] Test with actual ROM
- [ ] Package as ClawdHub skill
- [ ] Post to OpenClaw Discord for community feedback
