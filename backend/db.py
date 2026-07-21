import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


@contextmanager
def get_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                token TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL,
                score REAL,
                summary TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                flags TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()


def insert_candidate(token, name, email, role):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO candidates (token, name, email, role, status) VALUES (%s, %s, %s, %s, 'pending')",
            (token, name, email, role),
        )
        conn.commit()


def get_candidate(token):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM candidates WHERE token = %s", (token,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_candidate_status(token, status):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE candidates SET status = %s WHERE token = %s", (status, token))
        conn.commit()


def set_candidate_score(token, score, summary):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE candidates SET score = %s, summary = %s, status = 'completed' WHERE token = %s",
            (score, summary, token),
        )
        conn.commit()


def add_flag(token, reason):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT flags FROM candidates WHERE token = %s", (token,))
        row = cur.fetchone()
        existing = row["flags"] if row and row["flags"] else ""
        updated = f"{existing};{reason}" if existing else reason
        cur.execute("UPDATE candidates SET flags = %s WHERE token = %s", (updated, token))
        conn.commit()


def get_all_candidates():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM candidates ORDER BY created_at DESC")
        rows = cur.fetchall()
        return [dict(r) for r in rows]
