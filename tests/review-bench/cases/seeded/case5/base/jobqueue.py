"""A bounded asyncio worker pool whose results go through a TTL cache."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List, Optional

from cache import TTLCache
from metrics import Counters

DEFAULT_WORKERS = 4
DEFAULT_CAPACITY = 128
DEFAULT_BASE_DELAY = 0.05

# Hit rate below which warm_stale_keys() is willing to do work.
PREFETCH_HIT_RATE = 0.6

# How many recently-run keys stay eligible for warm-up.
MAX_WARM_KEYS = 256

Handler = Callable[[], Awaitable[Any]]


@dataclass
class Job:
    key: str
    handler: Handler
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("job key must not be empty")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")


class JobQueue:
    def __init__(
        self,
        workers: int = DEFAULT_WORKERS,
        capacity: int = DEFAULT_CAPACITY,
        cache: Optional[TTLCache] = None,
        counters: Optional[Counters] = None,
        base_delay: float = DEFAULT_BASE_DELAY,
    ) -> None:
        self._counters = counters if counters is not None else Counters()
        self._cache = cache if cache is not None else TTLCache(counters=self._counters)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=capacity)
        self._worker_count = workers
        self._workers: List[asyncio.Task] = []
        self._base_delay = base_delay
        # Insertion-ordered so the oldest key is the one that ages out.
        self._warm_keys: "OrderedDict[str, None]" = OrderedDict()

    async def start(self) -> None:
        if self._workers:
            return
        self._workers = [
            asyncio.create_task(self._worker(i)) for i in range(self._worker_count)
        ]

    async def submit(self, job: Job) -> None:
        """Enqueue a job, waiting for room if the queue is at capacity."""
        await self._queue.put(job)
        self._counters.incr("job.submitted")

    async def drain(self) -> None:
        """Wait until every submitted job has been handled."""
        await self._queue.join()

    async def aclose(self) -> None:
        for _ in self._workers:
            await self._queue.put(None)
        await asyncio.gather(*self._workers)
        self._workers = []

    async def _worker(self, index: int) -> None:
        while True:
            job = await self._queue.get()
            try:
                if job is None:
                    return
                await self._run_job(job)
            except Exception:
                self._counters.incr("job.abandoned")
            finally:
                self._queue.task_done()

    async def _run_job(self, job: Job) -> Any:
        delay = self._base_delay
        for attempt in range(1, job.max_attempts + 1):
            try:
                value = await self._cache.get_or_compute(job.key, job.handler)
            except Exception:
                self._counters.incr("job.attempt_failed")
                if attempt >= job.max_attempts:
                    self._counters.incr("job.failed")
                    raise
                await asyncio.sleep(delay)
                delay *= 2
            else:
                self._counters.incr("job.succeeded")
                self._remember_warm(job.key)
                return value

    def _remember_warm(self, key: str) -> None:
        self._warm_keys.pop(key, None)
        self._warm_keys[key] = None
        while len(self._warm_keys) > MAX_WARM_KEYS:
            self._warm_keys.popitem(last=False)

    def cache_hit_rate(self) -> float:
        hits = self._counters.get("cache.hit") + self._counters.get("cache.hit_after_wait")
        misses = self._counters.get("cache.miss")
        total = hits + misses
        if total == 0:
            # Nothing observed yet. Report a healthy rate so that a queue
            # which has only just started does not immediately warm up.
            return 1.0
        return hits / total

    async def warm_stale_keys(self, factory_for: Callable[[str], Optional[Handler]]) -> int:
        """Recompute recently-run keys before they expire.

        Only does anything when the observed hit rate has fallen below
        PREFETCH_HIT_RATE. Returns how many keys were refreshed.
        """
        if self.cache_hit_rate() >= PREFETCH_HIT_RATE:
            return 0

        refreshed = 0
        # Snapshot: workers keep running and mutating _warm_keys while the
        # factories below are awaited.
        for key in list(self._warm_keys):
            factory = factory_for(key)
            if factory is None:
                continue
            self._cache.invalidate(key)
            await self._cache.get_or_compute(key, factory)
            refreshed += 1

        self._counters.incr("cache.warmed", refreshed)
        return refreshed

    def stats(self) -> dict:
        return {
            "queue_depth": self._queue.qsize(),
            "cache_entries": self._cache.size(),
            "cache_hit_rate": self.cache_hit_rate(),
            "counters": self._counters.snapshot(),
        }
