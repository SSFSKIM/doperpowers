# case1 — answer key (never show to reviewers)

**Scenario.** A dependency-free Python telemetry module (`records.py`,
`windows.py`, `aggregate.py`, `pipeline.py`) that parses NDJSON readings,
assigns them to tumbling windows behind a watermark with a lateness grace
period, and emits per-window summary rows. The patch makes it multi-tenant
(per-tenant watermarks, windows keyed by `(tenant, window_start)`, per-tenant
`max_value` limits loaded from a new `tenants.json`/`tenants.py`) and adds a
batched entry point `summarize_files` that flushes the aggregator once per input
file, with `summarize_file` reduced to a wrapper over it.

**Seeded classes: L1, L3, L5.** `case1-b1` (L1) is in the rewritten
`WindowAssigner.assign`: the grace period is applied as
`cutoff = watermark + allowed_lateness`, the wrong sign, so any reading inside
the grace period is dropped as late — invisible at the default
`allowed_lateness=0`, silent data loss for every tenant configured with a grace
period. `case1-b2` (L3) is the cleanup the refactor dropped: splitting `flush()`
into `snapshot()` + `flush()` lost `self._pending.clear()`, so windows are never
retired — batch two re-emits batch one's rows and `_pending` grows without
bound, and the new multi-file path is what makes it reachable. `case1-b3` (L5)
is the new per-reading `load_tenant_limits(reading.tenant)` call in
`summarize_files`: `tenants.py` has no cache, so each reading costs one `open()`
plus a `json.load()` of `tenants.json` (verified: 500 readings → 500 opens).

**Baits (all three are correct and intentional).** (1) `parse_line` now rejects
non-numeric `value` — numeric strings and booleans that used to be coerced by
`float()` are `MalformedReading` — which looks like a breaking behaviour
regression but is deliberate and is documented in the function docstring, the
README conventions and `intent.md`. (2) `WindowStats` swaps its `None`-guarded
min/max tracking for `math.inf` / `-math.inf` sentinels updated with plain
`min`/`max`; the sentinels look like they could leak into the emitted rows, but
`minimum`/`maximum` are properties that return `None` while `count == 0`, so
`as_dict()` output is byte-identical to before. (3) Row ordering changes from
"sorted by window start" to "sorted by `(tenant, window_start)`", which looks
like an unannounced output-ordering change but is a strictly finer, still
deterministic total order and is stated in the docstring, README and intent.
