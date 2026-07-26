"""Parsing of raw newline-delimited telemetry readings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List


class MalformedReading(ValueError):
    """Raised when a raw line cannot be turned into a Reading."""


@dataclass(frozen=True)
class Reading:
    device_id: str
    ts: int
    value: float


REQUIRED_FIELDS = ("device_id", "ts", "value")


def parse_line(line: str) -> Reading:
    """Turn one NDJSON line into a Reading.

    The line must be a JSON object carrying at least ``device_id``, ``ts`` and
    ``value``. Unknown keys are ignored so that producers can add fields
    without breaking older consumers.
    """
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise MalformedReading("not valid JSON: %s" % exc.msg) from exc

    if not isinstance(payload, dict):
        raise MalformedReading("record must be a JSON object")

    missing = [name for name in REQUIRED_FIELDS if name not in payload]
    if missing:
        raise MalformedReading("missing fields: %s" % ", ".join(missing))

    return Reading(
        device_id=str(payload["device_id"]),
        ts=int(payload["ts"]),
        value=float(payload["value"]),
    )


def load_readings(path: str) -> List[Reading]:
    """Read every non-blank line of ``path`` into a list of Readings."""
    readings: List[Reading] = []
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                readings.append(parse_line(raw))
            except MalformedReading as exc:
                raise MalformedReading("line %d: %s" % (lineno, exc)) from None
    return readings
