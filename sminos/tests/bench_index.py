#!/usr/bin/env python3
"""bench_index — what one transcript's build costs, three ways (the desk
open-fast spec, docs/doperpowers/specs/2026-10-20-desk-open-fast-design.md,
M7, A3): cold (every row parsed from the first byte), loaded (a saved build
read back, then extended past its end), and warm (extended again in memory).

    bench_index.py <transcript.jsonl> [--keep]

The transcript is only read. The saved build is written under a temporary
SMINOS_HOME of this run's own (removed after, unless --keep), never the
machine's. The plane is imported from the plugin root this file sits under.
Prints one line per way — CPU and wall seconds, the rows and bytes indexed,
the 1-minute load — then the saved build's size and what saving it cost,
and a JSON summary; nothing of the transcript's content."""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts")


def timed(fn):
    cpu, wall = time.thread_time(), time.perf_counter()
    fn()
    return time.thread_time() - cpu, time.perf_counter() - wall


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("transcript")
    p.add_argument("--keep", action="store_true", help="leave the temporary SMINOS_HOME on disk")
    a = p.parse_args()
    path = os.path.realpath(a.transcript)
    if not os.path.isfile(path):
        sys.exit("bench_index: no file %s" % a.transcript)
    root = tempfile.mkdtemp(prefix="bi.", dir="/tmp")
    os.environ["SMINOS_HOME"] = os.path.join(root, "s")
    os.makedirs(os.environ["SMINOS_HOME"], mode=0o700)
    sys.path.insert(0, SCRIPTS)
    import sminos_plane as plane
    out = {"transcript_bytes": os.path.getsize(path), "load1": round(os.getloadavg()[0], 2)}
    try:
        def line(way, cpu, wall, t):
            out[way] = {"cpu": round(cpu, 3), "wall": round(wall, 3), "how": t.how}
            print("%-6s cpu %.2f s wall %.2f s  (%s; %d rows, %d bytes; load1 %.2f)" % (
                way, cpu, wall, t.how, len(t.index.uuids), t.index.end, os.getloadavg()[0]), flush=True)

        cold = plane.Transcript(path)
        cold.tried = True   # the reference parse: no saved build looked for
        line("cold", *timed(cold.extended), cold)
        cpu, wall = timed(lambda: cold.save() or sys.exit("bench_index: the build was not saved"))
        size = os.path.getsize(plane.build_file(path))
        out["save"] = {"cpu": round(cpu, 3), "wall": round(wall, 3), "bytes": size}
        print("save   cpu %.2f s wall %.2f s  (%.1f MB)" % (cpu, wall, size / 1e6), flush=True)
        loaded = plane.Transcript(path)
        line("loaded", *timed(loaded.extended), loaded)
        if loaded.how != "loaded":
            sys.exit("bench_index: the saved build was not used (%s)" % loaded.how)
        line("warm", *timed(loaded.extended), loaded)
        out["rows"], out["bytes"] = len(loaded.index.uuids), loaded.index.end
        out["load1_after"] = round(os.getloadavg()[0], 2)
        print(json.dumps(out), flush=True)
    finally:
        if a.keep:
            print("kept: %s" % root, file=sys.stderr)
        else:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
