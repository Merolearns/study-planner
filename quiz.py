"""Optional AI quiz generation via the Gemini API.

This module is intentionally defensive: the quiz feature is a bonus, not a
requirement. If google-generativeai isn't installed or GEMINI_API_KEY isn't
set, we return a structured "unavailable" result instead of raising, and the
CLI prints a plain-English message. Nothing in the rest of the app depends
on this working.
"""

import os

MODEL_NAME = "gemini-2.0-flash"
QUESTION_COUNT = 5


def generate_quiz(topic, course_name):
    """Try to generate quiz questions.

    Returns (questions, status) where status is one of:
        "ok"            - questions is a list of 5 strings
        "missing_key"   - GEMINI_API_KEY not set
        "not_installed" - google-generativeai not installed
        "api_error"     - key set but the call failed (message included)
    """
    if not os.environ.get("GEMINI_API_KEY"):
        return None, "missing_key"

    try:
        import google.generativeai as genai
    except ImportError:
        return None, "not_installed"

    prompt = (
        f"Write {QUESTION_COUNT} short study quiz questions for a college "
        f"course called '{course_name}', on the topic '{topic}'. "
        "Number them 1-5, one per line. Questions only, no answers."
    )

    try:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
    except Exception as exc:  # network, auth, quota -- all degrade the same way
        return None, f"api_error: {exc}"

    lines = [line.strip() for line in response.text.splitlines() if line.strip()]
    return lines[:QUESTION_COUNT], "ok"


def describe_status(status):
    """Human-readable explanation of a non-ok status."""
    if status == "missing_key":
        return (
            "Quiz generation is off: set the GEMINI_API_KEY environment "
            "variable to enable AI quizzes."
        )
    if status == "not_installed":
        return (
            "Quiz generation is off: install the optional dependency with "
            "'pip install google-generativeai' and set GEMINI_API_KEY."
        )
    if status.startswith("api_error"):
        detail = status.split(":", 1)[1].strip()
        return f"Quiz generation failed ({detail}). Check your key and connection."
    return status
