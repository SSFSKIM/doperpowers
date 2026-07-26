"""Per-key asyncio locks with reference counting.

Keeping one `asyncio.Lock` per key forever would grow without bound in a
process whose key space is unbounded (per-user keys, per-request keys), so a
key's lock is dropped as soon as its last holder releases it.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict


class KeyedLock:
    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}
        self._refs: Dict[str, int] = {}
        # Guards the two maps above, and nothing else: it is never held
        # across an await that belongs to the caller.
        self._guard = asyncio.Lock()

    def _drop_if_idle(self, key: str) -> None:
        if self._refs.get(key) == 0:
            del self._refs[key]
            del self._locks[key]

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        """Hold the lock for `key` for the duration of the block."""
        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
                self._refs[key] = 0
            # Claim a reference before releasing the guard so that a holder
            # on its way out cannot tear the slot down underneath us.
            self._refs[key] += 1

        try:
            async with lock:
                yield
        finally:
            async with self._guard:
                self._refs[key] -= 1
                self._drop_if_idle(key)

    def tracked_keys(self) -> int:
        """Number of keys currently holding a lock object."""
        return len(self._locks)
