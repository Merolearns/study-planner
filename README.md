# study-planner

A small command-line study planner I built for my own classes. It keeps track
of my courses and deadlines, generates a 7-day study schedule weighted by
what's due soonest, and runs a spaced-repetition review queue so formulas and
definitions don't rot between exams. There's also an optional AI quiz feature
that generates practice questions for a topic (off by default unless you set
it up).

This is a personal learning project — I wrote it to get better at building
small tools end to end. Nothing here is production software.

## Setup

```bash
pip install -r requirements.txt
```

The only hard dependency is `pytest` for running the tests. The Gemini quiz
feature needs the optional `google-generativeai` package plus an API key —
without both, the `quiz` command just tells you it's not configured.

## Usage

```bash
python planner.py course add "CPSC 483" --hours 6
python planner.py course list
python planner.py deadline add "CPSC 483" "midterm" 2026-10-20
python planner.py deadline list
python planner.py plan --hours 2.5
python planner.py review add "CPSC 483" "bayes theorem" --note "P(A|B) = P(B|A)P(A)/P(B)"
python planner.py review
python planner.py review done 1 --quality 4
python planner.py quiz "CPSC 483" --topic "decision trees"
```

Data is stored in a SQLite file at `~/.study-planner/planner.db`. Set
`STUDY_PLANNER_HOME` to a different directory if you want the database
somewhere else.

## How the scheduler works

Nothing fancy — a greedy weighting pass, no optimizer:

1. Each course gets an urgency weight from its nearest incomplete deadline:
   `weight = 1 / days_until_due` (clamped so past-due deadlines pin at the max).
2. Courses with no upcoming deadlines get a small baseline weight so they
   don't starve.
3. Each day's available minutes are split proportionally by weight, rounded to
   5-minute blocks. Rounding leftovers go to the most urgent course.

It regenerates the full week each time you run `plan`, replacing the previous
schedule.

## How the review queue works

Items climb a fixed interval ladder — 1, 3, 7, 14, 30 days — based on how
well you remembered them:

- quality 1–2: back to 1 day
- quality 3: stays where it is
- quality 4–5: climbs one rung

`review` shows everything due today or earlier; `review done ID --quality N`
records a review and schedules the next one.

## AI quizzes

To enable:

```bash
pip install google-generativeai
export GEMINI_API_KEY="your-key-here"
```

Then `python planner.py quiz "COURSE" --topic "TOPIC"` generates 5 practice
questions. If the package isn't installed or the key isn't set, the command
prints a message saying so and exits cleanly — the rest of the app never
depends on it.

## Tests

```bash
python -m pytest
```

Covers the scheduling math (urgency weighting, day totals, rounding) and the
interval logic (ladder climbing, resets, due-date checks).
