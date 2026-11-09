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

Minutes planned for days that have already passed are treated as missed
and carried forward: pass them as `carryover` ({course_id: minutes}) and
they are added to the first scheduled day of the new plan, so a skipped
day doesn't silently vanish from the week.
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
    {course_id: minutes}. Guarantees the sum equals total_minutes. When
    rounding up overshoots (a small day split across many courses), the
    excess is taken back from the largest allocations so no course is
    dropped from the plan."""
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
    if leftover > 0:
        top = max(weights, key=weights.get)
        allocations[top] += leftover
    elif leftover < 0:
        # rounding overshot (small day, many courses): take the excess
        # back from the largest allocations instead of dumping it all on
        # one course, which used to zero that course out of the plan.
        # Whole blocks while an allocation is above one block, then
        # single minutes, so no course ever drops to zero.
        while leftover < 0:
            largest = max(allocations, key=allocations.get)
            step = BLOCK_MINUTES if allocations[largest] > BLOCK_MINUTES else 1
            take = min(-leftover, step)
            allocations[largest] -= take
            leftover += take

    # drop zero-minute entries so the plan doesn't show noise
    return {cid: mins for cid, mins in allocations.items() if mins > 0}


def build_schedule(courses, hours_per_day=2.0, start=None, days=7,
                   days_off=None, carryover=None):
    """Build a `days`-long schedule.

    courses: list of {'id', 'name', 'nearest_due'}.
    days_off: optional set of weekday numbers (0=Monday..6=Sunday) that get
        no study time -- days marked off are skipped entirely, so the plan
        only covers the remaining days of the window.
    carryover: optional {course_id: minutes} of missed minutes from days
        that already passed. They are added to the first scheduled day
        (skipping days off), so a missed day rolls forward instead of
        disappearing. Entries for courses no longer in `courses` are
        ignored.
    Returns a list of {'day', 'course_id', 'course_name', 'minutes'} dicts.
    """
    start = start or date.today()
    days_off = set(days_off or ())
    carryover = dict(carryover or {})
    total_minutes = int(hours_per_day * 60)
    weights = course_weights(courses, start)
    id_to_name = {c["id"]: c["name"] for c in courses}

    plan = []
    carried = False
    for offset in range(days):
        day = start + timedelta(days=offset)
        if day.weekday() in days_off:
            continue
        todays = split_day(total_minutes, weights)
        if carryover and not carried:
            for course_id, minutes in carryover.items():
                if minutes > 0 and course_id in id_to_name:
                    todays[course_id] = todays.get(course_id, 0) + minutes
            carried = True
        for course_id, minutes in todays.items():
            plan.append(
                {
                    "day": day.isoformat(),
                    "course_id": course_id,
                    "course_name": id_to_name[course_id],
                    "minutes": minutes,
                }
            )
    return plan
