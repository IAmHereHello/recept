import io

from datetime import date, datetime
from tests.conftest import make_recipe

# Real 2x2 PNG / JPEG bytes so the /uploads mount serves a genuine image with a
# real Content-Type (it maps the extension, StaticFiles doesn't sniff content).
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000020802000000fdd49a73"
    "0000001649444154789c633cc1c5c5c0c0c0c4c0c0c0c0c000000b3800e011f4d5d6"
    "0000000049454e44ae426082"
)


def _freeze_today(monkeypatch, iso_date):
    import app.routers.planner as planner_module
    monkeypatch.setattr(planner_module, "_today", lambda: date.fromisoformat(iso_date))


def _redirect_uploads(monkeypatch, path):
    """Point both photo writes and the /uploads static mount at `path`."""
    import app.routers.sessions as sessions_module
    import main as main_module

    monkeypatch.setattr(sessions_module, "UPLOAD_DIR", path)
    for route in main_module.app.routes:
        if getattr(route, "name", "") == "uploads":
            monkeypatch.setattr(route.app, "all_directories", [str(path)])
            monkeypatch.setattr(route.app, "directory", str(path))


def start_cooking(client, recipe_id, cooked_by="michael"):
    resp = client.post("/sessions/", json={"recipe_id": recipe_id, "cooked_by": cooked_by, "cooking_mode": True})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_status_defaults_when_nothing_active_or_planned(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")  # Monday

    status = client.get("/dashboard/status").json()

    assert status["cooking_active"] is False
    assert status["cooking_recipe_id"] == 0
    assert status["cooking_recipe_name"] == ""
    assert status["cook_time_remaining_seconds"] == 0
    assert status["planned_today_recipe_id"] == 0
    assert status["planned_today_recipe_name"] == ""
    # Real ISO 8601 with a timezone offset, never a naive timestamp.
    assert datetime.fromisoformat(status["updated_at"]).tzinfo is not None


def test_status_reports_planned_recipe_for_today(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-07")  # Wednesday
    recipe = make_recipe(client, name="Chili sin carne")
    client.put(
        "/plan/2026-01-05/wed",
        json={"week_start": "2026-01-05", "day": "wed", "recipe_id": recipe["id"], "locked": False},
    )

    status = client.get("/dashboard/status").json()

    assert status["planned_today_recipe_id"] == recipe["id"]
    assert status["planned_today_recipe_name"] == "Chili sin carne"


def test_status_ignores_plan_entries_on_other_days(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")  # Monday
    recipe = make_recipe(client)
    client.put(
        "/plan/2026-01-05/tue",
        json={"week_start": "2026-01-05", "day": "tue", "recipe_id": recipe["id"], "locked": False},
    )

    status = client.get("/dashboard/status").json()

    assert status["planned_today_recipe_id"] == 0
    assert status["planned_today_recipe_name"] == ""


def test_status_reports_active_cooking_session_and_estimate(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    # cook_time=45min, 2 steps -> 1350s flat share per step
    recipe = make_recipe(client, name="Spaghetti Bolognese")
    session = start_cooking(client, recipe["id"])

    status = client.get("/dashboard/status").json()

    assert status["cooking_active"] is True
    assert status["cooking_recipe_id"] == recipe["id"]
    assert status["cooking_recipe_name"] == "Spaghetti Bolognese"
    assert status["cook_time_remaining_seconds"] == 2700

    # An active per-step timer folds into the total estimate, not on top of it.
    client.post(f"/sessions/{session['id']}/timer", json={"seconds": 300})
    status = client.get("/dashboard/status").json()
    assert status["cook_time_remaining_seconds"] == 300 + 1350


def test_status_reports_zero_remaining_when_recipe_has_no_cook_time(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    recipe = make_recipe(client, cook_time=None)
    start_cooking(client, recipe["id"])

    status = client.get("/dashboard/status").json()

    assert status["cooking_active"] is True
    assert status["cook_time_remaining_seconds"] == 0


def test_status_exposes_cooking_recipe_photo_as_fetchable_image_path(client, tmp_path, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    _redirect_uploads(monkeypatch, tmp_path)

    recipe = make_recipe(client, name="Shakshuka")
    session = start_cooking(client, recipe["id"])
    upload = client.post(
        f"/sessions/{session['id']}/photo",
        files={"file": ("plate.png", io.BytesIO(_PNG_BYTES), "image/png")},
        data={"uploaded_by": "michael"},
    )
    assert upload.status_code == 200, upload.text

    path = client.get("/dashboard/status").json()["cooking_recipe_image_path"]
    assert path and path.startswith("/")

    # Same app, same base URL, no auth -> raw image bytes + real Content-Type.
    img = client.get(path)
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.content == _PNG_BYTES


def test_status_image_path_is_scoped_to_the_recipe_being_cooked(client, tmp_path, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    _redirect_uploads(monkeypatch, tmp_path)

    # Another recipe has a photo but isn't the one being cooked.
    other = make_recipe(client, name="Other")
    other_session = start_cooking(client, other["id"])
    client.post(
        f"/sessions/{other_session['id']}/photo",
        files={"file": ("other.png", io.BytesIO(_PNG_BYTES), "image/png")},
        data={"uploaded_by": "michael"},
    )
    client.post(f"/sessions/{other_session['id']}/finish")

    cooking = make_recipe(client, name="Cooking now")
    session = start_cooking(client, cooking["id"])
    mine = client.post(
        f"/sessions/{session['id']}/photo",
        files={"file": ("mine.png", io.BytesIO(_PNG_BYTES), "image/png")},
        data={"uploaded_by": "rachel"},
    ).json()["photos"][0]["file_path"]

    assert client.get("/dashboard/status").json()["cooking_recipe_image_path"] == mine


def test_status_image_path_null_when_cooking_recipe_has_no_photo(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    recipe = make_recipe(client)
    start_cooking(client, recipe["id"])

    assert client.get("/dashboard/status").json()["cooking_recipe_image_path"] is None


def test_status_falls_back_to_imported_cover_image_when_no_photo(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    recipe = make_recipe(client, name="Griekse ovenschotel", image_path="/uploads/imported.jpg")
    start_cooking(client, recipe["id"])

    assert client.get("/dashboard/status").json()["cooking_recipe_image_path"] == "/uploads/imported.jpg"


def test_status_image_path_null_when_nothing_is_cooking(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    make_recipe(client)  # a recipe exists but no active session

    assert client.get("/dashboard/status").json()["cooking_recipe_image_path"] is None


def test_status_clears_cooking_fields_once_finished(client, monkeypatch):
    _freeze_today(monkeypatch, "2026-01-05")
    recipe = make_recipe(client)
    session = start_cooking(client, recipe["id"])
    client.post(f"/sessions/{session['id']}/finish")

    status = client.get("/dashboard/status").json()

    assert status["cooking_active"] is False
    assert status["cooking_recipe_id"] == 0
    assert status["cook_time_remaining_seconds"] == 0
