from fastapi import APIRouter, Depends, HTTPException
from sqlite3 import Connection
from datetime import date, timedelta
from app.database import get_db
from app.models import MealPlanEntry, GroceryRequest, SideDishIn

router = APIRouter(prefix="/plan", tags=["planner"])

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
COOLDOWN_DAYS = 14


def _week_start(week_start: str) -> str:
    """Normalize to Monday of the given week."""
    d = date.fromisoformat(week_start)
    return (d - timedelta(days=d.weekday())).isoformat()


def _today() -> date:
    # Indirection so tests can freeze "today" via monkeypatch.
    return date.today()


def _day_date(week_start: str, day: str) -> date:
    return date.fromisoformat(week_start) + timedelta(days=DAYS.index(day))


def _score_recipes(conn: Connection, week_start: str) -> list[dict]:
    cutoff = (date.fromisoformat(week_start) - timedelta(days=COOLDOWN_DAYS)).isoformat()
    rows = conn.execute("""
        SELECT
            r.id,
            r.name,
            r.is_vegetarian,
            r.is_vegan,
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
        if r["last_cooked"] and r["last_cooked"] >= cutoff:
            score -= 1.5  # soft cooldown penalty
        r["score"] = score
        scored.append(r)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


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
            result[day] = {**(entry or {"week_start": ws, "day": day, "recipe_id": None, "locked": False}), "sides": sides[day]}
    return result


@router.post("/suggest/{week_start}")
def suggest_week(week_start: str, vegetarian_only: bool = False, conn: Connection = Depends(get_db)):
    ws = _week_start(week_start)
    locked = conn.execute(
        "SELECT day, recipe_id FROM meal_plan WHERE week_start = ? AND locked = 1", (ws,)
    ).fetchall()
    locked_days = {row["day"] for row in locked}
    locked_recipe_ids = {row["recipe_id"] for row in locked}

    scored = _score_recipes(conn, ws)
    if vegetarian_only:
        scored = [r for r in scored if r["is_vegetarian"]]

    available = [r for r in scored if r["id"] not in locked_recipe_ids]
    suggestions = {}
    used_ids: set = set()
    idx = 0
    for day in DAYS:
        if day in locked_days:
            continue
        while idx < len(available) and available[idx]["id"] in used_ids:
            idx += 1
        if idx < len(available):
            suggestions[day] = available[idx]
            used_ids.add(available[idx]["id"])
            idx += 1
        else:
            suggestions[day] = None
    return suggestions


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
        """INSERT INTO meal_plan (week_start, day, recipe_id, locked)
           VALUES (?,?,?,?)
           ON CONFLICT(week_start, day) DO UPDATE SET recipe_id=excluded.recipe_id, locked=excluded.locked""",
        (ws, day, body.recipe_id, int(body.locked))
    )
    conn.commit()
    return {"week_start": ws, "day": day, "recipe_id": body.recipe_id, "locked": body.locked}


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
