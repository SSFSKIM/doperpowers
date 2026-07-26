"""Per-window accumulation of reading statistics."""

from __future__ import annotations

from typing import Dict, List, Optional

from records import Reading
from windows import Window


class WindowStats:
    """Running count / total / min / max for a single window."""

    def __init__(self, window: Window):
        self.window = window
        self.count = 0
        self.total = 0.0
        self.minimum: Optional[float] = None
        self.maximum: Optional[float] = None

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        if self.minimum is None or value < self.minimum:
            self.minimum = value
        if self.maximum is None or value > self.maximum:
            self.maximum = value

    @property
    def mean(self) -> Optional[float]:
        if self.count == 0:
            return None
        return self.total / self.count

    def as_dict(self) -> Dict[str, object]:
        return {
            "window_start": self.window.start,
            "window_end": self.window.end,
            "count": self.count,
            "total": self.total,
            "min": self.minimum,
            "max": self.maximum,
            "mean": self.mean,
        }


class WindowedAggregator:
    """Accumulate readings into the window they were assigned to."""

    def __init__(self) -> None:
        self._pending: Dict[int, WindowStats] = {}

    def add(self, window: Window, reading: Reading) -> None:
        stats = self._pending.get(window.start)
        if stats is None:
            stats = WindowStats(window)
            self._pending[window.start] = stats
        stats.observe(reading.value)

    def open_window_count(self) -> int:
        return len(self._pending)

    def flush(self) -> List[Dict[str, object]]:
        """Emit and retire every accumulated window, oldest first."""
        rows = [self._pending[start].as_dict() for start in sorted(self._pending)]
        self._pending.clear()
        return rows
