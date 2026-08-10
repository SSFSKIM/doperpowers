#!/usr/bin/env bash
#
# Hermetic tests for review-engine.sh — the single review-engine invocation.
# The engine is PURE correctness review driven through the codex-companion
# runtime; the companion layer is stubbed via REVIEW_COMPANION_DIR: stub
# with-effort.mjs / codex-companion.mjs log argv + the env recipe, emit
# canned output, and exit with STUB_RC. `codex` on PATH is a no-op (only
# its existence is probed). Real node runs the stubs and the engine's own
# render helper. No network, no real codex.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENGINE="$REPO_ROOT/skills/reviewing-prs/scripts/review-engine.sh"

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
    if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if grep -Fq -- "$2" <<<"$1"; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
}

export HOME="$TEST_ROOT/home"
export TMPDIR="$TEST_ROOT/tmp"
export ENGINE_LOG="$TEST_ROOT/engine.log"
mkdir -p "$HOME/.codex" "$HOME/.local/bin" "$TMPDIR"
echo '{"token":"fake"}' > "$HOME/.codex/auth.json"
: > "$HOME/.local/bin/codex-code-mode-host"; chmod +x "$HOME/.local/bin/codex-code-mode-host"

# codex exists on PATH (the engine probes it) but is never exercised —
# every invocation goes through the stubbed companion scripts below.
STUB_BIN="$TEST_ROOT/bin"; mkdir -p "$STUB_BIN"
printf '#!/usr/bin/env bash\nexit 0\n' > "$STUB_BIN/codex"; chmod +x "$STUB_BIN/codex"
NODE_DIR="$(dirname "$(command -v node)")"
GIT_DIR_BIN="$(dirname "$(command -v git)")"
export PATH="$STUB_BIN:$NODE_DIR:$GIT_DIR_BIN:/usr/bin:/bin"

# Stub companion: with-effort.mjs (single-review route) and
# codex-companion.mjs (panel route). Both log to ENGINE_LOG.
COMPANION="$TEST_ROOT/companion"
mkdir -p "$COMPANION/scripts" "$COMPANION/runtime/scripts" "$COMPANION/workflows"
: > "$COMPANION/workflows/code-review.mjs"
cat > "$COMPANION/scripts/with-effort.mjs" <<'STUB'
import { appendFileSync, lstatSync, readlinkSync } from "node:fs";
const e = process.env;
let link = "no", target = "";
try {
  if (lstatSync(`${e.CODEX_HOME}/auth.json`).isSymbolicLink()) {
    link = "yes"; target = readlinkSync(`${e.CODEX_HOME}/auth.json`);
  }
} catch {}
appendFileSync(e.ENGINE_LOG,
  `WITH_EFFORT ARGS: ${process.argv.slice(2).join(" ")}\n` +
  `LENS_ARG=${JSON.stringify(process.argv[process.argv.length - 1])}\n` +
  `ENV_CODEX_HOME=${e.CODEX_HOME ?? ""}\n` +
  `ENV_SSL_CERT_FILE=${e.SSL_CERT_FILE ?? ""}\n` +
  `ENV_HOST_PATH=${e.CODEX_CODE_MODE_HOST_PATH ?? ""}\n` +
  `ENV_PLUGIN_DATA=${e.CLAUDE_PLUGIN_DATA ?? ""}\n` +
  `AUTH_LINK=${link}\nAUTH_TARGET=${target}\n`);
if (e.STUB_EVENTS) process.stderr.write(e.STUB_EVENTS + "\n");
console.log("- [P2] stub finding (ratio.py:2)");
process.exit(Number(e.STUB_RC ?? 0));
STUB
cat > "$COMPANION/runtime/scripts/codex-companion.mjs" <<'STUB'
import { appendFileSync, readFileSync } from "node:fs";
const e = process.env;
appendFileSync(e.ENGINE_LOG,
  `COMPANION ARGS: ${JSON.stringify(process.argv.slice(2))}\n` +
  `ENV_CODEX_HOME=${e.CODEX_HOME ?? ""}\n` +
  `ENV_PLUGIN_DATA=${e.CLAUDE_PLUGIN_DATA ?? ""}\n`);
if (e.STUB_EVENTS) process.stderr.write(e.STUB_EVENTS + "\n");
if (e.STUB_PANEL_FILE) console.log(readFileSync(e.STUB_PANEL_FILE, "utf8"));
else console.log(JSON.stringify({ runId: "wf_stub", result: {
  verdict: "incorrect",
  findings: [{ id: "sweep#1", priority: "P1", title: "stub panel finding",
    file: "a.ts", lines: "10-12", comment: "why it is wrong",
    sources: ["sweep", "lens-1"] }],
  coverage: [], lenses: ["l1", "l2"], explanation: "confirmed: stub panel finding" } }));
process.exit(Number(e.STUB_RC ?? 0));
STUB
export REVIEW_COMPANION_DIR="$COMPANION"

WT="$TEST_ROOT/wt"; mkdir -p "$WT"; cd "$WT"

reset() { : > "$ENGINE_LOG"; rm -f "$TEST_ROOT"/out.txt*; }

echo "happy path (single review, non-nested):"
reset
env -u CODEX_HOME -u CODEX_SANDBOX -u CODEX_REVIEW_MODEL -u CODEX_REVIEW_EFFORT \
  -u CODEX_REVIEW_PANEL -u SSL_CERT_FILE -u CODEX_CODE_MODE_HOST_PATH \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "WITH_EFFORT ARGS: --effort xhigh -- review --base origin/main --wait --model gpt-5.6-sol" \
  "single route: with-effort wraps the native review verb, default model/effort"
assert_not_contains "$LOG" "COMPANION ARGS" "small/unmeasurable diff never routes to the panel"
assert_not_contains "$LOG" "developer_instructions" "pure engine sends no developer instructions"
assert_contains "$LOG" "ENV_CODEX_HOME=$TMPDIR/review-engine-home." "temporary CODEX_HOME stays outside the reviewed tree"
assert_contains "$LOG" "ENV_PLUGIN_DATA=$TMPDIR/review-engine-home." "temporary CLAUDE_PLUGIN_DATA isolates the companion ledger"
assert_contains "$LOG" "AUTH_LINK=yes" "auth.json symlinked into the engine home"
assert_equals "$(find "$TMPDIR" -maxdepth 1 -name 'review-engine-home.*' | wc -l | tr -d ' ')" "0" "engine home removed after the run"
assert_equals "$(cat "$TEST_ROOT/out.txt")" "- [P2] stub finding (ratio.py:2)" "findings land in --out"

echo "custom CODEX_HOME auth:"
reset
CUSTOM_CODEX_HOME="$TEST_ROOT/custom-codex"
mkdir -p "$CUSTOM_CODEX_HOME"
echo '{"token":"custom"}' > "$CUSTOM_CODEX_HOME/auth.json"
CODEX_HOME="$CUSTOM_CODEX_HOME" "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "AUTH_TARGET=$CUSTOM_CODEX_HOME/auth.json" "auth is inherited from a custom CODEX_HOME"

echo "only-if-unset env:"
reset
env -u CODEX_HOME SSL_CERT_FILE=/custom/pem CODEX_CODE_MODE_HOST_PATH=/custom/host \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "ENV_SSL_CERT_FILE=/custom/pem" "pre-set SSL_CERT_FILE preserved"
assert_contains "$LOG" "ENV_HOST_PATH=/custom/host" "pre-set host path preserved"

echo "lens routes to adversarial-review:"
reset
printf 'watch the actor identity assumptions in the changed routes' > "$TEST_ROOT/lens.txt"
CODEX_REVIEW_LENS_FILE="$TEST_ROOT/lens.txt" CODEX_REVIEW_PANEL=always \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "adversarial-review --base origin/main" "lens run uses the adversarial-review verb"
assert_contains "$LOG" 'LENS_ARG="watch the actor identity assumptions in the changed routes"' \
  "lens text travels as a single trailing argv element"
assert_not_contains "$LOG" "COMPANION ARGS" "a lensed run never routes to the panel, even under always"

echo "panel route (CODEX_REVIEW_PANEL=always):"
reset
CODEX_REVIEW_PANEL=always "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "COMPANION ARGS" "always forces the panel route"
assert_contains "$LOG" '"workflow","--script"' "panel runs through the workflow verb"
assert_contains "$LOG" "workflows/code-review.mjs" "panel script is the bundled code-review panel"
assert_contains "$LOG" '\"base\":\"origin/main\"' "panel args carry the base"
assert_contains "$LOG" '\"finderModel\":\"gpt-5.6-sol\"' "panel args carry the finder model"
assert_contains "$LOG" '\"finderEffort\":\"xhigh\"' "panel args carry the finder effort"
assert_not_contains "$LOG" "WITH_EFFORT" "panel route does not also run a single review"
OUT="$(cat "$TEST_ROOT/out.txt")"
assert_contains "$OUT" "Panel verdict: incorrect" "panel verdict rendered into --out"
assert_contains "$OUT" "- [P1] stub panel finding (a.ts:10-12)" "confirmed finding rendered with priority and location"
assert_contains "$OUT" "raised independently by: sweep, lens-1" "multi-source findings carry their lanes"
assert_equals "$([ -s "$TEST_ROOT/out.txt.panel.json" ] && echo yes)" "yes" "raw panel result kept beside --out"

echo "panel auto-threshold (real repo):"
REPO="$TEST_ROOT/repo"; mkdir -p "$REPO"; cd "$REPO"
git init -q -b main; git config user.email t@t; git config user.name t
git config commit.gpgsign false   # host git policy must not break the hermetic suite
echo base > seed.txt; git add .; git commit -qm seed
git checkout -qb feature
for i in $(seq 1 21); do echo "change $i" > "f$i.txt"; done
git add .; git commit -qm "21 files"
reset
"$ENGINE" --base main --out "$TEST_ROOT/out.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "COMPANION ARGS" "21 changed files crosses the file threshold → panel"
git checkout -q main; git checkout -qb small
echo tweak >> seed.txt; git add .; git commit -qm tweak
reset
"$ENGINE" --base main --out "$TEST_ROOT/out.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "WITH_EFFORT ARGS" "a small diff stays on the single review"
assert_not_contains "$LOG" "COMPANION ARGS" "a small diff never reaches the panel"
cd "$WT"

echo "panel interrupted verdict:"
reset
cat > "$TEST_ROOT/interrupted.json" <<'JSON'
{"runId":"wf_stub","result":{"verdict":"interrupted","findings":[],"coverage":[],"lenses":[],"explanation":"the lens-free sweep did not complete"}}
JSON
rc=0; CODEX_REVIEW_PANEL=always STUB_PANEL_FILE="$TEST_ROOT/interrupted.json" \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>"$TEST_ROOT/err.txt" || rc=$?
assert_equals "$rc" "4" "interrupted panel verdict is an engine failure (rc 4)"
assert_contains "$(cat "$TEST_ROOT/err.txt")" "panel interrupted: the lens-free sweep did not complete" \
  "interruption reason surfaces on stderr"

echo "rc passthrough:"
reset
rc=0; STUB_RC=3 "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" || rc=$?
assert_equals "$rc" "3" "single-route rc passes through"
rc=0; CODEX_REVIEW_PANEL=always STUB_RC=3 "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" || rc=$?
assert_equals "$rc" "3" "panel-route rc passes through"
assert_equals "$(find "$TMPDIR" -maxdepth 1 -name 'review-engine-home.*' | wc -l | tr -d ' ')" "0" "engine home removed even on failure"

echo "sandbox fail-closed:"
reset
rc=0; STUB_EVENTS='bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted' \
  env -u CODEX_SANDBOX "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "3" "sandbox-failure markers in the events log fail the run closed"

echo "usage errors:"
rc=0; "$ENGINE" --base origin/main 2>/dev/null || rc=$?
assert_equals "$rc" "2" "missing --out is a usage error"
rc=0; "$ENGINE" --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "2" "missing --base is a usage error"
rc=0; "$ENGINE" --base origin/main --criteria "$TEST_ROOT/x.md" --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "2" "retired --criteria flag is a usage error"
rc=0; CODEX_REVIEW_PANEL=sometimes "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "2" "unknown CODEX_REVIEW_PANEL value is a usage error"

echo "codex missing:"
# NODE_DIR may be a system bin dir that also carries a real codex — build a
# PATH with node alone so the probe genuinely misses.
NOCODEX="$TEST_ROOT/nocodex"; mkdir -p "$NOCODEX"
ln -s "$(command -v node)" "$NOCODEX/node"
rc=0; PATH="$NOCODEX:/usr/bin:/bin" "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "127" "missing codex CLI exits 127"

echo
if [ "$FAILURES" -gt 0 ]; then echo "$FAILURES failure(s)"; exit 1; fi
echo "all green"
