#!/usr/bin/env python3
"""Message reach at the send boundary (P5 O18 M4; MAWS's
docs/doperpowers/plans/2026-11-05-p5-o18-message-reach.md D3, D8, D10):
on a machine whose endpoint advertises `reach`, every log event pushed to a
session as a peer frame is the endpoint's to admit at that moment. The gate
(sminos.ReachGate) sits inside the push primitives, push_live and
resume_session; only the uplink, which holds the endpoint's one RL10
connection, asks `reach?` and pushes on `deliver`, under a permit for that
push alone. Every other deliverer leaves such an event owed for it. A
`refuse` settles `refused-reach` here, said in daemon.log; silence leaves it
owed, never given up. One owner's sessions of this machine reach each other
without an ask.

Each test is a fresh cut-over machine (test_words.WordsRig: its own HOME,
SMINOS_HOME and endpoint directory, the bridge faked), its uplink in this
process against the endpoint stand-in. Sessions are live `sleep` processes
with inboxes served by inbox_standin.py; `say` and `send` run as the CLI.

Run: python3 -B sminos/tests/test_reach_gate.py
"""

import argparse
import contextlib
import io
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_words as tw  # noqa: E402 — its machine: HOME, SMINOS_HOME, the enrollment, sessions, the uplink

import endpoint_standin  # noqa: E402
import sminos  # noqa: E402
import sminos_audience as au  # noqa: E402
import sminos_control as control  # noqa: E402
import sminos_holder_deliveries as hd  # noqa: E402
import sminos_outcomes as outcomes  # noqa: E402
import sminos_records as records  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

RECIP, SENDER, SEATED = tw.S1, tw.S2, tw.S3
ELSEWHERE = "6d000004-0000-4000-8000-0000000000d4"
OTHER = tw.OTHER                       # another machine's session writer
REACH = ["access", "reach"]            # an O18 endpoint's welcome
ANOTHER = ["mem-2"]                    # a session another member spawned on this machine
WAIT = 15


class Rig(tw.WordsRig):
    """The machine, its endpoint advertising `reach` (kept as the uplink
    keeps the welcome's), a hub project `hp`."""

    def setUp(self):
        super().setUp()
        au.keep_capabilities(REACH)

    def endpoint(self, capabilities=REACH, **fields):
        return super().endpoint(capabilities=capabilities, **fields)

    def owned(self, sid, owners=(records.MACHINE,)):
        """The session's record, final, naming `owners`."""
        records.establish(sid, {**records.default_provenance("launch"), "owners": list(owners)})

    def live(self, sid, name, owners=(records.MACHINE,)):
        self.session(self.hp, sid, name=name, inbox=True)
        self.owned(sid, owners)
        sminos.reconcile(self.hp)

    def cli(self, *args, session=SENDER):
        r = tw.sminos_cli(*args, cwd=self.hp.root, session=session)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def reach_asks(self, ep, seq=None):
        return [f for f in ep.frames("reach?") if seq is None or f["event"]["seq"] == seq]

    def seq(self, text):
        """The seq of the logged message whose text is `text`."""
        return next(e["seq"] for e in sminos.log_read(self.hp) if e.get("text") == text)

    def settled_at(self, text, sid=RECIP, writer="testhost/" + SENDER):
        """Whether the message is settled for the session."""
        return self.settled(self.hp, sid, writer) >= self.seq(text)

    def refused_line(self, writer_short, seq, sid=RECIP):
        return "the endpoint refused %s:%d (hp) reach into %s" % (writer_short, seq, sid[:8])

    def peer_say(self, seq, text, to=RECIP, writer=OTHER):
        """Another machine's session's `say`, as it arrives over RL10."""
        return self.arrive(self.hp, writer, seq, kind="say", to=(to,), signer=tw.MACHINE_K, sender="peer", text=text)

    def outbox(self):
        return outcomes.Outbox(self.hp).read()

    def seat(self, alias, sid, owners=(records.MACHINE,)):
        out = self.cli("seat", "add", "crew", alias, "--session", sid, session=None)
        self.assertIn("added", out)
        self.owned(sid, owners)
        sminos.forget_caches()

    def transcript(self, sid):
        d = os.path.join(os.environ["HOME"], ".claude", "projects", "-hp")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, sid + ".jsonl"), "w") as f:
            f.write(json.dumps({"type": "user", "sessionId": sid, "cwd": self.hp.root,
                                "message": {"role": "user", "content": "hi"}}) + "\n")
        sminos.forget_caches()
        sminos.transcripts_now()

    def launches(self):
        """`claude --bg --resume` faked: each launch's message, the resumed
        session reporting itself at once."""
        calls = []

        def bg(args, cwd, settings):
            calls.append(args[args.index("--resume") + 2])
            return "abcd1234", "backgrounded · abcd1234"
        for name, fake in (("run_claude_bg", bg), ("poll_uuid", lambda short, **_: (SEATED, "working", self.hp.root))):
            patcher = mock.patch.object(sminos, name, side_effect=fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        return calls

    def corrupt(self, sid):
        """The session's record file made unreadable; restore() puts it back."""
        path = records.record_path(sid)
        kept = Path(path).read_text()
        Path(path).write_text("{")
        return lambda: Path(path).write_text(kept)


# ------------------------------------------------------------- every path


class Paths(Rig):
    """Refused for a refuse, delivered for a deliver, through each path a
    peer push takes; nothing asks but the uplink."""

    def verdict(self, f):
        return "refuse" if "keep out" in f["event"]["text"] else "deliver"

    def test_a_same_machine_session_of_another_member(self):
        self.live(SENDER, "sender")
        self.live(RECIP, "rover", owners=ANOTHER)
        ep = self.endpoint(reach_verdict=self.verdict)
        self.uplink()
        ep.wait(lambda f: f["t"] == "member" and f["session"] == RECIP)
        out = self.cli("say", "@rover keep out")
        self.assertIn("rover: %s" % sminos.WORDS_RECORDED, out, "the CLI pushes nothing, the uplink asks")
        tw.wait_for(lambda: self.settled_at("@rover keep out"), timeout=WAIT)
        seq = self.seq("@rover keep out")
        self.assertEqual(len(self.reach_asks(ep, seq)), 1)
        ask = self.reach_asks(ep, seq)[0]
        self.assertEqual(set(ask), {"t", "id", "project", "session", "event"})
        self.assertEqual((ask["project"], ask["session"]), (self.hp.id, RECIP))
        self.assertNotIn("verified", ask["event"])
        self.assertIn(self.refused_line(SENDER[:8], seq), tw.daemon_log())
        self.assertIn("not-reachable", tw.daemon_log())
        self.assertNotIn("keep out", tw.daemon_log(), "content-free")
        self.cli("say", "@rover come in")
        tw.wait_for(lambda: self.inbox(RECIP), timeout=WAIT)
        self.assertEqual(len(self.inbox(RECIP)), 1)
        self.assertIn("come in", self.inbox(RECIP)[0])
        self.assertTrue(self.settled_at("@rover come in"))

    def test_a_live_seat(self):
        self.live(SENDER, "sender")
        self.session(self.hp, RECIP, name="rover", inbox=True)
        self.seat("rover", RECIP, owners=ANOTHER)
        ep = self.endpoint(reach_verdict=self.verdict)
        self.uplink()
        ep.wait(lambda f: f["t"] == "member" and f["session"] == RECIP)
        out = self.cli("send", "rover", "keep out")
        self.assertIn("the endpoint decides its delivery", out)
        tw.wait_for(lambda: self.settled_at("keep out"), timeout=WAIT)
        self.assertEqual(self.inbox(RECIP), [])
        self.assertIn(self.refused_line(SENDER[:8], self.seq("keep out")), tw.daemon_log())
        self.cli("send", "rover", "come in")
        tw.wait_for(lambda: self.inbox(RECIP), timeout=WAIT)
        self.assertEqual(len(self.inbox(RECIP)), 1)
        self.assertIn("come in", self.inbox(RECIP)[0])

    def test_a_stopped_seats_resume(self):
        self.live(SENDER, "sender")
        self.seat("parked", SEATED, owners=ANOTHER)
        self.transcript(SEATED)
        self.assertEqual(sminos.state(sminos.resolve_seat("crew/parked")), "stopped")
        launched = self.launches()
        ep = self.endpoint(reach_verdict=self.verdict)
        self.uplink()
        out = self.cli("send", "crew/parked", "keep out")
        self.assertIn("the endpoint decides its delivery", out)
        tw.wait_for(lambda: self.settled_at("keep out", SEATED), timeout=WAIT)
        self.assertEqual(launched, [], "nothing resumed for a refused message")
        self.assertIn(self.refused_line(SENDER[:8], self.seq("keep out"), SEATED), tw.daemon_log())
        self.cli("send", "crew/parked", "come in")
        tw.wait_for(lambda: launched, timeout=WAIT)
        self.assertEqual(len(launched), 1)
        self.assertIn("come in", launched[0], "resumed with the admitted message as its prompt")
        self.assertEqual(len(self.reach_asks(ep)), 2)

    def test_a_legacy_holders_direct_push(self):
        self.live(SENDER, "sender")
        self.live(RECIP, "rover", owners=ANOTHER)
        ep = self.endpoint(reach_verdict=self.verdict)
        self.uplink()
        out = self.cli("send", "rover", "keep out")
        self.assertIn("recorded %s:%d for rover; the endpoint decides its delivery" % (
            SENDER[:8], self.seq("keep out")), out)
        tw.wait_for(lambda: self.settled_at("keep out"), timeout=WAIT)
        self.assertEqual(self.inbox(RECIP), [])
        self.cli("send", "rover", "come in")
        tw.wait_for(lambda: self.inbox(RECIP), timeout=WAIT)
        self.assertIn("come in", self.inbox(RECIP)[0])
        self.assertEqual(hd.read_mode(hd.process(sminos.peer_for_session(RECIP)["pid"]))["mode"], "legacy")
        self.assertEqual(len(self.reach_asks(ep)), 2)

    def test_a_send_that_forgot_the_hold_is_stopped_inside_the_push(self):
        """The gate inside push_live is the authority: send_to_member's own
        legacy push, its SendDelivery not held, pushes nothing."""
        self.live(SENDER, "sender")
        self.live(RECIP, "rover", owners=ANOTHER)

        class Forgetful(sminos.SendDelivery):
            def __init__(self, *a):
                super().__init__(*a)
                self.held = None
        m = next(m for m in sminos.members(self.hp) if m.session == RECIP)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": SENDER}), \
                mock.patch.object(sminos, "SendDelivery", Forgetful), contextlib.redirect_stdout(out):
            sminos.send_to_member(self.hp, m, "sender", "sender", "slipped", "abcd0001")
        self.assertIn("the endpoint decides its delivery", out.getvalue())
        self.assertEqual(self.inbox(RECIP), [])
        self.assertEqual([e["text"] for e in sminos.owed(self.hp, m)], ["slipped"], "left owed, no attempt")
        self.assertNotIn("attempts", self.record(self.hp, RECIP).get("testhost/" + SENDER, {}))


# ------------------------------------------------------------- order, admission, retries


class Order(Rig):
    def test_an_earlier_event_refused_is_left_out_and_the_later_one_delivered(self):
        """Per writer, in order: seq 1 refused and settled, seq 2 delivered."""
        self.live(RECIP, "rover", owners=ANOTHER)
        self.peer_say(1, "first")
        self.peer_say(2, "second")
        ep = self.endpoint(reach_verdict=lambda f: "refuse" if f["event"]["seq"] == 1 else "deliver")
        self.uplink()
        tw.wait_for(lambda: self.settled(self.hp, RECIP, OTHER) == 2, timeout=WAIT)
        self.assertEqual(len(self.inbox(RECIP)), 1)
        self.assertIn("second", self.inbox(RECIP)[0])
        self.assertEqual([f["event"]["seq"] for f in self.reach_asks(ep)], [1, 2], "asked in order, each once")
        self.assertEqual(self.outcome_up(ep, OTHER, 2)["outcome"], "delivered", "the delivery's outcome goes up")
        time.sleep(0.5)
        self.assertEqual([f["message"]["body"]["event"]["seq"] for f in ep.frames("session")
                          if f["message"]["kind"] == "delivery"], [2], "the refusal stays here")

    def test_the_registry_admits_and_the_endpoint_refuses(self):
        """An event the hub admitted (it arrived over RL10) refused at reach:
        nothing delivered, settled refused-reach, no outcome back."""
        self.live(RECIP, "rover", owners=ANOTHER)
        self.peer_say(1, "admitted upstream")
        ep = self.endpoint(reach_verdict=("refuse", "unverified"))
        self.uplink()
        tw.wait_for(lambda: self.settled(self.hp, RECIP, OTHER) == 1, timeout=WAIT)
        time.sleep(0.5)
        self.assertEqual((self.inbox(RECIP), self.bridge, self.outbox()), ([], [], []))
        self.assertIn(self.refused_line("6d0000ff", 1) + ": unverified", tw.daemon_log())
        self.assertEqual(len(self.reach_asks(ep)), 1)

    def test_a_words_peer_verdict_asks_reach_again(self):
        """A member's `hub/<member>` words answered `peer`, then `reach?`
        refused: the words admission never stands for the push."""
        self.live(RECIP, "rover", owners=ANOTHER)
        self.arrive(self.hp, "hub/mem-1", 1, signer=tw.DEV_A, text="as a peer")
        ep = self.endpoint(verdict="peer", reach_verdict="refuse")
        self.uplink()
        tw.wait_for(lambda: self.settled(self.hp, RECIP, "hub/mem-1") == 1, timeout=WAIT)
        time.sleep(0.5)
        self.assertEqual((self.inbox(RECIP), self.bridge), ([], []))
        frames = ep.frames()
        words = next(i for i, f in enumerate(frames) if f["t"] == "words?")
        reach = next(i for i, f in enumerate(frames) if f["t"] == "reach?")
        self.assertLess(words, reach, "asked `reach?` after the `peer` verdict")
        self.assertEqual(frames[reach]["event"]["writer"], "hub/mem-1")
        self.assertIn(self.refused_line("hub/mem-1", 1), tw.daemon_log())

    def test_a_words_peer_verdict_then_deliver_is_a_peer_frame(self):
        self.live(RECIP, "rover", owners=ANOTHER)
        self.arrive(self.hp, "hub/mem-1", 1, signer=tw.DEV_A, text="as a peer")
        self.endpoint(verdict="peer", reach_verdict="deliver")
        self.uplink()
        tw.wait_for(lambda: self.inbox(RECIP), timeout=WAIT)
        self.assertIn("as a peer", self.inbox(RECIP)[0])
        self.assertEqual(self.bridge, [], "a peer's, never the bridge")

    def test_a_receipts_retry_asks_again(self):
        """A `gate` process: the first push, admitted, fails before it
        reaches the inbox; its receipt's retry asks `reach?` again, and is
        refused."""
        self.live(RECIP, "rover", owners=ANOTHER)
        rec = hd.activate(sminos.peer_for_session(RECIP)["pid"], "launch-1", RECIP)
        self.assertEqual(rec["mode"], "gate")
        self.peer_say(1, "retried")
        answers = iter(["deliver"])
        ep = self.endpoint(reach_verdict=lambda f: next(answers, "refuse"))
        pushes = []

        def fail(*a, **_kw):
            pushes.append(a[1])
            raise sminos.SendFailed("before", "the inbox went away")
        patcher = mock.patch.object(sminos, "send_frame", side_effect=fail)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.uplink()
        tw.wait_for(lambda: self.settled(self.hp, RECIP, OTHER) == 1, timeout=WAIT)
        self.assertEqual(len(pushes), 1, "the admitted push, made once")
        self.assertEqual(len(hd.markers(pushes[0])), 1, "under its receipt")
        asks = self.reach_asks(ep)
        self.assertEqual([f["event"]["seq"] for f in asks], [1, 1], "the retry asked again")
        self.assertNotEqual(asks[0]["id"], asks[1]["id"])
        self.assertEqual(self.inbox(RECIP), [])
        self.assertIn(self.refused_line("6d0000ff", 1), tw.daemon_log())
        self.assertEqual(self.outbox(), [], "no outcome goes back for a refusal")
        self.assertNotIn("delivery", {f["message"]["kind"] for f in ep.frames("session")})


# ------------------------------------------------------------- fail closed


class Owed(Rig):
    def test_an_unreadable_recipient_is_never_asked_and_delivered_once_it_reads(self):
        self.live(RECIP, "rover", owners=ANOTHER)
        restore = self.corrupt(RECIP)
        self.peer_say(1, "wait for me")
        ep = self.endpoint(reach_verdict="deliver")
        self.uplink()
        ep.wait(lambda f: f["t"] == "hello")
        time.sleep(2.0)
        self.assertEqual(self.reach_asks(ep), [], "no `reach?` for a recipient whose record cannot be read")
        self.assertEqual((self.inbox(RECIP), self.settled(self.hp, RECIP, OTHER)), ([], 0))
        self.assertEqual(sminos.deliver_next(self.hp, tw.member(RECIP))["delivered"], 0, "owed for every deliverer")
        restore()
        sminos.nudge_daemon()
        tw.wait_for(lambda: self.inbox(RECIP), timeout=WAIT)
        self.assertIn("wait for me", self.inbox(RECIP)[0])
        self.assertEqual(len(self.reach_asks(ep)), 1)

    def test_a_silent_endpoint_leaves_it_owed_with_no_attempt_then_it_is_delivered(self):
        self.live(RECIP, "rover", owners=ANOTHER)
        self.peer_say(1, "hello at last")
        ep = self.endpoint()
        with mock.patch.object(uplink, "REACH_WAIT", 0.3):
            self.uplink()
            ep.wait_until(lambda: len(self.reach_asks(ep)) >= 3, timeout=WAIT)
            first, second = self.reach_asks(ep)[:2]
            self.assertNotEqual(first["id"], second["id"], "asked again, under a new id")
            w = self.record(self.hp, RECIP).get(OTHER, {})
            self.assertEqual((w.get("settled", 0), w.get("attempts")), (0, None), "owed, no attempt counted")
            ep.send({"t": "reach", "id": first["id"], "verdict": "deliver"})   # an answer past its deadline
            time.sleep(0.5)
            self.assertEqual(self.inbox(RECIP), [], "no answer")
            self.assertEqual(tw.daemon_log().count("gave no answer on the reach of"), 1, "said once")
            ep.set(reach_verdict="deliver")
            tw.wait_for(lambda: self.inbox(RECIP), timeout=WAIT)
        self.assertIn("hello at last", self.inbox(RECIP)[0])

    def test_a_malformed_answer_is_no_answer(self):
        self.live(RECIP, "rover", owners=ANOTHER)
        self.peer_say(1, "again")
        ep = self.endpoint(reach_verdict="maybe")
        with mock.patch.object(uplink, "WORDS_EVERY", 0.2):
            self.uplink()
            ep.wait_until(lambda: len(self.reach_asks(ep)) >= 2, timeout=WAIT)
        self.assertEqual((self.inbox(RECIP), self.settled(self.hp, RECIP, OTHER)), ([], 0))
        self.assertIsNone(self.record(self.hp, RECIP).get(OTHER, {}).get("attempts"))

    def test_an_old_endpoint_is_never_asked_and_delivers_as_before(self):
        au.keep_capabilities(["access"])
        self.live(SENDER, "sender")
        self.live(RECIP, "rover", owners=ANOTHER)
        ep = self.endpoint(capabilities=["access"], reach_verdict="refuse")
        self.uplink()
        out = self.cli("say", "@rover as before")
        self.assertIn("rover: sent", out)
        self.assertIn("as before", self.inbox(RECIP)[0])
        self.peer_say(1, "imported")
        sminos.nudge_daemon()
        time.sleep(2.0)
        self.assertEqual(sminos.deliver_next(self.hp, tw.member(RECIP))["delivered"], 1)
        self.assertEqual(self.reach_asks(ep), [])


# ------------------------------------------------------------- one owner's sessions


class SameOwner(Rig):
    """The coordinator's ruling: a session of this machine to another whose
    record names literally the same owners needs no ask."""

    def test_two_machine_owned_sessions_need_no_endpoint(self):
        self.live(SENDER, "sender")
        self.live(RECIP, "rover")
        out = self.cli("say", "@rover no endpoint here")
        self.assertIn("rover: sent", out, "the CLI's fast path, with no endpoint listening")
        self.assertIn("no endpoint here", self.inbox(RECIP)[0])
        ep = self.endpoint(reach_verdict="refuse")
        self.uplink()
        out = self.cli("send", "rover", "nor here")
        self.assertIn("sent to rover", out)
        ep.wait(lambda f: f["t"] == "hello")
        time.sleep(1.0)
        self.assertEqual(self.reach_asks(ep), [])
        self.assertEqual(len(self.inbox(RECIP)), 2)

    def test_the_same_explicit_owners(self):
        self.live(SENDER, "sender", owners=ANOTHER)
        self.live(RECIP, "rover", owners=ANOTHER)
        self.assertIn("rover: sent", self.cli("say", "@rover mine"))

    def test_another_persons_session_on_this_machine_is_asked(self):
        self.live(SENDER, "sender")
        self.live(RECIP, "rover", owners=["m-other"])
        ep = self.endpoint(reach_verdict="deliver")
        self.uplink()
        self.assertIn(sminos.WORDS_RECORDED, self.cli("say", "@rover yours"))
        tw.wait_for(lambda: self.inbox(RECIP), timeout=WAIT)
        self.assertEqual(len(self.reach_asks(ep)), 1)

    def test_a_sender_whose_record_cannot_be_read_is_asked(self):
        self.live(SENDER, "sender")
        self.live(RECIP, "rover")
        sminos.log_append(self.hp, "testhost/" + SENDER, "say",
                          **{"from": "sender", "to": [{"session": RECIP, "alias": "rover"}], "text": "from the past"})
        self.corrupt(SENDER)
        self.assertEqual(sminos.deliver_next(self.hp, tw.member(RECIP))["gated"][0]["text"], "from the past")
        ep = self.endpoint(reach_verdict="deliver")
        self.uplink()
        tw.wait_for(lambda: self.inbox(RECIP), timeout=WAIT)
        self.assertEqual(len(self.reach_asks(ep)), 1)

    def test_the_operators_writer_is_never_the_fast_path(self):
        self.live(RECIP, "rover")
        e = sminos.log_append(self.hp, "testhost/human", "say",
                              **{"from": "human", "to": [{"session": RECIP, "alias": "rover"}], "text": "op"})
        self.assertTrue(sminos.ReachGate(self.hp).needs(e, RECIP))

    def mirrored(self, name):
        """A project git mirrors: a remote named, no hub."""
        p = self.project(name)
        smns = Path(p.root, ".smns")
        smns.write_text(json.dumps({**json.loads(smns.read_text()), "remote": "/nowhere/%s-log.git" % name}))
        sminos.forget_caches()
        p = sminos.resolve_project(p.root)
        self.assertTrue(p.remote and p.hub is None)
        return p

    def imported_say(self, project, text):
        """A `say` under this machine's name and SENDER's id, as a git merge
        brings one: no `verified`, nothing appended here."""
        seq = max([e["seq"] for e in sminos.log_read(project) if e["writer"] == "testhost/" + SENDER] or [0]) + 1
        return self.arrive(project, "testhost/" + SENDER, seq, kind="say", to=(RECIP,), signer=None,
                           sender="sender", text=text)

    def test_an_own_name_say_a_git_mirror_imported_goes_through_reach(self):
        """The writer name is not provenance: a git-mirrored log can import a
        line under this machine's name and an existing local session's id
        that no one here wrote. Only a log that cannot bring this machine's
        own writers from elsewhere takes the name for the sender: a hub
        project of its org, or a project nothing syncs."""
        gm = self.mirrored("gm")
        for sid, name in ((SENDER, "sender"), (RECIP, "rover")):
            self.session(gm, sid, name=name, inbox=True)
            self.owned(sid)
        sminos.reconcile(gm)
        e = self.imported_say(gm, "not from here")
        self.assertTrue(sminos.ReachGate(gm).needs(e, RECIP), "a git mirror's import is asked")
        self.assertTrue(sminos.ReachGate(gm.id).needs(e, RECIP), "named by its id alike")
        sminos.deliver_next(gm, tw.member(RECIP))
        self.assertEqual(self.inbox(RECIP), [], "left owed for the uplink's reach?")
        ep = self.endpoint(reach_verdict="refuse")
        self.uplink()
        tw.wait_for(lambda: self.reach_asks(ep), timeout=WAIT)
        self.assertEqual(self.reach_asks(ep)[0]["event"]["seq"], e["seq"])
        self.assertEqual(self.inbox(RECIP), [])

    def test_a_mirror_converted_to_a_hub_project_still_asks_about_what_git_imported(self):
        """`project init --hub` keeps the project's id, its log and its git
        remote (now the log's archive): a line git imported under this
        machine's name before the conversion is still in the log, so a
        project with a remote never takes the name for the sender."""
        gm = self.mirrored("gc")
        for sid, name in ((SENDER, "sender"), (RECIP, "rover")):
            self.session(gm, sid, name=name, inbox=True)
            self.owned(sid)
        sminos.reconcile(gm)
        e = self.imported_say(gm, "imported before the hub")
        enrolled = Path(os.environ["SMINOS_HOME"], "daemon", "identity.json")
        hub = {"hub": "http://127.0.0.1:9", "org": "org-1"}
        self.assertEqual({k: json.loads(enrolled.read_text())[k] for k in hub}, hub)
        r = tw.sminos_cli("project", "init", "--hub", cwd=gm.root, session=None)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        sminos.forget_caches()
        hp = sminos.resolve_project(gm.root)
        self.assertEqual((hp.id, hp.remote, (hp.hub or {}).get("org")), (gm.id, gm.remote, "org-1"),
                         "the same project, its remote kept, now of the org's hub")
        self.assertTrue(sminos.ReachGate(hp).needs(e, RECIP), "what git imported is still asked")
        sminos.deliver_next(hp, tw.member(RECIP))
        self.assertEqual(self.inbox(RECIP), [], "left owed for the uplink's reach?")

    def test_a_project_nothing_syncs_keeps_the_fast_path(self):
        lp = self.project("lp")
        self.assertFalse(lp.remote or lp.hub)
        for sid, name in ((SENDER, "sender"), (RECIP, "rover")):
            self.session(lp, sid, name=name, inbox=True)
            self.owned(sid)
        e = sminos.log_append(lp, "testhost/" + SENDER, "say",
                              **{"from": "sender", "to": [{"session": RECIP, "alias": "rover"}], "text": "mine"})
        self.assertFalse(sminos.ReachGate(lp).needs(e, RECIP))
        self.assertFalse(sminos.ReachGate(self.hp).needs(
            {**e, "seq": 99}, RECIP), "a hub project of this machine's org: its own writers are its own")


# ------------------------------------------------------------- the capability, before any welcome


class Capability(Rig):
    def test_a_cut_over_machine_with_no_capabilities_kept_holds_peer_pushes_until_a_welcome(self):
        """A cut-over machine whose endpoint has not said yet (no
        audiences.json: a welcome keeps it, an old endpoint's empty list
        included) is taken as reach-capable: a peer push waits for the
        endpoint's word rather than going unasked."""
        self.live(SENDER, "sender")
        self.live(RECIP, "rover", owners=ANOTHER)
        os.unlink(au.audiences_path())
        self.assertTrue(au.reach_capable())
        self.assertIn(sminos.WORDS_RECORDED, self.cli("say", "@rover before any welcome"))
        time.sleep(0.5)
        self.assertEqual(self.inbox(RECIP), [], "nothing pushed unasked")
        ep = self.endpoint(reach_verdict="deliver")
        self.uplink()
        tw.wait_for(lambda: self.inbox(RECIP), timeout=WAIT)
        self.assertEqual(len(self.reach_asks(ep)), 1)
        self.assertTrue(os.path.exists(au.audiences_path()), "the welcome kept what it said")

    def test_a_welcome_landing_just_after_the_read_finds_none_is_still_capable(self):
        """One read decides: the file missing when it was read is capable,
        though a welcome writes it (an endpoint without reach) a moment
        after."""
        os.unlink(au.audiences_path())
        real = sminos.json_at

        def welcome_after(path):
            try:
                return real(path)
            except FileNotFoundError:
                if path == au.audiences_path():
                    au._write_audiences({"v": 1, "capabilities": [], "sessions": {}})
                raise
        with mock.patch.object(sminos, "json_at", side_effect=welcome_after):
            self.assertTrue(au.reach_capable())
        self.assertFalse(au.reach_capable(), "and the welcome's word from then on")

    def test_an_endpoint_that_said_it_has_no_reach_pushes_as_before(self):
        au.keep_capabilities([])
        self.assertFalse(au.reach_capable())
        os.unlink(sminos.sibling_module("sminos_rl10").identity_path())
        sminos.forget_caches()
        self.assertFalse(au.reach_capable(), "a machine not cut over: never")


# ------------------------------------------------------------- the projectless push


class Projectless(Rig):
    def resume(self, seat, msg, session=SENDER):
        a = argparse.Namespace(seat=seat, msg=msg, wait=False, model=None, settings=None, effort=None)
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": session} if session else {}), \
                contextlib.redirect_stderr(err):
            if not session:
                os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            try:
                sminos.cmd_resume(a)
            except SystemExit as e:
                return e.code, err.getvalue()
        return 0, err.getvalue()

    def test_a_resume_with_a_message_reaches_only_its_owners_sessions(self):
        self.live(SENDER, "sender")
        self.seat("parked", SEATED, owners=ANOTHER)
        self.transcript(SEATED)
        launched = self.launches()
        code, err = self.resume("crew/parked", "from outside")
        self.assertNotEqual(code, 0)
        self.assertIn("parked has no project, so only its owners' sessions reach it", err)
        self.assertEqual(launched, [], "nothing stopped or launched")

    def test_the_same_owner_passes(self):
        self.live(SENDER, "sender")
        self.seat("parked", SEATED)
        self.transcript(SEATED)
        launched = self.launches()
        code, err = self.resume("crew/parked", "from my own session")
        self.assertEqual(code, 0, err)
        self.assertEqual(launched, ["from my own session"])

    def test_the_operator_is_the_machines_owners(self):
        self.seat("parked", SEATED)
        self.transcript(SEATED)
        launched = self.launches()
        self.assertEqual(self.resume("crew/parked", "from the terminal", session=None)[0], 0)
        self.assertEqual(launched, ["from the terminal"])

    def test_the_operator_meets_a_desk_spawned_seat_by_the_endpoints_word(self):
        """A seat the owner's desk spawned names the member; the operator's
        `@machine` is that member as the endpoint resolved a `@machine`
        session's owners. Another member's seat stays refused."""
        self.live(SENDER, "sender")
        self.assertTrue(au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(SENDER, ["mem-1"])}))
        self.seat("parked", SEATED, owners=["mem-1"])
        self.seat("theirs", ELSEWHERE, owners=ANOTHER)
        for sid in (SEATED, ELSEWHERE):
            self.transcript(sid)
        launched = self.launches()
        self.assertEqual(self.resume("crew/parked", "from its owner", session=None)[0], 0)
        code, err = self.resume("crew/theirs", "from outside", session=None)
        self.assertNotEqual(code, 0)
        self.assertIn("theirs has no project, so only its owners' sessions reach it", err)
        self.assertEqual(launched, ["from its owner"])


# ------------------------------------------------------------- the primitive


class Primitive(Rig):
    def test_push_live_with_a_peer_event_and_no_permit_raises_and_pushes_nothing(self):
        self.live(SENDER, "sender")
        self.live(RECIP, "rover", owners=ANOTHER)
        e = sminos.log_append(self.hp, "testhost/" + SENDER, "say",
                              **{"from": "sender", "to": [{"session": RECIP, "alias": "rover"}], "text": "direct"})
        peer = sminos.peer_for_session(RECIP)
        with self.assertRaises(sminos.ReachHeld) as caught:
            control.push_live(peer, RECIP, "direct", e, self.hp.id)
        self.assertEqual((caught.exception.phase, caught.exception.verdict), ("before", "owed"))
        self.assertEqual(self.inbox(RECIP), [])
        with sminos.reach_permit(self.hp, RECIP, e):
            control.push_live(peer, RECIP, "direct", e, self.hp.id)
        tw.wait_for(lambda: self.inbox(RECIP), timeout=WAIT)
        self.assertEqual(len(self.inbox(RECIP)), 1)
        with self.assertRaises(sminos.ReachHeld):
            control.push_live(peer, RECIP, "direct", e, self.hp.id)   # the permit was spent
        self.assertEqual(len(self.inbox(RECIP)), 1)

    def test_every_carried_event_is_checked(self):
        self.live(SENDER, "sender")
        self.live(RECIP, "rover", owners=ANOTHER)
        mk = lambda t: sminos.log_append(self.hp, "testhost/" + SENDER, "say", **{  # noqa: E731
            "from": "sender", "to": [{"session": RECIP, "alias": "rover"}], "text": t})
        first, last = mk("one"), mk("two")
        with sminos.reach_permit(self.hp, RECIP, last), self.assertRaises(sminos.ReachHeld) as caught:
            control.push_live(sminos.peer_for_session(RECIP), RECIP, "one\n\ntwo", last, self.hp.id,
                              carried=[first, last])
        self.assertEqual([e["seq"] for e in caught.exception.events], [first["seq"]])
        self.assertEqual(self.inbox(RECIP), [])

    def test_a_machine_not_reach_capable_pushes_as_before(self):
        au.keep_capabilities(["access"])
        self.live(SENDER, "sender")
        self.live(RECIP, "rover", owners=ANOTHER)
        e = sminos.log_append(self.hp, "testhost/" + SENDER, "say",
                              **{"from": "sender", "to": [{"session": RECIP, "alias": "rover"}], "text": "direct"})
        control.push_live(sminos.peer_for_session(RECIP), RECIP, "direct", e, self.hp.id)
        tw.wait_for(lambda: self.inbox(RECIP), timeout=WAIT)
        self.assertEqual(len(self.inbox(RECIP)), 1)


if __name__ == "__main__":
    unittest.main()
