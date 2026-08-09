#!/usr/bin/env bash
# _binding.sh — per-repo board-binding resolution (A2). Side-effect-free:
# sourceable from ANY entry point BEFORE gh-mode initialization. Defines
# BOARD_BINDING, BOARD_API_URL, BOARD_CREDENTIALS_FILE, BOARD_ROOT, _api_py.
# BOARD_ROOT, BOARD_API_URL and BOARD_CREDENTIALS_FILE are honored if the
# sourcing shell already set them (that is how _lib.sh hands over its own root,
# same process, and how a user overrides either value) but none of the three is
# exported — see the export note below.
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
# Credentials slug: the repo's stable identity, NOT the checkout directory.
# In a linked worktree --show-toplevel is the worktree dir (usually a branch
# name), which would name a token file nobody ever wrote; --git-common-dir is
# always <main-checkout>/.git, and in a plain checkout it is "$BOARD_ROOT/.git",
# so the same expression serves both. An inherited/exported override still wins.
if [ -z "${BOARD_CREDENTIALS_FILE:-}" ]; then
  _board_common_dir="$(git -C "$BOARD_ROOT" rev-parse --path-format=absolute --git-common-dir)"
  BOARD_CREDENTIALS_FILE="$HOME/.arkho-board/$(basename "$(dirname "$_board_common_dir")").env"
fi
# Only the binding is exported. BOARD_ROOT, BOARD_API_URL and
# BOARD_CREDENTIALS_FILE are repo-scoped: exporting them would let a descendant
# that sources this file from a DIFFERENT repo resolve its own board.json while
# holding the parent's URL and token file. _api_py passes both to python3
# explicitly, so nothing downstream depends on them being in the environment.
export BOARD_BINDING

# Run an inline python3 board operation with the API client importable and the
# binding env visible. _BINDING_DIR: this file's own directory, so non-board
# entry points (dispatch scripts) get the right PYTHONPATH without BOARD_SCRIPTS.
_BINDING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_api_py() { PYTHONPATH="$_BINDING_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  BOARD_API_URL="$BOARD_API_URL" BOARD_CREDENTIALS_FILE="$BOARD_CREDENTIALS_FILE" \
  python3 "$@"; }
