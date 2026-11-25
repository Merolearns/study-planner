"""Web UI for study-planner.

Thin Flask front end over the same modules the CLI uses: db, schedule,
reviews, quiz, and the validation helpers in planner. The CLI is untouched
-- this just renders its data as pages and calls the same functions.

Run it with:

    pip install -r requirements.txt
    python app.py

then open http://127.0.0.1:5000
"""

import math
import sqlite3
from datetime import date

import db
import planner
import quiz as quiz_mod
import reviews
import schedule as sched
from flask import Flask, redirect, render_template, request, url_for

app = Flask(__name__)

# a few muted bar colours, cycled per course so the plan bars differ
BAR_COLORS = ["#0e7490", "#2563eb", "#059669", "#b45309", "#7c3aed", "#be185d"]


def bar_color(course_id):
    return BAR_COLORS[course_id % len(BAR_COLORS)]


def courses_with_next(conn):
    """All courses, each with its nearest upcoming deadline (if any)."""
    rows = conn.execute(
        "SELECT id, name, hours_per_week FROM courses ORDER BY name"
    ).fetchall()
    out = []
    for row in rows:
        upcoming = conn.execute(
            "SELECT title, due_date FROM deadlines "
            "WHERE course_id = ? AND done = 0 AND due_date >= date('now') "
            "ORDER BY due_date LIMIT 1",
            (row["id"],),
        ).fetchone()
        days = None
        if upcoming:
            days = sched.days_until(upcoming["due_date"])
        out.append(
            {
                "id": row["id"],
                "name": row["name"],
                "hours_per_week": row["hours_per_week"],
                "next_title": upcoming["title"] if upcoming else None,
                "next_due": upcoming["due_date"] if upcoming else None,
                "days_until": days,
                "color": bar_color(row["id"]),
            }
        )
    return out


def upcoming_deadlines(conn):
    rows = conn.execute(
        "SELECT d.id, c.name AS course, d.title, d.due_date FROM deadlines d "
        "JOIN courses c ON c.id = d.course_id "
        "WHERE d.done = 0 ORDER BY d.due_date"
    ).fetchall()
    return [
        {
            "id": row["id"],
            "course": row["course"],
            "title": row["title"],
            "due_date": row["due_date"],
            "days_until": sched.days_until(row["due_date"]),
        }
        for row in rows
    ]


def due_reviews(conn):
    rows = conn.execute(
        "SELECT r.id, c.name AS course, r.title, r.note, r.interval_days, "
        "r.next_review, r.reviews_done FROM review_items r "
        "JOIN courses c ON c.id = r.course_id "
        "WHERE r.next_review <= date('now') ORDER BY r.next_review"
    ).fetchall()
    return [dict(row) for row in rows]


def saved_plan(conn):
    """The stored schedule, grouped by day, with each course's share."""
    rows = conn.execute(
        "SELECT s.day, s.course_id, c.name AS course, s.minutes "
        "FROM schedule_items s JOIN courses c ON c.id = s.course_id "
        "ORDER BY s.day, s.minutes DESC"
    ).fetchall()
    days = []
    for row in rows:
        if not days or days[-1]["day"] != row["day"]:
            days.append({"day": row["day"], "total": 0, "items": []})
        days[-1]["items"].append(
            {
                "course": row["course"],
                "minutes": row["minutes"],
                "color": bar_color(row["course_id"]),
            }
        )
        days[-1]["total"] += row["minutes"]
    for day in days:
        for item in day["items"]:
            item["pct"] = round(100 * item["minutes"] / day["total"])
    return days


def generate_plan(conn, hours_per_day, start, days_off):
    """Same plan path the CLI uses: build_schedule with carryover of
    missed minutes, then replace the stored schedule."""
    courses = conn.execute("SELECT id, name FROM courses").fetchall()
    course_info = []
    for course in courses:
        nearest = conn.execute(
            "SELECT due_date FROM deadlines WHERE course_id = ? AND done = 0 "
            "AND due_date >= date('now') ORDER BY due_date LIMIT 1",
            (course["id"],),
        ).fetchone()
        course_info.append(
            {
                "id": course["id"],
                "name": course["name"],
                "nearest_due": nearest["due_date"] if nearest else None,
            }
        )
    # minutes planned for days that already passed are missed, not done --
    # roll them onto the first day of the new plan
    carryover = {
        row["course_id"]: row["minutes"]
        for row in conn.execute(
            "SELECT course_id, SUM(minutes) AS minutes FROM schedule_items "
            "WHERE day < ? GROUP BY course_id",
            (start.isoformat(),),
        ).fetchall()
    }
    plan = sched.build_schedule(
        course_info, hours_per_day=hours_per_day, start=start, days=7,
        days_off=days_off, carryover=carryover,
    )
    if not plan:
        # Nothing to schedule (every day is a day off, or the hours
        # round to zero minutes): keep the stored plan instead of
        # wiping it -- the CLI does the same in cmd_plan.
        return plan
    conn.execute("DELETE FROM schedule_items")
    for item in plan:
        conn.execute(
            "INSERT INTO schedule_items (course_id, day, minutes) "
            "VALUES (?, ?, ?)",
            (item["course_id"], item["day"], item["minutes"]),
        )
    conn.commit()
    return plan


def parse_hours(raw):
    """Parse an hours value the way the CLI validates it."""
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        return None, "hours must be a number"
    if not math.isfinite(hours) or hours <= 0:
        return None, "hours must be more than 0"
    return hours, None


def seed_sample_week(conn):
    """Seed 3 courses, deadlines, and review items -- only when the
    database has no courses yet. Returns True if it seeded anything."""
    if conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0] > 0:
        return False
    today = date.today()
    from datetime import timedelta

    courses = [
        ("CPSC 483", 6.0),
        ("CPSC 335", 5.0),
        ("CPSC 351", 4.0),
    ]
    ids = {}
    for name, hours in courses:
        cur = conn.execute(
            "INSERT INTO courses (name, hours_per_week) VALUES (?, ?)",
            (name, hours),
        )
        ids[name] = cur.lastrowid
    deadlines = [
        ("CPSC 351", "lab report 3", today + timedelta(days=4)),
        ("CPSC 483", "midterm", today + timedelta(days=6)),
        ("CPSC 335", "project 2: sorting", today + timedelta(days=10)),
    ]
    for course, title, due in deadlines:
        conn.execute(
            "INSERT INTO deadlines (course_id, title, due_date) "
            "VALUES (?, ?, ?)",
            (ids[course], title, due.isoformat()),
        )
    review_items = [
        ("CPSC 483", "bayes theorem", "P(A|B) = P(B|A)P(A)/P(B)"),
        ("CPSC 335", "dijkstra's algorithm", "greedy, non-negative weights"),
        ("CPSC 351", "process scheduling", "FCFS vs round robin"),
    ]
    for course, title, note in review_items:
        conn.execute(
            "INSERT INTO review_items (course_id, title, note, next_review) "
            "VALUES (?, ?, ?, date('now'))",
            (ids[course], title, note),
        )
    conn.commit()
    generate_plan(conn, hours_per_day=2.0, start=today, days_off=None)
    return True


@app.route("/")
def index():
    conn = db.connect()
    try:
        return render_template(
            "index.html",
            courses=courses_with_next(conn),
            deadlines=upcoming_deadlines(conn),
            reviews=due_reviews(conn),
            plan_days=saved_plan(conn),
            today=date.today().isoformat(),
        )
    finally:
        conn.close()


@app.route("/courses", methods=["POST"])
def add_course():
    name = request.form.get("name", "").strip()
    hours, error = parse_hours(request.form.get("hours", "5"))
    conn = db.connect()
    try:
        if not name:
            error = "course name can't be empty"
        elif not error:
            try:
                conn.execute(
                    "INSERT INTO courses (name, hours_per_week) VALUES (?, ?)",
                    (name, hours),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                error = f"course '{name}' already exists"
        if error:
            return render_template(
                "index.html",
                courses=courses_with_next(conn),
                deadlines=upcoming_deadlines(conn),
                reviews=due_reviews(conn),
                plan_days=saved_plan(conn),
                today=date.today().isoformat(),
                error=error,
            )
        return redirect(url_for("index"))
    finally:
        conn.close()


@app.route("/deadlines", methods=["POST"])
def add_deadline():
    course_name = request.form.get("course", "").strip()
    title = request.form.get("title", "").strip()
    due = request.form.get("date", "").strip()
    conn = db.connect()
    try:
        error = None
        if not title:
            error = "deadline title can't be empty"
        else:
            try:
                course = planner.find_course(conn, course_name)
            except SystemExit as exc:
                error = str(exc).removeprefix("error: ")
                course = None
            if error is None:
                try:
                    # store canonical YYYY-MM-DD (see planner.cmd_deadline_add)
                    due = date.fromisoformat(due).isoformat()
                except ValueError:
                    error = "date must be YYYY-MM-DD"
            if error is None:
                conn.execute(
                    "INSERT INTO deadlines (course_id, title, due_date) "
                    "VALUES (?, ?, ?)",
                    (course["id"], title, due),
                )
                conn.commit()
        if error:
            return render_template(
                "index.html",
                courses=courses_with_next(conn),
                deadlines=upcoming_deadlines(conn),
                reviews=due_reviews(conn),
                plan_days=saved_plan(conn),
                today=date.today().isoformat(),
                error=error,
            )
        return redirect(url_for("index"))
    finally:
        conn.close()


@app.route("/deadlines/<int:deadline_id>/done", methods=["POST"])
def deadline_done(deadline_id):
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE deadlines SET done = 1 WHERE id = ?", (deadline_id,)
        )
        conn.commit()
        return redirect(url_for("index"))
    finally:
        conn.close()


@app.route("/plan", methods=["GET", "POST"])
def plan_page():
    conn = db.connect()
    try:
        courses = courses_with_next(conn)
        error = None
        generated = False
        if request.method == "POST":
            hours, error = parse_hours(request.form.get("hours", "2"))
            start_raw = request.form.get("start", "").strip()
            days_off_raw = request.form.get("days_off", "").strip()
            start = date.today()
            days_off = None
            if error is None and start_raw:
                try:
                    start = date.fromisoformat(start_raw)
                except ValueError:
                    error = "start date must be YYYY-MM-DD"
            if error is None and days_off_raw:
                try:
                    days_off = planner.parse_days_off(days_off_raw)
                except SystemExit as exc:
                    error = str(exc).removeprefix("error: ")
            if error is None:
                plan = generate_plan(conn, hours, start, days_off)
                if plan:
                    generated = True
                else:
                    error = ("nothing to schedule for this week -- "
                             "check the days off and hours")
        return render_template(
            "plan.html",
            courses=courses,
            plan_days=saved_plan(conn),
            today=date.today().isoformat(),
            error=error,
            generated=generated,
        )
    finally:
        conn.close()


@app.route("/review", methods=["GET", "POST"])
def review_page():
    conn = db.connect()
    try:
        error = None
        if request.method == "POST":
            course_name = request.form.get("course", "").strip()
            title = request.form.get("title", "").strip()
            note = request.form.get("note", "").strip()
            if not title:
                error = "review item title can't be empty"
            else:
                try:
                    course = planner.find_course(conn, course_name)
                except SystemExit as exc:
                    error = str(exc).removeprefix("error: ")
                    course = None
                if error is None:
                    conn.execute(
                        "INSERT INTO review_items "
                        "(course_id, title, note, next_review) "
                        "VALUES (?, ?, ?, date('now'))",
                        (course["id"], title, note),
                    )
                    conn.commit()
        return render_template(
            "review.html",
            reviews=due_reviews(conn),
            courses=courses_with_next(conn),
            error=error,
        )
    finally:
        conn.close()


@app.route("/review/<int:item_id>/done", methods=["POST"])
def review_done(item_id):
    try:
        quality = int(request.form.get("quality", ""))
    except ValueError:
        quality = 0
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT interval_days FROM review_items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None or quality not in (1, 2, 3, 4, 5):
            return redirect(url_for("review_page"))
        new_interval = reviews.next_interval(row["interval_days"], quality)
        next_review = reviews.next_review_date(new_interval)
        conn.execute(
            "UPDATE review_items SET interval_days = ?, next_review = ?, "
            "reviews_done = reviews_done + 1 WHERE id = ?",
            (new_interval, next_review, item_id),
        )
        conn.commit()
        return redirect(url_for("review_page"))
    finally:
        conn.close()


@app.route("/quiz", methods=["GET", "POST"])
def quiz_page():
    conn = db.connect()
    try:
        courses = courses_with_next(conn)
        questions = None
        status_message = None
        if request.method == "POST":
            course_name = request.form.get("course", "").strip()
            topic = request.form.get("topic", "").strip()
            try:
                course = planner.find_course(conn, course_name)
            except SystemExit as exc:
                return render_template(
                    "quiz.html",
                    courses=courses,
                    error=str(exc).removeprefix("error: "),
                )
            if not topic:
                return render_template(
                    "quiz.html", courses=courses,
                    error="topic can't be empty",
                )
            questions, status = quiz_mod.generate_quiz(topic, course["name"])
            if status != "ok":
                status_message = quiz_mod.describe_status(status)
        return render_template(
            "quiz.html",
            courses=courses,
            questions=questions,
            status_message=status_message,
        )
    finally:
        conn.close()


@app.route("/sample", methods=["POST"])
def load_sample():
    conn = db.connect()
    try:
        seeded = seed_sample_week(conn)
        return render_template(
            "index.html",
            courses=courses_with_next(conn),
            deadlines=upcoming_deadlines(conn),
            reviews=due_reviews(conn),
            plan_days=saved_plan(conn),
            today=date.today().isoformat(),
            notice=(
                "Sample week loaded: 3 courses, 3 deadlines, 3 review items, "
                "and a 7-day plan."
                if seeded
                else "The planner already has courses, so nothing was added."
            ),
        )
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(debug=True)
