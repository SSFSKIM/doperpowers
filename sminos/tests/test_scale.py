#!/usr/bin/env python3
"""What the daemon's loop and its uplink cost on a machine that follows every
project of its org (F1 of the org directory's acceptance run, 2026-10-19):
a member on another machine costs no look for a transcript here; a session
with none here (an old seat's) costs no walk of ~/.claude/projects per ask;
a reconciliation deciding on a resolution older than a move does not undo
the move (F3); and the uplink takes the org's directory ahead of the frames
queued before it. Hermetic: HOME and SMINOS_HOME are temporary.
"""

import glob
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid

HERE = os.path.dirname(os.path.realpath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN_ROOT, "skills", "sminos", "scripts")
T = tempfile.mkdtemp(prefix="sms.", dir="/tmp")
HOME, SH = os.path.join(T, "home"), os.path.join(T, "s")
os.environ.update(HOME=HOME, SMINOS_HOME=SH, SMINOS_DERIVE_EVERY="0")
for k in ("CLAUDE_CODE_SESSION_ID", "SMNS_INTERNAL", "SMNS_MEMBER", "DAEMON_HOME", "DAEMON_HOST", "AGORA_HOME"):
    os.environ.pop(k, None)
PROJECTS = os.path.join(HOME, ".claude", "projects")
os.makedirs(os.path.join(HOME, ".claude", "sessions"))
os.makedirs(os.path.join(SH, "daemon"))
os.makedirs(os.path.join(T, "bin"))
with open(os.path.join(T, "bin", "claude"), "w") as f:
    f.write('#!/bin/sh\ncase "$1" in agents) echo "[]";; esac\nexit 0\n')
os.chmod(os.path.join(T, "bin", "claude"), 0o755)
os.environ["PATH"] = os.path.join(T, "bin") + os.pathsep + os.environ["PATH"]
ORG, MACHINE, OTHER = "org-1", "testhost", "mini"
with open(os.path.join(SH, "daemon", "hub.json"), "w") as f:
    json.dump({"hub": "http://127.0.0.1:9", "org": ORG, "machine": MACHINE}, f)
sys.path.insert(0, SCRIPTS)

import sminos  # noqa: E402

daemon = sminos.daemon_module()
uplink = sminos.sibling_module("sminos_uplink")
SLEEPERS = []
PROCS = {}


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def transcript(cwd, sid):
    path = os.path.join(PROJECTS, cwd.replace("/", "-").replace(".", "-"), sid + ".jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(json.dumps({"type": "user", "cwd": cwd, "sessionId": sid, "message": {"role": "user", "content": "hi"}})
                + "\n")


def checkout(name, pid=None):
    """A git checkout; with `pid`, its .smns names hub project `pid` (registered here)."""
    d = os.path.join(T, "r", name)
    os.makedirs(os.path.join(d, ".git"), exist_ok=True)
    if pid:
        write(os.path.join(d, ".smns"), {"project": pid, "name": name, "hub": {"org": ORG}})
        write(os.path.join(SH, "projects", pid, "project.json"),
              {"project": pid, "name": name, "remote": "", "root": d, "hub": {"url": "http://127.0.0.1:9", "org": ORG}})
    return d


def live_session(cwd, sid=None, with_transcript=True):
    """A session whose engine record names a running process (a `sleep`, kept in PROCS)."""
    sid = sid or str(uuid.uuid4())
    p = subprocess.Popen(["sleep", "600"])
    SLEEPERS.append(p)
    PROCS[sid] = p
    if with_transcript:
        transcript(cwd, sid)
    write(os.path.join(HOME, ".claude", "sessions", "%d.json" % p.pid),
          {"pid": p.pid, "sessionId": sid, "cwd": cwd, "kind": "interactive", "entrypoint": "cli",
           "name": "s-" + sid[:4], "nameSource": "derived", "status": "idle"})
    return sid


def remote_member(project, sid, i):
    w = "%s/%s" % (OTHER, sid)
    path = os.path.join(project.home, "log", w.replace("/", ".") + ".jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for seq, e in enumerate([
                {"kind": "joined", "alias": "m%d" % i, "name_source": "derived", "machine": OTHER,
                 "cwd": "/Users/mini/p%d" % i, "session_kind": "interactive"},
                {"kind": "state", "state": "idle", "machine": OTHER},
                {"kind": "titled", "title": "remote %d" % i}], 1):
            f.write(json.dumps({"ts": "2026-10-18T00:00:%02d.000Z" % i, "writer": w, "seq": seq, "session": sid, **e})
                    + "\n")


def settle():
    """Past TRANSCRIPT_SHARED: a `fresh` ask after this lists the directories again."""
    time.sleep(sminos.TRANSCRIPT_SHARED + 0.05)


def quietly(fn, *args, **kwargs):
    import io
    out, err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        return fn(*args, **kwargs)
    finally:
        said, sys.stdout, sys.stderr = sys.stderr.getvalue(), out, err
        assert "tick failed" not in said, said


def refreshes():
    index = getattr(sminos, "_TINDEX", None)
    return index.refreshes if index is not None else 0


class Walks:
    """Every glob of ~/.claude/projects and every refresh of the transcript
    index while it is held, and every session a transcript was looked up for."""

    def __enter__(self):
        self.globs, self.asked = [], []
        self.refreshes = refreshes()
        self.real_glob, self.real_path = glob.glob, sminos.transcript_path

        def counted(pattern, *a, **k):
            if str(pattern).startswith(PROJECTS):
                self.globs.append(pattern)
            return self.real_glob(pattern, *a, **k)

        def asked(sid, *a, **k):
            self.asked.append(sid)
            return self.real_path(sid, *a, **k)

        glob.glob, sminos.transcript_path = counted, asked
        return self

    def __exit__(self, *_):
        glob.glob, sminos.transcript_path = self.real_glob, self.real_path
        self.refreshes = refreshes() - self.refreshes


class Scale(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for i in range(300):   # other work's project directories
            transcript("/Users/someone/w%d" % i, str(uuid.uuid4()))
        pid = str(uuid.uuid4())
        cls.root = checkout("app", pid)
        cls.project = sminos.known_project(pid)
        cls.remote = [str(uuid.uuid4()) for _ in range(30)]
        for i, sid in enumerate(cls.remote):
            remote_member(cls.project, sid, i)
        # Old seats of this machine whose transcripts the engine cleaned up.
        cls.old = []
        for i in range(30):
            sid = str(uuid.uuid4())
            cls.old.append(sid)
            write(os.path.join(SH, "%s.json" % uuid.uuid4()),
                  {"alias": "old%d" % i, "group": "fleet", "current": sid, "cwd": cls.root, "status": "idle"})
        cls.live = live_session(cls.root)
        quietly(daemon.tick_all)   # joins the seats and the live session

    def test_a_remote_member_costs_no_transcript_look(self):
        with Walks() as w:
            quietly(daemon.tick_all)
            sminos.forget_caches()
            view = sminos.view_of(self.project)   # what list shows, titles read
        self.assertEqual(len([m for m in view.members if not m.local]), len(self.remote))
        self.assertEqual(sorted(set(w.asked) & set(self.remote)), [])

    def test_sessions_without_a_transcript_cost_no_walk_each(self):
        with Walks() as w:
            for _ in range(3):
                quietly(daemon.tick_all)
                sminos.forget_caches()
                sminos.view_of(self.project)
        self.assertTrue(set(self.old) <= set(w.asked), "the old seats were asked about")
        self.assertEqual(w.globs, [], "no glob of the projects directory once the index is built")
        self.assertLessEqual(w.refreshes, 1, "the index is refreshed at most once a TRANSCRIPT_FRESH")

    def test_a_transcript_that_appears_is_found_by_a_poller(self):
        sid = str(uuid.uuid4())
        self.assertFalse(sminos.transcript_contains(sid, '"hi"'))
        transcript(self.root, sid)
        settle()
        self.assertTrue(sminos.transcript_contains(sid, '"hi"'))
        sid = str(uuid.uuid4())
        self.assertEqual(sminos.transcript_rows(sid), [])
        transcript(self.root, sid)
        settle()
        self.assertEqual(len(sminos.transcript_rows(sid)), 1, "a one-shot reader finds what appeared since")


class StaleResolution(unittest.TestCase):
    """F3: a tick whose resolution predates a .smns written under a live
    session reconciled the old project afresh and joined the session there
    again, after a reading verb had moved it."""

    def test_a_stale_resolution_does_not_rejoin_a_moved_session(self):
        d = checkout("stray")   # no .smns: this machine's own project
        sid = live_session(d)
        sminos.forget_caches()
        own = sminos.own_machine_project()
        quietly(daemon.tick_all)
        self.assertEqual(sminos.latest_membership(sminos._own_events(own, sid)), "joined")
        # The caches of a tick that began now: the session resolves to `own`.
        sminos.forget_caches()
        stale = sminos.view_of(own, titles=False)
        self.assertIn(sid, {m.session for m in stale.members})
        # A .smns lands, and another process (a reading verb) moves the session.
        pid = str(uuid.uuid4())
        checkout("stray", pid)
        new = sminos.known_project(pid)
        sminos.lifecycle(own, sid, "retired", by="", reason="moved", project=pid)
        sminos.lifecycle(new, sid, "joined", **sminos.joined_fields("s", "derived", d))
        # The tick goes on with what it resolved before.
        self.assertEqual(sminos.resolve_project(d).id, own.id, "the tick's resolution is the stale one")
        sminos.view_of(own, titles=False)
        self.assertEqual(sminos.latest_membership(sminos._own_events(own, sid)), "retired",
                         "the reconciliation did not join it to its old project again")


class FreshDecisions(unittest.TestCase):
    """What a reconciliation writes on a transcript's evidence looks for it as
    the directories are now, not as the index last listed them: a transcript
    may be seconds old (the review of the index)."""

    def test_a_hand_off_newer_than_the_index_is_not_retired_ended(self):
        d = checkout("handoff")
        own = sminos.own_machine_project()
        sid, job = live_session(d, with_transcript=False), str(uuid.uuid4())
        sminos.forget_caches()
        quietly(daemon.tick_all)   # joins it, and lists the transcripts before it has one
        self.assertEqual(sminos.latest_membership(sminos._own_events(own, sid)), "joined")
        path = os.path.join(PROJECTS, d.replace("/", "-").replace(".", "-"), sid + ".jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:   # its first turn, then the harness sends it to the background
            f.write(json.dumps({"type": "user", "cwd": d, "sessionId": sid,
                                "message": {"role": "user", "content": "go"}}) + "\n")
            f.write(json.dumps({"type": "continued-in", "continuedInSessionId": job}) + "\n")
        PROCS[sid].kill()
        PROCS[sid].wait()
        settle()
        quietly(daemon.tick_all)   # within TRANSCRIPT_FRESH of the last listing
        last = next(e for e in reversed(sminos._own_events(own, sid)) if e["kind"] in sminos.MEMBERSHIP)
        self.assertEqual((last["kind"], last.get("reason"), last.get("to")), ("retired", "continued", job))

    def test_a_recheck_reads_a_transcript_newer_than_the_index(self):
        a, b = checkout("launched"), checkout("wandered", str(uuid.uuid4()))
        sid = str(uuid.uuid4())
        rec = {"pid": os.getpid(), "sessionId": sid, "cwd": b}   # the shell moved on; the launch was in `a`
        sminos.forget_caches()
        sminos.transcript_path(str(uuid.uuid4()))   # the generation's listing, before the transcript
        transcript(a, sid)
        settle()
        self.assertNotEqual(sminos.record_project(rec).id, sminos.resolve_project(a).id)
        self.assertEqual(sminos.record_project(rec, fresh=True).id, sminos.resolve_project(a).id)


class SharedRefresh(unittest.TestCase):
    def test_a_passs_fresh_asks_share_one_listing(self):
        """Many writes of one pass (every seat under a .smns that just landed)
        each ask `fresh`: one refresh serves them all for TRANSCRIPT_SHARED."""
        index, now = sminos._TINDEX, [1000.0]
        index.clock = lambda: now[0]
        try:
            sminos.transcripts_now()
            before = index.refreshes
            for _ in range(50):
                sminos.transcript_path(str(uuid.uuid4()), fresh=True)
            self.assertEqual(index.refreshes, before)
            now[0] += sminos.TRANSCRIPT_SHARED
            sminos.transcript_path(str(uuid.uuid4()), fresh=True)
            self.assertEqual(index.refreshes, before + 1)
            # What this process just caused (derive's fork) is found by a one-shot look.
            sid = str(uuid.uuid4())
            transcript(os.path.join(T, "r", "app"), sid)
            self.assertEqual(sminos.transcript_path(sid, fresh=True), "", "inside the shared window")
            self.assertTrue(sminos.transcript_now(sid).endswith(sid + ".jsonl"))
        finally:
            index.clock = time.monotonic
            sminos.transcripts_now()


class OrgAhead(unittest.TestCase):
    """The org's directory is handled before the frames queued ahead of it."""

    def test_org_frame_is_taken_before_the_queue(self):
        stream = uplink.Stream({"hub": "http://127.0.0.1:9"})
        seen = []

        class Link:
            def dispatch(self, frame, _stream):
                seen.append(frame["t"])

            def deliver_imports(self):
                pass

            def tick(self):
                seen.append("tick")

        for _ in range(5):
            stream.items.put(("frame", "events", json.dumps({"t": "events", "project": "p", "events": []})))
        stream.org = json.dumps({"t": "org", "projects": [], "machines": []})
        stream.items.put(("org",))
        stream.items.put(("closed", "done"))
        uplink.serve_link(Link(), stream, lambda: False, threading.Event())
        self.assertEqual(seen[0], "org")
        self.assertEqual(seen.count("org"), 1)
        self.assertEqual(seen[1:], ["events"] * 5)


class BenchOpens(unittest.TestCase):
    """bench_scale.py opens on a small synthetic machine: an open of a
    large and of a small live session at +0.5 s, every live session in
    sequence after the warm-up, then the pair again after a restart; each
    line with its moment, size and E."""

    def test_the_opens_at_their_moments(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "bench_scale.py"), "opens", SCRIPTS, "--dirs", "3",
                            "--per-dir", "1", "--seats", "4", "--local", "2", "--remote", "1", "--mini", "1",
                            "--says", "2", "--live", "5", "--large", "1", "--large-rows", "600", "--warm-after", "1"],
                           capture_output=True, text=True, timeout=300,
                           env={k: v for k, v in os.environ.items() if k not in ("HOME", "SMINOS_HOME")})
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        lines = [json.loads(line) for line in r.stdout.splitlines() if line.startswith("{")]
        opens = [o for o in lines if "moment" in o and "summary" not in o]
        self.assertEqual([(o["moment"], o["size"]) for o in opens[:2]], [("+0.5 s", "large"), ("+0.5 s", "small")])
        warm = [o for o in opens if o["moment"] == "+1 s"]
        self.assertEqual(len(warm), 5, "every live session after the warm-up")
        self.assertEqual([(o["moment"], o["size"]) for o in opens[-2:]],
                         [("restart +0.5 s", "large"), ("restart +0.5 s", "small")])
        for o in opens:
            self.assertEqual(o["outcome"], "transcript-only (no bridge socket)", o)
            self.assertGreater(o["E"], 0)
        large = [o for o in opens if o["size"] == "large"]
        self.assertTrue(all(o["rows"] == 600 for o in large), large)
        self.assertEqual(large[0]["build"], "cold", "a fresh uplink's first open of it")
        self.assertIn(large[-1]["build"], ("cold", "loaded"), "after the restart: parsed or loaded, never warm")


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        for p in SLEEPERS:
            p.kill()
        shutil.rmtree(T, ignore_errors=True)
