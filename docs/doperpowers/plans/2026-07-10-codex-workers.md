# Codex Worker Species Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a symmetric Codex worker species (implementer + reviewer) beside the Claude daemons — same registry, same board protocol, engine chosen per dispatch — per `docs/doperpowers/specs/2026-07-10-codex-workers-design.md`.

**Architecture:** Sibling substrate scripts (`codex-spawn.sh`/`codex-resume.sh`) drive detached `codex exec --json` processes and write the same registry JSON as Claude daemons (`engine: codex`, `pid`, session id as key), so `board-bind.sh`/`board-reconcile.sh` work unchanged. Worker protocols keep one shared policy core; engine-specific text lives in `references/engine-blocks/` files composed at render time. Dispatch (review script + implement ritual) resolves the engine as label → `WORKER_ENGINE` → default `codex`.

**Tech Stack:** bash 3.2-compatible shell + embedded python3 (repo convention), `codex` CLI ≥ 0.142, `gh`, git worktrees, stub-binary shell tests.

## Global Constraints

- **Never** `--yolo` / `--dangerously-bypass-approvals-and-sandbox` on any codex invocation (spec: mirror of the `--dangerously-skip-permissions` ban).
- Every codex worker invocation carries: `--sandbox workspace-write`, `-c sandbox_workspace_write.network_access=true`, `-c features.hooks=false`, `-c approval_policy=on-request`, `-c approvals_reviewer=<auto value>` (default from Spike A, env-overridable via `CODEX_APPROVALS_REVIEWER`).
- Model/effort defaults: implement `gpt-5.6-sol`/`high`; review `gpt-5.6-sol`/`xhigh`.
- Registry: `~/.claude/orchestrating-daemons` (`DAEMON_HOME` override for tests). Codex meta is keyed by the codex session id; `current` always equals `uuid`.
- bash 3.2 compatible (macOS default): arrays OK; **no** `mapfile`, no associative arrays.
- `scripts/lint-shell.sh` must stay clean; all existing suites must stay green.
- Commit style: no `Co-Authored-By` / attribution lines. Commit after each task.

---

### Task 1: Spike A — `codex exec` contract (knowledge, not code)

**Files:**
- Modify: `docs/doperpowers/specs/2026-07-10-codex-workers-design.md` (record findings in `## Surprises & Discoveries`; adjust `## Revision Notes` if a finding contradicts the design)

**Question answered:** exact `--json` event shapes (`thread.started` field names, `agent_message` item shape, `turn.completed`/`turn.failed`), exit codes, resume-from-elsewhere semantics + flag acceptance, stdin-prompt on resume, and the approvals-reviewer config value headless.

- [ ] **Step 1: exec happy path + event shapes**

```bash
mkdir -p "$HOME/.claude/jobs-spike/repo" && cd "$HOME/.claude/jobs-spike/repo" && git init -q .
codex exec --json --sandbox workspace-write -c features.hooks=false \
  -m gpt-5.6-sol -c model_reasoning_effort=low \
  -o /tmp/spike-reply.txt - <<< "Reply with exactly the word: pong" \
  > /tmp/spike-events.jsonl 2>/tmp/spike-err.txt; echo "rc=$?"
head -3 /tmp/spike-events.jsonl; grep -o '"type":"[^"]*"' /tmp/spike-events.jsonl | sort | uniq -c
cat /tmp/spike-reply.txt
```

Observe: rc value; the `thread.started` event's id field name (`thread_id` vs `id`); the agent-message item's `type` string and text field; the terminal event name.

- [ ] **Step 2: failure exit code**

```bash
codex exec --json -m not-a-real-model - <<< "hi" >/tmp/spike-fail.jsonl 2>&1; echo "rc=$?"
tail -2 /tmp/spike-fail.jsonl
```

Observe: nonzero rc? error event shape?

- [ ] **Step 3: resume from another cwd, with flags + stdin prompt**

```bash
TID=$(python3 -c "import json,sys; print(next(json.loads(l).get('thread_id') or json.loads(l).get('id') for l in open('/tmp/spike-events.jsonl') if 'thread.started' in l))")
cd /tmp && codex exec resume "$TID" --json --sandbox workspace-write \
  -o /tmp/spike-reply2.txt - <<< "Now reply with exactly: pong2"; echo "rc=$?"
cat /tmp/spike-reply2.txt
```

Observe: resume works cross-cwd; flags accepted on resume; stdin `-` accepted (if not, note "resume prompt must be argv" — codex-resume.sh Step in Task 4 then passes the message as a positional arg instead of stdin).

- [ ] **Step 4: approvals reviewer headless**

```bash
cd "$HOME/.claude/jobs-spike/repo"
codex exec --json --sandbox workspace-write -c approval_policy=on-request \
  -c approvals_reviewer=auto_review -c features.hooks=false \
  - <<< "Run: git status. Then reply done." >/tmp/spike-appr.jsonl 2>&1; echo "rc=$?"
grep -c approval /tmp/spike-appr.jsonl || true
```

Repeat with `-c approvals_reviewer=guardian_subagent`. Observe: which value is accepted without error headless (check `codex exec --help` and `~/.codex/config.toml` docs if both pass). **The accepted value becomes the `CODEX_APPROVALS_REVIEWER` default in Task 3.**

- [ ] **Step 5: record verdicts**

Append to the spec's `## Surprises & Discoveries`: event field names, exit-code semantics, resume flag/stdin behavior, approvals value. If any finding contradicts a design statement, fix the spec and add a `## Revision Notes` line. Remove `/tmp/spike-*` and `~/.claude/jobs-spike`. Commit the spec update.

### Task 2: Spike B — sandbox vs worktree git, review composition, Codex-in-Codex (knowledge, not code)

**Files:**
- Modify: `docs/doperpowers/specs/2026-07-10-codex-workers-design.md` (same recording contract as Task 1)

**Question answered:** (a) can a sandboxed codex commit+push from a linked worktree with `--add-dir <main-root>`; (b) does `codex exec review --base X` compose with stdin PROMPT criteria; (c) does an inner `codex exec review --ephemeral` run under an outer sandboxed codex.

- [ ] **Step 1: scratch repo with linked worktree + local origin**

```bash
S=/tmp/spike-b; rm -rf "$S"; mkdir -p "$S"; cd "$S"
git init -q --bare origin.git && git clone -q origin.git main && cd main
git commit -q --allow-empty -m init && git push -q -u origin main 2>/dev/null || git push -q -u origin master
git worktree add -q ../wt -b feat
```

- [ ] **Step 2: sandboxed commit/push from the worktree**

```bash
cd "$S/wt"
codex exec --json --sandbox workspace-write -c features.hooks=false \
  --add-dir "$S/main" -m gpt-5.6-sol -c model_reasoning_effort=low - <<'T'
Create a file hello.txt containing "hi", git add + commit it (-m "feat: hi",
use -c user.email=t@t -c user.name=t), then git push origin HEAD:feat. Reply with the push result.
T
git -C "$S/main" log --oneline origin/feat 2>/dev/null || git -C "$S/wt" log --oneline -1
```

Observe: commit and push succeed with `--add-dir` pointing at the main clone root. If they fail, retry WITHOUT the worktree (direct clone) and record "linked worktrees need X" — the actual requirement found becomes `_codex_main_root`'s contract in Task 3.

- [ ] **Step 3: review composition**

```bash
cd "$S/wt" && printf 'x = 1/0\n' > bug.py && git add bug.py && git -c user.email=t@t -c user.name=t commit -qm "add bug"
codex exec review --base main --ephemeral -m gpt-5.6-sol \
  -c model_reasoning_effort=low -o /tmp/spike-review.txt - <<'C'
Beyond correctness, check SPEC COMPLIANCE: the change was supposed to add a
file named greeting.py. Report a finding if it does not.
C
cat /tmp/spike-review.txt
```

Observe: does the output contain BOTH a correctness finding (division by zero) AND the compliance finding (greeting.py missing)? If yes → composition works. If the PROMPT replaced the preset (no correctness finding), record it and note: engine block in Task 6 must spell full review criteria (cookbook-style) rather than relying on the preset.

- [ ] **Step 4: Codex-in-Codex**

```bash
cd "$S/wt"
codex exec --json --sandbox workspace-write -c features.hooks=false \
  -c sandbox_workspace_write.network_access=true --add-dir "$S/main" \
  -m gpt-5.6-sol -c model_reasoning_effort=low - <<'T'
Run this exact command and paste its last 5 lines:
codex exec review --base main --ephemeral -c model_reasoning_effort=low -o /tmp/inner.txt - <<<'Check correctness.'
T
```

Observe: inner review completes under the outer sandbox. If it fails on `~/.codex` writes, retry with the inner command prefixed `CODEX_HOME=$PWD/.codex-home` after `mkdir -p .codex-home && ln -s ~/.codex/auth.json .codex-home/auth.json` — record which variant works; the working one goes verbatim into the Task 6 engine block.

- [ ] **Step 5: record verdicts + cleanup + commit spec update**

Same contract as Task 1 Step 5. `rm -rf /tmp/spike-b /tmp/spike-review.txt`.

### Task 3: `_codex_lib.sh` + `codex-spawn.sh` + stub-codex tests

**Files:**
- Create: `skills/orchestrating-daemons/scripts/_codex_lib.sh`
- Create: `skills/orchestrating-daemons/scripts/codex-spawn.sh`
- Test: `tests/orchestrating-daemons/test-codex-scripts.sh`

**Interfaces:**
- Consumes: `_lib.sh` (`_meta_set`, `_meta_get`, `_reply_path`, `_reply_text`, `_now`, `_resolve_uuid`, `DAEMON_HOME`, `DAEMON_TIMEOUT`).
- Produces: `codex-spawn.sh [--no-wait] <name> <task> [cwd] [worktree] [model] [effort]` (same call shape as `daemon-spawn.sh` + trailing effort); registry meta with `engine`, `pid`, `effort`, `event_log` fields; `_codex_flags <model> <effort>` filling global array `CODEX_FLAGS`; `_codex_main_root <cwd>`, `_codex_thread_id <log>`, `_codex_last_message <log>`, `_codex_final_status <rc> <log>`.

- [ ] **Step 1: Write the failing test**

Create `tests/orchestrating-daemons/test-codex-scripts.sh` (executable). Full content:

```bash
#!/usr/bin/env bash
#
# Integration tests for the codex-engine half of the orchestrating-daemons
# toolkit. Hermetic: a STUB `codex` first on PATH mimics `codex exec --json`
# (thread.started + agent_message + turn.completed JSONL, -o reply file,
# resume). We drive the real scripts and assert on registry meta, replies,
# and status transitions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS_DIR="$REPO_ROOT/skills/orchestrating-daemons/scripts"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
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

export HOME="$TEST_ROOT/home"
export DAEMON_HOME="$TEST_ROOT/registry"
export STUB_STATE="$TEST_ROOT/stub"
export DAEMON_TIMEOUT=10
export DAEMON_UUID_POLL=5
WORK="$TEST_ROOT/work"
mkdir -p "$HOME" "$WORK" "$STUB_STATE"

STUB_BIN="$TEST_ROOT/bin"
mkdir -p "$STUB_BIN"
cat > "$STUB_BIN/codex" <<'STUB'
#!/usr/bin/env bash
# Minimal deterministic stand-in for `codex exec [resume]` (test use only).
# Event field names mirror the real CLI as pinned by Spike A.
set -euo pipefail
mkdir -p "$STUB_STATE"
echo "$*" >> "$STUB_STATE/calls.log"
[ "${1:-}" = "exec" ] || { echo "stub codex: only exec supported" >&2; exit 2; }
shift
resume=""
if [ "${1:-}" = "resume" ]; then resume="$2"; shift 2; fi
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift ;;
    -) : ;;
  esac
  shift
done
task="$(cat)"
if [ "${STUB_FAIL_EARLY:-0}" = "1" ]; then
  echo "stub codex: simulated launch failure" >&2
  exit 1
fi
if [ -z "$resume" ]; then
  n=$(cat "$STUB_STATE/n" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_STATE/n"
  tid="$(printf 'cdec%04d-0000-4000-8000-000000000000' "$n")"
else
  tid="$resume"
fi
printf '{"type":"thread.started","thread_id":"%s"}\n' "$tid"
[ "${STUB_SLEEP:-0}" != "0" ] && sleep "$STUB_SLEEP"
if [ "${STUB_FAIL_TURN:-0}" = "1" ]; then
  printf '{"type":"turn.failed","error":{"message":"stub turn failure"}}\n'
  exit 1
fi
reply="stub reply: $(printf '%s' "$task" | head -c 40)"
printf '{"type":"item.completed","item":{"type":"agent_message","text":"%s"}}\n' "$reply"
printf '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'
[ -n "$out" ] && printf '%s' "$reply" > "$out"
exit 0
STUB
chmod +x "$STUB_BIN/codex"
export PATH="$STUB_BIN:$PATH"

meta_field() {  # <uuid> <field>
    python3 -c "import json,sys; print(json.load(open('$DAEMON_HOME/$1.json')).get('$2',''))"
}
first_uuid() { basename "$(ls "$DAEMON_HOME"/cdec*.json | head -1)" .json; }

echo "== codex-spawn: blocking happy path =="
out="$("$SCRIPTS_DIR/codex-spawn.sh" job-a "say hi" "$WORK")"
uuid="$(first_uuid)"
assert_contains "$out" "--- reply ---" "blocking spawn prints reply banner"
assert_contains "$out" "stub reply: say hi" "blocking spawn prints the reply"
assert_equals "$(meta_field "$uuid" engine)" "codex" "meta engine=codex"
assert_equals "$(meta_field "$uuid" status)" "idle" "meta status=idle after clean turn"
assert_equals "$(meta_field "$uuid" turns)" "1" "meta turns=1"
assert_equals "$(meta_field "$uuid" current)" "$uuid" "current equals uuid"
assert_file_exists "$DAEMON_HOME/$uuid.reply.txt" "reply file recorded under uuid"
flags="$(grep 'exec' "$STUB_STATE/calls.log" | head -1)"
assert_contains "$flags" "--sandbox workspace-write" "spawn passes workspace-write"
assert_contains "$flags" "features.hooks=false" "spawn disables repo hooks"
assert_contains "$flags" "approval_policy=on-request" "spawn sets approval policy"
assert_contains "$flags" "model_reasoning_effort=high" "default effort high"
assert_contains "$flags" "-m gpt-5.6-sol" "default model gpt-5.6-sol"

echo "== codex-spawn: --no-wait leaves a working daemon, then finalizes =="
STUB_SLEEP=4 "$SCRIPTS_DIR/codex-spawn.sh" --no-wait job-b "slow task" "$WORK" >/dev/null
uuid_b="$(basename "$(ls -t "$DAEMON_HOME"/cdec*.json | head -1)" .json)"
assert_equals "$(meta_field "$uuid_b" status)" "working" "no-wait registers status=working"
pid_b="$(meta_field "$uuid_b" pid)"
if kill -0 "$pid_b" 2>/dev/null; then pass "recorded pid is alive mid-turn"; else fail "recorded pid is alive mid-turn"; fi
for _ in $(seq 1 15); do [ "$(meta_field "$uuid_b" status)" != "working" ] && break; sleep 1; done
assert_equals "$(meta_field "$uuid_b" status)" "idle" "watcher finalizes status=idle"
assert_file_exists "$DAEMON_HOME/$uuid_b.reply.txt" "watcher records reply file"

echo "== codex-spawn: turn failure -> error =="
STUB_FAIL_TURN=1 "$SCRIPTS_DIR/codex-spawn.sh" job-c "will fail" "$WORK" >/dev/null 2>&1 || true
uuid_c="$(basename "$(ls -t "$DAEMON_HOME"/cdec*.json | head -1)" .json)"
assert_equals "$(meta_field "$uuid_c" status)" "error" "failed turn records status=error"

echo "== codex-spawn: launch failure fails loud, registers nothing =="
n_before="$(ls "$DAEMON_HOME"/*.json 2>/dev/null | wc -l | tr -d ' ')"
if STUB_FAIL_EARLY=1 "$SCRIPTS_DIR/codex-spawn.sh" job-d "never starts" "$WORK" >/dev/null 2>&1; then
    fail "early failure exits nonzero"
else
    pass "early failure exits nonzero"
fi
n_after="$(ls "$DAEMON_HOME"/*.json 2>/dev/null | wc -l | tr -d ' ')"
assert_equals "$n_after" "$n_before" "early failure registers no meta"

echo ""
if [ "$FAILURES" -eq 0 ]; then echo "ALL TESTS PASSED"; else echo "$FAILURES FAILURE(S)"; exit 1; fi
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `tests/orchestrating-daemons/test-codex-scripts.sh`
Expected: FAIL — `codex-spawn.sh: No such file or directory`.

- [ ] **Step 3: Write `_codex_lib.sh`**

Create `skills/orchestrating-daemons/scripts/_codex_lib.sh`:

```bash
#!/usr/bin/env bash
# _codex_lib.sh — codex-engine helpers for the orchestrating-daemons toolkit.
# Sourced by codex-spawn.sh / codex-resume.sh AFTER _lib.sh.
#
# A codex daemon is a detached `codex exec --json` process. Unlike `claude
# --bg` there is no supervisor: WE detach it, WE record its pid, and a wrapper
# shell around the process finalizes the registry when the turn ends. The meta
# is the same JSON contract as claude daemons plus:
#   engine     "codex"
#   pid        codex process pid of the CURRENT turn (liveness: kill -0)
#   effort     model_reasoning_effort
#   event_log  JSONL event stream of the current turn (--json stdout)
# The codex session id (thread.started) keys the registry, so board-bind.sh /
# _resolve_uuid prefix matching work unchanged. Codex sessions keep ONE id
# across resumes — `current` always equals `uuid`.

# Default flags for every codex worker. NEVER add
# --dangerously-bypass-approvals-and-sandbox / --yolo here or at call sites —
# sandbox + approvals reviewer IS the safety contract (mirror of the
# claude-side --dangerously-skip-permissions ban). Fills global CODEX_FLAGS
# (bash 3.2: no mapfile).
_codex_flags() {  # <model> <effort>
  CODEX_FLAGS=( --json --sandbox workspace-write
    -c 'sandbox_workspace_write.network_access=true'
    -c 'features.hooks=false'
    -c 'approval_policy=on-request'
    -c "approvals_reviewer=${CODEX_APPROVALS_REVIEWER:-auto_review}"
    -m "$1" -c "model_reasoning_effort=$2" )
}

# If <cwd> is a LINKED worktree, echo the main repo root — its real .git lives
# there, outside the sandbox's workspace root, so it must be --add-dir'ed for
# commits to work (Spike B). Empty for a normal checkout / non-repo.
_codex_main_root() {
  local gd cd_
  gd="$(git -C "$1" rev-parse --git-dir 2>/dev/null)" || { printf ''; return 0; }
  cd_="$(git -C "$1" rev-parse --git-common-dir 2>/dev/null)" || { printf ''; return 0; }
  gd="$(cd "$1" 2>/dev/null && cd "$gd" 2>/dev/null && pwd -P)"
  cd_="$(cd "$1" 2>/dev/null && cd "$cd_" 2>/dev/null && pwd -P)"
  if [ -n "$gd" ] && [ -n "$cd_" ] && [ "$gd" != "$cd_" ]; then
    git -C "$cd_/.." rev-parse --show-toplevel 2>/dev/null || printf ''
  else
    printf ''
  fi
}

# Session/thread id from a --json event log (thread.started). Field names per
# Spike A; tolerant of drift (thread_id, then id).
_codex_thread_id() {
  [ -f "$1" ] || { printf ''; return 0; }
  python3 - "$1" <<'PY'
import json, sys
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("type") == "thread.started":
        print(d.get("thread_id") or d.get("id") or "")
        break
PY
}

# Last agent_message text from an event log — the live "reply so far", and the
# reply fallback when -o was never written (killed turn).
_codex_last_message() {
  [ -f "$1" ] || { printf ''; return 0; }
  python3 - "$1" <<'PY'
import json, sys
text = ""
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    item = d.get("item") or {}
    if isinstance(item, dict) and item.get("type") == "agent_message":
        t = item.get("text") or item.get("content") or ""
        if isinstance(t, list):
            t = " ".join(b.get("text", "") for b in t if isinstance(b, dict))
        if str(t).strip():
            text = str(t).strip()
print(text)
PY
}

# Terminal status for a finished turn: rc wins; a turn.failed event also means
# error even on rc 0 (belt and suspenders — payloads drift across versions).
_codex_final_status() {  # <rc> <event_log>
  if [ "$1" != "0" ]; then printf 'error'; return 0; fi
  if [ -f "$2" ] && grep -q '"type"[[:space:]]*:[[:space:]]*"turn.failed"' "$2"; then
    printf 'error'; return 0
  fi
  printf 'idle'
}

# Launch one detached codex turn: backgrounds codex inside a nohup'd wrapper
# that records the codex pid, waits for it, captures rc, and finalizes the
# registry (status + reply file) — the wrapper IS the watcher and survives the
# calling script. Args: <cwd> <taskfile> <run-prefix> then the codex argv after
# `codex` (e.g. exec --json ... or exec resume <id> ...). The -o/- redirection
# is appended here.
_codex_launch() {
  local cwd="$1" taskf="$2" run="$3"; shift 3
  nohup bash -c '
    set -u
    DIR="$1"; cwd="$2"; taskf="$3"; run="$4"; shift 4
    # shellcheck source=/dev/null
    source "$DIR/_lib.sh"; source "$DIR/_codex_lib.sh"
    cd "$cwd" || { echo 127 > "$run.rc"; exit 0; }
    codex "$@" -o "$run.reply.txt" - < "$taskf" > "$run.events.jsonl" 2> "$run.err" &
    cpid=$!
    echo "$cpid" > "$run.pid"
    rc=0; wait "$cpid" || rc=$?
    uuid="$(_codex_thread_id "$run.events.jsonl")"
    if [ -z "$uuid" ]; then echo "$rc" > "$run.rc"; exit 0; fi   # never produced a session — spawn fails loud instead
    status="$(_codex_final_status "$rc" "$run.events.jsonl")"
    if [ -s "$run.reply.txt" ]; then
      cp "$run.reply.txt" "$(_reply_path "$uuid")"
    else
      _codex_last_message "$run.events.jsonl" > "$(_reply_path "$uuid")"
    fi
    _meta_set "$uuid" status "$status" updated "$(_now)"
    echo "$rc" > "$run.rc"   # completion barrier — written LAST, after all finalization
  ' _ "$CODEX_LIB_DIR" "$cwd" "$taskf" "$run" "$@" >/dev/null 2>&1 &
}
```

- [ ] **Step 4: Write `codex-spawn.sh`**

Create `skills/orchestrating-daemons/scripts/codex-spawn.sh` (executable):

```bash
#!/usr/bin/env bash
# codex-spawn.sh [--no-wait] <name> <task> [cwd] [worktree] [model] [effort]
#
# Spawn a durable background CODEX worker (`codex exec --json`, detached) — the
# codex sibling of daemon-spawn.sh, writing the SAME registry so board-bind /
# board-reconcile / daemon-list work unchanged. Runs the FIRST turn, waits for
# it, and records the reply. NEVER RUN IN THE FOREGROUND (same contract as
# daemon-spawn.sh): use a Monitor or a background shell.
#
#   name       display name (registry)
#   task       initial prompt (delivered via stdin — no ARG_MAX limit on codex)
#   cwd        repo/dir the worker runs in (default: $PWD)
#   worktree   OPTIONAL worktree name → isolated git worktree at
#              <cwd>/.claude/worktrees/<name> on branch worktree-<name>
#              (created here; claude's --worktree is claude-native)
#   model      default $CODEX_MODEL or gpt-5.6-sol
#   effort     default $CODEX_EFFORT or high
#   --no-wait  register as soon as the session id materializes and return
#
# Status semantics: codex exec has no interactive approval prompts, so a codex
# daemon is NEVER `blocked` — the approvals reviewer adjudicates escalations
# in-flight; a declined escalation is a failed command the worker sees.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"
# shellcheck source=_codex_lib.sh
source "$DIR/_codex_lib.sh"
CODEX_LIB_DIR="$DIR"; export CODEX_LIB_DIR

nowait=0
if [ "${1:-}" = "--no-wait" ]; then nowait=1; shift; fi
name="${1:?usage: codex-spawn.sh [--no-wait] <name> <task> [cwd] [worktree] [model] [effort]}"
task="${2:?missing task}"
cwd="${3:-$PWD}"
worktree="${4:-}"
model="${5:-${CODEX_MODEL:-gpt-5.6-sol}}"
effort="${6:-${CODEX_EFFORT:-high}}"

command -v codex >/dev/null 2>&1 || { echo "codex-spawn: codex CLI not found" >&2; exit 1; }

# Worktree isolation (mirror of claude --worktree; reuse an existing one).
runcwd="$cwd"
if [ -n "$worktree" ]; then
  wt="$(printf '%s' "$worktree" | tr -c 'a-zA-Z0-9._-' '-')"
  wtdir="$cwd/.claude/worktrees/$wt"
  if [ ! -d "$wtdir" ]; then
    git -C "$cwd" worktree add "$wtdir" -b "worktree-$wt" >/dev/null 2>&1 \
      || git -C "$cwd" worktree add "$wtdir" "worktree-$wt" >/dev/null \
      || { echo "codex-spawn: worktree add failed for $wt" >&2; exit 1; }
  fi
  runcwd="$wtdir"
fi

runs="$DAEMON_HOME/runs"; mkdir -p "$runs"
run="$(mktemp "$runs/codex-run.XXXXXX")"; rm -f "$run"
taskf="$run.task.txt"
printf '%s' "$task" > "$taskf"

_codex_flags "$model" "$effort"
addroot="$(_codex_main_root "$runcwd")"
[ -n "$addroot" ] && CODEX_FLAGS=( "${CODEX_FLAGS[@]}" --add-dir "$addroot" )

_codex_launch "$runcwd" "$taskf" "$run" exec "${CODEX_FLAGS[@]}"

# Register as soon as the session id materializes.
uuid=""; i=0; max="${DAEMON_UUID_POLL:-30}"
while [ -z "$uuid" ]; do
  uuid="$(_codex_thread_id "$run.events.jsonl")"
  [ -n "$uuid" ] && break
  if [ -f "$run.rc" ] && [ -z "$(_codex_thread_id "$run.events.jsonl")" ]; then
    echo "codex-spawn: codex exited (rc=$(cat "$run.rc")) before a session id:" >&2
    tail -5 "$run.err" >&2 2>/dev/null || true
    exit 1
  fi
  i=$((i + 1)); [ "$i" -ge "$max" ] && break
  sleep 2
done
[ -n "$uuid" ] || { echo "codex-spawn: no session id after $((max * 2))s" >&2; exit 1; }

pid="$(cat "$run.pid" 2>/dev/null || printf '')"
status="working"
[ -f "$run.rc" ] && status="$(_codex_final_status "$(cat "$run.rc")" "$run.events.jsonl")"
_meta_set "$uuid" \
  uuid "$uuid" current "$uuid" short "$(printf '%.8s' "$uuid")" name "$name" \
  task "$task" cwd "$runcwd" worktree "$worktree" model "$model" effort "$effort" \
  engine "codex" pid "$pid" event_log "$run.events.jsonl" \
  status "$status" created "$(_now)" updated "$(_now)" turns "1"
# The wrapper may have finalized between our check and the write — re-apply.
[ -f "$run.rc" ] && _meta_set "$uuid" \
  status "$(_codex_final_status "$(cat "$run.rc")" "$run.events.jsonl")" updated "$(_now)"

if [ "$nowait" -eq 1 ]; then
  echo "daemon spawned (no-wait): $name  [codex $(printf '%.8s' "$uuid") / $uuid]  status=$(_meta_get "$uuid" status)  (reply: daemon-reply.sh $(printf '%.8s' "$uuid"))"
  exit 0
fi

# Blocking: wait for the wrapper's rc, bounded by DAEMON_TIMEOUT (watcher bound
# only — the turn itself is never killed; on timeout status stays working).
i=0; max=$((DAEMON_TIMEOUT / 2)); [ "$max" -le 0 ] && max=0
while [ ! -f "$run.rc" ]; do
  i=$((i + 1))
  if [ "$max" -gt 0 ] && [ "$i" -ge "$max" ]; then
    echo "daemon spawned: $name  [codex $uuid]  status=working (watcher timeout — turn continues; reply: daemon-reply.sh $(printf '%.8s' "$uuid"))"
    exit 0
  fi
  sleep 2
done
echo "daemon spawned: $name  [codex $(printf '%.8s' "$uuid") / $uuid]  status=$(_meta_get "$uuid" status)"
echo "--- reply ---"
_reply_text "$uuid"
```

> Amended during execution: `$run.rc` is written last as the completion barrier (review finding — fixed write-ordering race; the fixed sleep is gone).

> Amended during Task 4 execution: `_codex_flags` was split into a shared
> `_codex_flags_common <model> <effort> <sandbox-flag...>` plus `_codex_flags`
> (fresh spawn: `--sandbox workspace-write`) and a new `_codex_resume_flags`
> (resume: `-c sandbox_mode=workspace-write`, since `codex exec resume` has no
> `--sandbox` option — rc=2, no JSON, spike-proven). See Task 4's amendment
> note for the full rationale.

- [ ] **Step 5: Run the tests**

Run: `tests/orchestrating-daemons/test-codex-scripts.sh`
Expected: ALL TESTS PASSED.

- [ ] **Step 6: Lint + existing daemon suite**

Run: `scripts/lint-shell.sh && tests/orchestrating-daemons/test-daemon-scripts.sh`
Expected: lint clean; existing suite ALL TESTS PASSED.

- [ ] **Step 7: Commit**

```bash
git add skills/orchestrating-daemons/scripts/_codex_lib.sh skills/orchestrating-daemons/scripts/codex-spawn.sh tests/orchestrating-daemons/test-codex-scripts.sh
git commit -m "feat(orchestrating-daemons): codex-spawn — detached codex exec 워커, 공유 레지스트리"
```

### Task 4: `codex-resume.sh` + engine guard in `daemon-resume.sh`

**Files:**
- Create: `skills/orchestrating-daemons/scripts/codex-resume.sh`
- Modify: `skills/orchestrating-daemons/scripts/daemon-resume.sh` (engine guard after uuid resolution)
- Test: `tests/orchestrating-daemons/test-codex-scripts.sh`

**Interfaces:**
- Consumes: registry meta from Task 3 (`engine`, `pid`, `cwd`, `model`, `effort`), `_codex_launch`, `_codex_flags`, `_resolve_uuid`.
- Produces: `codex-resume.sh <uuid-or-prefix> <message>`; `daemon-resume.sh` rejects codex daemons with "use codex-resume.sh".

- [ ] **Step 1: Write the failing tests** — append to `tests/orchestrating-daemons/test-codex-scripts.sh` before the final summary block:

```bash
echo "== codex-resume: same session id, turns increment =="
out="$("$SCRIPTS_DIR/codex-resume.sh" "$uuid" "follow up")"
assert_contains "$out" "stub reply: follow up" "resume prints the new reply"
assert_equals "$(meta_field "$uuid" turns)" "2" "resume increments turns"
assert_equals "$(meta_field "$uuid" current)" "$uuid" "resume keeps the session id"
assert_contains "$(cat "$STUB_STATE/calls.log")" "exec resume $uuid" "stub saw exec resume <uuid>"

echo "== engine guards =="
if "$SCRIPTS_DIR/daemon-resume.sh" "$uuid" "hi" >/dev/null 2>&1; then
    fail "daemon-resume refuses a codex daemon"
else
    pass "daemon-resume refuses a codex daemon"
fi
if "$SCRIPTS_DIR/codex-resume.sh" "not-a-daemon" "hi" >/dev/null 2>&1; then
    fail "codex-resume errors on unknown id"
else
    pass "codex-resume errors on unknown id"
fi

echo "== codex-resume: refuses a live working turn =="
STUB_SLEEP=4 "$SCRIPTS_DIR/codex-spawn.sh" --no-wait job-e "long turn" "$WORK" >/dev/null
uuid_e="$(basename "$(ls -t "$DAEMON_HOME"/cdec*.json | head -1)" .json)"
if "$SCRIPTS_DIR/codex-resume.sh" "$uuid_e" "interrupt" >/dev/null 2>&1; then
    fail "resume refuses while a turn is live"
else
    pass "resume refuses while a turn is live"
fi
for _ in $(seq 1 15); do [ "$(meta_field "$uuid_e" status)" != "working" ] && break; sleep 1; done
```

- [ ] **Step 2: Run to verify failure** — Run: `tests/orchestrating-daemons/test-codex-scripts.sh`. Expected: FAIL at "codex-resume".

- [ ] **Step 3: Write `codex-resume.sh`** (executable):

```bash
#!/usr/bin/env bash
# codex-resume.sh <uuid-or-prefix-or-name-short> <message>
#
# Continue a CODEX daemon: `codex exec resume <session-id>` — the codex sibling
# of daemon-resume.sh. Unlike claude, codex keeps ONE session id across
# resumes: no forking, no purge, `current` never changes. NEVER RUN IN THE
# FOREGROUND (blocks while the turn runs) — Monitor or background shell.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"
# shellcheck source=_codex_lib.sh
source "$DIR/_codex_lib.sh"
CODEX_LIB_DIR="$DIR"; export CODEX_LIB_DIR

uuid="$(_resolve_uuid "${1:?usage: codex-resume.sh <id> <message>}")"
msg="${2:?missing message}"

[ "$(_meta_get "$uuid" engine)" = "codex" ] \
  || { echo "codex-resume: $uuid is not a codex daemon — use daemon-resume.sh" >&2; exit 1; }

# One turn per daemon at a time (same invariant as claude daemons).
if [ "$(_meta_get "$uuid" status)" = "working" ]; then
  pid="$(_meta_get "$uuid" pid)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "codex-resume: a turn is still running (pid $pid) — wait for it or retire" >&2
    exit 1
  fi
  # The pid is dead, but liveness (pid) and the registry write that finalizes
  # a turn (status) are two different signals read non-atomically: the prior
  # turn's _codex_launch wrapper can still be finalizing (_meta_set landing
  # AFTER our writes below would flip the registry back to a stale terminal
  # status mid-flight). The wrapper's rc file is its completion barrier — it
  # is written LAST, once the registry + reply are already finalized (see
  # _codex_launch) — so derive it from this meta's event_log
  # ("<run>.events.jsonl" -> "<run>.rc") and wait a bounded window for it.
  # If it appears, finalization is complete: re-read the finalized status
  # (the "working" value that got us here is stale) and proceed on it —
  # terminal idle/error is the expected shape; anything else is surfaced as
  # a note. If it never appears, the previous wrapper died mid-flight —
  # warn and proceed. No event_log in the meta -> nothing to wait on.
  prev_log="$(_meta_get "$uuid" event_log)"
  if [ -n "$prev_log" ]; then
    prev_rc="${prev_log%.events.jsonl}.rc"
    bound="${CODEX_RC_BARRIER_WAIT:-10}"
    j=0
    while [ ! -f "$prev_rc" ] && [ "$j" -lt "$bound" ]; do sleep 1; j=$((j + 1)); done
    if [ -f "$prev_rc" ]; then
      # Barrier landed — base the guard's decision on the FINALIZED status,
      # not the stale read above. Terminal (idle/error) means the prior turn
      # is fully wrapped up and the daemon is safely resumable. A lingering
      # "working" would take a wrapper that wrote rc without finalizing,
      # which _codex_launch cannot do — but the pid is dead either way, so
      # the turn is over regardless; surface the anomaly and continue.
      [ "$(_meta_get "$uuid" status)" = "working" ] && echo \
        "codex-resume: prior turn's rc landed but status is still 'working' — proceeding (pid dead, turn over)" >&2
    else
      echo "codex-resume: prior turn's completion barrier never appeared after ${bound}s — proceeding (wrapper presumed dead)" >&2
    fi
  fi
fi

cwd="$(_meta_get "$uuid" cwd)"; [ -d "$cwd" ] || cwd="$PWD"
model="$(_meta_get "$uuid" model)"; [ -n "$model" ] || model="${CODEX_MODEL:-gpt-5.6-sol}"
effort="$(_meta_get "$uuid" effort)"; [ -n "$effort" ] || effort="${CODEX_EFFORT:-high}"

runs="$DAEMON_HOME/runs"; mkdir -p "$runs"
run="$(mktemp "$runs/codex-run.XXXXXX")"; rm -f "$run"
taskf="$run.task.txt"
printf '%s' "$msg" > "$taskf"

# Resume-specific flags: `codex exec resume` has no --sandbox option at all
# (rc=2, no JSON — see _codex_resume_flags). Everything else (-m, effort,
# network, hooks, approvals) is unchanged from a fresh spawn.
_codex_resume_flags "$model" "$effort"
addroot="$(_codex_main_root "$cwd")"
[ -n "$addroot" ] && CODEX_FLAGS=( "${CODEX_FLAGS[@]}" --add-dir "$addroot" )

_codex_launch "$cwd" "$taskf" "$run" exec resume "$uuid" "${CODEX_FLAGS[@]}"

# Wait for the new pid (catches a `cd` failure, which never even backgrounds
# codex and writes an rc file directly instead).
i=0
while [ ! -f "$run.pid" ]; do
  if [ -f "$run.rc" ]; then break; fi
  i=$((i + 1)); [ "$i" -ge 15 ] && break
  sleep 1
done

# Early-failure detection (mirrors codex-spawn.sh's no-session-id guard): a
# CLI-argument-level failure (rc=2) exits before ever emitting this uuid's
# thread.started event, so its rc file can appear while the event log still
# shows no activity at all. Only treat the resume as a real turn — and only
# THEN bump turns — once we see that activity, or a short bounded wait for
# it runs out (at which point a turn is presumably genuinely underway).
i=0; max="${DAEMON_UUID_POLL:-30}"; started=""
while :; do
  if [ -n "$(_codex_thread_id "$run.events.jsonl")" ]; then started=1; break; fi
  if [ -f "$run.rc" ]; then break; fi
  i=$((i + 1)); [ "$i" -ge "$max" ] && { started=1; break; }
  sleep 2
done

if [ -z "$started" ]; then
  rc="$(cat "$run.rc" 2>/dev/null || printf '1')"
  echo "codex-resume: turn failed to start (rc=$rc) — turns not incremented:" >&2
  tail -5 "$run.err" >&2 2>/dev/null || true
  exit 1
fi

turns="$(_meta_get "$uuid" turns)"; turns=$((${turns:-1} + 1))
_meta_set "$uuid" pid "$(cat "$run.pid" 2>/dev/null || printf '')" \
  event_log "$run.events.jsonl" status "working" turns "$turns" updated "$(_now)"
[ -f "$run.rc" ] && _meta_set "$uuid" \
  status "$(_codex_final_status "$(cat "$run.rc")" "$run.events.jsonl")" updated "$(_now)"

# Blocking wait (same bound + semantics as codex-spawn — rc IS the completion
# barrier: _codex_launch writes it last, after the registry/reply are already
# finalized, so no post-loop settle sleep is needed here).
i=0; max=$((DAEMON_TIMEOUT / 2)); [ "$max" -le 0 ] && max=0
while [ ! -f "$run.rc" ]; do
  i=$((i + 1))
  if [ "$max" -gt 0 ] && [ "$i" -ge "$max" ]; then
    echo "resumed: [codex $uuid] status=working (watcher timeout — turn continues)"
    exit 0
  fi
  sleep 2
done
echo "resumed: [codex $(printf '%.8s' "$uuid")] status=$(_meta_get "$uuid" status)"
echo "--- reply ---"
_reply_text "$uuid"
```

> Amended during execution: resume flags use -c sandbox_mode (resume rejects
> --sandbox, spike-proven); turns bump gated on the turn actually starting;
> dead-pid resume waits on the prior run's rc barrier — and (re-review) once
> the barrier lands it re-reads the finalized status instead of trusting the
> stale "working" read, while a barrier that never lands is surfaced with a
> one-line stderr warning before proceeding.

- [ ] **Step 4: Guard `daemon-resume.sh`** — immediately after its `uuid="$(_resolve_uuid ...)"` line, insert:

```bash
[ "$(_meta_get "$uuid" engine)" = "codex" ] \
  && { echo "daemon-resume: $uuid is a codex daemon — use codex-resume.sh" >&2; exit 1; }
```

- [ ] **Step 5: Run tests** — `tests/orchestrating-daemons/test-codex-scripts.sh` → ALL TESTS PASSED; `tests/orchestrating-daemons/test-daemon-scripts.sh` → still green.

- [ ] **Step 6: Commit**

```bash
git add skills/orchestrating-daemons/scripts/codex-resume.sh skills/orchestrating-daemons/scripts/daemon-resume.sh tests/orchestrating-daemons/test-codex-scripts.sh
git commit -m "feat(orchestrating-daemons): codex-resume + 엔진 가드 — 단일 세션 id 재개"
```

### Task 5: read-side engine awareness — `daemon-list.sh`, `daemon-reply.sh`, `daemon-retire.sh`

**Files:**
- Modify: `skills/orchestrating-daemons/scripts/daemon-list.sh`
- Modify: `skills/orchestrating-daemons/scripts/daemon-reply.sh`
- Modify: `skills/orchestrating-daemons/scripts/daemon-retire.sh`
- Test: `tests/orchestrating-daemons/test-codex-scripts.sh`

**Interfaces:**
- Consumes: meta fields `engine`, `pid`, `event_log`, `_codex_last_message`.
- Produces: `daemon-list.sh` ENG column; `daemon-reply.sh` codex branch; `daemon-retire.sh` kills a live codex pid and prints a codex resume hint.

- [ ] **Step 1: Write the failing tests** — append before the summary block:

```bash
echo "== read-side engine awareness =="
listing="$("$SCRIPTS_DIR/daemon-list.sh")"
assert_contains "$listing" "ENG" "daemon-list has an engine column"
assert_contains "$listing" "codex" "daemon-list shows codex engine"
reply_out="$("$SCRIPTS_DIR/daemon-reply.sh" "$uuid")"
assert_contains "$reply_out" "stub reply: follow up" "daemon-reply prints the codex reply"

echo "== daemon-retire kills a live codex turn =="
STUB_SLEEP=30 "$SCRIPTS_DIR/codex-spawn.sh" --no-wait job-f "hang" "$WORK" >/dev/null
uuid_f="$(basename "$(ls -t "$DAEMON_HOME"/cdec*.json | head -1)" .json)"
pid_f="$(meta_field "$uuid_f" pid)"
retire_out="$("$SCRIPTS_DIR/daemon-retire.sh" "$uuid_f")"
assert_contains "$retire_out" "codex resume $uuid_f" "retire prints codex resume hint"
sleep 1
if kill -0 "$pid_f" 2>/dev/null; then fail "retire stops the live codex turn"; else pass "retire stops the live codex turn"; fi
assert_equals "$(meta_field "$uuid_f" status)" "retired" "retire records status"
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL at "engine column".

- [ ] **Step 3: `daemon-list.sh`** — in the python block, change the row build and print:

```python
    rows.append((m.get("updated", ""), m.get("name", "?"), short, m.get("status", "?"),
                 m.get("engine", "claude"), m.get("turns", "0"), reply))
```

```python
print(f"{'NAME':<18} {'SHORT':<9} {'STATUS':<14} {'ENG':<6} {'T':>2}  LATEST REPLY")
print("-" * 96)
for updated, name, short, status, engine, turns, reply in rows:
    print(f"{name[:18]:<18} {short[:8]:<9} {status:<14} {engine[:6]:<6} {str(turns):>2}  {reply[:46]}")
```

- [ ] **Step 4: `daemon-reply.sh`** — after the `source "$DIR/_lib.sh"` line add `source "$DIR/_codex_lib.sh"` (with a `# shellcheck source=_codex_lib.sh` line), and immediately after the `echo "--- latest reply ---"` / `cur=` lines, insert the codex branch before the existing working-status logic:

```bash
if [ "$(_meta_get "$uuid" engine)" = "codex" ]; then
  # Codex daemons have no claude transcript: a finished turn's reply is the
  # recorded reply file; a live turn's best truth is the event log so far.
  if [ "$(_meta_get "$uuid" status)" = "working" ]; then
    live="$(_codex_last_message "$(_meta_get "$uuid" event_log)")"
    if [ -n "$live" ]; then printf '%s\n' "$live"; else echo "(turn in progress — no message yet)"; fi
  else
    _reply_text "$uuid"
  fi
  exit 0
fi
```

- [ ] **Step 5: `daemon-retire.sh`** — replace the `claude stop` line and the final echo hints with engine-aware versions:

```bash
engine="$(_meta_get "$uuid" engine)"
if [ "$engine" = "codex" ]; then
  pid="$(_meta_get "$uuid" pid)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    # Killing the pid wakes _codex_launch's detached wrapper (its `wait` on the
    # codex pid returns), which then writes its OWN terminal status — racing the
    # "retired" write below and reliably clobbering it back to error/idle. Wait
    # on the wrapper's rc completion barrier (same one codex-resume.sh waits on)
    # so "retired" is the last word. Gated behind a live pid, so idle daemons
    # pay zero added latency.
    log="$(_meta_get "$uuid" event_log)"
    if [ -n "$log" ]; then
      rc_barrier="${log%.events.jsonl}.rc"
      bound="${CODEX_RC_BARRIER_WAIT:-10}"; j=0
      while [ ! -f "$rc_barrier" ] && [ "$j" -lt "$bound" ]; do sleep 1; j=$((j + 1)); done
    fi
  fi
  resume_hint="codex resume $uuid"
else
  [ -n "$short" ] && claude stop "$short" >/dev/null 2>&1 || true
  resume_hint="claude --resume $uuid"
fi
```

and in the two echo lines replace `claude --resume $uuid` with `$resume_hint`.

> Amended during execution: the original Step-5 snippet killed the pid then
> wrote `status=retired` with no wait — a deterministic race (reproduced 3/3,
> timestamp-instrumented) against `_codex_launch`'s detached finalization
> wrapper, which the kill itself wakes and which then clobbers "retired" back
> to a terminal status. Fixed with a bounded rc-barrier wait mirroring
> `codex-resume.sh`'s dead-pid guard, scoped to the live-pid codex branch only.

- [ ] **Step 6: Run tests** — codex suite ALL PASSED, daemon suite still green, `scripts/lint-shell.sh` clean.

- [ ] **Step 7: Commit**

```bash
git add skills/orchestrating-daemons/scripts/daemon-list.sh skills/orchestrating-daemons/scripts/daemon-reply.sh skills/orchestrating-daemons/scripts/daemon-retire.sh tests/orchestrating-daemons/test-codex-scripts.sh
git commit -m "feat(orchestrating-daemons): 리드사이드 엔진 인식 — ENG 컬럼, codex 리플라이/리타이어"
```

### Task 6: review protocol — engine blocks + template surgery

**Files:**
- Create: `skills/reviewing-prs/references/engine-blocks/engine-codex-review.md`
- Create: `skills/reviewing-prs/references/engine-blocks/fallback-claude.md`
- Create: `skills/reviewing-prs/references/engine-blocks/fallback-codex.md`
- Modify: `skills/reviewing-prs/references/review-worker-protocol.md`

**Interfaces:**
- Produces: template placeholders `{{ENGINE_BLOCK}}`, `{{FALLBACK_BLOCK}}`; blocks use only placeholders the dispatch already renders plus `CODEX_REVIEW_MODEL`/`CODEX_REVIEW_EFFORT` (added in Task 7).

- [ ] **Step 1: `engine-codex-review.md`** (the shared engine block — both species):

```markdown
REVIEW ENGINE — the native Codex reviewer via the COOKBOOK pattern (plain
`codex exec` with a self-diffing prompt). Run it from the worktree root
(`codex exec` has no -C flag for this; cd there first).

DO NOT use the `codex exec review` subcommand with a target flag: `--base`,
`--commit`, and `--uncommitted` each hard-conflict with a custom PROMPT at
the CLI parser (exit 2, no output) — no targeting flag can be combined with
custom spec-compliance criteria in one call. Instruct the diff in the prompt
instead, so a plain `codex exec` reviews the full multi-commit PR range.

If YOU are yourself a Codex worker (this call would nest codex-in-codex),
first give the inner call its own writable home, or its app-server client
fails to start ("Operation not permitted"):

  mkdir -p .codex-home && ln -sf ~/.codex/auth.json .codex-home/auth.json
  export CODEX_HOME="$PWD/.codex-home"

(The nested review then runs under stock read-only defaults — exactly what a
reviewer needs.) A Claude worker skips this — its `codex exec` is not nested.

Then compose the review call — paste the ticket brief's requirements /
acceptance criteria into the COMPLIANCE section (when the ticket is "none",
drop that section and review correctness only):

  cd <worktree-root> && codex exec --ephemeral -m {{CODEX_REVIEW_MODEL}} \
    -c model_reasoning_effort={{CODEX_REVIEW_EFFORT}} \
    -c features.hooks=false \
    -o /tmp/review-pr-{{PR_NUMBER}}-findings.txt - <<'CRITERIA'
  Review PR #{{PR_NUMBER}} ({{PR_TITLE}}). FIRST run
  `git diff origin/{{BASE_REF}}...HEAD` to see the ENTIRE PR range — every
  commit since the branch left origin/{{BASE_REF}}, not just the last commit —
  and review that whole diff.
  Review it for CORRECTNESS as a rigorous reviewer would (bugs, broken edge
  cases, unsafe or regressive changes), AND for SPEC COMPLIANCE against its
  ticket:
  <ticket requirements / acceptance criteria — paste from the brief below>
  Compliance checks: (1) does the diff fulfill every acceptance criterion?
  (2) is anything in the diff outside the ticket's scope? (3) does the PR
  body claim anything that is not actually in the diff?
  Report each finding as "- [severity] title (file:lines)"; compliance
  gaps are findings too.
  CRITERIA

The findings are the engine's final message (also in the -o file). The
verdict is YOURS, derived from the findings: approve when no critical/high
finding remains unresolved; needs-attention otherwise. Never add
--dangerously-bypass-approvals-and-sandbox / --yolo to the engine call.
```

> Amended during execution (pre-dispatch): the original Step-1 sketch used
> `codex exec review --base origin/{{BASE_REF}} ... <stdin PROMPT>`, which
> Task 2's Spike B proved impossible — targeting flags reject a custom PROMPT
> at the CLI parser (rc=2, no JSON). Rewritten to the cookbook pattern (plain
> `codex exec` + in-prompt `git diff origin/<base>...HEAD` self-diff), which
> the spike then live-verified over a two-commit range with combined
> correctness + compliance criteria. Added the CODEX_HOME symlink workaround
> for the codex-in-codex (Codex-worker) case, per Spike B (c). Both grounded
> in the spec's corrected Design section and Surprises (Task 2 spike (b)/(c)).

- [ ] **Step 2: `fallback-claude.md`**:

```markdown
ENGINE FALLBACK — if `codex` is unavailable (command missing, auth failure,
or repeated API errors after 2 retries with a short backoff): fall back to
a fresh Claude reviewer subagent at high effort over the same diff with the
same criteria, returning findings as "- [severity] title (file:lines)".
Record in the review-trail comment which engine reviewed.
```

- [ ] **Step 3: `fallback-codex.md`**:

```markdown
ENGINE FALLBACK — you have no second engine. If the review engine call
(`codex exec`) fails (auth failure, or repeated API errors after 2 retries
with a short backoff): when the ticket is not "none", park —
{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} needs-human "review engine unavailable: <error>"
— otherwise leave the escalation as a PR comment. Then end your turn.
Record in the review-trail comment that the engine was unavailable.
```

- [ ] **Step 4: template surgery on `review-worker-protocol.md`**:

1. Toolkit list: delete the line `- codex companion: {{CODEX_COMPANION}}`.
2. Replace the entire `REVIEW ENGINE — run the codex reviewer...` paragraph (the block from `REVIEW ENGINE` through `...you cannot distinguish wedged from busy.`) with:

```
{{ENGINE_BLOCK}}

{{FALLBACK_BLOCK}}
```

3. `RE-REVIEW (max 3 codex rounds total)` → `RE-REVIEW (max 3 engine rounds total)`.
4. In YOUR AUTHORITY's NEVER list, delete `, /codex:cancel`.
5. In the review-trail sentence keep `engine and rounds run` (now meaningful across species).

- [ ] **Step 5: sanity grep**

Run: `grep -n "CODEX_COMPANION\|codex:cancel\|codex-companion" skills/reviewing-prs/references/review-worker-protocol.md`
Expected: no matches.

- [ ] **Step 6: Commit**

```bash
git add skills/reviewing-prs/references/
git commit -m "feat(reviewing-prs): 리뷰 프로토콜 엔진 블록화 — 네이티브 codex exec review + 스펙 컴플라이언스"
```

### Task 7: `review-dispatch.sh` — engine switch, block composition, liveness

**Files:**
- Modify: `skills/reviewing-prs/scripts/review-dispatch.sh`
- Test: `tests/reviewing-prs/test-review-dispatch.sh`

**Interfaces:**
- Consumes: `codex-spawn.sh` (Task 3 call shape), engine-block files (Task 6).
- Produces: engine resolution `label → WORKER_ENGINE → codex`; env `CODEX_REVIEW_MODEL` (default `gpt-5.6-sol`), `CODEX_REVIEW_EFFORT` (default `xhigh`); `_reviewer_meta` emits `uuid|status|current|engine|pid`.

- [ ] **Step 1: Write the failing tests.** In `tests/reviewing-prs/test-review-dispatch.sh`: (a) near the env setup, add a stub `codex-spawn.sh` beside the existing `daemon-spawn.sh` stub — identical logic but logging `codex-spawn:$*` to `$SPAWN_LOG` and writing meta with `"engine": "codex", "pid": "99999"`; (b) export `WORKER_ENGINE=claude` at the top **so every existing case keeps exercising the claude path unchanged**; (c) append new cases:

```bash
echo "== engine switch =="
: > "$SPAWN_LOG"
gh_pr 41 OPEN 0 ""                                  # helper: canned PR, no labels
WORKER_ENGINE=codex run_dispatch 41
assert_contains "$(cat "$SPAWN_LOG")" "codex-spawn:" "default-codex env spawns codex"
prompt="$(cat "$PROMPT_DIR/review-pr-41.prompt")"
assert_contains "$prompt" "git diff origin/main...HEAD" "prompt carries the engine block (cookbook self-diff, BASE_REF rendered)"
assert_contains "$prompt" "SPEC COMPLIANCE" "prompt carries compliance criteria"
assert_not_contains "$prompt" "{{ENGINE_BLOCK}}" "engine block placeholder rendered"
assert_not_contains "$prompt" "CODEX_COMPANION" "companion is gone from the prompt"

: > "$SPAWN_LOG"
gh_pr 42 OPEN 0 "engine:claude"
WORKER_ENGINE=codex run_dispatch 42
assert_contains "$(cat "$SPAWN_LOG")" "spawn:" "engine:claude label overrides env"
prompt42="$(cat "$PROMPT_DIR/review-pr-42.prompt")"
assert_contains "$prompt42" "Claude reviewer subagent" "claude species gets the claude fallback block"

echo "== codex reviewer liveness in dedupe =="
sleep 300 & LIVEPID=$!
python3 - "$DAEMON_HOME" "$LIVEPID" <<'PY'
import json, sys
json.dump({"uuid": "cdec9999-0000-4000-8000-000000000000", "current": "cdec9999-0000-4000-8000-000000000000",
           "name": "review-pr-43", "engine": "codex", "pid": str(sys.argv[2]),
           "status": "working", "updated": "2026-07-10T00:00:00Z"},
          open(sys.argv[1] + "/cdec9999-0000-4000-8000-000000000000.json", "w"))
PY
gh_pr 43 OPEN 0 ""
out="$(WORKER_ENGINE=codex run_dispatch 43)"
assert_contains "$out" "skip active reviewer" "live codex pid dedupes"
kill "$LIVEPID" 2>/dev/null; wait "$LIVEPID" 2>/dev/null || true
: > "$SPAWN_LOG"
out="$(WORKER_ENGINE=codex run_dispatch 43)"
assert_contains "$(cat "$SPAWN_LOG")" "codex-spawn:" "dead codex pid retires + respawns"
```

(Adapt helper names — `gh_pr`/`run_dispatch` — to the file's actual canned-PR and invocation helpers; add a labels parameter to the PR-JSON helper if it lacks one.)

> Amended during execution (pre-dispatch): the "prompt carries the engine
> block" assertion originally checked for `codex exec review --base origin/main`
> — the disproven invocation Task 6 replaced with the cookbook pattern. Changed
> to `git diff origin/main...HEAD` (the cookbook block's self-diff line, which
> also proves `{{BASE_REF}}` rendered). Keep in sync with Task 6's engine block.

- [ ] **Step 2: Run to verify failure** — Expected: new cases FAIL (no codex-spawn call, `{{ENGINE_BLOCK}}` unrendered).

- [ ] **Step 3: Modify `review-dispatch.sh`**:

1. Header env docs: add `WORKER_ENGINE` (default codex; label `engine:*` overrides), `CODEX_REVIEW_MODEL` (default gpt-5.6-sol), `CODEX_REVIEW_EFFORT` (default xhigh); note `REVIEW_MODEL` = claude model.
2. After the `AUTO_MERGE_DISPLAY` block add:

```bash
CODEX_REVIEW_MODEL="${CODEX_REVIEW_MODEL:-gpt-5.6-sol}"
CODEX_REVIEW_EFFORT="${CODEX_REVIEW_EFFORT:-xhigh}"
ENGINE_BLOCK_FILE="$SKILL_DIR/references/engine-blocks/engine-codex-review.md"
FALLBACK_CLAUDE_FILE="$SKILL_DIR/references/engine-blocks/fallback-claude.md"
FALLBACK_CODEX_FILE="$SKILL_DIR/references/engine-blocks/fallback-codex.md"
```

3. Delete the `companion="$(ls ...codex-companion.mjs...)"` line and the `P_CODEX_COMPANION` render var.
4. In the exports python, derive the engine label:

```python
names = [l.get("name", "") for l in (d.get("labels") or [])]
eng = "claude" if "engine:claude" in names else ("codex" if "engine:codex" in names else "")
q("ENGINE_LABEL", eng)
```

5. In `dispatch_one`, after `eval "$exports"`:

```bash
engine="${ENGINE_LABEL:-${WORKER_ENGINE:-codex}}"
fallback_file="$FALLBACK_CODEX_FILE"
[ "$engine" = "claude" ] && fallback_file="$FALLBACK_CLAUDE_FILE"
```

6. In the render python: pass `ENGINE_BLOCK_FILE`/`FALLBACK_FILE`/`P_ENGINE_NAME`/`P_CODEX_REVIEW_MODEL`/`P_CODEX_REVIEW_EFFORT` through env, and compose blocks BEFORE the single placeholder pass:

```python
t = open(sys.argv[1]).read()
t = t.replace("{{ENGINE_BLOCK}}", open(os.environ["ENGINE_BLOCK_FILE"]).read())
t = t.replace("{{FALLBACK_BLOCK}}", open(os.environ["FALLBACK_FILE"]).read())
```

7. Replace the spawn line:

```bash
  if [ "$engine" = "codex" ]; then
    "$DAEMON_SCRIPTS/codex-spawn.sh" --no-wait "review-pr-$pr" "$prompt" "$wt" "" \
      "$CODEX_REVIEW_MODEL" "$CODEX_REVIEW_EFFORT"
  else
    "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "review-pr-$pr" "$prompt" "$wt" "" "${REVIEW_MODEL:-}"
  fi
```

8. `_reviewer_meta`: print `"%s|%s|%s|%s|%s" % (m.get("uuid",""), m.get("status",""), m.get("current",""), m.get("engine") or "claude", m.get("pid",""))`.
9. `_is_live` gains engine/pid params; `_decide` parses the two new fields:

```bash
# rc 0 when the reviewer's CURRENT turn is live: claude → session uuid visible
# in `claude agents`; codex → recorded pid alive.
_is_live() {  # <current> <engine> <pid>
  if [ "$2" = "codex" ]; then
    [ -n "$3" ] && kill -0 "$3" 2>/dev/null
    return
  fi
  claude agents --json --all 2>/dev/null | CUR="$1" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = []
sys.exit(0 if any(a.get("sessionId") == os.environ["CUR"] for a in d) else 1)'
}
```

and in `_decide`, replace the meta parsing + live check:

```bash
  uuid="${meta%%|*}"; rest="${meta#*|}"; status="${rest%%|*}"; rest="${rest#*|}"
  current="${rest%%|*}"; rest="${rest#*|}"; engine="${rest%%|*}"; pid="${rest#*|}"
  case "$status" in
    working|blocked)
      if _is_live "$current" "$engine" "$pid"; then echo "skip active reviewer"; else echo "respawn $uuid"; fi ;;
```

10. `_wt_occupied`: codex workers never appear in `claude agents`, so after the existing check fails, scan the registry — but count ONLY codex metas with a live pid (a stale claude-engine `working` meta must NOT start blocking removal; the claude path's fail-open behavior stays exactly as it was):

```bash
  # (append inside _wt_occupied, after the claude-agents python exits nonzero)
  DAEMON_HOME="$DAEMON_HOME" WT="$1" python3 - <<'PY'
import glob, json, os, sys
home = os.environ["DAEMON_HOME"]; wt = os.environ["WT"]
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if m.get("engine") != "codex" or m.get("cwd") != wt:
        continue
    if m.get("status") not in ("working", "blocked"):
        continue
    pid = str(m.get("pid") or "")
    if pid.isdigit():
        try:
            os.kill(int(pid), 0)
            sys.exit(0)   # live codex worker sits in this worktree
        except OSError:
            pass
sys.exit(1)
PY
```

(the shell wrapper: `claude`-agents check `&& return 0`, then this scan's exit code is the function's result).

- [ ] **Step 4: Run tests** — `tests/reviewing-prs/test-review-dispatch.sh` → ALL PASSED (old cases under `WORKER_ENGINE=claude`, new engine cases green); `scripts/lint-shell.sh` clean.

- [ ] **Step 5: Commit**

```bash
git add skills/reviewing-prs/scripts/review-dispatch.sh tests/reviewing-prs/test-review-dispatch.sh
git commit -m "feat(reviewing-prs): 디스패치 엔진 스위치 — 라벨→env→codex 기본, pid 라이브니스, 컴패니언 제거"
```

### Task 8: implement protocol — execution blocks + ritual + docs

**Files:**
- Create: `skills/implementing-tickets/references/engine-blocks/execution-claude.md`
- Create: `skills/implementing-tickets/references/engine-blocks/execution-codex.md`
- Modify: `skills/implementing-tickets/references/implement-worker-protocol.md`
- Modify: `skills/issue-tracker/SKILL.md` (dispatch ritual steps 2–3)
- Modify: `skills/implementing-tickets/SKILL.md` (pieces table)

- [ ] **Step 1: `execution-claude.md`** — move the current protocol EXECUTION mode list verbatim:

```markdown
EXECUTION (gate passed) — name the mode in the gate comment:
- DIRECT: the pre-spec is the plan — TDD
  (doperpowers:test-driven-development), commit frequently, open the PR.
- EXECPLAN: 2+ milestones, or enough files/design sequencing that a fresh
  session would need the document to survive context death →
  doperpowers:execplan (the gate already served as its grill; author the
  ExecPlan from ticket + gate findings, execute to the letter).
```

- [ ] **Step 2: `execution-codex.md`** — same discipline, inlined (no skill references):

```markdown
EXECUTION (gate passed) — name the mode in the gate comment:
- DIRECT: the pre-spec is the plan — strict TDD: for each behavior write
  the FAILING test first, run it and watch it fail, implement the minimal
  code, watch it pass, commit. Small, frequent commits. Open the PR with gh.
- PLAN: 2+ milestones, or enough files/design sequencing that a fresh
  session would need a document to survive context death → author a plan
  file first (docs/plans/issue-{{ISSUE_NUMBER}}.md on your branch:
  milestones with observable acceptance criteria, exact files per
  milestone), commit it, then execute it to the letter milestone by
  milestone — same TDD discipline within each.
```

- [ ] **Step 3: template surgery on `implement-worker-protocol.md`**: replace the EXECUTION mode list (from `EXECUTION (gate passed)` through the `doperpowers:execplan ... execute to the letter).` line) with `{{EXECUTION_BLOCK}}`, keeping the lines that follow (`The gate lowers the odds of a park...` onward). Change the gate-comment line to name the engine:

```
  gh issue comment {{ISSUE_NUMBER}} --body "[gate] pass — {{ENGINE_NAME}}/<mode>: <one line>"
```

- [ ] **Step 4: `skills/issue-tracker/SKILL.md` ritual steps 2–3** — rewrite to:

```markdown
2. Resolve the ENGINE — ticket label `engine:claude`/`engine:codex` →
   `$WORKER_ENGINE` → default `codex`. Render the Implement Worker Protocol
   (`doperpowers:implementing-tickets` →
   `references/implement-worker-protocol.md`): substitute every
   `{{PLACEHOLDER}}` (`ISSUE_NUMBER`, `ISSUE_URL`, `ISSUE_TITLE`, `REPO`,
   `BOARD_SCRIPTS` = this skill's scripts dir, `ISSUE_BODY` = the full
   issue body from `gh issue view <n> --json body`, `ENGINE_NAME` = the
   engine, `EXECUTION_BLOCK` = the engine's
   `references/engine-blocks/execution-<engine>.md`).
3. codex: `codex-spawn.sh "<n>-<slug>" "<prompt>" <repo> <worktree-name>`
   (model/effort default gpt-5.6-sol/high — override with
   `$CODEX_MODEL` / `$CODEX_EFFORT`, the vars codex-spawn.sh actually reads,
   or pass them as args 5–6). claude:
   `daemon-spawn.sh "<n>-<slug>" "<prompt>" <repo> <worktree-name>`. Both
   from `orchestrating-daemons` — always a worktree; workers write code.
```

> Amended during execution: the brief originally named the implement override
> vars `$CODEX_IMPL_MODEL`/`$CODEX_IMPL_EFFORT`, which exist nowhere — Task 3's
> `codex-spawn.sh` reads generic `$CODEX_MODEL`/`$CODEX_EFFORT` (defaults
> gpt-5.6-sol/high, == the implement defaults). No dedicated `*_IMPL_*` knob is
> needed: unlike review (which needs `CODEX_REVIEW_*` to reach `xhigh`), the
> implement defaults already equal the spawner's, so the ritual just uses the
> generic vars. Spec's Engine-selection section reconciled to match.

- [ ] **Step 5: `skills/implementing-tickets/SKILL.md` pieces table** — add a row after the protocol row:

```markdown
| `references/engine-blocks/` | per-engine EXECUTION text (claude: TDD/execplan skills; codex: the same discipline inlined) — composed into the protocol at render time |
```

- [ ] **Step 6: render smoke** — verify a hand render leaves no unrendered placeholders:

```bash
python3 - <<'PY'
import re
t = open("skills/implementing-tickets/references/implement-worker-protocol.md").read()
t = t.replace("{{EXECUTION_BLOCK}}", open("skills/implementing-tickets/references/engine-blocks/execution-codex.md").read())
subs = dict(ISSUE_NUMBER="1", ISSUE_URL="u", ISSUE_TITLE="t", REPO="r", BOARD_SCRIPTS="/b", ISSUE_BODY="b", ENGINE_NAME="codex")
t = re.sub(r"\{\{(\w+)\}\}", lambda m: subs.get(m.group(1), "MISSING-" + m.group(1)), t)
assert "MISSING-" not in t, [l for l in t.splitlines() if "MISSING-" in l]
print("render clean")
PY
```

Expected: `render clean`.

- [ ] **Step 7: Commit**

```bash
git add skills/implementing-tickets/ skills/issue-tracker/SKILL.md
git commit -m "feat(implementing-tickets): 실행 블록 엔진 분리 + 디스패치 리추얼 엔진 스위치"
```

### Task 9: SKILL.md docs — orchestrating-daemons + reviewing-prs

**Files:**
- Modify: `skills/orchestrating-daemons/SKILL.md`
- Modify: `skills/reviewing-prs/SKILL.md`

- [ ] **Step 1: orchestrating-daemons** — (a) Overview: after the first sentence add: "The substrate drives two engines under one registry: `claude --bg` daemons and detached `codex exec` workers (`engine: codex` in the meta) — the board pipeline picks per dispatch (label → `WORKER_ENGINE` → codex)." (b) Toolkit table: add rows

```markdown
| `codex-spawn.sh [--no-wait] <name> <task> [cwd] [worktree] [model] [effort]` | Spawn a detached `codex exec --json` worker into the same registry (`engine: codex`, pid liveness). Defaults gpt-5.6-sol/high. Launch in a bg shell. |
| `codex-resume.sh <id> <message>` | Continue a codex daemon (`codex exec resume` — same session id, no forking). Launch in a bg shell. |
```

(c) "Every turn is a native background agent" section: append one line — "(Claude engine only: codex sessions keep one id for life; `codex-resume.sh` never forks or purges.)" (d) Permissions section: append a codex paragraph:

```markdown
Codex workers get the same posture, spelled differently: `--sandbox
workspace-write` plus the approvals auto-reviewer (`-c
approval_policy=on-request -c approvals_reviewer=…`) — safe ops continue,
genuinely unsafe escalations are declined in-flight (fail-closed). A codex
daemon is therefore NEVER `blocked`: a declined escalation is a failed
command the worker sees and works around, or parks over. **Do not add
`--yolo` / `--dangerously-bypass-approvals-and-sandbox`** — the exact
mirror of the `--dangerously-skip-permissions` ban. `-c
features.hooks=false` is always on: a checked-out PR could ship
`.codex/hooks.json`, which would otherwise execute at session start.
```

- [ ] **Step 2: reviewing-prs** — (a) Overview: "reviews it with codex" → "reviews it with a native Codex reviewer (`codex exec` self-diffing the PR)". (b) Pieces table: add `references/engine-blocks/` row (engine + per-species fallback blocks) and note `review-dispatch.sh` resolves the worker engine (label → `WORKER_ENGINE` → codex). (c) Replace the whole `## Codex-lock handling` section with:

```markdown
## Review engine

Both worker species run the same engine: a native `codex exec` reviewer that
self-diffs the PR against its base (`git diff origin/<base>...HEAD`), with
correctness discipline AND spec-compliance criteria (the linked ticket's
acceptance) inlined in the review prompt — no companion, no machine-wide lock.
(The `codex exec review` subcommand can't take custom criteria — its target
flags reject a stdin prompt — so the cookbook plain-`codex exec` form carries
both.) The Claude species falls back to a fresh Claude high-effort reviewer
subagent when codex is unavailable; the Codex species has no second engine and
parks `needs-human` instead. The review-trail comment names the engine that
reviewed.
```

> Amended during execution (pre-dispatch): (a) and (c) originally described the
> reviewer as `codex exec review` with spec-compliance criteria "appended via
> stdin" — the exact composition Spike B proved impossible (targeting flags
> reject a custom PROMPT, rc=2). Rewritten to the cookbook `codex exec` self-diff
> form the Task 6 engine block actually ships, so the SKILL.md prose matches the
> implementation rather than the disproven sketch. Same stale-vs-spike class as
> Tasks 6–7.

(d) Adoption checklist: add item "10. Codex workers (the default engine): `codex` CLI installed and authed (`codex login`) on the runner machine; set `WORKER_ENGINE=claude` (env) or label `engine:claude` to opt a repo/PR out."

- [ ] **Step 3: sanity grep**

Run: `grep -rn "codex-companion\|codex:cancel\|machine-wide lock" skills/reviewing-prs/ skills/orchestrating-daemons/`
Expected: no matches (the lock is retired everywhere).

- [ ] **Step 4: Commit**

```bash
git add skills/orchestrating-daemons/SKILL.md skills/reviewing-prs/SKILL.md
git commit -m "docs(daemons,reviewing-prs): 듀얼 엔진 기질 문서화 — 승인 오토리뷰어, 리뷰 엔진 섹션, 락 폐기"
```

### Task 10: Final verification — spec acceptance as written

**Files:**
- Modify: `docs/doperpowers/specs/2026-07-10-codex-workers-design.md` (Revision Notes if anything shifted)

- [ ] **Step 1: full suites**

```bash
tests/orchestrating-daemons/test-daemon-scripts.sh
tests/orchestrating-daemons/test-codex-scripts.sh
tests/reviewing-prs/test-review-dispatch.sh
tests/claude-code/run-skill-tests.sh
tests/codex-plugin-sync/test-sync-to-codex-plugin.sh
scripts/lint-shell.sh
```

Expected: every suite ALL PASSED / lint clean.

- [ ] **Step 2: spec acceptance, bullet by bullet** — re-run the stub-level acceptance directly:
  - codex-spawn registry + bind + list + reply: covered by `test-codex-scripts.sh` (point at the PASS lines).
  - engine switch + label override + default: covered by the new `test-review-dispatch.sh` cases; for the implement side run Task 8 Step 6's render smoke for BOTH blocks.
  - dedupe live/dead codex pid: covered by the Task 7 liveness cases.
  - identical engine block both species / differing fallback: `diff <(...)` the two rendered prompts from the Task 7 test run, or assert via the existing test greps.
- [ ] **Step 3: live shakedown gate** — the spec's final acceptance bullet (a real Codex implement worker driving a real ticket to PR, and a real Codex review worker reviewing a real PR) runs on the next real dispatch, NOT in this plan. Note in the spec's `## Outcomes & Retrospective` trigger line that the live shakedown completes it.
- [ ] **Step 4: Commit any spec Revision Notes; push.**
