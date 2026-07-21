import sqlite3
from datetime import datetime, timedelta, timezone
from tests.conftest import make_recipe


def _set_session_fields(db_path, session_id, **fields):
    conn = sqlite3.connect(db_path)
    assignments = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE cook_sessions SET {assignments} WHERE id=?", (*fields.values(), session_id))
    conn.commit()
    conn.close()


def start_cooking(client, recipe_id, cooked_by="michael"):
    resp = client.post("/sessions/", json={"recipe_id": recipe_id, "cooked_by": cooked_by, "cooking_mode": True})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _backdate_step_started(db_path, session_id, seconds_ago):
    started = (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()
    _set_session_fields(db_path, session_id, step_started_at=started, last_activity_at=started)


def test_first_step_observation_sets_baseline_no_confirmation_needed(client, tmp_path):
    recipe = make_recipe(client)
    session = start_cooking(client, recipe["id"])
    _backdate_step_started(tmp_path / "test.db", session["id"], 100)

    resp = client.post(f"/sessions/{session['id']}/step", json={"step_index": 1})
    assert resp.json()["pending_step_confirmation"] is None


def test_second_observation_within_tolerance_auto_counts(client, tmp_path):
    recipe = make_recipe(client)
    db = tmp_path / "test.db"

    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 100)
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})
    client.post(f"/sessions/{s1['id']}/finish")

    # 5% off the 100s baseline -> within +-10%, auto-counted
    s2 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s2["id"], 105)
    resp = client.post(f"/sessions/{s2['id']}/step", json={"step_index": 1})
    assert resp.json()["pending_step_confirmation"] is None


def test_outlier_observation_creates_pending_confirmation(client, tmp_path):
    recipe = make_recipe(client)
    db = tmp_path / "test.db"

    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 100)
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})
    client.post(f"/sessions/{s1['id']}/finish")

    # 100% off the 100s baseline -> outlier, pending confirmation
    s2 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s2["id"], 200)
    resp = client.post(f"/sessions/{s2['id']}/step", json={"step_index": 1})
    pending = resp.json()["pending_step_confirmation"]
    assert pending is not None
    assert pending["seconds"] == 200
    assert pending["avg_seconds"] == 100
    assert pending["track"] == "main"
    assert pending["sort_order"] == 1


def test_pending_confirmation_survives_refetch(client, tmp_path):
    recipe = make_recipe(client)
    db = tmp_path / "test.db"
    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 100)
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})
    client.post(f"/sessions/{s1['id']}/finish")

    s2 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s2["id"], 200)
    client.post(f"/sessions/{s2['id']}/step", json={"step_index": 1})

    refetched = client.get(f"/sessions/{s2['id']}").json()
    assert refetched["pending_step_confirmation"] is not None


def test_confirming_outlier_as_counted_updates_average(client, tmp_path):
    recipe = make_recipe(client)
    db = tmp_path / "test.db"

    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 100)
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})
    client.post(f"/sessions/{s1['id']}/finish")

    s2 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s2["id"], 200)
    resp = client.post(f"/sessions/{s2['id']}/step", json={"step_index": 1})
    log_id = resp.json()["pending_step_confirmation"]["log_id"]

    confirm_resp = client.post(f"/sessions/step-time/{log_id}/confirm", json={"counted": True})
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["pending_step_confirmation"] is None
    client.post(f"/sessions/{s2['id']}/finish")

    # Average is now (100+200)/2=150. A 160s sample is within 10% of 150 but
    # NOT of the old 100 baseline, so this only stays uncontested if the
    # average really moved.
    s3 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s3["id"], 160)
    resp3 = client.post(f"/sessions/{s3['id']}/step", json={"step_index": 1})
    assert resp3.json()["pending_step_confirmation"] is None


def test_declining_outlier_leaves_average_untouched(client, tmp_path):
    recipe = make_recipe(client)
    db = tmp_path / "test.db"

    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 100)
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})
    client.post(f"/sessions/{s1['id']}/finish")

    s2 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s2["id"], 200)
    resp = client.post(f"/sessions/{s2['id']}/step", json={"step_index": 1})
    log_id = resp.json()["pending_step_confirmation"]["log_id"]

    client.post(f"/sessions/step-time/{log_id}/confirm", json={"counted": False})
    client.post(f"/sessions/{s2['id']}/finish")

    # Average should still be 100 -> a 105s sample (5% off) stays within tolerance.
    s3 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s3["id"], 105)
    resp3 = client.post(f"/sessions/{s3['id']}/step", json={"step_index": 1})
    assert resp3.json()["pending_step_confirmation"] is None


def test_confirm_already_resolved_log_rejected(client, tmp_path):
    recipe = make_recipe(client)
    db = tmp_path / "test.db"
    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 100)
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})
    client.post(f"/sessions/{s1['id']}/finish")

    s2 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s2["id"], 200)
    resp = client.post(f"/sessions/{s2['id']}/step", json={"step_index": 1})
    log_id = resp.json()["pending_step_confirmation"]["log_id"]
    client.post(f"/sessions/step-time/{log_id}/confirm", json={"counted": True})

    resp2 = client.post(f"/sessions/step-time/{log_id}/confirm", json={"counted": True})
    assert resp2.status_code == 400


def test_confirm_nonexistent_log_404(client):
    resp = client.post("/sessions/step-time/999/confirm", json={"counted": True})
    assert resp.status_code == 404


def test_very_short_step_not_logged(client, tmp_path):
    recipe = make_recipe(client)
    db = tmp_path / "test.db"
    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 1)  # below the 3s floor -> not logged
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})
    client.post(f"/sessions/{s1['id']}/finish")

    # If the 1s sample HAD been logged as a baseline, this 500s sample would
    # be a wild outlier. Since it wasn't, this instead becomes the fresh
    # baseline itself (nothing to compare against yet).
    s2 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s2["id"], 500)
    resp = client.post(f"/sessions/{s2['id']}/step", json={"step_index": 1})
    assert resp.json()["pending_step_confirmation"] is None


def test_finish_logs_final_step_time_once(client, tmp_path):
    recipe = make_recipe(client)  # 2 steps, cook_time=45
    db = tmp_path / "test.db"
    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 50)
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})  # step0 baseline = 50s
    _backdate_step_started(db, s1["id"], 80)
    client.post(f"/sessions/{s1['id']}/finish")  # step1 baseline = 80s

    # Calling finish again must not log a second (near-zero) sample for step1.
    client.post(f"/sessions/{s1['id']}/finish")

    s2 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s2["id"], 10)  # 10s already elapsed on the new cook's step0
    active = client.get("/sessions/active").json()
    # step0 learned=50s minus 10s elapsed = 40s remaining; step1 learned=80s untouched -> 120
    assert active["estimated_remaining_seconds"] == 120


def test_long_learned_step_no_longer_inflates_remaining_estimate(client, tmp_path):
    # Regression test for the reported bug: a 95-minute recipe was showing
    # 110+ minutes remaining because a step's real duration (e.g. a 45-minute
    # bake) got ADDED on top of a flat per-step share that already implicitly
    # assumed every step (including that one) took only cook_time/steps.
    recipe = make_recipe(client, cook_time=95, steps=[
        {"sort_order": 1, "description": "Prep"},
        {"sort_order": 2, "description": "Oven"},
        {"sort_order": 3, "description": "Serve"},
    ])
    db = tmp_path / "test.db"

    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 120)  # prep took 2 min
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})
    _backdate_step_started(db, s1["id"], 45 * 60)  # oven took 45 min
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 2})
    _backdate_step_started(db, s1["id"], 120)  # serve took 2 min
    client.post(f"/sessions/{s1['id']}/finish")

    s2 = start_cooking(client, recipe["id"])
    client.post(f"/sessions/{s2['id']}/step", json={"step_index": 1})  # move onto the oven step
    client.post(f"/sessions/{s2['id']}/timer", json={"seconds": 45 * 60})

    active = client.get("/sessions/active").json()
    assert active["estimated_remaining_seconds"] == 45 * 60 + 120


def test_meanwhile_steps_excluded_from_progression_and_estimate(client):
    recipe = make_recipe(client, cook_time=30, steps=[
        {"sort_order": 1, "description": "Prep"},
        {"sort_order": 2, "description": "Bake"},
        {"sort_order": 1, "description": "Chop veggies", "track": "meanwhile"},
    ])
    assert len(recipe["steps"]) == 3

    session = start_cooking(client, recipe["id"])
    active = client.get("/sessions/active").json()
    assert active["total_steps"] == 2

    resp = client.post(f"/sessions/{session['id']}/step", json={"step_index": 2})
    assert resp.status_code == 400


def test_create_session_group_starts_two_linked_sessions(client):
    r1 = make_recipe(client, name="Aubergine")
    r2 = make_recipe(client, name="Flatbread")

    resp = client.post("/sessions/group", json={"recipe_ids": [r1["id"], r2["id"]], "cooked_by": "michael"})
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["sessions"]) == 2
    group_id = body["group_id"]
    assert all(s["group_id"] == group_id for s in body["sessions"])
    assert all(s["cooking_mode"] is True and s["finished_at"] is None for s in body["sessions"])

    group = client.get(f"/sessions/group/{group_id}").json()
    names = {g["recipe_name"] for g in group}
    assert names == {"Aubergine", "Flatbread"}


def test_create_session_group_blocks_if_already_cooking(client):
    r1 = make_recipe(client)
    r2 = make_recipe(client)
    r3 = make_recipe(client)
    client.post("/sessions/", json={"recipe_id": r1["id"], "cooked_by": "michael", "cooking_mode": True})

    resp = client.post("/sessions/group", json={"recipe_ids": [r2["id"], r3["id"]], "cooked_by": "michael"})
    assert resp.status_code == 400


def test_create_session_group_requires_exactly_two_recipes(client):
    r1 = make_recipe(client)
    resp = client.post("/sessions/group", json={"recipe_ids": [r1["id"]], "cooked_by": "michael"})
    assert resp.status_code == 422


def test_single_create_blocked_while_unpaired_session_in_progress(client):
    recipe = make_recipe(client)
    client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael", "cooking_mode": True})

    resp = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael", "cooking_mode": True})
    assert resp.status_code == 400


def test_single_create_allowed_for_different_user(client):
    recipe = make_recipe(client)
    client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "michael", "cooking_mode": True})

    resp = client.post("/sessions/", json={"recipe_id": recipe["id"], "cooked_by": "rachel", "cooking_mode": True})
    assert resp.status_code == 201


def test_in_progress_endpoint_lists_all_active_sessions(client):
    r1 = make_recipe(client)
    r2 = make_recipe(client)
    client.post("/sessions/", json={"recipe_id": r1["id"], "cooked_by": "michael", "cooking_mode": True})
    client.post("/sessions/", json={"recipe_id": r2["id"], "cooked_by": "rachel", "cooking_mode": True})

    all_active = client.get("/sessions/in-progress").json()
    assert len(all_active) == 2


def test_session_group_not_found_404(client):
    resp = client.get("/sessions/group/999")
    assert resp.status_code == 404


def test_quit_session_undoes_its_own_counted_contribution_but_keeps_others(client, tmp_path):
    recipe = make_recipe(client)
    db = tmp_path / "test.db"

    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 100)
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})  # baseline avg=100
    client.post(f"/sessions/{s1['id']}/finish")

    s2 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s2["id"], 105)  # 5% off -> auto-counted, avg becomes 102.5
    resp = client.post(f"/sessions/{s2['id']}/step", json={"step_index": 1})
    assert resp.json()["pending_step_confirmation"] is None

    quit_resp = client.delete(f"/sessions/{s2['id']}")
    assert quit_resp.status_code == 204

    # Average should be back to exactly 100 (s1's contribution only) -> a
    # 112s sample is 12% off 100 (outlier) but only 9.3% off 102.5, so this
    # only stays an outlier if s2's contribution was genuinely undone.
    s3 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s3["id"], 112)
    resp = client.post(f"/sessions/{s3['id']}/step", json={"step_index": 1})
    assert resp.json()["pending_step_confirmation"] is not None


def test_quit_session_clears_step_duration_when_it_was_the_only_contributor(client, tmp_path):
    recipe = make_recipe(client)
    db = tmp_path / "test.db"

    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 100)
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})  # baseline avg=100, sole sample

    quit_resp = client.delete(f"/sessions/{s1['id']}")
    assert quit_resp.status_code == 204

    # No learned data should remain -- a wildly different value becomes the
    # fresh baseline instead of triggering an outlier confirmation.
    s2 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s2["id"], 900)
    resp = client.post(f"/sessions/{s2['id']}/step", json={"step_index": 1})
    assert resp.json()["pending_step_confirmation"] is None


def test_quit_session_with_pending_confirmation_does_not_affect_average(client, tmp_path):
    recipe = make_recipe(client)
    db = tmp_path / "test.db"

    s1 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s1["id"], 100)
    client.post(f"/sessions/{s1['id']}/step", json={"step_index": 1})  # baseline avg=100
    client.post(f"/sessions/{s1['id']}/finish")

    s2 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s2["id"], 300)  # wild outlier vs 100 -> pending, never counted
    resp = client.post(f"/sessions/{s2['id']}/step", json={"step_index": 1})
    assert resp.json()["pending_step_confirmation"] is not None

    quit_resp = client.delete(f"/sessions/{s2['id']}")
    assert quit_resp.status_code == 204

    # Average should still be exactly 100 -- the pending sample never counted
    # in the first place, so quitting has nothing to undo for it.
    s3 = start_cooking(client, recipe["id"])
    _backdate_step_started(db, s3["id"], 105)
    resp = client.post(f"/sessions/{s3['id']}/step", json={"step_index": 1})
    assert resp.json()["pending_step_confirmation"] is None
