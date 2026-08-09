#!/usr/bin/env bash
# _binding.sh — per-repo board-binding resolution (A2). Side-effect-free:
# sourceable from ANY entry point BEFORE gh-mode initialization. Defines
# BOARD_BINDING, BOARD_API_URL, BOARD_CREDENTIALS_FILE, BOARD_ROOT, _api_py.
# BOARD_ROOT is honored if the sourcing shell already set it (that is how
# _lib.sh hands over its own root, same process) but is deliberately NOT
# exported: an exported root would be inherited by every descendant process,
# and a dispatch script that sources this file from a DIFFERENT repo would
# then silently resolve board.json and credentials against its parent's repo.
# .doperpowers/board.json selects the substrate: absent or {"binding":"gh"}
# -> gh mode, byte-identical to pre-A2; {"binding":"api","url":...} -> the
# toolkit speaks the Arkho board API and gh is neither required nor invoked.
BOARD_BINDING=gh
BOARD_API_URL="${BOARD_API_URL:-}"
if [ -z "${BOARD_ROOT:-}" ]; then
  BOARD_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" \
    || { echo "error: not inside a git repo" >&2; return 1 2>/dev/null || exit 1; }
fi
if [ -f "$BOARD_ROOT/.doperpowers/board.json" ]; then
  _binding_line="$(python3 - "$BOARD_ROOT/.doperpowers/board.json" <<'PY'
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception as e:
    print("parse-error: %s" % e); sys.exit(0)
print("%s|%s" % (cfg.get("binding", "gh"), cfg.get("url", "")))
PY
)"
  case "$_binding_line" in
    parse-error*) echo "error: .doperpowers/board.json: ${_binding_line#parse-error: }" >&2
                  return 1 2>/dev/null || exit 1 ;;
    api\|*) BOARD_BINDING=api
            [ -n "$BOARD_API_URL" ] || BOARD_API_URL="${_binding_line#api|}"
            [ -n "$BOARD_API_URL" ] || { echo "error: .doperpowers/board.json names binding=api but no url" >&2
                                         return 1 2>/dev/null || exit 1; } ;;
  esac
fi
BOARD_CREDENTIALS_FILE="${BOARD_CREDENTIALS_FILE:-$HOME/.arkho-board/$(basename "$BOARD_ROOT").env}"
export BOARD_BINDING BOARD_API_URL BOARD_CREDENTIALS_FILE

# Run an inline python3 board operation with the API client importable and the
# binding env visible. _BINDING_DIR: this file's own directory, so non-board
# entry points (dispatch scripts) get the right PYTHONPATH without BOARD_SCRIPTS.
_BINDING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_api_py() { PYTHONPATH="$_BINDING_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  BOARD_API_URL="$BOARD_API_URL" BOARD_CREDENTIALS_FILE="$BOARD_CREDENTIALS_FILE" \
  python3 "$@"; }
