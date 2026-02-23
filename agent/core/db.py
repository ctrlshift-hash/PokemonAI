"""
PostgreSQL live feed push for the dashboard.
Uses the same pattern as ClaudeScape: single row upsert to live_feed table.
"""

import json
import logging

import psycopg2

from config import settings

logger = logging.getLogger(__name__)

_conn = None


def _get_conn():
    """Get or create a persistent database connection."""
    global _conn
    if _conn is None or _conn.closed:
        url = settings.DATABASE_URL
        if not url:
            return None
        try:
            _conn = psycopg2.connect(url)
            _conn.autocommit = True
            _init_table(_conn)
            logger.info("Connected to PostgreSQL")
        except Exception as e:
            logger.warning(f"Could not connect to PostgreSQL: {e}")
            _conn = None
            return None
    return _conn


def _init_table(conn):
    """Create the live_feed and sessions tables if they don't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS live_feed (
                id INTEGER PRIMARY KEY DEFAULT 1,
                data JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute(
            "INSERT INTO live_feed (id, data) VALUES (1, '{}') "
            "ON CONFLICT (id) DO NOTHING"
        )
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id SERIAL PRIMARY KEY,
                started_at TIMESTAMP DEFAULT NOW(),
                ended_at TIMESTAMP,
                ticks INTEGER DEFAULT 0,
                badges INTEGER DEFAULT 0,
                pokemon_caught INTEGER DEFAULT 0,
                whiteouts INTEGER DEFAULT 0,
                duration_secs INTEGER DEFAULT 0
            )
        """)


def init_db():
    """Initialize database connection and tables."""
    conn = _get_conn()
    if conn:
        logger.info("Database initialized")
    else:
        logger.warning("Database not available - dashboard will not update")


def push_live_feed(feed_data):
    """Push the latest tick data to PostgreSQL (upserts a single row)."""
    try:
        conn = _get_conn()
        if conn is None:
            return
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE live_feed SET data = %s, updated_at = NOW() WHERE id = 1",
                (json.dumps(feed_data, default=str),),
            )
    except Exception as e:
        logger.warning(f"Failed to push live feed: {e}")
        global _conn
        _conn = None


def create_session():
    """Create a new session record. Returns the session ID."""
    try:
        conn = _get_conn()
        if conn is None:
            return None
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (started_at) VALUES (NOW()) RETURNING id"
            )
            row = cur.fetchone()
            sid = row[0] if row else None
            logger.info(f"Session created: #{sid}")
            return sid
    except Exception as e:
        logger.warning(f"Failed to create session: {e}")
        return None


def update_session(session_id, ticks=0, badges=0, pokemon_caught=0, whiteouts=0):
    """Update a running session's stats."""
    try:
        conn = _get_conn()
        if conn is None:
            return
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE sessions
                   SET ticks = %s,
                       badges = %s,
                       pokemon_caught = %s,
                       whiteouts = %s,
                       duration_secs = EXTRACT(EPOCH FROM (NOW() - started_at))::int
                   WHERE id = %s""",
                (ticks, badges, pokemon_caught, whiteouts, session_id),
            )
    except Exception as e:
        logger.warning(f"Failed to update session: {e}")


def end_session(session_id, ticks=0, badges=0, pokemon_caught=0, whiteouts=0):
    """End a session with final stats."""
    try:
        conn = _get_conn()
        if conn is None:
            return
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE sessions
                   SET ended_at = NOW(),
                       ticks = %s,
                       badges = %s,
                       pokemon_caught = %s,
                       whiteouts = %s,
                       duration_secs = EXTRACT(EPOCH FROM (NOW() - started_at))::int
                   WHERE id = %s""",
                (ticks, badges, pokemon_caught, whiteouts, session_id),
            )
            logger.info(f"Session #{session_id} ended: {ticks} ticks")
    except Exception as e:
        logger.warning(f"Failed to end session: {e}")
