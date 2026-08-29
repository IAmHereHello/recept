"""Healthiness score -> Nutri-Score-style letter grade.

Thresholds live here (not stored) so they can be retuned without re-scoring.
"""
from typing import Optional

_BANDS = ((80, "A"), (65, "B"), (50, "C"), (35, "D"))


def grade(score: Optional[int]) -> Optional[str]:
    if score is None:
        return None
    for threshold, letter in _BANDS:
        if score >= threshold:
            return letter
    return "E"
