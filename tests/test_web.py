"""Tests for the study-planner web UI (app.py).

Uses Flask's test client with STUDY_PLANNER_HOME pointed at a throwaway
directory, so the real database is never touched.
"""

import os
from datetime import date, timedelta

import db
import pytest
import schedule as sched

import app as web_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDY_PLANNER_HOME", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    web_app.app.config["TESTING"] = True
    with web_app.app.test_client() as client:
        yield client


def _seed(conn):
    """Two courses with deadlines at known offsets from today."""
    today = date.today()
    cur = conn.execute(
        "INSERT INTO courses (name, hours_per_week) VALUES (?, ?)",
        ("CPSC 483", 6.0),
    )
    c483 = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO courses (name, hours_per_week) VALUES (?, ?)",
        ("CPSC 335", 5.0),
    )
    c335 = cur.lastrowid
    conn.execute(
        "INSERT INTO deadlines (course_id, title, due_date) VALUES (?, ?, ?)",
        (c483, "midterm", (today + timedelta(days=2)).isoformat()),
    )
    conn.execute(
        "INSERT INTO deadlines (course_id, title, due_date) VALUES (?, ?, ?)",
        (c335, "project 2", (today + timedelta(days=9)).isoformat()),
    )
    conn.execute(
        "INSERT INTO review_items (course_id, title, note, next_review) "
        "VALUES (?, ?, ?, date('now'))",
        (c483, "bayes theorem", "P(A|B) = P(B|A)P(A)/P(B)"),
    )
    conn.commit()
    return c483, c335


def test_home_renders_with_seeded_data(client):
    conn = db.connect()
    _seed(conn)
    conn.close()
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "CPSC 483" in html
    assert "midterm" in html
    assert "bayes theorem" in html
    assert "CPSC 335" in html


def test_home_empty_state_offers_sample(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Load sample week" in resp.get_data(as_text=True)


def test_add_course_and_deadline_round_trip(client):
    resp = client.post(
        "/courses", data={"name": "CPSC 351", "hours": "4"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "CPSC 351" in resp.get_data(as_text=True)
    resp = client.post(
        "/deadlines",
        data={
            "course": "CPSC 351",
            "title": "lab report 3",
            "date": (date.today() + timedelta(days=4)).isoformat(),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "lab report 3" in html
    conn = db.connect()
    row = conn.execute(
        "SELECT d.title FROM deadlines d JOIN courses c "
        "ON c.id = d.course_id WHERE c.name = 'CPSC 351'"
    ).fetchone()
    conn.close()
    assert row["title"] == "lab report 3"


def test_deadline_add_via_web_stores_canonical_date(client):
    client.post(
        "/courses", data={"name": "CPSC 351", "hours": "4"},
        follow_redirects=True,
    )
    # compact ISO form must be normalized, same as the CLI
    resp = client.post(
        "/deadlines",
        data={"course": "CPSC 351", "title": "final", "date": "20261201"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    conn = db.connect()
    row = conn.execute("SELECT due_date FROM deadlines").fetchone()
    conn.close()
    assert row["due_date"] == "2026-12-01"


def test_deadline_done_removes_it_from_dashboard(client):
    conn = db.connect()
    _seed(conn)
    conn.close()
    today = date.today()
    resp = client.post(
        "/deadlines",
        data={"course": "CPSC 483", "title": "quiz 1",
              "date": (today + timedelta(days=1)).isoformat()},
        follow_redirects=True,
    )
    assert "quiz 1" in resp.get_data(as_text=True)
    conn = db.connect()
    row = conn.execute(
        "SELECT id FROM deadlines WHERE title = 'quiz 1'"
    ).fetchone()
    conn.close()
    resp = client.post(f"/deadlines/{row['id']}/done", follow_redirects=True)
    assert resp.status_code == 200
    assert "quiz 1" not in resp.get_data(as_text=True)
    conn = db.connect()
    done = conn.execute(
        "SELECT done FROM deadlines WHERE id = ?", (row["id"],)
    ).fetchone()[0]
    conn.close()
    assert done == 1


def test_plan_generation_renders_real_schedule_math(client):
    conn = db.connect()
    c483, c335 = _seed(conn)
    conn.close()
    today = date.today()
    # the same math the CLI runs, computed independently here
    course_info = [
        {"id": c483, "name": "CPSC 483",
         "nearest_due": (today + timedelta(days=2)).isoformat()},
        {"id": c335, "name": "CPSC 335",
         "nearest_due": (today + timedelta(days=9)).isoformat()},
    ]
    expected = sched.build_schedule(
        course_info, hours_per_day=2.0, start=today, days=7
    )
    day0 = [item for item in expected if item["day"] == today.isoformat()]
    assert day0, "expected schedule to cover today"
    resp = client.post(
        "/plan",
        data={"hours": "2", "start": today.isoformat(), "days_off": ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for item in day0:
        assert item["course_name"] in html
        assert f"{item['minutes']} min" in html


def test_plan_with_days_off_skips_weekend(client):
    conn = db.connect()
    _seed(conn)
    conn.close()
    today = date.today()
    resp = client.post(
        "/plan",
        data={"hours": "2", "start": today.isoformat(), "days_off": "sat,sun"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    conn = db.connect()
    days = {
        row["day"]
        for row in conn.execute("SELECT DISTINCT day FROM schedule_items")
    }
    conn.close()
    # no stored day falls on a Saturday or Sunday
    for day in days:
        year, month, day_num = (int(p) for p in day.split("-"))
        assert date(year, month, day_num).weekday() < 5


def test_review_done_advances_interval(client):
    conn = db.connect()
    _seed(conn)
    item = conn.execute(
        "SELECT id, interval_days FROM review_items"
    ).fetchone()
    conn.close()
    assert item["interval_days"] == 1
    resp = client.post(
        f"/review/{item['id']}/done", data={"quality": "5"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    conn = db.connect()
    row = conn.execute(
        "SELECT interval_days, next_review, reviews_done FROM review_items "
        "WHERE id = ?",
        (item["id"],),
    ).fetchone()
    conn.close()
    assert row["interval_days"] == 3
    assert row["next_review"] == (
        date.today() + timedelta(days=3)
    ).isoformat()
    assert row["reviews_done"] == 1


def test_quiz_page_shows_not_configured_without_key(client):
    conn = db.connect()
    _seed(conn)
    conn.close()
    resp = client.post(
        "/quiz", data={"course": "CPSC 483", "topic": "decision trees"},
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Quiz generation is off" in html
    assert "GEMINI_API_KEY" in html


def test_bad_inputs_return_200_with_error_not_500(client):
    conn = db.connect()
    _seed(conn)
    conn.close()
    today = date.today()
    # bad date on a deadline
    resp = client.post(
        "/deadlines",
        data={"course": "CPSC 483", "title": "x", "date": "not-a-date"},
    )
    assert resp.status_code == 200
    assert "YYYY-MM-DD" in resp.get_data(as_text=True)
    # unknown course on a deadline
    resp = client.post(
        "/deadlines",
        data={
            "course": "No Such Course", "title": "x",
            "date": today.isoformat(),
        },
    )
    assert resp.status_code == 200
    assert "no course named" in resp.get_data(as_text=True)
    # zero hours on a course
    resp = client.post("/courses", data={"name": "Bad", "hours": "0"})
    assert resp.status_code == 200
    assert "more than 0" in resp.get_data(as_text=True)
    # zero hours on a plan
    resp = client.post(
        "/plan",
        data={"hours": "0", "start": today.isoformat(), "days_off": ""},
    )
    assert resp.status_code == 200
    assert "more than 0" in resp.get_data(as_text=True)


def test_sample_week_seeds_once(client):
    resp = client.post("/sample", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "CPSC 483" in html
    assert "midterm" in html
    assert "bayes theorem" in html
    assert "Sample week loaded" in html
    # second load refuses -- the planner already has courses
    resp = client.post("/sample", follow_redirects=True)
    assert "already has courses" in resp.get_data(as_text=True)
    conn = db.connect()
    count = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    conn.close()
    assert count == 3


def test_static_css_serves(client):
    resp = client.get("/static/style.css")
    assert resp.status_code == 200
    assert ".course-card" in resp.get_data(as_text=True)


def test_quiz_get_and_review_get_render(client):
    assert client.get("/quiz").status_code == 200
    assert client.get("/review").status_code == 200
    assert client.get("/plan").status_code == 200
    # without the key set, the environment variable is absent
    assert "GEMINI_API_KEY" not in os.environ
