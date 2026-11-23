#!/usr/bin/env python3
"""One machine's uplink over a store that knows no channel, driven tick by
tick in one process with no socket (CH2's M6: B11 on the wire): wire_scene.py
<scripts> <home>. Two sessions of one project exchange a tagged message, a
person speaks to each, the endpoint's word is given (`peer` on the person's
words, then `deliver` on every reach), and one person's message goes
unanswered past its deadline; it prints, as JSON, every frame the uplink
queued and what each inbox received. test_channels_wire.py's WireSameAsBase
runs it with this tree's scripts and with the merge base's and compares the
two, but for ids, times and paths. Hermetic: everything under <home>; the
sessions are `sleep`s, their inboxes inbox_standin.py.
"""
import json
import os
import subprocess
import sys
import time
from unittest import mock

SCRIPTS, HOME = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.realpath(__file__))
ORG, MACHINE, APP = "org-1", "alpha", "7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d"
ANN = "6c000b01-0000-4000-8000-0000000000b1"
BEE = "6c000b02-0000-4000-8000-0000000000b2"
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CONFIG_DIR", "WAKE_ENGINE_STATE",
            "MAWS_LANE", "SMNS_MEMBER", "SMINOS_LAUNCH", "MAWS_LAUNCHED_BY"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(HOME, "h"), SMINOS_HOME=os.path.join(HOME, "s"), DAEMON_HOST=MACHINE,
                  DAEMON_BOOT_ID="boot-current", SMINOS_DERIVE_EVERY="0",
                  PATH=os.path.join(HOME, "bin") + os.pathsep + os.environ["PATH"])
for d in (os.path.join(os.environ["HOME"], ".claude", "sessions"), os.path.join(os.environ["SMINOS_HOME"], "daemon"),
          os.path.join(HOME, "bin")):
    os.makedirs(d, mode=0o700, exist_ok=True)
with open(os.path.join(HOME, "bin", "claude"), "w") as f:
    f.write('#!/bin/sh\ncase "$1" in agents) echo "[]" ;; esac\nexit 0\n')
os.chmod(os.path.join(HOME, "bin", "claude"), 0o755)
sys.path.insert(0, SCRIPTS)

import sminos  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

CRED = {"org": ORG, "hub": "http://127.0.0.1:9", "machine": MACHINE, "key": None}
sminos.write_json(rl10.identity_path(), {"org": ORG, "hub": CRED["hub"], "name": MACHINE, "former": {},
                                         "ref": "machine-ref-1", "enrolled": "2026-11-10T00:00:00.000Z",
                                         "cutover": "2026-11-10T00:00:01.000Z", "build": "b"}, mode=0o600)
sminos.forget_caches()
uplink.keep_org({"projects": [{"id": APP, "name": "app", "kind": "hub", "retired": False}],
                 "machines": [{"name": MACHINE, "online": False}], "complete": True}, CRED)
root = os.path.join(HOME, "app")
os.makedirs(root)
with open(os.path.join(root, ".smns"), "w") as f:
    json.dump({"project": APP, "name": "app", "hub": {"org": ORG}}, f)
procs = []
try:
    for sid, name in ((ANN, "ann"), (BEE, "bee")):
        sock = os.path.join(HOME, "%s.sock" % name)
        open(sock + ".received", "a").close()
        procs.append(subprocess.Popen([sys.executable, "-B", os.path.join(HERE, "inbox_standin.py"), sock,
                                       sock + ".received"]))
        proc = subprocess.Popen(["sleep", "600"])
        procs.append(proc)
        with open(os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % proc.pid), "w") as f:
            json.dump({"pid": proc.pid, "sessionId": sid, "cwd": root, "kind": "interactive", "name": name,
                       "nameSource": "user", "status": "idle", "messagingSocketPath": sock}, f)
        for _ in range(600):
            if os.path.exists(sock):
                break
            time.sleep(0.01)
    sminos.forget_caches()
    sminos.view_of(sminos.resolve_project(root))

    class Lane:
        def __init__(self):
            self.sent = []

        def send(self, frames, then=None):
            self.sent.extend(frames)
            if then:
                then()

        def posting(self):
            return False

        def queued(self):
            return 0

        def close(self):
            pass

    link = uplink.Link(CRED, {}, transport=mock.Mock(number=1))
    link.generation = 1
    link.log_lane = link.session_lane = Lane()
    link.reach = True

    def tick():
        sminos.forget_caches()
        link.next_scan = link.next_upload = link.next_words = link.next_member_read = 0.0
        link.words_due = True
        link.tick()

    def say(sid, *argv):
        env = dict(os.environ, **({"CLAUDE_CODE_SESSION_ID": sid} if sid else {}))
        got = subprocess.run([os.path.join(SCRIPTS, "sminos"), "say", *argv], cwd=root, env=env,
                             capture_output=True, text=True, timeout=120)
        return [got.returncode, got.stdout + got.stderr]

    def answer(t, verdict):
        for f in [f for f in link.session_lane.sent if f.get("t") == t + "?" and f["id"] in link.asks]:
            sminos.forget_caches()
            link.dispatch({"t": t, "id": f["id"], "verdict": verdict}, None)

    out = {"said": []}
    tick()
    link.dispatch({"t": "have", "project": APP, "have": {}}, None)   # the upstream holds nothing yet: all goes up
    out["said"].append(say(ANN, "@bee hello bee"))
    out["said"].append(say("", "@ann from the person"))
    tick()
    tick()
    answer("words", "peer")
    tick()
    answer("reach", "deliver")
    tick()
    out["said"].append(say("", "@bee never answered"))
    tick()
    real = time.monotonic
    with mock.patch.object(uplink.time, "monotonic", lambda: real() + uplink.WORDS_WAIT + uplink.REACH_WAIT + 1):
        link.ask_words(link.member_known)
    out["frames"] = link.session_lane.sent
    out["inboxes"] = {}
    for name in ("ann", "bee"):
        with open(os.path.join(HOME, "%s.sock.received" % name)) as f:
            out["inboxes"][name] = [json.loads(line)["message"]["content"] for line in f if line.strip()]
    print(json.dumps(out, sort_keys=True, ensure_ascii=False))
finally:
    for p in procs:
        p.kill()
        p.wait()
