import io
from tests.conftest import make_recipe


def test_create_recipe_returns_computed_fields(client):
    recipe = make_recipe(client)
    assert recipe["name"] == "Spaghetti Bolognese"
    assert len(recipe["ingredients"]) == 2
    assert len(recipe["steps"]) == 2
    assert recipe["avg_rating"] is None
    assert recipe["last_cooked"] is None
    assert recipe["cover_photo"] is None


def test_prep_time_round_trips_through_create_and_update(client):
    recipe = make_recipe(client, cook_time=90, prep_time=25)
    assert recipe["cook_time"] == 90
    assert recipe["prep_time"] == 25

    updated = client.put(f"/recipes/{recipe['id']}", json={
        **{k: recipe[k] for k in ("name", "description", "difficulty", "cuisine_type",
                                  "is_vegetarian", "is_vegan", "ingredients", "steps")},
        "cook_time": 80,
        "prep_time": 20,
    }).json()
    assert updated["cook_time"] == 80
    assert updated["prep_time"] == 20


def test_prep_time_defaults_to_null(client):
    assert make_recipe(client)["prep_time"] is None


def test_create_recipe_freezer_fields_default(client):
    recipe = make_recipe(client)
    assert recipe["is_freezable"] is True
    assert recipe["portions"] is None
    assert recipe["freezer_months"] is None


def test_create_recipe_freezer_fields_explicit(client):
    recipe = make_recipe(client, portions=4, is_freezable=False, freezer_months=2)
    assert recipe["portions"] == 4
    assert recipe["is_freezable"] is False
    assert recipe["freezer_months"] == 2


def test_list_recipes_filters_by_freezable(client):
    make_recipe(client, name="Soep", is_freezable=True)
    make_recipe(client, name="Salade", is_freezable=False)

    resp = client.get("/recipes/", params={"freezable": True})
    assert [r["name"] for r in resp.json()] == ["Soep"]

    resp = client.get("/recipes/", params={"freezable": False})
    assert [r["name"] for r in resp.json()] == ["Salade"]


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


def test_create_recipe_with_side_dish_and_baking_flags(client):
    side = make_recipe(client, name="Focaccia", is_side_dish=True)
    baking = make_recipe(client, name="Sourdough Bread", is_baking=True)

    assert side["is_side_dish"] is True
    assert side["is_baking"] is False
    assert baking["is_baking"] is True
    assert baking["is_side_dish"] is False


def test_list_recipes_filters_by_side_dish_and_baking(client):
    make_recipe(client, name="Focaccia", is_side_dish=True)
    make_recipe(client, name="Sourdough Bread", is_baking=True)
    make_recipe(client, name="Spaghetti Bolognese")

    resp = client.get("/recipes/", params={"side_dish": True})
    assert [r["name"] for r in resp.json()] == ["Focaccia"]

    resp = client.get("/recipes/", params={"baking": True})
    assert [r["name"] for r in resp.json()] == ["Sourdough Bread"]


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


def test_update_recipe_freezer_fields(client):
    recipe = make_recipe(client, portions=2, is_freezable=True, freezer_months=None)
    recipe_id = recipe["id"]

    updated = {
        "name": "Spaghetti Bolognese (v2)",
        "is_vegetarian": False,
        "is_vegan": False,
        "portions": 6,
        "is_freezable": False,
        "freezer_months": 4,
        "ingredients": [],
        "steps": [],
    }
    resp = client.put(f"/recipes/{recipe_id}", json=updated)
    assert resp.status_code == 200
    body = resp.json()
    assert body["portions"] == 6
    assert body["is_freezable"] is False
    assert body["freezer_months"] == 4


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


def test_image_path_round_trips_and_feeds_cover_photo(client):
    recipe = make_recipe(client, image_path="/uploads/imported.jpg")
    assert recipe["image_path"] == "/uploads/imported.jpg"
    # With no cook-session photo yet, the imported image is the cover photo.
    assert recipe["cover_photo"] == "/uploads/imported.jpg"

    fetched = client.get(f"/recipes/{recipe['id']}").json()
    assert fetched["image_path"] == "/uploads/imported.jpg"
    assert fetched["cover_photo"] == "/uploads/imported.jpg"


def test_cook_session_photo_overrides_imported_cover_image(client, tmp_path, monkeypatch):
    import app.routers.sessions as sessions_module
    monkeypatch.setattr(sessions_module, "UPLOAD_DIR", tmp_path)

    recipe = make_recipe(client, image_path="/uploads/imported.jpg")
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()
    client.post(
        f"/sessions/{session['id']}/photo",
        files={"file": ("dinner.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        data={"uploaded_by": "michael"},
    )

    fetched = client.get(f"/recipes/{recipe['id']}").json()
    assert fetched["image_path"] == "/uploads/imported.jpg"  # column unchanged
    assert fetched["cover_photo"].endswith(".jpg")
    assert fetched["cover_photo"] != "/uploads/imported.jpg"  # the real photo wins


def test_update_recipe_removes_replaced_cover_image_file(client, tmp_path, monkeypatch):
    import app.routers.recipes as recipes_module
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(recipes_module, "UPLOAD_DIR", upload_dir)
    (upload_dir / "old.jpg").write_bytes(b"old-image")

    recipe = make_recipe(client, image_path="/uploads/old.jpg")
    resp = client.put(f"/recipes/{recipe['id']}", json={
        "name": recipe["name"], "is_vegetarian": False, "is_vegan": False,
        "image_path": None, "ingredients": [], "steps": [],
    })
    assert resp.status_code == 200
    assert resp.json()["image_path"] is None
    assert not (upload_dir / "old.jpg").exists()


def test_delete_recipe_removes_imported_cover_image_file(client, tmp_path, monkeypatch):
    import app.routers.recipes as recipes_module
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(recipes_module, "UPLOAD_DIR", upload_dir)
    (upload_dir / "cover.jpg").write_bytes(b"cover-image")

    recipe = make_recipe(client, image_path="/uploads/cover.jpg")
    assert client.delete(f"/recipes/{recipe['id']}").status_code == 204
    assert not (upload_dir / "cover.jpg").exists()


def test_delete_recipe_removes_uploaded_photo_files_from_disk(client, tmp_path, monkeypatch):
    import app.routers.recipes as recipes_module
    import app.routers.sessions as sessions_module
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(recipes_module, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(sessions_module, "UPLOAD_DIR", upload_dir)

    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()
    client.post(
        f"/sessions/{session['id']}/photo",
        files={"file": ("dinner.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        data={"uploaded_by": "michael"},
    )
    uploaded_files = list(upload_dir.iterdir())
    assert len(uploaded_files) == 1

    resp = client.delete(f"/recipes/{recipe['id']}")
    assert resp.status_code == 204
    assert list(upload_dir.iterdir()) == []
