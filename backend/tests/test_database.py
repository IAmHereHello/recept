import sqlite3
import threading
import app.database as database_module


def test_get_db_connection_usable_across_threads(tmp_path, monkeypatch):
    """Regression test for the fixed 'Niet gevonden' bug: FastAPI runs sync
    dependencies/endpoints via anyio's threadpool without guaranteeing the same
    worker thread across calls, so the connection from get_db() must be usable
    from a thread other than the one that created it. Without
    check_same_thread=False in database.py, this raises sqlite3.ProgrammingError.
    """
    db_path = tmp_path / "thread_test.db"
    monkeypatch.setattr(database_module, "DB_PATH", db_path)
    database_module.init_db()

    gen = database_module.get_db()
    conn = next(gen)

    result = {}

    def use_from_other_thread():
        try:
            conn.execute("SELECT 1").fetchone()
            result["ok"] = True
        except Exception as e:
            result["ok"] = False
            result["error"] = repr(e)

    t = threading.Thread(target=use_from_other_thread)
    t.start()
    t.join()

    gen.close()
    assert result.get("ok"), result.get("error")


def test_freezer_migration_adds_columns_to_pre_existing_db(tmp_path, monkeypatch):
    """Regression test for the freezer inventory feature: an existing database
    (built before freezer_items existed) must gain recipes.portions/is_freezable/
    freezer_months and meal_plan.freezer_item_id via ALTER TABLE when init_db()
    runs again, without losing data or erroring. meal_plan.freezer_item_id is the
    first REFERENCES column ever added via ALTER TABLE ADD COLUMN in this repo
    (existing ALTERs are plain scalars), so this also exercises that it's valid
    SQLite syntax on a nullable, no-default column.
    """
    db_path = tmp_path / "pre_freezer.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            is_vegetarian INTEGER NOT NULL DEFAULT 0,
            is_vegan INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE meal_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            day TEXT NOT NULL,
            recipe_id INTEGER,
            locked INTEGER NOT NULL DEFAULT 0,
            UNIQUE(week_start, day)
        );
    """)
    conn.execute("INSERT INTO recipes (name) VALUES ('Oude Stamppot')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(database_module, "DB_PATH", db_path)
    database_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    recipe_cols = [row[1] for row in conn.execute("PRAGMA table_info(recipes)").fetchall()]
    assert {"portions", "is_freezable", "freezer_months"} <= set(recipe_cols)

    plan_cols = [row[1] for row in conn.execute("PRAGMA table_info(meal_plan)").fetchall()]
    assert "freezer_item_id" in plan_cols

    row = conn.execute("SELECT name, is_freezable, portions, freezer_months FROM recipes").fetchone()
    assert row["name"] == "Oude Stamppot"
    assert row["is_freezable"] == 1
    assert row["portions"] is None
    assert row["freezer_months"] is None
    conn.close()

    # Re-running init_db() must be idempotent (no errors on already-migrated schema).
    database_module.init_db()


def test_last_activity_migration_adds_column_and_backfills_in_progress_rows(tmp_path, monkeypatch):
    """Regression test for the cooking-session inactivity feature: an existing
    database (built before last_activity_at existed) must gain the column via
    ALTER TABLE, with in-progress rows backfilled from step_started_at so
    staleness can be computed immediately without a NULL reference. Finished
    rows are intentionally left NULL since they're never staleness-checked.
    """
    db_path = tmp_path / "pre_last_activity.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            is_vegetarian INTEGER NOT NULL DEFAULT 0,
            is_vegan INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE cook_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            cooked_at TEXT NOT NULL DEFAULT (datetime('now')),
            notes TEXT,
            cooked_by TEXT,
            cooking_mode INTEGER NOT NULL DEFAULT 0,
            current_step INTEGER NOT NULL DEFAULT 0,
            step_started_at TEXT,
            timer_seconds INTEGER,
            timer_started_at TEXT,
            finished_at TEXT
        );
    """)
    conn.execute("INSERT INTO recipes (name) VALUES ('Oude Stamppot')")
    conn.execute(
        "INSERT INTO cook_sessions (recipe_id, cooked_at, cooking_mode, step_started_at, finished_at) "
        "VALUES (1, '2026-01-01T10:00:00', 1, '2026-01-01T10:05:00', NULL)"
    )
    conn.execute(
        "INSERT INTO cook_sessions (recipe_id, cooked_at, cooking_mode, finished_at) "
        "VALUES (1, '2026-01-01T09:00:00', 0, '2026-01-01T09:00:00')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(database_module, "DB_PATH", db_path)
    database_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cols = [row[1] for row in conn.execute("PRAGMA table_info(cook_sessions)").fetchall()]
    assert "last_activity_at" in cols

    rows = {row["cooking_mode"]: row for row in conn.execute("SELECT * FROM cook_sessions").fetchall()}
    assert rows[1]["last_activity_at"] == "2026-01-01T10:05:00"
    assert rows[0]["last_activity_at"] is None
    conn.close()

    # Re-running init_db() must be idempotent (no errors on already-migrated schema).
    database_module.init_db()


def test_init_db_creates_freezer_items_table(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr(database_module, "DB_PATH", db_path)
    database_module.init_db()

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(freezer_items)").fetchall()]
    assert set(cols) == {
        "id", "recipe_id", "cook_session_id", "portions_total", "portions_remaining",
        "frozen_at", "expires_at", "added_by", "created_at",
    }
    conn.close()
