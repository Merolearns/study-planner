"""Tests for the spaced repetition logic."""

import pytest

from reviews import is_due, next_interval, next_review_date
from datetime import date, timedelta


def test_good_review_climbs_ladder():
    assert next_interval(1, 5) == 3
    assert next_interval(3, 4) == 7
    assert next_interval(7, 5) == 14
    assert next_interval(14, 5) == 30


def test_interval_caps_at_thirty_days():
    assert next_interval(30, 5) == 30
    assert next_interval(30, 4) == 30


def test_bad_review_resets_to_one():
    assert next_interval(14, 1) == 1
    assert next_interval(30, 2) == 1


def test_mediocre_review_stays_put():
    assert next_interval(7, 3) == 7
    assert next_interval(30, 3) == 30


def test_invalid_quality_rejected():
    with pytest.raises(ValueError):
        next_interval(1, 0)
    with pytest.raises(ValueError):
        next_interval(1, 6)


def test_next_review_date_math():
    today = date.today()
    assert next_review_date(1, today) == (today + timedelta(days=1)).isoformat()
    assert next_review_date(14, today) == (today + timedelta(days=14)).isoformat()


def test_is_due():
    today = date.today()
    past = (today - timedelta(days=2)).isoformat()
    future = (today + timedelta(days=2)).isoformat()
    assert is_due({"next_review": past}, today)
    assert is_due({"next_review": today.isoformat()}, today)
    assert not is_due({"next_review": future}, today)
