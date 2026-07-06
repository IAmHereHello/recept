from tests.conftest import make_recipe


def test_week_start_normalizes_any_weekday_to_monday(client):
    recipe = make_recipe(client)
    # 2026-01-07 is a Wednesday; the same week's Monday is 2026-01-05.
    client.put("/plan/2026-01-07/wed", json={"week_start": "2026-01-07", "day": "wed", "recipe_id": recipe["id"], "locked": False})

    week_via_monday = client.get("/plan/2026-01-05").json()
    week_via_wednesday = client.get("/plan/2026-01-07").json()

    assert week_via_monday == week_via_wednesday
    assert week_via_monday["wed"]["recipe_id"] == recipe["id"]


def test_get_week_empty_days_are_null(client):
    week = client.get("/plan/2026-01-05").json()
    assert set(week.keys()) == {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    assert all(v is None for v in week.values())


def test_set_and_clear_day(client):
    recipe = make_recipe(client)
    client.put("/plan/2026-01-05/mon", json={"week_start": "2026-01-05", "day": "mon", "recipe_id": recipe["id"], "locked": False})
    assert client.get("/plan/2026-01-05").json()["mon"]["recipe_id"] == recipe["id"]

    resp = client.delete("/plan/2026-01-05/mon")
    assert resp.status_code == 204
    assert client.get("/plan/2026-01-05").json()["mon"] is None


def test_suggest_boosts_unrated_and_penalizes_recently_cooked(client):
    fresh = make_recipe(client, name="Never Cooked")
    stale = make_recipe(client, name="Cooked Yesterday")

    week_start = "2026-01-05"
    # cooked the day before the planning week -> within the 14-day cooldown
    session = client.post("/sessions/", json={"recipe_id": stale["id"], "cooked_at": "2026-01-04T18:00:00", "cooked_by": "michael"}).json()
    client.post(f"/sessions/{session['id']}/rate", json={"user": "michael", "stars": 4})
    client.post(f"/sessions/{session['id']}/rate", json={"user": "rachel", "stars": 4})

    suggestions = client.post(f"/plan/suggest/{week_start}").json()
    suggested_ids = [r["id"] for r in suggestions.values() if r]

    # fresh: unrated -> 3.0 + 0.5 boost = 3.5
    # stale: rated 4.0 avg, but within cooldown -> 4.0 - 1.5 = 2.5
    # fresh should clearly rank ahead of stale.
    assert fresh["id"] in suggested_ids
    assert suggested_ids.index(fresh["id"]) < suggested_ids.index(stale["id"])


def test_suggest_respects_locked_days(client):
    recipe_a = make_recipe(client, name="Recipe A")
    recipe_b = make_recipe(client, name="Recipe B")
    week_start = "2026-01-05"

    client.put(f"/plan/{week_start}/mon", json={"week_start": week_start, "day": "mon", "recipe_id": recipe_a["id"], "locked": True})

    suggestions = client.post(f"/plan/suggest/{week_start}").json()
    assert "mon" not in suggestions  # locked days are omitted, not overwritten
    # the locked recipe should not be suggested again on another day
    other_day_ids = [r["id"] for r in suggestions.values() if r]
    assert recipe_a["id"] not in other_day_ids


def test_suggest_vegetarian_only_filter(client):
    make_recipe(client, name="Veggie", is_vegetarian=True)
    make_recipe(client, name="Meaty", is_vegetarian=False)
    week_start = "2026-01-05"

    suggestions = client.post(f"/plan/suggest/{week_start}", params={"vegetarian_only": True}).json()
    suggested_names = {r["name"] for r in suggestions.values() if r}
    assert suggested_names == {"Veggie"}


def test_grocery_list_aggregates_ingredients_by_recipe(client):
    recipe = make_recipe(client)
    week_start = "2026-01-05"
    client.put(f"/plan/{week_start}/mon", json={"week_start": week_start, "day": "mon", "recipe_id": recipe["id"], "locked": False})

    resp = client.post("/plan/grocery", json={"week_start": week_start})
    assert resp.status_code == 200
    body = resp.json()
    assert recipe["name"] in body["by_recipe"]
    ingredient_names = {i["name"] for i in body["by_recipe"][recipe["name"]]}
    assert ingredient_names == {"Pasta", "Minced meat"}


def test_grocery_list_empty_week(client):
    resp = client.post("/plan/grocery", json={"week_start": "2026-01-05"})
    assert resp.json()["by_recipe"] == {}
