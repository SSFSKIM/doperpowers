#!/usr/bin/env python3
"""What the daemon's loop and its uplink cost on a machine that follows every
project of its org (F1 of the org directory's acceptance run, 2026-10-19):
a member on another machine costs no look for a transcript here; a session
with none here (an old seat's) costs no walk of ~/.claude/projects per ask;
a reconciliation deciding on a resolution older than a move does not undo
the move (F3); and the uplink takes the org's directory ahead of the frames
queued before it. Hermetic: HOME and SMINOS_HOME are temporary.
"""

import errno
import glob
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
import uuid
from unittest import mock

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


class HotLooks(unittest.TestCase):
    """The upload pass between scans (HubLog.writers with `live`): a machine's
    history is hundreds of own writers of sessions long ended, and the pass
    runs every UPLOAD_EVERY. It looks again only at the hot ones — a running
    session's, the operator's, one that changed lately, one it holds nothing
    of — and lists the log directory again only once it changed; the scan's
    whole look sees the rest (2026-10-28: an idle uplink at 5–16 % of a core)."""

    HOUR_AGO = time.time() - 3600

    def setUp(self):
        hublog = sminos.sibling_module("sminos_hublog")
        pid = str(uuid.uuid4())
        checkout("hot-%s" % pid[:8], pid)
        self.project = sminos.known_project(pid)
        self.log_dir = os.path.join(self.project.home, "log")
        os.makedirs(self.log_dir, exist_ok=True)
        self.sids = [str(uuid.uuid4()) for _ in range(40)]
        for sid in self.sids:
            self.write("%s/%s" % (MACHINE, sid), sid, 1)
        self.write(MACHINE + "/human", None, 1)
        self.write("%s/%s" % (OTHER, uuid.uuid4()), None, 1)   # another machine's: no upload's
        for name in os.listdir(self.log_dir):
            os.utime(os.path.join(self.log_dir, name), (self.HOUR_AGO, self.HOUR_AGO))
        self.still()
        self.hl = hublog.HubLog(self.project, {"key": b"k" * 32, "machine": MACHINE})
        self.hl.writers(own=True)   # the whole look: every own writer read

    def write(self, writer, sid, seq):
        path = os.path.join(self.log_dir, writer.replace("/", ".") + ".jsonl")
        with open(path, "a") as f:
            f.write(json.dumps({"ts": "2026-10-28T00:00:%02d.000Z" % seq, "writer": writer, "seq": seq,
                                "kind": "say", "session": sid or "", "to": [], "text": "x"}) + "\n")
        return path

    def still(self):
        """The log directory as it is after an hour of no file made or removed."""
        os.utime(self.log_dir, (self.HOUR_AGO, self.HOUR_AGO))

    def looked(self, live):
        """(what a hot look returns, the own writer files it looked at, whether it listed the directory)."""
        real_stat, real_glob, real_listdir = os.stat, glob.glob, os.listdir
        stats, lists = [], []

        def stat(path, *a, **k):
            if str(path).startswith(self.log_dir + os.sep):
                stats.append(os.path.basename(path))
            return real_stat(path, *a, **k)

        def counted(pattern, *a, **k):
            lists.append(pattern)
            return real_glob(pattern, *a, **k)

        def listdir(path=".", *a, **k):
            if path == self.log_dir:
                lists.append(path)
            return real_listdir(path, *a, **k)
        with mock.patch.object(os, "stat", stat), mock.patch.object(glob, "glob", counted), \
                mock.patch.object(os, "listdir", listdir):
            got = self.hl.writers(own=True, live=live)
        return got, sorted(stats), bool(lists)

    def unlistable(self):
        """The log directory's listing failing as it does in a process out of
        descriptors (many threads and sockets), its stat still answering."""
        def failing(real):
            def call(path=".", *a, **k):
                if path == self.log_dir:
                    raise OSError(errno.EMFILE, os.strerror(errno.EMFILE), path)
                return real(path, *a, **k)
            return call
        return mock.patch.multiple(os, scandir=failing(os.scandir), listdir=failing(os.listdir))

    def name(self, sid):
        return "%s.%s.jsonl" % (MACHINE, sid)

    def test_a_hot_look_passes_the_quiet_history_by(self):
        running = self.sids[0]
        recent = self.write("%s/%s" % (MACHINE, self.sids[1]), self.sids[1], 2)   # changed a moment ago
        self.hl.writers(own=True)
        got, stats, listed = self.looked({running})
        self.assertEqual(stats, sorted([self.name(running), os.path.basename(recent), MACHINE + ".human.jsonl"]))
        self.assertFalse(listed, "an unchanged directory is not listed again")
        self.assertEqual(len(got), len(self.sids) + 1, "every own writer is still in what it returns")
        self.assertEqual(got["%s/%s" % (MACHINE, self.sids[1])][0], 2)

    def test_what_a_hot_look_passes_by_the_whole_look_sees(self):
        quiet, running = self.sids[2], self.sids[3]
        self.write("%s/%s" % (MACHINE, quiet), quiet, 2)
        self.write("%s/%s" % (MACHINE, running), running, 2)
        self.still()
        got, _, _ = self.looked({running})
        self.assertEqual(got["%s/%s" % (MACHINE, running)][0], 2, "a running session's append: the next pass")
        self.assertEqual(got["%s/%s" % (MACHINE, quiet)][0], 1, "a writer quiet for an hour waits for the scan")
        self.assertEqual(self.hl.writers(own=True)["%s/%s" % (MACHINE, quiet)][0], 2, "the scan's whole look")

    def test_a_session_that_stopped_stays_hot_for_its_last_events(self):
        sid = self.sids[4]
        self.looked({sid})
        self.write("%s/%s" % (MACHINE, sid), sid, 2)   # the daemon's `retired`, after the process ended
        self.still()
        got, _, _ = self.looked(set())
        self.assertEqual(got["%s/%s" % (MACHINE, sid)][0], 2)

    def test_a_new_writer_is_listed_and_read(self):
        sid = str(uuid.uuid4())
        self.write("%s/%s" % (MACHINE, sid), sid, 1)
        got, stats, listed = self.looked(set())
        self.assertTrue(listed, "a file made there moves the directory's mtime")
        self.assertIn(self.name(sid), stats)
        self.assertEqual(got["%s/%s" % (MACHINE, sid)][0], 1)

    def test_a_look_that_lists_again_is_whole(self):
        """A file replaced by rename moves the directory, not the quiet
        writer's hotness: the look that lists again looks at every file."""
        quiet = self.sids[5]
        path = os.path.join(self.log_dir, self.name(quiet))
        with open(path) as f:
            first = f.read()
        with open(path + ".tmp", "w") as f:
            f.write(first + json.dumps({"ts": "2026-10-28T00:00:02.000Z", "writer": "%s/%s" % (MACHINE, quiet),
                                        "seq": 2, "kind": "say", "session": quiet, "to": [], "text": "x"}) + "\n")
        os.utime(path + ".tmp", (self.HOUR_AGO, self.HOUR_AGO))
        os.replace(path + ".tmp", path)
        got, _, listed = self.looked(set())
        self.assertTrue(listed)
        self.assertEqual(got["%s/%s" % (MACHINE, quiet)][0], 2)

    def test_a_listing_taken_as_the_directory_changed_is_not_kept(self):
        """On a coarse clock a file made in the tick of the listing leaves
        the directory's mtime as the listing saw it: a listing is kept only
        once the directory held still RACY before it."""
        now = time.time()
        os.utime(self.log_dir, (now, now))
        self.looked(set())
        sid = str(uuid.uuid4())
        self.write("%s/%s" % (MACHINE, sid), sid, 1)
        os.utime(self.log_dir, (now, now))   # the same mtime: made within the same tick
        got, _, listed = self.looked(set())
        self.assertTrue(listed)
        self.assertIn("%s/%s" % (MACHINE, sid), got)

    def test_a_listing_that_failed_is_not_kept(self):
        """A directory that could not be listed is no empty directory: the
        look keeps nothing of it, and the next one lists it again, though
        the directory held still and nothing in it changed since."""
        sid = str(uuid.uuid4())
        self.write("%s/%s" % (MACHINE, sid), sid, 1)
        os.utime(self.log_dir, (self.HOUR_AGO - 60, self.HOUR_AGO - 60))   # moved since setUp's listing, and still
        with self.unlistable():
            self.hl.writers(own=True, live=set())
        got, _, listed = self.looked(set())
        self.assertTrue(listed, "listed again")
        self.assertEqual(len(got), len(self.sids) + 2, "every own writer, the new one too")
        self.assertIn("%s/%s" % (MACHINE, sid), got)

    def test_the_own_files_are_those_glob_matches(self):
        """The listing matches as glob matched `<prefix>*.jsonl`: the prefix
        taken literally, a hidden name only for a hidden prefix."""
        hublog = sminos.sibling_module("sminos_hublog")
        for machine in ("testhost", "we[ir]d*?", ".dot", "org/host"):
            home = tempfile.mkdtemp(dir=T)
            d = os.path.join(home, "log")
            os.mkdir(d)
            prefix = machine.replace("/", ".") + "."
            for name in (prefix + "a.jsonl", prefix + ".jsonl", prefix + "jsonl", prefix + "a.jsonl.tmp",
                         "." + prefix + "a.jsonl", "x" + prefix + "a.jsonl", "legacy.a.jsonl", ".legacy.a.jsonl",
                         prefix.upper() + "a.jsonl", prefix + "a\nb.jsonl"):
                open(os.path.join(d, name), "w").close()
            hl = hublog.HubLog(types.SimpleNamespace(home=home), {"key": b"k" * 32, "machine": machine})
            for archive in (False, True):
                hl.archive, hl.listing = archive, None
                want = [p for prefix_ in [prefix] + (["legacy."] if archive else [])
                        for p in glob.glob(os.path.join(glob.escape(d), glob.escape(prefix_) + "*.jsonl"))]
                self.assertEqual(sorted(hl.own_paths()[0]), sorted(want), (machine, archive))


class QuietReads(unittest.TestCase):
    """The session plane reads a project's members again at MEMBERS_EVERY
    only once what that read draws on moved (Plane.stale): its log, the
    seats, its members' engine and session records; every project when a
    session came or went, and at MEMBERS_WHOLE."""

    def setUp(self):
        pid = str(uuid.uuid4())
        self.root = checkout("quiet-%s" % pid[:8], pid)
        self.project = sminos.known_project(pid)
        self.sid = live_session(self.root)
        quietly(daemon.tick_all)   # joins it
        self.plane = sminos.sibling_module("sminos_plane").Plane(MACHINE, lambda: None)
        self.addCleanup(self.plane.close)
        self.projects = {pid: self.project}
        self.plane.tick(self.projects)
        self.assertIn(self.sid, self.plane.members[pid], "the first read: its live member")

    def reads(self, whole=False):
        """How many projects the plane reads at its next look (MEMBERS_EVERY gone by; `whole`, MEMBERS_WHOLE too)."""
        self.plane.next_scan = self.plane.next_members = 0.0
        if whole:
            self.plane.next_whole = 0.0
        with mock.patch.object(self.plane, "refresh", wraps=self.plane.refresh) as refresh:
            self.plane.tick(self.projects)
        return refresh.call_count

    def test_an_unmoved_project_is_not_read_again(self):
        self.assertEqual(self.reads(), 0)
        self.assertEqual(self.reads(), 0)

    def test_an_append_to_its_log_is_read(self):
        self.assertEqual(self.reads(), 0)
        sminos.log_append(self.project, "%s/%s" % (OTHER, uuid.uuid4()), "say", to=[], text="hi")
        self.assertEqual(self.reads(), 1)
        self.assertEqual(self.reads(), 0)

    def test_a_members_engine_record_is_read(self):
        """Its state word comes from there, not the log."""
        self.assertEqual(self.reads(), 0)
        path = next(os.path.join(HOME, ".claude", "sessions", n) for n in os.listdir(os.path.join(HOME, ".claude", "sessions"))
                    if json.load(open(os.path.join(HOME, ".claude", "sessions", n))).get("sessionId") == self.sid)
        rec = json.load(open(path))
        rec["status"] = "busy"
        write(path, rec)
        self.assertEqual(self.reads(), 1)

    def test_every_project_is_read_at_members_whole(self):
        self.assertEqual(self.reads(), 0)
        self.assertEqual(self.reads(whole=True), 1)


class CheckoutsFromTheRead(unittest.TestCase):
    """Machine presence takes a project's checkouts from the plane's last
    read of who joined it from here (Plane.here). The scan that draws them
    comes before the plane's tick, so a draw at CHECKOUTS_EVERY can precede
    the read that finds a session's new directory: they are drawn again once
    the plane's read moved them, at the next scan — the checkouts posted, and
    whether the project is held or followed."""

    class Lane:
        def __init__(self):
            self.sent = []

        def send(self, frames, then=None):
            self.sent += frames

        def take(self):
            out, self.sent = self.sent, []
            return out

        def posting(self):
            return False

        def close(self):
            pass

    def setUp(self):
        self.cred = {"key": b"k" * 32, "machine": MACHINE, "org": ORG, "hub": "http://127.0.0.1:9"}
        self.link = uplink.Link(self.cred, {})
        self.addCleanup(self.link.close)
        self.link.log_lane = self.Lane()
        self.sid = str(uuid.uuid4())

    def opened(self, root_here):
        """A project open on the stream, with its root checked out here or not:
        (its id, its root, two directories of it a session may work in)."""
        pid = str(uuid.uuid4())
        root = checkout("co-%s" % pid[:8], pid)
        if not root_here:
            shutil.rmtree(root)
        dirs = []
        for i in (1, 2):
            d = os.path.join(T, "r", "co-%s-wt%d" % (pid[:8], i))
            os.makedirs(os.path.join(d, ".git"))
            write(os.path.join(d, ".smns"), {"project": pid, "name": "co-%s" % pid[:8], "hub": {"org": ORG}})
            dirs.append(d)
        sminos.forget_caches()
        self.link.logs[pid] = sminos.sibling_module("sminos_hublog").HubLog(sminos.known_project(pid), self.cred)
        self.link.opened.add(pid)
        return pid, root, dirs

    def scan(self, pid, now, here):
        """What the scan at `now` posts, the plane's last read having found `here` ({session: cwd})."""
        self.link.plane.here[pid] = here
        self.link.machine_presence(now)
        return self.link.log_lane.take()

    @staticmethod
    def posted(frames):
        """[(t, follow, the checkouts' paths)] of the frames."""
        return [(f["t"], f.get("follow", False),
                 [c["path"] for c in f["message"]["body"]["checkouts"]] if f["t"] == "session" else None)
                for f in frames]

    def test_a_new_worktree_goes_at_the_scan_after_the_read(self):
        pid, root, (w1, w2) = self.opened(root_here=True)
        now = 1000.0
        self.assertEqual(self.posted(self.scan(pid, now, {self.sid: w1})),
                         [("hello", False, None), ("session", False, [root, w1])])
        # The session moved to w2 and the daemon appended its `joined`; the
        # deadline's scan comes before the plane read it.
        self.assertEqual(self.scan(pid, now + uplink.CHECKOUTS_EVERY, {self.sid: w1}), [])
        self.assertEqual(self.posted(self.scan(pid, now + uplink.CHECKOUTS_EVERY + uplink.SCAN_EVERY,
                                               {self.sid: w2})),
                         [("session", False, [root, w2])], "at the next scan, not at the next deadline")
        self.assertEqual(self.scan(pid, now + uplink.CHECKOUTS_EVERY + 2 * uplink.SCAN_EVERY, {self.sid: w2}), [])

    def test_a_followed_project_is_held_at_the_scan_after_the_read(self):
        """A session that joined from a directory of the project and ended
        between two of the plane's reads leaves no member, only its
        directory: a checkout, so the project is held."""
        pid, _, (w1, _) = self.opened(root_here=False)
        now = 1000.0
        self.assertEqual(self.posted(self.scan(pid, now, {})), [("hello", True, None)])
        self.assertEqual(self.posted(self.scan(pid, now + uplink.SCAN_EVERY, {self.sid: w1})),
                         [("hello", False, None), ("session", False, [w1])])
        self.assertTrue(self.link.holds(pid))


class WholeReads(unittest.TestCase):
    """A whole read of a log is merged, and view_of's projection made, again
    only once a file of it moved; each reader still has events of its own."""

    def setUp(self):
        pid = str(uuid.uuid4())
        checkout("whole-%s" % pid[:8], pid)
        self.project = sminos.known_project(pid)
        for i, sid in enumerate(uuid.uuid4() for _ in range(5)):
            remote_member(self.project, str(sid), i)

    def test_a_reader_changes_no_other_readers_events(self):
        first = sminos.log_read(self.project)
        first[0]["kind"] = "changed by a reader"
        second = sminos.log_read(self.project)
        self.assertEqual(second[0]["kind"], "joined")
        self.assertEqual(len(first), len(second))

    def test_an_append_is_read_and_projected(self):
        before = sminos.view_of(self.project, titles=False)
        sid = str(uuid.uuid4())
        remote_member(self.project, sid, 9)
        after = sminos.view_of(self.project, titles=False)
        self.assertNotIn(sid, before.info)
        self.assertIn(sid, after.info)
        self.assertEqual(len(after.events), len(before.events) + 3)
        self.assertEqual(sminos.log_read(self.project)[-1]["session"], after.events[-1]["session"])


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
                            "--says", "2", "--own", "2", "--live", "5", "--large", "1", "--large-rows", "600",
                            "--warm-after", "1"],
                           capture_output=True, text=True, timeout=300,
                           env={k: v for k, v in os.environ.items() if k not in ("HOME", "SMINOS_HOME")})
        lines = [json.loads(line) for line in r.stdout.splitlines() if line.startswith("{")]
        missed = [o for o in lines if "incomplete" in o and "moment" in o]
        # A cold-start moment the stream was not ready for is said, not sampled late under its name.
        self.assertEqual(r.returncode, 3 if missed else 0, r.stdout[-2000:] + r.stderr[-2000:])
        for o in missed:
            self.assertIn(o["moment"], ("+0.5 s", "restart +0.5 s"))
            self.assertGreater(o["ready"] or 99, 0.5, "the stream was ready only after the moment, or never")
        opens = [o for o in lines if "moment" in o and "summary" not in o and "incomplete" not in o]
        for moment in ("+0.5 s", "restart +0.5 s"):
            if moment in [o["moment"] for o in missed]:
                continue
            pair = [o for o in opens if o["moment"] == moment]
            self.assertEqual([o["size"] for o in pair], ["large", "small"])
            for o in pair:
                self.assertGreaterEqual(o["sent"], 0.5, "sent at its moment, its offset with it")
                self.assertLess(o["sent"], 0.6, o)
        warm = [o for o in opens if o["moment"] == "+1 s"]
        self.assertEqual(len(warm), 5, "every live session after the warm-up")
        for o in opens:
            self.assertEqual(o["outcome"], "transcript-only (no bridge socket)", o)
            self.assertGreater(o["E"], 0)
        large = [o for o in opens if o["size"] == "large"]
        self.assertTrue(all(o["rows"] == 600 for o in large), large)
        self.assertIn(large[0]["build"], ("cold", "warm"),
                      "a fresh machine holds no saved build: parsed by its first open, or by the warmer before it")
        restarted = [o for o in large if o["moment"] == "restart +0.5 s"]
        for o in restarted:
            self.assertEqual(o["build"], "loaded", "after the restart, the build the first uplink saved")

    def test_a_stand_in_that_fails_to_start_is_ended(self):
        """bench_scale's stand-in is ended when its setup fails after it
        started (here: the machine has no credential to point at it)."""
        sys.path.insert(0, HERE)
        import bench_scale
        started = []
        real = subprocess.Popen

        def popen(*args, **kwargs):
            p = real(*args, **kwargs)
            started.append(p)
            return p
        root = tempfile.mkdtemp(dir=T)
        env = types.SimpleNamespace(root=root, sh=os.path.join(root, "s"))
        with mock.patch.object(bench_scale.subprocess, "Popen", popen):
            with self.assertRaises(OSError):
                bench_scale.standin(env)
        self.assertEqual(len(started), 1)
        self.assertIsNotNone(started[0].poll(), "the stand-in did not outlive its failed setup")


def processes():
    """{pid: (ppid, command)} of every live process on the machine (zombies left out)."""
    out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,stat=,command="], capture_output=True, text=True).stdout
    table = {}
    for line in out.splitlines():
        pid, ppid, stat, command = (line.split(None, 3) + [""])[:4]
        if not stat.startswith("Z"):
            table[int(pid)] = (int(ppid), command)
    return table


def descendants(root):
    """{pid: command} of every live process under `root`."""
    table, found, todo = processes(), {}, [root]
    while todo:
        parent = todo.pop()
        for pid, (ppid, command) in table.items():
            if ppid == parent and pid not in found:
                found[pid] = command
                todo.append(pid)
    return found


class BenchStops(unittest.TestCase):
    """bench_scale.py stopped by SIGTERM or SIGINT (a timeout, a harness):
    every process it started — the sessions, `daemon run` and its uplink,
    the stand-in — is stopped, the synthetic machine removed, and it exits
    128 + the signal."""

    SCALE = ["--dirs", "3", "--per-dir", "1", "--seats", "4", "--local", "2", "--remote", "1", "--mini", "1",
             "--says", "2", "--own", "2", "--live", "3"]

    def stopped(self, sig, argv, ready):
        """Runs bench_scale.py `argv`, signals it once `ready(commands, output)`
        holds of its descendants' command lines and its output, and checks
        what it leaves."""
        out_path = os.path.join(tempfile.mkdtemp(dir=T), "bench.out")
        with open(out_path, "w") as out_file:
            bench = subprocess.Popen([sys.executable, os.path.join(HERE, "bench_scale.py"), *argv, *self.SCALE],
                                     stdout=out_file, stderr=subprocess.STDOUT,
                                     env={k: v for k, v in os.environ.items() if k not in ("HOME", "SMINOS_HOME")})
        started = {}

        def output():
            with open(out_path) as f:
                return f.read()

        def left():
            table = processes()
            return {pid: c for pid, c in started.items() if table.get(pid, (0, None))[1] == c}
        try:
            deadline = time.time() + 120
            while time.time() < deadline and bench.poll() is None:
                started = descendants(bench.pid)
                if ready(list(started.values()), output()):
                    break
                time.sleep(0.2)
            else:
                self.fail("the bench never got there: %s\n%s" % (sorted(started.values()), output()))
            bench.send_signal(sig)
            bench.wait(90)
            self.assertEqual(bench.returncode, 128 + sig, output())
            deadline = time.time() + 15
            while left() and time.time() < deadline:
                time.sleep(0.2)
            self.assertEqual(left(), {}, "left running after the bench's %s:\n%s" % (sig.name, output()))
            built = next(line.split()[1] for line in output().splitlines() if line.startswith("built "))
            self.assertFalse(os.path.exists(built), "the synthetic machine was left on disk")
        finally:
            if bench.poll() is None:
                bench.kill()
                bench.wait()
            for pid in left():
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
            for line in output().splitlines():
                if line.startswith("built /tmp/smb-"):
                    shutil.rmtree(line.split()[1], ignore_errors=True)

    def mid_warmup(self, sig, *mode):
        standin = "endpoint_standin.py" if mode else "hub_standin.py"
        self.stopped(sig, ["run", SCRIPTS, *mode, "--warmup", "120", "--seconds", "60"], lambda commands, _: (
            any("daemon uplink" in c for c in commands) and any(standin in c for c in commands)
            and sum(c.startswith("sleep 86399") for c in commands) == 3))

    def test_sigterm_on_dx2(self):
        self.mid_warmup(signal.SIGTERM)

    def test_sigterm_on_rl10(self):
        self.mid_warmup(signal.SIGTERM, "--rl10")

    def test_sigint_on_rl10(self):
        self.mid_warmup(signal.SIGINT, "--rl10")

    def test_sigterm_mid_tick_in_process(self):
        """`tick` runs the daemon's tick_all in the bench's own process,
        which takes a SystemExit as one project's failure: the stop still
        ends the run there, not after every tick asked for."""
        self.stopped(signal.SIGTERM, ["tick", SCRIPTS, "--ticks", "100000"], lambda commands, out: (
            "steady tick" in out and sum(c.startswith("sleep 86399") for c in commands) == 3))

    def test_a_signal_while_a_child_starts_unwinds_only_once_it_is_known(self):
        """A signal that lands while spawn (or run_child, which waits for its
        child) starts a child is raised only once the child is in STARTED,
        so the end's sweep finds it."""
        sys.path.insert(0, HERE)
        import bench_scale
        real = subprocess.Popen
        self.addCleanup(bench_scale._SIGNAL.update, got=None, raised=False, shield=0)

        def popen(*args, **kwargs):
            p = real(*args, **kwargs)
            bench_scale._on_signal(signal.SIGTERM, None)
            return p
        for start in (bench_scale.spawn, bench_scale.run_child):
            with self.subTest(start.__name__):
                bench_scale._SIGNAL.update(got=None, raised=False, shield=0)
                with mock.patch.object(bench_scale.subprocess, "Popen", popen):
                    with self.assertRaises(bench_scale.Stopped):
                        start(["sleep", "86399"])
                child = bench_scale.STARTED[-1]
                self.assertEqual(child.args, ["sleep", "86399"])
                self.addCleanup(child.kill)
                bench_scale.end_started()
                self.assertIsNotNone(child.poll(), "the sweep ended it")


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        for p in SLEEPERS:
            p.kill()
        shutil.rmtree(T, ignore_errors=True)
