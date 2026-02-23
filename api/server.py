"""
Lightweight API server for Railway.
Reads live feed data from PostgreSQL and serves it to the Vercel frontend.
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def init_db():
    """Create tables if they don't exist."""
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL not set")
        return
    conn = psycopg2.connect(DATABASE_URL)
    try:
        conn.autocommit = True
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
    finally:
        conn.close()


def get_live_feed():
    """Read the latest live feed row."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT data, updated_at FROM live_feed WHERE id = 1")
            row = cur.fetchone()
            if row:
                return row[0], row[1]
            return None, None
    finally:
        conn.close()


def get_sessions(limit=10):
    """Get recent sessions."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, started_at, ended_at, ticks, badges,
                          pokemon_caught, whiteouts, duration_secs
                   FROM sessions ORDER BY id DESC LIMIT %s""",
                (limit,),
            )
            rows = cur.fetchall()
            sessions = []
            for row in rows:
                dur = row[7] or 0
                hours, rem = divmod(dur, 3600)
                mins, secs = divmod(rem, 60)
                sessions.append({
                    "id": row[0],
                    "started_at": row[1].isoformat() if row[1] else None,
                    "ended_at": row[2].isoformat() if row[2] else None,
                    "ticks": row[3] or 0,
                    "badges": row[4] or 0,
                    "pokemon_caught": row[5] or 0,
                    "whiteouts": row[6] or 0,
                    "duration": f"{hours}h {mins}m {secs}s" if dur > 0 else "running...",
                })
            return sessions
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/feed"):
            try:
                data, updated_at = get_live_feed()
                body = json.dumps(data or {})
                self.send_response(200)
            except Exception as e:
                body = json.dumps({"error": str(e)})
                self.send_response(500)
        elif self.path.startswith("/sessions"):
            try:
                sessions = get_sessions()
                body = json.dumps(sessions)
                self.send_response(200)
            except Exception as e:
                body = json.dumps({"error": str(e)})
                self.send_response(500)
        elif self.path == "/health":
            body = json.dumps({"status": "ok"})
            self.send_response(200)
        else:
            body = json.dumps({"error": "not found"})
            self.send_response(404)

        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Pokemon AI API server running on port {port}")
    server.serve_forever()
