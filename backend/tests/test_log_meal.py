from tests.conftest import make_recipe


def test_log_meal_creates_finished_session(client):
    recipe = make_recipe(client)
    resp = client.post("/sessions/log", json={
        "recipe_id": recipe["id"], "cooked_at": "2026-03-10", "cooked_by": "michael",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["finished_at"] is not None
    assert body["cooked_at"].startswith("2026-03-10")
    assert client.get("/sessions/active").json() is None  # not an in-progress session


def test_log_meal_triggers_review_for_both_users(client):
    recipe = make_recipe(client)
    client.post("/sessions/log", json={
        "recipe_id": recipe["id"], "cooked_at": "2026-03-10", "cooked_by": "michael",
    })
    assert len(client.get("/sessions/pending/rachel").json()) == 1
    assert len(client.get("/sessions/pending/michael").json()) == 1  # logger reviews it too


def test_log_meal_fills_empty_plan_day(client):
    recipe = make_recipe(client)
    # 2026-03-10 is a Tuesday; its week starts Monday 2026-03-09
    client.post("/sessions/log", json={"recipe_id": recipe["id"], "cooked_at": "2026-03-10"})

    week = client.get("/plan/2026-03-09").json()
    assert week["tue"]["recipe_id"] == recipe["id"]


def test_log_meal_reports_conflict_without_overwriting(client):
    planned = make_recipe(client, name="Al gepland")
    eaten = make_recipe(client, name="Wat we aten")
    client.put("/plan/2026-03-09/tue", json={"week_start": "2026-03-09", "day": "tue", "recipe_id": planned["id"], "locked": False})

    resp = client.post("/sessions/log", json={"recipe_id": eaten["id"], "cooked_at": "2026-03-10"})
    conflict = resp.json()["plan_conflict"]
    assert conflict["day"] == "tue"
    assert conflict["existing_recipe_id"] == planned["id"]
    assert conflict["cooked_recipe_id"] == eaten["id"]
    # plan is left untouched — the client asks the user first
    assert client.get("/plan/2026-03-09").json()["tue"]["recipe_id"] == planned["id"]


def test_log_meal_no_conflict_when_day_holds_same_recipe(client):
    recipe = make_recipe(client)
    client.put("/plan/2026-03-09/tue", json={"week_start": "2026-03-09", "day": "tue", "recipe_id": recipe["id"], "locked": False})

    resp = client.post("/sessions/log", json={"recipe_id": recipe["id"], "cooked_at": "2026-03-10"})
    assert resp.json()["plan_conflict"] is None


def test_log_meal_leaves_locked_day_alone(client):
    planned = make_recipe(client, name="Vast")
    eaten = make_recipe(client, name="Gegeten")
    client.put("/plan/2026-03-09/tue", json={"week_start": "2026-03-09", "day": "tue", "recipe_id": planned["id"], "locked": True})

    resp = client.post("/sessions/log", json={"recipe_id": eaten["id"], "cooked_at": "2026-03-10"})
    assert resp.json()["plan_conflict"] is None  # locked -> not touched, not reported
    assert client.get("/plan/2026-03-09").json()["tue"]["recipe_id"] == planned["id"]


def test_finish_cooking_adds_recipe_to_its_day(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={
        "recipe_id": recipe["id"], "cooked_by": "michael", "cooking_mode": True,
    }).json()
    resp = client.post(f"/sessions/{session['id']}/finish")
    assert resp.status_code == 200

    cooked_date = resp.json()["cooked_at"][:10]
    from datetime import date, timedelta
    d = date.fromisoformat(cooked_date)
    ws = (d - timedelta(days=d.weekday())).isoformat()
    day = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][d.weekday()]
    assert client.get(f"/plan/{ws}").json()[day]["recipe_id"] == recipe["id"]


def test_finish_cooking_reports_plan_conflict(client):
    planned = make_recipe(client, name="Gepland")
    cooking = make_recipe(client, name="Gekookt")
    from datetime import date, timedelta
    d = date.today()
    ws = (d - timedelta(days=d.weekday())).isoformat()
    day = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][d.weekday()]
    client.put(f"/plan/{ws}/{day}", json={"week_start": ws, "day": day, "recipe_id": planned["id"], "locked": False})

    session = client.post("/sessions/", json={
        "recipe_id": cooking["id"], "cooked_by": "michael", "cooking_mode": True,
    }).json()
    resp = client.post(f"/sessions/{session['id']}/finish")
    assert resp.json()["plan_conflict"]["existing_recipe_id"] == planned["id"]
