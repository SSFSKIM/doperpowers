#!/usr/bin/env python3
"""Live check of the desk's Resume (DC7 M4), against the engine itself.

What only a running engine shows, pinned so a release that breaks it fails
loudly:
- a terminal session that ended comes back through `sminos_rpc.resume` as
  a `--bg` job under its own id, `claude --bg --resume <session>` with
  nothing else on the line: the job's session is the same id, its process
  holds it (the engine's session record, kind `bg`), and the transcript is
  the same file;
- a Resume while that job runs is refused `session-live`, launching nothing;
- a Resume racing the owner reopening the session in a terminal (the
  reopen lands between the daemon's check and the launch: here the check is
  passed over on purpose) ends with the engine starting a copy, which is
  stopped, the RPC failed `copy-started`, and the owner's terminal the one
  process holding the id.

It spends one model call (haiku, a one-word reply), so no suite runs it:
run it by hand with the model gateway's keys in the environment. Isolation
is live-control-check.py's (whose class it extends): a temporary HOME whose
.claude is the config dir, so the `--bg` supervisor it starts is that
config's, never the owner's; a temporary SMINOS_HOME; a tmux server of its
own; the gateway keys in a 0600 env file removed at the end; every job and
that supervisor stopped before it exits.

    tests/mods/live-resume-check.py [--keep]
"""

import glob
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_control_check", os.path.join(HERE, "live-control-check.py"))
LC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LC)
LB = LC.LB
wait_for = LC.wait_for
SCRIPTS = os.path.join(LB.REPO, "skills", "sminos", "scripts")
NAME = "rslive"

# The daemon's Resume, as the uplink's worker runs it, in this check's
# isolation; `--skip-check` passes over the "live nowhere" check once, as a
# reopen landing just after it would.
RESUME = r'''
import json, sys, threading
sys.path.insert(0, sys.argv[1])
import sminos_rpc as r
if sys.argv[3] == "--skip-check":
    real, calls = r.holders, []
    def once(sid):
        calls.append(sid)
        return [] if len(calls) == 1 else real(sid)
    r.holders = once
try:
    out = r.resume(sys.argv[2], sys.argv[4], threading.Lock())
except r.Refused as e:
    out = e.outcome
print(json.dumps(out))
'''

# The gateway's model discovery is not part of what this check pins.
os.environ.setdefault("CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY", "")


class Resume(LC.Control):
    def records(self, sid):
        """The engine's records of live processes holding the session."""
        out = []
        for p in glob.glob(os.path.join(self.cfg, "sessions", "*.json")):
            try:
                with open(p) as f:
                    rec = json.load(f)
            except (OSError, ValueError):
                continue
            if rec.get("sessionId") == sid and LB._alive(rec.get("pid", 0)):
                out.append(rec)
        return out

    def resume(self, sid, skip=False):
        inner = "set -e; . %s; cd %s; exec python3 -c %s %s %s %s %s" % (
            shlex.quote(self.envfile), shlex.quote(self.work), shlex.quote(RESUME), shlex.quote(SCRIPTS),
            shlex.quote(sid), "--skip-check" if skip else "--check", shlex.quote(self.work))
        r = subprocess.run(["env", "-i", "/bin/bash", "--noprofile", "--norc", "-c", inner],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError("the resume did not run: %s" % r.stderr.strip()[-2000:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def agents(self):
        r = self.claude(["agents", "--json", "--all"], timeout=120)
        try:
            return json.loads(r.stdout or "[]")
        except ValueError:
            return []

    def terminal(self, window, args):
        inner = "set -e; . %s; cd %s; exec claude %s" % (shlex.quote(self.envfile), shlex.quote(self.work),
                                                          " ".join(shlex.quote(a) for a in args))
        cmd = "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)
        # A session of its own: the first one's end may have taken the server with it.
        subprocess.run(self.tmux + ["new-session", "-d", "-s", window, "-x", "200", "-y", "50", cmd], check=True)

    def run(self):
        self.setup()
        self.terminal("brl", ["--model", "haiku", "--permission-mode", "default", "-n", NAME])
        rec = wait_for("the terminal session's record", 120, lambda: self.record(NAME))
        sid, pid = rec["sessionId"], rec["pid"]
        wait_for("the prompt", 60, lambda: ">" in self.pane() or "❯" in self.pane())
        self.prompt("Reply with exactly the word READY.")
        rows = wait_for("its answer on disk", 240, lambda: [r for r in self.transcript_rows(sid)
                                                            if r.get("type") == "assistant"])
        transcript = glob.glob(os.path.join(self.cfg, "projects", "*", sid + ".jsonl"))
        self.keys("C-c")
        time.sleep(0.5)
        self.keys("C-c")
        wait_for("the terminal session's end", 60, lambda: not LB._alive(pid))
        self.check("a terminal session ran and ended", rows and transcript and not self.records(sid),
                   "session %s, %d answer rows, transcript %s" % (sid[:8], len(rows), transcript))

        out = self.resume(sid)
        held = self.records(sid)
        rows = [r for r in self.agents() if r.get("sessionId") == sid]
        self.jobs += [r.get("id") for r in rows]
        same_file = glob.glob(os.path.join(self.cfg, "projects", "*", sid + ".jsonl")) == transcript
        self.check("Resume brings it back as a --bg job under its own id",
                   out == {"state": "done", "result": {"session": sid}} and [h.get("kind") for h in held] == ["bg"]
                   and rows and same_file,
                   "outcome %s; holders %s; job rows %s; same transcript %s" % (
                       out, [(h.get("kind"), h.get("jobId")) for h in held],
                       [(r.get("id"), r.get("state")) for r in rows], same_file))

        before = len(self.agents())
        out = self.resume(sid)
        self.check("a Resume while it runs is refused session-live, launching nothing",
                   out["state"] == "failed" and out["error"]["code"] == "session-live" and len(self.agents()) == before,
                   "outcome %s" % out)

        for short in [r.get("id") for r in rows]:
            self.claude(["stop", short], timeout=120)
        wait_for("the job's end", 120, lambda: not self.records(sid))
        self.terminal("owner", ["--resume", sid])
        owner = wait_for("the owner's terminal holding it", 120, lambda: self.records(sid))
        out = self.resume(sid, skip=True)
        time.sleep(2)
        held = self.records(sid)
        copies = [r for r in self.agents() if r.get("sessionId") not in (sid, None)]
        self.jobs += [r.get("id") for r in copies]
        self.check("a Resume racing the owner's reopen stops the engine's copy and fails copy-started",
                   out["state"] == "failed" and out["error"]["code"] == "copy-started"
                   and [h.get("pid") for h in held] == [owner[0].get("pid")]
                   and all(not self.records(r.get("sessionId")) for r in copies),
                   "outcome %s; holders %s; copies %s" % (
                       out, [(h.get("kind"), h.get("pid")) for h in held],
                       [(r.get("id"), r.get("state"), bool(self.records(r.get("sessionId")))) for r in copies]))


def main():
    live = Resume("--keep" in sys.argv[1:])
    print("live resume check (%s):" % live.root, flush=True)
    try:
        live.run()
    except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
        live.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
        print("  pane at the failure:\n" + "\n".join("    " + line for line in live.pane().rstrip().splitlines()[-25:]))
    finally:
        live.cleanup()
    failed = [r for r in live.results if not r[1]]
    print("%s: %d of %d checks passed" % ("FAILED" if failed else "passed", len(live.results) - len(failed),
                                         len(live.results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
