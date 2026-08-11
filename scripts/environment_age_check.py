#!/usr/bin/env python3
"""Report whether a demo environment has exceeded its maximum lifetime."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--max-hours", type=int, default=24)
    parser.add_argument("--now", help="UTC timestamp override for deterministic tests")
    args = parser.parse_args()

    created_at = parse_utc(args.created_at)
    now = parse_utc(args.now) if args.now else datetime.now(UTC)
    age_hours = max(0.0, (now - created_at).total_seconds() / 3600)
    overdue = age_hours > args.max_hours
    output = os.getenv("GITHUB_OUTPUT")
    values = f"overdue={str(overdue).lower()}\nage_hours={age_hours:.1f}\n"
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(values)
    if overdue:
        print(
            f"::warning::Azure demo environment is {age_hours:.1f} hours old; "
            f"limit is {args.max_hours} hours"
        )
    else:
        print(
            f"Azure demo environment age is {age_hours:.1f} hours; limit is {args.max_hours} hours"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
