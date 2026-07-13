from datetime import date
from tests.conftest import make_recipe


def test_create_freezer_item_defaults_to_three_month_expiry(client):
    recipe = make_recipe(client, name="Chili")
    resp = client.post("/freezer/", json={"recipe_id": recipe["id"], "portions_total": 4})
    assert resp.status_code == 201, resp.text
    item = resp.json()
    assert item["recipe_id"] == recipe["id"]
    assert item["recipe_name"] == "Chili"
    assert item["portions_total"] == 4
    assert item["portions_remaining"] == 4
    assert item["frozen_at"] == date.today().isoformat()

    frozen = date.fromisoformat(item["frozen_at"])
    expires = date.fromisoformat(item["expires_at"])
    assert (expires.year, expires.month, expires.day) == (
        frozen.year + (1 if frozen.month + 3 > 12 else 0),
        (frozen.month + 3 - 1) % 12 + 1,
        frozen.day,
    )


def test_create_freezer_item_uses_recipe_freezer_months_override(client):
    recipe = make_recipe(client, name="Vissoep", freezer_months=1)
    resp = client.post("/freezer/", json={"recipe_id": recipe["id"], "portions_total": 2})
    item = resp.json()
    frozen = date.fromisoformat(item["frozen_at"])
    expires = date.fromisoformat(item["expires_at"])
    assert (expires.year, expires.month) == (
        frozen.year + (1 if frozen.month == 12 else 0),
        1 if frozen.month == 12 else frozen.month + 1,
    )


def test_create_freezer_item_explicit_dates(client):
    recipe = make_recipe(client)
    resp = client.post("/freezer/", json={
        "recipe_id": recipe["id"],
        "portions_total": 3,
        "frozen_at": "2026-01-15",
        "expires_at": "2026-12-31",
    })
    item = resp.json()
    assert item["frozen_at"] == "2026-01-15"
    assert item["expires_at"] == "2026-12-31"


def test_create_freezer_item_linked_to_cook_session(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()
    resp = client.post("/freezer/", json={
        "recipe_id": recipe["id"], "cook_session_id": session["id"], "portions_total": 2, "added_by": "rachel",
    })
    item = resp.json()
    assert item["cook_session_id"] == session["id"]
    assert item["added_by"] == "rachel"


def test_create_freezer_item_recipe_not_found(client):
    resp = client.post("/freezer/", json={"recipe_id": 999, "portions_total": 1})
    assert resp.status_code == 404


def test_list_freezer_items_ordered_by_expiry(client):
    r1 = make_recipe(client, name="A")
    r2 = make_recipe(client, name="B")
    client.post("/freezer/", json={"recipe_id": r1["id"], "portions_total": 1, "expires_at": "2026-06-01"})
    client.post("/freezer/", json={"recipe_id": r2["id"], "portions_total": 1, "expires_at": "2026-03-01"})

    resp = client.get("/freezer/")
    names = [i["recipe_name"] for i in resp.json()]
    assert names == ["B", "A"]


def test_consume_partial_portions(client):
    recipe = make_recipe(client)
    item = client.post("/freezer/", json={"recipe_id": recipe["id"], "portions_total": 4}).json()

    resp = client.post(f"/freezer/{item['id']}/consume", json={"portions": 1})
    assert resp.status_code == 200
    assert resp.json()["portions_remaining"] == 3


def test_consume_all_portions_deletes_item(client):
    recipe = make_recipe(client)
    item = client.post("/freezer/", json={"recipe_id": recipe["id"], "portions_total": 2}).json()

    resp = client.post(f"/freezer/{item['id']}/consume", json={"portions": 2})
    assert resp.status_code == 204

    resp = client.get("/freezer/")
    assert resp.json() == []


def test_consume_more_than_remaining_rejected(client):
    recipe = make_recipe(client)
    item = client.post("/freezer/", json={"recipe_id": recipe["id"], "portions_total": 2}).json()

    resp = client.post(f"/freezer/{item['id']}/consume", json={"portions": 5})
    assert resp.status_code == 400

    resp = client.get("/freezer/")
    assert resp.json()[0]["portions_remaining"] == 2


def test_set_freezer_item_expiry(client):
    recipe = make_recipe(client)
    item = client.post("/freezer/", json={"recipe_id": recipe["id"], "portions_total": 2}).json()

    resp = client.post(f"/freezer/{item['id']}/expires", json={"expires_at": "2027-01-01"})
    assert resp.status_code == 200
    assert resp.json()["expires_at"] == "2027-01-01"


def test_delete_freezer_item(client):
    recipe = make_recipe(client)
    item = client.post("/freezer/", json={"recipe_id": recipe["id"], "portions_total": 2}).json()

    resp = client.delete(f"/freezer/{item['id']}")
    assert resp.status_code == 204

    resp = client.get("/freezer/")
    assert resp.json() == []


def test_freezer_item_not_found(client):
    assert client.post("/freezer/999/consume", json={"portions": 1}).status_code == 404
    assert client.post("/freezer/999/expires", json={"expires_at": "2027-01-01"}).status_code == 404
    assert client.delete("/freezer/999").status_code == 404


def test_delete_recipe_cascades_to_freezer_items(client):
    recipe = make_recipe(client)
    client.post("/freezer/", json={"recipe_id": recipe["id"], "portions_total": 2})

    resp = client.delete(f"/recipes/{recipe['id']}")
    assert resp.status_code == 204

    resp = client.get("/freezer/")
    assert resp.json() == []


def test_deleting_freezer_item_detaches_meal_plan_day_without_deleting_it(client):
    recipe = make_recipe(client)
    item = client.post("/freezer/", json={"recipe_id": recipe["id"], "portions_total": 2}).json()

    client.put("/plan/2026-07-13/mon", json={
        "week_start": "2026-07-13", "day": "mon", "recipe_id": recipe["id"],
        "locked": False, "freezer_item_id": item["id"],
    })
    week = client.get("/plan/2026-07-13").json()
    assert week["mon"]["freezer_item_id"] == item["id"]

    resp = client.delete(f"/freezer/{item['id']}")
    assert resp.status_code == 204

    week = client.get("/plan/2026-07-13").json()
    assert week["mon"]["recipe_id"] == recipe["id"]
    assert week["mon"]["freezer_item_id"] is None
