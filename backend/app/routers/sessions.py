from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlite3 import Connection
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional
import aiofiles
import uuid

from app.config import UPLOAD_DIR
from app.database import get_db
from app.models import (
    CookSessionIn, CookSessionOut, RatingIn, PendingReviewOut, User,
    StepAdvanceIn, TimerStartIn, ActiveSessionOut, SessionGroupCreateIn,
    SessionGroupOut, StepTimeConfirmIn, GroupSessionOut,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.heic'}

# A session is considered abandoned once it's been this long since the cook
# last interacted with it — but a running timer's own end time counts as
# activity too, so waiting out a long bake never gets flagged mid-countdown
# (see _is_stale).
INACTIVITY_TIMEOUT_SECONDS = 60 * 60

# Step-time learning: a fresh observation within this fraction of the running
# average is auto-accepted; anything further off is held as a pending
# confirmation (see _log_step_time) rather than silently skewing the average.
OUTLIER_TOLERANCE = 0.10
# Guards against accidental double-taps (e.g. tapping "volgende" twice)
# logging a near-zero-second "step" that would drag the average down.
MIN_LOGGABLE_SECONDS = 3

_ACTIVE_SESSION_SELECT = """
    SELECT cs.id, cs.recipe_id, cs.cooked_by, cs.current_step,
           cs.timer_seconds, cs.timer_started_at, cs.step_started_at,
           cs.cooked_at, cs.finished_at, cs.last_activity_at, cs.group_id,
           r.name AS recipe_name, r.cook_time
    FROM cook_sessions cs
    JOIN recipes r ON r.id = cs.recipe_id
    WHERE cs.cooking_mode = 1 AND cs.finished_at IS NULL
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_aware(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _is_stale(row: dict, now: datetime) -> bool:
    if row["finished_at"] is not None:
        return False
    reference_raw = row["last_activity_at"] or row["step_started_at"] or row["cooked_at"]
    reference = _parse_aware(reference_raw)
    if row["timer_seconds"] is not None and row["timer_started_at"] is not None:
        timer_end = _parse_aware(row["timer_started_at"]) + timedelta(seconds=row["timer_seconds"])
        if timer_end > reference:
            reference = timer_end
    return (now - reference).total_seconds() > INACTIVITY_TIMEOUT_SECONDS


def _main_step_rows(conn: Connection, recipe_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT sort_order, wait_time_minutes, description FROM steps WHERE recipe_id=? AND track='main' ORDER BY sort_order",
        (recipe_id,)
    ).fetchall()]


def _estimate_remaining_seconds(
    conn: Connection, recipe_id: int, cook_time: Optional[int], main_steps: list[dict],
    current_step: int, active_timer_remaining: Optional[int], step_started_at: Optional[str], now: datetime,
) -> Optional[int]:
    total_steps = len(main_steps)
    if total_steps == 0:
        return None

    learned = {
        row["sort_order"]: row["avg_seconds"]
        for row in conn.execute(
            "SELECT sort_order, avg_seconds FROM step_durations WHERE recipe_id=? AND track='main' AND sample_count > 0",
            (recipe_id,)
        ).fetchall()
    }
    known_total = sum(learned.values())
    unknown_count = total_steps - len(learned)

    if cook_time is not None:
        # Budget minus whatever's already been empirically learned, spread
        # over the steps we still have no data for — NOT a flat cook_time/N
        # applied everywhere, which is what let a long learned/real step's
        # overrun distort every other step's share (the original bug).
        fallback_avg = max(0.0, cook_time * 60 - known_total) / unknown_count if unknown_count > 0 else 0.0
    elif unknown_count == 0:
        # No author estimate at all, but every step has real history — just
        # add the learned averages up directly.
        fallback_avg = 0.0
    else:
        return None  # nothing to derive a fallback share from

    def share_for(index: int, is_current: bool) -> float:
        sort_order = main_steps[index]["sort_order"]
        if is_current and active_timer_remaining is not None:
            return float(active_timer_remaining)
        base = learned.get(sort_order, fallback_avg)
        if is_current and sort_order in learned and step_started_at:
            elapsed = (now - _parse_aware(step_started_at)).total_seconds()
            return max(0.0, base - elapsed)
        return base

    current_share = share_for(current_step, True)
    remaining_share = sum(share_for(i, False) for i in range(current_step + 1, total_steps))
    return round(current_share + remaining_share)


def _active_session_out(conn: Connection, row: dict) -> dict:
    main_steps = _main_step_rows(conn, row["recipe_id"])
    total_steps = len(main_steps)

    active_timer_remaining = None
    if row["timer_seconds"] is not None and row["timer_started_at"] is not None:
        started = datetime.fromisoformat(row["timer_started_at"])
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        active_timer_remaining = max(0, round(row["timer_seconds"] - elapsed))

    estimated_remaining = None
    if total_steps > 0:
        estimated_remaining = _estimate_remaining_seconds(
            conn, row["recipe_id"], row["cook_time"], main_steps, row["current_step"],
            active_timer_remaining, row["step_started_at"], datetime.now(timezone.utc)
        )

    return {
        "session_id": row["id"],
        "recipe_id": row["recipe_id"],
        "recipe_name": row["recipe_name"],
        "cooked_by": row["cooked_by"],
        "current_step": row["current_step"],
        "total_steps": total_steps,
        "active_timer_remaining_seconds": active_timer_remaining,
        "estimated_remaining_seconds": estimated_remaining,
        "is_stale": _is_stale(row, datetime.now(timezone.utc)),
        "group_id": row["group_id"],
    }


def _log_step_time(conn: Connection, recipe_id: int, track: str, sort_order: int, cook_session_id: int, seconds: int) -> None:
    if seconds < MIN_LOGGABLE_SECONDS:
        return
    existing = conn.execute(
        "SELECT * FROM step_durations WHERE recipe_id=? AND track=? AND sort_order=?",
        (recipe_id, track, sort_order)
    ).fetchone()

    if existing is None or existing["sample_count"] == 0:
        # First-ever observation for this step — nothing to compare against,
        # so it becomes the baseline outright (no confirmation needed).
        conn.execute(
            "INSERT INTO step_time_logs (recipe_id, track, sort_order, cook_session_id, seconds, counted) VALUES (?,?,?,?,?,1)",
            (recipe_id, track, sort_order, cook_session_id, seconds)
        )
        conn.execute(
            """INSERT INTO step_durations (recipe_id, track, sort_order, avg_seconds, sample_count, updated_at)
               VALUES (?,?,?,?,1,?)
               ON CONFLICT(recipe_id, track, sort_order)
               DO UPDATE SET avg_seconds=excluded.avg_seconds, sample_count=1, updated_at=excluded.updated_at""",
            (recipe_id, track, sort_order, float(seconds), _now())
        )
        return

    avg = existing["avg_seconds"]
    count = existing["sample_count"]
    deviation = abs(seconds - avg) / avg if avg > 0 else 1.0

    if deviation <= OUTLIER_TOLERANCE:
        conn.execute(
            "INSERT INTO step_time_logs (recipe_id, track, sort_order, cook_session_id, seconds, counted) VALUES (?,?,?,?,?,1)",
            (recipe_id, track, sort_order, cook_session_id, seconds)
        )
        new_avg = (avg * count + seconds) / (count + 1)
        conn.execute(
            "UPDATE step_durations SET avg_seconds=?, sample_count=?, updated_at=? WHERE id=?",
            (new_avg, count + 1, _now(), existing["id"])
        )
    else:
        # Outside +-10% of the running average — hold it as a pending sample
        # rather than let a one-off (or a mistake) skew future estimates.
        # _fetch_session surfaces this via pending_step_confirmation until
        # the frontend calls /sessions/step-time/{id}/confirm.
        conn.execute(
            "INSERT INTO step_time_logs (recipe_id, track, sort_order, cook_session_id, seconds, counted) VALUES (?,?,?,?,?,NULL)",
            (recipe_id, track, sort_order, cook_session_id, seconds)
        )


def _undo_counted_step_times(conn: Connection, session_id: int) -> None:
    # Quitting mid-cook (whether via the explicit "Stop met koken" button or
    # abandoning a stale session) must not leave this session's step times
    # baked into the learned average — recompute each affected step's average
    # from its remaining counted samples (raw seconds are kept per-log
    # specifically so this recomputation is exact, not an approximation of
    # reversing the incremental rolling average), or clear it entirely if
    # this session was the only contributor so far. Pending/declined samples
    # never touched step_durations in the first place, so they need no
    # special handling here — they're simply cascade-deleted with the
    # session's rows.
    affected = conn.execute(
        "SELECT DISTINCT recipe_id, track, sort_order FROM step_time_logs WHERE cook_session_id=? AND counted=1",
        (session_id,)
    ).fetchall()
    for row in affected:
        remaining = conn.execute(
            """SELECT seconds FROM step_time_logs
               WHERE recipe_id=? AND track=? AND sort_order=? AND counted=1 AND cook_session_id != ?""",
            (row["recipe_id"], row["track"], row["sort_order"], session_id)
        ).fetchall()
        if remaining:
            seconds_list = [r["seconds"] for r in remaining]
            new_avg = sum(seconds_list) / len(seconds_list)
            conn.execute(
                "UPDATE step_durations SET avg_seconds=?, sample_count=?, updated_at=? WHERE recipe_id=? AND track=? AND sort_order=?",
                (new_avg, len(seconds_list), _now(), row["recipe_id"], row["track"], row["sort_order"])
            )
        else:
            conn.execute(
                "DELETE FROM step_durations WHERE recipe_id=? AND track=? AND sort_order=?",
                (row["recipe_id"], row["track"], row["sort_order"])
            )


def _fetch_session(conn: Connection, session_id: int) -> dict:
    row = conn.execute("SELECT * FROM cook_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    s = dict(row)
    s["is_stale"] = _is_stale(s, datetime.now(timezone.utc))
    s["ratings"] = [dict(r) for r in conn.execute(
        "SELECT * FROM ratings WHERE cook_session_id = ?", (session_id,)
    ).fetchall()]
    s["photos"] = [dict(p) for p in conn.execute(
        "SELECT id, file_path, uploaded_by FROM photos WHERE cook_session_id = ? ORDER BY uploaded_at", (session_id,)
    ).fetchall()]
    pending = conn.execute(
        """SELECT stl.id as log_id, stl.track, stl.sort_order, stl.seconds, sd.avg_seconds
           FROM step_time_logs stl
           LEFT JOIN step_durations sd
             ON sd.recipe_id = stl.recipe_id AND sd.track = stl.track AND sd.sort_order = stl.sort_order
           WHERE stl.cook_session_id = ? AND stl.counted IS NULL
           ORDER BY stl.id DESC LIMIT 1""",
        (session_id,)
    ).fetchone()
    s["pending_step_confirmation"] = dict(pending) if pending else None
    return s


@router.get("/recipe/{recipe_id}", response_model=list[CookSessionOut])
def list_sessions_for_recipe(recipe_id: int, conn: Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT id FROM cook_sessions WHERE recipe_id = ? ORDER BY cooked_at DESC", (recipe_id,)
    ).fetchall()
    return [_fetch_session(conn, row["id"]) for row in rows]


@router.post("/", response_model=CookSessionOut, status_code=201)
def create_session(body: CookSessionIn, conn: Connection = Depends(get_db)):
    # Only one *unpaired* in-progress cooking-mode session per person at a
    # time — combining two recipes is only sanctioned via the explicit
    # "Kook samen met..." pairing flow (POST /sessions/group), which creates
    # both sessions together atomically instead of letting them accumulate
    # ad hoc.
    if body.cooking_mode and body.cooked_by is not None:
        existing = conn.execute(
            "SELECT id FROM cook_sessions WHERE cooked_by=? AND cooking_mode=1 AND finished_at IS NULL",
            (body.cooked_by.value,)
        ).fetchone()
        if existing:
            raise HTTPException(
                400,
                "Er is al een kooksessie in uitvoering. Gebruik 'Kook samen met...' om een tweede recept te combineren."
            )

    cooked_at = body.cooked_at or _now()
    # Cooking-mode sessions start "in progress" (finished_at=NULL, on step 0);
    # everything else behaves exactly like the old instant-log flow (done immediately).
    step_started_at = _now() if body.cooking_mode else None
    finished_at = None if body.cooking_mode else cooked_at
    cur = conn.execute(
        """INSERT INTO cook_sessions
           (recipe_id, cooked_at, notes, cooked_by, cooking_mode, current_step, step_started_at, finished_at, last_activity_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (body.recipe_id, cooked_at, body.notes, body.cooked_by, int(body.cooking_mode), 0, step_started_at, finished_at, step_started_at)
    )
    conn.commit()
    return _fetch_session(conn, cur.lastrowid)


@router.post("/group", response_model=SessionGroupOut, status_code=201)
def create_session_group(body: SessionGroupCreateIn, conn: Connection = Depends(get_db)):
    # "Kook samen met..." — starts exactly two linked cooking-mode sessions at
    # once (e.g. the oven dish + the fresh flatbread), so their timers can be
    # tracked together and CookingMode can offer a switcher between them.
    if body.cooked_by is not None:
        existing = conn.execute(
            "SELECT id FROM cook_sessions WHERE cooked_by=? AND cooking_mode=1 AND finished_at IS NULL",
            (body.cooked_by.value,)
        ).fetchone()
        if existing:
            raise HTTPException(400, "Er is al een kooksessie in uitvoering.")

    for recipe_id in body.recipe_ids:
        if not conn.execute("SELECT id FROM recipes WHERE id=?", (recipe_id,)).fetchone():
            raise HTTPException(404, f"Recept {recipe_id} niet gevonden")

    cur = conn.execute("INSERT INTO session_groups DEFAULT VALUES")
    group_id = cur.lastrowid

    session_ids = []
    for recipe_id in body.recipe_ids:
        now = _now()
        cur2 = conn.execute(
            """INSERT INTO cook_sessions
               (recipe_id, cooked_at, cooked_by, cooking_mode, current_step, step_started_at, finished_at, last_activity_at, group_id)
               VALUES (?,?,?,1,0,?,NULL,?,?)""",
            (recipe_id, now, body.cooked_by.value if body.cooked_by else None, now, now, group_id)
        )
        session_ids.append(cur2.lastrowid)
    conn.commit()
    return {"group_id": group_id, "sessions": [_fetch_session(conn, sid) for sid in session_ids]}


@router.get("/group/{group_id}", response_model=list[GroupSessionOut])
def get_session_group(group_id: int, conn: Connection = Depends(get_db)):
    rows = conn.execute(
        """SELECT cs.id as session_id, cs.recipe_id, cs.finished_at, r.name as recipe_name
           FROM cook_sessions cs JOIN recipes r ON r.id = cs.recipe_id
           WHERE cs.group_id=? ORDER BY cs.id""",
        (group_id,)
    ).fetchall()
    if not rows:
        raise HTTPException(404, "Session group not found")
    return [dict(r) for r in rows]


@router.get("/in-progress", response_model=list[ActiveSessionOut])
def in_progress_sessions(conn: Connection = Depends(get_db)):
    # Every cooking-mode session still in progress (both users, any grouping)
    # — powers the app-wide persistent timer bar, which (unlike /active) never
    # collapses multiple concurrent sessions down to just the latest one.
    rows = conn.execute(_ACTIVE_SESSION_SELECT + " ORDER BY cs.last_activity_at DESC").fetchall()
    return [_active_session_out(conn, dict(row)) for row in rows]


@router.get("/active", response_model=Optional[ActiveSessionOut])
def active_session(conn: Connection = Depends(get_db)):
    # Most-recently-active in-progress session. Kept singular (rather than a
    # list) for backward compatibility with the external dashboard endpoint;
    # see /sessions/in-progress for the full list used inside the app.
    row = conn.execute(_ACTIVE_SESSION_SELECT + " ORDER BY cs.last_activity_at DESC LIMIT 1").fetchone()
    if not row:
        return None
    return _active_session_out(conn, dict(row))


@router.post("/{session_id}/step", response_model=CookSessionOut)
def advance_step(session_id: int, body: StepAdvanceIn, conn: Connection = Depends(get_db)):
    session = _fetch_session(conn, session_id)
    if session["finished_at"] is not None:
        raise HTTPException(400, "Cooking session is already finished")
    main_steps = _main_step_rows(conn, session["recipe_id"])
    total_steps = len(main_steps)
    if not (0 <= body.step_index < total_steps):
        raise HTTPException(400, "step_index out of range")

    current_time = datetime.now(timezone.utc)
    if session["step_started_at"] and 0 <= session["current_step"] < total_steps:
        left_step = main_steps[session["current_step"]]
        elapsed = (current_time - _parse_aware(session["step_started_at"])).total_seconds()
        _log_step_time(conn, session["recipe_id"], "main", left_step["sort_order"], session_id, round(elapsed))

    now = current_time.isoformat()
    conn.execute(
        """UPDATE cook_sessions SET current_step=?, step_started_at=?, timer_seconds=NULL, timer_started_at=NULL, last_activity_at=?
           WHERE id=?""",
        (body.step_index, now, now, session_id)
    )
    conn.commit()
    return _fetch_session(conn, session_id)


@router.post("/step-time/{log_id}/confirm", response_model=CookSessionOut)
def confirm_step_time(log_id: int, body: StepTimeConfirmIn, conn: Connection = Depends(get_db)):
    log = conn.execute("SELECT * FROM step_time_logs WHERE id=?", (log_id,)).fetchone()
    if not log:
        raise HTTPException(404, "Step time log not found")
    if log["counted"] is not None:
        raise HTTPException(400, "This step time was already confirmed")

    if body.counted:
        existing = conn.execute(
            "SELECT * FROM step_durations WHERE recipe_id=? AND track=? AND sort_order=?",
            (log["recipe_id"], log["track"], log["sort_order"])
        ).fetchone()
        if existing:
            new_avg = (existing["avg_seconds"] * existing["sample_count"] + log["seconds"]) / (existing["sample_count"] + 1)
            conn.execute(
                "UPDATE step_durations SET avg_seconds=?, sample_count=?, updated_at=? WHERE id=?",
                (new_avg, existing["sample_count"] + 1, _now(), existing["id"])
            )
        else:
            conn.execute(
                "INSERT INTO step_durations (recipe_id, track, sort_order, avg_seconds, sample_count, updated_at) VALUES (?,?,?,?,1,?)",
                (log["recipe_id"], log["track"], log["sort_order"], float(log["seconds"]), _now())
            )
        conn.execute("UPDATE step_time_logs SET counted=1 WHERE id=?", (log_id,))
    else:
        conn.execute("UPDATE step_time_logs SET counted=0 WHERE id=?", (log_id,))
    conn.commit()
    return _fetch_session(conn, log["cook_session_id"])


@router.post("/{session_id}/timer", response_model=CookSessionOut)
def start_timer(session_id: int, body: TimerStartIn, conn: Connection = Depends(get_db)):
    _fetch_session(conn, session_id)
    now = _now()
    conn.execute(
        "UPDATE cook_sessions SET timer_seconds=?, timer_started_at=?, last_activity_at=? WHERE id=?",
        (body.seconds, now, now, session_id)
    )
    conn.commit()
    return _fetch_session(conn, session_id)


@router.delete("/{session_id}/timer", status_code=204)
def clear_timer(session_id: int, conn: Connection = Depends(get_db)):
    _fetch_session(conn, session_id)
    conn.execute(
        "UPDATE cook_sessions SET timer_seconds=NULL, timer_started_at=NULL, last_activity_at=? WHERE id=?",
        (_now(), session_id)
    )
    conn.commit()


@router.post("/{session_id}/touch", status_code=204)
def touch_session(session_id: int, conn: Connection = Depends(get_db)):
    # Lightweight heartbeat pinged by the frontend while the cooking page is
    # open and visible, so reading a step for a while without pressing
    # anything doesn't get mistaken for having walked away.
    session = _fetch_session(conn, session_id)
    if session["finished_at"] is not None:
        raise HTTPException(400, "Cooking session is already finished")
    conn.execute("UPDATE cook_sessions SET last_activity_at=? WHERE id=?", (_now(), session_id))
    conn.commit()


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: int, conn: Connection = Depends(get_db)):
    # Abandons an in-progress session — used by both the "restart cooking
    # session?" stale-session dialog and the explicit "Stop met koken"
    # button. Finished sessions carry review/photo/freezer history and must
    # never be deletable this way.
    session = _fetch_session(conn, session_id)
    if session["finished_at"] is not None:
        raise HTTPException(400, "Cannot delete a finished cooking session")
    _undo_counted_step_times(conn, session_id)
    conn.execute("DELETE FROM cook_sessions WHERE id=?", (session_id,))
    conn.commit()


@router.post("/{session_id}/finish", response_model=CookSessionOut)
def finish_cooking(session_id: int, conn: Connection = Depends(get_db)):
    session = _fetch_session(conn, session_id)
    if session["finished_at"] is None and session["cooking_mode"] and session["step_started_at"]:
        main_steps = _main_step_rows(conn, session["recipe_id"])
        if 0 <= session["current_step"] < len(main_steps):
            elapsed = (datetime.now(timezone.utc) - _parse_aware(session["step_started_at"])).total_seconds()
            _log_step_time(
                conn, session["recipe_id"], "main", main_steps[session["current_step"]]["sort_order"],
                session_id, round(elapsed)
            )
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
