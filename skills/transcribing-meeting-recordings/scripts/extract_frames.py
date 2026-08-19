#!/usr/bin/env python3
"""Extract screen-state frames: scene-change detection + uniform fill.

Usage: extract_frames.py <workspace>
Writes: frames_all/{part}_{MMSS}.jpg

Two-layer coverage because each layer has a validated blind spot:
- scene detection (threshold 0.08) misses SPA page transitions on white
  backgrounds (they score below threshold) and fires hundreds of false
  positives on webcam-only stretches (face motion);
- the 60s uniform fill covers the former; the 10s min-gap collapses the latter.
Frames are grabbed at cut+1s so the new page has rendered. Parts whose source
has no video stream are skipped. After extraction: READ EVERY FRAME and author
work/screen_index.json (see references/pipeline-reference.md).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SRC = json.loads((W / "sources.json").read_text())
OUT = W / "frames_all"
OUT.mkdir(exist_ok=True)
WORK = W / "work"
WORK.mkdir(exist_ok=True)

MIN_GAP, FILL_EVERY, FILL_RADIUS, OFFSET = 10.0, 60, 25, 1.0


def has_video(src):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v",
                        "-show_entries", "stream=codec_type", "-of", "csv=p=0", src],
                       capture_output=True, text=True)
    return "video" in r.stdout


def duration(src):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", src], capture_output=True, text=True)
    return float(r.stdout.strip())


def grab(src, part, t):
    mm, ss = int(t // 60), int(t % 60)
    out = OUT / f"{part}_{mm:02d}{ss:02d}.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(round(t, 2)),
                    "-i", src, "-frames:v", "1", "-q:v", "3", str(out)], check=True)


for part, src in SRC["parts"].items():
    if not has_video(src):
        print(f"{part}: no video stream, skipped")
        continue
    scenes_txt = WORK / f"scenes_{part}.txt"
    if not scenes_txt.exists():  # full decode — slow; resume-safe
        subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf",
                        f"select='gt(scene,0.08)',metadata=print:file={scenes_txt}",
                        "-f", "null", "-"], check=True)
    times = [float(m) for m in re.findall(r"pts_time:([\d.]+)", scenes_txt.read_text())]
    kept, last = [], -1e9
    for t in times:
        if t - last >= MIN_GAP:
            kept.append(t + OFFSET)
            last = t
    dur = duration(src)
    for t in range(30, int(dur) - 5, FILL_EVERY):
        if not any(abs(t - k) < FILL_RADIUS for k in kept):
            kept.append(float(t))
    for t in sorted(kept):
        grab(src, part, t)
    print(f"{part}: {len(times)} scene candidates -> {len(kept)} frames")
