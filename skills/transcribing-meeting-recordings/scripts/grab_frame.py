#!/usr/bin/env python3
"""Extract one video frame at a transcript timestamp.

Usage: grab_frame.py <workspace> <part> <seconds|h:mm:ss> [out.jpg]
Transcript timestamps ARE video timestamps (no offset), per part.
"""
import json
import subprocess
import sys
from pathlib import Path

W = Path(sys.argv[1]).resolve()
part, t = sys.argv[2], sys.argv[3]
src = json.loads((W / "sources.json").read_text())["parts"][part]
out = sys.argv[4] if len(sys.argv) > 4 else f"frame_{part}_{t.replace(':', '-')}.jpg"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", t, "-i", src,
                "-frames:v", "1", "-q:v", "2", out], check=True)
print(out)
