#!/usr/bin/env bash
# test-sweep-retire-finished.sh — _sweep_api.sh phase 1's closing step: the seat
# of an ended run whose ticket is terminal is retired.
#
# THE STATE THIS STEP EXISTS FOR: the owner seat stays bound through `done` —
# its QA agent merges and writes the terminal transition, the server ends the
# run with it, and the renew phase strips the run from the seat's meta. Nothing
# else ever speaks to that seat again, so without this step every finished
# ticket leaves one idle background session behind. The gh tick's CANCEL pass
# is the parity target.
#
# PINS: an ended run on a `done` or `wontfix` ticket retires its seat; an ended
# run on a ticket that is NOT terminal (a reclaim, a park) is the resume path's
# and is left alone; a seat still `working` when its ticket went terminal is
# not retired mid-turn — and a later tick, which no longer sees a run to end,
# still retires it once its turn is over.
. "$(dirname "$0")/helpers.sh"

free_port() { python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'; }
wait_for_port() {  # poll rather than sleep — a fixed nap is a flake
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

# ---- the wire ---------------------------------------------------------------
# Every run the registry holds has already been ended by the server: the
# terminal transition (or the reclaim) is what ended it.
PORT="$(free_port)"
FIX="$TDIR/fixtures.json"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/runs/53/renew","status":409,
  "body":{"error":{"code":"run-ended","message":"run 53 is not open"}}},
 {"method":"POST","path":"/runs/54/renew","status":409,
  "body":{"error":{"code":"run-ended","message":"run 54 is not open"}}},
 {"method":"POST","path":"/runs/55/renew","status":409,
  "body":{"error":{"code":"run-ended","message":"reclaimed"}}},
 {"method":"POST","path":"/runs/56/renew","status":409,
  "body":{"error":{"code":"run-ended","message":"run 56 is not open"}}},
 {"method":"GET","path":"/tickets/72","status":200,
  "body":{"id":72,"state":"done","priority":"P2","title":"merged by its QA agent"}},
 {"method":"GET","path":"/tickets/73","status":200,
  "body":{"id":73,"state":"wontfix","priority":"P3","title":"closed by a human"}},
 {"method":"GET","path":"/tickets/74","status":200,
  "body":{"id":74,"state":"in-progress","priority":"P2","title":"reclaimed, a successor is due"}},
 {"method":"GET","path":"/tickets/75","status":200,
  "body":{"id":75,"state":"done","priority":"P2","title":"done while its owner still works"}}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null; { wait $MOCK; } 2>/dev/null || true; rm -rf "$TDIR"' EXIT
wait_for_port "$PORT" || { echo "FAIL mock server never listened on $PORT"; exit 1; }

r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$PORT" > "$r/.doperpowers/board.json"

# ---- the registry -----------------------------------------------------------
DH="$TDIR/registry"; mkdir -p "$DH"
DS="$TDIR/sminos-stub"; mkdir -p "$DS"
RETIRES="$TDIR/retires.log"; : > "$RETIRES"
TESTHOME="$TDIR/home"; mkdir -p "$TESTHOME/.claude/projects"

meta() { printf '%s\n' "$2" > "$DH/$1.json"; chmod 600 "$DH/$1.json"; }
# The owner of #72: its turn is over, the QA agent it dispatched wrote `done`.
meta u-done '{"uuid":"u-done","current":"u-done","status":"idle","run_id":53,"fence":1,
              "lane":"architect","bind_confirmed":true,"ticket":"72","run_bearer":"tok-53"}'
# #73 was closed wontfix under an idle worker.
meta u-wont '{"uuid":"u-wont","current":"u-wont","status":"idle","run_id":54,"fence":1,
              "lane":"implementer","bind_confirmed":true,"ticket":"73","run_bearer":"tok-54"}'
# #74's run was reclaimed: the ticket is still open and the resume path owns it.
meta u-reclaim '{"uuid":"u-reclaim","current":"u-reclaim","status":"idle","run_id":55,"fence":1,
                 "lane":"implementer","bind_confirmed":true,"ticket":"74","run_bearer":"tok-55"}'
# #75 is done, but its owner is still mid-turn (verifying the merge, cleaning up).
meta u-busy '{"uuid":"u-busy","current":"u-busy","status":"working","run_id":56,"fence":1,
              "lane":"architect","bind_confirmed":true,"ticket":"75","run_bearer":"tok-56"}'

# The sminos stub: `sync` answers from the record the way the real verb does
# (`live` for a running turn, `noop` for a record it will not reconcile), and
# `retire` records the seat and writes status=retired, as the real verb does.
cat > "$DS/sminos" <<STUB
#!/usr/bin/env bash
verb="\${1:-}"; shift || true
case "\$verb" in
migrate) exit 0 ;;
sync)
  python3 - "$DH/\$1.json" <<'PY'
import json, sys
try:
    m = json.load(open(sys.argv[1]))
except Exception:
    print("absent"); raise SystemExit(0)
print("live" if m.get("status") in ("working", "blocked") else "noop")
PY
  ;;
retire)
  echo "RETIRE \$1" >> "$RETIRES"
  python3 - "$DH/\$1.json" <<'PY'
import json, sys
p = sys.argv[1]
m = json.load(open(p)); m["status"] = "retired"
json.dump(m, open(p, "w"))
PY
  ;;
*) echo "stub sminos: unexpected verb '\$verb'" >&2; exit 2 ;;
esac
STUB
chmod +x "$DS/sminos"

SW() {  # SW <phase> — one _sweep_api.sh invocation against this fixture world
  ( cd "$r" && env HOME="$TESTHOME" DAEMON_HOME="$DH" SMINOS_CLI="$DS/sminos" \
      BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/_sweep_api.sh" "$@" )
}

# =========================================================================
# Tick 1 — the renew phase finds every run ended
# =========================================================================
OUT1="$TDIR/tick1.out"
SW renew > "$OUT1" 2>&1 || true

t  "run ended and ticket done → retire called"      "RETIRE u-done"    cat "$RETIRES"
t  "run ended and ticket wontfix → retire called"   "RETIRE u-wont"    cat "$RETIRES"
nt "run ended, ticket in-progress (reclaim) → not retired" "u-reclaim" cat "$RETIRES"
nt "ticket done but seat working → not retired this tick"  "u-busy"    cat "$RETIRES"
t  "the retirement is logged with ticket, run and seat" \
   "run 53: #72 is done — seat u-done retired" cat "$OUT1"
t  "a wontfix retirement names its state too" \
   "run 54: #73 is wontfix — seat u-wont retired" cat "$OUT1"
# The reclaimed seat is exactly what the resume path reads: its lane and ticket
# must survive this step untouched.
seat() { python3 -c 'import json, sys
m = json.load(open(sys.argv[1]))
print("status=%s ticket=%s lane=%s" % (m.get("status"), m.get("ticket"), m.get("lane")))' "$DH/$1.json"; }
t  "the reclaimed seat keeps its ticket and lane for the resume path" \
   "status=idle ticket=74 lane=implementer" seat u-reclaim

# =========================================================================
# Tick 2 — the busy owner's turn has ended; no run is left to end
# =========================================================================
python3 - "$DH/u-busy.json" <<'PY'
import json, sys
p = sys.argv[1]
m = json.load(open(p)); m["status"] = "idle"
json.dump(m, open(p, "w"))
PY
OUT2="$TDIR/tick2.out"
SW renew > "$OUT2" 2>&1 || true
t  "a later tick retires the seat once its turn is over" "RETIRE u-busy" cat "$RETIRES"
t  "and still names the run it ended on" \
   "run 56: #75 is done — seat u-busy retired" cat "$OUT2"
once() { grep -c "RETIRE u-done" "$RETIRES"; }
t  "a retired seat is not retired again" "1" once
nt "and the reclaimed seat is still left alone" "u-reclaim" cat "$RETIRES"

finish
