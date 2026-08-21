#!/usr/bin/env bash
#
# Hermetic tests for review-engine.sh — the single native-review invocation.
#
# The suite pins the seam the engine OWNS: the `node <companion>/with-effort.mjs`
# command line it composes (verb routing, defaults, the lens contract), the env
# recipe it exports, its rc mapping, and its fail-closed sandbox check. What
# happens on the far side of that seam — the app-server thread protocol — is
# the codex-companion runtime's contract, pinned by tests/codex-companion/
# against a protocol-speaking fake codex. An earlier version of this suite
# stubbed `codex` itself and rotted the moment the wrapper changed transport
# (dp#26); stubbing `node` keeps the pin on the surface this script controls.
#
# Both `codex` and `node` are stubs on a scrubbed PATH: codex exists only to
# satisfy the engine's preflight, node logs argv + env and plays the wrapper.
# No network, no real codex, no real node.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENGINE="$REPO_ROOT/skills/qa-loops/scripts/review-engine.sh"

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
assert_not_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
}

export HOME="$TEST_ROOT/home"
export TMPDIR="$TEST_ROOT/tmp"
export ENGINE_LOG="$TEST_ROOT/engine.log"
mkdir -p "$HOME/.codex" "$HOME/.local/bin" "$TMPDIR"
echo '{"token":"fake"}' > "$HOME/.codex/auth.json"
: > "$HOME/.local/bin/codex-code-mode-host"; chmod +x "$HOME/.local/bin/codex-code-mode-host"

# The host's TLS bundle the engine will discover when SSL_CERT_FILE is unset —
# computed by the same first-existing rule the engine uses, so the assert holds
# on macOS (/etc/ssl/cert.pem) and Debian-family (/etc/ssl/certs/…) alike.
HOST_CERT=""
for c in /etc/ssl/cert.pem /etc/ssl/certs/ca-certificates.crt; do
    [ -f "$c" ] && { HOST_CERT="$c"; break; }
done

STUB_BIN="$TEST_ROOT/bin"; mkdir -p "$STUB_BIN"
# codex: preflight satisfaction only. The engine must never reach it — an
# invocation would mean the engine bypassed the companion wrapper.
cat > "$STUB_BIN/codex" <<'STUB'
#!/usr/bin/env bash
echo "CODEX_INVOKED_DIRECTLY" >> "${ENGINE_LOG:-/dev/null}"
exit 97
STUB
chmod +x "$STUB_BIN/codex"
# node: the with-effort.mjs seam. Logs the composed argv and the env recipe,
# renders findings on stdout and progress on stderr (the engine splits those
# into --out and --out.events.log), exits STUB_NODE_RC.
cat > "$STUB_BIN/node" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
{
  printf 'ARGS:'; printf ' %q' "$@"; printf '\n'
  last=""; for a in "$@"; do last="$a"; done
  printf 'LAST_ARG=%s\n' "$last"
  echo "ENV_CODEX_HOME=${CODEX_HOME:-}"
  echo "ENV_PLUGIN_DATA=${CLAUDE_PLUGIN_DATA:-}"
  echo "ENV_SSL_CERT_FILE=${SSL_CERT_FILE:-}"
  echo "ENV_HOST_PATH=${CODEX_CODE_MODE_HOST_PATH:-}"
  echo "AUTH_LINK=$([ -L "${CODEX_HOME:-/nonexistent}/auth.json" ] && echo yes || echo no)"
  echo "AUTH_TARGET=$(readlink "${CODEX_HOME:-/nonexistent}/auth.json" 2>/dev/null || true)"
} >> "$ENGINE_LOG"
printf '%s\n' "${STUB_FINDINGS:-- [P2] stub finding (ratio.py:2)}"
[ -n "${STUB_EVENTS_TEXT:-}" ] && printf '%s\n' "$STUB_EVENTS_TEXT" >&2
exit "${STUB_NODE_RC:-0}"
STUB
chmod +x "$STUB_BIN/node"
export PATH="$STUB_BIN:/usr/bin:/bin"

WT="$TEST_ROOT/wt"; mkdir -p "$WT"; cd "$WT"

reset() { : > "$ENGINE_LOG"; rm -f "$TEST_ROOT/out.txt" "$TEST_ROOT/out.txt.events.log" "$TEST_ROOT/err.txt"; }
CLEAN_ENV=(env -u CODEX_HOME -u CODEX_SANDBOX -u CODEX_REVIEW_MODEL -u CODEX_REVIEW_EFFORT
           -u CODEX_REVIEW_LENS -u CODEX_REVIEW_LENS_FILE -u SSL_CERT_FILE -u CODEX_CODE_MODE_HOST_PATH)

echo "happy path (plain native review):"
reset
"${CLEAN_ENV[@]}" "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2> "$TEST_ROOT/err.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "with-effort.mjs" "the engine drives the companion wrapper, not codex"
assert_contains "$LOG" "--effort xhigh -- review --base origin/main --wait --model gpt-5.6-sol" "default effort/model on the native review verb"
assert_not_contains "$LOG" "adversarial-review" "no lens means the plain review verb"
assert_not_contains "$LOG" "CODEX_INVOKED_DIRECTLY" "codex is never invoked past the preflight"
assert_contains "$LOG" "ENV_CODEX_HOME=$TMPDIR/review-engine-home." "temporary CODEX_HOME stays outside the reviewed tree"
assert_contains "$LOG" "ENV_PLUGIN_DATA=$TMPDIR/review-engine-home." "companion job ledger isolated under the engine home"
assert_contains "$LOG" "AUTH_LINK=yes" "auth.json symlinked into the engine home"
assert_contains "$LOG" "ENV_SSL_CERT_FILE=$HOST_CERT" "TLS file bundle exported when unset"
assert_contains "$LOG" "ENV_HOST_PATH=$HOME/.local/bin/codex-code-mode-host" "code-mode host path exported when unset"
assert_equals "$(find "$TMPDIR" -maxdepth 1 -name 'review-engine-home.*' | wc -l | tr -d ' ')" "0" "engine home removed after the run"
assert_equals "$(cat "$TEST_ROOT/out.txt")" "- [P2] stub finding (ratio.py:2)" "findings land in --out"
assert_not_contains "$(cat "$TEST_ROOT/err.txt")" "warning" "non-nested run warns about nothing"

echo "custom model/effort:"
reset
CODEX_REVIEW_MODEL=gpt-test CODEX_REVIEW_EFFORT=medium \
env -u CODEX_HOME -u CODEX_SANDBOX -u CODEX_REVIEW_LENS -u CODEX_REVIEW_LENS_FILE \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "--effort medium -- review --base origin/main --wait --model gpt-test" "env overrides ride the argv"

echo "custom CODEX_HOME auth:"
reset
CUSTOM_CODEX_HOME="$TEST_ROOT/custom-codex"
mkdir -p "$CUSTOM_CODEX_HOME"
echo '{"token":"custom"}' > "$CUSTOM_CODEX_HOME/auth.json"
CODEX_HOME="$CUSTOM_CODEX_HOME" \
env -u CODEX_SANDBOX -u CODEX_REVIEW_LENS -u CODEX_REVIEW_LENS_FILE \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "AUTH_TARGET=$CUSTOM_CODEX_HOME/auth.json" "auth is inherited from a custom CODEX_HOME"

echo "lens routing:"
reset
LENS_TEXT='hunt along the seam: "double spend" & rollback ordering'
printf '%s' "$LENS_TEXT" > "$TEST_ROOT/lens.md"
CODEX_REVIEW_LENS_FILE="$TEST_ROOT/lens.md" CODEX_REVIEW_LENS="inline loser" \
env -u CODEX_HOME -u CODEX_SANDBOX \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "adversarial-review" "a lens routes through the challenge-review verb"
assert_contains "$LOG" "LAST_ARG=$LENS_TEXT" "the lens travels verbatim as the single trailing argument"
assert_not_contains "$LOG" "inline loser" "CODEX_REVIEW_LENS_FILE wins over the inline lens"
reset
CODEX_REVIEW_LENS="inline mandate" \
env -u CODEX_HOME -u CODEX_SANDBOX -u CODEX_REVIEW_LENS_FILE \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "LAST_ARG=inline mandate" "inline lens used when no lens file is set"
reset
rc=0
CODEX_REVIEW_LENS_FILE="$TEST_ROOT/no-such-lens.md" \
env -u CODEX_HOME -u CODEX_SANDBOX \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "2" "a missing lens file is a usage error"
assert_equals "$(cat "$ENGINE_LOG")" "" "…and the wrapper is never invoked for it"

echo "only-if-unset env:"
reset
SSL_CERT_FILE=/custom/pem CODEX_CODE_MODE_HOST_PATH=/custom/host \
env -u CODEX_HOME -u CODEX_SANDBOX -u CODEX_REVIEW_LENS -u CODEX_REVIEW_LENS_FILE \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "ENV_SSL_CERT_FILE=/custom/pem" "pre-set SSL_CERT_FILE preserved"
assert_contains "$LOG" "ENV_HOST_PATH=/custom/host" "pre-set host path preserved"

echo "rc passthrough:"
reset
rc=0; "${CLEAN_ENV[@]}" STUB_NODE_RC=5 "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "5" "the wrapper's rc passes through"
assert_equals "$(find "$TMPDIR" -maxdepth 1 -name 'review-engine-home.*' | wc -l | tr -d ' ')" "0" "engine home removed even on failure"

echo "fail-closed on a dead fs sandbox:"
reset
rc=0
"${CLEAN_ENV[@]}" STUB_EVENTS_TEXT='bwrap: loopback: Failed RTM_NEWADDR' \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2> "$TEST_ROOT/err.txt" || rc=$?
assert_equals "$rc" "3" "a clean rc over sandbox-failure markers is ENGINE-UNAVAILABLE"
assert_contains "$(cat "$TEST_ROOT/err.txt")" "ENGINE-UNAVAILABLE" "…and says so on stderr"
assert_contains "$(cat "$TEST_ROOT/out.txt.events.log")" "RTM_NEWADDR" "the events log keeps the evidence"

echo "nested under an outer codex sandbox:"
reset
rc=0
CODEX_SANDBOX=seatbelt STUB_EVENTS_TEXT='bwrap: loopback: Failed RTM_NEWADDR' \
env -u CODEX_HOME -u CODEX_REVIEW_LENS -u CODEX_REVIEW_LENS_FILE \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2> "$TEST_ROOT/err.txt" || rc=$?
assert_equals "$rc" "0" "nested probe confinement is the documented degraded path, not an error"
assert_contains "$(cat "$TEST_ROOT/err.txt")" "running nested under a codex sandbox" "…but the degraded run is attributable"

echo "usage errors:"
rc=0; "$ENGINE" --base origin/main 2>/dev/null || rc=$?
assert_equals "$rc" "2" "missing --out is a usage error"
rc=0; "$ENGINE" --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "2" "missing --base is a usage error"
rc=0; "$ENGINE" --base origin/main --criteria "$TEST_ROOT/x.md" --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "2" "retired --criteria flag is a usage error"

echo "missing dependencies:"
NODE_ONLY="$TEST_ROOT/node-only"; mkdir -p "$NODE_ONLY"; cp "$STUB_BIN/node" "$NODE_ONLY/node"
CODEX_ONLY="$TEST_ROOT/codex-only"; mkdir -p "$CODEX_ONLY"; cp "$STUB_BIN/codex" "$CODEX_ONLY/codex"
rc=0; PATH="$NODE_ONLY:/usr/bin:/bin" "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "127" "missing codex CLI exits 127"
rc=0; PATH="$CODEX_ONLY:/usr/bin:/bin" "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "127" "missing node exits 127"

echo
if [ "$FAILURES" -gt 0 ]; then echo "$FAILURES failure(s)"; exit 1; fi
echo "all green"
