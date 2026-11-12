"""Tests for the study-planner CLI argument handling."""

import pytest

import db
import planner
from planner import build_parser


def test_quality_out_of_range_rejected():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["review", "done", "1", "--quality", "7"])
    with pytest.raises(SystemExit):
        parser.parse_args(["review", "done", "1", "--quality", "0"])


def test_quality_in_range_accepted():
    parser = build_parser()
    for q in ("1", "3", "5"):
        args = parser.parse_args(["review", "done", "1", "--quality", q])
        assert args.quality == int(q)


def _conn(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDY_PLANNER_HOME", str(tmp_path))
    return db.connect()


def test_course_add_rejects_non_positive_hours(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    parser = build_parser()
    for hours in ("0", "-3"):
        args = parser.parse_args(["course", "add", "Math", "--hours", hours])
        with pytest.raises(SystemExit, match="more than 0"):
            planner.cmd_course_add(conn, args)
    # and a positive value still works
    args = parser.parse_args(["course", "add", "Math", "--hours", "4"])
    planner.cmd_course_add(conn, args)
    assert conn.execute(
        "SELECT hours_per_week FROM courses WHERE name = 'Math'"
    ).fetchone()[0] == 4.0
    conn.close()


def test_plan_rejects_non_positive_hours(tmp_path, monkeypatch):
    conn = _conn(tmp_path, monkeypatch)
    parser = build_parser()
    args = parser.parse_args(["course", "add", "Math"])
    planner.cmd_course_add(conn, args)
    for hours in ("0", "-2"):
        args = parser.parse_args(["plan", "--hours", hours])
        with pytest.raises(SystemExit, match="more than 0"):
            planner.cmd_plan(conn, args)
    conn.close()
