from fastapi import APIRouter, Depends
from sqlite3 import Connection
from datetime import datetime

from app.database import get_db
from app.models import DashboardStatusOut
from app.routers import planner, sessions

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/status", response_model=DashboardStatusOut)
def dashboard_status(conn: Connection = Depends(get_db)):
    # Reuses sessions.active_session's own timer/step-share math (calling the
    # route function directly, bypassing its Depends default) instead of
    # duplicating that estimate logic here.
    cooking = sessions.active_session(conn=conn)

    # planner._today()/_week_start() are indirections the test suite already
    # monkeypatches to freeze "today" — call them via the module object (not
    # a bound import) so that still works for this endpoint too.
    today = planner._today()
    week_start = planner._week_start(today.isoformat())
    day = planner.DAYS[today.weekday()]

    planned = conn.execute(
        """SELECT r.id AS recipe_id, r.name AS recipe_name
           FROM meal_plan mp JOIN recipes r ON r.id = mp.recipe_id
           WHERE mp.week_start = ? AND mp.day = ?""",
        (week_start, day)
    ).fetchone()

    # estimated_remaining_seconds is the total time left for the whole cook
    # (it already folds in active_timer_remaining_seconds for the current step
    # plus a flat per-step share for the rest) — it's None only when the
    # recipe has no cook_time set, in which case there's nothing to report.
    cook_time_remaining = (cooking["estimated_remaining_seconds"] or 0) if cooking else 0

    return {
        "cooking_active": cooking is not None,
        "cooking_recipe_id": cooking["recipe_id"] if cooking else 0,
        "cooking_recipe_name": cooking["recipe_name"] if cooking else "",
        "cook_time_remaining_seconds": cook_time_remaining,
        "planned_today_recipe_id": planned["recipe_id"] if planned else 0,
        "planned_today_recipe_name": planned["recipe_name"] if planned else "",
        # System-local time (not hardcoded to a timezone) so this always
        # matches whatever wall-clock date planner._today() just used.
        "updated_at": datetime.now().astimezone().isoformat(),
    }
