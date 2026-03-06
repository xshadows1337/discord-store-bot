"""
Persistent ticket storage using SQLite.
Tracks all tickets, their state, feedback, and activity logs.
"""

import sqlite3
import time
import json
from pathlib import Path
from loguru import logger

_DATA_DIR = Path(__file__).parent.parent
_DB_PATH = _DATA_DIR / 'tickets.db'


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_ticket_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER UNIQUE NOT NULL,
            guild_id INTEGER NOT NULL,
            opener_id INTEGER NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            topic TEXT,
            priority TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            claimed_by INTEGER,
            locked INTEGER NOT NULL DEFAULT 0,
            number INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            closed_at INTEGER,
            closed_by INTEGER,
            close_reason TEXT
        );

        CREATE TABLE IF NOT EXISTS ticket_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        );

        CREATE TABLE IF NOT EXISTS ticket_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            details TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        );

        CREATE TABLE IF NOT EXISTS ticket_counter (
            guild_id INTEGER PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0
        );
        """)
        conn.commit()
        logger.info("[TICKET_DB] Database initialized.")
    finally:
        conn.close()


# ── Counter ──────────────────────────────────────────────────────────────────

def next_ticket_number(guild_id: int) -> int:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT count FROM ticket_counter WHERE guild_id=?", (guild_id,)).fetchone()
        if row:
            new_count = row['count'] + 1
            conn.execute("UPDATE ticket_counter SET count=? WHERE guild_id=?", (new_count, guild_id))
        else:
            new_count = 1
            conn.execute("INSERT INTO ticket_counter (guild_id, count) VALUES (?, ?)", (guild_id, new_count))
        conn.commit()
        return new_count
    finally:
        conn.close()


# ── CRUD ─────────────────────────────────────────────────────────────────────

def create_ticket(channel_id: int, guild_id: int, opener_id: int, category: str, topic: str = None, number: int = 0) -> dict:
    conn = _get_conn()
    try:
        now = int(time.time())
        conn.execute(
            """INSERT INTO tickets (channel_id, guild_id, opener_id, category, topic, number, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (channel_id, guild_id, opener_id, category, topic, number, now),
        )
        conn.commit()
        return get_ticket_by_channel(channel_id)
    finally:
        conn.close()


def get_ticket_by_channel(channel_id: int) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM tickets WHERE channel_id=?", (channel_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_ticket_by_id(ticket_id: int) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_open_tickets_for_user(guild_id: int, opener_id: int, category: str = None) -> list[dict]:
    conn = _get_conn()
    try:
        if category:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE guild_id=? AND opener_id=? AND category=? AND status='open'",
                (guild_id, opener_id, category),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE guild_id=? AND opener_id=? AND status='open'",
                (guild_id, opener_id),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_open_tickets(guild_id: int) -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE guild_id=? AND status='open' ORDER BY created_at DESC",
            (guild_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_ticket(channel_id: int, **kwargs) -> dict | None:
    conn = _get_conn()
    try:
        allowed = {'category', 'topic', 'priority', 'status', 'claimed_by', 'locked', 'closed_at', 'closed_by', 'close_reason', 'opener_id'}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return get_ticket_by_channel(channel_id)
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [channel_id]
        conn.execute(f"UPDATE tickets SET {set_clause} WHERE channel_id=?", values)
        conn.commit()
        return get_ticket_by_channel(channel_id)
    finally:
        conn.close()


def close_ticket(channel_id: int, closed_by: int, reason: str = None) -> dict | None:
    return update_ticket(
        channel_id,
        status='closed',
        closed_at=int(time.time()),
        closed_by=closed_by,
        close_reason=reason,
    )


# ── Feedback ─────────────────────────────────────────────────────────────────

def save_feedback(ticket_id: int, user_id: int, rating: int, comment: str = None):
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO ticket_feedback (ticket_id, user_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
            (ticket_id, user_id, rating, comment, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def get_feedback(ticket_id: int) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM ticket_feedback WHERE ticket_id=? ORDER BY id DESC LIMIT 1", (ticket_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── Logs ─────────────────────────────────────────────────────────────────────

def log_ticket_action(ticket_id: int, action: str, user_id: int, details: str = None):
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO ticket_logs (ticket_id, action, user_id, details, created_at) VALUES (?, ?, ?, ?, ?)",
            (ticket_id, action, user_id, details, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def get_ticket_logs(ticket_id: int) -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM ticket_logs WHERE ticket_id=? ORDER BY created_at ASC",
            (ticket_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Stats ────────────────────────────────────────────────────────────────────

def get_ticket_stats(guild_id: int) -> dict:
    conn = _get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) as c FROM tickets WHERE guild_id=?", (guild_id,)).fetchone()['c']
        open_count = conn.execute("SELECT COUNT(*) as c FROM tickets WHERE guild_id=? AND status='open'", (guild_id,)).fetchone()['c']
        closed = conn.execute("SELECT COUNT(*) as c FROM tickets WHERE guild_id=? AND status='closed'", (guild_id,)).fetchone()['c']
        avg_rating = conn.execute(
            """SELECT AVG(f.rating) as avg_r FROM ticket_feedback f
               JOIN tickets t ON f.ticket_id = t.id WHERE t.guild_id=?""",
            (guild_id,),
        ).fetchone()['avg_r']
        return {
            'total': total,
            'open': open_count,
            'closed': closed,
            'avg_rating': round(avg_rating, 1) if avg_rating else None,
        }
    finally:
        conn.close()


# Initialize on import
init_ticket_db()
