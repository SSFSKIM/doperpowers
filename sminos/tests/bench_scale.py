#!/usr/bin/env python3
"""The sminos daemon's cost on a machine at the owner's Macs' scale: a
synthetic HOME and SMINOS_HOME, built the same way on every run, measured
against any copy of the scripts (a checkout's, or another commit's exported
with `git archive`), so a change is measured before and after.

    python3 bench_scale.py tick    <scripts-dir> [--ticks N]
    python3 bench_scale.py profile <scripts-dir> <out.prof>
    python3 bench_scale.py run     <scripts-dir> [--words W] [--seconds S] [--warmup W]
                                                 [--import-events N] [--profile-uplink OUT]
    python3 bench_scale.py verbs   <scripts-dir>
    python3 bench_scale.py opens   <scripts-dir> [--large G] [--large-rows N] [--warm-after S]
    python3 bench_scale.py shape   <scripts-dir>
    python3 bench_scale.py passes  <profile> [--top N]

    python3 bench_scale.py run <scripts-dir> --preset macbook --warmup 90 --strace 20 --pycalls 30 --nudges 6

`run` and `opens` run on RL10, against the endpoint stand-in: the DX2 hub's
arms went with #153 M5. Each still accepts --rl10, which the commands of
#153 M3e and O14's B2 name, and which changes nothing.

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
members of the `mini` machine (MINI in mini's own project) and chatter,
and OWN ended sessions of this machine in each hub project with a checkout
(its history there: one writer file each, which the uplink's upload pass
looks over; the MacBook held about 600 on 2026-10-28); LOCAL local projects
kept as history.

- `tick`: `daemon tick`'s work in one long-lived process, as `daemon run`
  does it (sminos_daemon.tick_all), its first tick (which joins the live
  sessions) apart; each tick's wall time and CPU time.
- `profile`: one steady-state tick under cProfile, written to <out.prof>.
- `run` (O14's B2 step 2, O12 M7c): `daemon run --interval 5` and its
  uplink against the endpoint stand-in (endpoint_standin.py) for S seconds
  after a W-second warm-up; the machine is cut over by the stand-in's
  complete welcome to a probe (`daemon probe`, the supervisor's) before
  `daemon run` starts, its uplink the RL10 child. --profile-uplink runs the
  uplink alone under cProfile instead. Each live session in a hub checkout
  is owed W `human` events,
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
  alone, started fresh against the endpoint stand-in (bench_rig's
  EndpointHub, in this process; the machine cut over by its welcome to
  `daemon probe` before the tick) once a tick has joined the live sessions;
  subscribes, each a frame the stand-in writes down the uplink's
  connection, at +0.5 s (a large session and
  a small one, together: the small one opens while the large one builds),
  at +S s (every live session, in sequence), then the uplink restarted (the
  same SMINOS_HOME: whatever it keeps on disk stays) and the +0.5 s pair
  again. One JSON line per open — its moment,
  size, rows and E (the snapshot's `session` frame's arrival at the
  stand-in less the subscribe's write), with N and the build from
  the plane's open line — and a summary per moment and size; each line says
  when, after the uplink's start, it went (`sent`). A +0.5 s pair goes only
  if the uplink's connection is ready by then — a connection newer than the
  last has sent the projects' hellos: else the moment is said missing, with
  when it was ready, never sampled late under its name, and the run ends
  with status 3.
- `shape`: the machine built, cut over by the stand-in's welcome and joined
  by a tick, then counted as the uplink would see it (projects registered
  and open, seats and those it may not read, members and their session
  records, engine records and live ones, bridges answering, host stores, own
  and former-name writer files, log events), to hold against the Mac it
  stands for.
- `passes`: a profile `run --pycalls` kept, read by pass: the CPU time of
  each thread (in a profile taken on Linux) and of each pass (the hook's
  timers: every call's CPU time on its own thread, the two member
  publishes, the plane's tick, presence and
  member reads, the upload pass, the scan, the words pass, the records scan,
  the bridge probes, each subscription's pump, the transcripts' workers and
  the metas look), then cProfile's callees of the main passes and the
  functions with the most time of their own.

--preset macbook or mini builds a machine of that Mac's shape (PRESETS:
the counts read on each, 2026-11-12; a flag given beside it wins), with
what the default machine has none of: hub projects followed without a
checkout and retired ones that kept an uplink.json, seats whose directory
is in a folder macOS protects, read as macOS would (--tcc: sminos.TCC on in
every sminos process the bench starts, the uplink's working directory
outside them), a former machine name holding writer files, session
records, engine records of processes gone, bridge sockets (most answering
`GET /status` from this process), host stores with their cursors kept,
one large log, the history aged past HOT_FOR, and one live session's
engine record rewritten every --working seconds, as a working session's
is; the mini's, 11 transcript subscriptions held open (--subs). With no
preset the machine is the one the B2 gate was set on.

`run --subs N` subscribes, once the uplink's stream has opened their
projects, to N sessions' transcripts (the live sessions in hub checkouts
first, then the member seats that have one), as a desk window does, and
holds every one open through the CPU window and the windows after it:
the sessions idle, nothing appended. It says how many snapshots arrived
before the CPU window, and how many subscriptions had ended by its end.

`run` also takes, each in a window of its own after the CPU window, so
neither touches the CPU figure: --strace S, the uplink's system calls for S
seconds (strace -f, through `sudo -n` where ptrace is scoped), a second by
kind and by path pattern; --pycalls S, the uplink's Python-level calls for
S seconds (cProfile, begun and ended by signal through the bench's hook),
a second in all, of Python functions, and of each file call, its profile
kept with --pycalls-prof. A window shorter than MEMBERS_WHOLE (60 s) holds
the whole member round, a member read of every project (103 at the
MacBook's shape), or not, as its phase falls, and so does a live
machine's profile: compare windows of 60 s. --nudges N, N nudges of
`daemon run` a few seconds apart, each its tick's wall time and how long
after the nudge it ended.
Every `daemon run` tick's wall and CPU time is recorded through the hook
(tick_all timed), the CPU window's said. --poll and --presence-every set the
uplink's POLL and the plane's PRESENCE_EVERY. --measures-out FILE keeps
every figure as JSON. The hook is a sitecustomize on the PYTHONPATH of every
process the bench starts; none of it is in the scripts measured.

--idle-gate judges the run by its --pycalls counts and not by B2's gate:
the idle uplink's Python-function calls and file calls a second, each under
its limit (IDLE_GATE_PYTHON, IDLE_GATE_FILE) and at least IDLE_GATE_FLOOR of
it (less is an uplink that stopped doing its work), the uplink's ticks a
second (Link.tick's calls in the window, printed beside the counts) inside
IDLE_GATE_TICKS, and no line of daemon.log saying "failed". A count holds on
a loaded or slow machine, as a CPU share does not: it moves only with the
ticks a second, a few percent, which is why the limits are read on the
runner class that judges and a run outside the band is not judged. The
gate's run, as the `sminos-idle` gate makes it:

    python3 bench_scale.py run <scripts-dir> --preset macbook --words 0 --working 30 \
        --warmup 60 --seconds 10 --pycalls 60 --idle-gate

The counting window is 60 s so that it holds one whole member round (the
loop's longest period) wherever it falls.
"""

import argparse
import datetime
import json
import os
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ORG, MACHINE, OTHER = "org-1", "testhost", "mini"
HUB_ROOTED = ("doperpowers", "MAWS", "desk-walk", "scratch")
EPOCH = datetime.datetime(2026, 10, 18)   # the events' clock: its first event a second after

# The counts read on each Mac (2026-11-12), as this machine's flags. Where a
# Mac's count was not read, the MacBook's stands in (the mini's open
# projects, host stores, own writers, log volume), and the mini has no
# former name: its report says which. The member rows are each Mac's
# published members (member frames a publish in its live uplink's profile:
# 57 on the MacBook, 96 on the mini), made up of its live sessions and as
# many seats as the rest.
PRESETS = {
    "macbook": dict(dirs=1650, seats=73, live=15, gone=27, local=25, rooted=20, followed=36, retired=20, remote=12,
                    says=700, own=36, refused=26, seat_members=42, records=251, bridges=12, answering=10,
                    host_projects=8, host_files=78, host_events=3900, former="oldbook", former_sessions=17,
                    big_log=30000, seat_brief=3000, age=3.0, working=3.0, tcc=True, subs=0),
    # The mini's own counts, read there: 88 projects, 555 own writer files, 3,002 files under the logs, 6
    # host stores of 52 files, 1,510 engine project directories, 11 transcript subscriptions held open by a
    # MAWS window (11 `plane-transcript` threads in a sample of its uplink); its 14 bridge sockets make 14 of its
    # 21 engine records live sessions (a socket is a running session's).
    "mini": dict(dirs=1480, seats=205, live=14, gone=7, local=9, rooted=15, followed=43, retired=19, remote=39,
                 says=700, own=32, refused=20, seat_members=82, records=150, bridges=14, answering=12,
                 host_projects=6, host_files=52, host_events=2600, former="", former_sessions=0,
                 big_log=30000, seat_brief=3000, age=3.0, working=3.0, tcc=True, subs=11),
}

# The bench's hook, a sitecustomize on the PYTHONPATH of every process it
# starts: what it sets from outside the scripts, each by an environment
# variable, applied as each sminos module is imported (and to __main__ when
# that is sminos.py). Nothing in it is the scripts' own.
HOOK = r'''
import importlib.abc
import importlib.machinery
import json
import os
import sys
import time

KNOBS = {"sminos": [("TCC", "BENCH_TCC", lambda v: v == "1")],
         "sminos_uplink": [("POLL", "BENCH_POLL", float)],
         "sminos_plane": [("PRESENCE_EVERY", "BENCH_PRESENCE_EVERY", float)]}


# The passes timed in the profile's window, each call's CPU time on its own thread (inclusive of what it
# calls): (class or None for a module function, name). Absent ones (another version's) are passed by.
PASSES = {"sminos_uplink": [("Link", n) for n in (
              "tick", "members", "publish_members", "upload_pass", "upload", "deliveries", "host_pass",
              "machine_presence", "leave_pass", "sync_policy", "words_pass", "ask_words", "relay_requests",
              "relay_rpcs", "deliver_imports", "post_session")] + [(None, "hub_projects")],
          "sminos_plane": [("Plane", n) for n in ("tick", "presence", "stale", "reread", "refresh")]
              + [("Records", "scan"), ("Subscription", "pump"), ("Bridges", "probe"), ("Bridges", "answers"),
                 ("Warmer", "tick"), ("Transcript", "work"), ("Disk", "meta"), ("Disk", "facts"), (None, "look")]}
TIMED, ON = {}, [False]


def timed(label, fn):
    def call(*args, **kwargs):
        if not ON[0]:
            return fn(*args, **kwargs)
        t = time.thread_time_ns()
        try:
            return fn(*args, **kwargs)
        finally:
            r = TIMED.setdefault(label, [0, 0])
            r[0] += 1
            r[1] += time.thread_time_ns() - t
    return call


def time_passes(name, mod):
    for cls, fn in PASSES.get(name, ()):
        owner = getattr(mod, cls, None) if cls else mod
        if owner is not None and callable(getattr(owner, fn, None)):
            setattr(owner, fn, timed("%s.%s" % (cls or name, fn), getattr(owner, fn)))


def patch(name, mod):
    if os.environ.get("BENCH_PROFILE") and name in PASSES and not hasattr(mod, "_bench_passes"):
        time_passes(name, mod)
        mod._bench_passes = True
    for attr, var, conv in KNOBS.get(name, ()):
        if os.environ.get(var):
            setattr(mod, attr, conv(os.environ[var]))
    if name == "sminos_daemon" and os.environ.get("BENCH_TICK_TIMES") and not hasattr(mod, "_bench_timed"):
        real, path = mod.tick_all, os.environ["BENCH_TICK_TIMES"]

        def tick_all(*args, **kwargs):
            at, cpu = time.time(), time.process_time()
            try:
                return real(*args, **kwargs)
            finally:
                with open(path, "a") as f:
                    f.write(json.dumps({"at": at, "wall": time.time() - at, "cpu": time.process_time() - cpu,
                                        "pid": os.getpid()}) + "\n")
        mod.tick_all, mod._bench_timed = tick_all, True


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if not name.startswith("sminos"):
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or spec.loader is None:
            return spec
        real = spec.loader.exec_module

        def exec_module(module):
            real(module)
            patch(name, module)
            main = sys.modules.get("__main__")
            if main is not None and str(getattr(main, "__file__", "")).endswith("sminos.py"):
                patch("sminos", main)
        spec.loader.exec_module = exec_module
        return spec


sys.meta_path.insert(0, Finder())

def thread_ticks():
    """{native id: (thread name, its CPU clock ticks)} of the threads running
    now, and the whole process's ticks under the key None (Linux's /proc)."""
    import threading
    out = {}
    for tid, name in [(None, "")] + [(t.native_id, t.name) for t in threading.enumerate()]:
        try:
            with open("/proc/self/stat" if tid is None else "/proc/self/task/%d/stat" % tid) as f:
                fields = f.read().rpartition(")")[2].split()
            out[tid] = (name, int(fields[11]) + int(fields[12]))
        except (OSError, ValueError, IndexError):
            pass
    return out


if os.environ.get("BENCH_PROFILE") and sys.argv[1:3] == ["daemon", "uplink"]:
    import signal
    held = {}

    def begin(*_):
        import cProfile
        if "pr" not in held:
            held["at"] = time.time()
            held["threads"] = thread_ticks()
            TIMED.clear()
            ON[0] = True
            held["pr"] = cProfile.Profile()
            held["pr"].enable()

    def end(*_):
        pr = held.pop("pr", None)
        if pr is None:
            return
        pr.disable()
        ON[0] = False
        now, before = thread_ticks(), held.pop("threads")
        tck = os.sysconf("SC_CLK_TCK")
        threads = {}
        for tid, (name, ticks) in now.items():
            if tid is not None:
                threads.setdefault(name, [0, 0.0])
                threads[name][0] += 1
                threads[name][1] += (ticks - before.get(tid, (name, 0))[1]) / tck
        whole = (now[None][1] - before[None][1]) / tck if None in now and None in before else None
        out = os.environ["BENCH_PROFILE"]
        pr.dump_stats(out + ".tmp")
        with open(out + ".window", "w") as f:
            json.dump({"from": held["at"], "to": time.time(), "cpu": whole, "threads": threads,
                       "passes": {k: {"calls": n, "cpu": ns / 1e9} for k, (n, ns) in TIMED.items()}}, f)
        os.replace(out + ".tmp", out)
    signal.signal(signal.SIGUSR1, begin)
    signal.signal(signal.SIGUSR2, end)
'''


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
        self.servers = []
        self.stopping = threading.Event()
        self.n = 0
        self.seqs = {}
        self.build(hub_url)

    def uid(self):
        return str(uuid.UUID(int=self.rnd.getrandbits(128), version=4))

    def ts(self):
        self.n += 1
        return (EPOCH + datetime.timedelta(seconds=self.n)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

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
        for name in (HUB_ROOTED + tuple("hub%d" % i for i in range(len(HUB_ROOTED), a.rooted)))[:a.rooted]:
            pid = self.uid()
            hubs[name] = (pid, self.repo(name, {"project": pid, "name": name, "hub": {"org": ORG}}))
            self.register(pid, name, hubs[name][1])
        own, mini = machine_project_id(ORG, MACHINE), machine_project_id(ORG, OTHER)
        follows = [self.uid() for _ in range(a.followed)]
        self.register(own, MACHINE, "")
        self.register(mini, OTHER, "")
        names = {p: n for n, (p, _) in hubs.items()}
        names.update({own: MACHINE, mini: OTHER})
        for i, follow in enumerate(follows):
            # Hub projects of the org with no checkout here, which the uplink opens to read and deliver.
            names[follow] = "phone walk" if i == 0 else "followed%d" % i
            self.register(follow, names[follow], "")
        self.rooted_ids = [p for p, _ in hubs.values()]
        self.hub_ids = self.rooted_ids + [own, mini] + follows
        # Hub projects the org's directory retired: registered, each with the uplink.json it kept when open.
        self.retired_ids = [self.uid() for _ in range(a.retired)]
        for i, pid in enumerate(self.retired_ids):
            names[pid] = "retired%d" % i
            self.register(pid, names[pid], "")
            write(os.path.join(self.sh, "projects", pid, "uplink.json"), {"host_sent": {}, "voided": {}, "dead": {}})
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
        # Seats: most retired or long idle, and most of those without a transcript here. The first REFUSED
        # in a folder macOS protects (~/Documents), which the uplink may not read (with --tcc, as on macOS):
        # where each is is told from the writer files this machine holds of it, under its name now or, for
        # the first FORMER_SESSIONS, a former one. SEAT_MEMBERS of the rest, when given, are not retired
        # (the daemon's tick joins each where its directory resolves), the others retired.
        self.member_seats, self.refused_seats, self.former_held, self.seat_targets = [], [], [], []
        for i in range(a.seats):
            sid = self.uid()
            refused = i < a.refused
            if refused:
                cwd = os.path.join(self.home, "Documents", "work%d" % (i % 6))
                status = ("retired", "idle", "done")[i % 3]
                self.refused_seats.append(sid)
                held_in = [x for x in self.hub_ids if x not in (own, mini)] or self.hub_ids
                pid = held_in[i % len(held_in)]
                former = i < a.former_sessions and a.former
                if former:
                    self.former_held.append(sid)
                self.log(pid, "%s/%s" % (a.former if former else MACHINE, sid), [
                    {"kind": "joined", "session": sid, "alias": "seat%d" % i, "name_source": "derived",
                     "machine": a.former if former else MACHINE, "cwd": cwd, "session_kind": "interactive"},
                    {"kind": "retired", "session": sid, "by": "", "reason": "ended"}])
            else:
                cwd = cwds[i % len(cwds)]
                if a.seat_members is None:
                    status = ("retired", "idle", "done")[i % 3]
                else:
                    status = "idle" if i - a.refused < a.seat_members else "retired"
                if status != "retired":
                    self.member_seats.append(sid)
            missing = (i % 10) < a.missing
            if not refused and status != "retired" and not missing and cwd in project_of:
                self.seat_targets.append({"sid": sid, "project": project_of[cwd]})
            if not missing:
                self.transcript(cwd, sid, "seat work %d" % i)
            seat = {"alias": "seat%d" % i, "group": "fleet", "current": sid, "cwd": cwd, "status": status,
                    "host": "" if missing else MACHINE, "created": self.ts(), "updated": self.ts(), "role": "",
                    "worktree": ""}
            if a.seat_brief:
                seat["brief"] = "a seat's brief " + "b" * a.seat_brief
            write(os.path.join(self.sh, "%s.json" % self.uid()), seat)
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
            p = spawn(["sleep", "86399"], start_new_session=True, stdin=subprocess.DEVNULL,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.sleepers.append(p)
            rec = {"pid": p.pid, "sessionId": sid, "cwd": cwd, "kind": "interactive", "entrypoint": "cli",
                   "status": "idle", "name": "live%d" % i, "nameSource": "derived",
                   "updatedAt": int(time.time() * 1000)}
            path = os.path.join(self.home, ".claude", "sessions", "%d.json" % p.pid)
            write(path, rec)
            self.live_sessions.append({"sid": sid, "cwd": cwd, "size": size, "project": project_of.get(cwd, own),
                                       "pid": p.pid, "engine": path, "rec": rec})
        # Engine records of sessions whose process is gone (each a pid that ran and was reaped).
        for i in range(a.gone):
            p = subprocess.Popen(["true"])
            p.wait()
            write(os.path.join(self.home, ".claude", "sessions", "%d.json" % p.pid), {
                "pid": p.pid, "sessionId": self.uid(), "cwd": cwds[i % len(cwds)], "kind": "interactive",
                "entrypoint": "cli", "status": "idle", "name": "gone%d" % i, "nameSource": "derived",
                "updatedAt": int(time.time() * 1000) - 86400000})
        # This machine's own history in its hub checkouts: sessions that joined, worked and ended.
        self.own_sids = {}
        for pid, d in hubs.values():
            for _ in range(a.own):
                sid = self.uid()
                self.own_sids.setdefault(pid, []).append(sid)
                self.log(pid, "%s/%s" % (MACHINE, sid), [
                    {"kind": "joined", "session": sid, "alias": "past", "name_source": "derived",
                     "machine": MACHINE, "cwd": d, "session_kind": "interactive"},
                    {"kind": "state", "session": sid, "state": "working", "machine": MACHINE},
                    {"kind": "say", "session": sid, "to": [], "text": "done " + "x" * 120},
                    {"kind": "retired", "session": sid, "by": "", "reason": "ended"}])
        # Members of the other machine, in every hub project (its own project most of all).
        for pid in self.hub_ids:
            n = a.mini if pid == mini else a.remote
            self.remote_members(pid, n, a.says if pid != mini else 0)
        for pid in self.retired_ids:
            self.remote_members(pid, 2, 0)
        if a.big_log and follows:
            # One log of tens of thousands of events: two machines' title loop over one session (manim-master's).
            sid = self.uid()
            self.log(follows[0], "%s/%s" % (OTHER, sid), [{"kind": "titled", "session": sid, "title": "loop %d" % k}
                                                          for k in range(a.big_log)])
        # `run`: a person's words owed to each live session in a hub checkout, one event from each of WORDS
        # members' devices, stored as an arrival over RL10 is (its signer under `verified`).
        self.words_owed = 0
        if a.mode == "run":
            for i, s in enumerate(x for x in self.live_sessions if x["project"] in project_of.values()):
                self.words_owed += a.words
                for k in range(a.words):
                    self.log(s["project"], "hub/mem-%d" % k, [{
                        "kind": "human", "from": "member %d" % k, "member": "mem-%d" % k,
                        "to": [{"session": s["sid"], "alias": "live%d" % i}], "text": "words %d for %d" % (k, i),
                        "verified": {"signer": {"kind": "device", "member": "mem-%d" % k, "device": "dev-%d" % k,
                                                "keyId": "k-dev-%d" % k}}}])
        self.session_records(a)
        self.host_stores(a, [p for p, _ in hubs.values()])
        # Its enrolment. `run`, `opens` and `shape` cut the machine over by the endpoint stand-in's welcome to a
        # probe, so before it the machine is named by DAEMON_HOST alone (below); `tick`, `profile` and `verbs`
        # measure a machine cut over, as the owner's Macs are.
        if a.mode not in ("run", "opens", "shape"):
            from rl10_identity import write_identity
            write_identity(self.sh, MACHINE, org=ORG, hub=hub_url,
                           former={a.former: sorted(self.former_held)} if self.former_held else None)
        write(os.path.join(self.sh, "daemon", "org.json"), {
            "projects": [{"id": p, "name": names[p], "kind": "machine" if p in (own, mini) else "hub",
                          "retired": p in self.retired_ids} for p in self.hub_ids + self.retired_ids],
            "machines": [{"name": MACHINE, "online": True, "seen": None}, {"name": OTHER, "online": True, "seen": None}],
            "at": "2026-10-18T00:00:00.000Z"})
        stub = os.path.join(self.root, "bin")
        os.makedirs(stub, exist_ok=True)
        with open(os.path.join(stub, "claude"), "w") as f:
            f.write('#!/bin/sh\ncase "$1" in agents) echo "[]";; esac\nexit 0\n')
        os.chmod(os.path.join(stub, "claude"), 0o755)
        site = os.path.join(self.root, "site")
        os.makedirs(site, exist_ok=True)
        with open(os.path.join(site, "sitecustomize.py"), "w") as f:
            f.write(HOOK)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("CLAUDE_CODE_", "SMNS_", "SMINOS_", "DAEMON_", "BENCH_", "PYTHON"))}
        self.env.update(HOME=self.home, SMINOS_HOME=self.sh, PATH=stub + os.pathsep + os.environ["PATH"],
                        SMINOS_DERIVE_EVERY="0", DAEMON_HOST=MACHINE, PYTHONPATH=site)
        if a.tcc:
            self.env["BENCH_TCC"] = "1"
        if a.mode == "run":
            self.env["BENCH_TICK_TIMES"] = os.path.join(self.root, "ticks.jsonl")
            if a.poll:
                self.env["BENCH_POLL"] = str(a.poll)
            if a.presence_every:
                self.env["BENCH_PRESENCE_EVERY"] = str(a.presence_every)
            if a.pycalls:
                self.env["BENCH_PROFILE"] = os.path.join(self.root, "uplink.prof")
        if a.age:
            # The history as old as on the Macs: no writer file changed within HOT_FOR (what a hot look
            # skips), no directory just made (what a kept listing waits out).
            then = time.time() - a.age * 86400
            for top in (self.sh, self.projects):
                for d, _, files in os.walk(top):
                    for name in files:
                        os.utime(os.path.join(d, name), (then, then))
                    os.utime(d, (then, then))
        self.bridges(a)
        if a.working:
            threading.Thread(target=self.working, args=(a.working,), daemon=True).start()

    def session_records(self, a):
        """RECORDS session records (what the hooks write for each session): the
        live sessions' and the member seats' first, then those of sessions long
        gone."""
        sids = [s["sid"] for s in self.live_sessions] + self.member_seats + self.refused_seats
        sids = sids[:a.records]
        sids += [self.uid() for _ in range(a.records - len(sids))]
        for sid in sids:
            write(os.path.join(self.sh, "session-records", sid + ".json"), {
                "session": sid, "origin": {"kind": "terminal"}, "owners": ["@machine"], "ownersProof": [],
                "principal": "@machine", "inference": {"kind": "slot", "configDir": os.path.join(self.home, ".claude")},
                "source": "hook", "basis": "hook", "created": self.ts(), "updated": self.ts()})

    def host_stores(self, a, rooted):
        """HOST_FILES host files (what sessions sent their person, the host
        store of a cut-over machine) over the first HOST_PROJECTS hub
        checkouts, HOST_EVENTS events in all, each written under one of the
        project's own ended sessions, every one gone up already: uplink.json
        holds each file's last seq as its cursor."""
        projects = rooted[:a.host_projects]
        if not projects or not a.host_files:
            return
        per = max(1, a.host_events // a.host_files)
        for k in range(a.host_files):
            pid = projects[k % len(projects)]
            sids = self.own_sids.get(pid) or [self.uid()]
            sid = sids[(k // len(projects)) % len(sids)]
            writer = "%s/%s" % (MACHINE, sid)
            rows = [{"ts": self.ts(), "writer": writer, "seq": seq, "kind": "message", "session": sid,
                     "text": "to the person %d " % seq + "m" * 1400} for seq in range(1, per + 1)]
            jsonl(os.path.join(self.sh, "projects", pid, "host", writer.replace("/", ".") + ".jsonl"), rows)
            state = os.path.join(self.sh, "projects", pid, "uplink.json")
            try:
                with open(state) as f:
                    d = json.load(f)
            except OSError:
                d = {"host_sent": {}, "voided": {}, "dead": {}}
            d["host_sent"][writer] = per
            write(state, d)

    def bridges(self, a):
        """A bridge socket for each of the first BRIDGES live sessions, the
        first ANSWERING of them answering from a thread of this process
        `GET /status` (DX5) and `GET /events`, the requests' stream, held
        open after its snapshot of nothing pending, as a quiet session's
        bridge holds it; the rest a socket nothing listens on (a child gone)."""
        import http.server
        import socketserver
        d = os.path.join(self.sh, "bridge")
        for i, s in enumerate(self.live_sessions[:a.bridges]):
            os.makedirs(d, mode=0o700, exist_ok=True)
            path = os.path.join(d, s["sid"] + ".sock")
            if i >= a.answering:
                dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                dead.bind(path)
                dead.close()
                continue
            body = json.dumps({"session": s["sid"], "pid": s["pid"], "launch": "launch-%d" % i,
                               "capabilities": {"send": True, "interrupt": True, "ask": True},
                               "permissionMode": "default", "permissionModeAt": 1760000000000}).encode()

            class Status(http.server.BaseHTTPRequestHandler):
                protocol_version = "HTTP/1.1"
                data, stopping = body, self.stopping
                # A quiet session's bridge snapshot (sminos_bridge's Child.snapshot): nothing streaming,
                # nothing pending, its named blocks kept.
                snapshot = (json.dumps({
                    "type": "snapshot", "session": s["sid"], "protocol": 1, "pid": s["pid"], "sessionInfo": {},
                    "turns": [], "streaming": [], "agents": [], "usage": None, "override": None,
                    "capabilities": {"send": True, "interrupt": True, "ask": True}, "cut": {},
                    "namedBlocks": True, "pending": [], "settled": []}) + "\n").encode()

                def do_GET(self):
                    if self.path == "/events":
                        self.send_response(200)
                        self.send_header("content-type", "application/x-ndjson")
                        self.end_headers()
                        self.wfile.write(self.snapshot)
                        self.wfile.flush()
                        self.stopping.wait()
                        self.close_connection = True
                        return
                    self.send_response(200)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(self.data)))
                    self.send_header("connection", "close")
                    self.end_headers()
                    self.wfile.write(self.data)
                    self.close_connection = True

                def log_message(self, *args):
                    pass

            srv = socketserver.ThreadingUnixStreamServer(path, Status)
            srv.daemon_threads = True
            threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True).start()
            self.servers.append(srv)

    def working(self, every):
        """The first live session's engine record rewritten every `every`
        seconds, whole, by rename, as the engine does for a session at work."""
        s = self.live_sessions[0]
        while not self.stopping.wait(every):
            s["rec"].update(status="busy", updatedAt=int(time.time() * 1000))
            write(s["engine"] + ".tmp", s["rec"])
            os.replace(s["engine"] + ".tmp", s["engine"])

    def close(self):
        self.stopping.set()
        for srv in self.servers:
            srv.shutdown()
            srv.server_close()
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
    p.add_argument("--own", type=int, default=150, help="this machine's ended sessions in each hub checkout")
    p.add_argument("--preset", choices=sorted(PRESETS), help="a Mac's shape (PRESETS); a flag given beside it wins")
    p.add_argument("--rooted", type=int, default=len(HUB_ROOTED), help="hub projects with a checkout here")
    p.add_argument("--followed", type=int, default=1, help="hub projects of the org with no checkout here")
    p.add_argument("--retired", type=int, default=0, help="hub projects the org retired, each with its uplink.json")
    p.add_argument("--refused", type=int, default=0,
                   help="of the seats, how many work in ~/Documents (a folder macOS protects)")
    p.add_argument("--tcc", action="store_true",
                   help="read macOS's protected folders as macOS would (sminos.TCC on in every sminos process)")
    p.add_argument("--seat-members", type=int, default=None, metavar="N",
                   help="of the other seats, how many are not retired (default: one in three retired)")
    p.add_argument("--seat-brief", type=int, default=0, metavar="BYTES", help="each seat record's brief")
    p.add_argument("--former", default="", metavar="NAME", help="a name this machine wrote under before")
    p.add_argument("--former-sessions", type=int, default=0, metavar="N",
                   help="of the refused seats, how many hold their writer file under the former name")
    p.add_argument("--records", type=int, default=0, help="session records (the live sessions' and seats' first)")
    p.add_argument("--gone", type=int, default=0, help="engine records of sessions whose process is gone")
    p.add_argument("--bridges", type=int, default=0, help="live sessions with a bridge socket")
    p.add_argument("--answering", type=int, default=0, help="of those, how many answer GET /status")
    p.add_argument("--host-projects", type=int, default=0, help="hub checkouts with a host store")
    p.add_argument("--host-files", type=int, default=0, help="host files over those")
    p.add_argument("--host-events", type=int, default=0, help="host events over those files")
    p.add_argument("--big-log", type=int, default=0, metavar="N", help="one followed project's log of N events")
    p.add_argument("--age", type=float, default=0, metavar="DAYS", help="the history's files this old")
    p.add_argument("--working", type=float, default=0, metavar="S",
                   help="one live session's engine record rewritten every S seconds")
    p.add_argument("--keep", action="store_true", help="leave the synthetic machine on disk")
    p.add_argument("--joined-by", metavar="SCRIPTS", help="make the first tick with this copy of the scripts")


def in_process(env, scripts):
    """The scripts imported here, against the synthetic machine."""
    os.environ.clear()
    os.environ.update(env.env)
    sys.path.insert(0, os.path.abspath(scripts))
    import sminos
    if env.a.tcc:
        sminos.TCC = True
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
    """A process's CPU time so far (user + system): from /proc where there is
    one (clock ticks, a hundredth of a second), else from ps, which prints
    hundredths on macOS and whole seconds on Linux — over a 60 s window a
    whole second is 1.7 % of a core, coarser than the 5 % gate can be read by."""
    try:
        with open("/proc/%d/stat" % pid) as f:
            fields = f.read().rpartition(")")[2].split()   # after the command's name, which may hold spaces
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")   # utime, stime
    except (OSError, ValueError, IndexError):
        pass
    out = run_child(["ps", "-o", "time=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    if not out:
        return None
    days, _, rest = out.rpartition("-")
    parts = [float(x) for x in rest.split(":")]
    secs = 0.0
    for x in parts:
        secs = secs * 60 + x
    return secs + (int(days) * 86400 if days else 0)


def ticks_ended(env):
    """The tick stamps now: daemon/ticked's mtime (each tick's end, from
    sminos 1.27.11), and every project's daemon.json's `tick` (each tick's,
    before: a copy of the scripts from then is measured too)."""
    out = set()
    try:
        out.add(("daemon/ticked", os.stat(os.path.join(env.sh, "daemon", "ticked")).st_mtime_ns))
    except OSError:
        pass
    root = os.path.join(env.sh, "projects")
    for pid in os.listdir(root):
        try:
            with open(os.path.join(root, pid, "daemon.json")) as f:
                out.add((pid, json.load(f).get("tick")))
        except (OSError, ValueError):
            pass
    return out


class EndpointStandin:
    """endpoint_standin.py serving the machine's RL10 socket, its identity
    complete (so its welcome cuts the machine over), answering no `words?`;
    `ctl` speaks to its control socket directly (a `send` is one frame
    down the live connection)."""

    IDENTITY = {"org": ORG, "hub": "http://127.0.0.1:9", "name": MACHINE, "former": [], "ref": "ref-" + MACHINE,
                "enrolled": "2026-10-01T00:00:00.000Z"}

    def __init__(self, env):
        self.dir = os.path.join(env.root, "ep")
        # A former name, as an endpoint that renamed the machine says it: the welcome's cut-over keeps the
        # sessions held under it this machine's (sminos_rl10.welcomed).
        identity = {**self.IDENTITY, "former": [env.a.former] if env.a.former else []}
        self.proc = spawn([sys.executable, os.path.join(HERE, "endpoint_standin.py"), "serve", self.dir,
                           json.dumps({"identity": identity})],
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


def import_burst(env, ep, n, give_up=120.0):
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
# The idle gate (`run --idle-gate`, on --preset macbook --words 0 --pycalls 60): the idle uplink's calls a second
# under cProfile. A count holds on a loaded or slow machine, where a CPU share does not, so a CI runner can judge it.
# The window is 60 s, the longest period in the loop (MEMBERS_WHOLE): a 20 s one read 46 k or 56 k as that round fell
# outside or inside it, a 60 s one 30,515, 30,513 and 30,516 Python-function calls and 2,694 file calls a second in
# each of three runs of sminos 1.46.3 at the presets' member rows of 2026-11-12 (1.46.2 read 50,263 and 2,789, 1.46.0
# 112,648 and 4,634). Each limit is the highest figure plus 10 %, rounded up to ten. A change that lowers the figures lowers the limits with it; one that must raise them says so in its diff.
# The counts still move a few percent with the runner's speed: the loop waits POLL after each tick ends, so the ticks a
# second are 1 / (POLL + a tick's length), and the per-tick work moves with them. So the limits are set from figures
# read on the runner class that judges (the sminos-idle gate's), the gate judges no run whose ticks a second fall
# outside IDLE_GATE_TICKS (a runner on which the counts cannot be judged), and a count under IDLE_GATE_FLOOR of its
# limit fails too: an uplink doing less than an idle one does has stopped doing its work (Link.tick catches a pass's
# exception and goes on), as has one whose daemon.log says "failed".
IDLE_GATE_PYTHON, IDLE_GATE_FILE = 33570, 2970
IDLE_GATE_TICKS, IDLE_GATE_FLOOR = (3.0, 4.0), 0.6
IDLE_FILE_CALLS = ("posix.stat>", "posix.lstat>", "posix.fstat>", "'stat' of 'posix.DirEntry'", "posix.scandir>",
                   "posix.listdir>", "_io.open>", "posix.open>", "posix.readlink>", "posix.getcwd>")


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


def cmd_run(a, env):
    """`run`: see the module's docstring. Exit status 1 when B2's gate fails."""
    ep = EndpointStandin(env)
    times = os.path.join(env.root, "words-passes.jsonl")
    env.env["SMINOS_WORDS_TIMES"] = times
    run = None
    try:
        log = open(os.path.join(env.root, "run.out"), "w")
        # Cut over first, by the stand-in's welcome to a probe (what `daemon run`'s supervisor runs): a first
        # tick before it would deliver the owed words as a machine not cut over does, before the probe's welcome.
        run_child([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "probe"], env=env.env,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not cut_over(env):
            print("the endpoint stand-in's welcome did not cut the machine over")
            return 1
        if a.profile_uplink:
            # Joined by a tick, then the uplink alone under cProfile.
            run_child([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "tick"], env=env.env,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            run = spawn([sys.executable, os.path.abspath(__file__), "_profiled", a.scripts,
                         a.profile_uplink, "daemon", "uplink"], env=env.env, stdout=log,
                        stderr=subprocess.STDOUT)
            time.sleep(a.warmup + a.seconds)
            return 0
        run = spawn([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "run", "--interval",
                     "5"], env=env.env, stdout=log, stderr=subprocess.STDOUT)
        began = time.time()
        subs = hold_subscriptions(env, ep, a.subs, began + a.warmup) if a.subs else []
        time.sleep(max(0.0, began + a.warmup - time.time()))
        status = run_child([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "status"],
                           env=env.env, capture_output=True, text=True).stdout
        if not cut_over(env) or "uplink: RL10 (local-only), running" not in status:
            print("after the %.0f s warm-up the machine is not on RL10: %s" % (
                a.warmup, next((x for x in status.splitlines() if x.startswith("uplink")), "no uplink line")))
            return 1
        up = int(open(os.path.join(env.sh, "daemon", "uplink.lock")).read().split()[1])
        held = subscription_states(ep, subs) if subs else None
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
        if subs:
            print("subscriptions: %d of %d asked, %d snapshots before the CPU window, %d ended by its end%s" % (
                held["asked"], a.subs, held["snapshots"], subscription_states(ep, subs)["ended"],
                "" if held["asked"] == a.subs else " (fewer sessions to subscribe to than asked)"))
        ticks = tick_rows(env, run.pid, t0, t1)
        measures = {"preset": a.preset, "scripts": os.path.abspath(a.scripts), "window": dt, "warmup": a.warmup,
                    "poll": a.poll, "presence_every": a.presence_every, "load1": os.getloadavg()[0],
                    "subs": {"asked": a.subs, **(held or {})},
                    "cpu": {"daemon run": 100 * (r1 - r0) / dt, "uplink": uplink_share,
                            "stand-in": 100 * (e1 - e0) / dt},
                    "words": {"wall": spread(walls), "gap": gap},
                    "ticks": {"wall": spread([r["wall"] for r in ticks]), "cpu": spread([r["cpu"] for r in ticks])}}
        if ticks:
            print("daemon run ticks: %d in the window; wall p50 %.3f s, p95 %.3f s, max %.3f s; CPU p50 %.3f s, "
                  "p95 %.3f s" % (len(ticks), measures["ticks"]["wall"]["p50"], measures["ticks"]["wall"]["p95"],
                                  measures["ticks"]["wall"]["max"], measures["ticks"]["cpu"]["p50"],
                                  measures["ticks"]["cpu"]["p95"]))
        # Each in a window of its own, after the CPU window: none of them is in its figure.
        if a.strace:
            measures["strace"] = strace_window(env, up, a.strace)
            print_strace(measures["strace"])
        if a.pycalls:
            measures["pycalls"] = pycalls_window(env, up, a.pycalls, a.pycalls_prof)
            print_pycalls(measures["pycalls"])
        if subs:
            measures["subs"]["ended after the windows"] = subscription_states(ep, subs)["ended"]
        if a.nudges:
            measures["nudges"] = nudged = nudge_window(env, run.pid, a.nudges)
            print("nudged ticks: %d of %d; wall %s; began after the nudge %s; ended after it %s" % (
                len(nudged), a.nudges, " ".join("%.3f" % r["wall"] for r in nudged),
                " ".join("%.3f" % r["began"] for r in nudged), " ".join("%.3f" % r["ended"] for r in nudged)))
        if a.import_events:
            took, got = import_burst(env, ep, a.import_events)
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
        gate = "O14 B2 step 2"
        if a.idle_gate:
            gate, pc = "idle counts", measures.get("pycalls") or {}
            files = sum(n for k, n in (pc.get("file") or {}).items() if any(x in k for x in IDLE_FILE_CALLS))
            lo, hi = IDLE_GATE_TICKS
            tps = pc.get("ticks_a_second")

            def counted(what, n, limit):
                floor = IDLE_GATE_FLOOR * limit
                return ("%s %d to %d a second" % (what, floor, limit), bool(pc) and floor <= n < limit,
                        "no profile" if not pc else "%.0f%s" % (n, ": less than an idle uplink does" if n < floor
                                                               else ""))
            checks = [("the uplink ticking %g to %g times a second, a runner on which the counts can be judged"
                       % (lo, hi), tps is not None and lo <= tps <= hi,
                       "no profile" if not pc else "Link.tick not timed" if tps is None else
                       "%.2f a second%s" % (tps, "" if lo <= tps <= hi else ": the counts cannot be judged here")),
                      counted("the idle uplink's Python-function calls", pc.get("python", 0), IDLE_GATE_PYTHON),
                      counted("its file calls", files, IDLE_GATE_FILE),
                      ("daemon.log without a failure", not failed,
                       "%d, the first: %s" % (len(failed), failed[0].strip()) if failed else "none")]
        for what, ok, said in checks:
            print("gate: %s: %s (%s)" % (what, "ok" if ok else "FAILED", said))
        ok = all(c[1] for c in checks)
        if a.measures_out:
            measures["gate"] = {what: [bool(ok_), said] for what, ok_, said in checks}
            write(a.measures_out, measures)
        print("gate (%s): %s" % (gate, "PASS" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        if run is not None:
            run.send_signal(signal.SIGTERM)
            try:
                run.wait(60)
            except subprocess.TimeoutExpired:
                run.kill()
        ep.stop()


def hold_subscriptions(env, ep, n, by):
    """`n` subscriptions to sessions' transcripts, sent down the uplink's
    stream by the stand-in once that stream has opened their projects (by
    `by` at the latest): the live sessions in hub checkouts first, then the
    member seats with a transcript. Never unsubscribed. [(project, sub)]."""
    import base64
    targets = [s for s in env.live_sessions if s["project"] in env.rooted_ids] + env.seat_targets
    targets = targets[:n]
    pids = {s["project"] for s in targets}
    while time.time() < by:
        o = ep.ctl("opened")
        if o.get("conn") is not None and pids <= set(o.get("projects") or ()):
            break
        time.sleep(0.5)
    out = []
    for s in targets:
        sub = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
        ep.ctl("send", {"frames": [{"t": "subscribe", "project": s["project"], "session": s["sid"], "agentId": None,
                                    "sub": sub}]})
        out.append((s["project"], sub))
    return out


def subscription_states(ep, subs):
    """How many of `subs` the stand-in has had a snapshot for, and how many an
    `end` for, from what it received."""
    mine = {sub for _, sub in subs}
    snaps, ends = set(), set()
    for r in ep.ctl("state")["received"]:
        m = r["frame"].get("message") if r["frame"].get("t") == "session" else None
        if isinstance(m, dict) and m.get("sub") in mine:
            (snaps if m.get("kind") == "snapshot" else ends if m.get("kind") == "end" else set()).add(m["sub"])
    return {"asked": len(subs), "snapshots": len(snaps), "ended": len(ends)}


def spread(xs):
    """{n, p50, p95, max} of a list of numbers ({n: 0} for none)."""
    xs = sorted(xs)
    return {"n": len(xs), "p50": percentile(xs, 50), "p95": percentile(xs, 95), "max": xs[-1]} if xs else {"n": 0}


def tick_rows(env, pid, t0, t1):
    """The `daemon run` ticks (pid's) the hook timed that began in [t0, t1]."""
    try:
        with open(env.env["BENCH_TICK_TIMES"]) as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except (OSError, KeyError):
        return []
    return [r for r in rows if r["pid"] == pid and t0 <= r["at"] <= t1]


# What strace shows that is no file call: waits, signals, memory, threads, sockets, the clock.
NOT_FILE = frozenset((
    "futex", "poll", "ppoll", "epoll_wait", "epoll_pwait", "epoll_pwait2", "epoll_ctl", "epoll_create1", "select",
    "pselect6", "clock_nanosleep", "nanosleep", "clock_gettime", "gettimeofday", "wait4", "waitid", "rt_sigaction",
    "rt_sigprocmask", "rt_sigreturn", "sigaltstack", "getpid", "gettid", "getppid", "getuid", "geteuid", "getgid",
    "getegid", "mmap", "munmap", "mprotect", "madvise", "mremap", "brk", "clone", "clone3", "set_robust_list",
    "rseq", "exit", "exit_group", "socket", "socketpair", "connect", "bind", "listen", "accept", "accept4",
    "getsockopt", "setsockopt", "getsockname", "getpeername", "sendto", "recvfrom", "sendmsg", "recvmsg",
    "sendmmsg", "recvmmsg", "shutdown", "getrandom", "sched_yield", "sched_getaffinity", "kill", "tgkill", "prctl",
    "pidfd_open", "pidfd_send_signal", "prlimit64", "uname", "sysinfo", "getrusage", "times", "eventfd2", "pipe2",
    "dup", "dup2", "dup3", "restart_syscall"))
PATH_CALLS = frozenset((
    "openat", "open", "newfstatat", "stat", "lstat", "statx", "access", "faccessat", "faccessat2", "readlink",
    "readlinkat", "mkdir", "mkdirat", "unlink", "unlinkat", "rename", "renameat", "renameat2", "utimensat", "chdir",
    "statfs", "truncate", "execve", "connect", "chmod", "fchmodat", "getcwd"))
STRACE_LINE = re.compile(r"(\d+) +(\d+\.\d+) (.*)")
QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
RESUMED = re.compile(r"<\.\.\. (\w+) resumed>(.*)")
ERRNO = re.compile(r"= -1 (E[A-Z]+)")
UUID_ANY = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def path_pattern(path, marks):
    """A path as the evidence's tables name it: the synthetic SMINOS_HOME
    `$S`, HOME `~`, its root `$R`; a project `<p>`, an engine project
    directory `<dir>`, a checkout `<repo>`, a session or seat `<uuid>`."""
    for root, mark in marks:
        if path == root or path.startswith(root + "/"):
            path = mark + path[len(root):]
            break
    for rx, to in ((r"^(\$S/projects/)[^/]+", r"\1<p>"), (r"^(~/\.claude/projects/)[^/]+", r"\1<dir>"),
                   (r"^(~/\.claude/sessions/)\d+", r"\1<pid>"), (r"^(\$R/r/)[^/]+", r"\1<repo>"),
                   (r"^(~/Documents/)[^/]+", r"\1<d>"), (r"^/proc/\d+", "/proc/<pid>")):
        path = re.sub(rx, to, path)
    return UUID_ANY.sub("<uuid>", path)


def ptrace_scoped():
    try:
        with open("/proc/sys/kernel/yama/ptrace_scope") as f:
            return int(f.read()) > 0
    except (OSError, ValueError):
        return False


def strace_window(env, pid, seconds):
    """The uplink's system calls for `seconds` (strace -f attached to it,
    through `sudo -n` where ptrace is scoped to descendants), a second by
    kind and by path pattern; the attaching and the detaching left out."""
    out = os.path.join(env.root, "uplink.strace")
    cmd = ["strace", "-f", "-qq", "-ttt", "-s", "256", "-o", out, "-p", str(pid)]
    if os.geteuid() != 0 and ptrace_scoped():
        cmd = ["sudo", "-n"] + cmd
    p = spawn(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    t0 = time.time()
    time.sleep(seconds)
    t1 = time.time()
    p.send_signal(signal.SIGINT)
    try:
        p.wait(60)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
    return strace_summary(env, out, t0, t1)


def strace_summary(env, path, t0, t1):
    import collections
    kinds, patterns, pending = collections.Counter(), collections.Counter(), {}
    marks = sorted(((env.sh, "$S"), (env.home, "~"), (env.root, "$R")), key=lambda m: -len(m[0]))

    def count(name, args, result):
        kinds[name] += 1
        if name in NOT_FILE:
            return
        m = QUOTED.search(args) if name in PATH_CALLS else None
        err = ERRNO.search(result)
        patterns[(name, err.group(1) if err else "", path_pattern(m.group(1), marks) if m else "")] += 1
    try:
        f = open(path, errors="replace")
    except OSError:
        return None
    with f:
        for line in f:
            m = STRACE_LINE.match(line)
            if not m:
                continue
            tid, at, rest = m.group(1), float(m.group(2)), m.group(3)
            if rest.startswith("<... "):
                r, held = RESUMED.match(rest), pending.pop(tid, None)
                if r and held and t0 <= held[0] <= t1:
                    count(held[1], held[2], r.group(2))
                continue
            name, _, args = rest.partition("(")
            if not name.isidentifier():
                continue   # +++ exited, --- a signal
            if rest.endswith("<unfinished ...>"):
                pending[tid] = (at, name, args)
            elif t0 <= at <= t1:
                count(name, args, args)
    dt = t1 - t0
    return {"seconds": dt, "calls": sum(kinds.values()) / dt,
            "file": sum(n for k, n in kinds.items() if k not in NOT_FILE) / dt,
            "kinds": {k: n / dt for k, n in kinds.most_common()},
            "patterns": [[name, err, pat, n / dt] for (name, err, pat), n in patterns.most_common(80)]}


def print_strace(s):
    if not s or not s["kinds"]:
        print("strace: nothing traced (is strace there, and may it attach?)")
        return
    print("strace (%.0f s): %.0f calls a second, %.0f of them file calls" % (s["seconds"], s["calls"], s["file"]))
    print("  by kind: " + ", ".join("%s %.0f" % (k, n) for k, n in s["kinds"].items() if k not in NOT_FILE and n >= 1))
    for name, err, pat, n in s["patterns"][:30]:
        print("  %8.1f/s %-10s %-7s %s" % (n, name, err, pat))


FILE_BUILTIN = re.compile(r"posix\.\w+>|io\.open>|DirEntry")
WAITS = re.compile(r"acquire|select|poll|sleep|recv|accept|'wait'|\.wait>|connect|sendall|send'|readinto")


def pycalls_window(env, pid, seconds, keep=None):
    """The uplink's Python-level calls for `seconds`: cProfile begun and
    ended in it by signal (the hook's BENCH_PROFILE), every thread's calls
    counted; a second in all, of Python functions (cProfile's entries with
    a file), and of each file call; its profile kept at `keep`."""
    import pstats
    out = env.env["BENCH_PROFILE"]
    os.kill(pid, signal.SIGUSR1)
    time.sleep(seconds)
    os.kill(pid, signal.SIGUSR2)
    deadline = time.time() + 120
    while not os.path.exists(out):
        if time.time() > deadline:
            return None
        time.sleep(0.2)
    with open(out + ".window") as f:
        w = json.load(f)
    dt = w["to"] - w["from"]
    total = python = 0
    files = {}
    for (fn, _, name), (_, nc, _, _, _) in pstats.Stats(out).stats.items():
        total += nc
        if fn != "~":
            python += nc
        elif FILE_BUILTIN.search(name):
            files[name] = files.get(name, 0) + nc
    if keep:
        shutil.copy(out, keep)
        shutil.copy(out + ".window", keep + ".window")
    ticks = (w.get("passes") or {}).get("Link.tick", {}).get("calls")
    return {"seconds": dt, "calls": total / dt, "python": python / dt,
            "file": {k: n / dt for k, n in sorted(files.items(), key=lambda kv: -kv[1])},
            "ticks": ticks, "ticks_a_second": None if ticks is None else ticks / dt}


def print_pycalls(s):
    if not s:
        print("python calls: no profile came back")
        return
    print("python calls (%.0f s, cProfile): %.0f calls a second, %.0f of them Python functions; file calls a second: %s"
          % (s["seconds"], s["calls"], s["python"], ", ".join("%s %.0f" % (re.sub(r"<built-in method |>", "", k), n)
                                                          for k, n in s["file"].items() if n >= 1)))
    if s.get("ticks") is None:
        print("uplink ticks: Link.tick not timed in the window")
    else:
        print("uplink ticks: Link.tick ran %d times in the %.0f s, %.2f a second" % (
            s["ticks"], s["seconds"], s["ticks_a_second"]))


def nudge_window(env, pid, n):
    """`n` nudges of `daemon run` (sminos.nudge_daemon's touch), each two
    seconds after a tick ended, so none lands on the interval's own: the
    tick it brought (the first to begin after it), its wall and CPU time,
    and how long after the nudge it began and ended."""
    path = os.path.join(env.sh, "daemon", "nudge")
    out = []
    for _ in range(n):
        last = tick_rows(env, pid, 0, time.time())
        if last:
            time.sleep(max(0.0, last[-1]["at"] + last[-1]["wall"] + 2.0 - time.time()))
        at = time.time()
        with open(path, "a"):
            pass
        os.utime(path)
        row, deadline = None, at + 30
        while row is None and time.time() < deadline:
            time.sleep(0.05)
            row = next(iter(tick_rows(env, pid, at, at + 30)), None)
        if row is not None:
            out.append({"began": row["at"] - at, "wall": row["wall"], "cpu": row["cpu"],
                        "ended": row["at"] + row["wall"] - at})
    return out


def cmd_shape(a, env):
    """`shape`: see the module's docstring."""
    import glob
    ep = EndpointStandin(env)
    try:
        run_child([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "probe"], env=env.env,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not cut_over(env):
            print("the endpoint stand-in's welcome did not cut the machine over")
            return 1
        run_child([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "tick"], env=env.env,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        ep.stop()
    sminos, _ = in_process(env, a.scripts)
    up, pl, br = (sminos.sibling_module(m) for m in ("sminos_uplink", "sminos_plane", "sminos_bridge"))
    records = sminos.records_module()
    known = sminos.known_projects()
    opened = up.hub_projects({"org": ORG, "machine": sminos.host_name()})
    rows = {}
    for p in known:
        rows[p.id] = {m.session for m in sminos.view_of(p, titles=False).members if m.local and m.session}
    members = set().union(*rows.values()) if rows else set()
    in_open = set().union(*(rows.get(pid, set()) for pid in opened)) if opened else set()
    seats = sminos.seats()
    socks = glob.glob(os.path.join(env.sh, "bridge", "*.sock"))
    answering = 0
    for path in socks:
        try:
            answering += br.request(path, "GET", "/status", timeout=2)[0] == 200
        except Exception:  # noqa: BLE001 — a socket nobody answers on
            pass
    logs = glob.glob(os.path.join(env.sh, "projects", "*", "log", "*.jsonl"))
    events = 0
    for path in logs:
        with open(path, "rb") as f:
            events += sum(1 for _ in f)
    states = {os.path.basename(os.path.dirname(x)) for x in glob.glob(os.path.join(env.sh, "projects", "*",
                                                                                     "uplink.json"))}
    own = sum(len(glob.glob(os.path.join(p.home, "log", MACHINE + ".*.jsonl"))) for p in opened.values())
    print("registered projects %d; hub projects open %d; with an uplink.json once open %d" % (
        len(known), len(opened), len(states | set(opened))))
    print("seats %d, %d of them where this machine may not read (TCC %s)" % (
        len(seats), sum(1 for s in seats if sminos.read_refused(str(s.get("cwd") or ""))), sminos.TCC))
    print("session-record files %d; members %d (%d in open projects), %d with a record" % (
        len(glob.glob(os.path.join(env.sh, "session-records", "*.json"))), len(members), len(in_open),
        sum(1 for s in members if records.read(s) is not None)))
    print("engine records %d, live %d; bridge sockets %d, answering %d" % (
        len(glob.glob(os.path.join(env.home, ".claude", "sessions", "*.json"))), len(pl.Records().scan()),
        len(socks), answering))
    print("host stores %d (%d files); own writer files in open projects %d; under the former name %d" % (
        len(glob.glob(os.path.join(env.sh, "projects", "*", "host"))),
        len(glob.glob(os.path.join(env.sh, "projects", "*", "host", "*.jsonl"))), own,
        len(glob.glob(os.path.join(env.sh, "projects", "*", "log", a.former + ".*.jsonl"))) if a.former else 0))
    print("log files %d, events %d; engine project dirs %d" % (len(logs), events, len(os.listdir(env.projects))))


def cmd_passes(argv):
    """`passes`: see the module's docstring."""
    import pstats
    p = argparse.ArgumentParser(prog="bench_scale.py passes")
    p.add_argument("profile")
    p.add_argument("--top", type=int, default=25)
    a = p.parse_args(argv)
    st = pstats.Stats(a.profile)
    st.calc_callees()
    try:
        with open(a.profile + ".window") as f:
            w = json.load(f)
        secs = w["to"] - w["from"]
    except (OSError, ValueError, KeyError):
        w, secs = {}, None

    def pct(t):
        return 100 * t / secs if secs else float("nan")

    def label(k):
        return k[2] if k[0] == "~" else "%s:%d %s" % (os.path.basename(k[0]), k[1], k[2])

    def find(file, name):
        """The function of that name in that file with the most time: the
        pass timers' wrappers stand between a pass and its caller, so callers
        cannot tell two methods of one name apart."""
        found = [k for k in st.stats if k[0].endswith(file) and k[2] == name]
        return max(found, key=lambda k: st.stats[k][3]) if found else None

    def show(title, key):
        if key is None:
            print("%s: not in the profile" % title)
            return
        _, nc, tt, ct, _ = st.stats[key]
        print("%s: %d calls, %.3f s cumulative (%.1f%% of the window), %.3f s its own" % (title, nc, ct, pct(ct), tt))
        for k, edge in sorted(st.all_callees.get(key, {}).items(), key=lambda kv: -kv[1][3])[:a.top]:
            print("  %-60s %8d calls %8.3f s %6.2f%%" % (label(k), edge[0], edge[3], pct(edge[3])))
    print("window %.1f s" % (secs or float("nan")))
    if w.get("cpu") is not None:
        print("CPU in the window: %.2f s, %.1f%% of a core (under the profiler); by thread (threads that came and "
              "went inside the window are in the whole only):" % (w["cpu"], pct(w["cpu"])))
        for name, (n, cpu) in sorted(w["threads"].items(), key=lambda kv: -kv[1][1]):
            print("  %-28s %3d threads %7.2f s %6.2f%%" % (name, n, cpu, pct(cpu)))
    elif w.get("passes") is not None:
        print("CPU in the window: not read (the process and thread totals come from Linux's /proc)")
    if w.get("passes") is not None:
        print("passes, each call's CPU time on its own thread, what it calls included (so they nest):")
        for name, r in sorted(w["passes"].items(), key=lambda kv: -kv[1]["cpu"]):
            print("  %-34s %8d calls %7.3f s %6.2f%% %8.3f ms a call" % (
                name, r["calls"], r["cpu"], pct(r["cpu"]), 1000 * r["cpu"] / max(1, r["calls"])))
    print("cProfile (wall time; on Python 3.12 one stack serves every thread, so a caller's cumulative time can "
          "read below its callees' while threads run: read the edges' calls, and the times as rough):")
    show("Link.tick", find("sminos_uplink.py", "tick"))
    show("Link.members", find("sminos_uplink.py", "members"))
    show("Link.upload_pass", find("sminos_uplink.py", "upload_pass"))
    show("Plane.tick (or the warmer's, whichever took longer)", find("sminos_plane.py", "tick"))
    show("Bridges.probe (its threads)", find("sminos_plane.py", "probe"))
    show("Subscription.pump (each subscription, each plane tick)", find("sminos_plane.py", "pump"))
    for k in sorted(k for k in st.stats if k[0].endswith("sminos_plane.py") and k[2] in ("work", "look", "meta",
                                                                                            "facts")):
        show("plane %s (line %d: the transcripts' workers, the metas look)" % (k[2], k[1]), k)
    roots = sorted(((k, v) for k, v in st.stats.items() if not v[4]), key=lambda kv: -kv[1][3])
    print("entries no profiled caller called (the frames running when the profile began, the threads' roots):")
    for k, v in roots[:8]:
        print("  %-60s %8d calls %8.3f s %6.2f%%" % (label(k), v[1], v[3], pct(v[3])))
    own = sorted(((k, v) for k, v in st.stats.items() if not WAITS.search(k[2])), key=lambda kv: -kv[1][2])
    print("most time of their own (waits left out):")
    for k, v in own[:a.top]:
        print("  %-60s %8d calls %8.3f s %6.2f%%" % (label(k), v[1], v[2], pct(v[2])))
    total = sum(v[1] for v in st.stats.values())
    print("calls: %d in all, %.0f a second" % (total, total / secs if secs else float("nan")))


def endpoint_host(env, scripts):
    """bench_rig's EndpointHub for the machine (in this process, its
    `session` frames stamped on arrival), the machine cut over by its
    welcome to `daemon probe`, as `run`'s is. The stand-in is stopped
    if the cut-over fails, so a setup that raises leaves it listening
    nowhere."""
    import bench_rig
    host = bench_rig.EndpointHub(env.root, env.env)
    try:
        r = run_child([sys.executable, os.path.join(scripts, "sminos.py"), "daemon", "probe"], env=env.env,
                      capture_output=True, text=True)
        host.check_cut_over(env.sh, (r.stdout or "") + (r.stderr or ""))
    except BaseException:
        host.close()
        raise
    return host


class EndpointOpens:
    """Where `opens` sends its subscribes: the endpoint stand-in
    (endpoint_host), its live connection's number the mark a restart's
    connection is newer than."""

    def __init__(self, env, scripts):
        import bench_rig
        self.host = endpoint_host(env, scripts)
        self.browser = bench_rig.EndpointBrowser(self.host, None, MACHINE)

    def mark(self):
        return self.host.ep.opened()["conn"] or 0

    def ready(self, after, pids):
        """A connection newer than number `after`, once its hellos opened every project named."""
        o = self.host.ep.opened()
        return o["conn"] is not None and o["conn"] > after and all(pid in o["projects"] for pid in pids)

    def close(self):
        self.host.close()


def cmd_opens(a, env):
    import bench_open as bo
    import bench_rig as rig
    where = EndpointOpens(env, a.scripts)
    up = [None]
    try:
        run_child([sys.executable, os.path.join(a.scripts, "sminos.py"), "daemon", "tick"], env=env.env,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        lives = env.live_sessions
        own = machine_project_id(ORG, MACHINE)
        small = next(s for s in lives if s["size"] == "small" and s["project"] != own)
        large = next((s for s in lives if s["size"] == "large"), None)
        if large is None:
            sys.exit("bench_scale opens: no live session in a hub checkout took a large transcript (--large)")
        browser = where.browser
        log_path = os.path.join(env.sh, "daemon.log")
        pair = [large, small]   # the large one's subscribe first: the small one opens while its build runs
        ready = where.ready

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
                generation = where.mark()
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
        where.close()


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
        run_child([sys.executable, os.path.join(a.scripts, "sminos.py")] + verb, env=env.env,
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


def run_child(argv, capture_output=False, **kw):
    """subprocess.run through spawn: its child in STARTED from its start, and
    killed if this process is stopped while it waits for it."""
    if capture_output:
        kw.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p = spawn(argv, **kw)
    try:
        out, err = p.communicate()
    except BaseException:
        p.kill()
        p.wait()
        raise
    return subprocess.CompletedProcess(argv, p.returncode, out, err)


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
    if sys.argv[1:2] == ["passes"]:
        return cmd_passes(sys.argv[2:])
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="mode", required=True)
    for mode in ("tick", "profile", "run", "verbs", "opens", "shape"):
        s = sub.add_parser(mode)
        s.add_argument("scripts")
        if mode == "profile":
            s.add_argument("out")
        scale(s)
    sub.choices["tick"].add_argument("--ticks", type=int, default=5)
    sub.choices["run"].add_argument("--seconds", type=float, default=60)
    sub.choices["run"].add_argument("--warmup", type=float, default=30)
    sub.choices["run"].add_argument("--import-events", type=int, default=0, metavar="N",
                                    help="after the window, time N events from the endpoint, one frame each, into "
                                         "the log")
    sub.choices["run"].add_argument("--profile-uplink", metavar="OUT",
                                    help="run the uplink alone under cProfile for warmup + seconds, its profile to OUT")
    sub.choices["run"].add_argument("--strace", type=float, default=0, metavar="S",
                                    help="after the CPU window, the uplink's system calls for S seconds")
    sub.choices["run"].add_argument("--pycalls", type=float, default=0, metavar="S",
                                    help="then its Python-level calls for S seconds, under cProfile")
    sub.choices["run"].add_argument("--pycalls-prof", metavar="OUT", help="keep that profile at OUT (see `passes`)")
    sub.choices["run"].add_argument("--idle-gate", action="store_true",
                                    help="judge the run by its --pycalls counts (IDLE_GATE_*), not by B2's gate")
    sub.choices["run"].add_argument("--nudges", type=int, default=0, metavar="N",
                                    help="then N nudges of daemon run, each its tick's wall time")
    sub.choices["run"].add_argument("--poll", type=float, default=0, metavar="S", help="the uplink's POLL")
    sub.choices["run"].add_argument("--presence-every", type=float, default=0, metavar="S",
                                    help="the plane's PRESENCE_EVERY")
    sub.choices["run"].add_argument("--measures-out", metavar="FILE", help="every figure of the run as JSON")
    sub.choices["run"].add_argument("--subs", type=int, default=0, metavar="N",
                                    help="transcript subscriptions held open from the warm-up through every window")
    sub.choices["run"].add_argument("--words", type=int, default=2, metavar="W",
                                    help="words-gated events owed to each live session in a hub checkout, "
                                         "one from each of W members, never answered")
    sub.choices["opens"].add_argument("--large", type=int, default=6, metavar="G",
                                      help="live sessions in hub checkouts given a large transcript")
    sub.choices["opens"].add_argument("--large-rows", type=int, default=15000, metavar="N")
    sub.choices["opens"].add_argument("--warm-after", type=float, default=30.0, metavar="S",
                                      help="when, after the uplink's start, every live session is opened in sequence")
    for mode in ("run", "opens"):
        sub.choices[mode].add_argument("--rl10", action="store_true",
                                       help="accepted, and changes nothing: RL10 is the only path (#153 M5)")
    # The preset as argparse reads it (--preset X, --preset=X), its values then the defaults under the flags given.
    preset = p.parse_args().preset
    for s in sub.choices.values():
        s.set_defaults(**PRESETS.get(preset, {}))
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
        if a.preset:
            print("preset %s: %d retired hub projects, %d seats in ~/Documents (TCC %s), %d session records, %d "
                  "engine records of processes gone, %d bridges (%d answering), %d host files, former name %r "
                  "holding %d, a log of %d events, history %g days old, a working session every %g s" % (
                      a.preset, a.retired, a.refused, "on" if a.tcc else "off", a.records, a.gone, a.bridges,
                      a.answering, a.host_files, a.former, a.former_sessions, a.big_log, a.age, a.working),
                  flush=True)
        if a.joined_by:
            # The first tick's joins made by another copy of the scripts (the
            # same events any copy writes), so a slow copy's steady state is
            # measured without waiting out its first tick.
            t = time.perf_counter()
            run_child([sys.executable, os.path.join(a.joined_by, "sminos.py"), "daemon", "tick"], env=env.env,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("joined by %s's first tick in %.1f s" % (a.joined_by, time.perf_counter() - t), flush=True)
        status = {"tick": cmd_tick, "profile": cmd_profile, "run": cmd_run, "verbs": cmd_verbs,
                  "opens": cmd_opens, "shape": cmd_shape}[a.mode](a, env)
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
