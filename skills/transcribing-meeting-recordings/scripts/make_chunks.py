#!/usr/bin/env python3
"""Extract 16k mono audio per part and cut silence-aligned ~10-min mp3 chunks.

Usage: make_chunks.py <workspace>
  <workspace>/sources.json: {"parts": {"p1": "/abs/video-or-audio", ...},
                             "speakers": {"api_id": "Display Name", ...}}
Writes: work/{part}_16k.wav, chunks/{part}_c{NN}.mp3, chunks/manifest.json

Chunk size exists for the 25MB upload limit and parallelism (10 min @ 64kbps
mono MP3 ~= 5MB). Boundaries land on the quietest 300ms within +/-25s of each
10-min mark so no word is split. No overlap: identical named reference clips
passed to every chunk make speaker labels coherent across chunks.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

TARGET, SEARCH = 600.0, 25.0  # 10-min chunks, +/-25s boundary search

W = Path(sys.argv[1]).resolve()
SRC = json.loads((W / "sources.json").read_text())
WORK, CHUNKS = W / "work", W / "chunks"
WORK.mkdir(exist_ok=True)
CHUNKS.mkdir(exist_ok=True)

manifest = []
for part, src in SRC["parts"].items():
    wav = WORK / f"{part}_16k.wav"
    if not wav.exists():
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", src,
             "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
    y, sr = sf.read(wav, dtype="float32")
    total = len(y) / sr
    hop = int(sr * 0.05)  # 50ms RMS frames
    n = len(y) // hop
    rms = np.sqrt(np.mean(y[: n * hop].reshape(n, hop) ** 2, axis=1))

    bounds, t = [0.0], TARGET
    while t < total - 120:  # avoid a tiny trailing chunk
        lo, hi = int((t - SEARCH) / 0.05), int((t + SEARCH) / 0.05)
        k = 6  # quietest 300ms stretch
        sums = np.convolve(rms[lo:hi], np.ones(k), "valid")
        cut = (lo + int(np.argmin(sums)) + k / 2) * 0.05
        bounds.append(round(cut, 2))
        t = cut + TARGET
    bounds.append(round(total, 2))

    for i in range(len(bounds) - 1):
        s, e = bounds[i], bounds[i + 1]
        out = CHUNKS / f"{part}_c{i:02d}.mp3"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", str(s), "-to", str(e),
             "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "64k", str(out)],
            check=True)
        manifest.append({"file": out.name, "part": part, "start": s, "end": e})
    print(f"{part}: {total:.1f}s -> {len(bounds) - 1} chunks {bounds}")

(CHUNKS / "manifest.json").write_text(json.dumps(manifest, indent=2))
print("total chunks:", len(manifest))
