import calendar
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlite3 import Connection
from app.database import get_db
from app.models import FreezerItemIn, FreezerItemOut, FreezerConsumeIn, FreezerExpiresIn

router = APIRouter(prefix="/freezer", tags=["freezer"])

DEFAULT_FREEZER_MONTHS = 3


def _today() -> date:
    # Indirection so tests can freeze "today" via monkeypatch.
    return date.today()


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _fetch_freezer_item(conn: Connection, item_id: int) -> dict:
    row = conn.execute(
        """SELECT fi.*, r.name AS recipe_name
           FROM freezer_items fi JOIN recipes r ON r.id = fi.recipe_id
           WHERE fi.id = ?""",
        (item_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Freezer item not found")
    return dict(row)


@router.get("/", response_model=list[FreezerItemOut])
def list_freezer_items(conn: Connection = Depends(get_db)):
    rows = conn.execute(
        """SELECT fi.*, r.name AS recipe_name
           FROM freezer_items fi JOIN recipes r ON r.id = fi.recipe_id
           ORDER BY fi.expires_at ASC"""
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/", response_model=FreezerItemOut, status_code=201)
def create_freezer_item(body: FreezerItemIn, conn: Connection = Depends(get_db)):
    recipe = conn.execute("SELECT freezer_months FROM recipes WHERE id = ?", (body.recipe_id,)).fetchone()
    if not recipe:
        raise HTTPException(404, "Recipe not found")
    frozen_at = date.fromisoformat(body.frozen_at) if body.frozen_at else _today()
    if body.expires_at:
        expires_at = date.fromisoformat(body.expires_at)
    else:
        months = recipe["freezer_months"] or DEFAULT_FREEZER_MONTHS
        expires_at = _add_months(frozen_at, months)
    cur = conn.execute(
        """INSERT INTO freezer_items
           (recipe_id, cook_session_id, portions_total, portions_remaining, frozen_at, expires_at, added_by)
           VALUES (?,?,?,?,?,?,?)""",
        (body.recipe_id, body.cook_session_id, body.portions_total, body.portions_total,
         frozen_at.isoformat(), expires_at.isoformat(), body.added_by)
    )
    conn.commit()
    return _fetch_freezer_item(conn, cur.lastrowid)


@router.post("/{item_id}/consume")
def consume_freezer_item(item_id: int, body: FreezerConsumeIn, conn: Connection = Depends(get_db)):
    item = _fetch_freezer_item(conn, item_id)
    remaining = item["portions_remaining"] - body.portions
    if remaining < 0:
        raise HTTPException(400, "Cannot consume more portions than remain")
    if remaining == 0:
        conn.execute("DELETE FROM freezer_items WHERE id = ?", (item_id,))
        conn.commit()
        return Response(status_code=204)
    conn.execute("UPDATE freezer_items SET portions_remaining = ? WHERE id = ?", (remaining, item_id))
    conn.commit()
    return _fetch_freezer_item(conn, item_id)


@router.post("/{item_id}/expires", response_model=FreezerItemOut)
def set_freezer_item_expiry(item_id: int, body: FreezerExpiresIn, conn: Connection = Depends(get_db)):
    _fetch_freezer_item(conn, item_id)
    conn.execute("UPDATE freezer_items SET expires_at = ? WHERE id = ?", (body.expires_at, item_id))
    conn.commit()
    return _fetch_freezer_item(conn, item_id)


@router.delete("/{item_id}", status_code=204)
def delete_freezer_item(item_id: int, conn: Connection = Depends(get_db)):
    _fetch_freezer_item(conn, item_id)
    conn.execute("DELETE FROM freezer_items WHERE id = ?", (item_id,))
    conn.commit()
