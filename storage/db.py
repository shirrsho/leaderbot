"""SQLite storage for collected posts and extracted leads."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "leads.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,          -- reddit / facebook / manual
    post_id TEXT UNIQUE NOT NULL,
    author TEXT,
    text TEXT,
    post_url TEXT,
    is_lead INTEGER,               -- 0/1
    confidence REAL,
    reason TEXT,
    intent TEXT,
    urgency TEXT,
    contact_hint TEXT,
    created_at TEXT,
    reviewed INTEGER DEFAULT 0
);

-- Remembers where we stopped paginating each subreddit, so the next run
-- continues from older posts instead of re-pulling the newest ones.
CREATE TABLE IF NOT EXISTS cursors (
    source_key TEXT PRIMARY KEY,   -- e.g. "reddit:smallbusiness"
    after TEXT
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def upsert_lead(row: dict):
    """Insert a lead record; ignore if post_id already exists."""
    conn = get_conn()
    conn.execute(
        """
        INSERT OR IGNORE INTO leads
        (source, post_id, author, text, post_url, is_lead, confidence,
         reason, intent, urgency, contact_hint, created_at)
        VALUES (:source, :post_id, :author, :text, :post_url, :is_lead,
                :confidence, :reason, :intent, :urgency, :contact_hint, :created_at)
        """,
        row,
    )
    conn.commit()
    conn.close()


def get_cursor(source_key: str):
    conn = get_conn()
    row = conn.execute("SELECT after FROM cursors WHERE source_key = ?", (source_key,)).fetchone()
    conn.close()
    return row["after"] if row else None


def set_cursor(source_key: str, after):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO cursors (source_key, after) VALUES (?, ?)
        ON CONFLICT(source_key) DO UPDATE SET after = excluded.after
        """,
        (source_key, after),
    )
    conn.commit()
    conn.close()


def clear_cursor(source_key: str):
    conn = get_conn()
    conn.execute("DELETE FROM cursors WHERE source_key = ?", (source_key,))
    conn.commit()
    conn.close()


def fetch_leads(min_confidence: float = 0.0, only_leads: bool = True):
    conn = get_conn()
    query = "SELECT * FROM leads WHERE confidence >= ?"
    params = [min_confidence]
    if only_leads:
        query += " AND is_lead = 1"
    query += " ORDER BY confidence DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
