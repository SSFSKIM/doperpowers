#!/usr/bin/env python3
"""Live check of the desk's Resume (DC7 M4), against the engine itself.

What only a running engine shows, pinned so a release that breaks it fails
loudly. A terminal session runs one turn, joins its project, and ends; then:
- delivery after Resume: an event from outside this machine owed to the
  ended session (a peer's say from another machine, the owner's message from
  the desk) is reported `recorded` by the daemon's tick, once; when Resume
  brings the session back, the next ticks deliver it, its outcome turning
  `delivered` for the same key, and its words reach the session;
- Resume brings the session back as a `--bg` job under its own id, `claude
  --bg --resume <session>` with nothing else on the line: the job's session
  is the same id, its process holds it (the engine's session record, kind
  `bg`, carrying `startedAt`), the transcript is the same file, and the
  launch and job the ledger kept are that process's;
- a Resume while that job runs is refused `session-live`, launching nothing;
- two Resumes at once, as the daemon runs them (a worker each, one lock per
  session), start one session: one `done`, the other `session-live`; and
  two `claude --bg --resume` launches at once from two processes (a stopped
  daemon's orphaned launch meeting the next daemon's) leave one process
  holding the session;
- claim reconciliation, a daemon stopping mid-Resume and the next one
  reading its ledger: a claim whose job was kept is `done` from that job's
  process, one stopped before its job was kept is `done` from the --bg
  process its launch started, and a process holding the session that started
  before a claim's launch is no evidence for it, its job id the same or none:
  not done, then `interrupted` once the window passes;
- a Resume racing the owner reopening the session in a terminal (the reopen
  lands between the daemon's check and the launch: here the check is passed
  over on purpose) ends with the engine starting a copy, which is stopped,
  the RPC failed `copy-started`, and the owner's terminal the one process
  holding the id;
- the seat cases: a seat `sminos spawn` started, stopped, resumes under its
  own id and reads as running; retired, its session is refused
  `unsupported`, nothing launched.

The RPCs run as the daemon runs them (RESUME): sealed under a key, received
with their code, checked, claimed in the ledger, executed on workers. Its
reads of the log, the outcomes and the seats are SMINOS. test_rpcs.py runs
both against the `claude` stand-in, so a change to their call paths is caught
without an engine run.

It spends a few model calls (haiku, one-word replies: the terminal's turn,
the two deliveries, the seat's first turn), so no suite runs it: run it by
hand with the model gateway's keys in the environment. Isolation is
live-control-check.py's (whose class it extends): a temporary HOME whose
.claude is the config dir, so the `--bg` supervisor it starts is that
config's, never the owner's; a temporary SMINOS_HOME; a tmux server of its
own; the gateway keys in a 0600 env file removed at the end; every job and
that supervisor stopped before it exits. The project names a hub (an org,
as a desk project's .smns does) so delivery keeps its outcomes; no hub is
reached, since the machine is enrolled at none.

    sminos/tests/mods/live-resume-check.py [--keep]
"""

import base64
import calendar
import glob
import importlib.util
import json
import os
import re
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
SCRIPTS = os.path.join(LB.PLUGIN_ROOT, "skills", "sminos", "scripts")
NAME = "rslive"
SEAT = "rsseat"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# The daemon's side of a Resume, in this check's isolation: argv is the
# scripts' directory, a mode, the project's directory, then the mode's own.
# Every mode but the restarts sends one Resume per session named, sealed under
# a key of its own and received as the uplink receives an `rpc` frame (two of
# one session are two at once: two workers, one lock), and prints the nonces,
# then each one's ledger entry once answered. `skip-check` passes over the
# check that no process holds the session until the launch, as a reopen
# landing just after it would. `die-after-job` and `die-before-job` stop the
# process as a daemon stopping mid-Resume would, once its launch's job is
# kept, or once the launch returned and before its job is kept: only the
# nonces are printed. `restart [seconds] <nonce>...` is the next daemon: it
# reconciles the ledger's claims and prints the nonces' entries once answered
# or when `seconds` pass; `restart-past-window` the same with its clock a
# trace's window ahead.
RESUME = r'''
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
import sminos, sminos_codes as codes, sminos_policy as policy, sminos_rpc as r

mode, cwd, rest = sys.argv[2], sys.argv[3], sys.argv[4:]
project = sminos.resolve_project(cwd)
machine = sminos.host_name()


class Here:
    """What the uplink knows of this machine, as the RPCs' checks ask it."""

    def project(self, pid):
        return project if pid == project.id else None

    def has_session(self, _project, _sid):
        return True

    def record(self, sid):
        live = r.holders(sid)
        return live[0] if live else None

    def checkouts(self, p):
        return policy.known_checkouts(p)

    def cwd(self, p, sid):
        sminos.forget_caches()
        return ((sminos.view_of(p, titles=False).info.get(sid) or {}).get("joined") or {}).get("cwd") or ""


def entries(rp, nonces, seconds):
    """Each nonce's ledger entry once every one is answered and no worker
    holds it, or as they stand when `seconds` pass."""
    deadline = time.time() + seconds
    while True:
        rp.next_reconcile = 0.0
        rp.due({project.id})
        got = [rp.ledger.get(n) for n in nonces]
        if time.time() >= deadline or (all(e and "outcome" in e for e in got) and not rp.flight & set(nonces)):
            return got
        time.sleep(0.2)


if mode in ("restart", "restart-past-window"):
    ahead = r.RESUME_TRACE_S + 1 if mode == "restart-past-window" else 0
    rp = r.Rpcs(os.urandom(32), machine, clock=lambda: time.time() + ahead)
    print(json.dumps(entries(rp, rest[1:], float(rest[0]))))
    sys.exit(0)

key = os.urandom(32)
rp = r.Rpcs(key, machine)
if mode == "skip-check":
    holders, launch, launched = r.holders, r.launch_resume, []
    r.holders = lambda sid: holders(sid) if launched else []

    def launch_once(sid, at):
        launched.append(sid)
        return launch(sid, at)
    r.launch_resume = launch_once
elif mode in ("die-after-job", "die-before-job"):
    note = rp.note

    def note_then_stop(nonce, fields):
        if "job" in fields and mode == "die-before-job":
            os._exit(0)
        note(nonce, fields)
        if "job" in fields:
            os._exit(0)
    rp.note = note_then_stop
sent = []
for sid in rest:
    draft = {"rpc": "resume", "project": project.id, "machine": machine, "member": "4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c",
             "created": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
             "nonce": codes.b64url(os.urandom(16)), "args": {"session": sid}}
    sent.append(codes.seal(key, "rpc", project.id, draft, None))
print(json.dumps([x["nonce"] for x in sent]), flush=True)
for x in sent:
    rp.receive(x, Here())
print(json.dumps(entries(rp, [x["nonce"] for x in sent], 600)))
'''

# What the check reads and writes of sminos, in its isolation: argv is the
# scripts' directory, an op, the project's directory, a session. `send <a>
# <b>` appends to the log, from outside this machine, a peer's say (another
# machine's writer) with text a and the owner's message from the desk (the
# hub's writer) with text b, each addressed to the session; prints their
# keys. `outcomes` prints the delivery outcomes kept for the session, in
# order. `seat` prints the seat whose current session it is ({alias, status,
# state}), or null. `latest` prints the session's last membership event.
SMINOS = r'''
import json, sys, uuid
sys.path.insert(0, sys.argv[1])
import sminos, sminos_outcomes as outcomes

op, cwd, sid = sys.argv[2], sys.argv[3], sys.argv[4]
project = sminos.resolve_project(cwd)
if op == "send":
    member = "4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c"
    joined = (sminos.view_of(project, titles=False).info.get(sid) or {}).get("joined") or {}
    to = [{"session": sid, "alias": joined.get("alias") or sid[:8]}]
    sent = [sminos.log_append(project, "otherhost/" + str(uuid.uuid4()), "say", to=to, text=sys.argv[5],
                              **{"from": "far"}),
            sminos.log_append(project, "hub/" + member, "human", to=to, text=sys.argv[6], member=member,
                              **{"from": "human"})]
    print(json.dumps([[e["writer"], e["seq"]] for e in sent]))
elif op == "outcomes":
    print(json.dumps([o for o in outcomes.Outbox(project).read() if o.get("session") == sid]))
elif op == "seat":
    seat = next((s for s in sminos.seats() if s["current"] == sid), None)
    print(json.dumps(seat and {"alias": seat["alias"], "status": seat["status"], "state": sminos.state(seat)}))
elif op == "latest":
    latest = (sminos.view_of(project, titles=False).info.get(sid) or {}).get("latest") or {}
    print(json.dumps({k: latest.get(k) for k in ("kind", "reason")}))
'''


def process_started(rec):
    """When an engine record's process started (epoch s): `startedAt` (ms),
    else `procStart` read as UTC, as sminos reads it; None when neither."""
    if isinstance(rec.get("startedAt"), (int, float)):
        return rec["startedAt"] / 1000.0
    try:
        return calendar.timegm(time.strptime(" ".join(str(rec.get("procStart")).split()), "%a %b %d %H:%M:%S %Y"))
    except ValueError:
        return None


def done(sid):
    return {"state": "done", "result": {"session": sid}}


def code_of(e):
    """An entry's outcome as (state, error code), or None while it is a claim."""
    o = (e or {}).get("outcome")
    return (o["state"], (o.get("error") or {}).get("code")) if o else None


def banner(text):
    """A launch's output, its telling lines: the job it backgrounded, a note
    or an error."""
    lines = [line.strip() for line in ANSI.sub("", text or "").splitlines() if line.strip()]
    told = [line for line in lines if re.search(r"backgrounded|note:|already|Couldn't|rror|shutting", line)]
    return " / ".join(told or lines[-1:]) or "(no output)"


def last_line(text):
    lines = [line.strip() for line in ANSI.sub("", text or "").splitlines() if line.strip()]
    return lines[-1] if lines else "(no output)"


# The gateway's model discovery is not part of what this check pins.
os.environ.setdefault("CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY", "")


class Resume(LC.Control):
    # -- the machine, as the check reads it

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

    def holding(self, sid, launched=None):
        """The holders as the details say them: kind, job, and when each
        started against a launch (s)."""
        return [(h.get("kind"), h.get("jobId"), "startedAt" in h,
                 None if launched is None or process_started(h) is None else round(process_started(h) - launched, 2))
                for h in self.records(sid)]

    def agents(self):
        r = self.claude(["agents", "--json", "--all"], timeout=120)
        try:
            return json.loads(r.stdout or "[]")
        except ValueError:
            return []

    def texts(self, sid):
        return json.dumps(self.transcript_rows(sid))

    def ledger(self):
        try:
            with open(os.path.join(self.smh, "daemon", "rpcs.json")) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    # -- running things in the check's isolation

    def wrapped(self, argv, timeout=600):
        inner = "set -e; . %s; cd %s; exec %s" % (shlex.quote(self.envfile), shlex.quote(self.work),
                                                   " ".join(shlex.quote(a) for a in argv))
        return subprocess.run(["env", "-i", "/bin/bash", "--noprofile", "--norc", "-c", inner],
                              capture_output=True, text=True, timeout=timeout)

    def popen(self, argv):
        inner = "set -e; . %s; cd %s; exec %s" % (shlex.quote(self.envfile), shlex.quote(self.work),
                                                   " ".join(shlex.quote(a) for a in argv))
        return subprocess.Popen(["env", "-i", "/bin/bash", "--noprofile", "--norc", "-c", inner],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def daemon(self, mode, *args):
        """RESUME in `mode`: its printed lines, each parsed."""
        r = self.wrapped(["python3", "-c", RESUME, SCRIPTS, mode, self.work, *args])
        lines = [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
        if r.returncode != 0 or not lines:
            raise RuntimeError("the daemon's side (%s) did not run: %s" % (mode, r.stderr.strip()[-2000:]))
        return lines

    def resume(self, *sids, mode="resume"):
        """The ledger entries of Resumes of `sids` sent at once, once answered."""
        lines = self.daemon(mode, *sids)
        if len(lines) < 2:
            raise RuntimeError("the daemon's side (%s) printed no outcome" % mode)
        return [e or {} for e in lines[1]]

    def smn(self, op, sid, *args):
        r = self.wrapped(["python3", "-c", SMINOS, SCRIPTS, op, self.work, sid, *args], timeout=120)
        if r.returncode != 0:
            raise RuntimeError("sminos %s did not run: %s" % (op, r.stderr.strip()[-2000:]))
        return json.loads(r.stdout.strip().splitlines()[-1])

    def tick(self):
        """One tick of the daemon's duties, as `sminos daemon run` ticks."""
        r = self.wrapped([self.sminos(), "daemon", "tick"], timeout=300)
        if r.returncode != 0:
            raise RuntimeError("sminos daemon tick: %s" % (r.stdout + r.stderr).strip()[-2000:])
        return r.stdout.strip()

    def outcomes(self, sid, keys):
        """Each key's delivery outcomes for the session, in order: [(outcome, reason)]."""
        got = self.smn("outcomes", sid)
        return {tuple(k): [(o["outcome"], o.get("reason")) for o in got
                           if [o["event"]["writer"], o["event"]["seq"]] == list(k)] for k in keys}

    def claim(self, sid, launched, **extra):
        """A Resume's claim as a daemon that stopped after its launch leaves it."""
        nonce = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
        d = self.ledger()
        d[nonce] = {"project": self.pid, "rpc": "resume", "session": sid, "at": launched, "launched_at": launched,
                    **extra}
        os.makedirs(os.path.join(self.smh, "daemon"), mode=0o700, exist_ok=True)
        with open(os.path.join(self.smh, "daemon", "rpcs.json"), "w") as f:
            json.dump(d, f)
        return nonce

    def stop_jobs(self, sid):
        """Every --bg job holding the session stopped, its process gone, and a
        moment for the supervisor to let the job go: a launch under a handle
        it still holds is refused "still shutting down"."""
        for h in self.records(sid):
            if h.get("kind") == "bg" and h.get("jobId"):
                self.claude(["stop", h["jobId"]], timeout=120)
        wait_for("the session's jobs to end", 120, lambda: not self.records(sid))
        time.sleep(3)

    def terminal(self, window, args):
        inner = "set -e; . %s; cd %s; exec claude %s" % (shlex.quote(self.envfile), shlex.quote(self.work),
                                                          " ".join(shlex.quote(a) for a in args))
        cmd = "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)
        # A session of its own: the first one's end may have taken the server with it.
        subprocess.run(self.tmux + ["new-session", "-d", "-s", window, "-x", "200", "-y", "50", cmd], check=True)

    def hub_project(self):
        path = os.path.join(self.work, ".smns")
        with open(path) as f:
            d = json.load(f)
        d["hub"] = {"org": "org-live"}
        with open(path, "w") as f:
            json.dump(d, f, indent=2)
        self.pid = d["project"]

    # -- the checks

    def run(self):
        self.setup()
        self.hub_project()
        self.terminal("brl", ["--model", "haiku", "--permission-mode", "default", "-n", NAME])
        rec = wait_for("the terminal session's record", 120, lambda: self.record(NAME))
        sid, pid = rec["sessionId"], rec["pid"]
        wait_for("the prompt", 60, lambda: ">" in self.pane() or "❯" in self.pane())
        self.prompt("Reply with exactly the word READY.")
        rows = wait_for("its answer on disk", 240, lambda: [r for r in self.transcript_rows(sid)
                                                            if r.get("type") == "assistant"])
        transcript = glob.glob(os.path.join(self.cfg, "projects", "*", sid + ".jsonl"))
        self.tick()   # it joins its project, as a session the daemon finds running does
        self.keys("C-c")
        time.sleep(0.5)
        self.keys("C-c")
        wait_for("the terminal session's end", 60, lambda: not LB._alive(pid))
        self.tick()   # its membership ends with its process
        latest = self.smn("latest", sid)
        self.check("a terminal session ran, joined its project, and ended",
                   rows and transcript and not self.records(sid) and latest == {"kind": "retired", "reason": "ended"},
                   "session %s, %d answer rows, transcript %s, membership %s" % (sid[:8], len(rows), transcript, latest))

        keys = self.delivery_recorded(sid)
        self.resume_back(sid, transcript)
        self.delivered(sid, keys)
        self.refused_while_live(sid)
        self.two_at_once(sid)
        self.two_launches(sid)
        self.reconciliation(sid)
        self.copy_race(sid)
        self.seat_cases()

    def delivery_recorded(self, sid):
        self.fig, self.plum = "FIG%d" % os.getpid(), "PLUM%d" % os.getpid()
        keys = self.smn("send", sid, "Reply with exactly the word %s. Run no tools." % self.fig,
                        "Reply with exactly the word %s. Run no tools." % self.plum)
        self.tick()
        self.tick()
        got = self.outcomes(sid, keys)
        self.check("an event from outside owed to the ended session (a peer's say, the owner's message from the desk) "
                   "is reported recorded once, however many ticks",
                   all([o for o, _ in got[tuple(k)]] == ["recorded"] for k in keys), json.dumps(list(got.values())))
        return keys

    def resume_back(self, sid, transcript):
        e = self.resume(sid)[0]
        held = self.records(sid)
        rows = [r for r in self.agents() if r.get("sessionId") == sid]
        self.jobs += [r.get("id") for r in rows]
        same_file = glob.glob(os.path.join(self.cfg, "projects", "*", sid + ".jsonl")) == transcript
        self.check("Resume brings it back as a --bg job under its own id",
                   e.get("outcome") == done(sid) and [h.get("kind") for h in held] == ["bg"] and rows and same_file,
                   "outcome %s; holders %s; job rows %s; same transcript %s" % (
                       e.get("outcome"), [(h.get("kind"), h.get("jobId")) for h in held],
                       [(r.get("id"), r.get("state")) for r in rows], same_file))
        launched = e.get("launched_at")
        started = [process_started(h) for h in held]
        self.check("its launch and job are what the ledger kept, and the job's process is that launch's, its record "
                   "carrying startedAt",
                   isinstance(launched, (int, float)) and [h.get("jobId") for h in held] == [e.get("job")]
                   and [r.get("id") for r in rows] == [e.get("job")]
                   and all(isinstance(h.get("startedAt"), (int, float)) for h in held)
                   and all(t is not None and t >= int(launched) for t in started),
                   "kept launch %s, job %s (session %s); holders (kind, job, startedAt, started - launch) %s; job rows %s"
                   % (launched, e.get("job"), sid[:8], self.holding(sid, launched), [r.get("id") for r in rows]))

    def delivered(self, sid, keys):
        got = {}
        for _ in range(4):   # the daemon ticks at once when Resume asks, then every few seconds
            self.tick()
            got = self.outcomes(sid, keys)
            if all([o for o, _ in got[tuple(k)]][-1:] == ["delivered"] for k in keys):
                break
            time.sleep(3)
        try:
            wait_for("the delivered words in the session", 90, lambda: self.fig in self.texts(sid)
                     and self.plum in self.texts(sid))
            reached = True
        except TimeoutError:
            reached = False
        self.check("once Resume brings it back, the daemon delivers both, each outcome turning delivered for the "
                   "same key, and the words reach the session",
                   all([o for o, _ in got[tuple(k)]] == ["recorded", "delivered"] for k in keys) and reached,
                   "outcomes %s; in the transcript: %s %s, %s %s" % (
                       json.dumps(list(got.values())), self.fig, self.fig in self.texts(sid), self.plum,
                       self.plum in self.texts(sid)))

    def refused_while_live(self, sid):
        before = len(self.agents())
        e = self.resume(sid)[0]
        self.check("a Resume while it runs is refused session-live, launching nothing",
                   code_of(e) == ("failed", "session-live") and "launched_at" not in e and len(self.agents()) == before,
                   "outcome %s" % e.get("outcome"))

    def two_at_once(self, sid):
        self.stop_jobs(sid)
        got = self.resume(sid, sid)
        held = self.records(sid)
        self.jobs += [h.get("jobId") for h in held]
        launches = [e for e in got if "launched_at" in e]
        self.check("two Resumes at once, as the daemon runs them, start one session: one done, the other session-live",
                   sorted(map(str, map(code_of, got))) == [str(("done", None)), str(("failed", "session-live"))]
                   and len(launches) == 1 and [h.get("kind") for h in held] == ["bg"],
                   "outcomes %s; launches %d; holders %s" % ([e.get("outcome") for e in got], len(launches),
                                                            self.holding(sid)))

    def two_launches(self, sid):
        self.stop_jobs(sid)
        before = {(r.get("id"), r.get("sessionId")) for r in self.agents()}
        procs = [self.popen(["claude", "--bg", "--resume", sid]) for _ in range(2)]
        outs = [p.communicate(timeout=300)[0] for p in procs]
        time.sleep(3)   # whatever either started has written its record
        held = self.records(sid)
        new = [r for r in self.agents() if (r.get("id"), r.get("sessionId")) not in before]
        copies = [r for r in new if r.get("sessionId") != sid]
        self.jobs += [r.get("id") for r in new] + [h.get("jobId") for h in held]
        self.check("two launches at once from two processes (an orphaned launch meeting the next daemon's) leave one "
                   "process holding the session",
                   len(held) == 1 and held[0].get("kind") == "bg",
                   "launches: %s; holders %s; copies %s" % (
                       "; ".join("exit %s, %s" % (p.returncode, banner(o)) for p, o in zip(procs, outs)),
                       self.holding(sid), [(r.get("id"), r.get("sessionId", "")[:8]) for r in copies]))
        for r in copies:
            self.claude(["stop", r.get("id")], timeout=120)

    def reconciliation(self, sid):
        self.stop_jobs(sid)
        [nonce], *rest = self.daemon("die-after-job", sid)
        kept = self.ledger().get(nonce) or {}
        got = self.daemon("restart", "90", nonce)[0][0] or {}
        held = self.records(sid)
        launched = kept.get("launched_at")
        self.check("a Resume whose daemon stopped once its job was kept is reconciled done by the next daemon, from "
                   "that job's process",
                   not rest and isinstance(launched, (int, float)) and kept.get("job") and "outcome" not in kept
                   and got.get("outcome") == done(sid) and [h.get("jobId") for h in held] == [kept.get("job")]
                   and all(process_started(h) is not None and process_started(h) >= int(launched) for h in held),
                   "claim left %s; reconciled %s; holders (kind, job, startedAt, started - launch) %s" % (
                       {k: kept.get(k) for k in ("launched_at", "job", "outcome")}, got.get("outcome"),
                       self.holding(sid, launched)))

        self.stop_jobs(sid)
        [nonce], *rest = self.daemon("die-before-job", sid)
        kept = self.ledger().get(nonce) or {}
        got = self.daemon("restart", "90", nonce)[0][0] or {}
        held = self.records(sid)
        self.jobs += [h.get("jobId") for h in held]
        launched = kept.get("launched_at")
        self.check("a Resume whose daemon stopped before its job was kept is reconciled done, from the --bg process "
                   "its launch started",
                   not rest and isinstance(launched, (int, float)) and "job" not in kept and "outcome" not in kept
                   and got.get("outcome") == done(sid) and [h.get("kind") for h in held] == ["bg"]
                   and all(process_started(h) is not None and process_started(h) >= int(launched) for h in held),
                   "claim left %s; reconciled %s; holders (kind, job, startedAt, started - launch) %s" % (
                       {k: kept.get(k) for k in ("launched_at", "job", "outcome")}, got.get("outcome"),
                       self.holding(sid, launched)))

        # The process holding it now started before the launches these claims
        # record: one keeps its job id (every --bg job of a session is named by
        # its id's first 8), one none. This case comes last: its second daemon
        # runs a window ahead of the clock, so the outcomes it keeps carry a
        # done_at later than any launch after them, and a jobless claim
        # reconciled after it would count these as Resumes still running.
        older = self.records(sid)
        time.sleep(1.1)
        launched = time.time()
        same_job = self.claim(sid, launched, job=(older[0].get("jobId") if older else None))
        jobless = self.claim(sid, launched)
        first = self.daemon("restart", "8", same_job, jobless)[0]
        later = self.daemon("restart-past-window", "60", same_job, jobless)[0]
        self.check("a process that started before a claim's launch is no evidence for it, its job id the same or none: "
                   "not done, then interrupted once the window passes",
                   older and older[0].get("kind") == "bg" and process_started(older[0]) is not None
                   and process_started(older[0]) < launched
                   and [code_of(e) for e in first] == [None, None]
                   and [code_of(e) for e in later] == [("failed", "interrupted")] * 2,
                   "first pass %s, past the window %s; holder (kind, job, startedAt, started - launch) %s" % (
                       [code_of(e) for e in first], [code_of(e) for e in later], self.holding(sid, launched)))

    def copy_race(self, sid):
        self.stop_jobs(sid)
        self.terminal("owner", ["--resume", sid])
        owner = wait_for("the owner's terminal holding it", 120, lambda: self.records(sid))
        before = {(r.get("id"), r.get("sessionId")) for r in self.agents()}
        e = self.resume(sid, mode="skip-check")[0]
        time.sleep(2)
        held = self.records(sid)
        copies = [r for r in self.agents() if r.get("sessionId") not in (sid, None)
                  and (r.get("id"), r.get("sessionId")) not in before]
        self.jobs += [r.get("id") for r in copies]
        self.check("a Resume racing the owner's reopen stops the engine's copy and fails copy-started",
                   code_of(e) == ("failed", "copy-started") and [h.get("pid") for h in held] == [owner[0].get("pid")]
                   and copies and all(not self.records(r.get("sessionId")) for r in copies),
                   "outcome %s; holders %s; copies %s" % (
                       e.get("outcome"), [(h.get("kind"), h.get("pid")) for h in held],
                       [(r.get("id"), r.get("state"), bool(self.records(r.get("sessionId")))) for r in copies]))

    def seat_cases(self):
        r = self.wrapped([self.sminos(), "spawn", SEAT, "Reply with exactly the word READY. Run no tools.",
                          "--model", "haiku", "--permission-mode", "default"])
        m = re.search(r"\[([0-9a-f]+) / ([0-9a-f-]{36})\]", r.stdout)
        if r.returncode != 0 or not m:
            raise RuntimeError("sminos spawn: %s" % (r.stdout + r.stderr).strip()[-2000:])
        sid = m.group(2)
        wait_for("the seat's first answer", 240, lambda: any(row.get("type") == "assistant"
                                                             for row in self.transcript_rows(sid)), every=1)
        wait_for("the seat's first turn to end", 240, lambda: (self.smn("seat", sid) or {}).get("state") == "idle",
                 every=2)
        spawned = self.records(sid)
        self.jobs += [h.get("jobId") for h in spawned]
        self.stop_jobs(sid)
        stopped = self.smn("seat", sid)
        e = self.resume(sid)[0]
        held = self.records(sid)
        self.jobs += [h.get("jobId") for h in held]
        after = self.smn("seat", sid)
        rows = [(r.get("id"), r.get("state")) for r in self.agents() if r.get("sessionId") == sid]
        self.check("a stopped seat's session resumes under its own id, and the seat reads as running",
                   (stopped or {}).get("state") == "stopped" and e.get("outcome") == done(sid)
                   and [h.get("kind") for h in held] == ["bg"] and (after or {}).get("state") in ("idle", "busy", "waiting"),
                   "spawned as job %s; stopped: %s; outcome %s; holders %s; job rows %s; then %s" % (
                       [h.get("jobId") for h in spawned], stopped, e.get("outcome"),
                       self.holding(sid, e.get("launched_at")), rows, after))
        r = self.wrapped([self.sminos(), "retire", SEAT], timeout=300)
        wait_for("the retired seat's job to end", 120, lambda: not self.records(sid))
        retired = self.smn("seat", sid)
        e = self.resume(sid)[0]
        time.sleep(3)
        self.check("a retired seat's session is refused unsupported, nothing launched",
                   r.returncode == 0 and (retired or {}).get("status") == "retired"
                   and code_of(e) == ("failed", "unsupported") and "retired" in e["outcome"]["error"]["message"]
                   and "launched_at" not in e and not self.records(sid),
                   "retire: %s; seat %s; outcome %s; holders %s" % (
                       last_line(r.stdout + r.stderr), retired, e.get("outcome"), self.holding(sid)))


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
