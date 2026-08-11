from datetime import UTC, datetime

import pytest

from scripts.environment_age_check import parse_utc


def test_parse_utc_normalises_an_offset() -> None:
    assert parse_utc("2026-08-11T20:00:00+01:00") == datetime(2026, 8, 11, 19, tzinfo=UTC)


def test_parse_utc_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone"):
        parse_utc("2026-08-11T19:00:00")
