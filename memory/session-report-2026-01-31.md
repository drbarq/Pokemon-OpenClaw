# Pokemon OpenClaw — Session Report: January 31, 2026

## The Day AI Learned to Play Pokemon One Button at a Time

### The Problem

We had an AI agent that could read Pokemon Red's RAM, see screenshots, and press buttons. What we didn't have was an AI that could actually *play*. Five sessions of sub-agents kept getting stuck on Route 1 — the simplest path in the game.

### What Went Wrong (Sessions 1-5)

**Fire-and-forget navigation.** The server had a `/api/navigate` endpoint that queued up 70+ button presses at once and returned immediately. The agent would sleep 15 seconds, check once, and miss everything — battles starting mid-navigation, the character getting stuck on signs, ledges creating invisible walls in the pathfinder data.

**Chunked movement (3 buttons at a time).** Pokemon Red needs each button press to fully process before the next one. Sending 3 at once meant the game swallowed inputs during animations. The character would stop moving and the agent had no idea why.

**Server playing instead of AI.** We built `auto_navigate` and `auto_fight` — the Python server handled pathfinding, battle detection, fighting, recovery, re-routing. One API call did everything. It worked (SMOG reached Viridian City!) but the AI wasn't playing. A pathfinding algorithm was playing. The LLM was just a glorified cron job.

### The Breakthrough: One Move at a Time

The fix was embarrassingly simple: **strip everything out and let the LLM make every decision.**

The API became three endpoints:
- `POST /api/press` — press ONE button, get state back
- `GET /api/state` — where am I, what's happening
- `GET /api/route` — ask the pathfinder for directions (GPS, not autopilot)

The agent loop:
1. Look at screenshot
2. Read game state
3. Think: where am I, what should I do?
4. Ask pathfinder for directions (optional — it's a tool, not a boss)
5. Press ONE button
6. See what happened
7. Repeat

### Results

**Session 6 (one-move-at-a-time):** 33 turns. Walked from Viridian City to the Mart. Talked to the clerk. Got Oak's Parcel. Saved. Clean, deliberate, no wasted moves.

**Session 7:** Traveled Route 1 south back to Pallet Town. Ran from battles at 6 HP (smart — it knew it couldn't fight). Whited out on the third encounter, which teleported it to Pallet Town for free (accidentally optimal). Entered Oak's Lab. Delivered the parcel. Got the Pokedex. Saved.

The AI made strategic decisions a script never would:
- Choosing to RUN from battles when HP was low instead of fighting
- Recognizing that whiting out was actually helpful (free teleport home)
- Pressing through NPC dialogue by reading the screenshot each time

### Architecture Lessons

| What We Tried | Why It Failed | What Worked |
|---|---|---|
| Queue 70 buttons at once | Battles interrupt, signs block, no error recovery | One button, check result |
| 3-button chunks | Game swallows inputs during animations | Single button with proper hold/wait |
| Server does pathfinding + fighting | AI isn't playing, just calling one endpoint | Pathfinder as GPS tool, AI decides |
| Sleep 15s then check | Misses battles, state changes | Immediate feedback after every press |

### The Key Insight

> The pathfinder is the GPS. The LLM is the driver. The driver can ignore the GPS whenever it wants.

The AI needs to be in the loop for every decision. Not because it's better at pathfinding (it's not — A* is perfect for that). But because the game is full of surprises: random battles, NPCs that walk into your path, ledges you can't climb back up, text that needs dismissing. Only something that can *see the screen and think* can handle all of that.

### Stats

- **SMOG the Squirtle:** Level 7, full health, Oak's Lab
- **Quest progress:** Oak's Parcel delivered ✅, Pokedex obtained ✅
- **Battles fought:** ~6 across all sessions (3 on the successful Viridian run)
- **Total development time:** ~4 hours of iteration
- **Architecture revisions:** 4 (fire-and-forget → blocking → auto → one-at-a-time)
- **Lines of code removed:** 223 (the best commit)

### What's Next

Pewter City and the first gym badge. Route 1 → Viridian City → Route 2 → Viridian Forest → Pewter City → Brock. SMOG needs to grind to ~Lv12-14 and learn Bubble/Water Gun to handle Brock's Rock-types.

### The Smoking Robot Plays Pokemon

This is what "AI as its own creature" looks like. Not a human replacement pretending to think. Not a script pretending to be smart. An actual AI making actual decisions, one button press at a time, learning from what it sees. The robot plays Pokemon the same way a human does — look at the screen, think, press a button, see what happens.

🚬🤖
