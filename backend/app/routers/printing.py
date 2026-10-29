import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlite3 import Connection
from app import printing
from app.database import get_db

router = APIRouter(tags=["printing"])


@router.get("/print/status")
def print_status():
    """Lets the frontend choose between Pi printing and the browser dialog."""
    name = printing.printer_name()
    return {"enabled": name is not None, "printer": name}


@router.post("/recipes/{recipe_id}/print")
async def print_recipe(recipe_id: int, conn: Connection = Depends(get_db)):
    if not conn.execute("SELECT 1 FROM recipes WHERE id=?", (recipe_id,)).fetchone():
        raise HTTPException(404, "Recipe not found")
    if not printing.printer_name():
        raise HTTPException(503, "Er is geen printer ingesteld op de Pi.")
    try:
        job = await asyncio.to_thread(printing.print_recipe, recipe_id)
    except printing.PrintError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "job": job}
