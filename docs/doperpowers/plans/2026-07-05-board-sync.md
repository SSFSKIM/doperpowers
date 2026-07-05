# board-sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the foundation and **Layer 1 (state + close-reason)** of board-sync — a deterministic toolkit plus a `board-sync` subagent that reconciles the local issue board with a repo's GitHub issues, closing the drift the substrate deferred.

**Architecture:** A thin judgment layer (the `board-sync` subagent) over deterministic scripts. `board-gh-plan.sh` computes a pure diff against a `.sync-state.json` watermark; the agent judges only conflicts/ambiguity; `board-gh-apply.sh` applies the unambiguous actions through the existing `board-transition.sh` (board side) and `gh` (GitHub side), then refreshes the watermark. The board's single-writer rule and state machine are untouched — every board write goes through a script.

**Tech Stack:** bash + inline `python3` (stdlib only), atomic writes (tmp + `os.replace`), `gh` CLI, the existing `skills/issue-tracker/scripts/` toolkit, a Claude Code plugin subagent + slash command, `CronCreate` for scheduling.

## Global Constraints

- Scripts live in `skills/issue-tracker/scripts/` and follow the house pattern verbatim: `set -euo pipefail`; `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"`; `. "$SCRIPT_DIR/_lib.sh"`; option parsing with `_need_arg`; a `T_*`-env + `_py - <<'PY'` heredoc that loads `map.json`, mutates, writes atomically (tmp then `os.replace`), appends to `log.jsonl`; and a trailing `board-map.sh --write` re-render (non-fatal).
- **Never hand-edit `map.json`.** All board mutations go through scripts. All GitHub mutations go through `gh`.
- Scripts must **refuse to run from a worktree** — this is inherited free by sourcing `_lib.sh` (`_board_root`).
- New node fields (`gh`, `labels`) are **optional and additive**: readers must use `.get(...)`, and boards written before this change must load unchanged. `map.json` `version` stays `1` (no migration).
- Commit messages use the repo's lowercase `area: summary` style (e.g. `issue-tracker: …`). No `Co-Authored-By` / attribution lines.
- Tests are **hermetic** (no network, no `claude` CLI): a throwaway git repo, fixture JSON fed to scripts via `--gh-json`, and `--dry-run` on the apply path. New board-sync tests go in a **new file** `tests/issue-tracker/test-board-gh-sync.sh` (do **not** edit the in-progress `test-board-scripts.sh`).
- Coarse-state mapping (the whole of Layer 1): board `done` ↔ GitHub `closed`/`completed`; board `wontfix` ↔ `closed`/`not_planned`; every other board state ↔ GitHub `open`. The fine state is board-only and is never inferred from GitHub.

---

### Task 1: Additive node fields (`gh`, `labels`) at registration

New tickets carry `gh: null` and `labels: []`; existing boards without the fields still load. This is the smallest change that lets every later task assume the fields exist on freshly-registered tickets.

**Files:**
- Modify: `skills/issue-tracker/scripts/board-register.sh:71-77` (the `tickets[tid] = {...}` literal)
- Test: `tests/issue-tracker/test-board-gh-sync.sh` (new file)

**Interfaces:**
- Produces: every node registered after this task has keys `gh` (int|null, default null) and `labels` (string[], default []).

- [ ] **Step 1: Write the failing test** — create `tests/issue-tracker/test-board-gh-sync.sh` with the harness preamble copied from `test-board-scripts.sh:9-52` (the `set -euo pipefail`, `pass/fail/assert_*`, throwaway repo, `run()` helper), then this first case:

```bash
echo "board-register (sync fields):"
out="$(run board-register.sh "First ticket" enhancement)"
tid="$(printf '%s' "$out" | awk '{print $1}')"
gh="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['$tid'].get('gh','MISSING'))")"
assert_equals "$gh" "None" "new ticket has gh field defaulting to null"
labels="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['$tid'].get('labels','MISSING'))")"
assert_equals "$labels" "[]" "new ticket has labels field defaulting to []"
```

End the file with the summary block from `test-board-scripts.sh:553-556`. `chmod +x` it.

- [ ] **Step 2: Run it to see it fail**

Run: `bash tests/issue-tracker/test-board-gh-sync.sh`
Expected: FAIL — `gh` is `MISSING` (field not written yet).

- [ ] **Step 3: Add the two fields to the node literal** in `board-register.sh`, extending the dict at lines 71-77:

```python
tickets[tid] = {
    "title": title, "md": md, "state": state, "category": category,
    "note": note or None, "parent": parent or None,
    "blocked_by": blocked, "spawned_by": spawned or None, "relates_to": [],
    "branch": None, "pr": None, "gh": None, "labels": [],
    "created": env["T_TODAY"], "updated": env["T_TODAY"],
}
```

- [ ] **Step 4: Run it to see it pass**

Run: `bash tests/issue-tracker/test-board-gh-sync.sh`
Expected: PASS (both assertions).

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-register.sh tests/issue-tracker/test-board-gh-sync.sh
git commit -m "issue-tracker: register writes additive gh/labels node fields"
```

---

### Task 2: `board-meta.sh` — deterministic writer for `gh` + `labels[]`

The invariant-safe writer board-sync uses for the non-state fields. Same shape as `board-edge.sh`: atomic write, log with a `"meta"` key, re-render.

**Files:**
- Create: `skills/issue-tracker/scripts/board-meta.sh`
- Test: `tests/issue-tracker/test-board-gh-sync.sh`

**Interfaces:**
- Produces: `board-meta.sh <id> [--gh N] [--add-label L]… [--rm-label L]…` — sets `gh` (int; `0` clears to null), adds/removes free labels (idempotent), bumps `updated`, appends one `{"ts","ticket","meta":<field>,"op","value"}` line per change to `log.jsonl`.

- [ ] **Step 1: Write the failing tests** — append to `test-board-gh-sync.sh`:

```bash
echo "board-meta:"
run board-register.sh "Meta target" enhancement >/dev/null           # next Tn
tid="$(run board-list.sh | grep 'Meta target' | awk '{print $1}')"
out="$(run board-meta.sh "$tid" --gh 42)"
assert_contains "$out" "$tid: gh = 42" "meta sets gh"
gh="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['$tid']['gh'])")"
assert_equals "$gh" "42" "gh written as integer"
run board-meta.sh "$tid" --add-label P0 --add-label size:M >/dev/null
run board-meta.sh "$tid" --add-label P0 >/dev/null                    # idempotent
labels="$(python3 -c "import json;print(','.join(json.load(open('$BOARD/map.json'))['tickets']['$tid']['labels']))")"
assert_equals "$labels" "P0,size:M" "labels added once, order preserved"
run board-meta.sh "$tid" --rm-label P0 >/dev/null
labels="$(python3 -c "import json;print(','.join(json.load(open('$BOARD/map.json'))['tickets']['$tid']['labels']))")"
assert_equals "$labels" "size:M" "label removed"
run board-meta.sh "$tid" --gh 0 >/dev/null
gh="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['$tid']['gh'])")"
assert_equals "$gh" "None" "gh 0 clears the link"
assert_fails run board-meta.sh T999 --gh 1                            # unknown ticket
assert_fails run board-meta.sh "$tid" --gh notanumber                # non-integer
```

- [ ] **Step 2: Run to see it fail**

Run: `bash tests/issue-tracker/test-board-gh-sync.sh`
Expected: FAIL — `board-meta.sh` does not exist.

- [ ] **Step 3: Create `skills/issue-tracker/scripts/board-meta.sh`:**

```bash
#!/usr/bin/env bash
# board-meta.sh — set a ticket's sync metadata: the GitHub link and free labels.
#
# Usage:
#   board-meta.sh <id> --gh N          link the GitHub issue number (0 clears)
#   board-meta.sh <id> --add-label L   add a free label (repeatable, idempotent)
#   board-meta.sh <id> --rm-label L    remove a free label (repeatable)
#
# The fields board-sync reconciles. Kept behind a script — not hand edits — so
# writes stay atomic and BOARD.* re-renders, exactly like board-transition/edge.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
tid="$1"; shift
gh="" adds="" rms=""
while [ $# -gt 0 ]; do
  case "$1" in
    --gh) _need_arg "$1" "${2:-}"; gh="$2"; shift 2 ;;
    --add-label) _need_arg "$1" "${2:-}"; adds="$adds${adds:+,}$2"; shift 2 ;;
    --rm-label) _need_arg "$1" "${2:-}"; rms="$rms${rms:+,}$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_ID="$tid" T_GH="$gh" T_ADDS="$adds" T_RMS="$rms" \
T_NOW="$(_now)" T_TODAY="$(_today)" _py - <<'PY'
import json, os, sys

def die(m): sys.stderr.write("error: %s\n" % m); sys.exit(1)

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
tid = env["T_ID"]
if tid not in tickets:
    die("unknown ticket: %s" % tid)
n = tickets[tid]
log = []

gh = env["T_GH"]
if gh != "":
    try:
        v = int(gh)
    except ValueError:
        die("--gh must be an integer issue number (0 to clear)")
    n["gh"] = None if v == 0 else v
    log.append({"ts": env["T_NOW"], "ticket": tid, "meta": "gh", "op": "set", "value": n["gh"]})

labels = list(n.get("labels") or [])
for l in [x for x in env["T_ADDS"].split(",") if x]:
    if l not in labels:
        labels.append(l)
        log.append({"ts": env["T_NOW"], "ticket": tid, "meta": "labels", "op": "add", "value": l})
for l in [x for x in env["T_RMS"].split(",") if x]:
    if l in labels:
        labels.remove(l)
        log.append({"ts": env["T_NOW"], "ticket": tid, "meta": "labels", "op": "rm", "value": l})
n["labels"] = labels
n["updated"] = env["T_TODAY"]

tmp = env["BOARD_MAP"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(board, f, indent=2); f.write("\n")
os.replace(tmp, env["BOARD_MAP"])
with open(env["BOARD_LOG"], "a") as f:
    for e in log:
        f.write(json.dumps(e) + "\n")
for e in log:
    print("%s: %s %s %s" % (tid, e["meta"], "=" if e["meta"] == "gh" else ("+=" if e["op"] == "add" else "-="), e["value"]))
PY

# BOARD.md is a pure render cache — refresh it on every board write. Non-fatal.
"$SCRIPT_DIR/board-map.sh" --write >/dev/null 2>&1 \
  || echo "warning: BOARD.md refresh failed (board-map.sh)" >&2
```

`chmod +x skills/issue-tracker/scripts/board-meta.sh`.

- [ ] **Step 4: Run to see it pass**

Run: `bash tests/issue-tracker/test-board-gh-sync.sh`
Expected: PASS (all board-meta assertions).

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-meta.sh tests/issue-tracker/test-board-gh-sync.sh
git commit -m "issue-tracker: board-meta.sh writes gh link + free labels"
```

---

### Task 3: `board-link.sh` — `--gh` sugar + one-time title backfill

Populates the `gh` field for the boards that predate it, by parsing the `(GH#NN)` marker every ticket already carries in its title.

**Files:**
- Create: `skills/issue-tracker/scripts/board-link.sh`
- Test: `tests/issue-tracker/test-board-gh-sync.sh`

**Interfaces:**
- Consumes: `board-meta.sh` (delegated to for `--gh`).
- Produces: `board-link.sh <id> --gh N` (sugar); `board-link.sh --backfill` (parse `GH#(\d+)` from each title into `gh`, only where `gh` is unset; prints one line per filled ticket + a count).

- [ ] **Step 1: Write the failing tests** — append:

```bash
echo "board-link (backfill):"
run board-register.sh "Legacy epic (GH#35)" enhancement >/dev/null
run board-register.sh "No marker here" bug >/dev/null
out="$(run board-link.sh --backfill)"
assert_contains "$out" "gh = 35 (from title)" "backfill parses GH#NN from title"
n="$(python3 -c "import json;t=json.load(open('$BOARD/map.json'))['tickets'];print(sum(1 for x in t.values() if x.get('gh')==35))")"
assert_equals "$n" "1" "exactly one ticket linked to #35"
# a ticket without a marker stays unlinked
un="$(python3 -c "import json;t=json.load(open('$BOARD/map.json'))['tickets'];print([x['gh'] for x in t.values() if x['title']=='No marker here'][0])")"
assert_equals "$un" "None" "markerless ticket stays unlinked"
# re-running backfill does not overwrite an existing link
run board-link.sh --backfill >/dev/null
```

- [ ] **Step 2: Run to see it fail**

Run: `bash tests/issue-tracker/test-board-gh-sync.sh`
Expected: FAIL — `board-link.sh` does not exist.

- [ ] **Step 3: Create `skills/issue-tracker/scripts/board-link.sh`:**

```bash
#!/usr/bin/env bash
# board-link.sh — link a ticket to its GitHub issue, or backfill links from titles.
#
# Usage:
#   board-link.sh <id> --gh N     set the ticket's GitHub issue number
#   board-link.sh --backfill      one-time: parse "(GH#NN)" from every title → gh
#                                  (only where gh is unset; never overwrites)
#
# After --backfill the board never depends on title text again.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 1 ] || { usage_from_header "$0" >&2; exit 2; }
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

if [ "$1" = "--backfill" ]; then
  T_NOW="$(_now)" T_TODAY="$(_today)" _py - <<'PY'
import json, os, re
env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
filled = 0
for tid in sorted(board["tickets"], key=lambda k: int(k[1:])):
    t = board["tickets"][tid]
    if t.get("gh"):
        continue
    m = re.search(r"GH#(\d+)", t.get("title", ""))
    if m:
        t["gh"] = int(m.group(1)); t["updated"] = env["T_TODAY"]; filled += 1
        print("%s: gh = %d (from title)" % (tid, t["gh"]))
tmp = env["BOARD_MAP"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(board, f, indent=2); f.write("\n")
os.replace(tmp, env["BOARD_MAP"])
print("backfilled %d ticket(s)" % filled)
PY
  "$SCRIPT_DIR/board-map.sh" --write >/dev/null 2>&1 \
    || echo "warning: BOARD.md refresh failed (board-map.sh)" >&2
  exit 0
fi

# else: <id> --gh N — delegate to board-meta
tid="$1"; shift
[ "${1:-}" = "--gh" ] || { usage_from_header "$0" >&2; exit 2; }
_need_arg "$1" "${2:-}"
exec "$SCRIPT_DIR/board-meta.sh" "$tid" --gh "$2"
```

`chmod +x skills/issue-tracker/scripts/board-link.sh`.

- [ ] **Step 4: Run to see it pass**

Run: `bash tests/issue-tracker/test-board-gh-sync.sh`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-link.sh tests/issue-tracker/test-board-gh-sync.sh
git commit -m "issue-tracker: board-link.sh — gh sugar + one-time title backfill"
```

---

### Task 4: `board-gh-plan.sh` — the deterministic state diff

The heart of board-sync: a pure function of (`map.json`, GitHub issue JSON, `.sync-state.json`) → a reconcile plan. No mutation. The `--gh-json` seam makes it hermetically testable.

**Files:**
- Create: `skills/issue-tracker/scripts/board-gh-plan.sh`
- Test: `tests/issue-tracker/test-board-gh-sync.sh`

**Interfaces:**
- Consumes: `map.json`; GitHub issues as `[{number,state,stateReason,labels,body,title}]` via `--gh-json FILE` / stdin / `gh issue list`; `.sync-state.json` (`{tickets:{Tn:{gh,state,...}}}`).
- Produces: JSON plan on stdout —
  `{"actions":[{ticket,gh,facet:"state",direction?,auto,target_board?|target_gh?,board,gh_state?,watermark?,conflict?,reason}], "unlinked_board":[Tn], "unlinked_gh":[num]}`.
  Action semantics: `auto:true` + no `conflict` ⇒ apply-able; `board->gh` carries `target_gh:[state,reason]`; `gh->board` carries `target_board:[state,note]` (may be `null` when reported).

- [ ] **Step 1: Write the failing tests** — append. These build a small board, write fixtures, and assert the emitted plan:

```bash
echo "board-gh-plan:"
# scratch board: 4 tickets, drive states, link to issues
run board-register.sh "Completion push" enhancement >/dev/null        # A
A="$(run board-list.sh | grep 'Completion push' | awk '{print $1}')"
run board-transition.sh "$A" in-progress >/dev/null
run board-transition.sh "$A" done >/dev/null                          # board done, issue still open
run board-meta.sh "$A" --gh 101 >/dev/null
run board-register.sh "GH closed it" enhancement >/dev/null           # B
B="$(run board-list.sh | grep 'GH closed it' | awk '{print $1}')"
run board-transition.sh "$B" in-progress >/dev/null                   # done-reachable
run board-meta.sh "$B" --gh 102 >/dev/null
run board-register.sh "Already agree" enhancement >/dev/null          # C  (open ↔ open)
C="$(run board-list.sh | grep 'Already agree' | awk '{print $1}')"
run board-meta.sh "$C" --gh 103 >/dev/null
run board-register.sh "Unlinked local" bug >/dev/null                 # D  (no gh)
D="$(run board-list.sh | grep 'Unlinked local' | awk '{print $1}')"

cat > "$TEST_ROOT/gh.json" <<JSON
[ {"number":101,"state":"OPEN","stateReason":null,"labels":[],"body":"","title":"x"},
  {"number":102,"state":"CLOSED","stateReason":"not_planned","labels":[],"body":"","title":"y"},
  {"number":103,"state":"OPEN","stateReason":null,"labels":[],"body":"","title":"z"},
  {"number":900,"state":"OPEN","stateReason":null,"labels":[],"body":"","title":"orphan"} ]
JSON
# empty watermark → C already agrees (no action); A/B each moved on one side only
: > "$BOARD/.sync-state.json"; echo '{"version":1,"tickets":{}}' > "$BOARD/.sync-state.json"
python3 - "$BOARD/.sync-state.json" "$A" "$B" "$C" <<'PY'
import json,sys
p,A,B,C=sys.argv[1:5]
d=json.load(open(p))
d["tickets"]={A:{"gh":101,"state":"in-progress"},B:{"gh":102,"state":"in-progress"},C:{"gh":103,"state":"ready-for-agent"}}
json.dump(d,open(p,"w"))
PY
plan="$(run board-gh-plan.sh --gh-json "$TEST_ROOT/gh.json")"
assert_contains "$plan" "\"ticket\": \"$A\"" "plan includes the board-moved ticket"
printf '%s' "$plan" | python3 -c "import json,sys;p=json.load(sys.stdin);a={x['ticket']:x for x in p['actions']}; import os
A,B,C,D='$A','$B','$C','$D'
assert a[A]['direction']=='board->gh' and a[A]['auto'] and a[A]['target_gh'][0]=='closed', 'A board->gh close'
assert a[B]['direction']=='gh->board' and a[B]['auto'] and a[B]['target_board'][0]=='wontfix', 'B gh->board wontfix'
assert C not in a, 'C already agrees, no action'
assert D in p['unlinked_board'], 'D unlinked_board'
assert 900 in p['unlinked_gh'], 'orphan open issue surfaced'
print('plan-assertions-ok')" && pass "plan diff correct each direction" || fail "plan diff correct each direction"
```

- [ ] **Step 2: Run to see it fail**

Run: `bash tests/issue-tracker/test-board-gh-sync.sh`
Expected: FAIL — `board-gh-plan.sh` does not exist.

- [ ] **Step 3: Create `skills/issue-tracker/scripts/board-gh-plan.sh`:**

```bash
#!/usr/bin/env bash
# board-gh-plan.sh — compute the board↔GitHub reconcile plan (no mutation).
#
# Usage:
#   board-gh-plan.sh [--gh-json FILE]
#
# GitHub issues come from --gh-json FILE, or stdin if piped, else:
#   gh issue list --state all --limit 1000 --json number,state,stateReason,labels,body,title
# Reads .sync-state.json (the last-sync watermark). Emits a JSON plan on stdout.
# Pure: it never writes the board or GitHub.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ -f "$MAP" ] || die "no board at $MAP"

ghjson=""
while [ $# -gt 0 ]; do
  case "$1" in
    --gh-json) _need_arg "$1" "${2:-}"; ghjson="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
if [ -n "$ghjson" ]; then
  GH_SRC="$(cat "$ghjson")"
elif [ ! -t 0 ]; then
  GH_SRC="$(cat)"
else
  GH_SRC="$(gh issue list --state all --limit 1000 \
            --json number,state,stateReason,labels,body,title)"
fi

BOARD_GH="$GH_SRC" BOARD_SYNC="$BOARD_DIR/.sync-state.json" _py - <<'PY'
import json, os
env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
gh = {i["number"]: i for i in json.loads(env["BOARD_GH"] or "[]")}
try:
    with open(env["BOARD_SYNC"]) as f:
        wm = json.load(f).get("tickets", {})
except FileNotFoundError:
    wm = {}

def coarse(state):
    if state == "done":    return ["closed", "completed"]
    if state == "wontfix": return ["closed", "not_planned"]
    return ["open", None]

def gh_coarse(issue):
    if str(issue["state"]).lower() == "closed":
        r = str(issue.get("stateReason") or "completed").lower()
        return ["closed", "not_planned" if r == "not_planned" else "completed"]
    return ["open", None]

DONE_REACHABLE = {"in-progress", "in-review"}
actions, unlinked_board, unlinked_gh = [], [], []
linked = set()

for tid in sorted(tickets, key=lambda k: int(k[1:])):
    n = tickets[tid]
    num = n.get("gh")
    if not num:
        unlinked_board.append(tid); continue
    if num not in gh:
        actions.append({"ticket": tid, "gh": num, "facet": "state", "conflict": True,
                        "auto": False, "board": n["state"], "gh_state": None,
                        "watermark": (wm.get(tid) or {}).get("state"),
                        "reason": "linked issue #%d not found on GitHub" % num})
        continue
    linked.add(num)
    b_c, g_c = coarse(n["state"]), gh_coarse(gh[num])
    w = wm.get(tid)
    w_c = coarse(w["state"]) if w and "state" in w else None
    if b_c == g_c:
        continue  # agree → no action (apply refreshes the watermark)
    b_moved = (w_c is None) or (b_c != w_c)
    g_moved = (w_c is None) or (g_c != w_c)
    if w_c is not None and b_moved and not g_moved:
        actions.append({"ticket": tid, "gh": num, "facet": "state",
                        "direction": "board->gh", "auto": True,
                        "board": n["state"], "gh_state": str(gh[num]["state"]).lower(),
                        "target_gh": b_c, "reason": "board changed"})
    elif w_c is not None and g_moved and not b_moved:
        target, auto, reason = None, True, "github changed"
        if g_c == ["closed", "completed"]:
            if n["state"] in DONE_REACHABLE:
                target = ["done", None]
            else:
                auto = False
                reason = "GitHub closed completed but board is %s (never started)" % n["state"]
        elif g_c == ["closed", "not_planned"]:
            target = ["wontfix", "sync: GitHub closed as not planned"]
        else:  # reopened while board terminal — ambiguous target open state
            auto = False
            reason = "GitHub reopened; board is %s — target open state ambiguous" % n["state"]
        a = {"ticket": tid, "gh": num, "facet": "state", "direction": "gh->board",
             "auto": auto, "board": n["state"], "gh_state": str(gh[num]["state"]).lower(),
             "target_board": target, "reason": reason}
        if not auto:
            a["conflict"] = True
        actions.append(a)
    else:  # both moved and disagree, or first contact with no watermark
        actions.append({"ticket": tid, "gh": num, "facet": "state", "conflict": True,
                        "auto": False, "board": n["state"],
                        "gh_state": str(gh[num]["state"]).lower(),
                        "watermark": (w or {}).get("state"),
                        "reason": "both sides diverged" if w_c is not None
                                  else "first sync: sides disagree"})

for num in sorted(gh):
    if num not in linked and str(gh[num]["state"]).lower() == "open":
        unlinked_gh.append(num)

print(json.dumps({"generated_by": "board-gh-plan", "actions": actions,
                  "unlinked_board": unlinked_board, "unlinked_gh": unlinked_gh},
                 indent=2))
PY
```

`chmod +x skills/issue-tracker/scripts/board-gh-plan.sh`.

- [ ] **Step 4: Run to see it pass**

Run: `bash tests/issue-tracker/test-board-gh-sync.sh`
Expected: PASS (`plan diff correct each direction`).

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-gh-plan.sh tests/issue-tracker/test-board-gh-sync.sh
git commit -m "issue-tracker: board-gh-plan.sh — deterministic state reconcile diff"
```

---

### Task 5: `board-gh-apply.sh` — apply the plan + refresh the watermark

Consumes a plan and executes only `auto:true`, non-conflict actions — board side via `board-transition.sh`, GitHub side via `gh`. `--dry-run` prints the exact commands (the hermetic test seam) and writes nothing. On a real run it rewrites `.sync-state.json` for every linked, non-conflict ticket.

**Files:**
- Create: `skills/issue-tracker/scripts/board-gh-apply.sh`
- Test: `tests/issue-tracker/test-board-gh-sync.sh`

**Interfaces:**
- Consumes: a plan (from `--plan FILE` / stdin) produced by `board-gh-plan.sh`; the same GitHub JSON via `--gh-json FILE` (to recompute the watermark); `board-transition.sh`.
- Produces: side effects (board transitions, `gh` calls) and a refreshed `.sync-state.json`; with `--dry-run`, only prints `board: …` / `gh: …` command lines.

- [ ] **Step 1: Write the failing tests** — append. Reuse the board+plan from Task 4; assert `--dry-run` prints the right commands and touches nothing:

```bash
echo "board-gh-apply (dry-run):"
run board-gh-plan.sh --gh-json "$TEST_ROOT/gh.json" > "$TEST_ROOT/plan.json"
map_before="$(cat "$BOARD/map.json")"
out="$(run board-gh-apply.sh --plan "$TEST_ROOT/plan.json" --gh-json "$TEST_ROOT/gh.json" --dry-run)"
assert_contains "$out" "gh: issue close 101 --reason completed" "dry-run plans the board->gh close"
assert_contains "$out" "board-transition.sh $B wontfix" "dry-run plans the gh->board wontfix"
assert_equals "$(cat "$BOARD/map.json")" "$map_before" "dry-run writes nothing to the board"
[ -f "$BOARD/.sync-state.json.tmp" ] && fail "dry-run no watermark tmp" || pass "dry-run leaves no watermark tmp"
```

Then a real board-side apply (GitHub calls are stubbed by pointing `gh` at a no-op via `--dry-run` is not enough; instead assert the board mutation for the `gh->board` action only, which needs no network):

```bash
echo "board-gh-apply (board side):"
# Apply only the gh->board wontfix for B by feeding a filtered plan (board side, no gh calls).
python3 - "$TEST_ROOT/plan.json" "$TEST_ROOT/plan-b.json" "$B" <<'PY'
import json,sys
src,dst,B=sys.argv[1:4]
p=json.load(open(src))
p["actions"]=[a for a in p["actions"] if a["ticket"]==B]
json.dump(p,open(dst,"w"))
PY
run board-gh-apply.sh --plan "$TEST_ROOT/plan-b.json" --gh-json "$TEST_ROOT/gh.json" --no-github
st="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['$B']['state'])")"
assert_equals "$st" "wontfix" "gh->board wontfix applied to the board via board-transition"
wm="$(python3 -c "import json;print(json.load(open('$BOARD/.sync-state.json'))['tickets']['$B']['state'])")"
assert_equals "$wm" "wontfix" "watermark refreshed to the reconciled board state"
```

(`--no-github` applies board-side actions and skips `gh` calls — the hermetic seam for the board half.)

- [ ] **Step 2: Run to see it fail**

Run: `bash tests/issue-tracker/test-board-gh-sync.sh`
Expected: FAIL — `board-gh-apply.sh` does not exist.

- [ ] **Step 3: Create `skills/issue-tracker/scripts/board-gh-apply.sh`:**

```bash
#!/usr/bin/env bash
# board-gh-apply.sh — apply a board-gh-plan, then refresh the sync watermark.
#
# Usage:
#   board-gh-apply.sh --plan FILE --gh-json FILE [--dry-run] [--no-github]
#   ... | board-gh-apply.sh --gh-json FILE [--dry-run]        (plan on stdin)
#
# Executes only auto:true, non-conflict actions: board side via board-transition.sh,
# GitHub side via gh. --dry-run prints the commands and writes nothing. --no-github
# applies board-side actions but skips gh calls (test/board-only seam). On a real
# run, .sync-state.json is rewritten for every linked, non-conflict ticket.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ -f "$MAP" ] || die "no board at $MAP"

planfile="" ghjson="" dry="" nogh=""
while [ $# -gt 0 ]; do
  case "$1" in
    --plan) _need_arg "$1" "${2:-}"; planfile="$2"; shift 2 ;;
    --gh-json) _need_arg "$1" "${2:-}"; ghjson="$2"; shift 2 ;;
    --dry-run) dry=1; shift ;;
    --no-github) nogh=1; shift ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -n "$planfile" ] && PLAN="$(cat "$planfile")" || PLAN="$(cat)"
[ -n "$ghjson" ] && GH_SRC="$(cat "$ghjson")" || GH_SRC="[]"

# 1) board-side transitions the plan asks for (unless dry-run) — via the real script.
printf '%s' "$PLAN" | PLAN_JSON="$PLAN" python3 -c '
import json, os, sys
plan = json.loads(os.environ["PLAN_JSON"])
for a in plan["actions"]:
    if not a.get("auto") or a.get("conflict"): continue
    if a.get("direction") == "gh->board" and a.get("target_board"):
        st, note = a["target_board"]
        print("%s\t%s\t%s" % (a["ticket"], st, note or ""))
' | while IFS="$(printf '\t')" read -r tid st note; do
  [ -z "$tid" ] && continue
  if [ -n "$dry" ]; then
    echo "board: board-transition.sh $tid $st ${note:+\"$note\"}"
  else
    if [ -n "$note" ]; then "$SCRIPT_DIR/board-transition.sh" "$tid" "$st" "$note" >/dev/null
    else "$SCRIPT_DIR/board-transition.sh" "$tid" "$st" >/dev/null; fi
    echo "board: $tid -> $st"
  fi
done

# 2) GitHub-side changes (unless dry-run or --no-github) — via gh.
printf '%s' "$PLAN" | PLAN_JSON="$PLAN" python3 -c '
import json, os
plan = json.loads(os.environ["PLAN_JSON"])
for a in plan["actions"]:
    if not a.get("auto") or a.get("conflict"): continue
    if a.get("direction") == "board->gh" and a.get("target_gh"):
        state, reason = a["target_gh"]
        if state == "closed":
            print("close\t%d\t%s" % (a["gh"], reason))
        else:
            print("reopen\t%d\t" % a["gh"])
' | while IFS="$(printf '\t')" read -r op num reason; do
  [ -z "$op" ] && continue
  if [ -n "$dry" ]; then
    [ "$op" = "close" ] && echo "gh: issue close $num --reason $reason" || echo "gh: issue reopen $num"
  elif [ -z "$nogh" ]; then
    if [ "$op" = "close" ]; then gh issue close "$num" --reason "$reason" >/dev/null
    else gh issue reopen "$num" >/dev/null; fi
    echo "gh: $op $num"
  fi
done

[ -n "$dry" ] && { echo "(dry-run: watermark unchanged)"; exit 0; }

# 3) Refresh the watermark for every linked, non-conflict ticket.
BOARD_GH="$GH_SRC" BOARD_SYNC="$BOARD_DIR/.sync-state.json" PLAN_JSON="$PLAN" \
T_TODAY="$(_today)" _py - <<'PY'
import json, os
env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
gh = {i["number"]: i for i in json.loads(env["BOARD_GH"] or "[]")}
plan = json.loads(env["PLAN_JSON"])
conflicted = {a["ticket"] for a in plan["actions"] if a.get("conflict")}
try:
    with open(env["BOARD_SYNC"]) as f:
        state = json.load(f)
except FileNotFoundError:
    state = {"version": 1, "tickets": {}}
wm = state.setdefault("tickets", {})
for tid, n in tickets.items():
    num = n.get("gh")
    if not num or num not in gh or tid in conflicted:
        continue  # unlinked, missing issue, or contested → leave watermark as-is
    wm[tid] = {"gh": num, "state": n["state"],
               "labels": list(n.get("labels") or [])}
state["version"] = 1
state["synced_at"] = env["T_TODAY"]
tmp = env["BOARD_SYNC"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(state, f, indent=2); f.write("\n")
os.replace(tmp, env["BOARD_SYNC"])
print("watermark: refreshed %d linked ticket(s)" % sum(
    1 for t, n in tickets.items() if n.get("gh") and n["gh"] in gh and t not in conflicted))
PY
```

`chmod +x skills/issue-tracker/scripts/board-gh-apply.sh`. Note the watermark refresh reads the board *after* the board-side transitions in step 1, so a ticket the plan just moved records its new state.

- [ ] **Step 4: Run to see it pass**

Run: `bash tests/issue-tracker/test-board-gh-sync.sh`
Expected: PASS (dry-run command lines + board-side wontfix + watermark refresh).

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-gh-apply.sh tests/issue-tracker/test-board-gh-sync.sh
git commit -m "issue-tracker: board-gh-apply.sh — apply plan + refresh watermark"
```

---

### Task 6: The `board-sync` subagent + `/board-sync` command

The judgment layer. The agent runs `plan`, applies the `auto` non-conflict actions, writes `SYNC-REPORT.md` from the conflicts + unlinked lists, and — under human invocation — walks the conflicts. Packaged as a Claude Code plugin subagent plus a slash command that dispatches it.

**Files:**
- Create: `agents/board-sync.md` (plugin subagent — auto-discovered by Claude Code at the plugin root)
- Create: `commands/board-sync.md` (slash command that invokes the agent)
- Test: manual smoke (documented in the final verification task) — an agent + command is a prompt, not unit-testable code.

**Interfaces:**
- Consumes: `board-gh-plan.sh`, `board-gh-apply.sh`, `gh`, `board-transition.sh`.
- Produces: applied reconciles + `doperpowers/issue-tracker/SYNC-REPORT.md`.

- [ ] **Step 1: Create `agents/board-sync.md`:**

```markdown
---
name: board-sync
description: Reconcile the local issue board (doperpowers/issue-tracker/map.json) with the repo's GitHub issues. Applies unambiguous state changes both ways; reports conflicts instead of guessing. Runs from the main checkout.
tools: Bash, Read
model: sonnet
---

You reconcile the local issue board with GitHub issues. You are the judgment
layer over a deterministic toolkit — you NEVER hand-edit map.json; every board
write goes through the scripts, every GitHub write through `gh`.

Scripts live in `skills/issue-tracker/scripts/` of the doperpowers plugin
(resolve via the installed plugin path). Run everything from the repo's MAIN
checkout (the scripts refuse worktrees).

Procedure:

1. Compute the plan:
   `board-gh-plan.sh > /tmp/board-sync-plan.json`
   (it fetches GitHub issues via `gh` itself). Read the JSON.

2. Apply the safe changes:
   `board-gh-plan.sh | board-gh-apply.sh`
   `board-gh-apply.sh` reads the plan from stdin, applies only `auto:true`,
   non-conflict actions, and refreshes the watermark from the plan itself (it
   does not take `--gh-json`). Do NOT pass `--dry-run` unless asked to preview.

3. Report everything you did NOT auto-apply. Write
   `doperpowers/issue-tracker/SYNC-REPORT.md` with three sections:
   - **Conflicts** — each `conflict:true` action, showing board / gh_state /
     watermark and the reason. These need a human decision.
   - **Unlinked (board)** — tickets with no `gh` link.
   - **Unlinked (GitHub)** — open issues with no board ticket.

4. If you were invoked by a human (not cron) and there are conflicts, walk them
   one at a time and propose a resolution; apply only what the human confirms,
   via `board-transition.sh` / `gh`. On cron, STOP after writing the report —
   never create issues or tickets, never resolve conflicts unattended.

Your final message: a one-line summary — N auto-applied, M conflicts, K
unlinked — and the report path.
```

- [ ] **Step 2: Create `commands/board-sync.md`:**

```markdown
---
description: Reconcile the local issue board with GitHub issues (via the board-sync agent).
---

Dispatch the `board-sync` subagent to reconcile `doperpowers/issue-tracker/map.json`
with this repo's GitHub issues. Run from the main checkout. After it finishes,
show me its summary and the path to `SYNC-REPORT.md`; if it reported conflicts,
walk me through them.
```

- [ ] **Step 3: Verify the plugin loads the agent** (no network):

Run: `ls agents/board-sync.md commands/board-sync.md && python3 -c "import re,sys; t=open('agents/board-sync.md').read(); assert t.startswith('---') and 'name: board-sync' in t and 'model: sonnet' in t; print('frontmatter ok')"`
Expected: both files listed + `frontmatter ok`.

- [ ] **Step 4: Commit**

```bash
git add agents/board-sync.md commands/board-sync.md
git commit -m "board-sync: subagent + /board-sync command (judgment layer)"
```

---

### Task 7: Document the toolkit in SKILL.md

Fold the four new scripts and board-sync into the issue-tracker manual so the orchestrator knows they exist.

**Files:**
- Modify: `skills/issue-tracker/SKILL.md` (the Toolkit table + a short "GitHub sync" subsection)

- [ ] **Step 1: Add rows to the Toolkit table** in `SKILL.md` (after the `board-reconcile.sh` row):

```markdown
| `board-link.sh <id> --gh N` \| `--backfill` | link a ticket to its GitHub issue; `--backfill` populates `gh` from the `(GH#NN)` marker in every title, once |
| `board-meta.sh <id> [--gh N] [--add-label L] [--rm-label L]` | writer for the `gh` link and free `labels[]` (atomic, re-renders) |
| `board-gh-plan.sh [--gh-json FILE]` | **read-only**: emit the board↔GitHub reconcile plan (state facet) as JSON |
| `board-gh-apply.sh [--plan FILE] [--dry-run] [--no-github]` | apply a plan's (stdin or `--plan`) `auto` non-conflict actions (board via scripts, GitHub via `gh`) and refresh `.sync-state.json` from the plan |
```

- [ ] **Step 2: Add a "## GitHub sync" subsection** after the toolkit table:

```markdown
## GitHub sync (board-sync)

`board-sync` (a subagent; `/board-sync`) keeps the board and GitHub issues in
step. It links tickets to issues (`gh` node field; `board-link.sh --backfill`
migrates existing boards from the `(GH#NN)` title marker), then reconciles state
both ways against a `.sync-state.json` watermark: board `done`↔closed/completed,
`wontfix`↔closed/not_planned, everything else↔open. Unambiguous changes apply
automatically; **true conflicts (both sides moved) are written to
`SYNC-REPORT.md`, never auto-resolved**. Cron runs are conservative — state only,
no counterpart creation. Run from the main checkout with `gh` authenticated.
```

- [ ] **Step 3: Commit**

```bash
git add skills/issue-tracker/SKILL.md
git commit -m "issue-tracker: document board-sync toolkit in SKILL.md"
```

---

### Task 8: Cron registration + final verification

Wire the schedule and run the spec's Layer-1 acceptance end-to-end.

**Files:** none created; this task registers a cron and runs acceptance.

- [ ] **Step 1: Register the daily cron** (operational — run in the session, not committed). Use `CronCreate` with a prompt that invokes the agent:

Prompt: *"Run the board-sync subagent to reconcile doperpowers/issue-tracker/map.json with this repo's GitHub issues, from the main checkout. This is an unattended run: apply only auto, non-conflict state changes; write conflicts and unlinked items to SYNC-REPORT.md; do not create issues or tickets."*
Schedule: daily. Record the cron id in the session output.

- [ ] **Step 2: Run the full board toolkit test suites**

Run: `bash tests/issue-tracker/test-board-gh-sync.sh && bash tests/issue-tracker/test-board-scripts.sh`
Expected: both print `ALL TESTS PASSED`.

- [ ] **Step 3: Execute the spec's acceptance behaviors** (`docs/doperpowers/specs/2026-07-05-board-sync-design.md`, "Acceptance"), Layer-1 subset, against a scratch board with a fixture `gh.json` (verbatim from the spec):
  - A linked ticket flipped to `done` with its issue still open → one apply closes it `completed`; second run is a no-op (empty plan actions).
  - An issue closed `not_planned` while the board shows it active → apply flips the board to `wontfix` via `board-transition.sh`.
  - Both sides diverged since last sync → neither side changes; the conflict appears in the plan with `conflict:true` and lands in `SYNC-REPORT.md`; the ticket's watermark is left stale.
  - A `… (GH#27)` title with no `gh` field → `board-link.sh --backfill` sets `gh:27`; a subsequent plan reads the field, not the title.
  - Unattended path: `board-gh-apply.sh` creates no issue/ticket; unlinked items are report-only.

- [ ] **Step 4: Manual live smoke** (documented, human-run): on the real repo, `board-gh-plan.sh` (no args, live `gh`) prints a plan; `/board-sync` in a main-checkout session applies it and writes `SYNC-REPORT.md`. Confirm no worktree run is possible (`board-gh-plan.sh` from a worktree is refused by `_lib.sh`).

- [ ] **Step 5: Final commit** (if any doc tweaks emerged)

```bash
git add -A && git commit -m "board-sync: Layer 1 (state sync) — acceptance verified" || echo "nothing to commit"
```

---

## Subsequent layers (separate plans)

Layer 1 above is a complete, shippable increment: bidirectional **state** sync + the agent + cron. Layers 2 and 3 extend the same scripts and each gets its own plan (write it once Layer 1 lands and verifies):

- **Layer 2 — labels.** Extend `board-gh-plan.sh` with a `labels` facet: set-diff `map.json` `labels[]` against each issue's free labels (exclude the managed set: `epic`, `category`→`bug`/`enhancement`, and `state:*`), watermark the last-synced set, propagate per-label add/remove both ways, conflict on a both-sides label disagreement. Extend `board-gh-apply.sh` to call `board-meta.sh --add-label/--rm-label` (board side) and `gh issue edit --add-label/--remove-label` (GitHub side). Add the one-way board→GH managed-label projection (`epic` from children; opt-in `state:<board-state>`).
- **Layer 3 — edges.** Extend the plan/apply with a `blocked_by` facet carried in the GitHub issue body as `<!-- board:blocked_by #68,#70 -->` (issue numbers resolved through the `gh` link). board→GH rewrites the block; GH→board parses it and re-cuts edges via `board-edge.sh`; conflict on disagreement. `parent`/`spawned_by`/`relates_to` stay board-only.

Each layer's plan follows the same TDD shape: fixture-driven `board-gh-plan.sh` unit tests in `test-board-gh-sync.sh`, `--dry-run` apply assertions, then the spec's acceptance for that layer.
