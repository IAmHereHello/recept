"""Combine ingredients from several recipes into one shopping list.

Ingredients are grouped by name (case- and whitespace-insensitive). Within a
group, numeric amounts in compatible units are summed (kg/g and l/dl/cl/ml are
converted to a common base); anything that can't be summed, like "snufje" or a
range such as "2-3", is kept as its own part of the quantity.
"""
import re
from fractions import Fraction

# unit alias -> (canonical unit, factor to that unit)
_UNITS: dict[str, tuple[str, int]] = {}
for _canon, _factor, _aliases in [
    ("g", 1, ["g", "gr", "gr.", "gram", "grams"]),
    ("g", 1000, ["kg", "kilo", "kilogram"]),
    ("ml", 1, ["ml", "milliliter"]),
    ("ml", 10, ["cl", "centiliter"]),
    ("ml", 100, ["dl", "deciliter"]),
    ("ml", 1000, ["l", "liter", "litre"]),
    ("el", 1, ["el", "el.", "eetlepel", "eetlepels", "tbsp"]),
    ("tl", 1, ["tl", "tl.", "theelepel", "theelepels", "tsp"]),
    ("teen", 1, ["teen", "tenen", "teentje", "teentjes"]),
    ("", 1, ["", "st", "st.", "stuk", "stuks"]),
]:
    for _a in _aliases:
        _UNITS[_a] = (_canon, _factor)

_UNICODE_FRACTIONS = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3"}


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _parse_amount(text: str | None) -> Fraction | None:
    """'2', '1,5', '1/2', '1 1/2', '½', '1½' -> Fraction; else None."""
    s = (text or "").strip()
    for u, ascii_ in _UNICODE_FRACTIONS.items():
        s = re.sub(rf"(\d){u}", rf"\1 {ascii_}", s).replace(u, ascii_)
    s = s.replace(",", ".")
    if not s:
        return None
    try:
        return sum((Fraction(part) for part in s.split()), Fraction(0))
    except (ValueError, ZeroDivisionError):
        return None


def _fmt_number(x: Fraction) -> str:
    if x.denominator == 1:
        return str(x.numerator)
    return f"{float(x):.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _fmt_quantity(total: Fraction, unit: str) -> str:
    if unit == "g" and total >= 1000:
        return f"{_fmt_number(total / 1000)} kg"
    if unit == "ml" and total >= 1000:
        return f"{_fmt_number(total / 1000)} l"
    return f"{_fmt_number(total)} {unit}".strip()


def combine(entries: list[tuple[str, list[dict]]]) -> list[dict]:
    """entries: (recipe_name, ingredient rows with name/amount/unit), one per
    planned meal, so a recipe planned twice counts twice.

    Returns [{name, quantity, recipes}] sorted by name.
    """
    groups: dict[str, dict] = {}
    for recipe_name, ingredients in entries:
        for ing in ingredients:
            key = _norm(ing["name"])
            if not key:
                continue
            g = groups.setdefault(key, {
                "name": ing["name"].strip(), "sums": {}, "other": [], "recipes": [],
            })
            if recipe_name not in g["recipes"]:
                g["recipes"].append(recipe_name)

            unit_raw = _norm(ing.get("unit"))
            amount = _parse_amount(ing.get("amount"))
            known = _UNITS.get(unit_raw)
            if amount is not None and known:
                canon, factor = known
                g["sums"][canon] = g["sums"].get(canon, Fraction(0)) + amount * factor
            elif amount is not None:
                # Unknown unit like "blik" or "zakje": still sum per unit.
                g["sums"][unit_raw] = g["sums"].get(unit_raw, Fraction(0)) + amount
            else:
                text = f"{(ing.get('amount') or '').strip()} {(ing.get('unit') or '').strip()}".strip()
                if text and text not in g["other"]:
                    g["other"].append(text)

    out = []
    for g in groups.values():
        parts = [_fmt_quantity(total, unit) for unit, total in g["sums"].items()]
        parts += g["other"]
        out.append({"name": g["name"], "quantity": " + ".join(parts), "recipes": g["recipes"]})
    out.sort(key=lambda i: _norm(i["name"]))
    return out
