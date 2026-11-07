#!/usr/bin/env python3
"""The `snapshots?` responder (P5 O18 M3; MAWS's
docs/doperpowers/plans/2026-11-05-p5-o18-message-reach.md, D7 and Interfaces
§B): an endpoint that lost its policy cache asks sminos, one project at a
time, for the newest stored `joined` and `state` of each remote session
writer, plain and stream, page after page until sminos marks the project's
last page `done`; sminos answers each `snapshots? {id, project, after?}`
with one bounded page `snapshots {id, project, events, next, done}`.

The uplink runs in this process: one `Link` on a lane that keeps what it is
sent, or `sminos_uplink.run_rl10` against sminos's endpoint stand-in
(endpoint_standin.py), in process too.

Hermetic: every test has its own HOME, SMINOS_HOME and MAWS_USER_DATA under
one temporary directory; nothing listens beyond a Unix socket there.
Run: python3 -B sminos/tests/test_snapshots.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "sminos" / "scripts"
BASE = tempfile.mkdtemp(prefix="sms.", dir="/tmp")   # short: a Unix socket's path is bounded
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import endpoint_standin  # noqa: E402
import sminos  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

DIGEST = "0123456789abcdef"
DEV = {"kind": "device", "member": "mem-1", "device": "dev-a", "keyId": "k-dev-a"}


def sid(n):
    return "5e%06x-0000-4000-8000-%012x" % (n, n)


def wait_for(pred, timeout=30, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = pred()
        if got:
            return got
        time.sleep(step)
    return pred()


def daemon_log():
    try:
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
            return f.read()
    except OSError:
        return ""


def stored(e):
    """An event as a page sends it: as stored, less `verified`."""
    return {k: v for k, v in e.items() if k != "verified"}


class Lane:
    """A Link's lane that keeps what it is sent, written as taken."""

    def __init__(self):
        self.sent = []

    def send(self, frames, then=None):
        self.sent += frames
        if then is not None:
            then({})

    def posting(self):
        return False

    def queued(self):
        return 0

    def hold(self, _project):
        return None, []

    def release(self, _project):
        pass

    def close(self):
        pass


class Machine(unittest.TestCase):
    """A fresh installation per test, `testhost` of org-1 cut over to its
    endpoint, formerly `oldhost`, with one hub project of org-1."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"),
                          MAWS_USER_DATA=os.path.join(home, "m"))
        self.home = home
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        self.epdir = os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint")
        sminos.write_json(rl10.identity_path(), {
            "org": "org-1", "hub": "http://127.0.0.1:9", "name": "testhost", "former": {"oldhost": []},
            "ref": "machine-ref-1", "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z",
            "build": "b"}, mode=0o600)
        sminos.forget_caches()
        rl10._SAID.update(find=None, revoked=None)
        self.hp = self.project("hubbed", hub=True)

    def project(self, name, hub=False):
        root = os.path.join(self.home, name)
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", root], check=True)
        subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "project", "init", "--name", name],
                       cwd=root, check=True, capture_output=True)
        if hub:
            smns = os.path.join(root, ".smns")
            d = json.loads(Path(smns).read_text())
            d["hub"] = {"url": "http://127.0.0.1:9", "org": "org-1"}
            Path(smns).write_text(json.dumps(d))
        sminos.forget_caches()
        project = sminos.resolve_project(root)
        sminos.project_path(project, "log")
        return project

    def link(self):
        cred = {"org": "org-1", "hub": "http://127.0.0.1:9", "machine": "testhost", "key": None}
        link = uplink.Link(cred, {}, transport=mock.Mock(number=1))
        self.addCleanup(link.close)
        link.generation = 1
        link.log_lane = link.session_lane = Lane()
        return link

    def put(self, writer, kind, text="", project=None):
        """The writer's next event, stored as an arrival over RL10 is (with `verified`)."""
        project = project or self.hp
        path = sminos.writer_path(project, writer)
        seq = len(Path(path).read_text().splitlines()) + 1 if os.path.exists(path) else 1
        e = {"ts": "2026-11-05T01:%02d:%02d.000Z" % (seq // 60, seq % 60), "writer": writer, "seq": seq,
             "kind": kind, "from": "m", "to": [], "text": text, "verified": {"signer": DEV}}
        self.assertEqual(hublog.append_verbatim(project, e), "appended")
        return e

    def remote(self, writer, text="", project=None):
        """A remote session writer with an older and a newer `joined` and
        `state`, and a `say` between: (its newest joined, its newest state)."""
        for kind in ("joined", "state", "say"):
            self.put(writer, kind, text, project)
        return self.put(writer, "joined", project=project), self.put(writer, "state", text, project)

    def ask(self, link, project=None, after=None, ask="a1"):
        project = project or self.hp
        frame = {"t": "snapshots?", "id": ask, "project": project if isinstance(project, str) else project.id}
        if after is not None:
            frame["after"] = after
        link.dispatch(frame, None)
        answers = link.session_lane.sent
        link.session_lane.sent = []
        self.assertEqual(len(answers), 1, answers)
        return answers[0]

    def pages(self, link, project=None):
        """Every page of a project, asked as the endpoint asks: each past the last's `next`."""
        out, after = [], None
        for n in range(1000):
            page = self.ask(link, project, after, ask="a%d" % n)
            out.append(page)
            if page["done"]:
                return out
            after = page["next"]
        self.fail("no last page")


class Responder(Machine):

    def test_a_project_of_many_snapshots_is_answered_page_by_page(self):
        expected = []
        for n in range(120):
            writer = "farhost/%s" % sid(n) if n % 3 else "farhost/%s~%s" % (sid(n), DIGEST)
            expected += [stored(e) for e in self.remote(writer)]
        # Not remote session writers: this machine's, under its name and its former one, a stream of one of
        # them, and a person's writer; none of them is sent.
        for writer in ("testhost/%s" % sid(900), "testhost/%s~%s" % (sid(901), DIGEST), "oldhost/%s" % sid(902),
                       "hub/mem-1", "farhost/human"):
            self.remote(writer)
        expected.sort(key=lambda e: (e["writer"], e["seq"]))
        link = self.link()
        pages = self.pages(link)
        self.assertEqual([len(p["events"]) for p in pages], [200, 40], "pages of at most SNAPSHOT_PAGE events")
        self.assertEqual([p["done"] for p in pages], [False, True], "only the last marked done")
        self.assertEqual([p["t"] for p in pages], ["snapshots"] * 2)
        self.assertEqual([p["id"] for p in pages], ["a0", "a1"], "each answers its own ask")
        self.assertEqual({p["project"] for p in pages}, {self.hp.id})
        self.assertEqual(pages[0]["next"], pages[0]["events"][-1]["writer"], "next is the page's last writer")
        self.assertIsNone(pages[-1]["next"])
        got = [e for p in pages for e in p["events"]]
        self.assertEqual(got, expected, "every remote writer's newest joined and state, as stored less verified, "
                                        "in writer order, each once")
        self.assertTrue(any("~" in e["writer"] for e in got), "streams are carried")
        # A page resumes where the cursor says, whoever asks.
        middle = expected[99]["writer"]
        page = self.ask(link, after=middle)
        self.assertEqual(page["events"][0], next(e for e in expected if e["writer"] > middle))
        # A new snapshot is the newest the next ask sends (the memo follows the log).
        last = expected[-1]["writer"]
        newer = self.put(last, "state", "newer")
        page = self.ask(link, after=expected[-3]["writer"])
        self.assertEqual(page["events"][-1], stored(newer))

    def test_a_page_is_bounded_in_bytes(self):
        for n in range(12):
            self.remote("farhost/%s" % sid(n), text="x" * 1500)
        link = self.link()
        with mock.patch.object(uplink, "LANE_ENTRY", 8 * 1024):
            pages = self.pages(link)
        self.assertGreater(len(pages), 2)
        for p in pages:
            self.assertLessEqual(len(json.dumps(p, ensure_ascii=False).encode("utf-8")), 8 * 1024)
            self.assertEqual(len(p["events"]) % 2, 0, "whole writers: a writer's pair is never split")
        self.assertEqual(len({e["writer"] for p in pages for e in p["events"]}), 12)
        # A writer larger than the bound still goes, alone on its page, so the rebuild always moves on.
        with mock.patch.object(uplink, "LANE_ENTRY", 1024):
            pages = self.pages(link)
        self.assertEqual([len(p["events"]) for p in pages], [2] * 12)

    def test_a_project_with_none_answers_one_empty_page_marked_done(self):
        self.remote("testhost/%s" % sid(1))   # its own only
        link = self.link()
        self.assertEqual(self.pages(link), [{"t": "snapshots", "id": "a0", "project": self.hp.id, "events": [],
                                             "next": None, "done": True}])
        self.assertEqual(self.ask(link, after="zzz")["events"], [], "past the last writer: none")

    def test_a_project_not_of_this_org_answers_done_and_is_said(self):
        local = self.project("local")
        self.remote("farhost/%s" % sid(1), project=local)
        link = self.link()
        for project in (local.id, "nosuchproject"):
            page = self.ask(link, project)
            self.assertEqual((page["project"], page["events"], page["next"], page["done"]), (project, [], None, True))
            self.assertIn("snapshots? for project %r, which is no hub project" % project, daemon_log())


class OverTheSocket(Machine):
    """The endpoint's rebuild as it runs: `snapshots?` down the RL10 socket,
    the next asked past each answer's `next` until one is `done`."""

    def test_a_rebuild_pages_through_the_endpoint_socket(self):
        expected = []
        for n in range(9):
            expected += [stored(e) for e in self.remote("farhost/%s" % sid(n))]
        ep = endpoint_standin.Endpoint(self.epdir)
        pages = []

        def handler(frame):
            if frame.get("t") != "snapshots":
                return []
            pages.append(frame)
            return [] if frame["done"] else [{"t": "snapshots?", "id": "p%d" % len(pages),
                                              "project": frame["project"], "after": frame["next"]}]
        ep.handler = handler
        ep.start()
        self.addCleanup(ep.stop)
        halt, box = threading.Event(), {}
        with mock.patch.object(uplink, "SNAPSHOT_PAGE", 4):
            thread = threading.Thread(target=lambda: box.update(kept=uplink.run_rl10(halt.is_set, halt)),
                                      daemon=True)
            thread.start()
            try:
                ep.wait(lambda f: f["t"] == "hello" and f.get("project") == self.hp.id)
                ep.send({"t": "snapshots?", "id": "p0", "project": self.hp.id})
                self.assertTrue(wait_for(lambda: pages and pages[-1]["done"]), pages)
            finally:
                halt.set()
                thread.join(30)
                if box.get("kept") is not None:
                    box["kept"].close()
        self.assertEqual([len(p["events"]) for p in pages], [4, 4, 4, 4, 2])
        self.assertEqual([p["id"] for p in pages], ["p0", "p1", "p2", "p3", "p4"])
        self.assertEqual([e for p in pages for e in p["events"]], expected)


def tearDownModule():
    shutil.rmtree(BASE, True)


if __name__ == "__main__":
    unittest.main()
