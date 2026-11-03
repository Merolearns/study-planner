"""Tests for the study-planner CLI argument handling."""

import pytest

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
