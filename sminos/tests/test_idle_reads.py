#!/usr/bin/env python3
"""What an idle uplink reads again (both Macs' uplinks at 11-13 % of a
core with nothing happening, the MacBook's making 7,550 file syscalls a
second, 2026-11-11): uplink.json read by stat, and once a project's upload pass;
where a session whose directory may not be read is recorded, told from one
listing of each log directory a cache generation, never by opening every
project's files under every name, and the registrations from the listing
alone; the working directory asked only for a path inside a protected
folder; the plugin manifest read by stat; the words and reach passes on the shared
merged log, its addressee index built once while no file moved; and the
host pass walking only a host file that moved or holds something past its
cursor. Counted by wrapping the calls, never timed. Hermetic: every test
has its own HOME and SMINOS_HOME under one temporary directory.
Run: python3 -B sminos/tests/test_idle_reads.py
"""

import builtins
import collections
import contextlib
import heapq
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


# ------------------------------------------------------------- B: where a session is recorded


def old_writer_events(project, host, session):
    """recorded_project's read as it was at 1.46.0 (sminos._writer_events): the reference."""
    where = os.path.join(project.home, "log")
    paths = [os.path.join(where, "%s.%s.jsonl" % (host, session))]
    base = "%s/%s" % (host, session)
    paths += [sminos.writer_path(project, w) for w in sorted(sminos.audience_module().streams_of(project))
              if sminos.writer_base(w) == base]
    files = []
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                files.append([e for e in map(sminos.parse_event, f) if e])
        except OSError:
            continue
    if len(files) <= 1:
        return files[0] if files else []
    return list(heapq.merge(*files, key=lambda e: e["ts"]))


def old_own_events(project, session):
    return [e for host, held in sminos.machine_identity()[1].items() if session in held
            for e in old_writer_events(project, host, session)] \
        + old_writer_events(project, sminos.host_name(), session)


def old_recorded_project(session):
    import glob
    best, at = None, ""
    for path in glob.glob(os.path.join(sminos.projects_root(), "*", "project.json")):
        p = sminos.known_project(os.path.basename(os.path.dirname(path)))
        last = next((e for e in reversed(old_own_events(p, session)) if e["kind"] in sminos.MEMBERSHIP), None) \
            if p is not None else None
        if last is not None and last["kind"] == "joined" and str(last.get("ts") or "") >= at:
            best, at = p, str(last.get("ts") or "")
    return sminos.Guessed(*best) if best is not None else None


def old_last_project(session):
    import glob
    best, at = None, ""
    for path in glob.glob(os.path.join(sminos.projects_root(), "*", "project.json")):
        p = sminos.known_project(os.path.basename(os.path.dirname(path)))
        last = next((e for e in reversed(old_own_events(p, session)) if e["kind"] in sminos.MEMBERSHIP), None) \
            if p is not None else None
        if last is not None and str(last.get("ts") or "") >= at:
            best, at = (p, last), str(last.get("ts") or "")
    if best is not None and best[1]["kind"] == "retired" and best[1].get("reason") == "moved":
        dest = str(best[1].get("project") or "")
        return sminos.known_project(dest) if dest and sminos.valid_name(dest) else None
    return best[0] if best is not None else None


class Recorded(Machine):
    """Six projects; S1 joined in two of them, the later one its own; S2
    held under the machine's former name; S3's only file an audience
    stream; S4 moved out of one project to another; S5 recorded nowhere."""

    def setUp(self):
        super().setUp()
        self.cut_over(former={"oldhost": [S2]})
        self.ps = [self.project("p%d" % i) for i in range(6)]
        p0, p1, p2, p3, p4, p5 = self.ps

        def ev(seq, minute, kind, session, **fields):
            return {"ts": "2026-11-01T00:%02d:00.000Z" % minute, "seq": seq, "kind": kind, "session": session,
                    **fields}
        self.write_lines(p0, "testhost/" + S1, [ev(1, 1, "joined", S1), ev(2, 2, "retired", S1, reason="ended")])
        self.write_lines(p1, "testhost/" + S1, [ev(1, 3, "joined", S1)])
        self.write_lines(p2, "oldhost/" + S2, [ev(1, 5, "joined", S2)])
        self.write_lines(p3, "testhost/" + S2, [ev(1, 4, "joined", S2)])
        stream = sminos.stream_writer("testhost/" + S3, ["mem-1"])
        sminos.audience_module().keep_stream(p4, stream, ["mem-1"])
        self.write_lines(p4, stream, [ev(1, 6, "joined", S3)])
        self.write_lines(p5, "testhost/" + S4, [ev(1, 7, "joined", S4),
                                                ev(2, 8, "retired", S4, reason="moved", project=p0.id)])
        self.write_lines(p2, "mini/" + S9, [ev(1, 9, "joined", S9)])   # another machine's: never this session's
        Path(sminos.projects_root(), ".hidden", "log").mkdir(parents=True)
        unregistered = Path(sminos.projects_root(), "no-registration", "log")
        unregistered.mkdir(parents=True)
        (unregistered / ("testhost.%s.jsonl" % S5)).write_text(
            json.dumps({"writer": "testhost/" + S5, **ev(1, 9, "joined", S5)}) + "\n")
        sminos.forget_caches()
        self.sessions = (S1, S2, S3, S4, S5, S9)

    def test_the_answers_are_the_old_ones(self):
        expected = {s: (old_recorded_project(s), old_last_project(s)) for s in self.sessions}
        p0, p1, p2, _, p4, _ = self.ps
        self.assertEqual({s: tuple(p and p.id for p in got) for s, got in expected.items()},
                         {S1: (p1.id, p1.id), S2: (p2.id, p2.id), S3: (p4.id, p4.id), S4: (None, p0.id),
                          S5: (None, None), S9: (None, None)}, "the reference reads the cases this test meant")
        sminos.forget_caches()
        got = {s: (sminos.recorded_project(s), sminos.last_project(s)) for s in self.sessions}
        self.assertEqual(got, expected)
        self.assertTrue(all(sminos.guessed(r) for r, _ in got.values() if r is not None))

    def test_no_failed_open_and_one_listing_of_each_log_a_generation(self):
        logs = {os.path.join(p.home, "log") for p in self.ps}
        for generation in range(2):
            sminos.forget_caches()
            calls = Calls()
            with calls.counting():
                for s in self.sessions:
                    sminos.recorded_project(s)   # last_project reads as 1.46.0 did (below)
            self.assertEqual(calls.of("open", ok=False), [], "no open of a file that is not there")
            listed = collections.Counter(c[1] for c in calls.made if c[0] in ("listdir", "scandir"))
            self.assertTrue(logs <= set(listed), listed)
            self.assertEqual({d: n for d, n in listed.items() if d.endswith("/log") and n > 1}, {},
                             "generation %d" % generation)
            self.assertEqual([c for c in calls.of("stat", ok=False) if c[1].endswith("streams.json")], [],
                             "no project's missing streams.json asked once per session")

    def test_last_project_reads_the_files_as_they_are_when_asked(self):
        """last_project decides membership while the statements are unknown
        (_session_project takes it as the session's project, and a
        reconciliation can move it there), so it never answers from a
        listing another session's lookup took earlier in the generation: a
        writer file made since is read."""
        p3 = self.ps[3]
        self.listings_taken()
        self.write_lines(p3, "testhost/" + S5, [{"ts": "2026-11-01T00:30:00.000Z", "seq": 1, "kind": "joined",
                                                 "session": S5}])
        self.assertEqual(sminos.last_project(S5), old_last_project(S5))
        self.assertEqual(sminos.last_project(S5).id, p3.id)

    def test_last_project_reads_a_stream_made_since_another_lookup(self):
        p1 = self.ps[1]
        self.listings_taken()
        stream = sminos.stream_writer("testhost/" + S5, ["mem-2"])
        sminos.audience_module().keep_stream(p1, stream, ["mem-2"])
        self.write_lines(p1, stream, [{"ts": "2026-11-01T00:31:00.000Z", "seq": 1, "kind": "joined", "session": S5}])
        self.assertEqual(sminos.last_project(S5), old_last_project(S5))
        self.assertEqual(sminos.last_project(S5).id, p1.id)

    def listings_taken(self):
        """A new generation, in which another session was asked about first."""
        sminos.forget_caches()
        sminos.recorded_project(S1)
        sminos.last_project(S1)

    def test_the_registrations_from_the_listing_alone(self):
        """known_projects, every scan: the registrations in sorted(glob)'s
        order, a directory with none passed by, with no lstat of each."""
        import glob
        for pid in ("a", "a-b"):   # "a-b/" sorts before "a/" as a path, after "a" as a name
            Path(sminos.projects_root(), pid).mkdir()
            Path(sminos.projects_root(), pid, "project.json").write_text(
                json.dumps({"project": pid, "name": pid, "remote": "", "root": ""}))
        expected = [os.path.basename(os.path.dirname(path))
                    for path in sorted(glob.glob(os.path.join(sminos.projects_root(), "*", "project.json")))]
        with mock.patch("os.lstat", side_effect=AssertionError("lstat")):
            got = [p.id for p in sminos.known_projects([])]
        self.assertEqual(got, [pid for pid in expected])
        self.assertNotIn("no-registration", got)

    def test_a_file_made_is_seen_in_the_next_generation(self):
        self.assertIsNone(sminos.recorded_project(S5))
        p3 = self.ps[3]
        self.write_lines(p3, "testhost/" + S5, [{"ts": "2026-11-01T00:30:00.000Z", "seq": 1, "kind": "joined",
                                                 "session": S5}])
        sminos.forget_caches()
        self.assertEqual(sminos.recorded_project(S5).id, p3.id)
        self.assertEqual(sminos.last_project(S5).id, p3.id)


# ------------------------------------------------------------- C: the working directory


def old_withheld(path):
    if not sminos.TCC or not path:
        return False
    folder = sminos.protected_folder(sminos._abs(path))
    here = sminos._own_cwd()
    return bool(folder) and not (here and sminos._under(here, folder))


class Withheld(Machine):
    def test_no_working_directory_for_a_path_outside_every_folder(self):
        home = os.environ["HOME"]
        outside = [os.path.join(home, "Developer", "app"), "/opt/x", home, os.path.join(home, "Library", "x"), "/"]
        with mock.patch.object(sminos, "TCC", True), mock.patch("os.getcwd", side_effect=AssertionError("asked")):
            for path in outside:
                self.assertFalse(sminos.withheld(path), path)
                self.assertFalse(sminos.read_refused(path), path)

    def test_the_same_refusals_inside_one(self):
        home = os.environ["HOME"]
        inside = [os.path.join(home, "Downloads", "app"), os.path.join(home, "Documents"), "/Volumes/usb/x",
                  os.path.join(home, "Library", "CloudStorage", "d"), os.path.join(home, "Desktop", "a", "b")]
        cwds = [os.path.join(home, "Downloads", "w"), os.path.join(home, "Documents", "z"), "/Volumes/usb", "/tmp",
                None]
        with mock.patch.object(sminos, "TCC", True):
            for cwd in cwds:
                getcwd = mock.Mock(side_effect=OSError("gone")) if cwd is None else mock.Mock(return_value=cwd)
                with mock.patch("os.getcwd", getcwd):
                    for path in inside:
                        old = old_withheld(path)
                        self.assertEqual(sminos.withheld(path), old, (path, cwd))
                        self.assertEqual(sminos.read_refused(path), old, (path, cwd))
        with mock.patch.object(sminos, "TCC", False), mock.patch("os.getcwd", side_effect=AssertionError("asked")):
            self.assertFalse(sminos.withheld(inside[0]), "no protected folders off macOS")


# ------------------------------------------------------------- E: the words and reach passes


def member(sid):
    return sminos.Member(session=sid, short=sid[:8], alias="m", name_source="derived", machine="testhost",
                         local=True, state="idle", state_age=None, charge="", charge_source="", status="", by="",
                         worktree="", seat=None)


class WordsPass(Machine):
    def setUp(self):
        super().setUp()
        self.p = self.project("work")
        self.arrive("hub/mem-1", 1, "human", signer=DEV)          # a person's words: words?
        self.arrive("mini/" + S9, 1, "say", signer=None)           # a peer's: reach?

    def arrive(self, writer, seq, kind, signer):
        e = {"ts": "2026-11-01T01:00:%02d.000Z" % seq, "writer": writer, "seq": seq, "kind": kind, "from": "alice",
             "to": [{"session": S1, "alias": "m"}], "text": "words %d" % seq}
        if signer is not None:
            e["verified"] = {"signer": signer}
        self.assertEqual(hublog.append_verbatim(self.p, e), "appended")
        return e

    def passes(self):
        return sminos.words_due(self.p, [member(S1)]), sminos.reach_due(self.p, [member(S1)])

    def test_an_unchanged_log_is_indexed_once(self):
        with mock.patch.object(sminos, "_addressees", wraps=sminos._addressees) as index:
            first = self.passes()
            second = self.passes()
        self.assertEqual(index.call_count, 1, "two passes, both kinds, over a log no file of which moved")
        self.assertEqual(first, second)
        self.assertEqual([(e["writer"], e["seq"]) for e in first[0][S1]], [("hub/mem-1", 1)])
        self.assertEqual([(e["writer"], e["seq"]) for e in first[1][S1]], [("mini/" + S9, 1)])

    def test_an_appended_event_is_seen_by_the_next_pass(self):
        self.passes()
        self.arrive("hub/mem-2", 1, "human", signer={**DEV, "member": "mem-2"})
        words, _ = self.passes()
        self.assertEqual(sorted((e["writer"], e["seq"]) for e in words[S1]), [("hub/mem-1", 1), ("hub/mem-2", 1)])

    def test_what_a_pass_hands_out_leaves_the_log_as_it_was(self):
        """The words pass's asks keep the shared events; the frames copy them."""
        before = json.loads(json.dumps(sminos.log_read(self.p)))
        link = self.link()
        link.reach = True
        link.plane = mock.Mock(member_rows={self.p.id: {S1: member(S1)}})
        link.ask_words({self.p.id: self.p})
        self.assertEqual(sorted(h["t"] for h in link.asks.values()), ["reach?", "words?"])
        for frame in link.session_lane.sent:
            frame["event"]["text"] = "changed by a reader of the frame"
        self.assertEqual(sminos.log_read(self.p), before)
        self.assertEqual(json.loads(json.dumps(sminos._store_whole(self.p, "log", shared=True)[1])), before)


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
