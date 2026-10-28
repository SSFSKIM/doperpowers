#!/usr/bin/env python3
"""The sminos daemon's cost on a machine at the owner's Macs' scale: a
synthetic HOME and SMINOS_HOME, built the same way on every run, measured
against any copy of the scripts (a checkout's, or another commit's exported
with `git archive`), so a change is measured before and after.

    python3 bench_scale.py tick    <scripts-dir> [--ticks N]
    python3 bench_scale.py profile <scripts-dir> <out.prof>
    python3 bench_scale.py run     <scripts-dir> [--rl10 [--words W]] [--seconds S] [--warmup W]
                                                 [--import-events N] [--profile-uplink OUT]
    python3 bench_scale.py verbs   <scripts-dir>
    python3 bench_scale.py opens   <scripts-dir> [--large G] [--large-rows N] [--warm-after S]

Every mode takes the scale's flags (--dirs, --seats, ...; --help lists them)
and --joined-by <scripts-dir>, which makes the first tick, the one that joins
every live session and seat, with another copy: the same events whichever
copy writes them, so a slow copy's steady state is measured without waiting
out its first tick. SIGTERM or SIGINT, in any mode, ends every process it
started (the sessions, `daemon run` and its uplink, the stand-in), removes
the synthetic machine unless --keep, and exits 128 + the signal.

The machine (`testhost`, enrolled in org `org-1`): DIRS engine project
directories under ~/.claude/projects, PER_DIR transcripts each; SEATS seat
records, MISSING of every ten without a transcript here (old seats whose
transcripts the engine cleaned up); LIVE running sessions (each a `sleep`
this script starts, under an engine record); four hub projects with a
checkout here, three without (this machine's own project, the `mini`
machine's, a hub project with no checkout here), each holding REMOTE
members of the `mini` machine (MINI in mini's own project) and chatter;
LOCAL local projects kept as history.

- `tick`: `daemon tick`'s work in one long-lived process, as `daemon run`
  does it (sminos_daemon.tick_all), its first tick (which joins the live
  sessions) apart; each tick's wall time and CPU time.
- `profile`: one steady-state tick under cProfile, written to <out.prof>.
- `run`: `daemon run --interval 5` and its uplink against the hub stand-in
  (hub_standin.py) for S seconds after a W-second warm-up; each process's
  CPU over the window, as a share of one core, and how many ticks ended;
  then, with --import-events, how long N events of the other machine take
  from the hub, one `events` frame each, into the log here.
  --profile-uplink runs the uplink alone under cProfile instead.
  With --rl10 (O14's B2 step 2, O12 M7c), against the endpoint stand-in
  (endpoint_standin.py) in place of the hub's: the machine is cut over by
  the stand-in's complete welcome to a probe (`daemon probe`, the
  supervisor's) before `daemon run` starts, its uplink the RL10 child. Each live session in a hub checkout is owed W `human` events,
  one from each of W members (`hub/mem-<k>`, stored with their `verified`
  signer as an arrival over RL10 is), which the stand-in never answers: each
  stays owed through the window, asked `words?` again at every pass once its
  ask's deadline passed, so every pass has the words-gated work of that
  count to do. The uplink appends a line per words pass to the file
  SMINOS_WORDS_TIMES names; the run reports each process's CPU, the passes
  in the window (count, p50, p95, max wall time) and the longest gap
  between passes (the window's ends included), and checks B2's gate: p95
  under 1 s, the uplink under 5 % of a core, a pass at least every 10 s (its
  period, WORDS_EVERY, plus one second for the tick loop's poll and the
  tick itself). --import-events N then arrive as RL10 `events` frames, one
  event each. Exits 1 when the gate fails.
- `verbs`: the wall and CPU time of `list --org` and `projects`.
- `opens` (the desk open-fast spec's A3): G of the live sessions in hub
  checkouts get a transcript of N rows (15,000, shaped as bench_rig.py
  shapes one for bench_open.py) in place of their short one; the uplink
  alone, started fresh against the stand-in once a tick has joined the live
  sessions; subscribes
  sent through the stand-in's `/control/send` at +0.5 s (a large session and
  a small one, together: the small one opens while the large one builds),
  at +S s (every live session, in sequence), then the uplink restarted (the
  same SMINOS_HOME: whatever it keeps on disk stays) and the +0.5 s pair
  again. One JSON line per open — its moment,
  size, rows and E (the snapshot's arrival at the stand-in less the
  subscribe's write, both the stand-in's stamps), with N and the build from
  the plane's open line — and a summary per moment and size; each line says
  when, after the uplink's start, it went (`sent`). A +0.5 s pair goes only
  if the uplink's stream has opened the sessions' projects by then: else the
  moment is said missing, with when the stream was ready, never sampled
  late under its name, and the run ends with status 3.
"""

import argparse
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ORG, MACHINE, OTHER = "org-1", "testhost", "mini"
KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"  # bytes(range(32)), base64url
HUB_ROOTED = ("doperpowers", "MAWS", "desk-walk", "scratch")
TS = "2026-10-18T%02d:%02d:%02d.000Z"


def machine_project_id(org, machine):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "smns-machine:%s:%s" % (org, machine.lower())))


def jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


class Env:
    def __init__(self, root, a, hub_url="http://127.0.0.1:9"):
        self.root, self.a, self.rnd = root, a, random.Random(7)
        self.home, self.sh = os.path.join(root, "h"), os.path.join(root, "s")
        self.projects = os.path.join(self.home, ".claude", "projects")
        self.sleepers = []
        self.n = 0
        self.seqs = {}
        self.build(hub_url)

    def uid(self):
        return str(uuid.UUID(int=self.rnd.getrandbits(128), version=4))

    def ts(self):
        self.n += 1
        return TS % (self.n // 3600 % 24, self.n // 60 % 60, self.n % 60)

    def transcript(self, cwd, sid, title=""):
        rows = [{"type": "user", "cwd": cwd, "sessionId": sid, "uuid": self.uid(),
                 "message": {"role": "user", "content": "start"}},
                {"type": "assistant", "cwd": cwd, "sessionId": sid, "uuid": self.uid(),
                 "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}],
                             "stop_reason": "end_turn"}}]
        if title:
            rows.append({"type": "ai-title", "aiTitle": title, "sessionId": sid})
        jsonl(os.path.join(self.projects, re.sub(r"[^A-Za-z0-9]", "-", cwd), sid + ".jsonl"), rows)

    def repo(self, name, smns=None):
        d = os.path.join(self.root, "r", name)
        os.makedirs(os.path.join(d, ".git"), exist_ok=True)
        with open(os.path.join(d, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/main\n")
        if smns:
            write(os.path.join(d, ".smns"), smns)
        return d

    def register(self, pid, name, root, hub=True):
        info = {"project": pid, "name": name, "remote": "", "root": root}
        if hub:
            info["hub"] = {"url": self.hub_url, "org": ORG}
        write(os.path.join(self.sh, "projects", pid, "project.json"), info)
        os.makedirs(os.path.join(self.sh, "projects", pid, "log"), exist_ok=True)

    def log(self, pid, writer, events):
        rows = []
        for e in events:
            self.seqs[(pid, writer)] = seq = self.seqs.get((pid, writer), 0) + 1
            rows.append({"ts": self.ts(), "writer": writer, "seq": seq, **e})
        jsonl(os.path.join(self.sh, "projects", pid, "log", writer.replace("/", ".") + ".jsonl"), rows)

    def remote_members(self, pid, n, says):
        sids = []
        for i in range(n):
            sid = self.uid()
            sids.append(sid)
            self.log(pid, "%s/%s" % (OTHER, sid), [
                {"kind": "joined", "session": sid, "alias": "m%d" % i, "name_source": "derived", "machine": OTHER,
                 "cwd": "/Users/mini/work/p%d" % i, "worktree": "", "role": "", "seat": "", "by": "",
                 "session_kind": "interactive", "repo": "p%d" % i, "branch": "main"},
                {"kind": "state", "session": sid, "state": "idle", "machine": OTHER},
                {"kind": "titled", "session": sid, "title": "remote work %d" % i}])
        for i in range(says if sids else 0):
            sid = sids[i % len(sids)]
            self.log(pid, "%s/%s" % (OTHER, sid), [{"kind": "say", "session": sid, "to": [],
                                                   "text": "progress note %d " % i + "x" * 200}])

    def build(self, hub_url):
        a = self.a
        self.hub_url = hub_url
        os.makedirs(os.path.join(self.home, ".claude", "sessions"), exist_ok=True)
        os.makedirs(os.path.join(self.sh, "daemon"), exist_ok=True)
        # The engine's project directories: other work, most of it long done.
        for i in range(a.dirs):
            cwd = "/Users/someone/work/area%d/proj%d" % (i % 37, i)
            for _ in range(a.per_dir):
                self.transcript(cwd, self.uid())
        # The checkouts: hub projects with a .smns here, and local repositories
        # (no .smns: on an enrolled machine, this machine's own project).
        hubs = {}
        for name in HUB_ROOTED:
            pid = self.uid()
            hubs[name] = (pid, self.repo(name, {"project": pid, "name": name, "hub": {"org": ORG}}))
            self.register(pid, name, hubs[name][1])
        own, mini, follow = machine_project_id(ORG, MACHINE), machine_project_id(ORG, OTHER), self.uid()
        self.register(own, MACHINE, "")
        self.register(mini, OTHER, "")
        self.register(follow, "phone walk", "")
        self.hub_ids = [p for p, _ in hubs.values()] + [own, mini, follow]
        locals_ = [self.repo("local%d" % i) for i in range(a.local)]
        for i, d in enumerate(locals_):
            pid = "local-local%d" % i
            self.register(pid, "local%d" % i, d, hub=False)
            for _ in range(3):
                sid = self.uid()
                w = "%s/%s" % (MACHINE, sid)
                self.log(pid, w, [{"kind": "joined", "session": sid, "alias": "old", "name_source": "derived",
                                   "machine": MACHINE, "cwd": d, "session_kind": "interactive"},
                                  {"kind": "retired", "session": sid, "by": "", "reason": "ended"}])
        cwds = [d for _, d in hubs.values()] * 3 + locals_
        project_of = {d: p for p, d in hubs.values()}
        # Seats: most retired or long idle, and most of those without a transcript here.
        for i in range(a.seats):
            sid, cwd = self.uid(), cwds[i % len(cwds)]
            missing = (i % 10) < a.missing
            if not missing:
                self.transcript(cwd, sid, "seat work %d" % i)
            write(os.path.join(self.sh, "%s.json" % self.uid()), {
                "alias": "seat%d" % i, "group": "fleet", "current": sid, "cwd": cwd, "status":
                    ("retired", "idle", "done")[i % 3], "host": "" if missing else MACHINE, "created": self.ts(),
                "updated": self.ts(), "role": "", "worktree": ""})
        # Live sessions: interactive ones in the checkouts, each a `sleep` under an engine record;
        # with `opens`'s --large, the first G of those in hub checkouts hold a large transcript.
        self.live_sessions = []
        large = getattr(a, "large", 0)
        for i in range(a.live):
            sid, cwd = self.uid(), cwds[i % len(cwds)]
            if large and cwd in project_of:
                large -= 1
                import bench_rig
                bench_rig.synthetic_transcript(os.path.join(self.projects, re.sub(r"[^A-Za-z0-9]", "-", cwd),
                                                             sid + ".jsonl"), a.large_rows, cwd, sid)
                size = "large"
            else:
                self.transcript(cwd, sid, "live work %d" % i)
                size = "small"
            self.live_sessions.append({"sid": sid, "cwd": cwd, "size": size, "project": project_of.get(cwd, own)})
            p = spawn(["sleep", "86399"], start_new_session=True, stdin=subprocess.DEVNULL,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.sleepers.append(p)
            write(os.path.join(self.home, ".claude", "sessions", "%d.json" % p.pid), {
                "pid": p.pid, "sessionId": sid, "cwd": cwd, "kind": "interactive", "entrypoint": "cli",
                "status": "idle", "name": "live%d" % i, "nameSource": "derived",
                "updatedAt": int(time.time() * 1000)})
        # Members of the other machine, in every hub project (its own project most of all).
        for pid in self.hub_ids:
            n = a.mini if pid == mini else a.remote
            self.remote_members(pid, n, a.says if pid != mini else 0)
        # RL10 (run --rl10): a person's words owed to each live session in a hub checkout, one event from each
        # of WORDS members' devices, stored as an arrival over RL10 is (its signer under `verified`).
        self.words_owed = 0
        if getattr(a, "rl10", False):
            for i, s in enumerate(x for x in self.live_sessions if x["project"] in project_of.values()):
                self.words_owed += a.words
                for k in range(a.words):
                    self.log(s["project"], "hub/mem-%d" % k, [{
                        "kind": "human", "from": "member %d" % k, "member": "mem-%d" % k,
                        "to": [{"session": s["sid"], "alias": "live%d" % i}], "text": "words %d for %d" % (k, i),
                        "verified": {"signer": {"kind": "device", "member": "mem-%d" % k, "device": "dev-%d" % k,
                                                "keyId": "k-dev-%d" % k}}}])
        write(os.path.join(self.sh, "daemon", "hub.json"), {
            "hub": hub_url, "org": ORG, "machine": MACHINE, "client_id": "cid-1", "client_secret": "secret-1",
            "key": KEY, "enrolled": "2026-10-01T00:00:00Z"})
        os.chmod(os.path.join(self.sh, "daemon", "hub.json"), 0o600)
        names = {p: n for n, (p, _) in hubs.items()}
        names.update({own: MACHINE, mini: OTHER, follow: "phone walk"})
        write(os.path.join(self.sh, "daemon", "org.json"), {
            "projects": [{"id": p, "name": names[p], "kind": "machine" if p in (own, mini) else "hub",
                          "retired": False} for p in self.hub_ids],
            "machines": [{"name": MACHINE, "online": True, "seen": None}, {"name": OTHER, "online": True, "seen": None}],
            "at": "2026-10-18T00:00:00.000Z"})
        stub = os.path.join(self.root, "bin")
        os.makedirs(stub, exist_ok=True)
        with open(os.path.join(stub, "claude"), "w") as f:
            f.write('#!/bin/sh\ncase "$1" in agents) echo "[]";; esac\nexit 0\n')
        os.chmod(os.path.join(stub, "claude"), 0o755)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("CLAUDE_CODE_", "SMNS_", "SMINOS_", "DAEMON_"))}
        self.env.update(HOME=self.home, SMINOS_HOME=self.sh, PATH=stub + os.pathsep + os.environ["PATH"],
                        SMINOS_DERIVE_EVERY="0")

    def close(self):
        for p in self.sleepers:
            p.kill()
            p.wait()


def scale(p):
    p.add_argument("--dirs", type=int, default=1500)
    p.add_argument("--per-dir", type=int, default=4)
    p.add_argument("--seats", type=int, default=200)
    p.add_argument("--missing", type=int, default=6, help="of every ten seats, how many have no transcript here")
    p.add_argument("--live", type=int, default=20)
    p.add_argument("--local", type=int, default=20)
    p.add_argument("--remote", type=int, default=40)
    p.add_argument("--mini", type=int, default=100)
    p.add_argument("--says", type=int, default=300)
    p.add_argument("--keep", action="store_true", help="leave the synthetic machine on disk")
    p.add_argument("--joined-by", metavar="SCRIPTS", help="make the first tick with this copy of the scripts")


def in_process(env, scripts):
    """The scripts imported here, against the synthetic machine."""
    os.environ.clear()
    os.environ.update(env.env)
    sys.path.insert(0, os.path.abspath(scripts))
    import sminos
    return sminos, sminos.daemon_module()


def tick_quietly(daemon):
    """One tick_all, its output kept; a project's failed tick fails the measurement."""
    import io
    stdout, stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        daemon.tick_all(quiet=True)
    finally:
        said, sys.stdout, sys.stderr = sys.stderr.getvalue(), stdout, stderr
    if "tick failed" in said:
        sys.exit("a tick failed:\n" + said)


def cmd_tick(a, env):
    sminos, daemon = in_process(env, a.scripts)
    out = []
    for i in range(a.ticks + 1):
        w, c = time.perf_counter(), time.process_time()
        tick_quietly(daemon)
        out.append((time.perf_counter() - w, time.process_time() - c))
        first = "first (this process's caches cold)" if a.joined_by else "first (joins the live sessions)"
        print("%s tick: %.3f s wall, %.3f s CPU" % (first if i == 0 else "steady", *out[-1]), flush=True)
    rest = sorted(out[1:])
    if rest:
        print("steady tick median: %.3f s wall, %.3f s CPU" % rest[len(rest) // 2])


def cmd_profile(a, env):
    import cProfile
    sminos, daemon = in_process(env, a.scripts)
    tick_quietly(daemon)
    pr = cProfile.Profile()
    pr.enable()
    tick_quietly(daemon)
    pr.disable()
    pr.dump_stats(a.out)
    print("profile of one steady tick: %s" % a.out)


def cpu_seconds(pid):
    """A process's CPU time so far (user + system), from ps."""
    out = subprocess.run(["ps", "-o", "time=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    if not out:
        return None
    days, _, rest = out.rpartition("-")
    parts = [float(x) for x in rest.split(":")]
    secs = 0.0
    for x in parts:
        secs = secs * 60 + x
    return secs + (int(days) * 86400 if days else 0)


def ticks_ended(env):
    """The tick stamps every project's daemon.json holds now."""
    out = set()
    root = os.path.join(env.sh, "projects")
    for pid in os.listdir(root):
        try:
            with open(os.path.join(root, pid, "daemon.json")) as f:
                out.add((pid, json.load(f).get("tick")))
        except (OSError, ValueError):
            pass
    return out


def import_burst(a, env, url, n, give_up=120.0):
    """`n` events of a new session of the other machine, sealed with the
    org's key, sent down the stream by the stand-in one frame each into the
    other machine's project (one this machine follows); (seconds until the
    last is in the log here, how many arrived)."""
    import base64
    import urllib.request
    sys.path.insert(0, os.path.abspath(a.scripts))
    import sminos_codes as codes
    key = base64.urlsafe_b64decode(KEY + "=")
    pid, sid = machine_project_id(ORG, OTHER), str(uuid.uuid4())
    writer = "%s/%s" % (OTHER, sid)
    path = os.path.join(env.sh, "projects", pid, "log", writer.replace("/", ".") + ".jsonl")

    def arrived():
        try:
            with open(path) as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return 0

    t0 = time.time()
    for seq in range(1, n + 1):
        ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        draft = {"ts": ts, "writer": writer, "seq": seq, "kind": "say", "session": sid, "to": [],
                 "text": "burst %d" % seq}
        e = codes.seal(key, "log", pid, draft, codes.b64url(os.urandom(16)))
        req = urllib.request.Request(url + "/control/inject", method="POST",
                                     data=json.dumps({"project": pid, "events": [e]}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
    while arrived() < n and time.time() - t0 < give_up:
        time.sleep(0.1)
    return time.time() - t0, arrived()


def cmd_run(a, env):
    if a.rl10:
        return cmd_run_rl10(a, env)
    port_file = os.path.join(env.root, "hub.port")
    hub = spawn([sys.executable, os.path.join(HERE, "hub_standin.py"), port_file, "cid-1", "secret-1",
                 "15000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run = None
    try:
        while not (os.path.exists(port_file) and open(port_file).read().strip()):
            time.sleep(0.05)
        url = "http://127.0.0.1:%s" % open(port_file).read().strip()
        cred = os.path.join(env.sh, "daemon", "hub.json")
        d = json.load(open(cred))
        d["hub"] = url
        write(cred, d)
        os.chmod(cred, 0o600)
        import urllib.request
        req = urllib.request.Request(url + "/control/register", method="POST", data=json.dumps(
            {"project": machine_project_id(ORG, OTHER), "name": OTHER, "kind": "machine"}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
        log = open(os.path.join(env.root, "run.out"), "w")
        if a.profile_uplink:
            # The uplink alone, this process its parent, under cProfile, once a
            # tick has joined the live sessions: no tick loop beside it.
            subprocess.run([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "tick"], env=env.env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            run = spawn([sys.executable, os.path.abspath(__file__), "_profiled", a.scripts,
                         a.profile_uplink, "daemon", "uplink"], env=env.env, stdout=log,
                        stderr=subprocess.STDOUT)
            time.sleep(a.warmup + a.seconds)
            return
        run = spawn([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "run", "--interval",
                     "5"], env=env.env, stdout=log, stderr=subprocess.STDOUT)
        time.sleep(a.warmup)
        up = int(open(os.path.join(env.sh, "daemon", "uplink.lock")).read().split()[1])
        r0, u0, t0, seen = cpu_seconds(run.pid), cpu_seconds(up), time.time(), ticks_ended(env)
        stamps = set()
        while time.time() - t0 < a.seconds:
            time.sleep(0.5)
            stamps |= ticks_ended(env) - seen
        r1, u1, dt = cpu_seconds(run.pid), cpu_seconds(up), time.time() - t0
        per_project = {}
        for pid, _ in stamps:
            per_project[pid] = per_project.get(pid, 0) + 1
        ticks = max(per_project.values(), default=0)
        print("window %.0f s after a %.0f s warm-up; %d ticks ended in it (interval 5 s)" % (dt, a.warmup, ticks))
        print("daemon run: %.1f CPU-s, %.1f%% of a core" % (r1 - r0, 100 * (r1 - r0) / dt))
        print("uplink:     %.1f CPU-s, %.1f%% of a core" % (u1 - u0, 100 * (u1 - u0) / dt))
        if a.import_events:
            took, got = import_burst(a, env, url, a.import_events)
            print("import: %d of %d events from the hub, one frame each, in the log after %.1f s%s" % (
                got, a.import_events, took, "" if got == a.import_events else " (gave up)"))
        with open(os.path.join(env.sh, "daemon.log")) as f:
            failed = [line for line in f if "failed" in line]
        if failed:
            print("daemon.log says %d failures, the first: %s" % (len(failed), failed[0].strip()))
    finally:
        if run is not None:
            run.send_signal(signal.SIGTERM)
            try:
                run.wait(60)
            except subprocess.TimeoutExpired:
                run.kill()
        hub.kill()
        hub.wait()


class EndpointStandin:
    """endpoint_standin.py serving the machine's RL10 socket, its identity
    complete (so its welcome cuts the machine over), answering no `words?`;
    `ctl` speaks to its control socket directly (a `send` is one frame
    down the live connection)."""

    IDENTITY = {"org": ORG, "hub": "http://127.0.0.1:9", "name": MACHINE, "former": [], "ref": "ref-" + MACHINE,
                "enrolled": "2026-10-01T00:00:00.000Z"}

    def __init__(self, env):
        self.dir = os.path.join(env.root, "ep")
        self.proc = spawn([sys.executable, os.path.join(HERE, "endpoint_standin.py"), "serve", self.dir,
                           json.dumps({"identity": self.IDENTITY})],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 10
            while not os.path.exists(os.path.join(self.dir, "ctl.sock")):
                if time.time() > deadline or self.proc.poll() is not None:
                    raise RuntimeError("the endpoint stand-in did not start in 10 s")
                time.sleep(0.05)
        except BaseException:
            self.stop()
            raise
        env.env["SMINOS_RL10"] = os.path.join(self.dir, "rl10.json")
        env.env.pop("MAWS_USER_DATA", None)

    def ctl(self, op, arg=None):
        import socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(60)
        try:
            sock.connect(os.path.join(self.dir, "ctl.sock"))
            sock.sendall((json.dumps({"op": op, "arg": arg or {}}) + "\n").encode())
            data = bytearray()
            while chunk := sock.recv(1 << 16):
                data += chunk
        finally:
            sock.close()
        answer = json.loads(data.decode())
        if "error" in answer:
            raise RuntimeError("the endpoint stand-in's %s: %s" % (op, answer["error"]))
        return answer

    def stop(self):
        self.proc.kill()
        self.proc.wait()


def import_burst_rl10(env, ep, n, give_up=120.0):
    """`n` events of a new session of the other machine, sent down the RL10
    socket by the stand-in, one `events` frame each, each wrapped as the
    endpoint sends another's event (`{event, signer}`), into the other
    machine's project; (seconds until the last is in the log here, how many
    arrived)."""
    pid, sid = machine_project_id(ORG, OTHER), str(uuid.uuid4())
    writer = "%s/%s" % (OTHER, sid)
    path = os.path.join(env.sh, "projects", pid, "log", writer.replace("/", ".") + ".jsonl")
    signer = {"kind": "machine", "ref": "ref-" + OTHER, "name": OTHER, "keyId": "k-" + OTHER}

    def arrived():
        try:
            with open(path) as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return 0

    t0 = time.time()
    for seq in range(1, n + 1):
        ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        e = {"ts": ts, "writer": writer, "seq": seq, "kind": "say", "session": sid, "to": [], "text": "burst %d" % seq}
        ep.ctl("send", {"frames": [{"t": "events", "project": pid, "events": [{"event": e, "signer": signer}]}]})
    while arrived() < n and time.time() - t0 < give_up:
        time.sleep(0.1)
    return time.time() - t0, arrived()


def percentile(xs, q):
    """The nearest-rank q-th percentile of xs (sorted ascending)."""
    import math
    return xs[max(0, math.ceil(q / 100 * len(xs)) - 1)]


WORDS_EVERY, POLL_SLACK = 10.0, 1.0   # sminos_uplink.WORDS_EVERY; the tick loop's poll and the tick itself
GATE_P95, GATE_CPU = 1.0, 5.0         # O14 B2 step 2: p95 per pass under 1 s, the uplink under 5 % of a core


def words_passes(path, t0, t1):
    """The words passes the uplink timed (SMINOS_WORDS_TIMES) that began in [t0, t1]."""
    try:
        with open(path) as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except OSError:
        return []
    return [r for r in rows if t0 <= r["at"] <= t1]


def cut_over(env):
    return os.path.exists(os.path.join(env.sh, "daemon", "identity.json"))


def cmd_run_rl10(a, env):
    """`run --rl10`: see the module's docstring. Exit status 1 when B2's gate fails."""
    ep = EndpointStandin(env)
    times = os.path.join(env.root, "words-passes.jsonl")
    env.env["SMINOS_WORDS_TIMES"] = times
    run = None
    try:
        log = open(os.path.join(env.root, "run.out"), "w")
        # Cut over first, by the stand-in's welcome to a probe (what `daemon run`'s supervisor runs): a first
        # tick on DX2 would deliver the owed words as a machine not cut over does, before the probe's welcome.
        subprocess.run([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "probe"], env=env.env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not cut_over(env):
            print("the endpoint stand-in's welcome did not cut the machine over")
            return 1
        if a.profile_uplink:
            # Joined by a tick, then the uplink alone under cProfile.
            subprocess.run([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "tick"], env=env.env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            run = spawn([sys.executable, os.path.abspath(__file__), "_profiled", a.scripts,
                         a.profile_uplink, "daemon", "uplink"], env=env.env, stdout=log,
                        stderr=subprocess.STDOUT)
            time.sleep(a.warmup + a.seconds)
            return 0
        run = spawn([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "run", "--interval",
                     "5"], env=env.env, stdout=log, stderr=subprocess.STDOUT)
        time.sleep(a.warmup)
        status = subprocess.run([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "status"],
                                env=env.env, capture_output=True, text=True).stdout
        if not cut_over(env) or "uplink: RL10 (local-only), running" not in status:
            print("after the %.0f s warm-up the machine is not on RL10: %s" % (
                a.warmup, next((x for x in status.splitlines() if x.startswith("uplink")), "no uplink line")))
            return 1
        up = int(open(os.path.join(env.sh, "daemon", "uplink.lock")).read().split()[1])
        r0, u0, e0, t0, seen = cpu_seconds(run.pid), cpu_seconds(up), cpu_seconds(ep.proc.pid), time.time(), \
            ticks_ended(env)
        stamps = set()
        while time.time() - t0 < a.seconds:
            time.sleep(0.5)
            stamps |= ticks_ended(env) - seen
        r1, u1, e1, t1 = cpu_seconds(run.pid), cpu_seconds(up), cpu_seconds(ep.proc.pid), time.time()
        dt = t1 - t0
        per_project = {}
        for pid, _ in stamps:
            per_project[pid] = per_project.get(pid, 0) + 1
        owed = env.words_owed
        print("window %.0f s after a %.0f s warm-up; %d ticks ended in it (interval 5 s); the uplink on RL10 "
              "(local-only), cut over by the endpoint stand-in's welcome; %d words-gated events owed, never answered"
              % (dt, a.warmup, max(per_project.values(), default=0), owed))
        uplink_share = 100 * (u1 - u0) / dt
        print("daemon run: %.1f CPU-s, %.1f%% of a core" % (r1 - r0, 100 * (r1 - r0) / dt))
        print("uplink:     %.1f CPU-s, %.1f%% of a core" % (u1 - u0, uplink_share))
        print("endpoint stand-in: %.1f CPU-s, %.1f%% of a core (not gated)" % (e1 - e0, 100 * (e1 - e0) / dt))
        passes = words_passes(times, t0, t1)
        walls = sorted(r["wall"] for r in passes)
        ats = [t0] + sorted(r["at"] for r in passes) + [t1]
        gap = max(b - x for x, b in zip(ats, ats[1:]))
        if walls:
            p95 = percentile(walls, 95)
            print("words pass: %d passes; per pass p50 %.3f s, p95 %.3f s, max %.3f s (CPU p95 %.3f s); longest gap "
                  "between passes %.2f s; asks out after the last: %d" % (
                      len(walls), percentile(walls, 50), p95, walls[-1],
                      percentile(sorted(r["cpu"] for r in passes), 95), gap, passes[-1]["asks"] if passes else 0))
        else:
            p95 = None
            print("words pass: no pass in the window (longest gap %.2f s)" % gap)
        if a.import_events:
            took, got = import_burst_rl10(env, ep, a.import_events)
            print("import: %d of %d events from the endpoint, one RL10 events frame each, in the log after %.1f s%s"
                  % (got, a.import_events, took, "" if got == a.import_events else " (gave up)"))
        with open(os.path.join(env.sh, "daemon.log")) as f:
            failed = [line for line in f if "failed" in line]
        if failed:
            print("daemon.log says %d failures, the first: %s" % (len(failed), failed[0].strip()))
        checks = [("words pass p95 under %g s" % GATE_P95, p95 is not None and p95 < GATE_P95,
                   "no pass" if p95 is None else "%.3f s" % p95),
                  ("uplink under %g%% of a core" % GATE_CPU, uplink_share < GATE_CPU, "%.1f%%" % uplink_share),
                  ("a words pass at least every %g s" % WORDS_EVERY, gap <= WORDS_EVERY + POLL_SLACK,
                   "longest gap %.2f s, %g s allowed past the period for the tick loop" % (gap, POLL_SLACK))]
        for what, ok, said in checks:
            print("gate: %s: %s (%s)" % (what, "ok" if ok else "FAILED", said))
        ok = all(c[1] for c in checks)
        print("gate (O14 B2 step 2): %s" % ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        if run is not None:
            run.send_signal(signal.SIGTERM)
            try:
                run.wait(60)
            except subprocess.TimeoutExpired:
                run.kill()
        ep.stop()


def standin(env):
    """hub_standin.py for the machine, its URL in the credential, the other
    machine's project registered. The process is ended if anything after its
    start fails, so a setup that raises leaves none behind."""
    import urllib.request
    port_file = os.path.join(env.root, "hub.port")
    hub = spawn([sys.executable, os.path.join(HERE, "hub_standin.py"), port_file, "cid-1", "secret-1",
                 "15000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline, port = time.time() + 10, ""
        while not port:
            if os.path.exists(port_file):
                with open(port_file) as f:
                    port = f.read().strip()
            if not port and (time.time() > deadline or hub.poll() is not None):
                raise RuntimeError("the stand-in wrote no port in 10 s")
            if not port:
                time.sleep(0.05)
        url = "http://127.0.0.1:%s" % port
        cred = os.path.join(env.sh, "daemon", "hub.json")
        with open(cred) as f:
            d = json.load(f)
        d["hub"] = url
        write(cred, d)
        os.chmod(cred, 0o600)
        req = urllib.request.Request(url + "/control/register", method="POST", data=json.dumps(
            {"project": machine_project_id(ORG, OTHER), "name": OTHER, "kind": "machine"}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except BaseException:
        stop(hub)
        raise
    return hub, url


def cmd_opens(a, env):
    import bench_open as bo
    import bench_rig as rig
    hub, url = standin(env)
    up = [None]
    try:
        subprocess.run([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "tick"], env=env.env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        lives = env.live_sessions
        own = machine_project_id(ORG, MACHINE)
        small = next(s for s in lives if s["size"] == "small" and s["project"] != own)
        large = next((s for s in lives if s["size"] == "large"), None)
        if large is None:
            sys.exit("bench_scale opens: no live session in a hub checkout took a large transcript (--large)")
        browser = rig.StandinBrowser(url, None, MACHINE)
        log_path = os.path.join(env.sh, "daemon.log")
        pair = [large, small]   # the large one's subscribe first: the small one opens while its build runs

        def ready(after, pids):
            """A stream newer than generation `after`, once it opened every project named."""
            st = rig.call(url, "GET", "/control/state")[1]
            gen = st["generation"]
            return gen > after and st["connected"] and all(
                st["projects"].get(pid, {}).get("open", {}).get(MACHINE) == gen for pid in pids)

        def finish(s, sub, at, moment, started):
            snap = None
            deadline = time.time() + 120
            while time.time() < deadline and snap is None:
                browser.poll()
                snap = next(((t, m) for t, m in browser.msgs if m.get("sub") == sub
                             and m.get("kind") in ("snapshot", "end")), None)
                if snap is None:
                    time.sleep(0.02)
            line = {}
            deadline = time.time() + 5
            while not line and time.time() < deadline:
                line = bo.open_lines(log_path).get(sub) or {}
                if not line:
                    time.sleep(0.05)
            browser.project = s["project"]
            browser.unsubscribe(sub)
            rec = {"moment": moment, "session": s["sid"][:8], "size": s["size"], "rows": line.get("rows"),
                   "E": None if snap is None or snap[1]["kind"] != "snapshot" else round(snap[0] - at, 3),
                   "N": line.get("N"), "build": line.get("build"), "cpu_ms": line.get("cpu_ms"),
                   "outcome": line.get("outcome"), "sent": round(at - started, 3), "load1": bo.load1()}
            print(json.dumps(rec), flush=True)
            return rec

        def opens(sessions, moment, started, together):
            """Subscribes for the sessions: all sent before any is waited on (`together`), or one by one."""
            out, pending = [], []
            for s in sessions:
                browser.project = s["project"]
                sub, at = browser.subscribe(s["sid"])
                pending.append((s, sub, at))
                if not together:
                    out.append(finish(*pending.pop(), moment, started))
            out += [finish(s, sub, at, moment, started) for s, sub, at in pending]
            return out

        records, generation, missed = [], 0, []
        for phase in ("start", "restart"):
            if up[0] is not None:
                generation = rig.call(url, "GET", "/control/state")[1]["generation"]
                stop(up[0])
            up[0] = spawn([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "uplink"],
                          env=env.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            started = time.time()
            moment = "+0.5 s" if phase == "start" else "restart +0.5 s"
            projects = [s["project"] for s in pair]
            time.sleep(max(0.0, started + 0.5 - time.time()))
            if ready(generation, projects):
                records += opens(pair, moment, started, together=True)
            else:
                # The cold start's sample is the open at its moment: a stream not ready then makes it
                # missing, not a later open filed under the moment's name.
                try:
                    rig.wait_for("the uplink's projects open on its stream", 120,
                                 lambda: ready(generation, projects), 0.02)
                    at = round(time.time() - started, 3)
                except TimeoutError:
                    at = None
                print(json.dumps({"moment": moment, "incomplete": "the uplink's stream had not opened the "
                                  "projects at the moment", "ready": at, "load1": bo.load1()}), flush=True)
                missed.append(moment)
            if phase == "start":
                time.sleep(max(0.0, started + a.warm_after - time.time()))
                records += opens(lives, "+%g s" % a.warm_after, started, together=False)
        for moment in dict.fromkeys(r["moment"] for r in records):
            for size in ("small", "large"):
                of = [r for r in records if r["moment"] == moment and r["size"] == size]
                if of:
                    print(json.dumps({"summary": moment, "size": size, "opens": len(of),
                                      "E": bo.stats(r["E"] for r in of), "N": bo.stats(r["N"] for r in of),
                                      "load1": {"min": min(r["load1"] for r in of),
                                                "max": max(r["load1"] for r in of)},
                                      "uptime": bo.uptime()}), flush=True)
        if missed:
            print(json.dumps({"summary": "opens", "complete": False, "incomplete": missed}), flush=True)
            return 3
    finally:
        if up[0] is not None:
            stop(up[0])
        hub.kill()
        hub.wait()


def stop(p):
    p.send_signal(signal.SIGTERM)
    try:
        p.wait(30)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()


def cmd_verbs(a, env):
    for verb in (["list", "--org"], ["projects"]):
        t = time.perf_counter()
        before = os.times()
        subprocess.run([sys.executable, os.path.join(a.scripts, "sminos.py")] + verb, env=env.env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        after = os.times()
        cpu = (after.children_user - before.children_user) + (after.children_system - before.children_system)
        print("%-10s %.2f s wall, %.2f s CPU" % (" ".join(verb), time.perf_counter() - t, cpu))


def profiled(scripts, out, argv):
    """A sminos verb run under cProfile until it returns or SIGTERM ends it."""
    import cProfile
    sys.path.insert(0, os.path.abspath(scripts))
    sys.argv = ["sminos"] + argv
    import sminos
    pr = cProfile.Profile()
    pr.enable()
    try:
        sminos.main()
    except SystemExit:
        pass
    finally:
        pr.disable()
        pr.dump_stats(out)


class Stopped(BaseException):
    """SIGTERM or SIGINT, raised where this process is (stop_on_signals).
    Neither SystemExit nor KeyboardInterrupt: `tick` and `profile` run the
    daemon's tick_all here, which takes those as one project's failure."""


STARTED = []   # every child this process started (spawn), for the end's sweep
_SIGNAL = {"got": None, "raised": False, "shield": 0}


def _on_signal(signum, _frame):
    if _SIGNAL["got"] is None:
        _SIGNAL["got"] = signum
    if not (_SIGNAL["raised"] or _SIGNAL["shield"]):
        _SIGNAL["raised"] = True
        raise Stopped(signum)


def stop_on_signals():
    """SIGTERM or SIGINT (a timeout, a harness, ^C) raises Stopped where this
    process is, once, so every `finally` runs and stops what it started; a
    later one changes nothing. Inside spawn, and once main's end has begun,
    a signal is only noted: spawn raises it after its child is in STARTED,
    and the end kills whatever of STARTED an unwind left running."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _on_signal)


def spawn(argv, **kw):
    """subprocess.Popen, its child in STARTED before a signal can unwind past it."""
    _SIGNAL["shield"] += 1
    try:
        p = subprocess.Popen(argv, **kw)
        STARTED.append(p)
    finally:
        _SIGNAL["shield"] -= 1
    if _SIGNAL["got"] is not None and not _SIGNAL["raised"]:
        _SIGNAL["raised"] = True
        raise Stopped(_SIGNAL["got"])
    return p


def end_started():
    """Every child of STARTED still running killed, then reaped: what an
    unwind cut short of its own stop (an uplink ends with its `daemon run`)."""
    for p in STARTED:
        if p.poll() is None:
            p.kill()
    for p in STARTED:
        p.wait()


def main():
    if sys.argv[1:2] == ["_profiled"]:
        return profiled(sys.argv[2], sys.argv[3], sys.argv[4:])
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="mode", required=True)
    for mode in ("tick", "profile", "run", "verbs", "opens"):
        s = sub.add_parser(mode)
        s.add_argument("scripts")
        if mode == "profile":
            s.add_argument("out")
        scale(s)
    sub.choices["tick"].add_argument("--ticks", type=int, default=5)
    sub.choices["run"].add_argument("--seconds", type=float, default=60)
    sub.choices["run"].add_argument("--warmup", type=float, default=30)
    sub.choices["run"].add_argument("--import-events", type=int, default=0, metavar="N",
                                    help="after the window, time N events from the hub, one frame each, into the log")
    sub.choices["run"].add_argument("--profile-uplink", metavar="OUT",
                                    help="run the uplink alone under cProfile for warmup + seconds, its profile to OUT")
    sub.choices["run"].add_argument("--rl10", action="store_true",
                                    help="against the RL10 endpoint stand-in, the machine cut over; B2's gate checked")
    sub.choices["run"].add_argument("--words", type=int, default=2, metavar="W",
                                    help="--rl10: words-gated events owed to each live session in a hub checkout, "
                                         "one from each of W members, never answered")
    sub.choices["opens"].add_argument("--large", type=int, default=6, metavar="G",
                                      help="live sessions in hub checkouts given a large transcript")
    sub.choices["opens"].add_argument("--large-rows", type=int, default=15000, metavar="N")
    sub.choices["opens"].add_argument("--warm-after", type=float, default=30.0, metavar="S",
                                      help="when, after the uplink's start, every live session is opened in sequence")
    a = p.parse_args()
    stop_on_signals()
    root = env = None
    status = 0
    try:
        root = tempfile.mkdtemp(prefix="smb-", dir="/tmp")
        t = time.perf_counter()
        env = Env(root, a)
        print("built %s in %.1f s: %d engine project dirs, %d seats (%d0%% without a transcript), %d live sessions, "
              "%d hub projects, %d local" % (root, time.perf_counter() - t, a.dirs, a.seats, a.missing, a.live,
                                             len(env.hub_ids), a.local), flush=True)
        if a.joined_by:
            # The first tick's joins made by another copy of the scripts (the
            # same events any copy writes), so a slow copy's steady state is
            # measured without waiting out its first tick.
            t = time.perf_counter()
            subprocess.run([sys.executable, os.path.join(a.joined_by, "sminos.py"), "daemon", "tick"], env=env.env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("joined by %s's first tick in %.1f s" % (a.joined_by, time.perf_counter() - t), flush=True)
        status = {"tick": cmd_tick, "profile": cmd_profile, "run": cmd_run, "verbs": cmd_verbs,
                  "opens": cmd_opens}[a.mode](a, env)
    except Stopped:
        pass
    finally:
        _SIGNAL["shield"] += 1   # from here a signal unwinds nothing: the end below always runs whole
        if env is not None:
            env.close()
        end_started()
        if root is not None and not a.keep:
            shutil.rmtree(root, ignore_errors=True)
    if _SIGNAL["got"] is not None:
        sys.exit(128 + _SIGNAL["got"])
    if status:
        sys.exit(status)   # opens: a moment it could not sample (its summary says which)


if __name__ == "__main__":
    main()
