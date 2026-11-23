#!/usr/bin/env python3
"""Saying into a channel (CH2's M4:
docs/doperpowers/plans/2026-11-22-sminos-channels-ch2.md, the milestone's
"Seams" and "Proves"; Interfaces §2 and §6's `chat`), on one machine cut
over to an endpoint that is never run and whose welcome listed `channels`
and not `reach`:

- The doors: `say --in <channel>` and `@<channel>/<alias>`, by a member
  (`Member`) and by a session that is no member (`Outsider`), each one event
  in the channel's log whose every entry of `to` carries the row's thread,
  delivered at once by the sender's own call (`deliver_say` through
  `owing`), a stopped member woken, one that may not be woken held, a
  sender that races the daemon told what happened; `@all` the live members,
  an untagged post nobody's.
- The reply line run as written: in the channel's log for a member's frame,
  in the sender's project for an outsider's, directly to a member that has
  since left the channel (refused where its project is retired or has
  left this machine, as `@<short>` is), to the session that continues a
  sender handed off, and never to a thread that came to hold the sender's
  old session; once run by a shell exactly as the frame writes it.
- An outsider's copy as record_copy keeps it: in a project whose log is not
  filtered by audience, to a private member, none and its warning; for
  recipients of two audiences, an event and a copy each; one that cannot
  be written, tried after the delivery and changing none of it.
- A torn row: no entry, and its tag cut from the text (`Lines`).
- Each refusal of §2 with nothing appended to any log (`Refused`).
- `chat <channel>`, `list <channel>`, and a person's and a machine's words
  (`Read`, `Words`).
- A store with no channel prints and writes what the merge base's code does
  (B11, `SameAsBase`), its launcher extracted from git.
- No word to a human under a channel's id (B7, CH2's M9, `HostWords`): a
  thread in two channels given a frame by its inbox and a person's words by
  a real bridge child (1.54's and this tree's) under `<channel>#<thread>`,
  then its words to its human, two questions and an answer through that
  bridge, a stop and the sweep: all in the thread's own project, the second
  question closed there, another project's question open, nothing under a
  channel's id or the `#` scope.

Hermetic: test_channels_delivery's Channel (test_wake's Engine, HOME,
SMINOS_HOME and the engine's state temporary; the engine first on PATH),
with daemon/identity.json written as test_channels_requests writes it.
Run: python3 -B sminos/tests/test_channels_say.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

import test_threads as T1  # noqa: E402
import endpoint_standin  # noqa: E402
import bridge_standin  # noqa: E402
from test_channels_delivery import FAR, Channel, reply_of  # noqa: E402
from test_channels_life import DESK, HUB, LOBBY  # noqa: E402
from test_threads import BASE, SCRIPTS, records, sminos, threads  # noqa: E402
from test_wake import wait_for  # noqa: E402
from test_wake_delivery import line as held_line  # noqa: E402
import sminos_channels as channels  # noqa: E402

FOREIGN = "0123abcf-4567-8abc-a123-456789abcdef"   # a channel registered under another org
APP = "7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d"   # a hub project of the org, beside the machine's own


class Say(Channel):
    """A Channel on a machine cut over to its endpoint (identity.json), whose kept welcome lists `channels`; `app`
    a hub project of the org beside the machine's own."""

    def setUp(self):
        super().setUp()
        rl10 = sminos.sibling_module("sminos_rl10")
        os.makedirs(os.path.dirname(rl10.identity_path()), mode=0o700, exist_ok=True)
        sminos.write_json(rl10.identity_path(), {
            "org": HUB["org"], "hub": HUB["url"], "name": sminos.host_name(), "former": {}, "ref": "machine-ref-1",
            "enrolled": "2026-11-10T00:00:00.000Z", "cutover": "2026-11-10T00:00:01.000Z", "build": "b"}, mode=0o600)
        self.au = sminos.audience_module()
        self.au.keep_capabilities(["channels"])
        sminos.forget_caches()
        self.p = self.project_of(self.root)
        self.app_root = os.path.join(self.home, "app")
        os.makedirs(self.app_root)
        with open(os.path.join(self.app_root, ".smns"), "w") as f:
            json.dump({"project": APP, "name": "app", "hub": {"org": HUB["org"]}}, f)
        self.app = self.project_of(self.app_root)

    def as_session(self, sid, *argv, cwd=None):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            return self.cli(*argv, cwd=cwd)

    def at_terminal(self, *argv, cwd=None):
        with mock.patch.dict(os.environ, {}):
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            return self.cli(*argv, cwd=cwd)

    def open_here(self, name, root=None):
        """A live session its human opened in `root` (the machine's project by default), with an inbox, joined:
        (thread, session, its inbox's file)."""
        sid = str(uuidlib.uuid4())
        _, proc = self.session(root=root, sid=sid, kind="interactive", name=name)
        received = self.inbox(sid, proc, name[:3])
        self.reconcile(self.project_of(root) if root else None)
        return threads.stamp(sid), sid, received

    def outsider(self, name="outside"):
        """A live thread its human opened in `app`, with an inbox, in no channel."""
        return self.open_here(name, self.app_root)

    def says(self, cid=DESK):
        """The messages of the channel's log, in its order."""
        sminos.forget_caches()
        return [e for e in sminos.log_read(self.chan(cid)) if e["kind"] in sminos.CHAT_KINDS]

    def project_says(self, p=None):
        """The messages of every project's log here (or of `p`'s): [(project id, event)]."""
        sminos.forget_caches()
        return [(q.id, e) for q in ([p] if p else sminos.known_projects()) for e in sminos.log_read(q)
                if e["kind"] in sminos.CHAT_KINDS]

    def logs(self):
        """Every log file under every log here, with its bytes: what a refusal must leave as it was."""
        out = {}
        for path in glob.glob(os.path.join(os.environ["SMINOS_HOME"], "projects", "*", "log", "*.jsonl")):
            with open(path, "rb") as f:
                out[path] = f.read()
        return out

    def line_for(self, out, alias):
        """deliver_say's lines for a recipient."""
        return [ln.split(": ", 1)[1] for ln in out.splitlines() if ln.startswith(alias + ": ")]

    def reply(self, sid, frame, text):
        """The reply line of `frame`, run as written by the session `sid`, with `text`."""
        tag = reply_of(frame)
        self.assertIsNotNone(tag, frame)
        return self.as_session(sid, "say", "@%s %s" % (tag, text))

    def removed(self, tid, sid):
        self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
        sminos.forget_caches()

    def far(self, alias, tid=None):
        """Another machine's live thread, a member of `app` and of the channel by its own writer's events there, as
        an import leaves them: (thread, session)."""
        sid, tid = str(uuidlib.uuid4()), tid or str(uuidlib.uuid4())
        w = "%s/%s" % (FAR, sid)
        sminos.log_append(self.app, w, "joined", session=sid, alias=alias, name_source="user", machine=FAR,
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive", thread=tid,
                          owners=["m-far"])
        sminos.log_append(self.app, w, "state", session=sid, state="idle", machine=FAR)
        sminos.log_append(self.app, w, "channels", session=sid, thread=tid, op=os.urandom(8).hex(), channels=[DESK])
        sminos.forget_caches()
        return tid, sid


# ------------------------------------------------------------ a member says (B1)


class Member(Say):
    def test_say_in_to_a_live_member_is_one_event_in_the_channel_and_one_frame(self):
        rtid, rsid, received = self.live("reader")
        stid, ssid, sreceived = self.live("writer")
        before = self.project_says()
        code, out = self.as_session(ssid, "say", "--in", "desk", "@reader the schema changed")
        self.assertEqual(code, 0, out)
        [e] = self.says()
        self.assertIn("recorded %s in desk" % sminos.event_ref(e), out)
        self.assertEqual(self.line_for(out, "reader"), ["sent"])
        self.assertEqual(e["kind"], "say")
        self.assertEqual(e["to"], [{"session": rsid, "alias": "reader", "thread": rtid}], "the row's thread")
        self.assertEqual(e["thread"], stid, "its sender's own thread")
        self.assertNotIn("from_project", e)
        self.assertNotIn("copy", e)
        self.assertEqual(self.project_says(), before, "no project's log gained a message")
        [frame] = self.got(received, "the schema changed")
        self.assertIn("[sminos chat desk %s from writer → @you]" % sminos.event_ref(e), frame)
        self.assertEqual(reply_of(frame), "%s/%s" % (DESK, stid[:8]))
        self.cli("daemon", "tick")
        self.assertEqual(len(self.got(received, "the schema changed")), 1, "a second tick pushes nothing more")
        self.assertEqual(self.got(sreceived, "the schema changed"), [], "nothing to its sender")
        self.assertEqual(self.owed_to(rtid), [])

    def test_a_tag_qualified_by_the_channel_by_its_name_and_its_id_and_name_short_opens_none(self):
        rtid, rsid, received = self.live("reader")
        stid, ssid, _ = self.live("writer")
        for q in ("desk", DESK):
            code, out = self.as_session(ssid, "say", "@%s/reader via %s" % (q, q))
            self.assertEqual(code, 0, (q, out))
            self.assertEqual(self.line_for(out, "reader"), ["sent"], q)
            self.assertEqual(len(self.got(received, "via %s" % q)), 1, q)
        self.assertEqual([e["to"][0]["thread"] for e in self.says()], [rtid] * 2)
        before = self.logs()
        code, out = self.as_session(ssid, "say", "@desk#%s/reader hi" % DESK[:8])
        self.assertEqual(code, 1, out)
        self.assertIn("@desk#%s/reader opens no tag (a tag's qualifier takes no #): nothing was recorded. Say it as "
                      "sminos say --in desk#%s \"@<alias> …\", or qualify the tag with the channel's id"
                      % (DESK[:8], DESK[:8]), out)
        self.assertEqual(self.logs(), before)

    def test_a_stopped_member_is_woken_and_one_that_may_not_be_is_held(self):
        wtid, wsid = self.stopped()
        stid, ssid, _ = self.live("writer")
        wake_alias = self.row_of(wsid).alias
        code, out = self.as_session(ssid, "say", "--in", "desk", "@%s wake for this" % wake_alias)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.line_for(out, wake_alias), ["sent (woken)"])
        self.assertEqual(len(self.resumes(wsid)), 1, "one launch")
        self.assertEqual(len(self.woken_got(wsid, "wake for this")), 1)
        htid, hsid = self.stopped(mode="plan")
        held_alias = self.row_of(hsid).alias
        code, out = self.as_session(ssid, "say", "--in", "desk", "--exit-held", "@%s held for now" % held_alias)
        self.assertEqual(code, sminos.EXIT_HELD, out)
        self.assertEqual(self.line_for(out, held_alias), [held_line("mode")])
        self.assertEqual(self.resumes(hsid), [])
        self.assertEqual(len(self.owed_to(htid)), 1, "owed, held")

    def test_a_sender_racing_the_daemon_reads_what_was_done_and_never_pending(self):
        wtid, wsid = self.stopped()
        stid, ssid, _ = self.live("writer")
        alias = self.row_of(wsid).alias
        real, raced = sminos.deliver_next, []

        def deliver_next(project, member, due=False, owing=None):
            if owing is not None and not raced:
                raced.append(None)
                raced[0] = channels.deliver(project)   # the daemon's pass took the lock first
            return real(project, member, due=due, owing=owing)
        with mock.patch.object(sminos, "deliver_next", deliver_next):
            code, out = self.as_session(ssid, "say", "--in", "desk", "@%s raced" % alias)
        self.assertEqual(code, 0, out)
        self.assertEqual(raced[0][0], 1, "the daemon's pass pushed it")
        [said] = self.line_for(out, alias)
        self.assertNotIn("pending", said)
        self.assertEqual(said, "sent (%s)" % sminos.DELIVERED_ELSEWHERE)
        self.cli("daemon", "tick")
        self.assertEqual(len(self.woken_got(wsid, "raced")), 1, "once")
        self.assertEqual(len(self.resumes(wsid)), 1)

    def test_all_reaches_the_live_members_and_an_untagged_post_prompts_no_one(self):
        atid, asid, areceived = self.live("ann")
        btid, bsid, breceived = self.live("bob")
        stid, ssid = self.stopped()
        wtid, wsid, wreceived = self.live("writer")
        code, out = self.as_session(wsid, "say", "--in", "desk", "@all everyone")
        self.assertEqual(code, 0, out)
        [e] = self.says()
        self.assertTrue(e["wake"])
        self.assertEqual(sorted(r["thread"] for r in e["to"]), sorted([atid, btid]), "the live rows, not its sender")
        for received in (areceived, breceived):
            self.assertEqual(len(self.got(received, "everyone")), 1)
        self.assertEqual(self.got(wreceived, "everyone"), [])
        self.assertEqual(self.resumes(ssid), [], "the stopped member is not woken")
        self.assertEqual(self.owed_to(stid), [], "nor owed")
        code, out = self.as_session(wsid, "say", "--in", "desk", "a note")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.says()[-1]["to"], "*")
        self.cli("daemon", "tick")
        for received in (areceived, breceived, wreceived):
            self.assertEqual(self.got(received, "a note"), [], "prompts no one")

    def test_all_reaches_a_row_whose_thread_id_is_the_senders_session_id(self):
        """A seat's thread id is its first session's; that session, back as a thread of its own, sends `@all`: the
        seat is another thread, and is reached (sessions are compared with sessions, threads with threads)."""
        wtid, wsid, _ = self.live("writer")
        stid, ssid = self.far("seat", tid=wsid)
        code, out = self.as_session(wsid, "say", "--in", "desk", "@all everyone")
        self.assertEqual(code, 0, out)
        [e] = self.says()
        self.assertEqual([r["thread"] for r in e["to"]], [stid], "the seat, not left out")

    def test_the_reply_line_lands_in_the_channel_and_reaches_the_first_senders_thread(self):
        rtid, rsid, received = self.live("reader")
        stid, ssid, sreceived = self.live("writer")
        self.as_session(ssid, "say", "--in", "desk", "@reader question")
        [frame] = self.got(received, "question")
        code, out = self.reply(rsid, frame, "answer")
        self.assertEqual(code, 0, out)
        q, a = self.says()
        self.assertEqual(a["to"], [{"session": ssid, "alias": "writer", "thread": stid}])
        self.assertEqual(a["thread"], rtid)
        self.assertEqual(self.line_for(out, "writer"), ["sent"])
        self.assertEqual(len(self.got(sreceived, "answer")), 1)

    def test_the_reply_line_runs_as_written_in_a_shell(self):
        """The frame's command itself, its placeholder alone replaced: the launcher's path and the quoting."""
        rtid, rsid, received = self.live("reader")
        stid, ssid, sreceived = self.live("writer")
        self.as_session(ssid, "say", "--in", "desk", "@reader what of it")
        [frame] = self.got(received, "what of it")
        m = re.search(r"\[To reply, run in Bash: (.*)\]", frame)
        self.assertIsNotNone(m, frame)
        self.assertEqual(m.group(1).count("<your reply>"), 1)
        command = m.group(1).replace("<your reply>", "it is answered")
        run = subprocess.run(["/bin/sh", "-c", command], cwd=self.root, capture_output=True, text=True,
                             env=dict(os.environ, CLAUDE_CODE_SESSION_ID=rsid))
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        sminos.forget_caches()
        a = self.says()[-1]
        self.assertEqual(a["text"], "@%s/%s it is answered" % (DESK, stid[:8]))
        self.assertEqual(a["to"], [{"session": ssid, "alias": "writer", "thread": stid}])
        self.assertEqual(a["thread"], rtid)
        self.assertEqual(len(self.got(sreceived, "it is answered")), 1)

    def test_the_reply_line_after_its_sender_was_handed_off_reaches_the_session_that_continues_it(self):
        rtid, rsid, received = self.live("reader")
        stid, old, oproc, sreceived = self.live_member("writer")
        self.as_session(old, "say", "--in", "desk", "@reader before the hand-off")
        [frame] = self.got(received, "before the hand-off")
        job, jproc = T1.Sessions.job(self, old)
        jreceived = self.inbox(job, jproc, "j")
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        self.assertEqual(threads.get(stid)["current"], job)
        code, out = self.reply(rsid, frame, "after it")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.says()[-1]["to"][0]["thread"], stid)
        self.assertEqual(len(self.got(jreceived, "after it")), 1, "the session that continues the thread")
        self.assertEqual(self.got(sreceived, "after it"), [])

    def test_a_hand_off_the_sweep_finishes_makes_its_sender_a_member_whole(self):
        """The session that continues a member's thread, its hand-off not yet finished when it says: the rosters'
        sweep finishes it, and membership and the sender's thread are read after that one sweep, so the post is
        a member's (its thread, no `from_project`, no copy), never a member's thread with an outsider's project."""
        rtid, rsid, received = self.live("reader")
        stid, old, oproc, _ = self.live_member("writer")
        job, jproc = T1.Sessions.job(self, old)
        self.inbox(job, jproc, "j")
        self.assertEqual(channels.channels_of(job), (), "the hand-off is the next reconciliation's to finish")
        before = self.project_says()
        code, out = self.as_session(job, "say", "--in", "desk", "@reader from the successor")
        self.assertEqual(code, 0, out)
        self.assertEqual(threads.get(stid)["current"], job, "the sweep finished the hand-off")
        [e] = self.says()
        self.assertEqual(e["thread"], stid)
        self.assertNotIn("from_project", e)
        self.assertNotIn("you are not in desk", out)
        self.assertEqual([x for x in self.project_says() if x not in before and x[1].get("copy")], [], "no copy")
        self.assertEqual(len(self.got(received, "from the successor")), 1)

    def test_the_reply_line_never_reaches_a_thread_that_came_to_hold_the_senders_old_session(self):
        rtid, rsid, received = self.live("reader")
        stid, old, oproc, sreceived = self.live_member("writer")
        self.as_session(old, "say", "--in", "desk", "@reader before")
        [frame] = self.got(received, "before")
        job, jproc = T1.Sessions.job(self, old)
        jreceived = self.inbox(job, jproc, "j")
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        _, again = self.session(sid=old, started=T1.ms_ago(-1))
        areceived = self.inbox(old, again, "a")
        self.reconcile()
        atid = threads.stamp(old)
        self.assertNotEqual(atid, stid, "the old session runs again as a thread of its own")
        self.add(atid, old, DESK)
        code, out = self.reply(rsid, frame, "to the thread")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.says()[-1]["to"][0]["thread"], stid)
        self.assertEqual(len(self.got(jreceived, "to the thread")), 1)
        self.assertEqual(self.got(areceived, "to the thread"), [], "never the thread that holds its old session")

    def test_the_reply_line_after_its_sender_left_goes_to_it_directly_and_the_replier_is_told(self):
        rtid, rsid, received = self.live("reader")
        stid, ssid, sreceived = self.live("writer")
        self.as_session(ssid, "say", "--in", "desk", "@reader question")
        [frame] = self.got(received, "question")
        self.removed(stid, ssid)
        chan_before = self.says()
        code, out = self.reply(rsid, frame, "answer after it left")
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        told = "@%s/%s is not in desk now: sent to it directly, in %s" % (DESK, stid[:8], self.p.name)
        self.assertIn(told, lines)
        [(pid, e)] = [(pid, e) for pid, e in self.project_says() if e.get("text", "").endswith("answer after it left")]
        self.assertEqual(pid, self.p.id, "the sender's own project's log")
        self.assertLess(lines.index(told), lines.index("recorded %s in %s" % (sminos.event_ref(e), self.p.name)))
        self.assertEqual(e["to"], [{"session": ssid, "alias": "writer"}], "a project's message, as today")
        self.assertEqual(self.says(), chan_before, "nothing in the channel's log")
        self.assertEqual(len(self.got(sreceived, "answer after it left")), 1)
        code, out = self.as_session(rsid, "say", "--in", "desk", "@%s again" % stid)
        self.assertEqual(code, 4, out)
        self.assertIn("%s is not in desk now (it left the channel, or its thread ended): nothing was recorded. "
                      "Drop --in to reach it in its own project" % ("@" + stid), out)


    def test_the_reply_line_to_a_sender_whose_project_has_left_or_is_retired_is_refused_as_the_short_tag_is(self):
        rtid, rsid, received = self.live("reader")
        stid, ssid, sreceived = self.open_here("writer", self.app_root)
        self.add(stid, ssid, DESK)
        self.as_session(ssid, "say", "--in", "desk", "@reader question", cwd=self.app_root)
        [frame] = self.got(received, "question")
        self.removed(stid, ssid)
        sminos.write_json(sminos.leaving_path(), {"counted": {}, "left": [APP]})
        cannot = "@%s/%s was in desk and cannot be reached now" % (DESK, stid[:8])
        for gone in ("left", "retired"):
            if gone == "retired":
                sminos.write_json(sminos.leaving_path(), {"counted": {}, "left": []})
            before = self.logs()
            with mock.patch.object(sminos, "org_retired", lambda pid: gone == "retired" and pid == APP):
                code, out = self.as_session(rsid, "say", "@%s ordinary" % ssid[:8])
                self.assertEqual(code, 4, (gone, out))
                code, out = self.reply(rsid, frame, "answer to a project that is gone")
            self.assertEqual(code, 4, (gone, out))
            self.assertIn(cannot, out, gone)
            self.assertNotIn("sent to it directly", out, gone)
            self.assertEqual(self.logs(), before, "nothing appended (%s)" % gone)
        self.assertEqual(self.got(sreceived, "answer to a project that is gone"), [])


# ------------------------------------------------------------ a session that is no member says (B2)


class Outsider(Say):
    def test_its_message_carries_its_project_a_copy_is_kept_and_it_reads_one_line(self):
        rtid, rsid, received = self.live("reader")
        otid, osid, oreceived = self.outsider()
        code, out = self.as_session(osid, "say", "--in", "desk", "@reader from outside", cwd=self.app_root)
        self.assertEqual(code, 0, out)
        [e] = self.says()
        self.assertEqual(e["from_project"], APP, "the sender's own project")
        self.assertEqual(e["thread"], otid)
        self.assertEqual(e["to"], [{"session": rsid, "alias": "reader", "thread": rtid}])
        lines = out.splitlines()
        rec = lines.index("recorded %s in desk" % sminos.event_ref(e))
        self.assertEqual(lines[rec + 1], "you are not in desk: replies to this come to you directly, in app. sminos "
                                         "channel add desk places you in it")
        [(pid, c)] = [(pid, c) for pid, c in self.project_says() if c.get("copy")]
        self.assertEqual(pid, APP)
        self.assertEqual(c["copy"], "%s:%s:%d" % (DESK, e["writer"], e["seq"]), "naming the channel's event")
        self.assertFalse(sminos.addressed_to(c, rsid), "owed to no one")
        self.assertEqual(self.line_for(out, "reader"), ["sent"])
        [frame] = self.got(received, "from outside")
        self.assertIn("[sminos chat desk %s from outside (not in desk) → @you]" % sminos.event_ref(e), frame)
        self.assertEqual(reply_of(frame), "%s/%s" % (APP, osid[:8]), "the sender in its own project")

    def test_a_copy_that_cannot_be_written_is_tried_after_the_delivery_and_changes_nothing_it_did(self):
        rtid, rsid, received = self.live("reader")
        otid, osid, _ = self.outsider()
        real, tried = sminos.log_append, []

        def append(project, writer, kind, **fields):
            if project.id == APP and fields.get("copy"):
                tried.append(sys.stdout.getvalue())   # what the sender had read when the copy was tried
                raise OSError("disk full")
            return real(project, writer, kind, **fields)

        with mock.patch.object(sminos, "log_append", append):
            code, out = self.as_session(osid, "say", "--in", "desk", "@reader a copy fails", cwd=self.app_root)
        self.assertEqual(code, 0, out)
        [seen] = tried
        self.assertIn("reader: sent", seen.splitlines(), "the delivery pass ran before the copy was tried")
        self.assertEqual(self.line_for(out, "reader"), ["sent"])
        self.assertIn("sminos: warning: delivered, but its copy could not be recorded in app: disk full", out)
        [e] = self.says()
        self.assertEqual(e["to"], [{"session": rsid, "alias": "reader", "thread": rtid}])
        self.assertEqual([c for _, c in self.project_says(self.app) if c.get("copy")], [], "no copy")
        self.assertEqual(len(self.got(received, "a copy fails")), 1, "delivered")
        self.assertEqual(self.owed_to(rtid), [], "and settled")

    def test_the_two_forms_of_the_reply_line(self):
        rtid, rsid, received = self.live("reader")
        otid, osid, oreceived = self.outsider()
        self.as_session(osid, "say", "@desk/reader first", cwd=self.app_root)
        [frame] = self.got(received, "first")
        code, out = self.reply(rsid, frame, "second")
        self.assertEqual(code, 0, out)
        [second] = self.got(oreceived, "second")
        [(pid, e2)] = [(pid, e) for pid, e in self.project_says() if e["text"].endswith("second")
                       and not e.get("copy")]
        self.assertEqual(pid, APP, "the reply in the outsider's project, a message to another project")
        self.assertEqual(e2.get("from_project"), self.p.id)
        code, out = self.as_session(osid, "say", "@%s third" % reply_of(second), cwd=self.app_root)
        self.assertEqual(code, 0, out)
        [(pid, e3)] = [(pid, e) for pid, e in self.project_says() if e["text"].endswith("third") and not e.get("copy")]
        self.assertEqual(pid, self.p.id, "the answer in the member's project")
        self.assertEqual(len(self.got(received, "third")), 1)
        self.assertEqual([e["text"] for e in self.says()], ["@desk/reader first"], "the channel's log holds the first "
                         "alone")

    def test_its_all_reaches_the_live_members_its_untagged_post_no_one_and_nothing_of_the_channel_reaches_it(self):
        atid, asid, areceived = self.live("ann")
        btid, bsid, breceived = self.live("bob")
        otid, osid, oreceived = self.outsider()
        code, out = self.as_session(osid, "say", "--in", "desk", "@all from outside to all", cwd=self.app_root)
        self.assertEqual(code, 0, out)
        for received in (areceived, breceived):
            self.assertEqual(len(self.got(received, "from outside to all")), 1)
        code, out = self.as_session(osid, "say", "--in", "desk", "a note from outside", cwd=self.app_root)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.says()[-1]["to"], "*")
        self.as_session(asid, "say", "--in", "desk", "@all members only")
        self.as_session(asid, "say", "--in", "desk", "@bob just bob")
        self.cli("daemon", "tick")
        for text in ("a note from outside", "members only", "just bob"):
            self.assertEqual(self.got(oreceived, text), [], text)
        self.assertEqual(self.got(areceived, "a note from outside"), [])
        self.assertIsNone(channels.debt(self.chan(DESK), threads.get(otid)), "it is owed nothing there")

    def test_its_event_carries_the_thread_the_rosters_sweep_gave_it(self):
        """A live session not yet a thread when it says: the roster's sweep over its project makes it one, and
        the event carries that thread."""
        rtid, rsid, received = self.live("reader")
        for i, argv in enumerate((("--in", "desk", "@reader named"), ("--in", "desk", "@all to all"))):
            osid = str(uuidlib.uuid4())   # a fresh sender per route: each route's own sweep makes it a thread
            _, oproc = self.session(root=self.app_root, sid=osid, kind="interactive", name="fresh%d" % i)
            self.inbox(osid, oproc, "fr%d" % i)
            self.assertEqual(threads.stamp(osid), "", "no thread yet")
            code, out = self.as_session(osid, "say", *argv, cwd=self.app_root)
            self.assertEqual(code, 0, out)
            otid = threads.stamp(osid)
            self.assertTrue(otid, "a thread now")
            self.assertEqual(self.says()[-1].get("thread"), otid, argv)

    def loose(self):
        """A local project, whose log is not filtered by audience."""
        local = os.path.join(self.home, "loose")
        os.makedirs(local)
        with open(os.path.join(local, ".smns"), "w") as f:
            json.dump({"project": "local-loose", "name": "loose"}, f)
        self.assertEqual(sminos.project_kind(self.project_of(local)), "local")
        return local

    def test_to_a_remote_member_whose_audience_is_not_known_no_copy_in_an_unfiltered_home_and_its_warning(self):
        self.au.keep_capabilities(["channels", "access"])
        local = self.loose()
        ftid, fsid = self.far("faraway")
        otid, osid, _ = self.open_here("outside", local)
        self.heard(osid)
        code, out = self.as_session(osid, "say", "--in", "desk", "@faraway unknown audience", cwd=local)
        self.assertEqual(code, 0, out)
        [e] = self.says()
        self.assertEqual(e["to"], [{"session": fsid, "alias": "faraway", "thread": ftid}])
        self.assertIn("delivered; its copy is not kept in loose: the message is for a private session's audience "
                      "alone, and loose's log is not filtered by audience", out)
        self.assertEqual([c for _, c in self.project_says(self.project_of(local)) if c.get("copy")], [], "no copy")
        self.assertTrue(self.au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(fsid, ["m-far"])}))
        code, out = self.as_session(osid, "say", "--in", "desk", "@faraway listed now", cwd=local)
        self.assertEqual(code, 0, out)
        self.assertNotIn("its copy is not kept", out)
        [c] = [c for _, c in self.project_says(self.project_of(local)) if c.get("copy")]
        self.assertTrue(c["text"].endswith("listed now"), "known listed: its copy kept")

    def test_a_listed_word_is_knowledge_only_under_a_welcome_with_access_and_from_a_frame_that_said_members(self):
        """A remote recipient's `members: null` kept from before a welcome that no longer lists `access` is no
        knowledge, nor is a frame that carried no `members` at all: no copy, today's warning, each; the listed
        word under a welcome with `access` keeps it, read once for the copy."""
        warning = ("delivered; its copy is not kept in loose: the message is for a private session's audience alone, "
                   "and loose's log is not filtered by audience")
        self.au.keep_capabilities(["channels", "access"])
        local = self.loose()
        ftid, fsid = self.far("faraway")
        otid, osid, _ = self.open_here("outside", local)
        self.heard(osid)
        copies = lambda: [c for _, c in self.project_says(self.project_of(local)) if c.get("copy")]  # noqa: E731
        self.assertTrue(self.au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(fsid, ["m-far"])}))
        self.au.keep_capabilities(["channels"])   # a later welcome without `access`
        code, out = self.as_session(osid, "say", "--in", "desk", "@faraway old word", cwd=local)
        self.assertEqual(code, 0, out)
        self.assertIn(warning, out)
        self.assertEqual(copies(), [], "an old word under a welcome without access: no copy")
        self.au.keep_capabilities(["channels", "access"])
        self.assertTrue(self.au.keep_audience({"t": "audience", "session": fsid, "owners": ["m-far"],
                                               "policyRev": 1}))   # said nothing of `members`
        code, out = self.as_session(osid, "say", "--in", "desk", "@faraway no members said", cwd=local)
        self.assertEqual(code, 0, out)
        self.assertIn(warning, out)
        self.assertEqual(copies(), [], "a frame that said no members: no copy")
        self.assertTrue(self.au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(
            fsid, ["m-far"], None, 2)}))
        real, reads = self.au._read_audiences, []

        def counted():
            reads.append(None)
            return real()
        btid, bsid = self.far("farther")
        self.assertTrue(self.au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(bsid, ["m-far"])}))
        record_copy = sminos.record_copy

        def copy_counted(home, delivered):
            reads.clear()
            with mock.patch.object(self.au, "_read_audiences", counted):
                return record_copy(home, delivered)
        with mock.patch.object(sminos, "record_copy", copy_counted):
            code, out = self.as_session(osid, "say", "--in", "desk", "@faraway @farther said listed", cwd=local)
        self.assertEqual(code, 0, out)
        self.assertNotIn("its copy is not kept", out)
        self.assertEqual([c["text"] for c in copies()], ["@faraway @farther said listed"])
        self.assertEqual(len(reads), 1, "the cache read once for the copy")

    def test_an_audience_cache_unreadable_at_the_copy_or_an_entry_without_members_keeps_no_copy(self):
        """An audiences file that cannot be read when the copy is weighed (the event recorded and delivered) is no
        knowledge: no copy, today's warning, the say a success; nor is an entry that does not say `members`."""
        self.au.keep_capabilities(["channels", "access"])
        local = self.loose()
        ftid, fsid = self.far("faraway")
        otid, osid, _ = self.open_here("outside", local)
        self.heard(osid)
        self.assertTrue(self.au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(fsid, ["m-far"])}))
        path = self.au.audiences_path()
        with open(path) as f:
            kept = f.read()
        real = sminos.record_copy

        def unreadable_then_copy(home, delivered):
            with open(path, "w") as f:
                f.write("{not json")
            return real(home, delivered)
        warning = ("delivered; its copy is not kept in loose: the message is for a private session's audience alone, "
                   "and loose's log is not filtered by audience")
        with mock.patch.object(sminos, "record_copy", unreadable_then_copy):
            code, out = self.as_session(osid, "say", "--in", "desk", "@faraway cache gone", cwd=local)
        self.assertEqual(code, 0, out)
        self.assertIn(warning, out)
        self.assertEqual(len([e for e in self.says() if e["text"].endswith("cache gone")]), 1, "recorded once")
        self.assertEqual([c for _, c in self.project_says(self.project_of(local)) if c.get("copy")], [], "no copy")
        d = json.loads(kept)
        del d["sessions"][fsid]["members"]
        with open(path, "w") as f:
            json.dump(d, f)
        code, out = self.as_session(osid, "say", "--in", "desk", "@faraway partial entry", cwd=local)
        self.assertEqual(code, 0, out)
        self.assertIn(warning, out)
        self.assertEqual([c for _, c in self.project_says(self.project_of(local)) if c.get("copy")], [], "no copy")

    def private(self, sid):
        """The session private, its audience as the endpoint gave it at its record's policyRev."""
        records.set_policy(sid, lambda a, shares: ("private", shares))
        self.heard(sid)

    def heard(self, sid):
        """The endpoint's audience for the session at its record's policyRev, as the uplink keeps it."""
        rec = records.read(sid)
        members = list(rec["owners"]) + [x["member"] for x in rec.get("shares") or []]
        self.assertTrue(self.au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(
            sid, rec["owners"], members, rec.get("policyRev", 0))}))

    def test_from_a_project_whose_log_is_not_filtered_to_a_private_member_no_copy_and_its_warning(self):
        self.au.keep_capabilities(["channels", "access"])
        local = os.path.join(self.home, "loose")
        os.makedirs(local)
        with open(os.path.join(local, ".smns"), "w") as f:
            json.dump({"project": "local-loose", "name": "loose"}, f)
        self.assertEqual(sminos.project_kind(self.project_of(local)), "local")
        rtid, rsid, received = self.live("reader")
        self.private(rsid)
        otid, osid, _ = self.open_here("outside", local)
        self.heard(osid)
        code, out = self.as_session(osid, "say", "--in", "desk", "@reader private words", cwd=local)
        self.assertEqual(code, 0, out)
        self.assertIn("delivered; its copy is not kept in loose: the message is for a private session's audience "
                      "alone, and loose's log is not filtered by audience", out)
        self.assertIn("you are not in desk: replies to this come to you directly, in loose.", out)
        self.assertEqual([e for _, e in self.project_says(self.project_of(local)) if e.get("copy")], [], "no copy")
        [e] = self.says()
        self.assertTrue(sminos.is_stream(e["writer"]), "under the private member's audience")
        self.assertEqual(len(self.got(received, "private words")), 1, "delivered")

    def test_recipients_of_two_audiences_are_two_events_and_a_copy_each(self):
        self.au.keep_capabilities(["channels", "access"])
        rtid, rsid, received = self.live("reader")
        self.private(rsid)
        ltid, lsid, lreceived = self.live("listed")
        otid, osid, _ = self.outsider()
        for sid in (lsid, osid):
            self.heard(sid)
        code, out = self.as_session(osid, "say", "--in", "desk", "@reader @listed to both", cwd=self.app_root)
        self.assertEqual(code, 0, out)
        events = self.says()
        self.assertEqual(len(events), 2, "an event an audience")
        self.assertEqual(sorted(e["to"][0]["thread"] for e in events), sorted([rtid, ltid]))
        copies = [e for _, e in self.project_says(self.app) if e.get("copy")]
        self.assertEqual(len(copies), 2, "a copy each")
        self.assertEqual(len(self.got(received, "to both")), 1)
        self.assertEqual(len(self.got(lreceived, "to both")), 1)


# ------------------------------------------------------------ what a recipient's line says, and an older row


class Lines(Say):
    def test_a_row_an_older_copy_left_unstamped_is_addressed_by_its_statements_thread_and_one_torn_is_not(self):
        stid, ssid, _ = self.live("writer")
        far_sid, far_tid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        w = "beta/" + far_sid
        sminos.log_append(self.app, w, "joined", session=far_sid, alias="olden", name_source="user", machine="beta",
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive")
        sminos.log_append(self.app, w, "state", session=far_sid, state="idle", machine="beta")
        sminos.log_append(self.app, w, "channels", session=far_sid, thread=far_tid, op=os.urandom(8).hex(),
                          channels=[DESK])
        sminos.forget_caches()
        code, out = self.as_session(ssid, "say", "--in", "desk", "@olden hello")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.says()[-1]["to"], [{"session": far_sid, "alias": "olden", "thread": far_tid}])
        self.assertEqual(self.line_for(out, "olden"), ["recorded (on beta)"])
        torn_sid = str(uuidlib.uuid4())
        w = "beta/" + torn_sid
        sminos.log_append(self.app, w, "joined", session=torn_sid, alias="torn", name_source="user", machine="beta",
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive",
                          thread=str(uuidlib.uuid4()))
        sminos.log_append(self.app, w, "state", session=torn_sid, state="idle", machine="beta")
        sminos.log_append(self.app, w, "channels", session=torn_sid, thread=str(uuidlib.uuid4()),
                          op=os.urandom(8).hex(), channels=[DESK])
        sminos.forget_caches()
        before = self.logs()
        code, out = self.as_session(ssid, "say", "--in", "desk", "@torn hello")
        self.assertEqual(code, 4, out)
        self.assertIn("torn: not addressed (its membership of desk names two threads: nothing was recorded for it)",
                      out)
        self.assertEqual(self.logs(), before)
        code, out = self.as_session(ssid, "say", "--in", "desk", "@torn @olden both")
        self.assertEqual(code, 0, out)
        self.assertEqual([r["alias"] for r in self.says()[-1]["to"]], ["olden"], "the torn row given no entry")

    def test_a_torn_rows_tag_is_left_out_of_the_text_its_recipients_read(self):
        """A torn row is given no entry, and its tag no place in the text: the text goes to a stream splitter
        that rebuilds it only for several audiences, so what one audience reads would name the row it skips. On
        every route: beside a thread that has left, the message goes to it directly, and names it alone."""
        rtid, rsid, received = self.live("reader")
        stid, ssid, sreceived = self.live("writer")
        torn_sid = str(uuidlib.uuid4())
        w = "beta/" + torn_sid
        sminos.log_append(self.app, w, "joined", session=torn_sid, alias="hidden", name_source="user",
                          machine="beta", cwd="/w", worktree="", role="", seat="", by="",
                          session_kind="interactive", thread=str(uuidlib.uuid4()))
        sminos.log_append(self.app, w, "state", session=torn_sid, state="idle", machine="beta")
        sminos.log_append(self.app, w, "channels", session=torn_sid, thread=str(uuidlib.uuid4()),
                          op=os.urandom(8).hex(), channels=[DESK])
        sminos.forget_caches()
        code, out = self.as_session(ssid, "say", "--in", "desk", "@hidden#%s @reader the plan" % torn_sid[:8])
        self.assertEqual(code, 0, out)
        [e] = self.says()
        self.assertEqual(e["to"], [{"session": rsid, "alias": "reader", "thread": rtid}])
        self.assertEqual(e["text"], "@reader the plan", "the skipped row's tag is not in the event's text")
        [frame] = self.got(received, "the plan")
        self.assertNotIn("hidden", frame)
        self.assertNotIn(torn_sid[:8], frame)
        self.removed(stid, ssid)
        code, out = self.as_session(rsid, "say", "@desk/hidden#%s @%s/%s the old reply" % (torn_sid[:8], DESK, stid[:8]))
        self.assertEqual(code, 0, out)
        self.assertIn("sent to it directly, in %s" % self.p.name, out)
        [(pid, d)] = [(pid, d) for pid, d in self.project_says() if d["text"].endswith("the old reply")]
        self.assertEqual(d["text"], "@%s/%s the old reply" % (DESK, stid[:8]), "the direct message names it alone")
        [frame] = self.got(sreceived, "the old reply")
        self.assertNotIn("hidden", frame)
        self.assertNotIn(torn_sid[:8], frame)

    def test_a_recipient_whose_record_here_no_longer_holds_the_channel_is_told_and_not_delivered(self):
        rtid, rsid, received = self.live("reader")
        stid, ssid, _ = self.live("writer")
        self.raw(rtid, lambda raw: raw.update(channels=[]))   # the record left; the log still states the channel
        with mock.patch.object(channels, "restate", lambda *a, **k: None):   # its restatement not yet made
            code, out = self.as_session(ssid, "say", "--in", "desk", "@reader hi")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.line_for(out, "reader"),
                         ["recorded (it is not in desk on its machine now: not delivered)"])
        self.assertEqual(self.got(received, "hi"), [])


# ------------------------------------------------------------ the refusals (§2), nothing appended


class Refused(Say):
    def refused(self, code, out, want, exit_code, before):
        self.assertEqual(code, exit_code, out)
        self.assertIn(want, out)
        self.assertEqual(self.logs(), before, "no log changed")

    def test_each_refusal_leaves_every_log_as_it_was(self):
        rtid, rsid, _ = self.live("reader")
        otid, osid, _ = self.outsider("faraway")
        stid, ssid, _ = self.live("writer")
        before = self.logs()
        say = lambda *argv: self.as_session(ssid, "say", *argv)  # noqa: E731
        self.refused(*say("--project", "desk", "hello"),
                     'desk is a channel, and a selector names projects: sminos say --in desk "@all …" reaches its '
                     'live members', 1, before)
        self.refused(*say("--in", "desk", "--org", "hello"), "a selector picks the recipients itself, and --in desk",
                     1, before)
        self.refused(*say("--in", "desk", "@lobby/reader hello"), "one message, one log: the tags name desk, lobby", 4,
                     before)
        self.refused(*say("--in", "desk", "@app/faraway hello"), "one message, one log: the tags name app, desk", 4,
                     before)
        self.refused(*say("@desk/reader @faraway#%s hello" % osid[:8]), "one message, one log: the tags name app, "
                     "desk", 4, before)
        self.refused(*say("@faraway @desk/reader hello"), "one message, one log: the tags name desk; @faraway "
                     "resolves outside desk", 4, before)   # a bare alias, unresolved: no project claimed for it
        self.refused(*say("--in", "desk", "@faraway hello"),
                     "no member faraway in channel desk; elsewhere: @app/faraway#%s. Drop --in to reach it in its own "
                     "project" % osid[:8], 4, before)
        self.refused(*say("@desk/nobody hello"), "no member nobody in channel desk", 4, before)
        self.refused(*say("@desk/%s hello" % otid), "no member %s in channel desk" % otid, 4, before)
        self.refused(*say("--in", "desk", "@all @reader hello"), "@all stands alone", 2, before)
        self.refused(*say("@desk/reader @all hello"), "@all stands alone", 2, before)
        self.refused(*say("--in", "desk", "@reader @writer hi"), "you cannot tag yourself", 2, before)
        self.refused(*self.at_terminal("say", "--in", "nowhere", "hi"), "no project 'nowhere'", 4, before)
        other = "9e000001-0000-8000-8000-0000000000e1"
        self.refused(*say("--in", other, "hi"), "no channel '%s' is known on this machine" % other, 4, before)

    def test_a_session_that_is_no_member_and_whose_project_cannot_be_told(self):
        """No project to name in `from_project`, to keep a copy in, to tell the sender of, or for a reply to reach:
        refused whole, whether the session is a thread (its reply would go to the channel, where it is not) or not
        (no reply line at all); a member whose project cannot be told writes as a member."""
        rtid, rsid, received = self.live("reader")
        otid, osid, _ = self.outsider()
        stid, ssid, _ = self.live("writer")
        bare = str(uuidlib.uuid4())
        self.assertEqual(threads.stamp(bare), "")
        before = self.logs()
        with mock.patch.object(sminos, "session_project", return_value=None):
            for sid in (osid, bare):
                for argv in (("--in", "desk", "@reader hi"), ("@desk/reader hi",), ("--in", "desk", "@all hi"),
                             ("--in", "desk", "untagged")):
                    self.refused(*self.as_session(sid, "say", *argv, cwd=self.app_root),
                                 channels.NO_HOME % "desk", 1, before)
            code, out = self.as_session(ssid, "say", "--in", "desk", "@reader as a member")
        self.assertEqual(code, 0, out)
        [e] = self.says()
        self.assertNotIn("from_project", e)
        self.assertEqual(e["thread"], stid)
        self.assertEqual(len(self.got(received, "as a member")), 1)

    def test_a_session_whose_project_cannot_be_told_follows_a_reply_line_to_a_thread_that_left_directly(self):
        """The direct route is a project's say and writes nothing into the channel: no project of the sender's is
        needed for it, and it is taken; a post into the channel by the same session is refused."""
        gtid, gsid, greceived = self.live("gone")
        self.live("reader")
        self.removed(gtid, gsid)
        otid, osid, _ = self.outsider()
        chan_before = self.says()
        with mock.patch.object(sminos, "session_project", return_value=None):
            code, out = self.as_session(osid, "say", "@desk/%s answer directly" % gtid[:8], cwd=self.app_root)
            self.assertEqual(code, 0, out)
            self.assertIn("@desk/%s is not in desk now: sent to it directly, in %s" % (gtid[:8], self.p.name), out)
            self.assertEqual(len(self.got(greceived, "answer directly")), 1, "delivered")
            self.assertEqual(self.says(), chan_before, "nothing in the channel's log")
            before = self.logs()
            self.refused(*self.as_session(osid, "say", "@desk/reader into the channel", cwd=self.app_root),
                         channels.NO_HOME % "desk", 1, before)

    def test_a_tag_that_names_a_thread_once_in_the_channel_with_no_row_now(self):
        stid, ssid, _ = self.live("writer")
        gone_sid, gone_tid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        w = "beta/" + gone_sid
        sminos.log_append(self.app, w, "joined", session=gone_sid, alias="olden", name_source="user", machine="beta",
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive", thread=gone_tid)
        sminos.log_append(self.app, w, "channels", session=gone_sid, thread=gone_tid, op=os.urandom(8).hex(),
                          channels=[DESK])
        sminos.log_append_batch(self.app, w, [{"kind": "retired", "session": gone_sid, "reason": "retire", "by": "",
                                               "thread": gone_tid}], skip_src=False)
        sminos.forget_caches()
        before = self.logs()
        self.refused(*self.as_session(ssid, "say", "@desk/%s hi" % gone_tid[:8]),
                     "@desk/%s was in desk and cannot be reached now (it has ended, or this machine may not read it): "
                     "nothing was recorded" % gone_tid[:8], 4, before)

    def test_the_enrollment_does_not_carry_the_channels_log(self):
        stid, ssid, _ = self.live("writer")
        sminos.register_if_absent(sminos.make_project(FOREIGN, "foreign", "", "", {"url": HUB["url"],
                                                                                   "org": "org-2"}))
        sminos.forget_caches()
        before = self.logs()
        self.refused(*self.at_terminal("say", "--in", "foreign", "hi"),
                     "cannot say into foreign: this machine's enrollment does not carry its log (its registration on "
                     "this machine names another org): nothing was written", 1, before)

    def test_a_terminal_and_a_session_with_in_a_project_and_a_channels_tag(self):
        stid, ssid, _ = self.live("writer")
        self.live("reader")
        before = self.logs()
        self.refused(*self.at_terminal("say", "--in", "app", "@desk/reader hi"),
                     "one message, one log: the tags name app, desk", 4, before)
        self.refused(*self.as_session(ssid, "say", "--in", "app", "@desk/reader hi"),
                     "--in is for an operator, not a session", 2, before)

    def test_chat_host_of_a_channel(self):
        code, out = self.at_terminal("chat", "--host", "desk")
        self.assertEqual(code, 1, out)
        self.assertIn("desk is a channel, and what a session sends its human is in its own project's log: sminos chat "
                      "--host <project>", out)


# ------------------------------------------------------------ a person's and a machine's words


class Words(Say):
    def test_a_person_at_a_terminal_writes_under_the_machines_human_writer_and_waits_for_the_endpoints_word(self):
        rtid, rsid, received = self.live("reader")
        code, out = self.at_terminal("say", "--in", "desk", "@reader from the person")
        self.assertEqual(code, 0, out)
        [e] = self.says()
        self.assertEqual((e["kind"], e["from"], e["writer"]), ("human", "human", sminos.writer_id()))
        self.assertNotIn("thread", e)
        self.assertNotIn("from_project", e)
        self.assertEqual(e["to"], [{"session": rsid, "alias": "reader", "thread": rtid}])
        self.assertEqual(self.line_for(out, "reader"), [sminos.WORDS_RECORDED], "left owed for the endpoint's word")
        self.assertEqual(self.got(received, "from the person"), [])

    def test_a_notice_from_a_machine_that_holds_no_member_is_recorded_and_chat_shows_its_program(self):
        code, out = self.at_terminal("say", "--notice", "devcloud", "--in", "desk", "lease ends")
        self.assertEqual(code, 0, out)
        [e] = self.says()
        self.assertEqual((e["kind"], e["notice"], e["to"]), ("human", "devcloud", "*"))
        code, out = self.at_terminal("chat", "desk", "-n", "5")
        self.assertEqual(code, 0, out)
        self.assertIn("devcloud@%s → *  lease ends" % sminos.host_name(), out)


# ------------------------------------------------------------ no word to a human under a channel's id (B7)


class HostWords(Say):
    """B7, proved and not built (CH2's M9): a session whose thread is in two channels is given a peer's frame
    from one by its inbox and a person's words in the other by its bridge, which keys them under
    `<channel>#<thread>`; then, through that bridge, it says something to its human, opens two questions and
    is answered the first; it stops, and the sweep runs. A real bridge child takes the frame and the export,
    once as a running session on 1.54 has it loaded (the merge base's launcher, extracted from git) and once
    as this tree's, with bridge_standin.py as its mod. Every word to the human lands in the thread's own
    project, the second question is closed there, another session's question in another project stays open,
    and nothing is written or queued under a channel's id or under the `#` scope as a log. What is proved is
    where things lie on disk, which is all an uplink frames host events from (Link.host_pass, which passes a
    channel's log by); no uplink runs here."""

    WORDS = "the words the session sends its human after the channel's frame"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.mkdtemp(dir=BASE)
        cls.base = extracted(MERGE_BASE, cls.tmp)

    def bridge(self, launcher, sid):
        """The session's bridge: `launcher`'s child with the stand-in as its mod. Its socket is named through a
        short link to SMINOS_HOME, since a Unix socket's path is bounded (104 bytes on macOS) and the suite's
        home under the system's temporary directory can pass it; the same files either way."""
        link = os.path.join(tempfile.mkdtemp(prefix="smb.", dir="/tmp"), "s")
        os.symlink(os.environ["SMINOS_HOME"], link)
        self.addCleanup(shutil.rmtree, os.path.dirname(link))
        bridge = sminos.sibling_module("sminos_bridge")
        patcher = mock.patch.object(bridge, "bridge_dir", lambda: os.path.join(link, "bridge"))
        patcher.start()
        self.addCleanup(patcher.stop)
        standin = bridge_standin.StandIn(launcher, sid, ops=["deliver"], cwd=self.root,
                                         env=dict(os.environ, SMINOS_HOME=link))
        self.addCleanup(standin.stop)
        return standin

    def turn(self):
        """A turn's rows as the mod exports them: a message to the human, two async questions, and the human's
        answer to the first."""
        def call(cid, name, inp, result):
            return [{"type": "assistant", "uuid": "a-" + cid, "message": {"role": "assistant", "content": [
                        {"type": "tool_use", "id": cid, "name": name, "input": inp}]}},
                    {"type": "user", "uuid": "r-" + cid, "message": {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": cid, "content": result}]}}]

        def ask(cid, q):
            return call(cid, sminos.ASK_TOOLS[0], {"questions": [{"question": q, "options": [{"label": "yes"}]}]},
                        sminos.ASYNC_RESULT)
        answer = {"type": "attachment", "uuid": "att-q1", "attachment": {"type": "hook_additional_context", "content": [
            "The human responded to your async AskUserQuestion (call toolu_q1): yes"]}}
        return call("toolu_m1", sminos.MESSAGE_TOOLS[0], {"text": self.WORDS}, "sent") + ask("toolu_q1", "first?") \
            + ask("toolu_q2", "second?") + [answer]

    def host_of(self, p, sid):
        sminos.forget_caches()
        return [e for e in sminos.host_read(p) if sminos.writer_session(e["writer"]) == sid]

    def scene(self, launcher):
        sid = str(uuidlib.uuid4())
        _, proc = self.session(sid=sid, kind="interactive", name="speaker")
        received = self.inbox(sid, proc, "spk")
        self.reconcile()
        tid = threads.stamp(sid)
        self.add(tid, sid, DESK, LOBBY)
        home = sminos.last_project(sid)
        self.assertEqual(home.id, self.p.id, "the thread's own project")
        standin = self.bridge(launcher, sid)
        self.message((sid, tid), cid=LOBBY, text="a peer's frame from the lobby")
        self.deliver(LOBBY)
        self.assertEqual(len(self.got(received, "a peer's frame from the lobby")), 1, "by the inbox")
        e = self.message((sid, tid), writer="%s/human" % FAR, kind="human", text="a person's words in the desk")
        sminos.forget_caches()
        o = channels.owing(self.chan(DESK), threads.get(tid), channels.own_row(threads.get(tid)))
        self.assertEqual(sminos.deliver_verdict(self.chan(DESK), o.member, e, "words", owing=o), "sent")
        self.assertEqual(len(standin.delivered), 1, "by the bridge")
        head, _, body = standin.delivered[0].partition("\n")
        self.assertTrue(head.startswith("[sminos chat desk %s from human" % sminos.event_ref(e)), head)
        self.assertEqual(body, "a person's words in the desk", "the channel's frame, as the mod took it")
        bridge = sminos.sibling_module("sminos_bridge")
        mark = "%s#%s/%s" % (DESK, tid, e["writer"])
        self.assertTrue(wait_for(lambda: bridge.load_kept(sid)["delivered"].get(mark) == e["seq"]),
                        "the bridge took it under the thread's scope, and keeps that mark")
        standin.post({"type": "export", "records": self.turn()})
        self.assertTrue(wait_for(lambda: len(self.host_of(home, sid)) == 4), self.host_of(home, sid))
        _, osid, _ = self.outsider("control")
        sminos.append_host(self.app, osid, [{"kind": "question", "from": "control", "to": "host",
                                             "text": ["still open?"], "choices": [], "src": "toolu_c1"}])
        standin.stop()
        self.end(proc)
        for _ in range(2):
            sminos.forget_caches()
            sminos.sibling_module("sminos_daemon").sweep_threads()
        got = [(e["kind"], e.get("src"), e.get("text"), e.get("closed")) for e in self.host_of(home, sid)]
        self.assertEqual(got, [("message", "toolu_m1", self.WORDS, None),
                               ("question", "toolu_q1", ["first?"], None),
                               ("question", "toolu_q2", ["second?"], None),
                               ("answered", "toolu_q1", "yes", None),
                               ("answered", "toolu_q2", sminos.QUESTION_CLOSED, "stopped")],
                         "the words, both questions and both answers in the thread's own project, the second closed")
        self.assertEqual([e["kind"] for e in self.host_of(self.app, osid)], ["question"],
                         "another session's question in another project stays open")
        for p in sminos.known_projects():
            for e in sminos.log_read(p) + sminos.host_read(p):
                if e["kind"] in ("message", "question", "answered"):
                    self.assertNotIn(DESK, json.dumps(e))
                    self.assertNotIn(LOBBY, json.dumps(e))
        for cid in (DESK, LOBBY):
            c = self.chan(cid)
            self.assertFalse({e["kind"] for e in sminos.log_read(c)} & {"message", "question", "answered"}, cid)
            for store in (sminos.HOST_STORE, sminos.QUEUED, "outbox"):
                self.assertFalse(os.path.exists(os.path.join(c.home, store)), (cid, store))
        root = os.path.realpath(os.environ["SMINOS_HOME"])
        kept = os.path.realpath(bridge.kept_path(sid))
        for d, dirs, names in os.walk(root):
            for n in dirs + names:
                self.assertNotIn("#", n, "no file or directory under the # scope: %s" % os.path.join(d, n))
            for n in names:
                path = os.path.join(d, n)
                if path == kept or not os.path.isfile(path):
                    continue
                with open(path, "rb") as f:
                    body = f.read()
                for cid in (DESK, LOBBY):
                    self.assertNotIn(("%s#%s" % (cid, tid)).encode(), body, "the scope written nowhere but the "
                                     "bridge's own marks: %s" % path)

    def test_through_a_bridge_on_1_54(self):
        self.scene(self.base)

    def test_through_this_trees_bridge(self):
        self.scene(os.path.join(SCRIPTS, "sminos"))


# ------------------------------------------------------------ reading a channel: chat and list


class Read(Say):
    def test_chat_reads_the_conversation_with_an_outsiders_clause_and_the_threads_cursor(self):
        rtid, rsid, _ = self.live("reader")
        stid, ssid, _ = self.live("writer")
        otid, osid, _ = self.outsider()
        self.as_session(ssid, "say", "--in", "desk", "@reader one")
        self.as_session(osid, "say", "--in", "desk", "@reader two", cwd=self.app_root)
        code, out = self.as_session(rsid, "chat", "desk")
        self.assertEqual(code, 0, out)
        self.assertIn("chat desk · 2 new", out)
        self.assertIn("writer → @reader  @reader one", out)
        self.assertIn("outside (not in desk) → @reader  @reader two", out)
        code, out = self.as_session(rsid, "chat", "desk")
        self.assertIn("(no new messages)", out, "its cursor moved")
        self.assertTrue(os.path.exists(os.path.join(self.chan(DESK).home, "cursors", "thread-%s.json" % rtid)),
                        "kept under its thread")
        code, out = self.at_terminal("chat", DESK, "-n", "1", "--json")
        self.assertEqual(json.loads(out.strip())["text"], "@reader two")

    def test_chat_after_a_hand_off_prints_only_what_is_new_to_the_thread(self):
        stid, ssid, _ = self.live("writer")
        rtid, old, oproc, _ = self.live_member("reader")
        self.as_session(ssid, "say", "--in", "desk", "@reader before")
        self.as_session(old, "chat", "desk")
        job, jproc = T1.Sessions.job(self, old)
        self.inbox(job, jproc, "j")
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        self.as_session(ssid, "say", "--in", "desk", "@reader after")
        code, out = self.as_session(job, "chat", "desk")
        self.assertIn("chat desk · 1 new", out)
        self.assertIn("after", out)
        self.assertNotIn("  before", out)

    def test_chat_of_a_seat_in_its_first_session_leaves_out_what_its_thread_said_in_another(self):
        """A seat's thread id is its first session's, so a reader whose key is its own session can still be a
        thread: its own messages are its thread's, whichever session wrote them (a refill's, then the first
        session restored), as a frame counts them."""
        sid, proc = self.session()
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        self.reconcile()
        tid = threads.stamp(sid)
        self.assertEqual(tid, sid, "the seat's thread is its first session's id")
        self.add(tid, sid, DESK)
        other = str(uuidlib.uuid4())   # its second occupant's, between a refill and the first's restoring
        sminos.log_append(self.chan(DESK), sminos.writer_id(other), "say", **{
            "from": "w", "to": "*", "text": "said in its second session", "thread": tid})
        wtid, wsid, _ = self.live("writer")
        self.as_session(wsid, "say", "--in", "desk", "from another thread")
        code, out = self.as_session(sid, "chat", "desk")
        self.assertEqual(code, 0, out)
        self.assertIn("chat desk · 1 new", out)
        self.assertIn("from another thread", out)
        self.assertNotIn("said in its second session", out)
        self.assertTrue(os.path.exists(os.path.join(self.chan(DESK).home, "cursors", "thread-%s.json" % tid)))

    def test_chat_of_a_session_that_is_no_thread_keeps_its_cursor_apart_from_a_thread_of_its_id(self):
        """A seat's thread id is its first session's: that session, run again before it is any thread's, reads
        the channel under a cursor of its own, never the seat's thread's."""
        rtid, rsid, _ = self.live("reader")
        wtid, wsid, _ = self.live("writer")
        self.as_session(wsid, "say", "--in", "desk", "@reader unread")
        self.assertEqual(threads.stamp(rtid), "", "a session of the thread's id that is no thread")
        code, out = self.as_session(rtid, "chat", "desk")
        self.assertEqual(code, 0, out)
        self.assertIn("unread", out)
        self.assertFalse(os.path.exists(os.path.join(self.chan(DESK).home, "cursors", "thread-%s.json" % rtid)),
                         "the thread's cursor untouched")
        code, out = self.as_session(rsid, "chat", "desk")
        self.assertIn("chat desk · 1 new", out, "the thread's message still unread to it")
        code, out = self.as_session(rtid, "chat", "desk")
        self.assertIn("(no new messages)", out, "the session's own cursor moved")

    def test_an_older_copys_read_under_the_bare_id_moves_neither_the_threads_chat_nor_its_frames_count(self):
        """An older copy keeps a reader's cursor under its bare session id, which a seat's thread id equals: what
        it reads under that key leaves the thread's own cursor, its chat's and its frames' unread count, as was."""
        rtid, rsid, received = self.live("reader")
        wtid, wsid, _ = self.live("writer")
        self.as_session(wsid, "say", "--in", "desk", "@reader one")
        [e] = self.says()
        sminos.cursor_save(self.chan(DESK), rtid, {e["writer"]: e["seq"]})   # an older copy's `chat`, by the bare id
        self.as_session(wsid, "say", "--in", "desk", "@reader two")
        [frame] = self.got(received, "two")
        self.assertIn("| unread 1]", frame, "the frame counts the first as unread")
        code, out = self.as_session(rsid, "chat", "desk")
        self.assertIn("chat desk · 2 new", out, "both unread to the thread")

    def test_chat_over_an_older_copys_closed_join_changes_no_record_and_no_log_file(self):
        sid, proc, tid = self.member(name="olden")
        self.end(proc)
        sminos.log_append(self.chan(DESK), sminos.writer_id(sid), "joined", session=sid, alias="olden",
                          name_source="user", machine=sminos.host_name(), cwd=self.root, worktree="", role="", seat="",
                          by="", session_kind="interactive")   # an older copy's join into the channel
        sminos.forget_caches()
        record = json.dumps(threads.get(tid), sort_keys=True)
        before = self.logs()
        code, out = self.at_terminal("chat", "desk")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.dumps(threads.get(tid), sort_keys=True), record, "its record")
        self.assertEqual(self.logs(), before, "no log file")

    def test_list_of_a_channel_prints_it_as_channel_does_and_filters_by_a_word(self):
        self.live("reader")
        self.live("writer")
        code, out = self.at_terminal("list", "desk")
        self.assertEqual(code, 0, out)
        self.assertIn("# desk", out)
        self.assertIn("reader [", out)
        self.assertIn("writer [", out)
        code, out = self.at_terminal("list", "desk", "read")
        self.assertIn("reader [", out)
        self.assertNotIn("writer [", out)


# ------------------------------------------------------------ B11: a store with no channel, against the merge base


MERGE_BASE = "61b27ebee04ab1e3c61c7e966eec656cfc851451"   # `git merge-base origin/main HEAD` when M4 was built
ANN = "6c000a01-0000-4000-8000-0000000000a1"
BEE = "6c000a02-0000-4000-8000-0000000000a2"
CAT = "6c000a03-0000-4000-8000-0000000000a3"
STUB = '#!/bin/sh\ncase "$1" in agents) echo "[]" ;; esac\nexit 0\n'


def extracted(rev, dest):
    """The launcher of revision `rev`'s sminos, extracted under `dest` (fetched from origin where this clone lacks
    it, as test-older-cli.sh pins its copies)."""
    top = subprocess.run(["git", "-C", HERE, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                         check=True).stdout.strip()
    if subprocess.run(["git", "-C", top, "cat-file", "-e", rev + "^{commit}"], capture_output=True).returncode:
        subprocess.run(["git", "-C", top, "fetch", "-q", "--depth=1", "origin", rev], check=True)
    archive = subprocess.run(["git", "-C", top, "archive", rev, "sminos"], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", dest], input=archive, check=True)
    return os.path.join(dest, "sminos", "skills", "sminos", "scripts", "sminos")


class SameAsBase(unittest.TestCase):
    """B11 for `say` and `chat`: two sessions of one project and one of another, on a machine that knows no
    channel, exchange tagged, untagged and `@all` messages, a person speaks, and each reads the chat; this tree's
    launcher prints, pushes and writes what the merge base's does, but for ids, times and paths."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir=BASE)
        cls.base = extracted(MERGE_BASE, cls.tmp)

    def scene(self, launcher):
        home = tempfile.mkdtemp(dir=BASE)
        env = dict(os.environ, HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"),
                   DAEMON_HOST="alpha", DAEMON_BOOT_ID="boot-current", SMINOS_DERIVE_EVERY="0",
                   PATH=os.path.join(home, "bin") + os.pathsep + os.environ["PATH"])
        for k in ("CLAUDE_CODE_SESSION_ID", "MAWS_USER_DATA", "CLAUDE_CONFIG_DIR", "WAKE_ENGINE_STATE"):
            env.pop(k, None)
        os.makedirs(os.path.join(env["HOME"], ".claude", "sessions"))
        os.makedirs(env["SMINOS_HOME"])
        os.makedirs(os.path.join(home, "bin"))
        with open(os.path.join(home, "bin", "claude"), "w") as f:
            f.write(STUB)
        os.chmod(os.path.join(home, "bin", "claude"), 0o755)
        roots = {}
        for name in ("work", "other"):
            roots[name] = os.path.join(home, name)
            subprocess.run(["git", "init", "-q", roots[name]], check=True)
        procs = []
        try:
            for sid, name, root in ((ANN, "ann", "work"), (BEE, "bee", "work"), (CAT, "cat", "other")):
                sock = os.path.join(home, "%s.sock" % name)
                open(sock + ".received", "a").close()
                procs.append(subprocess.Popen([sys.executable, "-B", os.path.join(HERE, "inbox_standin.py"), sock,
                                               sock + ".received"]))
                proc = subprocess.Popen(["sleep", "600"])
                procs.append(proc)
                with open(os.path.join(env["HOME"], ".claude", "sessions", "%d.json" % proc.pid), "w") as f:
                    json.dump({"pid": proc.pid, "sessionId": sid, "cwd": roots[root], "kind": "interactive",
                               "name": name, "nameSource": "user", "status": "idle", "messagingSocketPath": sock}, f)
                self.assertTrue(wait_for(lambda: os.path.exists(sock)))
            out = []
            steps = [(ANN, "work", ("say", "@bee hello bee")), (BEE, "work", ("say", "@ann hi back")),
                     (ANN, "work", ("say", "a note for the record")), (ANN, "work", ("say", "@all everyone")),
                     (ANN, "work", ("say", "@other/cat across projects")),
                     ("", "work", ("say", "--in", "other", "@cat from the person")),
                     ("", "work", ("say", "a person's note")),
                     (ANN, "work", ("say", "@nobody x")), (ANN, "work", ("say", "@other/nobody x")),
                     (BEE, "work", ("chat",)), (BEE, "work", ("chat",)), (BEE, "work", ("chat", "-n", "3")),
                     (ANN, "work", ("chat", "--json", "-n", "2")), ("", "work", ("chat",)),
                     ("", "work", ("chat", "other")), (CAT, "other", ("chat", "--kind", "say"))]
            for sid, root, argv in steps:
                run_env = dict(env, CLAUDE_CODE_SESSION_ID=sid) if sid else env
                got = subprocess.run([launcher] + list(argv), cwd=roots[root], env=run_env, capture_output=True,
                                     text=True, timeout=120)
                out.append((argv, got.returncode, got.stdout + got.stderr))
            inboxes = {}
            for name in ("ann", "bee", "cat"):
                with open(os.path.join(home, "%s.sock.received" % name)) as f:
                    inboxes[name] = [json.loads(line)["message"]["content"] for line in f if line.strip()]
            logs = {}
            for path in sorted(glob.glob(os.path.join(env["SMINOS_HOME"], "projects", "*", "log", "*.jsonl"))):
                with open(path) as f:
                    logs[os.path.relpath(path, env["SMINOS_HOME"])] = [
                        {k: v for k, v in json.loads(line).items() if k != "ts"} for line in f if line.strip()]
            return self.normal(home, launcher, {"out": out, "inboxes": inboxes, "logs": logs})
        finally:
            for p in procs:
                p.kill()
                p.wait()

    def normal(self, home, launcher, got):
        text = json.dumps(got, indent=1, sort_keys=True, ensure_ascii=False)
        text = text.replace(os.path.realpath(launcher), "<sminos>").replace(launcher, "<sminos>")
        text = text.replace(os.path.realpath(home), "<home>").replace(home, "<home>")
        text = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z", "<ts>", text)
        text = re.sub(r"(?<!\d)\d\d:\d\d:\d\d(?!\d)", "<hh:mm:ss>", text)
        keep = {ANN, BEE, CAT}
        text = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                      lambda m: m.group(0) if m.group(0) in keep else "<id>", text)
        text = re.sub(r"\b[0-9a-f]{16,32}\b", "<hex>", text)
        return text

    def test_say_and_chat_print_push_and_write_what_the_merge_base_does(self):
        mine = self.scene(os.path.join(SCRIPTS, "sminos"))
        base = self.scene(self.base)
        self.assertIn("recorded", mine)
        self.assertIn("hello bee", mine)
        if mine != base:
            import difflib
            self.fail("this tree differs from the merge base:\n" + "\n".join(difflib.unified_diff(
                base.splitlines(), mine.splitlines(), "merge base", "this tree", lineterm="", n=2)))


if __name__ == "__main__":
    unittest.main()
