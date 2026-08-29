import re
import json
import logging

import httpx
from fastapi import APIRouter, HTTPException
from app.ai import complete_json, get_api_key
from app.models import ImportUrlRequest

router = APIRouter(prefix="/import", tags=["import"])
logger = logging.getLogger("app.import")

# Fallback only — used when the page has no schema.org Recipe JSON-LD. Big
# recipe sites (AH, NYT, most WordPress food blogs) render the recipe body
# client-side, so the raw HTML is mostly framework noise; the structured
# JSON-LD block is the reliable source and is handled separately below.
HTML_CAP = 60000

SYSTEM_PROMPT = """You are a recipe extraction assistant.
You are given either schema.org Recipe JSON-LD or the raw HTML/text of a recipe webpage.
Extract the recipe and return ONLY valid JSON in this exact shape:
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
cook_time is in minutes as an integer (convert ISO 8601 durations like PT40M).
Split each ingredient string into amount (number/fraction as text), unit (g, ml, el, tl, teen, blik, snufje, ...), and the bare ingredient name.
difficulty is your judgement from the steps if the source doesn't state it.
Keep step text in the source language. If you cannot determine a field, use null.
Return only the JSON object, no markdown fences, no explanation."""


def _is_recipe(node: dict) -> bool:
    t = node.get("@type")
    return t == "Recipe" or (isinstance(t, list) and "Recipe" in t)


def _find_recipe_jsonld(html: str) -> dict | None:
    """Return the first schema.org Recipe object embedded in the page, if any.

    Handles multiple <script type="application/ld+json"> blocks, top-level
    arrays, and "@graph" wrappers. Parsed from the full HTML, not the
    token-capped slice, since these blocks often sit deep in the document.
    """
    blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    for block in blocks:
        try:
            parsed = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        candidates = parsed if isinstance(parsed, list) else [parsed]
        for node in candidates:
            if not isinstance(node, dict):
                continue
            if _is_recipe(node):
                return node
            for sub in node.get("@graph", []) or []:
                if isinstance(sub, dict) and _is_recipe(sub):
                    return sub
    return None


@router.post("/")
async def import_from_url(body: ImportUrlRequest):
    get_api_key()  # fail fast with 500 before spending a network fetch

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http_client:
            resp = await http_client.get(body.url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            full_html = resp.text
    except Exception as e:
        raise HTTPException(400, f"Could not fetch URL: {e}")

    recipe_ld = _find_recipe_jsonld(full_html)
    if recipe_ld is not None:
        logger.info("Found Recipe JSON-LD for %s", body.url)
        user_content = (
            "Here is the page's schema.org Recipe JSON-LD:\n\n"
            + json.dumps(recipe_ld, ensure_ascii=False)
        )
    else:
        logger.info("No Recipe JSON-LD for %s — falling back to raw HTML", body.url)
        user_content = f"Extract the recipe from this page HTML:\n\n{full_html[:HTML_CAP]}"

    return await complete_json(
        SYSTEM_PROMPT, user_content,
        context=f"import {body.url}", max_tokens=8192,
        bad_json_message="AI kon geen recept uit deze pagina halen — probeer een andere URL.",
    )
