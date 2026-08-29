import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlite3 import Connection
from app.ai import complete_json
from app.config import UPLOAD_DIR
from app.database import get_db
from app.health import grade as health_grade
from app.models import RecipeIn, RecipeOut

router = APIRouter(prefix="/recipes", tags=["recipes"])
logger = logging.getLogger("app.recipes")

HEALTH_SYSTEM = """Je bent een voedingsdeskundige. Beoordeel hoe gezond een recept is als doordeweekse avondmaaltijd.
Weeg mee: aandeel groente/fruit/peulvruchten, volkoren vs. wit meel, mager vs. vet/bewerkt vlees,
bereidingswijze (bakken/stomen vs. frituren), toegevoegde suiker, zout, verzadigd vet (room, boter, kaas),
en de balans van het bord.
Antwoord ALLEEN met JSON in exact deze vorm:
{"score": <geheel getal 0-100, 100 = zeer gezond>, "rationale": "<2-3 zinnen NL: de belangrijkste plus- en minpunten>", "tip": "<1 concrete tip om dit gerecht gezonder te maken>"}
Geen markdown, geen tekst buiten de JSON."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _score_health(recipe: dict) -> dict:
    """Ask Haiku for a 0-100 healthiness score + rationale + tip for one recipe."""
    ingredients = "\n".join(
        f"- {(i['amount'] or '')} {(i['unit'] or '')} {i['name']}".strip()
        for i in recipe["ingredients"]
    ) or "(geen ingrediënten opgegeven)"
    steps = "\n".join(
        f"{n}. {s['description']}" for n, s in enumerate(recipe["steps"], 1)
    ) or "(geen stappen opgegeven)"
    user = (
        f"Recept: {recipe['name']}\n"
        f"Porties: {recipe.get('portions') or 'onbekend'}\n\n"
        f"Ingrediënten:\n{ingredients}\n\n"
        f"Bereiding:\n{steps}"
    )
    data = await complete_json(
        HEALTH_SYSTEM, user,
        context="health-score", max_tokens=1024,
        bad_json_message="AI kon de gezondheid van dit recept niet bepalen — probeer het opnieuw.",
    )
    score = data.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 100:
        raise HTTPException(502, "AI gaf een ongeldige gezondheidsscore terug.")
    return {
        "score": int(round(score)),
        "rationale": (data.get("rationale") or "").strip() or None,
        "tip": (data.get("tip") or "").strip() or None,
    }


def _save_health(conn: Connection, recipe_id: int, result: dict) -> None:
    conn.execute(
        "UPDATE recipes SET health_score=?, health_rationale=?, health_tip=?, health_scored_at=? WHERE id=?",
        (result["score"], result["rationale"], result["tip"], _now(), recipe_id),
    )


def _fetch_recipe(conn: Connection, recipe_id: int) -> dict:
    row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Recipe not found")
    r = dict(row)
    r["ingredients"] = [dict(i) for i in conn.execute(
        "SELECT * FROM ingredients WHERE recipe_id = ? ORDER BY sort_order", (recipe_id,)
    ).fetchall()]
    r["steps"] = [dict(s) for s in conn.execute(
        "SELECT * FROM steps WHERE recipe_id = ? ORDER BY track, sort_order", (recipe_id,)
    ).fetchall()]
    rating_row = conn.execute(
        "SELECT AVG(r.stars) as avg FROM ratings r JOIN cook_sessions cs ON r.cook_session_id = cs.id WHERE cs.recipe_id = ?",
        (recipe_id,)
    ).fetchone()
    r["avg_rating"] = round(rating_row["avg"], 1) if rating_row["avg"] else None
    last = conn.execute(
        "SELECT cooked_at FROM cook_sessions WHERE recipe_id = ? ORDER BY cooked_at DESC LIMIT 1",
        (recipe_id,)
    ).fetchone()
    r["last_cooked"] = last["cooked_at"] if last else None
    photo = conn.execute(
        """SELECT p.file_path FROM photos p
           JOIN cook_sessions cs ON p.cook_session_id = cs.id
           WHERE cs.recipe_id = ? ORDER BY p.uploaded_at DESC LIMIT 1""",
        (recipe_id,)
    ).fetchone()
    r["cover_photo"] = photo["file_path"] if photo else None
    r["health_grade"] = health_grade(r.get("health_score"))
    return r


@router.get("/", response_model=list[RecipeOut])
def list_recipes(
    cuisine: str | None = None,
    vegetarian: bool | None = None,
    vegan: bool | None = None,
    difficulty: str | None = None,
    side_dish: bool | None = None,
    baking: bool | None = None,
    freezable: bool | None = None,
    conn: Connection = Depends(get_db),
):
    query = "SELECT id FROM recipes WHERE 1=1"
    params: list = []
    if cuisine:
        query += " AND cuisine_type = ?"
        params.append(cuisine)
    if vegetarian is not None:
        query += " AND is_vegetarian = ?"
        params.append(1 if vegetarian else 0)
    if vegan is not None:
        query += " AND is_vegan = ?"
        params.append(1 if vegan else 0)
    if difficulty:
        query += " AND difficulty = ?"
        params.append(difficulty)
    if side_dish is not None:
        query += " AND is_side_dish = ?"
        params.append(1 if side_dish else 0)
    if baking is not None:
        query += " AND is_baking = ?"
        params.append(1 if baking else 0)
    if freezable is not None:
        query += " AND is_freezable = ?"
        params.append(1 if freezable else 0)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [_fetch_recipe(conn, row["id"]) for row in rows]


@router.post("/", response_model=RecipeOut, status_code=201)
def create_recipe(body: RecipeIn, conn: Connection = Depends(get_db)):
    cur = conn.execute(
        "INSERT INTO recipes (name, description, cook_time, difficulty, cuisine_type, is_vegetarian, is_vegan, is_side_dish, is_baking, portions, is_freezable, freezer_months) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (body.name, body.description, body.cook_time, body.difficulty, body.cuisine_type, int(body.is_vegetarian), int(body.is_vegan), int(body.is_side_dish), int(body.is_baking), body.portions, int(body.is_freezable), body.freezer_months)
    )
    recipe_id = cur.lastrowid
    for ing in body.ingredients:
        conn.execute(
            "INSERT INTO ingredients (recipe_id, name, amount, unit, sort_order) VALUES (?,?,?,?,?)",
            (recipe_id, ing.name, ing.amount, ing.unit, ing.sort_order)
        )
    for step in body.steps:
        conn.execute(
            "INSERT INTO steps (recipe_id, sort_order, description, wait_time_minutes, track) VALUES (?,?,?,?,?)",
            (recipe_id, step.sort_order, step.description, step.wait_time_minutes, step.track.value)
        )
    conn.commit()
    return _fetch_recipe(conn, recipe_id)


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, conn: Connection = Depends(get_db)):
    return _fetch_recipe(conn, recipe_id)


@router.put("/{recipe_id}", response_model=RecipeOut)
def update_recipe(recipe_id: int, body: RecipeIn, conn: Connection = Depends(get_db)):
    _fetch_recipe(conn, recipe_id)
    conn.execute(
        "UPDATE recipes SET name=?, description=?, cook_time=?, difficulty=?, cuisine_type=?, is_vegetarian=?, is_vegan=?, is_side_dish=?, is_baking=?, portions=?, is_freezable=?, freezer_months=? WHERE id=?",
        (body.name, body.description, body.cook_time, body.difficulty, body.cuisine_type, int(body.is_vegetarian), int(body.is_vegan), int(body.is_side_dish), int(body.is_baking), body.portions, int(body.is_freezable), body.freezer_months, recipe_id)
    )
    conn.execute("DELETE FROM ingredients WHERE recipe_id = ?", (recipe_id,))
    conn.execute("DELETE FROM steps WHERE recipe_id = ?", (recipe_id,))
    for ing in body.ingredients:
        conn.execute(
            "INSERT INTO ingredients (recipe_id, name, amount, unit, sort_order) VALUES (?,?,?,?,?)",
            (recipe_id, ing.name, ing.amount, ing.unit, ing.sort_order)
        )
    for step in body.steps:
        conn.execute(
            "INSERT INTO steps (recipe_id, sort_order, description, wait_time_minutes, track) VALUES (?,?,?,?,?)",
            (recipe_id, step.sort_order, step.description, step.wait_time_minutes, step.track.value)
        )
    conn.commit()
    return _fetch_recipe(conn, recipe_id)


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, conn: Connection = Depends(get_db)):
    _fetch_recipe(conn, recipe_id)
    photo_rows = conn.execute(
        """SELECT p.file_path FROM photos p
           JOIN cook_sessions cs ON p.cook_session_id = cs.id
           WHERE cs.recipe_id = ?""",
        (recipe_id,)
    ).fetchall()
    conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    conn.commit()
    # photos cascade-delete at the DB level, but the actual files on disk don't
    # get removed automatically — clean those up now that the rows are gone.
    for row in photo_rows:
        (UPLOAD_DIR / Path(row["file_path"]).name).unlink(missing_ok=True)


@router.post("/health-review/bulk")
async def health_review_bulk(conn: Connection = Depends(get_db)):
    """Score every recipe that has no healthiness score yet, 5 at a time."""
    ids = [row["id"] for row in conn.execute(
        "SELECT id FROM recipes WHERE health_score IS NULL ORDER BY id"
    ).fetchall()]
    scored = failed = 0
    for start in range(0, len(ids), 5):
        chunk = ids[start:start + 5]
        recipes = [_fetch_recipe(conn, rid) for rid in chunk]
        results = await asyncio.gather(
            *(_score_health(r) for r in recipes), return_exceptions=True
        )
        for rid, result in zip(chunk, results):
            if isinstance(result, Exception):
                failed += 1
                logger.warning("bulk health-review failed for recipe %s: %s", rid, result)
                continue
            _save_health(conn, rid, result)
            scored += 1
        conn.commit()
    return {"scored": scored, "failed": failed, "total": len(ids)}


@router.post("/{recipe_id}/health-review", response_model=RecipeOut)
async def health_review(recipe_id: int, conn: Connection = Depends(get_db)):
    """(Re)score one recipe's healthiness via Haiku."""
    recipe = _fetch_recipe(conn, recipe_id)
    _save_health(conn, recipe_id, await _score_health(recipe))
    conn.commit()
    return _fetch_recipe(conn, recipe_id)
