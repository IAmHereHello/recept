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
            description TEXT NOT NULL,
            wait_time_minutes INTEGER,
            track TEXT NOT NULL DEFAULT 'main' CHECK(track IN ('main','meanwhile'))
        );

        CREATE TABLE IF NOT EXISTS session_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS step_durations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            track TEXT NOT NULL DEFAULT 'main' CHECK(track IN ('main','meanwhile')),
            sort_order INTEGER NOT NULL,
            avg_seconds REAL NOT NULL,
            sample_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(recipe_id, track, sort_order)
        );

        CREATE TABLE IF NOT EXISTS step_time_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            track TEXT NOT NULL DEFAULT 'main' CHECK(track IN ('main','meanwhile')),
            sort_order INTEGER NOT NULL,
            cook_session_id INTEGER NOT NULL REFERENCES cook_sessions(id) ON DELETE CASCADE,
            seconds INTEGER NOT NULL,
            counted INTEGER,
            recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
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

        CREATE TABLE IF NOT EXISTS freezer_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            cook_session_id INTEGER REFERENCES cook_sessions(id) ON DELETE SET NULL,
            portions_total INTEGER NOT NULL CHECK(portions_total > 0),
            portions_remaining INTEGER NOT NULL CHECK(portions_remaining >= 0),
            frozen_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            added_by TEXT CHECK(added_by IN ('michael','rachel')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS meal_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            day TEXT NOT NULL CHECK(day IN ('mon','tue','wed','thu','fri','sat','sun')),
            recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
            locked INTEGER NOT NULL DEFAULT 0,
            UNIQUE(week_start, day)
        );

        CREATE TABLE IF NOT EXISTS meal_plan_sides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            day TEXT NOT NULL CHECK(day IN ('mon','tue','wed','thu','fri','sat','sun')),
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            UNIQUE(week_start, day, recipe_id)
        );
    """)

    # Migration: cooked_by was added after the initial cook_sessions table;
    # existing databases need the column added since CREATE TABLE IF NOT EXISTS
    # is a no-op when the table already exists.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(cook_sessions)").fetchall()]
    if "cooked_by" not in cols:
        conn.execute("ALTER TABLE cook_sessions ADD COLUMN cooked_by TEXT CHECK(cooked_by IN ('michael','rachel'))")

    # Migration: side dish / baking categories, added after the initial recipes table.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(recipes)").fetchall()]
    if "is_side_dish" not in cols:
        conn.execute("ALTER TABLE recipes ADD COLUMN is_side_dish INTEGER NOT NULL DEFAULT 0")
    if "is_baking" not in cols:
        conn.execute("ALTER TABLE recipes ADD COLUMN is_baking INTEGER NOT NULL DEFAULT 0")

    # Migration: photo uploader attribution, added after the initial photos table.
    # Existing photos get NULL (unknown uploader) since there's no way to backfill this.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(photos)").fetchall()]
    if "uploaded_by" not in cols:
        conn.execute("ALTER TABLE photos ADD COLUMN uploaded_by TEXT CHECK(uploaded_by IN ('michael','rachel'))")

    # Migration: cooking mode, added after the initial cook_sessions table.
    # `cooking_mode` distinguishes sessions started via the new guided flow from
    # legacy instant ones — this matters because it's what makes the cook (not
    # just the other person) show up in their own pending-review queue. Existing
    # rows are backfilled to cooking_mode=0 (via the column DEFAULT) and
    # finished_at=cooked_at (immediately "done", matching their old behavior),
    # so upgrading never retroactively surfaces a backlog of self-review prompts.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(cook_sessions)").fetchall()]
    if "cooking_mode" not in cols:
        conn.execute("ALTER TABLE cook_sessions ADD COLUMN cooking_mode INTEGER NOT NULL DEFAULT 0")
    if "current_step" not in cols:
        conn.execute("ALTER TABLE cook_sessions ADD COLUMN current_step INTEGER NOT NULL DEFAULT 0")
    if "step_started_at" not in cols:
        conn.execute("ALTER TABLE cook_sessions ADD COLUMN step_started_at TEXT")
    if "timer_seconds" not in cols:
        conn.execute("ALTER TABLE cook_sessions ADD COLUMN timer_seconds INTEGER")
    if "timer_started_at" not in cols:
        conn.execute("ALTER TABLE cook_sessions ADD COLUMN timer_started_at TEXT")
    if "finished_at" not in cols:
        conn.execute("ALTER TABLE cook_sessions ADD COLUMN finished_at TEXT")
        conn.execute("UPDATE cook_sessions SET finished_at = cooked_at WHERE finished_at IS NULL")

    # Migration: freezer tracking fields, added after the initial recipes table.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(recipes)").fetchall()]
    if "portions" not in cols:
        conn.execute("ALTER TABLE recipes ADD COLUMN portions INTEGER")
    if "is_freezable" not in cols:
        conn.execute("ALTER TABLE recipes ADD COLUMN is_freezable INTEGER NOT NULL DEFAULT 1")
    if "freezer_months" not in cols:
        conn.execute("ALTER TABLE recipes ADD COLUMN freezer_months INTEGER")

    # Migration: link a meal_plan day to the freezer batch it was suggested from.
    # SET NULL on delete so consuming/removing the freezer item detaches the
    # day's badge instead of deleting the day's plan entry.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(meal_plan)").fetchall()]
    if "freezer_item_id" not in cols:
        conn.execute("ALTER TABLE meal_plan ADD COLUMN freezer_item_id INTEGER REFERENCES freezer_items(id) ON DELETE SET NULL")

    # Migration: last_activity_at drives the "close an abandoned cooking
    # session after inactivity" feature — updated on every step/timer action
    # plus a frontend heartbeat while the cooking page is open and visible.
    # Backfill only matters for rows still in progress (finished_at IS NULL);
    # finished sessions never get staleness-checked, so leaving them NULL is fine.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(cook_sessions)").fetchall()]
    if "last_activity_at" not in cols:
        conn.execute("ALTER TABLE cook_sessions ADD COLUMN last_activity_at TEXT")
        conn.execute(
            "UPDATE cook_sessions SET last_activity_at = COALESCE(step_started_at, cooked_at) WHERE finished_at IS NULL"
        )

    # Migration: steps gain an explicit wait time (replacing regex-parsing of
    # the description text) and a track ('main' vs 'meanwhile') so the recipe
    # builder can hold a pool of flexible-timing steps alongside the guided
    # main sequence. Existing rows default to track='main' via the column
    # DEFAULT, which is exactly the old (single-track) behavior.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(steps)").fetchall()]
    if "wait_time_minutes" not in cols:
        conn.execute("ALTER TABLE steps ADD COLUMN wait_time_minutes INTEGER")
    if "track" not in cols:
        conn.execute("ALTER TABLE steps ADD COLUMN track TEXT NOT NULL DEFAULT 'main' CHECK(track IN ('main','meanwhile'))")

    # Migration: cook_sessions gain a nullable group_id linking two sessions
    # started together via "Kook samen met..." (paired multi-recipe cooking).
    # Most sessions are solo and stay NULL.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(cook_sessions)").fetchall()]
    if "group_id" not in cols:
        conn.execute("ALTER TABLE cook_sessions ADD COLUMN group_id INTEGER REFERENCES session_groups(id) ON DELETE SET NULL")

    conn.commit()
    conn.close()
