import io
import sqlite3
from datetime import datetime, timedelta, timezone
from tests.conftest import make_recipe


def _set_session_fields(db_path, session_id, **fields):
    conn = sqlite3.connect(db_path)
    assignments = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE cook_sessions SET {assignments} WHERE id=?", (*fields.values(), session_id))
    conn.commit()
    conn.close()


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


def test_pending_reviews_carry_recipe_freezer_fields(client):
    recipe = make_recipe(client, name="Chili", portions=4, is_freezable=True)
    client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"})

    pending = client.get("/sessions/pending/rachel").json()
    assert pending[0]["is_freezable"] is True
    assert pending[0]["portions"] == 4

    non_freezable = make_recipe(client, name="Salade", is_freezable=False)
    client.post("/sessions/", json={"recipe_id": non_freezable["id"], "cooked_by": "michael"})

    pending = client.get("/sessions/pending/rachel").json()
    salade_entry = next(p for p in pending if p["recipe_name"] == "Salade")
    assert salade_entry["is_freezable"] is False
    assert salade_entry["portions"] is None


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
        data={"uploaded_by": "michael"},
    )
    assert resp.status_code == 400


def test_photo_upload_requires_uploaded_by(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    resp = client.post(
        f"/sessions/{session['id']}/photo",
        files={"file": ("dinner.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
    )
    assert resp.status_code == 422


def test_photo_upload_accepts_supported_extension(client, tmp_path, monkeypatch):
    import app.routers.sessions as sessions_module
    monkeypatch.setattr(sessions_module, "UPLOAD_DIR", tmp_path)

    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    resp = client.post(
        f"/sessions/{session['id']}/photo",
        files={"file": ("dinner.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        data={"uploaded_by": "michael"},
    )
    assert resp.status_code == 200
    photos = resp.json()["photos"]
    assert len(photos) == 1
    assert photos[0]["file_path"].startswith("/uploads/")
    assert photos[0]["uploaded_by"] == "michael"


def test_delete_photo_removes_row_and_file(client, tmp_path, monkeypatch):
    import app.routers.sessions as sessions_module
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(sessions_module, "UPLOAD_DIR", upload_dir)

    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()
    upload_resp = client.post(
        f"/sessions/{session['id']}/photo",
        files={"file": ("dinner.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        data={"uploaded_by": "michael"},
    ).json()
    photo_id = upload_resp["photos"][0]["id"]
    assert len(list(upload_dir.iterdir())) == 1

    resp = client.delete(f"/sessions/{session['id']}/photo/{photo_id}")
    assert resp.status_code == 204
    assert list(upload_dir.iterdir()) == []

    updated = client.get(f"/sessions/{session['id']}").json()
    assert updated["photos"] == []


def test_delete_photo_not_found_404(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    resp = client.delete(f"/sessions/{session['id']}/photo/999")
    assert resp.status_code == 404


def test_delete_photo_wrong_session_404(client, tmp_path, monkeypatch):
    import app.routers.sessions as sessions_module
    monkeypatch.setattr(sessions_module, "UPLOAD_DIR", tmp_path)

    recipe = make_recipe(client)
    session_a = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()
    session_b = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "rachel"}).json()
    upload_resp = client.post(
        f"/sessions/{session_a['id']}/photo",
        files={"file": ("dinner.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        data={"uploaded_by": "michael"},
    ).json()
    photo_id = upload_resp["photos"][0]["id"]

    resp = client.delete(f"/sessions/{session_b['id']}/photo/{photo_id}")
    assert resp.status_code == 404


def test_rate_session_not_found(client):
    resp = client.post("/sessions/999/rate", json={"user": "rachel", "stars": 3})
    assert resp.status_code == 404


def test_rate_session_accepts_half_star(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    resp = client.post(f"/sessions/{session['id']}/rate", json={"user": "rachel", "stars": 3.5})
    assert resp.status_code == 200
    ratings = resp.json()["ratings"]
    assert ratings[0]["stars"] == 3.5

    recipe_after = client.get(f"/recipes/{recipe['id']}").json()
    assert recipe_after["avg_rating"] == 3.5


def test_rate_session_rejects_non_half_step_stars(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    resp = client.post(f"/sessions/{session['id']}/rate", json={"user": "rachel", "stars": 3.3})
    assert resp.status_code == 422


def test_recipe_avg_rating_averages_half_star_values(client):
    recipe = make_recipe(client)
    s1 = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()
    s2 = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    client.post(f"/sessions/{s1['id']}/rate", json={"user": "rachel", "stars": 3.5})
    client.post(f"/sessions/{s2['id']}/rate", json={"user": "rachel", "stars": 4})

    recipe_after = client.get(f"/recipes/{recipe['id']}").json()
    assert recipe_after["avg_rating"] == 3.8


def test_delete_rating_removes_it(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()
    client.post(f"/sessions/{session['id']}/rate", json={"user": "rachel", "stars": 4})

    resp = client.delete(f"/sessions/{session['id']}/rate/rachel")
    assert resp.status_code == 204

    updated = client.get(f"/sessions/{session['id']}").json()
    assert updated["ratings"] == []


def test_delete_rating_nonexistent_is_noop(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    resp = client.delete(f"/sessions/{session['id']}/rate/rachel")
    assert resp.status_code == 204


def test_delete_rating_then_recipe_avg_rating_recalculates(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()
    client.post(f"/sessions/{session['id']}/rate", json={"user": "michael", "stars": 2})
    client.post(f"/sessions/{session['id']}/rate", json={"user": "rachel", "stars": 4})

    client.delete(f"/sessions/{session['id']}/rate/rachel")

    recipe_after = client.get(f"/recipes/{recipe['id']}").json()
    assert recipe_after["avg_rating"] == 2.0


def test_fresh_cooking_session_is_not_stale(client):
    recipe = make_recipe(client)
    session = client.post(
        "/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael", "cooking_mode": True}
    ).json()

    assert session["is_stale"] is False
    assert client.get("/sessions/active").json()["is_stale"] is False


def test_session_becomes_stale_after_inactivity_timeout(client, tmp_path):
    recipe = make_recipe(client)
    session = client.post(
        "/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael", "cooking_mode": True}
    ).json()

    long_ago = (datetime.now(timezone.utc) - timedelta(minutes=61)).isoformat()
    _set_session_fields(tmp_path / "test.db", session["id"], last_activity_at=long_ago)

    assert client.get(f"/sessions/{session['id']}").json()["is_stale"] is True
    assert client.get("/sessions/active").json()["is_stale"] is True


def test_running_timer_prevents_staleness_during_countdown(client, tmp_path):
    recipe = make_recipe(client)
    session = client.post(
        "/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael", "cooking_mode": True}
    ).json()

    # last_activity_at alone (90 min ago) would be stale, but a 3-hour timer
    # that also started 90 min ago hasn't ended yet — its future end time
    # should keep the session fresh while it counts down.
    started_90_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat()
    _set_session_fields(
        tmp_path / "test.db", session["id"],
        last_activity_at=started_90_min_ago, timer_started_at=started_90_min_ago, timer_seconds=3 * 60 * 60,
    )

    assert client.get(f"/sessions/{session['id']}").json()["is_stale"] is False


def test_session_stale_once_a_finished_timer_itself_is_old_enough(client, tmp_path):
    recipe = make_recipe(client)
    session = client.post(
        "/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael", "cooking_mode": True}
    ).json()

    # A 1-hour timer started 200 min ago ended 140 min ago — well past the
    # 60-minute threshold, even though last_activity_at was also 200 min ago.
    started_200_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=200)).isoformat()
    _set_session_fields(
        tmp_path / "test.db", session["id"],
        last_activity_at=started_200_min_ago, timer_started_at=started_200_min_ago, timer_seconds=60 * 60,
    )

    assert client.get(f"/sessions/{session['id']}").json()["is_stale"] is True


def test_touch_updates_last_activity_and_keeps_session_fresh(client, tmp_path):
    recipe = make_recipe(client)
    session = client.post(
        "/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael", "cooking_mode": True}
    ).json()

    long_ago = (datetime.now(timezone.utc) - timedelta(minutes=61)).isoformat()
    _set_session_fields(tmp_path / "test.db", session["id"], last_activity_at=long_ago)
    assert client.get(f"/sessions/{session['id']}").json()["is_stale"] is True

    resp = client.post(f"/sessions/{session['id']}/touch")
    assert resp.status_code == 204
    assert client.get(f"/sessions/{session['id']}").json()["is_stale"] is False


def test_touch_finished_session_rejected(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    resp = client.post(f"/sessions/{session['id']}/touch")
    assert resp.status_code == 400


def test_delete_session_removes_unfinished_session(client):
    recipe = make_recipe(client)
    session = client.post(
        "/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael", "cooking_mode": True}
    ).json()

    resp = client.delete(f"/sessions/{session['id']}")
    assert resp.status_code == 204
    assert client.get(f"/sessions/{session['id']}").status_code == 404


def test_delete_session_rejects_already_finished_session(client):
    recipe = make_recipe(client)
    session = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"}).json()

    resp = client.delete(f"/sessions/{session['id']}")
    assert resp.status_code == 400
    assert client.get(f"/sessions/{session['id']}").status_code == 200


def test_advance_step_and_timer_actions_refresh_last_activity(client, tmp_path):
    recipe = make_recipe(client)
    session = client.post(
        "/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael", "cooking_mode": True}
    ).json()

    long_ago = (datetime.now(timezone.utc) - timedelta(minutes=61)).isoformat()
    _set_session_fields(tmp_path / "test.db", session["id"], last_activity_at=long_ago)
    assert client.get(f"/sessions/{session['id']}").json()["is_stale"] is True

    client.post(f"/sessions/{session['id']}/step", json={"step_index": 1})
    assert client.get(f"/sessions/{session['id']}").json()["is_stale"] is False

    _set_session_fields(tmp_path / "test.db", session["id"], last_activity_at=long_ago)
    client.post(f"/sessions/{session['id']}/timer", json={"seconds": 60})
    assert client.get(f"/sessions/{session['id']}").json()["is_stale"] is False
