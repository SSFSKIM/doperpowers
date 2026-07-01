#!/usr/bin/env bash
# daemon-list.sh [status]
#
# Print the fleet: every daemon in the registry, newest activity first. Optional
# arg filters by status (e.g. `daemon-list.sh awaiting-human`). This is YOUR
# tracking view and the one to show the human when they ask "what's running".

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"

DAEMON_HOME="$DAEMON_HOME" python3 - "${1:-}" <<'PY'
import glob, json, os, sys
home = os.environ["DAEMON_HOME"]
want = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None

rows = []
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if want and m.get("status") != want:
        continue
    uuid = m.get("uuid", "")
    reply = ""
    rp = os.path.join(home, f"{uuid}.reply.txt")
    if os.path.exists(rp):
        try:
            reply = " ".join(open(rp).read().split())
        except Exception:
            pass
    rows.append((m.get("updated", ""), m.get("name", "?"), uuid, m.get("status", "?"),
                 m.get("turns", "0"), reply))

rows.sort(reverse=True)
if not rows:
    print("(no daemons)"); raise SystemExit

print(f"{'NAME':<18} {'SHORT':<9} {'STATUS':<14} {'T':>2}  LATEST REPLY")
print("-" * 96)
for updated, name, uuid, status, turns, reply in rows:
    print(f"{name[:18]:<18} {uuid[:8]:<9} {status:<14} {str(turns):>2}  {reply[:52]}")
print()
print("full uuid + reply:  daemon-reply.sh <short-or-full-uuid>")
PY
