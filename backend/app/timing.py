"""Cook-time learning and the "time remaining" estimate.

Three signals feed the estimate, most-trusted first:

1. `step_durations` — a learned per-step average + spread, updated by an
   exponentially weighted moving average (EWMA) so recent cooks matter more
   than the first one ever. Keyed by (recipe_id, track, sort_order).
2. `steps.wait_time_minutes` — an authored passive wait (rest / oven / simmer)
   for steps with no learned history yet.
3. `cook_sessions.active_seconds` / `recipes.cook_time` — a whole-recipe budget
   spread across whatever steps signals 1 and 2 didn't cover.

Kept out of `routers/sessions.py` so it can be unit-tested and reused by
`routers/recipes.py` without importing the router module.
"""

from datetime import datetime, timezone
from sqlite3 import Connection
from typing import Optional

# EWMA weight for the newest sample. 0.35 ~= "the last 3 cooks carry most of
# the weight" — responsive to a recipe you've gotten faster at without a single
# bad night swinging it wildly.
EWMA_ALPHA = 0.35

# Until this many counted samples exist, the EWMA stddev isn't a trustworthy
# spread yet, so outlier detection falls back to a percentage band.
MIN_SAMPLES_FOR_SIGMA = 4
OUTLIER_TOLERANCE = 0.15          # +-15% band while sigma isn't trusted yet
OUTLIER_MIN_ABS_SECONDS = 90      # never flag a deviation smaller than this

# Steps with no signal at all get a wide uncertainty band for the low/high
# bracket (they're pure guesswork off the recipe budget).
UNLEARNED_SPREAD_FRACTION = 0.4

# Only use whole-cook history once we have at least this many samples — a
# single cook could just be the night you got distracted.
TYPICAL_MIN_SAMPLES = 2
TYPICAL_WINDOW = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_aware(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def recompute_step_duration(conn: Connection, recipe_id: int, track: str, sort_order: int) -> None:
    """Rebuild the step_durations row for one step from its counted raw logs.

    Replaying the full EWMA from `step_time_logs` (rather than nudging the
    stored average incrementally) means every write path — a new sample, a
    confirmed outlier, a quit session's samples being withdrawn — stays exact
    and consistent with no special-case reversal math.
    """
    rows = conn.execute(
        """SELECT seconds FROM step_time_logs
           WHERE recipe_id=? AND track=? AND sort_order=? AND counted=1
           ORDER BY id""",
        (recipe_id, track, sort_order),
    ).fetchall()
    if not rows:
        conn.execute(
            "DELETE FROM step_durations WHERE recipe_id=? AND track=? AND sort_order=?",
            (recipe_id, track, sort_order),
        )
        return

    secs = [r["seconds"] for r in rows]
    avg = float(secs[0])
    var = 0.0
    for x in secs[1:]:
        diff = x - avg
        avg += EWMA_ALPHA * diff
        var = (1 - EWMA_ALPHA) * (var + EWMA_ALPHA * diff * diff)
    stddev = var ** 0.5

    conn.execute(
        """INSERT INTO step_durations (recipe_id, track, sort_order, avg_seconds, stddev_seconds, sample_count, updated_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(recipe_id, track, sort_order) DO UPDATE SET
             avg_seconds=excluded.avg_seconds, stddev_seconds=excluded.stddev_seconds,
             sample_count=excluded.sample_count, updated_at=excluded.updated_at""",
        (recipe_id, track, sort_order, avg, stddev, len(secs), _now()),
    )


def is_outlier(avg: float, stddev: float, sample_count: int, seconds: float) -> bool:
    """Whether `seconds` is far enough off the running average to hold for
    confirmation rather than fold in silently."""
    if sample_count >= MIN_SAMPLES_FOR_SIGMA:
        band = max(2 * stddev, OUTLIER_MIN_ABS_SECONDS)
    else:
        band = max(avg * OUTLIER_TOLERANCE, OUTLIER_MIN_ABS_SECONDS)
    return abs(seconds - avg) > band


def recipe_typical_seconds(
    conn: Connection, recipe_id: int, min_samples: int = TYPICAL_MIN_SAMPLES
) -> Optional[int]:
    """Median wall-clock duration of this recipe's recent finished cooks, or
    None if there aren't enough samples yet."""
    rows = conn.execute(
        """SELECT active_seconds FROM cook_sessions
           WHERE recipe_id=? AND active_seconds IS NOT NULL
           ORDER BY cooked_at DESC LIMIT ?""",
        (recipe_id, TYPICAL_WINDOW),
    ).fetchall()
    vals = sorted(r["active_seconds"] for r in rows)
    if len(vals) < min_samples:
        return None
    n = len(vals)
    if n % 2:
        return int(vals[n // 2])
    return int((vals[n // 2 - 1] + vals[n // 2]) // 2)


def estimate_remaining(
    conn: Connection,
    recipe_id: int,
    budget_seconds: Optional[float],
    main_steps: list[dict],
    current_step: int,
    active_timer_remaining: Optional[int],
    step_started_at: Optional[str],
    now: datetime,
) -> Optional[tuple[int, int, int]]:
    """(mid, low, high) seconds left for the whole cook, or None when there's
    nothing to derive an estimate from.

    `budget_seconds` is the whole-recipe fallback (typical duration, else
    cook_time*60, else None). `main_steps` are the ordered 'main'-track step
    rows (each a dict with sort_order + wait_time_minutes).
    """
    total_steps = len(main_steps)
    if total_steps == 0 or not (0 <= current_step < total_steps):
        return None

    learned = {
        r["sort_order"]: (r["avg_seconds"], r["stddev_seconds"])
        for r in conn.execute(
            """SELECT sort_order, avg_seconds, stddev_seconds FROM step_durations
               WHERE recipe_id=? AND track='main' AND sample_count > 0""",
            (recipe_id,),
        ).fetchall()
    }
    waits = {
        s["sort_order"]: s["wait_time_minutes"] * 60
        for s in main_steps
        if s["wait_time_minutes"] and s["sort_order"] not in learned
    }

    known_total = sum(v[0] for v in learned.values()) + sum(waits.values())
    unknown_count = total_steps - len(learned) - len(waits)

    if budget_seconds is not None:
        fallback_avg = max(0.0, budget_seconds - known_total) / unknown_count if unknown_count > 0 else 0.0
    elif unknown_count == 0:
        fallback_avg = 0.0
    else:
        return None  # no per-step data and no budget -> nothing to go on

    def base_and_spread(sort_order: int) -> tuple[float, float]:
        if sort_order in learned:
            return learned[sort_order]
        if sort_order in waits:
            return float(waits[sort_order]), 0.0
        return fallback_avg, fallback_avg * UNLEARNED_SPREAD_FRACTION

    mid = low = high = 0.0
    for i in range(current_step, total_steps):
        sort_order = main_steps[i]["sort_order"]
        is_current = i == current_step
        base, spread = base_and_spread(sort_order)

        if is_current and active_timer_remaining is not None:
            base, spread = float(active_timer_remaining), 0.0
        elif is_current and step_started_at and (sort_order in learned or sort_order in waits):
            # A concrete base we can burn down as the step runs; the flat
            # fallback stays frozen (subtracting elapsed off a guess is noise).
            elapsed = (now - _parse_aware(step_started_at)).total_seconds()
            base = max(0.0, base - elapsed)
            spread = min(spread, base)

        mid += base
        low += max(0.0, base - spread)
        high += base + spread

    return round(mid), round(low), round(high)
