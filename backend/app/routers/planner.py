from fastapi import APIRouter, Depends, HTTPException
from sqlite3 import Connection
from datetime import date, timedelta
from typing import Optional
from app.database import get_db
from app.health import grade as health_grade
from app.models import MealPlanEntry, GroceryRequest, SideDishIn, SuggestIn

router = APIRouter(prefix="/plan", tags=["planner"])

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
COOLDOWN_DAYS = 14
FREEZER_BOOST_WINDOW_DAYS = 14

# Healthiness is a gentle nudge, not a gate: a 100/100 recipe gains +0.75 and a
# 0/100 loses 0.75, versus the 1.5 cooldown penalty and the 1-5 rating base.
# Unscored recipes (health_score IS NULL) are unaffected.
HEALTH_WEIGHT = 0.75


def _week_start(week_start: str) -> str:
    """Normalize to Monday of the given week."""
    d = date.fromisoformat(week_start)
    return (d - timedelta(days=d.weekday())).isoformat()


def _today() -> date:
    # Indirection so tests can freeze "today" via monkeypatch.
    return date.today()


def _day_date(week_start: str, day: str) -> date:
    return date.fromisoformat(week_start) + timedelta(days=DAYS.index(day))


def _recent_planned_dates(conn: Connection, before: date, cutoff: date) -> dict[int, str]:
    """recipe_id -> most recent meal_plan date that is on/after `cutoff` and
    strictly before `before`. A dish that was on the menu recently is treated
    like a real cook session for cooldown scoring — you presumably ate it.
    """
    out: dict[int, str] = {}
    for row in conn.execute(
        "SELECT recipe_id, week_start, day FROM meal_plan WHERE recipe_id IS NOT NULL"
    ).fetchall():
        d = _day_date(row["week_start"], row["day"])
        if cutoff <= d < before:
            iso = d.isoformat()
            if row["recipe_id"] not in out or iso > out[row["recipe_id"]]:
                out[row["recipe_id"]] = iso
    return out


def _score_recipes(conn: Connection, week_start: str) -> list[dict]:
    ws_date = date.fromisoformat(week_start)
    cutoff_date = ws_date - timedelta(days=COOLDOWN_DAYS)
    cutoff = cutoff_date.isoformat()
    recent_planned = _recent_planned_dates(conn, before=ws_date, cutoff=cutoff_date)
    rows = conn.execute("""
        SELECT
            r.id,
            r.name,
            r.is_vegetarian,
            r.is_vegan,
            r.health_score,
            AVG(rt.stars) as avg_stars,
            COUNT(DISTINCT rt.id) as rating_count,
            MAX(cs.cooked_at) as last_cooked
        FROM recipes r
        LEFT JOIN cook_sessions cs ON cs.recipe_id = r.id
        LEFT JOIN ratings rt ON rt.cook_session_id = cs.id
        WHERE r.is_side_dish = 0 AND r.is_baking = 0
        GROUP BY r.id
    """).fetchall()

    scored = []
    for row in rows:
        r = dict(row)
        score = r["avg_stars"] or 3.0
        if r["rating_count"] == 0:
            score += 0.5  # boost unrated (try new dishes)
        last_activity = max(
            (v for v in (r["last_cooked"], recent_planned.get(r["id"])) if v),
            default=None,
        )
        if last_activity and last_activity >= cutoff:
            score -= 1.5  # soft cooldown penalty (real cook OR a recent plan entry)
        if r["health_score"] is not None:
            score += ((r["health_score"] - 50) / 50) * HEALTH_WEIGHT  # gentle health nudge
        r["health_grade"] = health_grade(r["health_score"])
        r["score"] = score
        scored.append(r)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def sync_cooked_meal(conn: Connection, recipe_id: int, when: date) -> Optional[dict]:
    """Reflect a just-cooked or retroactively-logged meal onto that day's plan.

    - locked day, or the day already holds this same recipe: no-op -> None
    - empty day: fill it -> None
    - a *different* unlocked meal already planned: leave it, return a conflict
      dict so the caller can ask the user whether to overwrite
    """
    ws = (when - timedelta(days=when.weekday())).isoformat()
    day = DAYS[when.weekday()]
    row = conn.execute(
        "SELECT recipe_id, locked FROM meal_plan WHERE week_start=? AND day=?", (ws, day)
    ).fetchone()
    if row and row["locked"]:
        return None
    if row and row["recipe_id"] == recipe_id:
        return None
    if row and row["recipe_id"] is not None:
        def _name(rid):
            hit = conn.execute("SELECT name FROM recipes WHERE id=?", (rid,)).fetchone()
            return hit["name"] if hit else None
        return {
            "week_start": ws, "day": day,
            "existing_recipe_id": row["recipe_id"], "existing_recipe_name": _name(row["recipe_id"]),
            "cooked_recipe_id": recipe_id, "cooked_recipe_name": _name(recipe_id),
        }
    conn.execute(
        """INSERT INTO meal_plan (week_start, day, recipe_id, locked, freezer_item_id)
           VALUES (?,?,?,0,NULL)
           ON CONFLICT(week_start, day) DO UPDATE SET recipe_id=excluded.recipe_id""",
        (ws, day, recipe_id),
    )
    return None


def _freezer_candidates(conn: Connection, week_start: str) -> list[dict]:
    """Freezer batches within FREEZER_BOOST_WINDOW_DAYS of expiry (or already
    overdue), soonest first. Deliberately bypasses _score_recipes/cooldown:
    this answers "eat existing leftovers", not "should I cook this again".
    """
    horizon = (date.fromisoformat(week_start) + timedelta(days=FREEZER_BOOST_WINDOW_DAYS)).isoformat()
    rows = conn.execute(
        """SELECT fi.id AS freezer_item_id, fi.recipe_id, fi.portions_remaining, fi.expires_at,
                  r.name, r.is_vegetarian
           FROM freezer_items fi
           JOIN recipes r ON r.id = fi.recipe_id
           WHERE fi.expires_at <= ? AND r.is_side_dish = 0 AND r.is_baking = 0
           ORDER BY fi.expires_at ASC""",
        (horizon,)
    ).fetchall()
    return [dict(r) for r in rows]


def _sides_by_day(conn: Connection, week_start: str) -> dict[str, list]:
    rows = conn.execute(
        """SELECT mps.day, mps.recipe_id, r.name AS recipe_name
           FROM meal_plan_sides mps
           JOIN recipes r ON r.id = mps.recipe_id
           WHERE mps.week_start = ?
           ORDER BY mps.id""",
        (week_start,)
    ).fetchall()
    by_day: dict[str, list] = {day: [] for day in DAYS}
    for row in rows:
        by_day[row["day"]].append({"recipe_id": row["recipe_id"], "recipe_name": row["recipe_name"]})
    return by_day


def _attach_freezer_info(conn: Connection, plan: dict) -> None:
    for entry in plan.values():
        if entry and entry.get("freezer_item_id"):
            fi = conn.execute(
                "SELECT portions_remaining, portions_total, expires_at FROM freezer_items WHERE id = ?",
                (entry["freezer_item_id"],)
            ).fetchone()
            entry["freezer"] = dict(fi) if fi else None


@router.get("/{week_start}")
def get_week(week_start: str, conn: Connection = Depends(get_db)):
    ws = _week_start(week_start)
    rows = conn.execute(
        "SELECT * FROM meal_plan WHERE week_start = ? ORDER BY id", (ws,)
    ).fetchall()
    plan = {row["day"]: dict(row) for row in rows}
    sides = _sides_by_day(conn, ws)
    result = {}
    for day in DAYS:
        entry = plan.get(day)
        if entry is None and not sides[day]:
            result[day] = None
        else:
            result[day] = {**(entry or {"week_start": ws, "day": day, "recipe_id": None, "locked": False, "freezer_item_id": None}), "sides": sides[day]}
    _attach_freezer_info(conn, result)
    return result


def _week_plan_state(conn: Connection, ws: str):
    rows = conn.execute(
        "SELECT day, recipe_id, locked FROM meal_plan WHERE week_start = ?", (ws,)
    ).fetchall()
    locked_days = {r["day"] for r in rows if r["locked"]}
    filled_days = {r["day"] for r in rows if r["recipe_id"] is not None}
    # Everything already on this week's menu (locked or not) is off the table —
    # you don't want the same dish suggested twice in one week.
    planned_recipe_ids = {r["recipe_id"] for r in rows if r["recipe_id"] is not None}
    return locked_days, filled_days, planned_recipe_ids


@router.post("/suggest/{week_start}")
def suggest_week(
    week_start: str,
    vegetarian_only: bool = False,
    body: Optional[SuggestIn] = None,
    conn: Connection = Depends(get_db),
):
    ws = _week_start(week_start)
    exclude_ids = set(body.exclude_recipe_ids) if body else set()
    locked_days, filled_days, planned_recipe_ids = _week_plan_state(conn, ws)
    # Only suggest for days that are neither locked nor already filled, so
    # re-rolling after applying a few suggestions only touches what's still open.
    open_days = [d for d in DAYS if d not in locked_days and d not in filled_days]

    suggestions: dict = {}
    used_ids: set = set(exclude_ids)  # rejected recipes never come back this round

    # Priority pass: freezer batches nearing expiry get first claim on open
    # days (soonest-expiring -> earliest open day), ahead of normal scoring.
    freezer_candidates = _freezer_candidates(conn, ws)
    if vegetarian_only:
        freezer_candidates = [f for f in freezer_candidates if f["is_vegetarian"]]

    fc_idx = 0
    for day in open_days:
        while fc_idx < len(freezer_candidates) and (
            freezer_candidates[fc_idx]["recipe_id"] in planned_recipe_ids
            or freezer_candidates[fc_idx]["recipe_id"] in used_ids
        ):
            fc_idx += 1
        if fc_idx < len(freezer_candidates):
            f = freezer_candidates[fc_idx]
            suggestions[day] = {
                "id": f["recipe_id"], "name": f["name"],
                "from_freezer": True,
                "freezer_item_id": f["freezer_item_id"],
                "portions_remaining": f["portions_remaining"],
            }
            used_ids.add(f["recipe_id"])
            fc_idx += 1

    scored = _score_recipes(conn, ws)
    if vegetarian_only:
        scored = [r for r in scored if r["is_vegetarian"]]
    available = [r for r in scored if r["id"] not in planned_recipe_ids and r["id"] not in used_ids]

    idx = 0
    for day in open_days:
        if day in suggestions:
            continue
        while idx < len(available) and available[idx]["id"] in used_ids:
            idx += 1
        if idx < len(available):
            suggestions[day] = {**available[idx], "from_freezer": False}
            used_ids.add(available[idx]["id"])
            idx += 1
        else:
            suggestions[day] = None
    return suggestions


@router.post("/suggest/{week_start}/{day}")
def suggest_day(
    week_start: str,
    day: str,
    vegetarian_only: bool = False,
    body: Optional[SuggestIn] = None,
    conn: Connection = Depends(get_db),
):
    """Re-roll a single day — the best-scoring recipe not already on this
    week's menu and not in the caller's reject list. Normal scoring only
    (freezer batches only surface via the full 'Suggesties' run)."""
    ws = _week_start(week_start)
    if day not in DAYS:
        raise HTTPException(404, "Unknown day")
    exclude_ids = set(body.exclude_recipe_ids) if body else set()
    _, _, planned_recipe_ids = _week_plan_state(conn, ws)

    scored = _score_recipes(conn, ws)
    if vegetarian_only:
        scored = [r for r in scored if r["is_vegetarian"]]
    for r in scored:
        if r["id"] in planned_recipe_ids or r["id"] in exclude_ids:
            continue
        return {**r, "from_freezer": False}
    return None


@router.put("/{week_start}/{day}")
def set_day(week_start: str, day: str, body: MealPlanEntry, conn: Connection = Depends(get_db)):
    ws = _week_start(week_start)
    if body.recipe_id is not None:
        recipe = conn.execute(
            "SELECT is_side_dish, is_baking FROM recipes WHERE id = ?", (body.recipe_id,)
        ).fetchone()
        if recipe and (recipe["is_side_dish"] or recipe["is_baking"]):
            raise HTTPException(400, "This recipe is a side dish or baking recipe and cannot be used as a main dish")
    conn.execute(
        """INSERT INTO meal_plan (week_start, day, recipe_id, locked, freezer_item_id)
           VALUES (?,?,?,?,?)
           ON CONFLICT(week_start, day) DO UPDATE SET recipe_id=excluded.recipe_id, locked=excluded.locked, freezer_item_id=excluded.freezer_item_id""",
        (ws, day, body.recipe_id, int(body.locked), body.freezer_item_id)
    )
    conn.commit()
    return {"week_start": ws, "day": day, "recipe_id": body.recipe_id, "locked": body.locked, "freezer_item_id": body.freezer_item_id}


@router.delete("/{week_start}/{day}", status_code=204)
def clear_day(week_start: str, day: str, conn: Connection = Depends(get_db)):
    ws = _week_start(week_start)
    conn.execute("DELETE FROM meal_plan WHERE week_start = ? AND day = ?", (ws, day))
    conn.execute("DELETE FROM meal_plan_sides WHERE week_start = ? AND day = ?", (ws, day))
    conn.commit()


@router.post("/{week_start}/{day}/sides", status_code=201)
def add_side_dish(week_start: str, day: str, body: SideDishIn, conn: Connection = Depends(get_db)):
    ws = _week_start(week_start)
    conn.execute(
        "INSERT OR IGNORE INTO meal_plan_sides (week_start, day, recipe_id) VALUES (?,?,?)",
        (ws, day, body.recipe_id)
    )
    conn.commit()
    recipe = conn.execute("SELECT name FROM recipes WHERE id = ?", (body.recipe_id,)).fetchone()
    return {"week_start": ws, "day": day, "recipe_id": body.recipe_id, "recipe_name": recipe["name"] if recipe else None}


@router.delete("/{week_start}/{day}/sides/{recipe_id}", status_code=204)
def remove_side_dish(week_start: str, day: str, recipe_id: int, conn: Connection = Depends(get_db)):
    ws = _week_start(week_start)
    conn.execute(
        "DELETE FROM meal_plan_sides WHERE week_start = ? AND day = ? AND recipe_id = ?",
        (ws, day, recipe_id)
    )
    conn.commit()


@router.post("/grocery")
def grocery_list(body: GroceryRequest, conn: Connection = Depends(get_db)):
    ws = _week_start(body.week_start)
    today = _today()
    plan_rows = conn.execute(
        "SELECT day, recipe_id FROM meal_plan WHERE week_start = ? AND recipe_id IS NOT NULL", (ws,)
    ).fetchall()
    plan_rows = [row for row in plan_rows if _day_date(ws, row["day"]) >= today]

    side_rows = conn.execute(
        "SELECT day, recipe_id FROM meal_plan_sides WHERE week_start = ?", (ws,)
    ).fetchall()
    side_rows = [row for row in side_rows if _day_date(ws, row["day"]) >= today]

    grocery: dict[str, list] = {}  # recipe_name -> ingredients
    for row in [*plan_rows, *side_rows]:
        recipe = conn.execute("SELECT name FROM recipes WHERE id = ?", (row["recipe_id"],)).fetchone()
        if not recipe:
            continue
        ingredients = conn.execute(
            "SELECT name, amount, unit FROM ingredients WHERE recipe_id = ? ORDER BY sort_order",
            (row["recipe_id"],)
        ).fetchall()
        grocery[recipe["name"]] = [dict(i) for i in ingredients]

    return {"week_start": ws, "by_recipe": grocery}
