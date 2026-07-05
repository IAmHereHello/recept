from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlite3 import Connection
from pathlib import Path
from datetime import datetime
import aiofiles
import uuid

from app.database import get_db
from app.models import CookSessionIn, CookSessionOut, RatingIn

router = APIRouter(prefix="/sessions", tags=["sessions"])

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def _fetch_session(conn: Connection, session_id: int) -> dict:
    row = conn.execute("SELECT * FROM cook_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    s = dict(row)
    s["ratings"] = [dict(r) for r in conn.execute(
        "SELECT * FROM ratings WHERE cook_session_id = ?", (session_id,)
    ).fetchall()]
    s["photos"] = [row["file_path"] for row in conn.execute(
        "SELECT file_path FROM photos WHERE cook_session_id = ? ORDER BY uploaded_at", (session_id,)
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
    cooked_at = body.cooked_at or datetime.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO cook_sessions (recipe_id, cooked_at, notes) VALUES (?,?,?)",
        (body.recipe_id, cooked_at, body.notes)
    )
    conn.commit()
    return _fetch_session(conn, cur.lastrowid)


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


@router.post("/{session_id}/photo", response_model=CookSessionOut)
async def upload_photo(session_id: int, file: UploadFile = File(...), conn: Connection = Depends(get_db)):
    _fetch_session(conn, session_id)
    suffix = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    filename = f"{uuid.uuid4()}{suffix}"
    dest = UPLOAD_DIR / filename
    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)
    conn.execute(
        "INSERT INTO photos (cook_session_id, file_path) VALUES (?,?)",
        (session_id, f"/uploads/{filename}")
    )
    conn.commit()
    return _fetch_session(conn, session_id)


@router.get("/{session_id}", response_model=CookSessionOut)
def get_session(session_id: int, conn: Connection = Depends(get_db)):
    return _fetch_session(conn, session_id)
