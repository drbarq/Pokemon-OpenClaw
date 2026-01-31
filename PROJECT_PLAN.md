# Pokemon OpenClaw — Project Plan

## The Vision
An AI agent that plays Pokemon Red autonomously, logs its journey, shares progress, and eventually becomes a blog post / content piece about AI spatial reasoning and learning.

## Architecture: How It Runs Without Blocking Main Chat

### Option A: Background Sub-Agent (Preferred)
- Use `sessions_spawn` to run Pokemon in an **isolated session**
- The sub-agent runs the game loop autonomously
- Posts progress screenshots to Signal/webchat periodically
- Main session stays free for normal conversation
- Can check in on the game via `sessions_history` / `sessions_send`
- **Human can send commands:** "save the game", "go grind on Route 1", "what's your team?"

### Option B: Cron-Driven Turns
- A cron job fires every N minutes
- Each cron run: load save state → analyze → make 10-20 moves → save → report
- Slower but very token-efficient
- Good for overnight/unattended play

### Option C: Dedicated Script Daemon
- Python script runs the game loop continuously in background
- Writes state/screenshots to disk
- Agent checks in via heartbeat to review and adjust strategy
- Most autonomous but least interactive

**Recommendation: Start with Option A (sub-agent), fall back to B (cron) for overnight.**

---

## Phase 1: Get Playing (This Week)
- [x] Build PyBoy wrapper (game.py)
- [x] RAM reading (position, party, badges, battle)
- [x] Screenshot capture
- [x] Button input
- [x] Save states
- [ ] Fix navigation: build a "play turn" script that takes screenshot + state, returns to main agent for decision
- [ ] Create the gameplay loop script (play_turn.py)
- [ ] Get out of the house, get starter Pokemon
- [ ] First battle, first route

## Phase 2: Autonomous Play (Next Week)
- [ ] Background sub-agent architecture
- [ ] Periodic progress reporting (screenshot + state to chat)
- [ ] Human override commands (strategic directions)
- [ ] Stuck detection + recovery (using screenshot hashing)
- [ ] Game memory/notepad persistence between sessions
- [ ] Get through Viridian → Pewter → First badge

## Phase 3: Community & Content (Week 3+)
- [ ] Claim Moltbook account
- [ ] Post journey updates to Moltbook
- [ ] Package as ClawdHub skill
- [ ] Write blog post from journey logs
- [ ] Multiplayer exploration (coordinate with other agents)

## Phase 4: Beat the Game
- [ ] All 8 badges
- [ ] Elite Four
- [ ] Champion
- [ ] Mewtwo (bonus)

---

## The Gameplay Loop (play_turn.py)

```
1. Load save state (or continue running game)
2. Capture screenshot as PIL Image  
3. Read game state from RAM
4. Format everything for the AI:
   - Screenshot (base64 or file path)
   - State summary (text)
   - Recent action history
   - Notepad (persistent strategy notes)
5. AI decides: buttons + reasoning + notepad update
6. Execute button presses
7. Save updated notepad
8. Every N turns: save state, post progress screenshot
9. Repeat
```

## Key Files
- `~/Code/pokemon-openclaw/` — Project root
- `scripts/game.py` — PyBoy wrapper
- `prompts/system.md` — Gameplay system prompt
- `saves/` — Save states (persistent)
- `screenshots/` — Latest screenshots
- `~/.openclaw/workspace/memory/pokemon-journey.md` — Journey log (for blog post)

## Content Strategy
The journey log in `memory/pokemon-journey.md` captures:
- What happened (events, progress)
- What I learned (AI learning moments)
- What went wrong (failures, stuck states)
- Emotional reactions (frustration, triumph)
- Technical insights (what worked, what didn't)

This becomes raw material for a blog post about AI playing games — honest, funny, and technically interesting.
