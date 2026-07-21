import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "interviews.db"))


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                token TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL,
                score REAL,
                summary TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(candidates)")}
        if "flags" not in existing_columns:
            conn.execute("ALTER TABLE candidates ADD COLUMN flags TEXT NOT NULL DEFAULT ''")
        conn.commit()


def add_flag(token, reason):
    with get_connection() as conn:
        row = conn.execute("SELECT flags FROM candidates WHERE token = ?", (token,)).fetchone()
        existing = row["flags"] if row and row["flags"] else ""
        updated = f"{existing};{reason}" if existing else reason
        conn.execute("UPDATE candidates SET flags = ? WHERE token = ?", (updated, token))
        conn.commit()


def insert_candidate(token, name, email, role):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO candidates (token, name, email, role, status) VALUES (?, ?, ?, ?, 'pending')",
            (token, name, email, role),
        )
        conn.commit()


def get_candidate(token):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM candidates WHERE token = ?", (token,)).fetchone()
        return dict(row) if row else None


def update_candidate_status(token, status):
    with get_connection() as conn:
        conn.execute("UPDATE candidates SET status = ? WHERE token = ?", (status, token))
        conn.commit()


def set_candidate_score(token, score, summary):
    with get_connection() as conn:
        conn.execute(
            "UPDATE candidates SET score = ?, summary = ?, status = 'completed' WHERE token = ?",
            (score, summary, token),
        )
        conn.commit()


def get_all_candidates():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM candidates ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
