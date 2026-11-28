#!/usr/bin/env python3
"""Fail when a tracked CLAUDE.md exceeds its word budget.

Every session and subagent that touches a directory reads its CLAUDE.md
whole, so each word is paid by work that has nothing to do with it. The
budget is the owner's (1,500 words, root and nested alike; 2026-11-28).
Words are counted as `wc -w` does: runs of non-whitespace.

Usage: scripts/check-claudemd-budget.py [repo-root]   (default: this checkout)
"""
import pathlib
import subprocess
import sys

BUDGET = 1500

# Files over budget when the check landed, each held at its count then so it
# cannot grow while the branch that brings it under budget is in flight.
# An entry whose file is at or under budget fails the check: remove it, or the
# file could grow back to its old allowance unnoticed.
ALLOWANCE_DATE = "2026-11-28"
ALLOWANCE = {
    "sminos/hooks/mods/CLAUDE.md": 6045,
    "sminos/skills/manager/scripts/CLAUDE.md": 3176,
    "sminos/skills/sminos/scripts/CLAUDE.md": 44454,
    "task/CLAUDE.md": 1628,
    "to-human/CLAUDE.md": 4380,
}

WHERE = (
    "A CLAUDE.md holds what a session needs before it reads the code and cannot get\n"
    "from it: what is there and where, invariants and traps with their reason, commands\n"
    "that are not discoverable, conventions binding work there. How a feature works\n"
    "belongs in its code and docstrings, why it was designed so in its spec, how it came\n"
    "to be and what was measured in git. Move a fact whose only copy is the CLAUDE.md\n"
    "there before cutting it (root CLAUDE.md, \"CLAUDE.md files hold what the code\n"
    "cannot tell\")."
)


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent)
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", "CLAUDE.md", "**/CLAUDE.md"],
        check=True, capture_output=True,
    ).stdout.decode().split("\0")
    over, stale = [], []
    for rel in sorted(p for p in listed if p):
        path = root / rel
        if not path.is_file():
            continue
        words = len(path.read_text(encoding="utf-8", errors="replace").split())
        ceiling = ALLOWANCE.get(rel)
        if ceiling is not None and words <= BUDGET:
            stale.append(f"{rel}: {words} words, within the {BUDGET}-word budget; remove its entry from ALLOWANCE in scripts/check-claudemd-budget.py")
        elif ceiling is not None and words > ceiling:
            over.append(f"{rel}: {words} words, over its {ALLOWANCE_DATE} allowance of {ceiling} (budget {BUDGET})")
        elif ceiling is None and words > BUDGET:
            over.append(f"{rel}: {words} words, over the {BUDGET}-word budget")
    if over or stale:
        for line in over + stale:
            print(f"FAIL {line}")
        if over:
            print()
            print(WHERE)
        return 1
    print(f"every tracked CLAUDE.md is within its budget ({BUDGET} words; {len(ALLOWANCE)} allowance(s) in force)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
