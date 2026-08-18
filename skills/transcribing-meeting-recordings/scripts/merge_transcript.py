#!/usr/bin/env python3
"""Merge diarized chunks into transcript.json/.md, with inline screen markers.

Usage: merge_transcript.py <workspace> <diar_subdir>
Reads:  chunks/manifest.json, work/<diar_subdir>/*.json, sources.json,
        work/screen_index.json (optional — authored by the agent after reading
        every extracted frame; see references/pipeline-reference.md)
Writes: transcript.json (parts[].segments with per-segment "screen",
        parts[].screens index), transcript.md (turn-merged, screen markers)

Turns merge when same speaker, gap < 3s, and same active screen. Unknown
speakers render as "Unknown <label>" — swap the word for the transcript's
language. Anonymous labels are per-chunk; this script never merges them
across chunks.
"""
import json
import sys
from pathlib import Path

W = Path(sys.argv[1]).resolve()
DIAR = W / "work" / sys.argv[2]
SRC = json.loads((W / "sources.json").read_text())
DISPLAY = SRC["speakers"]
UNKNOWN = SRC.get("unknown_word", "Unknown")

idx_path = W / "work" / "screen_index.json"
index = json.loads(idx_path.read_text()) if idx_path.exists() else {}


def fmt(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), int(t % 60)
    return f"{h}:{m:02d}:{s:02d}"


manifest = json.loads((W / "chunks" / "manifest.json").read_text())
parts = {p: [] for p in SRC["parts"]}
for entry in manifest:
    data = json.loads((DIAR / (Path(entry["file"]).stem + ".json")).read_text())
    for s in data["segments"]:
        text = s["text"].strip()
        if not text:
            continue
        parts[entry["part"]].append({
            "start": round(s["start"] + entry["start"], 2),
            "end": round(s["end"] + entry["start"], 2),
            "speaker": DISPLAY.get(s["speaker"], f"{UNKNOWN} {s['speaker']}"),
            "speaker_raw": s["speaker"],
            "text": text,
        })

md = ["# Transcript (diarized)", "",
      f"- Speakers: {', '.join(DISPLAY.values())}  |  timestamps = each part's own video time",
      "- A screen marker line shows what is on screen from that point on; when the",
      "  dialogue points at the screen, open the marker's image file.",
      ""]
out_parts = []
for part, segs in parts.items():
    segs.sort(key=lambda s: s["start"])
    screens = index.get(part, [])
    for seg in segs:
        active = None
        for sc in screens:
            if seg["start"] >= sc["t"]:
                active = sc
            else:
                break
        seg["screen"] = active["frame"] if active else None
    out_parts.append({"part": part, "source": SRC["parts"][part],
                      "screens": screens, "segments": segs})

    turns = []
    for s in segs:
        if turns and turns[-1]["speaker"] == s["speaker"] \
                and s["start"] - turns[-1]["end"] < 3.0 \
                and turns[-1]["screen"] == s["screen"]:
            turns[-1]["text"] += " " + s["text"]
            turns[-1]["end"] = s["end"]
        else:
            turns.append(dict(s))

    dur = segs[-1]["end"] if segs else 0
    md += [f"## {part.upper()} — `{Path(SRC['parts'][part]).name}` ({fmt(dur)})", ""]
    si, emitted = 0, -1
    for t in turns:
        while si < len(screens) and t["start"] >= screens[si]["t"]:
            si += 1
        for k in range(emitted + 1, si):
            sc = screens[k]
            if sc["frame"]:
                md.append(f"> 🖼 [{fmt(sc['t'])}~] `{sc['frame']}` — {sc['desc']}")
            else:
                md.append(f"> ⬜ [{fmt(sc['t'])}~] no screen share — {sc['desc']}")
            md.append("")
        emitted = si - 1
        md.append(f"**[{fmt(t['start'])}] {t['speaker']}**: {t['text']}")
        md.append("")

(W / "transcript.json").write_text(json.dumps(
    {"speakers": DISPLAY, "parts": out_parts}, ensure_ascii=False, indent=1))
(W / "transcript.md").write_text("\n".join(md))
print("wrote transcript.json, transcript.md",
      "(no screen_index.json — markers omitted)" if not index else "")
