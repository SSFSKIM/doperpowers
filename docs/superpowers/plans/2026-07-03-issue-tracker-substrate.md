# Issue-Tracker Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local JSON issue board (`doperpowers/issue-tracker/` in the consumer repo) with a bash+python3 script toolkit, an orchestrator skill, and an `issue-register` that emits tickets onto it.

**Architecture:** Single `map.json` (graph + states, orchestrator-only writer, main-checkout canonical) + per-ticket markdown + append-only `log.jsonl`. Six scripts pattern-matched to the `orchestrating-daemons` toolkit enforce the invariants (transition legality, mandatory notes, done/epic sweeps, atomic writes, worktree guard); the LLM judges semantics. Daemon binding lives in the daemon registry (`ticket` key), never in the map.

**Tech Stack:** bash (macOS 3.2-compatible) + inline python3 stdlib. Zero dependencies.

**Spec:** `docs/superpowers/specs/2026-07-03-issue-tracker-substrate-design.md` — read it before starting.

## Global Constraints

- Scripts are bash 3.2-compatible (no `mapfile`, no associative arrays, no `${var,,}`); all logic lives in inline `python3 -` heredocs, stdlib only — exactly like `skills/orchestrating-daemons/scripts/`.
- Data dir is literally `doperpowers/issue-tracker/` under the consumer repo's main checkout. Lazy-created; no setup skill.
- Every script sources `_lib.sh`, which **refuses to run from a linked git worktree**.
- All JSON writes are atomic: write `<file>.tmp`, then `os.replace`.
- States are exactly: `ready-for-agent in-progress blocked needs-info in-review done wontfix deferred`. Categories: `bug | enhancement`. Notes are mandatory when moving to `blocked`, `needs-info`, `wontfix`.
- Only new files, except one modification: `skills/issue-register/SKILL.md` (fork-only file; zero upstream conflict).
- `scripts/lint-shell.sh <files>` must pass on every new shell file.
- Commit after every task. No `Co-Authored-By` / attribution lines in commit messages.

## File Structure

```
skills/issue-tracker/
  SKILL.md                     # orchestrator manual + Worker Protocol block   (Task 5)
  scripts/
    _lib.sh                    # guard, paths, lazy init, _py helper           (Task 1)
    board-register.sh          # add node, allocate ID                        (Task 1)
    board-transition.sh        # legality + notes + sweeps + log              (Task 2)
    board-list.sh              # view + eligibility                           (Task 3)
    board-show.sh              # node + md + bound daemon                     (Task 3)
    board-bind.sh              # write ticket key into daemon meta            (Task 4)
    board-reconcile.sh         # read-only reporter                           (Task 4)
tests/issue-tracker/
  test-board-scripts.sh        # hermetic suite, grown task-by-task           (Tasks 1-4)
skills/issue-register/SKILL.md # steps 6-7 emit onto the board                (Task 6)
```

---

### Task 1: `_lib.sh` + `board-register.sh` + hermetic test scaffold

**Files:**
- Create: `skills/issue-tracker/scripts/_lib.sh`
- Create: `skills/issue-tracker/scripts/board-register.sh`
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Produces: `_lib.sh` exports `BOARD_ROOT`, `BOARD_DIR` (`$BOARD_ROOT/doperpowers/issue-tracker`), `MAP` (`$BOARD_DIR/map.json`), `LOG` (`$BOARD_DIR/log.jsonl`), `DAEMON_HOME` (default `$HOME/.claude/orchestrating-daemons`), and functions `die`, `_now` (UTC ISO), `_today` (UTC date), `_board_init` (lazy bootstrap), `_py` (runs `python3` with `BOARD_MAP`/`BOARD_LOG` exported). Sourcing `_lib.sh` runs the worktree guard immediately.
- Produces: `board-register.sh <title> <category> [--state S] [--note TEXT] [--parent TID] [--blocked-by TID[,TID…]] [--spawned-by TID]` → prints `<id> <md-relpath>` (e.g. `T1 tickets/T1-some-slug.md`) on stdout. (The spec's shorthand listed `<md>` as an argument; the md path is actually an *output* — the ID embedded in the filename is allocated here.)

- [ ] **Step 1: Write the failing test scaffold**

Create `tests/issue-tracker/test-board-scripts.sh` (mode 755):

```bash
#!/usr/bin/env bash
#
# Hermetic tests for the issue-tracker board toolkit.
#
# The board scripts touch only the filesystem (a git repo's main checkout, the
# board data dir, and the daemon registry dir) — no network, no `claude` CLI.
# We build a throwaway git repo + worktree and a fake daemon registry, drive
# the real scripts end-to-end, and assert on map.json / log.jsonl / output.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS_DIR="$REPO_ROOT/skills/issue-tracker/scripts"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() {
    echo "  [FAIL] $1"
    FAILURES=$((FAILURES + 1))
}
assert_equals() {
    if [[ "$1" == "$2" ]]; then pass "$3"; else
        fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}
assert_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_file_exists() {
    if [[ -f "$1" ]]; then pass "$2"; else fail "$2"; echo "    missing: $1"; fi
}
assert_fails() { # cmd... — passes when the command exits non-zero
    if "$@" >/dev/null 2>&1; then fail "expected failure: $*"; else pass "refused: $*"; fi
}

# ---- environment: throwaway git repo + worktree, fake daemon registry -------
export HOME="$TEST_ROOT/home"; mkdir -p "$HOME"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
WORK="$TEST_ROOT/work"
git init -q "$WORK"
git -C "$WORK" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
git -C "$WORK" worktree add -q -b t-branch "$TEST_ROOT/wt"
BOARD="$WORK/doperpowers/issue-tracker"

run() { # run a board script from the main checkout
    local s="$1"; shift
    (cd "$WORK" && "$SCRIPTS_DIR/$s" "$@")
}

# ---- Task 1: register + lazy init + worktree guard ---------------------------
echo "board-register:"

out="$(run board-register.sh "Worktree map viewer" enhancement)"
assert_equals "$out" "T1 tickets/T1-worktree-map-viewer.md" "first register returns T1 + slug md path"
assert_file_exists "$BOARD/map.json" "lazy init created map.json"
assert_file_exists "$BOARD/log.jsonl" "birth logged to log.jsonl"
state="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T1']['state'])")"
assert_equals "$state" "ready-for-agent" "default birth state is ready-for-agent"

out="$(run board-register.sh "Deferred idea" bug --state deferred)"
assert_contains "$out" "T2" "second register allocates T2"

out="$(run board-register.sh "Child slice" enhancement --parent T1 --blocked-by T2)"
assert_contains "$out" "T3" "third register allocates T3"
parent="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T3']['parent'])")"
assert_equals "$parent" "T1" "parent edge stored"

assert_fails run board-register.sh "Bad" gadget                       # bad category
assert_fails run board-register.sh "Bad" bug --state blocked          # blocked without note
assert_fails run board-register.sh "Bad" bug --parent T99             # dangling ref
assert_fails run board-register.sh "Bad" bug --state in-progress      # not a birth state

(cd "$TEST_ROOT/wt" && "$SCRIPTS_DIR/board-register.sh" "From worktree" bug) \
    >/dev/null 2>&1 && fail "worktree guard" || pass "refused to run from a worktree"

[ -f "$BOARD/map.json.tmp" ] && fail "no tmp litter" || pass "no tmp litter after writes"

# ---- summary -----------------------------------------------------------------
echo
if [[ "$FAILURES" -eq 0 ]]; then echo "ALL TESTS PASSED"; else
    echo "$FAILURES TEST(S) FAILED"; exit 1; fi
```

Later tasks insert their test blocks **before the `# ---- summary` line**.

- [ ] **Step 2: Run it to make sure it fails**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: FAIL — `board-register.sh: No such file or directory` (non-zero exit).

- [ ] **Step 3: Write `_lib.sh`**

Create `skills/issue-tracker/scripts/_lib.sh` (mode 644 — it is sourced, not run):

```bash
#!/usr/bin/env bash
# _lib.sh — shared helpers for the issue-tracker board toolkit.
# Sourced by board-*.sh. Not meant to be run directly.
#
# The board is one map.json (graph + states) plus per-ticket markdown and an
# append-only log.jsonl under doperpowers/issue-tracker/ in the consumer repo.
# Single-writer rule: only the orchestrator (main session) writes it, and only
# from the repo's MAIN checkout — sourcing this file enforces the second half
# by refusing to run from a linked worktree.
set -euo pipefail

_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
_today() { date -u +%Y-%m-%d; }

die() {
  echo "error: $*" >&2
  exit 1
}

# Resolve the repo root; refuse linked worktrees (canonical-copy rule).
# In a linked worktree, --git-dir points under <main>/.git/worktrees/<name>
# while --git-common-dir points at <main>/.git — they differ.
_board_root() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git repo"
  local gd cdir
  gd="$(cd "$(git rev-parse --git-dir)" && pwd)"
  cdir="$(cd "$(git rev-parse --git-common-dir)" && pwd)"
  [ "$gd" = "$cdir" ] || die "refusing to touch the board from a worktree — run from the main checkout"
  git rev-parse --show-toplevel
}

BOARD_ROOT="$(_board_root)"
BOARD_DIR="$BOARD_ROOT/doperpowers/issue-tracker"
MAP="$BOARD_DIR/map.json"
LOG="$BOARD_DIR/log.jsonl"

# Daemon registry — same default (and same test override) as orchestrating-daemons.
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"

# Lazy bootstrap: first register creates the data dir + an empty map.
_board_init() {
  [ -f "$MAP" ] && return 0
  mkdir -p "$BOARD_DIR/tickets"
  printf '{\n  "version": 1,\n  "next_id": 1,\n  "tickets": {}\n}\n' > "$MAP"
}

# Run an inline python3 board operation with the board paths exported.
_py() { BOARD_MAP="$MAP" BOARD_LOG="$LOG" python3 "$@"; }

usage_from_header() { grep '^#' "$1" | grep -v '^#!' | sed 's/^# \{0,1\}//'; }
```

- [ ] **Step 4: Write `board-register.sh`**

Create `skills/issue-tracker/scripts/board-register.sh` (mode 755):

```bash
#!/usr/bin/env bash
# board-register.sh — add a ticket to the board (lazy-creates it on first use).
#
# Usage:
#   board-register.sh <title> <category> [--state S] [--note TEXT] [--parent TID]
#                     [--blocked-by TID[,TID...]] [--spawned-by TID]
#
#   category  bug | enhancement
#   --state   birth state: ready-for-agent (default) | needs-info | blocked | deferred
#             (needs-info / blocked require --note)
#
# Prints "<id> <md-relpath>" — the caller (orchestrator) writes that markdown.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
title="$1" category="$2"
shift 2
state="ready-for-agent" note="" parent="" blocked_by="" spawned_by=""
while [ $# -gt 0 ]; do
  case "$1" in
    --state) state="$2"; shift 2 ;;
    --note) note="$2"; shift 2 ;;
    --parent) parent="$2"; shift 2 ;;
    --blocked-by) blocked_by="$2"; shift 2 ;;
    --spawned-by) spawned_by="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done

_board_init
T_TITLE="$title" T_CATEGORY="$category" T_STATE="$state" T_NOTE="$note" \
T_PARENT="$parent" T_BLOCKED="$blocked_by" T_SPAWNED="$spawned_by" \
T_NOW="$(_now)" T_TODAY="$(_today)" _py - <<'PY'
import json, os, re, sys

def die(msg):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(1)

env = os.environ
title, category, state, note = env["T_TITLE"], env["T_CATEGORY"], env["T_STATE"], env["T_NOTE"]
if category not in ("bug", "enhancement"):
    die("category must be bug|enhancement")
BIRTH = ("ready-for-agent", "needs-info", "blocked", "deferred")
if state not in BIRTH:
    die("birth state must be one of: %s" % ", ".join(BIRTH))
if state in ("needs-info", "blocked") and not note:
    die("--note is required for state %s" % state)

with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
parent, spawned = env["T_PARENT"], env["T_SPAWNED"]
blocked = [b for b in env["T_BLOCKED"].split(",") if b]
for ref in [parent, spawned] + blocked:
    if ref and ref not in tickets:
        die("unknown ticket ref: %s" % ref)

tid = "T%d" % board["next_id"]
board["next_id"] += 1
slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", title.lower())).strip("-")[:40] or "ticket"
md = "tickets/%s-%s.md" % (tid, slug)
tickets[tid] = {
    "title": title, "md": md, "state": state, "category": category,
    "note": note or None, "parent": parent or None,
    "blocked_by": blocked, "spawned_by": spawned or None, "relates_to": [],
    "branch": None, "pr": None,
    "created": env["T_TODAY"], "updated": env["T_TODAY"],
}
tmp = env["BOARD_MAP"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(board, f, indent=2)
    f.write("\n")
os.replace(tmp, env["BOARD_MAP"])
with open(env["BOARD_LOG"], "a") as f:
    f.write(json.dumps({"ts": env["T_NOW"], "ticket": tid, "from": None,
                        "to": state, "note": note or None}) + "\n")
print("%s %s" % (tid, md))
PY
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: `ALL TESTS PASSED` (12 PASS lines, 0 FAIL).

- [ ] **Step 6: Lint and commit**

```bash
scripts/lint-shell.sh skills/issue-tracker/scripts/_lib.sh skills/issue-tracker/scripts/board-register.sh tests/issue-tracker/test-board-scripts.sh
git add skills/issue-tracker/scripts/_lib.sh skills/issue-tracker/scripts/board-register.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "issue-tracker: board lib + register with hermetic test scaffold"
```

---

### Task 2: `board-transition.sh` — the invariant home

**Files:**
- Create: `skills/issue-tracker/scripts/board-transition.sh`
- Modify: `tests/issue-tracker/test-board-scripts.sh` (insert block before `# ---- summary`)

**Interfaces:**
- Consumes: `_lib.sh` (`die`, `_now`, `_today`, `_py`, `MAP`, `usage_from_header`); map schema from Task 1.
- Produces: `board-transition.sh <id> <to-state> [note] [--branch NAME] [--pr URL]` → applies the transition + sweeps, appends every applied change to `log.jsonl`, prints one `T<n>: <from> → <to>` line per applied change and `now eligible: …` lines after a `done`.

- [ ] **Step 1: Write the failing tests**

Insert before `# ---- summary` in `tests/issue-tracker/test-board-scripts.sh`:

```bash
# ---- Task 2: transition legality, notes, sweeps, log --------------------------
echo "board-transition:"

# Board so far: T1 ready (epic-to-be), T2 deferred, T3 ready (parent T1, blocked_by T2)
assert_fails run board-transition.sh T1 done                 # illegal ready→done
assert_fails run board-transition.sh T1 blocked              # note required
assert_fails run board-transition.sh T1 ready-for-agent      # same-state
assert_fails run board-transition.sh T99 done                # unknown ticket
assert_fails run board-transition.sh T1 shipping             # unknown state

out="$(run board-transition.sh T3 in-progress)"
assert_contains "$out" "T3: ready-for-agent → in-progress" "transition applied"
assert_contains "$out" "T1: ready-for-agent → in-progress" "epic parent pulled to in-progress"

out="$(run board-transition.sh T3 in-review "" --branch worktree-t3 --pr "PR#12")"
pr="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T3']['pr'])")"
assert_equals "$pr" "PR#12" "pr recorded on in-review"

out="$(run board-transition.sh T2 ready-for-agent)"    # revive the deferred blocker
out="$(run board-transition.sh T2 in-progress)"
out="$(run board-transition.sh T2 done)"
assert_contains "$out" "T2: in-progress → done" "blocker done"

out="$(run board-transition.sh T3 done)"
assert_contains "$out" "T1: in-progress → done" "epic auto-closed when all children terminal"

# done unblocks dependents: T4 blocked_by the not-yet-done T5
run board-register.sh "Blocker" bug >/dev/null                       # T4
run board-register.sh "Dependent" bug --blocked-by T4 >/dev/null     # T5
run board-transition.sh T4 in-progress >/dev/null
out="$(run board-transition.sh T4 done)"
assert_contains "$out" "now eligible: T5" "done sweep reports newly eligible dependents"

lines="$(wc -l < "$BOARD/log.jsonl" | tr -d ' ')"
assert_equals "$lines" "15" "every applied change logged (5 births + 10 transitions)"
```

- [ ] **Step 2: Run to verify the new block fails**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: register tests PASS; transition block fails with `board-transition.sh: No such file or directory`.

- [ ] **Step 3: Write `board-transition.sh`**

Create `skills/issue-tracker/scripts/board-transition.sh` (mode 755):

```bash
#!/usr/bin/env bash
# board-transition.sh — move a ticket to a new state, enforcing the invariants.
#
# Usage:
#   board-transition.sh <id> <to-state> [note] [--branch NAME] [--pr URL]
#
# Enforces transition legality and mandatory notes (blocked/needs-info/wontfix),
# records branch/pr, appends every applied change to log.jsonl, and sweeps:
#   → in-progress : the first active child pulls its parent epic(s) to in-progress
#   → done/wontfix: an epic closes when every child is terminal and at least one
#                   is done; a done ticket prints its newly-eligible dependents
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
tid="$1" to="$2"
shift 2
note="" branch="" pr=""
if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then note="$1"; shift; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) branch="$2"; shift 2 ;;
    --pr) pr="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_ID="$tid" T_TO="$to" T_NOTE="$note" T_BRANCH="$branch" T_PR="$pr" \
T_NOW="$(_now)" T_TODAY="$(_today)" _py - <<'PY'
import json, os, sys

def die(msg):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(1)

env = os.environ
LEGAL = {
    "ready-for-agent": {"in-progress", "needs-info", "blocked", "wontfix", "deferred"},
    "in-progress":     {"needs-info", "blocked", "in-review", "done", "wontfix", "deferred"},
    "needs-info":      {"ready-for-agent", "in-progress", "wontfix", "deferred"},
    "blocked":         {"ready-for-agent", "in-progress", "wontfix", "deferred"},
    "in-review":       {"in-progress", "done", "wontfix"},
    "deferred":        {"ready-for-agent", "needs-info", "blocked", "wontfix"},
    "done":            set(),   # terminal
    "wontfix":         set(),   # terminal
}
NOTE_REQUIRED = {"blocked", "needs-info", "wontfix"}
TERMINAL = {"done", "wontfix"}

with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
tid, to, note = env["T_ID"], env["T_TO"], env["T_NOTE"]
if tid not in tickets:
    die("unknown ticket: %s" % tid)
if to not in LEGAL:
    die("unknown state: %s" % to)
cur = tickets[tid]["state"]
if to == cur:
    die("%s is already %s" % (tid, cur))
if to not in LEGAL[cur]:
    die("illegal transition: %s → %s (%s)" % (cur, to, tid))
if to in NOTE_REQUIRED and not note:
    die("a note is required when moving to %s" % to)

applied = []
def apply(t, new, why):
    old = tickets[t]["state"]
    tickets[t]["state"] = new
    tickets[t]["updated"] = env["T_TODAY"]
    tickets[t]["note"] = why or None       # stale notes cleared on every move
    applied.append({"ts": env["T_NOW"], "ticket": t, "from": old, "to": new,
                    "note": why or None})

apply(tid, to, note)
if env["T_BRANCH"]:
    tickets[tid]["branch"] = env["T_BRANCH"]
if env["T_PR"]:
    tickets[tid]["pr"] = env["T_PR"]

def children(p):
    return [t for t, n in tickets.items() if n.get("parent") == p]

# Sweep: first active child pulls its epic chain to in-progress.
if to == "in-progress":
    p = tickets[tid].get("parent")
    while p and tickets[p]["state"] in ("ready-for-agent", "needs-info", "blocked", "deferred"):
        apply(p, "in-progress", "epic: child %s started" % tid)
        p = tickets[p].get("parent")

# Sweep: a terminal child may close its epic chain (all children terminal,
# at least one done — an all-wontfix epic is left for human judgment).
if to in TERMINAL:
    p = tickets[tid].get("parent")
    while p:
        kids = children(p)
        if kids and tickets[p]["state"] not in TERMINAL \
           and all(tickets[k]["state"] in TERMINAL for k in kids) \
           and any(tickets[k]["state"] == "done" for k in kids):
            apply(p, "done", "epic: all children terminal")
            p = tickets[p].get("parent")
        else:
            break

# Report dependents this `done` made eligible (derived, nothing written).
if to == "done":
    for t, n in sorted(tickets.items(), key=lambda kv: int(kv[0][1:])):
        if n["state"] == "ready-for-agent" and tid in n.get("blocked_by", []) \
           and all(tickets.get(b, {}).get("state") == "done" for b in n["blocked_by"]):
            print("now eligible: %s  %s" % (t, n["title"]))

tmp = env["BOARD_MAP"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(board, f, indent=2)
    f.write("\n")
os.replace(tmp, env["BOARD_MAP"])
with open(env["BOARD_LOG"], "a") as f:
    for e in applied:
        f.write(json.dumps(e) + "\n")
for e in applied:
    print("%s: %s → %s" % (e["ticket"], e["from"], e["to"]))
PY
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: `ALL TESTS PASSED`.

- [ ] **Step 5: Lint and commit**

```bash
scripts/lint-shell.sh skills/issue-tracker/scripts/board-transition.sh tests/issue-tracker/test-board-scripts.sh
git add skills/issue-tracker/scripts/board-transition.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "issue-tracker: board-transition with legality, note, and sweep invariants"
```

---

### Task 3: `board-list.sh` + `board-show.sh`

**Files:**
- Create: `skills/issue-tracker/scripts/board-list.sh`
- Create: `skills/issue-tracker/scripts/board-show.sh`
- Modify: `tests/issue-tracker/test-board-scripts.sh` (insert before `# ---- summary`)

**Interfaces:**
- Consumes: `_lib.sh`; map schema; daemon meta files `$DAEMON_HOME/<uuid>.json` with optional `ticket` key (written by Task 4's `board-bind.sh`; tests fake them directly).
- Produces: `board-list.sh [state]` → one line per ticket: `ID STATE CATEGORY TITLE [tags] — note`, tags among `epic`, `ELIGIBLE`, `waiting:<ids>`, `STUCK(wontfix blocker)`, `MISSING-MD`. `board-show.sh <id>` → node JSON, absolute md path, `daemon:` line (bound daemon or `(none bound)`).

- [ ] **Step 1: Write the failing tests**

Insert before `# ---- summary`:

```bash
# ---- Task 3: list + show ------------------------------------------------------
echo "board-list / board-show:"

# Fresh eligible ticket + a blocked-by-live-ticket dependent
run board-register.sh "Solo ready" enhancement >/dev/null            # T6
run board-register.sh "Waiting on T6" bug --blocked-by T6 >/dev/null # T7

out="$(run board-list.sh)"
assert_contains "$out" "T6" "list shows all tickets"
echo "$out" | grep "T6" | grep -q "ELIGIBLE" && pass "T6 eligible" || fail "T6 eligible"
echo "$out" | grep "T7" | grep -q "waiting:T6" && pass "T7 waiting on T6" || fail "T7 waiting on T6"
echo "$out" | grep "T1 " | grep -q "epic" && pass "T1 tagged epic" || fail "T1 tagged epic"

out="$(run board-list.sh done)"
assert_contains "$out" "T2" "state filter shows done tickets"
echo "$out" | grep -q "T6" && fail "filter excludes others" || pass "filter excludes others"

out="$(run board-show.sh T6)"
assert_contains "$out" "Solo ready" "show prints the node"
assert_contains "$out" "(none bound)" "show reports no bound daemon"

# Fake a bound daemon in the registry, then show finds it
cat > "$DAEMON_HOME/aaaa1111-0000-0000-0000-000000000001.json" <<'META'
{"uuid": "aaaa1111-0000-0000-0000-000000000001", "short": "aaaa1111",
 "name": "t6-worker", "status": "idle", "cwd": "/tmp/x", "worktree": "t6",
 "ticket": "T6"}
META
out="$(run board-show.sh T6)"
assert_contains "$out" "aaaa1111" "show finds the bound daemon"

assert_fails run board-show.sh T99

# A stray tmp from an interrupted write is ignored by readers (atomicity).
touch "$BOARD/map.json.tmp"
run board-list.sh >/dev/null && pass "stray map.json.tmp ignored" || fail "stray map.json.tmp ignored"
rm -f "$BOARD/map.json.tmp"
```

- [ ] **Step 2: Run to verify the new block fails**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: earlier blocks PASS; this block fails on missing `board-list.sh`.

- [ ] **Step 3: Write `board-list.sh`**

Create `skills/issue-tracker/scripts/board-list.sh` (mode 755):

```bash
#!/usr/bin/env bash
# board-list.sh — board view with computed eligibility.
#
# Usage: board-list.sh [state]
#
# Eligible = ready-for-agent + every blocked_by ticket done + not an epic.
# Tags: epic | ELIGIBLE | waiting:<ids> | STUCK(wontfix blocker) | MISSING-MD
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_FILTER="${1:-}" _py - <<'PY'
import json, os

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
flt = env["T_FILTER"]
board_dir = os.path.dirname(env["BOARD_MAP"])
epics = {n["parent"] for n in tickets.values() if n.get("parent")}

for tid, n in sorted(tickets.items(), key=lambda kv: int(kv[0][1:])):
    if flt and n["state"] != flt:
        continue
    tags = []
    if tid in epics:
        tags.append("epic")
    elif n["state"] == "ready-for-agent":
        blockers = [b for b in n.get("blocked_by", [])
                    if tickets.get(b, {}).get("state") != "done"]
        if not blockers:
            tags.append("ELIGIBLE")
        else:
            tags.append("waiting:" + ",".join(blockers))
            if any(tickets.get(b, {}).get("state") == "wontfix" for b in blockers):
                tags.append("STUCK(wontfix blocker)")
    if not os.path.exists(os.path.join(board_dir, n["md"])):
        tags.append("MISSING-MD")
    extra = ("  [%s]" % " ".join(tags)) if tags else ""
    note = ("  — %s" % n["note"]) if n.get("note") else ""
    print("%-5s %-15s %-11s %s%s%s" % (tid, n["state"], n["category"], n["title"], extra, note))
PY
```

- [ ] **Step 4: Write `board-show.sh`**

Create `skills/issue-tracker/scripts/board-show.sh` (mode 755):

```bash
#!/usr/bin/env bash
# board-show.sh — one ticket in full: node JSON, md path, bound daemon.
#
# Usage: board-show.sh <id>
#
# The daemon binding lives in the daemon registry (a `ticket` key in the
# daemon's meta JSON — see board-bind.sh), never in the map.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ $# -eq 1 ] || { usage_from_header "$0" >&2; exit 2; }
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_ID="$1" T_DHOME="$DAEMON_HOME" _py - <<'PY'
import glob, json, os, sys

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tid = env["T_ID"]
n = board["tickets"].get(tid)
if n is None:
    sys.stderr.write("error: unknown ticket: %s\n" % tid)
    sys.exit(1)
print(json.dumps({tid: n}, indent=2))
print("md: %s" % os.path.join(os.path.dirname(env["BOARD_MAP"]), n["md"]))
for p in sorted(glob.glob(os.path.join(env["T_DHOME"], "*.json"))):
    try:
        with open(p) as f:
            m = json.load(f)
    except (ValueError, OSError):
        continue
    if m.get("ticket") == tid:
        print("daemon: %s  status=%s  cwd=%s  worktree=%s" %
              (m.get("uuid", os.path.basename(p)[:-5]), m.get("status"),
               m.get("cwd"), m.get("worktree") or "-"))
        break
else:
    print("daemon: (none bound)")
PY
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: `ALL TESTS PASSED`.

- [ ] **Step 6: Lint and commit**

```bash
scripts/lint-shell.sh skills/issue-tracker/scripts/board-list.sh skills/issue-tracker/scripts/board-show.sh tests/issue-tracker/test-board-scripts.sh
git add skills/issue-tracker/scripts/board-list.sh skills/issue-tracker/scripts/board-show.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "issue-tracker: board-list eligibility view + board-show with daemon binding"
```

---

### Task 4: `board-bind.sh` + `board-reconcile.sh`

**Files:**
- Create: `skills/issue-tracker/scripts/board-bind.sh`
- Create: `skills/issue-tracker/scripts/board-reconcile.sh`
- Modify: `tests/issue-tracker/test-board-scripts.sh` (insert before `# ---- summary`)

**Interfaces:**
- Consumes: `_lib.sh`; daemon registry file format (`<uuid>.json` meta, `<uuid>.reply.txt` latest reply — the contract is the FILES, not the daemon toolkit's code); proposal block format `{"ticket":"T7","from":"in-progress","to":"in-review","reason":"…","evidence":"…"}` (a bare or fenced JSON object anywhere in the reply; the LAST one for this ticket wins).
- Produces: `board-bind.sh <uuid-or-prefix> <ticket-id>` → writes `ticket` + `updated` keys into the daemon meta (atomic), prints `bound <tid> ← <uuid>`. `board-reconcile.sh` → read-only report lines prefixed `proposal`, `orphaned`, `anomaly`, `dispatch`; always exits 0.

- [ ] **Step 1: Write the failing tests**

Insert before `# ---- summary`:

```bash
# ---- Task 4: bind + reconcile --------------------------------------------------
echo "board-bind / board-reconcile:"

cat > "$DAEMON_HOME/bbbb2222-0000-0000-0000-000000000002.json" <<'META'
{"uuid": "bbbb2222-0000-0000-0000-000000000002", "short": "bbbb2222",
 "name": "t7-worker", "status": "idle", "cwd": "/tmp/y", "worktree": "t7"}
META
out="$(run board-bind.sh bbbb2222 T7)"
assert_contains "$out" "bound T7" "bind reports success"
tk="$(python3 -c "import json;print(json.load(open('$DAEMON_HOME/bbbb2222-0000-0000-0000-000000000002.json'))['ticket'])")"
assert_equals "$tk" "T7" "bind wrote the ticket key into daemon meta"
assert_fails run board-bind.sh bbbb2222 T99          # unknown ticket
assert_fails run board-bind.sh zzzz9999 T7           # no matching daemon

# Reconcile case 1: a proposal in a reply that the board hasn't applied.
run board-transition.sh T6 in-progress >/dev/null
cat > "$DAEMON_HOME/aaaa1111-0000-0000-0000-000000000001.reply.txt" <<'REPLY'
Build finished; PR opened.
{"ticket":"T6","from":"in-progress","to":"in-review","reason":"build done","evidence":"PR #9"}
REPLY
# Reconcile case 2: in-progress with no bound daemon.
run board-transition.sh T7 in-progress >/dev/null
rm "$DAEMON_HOME/bbbb2222-0000-0000-0000-000000000002.json"

out="$(run board-reconcile.sh)"
assert_contains "$out" "proposal  T6: in-progress → in-review" "reconcile surfaces the unapplied proposal"
assert_contains "$out" "board-transition.sh T6 in-review" "reconcile prints the apply command"
assert_contains "$out" "orphaned  T7" "reconcile flags in-progress ticket with no daemon"

map_before="$(cat "$BOARD/map.json")"
run board-reconcile.sh >/dev/null
assert_equals "$(cat "$BOARD/map.json")" "$map_before" "reconcile never writes the board"
```

- [ ] **Step 2: Run to verify the new block fails**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: earlier blocks PASS; this block fails on missing `board-bind.sh`.

- [ ] **Step 3: Write `board-bind.sh`**

Create `skills/issue-tracker/scripts/board-bind.sh` (mode 755):

```bash
#!/usr/bin/env bash
# board-bind.sh — bind a spawned daemon to a ticket.
#
# Usage: board-bind.sh <daemon-uuid-or-prefix> <ticket-id>
#
# Writes a `ticket` key into the daemon's registry meta (additive JSON merge —
# zero changes to the orchestrating-daemons toolkit). The registry is the ONLY
# home of the binding: machine-lifetime data never enters the map.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ $# -eq 2 ] || { usage_from_header "$0" >&2; exit 2; }
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_Q="$1" T_ID="$2" T_DHOME="$DAEMON_HOME" T_NOW="$(_now)" _py - <<'PY'
import glob, json, os, sys

def die(msg):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(1)

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
if env["T_ID"] not in board["tickets"]:
    die("unknown ticket: %s" % env["T_ID"])
hits = []
for p in glob.glob(os.path.join(env["T_DHOME"], "*.json")):
    u = os.path.basename(p)[:-5]
    if u == env["T_Q"] or u.startswith(env["T_Q"]):
        hits.append(p)
if len(hits) != 1:
    die("%d daemons match '%s'" % (len(hits), env["T_Q"]))
with open(hits[0]) as f:
    meta = json.load(f)
meta["ticket"] = env["T_ID"]
meta["updated"] = env["T_NOW"]
tmp = hits[0] + ".tmp"
with open(tmp, "w") as f:
    json.dump(meta, f, indent=2)
os.replace(tmp, hits[0])
print("bound %s ← %s" % (env["T_ID"], os.path.basename(hits[0])[:-5]))
PY
```

- [ ] **Step 4: Write `board-reconcile.sh`**

Create `skills/issue-tracker/scripts/board-reconcile.sh` (mode 755):

```bash
#!/usr/bin/env bash
# board-reconcile.sh — read-only catch-up report; NEVER writes anything.
#
# Usage: board-reconcile.sh
#
# Scans daemon replies for proposal blocks the board hasn't applied, flags
# in-progress tickets with no live bound daemon, and lists dispatchable
# tickets. Applying anything is the orchestrator's judge step, via
# board-transition.sh — this script only reports.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_DHOME="$DAEMON_HOME" _py - <<'PY'
import glob, json, os, re

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]

bound = {}   # ticket id -> daemon meta
for p in sorted(glob.glob(os.path.join(env["T_DHOME"], "*.json"))):
    try:
        with open(p) as f:
            m = json.load(f)
    except (ValueError, OSError):
        continue
    if m.get("ticket"):
        m["_uuid"] = m.get("uuid", os.path.basename(p)[:-5])
        bound[m["ticket"]] = m

def by_id(items):
    return sorted(items, key=lambda kv: int(kv[0][1:]))

# 1. Unapplied proposals in daemon replies (last block for the ticket wins).
for t, m in by_id(bound.items()):
    reply = os.path.join(env["T_DHOME"], "%s.reply.txt" % m["_uuid"])
    if not os.path.exists(reply):
        continue
    with open(reply) as f:
        blocks = re.findall(r'\{[^{}]*"ticket"[^{}]*\}', f.read())
    prop = None
    for raw in reversed(blocks):
        try:
            cand = json.loads(raw)
        except ValueError:
            continue
        if cand.get("ticket") == t:
            prop = cand
            break
    cur = tickets.get(t, {}).get("state")
    if prop and prop.get("to") and prop["to"] != cur:
        print("proposal  %s: %s → %s  (reason: %s; evidence: %s)" %
              (t, cur, prop["to"], prop.get("reason", "-"), prop.get("evidence", "-")))
        print("          apply: board-transition.sh %s %s" % (t, prop["to"]))

# 2. in-progress tickets with a missing or terminal daemon.
for t, n in by_id(tickets.items()):
    if n["state"] != "in-progress":
        continue
    m = bound.get(t)
    if m is None:
        print("orphaned  %s: in-progress but no bound daemon — respawn + board-bind, or transition" % t)
    elif m.get("status") in ("error", "retired"):
        print("anomaly   %s: bound daemon %s status=%s" % (t, m["_uuid"][:8], m["status"]))

# 3. Dispatchable tickets (same rule as board-list eligibility).
epics = {n["parent"] for n in tickets.values() if n.get("parent")}
for t, n in by_id(tickets.items()):
    if n["state"] == "ready-for-agent" and t not in epics \
       and all(tickets.get(b, {}).get("state") == "done" for b in n.get("blocked_by", [])):
        print("dispatch  %s: %s" % (t, n["title"]))
PY
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: `ALL TESTS PASSED`.

- [ ] **Step 6: Lint and commit**

```bash
scripts/lint-shell.sh skills/issue-tracker/scripts/board-bind.sh skills/issue-tracker/scripts/board-reconcile.sh tests/issue-tracker/test-board-scripts.sh
git add skills/issue-tracker/scripts/board-bind.sh skills/issue-tracker/scripts/board-reconcile.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "issue-tracker: board-bind daemon binding + read-only board-reconcile"
```

---

### Task 5: `skills/issue-tracker/SKILL.md` — the orchestrator manual

**Files:**
- Create: `skills/issue-tracker/SKILL.md`

**Interfaces:**
- Consumes: every script from Tasks 1–4 (documented verbatim); the Worker Protocol proposal-block format from Task 4's reconcile parser.
- Produces: the skill the main session auto-triggers when operating the board; the Worker Protocol block that gets embedded in every spawn prompt.

- [ ] **Step 1: Write the skill**

Create `skills/issue-tracker/SKILL.md` with exactly this content:

````markdown
---
name: issue-tracker
description: Use when managing the local issue board — registering tickets, dispatching background daemons to tickets, judging daemon state proposals, reconciling the board after time away, or asking what is in progress / blocked / dispatchable. The board lives in doperpowers/issue-tracker/ in the repo.
---

# Issue Tracker

A local, repo-portable issue board. Tickets are **purpose-units**: born as
pre-specs from `issue-register`, driven end-to-end (brainstorm → spec → plan →
build → PR) by background daemons (`orchestrating-daemons`), tracked as nodes
in `doperpowers/issue-tracker/map.json`.

**You (the main session) are the orchestrator — the board's only writer.**
Daemons never touch the board; they end turns with *proposal blocks* that you
judge and apply. All writes go through the scripts, from the MAIN checkout
only (they refuse worktrees).

## The two roles

| | writes the board? | how it talks |
|---|---|---|
| **Orchestrator** (main session — you) | yes, sole writer, via scripts | runs the toolkit; judges proposals |
| **Worker** (daemon, one ticket each) | never | reads its ticket md; ends turns with a proposal block |

## State vocabulary

`ready-for-agent → in-progress → in-review → done` is the happy path.

| state | meaning | note |
|---|---|---|
| `ready-for-agent` | pre-spec complete; dispatchable once blockers are done | — |
| `in-progress` | a daemon is driving it (an epic stays here while children run) | optional |
| `blocked` | non-ticket blockage: credentials / auth / human hand | **required** |
| `needs-info` | waiting on knowledge: research or a human taste/product decision | **required** |
| `in-review` | PR open (review rounds, conflicts, merge queue — all of it) | PR link |
| `done` | landed — verify the merge before flipping | optional |
| `wontfix` | rejected | **required** |
| `deferred` | tracked, not now | optional |

**Discriminant:** waiting on an *action/precondition* → `blocked`; waiting on
*knowledge/decision* → `needs-info`.

Ticket dependencies are **edges** (`blocked_by`), never states — eligibility is
computed. Epics (nodes with children) are never dispatched; the sweep moves
them automatically.

## Toolkit

Paths relative to this skill's `scripts/` directory. Use them — don't hand-edit
`map.json`.

| script | does |
|---|---|
| `board-register.sh <title> <category> [--state S] [--note N] [--parent T] [--blocked-by T,T] [--spawned-by T]` | add a node; prints `<id> <md-relpath>` — then YOU write that markdown (pre-spec) |
| `board-transition.sh <id> <state> [note] [--branch B] [--pr URL]` | apply a state change; enforces legality + notes; runs the epic/unblock sweeps |
| `board-list.sh [state]` | board view; `ELIGIBLE` tag = dispatchable |
| `board-show.sh <id>` | node + md path + bound daemon |
| `board-bind.sh <uuid> <id>` | record which daemon owns the ticket (in the daemon registry) |
| `board-reconcile.sh` | read-only catch-up: unapplied proposals, orphaned tickets, dispatchables |

## The dispatch loop

1. `board-list.sh` → pick an `ELIGIBLE` ticket.
2. Build a **self-contained spawn prompt**: the full ticket md content + the
   Worker Protocol block below.
3. `daemon-spawn.sh "<id>-<slug>" "<prompt>" <repo> <worktree-name>` (from
   `orchestrating-daemons` — always a worktree; workers write code).
4. `board-bind.sh <uuid> <id>` then `board-transition.sh <id> in-progress`.
5. When a daemon's turn ends, judge its proposal block (per
   `orchestrating-daemons`: answer / queue for the human / wake the human),
   then apply or refuse with `board-transition.sh`.
6. On `done`: verify the PR actually landed first — `done` means *landed*,
   not "worker says finished". Append an outcome summary to the ticket md.

**Reconcile-on-wake:** been away? `board-reconcile.sh` first. It lists what
the daemons proposed while you were gone and what needs respawning.

## Worker Protocol (embed VERBATIM in every spawn prompt)

```
You own ticket <ID> end-to-end: brainstorm → spec → plan → build → PR, in your
worktree. Your ticket brief is below; treat it as the source of truth.

The issue board is READ-ONLY for you. To change your ticket's state, end your
turn with a single-line JSON proposal block:
{"ticket":"<ID>","from":"<current>","to":"<proposed>","reason":"…","evidence":"…"}

Escalation: waiting on an action/precondition (credentials, access, another
ticket's work) → propose "blocked". Waiting on knowledge or a human
taste/product decision → propose "needs-info". State the question crisply and
END YOUR TURN — never guess above your scope, never expand it.
```

## Ticket markdown

`doperpowers/issue-tracker/tickets/<id>-<slug>.md` — written by YOU (register
time, plus a terminal outcome summary). Frontmatter `id/title/category` only —
state lives in the map alone. Body: Problem & intent / Constraints / Success
criteria / Open questions / Decision log.

## Edge cases

- `orphaned` in reconcile → the daemon died: respawn, re-bind, resume the ticket.
- A wontfix blocker makes a dependent `STUCK` — re-cut the `blocked_by` edge or
  wontfix the dependent; that is a human call.
- `map.json` corrupted → restore from git history.
- Never run board scripts from a worktree (they refuse; work from the main checkout).
````

- [ ] **Step 2: Verify the skill loads**

Run: `head -5 skills/issue-tracker/SKILL.md`
Expected: frontmatter with `name: issue-tracker` and the `description:` line.

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: `ALL TESTS PASSED` (unchanged — the skill is prose).

- [ ] **Step 3: Commit**

```bash
git add skills/issue-tracker/SKILL.md
git commit -m "issue-tracker: orchestrator skill with worker protocol block"
```

---

### Task 6: `issue-register` emits onto the board

**Files:**
- Modify: `skills/issue-register/SKILL.md`

**Interfaces:**
- Consumes: `board-register.sh` CLI from Task 1; ticket md format from Task 5.
- Produces: issue-register whose steps 6–7 register work-items on the board instead of writing a standalone register file.

- [ ] **Step 1: Replace checklist steps 6–7**

In `skills/issue-register/SKILL.md`, replace:

```markdown
6. **Write the register** — produce the map artifact (template below). Map-first (markdown); export to a tracker only if asked.
7. **Stop & hand off** — present the reviewed map. Per work-item the next step is depth elsewhere (`brainstorming`). When handing one off, pass its **register path + stable ID** (and parent ID if a child) so the link survives the boundary — the downstream work traces back to its register entry. Do NOT cross the seam here.
```

with:

```markdown
6. **Register onto the board** — for each work-item, run the `issue-tracker` skill's `board-register.sh` (title, `bug`/`enhancement`, `--parent`/`--blocked-by` edges; state `ready-for-agent` when complete & unblocked, `--state needs-info` when open questions remain, `--state deferred` when parked, `--state blocked` for non-ticket blockage — the last three need `--note`). Then write the ticket markdown the script names: a **self-contained pre-spec** carrying every decision from the grilling (template below).
7. **Stop & hand off** — present the board (`board-list.sh`). Each ticket is now a self-contained purpose-unit: the orchestrator dispatches daemons to `ELIGIBLE` tickets per the `issue-tracker` skill, or takes one into `brainstorming` in-session. Do NOT cross the seam here.
```

- [ ] **Step 2: Replace "The Register Artifact" section**

Replace the section starting `## The Register Artifact` down to (not including) `## Clustering Rules` with:

````markdown
## The Ticket Artifact

Each work-item becomes a board ticket: a node registered via `board-register.sh`
plus `doperpowers/issue-tracker/tickets/<id>-<slug>.md`:

```markdown
---
id: T7
title: <title>
category: bug | enhancement
---
## Problem & intent      ← what and why, from the user's perspective
## Constraints           ← non-negotiables, boundaries
## Success criteria      ← outcome, not implementation
## Open questions        ← unresolved after grilling
## Decision log          ← every decision from the grilling, dated
```

The md must be **self-contained**: a fresh-context daemon must be able to start
from this file alone. Every decision the grilling produced goes in the Decision
log — that is what lets the daemon drive brainstorm → PR with minimal
escalation.

State is NOT in the md — the board (`map.json`) is the single source of truth.
Cluster hierarchy → `--parent`; ordering → `--blocked-by`; parked → `--state
deferred`; open-questions-remain → `--state needs-info`.

Deliberately NOT in a ticket: solution, architecture, tech choices, file paths,
acceptance-criteria-as-tasks. Those belong downstream.
````

- [ ] **Step 3: Update the two mistake-table rows and one principle**

In the `## Common Mistakes` table, replace the row:

```markdown
| Dropping the link at handoff | Pass the register path + work-item ID (and parent ID) downstream so the graph survives the boundary. |
```

with:

```markdown
| Dropping the link at handoff | The board IS the link: register with `--parent`/`--blocked-by` edges before handing off. |
```

and replace the row:

```markdown
| Publishing implementation issues | That happens downstream, after design. The register is pre-spec. |
```

with:

```markdown
| Publishing implementation issues | Tickets are pre-spec purpose-units. Design happens downstream, driven by the ticket's daemon. |
```

In `## Key Principles`, replace:

```markdown
- **Keep the link** — every slice remembers its parent, and hands off with its register path + ID; the map is a graph, not a shredder.
```

with:

```markdown
- **Keep the link** — every slice remembers its parent as a board edge; the map is a graph, not a shredder.
```

- [ ] **Step 4: Verify and commit**

Run: `grep -n "board-register" skills/issue-register/SKILL.md`
Expected: at least one hit in step 6.

Run: `grep -n "docs/issue-register" skills/issue-register/SKILL.md`
Expected: no hits (old artifact path gone).

```bash
git add skills/issue-register/SKILL.md
git commit -m "issue-register: register work-items onto the issue-tracker board"
```

---

### Task 7: Full verification sweep

**Files:** none new.

- [ ] **Step 1: Full board suite**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: `ALL TESTS PASSED`, exit 0.

- [ ] **Step 2: Daemon suite unaffected**

Run: `tests/orchestrating-daemons/test-daemon-scripts.sh`
Expected: `ALL TESTS PASSED` (we never modified that toolkit).

- [ ] **Step 3: Shell lint baseline**

Run: `scripts/lint-shell.sh skills/issue-tracker/scripts/*.sh tests/issue-tracker/*.sh`
Expected: exit 0, no findings.

- [ ] **Step 4: Commit anything outstanding**

```bash
git status --short   # expect: clean
```
