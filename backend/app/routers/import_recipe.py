import os
import httpx
import anthropic
import json
from fastapi import APIRouter, HTTPException
from app.models import ImportUrlRequest

router = APIRouter(prefix="/import", tags=["import"])

SYSTEM_PROMPT = """You are a recipe extraction assistant.
Given the raw HTML or text of a recipe webpage, extract the recipe and return ONLY valid JSON in this exact shape:
{
  "name": "...",
  "description": "...",
  "cook_time": 30,
  "difficulty": "easy|medium|hard",
  "cuisine_type": "...",
  "is_vegetarian": false,
  "is_vegan": false,
  "ingredients": [
    {"name": "...", "amount": "...", "unit": "...", "sort_order": 0}
  ],
  "steps": [
    {"sort_order": 1, "description": "..."}
  ]
}
cook_time is in minutes as an integer. If you cannot determine a field, use null.
Return only the JSON object, no markdown fences, no explanation."""


@router.post("/")
async def import_from_url(body: ImportUrlRequest):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(body.url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            html = resp.text[:40000]  # cap to avoid token explosion
    except Exception as e:
        raise HTTPException(400, f"Could not fetch URL: {e}")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Extract the recipe from this page:\n\n{html}"}],
    )

    raw = message.content[0].text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(500, "AI returned invalid JSON — try a different URL")

    return data
