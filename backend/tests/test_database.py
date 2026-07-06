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
