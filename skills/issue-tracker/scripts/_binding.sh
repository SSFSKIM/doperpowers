#!/usr/bin/env bash
# _binding.sh — per-repo board-binding resolution (A2). Side-effect-free:
# sourceable from ANY entry point BEFORE gh-mode initialization. Defines
# BOARD_BINDING, BOARD_API_URL, BOARD_CREDENTIALS_FILE, BOARD_ROOT, _api_py,
# and — in api mode only — BOARD_REPO.
# BOARD_ROOT, BOARD_API_URL, BOARD_CREDENTIALS_FILE and BOARD_REPO are honored
# if the sourcing shell already set them (that is how _lib.sh hands over its own
# root, same process, and how a user overrides any of the values) but none of
# the four is exported here — see the export note below.
# .doperpowers/board.json selects the substrate: absent or {"binding":"gh"}
# -> gh mode, byte-identical to pre-A2; {"binding":"api","url":...,"repo":...}
# -> the toolkit speaks the Arkho board API, for the named repo, and gh is
# neither required nor invoked. BOARD_REPO means different things per binding:
# in api mode it is the BOARD's repo key (a bare name the service registered),
# in gh mode it is owner/name and _lib.sh resolves it.
BOARD_BINDING=gh
BOARD_API_URL="${BOARD_API_URL:-}"
# This file's own directory, so non-board entry points (dispatch scripts) get
# the right PYTHONPATH without BOARD_SCRIPTS. Defined up here because the repo
# fallback below imports the client too, not only _api_py at the foot.
_BINDING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The repo THIS SESSION's own seat record was bound for, or nothing.
#
# A worker checks out the head it was dispatched for, and a head predating the
# `repo` key carries a two-key board.json — so the file cannot answer. The env
# prefix that was meant to was dropped by `claude --bg` before the worker's own
# shells ran (dp#35). The record can answer: board-bind.sh stamped `board_repo`
# onto it beside the run when the dispatcher bound this session.
#
# The URL is never taken from the record. The checkout's board.json names the
# board; a record naming a different service is not this checkout's session, and
# that same board equality is the whole guard here. Empty on every ordinary
# failure — no session id, no registry, no record — because the caller's next
# line is the fatal that says the repo is undeclared, which is the right
# diagnosis for all of them.
#
# STDERR IS NOT SWALLOWED. own_seat() writes there for one reason: a seat this
# session was DISPATCHED into whose bind never landed, where it refuses to
# resolve anything rather than let the process act as somebody else. That
# refusal is the diagnosis, and the `no repo` fatal that follows it is only the
# symptom — hiding the first would leave an operator reading the wrong one.
_repo_from_own_seat() {
  BOARD_API_URL="$BOARD_API_URL" \
  PYTHONPATH="$_BINDING_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 -c '
import _board_api as A
seat = A.own_seat()
print(str(seat[1].get("board_repo") or "").strip() if seat else "")' || true
}
if [ -z "${BOARD_ROOT:-}" ]; then
  BOARD_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" \
    || { echo "error: not inside a git repo" >&2; return 1 2>/dev/null || exit 1; }
fi
# The main checkout's .git, always — in a plain checkout it is "$BOARD_ROOT/.git",
# and in a linked worktree it is still the main checkout's, which is the only
# stable identity a worktree has. Empty when BOARD_ROOT is no checkout at all:
# that is a repo with no board and no credentials slug, not a fatal, and the
# `git` failure must not take the caller down before the binding is decided.
_board_common_dir="$(git -C "$BOARD_ROOT" rev-parse --path-format=absolute \
  --git-common-dir 2>/dev/null || true)"
_board_config="$BOARD_ROOT/.doperpowers/board.json"
# A LINKED WORKTREE READS THE MAIN CHECKOUT'S FILE WHEN IT HAS NONE OF ITS OWN.
# board.json is committed, so a worktree at a current head carries it — but a
# worker checks out the head it was DISPATCHED for, and a head predating that
# commit has no file at all. The answer was a silent gh: the first board
# command spoke to the fork's GitHub issues, and a write would have landed on
# an unrelated one. The repo is one binding wherever it is checked out from.
[ -f "$_board_config" ] || [ -z "$_board_common_dir" ] \
  || _board_config="$(dirname "$_board_common_dir")/.doperpowers/board.json"
if [ -f "$_board_config" ]; then
  _binding_line="$(python3 - "$_board_config" <<'PY'
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception as e:
    print("parse-error: %s" % e); sys.exit(0)
# The repo is TRIMMED here: `[ -n " " ]` is true in the shell, so a repo of
# spaces would pass the emptiness check below and then ride the wire as an
# encoded blank — which the server reads as no filter at all.
print("%s|%s|%s" % (cfg.get("binding", "gh"), cfg.get("url", ""),
                    str(cfg.get("repo") or "").strip()))
PY
)"
  case "$_binding_line" in
    parse-error*) echo "error: .doperpowers/board.json: ${_binding_line#parse-error: }" >&2
                  return 1 2>/dev/null || exit 1 ;;
  esac
  _binding_rest="${_binding_line#*|}"
  case "${_binding_line%%|*}" in
    api) BOARD_BINDING=api
         [ -n "$BOARD_API_URL" ] || BOARD_API_URL="${_binding_rest%%|*}"
         [ -n "$BOARD_API_URL" ] || { echo "error: .doperpowers/board.json names binding=api but no url" >&2
                                      return 1 2>/dev/null || exit 1; }
         # THE REPO THE BOARD KNOWS THIS CHECKOUT BY. One service serves
         # several repositories out of one ticket namespace, so a client that
         # names none is not repo-neutral: the server picks for it — its
         # founding repo on an ordinary write, EVERY repo on a list read — and
         # a register run from a neighbouring checkout files into whichever
         # repo the service was founded with. Declared, never guessed: neither
         # the server's pick nor the checkout's directory name is this repo's
         # identity on the board, and a wrong one is silent. An env override
         # still wins (a blank one is no declaration at all — and a blank
         # spelled as whitespace is still a blank, so the override is trimmed
         # before it is weighed, exactly as the file's value is).
         BOARD_REPO="$(printf '%s' "${BOARD_REPO:-}" \
           | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
         [ -n "$BOARD_REPO" ] || BOARD_REPO="${_binding_rest#*|}"
         [ -n "$BOARD_REPO" ] || BOARD_REPO="$(_repo_from_own_seat)"
         [ -n "$BOARD_REPO" ] || { echo "error: .doperpowers/board.json names binding=api but no repo" >&2
                                   return 1 2>/dev/null || exit 1; } ;;
    gh) : ;;
    # AN UNKNOWN BINDING IS A CONFIGURATION ERROR, NOT A DEFAULT. Falling
    # through left BOARD_BINDING=gh, so a typo (`"api "`, `"API"`, `"arkho"`)
    # silently sent every read and every mutation to GitHub — against a repo
    # whose board lives somewhere else entirely.
    *) echo "error: .doperpowers/board.json: unknown binding \"${_binding_line%%|*}\" — expected \"gh\" or \"api\"" >&2
       return 1 2>/dev/null || exit 1 ;;
  esac
fi
# Credentials slug: the repo's stable identity, NOT the checkout directory.
# In a linked worktree --show-toplevel is the worktree dir (usually a branch
# name), which would name a token file nobody ever wrote, so the common dir
# derived above is what names the file — the same identity the binding was just
# read from. A root that is no checkout has none and names itself. An
# inherited/exported override still wins.
if [ -z "${BOARD_CREDENTIALS_FILE:-}" ]; then
  BOARD_CREDENTIALS_FILE="$HOME/.arkho-board/$(basename \
    "$(dirname "${_board_common_dir:-$BOARD_ROOT/.git}")").env"
fi
# Only the binding is exported. BOARD_ROOT, BOARD_API_URL, BOARD_CREDENTIALS_FILE
# and BOARD_REPO are repo-scoped: exporting them would let a descendant that
# sources this file from a DIFFERENT repo resolve its own board.json while
# holding the parent's URL, token file and repo key. _api_py passes all three to
# python3 explicitly, so nothing downstream depends on them being in the
# environment.
export BOARD_BINDING

# Run an inline python3 board operation with the API client importable and the
# binding env visible.
_api_py() { PYTHONPATH="$_BINDING_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  BOARD_API_URL="$BOARD_API_URL" BOARD_CREDENTIALS_FILE="$BOARD_CREDENTIALS_FILE" \
  BOARD_REPO="${BOARD_REPO:-}" \
  python3 "$@"; }

# The per-binding subdirectory of a machine-global registry store — the shell's
# reach into _board_api.store_dir(), created on demand. NOT exported, by the
# same rule BOARD_REPO follows in api mode: each script calls it after sourcing
# this file, so a descendant that resolves a DIFFERENT repo's binding never
# inherits this one's store paths.
board_store_dir() {  # <store name> — echoes <registry root>/<name>/<digest>
  _api_py -c 'import sys, _board_api as A; print(A.store_dir(sys.argv[1]))' "$1"
}
