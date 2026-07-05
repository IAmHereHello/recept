from fastapi import APIRouter, Depends, HTTPException
from sqlite3 import Connection
from app.database import get_db
from app.models import RecipeIn, RecipeOut

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _fetch_recipe(conn: Connection, recipe_id: int) -> dict:
    row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Recipe not found")
    r = dict(row)
    r["ingredients"] = [dict(i) for i in conn.execute(
        "SELECT * FROM ingredients WHERE recipe_id = ? ORDER BY sort_order", (recipe_id,)
    ).fetchall()]
    r["steps"] = [dict(s) for s in conn.execute(
        "SELECT * FROM steps WHERE recipe_id = ? ORDER BY sort_order", (recipe_id,)
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
    return r


@router.get("/", response_model=list[RecipeOut])
def list_recipes(
    cuisine: str | None = None,
    vegetarian: bool | None = None,
    vegan: bool | None = None,
    difficulty: str | None = None,
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
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [_fetch_recipe(conn, row["id"]) for row in rows]


@router.post("/", response_model=RecipeOut, status_code=201)
def create_recipe(body: RecipeIn, conn: Connection = Depends(get_db)):
    cur = conn.execute(
        "INSERT INTO recipes (name, description, cook_time, difficulty, cuisine_type, is_vegetarian, is_vegan) VALUES (?,?,?,?,?,?,?)",
        (body.name, body.description, body.cook_time, body.difficulty, body.cuisine_type, int(body.is_vegetarian), int(body.is_vegan))
    )
    recipe_id = cur.lastrowid
    for ing in body.ingredients:
        conn.execute(
            "INSERT INTO ingredients (recipe_id, name, amount, unit, sort_order) VALUES (?,?,?,?,?)",
            (recipe_id, ing.name, ing.amount, ing.unit, ing.sort_order)
        )
    for step in body.steps:
        conn.execute(
            "INSERT INTO steps (recipe_id, sort_order, description) VALUES (?,?,?)",
            (recipe_id, step.sort_order, step.description)
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
        "UPDATE recipes SET name=?, description=?, cook_time=?, difficulty=?, cuisine_type=?, is_vegetarian=?, is_vegan=? WHERE id=?",
        (body.name, body.description, body.cook_time, body.difficulty, body.cuisine_type, int(body.is_vegetarian), int(body.is_vegan), recipe_id)
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
            "INSERT INTO steps (recipe_id, sort_order, description) VALUES (?,?,?)",
            (recipe_id, step.sort_order, step.description)
        )
    conn.commit()
    return _fetch_recipe(conn, recipe_id)


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, conn: Connection = Depends(get_db)):
    _fetch_recipe(conn, recipe_id)
    conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    conn.commit()
