#!/usr/bin/env python3
"""The lead, and whose words a post is (CH2's M8:
docs/doperpowers/plans/2026-11-22-sminos-channels-ch2.md, the milestone's
"Seams" and "Proves"; Interfaces §5), on one machine cut over to an endpoint
that is never run and whose welcome listed `channels`:

- The verb, `channel lead <channel> <thread|none>` (`Verb`): refused inside
  a session before anything is read, where there is no terminal, without the
  capability, where the enrollment does not carry the channel's log, for a
  thread that is not in the channel (an unknown name exit 4), where the
  stream choice refuses, and when the person does not type yes, each with
  every log as it was; a typed yes on a real controlling terminal writes the
  event under the machine's human writer, plain for a thread that is not
  private, under that writer's audience stream after a plain clearing event
  for one that is, on this machine and for a thread of another machine; the
  raw upload of a private lead, and a less-privileged reader's copy of the
  log, which reads no lead; `none` clears it.
- Whose lead is in effect (`LeadOf`): the last honoured `channel-lead` by
  merge order, two machines' human writers the later holding; one under a
  session's writer, under `hub/<member>` or carrying `notice` ignored; a
  lead removed, ended and returned (untagged, untagged, addressed again),
  and an earlier lead never back in its place.
- The post (`Post`): an untagged message the person types at a terminal is
  addressed to the lead; one from a session, a notice and a tagged one are
  not; on the lead's machine the endpoint's `words` hands it to the bridge
  keyed by the channel and the thread (the supervisor's reply where no
  bridge takes it), never an inbox frame; `peer` hands it over as a peer's
  frame from `human`; a stopped lead is woken by it; a notice tagged to the
  lead is a machine's notice whatever the word, and the manager's
  classifier does not mark it the owner's; nothing a push of a post leaves
  under the channel or in the lead's project is a word to a human (B7).
- `channel show` and its `--json` with and without a lead (`Show`).

Hermetic: test_channels_say's Say (test_wake's Engine, HOME, SMINOS_HOME and
the engine's state temporary; the engine first on PATH); the typed yes on a
controlling pty of the CLI's own (pty.fork), as test_visibility drives
`confirmed`; the uplink a Link over the store whose lanes keep what they are
sent, as test_channels_wire's Messages drives one.
Run: python3 -B sminos/tests/test_channels_lead.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import glob
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

import endpoint_standin  # noqa: E402
import test_threads as T1  # noqa: E402
from test_channels_life import DESK, HUB  # noqa: E402
from test_channels_say import APP, FOREIGN, Say  # noqa: E402
from test_threads import SCRIPTS, records, sminos, threads  # noqa: E402
from test_wake import wait_for  # noqa: E402
import sminos_channels as channels  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_uplink as uplink  # noqa: E402
import channel_wire as wire  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "skills", "manager", "scripts"))
import manager_window  # noqa: E402

CRED = {"org": HUB["org"], "hub": HUB["url"], "key": None}
FAR = "beta"   # another machine of the org


class Lane:
    """A Link's lane that keeps what it is sent, written as taken at once."""

    def __init__(self):
        self.sent = []

    def send(self, frames, then=None):
        self.sent += frames
        if then is not None:
            then()

    def posting(self):
        return False

    def queued(self):
        return 0

    def close(self):
        pass


class Lead(Say):
    # -- the CLI in a process of its own

    def env(self):
        return {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}

    def tty(self, answer, *argv, cwd=None):
        """The CLI on a controlling pty of its own, a person typing `answer` at its prompt (none typed when no
        prompt comes): (exit code, what it printed, whether it prompted)."""
        env = self.env()
        pid, fd = pty.fork()
        if pid == 0:
            try:
                os.chdir(cwd or self.root)
                os.execve(sys.executable, [sys.executable, "-B", os.path.join(SCRIPTS, "sminos.py"), *argv], env)
            finally:
                os._exit(127)
        out, sent, end = b"", False, time.monotonic() + 60
        while time.monotonic() < end:
            ready, _, _ = select.select([fd], [], [], 1)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            if not sent and b"[y/N]" in out:
                os.write(fd, answer.encode() + b"\n")
                sent = True
        _, status = os.waitpid(pid, 0)
        os.close(fd)
        sminos.forget_caches()
        return os.waitstatus_to_exitcode(status), out.decode("utf-8", "replace").replace("\r\n", "\n"), sent

    def alone(self, *argv, cwd=None):
        """The CLI with no controlling terminal (a new session: /dev/tty opens nothing)."""
        p = subprocess.run([sys.executable, "-B", os.path.join(SCRIPTS, "sminos.py"), *argv], cwd=cwd or self.root,
                           env=self.env(), capture_output=True, text=True, timeout=60, start_new_session=True)
        sminos.forget_caches()
        return p.returncode, p.stdout + p.stderr

    # -- the channel's log

    def leads(self, cid=DESK):
        """The channel-lead events of the channel's log, in its order."""
        sminos.forget_caches()
        return [e for e in sminos.log_read(self.chan(cid)) if e["kind"] == "channel-lead"]

    def lead_event(self, tid, sid, writer=None, **more):
        """A channel-lead written as the verb writes one, or under another writer (as an import leaves one)."""
        fields = {"thread": tid, **({"session": sid} if tid else {}), **more}
        time.sleep(0.002)   # the merged log's order is by time
        e = sminos.log_append(self.chan(DESK), writer or sminos.writer_id(), "channel-lead", **fields)
        sminos.forget_caches()
        return e

    def lead_now(self):
        """The alias of the lead in effect here, or None."""
        sminos.forget_caches()
        got = channels.lead_of(self.chan(DESK))
        return None if got is None else got[1].alias

    def heard(self, sid):
        """The endpoint's audience for the session at its record's policyRev, as the uplink keeps it."""
        rec = records.read(sid)
        members = list(rec["owners"]) + [x["member"] for x in rec.get("shares") or []]
        self.assertTrue(self.au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(
            sid, rec["owners"], members, rec.get("policyRev", 0))}))

    def far(self, alias, machine=FAR, state="idle"):
        """Another machine's thread, a member of `app` and of the channel by its own writer's events there, as an
        import leaves them: (thread, session)."""
        sid, tid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        w = "%s/%s" % (machine, sid)
        sminos.log_append(self.app, w, "joined", session=sid, alias=alias, name_source="user", machine=machine,
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive", thread=tid,
                          owners=["m-far"])
        sminos.log_append(self.app, w, "state", session=sid, state=state, machine=machine)
        sminos.log_append(self.app, w, "channels", session=sid, thread=tid, op=os.urandom(8).hex(), channels=[DESK])
        sminos.forget_caches()
        return tid, sid


# ------------------------------------------------------------ the verb


class Verb(Lead):
    def refused(self, got, want, exit_code, before):
        code, out = got[0], got[1]
        self.assertEqual(code, exit_code, out)
        self.assertIn(want, out)
        self.assertEqual(self.logs(), before, "no log changed")

    def test_inside_a_session_it_is_refused_before_anything_is_read(self):
        rtid, rsid, _ = self.live("reader")
        before = self.logs()
        with mock.patch.object(channels, "find_channel", side_effect=AssertionError("read")):
            self.refused(self.as_session(rsid, "channel", "lead", "desk", "reader"), channels.LEAD_IN_SESSION, 1,
                         before)
        self.assertIn("channel lead is for a person at a terminal, and this runs inside a session: nothing was "
                      "written. Report it to your human instead", channels.LEAD_IN_SESSION)

    def test_with_no_terminal_it_is_refused(self):
        self.live("reader")
        before = self.logs()
        self.refused(self.alone("channel", "lead", "desk", "reader"),
                     "naming a channel's lead needs its owner at a terminal to confirm it, and this has none: nothing "
                     "was written", 1, before)

    def test_a_typed_yes_writes_the_lead_plain_under_the_machines_human_writer(self):
        rtid, rsid, _ = self.live("reader")
        code, out, asked = self.tty("y", "channel", "lead", "desk", "reader")
        self.assertEqual(code, 0, out)
        label = "reader#%s" % rsid[:8]
        self.assertIn("Make %s the lead of desk? A message you type into desk with no tag, on this machine, is then "
                      "addressed to it. Confirm? [y/N] " % label, out)
        self.assertIn("%s leads desk" % label, out)
        self.assertNotIn("(on ", out)
        self.assertNotIn("(private", out)
        [e] = self.leads()
        self.assertEqual((e["writer"], e["thread"], e["session"]), (sminos.writer_id(), rtid, rsid))
        self.assertNotIn("to", e)
        self.assertIsNone(wire._event_breach(DESK, e, {}, wire.ALLOWED_SPOKEN, "written"))
        self.assertEqual(self.lead_now(), "reader")

    def test_not_confirmed_nothing_is_written(self):
        self.live("reader")
        before = self.logs()
        code, out, asked = self.tty("n", "channel", "lead", "desk", "reader")
        self.assertTrue(asked)
        self.refused((code, out), "not confirmed: nothing was written", 1, before)

    def test_a_thread_not_in_the_channel_is_refused_and_an_unknown_name_is_exit_4(self):
        self.live("reader")
        otid, osid, _ = self.outsider("faraway")
        before = self.logs()
        code, out, asked = self.tty("y", "channel", "lead", "desk", "faraway#%s" % osid[:8])
        self.refused((code, out), "faraway#%s is not in desk: sminos channel add desk <thread> places it first"
                     % osid[:8], 1, before)
        self.assertFalse(asked, "refused before the prompt")
        code, out, asked = self.tty("y", "channel", "lead", "desk", "nobody")
        self.assertEqual(code, 4, out)
        self.assertFalse(asked)
        self.assertEqual(self.logs(), before)

    def test_a_member_is_named_through_the_channels_roster_from_any_directory(self):
        tid, sid = self.far("faraway")
        code, out, _ = self.tty("y", "channel", "lead", "desk", "faraway", cwd=self.home)
        self.assertEqual(code, 0, out)
        self.assertEqual([(e["thread"], e["session"]) for e in self.leads()], [(tid, sid)])

    def test_without_the_capability_or_where_the_enrollment_does_not_carry_the_channel(self):
        self.live("reader")
        sminos.register_if_absent(sminos.make_project(FOREIGN, "foreign", "", "", {"url": HUB["url"],
                                                                                   "org": "org-2"}))
        sminos.forget_caches()
        before = self.logs()
        self.refused(self.alone("channel", "lead", "foreign", "reader"),
                     "cannot name the lead of foreign: this machine's enrollment does not carry its log", 1, before)
        self.au.keep_capabilities([])
        self.refused(self.alone("channel", "lead", "desk", "reader"), channels.CAPABILITY_REFUSAL, 1, before)

    def test_none_clears_it(self):
        rtid, rsid, _ = self.live("reader")
        self.lead_event(rtid, rsid)
        code, out, asked = self.tty("y", "channel", "lead", "desk", "none")
        self.assertEqual(code, 0, out)
        self.assertIn("Clear the lead of desk? Confirm? [y/N] ", out)
        self.assertIn("desk has no lead", out)
        e = self.leads()[-1]
        self.assertEqual((e["writer"], e["thread"]), (sminos.writer_id(), None))
        self.assertNotIn("session", e)
        self.assertIsNone(self.lead_now())

    def test_a_lead_on_another_machine_is_taken_and_the_command_says_how_a_post_reaches_it(self):
        tid, sid = self.far("faraway")
        code, out, _ = self.tty("y", "channel", "lead", "desk", "faraway")
        self.assertEqual(code, 0, out)
        self.assertIn("faraway#%s leads desk" % sid[:8], out)
        self.assertIn("(on beta: a message you type here reaches it as a peer's, not as its human's words)", out)
        [e] = self.leads()
        self.assertEqual((e["thread"], e["session"]), (tid, sid))

    def private(self, sid):
        records.set_policy(sid, lambda a, shares: ("private", shares))
        self.heard(sid)

    def test_a_private_lead_goes_under_its_audience_after_a_plain_clearing_event(self):
        self.au.keep_capabilities(["channels", "access"])
        rtid, rsid, _ = self.live("reader")
        self.private(rsid)
        code, out, _ = self.tty("y", "channel", "lead", "desk", "reader")
        self.assertEqual(code, 0, out)
        self.assertIn("reader#%s leads desk" % rsid[:8], out)
        self.assertIn("(private: only machines that may read it see that it leads)", out)
        clearing, named = self.leads()
        self.assertEqual((clearing["writer"], clearing["thread"]), (sminos.writer_id(), None), "plain, first")
        self.assertNotIn("session", clearing)
        self.assertTrue(sminos.is_stream(named["writer"]), "under the thread's audience")
        self.assertEqual(sminos.writer_base(named["writer"]), sminos.writer_id())
        self.assertEqual((named["thread"], named["session"]), (rtid, rsid))
        self.assertEqual(self.lead_now(), "reader", "this machine reads what it wrote")
        for e in (clearing, named):
            self.assertIsNone(wire._event_breach(DESK, e, {}, wire.ALLOWED_SPOKEN, "written"))
        self.assertEqual(self.reader_without(named["writer"]), None, "a reader outside its audience reads no lead")
        events = self.uploaded()
        self.assertEqual([(e["writer"], e["thread"]) for e in events],
                         [(sminos.writer_id(), None), (named["writer"], rtid)], "the raw upload")
        self.assertEqual(events[1]["session"], rsid)

    def test_a_private_lead_of_another_machine_whose_audience_this_endpoint_holds(self):
        self.au.keep_capabilities(["channels", "access"])
        tid, sid = self.far("faraway")
        self.assertTrue(self.au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(
            sid, ["m-far"], ["m-far"], 1)}))
        code, out, _ = self.tty("y", "channel", "lead", "desk", "faraway")
        self.assertEqual(code, 0, out)
        self.assertIn("(on beta: ", out)
        self.assertIn("(private: ", out)
        clearing, named = self.leads()
        self.assertEqual(clearing["thread"], None)
        self.assertTrue(sminos.is_stream(named["writer"]))
        self.assertEqual((named["thread"], named["session"]), (tid, sid))
        self.assertIsNone(self.reader_without(named["writer"]))

    def test_a_private_thread_whose_audience_is_not_known_here_is_refused_in_the_choices_words(self):
        self.au.keep_capabilities(["channels", "access"])
        rtid, rsid, _ = self.live("reader")
        records.set_policy(rsid, lambda a, shares: ("private", shares))   # its audience at this policyRev not heard
        before = self.logs()
        code, out, asked = self.tty("y", "channel", "lead", "desk", "reader")
        self.refused((code, out), "the lead reader#%s" % rsid[:8], 1, before)
        self.assertFalse(asked)

    def reader_without(self, writer):
        """lead_of over a copy of this machine's store whose channel's log lacks the stream writer's file: what a
        machine outside that audience holds (the hub never sends it the stream). The alias it reads, or None."""
        copy = os.path.join(self.home, "reader-copy")
        shutil.copytree(os.environ["SMINOS_HOME"], copy, symlinks=True)
        os.unlink(sminos.writer_path(self.chan(DESK), writer).replace(os.environ["SMINOS_HOME"], copy, 1))
        with mock.patch.dict(os.environ, {"SMINOS_HOME": copy}):
            sminos.forget_caches()
            got = channels.lead_of(self.chan(DESK))
        sminos.forget_caches()
        return None if got is None else got[1].alias

    def uploaded(self):
        """The channel-lead events a Link uploads under the channel's id."""
        link = uplink.Link(dict(CRED, machine=sminos.host_name()), {}, transport=mock.Mock(number=1))
        self.addCleanup(link.close)
        link.generation = 1
        link.log_lane = link.session_lane = Lane()
        link.serves_channels = True
        hl = link.logs[DESK] = hublog.HubLog(self.chan(DESK), link.cred)
        link.opened.add(DESK)
        link.channels.add(DESK)
        hl.on_have({"t": "have", "project": DESK, "have": {}})
        sminos.forget_caches()
        link.upload(hl)
        return [e for f in link.log_lane.sent if f.get("t") == "events" and f.get("project") == DESK
                for e in f.get("events") or () if e.get("kind") == "channel-lead"]


# ------------------------------------------------------------ whose lead is in effect


class LeadOf(Lead):
    def test_the_last_honoured_lead_decides_and_each_one_not_honoured_is_skipped(self):
        atid, asid, _ = self.live("alder")
        btid, bsid, _ = self.live("birch")
        self.assertIsNone(self.lead_now(), "none by default")
        self.lead_event(atid, asid)
        self.assertEqual(self.lead_now(), "alder")
        for writer, more, why in ((sminos.writer_id(bsid), {}, "a session's writer"),
                                  ("hub/m-owner", {}, "a phone's writer"),
                                  (sminos.writer_id(), {"notice": "devcloud"}, "a notice"),
                                  ("legacy/human", {}, "no machine's writer"),
                                  (sminos.writer_id(), {"to": [{"session": bsid, "alias": "birch", "thread": btid}]},
                                   "one that carries to")):
            self.lead_event(btid, bsid, writer=writer, **more)
            self.assertEqual(self.lead_now(), "alder", why)
        self.lead_event(btid, None, writer=sminos.writer_id())   # a thread with no session: no lead event
        self.assertEqual(self.lead_now(), "alder")
        e = sminos.log_append(self.chan(DESK), sminos.writer_id(), "channel-lead", session=bsid)
        self.assertFalse(channels.is_lead(e), "no thread at all: no lead event, and no clearing one")
        self.assertEqual(self.lead_now(), "alder")

    def test_two_machines_human_writers_the_later_by_merge_order_holds(self):
        atid, asid, _ = self.live("alder")
        btid, bsid, _ = self.live("birch")
        self.lead_event(atid, asid)
        self.lead_event(btid, bsid, writer="%s/human" % FAR)
        self.assertEqual(self.lead_now(), "birch", "another machine's human writer, later")
        self.lead_event(atid, asid)
        self.assertEqual(self.lead_now(), "alder")
        self.lead_event(None, None, writer="%s/human~%s" % (FAR, "0" * 16))
        self.assertIsNone(self.lead_now(), "a clearing event under a stream of a machine's human writer")

    def test_a_lead_not_in_effect_leaves_no_lead_and_an_earlier_lead_never_comes_back(self):
        atid, asid, _ = self.live("alder")
        btid, bsid, _ = self.live("birch")
        self.lead_event(atid, asid)
        self.lead_event(btid, bsid)
        self.removed(btid, bsid)
        self.assertIsNone(self.lead_now(), "birch left: no lead, and not alder")

    def post(self, text):
        code, out = self.at_terminal("say", "--in", "desk", text)
        self.assertEqual(code, 0, out)
        return self.says()[-1]["to"]

    def test_the_lead_removed_ended_and_returned(self):
        """The seam with the roster (M1): a lead is in effect while its thread has a row there."""
        sid, proc = self.session(name="leader")
        received = self.inbox(sid, proc, "l")
        self.reconcile()
        tid = threads.stamp(sid)
        self.add(tid, sid, DESK)
        self.lead_event(tid, sid)
        self.assertEqual([r["thread"] for r in self.post("one")], [tid], "addressed")
        self.removed(tid, sid)
        self.assertEqual(self.post("two"), "*", "removed: untagged")
        self.add(tid, sid, DESK)
        self.assertEqual([r["thread"] for r in self.post("three")], [tid], "back in it: addressed again")
        self.ended_by_its_process(sid, proc)
        self.assertTrue(threads.record_ended(threads.get(tid)), "ended")
        self.assertEqual(self.post("four"), "*", "ended: untagged")
        _, proc = self.session(sid=sid, name="leader")
        self.reconcile()
        self.assertFalse(threads.record_ended(threads.get(tid)), "returned")
        self.assertEqual([r["thread"] for r in self.post("five")], [tid], "returned: addressed again")
        del received


# ------------------------------------------------------------ the post


class Post(Lead):
    def link(self, reach=False):
        link = uplink.Link(dict(CRED, machine=sminos.host_name()), {}, transport=mock.Mock(number=1))
        self.addCleanup(link.close)
        link.generation = 1
        link.log_lane = link.session_lane = Lane()
        link.reach, link.serves_channels = reach, True
        link.logs[DESK] = hublog.HubLog(self.chan(DESK), link.cred)
        link.opened.add(DESK)
        link.channels.add(DESK)
        return link

    def ask_pass(self, link):
        sminos.forget_caches()
        link.next_member_read = 0.0
        link.members(time.monotonic())
        sminos.forget_caches()
        link.ask_words({})

    def asks(self, link, t=("words?", "reach?")):
        return [f for f in link.session_lane.sent if f.get("t") in t and f.get("project") == DESK]

    def answer(self, link, ask, verdict):
        sminos.forget_caches()
        link.dispatch({"t": "words" if ask["t"] == "words?" else "reach", "id": ask["id"], "verdict": verdict}, None)

    def carry(self):
        sminos.forget_caches()
        got = channels.carry_words(self.chan(DESK))
        sminos.forget_caches()
        channels.deliver(self.chan(DESK))
        return got

    def worded(self, link, verdict, text):
        """The endpoint's word on the post carrying `text`: the one ask about it answered `verdict` (and, where
        that asks the endpoint about reach next, `deliver`), then the daemon's channel pass."""
        self.ask_pass(link)
        asked = [f for f in self.asks(link) if text in str((f.get("event") or {}).get("text"))]
        self.assertEqual([f["t"] for f in asked], ["words?"], "a words? under the channel's id")
        self.answer(link, asked[0], verdict)
        self.ask_pass(link)
        more = [f for f in self.asks(link, ("reach?",)) if text in str((f.get("event") or {}).get("text"))]
        for f in more:
            self.answer(link, f, "deliver")
        return self.carry()

    def bridge(self):
        """Every key the bridge was handed (control.deliver's posts), each submitted."""
        control = sminos.control_module()
        keys = []

        def post_command(path, body, *a):
            keys.append(body["key"])
            return 200, {"ok": True, "result": {"submitted": True}}
        p = mock.patch.object(control, "post_command", post_command)
        p.start()
        self.addCleanup(p.stop)
        return keys

    def no_word_to_a_human(self, tid, sid):
        """B7: no message, question or answered under the channel, and none in the lead's project naming it."""
        sminos.forget_caches()
        kinds = {e["kind"] for e in sminos.log_read(self.chan(DESK))}
        self.assertEqual(kinds & {"message", "question", "answered"}, set())
        home = sminos.last_project(sid)
        for e in sminos.log_read(home) + sminos.host_read(home):
            if e["kind"] in ("message", "question", "answered"):
                self.assertNotIn(DESK, json.dumps(e))
        self.assertFalse(glob.glob(os.path.join(self.chan(DESK).home, "host", "*.jsonl")))

    def test_an_untagged_post_from_a_terminal_is_addressed_to_the_lead(self):
        rtid, rsid, _ = self.live("reader")
        self.live("other")
        self.lead_event(rtid, rsid)
        code, out = self.at_terminal("say", "--in", "desk", "do it")
        self.assertEqual(code, 0, out)
        [e] = self.says()
        self.assertEqual((e["kind"], e["writer"]), ("human", sminos.writer_id()))
        self.assertEqual(e["to"], [{"session": rsid, "alias": "reader", "thread": rtid}])
        self.assertNotIn("wake", e)
        self.assertEqual(self.line_for(out, "reader"), [sminos.WORDS_RECORDED], "left for the endpoint's word")

    def test_a_sessions_post_a_notice_and_a_tagged_post_are_not_the_leads(self):
        rtid, rsid, _ = self.live("reader")
        otid, osid, _ = self.live("other")
        self.lead_event(rtid, rsid)
        self.as_session(osid, "say", "--in", "desk", "a session's note")
        self.assertEqual(self.says()[-1]["to"], "*", "a session's untagged post is untagged")
        code, out = self.at_terminal("say", "--notice", "devcloud", "--in", "desk", "lease ends")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.says()[-1]["to"], "*", "a machine's notice with no tag stays untagged")
        self.at_terminal("say", "--in", "desk", "@other for other")
        self.assertEqual([r["thread"] for r in self.says()[-1]["to"]], [otid], "a tagged post names whom it tags")

    def test_on_the_leads_machine_the_endpoints_words_hand_it_to_the_bridge_keyed_by_the_channel(self):
        rtid, rsid, received = self.live("reader")
        self.lead_event(rtid, rsid)
        keys = self.bridge()
        self.at_terminal("say", "--in", "desk", "do it")
        [e] = self.says()
        self.assertEqual(self.worded(self.link(), "words", "do it"), 1)
        self.assertEqual(keys, [{"project": "%s#%s" % (DESK, rtid), "writer": e["writer"], "seq": e["seq"]}],
                         "the bridge's deliver, keyed by the channel and the thread")
        self.assertEqual(self.received(received), [], "never a peer's inbox frame")
        self.no_word_to_a_human(rtid, rsid)

    def test_where_no_bridge_takes_it_the_supervisors_reply_does(self):
        rtid, rsid, received = self.live("reader")
        self.lead_event(rtid, rsid)
        control = sminos.control_module()
        supervised = []
        with mock.patch.object(control, "post_command", return_value=None), \
                mock.patch.object(control, "bg_job", return_value="abcd1234"), \
                mock.patch.object(control, "supervisor_reply",
                                  side_effect=lambda short, text, session: supervised.append(text) or True):
            self.at_terminal("say", "--in", "desk", "do it")
            self.worded(self.link(), "words", "do it")
        self.assertEqual(len(supervised), 1)
        self.assertIn("do it", supervised[0])
        self.assertEqual(self.received(received), [])

    def test_a_peer_word_hands_it_over_as_a_peers_frame_from_human(self):
        rtid, rsid, received = self.live("reader")
        self.lead_event(rtid, rsid)
        keys = self.bridge()
        self.at_terminal("say", "--in", "desk", "do it")
        self.worded(self.link(), "peer", "do it")
        [frame] = self.got(received, "do it")
        self.assertIn("from human", frame)
        self.assertNotIn("To reply", frame, "a person's message has no reply line")
        self.assertEqual(keys, [], "the bridge handed nothing")
        self.no_word_to_a_human(rtid, rsid)

    def test_a_stopped_lead_is_woken_by_the_post(self):
        tid, sid = self.stopped()
        self.lead_event(tid, sid)
        self.at_terminal("say", "--in", "desk", "wake and do it")
        self.assertEqual([r["thread"] for r in self.says()[-1]["to"]], [tid])
        self.worded(self.link(), "words", "wake and do it")
        self.assertEqual(self.launches(), 1, "woken")
        self.assertTrue(wait_for(lambda: self.woken_got(sid, "wake and do it")), "and handed the post")

    def test_a_notice_tagged_to_the_lead_is_a_machines_notice_whatever_the_word(self):
        for verdict in ("words", "peer"):
            with self.subTest(verdict=verdict):
                rtid, rsid, received = self.live("reader-" + verdict)
                self.lead_event(rtid, rsid)
                keys = self.bridge()
                code, out = self.at_terminal("say", "--notice", "devcloud", "--in", "desk",
                                             "@reader-%s lease ends (%s)" % (verdict, verdict))
                self.assertEqual(code, 0, out)
                self.worded(self.link(), verdict, "lease ends (%s)" % verdict)
                [frame] = self.got(received, "lease ends (%s)" % verdict)
                self.assertIn("from devcloud@%s" % sminos.host_name(), frame)
                self.assertNotIn("To reply", frame, "no reply line")
                self.assertEqual(keys, [], "the bridge handed nothing")
                sminos.forget_caches()
                owner = manager_window.OwnerWords(sminos.log_read(self.chan(DESK)), [rsid])
                self.assertFalse(owner.corroborates(frame), "the manager's classifier does not mark it the owner's")


# ------------------------------------------------------------ channel show


class Show(Lead):
    def test_show_prints_the_lead_only_while_one_is_in_effect(self):
        rtid, rsid, _ = self.live("reader")
        code, out = self.at_terminal("channel", "show", "desk")
        self.assertNotIn("lead ", out)
        code, out = self.at_terminal("channel", "show", "desk", "--json")
        self.assertNotIn("lead", json.loads(out))
        self.lead_event(rtid, rsid)
        code, out = self.at_terminal("channel", "show", "desk")
        lines = out.splitlines()
        self.assertEqual(lines[0], "# desk  %s" % DESK)
        self.assertEqual(lines[1], "lead  reader#%s" % rsid[:8], "after its heading")
        code, out = self.at_terminal("channel", "show", "desk", "--json")
        self.assertEqual(json.loads(out)["lead"], rtid)
        self.removed(rtid, rsid)
        code, out = self.at_terminal("channel", "show", "desk", "--json")
        self.assertNotIn("lead", json.loads(out), "a lead not in effect is none")


if __name__ == "__main__":
    unittest.main()
