"""Rendering document rows into the formats the API can serve."""

from __future__ import annotations

import csv
import io
from typing import Dict, List

Row = Dict[str, object]

FORMATS = ("csv", "text")


class UnknownFormat(ValueError):
    """Raised when a caller asks for a format we do not render."""


def columns_of(rows: List[Row]) -> List[str]:
    """Every column present in ``rows``, in first-seen order."""
    seen = set()
    columns: List[str] = []
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    return columns


def to_csv(rows: List[Row]) -> str:
    """Rows as CSV with a header line. No rows means no output at all."""
    if not rows:
        return ""
    columns = columns_of(rows)
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return buffer.getvalue()


def to_text(rows: List[Row]) -> str:
    """Rows as a pipe-separated table. No rows means no output at all."""
    if not rows:
        return ""
    columns = columns_of(rows)
    lines = [" | ".join(columns)]
    for row in rows:
        lines.append(" | ".join(str(row.get(column, "")) for column in columns))
    return "\n".join(lines) + "\n"


def render(rows: List[Row], fmt: str) -> str:
    """Render ``rows`` in ``fmt``; see FORMATS for what we support."""
    if fmt == "csv":
        return to_csv(rows)
    if fmt == "text":
        return to_text(rows)
    raise UnknownFormat("unknown format: %s" % fmt)
