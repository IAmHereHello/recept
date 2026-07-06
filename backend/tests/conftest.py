import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

import app.database as database_module
import main as main_module


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient backed by a fresh temp SQLite file per test.

    Patches database_module.DB_PATH before the app's lifespan runs init_db(),
    so every request in this test hits an isolated schema/instance instead of
    the real backend/receptapp.db.
    """
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database_module, "DB_PATH", db_path)
    with TestClient(main_module.app) as c:
        yield c


def make_recipe(client, **overrides):
    body = {
        "name": "Spaghetti Bolognese",
        "description": "Classic",
        "cook_time": 45,
        "difficulty": "easy",
        "cuisine_type": "Italian",
        "is_vegetarian": False,
        "is_vegan": False,
        "ingredients": [
            {"name": "Pasta", "amount": "500", "unit": "g", "sort_order": 0},
            {"name": "Minced meat", "amount": "400", "unit": "g", "sort_order": 1},
        ],
        "steps": [
            {"sort_order": 1, "description": "Boil pasta"},
            {"sort_order": 2, "description": "Make sauce"},
        ],
    }
    body.update(overrides)
    resp = client.post("/recipes/", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()
