from datetime import date, datetime
from tests.conftest import make_recipe


def _freeze_today(monkeypatch, iso_date):
    import app.routers.planner as planner_module
    monkeypatch.setattr(planner_module, "_today", lambda: date.fromisoformat(iso_date))


def start_cooking(client, recipe_id, cooked_by="michael"):
    resp = client.post("/sessions/", json={"recipe_id": recipe_id, "cooked_by": cooked_by, "cooking_mode": True})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_status_defaults_when_nothing_active_or_planned(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")  # Monday

    status = client.get("/dashboard/status").json()

    assert status["cooking_active"] is False
    assert status["cooking_recipe_id"] == 0
    assert status["cooking_recipe_name"] == ""
    assert status["cook_time_remaining_seconds"] == 0
    assert status["planned_today_recipe_id"] == 0
    assert status["planned_today_recipe_name"] == ""
    # Real ISO 8601 with a timezone offset, never a naive timestamp.
    assert datetime.fromisoformat(status["updated_at"]).tzinfo is not None


def test_status_reports_planned_recipe_for_today(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-07")  # Wednesday
    recipe = make_recipe(client, name="Chili sin carne")
    client.put(
        "/plan/2026-01-05/wed",
        json={"week_start": "2026-01-05", "day": "wed", "recipe_id": recipe["id"], "locked": False},
    )

    status = client.get("/dashboard/status").json()

    assert status["planned_today_recipe_id"] == recipe["id"]
    assert status["planned_today_recipe_name"] == "Chili sin carne"


def test_status_ignores_plan_entries_on_other_days(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")  # Monday
    recipe = make_recipe(client)
    client.put(
        "/plan/2026-01-05/tue",
        json={"week_start": "2026-01-05", "day": "tue", "recipe_id": recipe["id"], "locked": False},
    )

    status = client.get("/dashboard/status").json()

    assert status["planned_today_recipe_id"] == 0
    assert status["planned_today_recipe_name"] == ""


def test_status_reports_active_cooking_session_and_estimate(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    # cook_time=45min, 2 steps -> 1350s flat share per step
    recipe = make_recipe(client, name="Spaghetti Bolognese")
    session = start_cooking(client, recipe["id"])

    status = client.get("/dashboard/status").json()

    assert status["cooking_active"] is True
    assert status["cooking_recipe_id"] == recipe["id"]
    assert status["cooking_recipe_name"] == "Spaghetti Bolognese"
    assert status["cook_time_remaining_seconds"] == 2700

    # An active per-step timer folds into the total estimate, not on top of it.
    client.post(f"/sessions/{session['id']}/timer", json={"seconds": 300})
    status = client.get("/dashboard/status").json()
    assert status["cook_time_remaining_seconds"] == 300 + 1350


def test_status_reports_zero_remaining_when_recipe_has_no_cook_time(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    recipe = make_recipe(client, cook_time=None)
    start_cooking(client, recipe["id"])

    status = client.get("/dashboard/status").json()

    assert status["cooking_active"] is True
    assert status["cook_time_remaining_seconds"] == 0


def test_status_clears_cooking_fields_once_finished(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    recipe = make_recipe(client)
    session = start_cooking(client, recipe["id"])
    client.post(f"/sessions/{session['id']}/finish")

    status = client.get("/dashboard/status").json()

    assert status["cooking_active"] is False
    assert status["cooking_recipe_id"] == 0
    assert status["cook_time_remaining_seconds"] == 0
