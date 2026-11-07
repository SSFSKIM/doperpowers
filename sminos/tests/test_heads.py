#!/usr/bin/env python3
"""An own writer of no session waits for its upstream's head (#147): a machine
that enrols, is cut over or is renamed may hold nothing of what its upstream
holds already under the name it now writes as (a VM recreated under its old
name, an enrolment with --replace, the endpoint's welcome). Its session
writers are new UUIDs, but its operator writer, `<name>/human`, would take
seqs from 1 that the upstream holds already: never uploaded, and a fork of
the log. So until the uplink has seen the upstream's head for that writer and
the log has reached it, an append to it in a project of the upstream waits
(`projects/<id>/queued/`), and then lands above that head and goes up.

On DX2 the hub's backlog brings the writer's events (an import); on RL10 the
endpoint refuses an own-writer event it never signed and sends its position
as `spent`. Both reach the head.

Hermetic: every test has its own HOME and SMINOS_HOME under one temporary
directory.
Run: python3 -B sminos/tests/test_heads.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "sminos" / "scripts"
BASE = tempfile.mkdtemp(prefix="smh.", dir="/tmp")
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import sminos  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
from rl10_identity import write_identity  # noqa: E402

W = "testhost/human"


class Machine(unittest.TestCase):
    """A fresh installation per test, named `testhost` (DAEMON_HOST) until a
    welcome cuts it over into org-1, with one hub project, `work`."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"), DAEMON_HOST="testhost")
        self.addCleanup(os.environ.pop, "DAEMON_HOST", None)
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        rl10._SAID.update(find=None, revoked=None)
        sminos.forget_caches()
        p = sminos.make_project("6e000004-0000-4000-8000-000000000001", "work", "", "",
                                {"url": "http://127.0.0.1:9", "org": "org-1"})
        sminos.project_path(p, "log")
        self.p = p

    def welcome(self, **identity):
        """The machine cut over (RL10): the endpoint's first welcome is its
        enrolment, which marks the operator writer as waiting for its head."""
        rl10.welcomed({**Rl10.WELCOME, "identity": {**Rl10.WELCOME["identity"], **identity}})

    def endpoint_log(self, machine="testhost"):
        """The project's log plane as the uplink holds it on RL10: no code."""
        return hublog.HubLog(self.p, {"key": None, "machine": machine}, coded=False)

    def say(self, text):
        return sminos.log_append(self.p, W, "human", **{"from": "human", "to": "*", "text": text})

    def log(self):
        return [e for e in sminos.log_read(self.p) if e["writer"] == W]

    def uploaded(self, hl):
        return [(e["writer"], e["seq"], e.get("text")) for frame, _ in hl.uploads() for e in frame["events"]
                if e["writer"] == W]

    def assert_one_event_a_position(self):
        seen = [(e["writer"], e["seq"]) for e in sminos.log_read(self.p)]
        self.assertEqual(len(seen), len(set(seen)), "no two events at one (writer, seq)")


class Dx2OnRl10(Machine):
    """DX2's shared tests on RL10 (#153 M3a; DX2's own went in M4): the
    endpoint's welcome is the enrolment that marks the writer, the
    upstream's events at the writer's positions come as `spent`, and the log
    plane is uncoded. The first of them is
    Rl10.test_the_cutovers_welcome_holds_the_writer_until_the_endpoints_head."""

    def test_a_machine_enrolled_before_appends_at_once(self):
        write_identity(os.environ["SMINOS_HOME"])   # an enrolment no welcome marked
        sminos.forget_caches()
        self.assertEqual(self.say("now")["seq"], 1, "no mark: nothing waits, as before")

    def test_a_release_cut_short_after_its_append_is_finished_without_a_second_copy(self):
        self.welcome()
        self.say("early")
        kept = Path(sminos.queued_path(self.p, W)).read_text()
        hl = self.endpoint_log()
        hl.on_have({"have": {}})
        self.assertEqual([e["text"] for e in self.log()], ["early"])
        Path(sminos.queued_path(self.p, W)).write_text(kept)   # as a crash before the queue's removal leaves it
        hl.on_have({"have": {W: 1}})
        self.assertEqual([e["text"] for e in self.log()], ["early"], "not appended twice")
        self.assertFalse(os.path.exists(sminos.queued_path(self.p, W)))

    def test_an_endpoint_holding_nothing_of_the_writer_releases_it_at_the_have(self):
        self.welcome()
        self.assertIsNone(self.say("early")["seq"])
        hl = self.endpoint_log()
        hl.on_have({"have": {}})
        self.assertEqual([(e["seq"], e["text"]) for e in self.log()], [(1, "early")])
        self.assertEqual(self.uploaded(hl), [(W, 1, "early")])

    def test_a_new_enrolment_waits_again_and_a_session_writer_never_waits(self):
        self.welcome()
        hl = self.endpoint_log()
        hl.on_have({"have": {}})
        self.assertEqual(self.say("first")["seq"], 1)
        self.welcome(enrolled="2026-10-29T00:00:00.000Z")   # enrolled again under the same name
        self.assertIsNone(self.say("second")["seq"], "known for the enrolment it was seen under, not this one")
        sid = "6e000001-0000-4000-8000-0000000000e1"
        joined = sminos.log_append(self.p, "testhost/" + sid, "joined", session=sid, alias="a", name_source="derived",
                                   machine="testhost", cwd="/w", session_kind="interactive")
        self.assertEqual(joined["seq"], 1, "a session's writer is a new UUID: it never collides, never waits")

    def test_a_cutover_undone_before_the_first_have_leaves_what_waits_named(self):
        """identity.json removed (the cutover undone) before the endpoint's
        first `have`: with no upstream, nothing releases what waits, and
        appending it here could take a seq the endpoint holds. It stays
        queued, `daemon owed` names it, and the next enrolment under the
        name releases it above the endpoint's head."""
        self.welcome()
        self.say("early")
        os.remove(rl10.identity_path())
        sminos.forget_caches()
        out = subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "daemon", "owed"],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        line = [x for x in out.stdout.splitlines() if x.startswith("work: ")]
        self.assertEqual(len(line), 1, out.stdout)
        self.assertIn("queued 1 [testhost/human (no upstream releases it)]", line[0])
        self.assertNotIn("early", out.stdout + out.stderr, "no body")
        self.assertEqual(self.log(), [], "nothing appended at a seq the endpoint may hold")
        self.welcome(enrolled="2026-10-29T00:00:00.000Z")
        hl = self.endpoint_log()
        hl.on_have({"have": {W: 2}})
        for seq in (1, 2):
            self.assertTrue(hl.spend(W, seq, "conflict"))
        self.assertEqual([(e["seq"], e["text"]) for e in self.log()], [(3, "early")],
                         "an enrolment under the name again releases it above the endpoint's head")
        self.assertFalse(os.path.exists(sminos.queued_path(self.p, W)), "nothing left waiting")

    def test_daemon_owed_counts_what_waits(self):
        self.welcome()
        self.say("early")
        out = subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "daemon", "owed"],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        line = [x for x in out.stdout.splitlines() if x.startswith("work: ")]
        self.assertEqual(len(line), 1, out.stdout)
        self.assertIn("queued 1", line[0])
        self.assertNotIn("early", out.stdout, "no body")

    def test_an_operators_say_says_it_waits(self):
        self.welcome()
        out = subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "say", "--in", "work", "hello"],
                             capture_output=True, text=True, timeout=60, cwd=os.environ["HOME"])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("waits", out.stdout)
        self.assertEqual(self.log(), [])
        self.assertEqual([e["text"] for e in sminos.queued_read(self.p, W)], ["hello"])


class Streams(Machine):
    """The operator's words to a private session go under an audience stream
    of its writer, `<name>/human~<digest>` (P5 O18 D6): each such stream
    waits for its own head as the plain writer does, and is released on it."""

    D1, D2 = "%016x" % 0xd1, "%016x" % 0xd2

    def stream(self, digest, name="testhost"):
        return "%s/human~%s" % (name, digest)

    def append(self, writer, text):
        return sminos.log_append(self.p, writer, "human", **{"from": "human", "to": "*", "text": text})

    def held(self, writer):
        return [(e["seq"], e["text"]) for e in sminos.log_read(self.p) if e["writer"] == writer]

    def test_an_operator_stream_waits_for_its_own_head_and_lands_above_it_on_rl10(self):
        """The same on RL10: the endpoint's welcome marks every operator
        writer, and the upstream's events at their positions come as `spent`."""
        self.welcome()
        s1, s2 = self.stream(self.D1), self.stream(self.D2)
        self.assertIsNone(self.append(s1, "to the private one")["seq"], "it waits, as the plain writer does")
        hl = self.endpoint_log()
        hl.on_have({"have": {W: 1, s1: 2}})
        self.assertIsNone(self.append(s1, "again")["seq"], "its head is known, the log not at it")
        self.assertTrue(hl.spend(W, 1, "conflict"))
        self.assertIsNone(self.append(s1, "a third")["seq"], "the plain writer's head says nothing of the stream's")
        self.assertEqual(self.append(W, "plain")["seq"], 2, "the plain writer released on its own head")
        for seq in (1, 2):
            self.assertTrue(hl.spend(s1, seq, "conflict"))
        self.assertEqual(self.held(s1), [(3, "to the private one"), (4, "again"), (5, "a third")],
                         "released above the stream's head, in order")
        self.assertEqual([(w, s) for frame, _ in hl.uploads() for e in frame["events"]
                          for w, s in [(e["writer"], e["seq"])] if w == s1], [(s1, 3), (s1, 4), (s1, 5)])
        self.assertEqual(self.append(s2, "a stream the endpoint holds nothing of")["seq"], 1,
                         "a stream the have named no head for has none to wait for")
        self.assertEqual(self.append(s1, "after")["seq"], 6)
        self.assert_one_event_a_position()

    def test_before_any_have_every_operator_stream_waits_on_rl10(self):
        self.welcome()
        self.assertIsNone(self.append(self.stream(self.D2), "early")["seq"])
        self.endpoint_log().on_have({"have": {}})
        self.assertEqual(self.held(self.stream(self.D2)), [(1, "early")], "released at the have, which holds none")

    def test_a_former_names_queues_release_each_into_its_namesake(self):
        rl10.welcomed(Rl10.WELCOME)
        self.assertIsNone(self.append(self.stream(self.D1), "stream as testhost")["seq"])
        self.assertIsNone(self.append(W, "plain as testhost")["seq"])
        rl10.welcomed({**Rl10.WELCOME, "identity": {**Rl10.WELCOME["identity"], "name": "renamed"}})
        new1 = self.stream(self.D1, "renamed")
        self.assertIsNone(self.append(new1, "stream as renamed")["seq"])
        hl = hublog.HubLog(self.p, {"key": None, "machine": "renamed"}, coded=False)
        hl.on_have({"have": {new1: 1}})
        self.assertEqual(self.held("renamed/human"), [(1, "plain as testhost")], "the plain into the plain")
        self.assertEqual(self.held(new1), [], "the stream waits for its own head")
        hl.spend(new1, 1, "conflict")
        self.assertEqual(self.held(new1), [(2, "stream as testhost"), (3, "stream as renamed")],
                         "the stream's queues, former name first, into the stream of the same digest")
        self.assertEqual(sminos.queued_operators(self.p), {})


class Rl10(Machine):
    WELCOME = {"t": "welcome", "protocol": {"major": 1, "minor": 0}, "build": "b",
               "identity": {"org": "org-1", "hub": "http://127.0.0.1:9", "name": "testhost", "former": [],
                            "ref": "machine-ref-1", "enrolled": "2026-10-28T01:00:00.000Z"}}

    def test_the_cutovers_welcome_holds_the_writer_until_the_endpoints_head(self):
        """The cut-over's first welcome is a new enrolment: the operator
        writer waits for the endpoint's `have`. The hub's own-writer events
        the endpoint never signed come down as `spent`; once the log reaches
        the head through them, what waited lands above it and goes up."""
        self.assertEqual(self.say("before the cutover")["seq"], 1)
        rl10.welcomed(self.WELCOME)
        self.assertIsNone(self.say("early")["seq"], "the welcome marked the enrolment")
        hl = hublog.HubLog(self.p, {"key": None, "machine": "testhost"}, coded=False)
        hl.on_have({"have": {W: 4}})
        self.assertIsNone(self.say("between")["seq"])
        for seq in (2, 3, 4):
            self.assertTrue(hl.spend(W, seq, "conflict"))
        self.assertEqual([(e["seq"], e["text"]) for e in self.log()],
                         [(1, "before the cutover"), (5, "early"), (6, "between")])
        self.assertEqual(self.uploaded(hl), [(W, 5, "early"), (W, 6, "between")], "what the endpoint lacks goes up")
        self.assertTrue(all(sminos.receipted(self.p, e) for e in self.log()[1:]), "receipted as an own append")
        self.assertEqual(self.say("after")["seq"], 7)
        self.assert_one_event_a_position()
        self.assertFalse(os.path.exists(sminos.queued_path(self.p, W)), "nothing left waiting")

    def test_a_renaming_welcome_holds_the_new_names_writer(self):
        rl10.welcomed(self.WELCOME)
        hublog.HubLog(self.p, {"key": None, "machine": "testhost"}, coded=False).on_have({"have": {}})
        self.assertEqual(self.say("as testhost")["seq"], 1)
        rl10.welcomed({**self.WELCOME, "identity": {**self.WELCOME["identity"], "name": "renamed"}})
        e = sminos.log_append(self.p, "renamed/human", "human", **{"from": "human", "to": "*", "text": "as renamed"})
        self.assertIsNone(e["seq"], "the new name's operator writer waits for its head")


class Publication(Machine):
    """The mark goes before the enrolment it names: an appender that reads
    the new identity reads its mark too, and a mark that cannot be written
    leaves the identity unwritten, so the next welcome writes both."""

    def test_the_welcome_marks_before_it_writes_the_identity(self):
        seen, real = [], sminos.write_json

        def write_json(path, data, mode=0o600):
            if path == rl10.identity_path():
                seen.append(json.loads(Path(os.environ["SMINOS_HOME"], "daemon", sminos.HEADS_FILE).read_text()))
            return real(path, data, mode)
        with mock.patch.object(sminos, "write_json", write_json):
            rl10.welcomed(Rl10.WELCOME)
        self.assertEqual(seen, [{"marks": [{"name": "testhost", "enrolled": Rl10.WELCOME["identity"]["enrolled"]}]}])

    def test_a_renaming_welcome_keeps_the_old_enrolment_marked_until_it_is_replaced(self):
        """While a welcome publishes a new enrolment, the one still current
        stays marked: an append as it waits as before."""
        rl10.welcomed(Rl10.WELCOME)
        seen, real = [], sminos.write_json

        def write_json(path, data, mode=0o600):
            if path == rl10.identity_path():
                sminos.forget_caches()
                seen.append(sminos.waits_for_head(self.p, W))
            return real(path, data, mode)
        with mock.patch.object(sminos, "write_json", write_json):
            rl10.welcomed({**Rl10.WELCOME, "identity": {**Rl10.WELCOME["identity"], "name": "renamed"}})
        self.assertEqual(seen, [True], "testhost/human still waits while the rename is published")

    def test_a_mark_that_fails_leaves_the_cutover_to_the_next_welcome(self):
        with mock.patch.object(sminos, "mark_enrolled", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                rl10.welcomed(Rl10.WELCOME)
        self.assertFalse(rl10.cut_over(), "no identity without its mark")
        rl10.welcomed(Rl10.WELCOME)
        self.assertIsNone(self.say("early")["seq"], "the next welcome cut over, marked")


class Renamed(Machine):
    def test_what_waited_under_a_former_name_lands_under_the_name_now(self):
        """A welcome renames the machine while an append waits: the
        operator's words are not abandoned under a writer no upload takes;
        once the new name's head is reached they land under it, in order."""
        rl10.welcomed(Rl10.WELCOME)
        self.assertIsNone(self.say("as testhost")["seq"])
        rl10.welcomed({**Rl10.WELCOME, "identity": {**Rl10.WELCOME["identity"], "name": "renamed"}})
        self.assertIsNone(sminos.log_append(self.p, "renamed/human", "human",
                                            **{"from": "human", "to": "*", "text": "as renamed"})["seq"])
        hl = hublog.HubLog(self.p, {"key": None, "machine": "renamed"}, coded=False)
        hl.on_have({"have": {"renamed/human": 2}})
        for seq in (1, 2):
            hl.spend("renamed/human", seq, "conflict")
        self.assertEqual([(e["seq"], e["text"]) for e in sminos.log_read(self.p) if e["writer"] == "renamed/human"],
                         [(3, "as testhost"), (4, "as renamed")])
        self.assertEqual([e["seq"] for frame, _ in hl.uploads() for e in frame["events"]], [3, 4])
        self.assertEqual(sminos.queued_operators(self.p), {}, "no queue is left behind")

    def test_appends_said_in_one_millisecond_across_a_rename_land_in_the_order_said(self):
        """ts has milliseconds alone, so an append as the former name and one
        as the name now can tie. On a tie the former name's goes first (a
        rename comes between them), and within one queue its file order
        holds, whatever the queues' names sort as."""
        rl10.welcomed(Rl10.WELCOME)
        with mock.patch.object(sminos, "now", return_value="2026-10-28T02:00:00.000Z"):
            self.say("testhost 1")
            self.say("testhost 2")
            rl10.welcomed({**Rl10.WELCOME, "identity": {**Rl10.WELCOME["identity"], "name": "renamed"}})
            for text in ("renamed 1", "renamed 2"):
                self.assertIsNone(sminos.log_append(self.p, "renamed/human", "human",
                                                    **{"from": "human", "to": "*", "text": text})["seq"])
        hublog.HubLog(self.p, {"key": None, "machine": "renamed"}, coded=False).on_have({"have": {}})
        self.assertEqual([(e["seq"], e["text"]) for e in sminos.log_read(self.p) if e["writer"] == "renamed/human"],
                         [(1, "testhost 1"), (2, "testhost 2"), (3, "renamed 1"), (4, "renamed 2")])

    def test_within_one_queue_its_file_order_holds_against_a_clock_stepped_back_on_rl10(self):
        self.welcome()
        for ts, text in (("2026-10-28T02:00:01.000Z", "first"), ("2026-10-28T02:00:00.000Z", "second")):
            with mock.patch.object(sminos, "now", return_value=ts):
                self.say(text)
        self.endpoint_log().on_have({"have": {}})
        self.assertEqual([e["text"] for e in self.log()], ["first", "second"])

    def rename_after_first_welcome(self):
        rl10.welcomed(Rl10.WELCOME)

    def test_a_queue_is_drained_under_its_own_writers_lock(self):
        """An appender still running as the former name queues under that
        writer's lock: the release drains that queue under the same lock, so
        what it queues meanwhile is either drained or left for the next
        release, never removed unread."""
        self.rename_after_first_welcome()
        self.say("first")
        rl10.welcomed({**Rl10.WELCOME, "identity": {**Rl10.WELCOME["identity"], "name": "renamed"}})
        hl = hublog.HubLog(self.p, {"key": None, "machine": "renamed"}, coded=False)
        old = sminos.writer_path(self.p, W)
        stale = sminos.writer_locks(old)
        stale.__enter__()
        done = threading.Event()
        threading.Thread(target=lambda: (hl.on_have({"have": {}}), done.set()), daemon=True).start()
        self.assertFalse(done.wait(0.5), "the release waits for the former writer's lock")
        sminos._queue(self.p, W, [{"kind": "human", "from": "human", "to": "*", "text": "second"}])
        stale.__exit__(None, None, None)
        self.assertTrue(done.wait(10))
        self.assertEqual([e["text"] for e in sminos.log_read(self.p) if e["writer"] == "renamed/human"],
                         ["first", "second"])
        self.assertEqual(sminos.queued_operators(self.p), {})

    def test_a_release_cut_short_under_a_former_name_is_not_appended_again(self):
        self.rename_after_first_welcome()
        self.say("early")
        kept = Path(sminos.queued_path(self.p, W)).read_text()
        hublog.HubLog(self.p, {"key": None, "machine": "testhost"}, coded=False).on_have({"have": {}})
        self.assertEqual([(e["writer"], e["text"]) for e in sminos.log_read(self.p)], [(W, "early")])
        Path(sminos.queued_path(self.p, W)).write_text(kept)   # a crash before the queue's removal
        rl10.welcomed({**Rl10.WELCOME, "identity": {**Rl10.WELCOME["identity"], "name": "renamed"}})
        hublog.HubLog(self.p, {"key": None, "machine": "renamed"}, coded=False).on_have({"have": {}})
        self.assertEqual([(e["writer"], e["text"]) for e in sminos.log_read(self.p)], [(W, "early")],
                         "the former writer's log holds it: not appended again under the new name")
        self.assertEqual(sminos.queued_operators(self.p), {})

    def test_an_enrolment_published_during_a_release_does_not_queue_what_it_releases(self):
        """A welcome publishes another enrolment under this name while a
        release runs (after it marked the writer known): what the release
        found its head for is appended, never queued again and removed."""
        self.welcome()
        self.say("early")
        real = sminos.write_json

        def write_json(path, data, mode=0o600):
            real(path, data, mode)
            if path == os.path.join(self.p.home, sminos.HEADS_FILE) and not getattr(write_json, "done", False):
                write_json.done = True
                self.welcome(enrolled="2026-10-29T00:00:00.000Z")   # enrolled again, landing in between
        hl = self.endpoint_log()
        with mock.patch.object(sminos, "write_json", write_json):
            hl.on_have({"have": {}})
        self.assertEqual([(e["seq"], e["text"]) for e in self.log()], [(1, "early")])
        self.assertEqual(sminos.queued_read(self.p, W), [])

    def test_a_queue_made_after_the_release_by_a_command_from_before_a_rename_is_drained(self):
        self.rename_after_first_welcome()
        rl10.welcomed({**Rl10.WELCOME, "identity": {**Rl10.WELCOME["identity"], "name": "renamed"}})
        hl = hublog.HubLog(self.p, {"key": None, "machine": "renamed"}, coded=False)
        hl.on_have({"have": {}})
        hl.on_have({"have": {}})   # a periodic have: nothing waits now
        sminos._queue(self.p, W, [{"kind": "human", "from": "human", "to": "*", "text": "late"}])   # still as testhost
        hl.on_have({"have": {"renamed/human": 0}})
        self.assertEqual([e["text"] for e in sminos.log_read(self.p) if e["writer"] == "renamed/human"], ["late"])
        self.assertEqual(sminos.queued_operators(self.p), {})

    def test_an_uplink_outliving_a_reenrolment_under_another_name_drains_nothing(self):
        """A welcome renames the machine while the old uplink's stream runs:
        until it is replaced, that stream is testhost's and leaves renamed's
        queue alone."""
        self.welcome()
        old = self.endpoint_log()
        self.welcome(name="renamed", enrolled="2026-10-29T00:00:00.000Z")
        self.assertIsNone(sminos.log_append(self.p, "renamed/human", "human",
                                            **{"from": "human", "to": "*", "text": "as renamed"})["seq"])
        old.on_have({"have": {}})
        self.assertEqual(sminos.log_read(self.p), [], "nothing drained into the old name's writer")
        self.assertEqual([e["text"] for e in sminos.queued_read(self.p, "renamed/human")], ["as renamed"])

    def test_a_fragment_a_queue_was_left_with_does_not_swallow_the_next_append_on_rl10(self):
        self.welcome()
        self.say("early")
        with open(sminos.queued_path(self.p, W), "a") as f:
            f.write('{"ts": "2026-10-28T00:00:00.000Z", "writer": "testhost/hu')   # an interrupted write
        self.say("after it")
        self.assertEqual([e["text"] for e in sminos.queued_read(self.p, W)], ["early", "after it"])


def tearDownModule():
    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
