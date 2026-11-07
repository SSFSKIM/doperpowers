#!/usr/bin/env python3
"""macOS's protected folders (TCC): a sminos process reads inside ~/Desktop,
~/Documents, ~/Downloads, iCloud Drive, ~/Library/CloudStorage or a volume
only when its own working directory is inside the same folder, and a child it
starts on its own initiative (derive's fork) starts neither inside such a
folder nor above one. The daemon, whose working directory is neither, tells
such a session's project from what this machine recorded and leaves a member
it cannot tell as recorded (the Mac mini, 2026-11-07: derive's fork in $HOME
raised a Downloads dialog charged to the daemon, which held the machine's CI
runner until someone dismissed it). Hermetic: HOME and SMINOS_HOME are
temporary; the platform is the guard's flag (sminos.TCC), so it runs on Linux.
"""

import builtins
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN_ROOT, "skills", "sminos", "scripts")
T = os.path.realpath(tempfile.mkdtemp(prefix="smp.", dir="/tmp"))
HOME, SH = os.path.join(T, "home"), os.path.join(T, "s")
os.environ.update(HOME=HOME, SMINOS_HOME=SH, SMINOS_DERIVE_EVERY="0", SMINOS_STUB_LOG=os.path.join(T, "forks"))
for k in ("CLAUDE_CODE_SESSION_ID", "SMNS_INTERNAL", "SMNS_MEMBER", "DAEMON_HOME", "DAEMON_HOST", "AGORA_HOME"):
    os.environ.pop(k, None)
PROJECTS = os.path.join(HOME, ".claude", "projects")
DOWNLOADS, DOCUMENTS = os.path.join(HOME, "Downloads"), os.path.join(HOME, "Documents")
for d in (os.path.join(HOME, ".claude", "sessions"), os.path.join(SH, "daemon"), os.path.join(T, "bin"),
          DOWNLOADS, DOCUMENTS, os.path.join(HOME, "Desktop")):
    os.makedirs(d)
# The stub engine: a derive fork (`-p`) says where it started and answers one line.
with open(os.path.join(T, "bin", "claude"), "w") as f:
    f.write('#!/bin/sh\ncase "$1" in\n  agents) echo "[]";;\n'
            '  -p) pwd >> "$SMINOS_STUB_LOG"; echo \'{"type": "result", "result": "keeps the lights on"}\';;\n'
            'esac\nexit 0\n')
os.chmod(os.path.join(T, "bin", "claude"), 0o755)
os.environ["PATH"] = os.path.join(T, "bin") + os.pathsep + os.environ["PATH"]
ORG, MACHINE = "org-1", "testhost"
with open(os.path.join(SH, "daemon", "hub.json"), "w") as f:
    json.dump({"hub": "http://127.0.0.1:9", "org": ORG, "machine": MACHINE}, f)
sys.path.insert(0, SCRIPTS)

import sminos  # noqa: E402

daemon = sminos.daemon_module()
SLEEPERS = []


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def register(pid, name, root):
    write(os.path.join(SH, "projects", pid, "project.json"),
          {"project": pid, "name": name, "remote": "", "root": root, "hub": {"url": "http://127.0.0.1:9", "org": ORG}})


def checkout(d, pid=None, name="app"):
    """A git checkout at `d`; with `pid`, its .smns names hub project `pid`."""
    os.makedirs(os.path.join(d, ".git"), exist_ok=True)
    if pid:
        write(os.path.join(d, ".smns"), {"project": pid, "name": name, "hub": {"org": ORG}})
    return d


def transcript(cwd, sid, tools=0):
    path = os.path.join(PROJECTS, cwd.replace("/", "-").replace(".", "-"), sid + ".jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(json.dumps({"type": "user", "cwd": cwd, "sessionId": sid, "message": {"role": "user", "content": "hi"}})
                + "\n")
        for i in range(tools):   # derive asks a member whose model made ten tool calls
            f.write(json.dumps({"type": "assistant", "cwd": cwd, "sessionId": sid, "message": {
                "role": "assistant", "content": [{"type": "tool_use", "id": "toolu_%d" % i, "name": "Bash",
                                                  "input": {"command": "true"}}]}}) + "\n")


def live_session(cwd, tools=0):
    """A session whose engine record names a running process (a `sleep`)."""
    sid = str(uuid.uuid4())
    p = subprocess.Popen(["sleep", "600"])
    SLEEPERS.append(p)
    transcript(cwd, sid, tools)
    rec = {"pid": p.pid, "sessionId": sid, "cwd": cwd, "kind": "interactive", "entrypoint": "cli",
           "name": "s-" + sid[:4], "nameSource": "derived", "status": "idle"}
    write(os.path.join(HOME, ".claude", "sessions", "%d.json" % p.pid), rec)
    sminos.transcripts_now()   # the index lists the transcript just written
    return sid, rec


def quietly(fn, *args, **kwargs):
    import io
    out, err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        return fn(*args, **kwargs)
    finally:
        said, sys.stdout, sys.stderr = sys.stderr.getvalue(), out, err
        assert "tick failed" not in said, said


@contextlib.contextmanager
def in_dir(d):
    """This process's working directory at `d` for the block."""
    before = os.getcwd()
    os.chdir(d)
    try:
        yield
    finally:
        os.chdir(before)


@contextlib.contextmanager
def tcc(on=True):
    """The platform the guard reads: macOS's privacy folders, or none (Linux)."""
    with mock.patch.object(sminos, "TCC", on, create=True):
        yield


@contextlib.contextmanager
def unreadable(d):
    """`d` refuses every read below it, as a folder TCC withholds does (a
    process run as root reads it all the same: Touches is the proof there)."""
    os.chmod(d, 0)
    try:
        yield
    finally:
        os.chmod(d, 0o755)


class Touches:
    """Every look this process takes at a path at or under `prefix`: a stat
    (isdir, isfile, exists and realpath go through one), a listing, an open,
    a write, and a child started there or pointed there (`git -C`)."""

    NAMES = ("stat", "lstat", "listdir", "scandir", "open", "access", "mkdir", "makedirs", "utime", "unlink",
             "rename", "replace", "chmod")

    def __init__(self, *prefixes):
        self.prefixes = [p.casefold().rstrip("/") for p in prefixes]
        self.seen = []

    def note(self, path):
        if isinstance(path, int):
            return
        try:
            p = os.path.abspath(os.fsdecode(path)).casefold()
        except (TypeError, ValueError):
            return
        if any(p == x or p.startswith(x + "/") for x in self.prefixes):
            self.seen.append(p)

    def wrap(self, fn):
        def looked(path, *a, **k):
            self.note(path)
            return fn(path, *a, **k)
        return looked

    def __enter__(self):
        self.stack = contextlib.ExitStack()
        for name in self.NAMES:
            self.stack.enter_context(mock.patch.object(os, name, self.wrap(getattr(os, name))))
        self.stack.enter_context(mock.patch.object(builtins, "open", self.wrap(builtins.open)))
        real = subprocess.Popen
        touches = self

        class Popen(real):
            def __init__(self, args, *a, **k):
                if k.get("cwd"):
                    touches.note(k["cwd"])
                argv = list(args) if isinstance(args, (list, tuple)) else [args]
                for i, x in enumerate(argv[:-1]):
                    if x == "-C":
                        touches.note(argv[i + 1])
                super().__init__(args, *a, **k)

        self.stack.enter_context(mock.patch.object(subprocess, "Popen", Popen))
        return self

    def __exit__(self, *exc):
        self.stack.close()


def own_events(project, sid):
    return [(e["kind"], e.get("reason"), e.get("project")) for e in sminos._own_events(project, sid)]


def latest(project, sid):
    return sminos.latest_membership(sminos._own_events(project, sid))


class DaemonView(unittest.TestCase):
    """The daemon's view: its working directory is not in the folder."""

    def test_a_downloads_session_is_told_from_the_registry_without_a_look_there(self):
        pid = str(uuid.uuid4())
        d = checkout(os.path.join(DOWNLOADS, "app"), pid)
        register(pid, "app", d)
        sid, rec = live_session(d)
        with tcc(), in_dir(d):   # its own hook, where it works: the folder is read, and it joins
            sminos.forget_caches()
            quietly(daemon.tick_all)
        project = sminos.known_project(pid)
        self.assertEqual(latest(project, sid), "joined")
        held = own_events(project, sid)
        with tcc(), in_dir(T), unreadable(d), Touches(DOWNLOADS) as t:
            for _ in range(2):
                sminos.forget_caches()
                quietly(daemon.tick_all)
            sminos.forget_caches()
            told = sminos.record_project(rec)
            found = sminos.resolve_project(os.path.join(d, "sub"))
        self.assertEqual(t.seen, [], "nothing under ~/Downloads was looked at")
        self.assertEqual((told.id, sminos.guessed(told)), (pid, True))
        self.assertEqual(found.id, pid, "a directory below a registered root is that project's")
        self.assertEqual(own_events(project, sid), held, "its record is as it was")
        self.assertEqual(own_events(sminos.own_machine_project(), sid), [], "and it joined nowhere else")

    def test_one_nothing_registered_tells_is_unknown_and_its_member_stays_as_recorded(self):
        # A clone of a project whose registered root is another clone: no
        # registration names this directory.
        pid = str(uuid.uuid4())
        first = checkout(os.path.join(T, "r", "first"), pid, "twin")
        register(pid, "twin", first)
        d = checkout(os.path.join(DOWNLOADS, "twin"), pid, "twin")
        sid, rec = live_session(d)
        with tcc(), in_dir(d):
            sminos.forget_caches()
            quietly(daemon.tick_all)
        project = sminos.known_project(pid)
        self.assertEqual((project.root, latest(project, sid)), (first, "joined"))
        held = own_events(project, sid)
        with tcc(), in_dir(T), unreadable(d), Touches(DOWNLOADS) as t:
            for _ in range(2):
                sminos.forget_caches()
                quietly(daemon.tick_all)
            sminos.forget_caches()
            unknown = sminos.resolve_project(d)
            told = sminos.record_project(rec)
        self.assertEqual(own_events(project, sid), held, "no move, no retirement, no rewrite")
        self.assertEqual(own_events(sminos.own_machine_project(), sid), [], "it was moved to no other project")
        self.assertEqual(t.seen, [], "nothing under ~/Downloads was looked at")
        self.assertIsNone(unknown, "no registration tells the directory: unknown")
        self.assertEqual((told.id, sminos.guessed(told)), (pid, True), "the session reads as its recorded member")

    def test_a_seat_nothing_tells_is_in_no_project_made_up_for_it(self):
        d = os.path.join(DOWNLOADS, "loose")
        os.makedirs(d)
        seat = {"alias": "loose", "group": "fleet", "current": "", "cwd": d, "status": "idle"}
        with tcc(), in_dir(T), Touches(DOWNLOADS) as t:
            sminos.forget_caches()
            p = sminos.seat_project(seat)
        self.assertEqual(t.seen, [])
        self.assertIsNone(p, "neither a local project named after the directory nor the machine's")

    def test_a_process_inside_the_folder_still_reads_it(self):
        pid = str(uuid.uuid4())
        d = checkout(os.path.join(DOWNLOADS, "inside"), pid, "inside")
        with tcc(), in_dir(os.path.join(DOWNLOADS)), Touches(DOWNLOADS) as t:
            sminos.forget_caches()
            p = sminos.resolve_project(d)
        self.assertEqual((p.id, sminos.guessed(p)), (pid, False), "read off its .smns")
        self.assertNotEqual(t.seen, [])

    def test_linux_is_unchanged(self):
        pid = str(uuid.uuid4())
        d = checkout(os.path.join(DOWNLOADS, "linux"), pid, "linux")
        with tcc(False), in_dir(T), Touches(DOWNLOADS) as t:
            sminos.forget_caches()
            p = sminos.resolve_project(d)
            refused, launch = sminos.read_refused(d), sminos.launch_refused(HOME)
        self.assertEqual((p.id, sminos.guessed(p)), (pid, False), "read off its .smns, as before")
        self.assertNotEqual(t.seen, [])
        self.assertEqual((refused, launch), (False, ""))


class Derive(unittest.TestCase):
    """derive forks no member in, or above, a protected folder."""

    def setUp(self):
        self.home = live_session(HOME, tools=10)[0]
        self.docs_dir = os.path.join(DOCUMENTS, "College")
        os.makedirs(self.docs_dir, exist_ok=True)
        self.docs = live_session(self.docs_dir, tools=10)[0]
        self.plain_dir = os.path.join(T, "r", "plain-%s" % uuid.uuid4().hex[:6])
        os.makedirs(self.plain_dir)
        self.plain = live_session(self.plain_dir, tools=10)[0]
        with tcc(), in_dir(self.docs_dir):   # each joins: the one in ~/Documents from where it works
            sminos.forget_caches()
            quietly(daemon.tick_all)
        self.own = sminos.own_machine_project()
        for sid in (self.home, self.docs, self.plain):
            self.assertEqual(latest(self.own, sid), "joined")
        open(os.environ["SMINOS_STUB_LOG"], "w").close()

    def forks(self):
        with open(os.environ["SMINOS_STUB_LOG"]) as f:
            return [x for x in f.read().splitlines() if x]

    def derive(self, sid, held_off=True):
        sminos.forget_caches()
        m = next(m for m in sminos.members(self.own) if m.session == sid)
        return quietly(sminos.derive_member, self.own, m, held_off=held_off)

    def lines(self, sid):
        return [e for e in sminos._own_events(self.own, sid) if e["kind"] == "in-charge"]

    def logged(self, sid):
        try:
            with open(os.path.join(SH, "daemon.log")) as f:
                return [x for x in f if sid[:8] in x]
        except FileNotFoundError:
            return []

    def test_a_member_in_home_or_documents_is_skipped_and_a_plain_one_forked(self):
        with tcc(), in_dir(T):
            for _ in range(2):   # the daemon's runs, five minutes apart
                outcomes = [self.derive(sid) for sid in (self.home, self.docs)]
                self.assertEqual(outcomes, ["refused", "refused"])
            self.assertEqual(self.derive(self.plain), "derived")
        self.assertEqual(self.forks(), [self.plain_dir], "the only fork started in the plain directory")
        for sid in (self.home, self.docs):
            self.assertEqual(self.lines(sid), [], "nothing recorded")
            self.assertEqual(len(self.logged(sid)), 1, "one daemon.log line for the session, not one per run")
        self.assertEqual(len(self.lines(self.plain)), 1)

    def test_derive_member_from_the_members_own_directory_forks_there(self):
        with tcc(), in_dir(self.docs_dir):
            self.assertEqual(self.derive(self.docs, held_off=False), "derived")
        self.assertEqual(self.forks(), [self.docs_dir])

    def test_linux_forks_in_home_as_before(self):
        with tcc(False), in_dir(T):
            self.assertEqual(self.derive(self.home), "derived")
        self.assertEqual(self.forks(), [HOME])


def tearDownModule():
    for p in SLEEPERS:
        p.kill()
        p.wait()
    for root, dirs, _ in os.walk(T):
        for d in dirs:
            try:
                os.chmod(os.path.join(root, d), 0o755)
            except OSError:
                pass
    shutil.rmtree(T, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
