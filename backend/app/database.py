import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "receptapp.db"


def get_db():
    # check_same_thread=False: FastAPI resolves sync dependencies and runs sync
    # endpoint functions via anyio's threadpool, which does not guarantee the same
    # worker thread across those calls. Without this, sqlite3 intermittently raises
    # "SQLite objects created in a thread can only be used in that same thread"
    # (~50% of requests), since this connection is only ever used within one request.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            cook_time INTEGER,
            difficulty TEXT CHECK(difficulty IN ('easy','medium','hard')),
            cuisine_type TEXT,
            is_vegetarian INTEGER NOT NULL DEFAULT 0,
            is_vegan INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            amount TEXT,
            unit TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            sort_order INTEGER NOT NULL,
            description TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cook_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            cooked_at TEXT NOT NULL DEFAULT (datetime('now')),
            notes TEXT,
            cooked_by TEXT CHECK(cooked_by IN ('michael','rachel'))
        );

        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cook_session_id INTEGER NOT NULL REFERENCES cook_sessions(id) ON DELETE CASCADE,
            file_path TEXT NOT NULL,
            uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cook_session_id INTEGER NOT NULL REFERENCES cook_sessions(id) ON DELETE CASCADE,
            user TEXT NOT NULL CHECK(user IN ('michael','rachel')),
            stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 5),
            rated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(cook_session_id, user)
        );

        CREATE TABLE IF NOT EXISTS meal_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            day TEXT NOT NULL CHECK(day IN ('mon','tue','wed','thu','fri','sat','sun')),
            recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
            locked INTEGER NOT NULL DEFAULT 0,
            UNIQUE(week_start, day)
        );
    """)

    # Migration: cooked_by was added after the initial cook_sessions table;
    # existing databases need the column added since CREATE TABLE IF NOT EXISTS
    # is a no-op when the table already exists.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(cook_sessions)").fetchall()]
    if "cooked_by" not in cols:
        conn.execute("ALTER TABLE cook_sessions ADD COLUMN cooked_by TEXT CHECK(cooked_by IN ('michael','rachel'))")

    conn.commit()
    conn.close()
