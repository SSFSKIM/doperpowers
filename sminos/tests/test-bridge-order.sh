#!/usr/bin/env bash
#
# Row order and the snapshot cut (DC2 M4, DX5): the child's readiness, each
# loop's cut, a later resync ending every subscription, and the reference
# consumer (bridge_order.py) joining a transcript on disk with the real
# child's stream through the cases the order exists for. Hermetic: HOME and
# SMINOS_HOME are temporary (SMINOS_HOME short, for the socket's path).
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SMINOS="$PLUGIN_ROOT/skills/sminos/scripts/sminos"

T="$(mktemp -d /tmp/smo.XXXXXX)"
cleanup() {
  for _ in $(seq 1 60); do pgrep -f "bridge --session 5b000001-0000-4000-8000-000000000f" >/dev/null 2>&1 || break; sleep 0.05; done
  rm -rf "$T"
}
trap cleanup EXIT

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME MAWS_LANE CLAUDE_CONFIG_DIR SMINOS_BRIDGE_READY_WAIT
export HOME="$T/home"
export SMINOS_HOME="$T/s"
mkdir -p "$HOME" "$T/work"
mkdir -m 700 "$SMINOS_HOME"

echo "row order and the snapshot cut:"
PASSES=0
FAILURES=0
while IFS= read -r line; do
  echo "  $line"
  case "$line" in
    "ok "*) PASSES=$((PASSES + 1)) ;;
    "FAIL "*) FAILURES=$((FAILURES + 1)) ;;
  esac
done < <(python3 "$SCRIPT_DIR/bridge_order.py" "$SMINOS" "$T/work" 2>&1)

echo
if [ "$FAILURES" -eq 0 ] && [ "$PASSES" -gt 0 ]; then
  echo "all $PASSES bridge order assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) bridge order assertions FAILED"
  exit 1
fi
