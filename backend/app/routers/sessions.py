from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlite3 import Connection
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import aiofiles
import uuid

from app.config import UPLOAD_DIR
from app.database import get_db
from app.models import (
    CookSessionIn, CookSessionOut, RatingIn, PendingReviewOut, User,
    StepAdvanceIn, TimerStartIn, ActiveSessionOut,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.heic'}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_session(conn: Connection, session_id: int) -> dict:
    row = conn.execute("SELECT * FROM cook_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    s = dict(row)
    s["ratings"] = [dict(r) for r in conn.execute(
        "SELECT * FROM ratings WHERE cook_session_id = ?", (session_id,)
    ).fetchall()]
    s["photos"] = [dict(p) for p in conn.execute(
        "SELECT id, file_path, uploaded_by FROM photos WHERE cook_session_id = ? ORDER BY uploaded_at", (session_id,)
    ).fetchall()]
    return s


@router.get("/recipe/{recipe_id}", response_model=list[CookSessionOut])
def list_sessions_for_recipe(recipe_id: int, conn: Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT id FROM cook_sessions WHERE recipe_id = ? ORDER BY cooked_at DESC", (recipe_id,)
    ).fetchall()
    return [_fetch_session(conn, row["id"]) for row in rows]


@router.post("/", response_model=CookSessionOut, status_code=201)
def create_session(body: CookSessionIn, conn: Connection = Depends(get_db)):
    cooked_at = body.cooked_at or _now()
    # Cooking-mode sessions start "in progress" (finished_at=NULL, on step 0);
    # everything else behaves exactly like the old instant-log flow (done immediately).
    step_started_at = _now() if body.cooking_mode else None
    finished_at = None if body.cooking_mode else cooked_at
    cur = conn.execute(
        """INSERT INTO cook_sessions
           (recipe_id, cooked_at, notes, cooked_by, cooking_mode, current_step, step_started_at, finished_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (body.recipe_id, cooked_at, body.notes, body.cooked_by, int(body.cooking_mode), 0, step_started_at, finished_at)
    )
    conn.commit()
    return _fetch_session(conn, cur.lastrowid)


@router.get("/active", response_model=Optional[ActiveSessionOut])
def active_session(conn: Connection = Depends(get_db)):
    # Most-recently-started in-progress session; if both users somehow start
    # cooking at once (not a designed-for scenario for a two-person household),
    # only the latest one is surfaced.
    row = conn.execute(
        """SELECT cs.id, cs.recipe_id, cs.cooked_by, cs.current_step,
                  cs.timer_seconds, cs.timer_started_at, r.name AS recipe_name, r.cook_time
           FROM cook_sessions cs
           JOIN recipes r ON r.id = cs.recipe_id
           WHERE cs.cooking_mode = 1 AND cs.finished_at IS NULL
           ORDER BY cs.id DESC LIMIT 1"""
    ).fetchone()
    if not row:
        return None

    total_steps = conn.execute(
        "SELECT COUNT(*) as c FROM steps WHERE recipe_id = ?", (row["recipe_id"],)
    ).fetchone()["c"]

    active_timer_remaining = None
    if row["timer_seconds"] is not None and row["timer_started_at"] is not None:
        started = datetime.fromisoformat(row["timer_started_at"])
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        active_timer_remaining = max(0, round(row["timer_seconds"] - elapsed))

    estimated_remaining = None
    if row["cook_time"] is not None and total_steps > 0:
        per_step = (row["cook_time"] * 60) / total_steps
        remaining_after_current = (total_steps - row["current_step"] - 1) * per_step
        current_step_share = active_timer_remaining if active_timer_remaining is not None else per_step
        estimated_remaining = round(current_step_share + remaining_after_current)

    return {
        "session_id": row["id"],
        "recipe_id": row["recipe_id"],
        "recipe_name": row["recipe_name"],
        "cooked_by": row["cooked_by"],
        "current_step": row["current_step"],
        "total_steps": total_steps,
        "active_timer_remaining_seconds": active_timer_remaining,
        "estimated_remaining_seconds": estimated_remaining,
    }


@router.post("/{session_id}/step", response_model=CookSessionOut)
def advance_step(session_id: int, body: StepAdvanceIn, conn: Connection = Depends(get_db)):
    session = _fetch_session(conn, session_id)
    if session["finished_at"] is not None:
        raise HTTPException(400, "Cooking session is already finished")
    total_steps = conn.execute(
        "SELECT COUNT(*) as c FROM steps WHERE recipe_id = ?", (session["recipe_id"],)
    ).fetchone()["c"]
    if not (0 <= body.step_index < total_steps):
        raise HTTPException(400, "step_index out of range")
    conn.execute(
        """UPDATE cook_sessions SET current_step=?, step_started_at=?, timer_seconds=NULL, timer_started_at=NULL
           WHERE id=?""",
        (body.step_index, _now(), session_id)
    )
    conn.commit()
    return _fetch_session(conn, session_id)


@router.post("/{session_id}/timer", response_model=CookSessionOut)
def start_timer(session_id: int, body: TimerStartIn, conn: Connection = Depends(get_db)):
    _fetch_session(conn, session_id)
    conn.execute(
        "UPDATE cook_sessions SET timer_seconds=?, timer_started_at=? WHERE id=?",
        (body.seconds, _now(), session_id)
    )
    conn.commit()
    return _fetch_session(conn, session_id)


@router.delete("/{session_id}/timer", status_code=204)
def clear_timer(session_id: int, conn: Connection = Depends(get_db)):
    _fetch_session(conn, session_id)
    conn.execute(
        "UPDATE cook_sessions SET timer_seconds=NULL, timer_started_at=NULL WHERE id=?",
        (session_id,)
    )
    conn.commit()


@router.post("/{session_id}/finish", response_model=CookSessionOut)
def finish_cooking(session_id: int, conn: Connection = Depends(get_db)):
    _fetch_session(conn, session_id)
    conn.execute(
        "UPDATE cook_sessions SET finished_at=? WHERE id=?",
        (_now(), session_id)
    )
    conn.commit()
    return _fetch_session(conn, session_id)


@router.get("/pending/{user}", response_model=list[PendingReviewOut])
def pending_reviews(user: User, conn: Connection = Depends(get_db)):
    # A session is pending for `user` once it's finished, they haven't rated it
    # yet, and either they didn't cook it (the original rule) or it was started
    # via cooking mode — in which case the cook reviews it later too, deferred
    # to this same gate rather than rating immediately when it's done.
    rows = conn.execute(
        """SELECT cs.id, cs.recipe_id, cs.cooked_at, r.name AS recipe_name, r.is_freezable, r.portions
           FROM cook_sessions cs
           JOIN recipes r ON r.id = cs.recipe_id
           WHERE cs.finished_at IS NOT NULL
             AND (cs.cooked_by != ? OR cs.cooking_mode = 1)
             AND NOT EXISTS (
               SELECT 1 FROM ratings rt WHERE rt.cook_session_id = cs.id AND rt.user = ?
             )
           ORDER BY cs.cooked_at ASC""",
        (user.value, user.value)
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/{session_id}/rate", response_model=CookSessionOut)
def rate_session(session_id: int, body: RatingIn, conn: Connection = Depends(get_db)):
    _fetch_session(conn, session_id)
    conn.execute(
        """INSERT INTO ratings (cook_session_id, user, stars)
           VALUES (?,?,?)
           ON CONFLICT(cook_session_id, user) DO UPDATE SET stars=excluded.stars, rated_at=datetime('now')""",
        (session_id, body.user, body.stars)
    )
    conn.commit()
    return _fetch_session(conn, session_id)


@router.delete("/{session_id}/rate/{user}", status_code=204)
def delete_rating(session_id: int, user: User, conn: Connection = Depends(get_db)):
    _fetch_session(conn, session_id)
    conn.execute(
        "DELETE FROM ratings WHERE cook_session_id = ? AND user = ?",
        (session_id, user.value)
    )
    conn.commit()


@router.post("/{session_id}/photo", response_model=CookSessionOut)
async def upload_photo(
    session_id: int,
    file: UploadFile = File(...),
    uploaded_by: User = Form(...),
    conn: Connection = Depends(get_db),
):
    _fetch_session(conn, session_id)
    suffix = Path(file.filename).suffix.lower() if file.filename else '.jpg'
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    filename = f"{uuid.uuid4()}{suffix}"
    dest = UPLOAD_DIR / filename
    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)
    conn.execute(
        "INSERT INTO photos (cook_session_id, file_path, uploaded_by) VALUES (?,?,?)",
        (session_id, f"/uploads/{filename}", uploaded_by.value)
    )
    conn.commit()
    return _fetch_session(conn, session_id)


@router.delete("/{session_id}/photo/{photo_id}", status_code=204)
def delete_photo(session_id: int, photo_id: int, conn: Connection = Depends(get_db)):
    _fetch_session(conn, session_id)
    row = conn.execute(
        "SELECT file_path FROM photos WHERE id = ? AND cook_session_id = ?", (photo_id, session_id)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Photo not found")
    conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    conn.commit()
    (UPLOAD_DIR / Path(row["file_path"]).name).unlink(missing_ok=True)


@router.get("/{session_id}", response_model=CookSessionOut)
def get_session(session_id: int, conn: Connection = Depends(get_db)):
    return _fetch_session(conn, session_id)
