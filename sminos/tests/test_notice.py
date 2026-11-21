#!/usr/bin/env python3
"""A machine's notice (contract X8; EN.G1's plan, M1:
docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md, Interfaces
§1 and §2), against the test engine:

- the marker: `notice_of` and `notice_sender`, what `owner_event` and the
  manager's reading of the owner's words make of a marked event;
- `say --notice <program>`: the field on every event it appends (a tag, a
  broadcast, an `--in` note), refused in a session and for a value outside
  the pattern; a project named by its id where two logs share a name;
- what a reader shows: the frame's first line, a retry's pointer, `sminos
  chat`, the TUI;
- the route: the inbox frame from `<program>@<machine>` with no reply line,
  never the bridge or a supervisor, for a verdict of `words`, of `peer` and
  for none; a receipt's marker first; a stopped thread woken for it;
- a direct `send`, `send --wait` and `resume` pushing a queue that holds a
  notice as runs, each by its own route, settled as each lands;
- `say --exit-held`: exit 3 where a tagged recipient's line is a held one,
  on this machine and for another machine's published state.

Hermetic: test_wake.Engine (HOME, SMINOS_HOME and the engine's state
temporary, the engine first on PATH and checked to be).
Run: python3 -B sminos/tests/test_notice.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import json
import os
import re
import subprocess
import sys
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "skills", "manager", "scripts"))

from test_wake import line_of, wait_for  # noqa: E402
from test_wake_delivery import FLAGS, STARTING, WORDS, line  # noqa: E402
from test_wake_seat import SCRIPT, sminos, threads, wake  # noqa: E402
from test_wake_verbs import Verbs  # noqa: E402
import manager_window  # noqa: E402
import sminos_tui as tui  # noqa: E402

control = sminos.control_module()
HUMAN = "testhost/human"
ENVELOPE_RE = re.compile(r'<cross-session-message from-name="([^"]*)">\n(.*)\n</cross-session-message>', re.S)


def event(writer=HUMAN, kind="human", **more):
    return {"ts": "2026-11-21T10:00:00.000Z", "writer": writer, "seq": 1, "kind": kind, "from": "human",
            "to": [{"session": str(uuidlib.uuid4()), "alias": "x"}], "text": "devcloud on vm: idle", **more}


def envelope(content):
    """(from-name, body) of an inbox's frame."""
    m = ENVELOPE_RE.fullmatch(content)
    return m.group(1), m.group(2)


# ------------------------------------------------------------ the marker


class Marker(unittest.TestCase):
    def test_a_human_event_under_a_machines_human_writer_or_its_stream_is_marked(self):
        self.assertEqual(sminos.notice_of(event(notice="devcloud")), "devcloud")
        self.assertEqual(sminos.notice_of(event("dc-x-0001/human~0123456789abcdef", notice="devcloud")), "devcloud")

    def test_the_field_on_any_other_kind_or_writer_or_empty_or_no_string_marks_nothing(self):
        for e in (event(kind="say", notice="devcloud"),
                  event("dc-x-0001/6d000001-0000-4000-8000-0000000000d1", notice="devcloud"),
                  event("hub/mem-1", notice="devcloud"), event(notice=""), event(notice=7), event(notice=["x"]),
                  event()):
            with self.subTest(e=e):
                self.assertEqual(sminos.notice_of(e), "")

    def test_only_a_machine_name_by_mawss_grammar_marks_and_never_hub_or_legacy(self):
        for machine in ("legacy", "Legacy", "Hub", "hub", "a machine", ".mac", "-mac", "_mac", "m" * 64, "a/b"):
            for stream in ("", "~0123456789abcdef"):
                with self.subTest(machine=machine, stream=stream):
                    e = event("%s/human%s" % (machine, stream), notice="devcloud")
                    self.assertEqual(sminos.notice_of(e), "")
                    self.assertTrue(sminos.owner_event(e), "read as today: a human event of that writer")
        for machine in ("m" * 63, "Mac-mini.local", "dc-x-0001", "a_b"):
            with self.subTest(machine=machine):
                self.assertEqual(sminos.notice_of(event("%s/human" % machine, notice="devcloud")), "devcloud")

    def test_the_sender_is_the_program_at_the_machine_its_writer_names(self):
        self.assertEqual(sminos.notice_sender(event("dc-x-0001/human", notice="devcloud")), "devcloud@dc-x-0001")
        self.assertEqual(sminos.notice_sender(event("dc-x-0001/human~0123456789abcdef", notice="devcloud")),
                         "devcloud@dc-x-0001", "from the stream's base writer")
        for odd in ("Devcloud", "a b", "x" * 33, "dev]cloud"):
            with self.subTest(notice=odd):
                self.assertEqual(sminos.notice_sender(event("dc-x-0001/human", notice=odd)), "notice@dc-x-0001")

    def test_a_marked_event_is_not_the_owners_words_and_the_same_event_without_the_field_is(self):
        self.assertFalse(sminos.owner_event(event(notice="devcloud")))
        self.assertTrue(sminos.owner_event(event()))
        self.assertTrue(sminos.owner_event(event("hub/mem-1", notice="devcloud")), "the field marks nothing there")

    def test_the_managers_reading_of_the_owners_words_leaves_it_out(self):
        sid = str(uuidlib.uuid4())
        plain = dict(event(text="do this"), to=[{"session": sid, "alias": "x"}])
        marked = dict(event(text="devcloud on vm: idle", notice="devcloud"), seq=2, to=[{"session": sid, "alias": "x"}])
        words = manager_window.OwnerWords([plain, marked], [sid])
        self.assertEqual(words.texts, {"do this"})


# ------------------------------------------------------------ the rig


class Notices(Verbs):
    def notice(self, sid, text, alias="x"):
        """A machine's notice of this machine's operator writer, owed to the session and pushed by nobody yet."""
        return sminos.log_append(self.p, HUMAN, "human", **{"from": "human", "to": [{"session": sid, "alias": alias}],
                                                            "text": text, "notice": "devcloud"})

    def say_notice(self, *argv, cwd=None):
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        return self.cli("say", "--notice", "devcloud", *argv, cwd=cwd)

    def events(self, text, p=None):
        p = p or self.p
        d = sminos.project_path(p, "log")
        out = []
        for name in sorted(os.listdir(d)):
            if name.endswith(".jsonl"):
                with open(os.path.join(d, name)) as f:
                    out += [json.loads(x) for x in f if x.strip() and text in x]
        return out

    def settled(self, sid, writer=HUMAN):
        return sminos._delivery(sminos.delivered_load(self.p, sid), writer)["settled"]

    def bridge(self, took=True):
        """control.deliver recording (session, event, text); it takes each, or declines with None."""
        calls = []
        p = mock.patch.object(control, "deliver", side_effect=lambda session, project, e, text:
                              calls.append((session, e, text)) or (True if took else None))
        p.start()
        self.addCleanup(p.stop)
        return calls


# ------------------------------------------------------------ say --notice


class Say(Notices):
    def test_the_field_is_on_a_tagged_event_on_each_event_of_a_broadcast_and_on_an_in_note(self):
        sid, _ = self.session(name="live-a")
        other, _ = self.session(name="live-b")
        self.reconcile()
        code, out = self.say_notice("@%s tagged notice" % sid[:8])
        self.assertEqual(code, 0, out)
        [e] = self.events("tagged notice")
        self.assertEqual((e["kind"], e["writer"], e["notice"]), ("human", HUMAN, "devcloud"))
        code, out = self.say_notice("--project", self.p.id, "broadcast notice")
        self.assertEqual(code, 0, out)
        broadcast = self.events("broadcast notice")
        self.assertTrue(broadcast)
        self.assertEqual({x["notice"] for x in broadcast}, {"devcloud"})
        self.assertEqual(sorted(r["session"] for x in broadcast for r in x["to"]), sorted([sid, other]))
        code, out = self.say_notice("--in", self.p.id, "a note for later")
        self.assertEqual(code, 0, out)
        [e] = self.events("a note for later")
        self.assertEqual((e["to"], e["notice"]), ("*", "devcloud"))
        code, out = self.say("@%s no flag" % sid[:8])
        self.assertEqual(code, 0, out)
        self.assertNotIn("notice", self.events("no flag")[0], "no key without the flag")

    def test_a_session_is_refused_and_nothing_appended(self):
        sid = self.live_sender("sender-a")
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            code, out = self.cli("say", "--notice", "devcloud", "@%s from a session" % sid[:8])
        self.assertEqual(code, 2, out)
        self.assertIn("--notice marks a notice of a machine's own program, and a session is not one: drop it", out)
        self.assertEqual(self.events("from a session"), [])

    def test_a_value_outside_the_pattern_is_refused(self):
        sid = self.live_sender("sender-a")
        for value in ("DevCloud", "dev cloud", "x" * 33, "9x", "dev_cloud", ""):
            for session in ("", sid):
                with self.subTest(value=value, session=session):
                    text = "odd %r %s" % (value, session[:8])
                    env = {"CLAUDE_CODE_SESSION_ID": session} if session else {}
                    with mock.patch.dict(os.environ, env):
                        argv = ["--in", self.p.id] if not session else []
                        code, out = self.cli("say", "--notice", value, *argv, text)
                    self.assertEqual(code, 2, out)
                    self.assertIn("--notice names the program that speaks, as a lower-case word of letters, digits "
                                  "and hyphens (32 at most): %s" % value, out)
                    self.assertEqual(self.events(text), [], "nothing appended")

    def test_a_project_named_by_its_id_where_two_logs_share_its_name(self):
        roots = []
        for d in ("twin-a", "twin-b"):
            root = self.repo(d)
            subprocess.run([sys.executable, "-B", SCRIPT, "project", "init", "--name", "twin"], cwd=root, check=True,
                           capture_output=True)
            roots.append(root)
        a, b = (self.project_of(r) for r in roots)
        self.assertEqual((a.name, b.name), ("twin", "twin"))
        self.assertNotEqual(a.id, b.id)
        self.session(root=roots[0], name="twin-live")
        self.reconcile(a)
        code, out = self.say_notice("--project", a.id, "to the id's log")
        self.assertEqual(code, 0, out)
        code, out = self.say_notice("--in", b.id, "a note in b")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.events("to the id's log", a)), 1)
        self.assertEqual(self.events("to the id's log", b), [])
        self.assertEqual(len(self.events("a note in b", b)), 1)
        self.assertEqual(self.events("a note in b", a), [])


# ------------------------------------------------------------ what a reader shows


class Shown(Notices):
    def test_the_frames_first_line_names_the_notice_sender_and_one_ref(self):
        sid, _ = self.session()
        e = self.notice(sid, "devcloud on vm: idle 3d")
        first = sminos.frame_of(self.p, e, sminos.log_read(self.p), sid, {}).split("\n", 1)[0]
        m = re.fullmatch(r"\[sminos chat (\S+) (\S+) from devcloud@testhost → @you(?: \| unread \d+)?\]", first)
        self.assertIsNotNone(m, first)
        self.assertEqual(m.group(1), self.p.name)
        self.assertTrue(m.group(2).endswith(":%d" % e["seq"]), "one token ending :<seq>")

    def test_a_notice_carrying_a_msg_id_is_still_the_chat_frame_and_is_found_landed_as_one(self):
        sid, _ = self.session()
        e = sminos.log_append(self.p, HUMAN, "human", **{"from": "human", "to": [{"session": sid, "alias": "x"}],
                                                         "text": "devcloud on vm: with an id", "notice": "devcloud",
                                                         "msg_id": "abc12345"})
        frame = sminos.frame_of(self.p, e, sminos.log_read(self.p), sid, {})
        self.assertTrue(frame.startswith("[sminos chat %s %s from devcloud@testhost → @you"
                                         % (self.p.name, sminos.event_ref(e))), frame)
        self.assertNotIn("[sminos message from", frame)
        seen = []

        def holds(session, needle, match):
            seen.append(needle)
            return match(frame)
        with mock.patch.object(sminos, "_transcript_holds", holds):
            self.assertTrue(sminos.frame_landed(self.p, sid, e), "the chat frame, found by its head and its text")
        self.assertEqual(seen, [(" %s from " % sminos.event_ref(e)).encode()], "looked for as a chat frame")
        unmarked = dict(e, notice="")
        self.assertTrue(sminos.frame_of(self.p, unmarked, sminos.log_read(self.p), sid, {}).startswith(
            "[sminos message from human id=abc12345]"), "an unmarked one keeps a send's frame")

    def test_the_label_follows_the_sender_as_sender_labels_gives_it(self):
        sid, _ = self.session()
        e = self.notice(sid, "with a label")
        with mock.patch.object(sminos, "sender_labels", lambda project: lambda x: " (unverified)"):
            first = sminos.frame_of(self.p, e, sminos.log_read(self.p), sid, {}).split("\n", 1)[0]
        self.assertTrue(first.startswith("[sminos chat %s %s from devcloud@testhost (unverified) → @you"
                                         % (self.p.name, sminos.event_ref(e))), first)

    def test_a_retrys_pointer_chat_and_the_tui_name_the_same_sender(self):
        sid, _ = self.session()
        e = self.notice(sid, "devcloud on vm: shown")
        self.assertTrue(sminos.holder_wake(self.p, e).startswith(
            "[sminos chat %s %s from devcloud@testhost → @you, again]" % (self.p.name, sminos.event_ref(e))))
        self.assertIn(" %s devcloud@testhost → @x  devcloud on vm: shown" % sminos.event_ref(e), sminos.chat_line(e))
        code, out = self.cli("chat", "-n", "5")
        self.assertIn("devcloud@testhost → @x  devcloud on vm: shown", out)
        self.assertIn(" devcloud@testh ", tui.chat_row(e), "the panel's column, cut to its width as any sender")
        head = tui.overlay_lines({"overlay": ("message", e)}, 80)[0]
        self.assertIn(" · devcloud@testhost → @x · ", head)
        plain = dict(e, notice="")
        self.assertIn(" human → @x ", sminos.chat_line(plain), "an unmarked one as before")
        self.assertIn(" · human → ", tui.overlay_lines({"overlay": ("message", plain)}, 80)[0])


# ------------------------------------------------------------ the route


class Route(Notices):
    def setUp(self):
        super().setUp()
        self.supervised = []
        for name, fake in (("supervisor_reply", lambda short, text, session: self.supervised.append(text) or True),
                           ("bg_job", lambda peer: "abcd1234")):
            p = mock.patch.object(control, name, side_effect=fake)
            p.start()
            self.addCleanup(p.stop)

    def push(self, sid, e, words):
        frame = sminos.frame_of(self.p, e, sminos.log_read(self.p), sid, {})
        control.push_live(sminos.peer_for_session(sid), sid, frame, e, self.p.id, words=words)
        return frame

    def test_a_notice_takes_the_inbox_for_every_verdict_and_never_the_bridge_or_a_supervisor(self):
        took = self.bridge()
        for words in (True, False, None):
            with self.subTest(words=words):
                sid = str(uuidlib.uuid4())
                received = self.terminal(sid)
                e = self.notice(sid, "devcloud on vm: %s" % words)
                frame = self.push(sid, e, words)
                [got] = self.received(received)
                name, body = envelope(got)
                self.assertEqual(name, "devcloud@testhost")
                self.assertEqual(body, frame, "the frame and no reply line")
                self.assertNotIn("[To reply", got)
        self.assertEqual((took, self.supervised), ([], []), "neither the bridge nor a supervisor")

    def test_the_same_event_unmarked_takes_the_bridge_as_before(self):
        took = self.bridge()
        sid = str(uuidlib.uuid4())
        received = self.terminal(sid)
        e = sminos.log_append(self.p, HUMAN, "human", **{"from": "human", "to": [{"session": sid, "alias": "x"}],
                                                         "text": "the owner's words"})
        self.push(sid, e, True)
        self.assertEqual([c[1]["seq"] for c in took], [e["seq"]])
        self.assertEqual(self.received(received), [])

    def test_a_receipts_marker_goes_first_then_the_notice_frame(self):
        sid = str(uuidlib.uuid4())
        received = self.terminal(sid)
        e = self.notice(sid, "devcloud on vm: with a receipt")
        frame = sminos.frame_of(self.p, e, sminos.log_read(self.p), sid, {})
        marker = sminos.holder_module().marker("a" * 24 + "." + "b" * 16, 1)
        control.push_live(sminos.peer_for_session(sid), sid, frame, e, self.p.id, words=True, marker=marker)
        [got] = self.received(received)
        name, body = envelope(got)
        self.assertEqual((name, body), ("devcloud@testhost", marker + "\n" + frame))

    def test_an_addressed_notice_wakes_a_stopped_thread_and_its_frame_carries_the_wakes_line(self):
        took = self.bridge()
        tid, sid = self.human_thread()
        code, out = self.say_notice("@%s devcloud on vm: idle 3d" % sid[:8])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.shown(out, sid), ["sent (woken)"])
        self.assertEqual(self.resumes(sid), [FLAGS], "one wake")
        [got] = self.frames(sid)
        name, _ = envelope(got)
        self.assertEqual(name, "devcloud@testhost")
        pushed, said = line_of(got)
        self.assertTrue(pushed.startswith("[sminos chat %s " % self.p.name) and " from devcloud@testhost → @you"
                        in pushed.split("\n", 1)[0], pushed)
        self.assertTrue(said.startswith(wake.LINE_HEAD), "the wake's line after the frame")
        self.assertNotIn("[To reply", got)
        self.assertEqual((took, self.supervised), ([], []))
        self.assertEqual(self.owed(sid), [])


# ------------------------------------------------------------ a direct send's runs


class Runs(Notices):
    """On a machine not cut over: an operator's verb goes by the bridge as the owner's words, and a notice its
    writer still owes the same session goes ahead of it as a push of its own, from devcloud@testhost."""

    def test_send_to_a_live_session_pushes_the_notice_then_the_verb_each_once(self):
        took = self.bridge()
        sid = str(uuidlib.uuid4())
        received = self.terminal(sid)
        e = self.notice(sid, "devcloud on vm: owed")
        code, out = self.send(sid[:8], "the operator's send")
        self.assertEqual(code, 0, out)
        [got] = self.received(received)
        self.assertEqual(envelope(got)[0], "devcloud@testhost")
        self.assertIn("devcloud on vm: owed", got)
        self.assertNotIn("the operator's send", got)
        [(_, routed, text)] = took
        self.assertIn("the operator's send", text)
        self.assertNotIn("devcloud on vm: owed", text)
        [mine] = self.logged("the operator's send")
        self.assertEqual(routed["seq"], mine["seq"])
        self.assertLess(e["seq"], mine["seq"])
        self.assertEqual(self.settled(sid), mine["seq"], "settled past both once both landed")
        self.assertEqual(self.owed(sid), [])

    def test_a_second_push_that_fails_leaves_the_notice_settled_and_the_verb_owed(self):
        self.bridge()
        sid = str(uuidlib.uuid4())
        self.terminal(sid)
        e = self.notice(sid, "devcloud on vm: first run")
        real, seen = control.push_live, []

        def push_live(peer, session, text, event=None, *a, **k):
            seen.append(event["seq"])
            if len(seen) == 2:
                raise sminos.SendFailed("before", "the session went away")
            return real(peer, session, text, event, *a, **k)
        with mock.patch.object(control, "push_live", push_live):
            code, out = self.send(sid[:8], "never handed over")
        self.assertEqual(code, 4, out)
        self.assertEqual(self.settled(sid), e["seq"], "the notice's alone")
        self.assertEqual(self.owed(sid), ["never handed over"])

    def uncertain_at(self, n):
        """control.push_live failing after its write at the n-th push of this call."""
        real, seen = control.push_live, []

        def push_live(peer, session, text, event=None, *a, **k):
            seen.append(event["seq"])
            real(peer, session, text, event, *a, **k)
            if len(seen) == n:
                raise sminos.SendFailed("after", "the close-out failed")
        return mock.patch.object(control, "push_live", push_live)

    def test_an_uncertain_notice_run_names_itself_and_leaves_the_verb_queued(self):
        self.bridge()
        sid = str(uuidlib.uuid4())
        self.terminal(sid)
        e = self.notice(sid, "devcloud on vm: uncertain")
        with self.uncertain_at(1):
            code, out = self.send(sid[:8], "still queued")
        self.assertEqual(code, 1, out)
        [mine] = self.logged("still queued")
        self.assertIn("is UNCERTAIN for %s, pushed ahead of this message" % sminos.event_ref(e), out)
        self.assertIn("This message (id=%s) was not pushed: it stays queued, and the daemon delivers it"
                      % mine["msg_id"], out)
        self.assertNotIn("do not blindly re-send", out)
        self.assertEqual(self.settled(sid), e["seq"], "the uncertain run settled, never pushed again")
        self.assertEqual(self.owed(sid), ["still queued"])

    def test_an_uncertain_last_run_says_what_it_said_before(self):
        self.bridge()
        sid = str(uuidlib.uuid4())
        self.terminal(sid)
        self.notice(sid, "devcloud on vm: lands")
        with self.uncertain_at(2):
            code, out = self.send(sid[:8], "the verb itself")
        self.assertEqual(code, 1, out)
        self.assertIn("the frame was written but the close-out failed (the close-out failed); do not blindly re-send",
                      out)
        self.assertNotIn("pushed ahead of this message", out)
        self.assertEqual(self.owed(sid), [])

    def test_send_wait_pushes_both_and_returns_the_reply_to_its_own_message(self):
        took = self.bridge(took=False)
        code, out = self.cli("spawn", "w", "the task")
        self.assertEqual(code, 0, out)
        s = next(x for x in sminos.seats() if x["alias"] == "w")
        sid = s["current"]
        self.assertTrue(wait_for(lambda: self.record(sid) is not None))
        self.assertTrue(wait_for(lambda: self.record(sid)["status"] == "idle", timeout=30))
        before = len(self.frames(sid))
        e = self.notice(sid, "devcloud on vm: before the wait", alias="w")
        code, out = self.cli("send", "w", "waited on", "--wait")
        self.assertEqual(code, 0, out)
        [mine] = self.logged("waited on")
        self.assertIn("reply to %s" % mine["msg_id"], out)
        frames = self.frames(sid)[before:]
        self.assertEqual([envelope(f)[0] for f in frames], ["devcloud@testhost", "human"], "two pushes, in order")
        self.assertIn("devcloud on vm: before the wait", frames[0])
        self.assertIn("id=%s" % mine["msg_id"], frames[1])
        self.assertEqual([c[1]["seq"] for c in took], [mine["seq"]], "the bridge offered the verb's alone")
        self.assertEqual(self.settled(sid), mine["seq"])
        self.assertLess(e["seq"], mine["seq"])

    def test_resume_of_a_stopped_seat_wakes_it_once_and_pushes_both(self):
        took = self.bridge()
        s = self.seat()
        sid = s["current"]
        launched = self.launches()
        e = self.notice(sid, "devcloud on vm: while stopped", alias="w")
        code, out = self.cli("resume", "w", "start over")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.launches(), launched + 1, "one wake")
        self.assertTrue(wait_for(lambda: self.frames(sid)))
        notices = [f for f in self.frames(sid) if "devcloud on vm: while stopped" in f]
        self.assertEqual(len(notices), 1)
        self.assertEqual(envelope(notices[0])[0], "devcloud@testhost")
        self.assertNotIn("start over", "".join(self.frames(sid)))
        [(_, routed, text)] = took
        self.assertIn("start over", text)
        self.assertNotIn("while stopped", text)
        self.assertEqual(self.settled(sid), routed["seq"])
        self.assertLess(e["seq"], routed["seq"])

    def test_a_held_thread_pushes_nothing_marks_both_and_the_wait_exits_4(self):
        tid, sid = self.human_thread("plan")
        e = self.notice(sid, "devcloud on vm: held too")
        code, out = self.cli("send", sid[:8], "held send", "--wait")
        self.assertEqual(code, 4, out)
        self.assertIn(line("mode"), out)
        [mine] = self.logged("held send")
        self.assertEqual({seq for _, seq in self.marked(sid)}, {e["seq"], mine["seq"]})
        self.assertEqual(self.frames(sid), [])
        self.assertEqual(self.resumes(sid), [])

    def test_with_no_notice_queued_each_verb_makes_its_one_push(self):
        took = self.bridge()
        sid = str(uuidlib.uuid4())
        received = self.terminal(sid)
        code, out = self.send(sid[:8], "alone")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(took), 1)
        self.assertEqual(self.received(received), [])
        s = self.seat()
        code, out = self.cli("resume", "w", "alone again")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(took), 2)
        self.assertIn("alone again", took[1][2])


# ------------------------------------------------------------ say --exit-held


class ExitHeld(Notices):
    def held_case(self, why):
        """A local thread held for `why`; its session."""
        if why == "failed":
            tid, sid = self.human_thread()
            self.switch("fail-job")
            return sid
        mode = "plan" if why == "mode" else "auto"
        tid, sid = self.human_thread(mode)
        if why == "cwd":
            self.edit(tid, launch={"cwd": os.path.join(self.home, "gone"), "at": sminos.now()})
        elif why == "transcript":
            os.unlink(sminos.transcript_now(sid))
        elif why == "config":
            self.foreign(sid)
        elif why == "protected":
            self.edit(tid, launch={"cwd": self.vault(), "at": sminos.now()})
        sminos.forget_caches()
        return sid

    def both(self, tag, text):
        """(exit, out) with --exit-held, then without it, of one tagged say each."""
        flagged = self.cli("say", "--exit-held", "%s %s (flag)" % (tag, text))
        plain = self.cli("say", "%s %s (plain)" % (tag, text))
        return flagged, plain

    def test_a_local_thread_held_for_each_reason_exits_3_with_the_line_unchanged(self):
        for why in ("config", "transcript", "cwd", "protected", "mode", "failed"):
            with self.subTest(why=why):
                sid = self.held_case(why)
                (code, out), (plain_code, plain_out) = self.both("@%s" % sid[:8], "held for %s" % why)
                self.assertEqual(code, 3, out)
                self.assertEqual(self.shown(out, sid), [line(why)])
                self.assertEqual((plain_code, self.shown(plain_out, sid)), (0, [line(why)]), "without it: as today")
                self.assertTrue(self.owes(sid, "held for %s (flag)" % why), "recorded")
                if why == "failed":
                    os.unlink(os.path.join(self.state, "fail-job"))

    def test_a_hold_that_passes_a_live_one_and_a_woken_one_exit_0(self):
        tid, sid = self.human_thread()
        self.switch("late-inbox", 5)
        code, out = self.cli("say", "--exit-held", "@%s soon" % sid[:8])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.shown(out, sid), [STARTING])
        os.unlink(os.path.join(self.state, "late-inbox"))
        tid, woken = self.human_thread()
        code, out = self.cli("say", "--exit-held", "@%s wake up" % woken[:8])
        self.assertEqual((code, self.shown(out, woken)), (0, ["sent (woken)"]), out)
        live = str(uuidlib.uuid4())
        self.terminal(live)
        code, out = self.cli("say", "--exit-held", "@%s you run" % live[:8])
        self.assertEqual((code, self.shown(out, live)), (0, ["sent"]), out)

    def remote(self, wake_value, why=None):
        sid = str(uuidlib.uuid4())
        w = "elsewhere/%s" % sid
        sminos.log_append(self.p, w, "joined", session=sid, alias="far", name_source="user", machine="elsewhere",
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive",
                          thread=str(uuidlib.uuid4()))
        sminos.log_append(self.p, w, "state", session=sid, state="stopped", machine="elsewhere",
                          **({"wake": wake_value} if wake_value else {}), **({"why": why} if why else {}))
        sminos.forget_caches()
        return sid

    def test_another_machines_published_hold_exits_3_and_woken_or_nothing_0(self):
        cases = [(("held", why), 3) for why in list(WORDS) + ["read-only", None]]
        cases += [(("woken", None), 0), ((None, None), 0)]
        for (value, why), want in cases:
            with self.subTest(wake=value, why=why):
                sid = self.remote(value, why)
                (code, out), (plain_code, plain_out) = self.both("@far#%s" % sid[:8], "far away")
                self.assertEqual(code, want, out)
                self.assertEqual(plain_code, 0, plain_out)
                self.assertEqual(out.splitlines()[1:], plain_out.splitlines()[1:], "the same line for it")

    def test_an_ended_thread_and_no_member_exit_4_with_nothing_recorded(self):
        tid, sid = self.human_thread()
        code, out = self.cli("retire", sid[:8])
        self.assertEqual(code, 0, out)
        for tag in ("@%s" % sid[:8], "@nobody-here"):
            for flag in (["--exit-held"], []):
                with self.subTest(tag=tag, flag=flag):
                    code, out = self.cli("say", *flag, "%s gone %s" % (tag, flag))
                    self.assertEqual(code, 4, out)
                    self.assertEqual(self.logged("%s gone %s" % (tag, flag)), [])

    def test_two_recipients_one_held_exits_3(self):
        held = self.held_case("mode")
        live = str(uuidlib.uuid4())
        self.terminal(live)
        code, out = self.cli("say", "--exit-held", "@%s @%s both of you" % (held[:8], live[:8]))
        self.assertEqual(code, 3, out)
        code, out = self.cli("say", "--exit-held", "@%s just you" % live[:8])
        self.assertEqual(code, 0, out)

    def test_untagged_the_flag_changes_nothing(self):
        code, out = self.cli("say", "--exit-held", "--in", self.p.id, "a note")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
