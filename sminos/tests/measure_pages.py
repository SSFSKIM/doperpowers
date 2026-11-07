#!/usr/bin/env python3
"""DC8.G1's measurement (the desk, DC8 M2): the open's transcript build, on
transcripts of at least 150 MB and 10,000 rows. Run by hand, one at a time on
a busy machine, never in the suites:

    /tmp/maws-review/with-slot.sh python3 sminos/tests/measure_pages.py \\
        [--copy TRANSCRIPT]... [--synthetic-mb 160 | --no-synthetic]

Each transcript — a synthetic one this writes (12,000 rows and records of
the engine's other kinds, at least 150 MB) and a copy of each --copy file,
made under a temporary directory (the original is only read, once) — is
measured in this process: one full parse as the plane did it before DC8
(the file read whole, every line given to json.loads; each page and each
open cost this), against the offset index's build, then a second build of
the same file (it reads nothing). The 1-minute load average is read at each
transcript's start and end.

The measurement's second half, through `sminos daemon uplink` against the
DX2 hub stand-in, went with that transport (#153 M5); the open through the
real uplink on RL10 is bench_open.py's and bench_scale.py's.
Hermetic: HOME and SMINOS_HOME are temporary.
"""

import argparse
import gc
import json
import os
import random
import shutil
import sys
import time
import uuid as uuidlib

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import test_session_plane as tsp  # noqa: E402 — its import isolates HOME and SMINOS_HOME under a temporary root

import sminos_plane as plane  # noqa: E402

T = tsp.T


def full_parse_before_dc8(path):
    """The plane's read of a whole transcript before DC8 (rows_of)."""
    with open(path, "rb") as f:
        data = f.read()
    end = data.rfind(b"\n")
    out = []
    for line in data[:end].split(b"\n"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("uuid"), str) and row["uuid"]:
            out.append((row["uuid"], row))
    return out


def synthetic(path, megabytes, rows=12000):
    """A transcript shaped as the engine writes one: user and assistant rows
    of varied sizes (some tool results carrying a nested `uuid` of their own),
    and between them the engine's records that are not rows (`api-request`
    bodies, queue operations), to at least `megabytes` MB."""
    rnd = random.Random(8)
    words = "the plane reads only what a page needs from the index it keeps ".split()
    parent = None
    with open(path, "w") as f:
        i = 0
        while i < rows or f.tell() < megabytes * 1e6:
            u = str(uuidlib.UUID(int=rnd.getrandbits(128)))
            text = " ".join(rnd.choice(words) for _ in range(rnd.choice((20, 200, 1200, 2400))))
            row = {"parentUuid": parent, "isSidechain": False, "type": "user" if i % 2 else "assistant",
                   "message": {"role": "user" if i % 2 else "assistant", "content": [{"type": "text", "text": text}]},
                   "uuid": u, "timestamp": "2026-10-17T00:00:%02d.000Z" % (i % 60)}
            if i % 7 == 0:
                row["toolUseResult"] = {"uuid": str(uuidlib.UUID(int=rnd.getrandbits(128))), "status": "completed"}
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
            if i % 3 == 0:
                f.write(json.dumps({"type": "api-request", "body": {"messages": [text] * 3}},
                                   separators=(",", ":")) + "\n")
            f.write(json.dumps({"type": "queue-operation", "operation": "dequeue"}) + "\n")
            parent = u
            i += 1
    return i


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return time.perf_counter() - t0, out


def in_process(path):
    """Today's full parse against the index's build and a second build."""
    with open(path, "rb") as f:
        while f.read(64 << 20):
            pass   # the page cache warm for both
    before, rows = timed(lambda: full_parse_before_dc8(path))
    count = len(rows)
    del rows   # what the parse kept would weigh on the build's collections
    gc.collect()
    t = plane.Transcript(path)
    built, _ = timed(t.extended)
    again, _ = timed(t.extended)
    return {"size_mb": round(os.path.getsize(path) / 1e6, 1), "rows": count, "indexed": len(t.index.uuids),
            "full_parse_before_s": round(before, 3), "index_build_s": round(built, 3),
            "second_build_s": round(again, 4), "index_parsed_mb": round(t.index.parsed / 1e6, 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--copy", action="append", default=[], help="a transcript to measure a copy of")
    ap.add_argument("--synthetic-mb", type=float, default=160)
    ap.add_argument("--no-synthetic", action="store_true", help="measure the copies alone")
    a = ap.parse_args()
    results = []
    try:
        for name in ([] if a.no_synthetic else ["synthetic"]) + a.copy:
            dest = os.path.join(T, "measured", "%s.jsonl" % uuidlib.uuid4())
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if name == "synthetic":
                synthetic(dest, a.synthetic_mb)
            else:
                shutil.copyfile(name, dest)
            sys.stderr.write("measuring %s\n" % os.path.basename(name))
            load = os.getloadavg()[0]
            result = {"transcript": os.path.basename(name), **in_process(dest)}
            result["load1"] = {"start": round(load, 2), "end": round(os.getloadavg()[0], 2)}
            os.unlink(dest)
            results.append(result)
            print(json.dumps(result, indent=2), flush=True)
    finally:
        if os.environ.get("MEASURE_KEEP"):
            sys.stderr.write("kept: %s\n" % T)
        else:
            shutil.rmtree(T, ignore_errors=True)
    return results


if __name__ == "__main__":
    main()
