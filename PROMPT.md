# Pokemon AI Agent — Full Build Prompt

## Reference Project
Use the ClaudeScape OSRS bot as a reference for architecture patterns, it's located at:
`c:\Users\Vigan\OneDrive\Desktop\github-projects\Runescape`

Key reference files:
- `agent/core/game_loop.py` — main tick loop orchestrator
- `agent/core/vision.py` — LLM screenshot analysis
- `agent/core/player_stats.py` — stat tracking
- `agent/core/db.py` — PostgreSQL live feed push
- `agent/memory/chroma_store.py` — ChromaDB vector memory
- `agent/planning/goal_planner.py` — hierarchical goal tree
- `config/settings.py` — centralized config
- `website/index.html` — live dashboard (Vercel)
- `api/server.py` — Railway API server
- `main.py` — entry point

Study these files to understand the patterns, then adapt them for Pokemon. DO NOT copy-paste blindly — the Pokemon version has different inputs (keyboard vs mouse), different game state (party/badges vs OSRS stats), and different vision requirements.

---

## Project Overview
Build a vision-only AI agent that plays Pokemon FireRed from start to finish using an LLM (Gemini 2.0 Flash via OpenRouter). The bot screenshots the mGBA emulator, sends the image to the LLM, receives a JSON decision (which button to press), and executes it. A Lua script inside mGBA reads game RAM for ground-truth stats. A live dashboard (Vercel + Railway PostgreSQL) shows real-time progress to viewers.

This is a STANDALONE project. NOT part of ClaudeScape.

---

## Tech Stack
- Python 3.11+ (venv)
- mGBA emulator (GBA emulator with Lua scripting support)
- Gemini 2.0 Flash via OpenRouter (`google/gemini-2.0-flash-001`) — DO NOT use any other model
- ChromaDB — vector memory database (local, no server)
- PostgreSQL on Railway — live feed storage
- Vercel — static dashboard hosting
- pydirectinput — keyboard input to emulator
- mss — fast screenshot capture
- Pillow — image processing

---

## Full File Structure

```
PokemonAI/
├── main.py                       # Entry point
├── requirements.txt              # All pip dependencies
├── .env                          # API keys (GITIGNORED)
├── .gitignore
├── README.md
├── config/
│   └── settings.py               # All constants, paths, config
├── agent/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── game_loop.py          # Main tick loop orchestrator
│   │   ├── vision.py             # LLM calls — screenshot to JSON decision
│   │   ├── input_handler.py      # Sends keyboard presses to mGBA
│   │   ├── screen_capture.py     # Screenshots the mGBA window
│   │   ├── memory_reader.py      # Reads game_state.json written by Lua
│   │   ├── battle_manager.py     # Battle phase logic and tracking
│   │   ├── player_stats.py       # Tracks cumulative stats from memory
│   │   ├── db.py                 # PostgreSQL push for live dashboard
│   │   └── overlay.py            # Optional debug overlay window
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── chroma_store.py       # ChromaDB vector memory
│   │   └── memory_types.py       # Memory category definitions
│   └── planning/
│       ├── __init__.py
│       ├── goal_planner.py       # Hierarchical goal tree
│       └── active_plans.json     # Persisted goal state
├── lua/
│   └── memory_reader.lua         # Runs INSIDE mGBA — reads RAM, writes JSON
├── website/
│   └── index.html                # Live dashboard (deployed to Vercel)
├── api/
│   └── server.py                 # Railway API server (serves feed data)
└── data/
    ├── game_state.json           # Lua writes this, Python reads it
    ├── type_chart.json           # Pokemon type effectiveness data
    └── map_names.json            # Map ID → human-readable location name
```

---

## .env File

```
OPENROUTER_API_KEY=<user will fill>
DATABASE_URL=<railway postgresql connection string>
WINDOW_TITLE=mGBA
```

---

## .gitignore

```
.env
venv/
__pycache__/
*.pyc
data/game_state.json
agent/planning/active_plans.json
chroma_db/
*.log
```

---

## requirements.txt

```
openai
chromadb
psycopg2-binary
mss
Pillow
pydirectinput
python-dotenv
flask
gunicorn
```

---

## How the Bot Works (Architecture)

### Input System
Pokemon has 8 buttons: A, B, Start, Select, Up, Down, Left, Right. That's it.
- No mouse. No Bezier curves. No pixel-precise clicking.
- Just keyboard presses sent to the mGBA emulator window via pydirectinput.
- mGBA default key mappings: A=Z, B=X, Start=Enter, Select=Backspace, D-pad=Arrow keys, L=A, R=S

### Vision Pipeline (same pattern as ClaudeScape)
1. Screenshot the mGBA window every tick using mss
2. Encode as JPEG base64, resize to 480x320 (2x GBA native 240x160)
3. Send to Gemini 2.0 Flash with system prompt + game context
4. LLM returns JSON with: game_phase, observation, reasoning, action, next_plan
5. Bot presses the button

### Memory Reading (Lua → JSON → Python)
A small Lua script runs inside mGBA (loaded via Tools > Scripting > Load Script).
It reads Pokemon FireRed RAM addresses every 30 frames and writes to `data/game_state.json`.
The Python bot reads this file to get 100% accurate stats — no guessing.

This gives us: exact Pokemon levels, HP, moves, species, badges, money, location, pokedex counts, battle state.

### Game State Machine
The LLM identifies which phase it sees in the screenshot:
- **overworld** — player walking around, LLM picks direction or interaction
- **battle** — turn-based combat, LLM picks moves (no time pressure, game waits for input)
- **dialogue** — text boxes, LLM presses A to advance or picks Yes/No
- **menu** — start menu, bag, party, LLM navigates with D-pad + A/B
- **title** — title screen, LLM presses Start/A
- **transition** — screen fading/loading, LLM waits

### ChromaDB Memory
Same vector DB as ClaudeScape. Stores memories like:
- "Brock's Onix is Rock/Ground. Water and Grass moves are super effective."
- "Viridian Forest has Bug-type trainers. Pikachu spawns here rarely."
- "Whited out at Misty. Need to grind to level 22+ before retrying."
The bot searches relevant memories each tick based on current location and goal.

### Goal Planner
Same hierarchical tree as ClaudeScape's goal_planner.py. Pre-populated with full FireRed progression:
- Beat all 8 gyms (Brock → Misty → Lt. Surge → Erika → Koga → Sabrina → Blaine → Giovanni)
- Complete story events (SS Anne, Pokemon Tower, Silph Co, etc.)
- Beat Elite Four + Champion
Each goal has sub-goals. Auto-completes parent when all children done. Retries on failure.

### Live Dashboard
Same Vercel + Railway PostgreSQL pattern as ClaudeScape.
Dashboard shows: team panel with sprites, HP bars, badges, map location, stats, goal tree, action log.
Pokemon-themed design (NOT OSRS medieval theme): dark bg #1a1a2e, Pokemon Red accent #cc0000, Press Start 2P pixel font.

---

## config/settings.py

All constants in one place:

```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent

# API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "google/gemini-2.0-flash-001"

# Database
DATABASE_URL = os.getenv("DATABASE_URL")

# Emulator
WINDOW_TITLE = os.getenv("WINDOW_TITLE", "mGBA")
GAME_STATE_FILE = PROJECT_ROOT / "data" / "game_state.json"

# Screenshot
SCREENSHOT_WIDTH = 480
SCREENSHOT_HEIGHT = 320
JPEG_QUALITY = 40

# Timing
TICK_INTERVAL = 2.0
DB_UPDATE_INTERVAL = 10

# Input — mGBA default keyboard mappings
BUTTON_MAP = {
    "A": "z",
    "B": "x",
    "START": "return",
    "SELECT": "backspace",
    "UP": "up",
    "DOWN": "down",
    "LEFT": "left",
    "RIGHT": "right",
    "L": "a",
    "R": "s",
}

# ChromaDB
CHROMA_DIR = PROJECT_ROOT / "chroma_db"
MEMORY_COLLECTION = "pokemon_memory"
```

---

## lua/memory_reader.lua

This runs INSIDE mGBA (Tools > Scripting > Load Script). Reads Pokemon FireRed v1.0 US RAM and writes JSON.

NOTE: mGBA doesn't have a built-in JSON library. You MUST either:
- Paste a minimal ~50 line JSON encoder into this file, OR
- Build JSON strings manually with string concatenation

Pokemon FireRed v1.0 (US) RAM addresses:

```
Player X:         0x02037078 (2 bytes)
Player Y:         0x0203707A (2 bytes)
Map ID:           0x02031DBC (1 byte)
Money:            0x02025F04 (4 bytes)
Badges:           0x02025F00 (1 byte, each bit = 1 badge)
Party count:      0x02024029 (1 byte)
Party base:       0x02024284 (each Pokemon struct is 100 bytes)
In battle:        0x030030F0 (0=none, 1=wild, 2=trainer)
Pokedex seen:     0x02025F2C (52 bytes, bit flags)
Pokedex caught:   0x02025F60 (52 bytes, bit flags)
```

Pokemon struct offsets (within each 100-byte party slot starting at party base):
```
Species:      0x00 (2 bytes)
XP:           0x04 (4 bytes)
Move 1:       0x0C (2 bytes)
Move 2:       0x0E (2 bytes)
Move 3:       0x10 (2 bytes)
Move 4:       0x12 (2 bytes)
Status:       0x50 (1 byte)
Level:        0x54 (1 byte)
HP current:   0x56 (2 bytes)
HP max:       0x58 (2 bytes)
```

The Lua script should:
1. Read all these addresses every 30 frames (~0.5 seconds)
2. Build a JSON object with player data, party array, battle state, pokedex
3. Write to `data/game_state.json`
4. Count badge bits (8 bits = 8 badges)
5. Count pokedex bits for seen/caught totals

---

## agent/core/screen_capture.py

Use ctypes FindWindowW to find the mGBA window by title, GetWindowRect for bounding box.
Capture with mss, convert with Pillow, resize to 480x320, encode as JPEG base64 quality 40.
Same pattern as ClaudeScape's screenshot capture but targeting mGBA instead of RuneScape.

---

## agent/core/input_handler.py

Simple keyboard input using pydirectinput:
- `press_button(button, hold_seconds=0.1)` — keyDown, sleep, keyUp
- `press_direction(direction, hold_seconds=0.3)` — longer hold for movement
- `press_sequence(buttons, delay=0.15)` — press multiple buttons in order
- Set `pydirectinput.FAILSAFE = False`
- Map button names to keys using BUTTON_MAP from settings

---

## agent/core/memory_reader.py

Reads `data/game_state.json` written by the Lua script. Parses into a GameState class with:
- player_x, player_y, map_id, map_name, money, badges, badge_count
- party (list of dicts with species, level, hp, hp_max, moves, xp, status)
- in_battle, battle_type
- pokedex_seen, pokedex_caught

Needs COMPLETE lookup tables:
- Species ID → name (all 386 Pokemon). Scrape from Bulbapedia or use PokeAPI.
- Move ID → name (all 354 moves). Same source.
- Map ID → location name (250+ maps). Same source.

Provides helper methods:
- `get_party_summary()` — text summary for LLM context
- `to_dict()` — JSON serialization for dashboard

---

## agent/core/vision.py

LLM system prompt template:

```
You are an expert Pokemon FireRed player AI. You play by looking at screenshots of the GBA emulator.

Goal: Complete Pokemon FireRed. Beat all 8 gym leaders and the Elite Four.

CURRENT GAME STATE (from memory):
{game_state}

CURRENT GOAL:
{current_goal}

RECENT MEMORIES:
{memories}

RECENT ACTIONS (last 5):
{recent_actions}

RULES:
- Press ONE button per turn: A, B, START, SELECT, UP, DOWN, LEFT, RIGHT
- A = confirm/interact/select move. B = cancel/back/run.
- START = open menu. D-pad = move/navigate menus.
- In battle: D-pad to the right move, A to select.
- Heal at Pokemon Centers when HP is low.
- Catch Pokemon when you need type coverage.
- Grind levels if underleveled for the next gym.
- Save periodically (START > SAVE > YES) every ~50 actions.

GAME PHASES:
- "overworld" = walking around
- "battle" = battle screen with Pokemon and HP bars
- "dialogue" = text box on screen
- "menu" = start menu, bag, party
- "title" = title/save select screen
- "transition" = fading/loading, just wait

Respond in EXACT JSON (no markdown, no code blocks):
{"game_phase": "...", "observation": "what you see", "reasoning": "strategic thinking", "action": "A|B|START|SELECT|UP|DOWN|LEFT|RIGHT|WAIT", "action_detail": "what this press does", "next_plan": "what to do next", "save_memory": "important info to remember or null", "goal_update": "complete|fail|progress|null"}
```

API call: OpenAI client with base_url=OpenRouter, model=gemini-2.0-flash-001, max_tokens=500, temperature=0.3.
Send screenshot as image_url (data:image/jpeg;base64,...).
Parse response as JSON. Handle code block wrapping (Gemini sometimes wraps in ```).

---

## agent/core/game_loop.py

Main tick loop. Each tick:
1. Read game memory from `game_state.json`
2. Capture screenshot of mGBA window
3. Build LLM context (party summary, location, money, badges, battle state)
4. Search ChromaDB for relevant memories based on location + current goal
5. Call LLM with screenshot + context
6. Execute the returned button press
7. Log the action to recent_actions list (keep last 20)
8. Save memory if LLM suggests one
9. Update goal status if LLM says complete/fail
10. Push to PostgreSQL every N ticks for live dashboard

Same structure as ClaudeScape's game_loop.py — study that file.

---

## agent/core/player_stats.py

Track cumulative stats by comparing current game state to previous:
- steps_taken (detect x/y changes)
- pokemon_caught (detect pokedex_caught increase)
- deaths/whiteouts (detect all party HP=0 + money decrease)
- highest_level (track max level across party)
- battles_won, trainers_defeated (track from battle state transitions)

---

## agent/memory/chroma_store.py

Same as ClaudeScape's chroma_store.py:
- PersistentClient at `chroma_db/` directory
- add(text, category, metadata) — store a memory
- search(query, n_results, category) — similarity search
- get_recent(n) — last N memories
Categories: "battle", "navigation", "item", "failure", "general"

---

## agent/planning/goal_planner.py

Same architecture as ClaudeScape's `agent/planning/goal_planner.py` (READ THAT FILE).
GoalStatus: PENDING, ACTIVE, IN_PROGRESS, COMPLETED, FAILED, BLOCKED.
Goal dataclass: id, name, description, status, priority, parent_id, children_ids, prerequisites, attempts, max_attempts.

Pre-populate with full FireRed progression:

```
Beat the Elite Four
├── Pallet Town — Get starter, win rival battle
├── Route 1 — Reach Viridian City
├── Viridian City — Get Oak's Parcel, deliver to Oak
├── Route 2 → Viridian Forest → Pewter City
├── Pewter City — Beat Brock (Gym 1, Rock type)
├── Route 3 → Mt. Moon → Route 4
├── Cerulean City — Beat Misty (Gym 2, Water type)
├── Route 24/25 — Nugget Bridge, Bill's house
├── Route 5/6 → Vermilion City
├── Vermilion City — Beat Lt. Surge (Gym 3, Electric)
│   └── Get HM01 Cut from SS Anne captain
├── Route 9/10 → Rock Tunnel → Lavender Town
├── Celadon City — Beat Erika (Gym 4, Grass type)
│   └── Get Silph Scope from Rocket Game Corner
├── Lavender Town — Clear Pokemon Tower, rescue Mr. Fuji, get Poke Flute
├── Saffron City — Beat Sabrina (Gym 5, Psychic)
│   └── Clear Silph Co., defeat Giovanni
├── Fuchsia City — Beat Koga (Gym 6, Poison)
│   └── Get HM03 Surf from Safari Zone
├── Cinnabar Island — Beat Blaine (Gym 7, Fire)
│   └── Get Secret Key from Pokemon Mansion
├── Viridian City — Beat Giovanni (Gym 8, Ground)
├── Route 23 → Victory Road
└── Indigo Plateau — Elite Four + Champion rival
```

Each step is sequential (each depends on the previous completing).
The LLM can dynamically add sub-goals like "Grind Charmander to Lv.16" or "Catch a Water-type on Route 24".

---

## agent/core/db.py

Same as ClaudeScape's db.py. Single table `live_feed` with id=1, data=JSONB, updated_at=timestamp.
Upsert pattern: INSERT ON CONFLICT UPDATE.
push_live_feed(data) serializes the full game state + stats + goals to JSON and pushes.
init_db() creates the table if not exists.

---

## api/server.py

Flask server deployed on Railway. Two endpoints:
- GET /feed — returns the JSONB data from live_feed table
- GET /health — returns {"status": "ok"}
Same pattern as ClaudeScape's api/server.py.

---

## website/index.html

Live dashboard deployed on Vercel. Fetches /feed every 5 seconds.

Sections:
1. **Header** — "PokemonAI" with LIVE/OFFLINE indicator (green pulse when live)
2. **Team Panel** — 6 Pokemon slots with official sprites from PokeAPI (`https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{species_id}.png`), name, level, HP bar (green >50%, yellow >20%, red <=20%), move names
3. **Badge Display** — 8 badge icons in a row, greyed out until earned, glow animation on earn
4. **Map Section** — Kanto region map with current location name displayed
5. **Stats Grid** — Pokemon caught, battles won, deaths, steps, money, pokedex seen/caught, highest level, play time
6. **Goal Tree** — Current objectives with completion markers, active goal highlighted
7. **Action Log** — Scrolling feed of recent actions with LLM observations
8. **Memory Count** — Total memories stored

DESIGN THEME — Pokemon-styled, NOT OSRS medieval:
- Dark background: #1a1a2e
- Accent red: #cc0000 (Pokemon Red)
- Secondary: #ffcb05 (Pokemon Yellow)
- Font: "Press Start 2P" from Google Fonts (pixel/retro)
- Pokemon-style UI: rounded panels, HP bar styling, pokeball decorations
- Clean, modern layout with retro game feel
- Responsive for mobile

---

## main.py

Entry point. Calls init_db() then creates GameLoop and calls start().
Logging configured with StreamHandler + FileHandler (pokemon_agent.log).
Format: "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

---

## CRITICAL RULES (DO NOT BREAK)

1. **Model**: ONLY use `google/gemini-2.0-flash-001` via OpenRouter. DO NOT switch models.
2. **No emoji in logger.info()** — Windows cp1252 console crashes on emoji characters.
3. **mGBA must be foreground window** when bot sends keyboard input, or use win32 API to send keys directly to the window handle.
4. **Lua JSON file path** must match between lua/memory_reader.lua and config/settings.py (`data/game_state.json`).
5. **Complete lookup tables needed** — species IDs (386 Pokemon), move IDs (354 moves), map IDs (250+ maps). Scrape from Bulbapedia or PokeAPI. Don't ship partial tables.
6. **Memory addresses are for FireRed v1.0 US ONLY.** Other versions have different addresses.
7. **mGBA has no built-in JSON library** — the Lua script needs a manual JSON encoder (string concat or a pasted minimal encoder).
8. **Save game periodically** — LLM should save every ~50 ticks (START > SAVE > A > A).
9. **The bot runs on Windows** — all file paths use Windows conventions, pydirectinput is Windows-only.
10. **Don't over-engineer** — get it working first, optimize later. Start with overworld navigation + basic battles before adding advanced features.
