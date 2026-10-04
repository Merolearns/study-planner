"""Spaced repetition queue.

Simple fixed-ladder approach, loosely inspired by SM-2 but without the
ease-factor math. An item climbs the ladder [1, 3, 7, 14, 30] days when
reviews go well and drops back when they don't:

    quality 1-2  -> back to 1 day
    quality 3    -> stays on the current rung
    quality 4-5  -> climbs one rung (stays at 30 max)

Good enough for keeping vocabulary, formulas, and definitions fresh.
"""

from datetime import date, timedelta

LADDER = [1, 3, 7, 14, 30]


def next_interval(current_days, quality):
    """Return the new interval in days after a review with the given
    quality score (1-5)."""
    if quality not in (1, 2, 3, 4, 5):
        raise ValueError("quality must be between 1 and 5")

    if quality <= 2:
        return LADDER[0]
    if quality == 3:
        return current_days if current_days in LADDER else LADDER[0]
    # quality 4 or 5: climb one rung
    try:
        rung = LADDER.index(current_days)
    except ValueError:
        rung = 0
    return LADDER[min(rung + 1, len(LADDER) - 1)]


def next_review_date(interval_days, today=None):
    today = today or date.today()
    return (today + timedelta(days=interval_days)).isoformat()


def is_due(item, today=None):
    """True if the item's next_review date is today or earlier."""
    today = today or date.today()
    return item["next_review"] <= today.isoformat()
