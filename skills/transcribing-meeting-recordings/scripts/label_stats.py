#!/usr/bin/env python3
"""Per-chunk named-vs-anonymous speaker label stats — the pass-2 trigger check.

Usage: label_stats.py <workspace> <out_subdir>

Pass 2 (same-channel ref bootstrap) is warranted when overall anon rate is
above ~5%, or any chunk shows a named speaker depleted while one anonymous
label dominates carrying that speaker's speech. Anonymous labels are per-chunk
identities — never merge them across chunks.
"""
import json
import sys
from pathlib import Path

W = Path(sys.argv[1]).resolve()
DIAR = W / "work" / sys.argv[2]
SPK = set(json.loads((W / "sources.json").read_text())["speakers"].keys())

tot_named = tot = 0
for f in sorted(DIAR.glob("*.json")):
    segs = json.loads(f.read_text())["segments"]
    counts = {}
    for s in segs:
        counts[s["speaker"]] = counts.get(s["speaker"], 0) + 1
    named = sum(v for k, v in counts.items() if k in SPK)
    tot_named += named
    tot += len(segs)
    print(f"{f.stem}: {len(segs):4d} segs, named {named/max(len(segs),1):5.1%}  "
          f"{dict(sorted(counts.items(), key=lambda kv: -kv[1]))}")
print(f"TOTAL: {tot} segs, named {tot_named/max(tot,1):.1%}, "
      f"anon {1 - tot_named/max(tot,1):.1%}")
