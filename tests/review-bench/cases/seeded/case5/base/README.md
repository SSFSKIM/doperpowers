# async job queue with a single-flight cache

Four modules, no dependencies outside the standard library. Import them as
top-level modules (run from this directory).

    metrics.py    counter registry, loop-thread only
    keylock.py    per-key asyncio locks with reference counting
    cache.py      TTL cache that computes each miss exactly once
    jobqueue.py   bounded worker pool with retries, backed by that cache

## Shape

    queue = JobQueue(workers=4, capacity=128)
    await queue.start()
    await queue.submit(Job(key="user:42", handler=fetch_user_42))
    await queue.drain()
    await queue.aclose()

A job is a key plus a zero-argument coroutine function. The key is what the
cache is keyed on, so two jobs with the same key that run close together
share one call to the handler: the second one waits on that key's lock and
then finds the value the first one stored.

## Why keys are locked instead of the whole cache

A single cache-wide lock would serialise every recomputation, which is the
opposite of what a queue with four workers is for. `KeyedLock` hands out one
`asyncio.Lock` per key and drops it once the last holder releases it, so a
process that sees unbounded key cardinality does not accumulate one lock per
key it has ever seen. The map of locks is itself guarded, but that guard is
only ever held for the few statements that mutate the map -- never across an
`await` that belongs to the caller.

## Expiry

Entries carry a monotonic deadline. Reads past the deadline drop the entry
and recompute; the clock is injectable so tests do not have to sleep.

## Retries

`Job.max_attempts` (default 3) applies to the whole cached computation. A
failed attempt sleeps for an exponentially growing delay and tries again;
the last failure propagates to the worker, which counts it and moves on.

## Warm-up

`JobQueue.warm_stale_keys()` recomputes recently-run keys ahead of their
expiry, but only when the observed cache hit rate has fallen below
`PREFETCH_HIT_RATE`. The set of candidate keys is bounded at
`MAX_WARM_KEYS`; the oldest is dropped first.
