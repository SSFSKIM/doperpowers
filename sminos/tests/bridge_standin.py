#!/usr/bin/env python3
"""A live session's bridge as sminos_fork meets it: the real child (`sminos
bridge --session <id>`) with this process as its mod, answering `btw` as
bridge-btw.tsx does and `ask` as bridge-ask.tsx does — the op answered at
once (`started`, or a refusal with its code), then its start and its end on
the stream, the end carrying the answer and its usage, or the reason there is
none. Its capabilities list the ops it is given, so `bridge_offers` reads them
as a loaded module's.

How each op is answered, `btw` and `ask` alike:
    {"text": "...", "usage": {...}}   an answer (usage defaults to USAGE)
    {"refuse": ["code", "why"]}       refused at the op
    {"end": {"reason": "...", ...}}   started, then ended with no answer
    {"silent": true}                  started, never ended
    {"reload": true, ...}             the child replaced before the end is posted (to the new child)

As a module: StandIn(cli, session, ops=[...], btw={...}, ask={...}); its
`commands` are the ops it received. As a script, it runs until SIGTERM:

    bridge_standin.py <sminos CLI> <session> '<{"ops": [...], "btw": {...}, "ask": {...}}>' <ready file> <log file>

writing the ready file once the child serves its first snapshot, and each op
it receives to the log file as a JSON line.
"""

import http.client
import json
import signal
import socket
import subprocess
import sys
import threading

USAGE = {"input": 156, "output": 40, "cacheRead": 120027, "cacheWrite": 0}
NONCE_HEADER = "X-Bridge-Nonce"   # sminos_bridge.NONCE_HEADER


class _Unix(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("bridge", timeout=10)
        self._path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


class StandIn:
    def __init__(self, cli, session, ops=("btw", "ask"), btw=None, ask=None, log=None):
        self.session, self.ops, self.log = session, list(ops), log
        self.answers = {"btw": btw or {"text": "Keeps the stand-in's tool working."},
                        "ask": ask or {"text": "Nothing blocking."}}
        self.cli, self.commands = cli, []
        self.start_child()

    def start_child(self):
        """A child for the session, this process its mod: its hello read, then the session's start and the
        mod's state (with the capabilities) posted, as a module that loads does."""
        self.proc = subprocess.Popen([str(self.cli), "bridge", "--session", self.session], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True)
        hello = json.loads(self.proc.stdout.readline())
        assert hello.get("op") == "hello", hello
        self.child = (hello["socket"], hello["nonce"])   # one value: a post never pairs one child's socket with another's nonce
        threading.Thread(target=self.drain, args=(self.proc,), daemon=True).start()
        caps = {"sminos": "test", "protocol": 2, "engine": "test", "ops": self.ops, "reads": [], "routes": {},
                "controls": {op: {"available": True} for op in self.ops}}
        self.post({"type": "session", "phase": "start", "session": self.session, "cwd": "/", "t": 0},
                  {"type": "resync", "turns": [], "streaming": [], "agents": [], "cut": hello.get("seed") or {},
                   "capabilities": caps, "t": 0})

    def post(self, *events):
        sock, nonce = self.child
        c = _Unix(sock)
        try:
            c.request("POST", "/events", body=json.dumps(list(events)).encode(),
                      headers={"content-type": "application/json", NONCE_HEADER: nonce})
            status = c.getresponse().status
        finally:
            c.close()
        assert status == 204, status

    def drain(self, proc):
        with proc.stdout:
            for line in proc.stdout:
                cmd = json.loads(line)
                self.commands.append(cmd)
                if self.log:
                    with open(self.log, "a") as f:
                        f.write(json.dumps(cmd) + "\n")
                threading.Thread(target=self.answer, args=(cmd,), daemon=True).start()

    def answer(self, cmd):
        op, oid = cmd.get("op"), cmd.get("id")
        how = self.answers.get(op) if op in self.ops else None
        if how is None:
            self.post({"type": "result", "id": oid, "op": op, "ok": False, "error": "unknown op: %s" % op})
            return
        if "refuse" in how:
            code, why = how["refuse"]
            self.post({"type": "result", "id": oid, "op": op, "ok": False, "error": why, "code": code})
            return
        started = {"started": True, "id": oid, **({"agentId": "a-standin"} if op == "ask" else {})}
        self.post({"type": "result", "id": oid, "op": op, "ok": True, "result": started})
        self.post({"type": op, "phase": "start", "id": oid, "t": 0})
        if how.get("silent"):
            return
        if "end" in how:
            end = dict(how["end"])
        else:
            end = {"text": how["text"], "usage": how.get("usage", USAGE),
                   **({"truncated": True} if how.get("truncated") else {})}
        if how.get("reload"):
            # A reload of the module mid-op: the child is replaced, and the module after it posts the end to the
            # new child before any subscriber is back on its stream.
            self.stop()
            self.start_child()
        self.post({"type": op, "phase": "end", "id": oid, **end, "t": 0})

    def stop(self):
        self.proc.terminate()
        self.proc.wait(10)


def main(argv):
    cli, session, config, ready, log = argv[1:6]
    c = json.loads(config)
    standin = StandIn(cli, session, ops=c.get("ops", ["btw", "ask"]), btw=c.get("btw"), ask=c.get("ask"), log=log)

    def stop(_signum, _frame):
        standin.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    open(ready, "w").close()
    signal.pause()


if __name__ == "__main__":
    main(sys.argv)
