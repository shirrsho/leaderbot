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

-- Remembers where we stopped paginating each subreddit, so the next run
-- continues from older posts instead of re-pulling the newest ones.
CREATE TABLE IF NOT EXISTS cursors (
    source_key TEXT PRIMARY KEY,   -- e.g. "reddit:smallbusiness"
    after TEXT
);

-- Companies found via map search + AI-shortlisted as probable customers.
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id TEXT UNIQUE NOT NULL,   -- external id (e.g. osm node id)
    name TEXT,
    category TEXT,
    address TEXT,
    phone TEXT,
    website TEXT,
    lat TEXT,
    lon TEXT,
    source TEXT,
    is_customer INTEGER,
    confidence REAL,
    reason TEXT,
    fit_signals TEXT,
    query TEXT,
    location TEXT,
    created_at TEXT
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


def upsert_company(row: dict):
    """Insert or update a company by its external company_id."""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO companies
        (company_id, name, category, address, phone, website, lat, lon, source,
         is_customer, confidence, reason, fit_signals, query, location, created_at)
        VALUES (:company_id, :name, :category, :address, :phone, :website, :lat,
                :lon, :source, :is_customer, :confidence, :reason, :fit_signals,
                :query, :location, :created_at)
        ON CONFLICT(company_id) DO UPDATE SET
            is_customer=excluded.is_customer, confidence=excluded.confidence,
            reason=excluded.reason, fit_signals=excluded.fit_signals,
            phone=excluded.phone, website=excluded.website,
            query=excluded.query, location=excluded.location,
            created_at=excluded.created_at
        """,
        row,
    )
    conn.commit()
    conn.close()


def fetch_companies(min_confidence: float = 0.0, only_customers: bool = True):
    conn = get_conn()
    query = "SELECT * FROM companies WHERE confidence >= ?"
    params = [min_confidence]
    if only_customers:
        query += " AND is_customer = 1"
    query += " ORDER BY confidence DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
