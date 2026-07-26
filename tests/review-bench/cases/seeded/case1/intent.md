# Multi-tenant partitioning and batched ingest

The ingest module was written when we had one customer. It is now serving
several, and two problems fall out of that:

1. **Watermarks are shared.** One tenant replaying a busy day pushes the global
   watermark forward and makes another tenant's perfectly in-order readings
   look late. Watermarks become per-tenant, and windows are keyed by
   `(tenant, window_start)` so summary rows never mix tenants.

2. **One giant file per run.** Backfills arrive as a directory of consecutive
   NDJSON slices. `summarize_files` processes them as one continuous stream —
   watermarks carry across slices — but treats each file as a batch and flushes
   the aggregator at the end of it, so a long backfill does not have to hold
   every window it has ever seen. `summarize_file` becomes a thin wrapper over
   the batch path.

Also in this change:

* `tenants.json` + `tenants.py` hold per-tenant ingest limits. Readings above a
  tenant's `max_value` are counted in `clipped` and dropped before windowing;
  unknown tenants inherit the `default` entry.
* `value` must now be a finite JSON number. We used to `float()` whatever showed
  up, which silently accepted `"12.5"` and `true` from a broken producer for two
  quarters — and `NaN`, which Python's `json` accepts as a literal and which
  poisons every sum it reaches. Those lines are now rejected as malformed so the
  producer's own alerting fires. This is a deliberate tightening — expect a spike
  in `MalformedReading` from any producer that was relying on coercion.
* `WindowStats` keeps `+inf`/`-inf` sentinels internally instead of `None`
  checks in the hot path; `minimum`/`maximum` are now properties that still
  report `None` for an empty window, so the emitted rows are unchanged.
* Rows are ordered by `(tenant, window_start)` rather than by window start
  alone, which is the only stable ordering now that a batch can carry several
  tenants.
