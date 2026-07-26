"""Glue: raw NDJSON file in, window summary rows out."""

from __future__ import annotations

from typing import Dict, List

from aggregate import WindowedAggregator
from records import load_readings
from windows import WindowAssigner


def summarize_file(
    path: str,
    width_seconds: int,
    allowed_lateness: int = 0,
) -> Dict[str, object]:
    """Summarize one NDJSON file into window rows.

    Readings are processed in file order so that the watermark reflects the
    order the producer actually emitted them in.
    """
    readings = load_readings(path)
    assigner = WindowAssigner(width_seconds, allowed_lateness=allowed_lateness)
    aggregator = WindowedAggregator()

    for reading in readings:
        window = assigner.assign(reading)
        if window is None:
            continue
        aggregator.add(window, reading)

    rows: List[Dict[str, object]] = aggregator.flush()
    return {
        "windows": rows,
        "read": len(readings),
        "dropped_late": assigner.dropped_late,
    }
