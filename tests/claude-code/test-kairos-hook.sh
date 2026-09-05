#!/usr/bin/env bash
# The kairos SessionStart hook: silent unless the session was launched with
# KAIROS=1, and then it prints the skill BODY (never the frontmatter) so the
# text the session starts with is the same text `/kairos` loads.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/kairos.sh"
FAILURES=0

fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
pass() { echo "  [PASS] $1"; }

out="$(env -u KAIROS "$HOOK")"
if [ -z "$out" ]; then pass "no KAIROS: the hook prints nothing"; else fail "no KAIROS: printed: $out"; fi

out="$(KAIROS=0 "$HOOK")"
if [ -z "$out" ]; then pass "KAIROS=0: the hook prints nothing"; else fail "KAIROS=0: printed: $out"; fi

out="$(KAIROS=1 "$HOOK")"
if grep -q "PROACTIVE mode" <<<"$out"; then pass "KAIROS=1: the skill body is injected"
else fail "KAIROS=1: body missing, got: $out"; fi
if grep -qE '^(---|name:|description:|disable-model-invocation:)' <<<"$out"; then
  fail "KAIROS=1: frontmatter leaked into the session"
else pass "KAIROS=1: frontmatter stripped"; fi

body="$(awk 'seen > 1 { print } /^---$/ { seen++ }' "$REPO_ROOT/skills/kairos/SKILL.md")"
if [ "$out" = "$body" ]; then pass "the hook's text IS the skill's body"; else fail "hook text differs from the skill body"; fi

if python3 - "$REPO_ROOT/hooks/hooks.json" <<'PY'
import json, sys
h = json.load(open(sys.argv[1]))["hooks"]["SessionStart"]
assert any("kairos.sh" in x["command"] for e in h for x in e["hooks"]), "hooks.json does not wire kairos.sh"
assert all(m in h[0]["matcher"] for m in ("startup", "compact")), "the hook must fire on startup and after compaction"
PY
then pass "hooks.json wires the hook on startup and compact"; else fail "hooks.json wiring"; fi

echo
if [ "$FAILURES" -eq 0 ]; then echo "All kairos hook tests passed"; exit 0
else echo "$FAILURES kairos hook test(s) failed"; exit 1; fi
