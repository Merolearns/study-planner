"""Tests for quiz generation, with the Gemini SDK stubbed out."""
import sys
import types

import quiz


class _BlockedResponse:
    """Mimics a safety-blocked reply: .text raises ValueError."""

    @property
    def text(self):
        raise ValueError(
            "The `response.text` quick accessor only works for a single "
            "candidate response with text parts."
        )


class _FakeModel:
    def __init__(self, response):
        self._response = response

    def generate_content(self, prompt):
        return self._response


def _install_fake_genai(monkeypatch, response):
    fake = types.ModuleType("google.generativeai")
    fake.configure = lambda api_key: None
    fake.GenerativeModel = lambda name: _FakeModel(response)
    pkg = types.ModuleType("google")
    pkg.generativeai = fake
    monkeypatch.setitem(sys.modules, "google", pkg)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def test_blocked_reply_returns_api_error_instead_of_raising(monkeypatch):
    # a safety-blocked reply has no usable text: reading .text raises
    # ValueError, which used to escape generate_quiz and crash the caller
    _install_fake_genai(monkeypatch, _BlockedResponse())
    questions, status = quiz.generate_quiz("fractions", "Math 101")
    assert questions is None
    assert status.startswith("api_error")
    assert quiz.describe_status(status).startswith("Quiz generation failed")


def test_ok_reply_returns_five_questions(monkeypatch):
    class _OkResponse:
        text = (
            "1. What is 1+1?\n2. What is 2+2?\n3. What is 3+3?\n"
            "4. What is 4+4?\n5. What is 5+5?\n6. Extra?"
        )

    _install_fake_genai(monkeypatch, _OkResponse())
    questions, status = quiz.generate_quiz("addition", "Math 101")
    assert status == "ok"
    assert len(questions) == 5
    assert questions[0].startswith("1.")


def test_missing_key_without_sdk(monkeypatch):
    # no key at all: still the friendly missing_key result, no import
    # of the SDK attempted
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    questions, status = quiz.generate_quiz("addition", "Math 101")
    assert questions is None
    assert status == "missing_key"
