"""Tumbling window assignment with a watermark and a lateness grace period."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from records import Reading


@dataclass(frozen=True)
class Window:
    """A half-open time window ``[start, end)``."""

    start: int
    end: int

    def contains(self, ts: int) -> bool:
        return self.start <= ts < self.end


class WindowAssigner:
    """Assign readings to fixed-width tumbling windows.

    The assigner tracks a watermark: the largest timestamp it has seen. A
    reading is *late* when its timestamp has fallen further behind the
    watermark than ``allowed_lateness`` seconds. Late readings are counted in
    ``dropped_late`` and discarded; everything else is assigned to the window
    its timestamp falls into.
    """

    def __init__(self, width_seconds: int, allowed_lateness: int = 0, origin: int = 0):
        if width_seconds <= 0:
            raise ValueError("width_seconds must be positive")
        if allowed_lateness < 0:
            raise ValueError("allowed_lateness must not be negative")
        self.width_seconds = width_seconds
        self.allowed_lateness = allowed_lateness
        self.origin = origin
        self.watermark: Optional[int] = None
        self.dropped_late = 0

    def window_for(self, ts: int) -> Window:
        """Return the window a timestamp belongs to."""
        index = (ts - self.origin) // self.width_seconds
        start = self.origin + index * self.width_seconds
        return Window(start=start, end=start + self.width_seconds)

    def assign(self, reading: Reading) -> Optional[Window]:
        """Return the window for ``reading``, or None when it arrived too late."""
        if self.watermark is not None:
            if reading.ts < self.watermark - self.allowed_lateness:
                self.dropped_late += 1
                return None

        if self.watermark is None or reading.ts > self.watermark:
            self.watermark = reading.ts

        return self.window_for(reading.ts)
