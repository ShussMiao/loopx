from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_MIN_TIMESTAMP = datetime.min.replace(tzinfo=timezone.utc)


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def chronology_key(value: Any) -> tuple[int, datetime, str]:
    """Order timestamps by UTC instant with deterministic legacy fallbacks."""

    raw = str(value or "")
    try:
        parsed = parse_timestamp(value)
    except OverflowError:
        # UTC conversion can overflow at datetime's representable boundaries.
        parsed = None
    if parsed is None:
        return (0, _MIN_TIMESTAMP, raw)
    return (1, parsed, raw)


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def now_utc_iso() -> str:
    return utc_isoformat(now_utc())


def now_local_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def utc_isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_timestamp() -> str:
    return now_utc().strftime("%Y%m%dT%H%M%SZ")
