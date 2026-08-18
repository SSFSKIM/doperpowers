#!/usr/bin/env python3
"""Find the time offset of one recording within another (audio<->video sync).

Usage: sync_offset.py <file_a> <file_b>
Prints the offset of B's start within A's timeline, with confidence signals.
Only needed when transcribing a track other than the video's own audio —
prefer the video's own track (see SKILL.md Source prep).

Method: 20ms RMS envelopes on 4kHz mono downsamples, FFT cross-correlation.
Trust it only if the peak clearly separates from the runner-up AND head/tail
window offsets agree within ~0.2s per hour (drift check).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


def envelope(path, hop_s=0.02):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path),
                        "-vn", "-ac", "1", "-ar", "4000", tmp.name], check=True)
        y, sr = sf.read(tmp.name, dtype="float32")
    Path(tmp.name).unlink()
    step = int(sr * hop_s)
    n = len(y) // step
    e = np.sqrt(np.mean(y[: n * step].reshape(n, step) ** 2, axis=1))
    return (e - e.mean()) / (e.std() + 1e-9)


def best_lag(a, b):  # lag of b within a, in hops
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    corr = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)))
    corr = np.concatenate([corr[-len(b) + 1:], corr[: len(a)]])
    i = int(np.argmax(corr))
    peak = corr[i]
    corr[max(0, i - 250): i + 250] = -np.inf  # blank +/-5s around peak
    runner = float(np.max(corr))
    return i - (len(b) - 1), float(peak), runner


a, b = envelope(sys.argv[1]), envelope(sys.argv[2])
lag, peak, runner = best_lag(a, b)
offset = lag * 0.02
print(f"B starts at A t={offset:+.2f}s  (peak/runner-up ratio "
      f"{peak / max(abs(runner), 1e-9):.2f} — want clearly > 1)")

# drift check: head vs tail windows of B
win = min(len(b) // 3, int(600 / 0.02))
for name, seg, base in (("head", b[:win], 0), ("tail", b[-win:], (len(b) - win) * 0.02)):
    l2, _, _ = best_lag(a, seg)
    print(f"{name}: offset {l2 * 0.02 - base:+.2f}s")
print("head/tail should agree within ~0.2s per hour of audio")
