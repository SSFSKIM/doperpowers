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
  log, which reads no lead; `none` clears it. Also: refused inside a
  session before any migration; a torn row refused before the prompt; a
  removal, an end or a hand-off while the prompt is read refused, nothing
  written; a private lead not written behind a reset that waits for its
  head.
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
  under the channel or in the lead's project is a word to a human (B7);
  another machine's verified post to the lead here arrives on `peer` as a
  peer's frame.
- `channel show` and its `--json` with and without a lead (`Show`).
- The pty driver (`Driver`, pty_answer.py): killed and reaped at its
  deadline.

Hermetic: test_channels_say's Say (test_wake's Engine, HOME, SMINOS_HOME and
the engine's state temporary; the engine first on PATH); the typed yes on a
controlling pty of the CLI's own (pty_answer.py, the driver the shell
suites share), as test_visibility drives `confirmed`; the uplink a Link over the store whose lanes keep what they are
sent, as test_channels_wire's Messages drives one.
Run: python3 -B sminos/tests/test_channels_lead.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import glob
import json
import os
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
import pty_answer  # noqa: E402
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

    def tty(self, answer, *argv, cwd=None, meanwhile=None):
        """The CLI on a controlling pty of its own, a person typing `answer` at its prompt (none typed when no
        prompt comes; `meanwhile()` run while the prompt is shown): (exit code, what it printed, whether it
        prompted). A child that does not end in time is killed, its code None."""
        got = pty_answer.run([sys.executable, "-B", os.path.join(SCRIPTS, "sminos.py"), *argv], answer,
                             cwd=cwd or self.root, env=self.env(), meanwhile=meanwhile)
        sminos.forget_caches()
        return got

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

    def test_inside_a_session_it_is_refused_before_any_migration(self):
        """Review round 1: the refusal comes in the launcher's dispatch, before migrate (which can wait on a lock
        and rewrite records)."""
        rtid, rsid, _ = self.live("reader")
        with mock.patch.object(sminos, "migrate", side_effect=AssertionError("migrated")):
            code, out = self.as_session(rsid, "channel", "lead", "desk", "reader")
        self.assertEqual(code, 1, out)
        self.assertIn(channels.LEAD_IN_SESSION, out)

    def test_a_private_lead_is_refused_before_anything_is_queued_where_the_plain_writer_waits_for_its_head(self):
        """Review rounds 1 and 2: a writer waits for its head on its own (sminos.waits_for_head is per writer), so
        the private event never goes behind a reset still queued; and the refusal queues nothing either (a reset
        left queued would clear the earlier lead once released, with no `none` run). The earlier lead survives
        the queue's release."""
        self.au.keep_capabilities(["channels", "access"])
        atid, asid, _ = self.live("alder")
        self.lead_event(atid, asid)
        rtid, rsid, _ = self.live("reader")
        self.private(rsid)
        plain = sminos.writer_id()
        # A new enrolment, whose first `have` named a head upstream for the plain writer and none for the stream:
        # the plain writer waits for its head, the stream does not.
        sminos.mark_enrolled(sminos.host_name(), "2026-11-10T00:00:00.000Z")
        sminos.keep_headed(self.chan(DESK), [plain])
        sminos.forget_caches()
        self.assertTrue(sminos.waits_for_head(self.chan(DESK), plain))
        before = self.logs()
        code, out, asked = self.tty("y", "channel", "lead", "desk", "reader")
        self.assertEqual(code, 1, out)
        self.assertIn("this machine's writer waits for its head", out)
        self.assertNotIn("leads desk", out)
        self.assertEqual(self.logs(), before, "nothing in the log")
        self.assertEqual(glob.glob(os.path.join(self.chan(DESK).home, sminos.QUEUED, "*.jsonl")), [], "nor queued")
        sminos.release_queued(self.chan(DESK), plain)
        self.assertEqual(self.lead_now(), "alder", "the earlier lead survives the queue's release")

    def confirmed_in_process(self):
        """The person's yes, given in this process (the cases below stage what happens between two reads inside
        one append, which only an in-process call can reach; the yes itself is driven on a pty above)."""
        p = mock.patch.object(sminos.sibling_module("sminos_visibility"), "confirmed", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def test_a_head_wait_that_begins_between_a_check_and_the_append_never_queues_the_reset(self):
        """Review round 3: whether the private lead's reset may go is one decision, at _append's own head check
        under the writer's lock (queue=False), never a guard's read followed by a second one: a welcome that marks
        a new enrolment holds no writer lock, so the answer can change between two reads. Here it changes right
        after the first read of waits_for_head, and the reset is still never queued."""
        self.au.keep_capabilities(["channels", "access"])
        rtid, rsid, _ = self.live("reader")
        self.private(rsid)
        self.confirmed_in_process()
        plain, real, calls = sminos.writer_id(), sminos.waits_for_head, []

        def waits_for_head(project, writer):
            got = real(project, writer)
            if writer == plain and not calls:
                calls.append(got)
                # A same-name re-enrollment's welcome, between this read and any later one: the plain writer now
                # waits for its head.
                sminos.mark_enrolled(sminos.host_name(), "2026-11-10T00:00:00.000Z")
                sminos.keep_headed(self.chan(DESK), [plain])
            return got
        with mock.patch.object(sminos, "waits_for_head", waits_for_head):
            code, out = self.at_terminal("channel", "lead", "desk", "reader")
        self.assertEqual(calls, [False], "the head was ready at the one read that decided")
        self.assertEqual(glob.glob(os.path.join(self.chan(DESK).home, sminos.QUEUED, "*.jsonl")), [],
                         "the reset never entered the queue")
        self.assertEqual(code, 0, out)
        self.assertEqual([e["thread"] for e in self.leads()], [None, rtid], "the reset landed, then the lead")

    def test_a_rename_between_the_reset_and_the_private_lead_says_both_facts(self):
        """Review round 3: a rename after the private lead's reset landed says what is true: the reset was written,
        the private lead was not, and why."""
        self.au.keep_capabilities(["channels", "access"])
        rtid, rsid, _ = self.live("reader")
        self.private(rsid)
        self.confirmed_in_process()
        rl10 = sminos.sibling_module("sminos_rl10")
        host, real = sminos.host_name(), sminos._append

        def append(project, writer, events, **kw):
            got = real(project, writer, events, **kw)
            if events and events[0].get("kind") == "channel-lead" and events[0].get("thread") is None:
                with open(rl10.identity_path()) as f:
                    ident = json.load(f)
                ident["name"] = "renamed-host"
                sminos.write_json(rl10.identity_path(), ident, mode=0o600)
            return got
        with mock.patch.object(sminos, "_append", append):
            code, out = self.at_terminal("channel", "lead", "desk", "reader")
        self.assertEqual(code, 1, out)
        self.assertIn("its clearing event was written (desk has no lead now); the private lead was not, because this "
                      "machine's name changed (%s, now renamed-host)" % host, out)
        self.assertNotIn("nothing was written", out)

    def test_a_rename_while_the_prompt_is_read_writes_nothing(self):
        """Review round 2: both writers come from the machine's name as its files say after the answer; a rename
        meanwhile refuses, with nothing written under the old name or the new."""
        rtid, rsid, _ = self.live("reader")
        rl10 = sminos.sibling_module("sminos_rl10")

        def renamed():
            with open(rl10.identity_path()) as f:
                ident = json.load(f)
            ident["name"] = "renamed-host"
            sminos.write_json(rl10.identity_path(), ident, mode=0o600)
        before = self.logs()
        code, out, asked = self.tty("y", "channel", "lead", "desk", "reader", meanwhile=renamed)
        self.assertTrue(asked)
        self.assertEqual(code, 1, out)
        self.assertIn("this machine's name changed while you answered", out)
        self.assertEqual(self.logs(), before)
        self.assertEqual(glob.glob(os.path.join(self.chan(DESK).home, sminos.QUEUED, "*.jsonl")), [])

    def test_a_thread_that_leaves_or_ends_while_the_prompt_is_read_is_not_named(self):
        """Review round 1: after the answer the chosen thread is read again by its id, its row and its current
        session; a change refuses, asking for a run again, and the alias is not resolved again."""
        rtid, rsid, _ = self.live("reader")
        before = self.logs()
        code, out, asked = self.tty("y", "channel", "lead", "desk", "reader",
                                    meanwhile=lambda: self.removed(rtid, rsid))
        self.assertTrue(asked)
        self.assertEqual(code, 1, out)
        self.assertIn("reader#%s changed while you answered" % rsid[:8], out)
        self.assertNotIn("leads desk", out)
        self.assertEqual(self.leads(), [])
        del before

    def test_a_hand_off_while_the_prompt_is_read_is_not_named_under_the_old_session(self):
        tid, old, oproc, _ = self.live_member("reader")

        def hand_off():
            job, jproc = T1.Sessions.job(self, old)
            self.inbox(job, jproc, "j")
            self.reconcile()
            self.end(oproc)
            self.reconcile()
        code, out, asked = self.tty("y", "channel", "lead", "desk", "reader", meanwhile=hand_off)
        self.assertTrue(asked)
        self.assertEqual(code, 1, out)
        self.assertIn("changed while you answered", out)
        self.assertEqual(self.leads(), [], "no event under the predecessor's session")

    def test_a_torn_row_is_refused_before_the_prompt(self):
        """Review round 1: a row whose stamp and statement name two threads is addressed as no thread
        (thread_of_row None), as M4 refuses it for a tag."""
        torn_sid = str(uuidlib.uuid4())
        w = "%s/%s" % (FAR, torn_sid)
        sminos.log_append(self.app, w, "joined", session=torn_sid, alias="torn", name_source="user", machine=FAR,
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive",
                          thread=str(uuidlib.uuid4()))
        sminos.log_append(self.app, w, "state", session=torn_sid, state="idle", machine=FAR)
        sminos.log_append(self.app, w, "channels", session=torn_sid, thread=str(uuidlib.uuid4()),
                          op=os.urandom(8).hex(), channels=[DESK])
        sminos.forget_caches()
        before = self.logs()
        code, out, asked = self.tty("y", "channel", "lead", "desk", "torn")
        self.assertFalse(asked, "refused before the prompt")
        self.refused((code, out), "torn#%s: its membership of desk names two threads" % torn_sid[:8], 4, before)

    def test_f5_a_target_that_turns_private_while_the_writer_waits_gets_no_plain_lead(self):
        """Frontier F5: the stream is chosen before _append takes the writer's locks; the choice is read again under
        them, so a target that turned private meanwhile gets no identifying lead on the plain writer."""
        self.au.keep_capabilities(["channels", "access"])
        rtid, rsid, _ = self.live("reader")
        self.confirmed_in_process()
        real = sminos._append

        def append(project, writer, events, **kw):
            if events and events[0].get("kind") == "channel-lead" and events[0].get("thread"):
                self.private(rsid)   # while the writer's lock was waited for
            return real(project, writer, events, **kw)
        before = self.logs()
        with mock.patch.object(sminos, "_append", append):
            code, out = self.at_terminal("channel", "lead", "desk", "reader")
        self.assertEqual(code, 1, out)
        self.assertIn("reader#%s's audience changed while its lead was written: nothing was written. Run it again"
                      % rsid[:8], out)
        self.assertEqual({k: v for k, v in self.logs().items() if v}, before,
                         "no lead on the plain writer (whose file the append's open may create, empty)")
        self.assertEqual(glob.glob(os.path.join(self.chan(DESK).home, sminos.QUEUED, "*.jsonl")), [], "nor queued")

    def test_f5_a_private_target_whose_audience_changes_after_the_reset_says_both_facts(self):
        self.au.keep_capabilities(["channels", "access"])
        rtid, rsid, _ = self.live("reader")
        self.private(rsid)
        self.confirmed_in_process()
        real = sminos._append

        def append(project, writer, events, **kw):
            if events and events[0].get("kind") == "channel-lead" and events[0].get("thread"):
                records.set_policy(rsid, lambda a, shares: ("listed", shares))
            return real(project, writer, events, **kw)
        with mock.patch.object(sminos, "_append", append):
            code, out = self.at_terminal("channel", "lead", "desk", "reader")
        self.assertEqual(code, 1, out)
        self.assertIn("its clearing event was written (desk has no lead now); the private lead was not, because "
                      "reader#%s's audience changed while it was written" % rsid[:8], out)
        self.assertEqual([e["thread"] for e in self.leads()], [None], "the reset alone")

    def test_f23_an_id_shaped_alias_is_named_through_the_channel_from_another_project(self):
        """Frontier F23: an alias in id form that no thread's or session's id begins with is looked up as an alias in
        the channel (M1's fallback), as a tag in it is."""
        tid, sid = self.far("deadbeef")
        code, out, _ = self.tty("y", "channel", "lead", "desk", "deadbeef")
        self.assertEqual(code, 0, out)
        self.assertEqual([(e["thread"], e["session"]) for e in self.leads()], [(tid, sid)])

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
        self.assertEqual(self.lead_now(), "alder", "a clearing event is plain: one under a stream clears nothing")
        self.lead_event(None, None, writer="%s/human" % FAR)
        self.assertIsNone(self.lead_now(), "a plain one does")

    def test_a_lead_not_in_effect_leaves_no_lead_and_an_earlier_lead_never_comes_back(self):
        atid, asid, _ = self.live("alder")
        btid, bsid, _ = self.live("birch")
        self.lead_event(atid, asid)
        self.lead_event(btid, bsid)
        self.removed(btid, bsid)
        self.assertIsNone(self.lead_now(), "birch left: no lead, and not alder")

    def test_f24_a_lead_history_with_a_file_that_cannot_be_read_gives_no_lead(self):
        """Frontier F24: the latest lead may be in a writer's file that cannot be read; the one a readable file names
        is then not the lead in effect. An incomplete read gives no lead."""
        atid, asid, _ = self.live("alder")
        btid, bsid, _ = self.live("birch")
        self.lead_event(atid, asid)
        self.lead_event(btid, bsid, writer="%s/human" % FAR)
        self.assertEqual(self.lead_now(), "birch")
        path = sminos.writer_path(self.chan(DESK), "%s/human" % FAR)
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o600)
        sminos._LOG_FILES.clear()   # a process of its own: no file's events held from before (a chmod moves no key)
        self.assertIsNone(self.lead_now(), "not alder: the read is incomplete")
        os.chmod(path, 0o600)
        self.assertEqual(self.lead_now(), "birch", "read again whole once the file reads")

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

    def test_another_machines_verified_post_to_the_lead_here_arrives_on_peer_as_a_peers_frame(self):
        """Review round 1: the remote writer's seam. The post was written at a terminal of another machine whose
        lead this thread is: here it is an import, verified, with no receipt, and the endpoint's word for another
        machine's human writer is `peer`."""
        rtid, rsid, received = self.live("reader")
        keys = self.bridge()
        time.sleep(0.002)
        e = sminos.log_append(self.chan(DESK), "%s/human" % FAR, "human", **{
            "from": "human", "to": [{"session": rsid, "alias": "reader", "thread": rtid}], "text": "from beta's owner",
            "verified": {"signer": {"kind": "machine", "keyId": "key-beta"}}})
        sminos.forget_caches()
        self.assertFalse(channels.appended_here(self.chan(DESK), e), "an import, no receipt here")
        self.worded(self.link(), "peer", "from beta's owner")
        [frame] = self.got(received, "from beta's owner")
        self.assertIn("from human", frame)
        self.assertNotIn("To reply", frame)
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
                owner = manager_window.OwnerWords([("desk", DESK, sminos.log_read(self.chan(DESK)))], [rsid])
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



# ------------------------------------------------------------ the pty driver


class Driver(unittest.TestCase):
    def test_a_command_that_never_prompts_or_never_ends_is_killed_and_reaped_at_the_deadline(self):
        """Review round 1: a prompt regression fails its test instead of hanging the gate."""
        for argv in (["sleep", "30"], [sys.executable, "-c", "import time; print('[y/N] '); time.sleep(30)"]):
            with self.subTest(argv=argv[0]):
                at = time.monotonic()
                code, out, _ = pty_answer.run(argv, "y", deadline=1)
                self.assertIsNone(code)
                self.assertLess(time.monotonic() - at, 10)
        def boom():
            raise RuntimeError("meanwhile failed")
        with self.assertRaises(RuntimeError):
            pty_answer.run([sys.executable, "-c", "print('[y/N] '); import time; time.sleep(30)"], "y",
                           meanwhile=boom)
        with self.assertRaises(ChildProcessError, msg="the child killed and reaped when meanwhile raises"):
            os.waitpid(pty_answer.LAST_PID, os.WNOHANG)
        code, out, prompted = pty_answer.run([sys.executable, "-c", "print(input('Go? [y/N] '))"], "y")
        self.assertEqual((code, prompted), (0, True))
        self.assertIn("Go? [y/N] y", out)


if __name__ == "__main__":
    unittest.main()
