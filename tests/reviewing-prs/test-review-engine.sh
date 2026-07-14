#!/usr/bin/env bash
#
# Hermetic tests for review-engine.sh — the pure native-correctness invocation.
# `codex` is stubbed: it logs argv + the env recipe, honors -o, and exits
# with STUB_CODEX_RC. No network, no real codex.
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

STUB_BIN="$TEST_ROOT/bin"; mkdir -p "$STUB_BIN"
cat > "$STUB_BIN/codex" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
{
  printf 'ARGS:'; printf ' %q' "$@"; printf '\n'
  echo "ENV_CODEX_HOME=${CODEX_HOME:-}"
  echo "ENV_SSL_CERT_FILE=${SSL_CERT_FILE:-}"
  echo "ENV_HOST_PATH=${CODEX_CODE_MODE_HOST_PATH:-}"
  echo "AUTH_LINK=$([ -L "${CODEX_HOME:-/nonexistent}/auth.json" ] && echo yes || echo no)"
  echo "AUTH_TARGET=$(readlink "${CODEX_HOME:-/nonexistent}/auth.json" 2>/dev/null || true)"
} >> "$ENGINE_LOG"
prev=""; out=""
for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done
[ -n "$out" ] && echo "- [P2] stub finding (ratio.py:2)" > "$out"
exit "${STUB_CODEX_RC:-0}"
STUB
chmod +x "$STUB_BIN/codex"
export PATH="$STUB_BIN:/usr/bin:/bin"

WT="$TEST_ROOT/wt"; mkdir -p "$WT"; cd "$WT"

reset() { : > "$ENGINE_LOG"; rm -f "$TEST_ROOT/out.txt" "$TEST_ROOT/out.txt.events.jsonl"; }

echo "happy path (non-nested):"
reset
env -u CODEX_HOME -u CODEX_SANDBOX -u CODEX_REVIEW_MODEL -u CODEX_REVIEW_EFFORT \
  -u SSL_CERT_FILE -u CODEX_CODE_MODE_HOST_PATH \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "exec review --base origin/main" "invokes the native review subcommand with the base"
assert_contains "$LOG" "gpt-5.6-sol" "default model applied"
assert_contains "$LOG" "xhigh" "default effort applied"
assert_not_contains "$LOG" "developer_instructions" "native correctness review receives no custom developer instructions"
assert_not_contains "$LOG" "criteria" "native correctness review receives no ticket criteria"
assert_not_contains "$LOG" "danger-full-access" "non-nested run never widens the sandbox"
assert_contains "$LOG" "ENV_CODEX_HOME=$TMPDIR/review-engine-home." "temporary CODEX_HOME stays outside the reviewed tree"
assert_contains "$LOG" "AUTH_LINK=yes" "auth.json symlinked into the engine home"
assert_equals "$(find "$TMPDIR" -maxdepth 1 -name 'review-engine-home.*' | wc -l | tr -d ' ')" "0" "engine home removed after the run"
assert_equals "$(cat "$TEST_ROOT/out.txt")" "- [P2] stub finding (ratio.py:2)" "findings land in --out"

echo "custom CODEX_HOME auth:"
reset
CUSTOM_CODEX_HOME="$TEST_ROOT/custom-codex"
mkdir -p "$CUSTOM_CODEX_HOME"
echo '{"token":"custom"}' > "$CUSTOM_CODEX_HOME/auth.json"
CODEX_HOME="$CUSTOM_CODEX_HOME" \
env -u CODEX_SANDBOX -u SSL_CERT_FILE -u CODEX_CODE_MODE_HOST_PATH \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "AUTH_TARGET=$CUSTOM_CODEX_HOME/auth.json" "auth is inherited from a custom CODEX_HOME"

echo "nested:"
reset
CODEX_SANDBOX=seatbelt \
env -u CODEX_HOME -u SSL_CERT_FILE -u CODEX_CODE_MODE_HOST_PATH \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" 'danger-full-access' "nested run skips self-profiling (outer profile confines)"
assert_contains "$LOG" "ENV_HOST_PATH=$HOME/.local/bin/codex-code-mode-host" "code-mode host path exported"
assert_contains "$LOG" "ENV_SSL_CERT_FILE=/etc/ssl/cert.pem" "TLS file bundle exported"

echo "only-if-unset env:"
reset
env -u CODEX_HOME CODEX_SANDBOX=seatbelt SSL_CERT_FILE=/custom/pem CODEX_CODE_MODE_HOST_PATH=/custom/host \
  "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt"
LOG="$(cat "$ENGINE_LOG")"
assert_contains "$LOG" "ENV_SSL_CERT_FILE=/custom/pem" "pre-set SSL_CERT_FILE preserved"
assert_contains "$LOG" "ENV_HOST_PATH=/custom/host" "pre-set host path preserved"

echo "rc passthrough:"
reset
rc=0; env -u CODEX_HOME STUB_CODEX_RC=3 "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" || rc=$?
assert_equals "$rc" "3" "codex rc passes through"
assert_equals "$(find "$TMPDIR" -maxdepth 1 -name 'review-engine-home.*' | wc -l | tr -d ' ')" "0" "engine home removed even on failure"

echo "usage errors:"
rc=0; "$ENGINE" --base origin/main 2>/dev/null || rc=$?
assert_equals "$rc" "2" "missing --out is a usage error"
rc=0; "$ENGINE" --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "2" "missing --base is a usage error"

echo "codex missing:"
rc=0; PATH="/usr/bin:/bin" "$ENGINE" --base origin/main --out "$TEST_ROOT/out.txt" 2>/dev/null || rc=$?
assert_equals "$rc" "127" "missing codex CLI exits 127"

echo
if [ "$FAILURES" -gt 0 ]; then echo "$FAILURES failure(s)"; exit 1; fi
echo "all green"
