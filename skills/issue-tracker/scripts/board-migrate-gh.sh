#!/usr/bin/env bash
# board-migrate-gh.sh — one-shot v6→v7 migration: push a legacy board.json's
# knowledge into GitHub, after which GitHub is the only board store.
#
# Usage:
#   board-migrate-gh.sh [--board FILE] [--apply]
#
#   --board  legacy board.json (default doperpowers/issue-tracker/board.json)
#   --apply  execute; without it this is a read-only dry-run plan
#
# Per linked ticket (a `gh` field): sets the status:* label / close reason,
# creates missing sub-issue (parent) + dependency (blocked_by) edges, and
# writes the board:meta block (spawned-by / relates-to / branch / pr / note).
# Unlinked tickets are created as new issues. Ticket-md pre-spec content is
# appended to the issue body once (marker-guarded), when it says more than the
# empty skeleton.
#
# Conflict policy (reported either way):
#   GH closed  + board open      → GitHub wins (an issue closed is reality)
#   GH open    + board terminal  → board wins (done means landed) — closes it
#   both closed, reasons differ  → report only, no mutation
#
# Afterwards: git rm -r doperpowers/issue-tracker/ (history keeps the legacy
# board) and adopt the v7 SKILL.md rules in the consumer CLAUDE.md.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

board="$BOARD_DIR/board.json" apply=0
while [ $# -gt 0 ]; do
  case "$1" in
    --board) _need_arg "$1" "${2:-}"; board="$2"; shift 2 ;;
    --apply) apply=1; shift ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -f "$board" ] || die "no legacy board at $board"

T_BOARD="$board" T_APPLY="$apply" _py - <<'PY'
import json
import os
import re
import _board as B

env = os.environ
apply = env["T_APPLY"] == "1"
with open(env["T_BOARD"]) as f:
    legacy = json.load(f)["tickets"]
board_dir = os.path.dirname(env["T_BOARD"])
live = B.snapshot()

acted = []
def act(line, fn=None):
    acted.append(line)
    print(("apply " if apply else "plan  ") + line)
    if apply and fn:
        fn()

if apply:
    B.ensure_labels()

# Pass 1 — create issues for unlinked tickets, so every T-ID resolves.
gh_of = {}   # T-ID -> issue number (str)
for tid, n in sorted(legacy.items(), key=lambda kv: int(kv[0][1:])):
    if n.get("gh"):
        gh_of[tid] = str(n["gh"])
for tid, n in sorted(legacy.items(), key=lambda kv: int(kv[0][1:])):
    if tid in gh_of:
        continue
    title = " ".join(str(n["title"]).split())
    def create(n=n, tid=tid, title=title):
        body = ""
        md = os.path.join(board_dir, n.get("md") or "")
        if n.get("md") and os.path.isfile(md):
            with open(md) as f:
                body = re.sub(r"\A---\n.*?\n---\n", "", f.read(), flags=re.S)
        out = B.gh(["issue", "create", "-R", B.repo(), "--title", title,
                    "--label", n.get("category") or "enhancement",
                    "--body-file", "-"], input_text=body or title)
        m = re.search(r"/issues/(\d+)\s*$", out.strip())
        if not m:
            B.die("could not parse created issue for %s" % tid)
        gh_of[tid] = m.group(1)
    act("create issue for %s  %s" % (tid, title), create)
    if not apply:
        gh_of[tid] = "NEW:%s" % tid   # dry-run placeholder for edge planning

def node(num):
    if num.startswith("NEW:"):
        return None
    if num not in live:
        live.update(B.snapshot(refresh=True))
    return live.get(num)

# Pass 2 — states, edges, meta.
for tid, n in sorted(legacy.items(), key=lambda kv: int(kv[0][1:])):
    num = gh_of[tid]
    gn = node(num)
    want = n["state"]
    ref = "%s→#%s" % (tid, num)

    # state
    if gn is None:
        if want != "ready-for-agent":
            act("%s: label new issue status:%s" % (ref, want),
                None)   # applied below only in apply mode via gn refetch — dry-run new issues skip
    else:
        have = gn["state"]
        if have in B.TERMINAL and want not in B.TERMINAL:
            print("note  %s: GitHub already closed (%s), board said %s — GitHub wins" % (ref, have, want))
        elif have in B.TERMINAL and want in B.TERMINAL and have != want:
            print("note  %s: closed as %s but board said %s — left as-is, human call" % (ref, have, want))
        elif have not in B.TERMINAL and want in B.TERMINAL:
            act("%s: close as %s (board terminal wins)" % (ref, want),
                lambda num=num, gn=gn, want=want: (
                    B.edit_labels(num, remove=[B.STATUS_PREFIX + s for s in gn["status_labels"]]),
                    B.close(num, want)))
        elif have != want:
            # Happy-path progression: GitHub-side automation (assign→in-progress,
            # PR→in-review) is what the legacy board historically lagged behind —
            # never downgrade an issue GitHub says is further along. Paused board
            # states (deferred/blocked/needs-info) are deliberate decisions and
            # still win.
            HAPPY = {"ready-for-agent": 0, "in-progress": 1, "in-review": 2}
            if want in HAPPY and have in HAPPY and HAPPY[have] > HAPPY[want]:
                print("note  %s: GitHub is further along (%s > board %s) — GitHub wins, label kept"
                      % (ref, have, want))
            else:
                act("%s: status label → %s (was %s)" % (ref, want, have),
                    lambda num=num, gn=gn, want=want: B.set_state_label(num, gn, want))

    # edges (only for live nodes on both ends)
    if gn is not None:
        pgh = gh_of.get(n.get("parent") or "")
        if n.get("parent") and pgh and not pgh.startswith("NEW:"):
            if gn.get("parent") != pgh:
                pn = node(pgh)
                if pn is not None:
                    act("%s: parent → #%s" % (ref, pgh),
                        lambda gn=gn, pn=pn: B.add_sub_issue(pn, gn, replace=bool(gn.get("parent"))))
        for b in n.get("blocked_by") or []:
            bgh = gh_of.get(b)
            if not bgh or bgh.startswith("NEW:"):
                continue
            if bgh not in gn["blocked_by"]:
                bn = node(bgh)
                if bn is not None:
                    act("%s: blocked_by += #%s" % (ref, bgh),
                        lambda gn=gn, bn=bn: B.add_blocked_by(gn, bn))

        # meta block + md pre-spec content
        meta = {}
        sb = gh_of.get(n.get("spawned_by") or "")
        if sb and not sb.startswith("NEW:"):
            meta["spawned-by"] = "#" + sb
        rel = [gh_of[r] for r in (n.get("relates_to") or [])
               if r in gh_of and not gh_of[r].startswith("NEW:")]
        if rel:
            meta["relates-to"] = " ".join("#" + r for r in rel)
        if n.get("branch"):
            meta["branch"] = n["branch"]
        if n.get("pr"):
            meta["pr"] = n["pr"]
        if n.get("note"):
            meta["note"] = " ".join(str(n["note"]).split())
        have_meta = B.parse_meta(gn["body"])
        want_meta = dict(have_meta)
        want_meta.update(meta)

        append = ""
        MARK = "## Board pre-spec (migrated)"
        md = os.path.join(board_dir, n.get("md") or "")
        if n.get("md") and os.path.isfile(md) and MARK not in gn["body"]:
            with open(md) as f:
                content = re.sub(r"\A---\n.*?\n---\n", "", f.read(), flags=re.S).strip()
            # skip skeletons: headers/blank lines only says nothing
            meat = [l for l in content.splitlines()
                    if l.strip() and not l.startswith("#") and l.strip() != "_(pre-spec: fill in)_"]
            if len(meat) >= 3:
                append = "\n\n%s\n\n%s" % (MARK, content)

        if want_meta != have_meta or append:
            what = []
            if want_meta != have_meta:
                what.append("meta{%s}" % ",".join(sorted(set(meta))))
            if append:
                what.append("pre-spec md")
            def write_body(num=num, gn=gn, want_meta=want_meta, append=append):
                base = B.META_RE.sub("", gn["body"] or "").rstrip("\n")
                B.set_body(num, B.render_body(base + append, want_meta))
            act("%s: body += %s" % (ref, " + ".join(what)), write_body)

print("%s: %d action(s)%s" % ("migrated" if apply else "dry-run",
                              len(acted), "" if apply else " — re-run with --apply"))
if not apply and any(v.startswith("NEW:") for v in gh_of.values()):
    print("note: dry-run cannot plan states/edges for to-be-created issues — they apply on --apply")

# Untracked open issues (no board ticket points at them): name them; human labels or closes.
linked = {v for v in gh_of.values() if not v.startswith("NEW:")}
for num in sorted(live, key=int):
    if num not in linked and live[num]["state"] == B.UNTRACKED:
        print("untracked open issue #%s: %s — board-transition.sh %s <state> (or close it)"
              % (num, " ".join(live[num]["title"].split()), num))
PY
