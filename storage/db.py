"""SQLite storage for collected posts and extracted leads."""
import os
import sqlite3
from pathlib import Path

# Override with LEADS_DB_PATH to point at a mounted volume in Docker so the
# database survives container recreation/rebuilds.
DB_PATH = Path(os.environ.get(
    "LEADS_DB_PATH",
    Path(__file__).resolve().parent.parent / "leads.db",
))

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
