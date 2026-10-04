"""7-day study schedule generation.

The algorithm is deliberately simple -- a greedy weighting pass, not an
optimizer. For each course we compute an urgency weight from its nearest
incomplete deadline:

    weight = 1 / max(days_until_due, 0.5)

So a deadline 2 days out counts about 3.5x more than one 7 days out, and
past-due deadlines pin at the max weight. Courses with no upcoming deadlines
get a small baseline weight so they don't starve completely.

Each day's available minutes are split across courses proportionally to
their weights, rounded to 5-minute blocks. Leftover minutes from rounding
go to the highest-weight course. Nothing is backtracked or rebalanced --
for a personal planner this is good enough and easy to reason about.

TODO: let the user mark days off (no studying on Sundays, etc.)
TODO: carry unfinished minutes forward when a day is missed
"""

from datetime import date, timedelta

BASELINE_WEIGHT = 0.1  # courses with no upcoming deadlines
BLOCK_MINUTES = 5      # round allocations to 5-minute blocks


def days_until(iso_date, today=None):
    today = today or date.today()
    year, month, day = (int(part) for part in iso_date.split("-"))
    return (date(year, month, day) - today).days


def course_weights(courses, today=None):
    """Map course_id -> urgency weight. courses is a list of dicts with
    'id' and 'nearest_due' (ISO date or None)."""
    today = today or date.today()
    weights = {}
    for course in courses:
        due = course.get("nearest_due")
        if due is None:
            weights[course["id"]] = BASELINE_WEIGHT
        else:
            remaining = max(days_until(due, today), 0.5)
            weights[course["id"]] = 1.0 / remaining
    return weights


def split_day(total_minutes, weights):
    """Split one day's minutes across course ids by weight. Returns
    {course_id: minutes}. Guarantees the sum equals total_minutes."""
    if not weights or total_minutes <= 0:
        return {}

    total_weight = sum(weights.values())
    allocations = {}
    assigned = 0
    for course_id, weight in weights.items():
        share = weight / total_weight
        blocks = round(total_minutes * share / BLOCK_MINUTES)
        minutes = blocks * BLOCK_MINUTES
        allocations[course_id] = minutes
        assigned += minutes

    # hand the rounding leftovers to the most urgent course
    leftover = total_minutes - assigned
    if leftover:
        top = max(weights, key=weights.get)
        allocations[top] += leftover

    # drop zero-minute entries so the plan doesn't show noise
    return {cid: mins for cid, mins in allocations.items() if mins > 0}


def build_schedule(courses, hours_per_day=2.0, start=None, days=7):
    """Build a `days`-long schedule.

    courses: list of {'id', 'name', 'nearest_due'}.
    Returns a list of {'day', 'course_id', 'course_name', 'minutes'} dicts.
    """
    start = start or date.today()
    total_minutes = int(hours_per_day * 60)
    weights = course_weights(courses, start)
    id_to_name = {c["id"]: c["name"] for c in courses}

    plan = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for course_id, minutes in split_day(total_minutes, weights).items():
            plan.append(
                {
                    "day": day.isoformat(),
                    "course_id": course_id,
                    "course_name": id_to_name[course_id],
                    "minutes": minutes,
                }
            )
    return plan
