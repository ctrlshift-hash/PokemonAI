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
TICK_INTERVAL = 0.5
DB_UPDATE_INTERVAL = 10
PLANNING_REVIEW_INTERVAL = 25
SAVE_REMINDER_INTERVAL = 50
MAX_CONSECUTIVE_ERRORS = 5
ERROR_PAUSE_SECONDS = 10

# Input — mGBA default keyboard mappings
BUTTON_MAP = {
    "A": "x",
    "B": "z",
    "START": "return",
    "SELECT": "backspace",
    "UP": "up",
    "DOWN": "down",
    "LEFT": "left",
    "RIGHT": "right",
    "L": "a",
    "R": "s",
}

DIRECTION_BUTTONS = {"UP", "DOWN", "LEFT", "RIGHT"}

# ChromaDB
CHROMA_DIR = PROJECT_ROOT / "chroma_db"
MEMORY_COLLECTION = "pokemon_memory"
MEMORY_TOP_K = 5

# Logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Data files
TYPE_CHART_FILE = PROJECT_ROOT / "data" / "type_chart.json"
MAP_NAMES_FILE = PROJECT_ROOT / "data" / "map_names.json"

# LLM
LLM_MAX_TOKENS = 150
LLM_TEMPERATURE = 0.3

# Overlay
OVERLAY_ENABLED = True
OVERLAY_WIDTH = 340
