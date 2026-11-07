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

- Rl10: the uplink in this process against endpoint_standin.py, whose ctl
  `refuse` sends `not-reachable`.
- Dx2OnRl10: an uncoded HubLog against endpoint_standin's own admission,
  whose `withhold` plays the hub's reach judgement (Reach), which withholds
  a message naming a session nobody exposed.
- RestateOnRl10: the same rig, a session's own `joined` or `state` the hub
  withheld restated once by the daemon's next tick (MAWS #492): admitted,
  never restated again once withheld again, owed nothing after a newer one;
  the debt and the restatement's identity outliving an interrupted write,
  and a restated marker kept until its verdict.
- RestateThroughTheUplink: one restatement end to end through the uplink;
  StandinWithholds: the stand-in's `withhold` itself.

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
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_words as tw  # noqa: E402  (its machine, sessions and inboxes, the endpoint stand-in)

import endpoint_standin  # noqa: E402
import sminos  # noqa: E402
import sminos_archive as archive  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
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


class Reach:
    """The hub's reach judgement for these cases, for endpoint_standin's
    `withhold`: an event naming GHOST (a session
    nobody exposed), and a `joined` or `state` of S1 while its registry row
    binds it to another machine (`bound`)."""

    def __init__(self):
        self.bound = None

    def __call__(self, _project, e):
        if any(isinstance(t, dict) and t.get("session") == GHOST for t in e.get("to") or ()):
            return True
        return e.get("kind") in ("joined", "state") and e.get("session") == S1 and self.bound not in (None, "testhost")


class OverRl10(Sender):
    """An uncoded HubLog (a machine cut over to its endpoint) against
    endpoint_standin's admission: what the plane owes taken by the stand-in's
    own `take` and its `refused` frames handed back, a `have` as the
    stand-in builds it, the frames passed by hand. The hub's withholding is
    the stand-in's `withhold` (Reach)."""

    def setUp(self):
        super().setUp()
        self.reach = Reach()
        self.ep = endpoint_standin.Endpoint(self.epdir, withhold=self.reach)
        self.hl = hublog.HubLog(self.p, {"key": None, "machine": "testhost"})

    def project(self, name, hub=False):
        self.cut_over()
        return super().project(name, hub)

    def hello(self, have=None, withheld=True):
        """The endpoint's `have` taken in (without its withheld list,
        `withheld` off). `have` is DX2's hello vector, which picks a backlog:
        on RL10 another's events come down on their own (`spent`, `events`)."""
        got = self.ep.have(self.p.id)
        self.hl.on_have(got if withheld else {k: v for k, v in got.items() if k != "withheld"})
        return got

    def upload(self, refusals=True):
        got = []
        for frame, reach in self.hl.uploads():
            self.assertEqual(frame["t"], "events")
            got += self.ep.take(frame["project"], frame["events"])
            self.hl.took(reach)
        if refusals:
            for f in got:
                self.hl.on_refused(f)
        return [f["refusal"] for f in got]

    def stored(self):
        held = self.ep.logs.get(self.p.id, {}).get(W, {})
        withheld = set((self.ep.withheld.get(self.p.id) or {}).get(W, ()))
        return [(seq, None, True) if seq in withheld else (seq, held[seq].get("text"), None)
                for seq in sorted(set(held) | withheld)]


class Dx2OnRl10(OverRl10):
    """An own event the endpoint withheld, settled withheld here whichever
    way its word arrives: its refusal, a `have`'s withheld list, or `spent
    withheld` (#153 M3b; the cases were Dx2's, over DX2)."""

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
        """RL10 says the position withheld on resync as `spent withheld`
        (Link.on_spent hands it to HubLog.spend), where DX2's backlog
        brought the tombstone."""
        self.hello()
        self.joined()
        self.say("the secret words")
        self.upload(refusals=False)   # the refusal lost to a dropped connection
        self.assertEqual(self.hl.withheld(), {})
        self.hl.reset()
        self.hello(withheld=False)   # a have that predates the withholding's
        self.hl.spend(W, 2, "withheld")
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


class RestateOnRl10(OverRl10):
    """A withheld own snapshot restated (D5; MAWS #492): withhold_own owes a
    restatement of the session's `joined` or `state`, the daemon's next tick
    writes it from the record as it is now, and a restatement the hub
    withholds again owes nothing more. The daemon writes the snapshots
    itself (its reconciliation joins the live session, publish_state its
    first word); the stand-in's `withhold` binding S1 to another machine
    (Reach.bound) is what withholds them, and binding it back by hand plays
    a cause that clears (the provenance race), which the stand-in cannot
    race (#153 M3b; the cases were Restate's, over DX2)."""

    def setUp(self):
        super().setUp()
        self.bind("other")

    def bind(self, machine):
        self.reach.bound = machine

    def tick(self):
        sminos.forget_caches()
        return daemon.tick(self.p)

    def own(self, kind=None):
        return [e for e in tw.read_lines(sminos.writer_path(self.p, W)) if kind is None or e["kind"] == kind]

    def hub_has(self, e):
        if e["seq"] in set((self.ep.withheld.get(self.p.id) or {}).get(W, ())):
            return {"writer": W, "seq": e["seq"], "withheld": True}
        return self.ep.logs.get(self.p.id, {}).get(W, {}).get(e["seq"])

    def withhold_the_first_snapshots(self):
        """The daemon's first tick joins S1 and publishes its word; both go
        up and the hub withholds them. Returns (the joined, the state)."""
        self.hello()
        self.tick()
        joined, state = self.own("joined"), self.own("state")
        self.assertEqual((len(joined), len(state)), (1, 1), self.own())
        self.assertEqual(sorted(r["seq"] for r in self.upload() if r["reason"] == "not-reachable"),
                         sorted([joined[0]["seq"], state[0]["seq"]]))
        return joined[0], state[0]

    def test_a_withheld_joined_is_restated_at_the_next_tick_and_the_hub_admits_it(self):
        first, _ = self.withhold_the_first_snapshots()
        self.assertEqual(self.hub_has(first), {"writer": W, "seq": first["seq"], "withheld": True})
        self.bind("testhost")
        self.tick()
        joined = self.own("joined")
        self.assertEqual(len(joined), 2, "the next tick writes the joined again")
        again = joined[1]
        self.assertEqual({k: again.get(k) for k in ("alias", "cwd", "machine", "session_kind")},
                         {k: first.get(k) for k in ("alias", "cwd", "machine", "session_kind")},
                         "from the session's last joined")
        self.assertEqual(self.upload(), [], "admitted")
        self.assertEqual(self.hub_has(again)["kind"], "joined")
        self.tick()
        self.assertEqual(len(self.own("joined")), 2, "restated once")
        self.assertIn("restated", tw.daemon_log())

    def test_a_restatement_withheld_again_is_not_restated(self):
        first, _ = self.withhold_the_first_snapshots()   # bound to another machine for good
        self.tick()
        joined, state = self.own("joined"), self.own("state")
        self.assertEqual((len(joined), len(state)), (2, 2), "each restated once")
        self.assertEqual(sorted(r["seq"] for r in self.upload() if r["reason"] == "not-reachable"),
                         sorted([joined[1]["seq"], state[1]["seq"]]), "withheld again")
        for _ in range(2):
            self.tick()
        self.assertEqual((len(self.own("joined")), len(self.own("state"))), (2, 2), "no third snapshot")
        said = [x for x in tw.daemon_log().splitlines() if "again" in x and S1[:8] in x]
        self.assertEqual(len(said), 2, tw.daemon_log())

    def test_a_withheld_state_followed_by_a_newer_own_state_owes_nothing(self):
        _, state = self.withhold_the_first_snapshots()
        newer = sminos.lifecycle(self.p, S1, "state", state="busy", machine="testhost")[0]
        self.bind("testhost")
        self.tick()
        self.assertEqual([e["seq"] for e in self.own("state")], [state["seq"], newer["seq"]],
                         "the newer state stands for it")
        self.assertEqual(len(self.own("joined")), 2, "the joined, with nothing newer, is still owed")

    def test_a_withheld_joined_of_a_session_that_ended_is_not_restated(self):
        self.withhold_the_first_snapshots()
        self.end_sender()
        self.tick()
        kinds = [e["kind"] for e in self.own()]
        self.assertEqual(kinds[-1], "retired", kinds)
        self.assertEqual((kinds.count("joined"), kinds.count("state")), (1, 1),
                         "a retired session is never joined again by a restatement")
        self.tick()
        self.assertEqual(self.own()[-1]["kind"], "retired")

    def test_a_withheld_message_owes_no_restatement(self):
        self.bind("testhost")
        self.hello()
        self.tick()
        self.upload()
        before = len(self.own())
        self.say("the secret words")
        self.assertEqual([r["reason"] for r in self.upload()], ["not-reachable"])
        self.tick()
        self.assertEqual(len(self.own()), before + 1, "nothing written for it")

    # Interruptions: a debt or a restatement's identity outlives a process
    # that dies between two writes, and a marker outlives any delay of its
    # verdict.

    def restate(self):
        return daemon._restate_held(sminos.project_path(self.p, daemon.RESTATE_FILE))

    def restated_before_a_crash(self):
        """The tick died after it appended the restatement of S1's `joined`
        and before it recorded it: the entry left `restating`. Returns the
        restatement."""
        held = self.restate()
        held[S1]["joined"]["restating"] = True
        sminos.write_json(sminos.project_path(self.p, daemon.RESTATE_FILE), held)
        return sminos.lifecycle(self.p, S1, "joined", **sminos.joined_again(sminos.own_events_of(self.p, S1), S1))[0]

    def test_the_debt_is_recorded_before_the_position_is_settled(self):
        self.hello()
        self.tick()
        joined = self.own("joined")[0]
        with mock.patch.object(hublog.HubLog, "save", side_effect=OSError("no space left")):
            with self.assertRaises(OSError):
                self.hl.withhold_own(W, joined["seq"])
        self.assertEqual(self.restate()[S1]["joined"]["seq"], joined["seq"], "owed, though never settled")
        self.assertTrue(self.hl.withhold_own(W, joined["seq"]), "its refusal seen again on resync settles it")
        self.assertEqual(self.restate()[S1]["joined"]["seq"], joined["seq"])

    def test_a_debt_that_cannot_be_recorded_still_settles_the_position(self):
        self.hello()
        self.tick()
        joined = self.own("joined")[0]
        with mock.patch.object(daemon, "owe_restatement", side_effect=OSError("no space left")):
            self.assertTrue(self.hl.withhold_own(W, joined["seq"]))
        self.assertIn(joined["seq"], self.hl.withheld()[W])
        self.assertIn("no space left", tw.daemon_log())

    def test_a_restatement_left_restating_and_appended_is_adopted(self):
        first, _ = self.withhold_the_first_snapshots()
        again = self.restated_before_a_crash()
        self.tick()
        self.assertEqual([e["seq"] for e in self.own("joined")], [first["seq"], again["seq"]], "not written again")
        self.assertEqual(self.restate()[S1]["joined"],
                         {"writer": again["writer"], "seq": again["seq"], "ts": again["ts"], "restated": True})
        self.upload()   # still bound to another machine: withheld again
        self.assertNotIn("joined", self.restate().get(S1, {}))
        self.tick()
        self.assertEqual(len(self.own("joined")), 2, "owed nothing more")

    def test_a_restatement_left_restating_and_withheld_owes_nothing(self):
        self.withhold_the_first_snapshots()
        self.restated_before_a_crash()
        self.upload()   # its verdict before any tick recovers it
        self.assertNotIn("joined", self.restate().get(S1, {}))
        self.tick()
        self.assertEqual(len(self.own("joined")), 2)

    def test_a_restated_marker_outlives_a_delayed_verdict(self):
        self.withhold_the_first_snapshots()
        self.tick()   # both restated, their verdicts not yet taken
        held = self.restate()
        for at in held[S1].values():
            at["ts"] = "2026-01-01T00:00:00.000Z"
        sminos.write_json(sminos.project_path(self.p, daemon.RESTATE_FILE), held)
        newer = sminos.lifecycle(self.p, S1, "state", state="busy", machine="testhost")[0]
        self.assertEqual(daemon.owe_restatement(self.p, W, newer["seq"], newer), "owed")
        self.assertTrue(self.restate()[S1]["joined"].get("restated"), "no verdict yet: kept, however old")
        self.upload()   # the verdicts arrive: each withheld
        self.assertNotIn("joined", self.restate().get(S1, {}))
        self.tick()
        self.assertEqual(len(self.own("joined")), 2, "not restated again")

    def test_a_restated_marker_is_dropped_once_a_have_admits_it(self):
        self.withhold_the_first_snapshots()
        self.bind("testhost")
        self.tick()
        self.assertEqual(sorted(self.restate()[S1]), ["joined", "state"])
        self.assertEqual(self.upload(), [], "admitted")
        self.tick()
        self.assertEqual(sorted(self.restate()[S1]), ["joined", "state"], "the hub's have has not said so yet")
        self.hello()
        self.tick()
        self.assertEqual(self.restate(), {})


class RestateThroughTheUplink(Sender):
    """A withheld `joined` restated end to end on RL10: the uplink in this
    process against endpoint_standin.py, whose `withhold` withholds S1's
    snapshots while it is bound elsewhere; the daemon's tick restates it,
    the uplink takes it up, and a later `have` that admits it drops the
    marker."""

    def project(self, name, hub=False):
        self.cut_over()
        return super().project(name, hub)

    def own(self, kind):
        return [e for e in tw.read_lines(sminos.writer_path(self.p, W)) if e["kind"] == kind]

    def restate(self):
        return daemon._restate_held(sminos.project_path(self.p, daemon.RESTATE_FILE))

    def tick(self):
        sminos.forget_caches()
        daemon.tick(self.p)
        sminos.nudge_daemon()

    def test_a_withheld_joined_is_restated_taken_up_and_its_marker_dropped_at_a_have(self):
        reach = Reach()
        reach.bound = "other"
        ep = self.endpoint(withhold=reach)
        self.uplink()
        ep.wait(lambda f: f["t"] == "hello" and f.get("project") == self.p.id)
        self.tick()
        first = tw.wait_for(lambda: self.own("joined"), timeout=10)[0]
        withheld = lambda: set((ep.withheld.get(self.p.id) or {}).get(W, ()))  # noqa: E731
        ep.wait_until(lambda: first["seq"] in withheld())
        self.assertTrue(tw.wait_for(lambda: first["seq"] in self.uplink_state().get("withheld", {}).get(W, ()),
                                    timeout=20), "settled withheld from the endpoint's refusal")
        self.assertEqual(self.restate()[S1]["joined"]["seq"], first["seq"], "a restatement owed")
        reach.bound = "testhost"
        self.tick()
        joined = self.own("joined")
        self.assertEqual(len(joined), 2, "the next tick writes the joined again")
        ep.wait_until(lambda: joined[1]["seq"] in ep.logs.get(self.p.id, {}).get(W, {}))
        self.assertEqual(ep.logs[self.p.id][W][joined[1]["seq"]]["kind"], "joined", "admitted")
        self.assertTrue(self.restate()[S1]["joined"].get("restated"), "kept until a have says so")
        conns = ep.conns
        ep.drop()   # the next connection's hello is answered by a have that admits it
        ep.wait_until(lambda: any(n > conns and f["t"] == "hello" and f.get("project") == self.p.id
                                  for n, f in ep.received))
        self.assertTrue(tw.wait_for(lambda: (self.tick(), "joined" not in self.restate().get(S1, {}))[1],
                                    timeout=20), self.restate())
        self.tick()
        self.assertEqual(len(self.own("joined")), 2, "restated once")


class StandinWithholds(unittest.TestCase):
    """endpoint_standin's `withhold` (#153 M3b), which the cases above
    stand on, against the stand-in alone."""

    P, WR = "proj-1", "testhost/s1"

    def setUp(self):
        self.dir = os.path.join(tw.BASE, "ep-%s" % self._testMethodName[-24:])
        self.out = set()
        self.ep = endpoint_standin.Endpoint(self.dir, withhold=lambda _p, e: e["seq"] in self.out)

    def ev(self, seq, text="t"):
        return {"ts": "2026-11-07T00:00:%02d.000Z" % seq, "writer": self.WR, "seq": seq, "kind": "say", "text": text}

    def refusals(self, *events):
        return [f["refusal"] for f in self.ep.take(self.P, list(events))]

    def test_a_withheld_upload_is_refused_not_reachable_listed_and_counted_and_its_writer_goes_on(self):
        self.out.add(2)
        self.assertEqual(self.refusals(self.ev(1), self.ev(2), self.ev(3)),
                         [{"reason": "not-reachable", "writer": self.WR, "seq": 2}], "no message")
        self.assertEqual(sorted(self.ep.logs[self.P][self.WR]), [1, 3], "the writer goes on")
        have = self.ep.have(self.P)
        self.assertEqual((have["have"], have["withheld"]), ({self.WR: 3}, {self.WR: [2]}))
        self.ep.set(admit=False)
        self.assertEqual(self.ep.have(self.P)["have"], {self.WR: 3}, "a withheld position counts, admitted or not")

    def test_a_withheld_position_sent_again_is_withheld_again_or_a_conflict(self):
        self.out.add(1)
        self.refusals(self.ev(1))
        self.out.clear()   # the judgement changed: the position stays withheld
        self.assertEqual(self.refusals(self.ev(1)), [{"reason": "not-reachable", "writer": self.WR, "seq": 1}])
        self.assertEqual(self.refusals(self.ev(1, "another")), [{"reason": "conflict", "writer": self.WR, "seq": 1}])
        self.assertNotIn(self.P, {p for p, ws in self.ep.logs.items() if ws.get(self.WR)})

    def test_a_position_held_is_never_withheld_and_none_withholds_nothing(self):
        self.refusals(self.ev(1))
        self.out.add(1)
        self.assertEqual(self.refusals(self.ev(1)), [], "an admitted position sent again stays admitted")
        self.assertNotIn("withheld", self.ep.have(self.P))
        plain = endpoint_standin.Endpoint(self.dir + "-plain")
        self.assertEqual(plain.take(self.P, [self.ev(1)]), [])
        self.assertIsNone(plain.withhold)


def tearDownModule():
    shutil.rmtree(tw.BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
