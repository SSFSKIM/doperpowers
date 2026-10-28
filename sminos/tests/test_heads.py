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

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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

KEY = base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode()
W = "testhost/human"


class Machine(unittest.TestCase):
    """A fresh installation per test, `testhost` enrolled in org-1 (DX2's
    hub.json), with one hub project, `work`."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"))
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        rl10._SAID.update(find=None, revoked=None)
        sminos.forget_caches()
        p = sminos.make_project("6e000004-0000-4000-8000-000000000001", "work", "", "",
                                {"url": "http://127.0.0.1:9", "org": "org-1"})
        sminos.project_path(p, "log")
        self.p = p

    def enrol(self, enrolled="2026-10-28T00:00:00Z", fresh=True):
        """hub.json as `hub enroll` writes it; `fresh`, the enrolment's mark
        as it writes it too (a machine enrolled before #147 has none)."""
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json"),
                          {"hub": "http://127.0.0.1:9", "org": "org-1", "machine": "testhost", "client_id": "c",
                           "client_secret": "s", "key": KEY, "former": {}, "enrolled": enrolled}, mode=0o600)
        sminos.forget_caches()
        if fresh:
            sminos.mark_enrolled("testhost", enrolled)

    def say(self, text):
        return sminos.log_append(self.p, W, "human", **{"from": "human", "to": "*", "text": text})

    def log(self):
        return [e for e in sminos.log_read(self.p) if e["writer"] == W]

    def hub_events(self, n):
        """What another machine wrote as testhost/human at the hub, 1..n, sealed under the org key."""
        key = base64.urlsafe_b64decode(KEY + "=")
        return [hublog.seal(key, self.p.id, {"ts": "2026-10-01T00:00:%02d.000Z" % s, "writer": W, "seq": s,
                                             "kind": "human", "from": "human", "to": "*", "text": "old %d" % s})
                for s in range(1, n + 1)]

    def uploaded(self, hl):
        return [(e["writer"], e["seq"], e.get("text")) for frame, _ in hl.uploads() for e in frame["events"]
                if e["writer"] == W]

    def assert_one_event_a_position(self):
        seen = [(e["writer"], e["seq"]) for e in sminos.log_read(self.p)]
        self.assertEqual(len(seen), len(set(seen)), "no two events at one (writer, seq)")


class Dx2(Machine):
    def test_an_operator_append_before_the_backlog_waits_and_lands_above_the_hubs_head(self):
        self.enrol()
        early = self.say("early")
        self.assertIsNone(early["seq"], "it waits: no seq taken before the hub's head is known")
        self.assertEqual(self.log(), [])
        hl = hublog.HubLog(self.p, {"key": base64.urlsafe_b64decode(KEY + "="), "machine": "testhost"})
        hl.on_have({"have": {W: 3}})
        self.assertIsNone(self.say("between")["seq"], "the head is known, the backlog not landed: still waiting")
        self.assertEqual(hl.take(self.hub_events(3)), (3, []))
        self.assertEqual([(e["seq"], e["text"]) for e in self.log()],
                         [(1, "old 1"), (2, "old 2"), (3, "old 3"), (4, "early"), (5, "between")],
                         "the hub's history whole, then what waited, above its head, in order")
        self.assertEqual(self.uploaded(hl), [(W, 4, "early"), (W, 5, "between")], "and it goes up")
        self.assertTrue(all(sminos.receipted(self.p, e) for e in self.log()[3:]), "receipted as an own append")
        self.assertEqual(self.say("after")["seq"], 6, "from then on an append takes its seq at once")
        self.assert_one_event_a_position()
        self.assertFalse(os.path.exists(sminos.queued_path(self.p, W)), "nothing left waiting")

    def test_a_release_cut_short_after_its_append_is_finished_without_a_second_copy(self):
        self.enrol()
        self.say("early")
        kept = Path(sminos.queued_path(self.p, W)).read_text()
        hl = hublog.HubLog(self.p, {"key": base64.urlsafe_b64decode(KEY + "="), "machine": "testhost"})
        hl.on_have({"have": {}})
        self.assertEqual([e["text"] for e in self.log()], ["early"])
        Path(sminos.queued_path(self.p, W)).write_text(kept)   # as a crash before the queue's removal leaves it
        hl.on_have({"have": {W: 1}})
        self.assertEqual([e["text"] for e in self.log()], ["early"], "not appended twice")
        self.assertFalse(os.path.exists(sminos.queued_path(self.p, W)))

    def test_a_hub_holding_nothing_of_the_writer_releases_it_at_the_have(self):
        self.enrol()
        self.assertIsNone(self.say("early")["seq"])
        hl = hublog.HubLog(self.p, {"key": base64.urlsafe_b64decode(KEY + "="), "machine": "testhost"})
        hl.on_have({"have": {}})
        self.assertEqual([(e["seq"], e["text"]) for e in self.log()], [(1, "early")])
        self.assertEqual(self.uploaded(hl), [(W, 1, "early")])

    def test_a_machine_enrolled_before_appends_at_once(self):
        self.enrol(fresh=False)
        self.assertEqual(self.say("now")["seq"], 1, "no mark: nothing waits, as before")

    def test_a_new_enrolment_waits_again_and_a_session_writer_never_waits(self):
        self.enrol()
        hl = hublog.HubLog(self.p, {"key": base64.urlsafe_b64decode(KEY + "="), "machine": "testhost"})
        hl.on_have({"have": {}})
        self.assertEqual(self.say("first")["seq"], 1)
        self.enrol(enrolled="2026-10-29T00:00:00Z")
        self.assertIsNone(self.say("second")["seq"], "known for the enrolment it was seen under, not this one")
        sid = "6e000001-0000-4000-8000-0000000000e1"
        joined = sminos.log_append(self.p, "testhost/" + sid, "joined", session=sid, alias="a", name_source="derived",
                                   machine="testhost", cwd="/w", session_kind="interactive")
        self.assertEqual(joined["seq"], 1, "a session's writer is a new UUID: it never collides, never waits")

    def test_daemon_owed_counts_what_waits(self):
        self.enrol()
        self.say("early")
        out = subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "daemon", "owed"],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        line = [x for x in out.stdout.splitlines() if x.startswith("work: ")]
        self.assertEqual(len(line), 1, out.stdout)
        self.assertIn("queued 1", line[0])
        self.assertNotIn("early", out.stdout, "no body")

    def test_an_operators_say_says_it_waits(self):
        self.enrol()
        out = subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "say", "--in", "work", "hello"],
                             capture_output=True, text=True, timeout=60, cwd=os.environ["HOME"])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("waits", out.stdout)
        self.assertEqual(self.log(), [])
        self.assertEqual([e["text"] for e in sminos.queued_read(self.p, W)], ["hello"])


class Rl10(Machine):
    WELCOME = {"t": "welcome", "protocol": {"major": 1, "minor": 0}, "build": "b",
               "identity": {"org": "org-1", "hub": "http://127.0.0.1:9", "name": "testhost", "former": [],
                            "ref": "machine-ref-1", "enrolled": "2026-10-28T01:00:00.000Z"}}

    def test_the_cutovers_welcome_holds_the_writer_until_the_endpoints_head(self):
        """The cut-over's first welcome is a new enrolment: the operator
        writer waits for the endpoint's `have`. The hub's own-writer events
        the endpoint never signed come down as `spent`; once the log reaches
        the head through them, what waited lands above it and goes up."""
        self.enrol(fresh=False)
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
        self.assertEqual(self.say("after")["seq"], 7)
        self.assert_one_event_a_position()

    def test_a_renaming_welcome_holds_the_new_names_writer(self):
        self.enrol(fresh=False)
        rl10.welcomed(self.WELCOME)
        hublog.HubLog(self.p, {"key": None, "machine": "testhost"}, coded=False).on_have({"have": {}})
        self.assertEqual(self.say("as testhost")["seq"], 1)
        rl10.welcomed({**self.WELCOME, "identity": {**self.WELCOME["identity"], "name": "renamed"}})
        e = sminos.log_append(self.p, "renamed/human", "human", **{"from": "human", "to": "*", "text": "as renamed"})
        self.assertIsNone(e["seq"], "the new name's operator writer waits for its head")


def tearDownModule():
    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
