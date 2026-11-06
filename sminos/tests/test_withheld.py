#!/usr/bin/env python3
"""The sender's side of a hub refusal (P5 O18 M4; MAWS's
docs/doperpowers/plans/2026-11-05-p5-o18-message-reach.md, D5 "The new
own-refused settlement"): an own event the hub withheld `not-reachable` is
settled withheld here (`HubLog.withhold_own`) — recorded in uplink.json,
kept in its writer file, counted as uploaded so the writer's next events go
up — and its sending session, while live, is shown
`[sminos: your message to <alias> was not delivered: not-reachable]`, once,
whichever way the hub's word arrives: its refusal, its tombstone on resync
(DX2's tombstone, RL10's `spent withheld`) or a `have`'s withheld list.

- Dx2: HubLog against hub_standin.py over DX2, which withholds a message
  naming a session nobody exposed.
- Rl10: the uplink in this process against endpoint_standin.py, whose ctl
  `refuse` sends `not-reachable`.

Sessions are live `sleep` processes whose inboxes inbox_standin.py serves
(test_words.Machine). Hermetic: HOME, SMINOS_HOME and MAWS_USER_DATA are
temporary, one set per test.
Run: python3 -B sminos/tests/test_withheld.py
"""

import json
import os
import shutil
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_reach as tr  # noqa: E402  (its stand-in hub, as two machines meet it)
import test_words as tw  # noqa: E402  (its machine, sessions and inboxes, the endpoint stand-in)

import sminos  # noqa: E402
import sminos_archive as archive  # noqa: E402
import sminos_hublog as hublog  # noqa: E402

S1 = tw.S1
GHOST = "6e0000ee-0000-4000-8000-0000000000ee"   # a session nobody exposed: the hub withholds what names it
W = "testhost/" + S1
NOTICE = "[sminos: your message to ghost was not delivered: not-reachable]"


def notices(inbox):
    """The notice lines the inbox took, out of their peer envelopes."""
    return [line for t in inbox for line in t.splitlines() if "was not delivered" in line]


class Sender(tw.Machine):
    """A hub project with one live session of this machine, S1, its inbox served."""

    def setUp(self):
        super().setUp()
        self.p = self.project("work", hub=True)
        self.end_sender = self.session(self.p, S1, name="sender", inbox=True)

    def joined(self):
        return sminos.log_append(self.p, W, "joined", session=S1, alias="sender", name_source="set",
                                 machine="testhost", cwd=self.p.root, session_kind="interactive")

    def say(self, text, to=None):
        return sminos.log_append(self.p, W, "say", **{
            "from": "sender", "to": to if to is not None else [{"session": GHOST, "alias": "ghost"}], "text": text})

    def file(self):
        return [(e["seq"], e["kind"], e.get("text")) for e in tw.read_lines(sminos.writer_path(self.p, W))]

    def uplink_state(self):
        return json.loads(Path(self.p.home, hublog.STATE_FILE).read_text())


class Dx2(Sender):
    @classmethod
    def setUpClass(cls):
        cls.hub = tr.Hub()

    @classmethod
    def tearDownClass(cls):
        cls.hub.stop()

    def setUp(self):
        super().setUp()
        self.m = tr.Machine(self.hub, "testhost")
        self.hl = hublog.HubLog(self.p, {"key": tr.RAW_KEY, "machine": "testhost"})

    def hello(self, have=None, withheld=True):
        """A hello and the hub's answer taken in: its `have` (without its
        withheld list, `withheld` off), then its backlog."""
        frames = self.m.hello(self.p.id, have)
        got = next(f for f in frames if f["t"] == "have")
        self.hl.on_have(got if withheld else {k: v for k, v in got.items() if k != "withheld"})
        for f in frames:
            if f["t"] == "events":
                self.hl.take(f["events"])
        return got

    def upload(self, refusals=True):
        """What the plane owes the hub posted; the refusals the hub sends back taken in (`refusals`)."""
        mark = self.m.mark()
        for frame, reach in self.hl.uploads():
            self.m.post(frame)
            self.hl.took(reach)
        time.sleep(0.2)
        got = self.m.since(mark, "refused")
        if refusals:
            for f in got:
                self.hl.on_refused(f)
        return [f["refusal"] for f in got]

    def stored(self):
        return [(e["seq"], e.get("text"), e.get("withheld"))
                for e in self.hub.state()["projects"][self.p.id]["writers"].get(W, [])]

    def test_a_refusal_settles_the_event_withheld_and_the_session_is_told_once(self):
        self.hello()
        self.joined()
        self.say("the secret words")
        self.assertEqual(self.upload(), [{"reason": "not-reachable", "writer": W, "seq": 2}])
        self.assertEqual(self.hl.withheld(), {W: {2}})
        self.assertEqual(self.uplink_state()["withheld"], {W: [2]}, "kept in uplink.json")
        self.assertEqual(self.file()[1], (2, "say", "the secret words"),
                         "the writer file keeps what its session tried to send")
        self.say("after it", to="*")
        self.assertEqual(self.upload(), [], "the writer goes on")
        self.assertEqual(self.stored(), [(1, None, None), (2, None, True), (3, "after it", None)],
                         "its next event uploads, above the hub's tombstone")
        self.hl.show_notices()
        inbox = tw.wait_for(lambda: self.inbox(S1), timeout=10)
        self.assertEqual(notices(inbox), [NOTICE])
        self.assertNotIn("secret", json.dumps(inbox), "the notice names whom, never what")
        self.hello(self.hl.vector())   # the next have lists the position withheld: settled already
        self.hl.on_refused({"t": "refused", "project": self.p.id,
                            "refusal": {"reason": "not-reachable", "writer": W, "seq": 2}})   # a resend's refusal
        self.hl.show_notices()
        time.sleep(0.5)
        self.assertEqual(notices(self.inbox(S1)), [NOTICE], "one notice")
        self.assertEqual(self.hl.taken()[W], 3, "counted as uploaded: nothing owed behind it")
        self.assertNotIn("notices", {k: v for k, v in self.uplink_state().items() if v})

    def test_its_tombstone_on_resync_with_no_refusal_settles_it_the_same(self):
        self.hello()
        self.joined()
        self.say("the secret words")
        self.upload(refusals=False)   # the refusal lost to a dropped connection
        self.assertEqual(self.hl.withheld(), {})
        self.hl.reset()
        self.hello({}, withheld=False)   # a hello naming less than the log holds: the backlog brings the tombstone
        self.assertEqual(self.hl.withheld(), {W: {2}})
        self.assertEqual(self.file()[1], (2, "say", "the secret words"))
        self.assertEqual(self.hl.spent(), {}, "not spent: this machine's event holds the position")
        self.say("after it", to="*")
        self.upload()
        self.assertEqual(self.stored()[-1], (3, "after it", None))
        self.hl.show_notices()
        self.assertEqual(notices(tw.wait_for(lambda: self.inbox(S1), timeout=10)), [NOTICE])

    def test_a_haves_withheld_list_settles_a_refusal_lost_on_the_way(self):
        self.hello()
        self.joined()
        self.say("the secret words")
        self.upload(refusals=False)
        self.hello(self.hl.vector())
        self.assertEqual(self.hl.withheld(), {W: {2}})
        self.hl.show_notices()
        self.assertEqual(notices(tw.wait_for(lambda: self.inbox(S1), timeout=10)), [NOTICE])

    def test_a_session_not_live_keeps_its_notice_until_it_is_live_again(self):
        self.hello()
        self.joined()
        self.end_sender()
        self.say("the secret words")
        self.upload()
        sminos.forget_caches()
        self.hl.show_notices()
        self.assertEqual(len(self.uplink_state()["notices"]), 1, "kept while the session is not live")
        self.session(self.p, S1, name="sender", inbox=True)
        # Each upload pass shows what is owed: until the inbox listens (its old socket file is still there), a push
        # that reaches nothing keeps the notice.
        self.assertEqual(tw.wait_for(lambda: (self.hl.show_notices(), notices(self.inbox(S1)))[1], timeout=10),
                         [NOTICE], "shown once it is")
        self.assertEqual(self.uplink_state()["notices"], [])

    def test_a_notice_whose_session_stays_away_a_day_is_dropped(self):
        self.hello()
        self.joined()
        self.end_sender()
        e = self.say("the secret words")
        self.upload()
        d = self.uplink_state()
        self.hl.save({**d, "notices": [{**n, "ts": "2026-01-01T00:00:00.000Z"} for n in d["notices"]]})
        self.hl.show_notices()
        self.assertEqual(self.uplink_state()["notices"], [], "dropped past its day")
        self.assertIn("the notice of %s:%d of work was not shown" % (W, e["seq"]), tw.daemon_log())

    def test_the_operators_notice_is_a_line_in_daemon_log(self):
        self.hello()
        op = "testhost/human"
        sminos.log_append(self.p, op, "human", **{"from": "human", "to": [{"session": GHOST, "alias": "ghost"}],
                                                   "text": "the operator's secret"})
        self.upload()
        self.assertEqual(self.hl.withheld(), {op: {1}})
        self.assertNotIn("notices", {k: v for k, v in self.uplink_state().items() if v}, "no session to tell")
        said = [x for x in tw.daemon_log().splitlines() if "%s:1" % op in x and "withheld" in x]
        self.assertEqual(len(said), 1, tw.daemon_log())
        self.assertIn("message to ghost was not delivered", said[0])
        self.assertNotIn("secret", tw.daemon_log())

    def test_the_archive_writes_the_tombstone_of_a_position_withheld_here(self):
        """A refusal received under a name, the machine renamed before a
        `have` listed it: the former name's frontier is frozen without it,
        and the position recorded withheld here is still a tombstone."""
        self.hello()
        self.joined()
        self.say("the secret words")
        self.upload()
        d = self.uplink_state()
        d["archive_have"] = {"have": {W: 2}, "withheld": {}}   # as a have that predates the refusal saved it
        self.hl.save(d)
        clone = os.path.join(self.home, "clone")
        os.makedirs(clone)
        archive.copy_log(self.p, clone)
        held = tw.read_lines(os.path.join(clone, W.replace("/", ".") + ".jsonl"))
        self.assertEqual(held[1], {"writer": W, "seq": 2, "withheld": True})
        self.assertNotIn("secret", json.dumps(held))


class Rl10(Sender):
    """The uplink itself, which may join the live session on its own: positions are the ones the appends took."""

    def project(self, name, hub=False):
        self.cut_over()
        return super().project(name, hub)

    def start(self):
        ep = self.endpoint()
        self.uplink()
        ep.wait(lambda f: f["t"] == "hello" and f.get("project") == self.p.id)
        return ep

    def uploaded(self, ep, e):
        sminos.nudge_daemon()
        return ep.wait_until(lambda: e["seq"] in ep.logs.get(self.p.id, {}).get(W, {}))

    def held(self, e):
        return next((x["kind"], x.get("text")) for x in tw.read_lines(sminos.writer_path(self.p, W))
                    if x["seq"] == e["seq"])

    def test_a_refusal_settles_the_event_withheld_and_the_session_is_told(self):
        ep = self.start()
        self.joined()
        e = self.say("the secret words")
        self.uploaded(ep, e)
        ep.refuse_upload(self.p.id, W, e["seq"])
        self.assertEqual(tw.wait_for(lambda: notices(self.inbox(S1)), timeout=20), [NOTICE])
        self.assertEqual(self.uplink_state()["withheld"], {W: [e["seq"]]})
        self.assertEqual(self.held(e), ("say", "the secret words"), "the writer file keeps it")
        self.uploaded(ep, self.say("after it", to="*"))
        ep.refuse_upload(self.p.id, W, e["seq"])   # said again: settled already
        time.sleep(1.5)
        self.assertEqual(notices(self.inbox(S1)), [NOTICE], "one notice")
        self.assertNotIn("secret", json.dumps(self.inbox(S1)))

    def test_spent_withheld_with_no_refusal_settles_it_the_same(self):
        ep = self.start()
        self.joined()
        e = self.say("the secret words")
        self.uploaded(ep, e)
        for _ in range(2):
            ep.send({"t": "spent", "project": self.p.id, "writer": W, "seq": e["seq"], "reason": "withheld"})
        self.assertEqual(tw.wait_for(lambda: notices(self.inbox(S1)), timeout=20), [NOTICE])
        self.assertEqual(self.uplink_state()["withheld"], {W: [e["seq"]]})
        self.assertNotIn(W, self.uplink_state().get("spent") or {}, "not spent: its event holds the position")
        self.assertEqual(self.held(e), ("say", "the secret words"))
        self.uploaded(ep, self.say("after it", to="*"))
        time.sleep(1.0)
        self.assertEqual(notices(self.inbox(S1)), [NOTICE], "one notice")


def tearDownModule():
    for base in (tr.BASE, tw.BASE):
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
