"""
Pokemon AI Agent - Main Entry Point
A vision-based AI that plays Pokemon FireRed using Gemini 2.0 Flash.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import settings


def setup_logging(level="INFO"):
    """Configure logging to both console and file."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    log_file = settings.LOG_DIR / "pokemon_agent.log"

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, mode="a", encoding="utf-8"),
    ]

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        handlers=handlers,
    )

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(
        description="Pokemon AI Agent - Autonomous FireRed player powered by Gemini vision"
    )
    parser.add_argument(
        "--interval", type=float, default=settings.TICK_INTERVAL,
        help="Seconds between game loop ticks (default: 2.0)"
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )
    parser.add_argument(
        "--reset-goals", action="store_true",
        help="Reset all goals and start fresh"
    )
    parser.add_argument(
        "--no-overlay", action="store_true",
        help="Disable the transparent overlay window"
    )

    args = parser.parse_args()

    settings.TICK_INTERVAL = args.interval
    if args.no_overlay:
        settings.OVERLAY_ENABLED = False

    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    # Banner
    logger.info("""
 ____       _                                _    ___
|  _ \\ ___ | | _____ _ __ ___   ___  _ __   / \\  |_ _|
| |_) / _ \\| |/ / _ \\ '_ ` _ \\ / _ \\| '_ \\ / _ \\  | |
|  __/ (_) |   <  __/ | | | | | (_) | | | / ___ \\ | |
|_|   \\___/|_|\\_\\___|_| |_| |_|\\___/|_| |_/_/   \\_\\___|
    Vision AI plays Pokemon FireRed (Gemini 2.0 Flash)
    """)

    # Validate API key
    if not settings.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    # Reset goals if requested
    if args.reset_goals:
        plans_file = settings.PROJECT_ROOT / "agent" / "planning" / "active_plans.json"
        if plans_file.exists():
            plans_file.unlink()
            logger.info("Goals reset - starting fresh")

    # Initialize database
    from agent.core.db import init_db
    init_db()

    # Initialize and run
    from agent.core.game_loop import GameLoop

    agent = GameLoop()
    logger.info(f"Starting agent with {args.interval}s tick interval")
    agent.run()


if __name__ == "__main__":
    main()
