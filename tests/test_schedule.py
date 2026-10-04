"""Tests for the scheduling algorithm."""

from datetime import date, timedelta

from schedule import build_schedule, course_weights, split_day


def courses_for_test():
    return [
        {"id": 1, "name": "CS 101", "nearest_due": None},
        {"id": 2, "name": "MATH 250", "nearest_due": None},
    ]


def test_closer_deadline_gets_more_time():
    today = date.today()
    soon = (today + timedelta(days=2)).isoformat()
    later = (today + timedelta(days=10)).isoformat()
    courses = [
        {"id": 1, "name": "urgent", "nearest_due": soon},
        {"id": 2, "name": "chill", "nearest_due": later},
    ]
    plan = build_schedule(courses, hours_per_day=2.0, start=today, days=1)
    by_course = {p["course_id"]: p["minutes"] for p in plan}
    assert by_course[1] > by_course[2]


def test_day_total_matches_available_hours():
    plan = build_schedule(courses_for_test(), hours_per_day=2.0, days=7)
    totals = {}
    for item in plan:
        totals[item["day"]] = totals.get(item["day"], 0) + item["minutes"]
    assert len(totals) == 7
    assert all(total == 120 for total in totals.values())


def test_course_without_deadlines_still_gets_something():
    # baseline weight should keep no-deadline courses from starving
    today = date.today()
    soon = (today + timedelta(days=1)).isoformat()
    courses = [
        {"id": 1, "name": "urgent", "nearest_due": soon},
        {"id": 2, "name": "no-deadline", "nearest_due": None},
    ]
    weights = course_weights(courses, today)
    assert weights[2] > 0
    assert weights[1] > weights[2]


def test_weights_fall_off_with_distance():
    today = date.today()
    c = lambda cid, d: {  # noqa: E731 - test helper
        "id": cid,
        "name": str(cid),
        "nearest_due": (today + timedelta(days=d)).isoformat(),
    }
    weights = course_weights([c(1, 2), c(2, 4), c(3, 8)], today)
    assert weights[1] > weights[2] > weights[3]


def test_split_day_rounding_keeps_total():
    alloc = split_day(120, {1: 1.0, 2: 1.0, 3: 1.0})
    assert sum(alloc.values()) == 120


def test_schedule_spans_seven_days():
    plan = build_schedule(courses_for_test(), days=7)
    days = {item["day"] for item in plan}
    assert len(days) == 7
