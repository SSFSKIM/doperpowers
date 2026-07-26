feat(queue): retrievable job results, joinable computations, sliding TTL

Three things came out of last week's load test, plus the API change support
asked for.

* **Results are retrievable.** `submit()` now returns a job id and every
  finished job files a `JobResult` under it, success or failure. Support has
  been reading counters and guessing. Retention is a bounded buffer
  (`MAX_RETAINED_RESULTS`, oldest dropped first) rather than a registry,
  because most callers are fire-and-forget and will never collect anything;
  nothing here may depend on collection to be freed.

* **`submit()` no longer waits for room.** A full queue means the pool is
  saturated, and the request handlers would rather fail the request than
  hold a connection open until a worker frees up. It raises
  `asyncio.QueueFull`. It stays a coroutine so no caller has to change.

* **A second caller for a key in flight now joins it** instead of queueing
  on the key's lock. Under the load test we were holding a lock slot per
  waiter for the whole of somebody else's computation, which is exactly the
  bookkeeping the keyed locks exist to avoid.

* **Hot keys get a sliding TTL.** A key being read constantly was still
  being thrown away on a fixed schedule and recomputed in the middle of the
  read burst. A key read at least `refresh_after_hits` times *while it is
  still fresh* slides its deadline forward instead. This is a liveness
  optimisation only: once a deadline has passed the entry is gone and the
  next read recomputes it, however hot the key was.

* **`KeyedLock.hold()` takes a timeout.** A key whose computation is stuck
  on an upstream should not accumulate waiters that will never be served;
  they raise `asyncio.TimeoutError` and the caller decides. Taking the
  reference and taking the lock now happen under the same guard.

Also: retry backoff gets full jitter and a ceiling (four workers that failed
against the same upstream in the same instant were coming back in the same
instant), and warm-up gets a minimum interval between passes so it cannot be
driven in a loop by a caller polling `stats()`.
