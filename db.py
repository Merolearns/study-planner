"""SQLite storage for the study planner.

One file database under ~/.study-planner/planner.db. Schema is created on
first connect, so there is no separate setup step.
"""

import os
import sqlite3
from pathlib import Path


def default_db_path():
    home = Path(os.environ.get("STUDY_PLANNER_HOME", Path.home()))
    return home / ".study-planner" / "planner.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT UNIQUE NOT NULL,
    hours_per_week REAL NOT NULL DEFAULT 5.0
);

CREATE TABLE IF NOT EXISTS deadlines (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    title     TEXT NOT NULL,
    due_date  TEXT NOT NULL,          -- ISO date, YYYY-MM-DD
    done      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS review_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id    INTEGER NOT NULL REFERENCES courses(id),
    title        TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    interval_days INTEGER NOT NULL DEFAULT 1,
    next_review  TEXT NOT NULL,       -- ISO date, YYYY-MM-DD
    reviews_done INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS schedule_items (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    day       TEXT NOT NULL,          -- ISO date, YYYY-MM-DD
    minutes   INTEGER NOT NULL,
    topic     TEXT NOT NULL DEFAULT ''
);
"""


def connect(path=None):
    """Open the database and make sure the schema exists."""
    path = Path(path) if path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
