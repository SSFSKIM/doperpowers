# shellcheck shell=bash
#
# Machines cut over to their endpoints, two or more to a suite, for the shell
# suites' two-machine compositions (#153 M3d). Sourced by a suite after it
# defines `as` (dir host: a machine's HOME, SMINOS_HOME and host name), T,
# SCRIPT_DIR and PIDS. Each machine is a real sminos home with its daemon,
# cut over as an endpoint's welcome leaves a machine (daemon/identity.json),
# never enrolled at a hub and holding no hub.json, its endpoint
# endpoint_standin.py. Between two machines, `rl10_relay` is one pass of the
# hand-off (endpoint_standin's `hand`): what one stand-in accepted reaches the
# other's live connection as arrivals, through the stand-in's own echo, never
# a frame written by hand. In production MAWS's relay carries them.
#
#   rl10_as <dir> <host>     the machine in $T/<dir>, as `as` names it, with
#                            its MAWS_USER_DATA; EP its endpoint's directory
#   rl10_cut_over            this machine cut over as $DAEMON_HOST of org-1
#   rl10_serve [<fields>]    its stand-in up, with that identity; a person's
#                            words delivered on its `words` verdict; <fields>
#                            more of its config, a JSON object's members (one
#                            named again, identity, overrides: the last wins)
#   rl10_directory <body> <ep-dir>...  the org's directory (an `org` frame's
#                            body) the stand-ins hold, sent down each live
#                            connection
#   rl10_relay <ep-dir>...   one hand-off pass each way between every two; a
#                            failure other than a connection gone says why on
#                            stderr and returns non-zero
#   rl10_q <ep-dir> <expr>   a Python expression over a stand-in's state, as
#                            JSON: d the state, F its frames [(connection,
#                            frame)], up(pid) the events uploaded in a project
#                            [(connection, event)]
#   rl10_up <ep-dir> <pid> <text>   the first event uploaded in the project
#                            carrying the text, as a JSON line (empty: none)
#   rl10_mp <host>           a machine's machine project id in org-1

RL10_ENROLLED=2026-11-05T00:00:00.000Z

rl10_as() {
  as "$1" "$2"
  export MAWS_USER_DATA="$T/$1/maws"
  EP="$MAWS_USER_DATA/mawsd/endpoint"
}

rl10_identity() { # host → the identity the endpoint enrolled it under
  printf '{"org": "org-1", "hub": "http://127.0.0.1:9", "name": "%s", "former": [], "ref": "ref-%s", "enrolled": "%s"}' \
    "$1" "$1" "$RL10_ENROLLED"
}

rl10_cut_over() {
  mkdir -p "$SMINOS_HOME/daemon"
  chmod 700 "$SMINOS_HOME" "$SMINOS_HOME/daemon"
  python3 - "$SMINOS_HOME/daemon/identity.json" "$(rl10_identity "$DAEMON_HOST")" <<'PY'
import json, os, sys
with open(sys.argv[1], "w") as f:
    json.dump({**json.loads(sys.argv[2]), "former": {}, "cutover": "2026-11-05T00:00:01.000Z", "build": "b"}, f)
os.chmod(sys.argv[1], 0o600)
PY
}

rl10_serve() {
  python3 "$SCRIPT_DIR/endpoint_standin.py" serve "$EP" \
    "{\"identity\": $(rl10_identity "$DAEMON_HOST"), \"verdict\": \"words\", \"ask_legacy\": false${1:+, $1}}" &
  PIDS+=("$!")
  local end=$((SECONDS + 30))
  until [ -S "$EP/ctl.sock" ]; do
    [ "$SECONDS" -ge "$end" ] && { echo "  the endpoint stand-in at $EP did not come up"; return 1; }
    sleep 0.05
  done
}

rl10_directory() {
  local body=$1 d
  shift
  for d in "$@"; do
    python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$d" set "{\"org\": $body}" >/dev/null
    python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$d" send "{\"frames\": [{\"t\": \"org\", ${body#\{}]}" >/dev/null 2>&1 || true
  done
}

rl10_relay() { python3 "$SCRIPT_DIR/endpoint_standin.py" relay "$@" >/dev/null; }

rl10_q() {
  python3 -B -c 'import json, sys
sys.path.insert(0, sys.argv[1])
import endpoint_standin
d = json.loads(endpoint_standin.ctl_call(sys.argv[2], "state", {}))
F = [(r["conn"], r["frame"]) for r in d["received"]]
def up(pid):
    return [(c, e) for c, f in F if f.get("t") == "events" and f.get("project") == pid for e in f.get("events", [])]
print(json.dumps(eval(sys.argv[3])))' "$SCRIPT_DIR" "$1" "$2"
}

rl10_up() {
  python3 -B -c 'import json, sys
sys.path.insert(0, sys.argv[1])
import endpoint_standin
d = json.loads(endpoint_standin.ctl_call(sys.argv[2], "state", {}))
for r in d["received"]:
    f = r["frame"]
    if f.get("t") == "events" and f.get("project") == sys.argv[3]:
        for e in f.get("events", []):
            if sys.argv[4] in json.dumps(e, ensure_ascii=False):
                print(json.dumps(e, ensure_ascii=False))
                sys.exit(0)' "$SCRIPT_DIR" "$1" "$2" "$3"
}

rl10_mp() { python3 -c 'import sys, uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, "smns-machine:org-1:" + sys.argv[1].lower()))' "$1"; }
