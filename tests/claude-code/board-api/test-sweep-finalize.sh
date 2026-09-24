#!/usr/bin/env bash
# test-sweep-finalize.sh — _sweep_api.sh closes an in-review ticket whose PR
# merged after its QA agent returned, without waiting for the recovery ladder.
#
# THE STATE THIS PASS EXISTS FOR: an armed auto-merge (or a later human merge)
# lands while the owner is idle and its run is still open. Nothing else writes
# done on the API board. GitHub's merged head must match the latest review
# trail after entry into review; a moved ticket and a working owner are left
# alone. The pass runs before review-recover can wake that idle owner.
#
# PINS: run versus automation authority, the server's evidence refusal, head
# mismatch, missing/stale evidence, epic and open-PR filtering, a fresh by-id
# read, sync-before-status, a failed registry scan, a dead owner's stale `working` record, and the
# whole tick's no-wasted-nudge order.
. "$(dirname "$0")/helpers.sh"

free_port() { python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'; }
wait_for_port() {
  local tries=200
  while [ "$tries" -gt 0 ]; do
    if python3 -c "import socket, sys
sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $1)) == 0 else 1)"; then return 0; fi
    tries=$((tries - 1)); sleep 0.05
  done
  return 1
}

TDIR="$(mktemp -d)"
trap 'rm -rf "$TDIR"' EXIT
CREDS="$TDIR/creds.env"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
PORT="$(free_port)"
FIX="$TDIR/fixtures.json"; : > "$FIX.log"
# The mock matches method + path PREFIX, first match wins. Timeline routes
# precede their by-id routes so a timeline cannot masquerade as a ticket.
python3 - "$FIX" <<'PY'
import json, sys

f = []
def route(method, path, body, status=200):
    f.append({"method": method, "path": path, "status": status, "body": body})
def sha(n):
    return f"{n:040d}"
def pr(n):
    return f"https://github.com/o/r/pull/{n}"

ids = (80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91)
rows = {n: {"id": n, "state": "in-review", "priority": "P1",
            "title": f"ticket {n}", "pr_url": "512" if n == 84 else pr(n),
            "owner_run": None if n in (82, 88) else n, "plan": None}
        for n in ids}
route("GET", "/tickets?limit=200&states=in-review",
      {"items": list(rows.values()), "next": None, "as_of": 1})

def transition(cursor):
    return {"source": "board", "cursor": str(cursor), "kind": "transition",
            "runId": None, "body": {"note": "review opened", "to": "in-review"}}
def trail(cursor, text):
    return {"source": "board", "cursor": str(cursor), "kind": "review-trail",
            "runId": None, "body": {"text": text}}

for n in (80, 82, 83, 85, 86, 87, 88, 89, 90, 91):
    text = "round 1 — level medium"
    if n != 85:
        text += "\nreviewed head: " + sha(830 if n == 83 else n)
    records = ([trail(1, text), transition(2)] if n == 86
               else [transition(1), trail(2, text)])
    route("GET", f"/tickets/{n}/timeline", {"records": records})

for n in (80, 82, 88, 89, 90, 91):
    row = rows[n].copy()
    if n == 89:
        row["state"] = "in-progress"  # rebuild between list and re-read
    route("GET", f"/tickets/{n}", row)

route("POST", "/tickets/80/transition", {"ok": True, "to": "done"})
route("POST", "/tickets/82/transition",
      {"error": {"code": "review-trail-required", "message":
       "in-review → done needs a review-trail event by this run after the latest entry into in-review"}}, 403)
route("POST", "/tickets/88/transition", {"ok": True, "to": "done"})
route("POST", "/tickets/91/transition", {"ok": True, "to": "done"})
for n in (80, 81, 83, 85, 86, 87, 89, 90):
    route("POST", f"/runs/{n}/renew", {"renewed": True})
route("GET", "/answers/unrelayed", [])
route("GET", "/runs/needing-resume", [])
with open(sys.argv[1], "w") as out:
    json.dump(f, out)
PY
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null; { wait $MOCK; } 2>/dev/null || true; rm -rf "$TDIR"' EXIT
wait_for_port "$PORT" || { echo "FAIL mock server never listened on $PORT"; exit 1; }

r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$PORT" > "$r/.doperpowers/board.json"

DH="$TDIR/registry"; mkdir -p "$DH"
DS="$TDIR/stubs"; mkdir -p "$DS"
NUDGES="$TDIR/nudges.log"; : > "$NUDGES"
TESTHOME="$TDIR/home"; mkdir -p "$TESTHOME/.claude/projects/proj"
meta() {
  printf '{"uuid":"u-%s","current":"u-%s","status":"%s","run_id":%s,"fence":1,"lane":"implementer","bind_confirmed":true,"ticket":"%s","run_bearer":"tok-%s","phase":"review"}\n' \
    "$1" "$1" "$2" "$1" "$1" "$1" > "$DH/u-$1.json"
  chmod 600 "$DH/u-$1.json"
}
for n in 80 81 83 85 86 87 89 90 91; do
  status=idle; case "$n" in 87|91) status=working ;; esac
  meta "$n" "$status"
  touch "$TESTHOME/.claude/projects/proj/u-$n.jsonl"
done
touch -t 202607170000 "$TESTHOME/.claude/projects/proj/u-80.jsonl"

# gh answers from the requested PR number, not the call sequence. A real PR's
# merge commit and head are separate values, especially for squash merges.
cat > "$DS/gh" <<'STUB'
#!/usr/bin/env bash
echo "GH $*" >> "$GH_LOG"
[ "${1:-}" = pr ] && [ "${2:-}" = view ] && [ "${4:-}" = --json ] &&
  [ "${5:-}" = mergedAt,mergeCommit,headRefOid ] || exit 2
url="${3%/}"; n="${url##*/}"
case "$n" in
  81) echo '{"mergedAt":null,"mergeCommit":null,"headRefOid":null}'; exit 0 ;;
  80|82|83|85|86|87|88|89|90|91) ;;
  *) exit 2 ;;
esac
head="$n"; [ "$n" != 83 ] || head=831
printf '{"mergedAt":"2026-09-23T12:00:00Z","mergeCommit":{"oid":"%040d"},"headRefOid":"%040d"}\n' "$((n * 100))" "$head"
STUB
cat > "$DS/sminos" <<'STUB'
#!/usr/bin/env bash
verb="${1:-}"; shift || true
case "$verb" in
  migrate) exit 0 ;;
  sync)
    python3 - "$DAEMON_HOME/$1.json" "$1" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as f:
        m = json.load(f)
except Exception:
    print("absent"); raise SystemExit(0)
if sys.argv[2] == "u-91":
    print("absent"); raise SystemExit(0)  # the session is gone; its record still says working
if sys.argv[2] == "u-90" and m["status"] == "idle":
    m["status"] = "working"  # native wake repaired the stale record
    with open(sys.argv[1], "w") as f:
        json.dump(m, f)
print("live" if m["status"] in ("working", "blocked") else "noop")
PY
    ;;
  resume|wake) echo "WAKE uuid=${1:-}" >> "$NUDGE_LOG" ;;
  *) echo "stub sminos: unexpected verb '$verb'" >&2; exit 2 ;;
esac
STUB
chmod +x "$DS/gh" "$DS/sminos"
: > "$TDIR/gh.log"
SW() {
  ( cd "$r" && env HOME="$TESTHOME" DAEMON_HOME="$DH" SMINOS_CLI="$DS/sminos" \
      NUDGE_LOG="$NUDGES" GH_LOG="$TDIR/gh.log" PATH="$DS:$PATH" \
      BOARD_CREDENTIALS_FILE="$CREDS" BOARD_SWEEP_TICK_BUDGET=900 \
      "$SCRIPTS/_sweep_api.sh" "$@" )
}
# Render the API request log's parsed body for assertions on the actual wire,
# not on escaped JSON-within-JSON in the mock's log.
posts() { python3 - "$FIX.log" "$1" <<'PY'
import json, sys
for line in open(sys.argv[1]):
    req = json.loads(line)
    if req["method"] == "POST" and req["path"].startswith(sys.argv[2]):
        body = json.loads(req["body"])
        print(f'{req["path"]} auth={req["auth"]} to={body.get("to")} note={body.get("note")}')
PY
}
post_count() { printf '[%s]\n' "$(posts "/tickets/$1/transition" | wc -l | tr -d ' ')"; }
renew_count() { printf '[%s]\n' "$(posts "/runs/$1/renew" | wc -l | tr -d ' ')"; }

# The stand-alone pass: every candidate shares this one fixture world. Its
# renewal is held off here (its own run below pins it): a renewal pass syncs
# every seat, u-90 included, before finalize reaches it.
OUT="$TDIR/finalize.out"; code=0
BOARD_FINALIZE_RENEW_SEC=99999999999 SW finalize > "$OUT" 2>&1 || code=$?
t  "finalize is invocable alone" "exit=0" printf 'exit=%s\n' "$code"
M80="$(printf '%040d' 8000)"; SHA80="$(printf '%040d' 80)"
SHA83M="$(printf '%040d' 831)"; SHA83R="$(printf '%040d' 830)"
M88="$(printf '%040d' 8800)"; SHA88="$(printf '%040d' 88)"
t  "80 closes as its owning run with the reviewed merge note" \
   "/tickets/80/transition auth=Bearer tok-80 to=done note=finalize: https://github.com/o/r/pull/80 merged as $M80 at the reviewed head $SHA80" posts /tickets/80/transition
t  "80's close is reported as its run" "done written as run 80" cat "$OUT"
t  "81's open PR is inspected" "pull/81 --json mergedAt,mergeCommit,headRefOid" cat "$TDIR/gh.log"
t  "81's open PR is not closed" "[0]" post_count 81
nt "81's ordinary open PR is silent" "#81" cat "$OUT"
t  "82 makes exactly one refused attempt" "[1]" post_count 82
t  "82's ownerless attempt is automation, not human" "/tickets/82/transition auth=Bearer a to=done" posts /tickets/82/transition
t  "82's server evidence refusal is left with recovery" "the board refused done (review-trail-required)" cat "$OUT"
t  "83 names both mismatched heads" "GitHub merged $SHA83M, the trail names $SHA83R" cat "$OUT"
t  "83 is not closed off the reviewed head" "[0]" post_count 83
nt "84's numeric epic package never reaches GitHub" "512" cat "$TDIR/gh.log"
t  "84's epic package is not closed" "[0]" post_count 84
t  "85 without a head line is held" "#85 — merged, but the latest review-trail names no reviewed head" cat "$OUT"
t  "85 is not closed" "[0]" post_count 85
t  "86's trail before the latest review entry is held" "#86 — merged, but no review-trail since the ticket last entered review" cat "$OUT"
t  "86 is not closed" "[0]" post_count 86
t  "87's working owner is left to its agent" "#87 — merged, but its owner u-87 is mid-turn" cat "$OUT"
t  "87 is not closed" "[0]" post_count 87
t  "88 closes as automation with the reviewed merge note" \
   "/tickets/88/transition auth=Bearer a to=done note=finalize: https://github.com/o/r/pull/88 merged as $M88 at the reviewed head $SHA88" posts /tickets/88/transition
t  "88's close is reported as automation" "done written as automation" cat "$OUT"
t  "89's moved ticket is held" "#89 — moved between the read and the write (now in-progress" cat "$OUT"
t  "89 is not closed" "[0]" post_count 89
t  "90's natively-woken owner is left to its agent" "#90 — merged, but its owner u-90 is mid-turn" cat "$OUT"
t  "90 is not closed" "[0]" post_count 90
M91="$(printf '%040d' 9100)"; SHA91="$(printf '%040d' 91)"
t  "91's dead owner is not mid-turn: it closes as its run" \
   "/tickets/91/transition auth=Bearer tok-91 to=done note=finalize: https://github.com/o/r/pull/91 merged as $M91 at the reviewed head $SHA91" posts /tickets/91/transition
nt "91's dead owner is never reported mid-turn" "#91 — merged, but its owner" cat "$OUT"
t  "90 was synced before its status was trusted" '"status": "working"' cat "$DH/u-90.json"
# Assert the ordering, rather than only the presence of all three operations.
t  "80's evidence, fresh by-id read and write are in order" "ordered" python3 - "$FIX.log" <<'PY'
import json, sys
calls = [json.loads(line) for line in open(sys.argv[1])]
def index(method, path):
    return next(i for i, c in enumerate(calls)
                if c["method"] == method and c["path"].startswith(path))
timeline = index("GET", "/tickets/80/timeline")
row = next(i for i, c in enumerate(calls)
           if c["method"] == "GET" and c["path"] == "/tickets/80")
write = index("POST", "/tickets/80/transition")
print("ordered" if timeline < row < write else "out of order")
PY

# A new tick sees the original list projection again. If review-recover ran
# before finalize, the stale idle u-80 would be woken before the close.
: > "$FIX.log"; : > "$NUDGES"
meta 80 idle
ALL="$TDIR/all.out"; code=0
SW all > "$ALL" 2>&1 || code=$?
t  "all completes" "exit=0" printf 'exit=%s\n' "$code"
t  "all reaches finalize and closes 80" "#80 — https://github.com/o/r/pull/80 merged as $M80 at the reviewed head $SHA80; done written as run 80" cat "$ALL"
nt "all spends no review-recover nudge on the closed owner" "u-80" cat "$NUDGES"
nt "all never starts a nudge for the closed ticket" "review-recover: #80" cat "$ALL"
t  "80's transition clears its seat's review mark" "phase=<absent>" python3 - "$DH/u-80.json" <<'PY'
import json, sys
print("phase=" + str(json.load(open(sys.argv[1])).get("phase", "<absent>")))
PY
t  "all's finalize adds no renewal pass on top of the tick's fresh one" "[1]" renew_count 80

# Serial reads across many candidates can fill the tick budget, which is the
# lease's own length, so the pass renews every live run again once the last
# renewal is old. At 0 seconds that is ahead of every candidate: run 80 is
# renewed again after its own ticket's write, on the way to 81 onward.
: > "$FIX.log"; meta 80 idle; meta 90 idle
RENEWOUT="$TDIR/renew.out"; code=0
BOARD_FINALIZE_RENEW_SEC=0 SW finalize > "$RENEWOUT" 2>&1 || code=$?
t  "the renewing pass completes" "exit=0" printf 'exit=%s\n' "$code"
t  "live runs are renewed between candidates, not once" "renewed after" python3 - "$FIX.log" <<'PY'
import json, sys
calls = [json.loads(line) for line in open(sys.argv[1])]
posts = [c["path"] for c in calls if c["method"] == "POST"]
write = posts.index("/tickets/80/transition")
before = "/runs/80/renew" in posts[:write]
after = "/runs/80/renew" in posts[write + 1:]
print("renewed after" if before and after else "before=%s after=%s" % (before, after))
PY
nt "a dead owner's lease is still left to expire" "/runs/91/renew" posts /runs/

# A registry scan that dies is not an empty registry. Read as one, every owned
# ticket would fall to the ownerless automation write, whose override passes
# the local fence — a mid-turn owner (90) closed under its own agent — and
# whose principal skips the server's by-this-run trail gate. The wrapper kills
# only the sweep's registry scan (its source is the one that reads `all`), so
# board-transition's own fence scan still runs as it would in the field.
SCANSTUB="$TDIR/scanstub"; mkdir -p "$SCANSTUB"
cat > "$SCANSTUB/python3" <<STUB
#!/usr/bin/env bash
if [ "\${1:-}" = - ]; then
  src="\$(cat)"
  case "\$src" in *keep_runless*) exit 1 ;; esac
  exec "$(command -v python3)" "\$@" <<< "\$src"
fi
exec "$(command -v python3)" "\$@"
STUB
chmod +x "$SCANSTUB/python3"
: > "$FIX.log"
SCANFAIL="$TDIR/scanfail.out"; code=0
# Renewal held off: its own scan would die first and end the tick, which is
# renew's failure line, not this pass's.
( PATH="$SCANSTUB:$PATH"; BOARD_FINALIZE_RENEW_SEC=99999999999 SW finalize ) > "$SCANFAIL" 2>&1 || code=$?
t  "a failed registry scan is reported" "#80 — the registry scan failed; nothing is written this tick" cat "$SCANFAIL"
t  "a failed registry scan does not close 80 as automation" "[0]" post_count 80
t  "a failed registry scan does not close 90 under its mid-turn owner" "[0]" post_count 90
nt "a failed registry scan never overrides the local fence" "override:" cat "$SCANFAIL"

# A gh-bound checkout refuses the API tick before looking at GitHub.
ghrepo="$(mkrepo)"
before="$(wc -l < "$TDIR/gh.log")"
wrong_binding() { ( cd "$ghrepo" && env HOME="$TESTHOME" DAEMON_HOME="$DH" PATH="$DS:$PATH" GH_LOG="$TDIR/gh.log" "$SCRIPTS/_sweep_api.sh" finalize ); }
t  "a gh-bound checkout refuses the API pass" "runs only under an api binding" wrong_binding
gh_unchanged() { [ "$(wc -l < "$TDIR/gh.log")" = "$before" ] && echo unchanged; }
t  "a gh-bound checkout never calls GitHub" "unchanged" gh_unchanged
finish
