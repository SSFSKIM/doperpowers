#!/usr/bin/env python3
"""Cut same-channel speaker refs from confident pass-1 solo runs.

Usage: bootstrap_refs.py <workspace> <pass1_subdir> <refs_out_dir>

Per speaker: the best run of consecutive same-speaker segments (gap < 0.8s,
total >= 4s, capped 9.5s), scored by duration * that chunk's named-label ratio
so runs from cleanly-labeled chunks win. Cut from the part's own 16k wav —
the transcription track itself. Cross-channel refs measured 29-35% anonymous
labels; same-channel took the same runs to 0.7-3.9%.
"""
import json
import subprocess
import sys
from pathlib import Path

W = Path(sys.argv[1]).resolve()
DIAR = W / "work" / sys.argv[2]
REFS = Path(sys.argv[3]).resolve()
REFS.mkdir(parents=True, exist_ok=True)

SPEAKERS = list(json.loads((W / "sources.json").read_text())["speakers"].keys())
manifest = {e["file"]: e for e in json.loads((W / "chunks" / "manifest.json").read_text())}

best: "dict[str, dict | None]" = {s: None for s in SPEAKERS}
for f in sorted(DIAR.glob("*.json")):
    entry = manifest[f.stem + ".mp3"]
    segs = json.loads(f.read_text())["segments"]
    conf = sum(1 for s in segs if s["speaker"] in SPEAKERS) / max(len(segs), 1)
    run = None
    for s in segs:
        sp = s["speaker"]
        if run and sp == run["sp"] and s["start"] - run["end"] < 0.8:
            run["end"] = s["end"]
        else:
            run = {"sp": sp, "start": s["start"], "end": s["end"]}
        if run["sp"] in SPEAKERS:
            dur = run["end"] - run["start"]
            score = min(dur, 9.5) * conf
            b = best[run["sp"]]
            if dur >= 4.0 and (b is None or score > b["score"]):
                best[run["sp"]] = {"score": score, "part": entry["part"],
                                   "start": entry["start"] + run["start"],
                                   "dur": min(dur, 9.5)}

for sp in SPEAKERS:
    b = best[sp]
    assert b, f"no confident solo run found for {sp} — point refs manually"
    wav = W / "work" / f"{b['part']}_16k.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-ss", str(round(b["start"], 2)), "-t", str(round(b["dur"], 2)),
                    "-i", str(wav), str(REFS / f"{sp}.wav")], check=True)
    print(f"{sp}: {b['part']} @ {b['start']:.1f}s dur {b['dur']:.1f}s (score {b['score']:.1f})")
