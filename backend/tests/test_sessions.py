import io
from tests.conftest import make_recipe


def test_create_session_and_rate(client):
    recipe = make_recipe(client)
    resp = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"})
    assert resp.status_code == 201
    session = resp.json()
    assert session["cooked_by"] == "michael"
    assert session["ratings"] == []

    resp = client.post(f"/sessions/{session['id']}/rate", json={"user": "rachel", "stars": 4})
    assert resp.status_code == 200
    ratings = resp.json()["ratings"]
    assert len(ratings) == 1
    assert ratings[0]["user"] == "rachel" and ratings[0]["stars"] == 4

    recipe_after = client.get(f"/recipes/{recipe['id']}").json()
    assert recipe_after["avg_rating"] == 4.0


def test_rating_same_user_twice_upserts_not_duplicates(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    client.post(f"/sessions/{session['id']}/rate", json={"user": "rachel", "stars": 2})
    resp = client.post(f"/sessions/{session['id']}/rate", json={"user": "rachel", "stars": 5})

    ratings = resp.json()["ratings"]
    assert len(ratings) == 1
    assert ratings[0]["stars"] == 5


def test_pending_reviews_shows_up_for_other_user_only(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    pending_rachel = client.get("/sessions/pending/rachel").json()
    assert len(pending_rachel) == 1
    assert pending_rachel[0]["id"] == session["id"]
    assert pending_rachel[0]["recipe_name"] == recipe["name"]

    pending_michael = client.get("/sessions/pending/michael").json()
    assert pending_michael == []


def test_pending_review_cleared_after_rating(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    client.post(f"/sessions/{session['id']}/rate", json={"user": "rachel", "stars": 3})

    pending_rachel = client.get("/sessions/pending/rachel").json()
    assert pending_rachel == []


def test_pending_review_not_shown_if_cook_already_rated_for_other(client):
    # Michael cooks and immediately rates on Rachel's behalf via the "rate for
    # other" checkbox — the review gate should not re-prompt Rachel.
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()
    client.post(f"/sessions/{session['id']}/rate", json={"user": "rachel", "stars": 5})

    assert client.get("/sessions/pending/rachel").json() == []


def test_pending_reviews_queue_oldest_first(client):
    recipe = make_recipe(client)
    s1 = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_at": "2026-01-01T10:00:00", "cooked_by": "michael"}).json()
    s2 = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_at": "2026-01-03T10:00:00", "cooked_by": "michael"}).json()
    s3 = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_at": "2026-01-02T10:00:00", "cooked_by": "michael"}).json()

    pending = client.get("/sessions/pending/rachel").json()
    assert [p["id"] for p in pending] == [s1["id"], s3["id"], s2["id"]]


def test_session_with_no_cooked_by_never_pending(client):
    recipe = make_recipe(client)
    client.post("/sessions/", json={"recipe_id": recipe["id"]})
    assert client.get("/sessions/pending/rachel").json() == []
    assert client.get("/sessions/pending/michael").json() == []


def test_photo_upload_rejects_unsupported_extension(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    resp = client.post(
        f"/sessions/{session['id']}/photo",
        files={"file": ("malware.exe", io.BytesIO(b"data"), "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_photo_upload_accepts_supported_extension(client, tmp_path, monkeypatch):
    import app.routers.sessions as sessions_module
    monkeypatch.setattr(sessions_module, "UPLOAD_DIR", tmp_path)

    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    resp = client.post(
        f"/sessions/{session['id']}/photo",
        files={"file": ("dinner.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
    )
    assert resp.status_code == 200
    photos = resp.json()["photos"]
    assert len(photos) == 1
    assert photos[0].startswith("/uploads/")


def test_rate_session_not_found(client):
    resp = client.post("/sessions/999/rate", json={"user": "rachel", "stars": 3})
    assert resp.status_code == 404
