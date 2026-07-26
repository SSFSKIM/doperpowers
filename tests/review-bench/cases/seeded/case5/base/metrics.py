"""A counter registry small enough to keep in the process.

Counters are only ever touched from the event loop thread, so there is no
lock here. Nothing in this package hands a Counters instance to an executor.
"""

from __future__ import annotations

from typing import Dict


class Counters:
    def __init__(self) -> None:
        self._values: Dict[str, int] = {}

    def incr(self, name: str, amount: int = 1) -> None:
        self._values[name] = self._values.get(name, 0) + amount

    def get(self, name: str) -> int:
        return self._values.get(name, 0)

    def snapshot(self) -> Dict[str, int]:
        return dict(self._values)

    def reset(self) -> None:
        self._values.clear()
