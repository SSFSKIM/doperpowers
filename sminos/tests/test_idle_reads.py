#!/usr/bin/env python3
"""What an idle uplink reads again (sminos 1.46.1; the MacBook's uplink at
11-13 % of a core, 7,550 file syscalls a second with nothing happening,
2026-11-11): uplink.json read by stat, and once a project's upload pass;
the plugin manifest read by stat; and the host pass walking only a host
file that moved or holds something past its cursor. Counted by wrapping
the calls, never timed. Hermetic: every test has its own HOME and
SMINOS_HOME under one temporary directory.
Run: python3 -B sminos/tests/test_idle_reads.py
"""

import builtins
import contextlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "sminos" / "scripts"
BASE = os.path.realpath(tempfile.mkdtemp(prefix="smi.", dir="/tmp"))
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import sminos  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_uplink as uplink  # noqa: E402
from rl10_identity import write_identity  # noqa: E402

S1 = "6f000001-0000-4000-8000-0000000000f1"
S2 = "6f000002-0000-4000-8000-0000000000f2"
S3 = "6f000003-0000-4000-8000-0000000000f3"
S4 = "6f000004-0000-4000-8000-0000000000f4"
S5 = "6f000005-0000-4000-8000-0000000000f5"
S9 = "6f000009-0000-4000-8000-0000000000f9"
DEV = {"kind": "device", "member": "mem-1", "device": "dev-a", "keyId": "k-dev-a"}


class Calls:
    """The file calls made while it is installed: (call, path, whether it
    raised OSError), for builtins.open, os.stat, os.listdir, os.scandir and
    os.getcwd."""

    def __init__(self):
        self.made = []

    @contextlib.contextmanager
    def counting(self):
        real = {"open": builtins.open, "stat": os.stat, "listdir": os.listdir, "scandir": os.scandir,
                "getcwd": os.getcwd}

        def wrap(name, fn):
            def call(*args, **kwargs):
                path = os.fspath(args[0]) if args and isinstance(args[0], (str, bytes, os.PathLike)) else ""
                try:
                    out = fn(*args, **kwargs)
                except OSError:
                    self.made.append((name, path, False))
                    raise
                self.made.append((name, path, True))
                return out
            return call
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("builtins.open", wrap("open", real["open"])))
            for name in ("stat", "listdir", "scandir", "getcwd"):
                stack.enter_context(mock.patch("os." + name, wrap(name, real[name])))
            yield self

    def of(self, name, path=None, ok=None):
        return [c for c in self.made if c[0] == name and (path is None or c[1] == path)
                and (ok is None or c[2] == ok)]


class Lane:
    """A Link's lane that keeps what it is sent, written as taken at once."""

    def __init__(self, run_thens=True):
        self.sent, self.run_thens = [], run_thens

    def send(self, frames, then=None):
        self.sent += frames
        if then is not None and self.run_thens:
            then()

    def posting(self):
        return False

    def queued(self):
        return 0

    def close(self):
        pass


class Machine(unittest.TestCase):
    """A fresh installation per test, `testhost` cut over into org-1."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"))
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        self.cut_over()
        rl10._SAID.update(find=None, revoked=None)

    def cut_over(self, name="testhost", former=None):
        write_identity(os.environ["SMINOS_HOME"], name, former=former)
        sminos.forget_caches()

    def project(self, name):
        pid = "6f00%04d-0000-4000-8000-%012d" % (len(name), sum(map(ord, name)))
        p = sminos.make_project(pid, name, "", "", {"url": "http://127.0.0.1:9", "org": "org-1"})
        sminos.project_path(p, "log")
        sminos.forget_caches()
        return sminos.find_project(pid)

    def link(self):
        cred = {"org": "org-1", "hub": "http://127.0.0.1:9", "machine": "testhost", "key": None}
        link = uplink.Link(cred, {}, transport=mock.Mock(number=1))
        self.addCleanup(link.close)
        link.generation = 1
        link.log_lane = link.session_lane = Lane()
        link.members_before = lambda project, sessions: True   # the member frames are another test's
        return link

    def write_lines(self, project, writer, events, store="log"):
        """Events written as a writer file holds them, under any writer name."""
        path = sminos.store_path(project, store, writer)
        with open(path, "a") as f:
            for e in events:
                f.write(json.dumps({"writer": writer, **e}) + "\n")


# ------------------------------------------------------------- A: uplink.json


class UplinkState(Machine):
    def setUp(self):
        super().setUp()
        self.p = self.project("work")
        self.hl = hublog.HubLog(self.p, {"key": None, "machine": "testhost"})
        self.path = os.path.join(self.p.home, hublog.STATE_FILE)
        self.w = "testhost/" + S1
        self.hl.save({"host_sent": {self.w: 1}, "voided": {}, "dead": {}})

    def test_an_unchanged_file_is_not_opened_again(self):
        link = self.link()
        sminos.log_append(self.p, self.w, "say", to=[], text="one")
        self.hl.on_have({"have": {}})
        self.hl.notices_owed = False
        link.upload(self.hl)
        link.host_pass(self.hl)
        calls = Calls()
        with calls.counting():
            link.upload(self.hl)
            link.host_pass(self.hl)
            self.hl.state()
            self.hl.dead(), self.hl.voided(), self.hl.host_sent(), self.hl.spent()
        self.assertEqual(calls.of("open", self.path), [], "read by stat while it holds still")
        self.assertTrue(calls.of("stat", self.path))

    def test_one_pass_reads_it_once(self):
        """The draw's dead and voided, and the host pass's cursor: one read.
        A write's continuation, which reads it to change it, runs between
        ticks (the lane's ("sent", thens)), not in the pass."""
        link = self.link()
        link.log_lane = link.session_lane = Lane(run_thens=False)
        sminos.log_append(self.p, self.w, "say", to=[], text="one")
        sminos._append(self.p, self.w, [{"kind": "message", "session": S1, "text": t} for t in ("sent", "not yet")],
                       store=sminos.HOST_STORE)   # the cursor is at 1
        self.hl.on_have({"have": {}})
        self.hl.notices_owed = False
        with mock.patch.object(self.hl, "state", wraps=self.hl.state) as state:
            link.upload_pass(self.hl, None)
        kinds = [f.get("t") for f in link.log_lane.sent]
        self.assertIn("events", kinds, "a fresh draw uploaded")
        self.assertIn("session", kinds, "and the host pass sent")
        self.assertEqual(state.call_count, 1)

    def test_a_save_and_an_outside_rename_are_seen_at_the_next_read(self):
        self.assertEqual(self.hl.host_sent(), {self.w: 1})
        self.hl.keep_host_sent({self.w: 4})
        self.assertEqual(self.hl.host_sent(), {self.w: 4}, "a save")
        tmp = self.path + ".outside"
        Path(tmp).write_text(json.dumps({"host_sent": {self.w: 7}}))
        os.replace(tmp, self.path)
        self.assertEqual(self.hl.host_sent(), {self.w: 7}, "a rewrite by rename from outside")
        Path(tmp).write_text("[1, 2]")
        os.replace(tmp, self.path)
        self.assertEqual(self.hl.state(), {}, "not a JSON object")
        os.unlink(self.path)
        self.assertEqual(self.hl.state(), {}, "missing")

    def test_a_caller_changing_its_dict_changes_no_one_elses(self):
        d = self.hl.state()
        d["host_sent"][self.w] = 99
        d["notices"] = ["x"]
        self.assertEqual(self.hl.state(), {"host_sent": {self.w: 1}, "voided": {}, "dead": {}})
        self.assertIsNot(self.hl.state(), self.hl.state())


# ------------------------------------------------------------- D: the plugin manifest


class Desk(Machine):
    def test_the_manifest_is_read_by_stat(self):
        """desk(), in every project's presence: the version it reports read
        again only once the manifest moved (a bump alone restarts nothing)."""
        version = json.loads(Path(hublog.PLUGIN_MANIFEST).read_text())["version"]
        hublog.desk()
        calls = Calls()
        with calls.counting():
            got = [hublog.desk()["sminos"] for _ in range(3)]
        self.assertEqual(got, [version] * 3)
        self.assertEqual(calls.of("open", hublog.PLUGIN_MANIFEST), [])
        manifest = Path(BASE, "plugin.json")
        manifest.write_text(json.dumps({"version": "9.9.9"}))
        with mock.patch.object(hublog, "PLUGIN_MANIFEST", str(manifest)):
            self.assertEqual(hublog.desk()["sminos"], "9.9.9")
            tmp = Path(BASE, "plugin.json.tmp")
            tmp.write_text(json.dumps({"version": "9.9.10"}))
            os.replace(tmp, manifest)
            self.assertEqual(hublog.desk()["sminos"], "9.9.10", "a new manifest is seen")
            manifest.write_text("[]")
            self.assertEqual(hublog.desk()["sminos"], "unknown")


# ------------------------------------------------------------- F: the host pass


class HostPass(Machine):
    def setUp(self):
        super().setUp()
        self.p = self.project("work")
        self.hl = hublog.HubLog(self.p, {"key": None, "machine": "testhost"})
        self.link = self.link()
        self.w = "testhost/" + S1

    def host(self, writer, *texts):
        sminos._append(self.p, writer, [{"kind": "message", "session": sminos.writer_session(writer), "text": t}
                                        for t in texts], store=sminos.HOST_STORE)

    def test_an_unchanged_sent_file_is_not_walked_again(self):
        self.host(self.w, "one", "two")
        self.link.host_pass(self.hl)
        self.assertEqual(self.hl.host_sent(), {self.w: 2})
        sent = len(self.link.session_lane.sent)
        with mock.patch.object(self.hl, "is_own", wraps=self.hl.is_own) as own:
            self.link.host_pass(self.hl)
            self.link.host_pass(self.hl)
        self.assertEqual(own.call_count, 0, "nothing in it past the cursor, and it did not move")
        self.assertEqual(len(self.link.session_lane.sent), sent)

    def test_an_appended_event_goes_up_at_the_next_pass(self):
        self.host(self.w, "one")
        self.link.host_pass(self.hl)
        self.link.host_pass(self.hl)
        before = len(self.link.session_lane.sent)
        self.host(self.w, "two")
        self.link.host_pass(self.hl)
        self.assertEqual(len(self.link.session_lane.sent), before + 1)
        self.assertIn('"two"', json.dumps(self.link.session_lane.sent[-1]))
        self.assertEqual(self.hl.host_sent(), {self.w: 2})

    def test_a_cursor_that_went_back_sends_again(self):
        """The skip is the cursor as it is now, not as the file was last walked."""
        self.host(self.w, "one", "two")
        self.link.host_pass(self.hl)
        before = len(self.link.session_lane.sent)
        self.hl.save({**self.hl.state(), "host_sent": {}})
        self.link.host_queued.clear()
        self.link.host_pass(self.hl)
        self.assertEqual(len(self.link.session_lane.sent), before + 2, "both again")

    def test_again_owes_the_last_ones_whatever_the_skip(self):
        self.host(self.w, "one", "two")
        self.link.host_pass(self.hl)
        self.link.host_pass(self.hl)
        before = len(self.link.session_lane.sent)
        self.link.host_pass(self.hl, again=True)
        self.assertEqual(len(self.link.session_lane.sent), before + 2, "each session's last ones")

    def test_a_rename_of_the_machine_is_followed(self):
        old = "oldhost/" + S2
        self.host(old, "before the rename")
        self.link.host_pass(self.hl)
        self.assertFalse(self.hl.is_own(old))
        self.assertEqual(self.link.session_lane.sent, [], "another machine's name: not this machine's")
        self.cut_over(former={"oldhost": [S2]})
        self.assertTrue(self.hl.is_own(old), "a former name, as the welcome that renamed it says")
        self.link.host_pass(self.hl)
        self.assertEqual(len(self.link.session_lane.sent), 1)
        self.assertIn('"before the rename"', json.dumps(self.link.session_lane.sent[0]))
        self.cut_over()
        self.assertFalse(self.hl.is_own(old), "a name the identity no longer lists")
        self.assertTrue(self.hl.is_own(self.w))


def tearDownModule():
    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
