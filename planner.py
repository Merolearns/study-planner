#!/usr/bin/env python3
"""study-planner: a small CLI for planning study time.

Subcommands:
    course add NAME [--hours H]      register a course
    course list                     show courses and upcoming deadlines
    deadline add COURSE "TITLE" DATE
    deadline list                   show all incomplete deadlines
    plan [--hours H] [--start DATE]  print a 7-day schedule
    review add COURSE "TITLE" [--note TEXT]
    review                          show items due for review
    review done ITEM_ID --quality 1-5
    quiz COURSE --topic "TOPIC"     generate practice questions (optional AI)

Data lives in ~/.study-planner/planner.db (override with
STUDY_PLANNER_HOME for a different home dir).
"""

import argparse
import sys
from datetime import date

import db
import quiz as quiz_mod
import reviews
import schedule as sched


def find_course(conn, name):
    row = conn.execute(
        "SELECT id, name FROM courses WHERE lower(name) = lower(?)", (name,)
    ).fetchone()
    if row is None:
        sys.exit(f"error: no course named '{name}' (see: course list)")
    return row


def cmd_course_add(conn, args):
    try:
        conn.execute(
            "INSERT INTO courses (name, hours_per_week) VALUES (?, ?)",
            (args.name, args.hours),
        )
        conn.commit()
    except Exception:
        sys.exit(f"error: course '{args.name}' already exists")
    print(f"added course '{args.name}' ({args.hours} hrs/week)")


def cmd_course_list(conn, _args):
    rows = conn.execute(
        "SELECT id, name, hours_per_week FROM courses ORDER BY name"
    ).fetchall()
    if not rows:
        print("no courses yet -- add one with: course add NAME")
        return
    for row in rows:
        upcoming = conn.execute(
            "SELECT title, due_date FROM deadlines "
            "WHERE course_id = ? AND done = 0 AND due_date >= date('now') "
            "ORDER BY due_date LIMIT 1",
            (row["id"],),
        ).fetchone()
        due = (
            f"next: {upcoming['title']} ({upcoming['due_date']})"
            if upcoming
            else "no upcoming deadlines"
        )
        print(f"{row['id']:>3}  {row['name']:<30} {due}")


def cmd_deadline_add(conn, args):
    course = find_course(conn, args.course)
    try:
        date.fromisoformat(args.date)
    except ValueError:
        sys.exit("error: date must be YYYY-MM-DD")
    conn.execute(
        "INSERT INTO deadlines (course_id, title, due_date) VALUES (?, ?, ?)",
        (course["id"], args.title, args.date),
    )
    conn.commit()
    print(f"added deadline '{args.title}' for {course['name']} on {args.date}")


def cmd_deadline_list(conn, _args):
    rows = conn.execute(
        "SELECT d.id, c.name AS course, d.title, d.due_date FROM deadlines d "
        "JOIN courses c ON c.id = d.course_id "
        "WHERE d.done = 0 ORDER BY d.due_date"
    ).fetchall()
    if not rows:
        print("no incomplete deadlines")
        return
    for row in rows:
        print(f"{row['id']:>3}  {row['due_date']}  [{row['course']}] {row['title']}")


def cmd_plan(conn, args):
    courses = conn.execute("SELECT id, name FROM courses").fetchall()
    if not courses:
        sys.exit("error: add a course first (course add NAME)")

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

    try:
        start = date.fromisoformat(args.start) if args.start else None
    except ValueError:
        sys.exit("error: --start must be YYYY-MM-DD")

    plan = sched.build_schedule(
        course_info, hours_per_day=args.hours, start=start, days=7
    )
    if not plan:
        print("nothing to schedule")
        return

    # wipe the old plan and store the new one
    conn.execute("DELETE FROM schedule_items")
    for item in plan:
        conn.execute(
            "INSERT INTO schedule_items (course_id, day, minutes) VALUES (?, ?, ?)",
            (item["course_id"], item["day"], item["minutes"]),
        )
    conn.commit()

    current_day = None
    for item in plan:
        if item["day"] != current_day:
            current_day = item["day"]
            print(f"\n{current_day}")
        print(f"  {item['minutes']:>3} min  {item['course_name']}")
    print()


def cmd_review_add(conn, args):
    course = find_course(conn, args.course)
    conn.execute(
        "INSERT INTO review_items (course_id, title, note, next_review) "
        "VALUES (?, ?, ?, date('now'))",
        (course["id"], args.title, args.note),
    )
    conn.commit()
    print(f"added '{args.title}' to the review queue for {course['name']}")


def cmd_review_list(conn, _args):
    rows = conn.execute(
        "SELECT r.id, c.name AS course, r.title, r.note, r.interval_days, "
        "r.next_review, r.reviews_done FROM review_items r "
        "JOIN courses c ON c.id = r.course_id "
        "WHERE r.next_review <= date('now') ORDER BY r.next_review"
    ).fetchall()
    if not rows:
        print("nothing due for review -- nice.")
        return
    for row in rows:
        note = f" -- {row['note']}" if row["note"] else ""
        print(
            f"{row['id']:>3}  [{row['course']}] {row['title']}{note} "
            f"(interval {row['interval_days']}d, reviewed {row['reviews_done']}x)"
        )


def cmd_review_done(conn, args):
    row = conn.execute(
        "SELECT id, interval_days FROM review_items WHERE id = ?", (args.item_id,)
    ).fetchone()
    if row is None:
        sys.exit(f"error: no review item with id {args.item_id}")

    new_interval = reviews.next_interval(row["interval_days"], args.quality)
    next_review = reviews.next_review_date(new_interval)
    conn.execute(
        "UPDATE review_items SET interval_days = ?, next_review = ?, "
        "reviews_done = reviews_done + 1 WHERE id = ?",
        (new_interval, next_review, args.item_id),
    )
    conn.commit()
    print(f"next review in {new_interval} day(s) ({next_review})")


def cmd_quiz(conn, args):
    course = find_course(conn, args.course)
    questions, status = quiz_mod.generate_quiz(args.topic, course["name"])
    if status != "ok":
        print(quiz_mod.describe_status(status))
        return
    print(f"Quiz: {course['name']} -- {args.topic}\n")
    for question in questions:
        print(question)
    print()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="study-planner", description="plan study time across your courses"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # course
    p_course = sub.add_parser("course", help="manage courses")
    course_sub = p_course.add_subparsers(dest="course_cmd", required=True)
    p_add = course_sub.add_parser("add", help="add a course")
    p_add.add_argument("name")
    p_add.add_argument("--hours", type=float, default=5.0,
                       help="target hours per week (default 5)")
    p_add.set_defaults(func=cmd_course_add)
    p_list = course_sub.add_parser("list", help="list courses")
    p_list.set_defaults(func=cmd_course_list)

    # deadline
    p_deadline = sub.add_parser("deadline", help="manage deadlines")
    deadline_sub = p_deadline.add_subparsers(dest="deadline_cmd", required=True)
    p_dadd = deadline_sub.add_parser("add", help="add a deadline")
    p_dadd.add_argument("course")
    p_dadd.add_argument("title")
    p_dadd.add_argument("date", help="YYYY-MM-DD")
    p_dadd.set_defaults(func=cmd_deadline_add)
    p_dlist = deadline_sub.add_parser("list", help="list incomplete deadlines")
    p_dlist.set_defaults(func=cmd_deadline_list)

    # plan
    p_plan = sub.add_parser("plan", help="generate a 7-day study schedule")
    p_plan.add_argument("--hours", type=float, default=2.0,
                        help="available study hours per day (default 2)")
    p_plan.add_argument("--start", help="schedule start date YYYY-MM-DD")
    p_plan.set_defaults(func=cmd_plan)

    # review
    p_review = sub.add_parser("review", help="spaced repetition queue")
    review_sub = p_review.add_subparsers(dest="review_cmd")
    p_radd = review_sub.add_parser("add", help="add an item to the queue")
    p_radd.add_argument("course")
    p_radd.add_argument("title")
    p_radd.add_argument("--note", default="", help="extra context")
    p_radd.set_defaults(func=cmd_review_add)
    p_rdone = review_sub.add_parser("done", help="record a completed review")
    p_rdone.add_argument("item_id", type=int)
    p_rdone.add_argument("--quality", type=int, required=True,
                         help="how well you remembered it, 1-5")
    p_rdone.set_defaults(func=cmd_review_done)
    # bare `review` with no subcommand lists due items
    p_review.set_defaults(func=cmd_review_list)

    # quiz
    p_quiz = sub.add_parser("quiz", help="generate practice questions")
    p_quiz.add_argument("course")
    p_quiz.add_argument("--topic", required=True)
    p_quiz.set_defaults(func=cmd_quiz)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    conn = db.connect()
    try:
        args.func(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
