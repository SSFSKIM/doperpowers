#!/usr/bin/env bash
# _lib.sh — shared helpers for the issue-tracker board toolkit (v7: GitHub SSOT).
# Sourced by board-*.sh. Not meant to be run directly.
#
# The board IS the repo's GitHub issues — there is no local state file, no
# single-writer rule, and no worktree guard (nothing here writes a git file).
# Scripts talk to GitHub through `gh` via the shared python module _board.py;
# doperpowers/issue-tracker/ survives only as a gitignored render-cache dir
# for board-map.sh.
set -euo pipefail

_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
_today() { date -u +%Y-%m-%d; }

die() {
  echo "error: $*" >&2
  exit 1
}

# Arity guard for option parsing: die (naming the option) instead of tripping a
# raw `set -u` unbound-variable error when an option is given its final operand.
# Call as `_need_arg "$1" "${2:-}"` right before consuming "$2".
_need_arg() { [ -n "${2:-}" ] || die "option $1 requires a value"; }

# Repo root — render caches and the daemon-registry lookups anchor here. Any
# checkout works, worktrees included: the board lives on GitHub, so there is
# nothing local to diverge.
_board_root() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git repo"
  git rev-parse --show-toplevel
}

BOARD_ROOT="$(_board_root)"
BOARD_DIR="$BOARD_ROOT/doperpowers/issue-tracker"   # render cache only (gitignored)
BOARD_SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Seat registry — ONE registry-root rule, the sminos CLI's own: $SMINOS_HOME,
# then $DAEMON_HOME, then the default. Both names are exported at the same
# value so the CLI, the board scripts and every child read one root.
DAEMON_HOME="${SMINOS_HOME:-${DAEMON_HOME:-$HOME/.claude/sminos}}"
SMINOS_HOME="$DAEMON_HOME"
export SMINOS_HOME DAEMON_HOME

# THE MIGRATION PRECEDES THE FIRST READ — including _binding.sh's, which is
# why this whole block sits AHEAD of the source below rather than after it: an
# api binding with no `repo` in its board.json falls back to this session's own
# seat record, and that read is the first one in the process. Several scripts
# sourcing this file also glob $DAEMON_HOME/*.json directly and never touch
# the CLI, so without this
# they would read a pre-cutover root as an empty fleet: no bound owner, no
# live worker, every guard open. Gated on the cutover actually being pending
# — the legacy root still a real directory — because that check is a stat
# while the migration itself takes $DAEMON_HOME/.metalock, and a lock taken
# at SOURCE TIME by every board script would serialise scripts that only ever
# needed it to write (and deadlocks against a caller already holding it).
# Once per process, and fail closed: "the migration broke" and "the fleet is
# idle" are indistinguishable downstream.
SMINOS_CLI="${SMINOS_CLI:-$BOARD_SCRIPTS/../../sminos/scripts/sminos}"
_sminos_cutover_pending() {
  [ -z "${SMINOS_MIGRATED:-}" ] || return 1
  # A former root still a real directory: the daemon substrate's, or sminos's
  # under its former name.
  local legacy
  for legacy in orchestrating-daemons agora; do
    if [ -d "$HOME/.claude/$legacy" ] && [ ! -L "$HOME/.claude/$legacy" ]; then
      return 0
    fi
  done
  # A `.v2-<ts>` aside beside the root means the rename landed but the merge
  # of the old groups/ did not finish: the registry is mid-cutover, which is
  # precisely the half-migrated state a direct reader must never mistake for
  # an idle fleet. One glob, no lock.
  set -- "$HOME"/.claude/sminos.v2-*
  [ -e "$1" ]
}
if _sminos_cutover_pending; then
  "$SMINOS_CLI" migrate --quiet \
    || die "sminos migrate failed — refusing to read a possibly half-migrated registry"
fi
SMINOS_MIGRATED=1
export SMINOS_CLI SMINOS_MIGRATED

# shellcheck source=_binding.sh
. "$BOARD_SCRIPTS/_binding.sh"

# The target repo (owner/name) — gh mode only: $BOARD_REPO wins, else the
# checkout's repo. Fail-loud when gh is missing/unauthenticated/offline.
if [ "$BOARD_BINDING" = gh ] && [ -z "${BOARD_REPO:-}" ]; then
  command -v gh >/dev/null 2>&1 || die "\`gh\` not found — the board lives on GitHub"
  BOARD_REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" \
    || die "cannot resolve the GitHub repo (gh auth status? set BOARD_REPO=owner/name)"
fi
# EXPORTED IN gh MODE ONLY. gh consumers read it out of the environment
# (_board.py's repo(), board-transition's closed-ticket probe), so there it has
# to travel. In api mode nothing downstream reads the environment — _api_py
# hands the value to python3 explicitly — and exporting it would make this
# process's repo the DEFAULT for any descendant that resolves its own binding:
# _binding.sh honours an inherited BOARD_REPO so a user can override the file,
# and a value derived from the parent's board.json is not that override. A verb
# run from a neighbouring checkout would then read and write the parent's repo,
# which is the accident this key exists to prevent, one level down.
#
# Worker handovers are the deliberate exception: they put the key in the child's
# environment ON PURPOSE, because a worker checks out the head it was dispatched
# for and a head predating this key carries a board.json without one. That child
# is bound to the handing-over process's repo by construction — the run bearer
# beside the key ties it to a ticket in that repo — so it is a pin, not a leak.
# An ambient export is neither, which is why these are scoped.
#
# THE RULE, one line: wherever BOARD_API_URL is pinned on an env prefix for a
# worker, BOARD_REPO is pinned beside it. The two facts have the same lifetime
# and the same blast radius, and a worker that kept the URL while losing the
# repo dies on `binding=api but no repo` mid-run. Today that is the two
# dispatchers' spawns and the sweep's three handovers (relay resume, successor
# resume, fresh-successor spawn); a new one inherits the rule, not a review.
# The prefix is the DECLARED channel; the seat record is the DELIVERED one.
# `claude --bg` drops every spawn-prefix variable — the run bearer and the fence
# included, not just these two — so on the background route the pin reaches the
# dispatcher's child process and no shell inside it. What reaches those shells
# is $CLAUDE_CODE_SESSION_ID, and the client resolves the whole run context
# (bearer, run id, fence) and this repo key out of the seat record that names it
# (dp#35, _board_api.own_seat). The prefix still earns its place: it is correct
# wherever env survives, it is what board-bind stamps the record FROM, and it is
# resolved first — so it remains the rule above, and a new call site inherits
# that rule rather than a review.
if [ "$BOARD_BINDING" = gh ]; then export BOARD_REPO; fi


# Render-cache dir: created on demand, always gitignored — BOARD.html/BOARD.md
# are views of GitHub state and must never be committed (a committed render is
# how v6's board forked across branches).
_render_dir() {
  mkdir -p "$BOARD_DIR"
  [ -f "$BOARD_DIR/.gitignore" ] || printf '*\n' > "$BOARD_DIR/.gitignore"
}

# The recorded --serve pid, but only when it still looks like OUR python
# http.server (prints it and returns 0). A reboot can recycle a stale
# pidfile's pid onto an unrelated process — which --stop must not kill and
# --serve must not mistake for a running board server.
_board_server_pid() {
  local pid
  pid="$(cat "$BOARD_DIR/.server.pid" 2>/dev/null)" || return 1
  [ -n "$pid" ] || return 1
  case "$(ps -o command= -p "$pid" 2>/dev/null)" in
    *http.server*) printf '%s\n' "$pid" ;;
    *) return 1 ;;
  esac
}

# Live tab refresh: when `board-map.sh --serve` left a server up, a successful
# mutation re-renders the cache in the background — every open BOARD.html tab
# hot-reloads on its next poll. No server → free no-op, so mutating scripts
# call this unconditionally as their last step.
_rerender_if_serving() {
  _board_server_pid >/dev/null 2>&1 || return 0
  ("$BOARD_SCRIPTS/board-map.sh" --write >/dev/null 2>&1 &)
}

# Run an inline python3 board operation with _board.py importable.
export BOARD_SCRIPTS
_py() { PYTHONPATH="$BOARD_SCRIPTS${PYTHONPATH:+:$PYTHONPATH}" python3 "$@"; }

# Set seat-record fields under the registry lock — key/value pairs, an EMPTY
# value REMOVING the key. `updated` is never rewritten: the sweep's relay pass
# reads it as last-turn activity, so a bookkeeping write that refreshed it
# would read as a worker that had just spoken. (board-sweep.sh carries its own
# copy of this helper — it sources _binding.sh alone, not this file.)
_meta_put() {  # <uuid> <key> <value> [<key> <value> …]
  # \037-TERMINATED, not newline-separated: a command substitution strips
  # TRAILING newlines, so a removal — whose value is the empty string, and is
  # normally the last field — lost that field and the key silently stayed.
  M_UUID="$1" M_KV="$(printf "%s\037" "${@:2}")" python3 - <<'PY'
import fcntl, json, os
home = os.environ["DAEMON_HOME"]
lock = open(os.path.join(home, ".metalock"), "a")
fcntl.flock(lock, fcntl.LOCK_EX)
p = os.path.join(home, os.environ["M_UUID"] + ".json")
m = json.load(open(p))
kv = os.environ["M_KV"].split("\x1f")[:-1]
for k, v in zip(kv[0::2], kv[1::2]):
    if v == "":
        m.pop(k, None)
    else:
        m[k] = v
# A meta holding the run bearer is 0600 from creation — recreating it at the
# default umask would republish that secret, if only for the width of one
# write. Any other meta keeps the mode it already had.
mode = 0o600 if m.get("run_bearer") else os.stat(p).st_mode & 0o777
tmp = p + ".tmp"
with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode), "w") as f:
    json.dump(m, f, indent=2)
os.chmod(tmp, mode)   # umask narrowing, and a tmp left by an earlier crash
os.replace(tmp, p)
PY
}

# The seats whose review phase MOVES, and what it moves to — the scan half of
# _phase_stamp below. A FUNCTION, not an inline "$(…)", for board-answer.sh's
# reason: bash 3.2 lexes a command substitution with a matcher that does not
# understand the heredoc inside it, so every apostrophe in this prose would
# toggle its quote state and the script would die at parse time.
_phase_rows() {  # <ticket> <state> — "<uuid> <phase>" per seat whose mark moves
  local board repo
  if [ "$BOARD_BINDING" = api ]; then board="api:${BOARD_API_URL:-}"; repo="${BOARD_REPO:-}"
  # gh mode needs no repo dimension: the owner/name inside the key IS the identity.
  else board="gh:${BOARD_REPO:-}"; repo=""; fi
  T_ID="${1#\#}" T_STATE="$2" T_DHOME="$DAEMON_HOME" T_BOARD="$board" T_REPO="$repo" \
  _py - <<'PY'
import glob, json, os
from _board_api import meta_is_mine
env = os.environ
tid, state = env["T_ID"], env["T_STATE"]
for p in sorted(glob.glob(os.path.join(env["T_DHOME"], "*.json"))):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if str(m.get("ticket", "")).lstrip("#") != tid:
        continue
    # The registry is machine-global and a board is not: a neighbouring repo
    # seat on ITS ticket 9 is not ours to mark.
    if not meta_is_mine(m, env["T_BOARD"], env["T_REPO"]):
        continue
    cur = str(m.get("phase") or "")
    if state == "in-review":
        want = "review"
    elif state == "needs-human" and cur:
        want = "review-parked"
    else:
        want = ""
    if want != cur:
        print("%s %s" % (m.get("uuid") or os.path.basename(p)[:-5], want))
PY
}

# Mark the seats bound to <ticket> with the ticket's review phase: `review`
# while it is in-review, `review-parked` after a park out of the review, no key
# at all otherwise. The local lane cap and the tick's review-recovery selector
# read this off the registry rather than paying a ticket read per seat per
# tick.
#
# DERIVED FROM THE STATE THE BOARD WROTE, never the edge the caller asked for:
# the convergence rule and the server both transmute a rebuild into a park, and
# that park is a review park. `needs-human` reads the seat's own mark for the
# same reason — it is the record of where the park came from.
#
# EVERY bound seat, because the phase is the TICKET's: a stale second binding
# left holding a lane slot the live one does not is the accounting this exists
# to get right. No bound seat marks nothing, and a failure is reported and
# never fatal — the transition it follows has already landed.
_phase_stamp() {  # <ticket> <state-the-board-wrote>
  local rows uuid want
  [ -n "${2:-}" ] && [ -d "$DAEMON_HOME" ] || return 0
  rows="$(_phase_rows "$1" "$2")" \
    || { echo "note: #$1 — the seat review phase was not updated (registry scan failed)" >&2
         return 0; }
  while read -r uuid want; do
    [ -n "$uuid" ] || continue
    _meta_put "$uuid" phase "$want" \
      || echo "note: #$1 — the review phase write on seat ${uuid%%-*} failed" >&2
  done <<EOF
$rows
EOF
}

# Verbs with no API-mode counterpart refuse in one voice: the same message from
# four copies drifted the moment one of them was edited, and this one described
# a route set (edge re-cut / priority / relates / body edits) that does not name
# what board-migrate-gh actually is. The caller says what IT is; the pointer is
# shared.
_refuse_no_api_route() {  # <what this verb does>
  [ "$BOARD_BINDING" != api ] || die "$1 has no API-mode counterpart — \
file a server-side ticket in the arkho repo if the need is real; \
until such a route lands, run this against a gh-bound repo only"
}

# The script's own header block — the CONTIGUOUS run of column-0 `#` lines
# after the shebang, and nothing else. Grepping every column-0 `#` line in the
# file swept up any later comment that happened to start at column 0, so a
# usage message grew a paragraph about lock stealing as the file grew; scripts
# indented such notes by one space purely to stay out of it.
usage_from_header() {
  awk 'NR == 1 && /^#!/ { next }
       /^#/ { sub(/^# ?/, ""); print; next }
       { exit }' "$1"
}
