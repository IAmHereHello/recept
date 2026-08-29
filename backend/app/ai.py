"""Shared Anthropic helper — one place for the model id, JSON extraction, and
the "single-turn call that must return one JSON object" error handling used by
both recipe import and healthiness scoring.
"""
import os
import re
import json
import logging

import anthropic
from fastapi import HTTPException

logger = logging.getLogger("app.ai")

MODEL = "claude-haiku-4-5-20251001"


def get_api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")
    return key


def extract_json(raw: str) -> str:
    """Best-effort pull the JSON object out of the model's reply.

    Tolerates a ```json ... ``` fence or stray prose around the object even
    though our prompts ask for neither.
    """
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            text = text[start:end + 1]
    return text


async def complete_json(
    system: str,
    user_content: str,
    *,
    context: str,
    max_tokens: int = 2048,
    bad_json_message: str = "AI gaf een ongeldig antwoord — probeer het opnieuw.",
) -> dict:
    """Run one Haiku turn that must return a single JSON object.

    Raises HTTPException(502) with a Dutch message on any AI-side failure
    (API error, truncation, empty reply, unparseable output). `context` is a
    short label for the server logs.
    """
    client = anthropic.AsyncAnthropic(api_key=get_api_key())
    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.APIError as e:
        logger.exception("Anthropic call failed (%s)", context)
        raise HTTPException(502, f"AI-aanvraag mislukt: {e}")

    stop_reason = getattr(message, "stop_reason", None)
    raw = "".join(b.text for b in message.content if hasattr(b, "text")).strip()

    if stop_reason == "max_tokens":
        logger.warning("AI hit max_tokens (%s)", context)
        raise HTTPException(502, "AI-antwoord te lang — probeer het opnieuw.")
    if not raw:
        logger.warning("Empty AI response (%s, stop_reason=%s)", context, stop_reason)
        raise HTTPException(502, "AI gaf een leeg antwoord — probeer het opnieuw.")
    try:
        return json.loads(extract_json(raw))
    except json.JSONDecodeError:
        logger.warning("Non-JSON AI response (%s):\n%s", context, raw[:2000])
        raise HTTPException(502, bad_json_message)
