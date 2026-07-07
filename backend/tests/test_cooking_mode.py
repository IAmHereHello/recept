from tests.conftest import make_recipe


def start_cooking(client, recipe_id, cooked_by="michael"):
    resp = client.post("/sessions/", json={"recipe_id": recipe_id, "cooked_by": cooked_by, "cooking_mode": True})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_start_cooking_mode_sets_in_progress_status(client):
    recipe = make_recipe(client)
    session = start_cooking(client, recipe["id"])

    assert session["cooking_mode"] is True
    assert session["current_step"] == 0
    assert session["finished_at"] is None


def test_legacy_session_is_finished_immediately(client):
    recipe = make_recipe(client)
    resp = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"})
    session = resp.json()

    assert session["cooking_mode"] is False
    assert session["finished_at"] is not None


def test_advance_step_updates_current_step_and_resets_timer(client):
    recipe = make_recipe(client)  # 2 steps
    session = start_cooking(client, recipe["id"])
    client.post(f"/sessions/{session['id']}/timer", json={"seconds": 60})

    resp = client.post(f"/sessions/{session['id']}/step", json={"step_index": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_step"] == 1

    # advancing clears any timer that was running for the previous step
    active = client.get("/sessions/active").json()
    assert active["active_timer_remaining_seconds"] is None


def test_advance_step_rejects_out_of_range_index(client):
    recipe = make_recipe(client)  # 2 steps -> valid indices are 0, 1
    session = start_cooking(client, recipe["id"])

    resp = client.post(f"/sessions/{session['id']}/step", json={"step_index": 2})
    assert resp.status_code == 400


def test_advance_step_rejects_when_already_done(client):
    recipe = make_recipe(client)
    session = start_cooking(client, recipe["id"])
    client.post(f"/sessions/{session['id']}/finish")

    resp = client.post(f"/sessions/{session['id']}/step", json={"step_index": 1})
    assert resp.status_code == 400


def test_start_timer_sets_seconds_and_started_at(client):
    recipe = make_recipe(client)
    session = start_cooking(client, recipe["id"])

    resp = client.post(f"/sessions/{session['id']}/timer", json={"seconds": 120})
    assert resp.status_code == 200

    active = client.get("/sessions/active").json()
    assert active["active_timer_remaining_seconds"] == 120


def test_clear_timer(client):
    recipe = make_recipe(client)
    session = start_cooking(client, recipe["id"])
    client.post(f"/sessions/{session['id']}/timer", json={"seconds": 120})

    resp = client.delete(f"/sessions/{session['id']}/timer")
    assert resp.status_code == 204

    active = client.get("/sessions/active").json()
    assert active["active_timer_remaining_seconds"] is None


def test_finish_cooking_mode_sets_done_and_finished_at(client):
    recipe = make_recipe(client)
    session = start_cooking(client, recipe["id"])

    resp = client.post(f"/sessions/{session['id']}/finish")
    assert resp.status_code == 200
    assert resp.json()["finished_at"] is not None

    assert client.get("/sessions/active").json() is None


def test_active_session_endpoint_returns_null_when_none_in_progress(client):
    assert client.get("/sessions/active").json() is None

    recipe = make_recipe(client)
    client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"})  # legacy, instantly done
    assert client.get("/sessions/active").json() is None


def test_active_session_computes_remaining_seconds_from_step_and_timer(client):
    # cook_time=45min, 2 steps -> 22.5 min (1350s) per step share
    recipe = make_recipe(client)
    session = start_cooking(client, recipe["id"])

    # No timer active on step 0: estimate = flat share for step 0 (1350s) + share for remaining step 1 (1350s)
    active = client.get("/sessions/active").json()
    assert active["session_id"] == session["id"]
    assert active["recipe_name"] == recipe["name"]
    assert active["cooked_by"] == "michael"
    assert active["total_steps"] == 2
    assert active["active_timer_remaining_seconds"] is None
    assert active["estimated_remaining_seconds"] == 2700

    # With an active 300s timer on the current step, that replaces the flat share for step 0
    client.post(f"/sessions/{session['id']}/timer", json={"seconds": 300})
    active = client.get("/sessions/active").json()
    assert active["active_timer_remaining_seconds"] == 300
    assert active["estimated_remaining_seconds"] == 300 + 1350

    # Advance to the last step: no more steps after it, so estimate is just that step's flat share
    client.post(f"/sessions/{session['id']}/step", json={"step_index": 1})
    active = client.get("/sessions/active").json()
    assert active["estimated_remaining_seconds"] == 1350


def test_active_session_omits_estimate_when_recipe_has_no_cook_time(client):
    recipe = make_recipe(client, cook_time=None)
    start_cooking(client, recipe["id"])

    active = client.get("/sessions/active").json()
    assert active["estimated_remaining_seconds"] is None
    assert active["total_steps"] == 2


def test_pending_reviews_includes_cook_for_new_cooking_mode_sessions(client):
    recipe = make_recipe(client)
    session = start_cooking(client, recipe["id"], cooked_by="michael")
    client.post(f"/sessions/{session['id']}/finish")

    # Both the cook and the other person are now pending
    assert len(client.get("/sessions/pending/michael").json()) == 1
    assert len(client.get("/sessions/pending/rachel").json()) == 1


def test_pending_reviews_excludes_cook_for_legacy_sessions(client):
    recipe = make_recipe(client)
    client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael"})

    # Legacy (non-cooking-mode) sessions keep the old behavior: only the other person is prompted.
    assert client.get("/sessions/pending/michael").json() == []
    assert len(client.get("/sessions/pending/rachel").json()) == 1
