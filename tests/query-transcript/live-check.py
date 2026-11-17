#!/usr/bin/env python3
"""Live check of query-transcript (real haiku calls, about $0.15; not in a gate).

    live-check.py <transcript>

Puts the design spike's known-answer questions to segment 0 of the transcript
the caller names: the owner's CI-opt session of 2026-10-15
(a45b97a3-375e-4b0c-a46e-a6659b76e229), which lives on the MacBook only. It
checks the known answers, that quotes come back checked and stamped, and that
the run leaves nothing in the work directory's project folder.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = """\
1. In the human's short follow-up message about Mac overload, what cause did they give for the overload?
2. The human rejected a fixed monthly cost for a CI server as a burden. What was the amount and currency, \
and what alternative did they ask about?
3. What is the exact task id carried by the FIRST task-notification in this conversation?
4. To the question about which thing "프로젝트별 CI 설정 시스템" referred to, which option did the human pick?
5. Did the session run `gh pr create` at any point so far? If yes, quote the command."""
KNOWN = [("the first task-notification's id", r"abfb63cb3b678267d"),
         ("the option the human picked", r"공용 CI 킷"),
         ("the rejected monthly cost", r"200\s*(유로|euro|EUR|€)")]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    work = os.path.realpath(os.path.expanduser("~/.cache/query-transcript/work"))
    folder = Path(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")) / "projects" / \
        re.sub(r"[^A-Za-z0-9]", "-", work)
    p = subprocess.run([str(ROOT / "bin" / "query-transcript"), sys.argv[1], QUESTIONS, "--segment", "0", "--json"],
                       capture_output=True, text=True)
    failures = []
    if p.returncode != 0:
        sys.exit("FAIL: exit %d\n%s%s" % (p.returncode, p.stdout, p.stderr))
    seg = json.loads(p.stdout)["segments"][0]
    print(seg["answer"], "\n")
    for q in seg["quotes"]:
        print("  %s  %s" % ("%s %s" % (q["time"], q["kind"]) if q["found"] else "NOT FOUND", q["quote"][:100]))
    u = seg["usage"]
    print("\nvia %s · %s in · %s out · $%s · %s s\n" % (u["model"], u["input"], u["output"], u["cost"], u["seconds"]))
    for what, pattern in KNOWN:
        if not re.search(pattern, seg["answer"]):
            failures.append("the answer misses %s (%s)" % (what, pattern))
    found = [q for q in seg["quotes"] if q["found"]]
    if not found:
        failures.append("no quote was found in the record")
    if any(not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", q["time"]) for q in found):
        failures.append("a found quote has no time")
    left = sorted(os.listdir(folder)) if folder.exists() else []
    if left:
        failures.append("left in %s: %s" % (folder, left))
    for f in failures:
        print("FAIL: " + f)
    print("PASS" if not failures else "FAILED (%d)" % len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
