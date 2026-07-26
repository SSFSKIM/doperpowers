# windowed-telemetry

A small, dependency-free module that turns a stream of raw device readings into
per-window summary rows.

## What it does

1. `records.py` parses newline-delimited JSON readings (`device_id`, `ts`,
   `value`) into `Reading` objects. Malformed lines raise `MalformedReading`
   with the offending line number.
2. `windows.py` assigns each reading to a fixed-width tumbling window. It keeps
   a watermark (the largest timestamp seen so far) and drops readings that fall
   further behind the watermark than `allowed_lateness` seconds.
3. `aggregate.py` accumulates count / total / min / max per window and can emit
   the accumulated windows as plain dictionaries.
4. `pipeline.py` glues the three together into `summarize_file`.

## Usage

```python
from pipeline import summarize_file

report = summarize_file("readings.ndjson", width_seconds=60, allowed_lateness=30)
for row in report["windows"]:
    print(row["window_start"], row["count"], row["mean"])
print("dropped as late:", report["dropped_late"])
```

## Conventions

* Timestamps are integer epoch seconds.
* Window bounds are half-open: `[start, end)`.
* Emitted rows are sorted by window start.
