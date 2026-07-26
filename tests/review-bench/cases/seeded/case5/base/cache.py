"""A TTL cache whose misses are computed exactly once."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from keylock import KeyedLock
from metrics import Counters

DEFAULT_TTL_SECONDS = 30.0
DEFAULT_MAX_ENTRIES = 1024

Factory = Callable[[], Awaitable[Any]]


@dataclass
class Entry:
    value: Any
    expires_at: float
    last_used: float
    hits: int = 0


class TTLCache:
    """Cache values for `ttl` seconds, computing each miss once.

    Two coroutines that miss on the same key at the same moment do not both
    call the factory: the second waits on that key's lock and then finds the
    value the first one stored.
    """

    def __init__(
        self,
        ttl: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        counters: Optional[Counters] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._ttl = ttl
        self._max_entries = max_entries
        self._entries: Dict[str, Entry] = {}
        self._locks = KeyedLock()
        self._counters = counters if counters is not None else Counters()
        self._clock = clock

    def _lookup(self, key: str) -> Optional[Entry]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        now = self._clock()
        if entry.expires_at <= now:
            del self._entries[key]
            self._counters.incr("cache.expired")
            return None
        entry.hits += 1
        entry.last_used = now
        return entry

    def _store(self, key: str, value: Any) -> None:
        now = self._clock()
        self._entries[key] = Entry(value=value, expires_at=now + self._ttl, last_used=now)
        self._evict()

    def _evict(self) -> None:
        while len(self._entries) > self._max_entries:
            coldest = min(self._entries, key=lambda k: self._entries[k].last_used)
            del self._entries[coldest]
            self._counters.incr("cache.evicted")

    async def get_or_compute(self, key: str, factory: Factory) -> Any:
        entry = self._lookup(key)
        if entry is not None:
            self._counters.incr("cache.hit")
            return entry.value

        async with self._locks.hold(key):
            # Whoever held the lock before us may have filled the key in.
            entry = self._lookup(key)
            if entry is not None:
                self._counters.incr("cache.hit_after_wait")
                return entry.value

            self._counters.incr("cache.miss")
            value = await factory()
            self._store(key, value)
            return value

    def invalidate(self, key: str) -> bool:
        """Drop `key`. Returns whether anything was there."""
        return self._entries.pop(key, None) is not None

    def size(self) -> int:
        return len(self._entries)

    def tracked_locks(self) -> int:
        return self._locks.tracked_keys()
