# case5 — async job queue gains result retrieval, joinable computations, sliding TTL

**Scenario.** A four-module asyncio package (`metrics.py`, `keylock.py`,
`cache.py`, `jobqueue.py`): a bounded worker pool whose jobs are deduplicated
through a TTL cache, which in turn serialises per key using reference-counted
`asyncio.Lock` objects. The patch makes `submit()` return a job id and retain
a bounded buffer of `JobResult`s, makes a second caller for an in-flight key
join that computation instead of queueing on its lock, gives hot keys a
sliding TTL, adds an acquire timeout to `KeyedLock.hold()`, and adds jitter
plus a ceiling to the retry backoff. **Seeded classes: L1, L2, L3, L5.**
`case5-b1` (L1) puts the sliding-TTL refresh *before* the expiry test in
`_lookup`, so any key read three times becomes immortal and serves a stale
value forever — which the README and intent.md both explicitly rule out.
`case5-b2` (L3) sets the new in-flight `Event` before `await factory()` and
clears it after, with no `try/finally`, so a raising factory leaves an event
that is never set and every later caller for that key waits on it forever;
because `_run_job` retries the same key, the first failure hangs the worker
permanently and `drain()` never returns. `case5-b3` (L5) moves the entire
body of `hold()` — acquire, `yield`, and the caller's critical section —
inside `async with self._guard`, so a single process-wide lock is held across
the caller's awaits: every computation in the process serialises, the per-key
locks become dead code, and the new timeout can never fire. `case5-b4` (L2)
is the contract break: `cache.py` renamed its counters into a `cache.get.*`
namespace, but `jobqueue.cache_hit_rate()` still reads the old names, so the
rate is permanently the `total == 0` placeholder of 1.0 and warm-up silently
never runs again.

**Baits (correct, do not report).** (1) `_results` is an `OrderedDict` that
grows on every job and is never cleaned up on collection — it looks like the
textbook fire-and-forget leak, but `_record_result` trims it to
`MAX_RETAINED_RESULTS` oldest-first, `result()` documents the ageing-out, and
it is the same bounded pattern `_warm_keys` already used. (2) `submit()` now
raises `asyncio.QueueFull` instead of waiting for room — a real behavior
change that looks like a regression, documented in the docstring, the README
and intent.md, and deliberately left as a coroutine so callers do not change.
(3) The worker loop's `get()` moved into a `_next_job()` helper while
`task_done()` stayed in `_worker`'s `finally` — the pairing is still exactly
one `task_done()` per `get()`, sentinels included, so `drain()` still
terminates. (4) The retry backoff uses full jitter, `random.uniform(0, delay)`,
which can sleep ~0 seconds and looks like it defeats the backoff; it is
deliberate, commented, and bounded by `max_attempts` and
`MAX_BACKOFF_SECONDS`. (5) `WARM_INTERVAL_SECONDS = 30.0` duplicates the
value of `cache.DEFAULT_TTL_SECONDS` rather than importing it, with a comment
explaining that the two numbers answer different questions and must be free
to diverge.
