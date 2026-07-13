from datetime import date
from tests.conftest import make_recipe


def _freeze_today(monkeypatch, iso_date):
    import app.routers.planner as planner_module
    monkeypatch.setattr(planner_module, "_today", lambda: date.fromisoformat(iso_date))


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


def test_suggest_boosts_freezer_item_nearing_expiry(client):
    week_start = "2026-01-05"
    freezer_recipe = make_recipe(client, name="Frozen Chili")
    other_recipe = make_recipe(client, name="Fresh Idea")
    # within FREEZER_BOOST_WINDOW_DAYS (14) of week_start
    item = client.post("/freezer/", json={
        "recipe_id": freezer_recipe["id"], "portions_total": 3, "expires_at": "2026-01-15",
    }).json()

    suggestions = client.post(f"/plan/suggest/{week_start}").json()
    assert suggestions["mon"]["from_freezer"] is True
    assert suggestions["mon"]["freezer_item_id"] == item["id"]
    assert suggestions["mon"]["portions_remaining"] == 3
    assert suggestions["mon"]["id"] == freezer_recipe["id"]

    # remaining days fall back to normal scoring, tagged from_freezer False
    other_days = [suggestions[d] for d in ["tue", "wed"] if suggestions[d]]
    assert all(s["from_freezer"] is False for s in other_days)


def test_suggest_ignores_freezer_item_outside_window(client):
    week_start = "2026-01-05"
    freezer_recipe = make_recipe(client, name="Frozen Chili")
    client.post("/freezer/", json={
        "recipe_id": freezer_recipe["id"], "portions_total": 3, "expires_at": "2026-03-01",
    })

    suggestions = client.post(f"/plan/suggest/{week_start}").json()
    assert suggestions["mon"]["from_freezer"] is False


def test_suggest_freezer_boost_respects_vegetarian_filter(client):
    week_start = "2026-01-05"
    meaty = make_recipe(client, name="Frozen Meat Stew", is_vegetarian=False)
    client.post("/freezer/", json={"recipe_id": meaty["id"], "portions_total": 2, "expires_at": "2026-01-15"})

    suggestions = client.post(f"/plan/suggest/{week_start}", params={"vegetarian_only": True}).json()
    assert all(s is None or s["id"] != meaty["id"] for s in suggestions.values())


def test_suggest_freezer_boost_excludes_locked_recipe(client):
    week_start = "2026-01-05"
    recipe = make_recipe(client, name="Frozen Chili")
    client.post("/freezer/", json={"recipe_id": recipe["id"], "portions_total": 2, "expires_at": "2026-01-15"})
    client.put(f"/plan/{week_start}/mon", json={"week_start": week_start, "day": "mon", "recipe_id": recipe["id"], "locked": True})

    suggestions = client.post(f"/plan/suggest/{week_start}").json()
    assert "mon" not in suggestions
    assert all(s is None or s["id"] != recipe["id"] for s in suggestions.values())


def test_set_day_with_freezer_item_reflected_in_get_week(client):
    week_start = "2026-01-05"
    recipe = make_recipe(client, name="Frozen Chili")
    item = client.post("/freezer/", json={"recipe_id": recipe["id"], "portions_total": 3}).json()

    client.put(f"/plan/{week_start}/mon", json={
        "week_start": week_start, "day": "mon", "recipe_id": recipe["id"],
        "locked": False, "freezer_item_id": item["id"],
    })

    week = client.get(f"/plan/{week_start}").json()
    assert week["mon"]["freezer_item_id"] == item["id"]
    assert week["mon"]["freezer"]["portions_remaining"] == 3


def test_grocery_list_aggregates_ingredients_by_recipe(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    recipe = make_recipe(client)
    week_start = "2026-01-05"
    client.put(f"/plan/{week_start}/mon", json={"week_start": week_start, "day": "mon", "recipe_id": recipe["id"], "locked": False})

    resp = client.post("/plan/grocery", json={"week_start": week_start})
    assert resp.status_code == 200
    body = resp.json()
    assert recipe["name"] in body["by_recipe"]
    ingredient_names = {i["name"] for i in body["by_recipe"][recipe["name"]]}
    assert ingredient_names == {"Pasta", "Minced meat"}


def test_grocery_list_empty_week(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    resp = client.post("/plan/grocery", json={"week_start": "2026-01-05"})
    assert resp.json()["by_recipe"] == {}


def test_grocery_list_excludes_past_days(client, monkeypatch):
    week_start = "2026-01-05"  # Monday
    past = make_recipe(client, name="Past Dish")
    future = make_recipe(client, name="Future Dish")
    client.put(f"/plan/{week_start}/mon", json={"week_start": week_start, "day": "mon", "recipe_id": past["id"], "locked": False})
    client.put(f"/plan/{week_start}/wed", json={"week_start": week_start, "day": "wed", "recipe_id": future["id"], "locked": False})

    # Freeze "today" to Wednesday of that week: Monday is in the past, Wednesday is not.
    _freeze_today(monkeypatch, "2026-01-07")

    resp = client.post("/plan/grocery", json={"week_start": week_start})
    body = resp.json()
    assert "Past Dish" not in body["by_recipe"]
    assert "Future Dish" in body["by_recipe"]


def test_grocery_list_excludes_all_days_of_a_fully_past_week(client, monkeypatch):
    week_start = "2026-01-05"
    recipe = make_recipe(client)
    client.put(f"/plan/{week_start}/mon", json={"week_start": week_start, "day": "mon", "recipe_id": recipe["id"], "locked": False})

    _freeze_today(monkeypatch, "2026-02-01")

    resp = client.post("/plan/grocery", json={"week_start": week_start})
    assert resp.json()["by_recipe"] == {}


def test_suggestions_exclude_side_dish_and_baking_recipes(client):
    make_recipe(client, name="Main Course")
    make_recipe(client, name="Focaccia", is_side_dish=True)
    make_recipe(client, name="Sourdough Bread", is_baking=True)
    week_start = "2026-01-05"

    suggestions = client.post(f"/plan/suggest/{week_start}").json()
    suggested_names = {r["name"] for r in suggestions.values() if r}
    assert suggested_names == {"Main Course"}


def test_set_day_rejects_side_dish_as_main(client):
    side = make_recipe(client, name="Focaccia", is_side_dish=True)
    resp = client.put("/plan/2026-01-05/mon", json={"week_start": "2026-01-05", "day": "mon", "recipe_id": side["id"], "locked": False})
    assert resp.status_code == 400


def test_set_day_rejects_baking_recipe_as_main(client):
    baking = make_recipe(client, name="Sourdough Bread", is_baking=True)
    resp = client.put("/plan/2026-01-05/mon", json={"week_start": "2026-01-05", "day": "mon", "recipe_id": baking["id"], "locked": False})
    assert resp.status_code == 400


def test_add_and_remove_side_dish_for_a_day(client):
    week_start = "2026-01-05"
    side = make_recipe(client, name="Focaccia", is_side_dish=True)

    resp = client.post(f"/plan/{week_start}/mon/sides", json={"recipe_id": side["id"]})
    assert resp.status_code == 201

    week = client.get(f"/plan/{week_start}").json()
    assert week["mon"]["sides"] == [{"recipe_id": side["id"], "recipe_name": "Focaccia"}]

    resp = client.delete(f"/plan/{week_start}/mon/sides/{side['id']}")
    assert resp.status_code == 204
    week = client.get(f"/plan/{week_start}").json()
    assert week["mon"] is None


def test_multiple_side_dishes_per_day_allowed(client):
    week_start = "2026-01-05"
    side_a = make_recipe(client, name="Focaccia", is_side_dish=True)
    side_b = make_recipe(client, name="Green Salad", is_side_dish=True)

    client.post(f"/plan/{week_start}/mon/sides", json={"recipe_id": side_a["id"]})
    client.post(f"/plan/{week_start}/mon/sides", json={"recipe_id": side_b["id"]})

    week = client.get(f"/plan/{week_start}").json()
    names = {s["recipe_name"] for s in week["mon"]["sides"]}
    assert names == {"Focaccia", "Green Salad"}


def test_adding_same_side_dish_twice_is_a_noop(client):
    week_start = "2026-01-05"
    side = make_recipe(client, name="Focaccia", is_side_dish=True)

    client.post(f"/plan/{week_start}/mon/sides", json={"recipe_id": side["id"]})
    resp = client.post(f"/plan/{week_start}/mon/sides", json={"recipe_id": side["id"]})
    assert resp.status_code == 201

    week = client.get(f"/plan/{week_start}").json()
    assert len(week["mon"]["sides"]) == 1


def test_clear_day_also_clears_side_dishes(client):
    week_start = "2026-01-05"
    main = make_recipe(client, name="Main Course")
    side = make_recipe(client, name="Focaccia", is_side_dish=True)
    client.put(f"/plan/{week_start}/mon", json={"week_start": week_start, "day": "mon", "recipe_id": main["id"], "locked": False})
    client.post(f"/plan/{week_start}/mon/sides", json={"recipe_id": side["id"]})

    resp = client.delete(f"/plan/{week_start}/mon")
    assert resp.status_code == 204

    week = client.get(f"/plan/{week_start}").json()
    assert week["mon"] is None


def test_get_week_includes_sides_even_without_main_dish(client):
    week_start = "2026-01-05"
    side = make_recipe(client, name="Focaccia", is_side_dish=True)
    client.post(f"/plan/{week_start}/mon/sides", json={"recipe_id": side["id"]})

    week = client.get(f"/plan/{week_start}").json()
    assert week["mon"]["recipe_id"] is None
    assert week["mon"]["sides"] == [{"recipe_id": side["id"], "recipe_name": "Focaccia"}]


def test_grocery_list_includes_side_dish_ingredients(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    week_start = "2026-01-05"
    side = make_recipe(client, name="Focaccia", is_side_dish=True, ingredients=[
        {"name": "Flour", "amount": "500", "unit": "g", "sort_order": 0},
    ])
    client.post(f"/plan/{week_start}/mon/sides", json={"recipe_id": side["id"]})

    resp = client.post("/plan/grocery", json={"week_start": week_start})
    body = resp.json()
    assert "Focaccia" in body["by_recipe"]
    assert {i["name"] for i in body["by_recipe"]["Focaccia"]} == {"Flour"}


def test_grocery_list_side_dish_excluded_on_past_day(client, monkeypatch):
    week_start = "2026-01-05"
    side = make_recipe(client, name="Focaccia", is_side_dish=True)
    client.post(f"/plan/{week_start}/mon/sides", json={"recipe_id": side["id"]})

    _freeze_today(monkeypatch, "2026-01-07")  # Wednesday: Monday is now in the past

    resp = client.post("/plan/grocery", json={"week_start": week_start})
    assert "Focaccia" not in resp.json()["by_recipe"]
