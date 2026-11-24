"""The large usage fixture the slow tests stream (written by `make fixtures`)."""
from __future__ import annotations

import csv
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path

COLUMNS = (
    ("usage_events", "occurred_at", "Time"),
    ("products", "name", "Product"),
    ("usage_events", "quantity", "Quantity"),
    ("usage_events", "unit_price", "Unit price"),
    ("usage_events", "currency", "Currency"),
)


class UsageFixture:
    def __init__(self, path: Path):
        self.path = path
        self.columns = COLUMNS
        with path.open() as f:
            self.count = int(f.readline().split("=")[1])  # "-- rows=2000000"

    def rows(self) -> Iterator[dict]:
        with self.path.open() as f:
            f.readline()
            for rec in csv.reader(f):
                yield {"usage_events.occurred_at": datetime.fromisoformat(rec[0]), "products.name": rec[1],
                       "usage_events.quantity": Decimal(rec[2]), "usage_events.unit_price": Decimal(rec[3]),
                       "usage_events.currency": rec[4]}
