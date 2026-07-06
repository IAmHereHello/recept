from tests.conftest import make_recipe


def test_create_recipe_returns_computed_fields(client):
    recipe = make_recipe(client)
    assert recipe["name"] == "Spaghetti Bolognese"
    assert len(recipe["ingredients"]) == 2
    assert len(recipe["steps"]) == 2
    assert recipe["avg_rating"] is None
    assert recipe["last_cooked"] is None
    assert recipe["cover_photo"] is None


def test_get_recipe_not_found(client):
    resp = client.get("/recipes/999")
    assert resp.status_code == 404


def test_list_recipes_filters(client):
    make_recipe(client, name="Veggie Curry", is_vegetarian=True, is_vegan=True, cuisine_type="Indian", difficulty="medium")
    make_recipe(client, name="Beef Stew", is_vegetarian=False, is_vegan=False, cuisine_type="Dutch", difficulty="hard")

    resp = client.get("/recipes/", params={"vegetarian": True})
    names = [r["name"] for r in resp.json()]
    assert names == ["Veggie Curry"]

    resp = client.get("/recipes/", params={"cuisine": "Dutch"})
    names = [r["name"] for r in resp.json()]
    assert names == ["Beef Stew"]

    resp = client.get("/recipes/", params={"difficulty": "medium"})
    names = [r["name"] for r in resp.json()]
    assert names == ["Veggie Curry"]


def test_update_recipe_replaces_ingredients_and_steps(client):
    recipe = make_recipe(client)
    recipe_id = recipe["id"]

    updated = {
        "name": "Spaghetti Bolognese (v2)",
        "description": "Updated",
        "cook_time": 30,
        "difficulty": "medium",
        "cuisine_type": "Italian",
        "is_vegetarian": False,
        "is_vegan": False,
        "ingredients": [{"name": "Tomato sauce", "amount": "1", "unit": "jar", "sort_order": 0}],
        "steps": [{"sort_order": 1, "description": "Heat sauce"}],
    }
    resp = client.put(f"/recipes/{recipe_id}", json=updated)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Spaghetti Bolognese (v2)"
    assert [i["name"] for i in body["ingredients"]] == ["Tomato sauce"]
    assert [s["description"] for s in body["steps"]] == ["Heat sauce"]


def test_delete_recipe(client):
    recipe = make_recipe(client)
    recipe_id = recipe["id"]

    resp = client.delete(f"/recipes/{recipe_id}")
    assert resp.status_code == 204

    resp = client.get(f"/recipes/{recipe_id}")
    assert resp.status_code == 404


def test_delete_recipe_cascades_to_ingredients_and_sessions(client):
    recipe = make_recipe(client)
    recipe_id = recipe["id"]
    client.post("/sessions/", json={"recipe_id": recipe_id, "cooked_by": "michael"})

    resp = client.delete(f"/recipes/{recipe_id}")
    assert resp.status_code == 204

    resp = client.get(f"/sessions/recipe/{recipe_id}")
    assert resp.json() == []
