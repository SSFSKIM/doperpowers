#!/usr/bin/env python3
"""A session's reach set by its owner, and unlisting (P5 O18 M4; MAWS's
docs/doperpowers/plans/2026-11-05-p5-o18-message-reach.md D6, D10,
Interfaces §C): `sminos access` and `sminos share` through set_visibility
(narrowing from any shell, widening only from the operator's terminal,
confirmed at /dev/tty); the transition a change writes once the endpoint
gives the session's audience at its new policyRev (the `unlisted` notice of
the members it withdrew, then the snapshot under the new stream, the notice
first in upload order); and the reader's projection dropping a session at a
notice it sees, through the hub stand-in's filter.

Each test is a fresh machine (test_words.Machine: its own HOME and
SMINOS_HOME), `testhost` of org-1, cut over to its endpoint. The CLI runs as
a subprocess; a confirming terminal is a real controlling pty (pty.fork).
The uplink's side is one Link on a lane that keeps what it is sent, its
endpoint's frames dispatched to it.

Run: python3 -B sminos/tests/test_visibility.py
"""

import json
import os
import pty
import select
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_words as tw  # noqa: E402 — its machine: HOME, SMINOS_HOME, the enrollment, sessions, a Link
import test_reach as tr  # noqa: E402 — the hub stand-in as two machines meet it over DX2

import endpoint_standin  # noqa: E402
import sminos  # noqa: E402
import sminos_audience as au  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_records as records  # noqa: E402
import sminos_visibility as vis  # noqa: E402

SCRIPTS = tw.SCRIPTS
A, B, C = "a" * 32, "b" * 32, "c" * 32          # member ids; A owns this machine's sessions
S = "6d0000a1-0000-4000-8000-0000000000a1"      # a local session (short 6d0000a1)
U = "6d0000b2-0000-4000-8000-0000000000b2"      # another machine's session
OTHER = "othermachine"
WIDENING = "widening reach needs its owner: run this in a terminal, or use MAWS"


def stream(sid, members, machine="testhost"):
    return "%s/%s~%s" % (machine, sid, sminos.audience_digest(members))


class Base(tw.Machine):
    def setUp(self):
        super().setUp()
        self.cut_over()
        self.p = self.project("work", hub=True)
        au.keep_capabilities(["access", "reach"])

    def audience(self, sid, owners, members=None, rev=0, **extra):
        self.assertTrue(au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(sid, owners, members, rev),
                                          **extra}))

    def local(self, sid, access="listed", shares=(), grade="list"):
        """A session of this machine owned by A with a final record, that
        policy set, and the endpoint's word on its audience at its policyRev."""
        records.establish(sid, {**records.default_provenance("launch"), "owners": [A]})
        if access != "listed" or shares:
            records.set_policy(sid, lambda _a, _s: (access, [{"member": m, "grade": grade} for m in shares]))
        rec = records.read(sid)
        self.audience(sid, [A], sorted({A, *shares}) if access == "private" else None, rec.get("policyRev", 0))
        return rec

    def policy(self, sid=S):
        sminos.forget_caches()
        return au.policy_of(records.read(sid))

    def env(self, session=None, home=None):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        if session:
            env["CLAUDE_CODE_SESSION_ID"] = session
        return env

    def cli(self, *args, session=None):
        """The CLI with no controlling terminal (a new session: /dev/tty
        cannot be opened), from an agent's shell when `session` is given."""
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), *args], cwd=self.p.root,
                              env=self.env(session), capture_output=True, text=True, timeout=60,
                              start_new_session=True)

    def tty(self, answer, *args):
        """The CLI on a controlling pty of its own, the operator answering
        `answer` at the confirmation. (exit code, everything it printed)."""
        env = self.env()
        pid, fd = pty.fork()
        if pid == 0:
            try:
                os.chdir(self.p.root)
                os.execve(sys.executable, [sys.executable, "-B", str(SCRIPTS / "sminos.py"), *args], env)
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
        return os.waitstatus_to_exitcode(status), out.decode("utf-8", "replace")

    def remote(self, sid, alias, owners=(B,)):
        e = {"ts": "2026-11-05T01:00:00.000Z", "writer": "%s/%s" % (OTHER, sid), "seq": 1, "kind": "joined",
             "session": sid, "alias": alias, "name_source": "set", "machine": OTHER, "cwd": "/w", "worktree": "",
             "role": "", "seat": "", "by": "", "session_kind": "interactive", "owners": list(owners),
             "origin": {"kind": "terminal"},
             "verified": {"signer": {"kind": "machine", "ref": "ref-o", "name": OTHER, "keyId": "k"},
                          "owners": [{"id": o, "email": "%s@example.org" % o[0]} for o in owners]}}
        self.assertEqual(hublog.append_verbatim(self.p, e), "appended")
        sminos.forget_caches()

    def events(self, writer):
        try:
            return tw.read_lines(sminos.writer_path(self.p, writer))
        except FileNotFoundError:
            return []


# ------------------------------------------------------------- the setters


class Setters(Base):
    def test_acceptance_8_an_agents_shell_narrows_and_never_widens(self):
        """From an agent's shell: a share and going listed are refused, going
        private succeeds."""
        self.local(S)
        got = self.cli("share", S, B, "view", session=S)
        self.assertNotEqual(got.returncode, 0)
        self.assertIn(WIDENING, got.stderr)
        self.assertEqual(self.policy(), ("listed", [], 0), "nothing written")
        got = self.cli("access", S, "private", session=S)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(self.policy(), ("private", [], 1))
        self.assertIn("private", got.stdout)
        self.assertIn("policyRev 1", got.stdout)
        got = self.cli("access", S, "listed", session=S)
        self.assertNotEqual(got.returncode, 0)
        self.assertIn(WIDENING, got.stderr)
        self.assertEqual(self.policy(), ("private", [], 1), "still private")

    def test_narrowing_is_any_shells_lowering_access_a_grade_or_removing_a_share(self):
        self.local(S, access="org-converse")
        self.assertEqual(self.cli("access", S, "org-view", session=S).returncode, 0)
        records.set_policy(S, lambda a, s: (a, [{"member": B, "grade": "approve"}]))
        got = self.cli("share", S, B, "list", session=S)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(self.policy()[1], [{"member": B, "grade": "list"}])
        self.assertEqual(self.cli("share", S, B, "none", session=S).returncode, 0)
        self.assertEqual(self.policy()[1], [])

    def test_the_operator_widens_from_a_terminal_that_confirms(self):
        self.local(S, access="private")
        code, out = self.tty("n", "access", S, "listed")
        self.assertNotEqual(code, 0, out)
        self.assertEqual(self.policy()[0], "private", "declined: nothing written")
        got = self.cli("access", S, "listed")
        self.assertNotEqual(got.returncode, 0)
        self.assertIn("terminal", got.stderr, "no terminal to confirm at")
        self.assertEqual(self.policy()[0], "private")
        code, out = self.tty("y", "share", S, B, "view")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.policy()[1], [{"member": B, "grade": "view"}])
        code, out = self.tty("y", "access", S, "listed")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.policy()[0], "listed")

    def test_a_change_with_nothing_to_change_writes_nothing(self):
        rec = self.local(S, access="private")
        got = self.cli("access", S, "private", session=S)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(self.policy()[2], rec["policyRev"], "no policyRev bumped")
        self.assertEqual(vis.transitions(), {}, "no transition")

    def test_an_endpoint_without_access_takes_only_listed(self):
        au.keep_capabilities([])
        self.local(S)
        got = self.cli("access", S, "private", session=S)
        self.assertNotEqual(got.returncode, 0)
        self.assertIn("access", got.stderr)
        self.assertEqual(self.policy(), ("listed", [], 0))
        self.assertEqual(self.cli("access", S, "listed", session=S).returncode, 0, "a no-op is no change")
        records.set_policy(S, lambda a, s: ("private", s))   # private from before the endpoint lost it
        code, out = self.tty("y", "access", S, "listed")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.policy()[0], "listed", "going listed: what it can carry")

    def test_another_machines_session_is_refused_naming_its_machine(self):
        self.remote(U, "bob")
        got = self.cli("access", "bob", "private", session=S)
        self.assertNotEqual(got.returncode, 0)
        self.assertIn(OTHER, got.stderr)

    def test_a_member_by_its_alias_and_a_person_by_an_email_this_machine_holds(self):
        self.session(self.p, S, name="kept")
        self.local(S, access="private", shares=(B,))
        sminos.view_of(self.p)
        self.remote(U, "bob", owners=(B,))   # its verified owners: B as b@example.org
        got = self.cli("share", "kept", "b@example.org", "none", session=S)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(self.policy()[1], [])
        got = self.cli("share", "kept", "nobody@example.org", "none", session=S)
        self.assertNotEqual(got.returncode, 0)
        self.assertIn("id", got.stderr, "asked for the member's id")

    def test_two_setters_racing_leave_the_pending_transition_at_the_records_revision(self):
        """The second setter runs between the first's policy write and its
        pending entry: one lock serializes both, so the entry kept is the
        latest revision's, its previous audience the one before the
        earliest change the endpoint has not answered."""
        rec = self.local(S, access="private", shares=(B, C))
        real, box = records.set_policy, {}

        def first_paused(sid, mutate, deadline=None):
            out = real(sid, mutate, deadline)
            if "second" not in box:
                box["second"] = threading.Thread(target=lambda: vis.set_visibility(S, share=(C, None), operator=False))
                box["second"].start()
                box["second"].join(0.5)
            return out
        with mock.patch.object(records, "set_policy", side_effect=first_paused):
            vis.set_visibility(S, share=(B, None), operator=False)
        box["second"].join(10)
        rev = records.read(S)["policyRev"]
        self.assertEqual(rev, rec["policyRev"] + 2)
        t = vis.transitions()[S]
        self.assertEqual((t["policyRev"], t["previous"]), (rev, [A, B, C]))
        self.assertEqual(vis.withdrawn_of(t, {"members": [A], "policyRev": rev}), ([B, C], ""),
                         "both changes' withdrawn members")


# ------------------------------------------------------------- the transition


class Transitions(Base):
    def setUp(self):
        super().setUp()
        self.session(self.p, S, name="kept")

    def start(self, access="private", shares=()):
        """S with that policy, joined (its snapshot under its stream), and a
        Link that has published its member frame."""
        rec = self.local(S, access=access, shares=shares)
        sminos.view_of(self.p)
        link = self.link()
        link.welcomed_rl10({"t": "welcome", "capabilities": ["access", "reach"], "policy": None})
        link.members(0.0)
        link.log_lane.take()
        return link, rec

    def published(self, link, rev):
        """The member frame of S at `rev` published (what the endpoint answers
        with its audience frame)."""
        link.members(0.0)
        frames = [f for f in link.log_lane.take() if f.get("t") == "member" and f.get("session") == S]
        self.assertEqual([f.get("policyRev") for f in frames], [rev])

    def answer(self, link, members, rev, **extra):
        link.dispatch({"t": "audience", **endpoint_standin.audience_frame(S, [A], members, rev), **extra}, None)

    def kinds(self, writer):
        return [e["kind"] for e in self.events(writer)]

    def upload_order(self):
        """This machine's own events in the order an upload draws them."""
        hl = hublog.HubLog(self.p, {"key": None, "machine": "testhost"}, coded=False)
        hl.have = {}
        return [(e["writer"], e["kind"]) for frame, _ in hl.uploads() for e in frame["events"]]

    def check_notice_first(self, notice, snapshot):
        order = self.upload_order()
        self.assertLess(order.index((notice, "unlisted")), order.index((snapshot, "joined")),
                        "the notice goes up before the snapshot: %r" % order)

    def test_removing_one_share_unlists_it_to_that_member_alone(self):
        link, rec = self.start(shares=(B, C))
        self.assertEqual(self.kinds(stream(S, [A, B, C])), ["joined"])
        out = vis.set_visibility(S, share=(B, None), operator=False)
        rev = rec["policyRev"] + 1
        self.assertEqual(out["record"]["policyRev"], rev)
        t = vis.transitions()[S]
        self.assertEqual((t["policyRev"], t["previous"]), (rev, [A, B, C]), "the previous audience as known then")
        self.assertEqual(self.kinds(stream(S, [B])), [], "nothing before the endpoint's word")
        self.published(link, rev)
        self.answer(link, [A, C], rev)
        notice = self.events(stream(S, [B]))
        self.assertEqual([{k: e[k] for k in ("kind", "session")} for e in notice], [{"kind": "unlisted", "session": S}])
        self.assertFalse({"audience", "policyRev", "text", "to"} & set(notice[0]), "content-free; the endpoint signs")
        self.assertEqual(au.stream_audience(self.p, stream(S, [B])), [B], "its stream's audience kept")
        snap = self.events(stream(S, [A, C]))
        self.assertEqual([e["kind"] for e in snap], ["joined", "state"], "then the snapshot, in the new stream")
        self.assertLess(notice[0]["ts"], snap[0]["ts"])
        done = vis.transitions()[S]
        self.assertEqual(done["notice"], stream(S, [B]))
        self.assertTrue(done.get("done"))
        self.check_notice_first(stream(S, [B]), stream(S, [A, C]))

    def test_the_endpoints_withdrawn_set_names_the_notices_stream(self):
        link, rec = self.start(shares=(B, C))
        vis.set_visibility(S, share=(B, None), operator=False)
        rev = rec["policyRev"] + 1
        os.unlink(vis.transitions_path())   # the previous audience lost: the endpoint's word alone
        vis.set_pending(S, {"policyRev": rev, "access": "private"})
        self.published(link, rev)
        self.answer(link, [A, C], rev, withdrawn=[B])
        self.assertEqual(self.kinds(stream(S, [B])), ["unlisted"])
        self.assertEqual(au.entry_of(S)["withdrawn"], [B], "kept with its entry")

    def test_going_private_unlists_it_to_everyone_else_when_the_endpoint_names_them(self):
        link, rec = self.start(access="listed")
        out = self.cli("access", S, "private", session=S)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("pending", out.stdout, "no daemon runs: the notice and snapshot are pending")
        rev = rec.get("policyRev", 0) + 1
        self.assertIsNone(vis.transitions()[S]["previous"], "listed: the whole org")
        self.published(link, rev)
        self.answer(link, [A], rev, withdrawn=[B, C])
        self.assertEqual(self.kinds(stream(S, [B, C])), ["unlisted"])
        self.assertEqual(self.kinds(stream(S, [A])), ["joined", "state"])
        self.check_notice_first(stream(S, [B, C]), stream(S, [A]))

    def test_going_private_without_the_withdrawn_set_writes_the_snapshot_and_says_why_no_notice(self):
        link, rec = self.start(access="org-view")
        vis.set_visibility(S, access="private", operator=False)
        rev = rec.get("policyRev", 0) + 1
        self.published(link, rev)
        self.answer(link, [A], rev)
        self.assertEqual(self.kinds(stream(S, [A])), ["joined", "state"])
        self.assertEqual([n for n in os.listdir(os.path.join(self.p.home, "log")) if "unlisted" in Path(
            self.p.home, "log", n).read_text()], [], "no notice anywhere")
        self.assertIn("no unlisted notice for session %s at policyRev %d" % (S[:8], rev), tw.daemon_log())
        self.assertEqual(vis.transitions()[S]["notice"], "")

    def test_a_new_share_or_a_raised_grade_writes_the_snapshot_alone(self):
        link, rec = self.start()
        vis.set_visibility(S, share=(B, "list"), operator=True)
        self.published(link, rec["policyRev"] + 1)
        self.answer(link, [A, B], rec["policyRev"] + 1)
        self.assertEqual(self.kinds(stream(S, [A, B])), ["joined", "state"])
        vis.set_visibility(S, share=(B, "view"), operator=True)
        self.published(link, rec["policyRev"] + 2)
        self.answer(link, [A, B], rec["policyRev"] + 2)
        self.assertEqual(self.kinds(stream(S, [A, B])), ["joined", "state", "joined", "state"])
        self.assertFalse([w for w in au.streams_of(self.p) if w not in (stream(S, [A]), stream(S, [A, B]))],
                         "no notice: nobody withdrawn")

    def test_lowering_a_grade_withdraws_nobody(self):
        link, rec = self.start(shares=(B,))
        records.set_policy(S, lambda a, s: (a, [{"member": B, "grade": "approve"}]))
        self.audience(S, [A], [A, B], rec["policyRev"] + 1)
        vis.set_visibility(S, share=(B, "list"), operator=False)
        self.published(link, rec["policyRev"] + 2)
        self.answer(link, [A, B], rec["policyRev"] + 2)
        self.assertEqual(vis.transitions()[S]["notice"], "")
        self.assertEqual(self.kinds(stream(S, [A, B]))[-2:], ["joined", "state"])

    def test_going_listed_writes_the_snapshot_under_its_plain_writer(self):
        link, rec = self.start()
        vis.set_visibility(S, access="listed", operator=True)
        self.published(link, rec["policyRev"] + 1)
        self.answer(link, None, rec["policyRev"] + 1)
        self.assertEqual(self.kinds("testhost/" + S)[-2:], ["joined", "state"])
        self.assertEqual(vis.transitions()[S]["notice"], "")

    def test_an_audience_kept_before_a_restart_completes_the_transition_at_the_tick(self):
        link, rec = self.start(shares=(B,))
        vis.set_visibility(S, share=(B, None), operator=False)
        self.audience(S, [A], [A], rec["policyRev"] + 1)   # kept, and the uplink stopped before it wrote anything
        link.members(0.0)
        link.complete_transitions()
        self.assertEqual(self.kinds(stream(S, [B])), ["unlisted"])
        self.assertEqual(self.kinds(stream(S, [A])), ["joined", "state"])
        before = len(os.listdir(os.path.join(self.p.home, "log")))
        link.complete_transitions()
        self.assertEqual(len(os.listdir(os.path.join(self.p.home, "log"))), before, "done once")

    def test_an_audience_at_another_policyrev_completes_nothing(self):
        link, rec = self.start(shares=(B,))
        vis.set_visibility(S, share=(B, None), operator=False)
        self.answer(link, [A, B], rec["policyRev"])   # the old one, restated after a welcome
        self.assertFalse(vis.transitions()[S].get("done"))
        self.assertEqual(self.kinds(stream(S, [B])), [])

    def test_a_draw_suspended_mid_batch_sends_the_notice_in_or_before_its_snapshots_frame(self):
        """An upload drawn before the transition and suspended between
        frames is drawn again after it, so the notice's writer goes first and
        the snapshot, under a stream that already had events, never ahead."""
        link, rec = self.start(shares=(C,))
        vis.set_visibility(S, share=(B, "list"), operator=True)
        self.published(link, rec["policyRev"] + 1)
        self.answer(link, [A, B, C], rec["policyRev"] + 1)
        early = "testhost/00000000-0000-4000-8000-000000000000"   # sorts before every stream of S
        for n in (1, 2):
            sminos.log_append(self.p, early, "status", session=early.split("/")[1], status="n%d" % n)
        hl = link.logs[self.p.id] = hublog.HubLog(self.p, {"key": None, "machine": "testhost"}, coded=False)
        hl.have = {}
        frames = []

        def draw():
            got = hl.next_upload()
            if got is not None:
                frames.append([(e["writer"], e["seq"], e["kind"]) for e in got[0]["events"]])
                hl.took(got[1])
            return got
        with mock.patch.object(hublog, "BATCH_BYTES", 1):   # one event a frame
            self.assertEqual(draw()[0]["events"][0]["writer"], early)
            rev = rec["policyRev"] + 2
            vis.set_visibility(S, share=(B, None), operator=False)
            self.published(link, rev)
            self.answer(link, [A, C], rev)
            while draw() is not None or draw() is not None:
                pass
        snap = max(e["seq"] for e in self.events(stream(S, [A, C])) if e["kind"] == "joined")
        at = {key: i for i, f in enumerate(frames) for key in f}
        self.assertLessEqual(at[(stream(S, [B]), 1, "unlisted")], at[(stream(S, [A, C]), snap, "joined")],
                             "the notice in or before its snapshot's frame: %r" % frames)

    def test_a_snapshot_that_fails_to_write_leaves_the_transition_pending_for_the_next_tick(self):
        link, rec = self.start(shares=(B, C))
        vis.set_visibility(S, share=(B, None), operator=False)
        rev = rec["policyRev"] + 1
        self.published(link, rev)
        real, failed = sminos._append, []

        def once(project, writer, events, **kw):
            if not failed and events and events[0].get("kind") == "joined":
                failed.append(writer)
                raise OSError("No space left on device")
            return real(project, writer, events, **kw)
        with mock.patch.object(sminos, "_append", side_effect=once):
            self.answer(link, [A, C], rev)
        self.assertEqual(failed, [stream(S, [A, C])])
        self.assertEqual(self.kinds(stream(S, [B])), ["unlisted"], "the notice written")
        self.assertEqual(self.kinds(stream(S, [A, C])), [])
        self.assertFalse(vis.transitions()[S].get("done"), "pending while its snapshot is not written")
        link.complete_transitions()
        self.assertEqual(self.kinds(stream(S, [A, C])), ["joined", "state"], "written at the next try")
        self.assertEqual(self.kinds(stream(S, [B])), ["unlisted"], "the notice once")
        self.assertTrue(vis.transitions()[S].get("done"))

    def test_a_notice_is_nothing_to_chat_delivery_or_a_projection(self):
        link, rec = self.start(shares=(B,))
        vis.set_visibility(S, share=(B, None), operator=False)
        self.published(link, rec["policyRev"] + 1)
        self.answer(link, [A], rec["policyRev"] + 1)
        events = sminos.log_read(self.p)
        notice = next(e for e in events if e["kind"] == "unlisted")
        self.assertEqual(au.session_refs(notice), [], "it names no session but its writer's")
        self.assertEqual(sminos.addressees(events), {}, "addressed to no one")
        self.assertIn(S, [m.session for m in sminos.members(self.p)], "its own session stays: its record is here")
        got = subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "chat", "-n", "50", "--json"],
                             cwd=self.p.root, env=self.env(), capture_output=True, text=True, timeout=60)
        self.assertNotIn("unlisted", got.stdout)


# ------------------------------------------------------------- a private record lost


class Recovered(Base):
    """A private session whose record file is lost is recreated private
    (ensure_record); its policyRev comes back above every revision this
    machine still holds of it, so the endpoint's audience at the new one
    can be kept over the last, and the session writes again."""

    def setUp(self):
        super().setUp()
        self.session(self.p, S, name="kept")

    def lose(self):
        os.unlink(records.record_path(S))
        sminos.forget_caches()
        return sminos.ensure_record(self.p, S)

    def test_a_lost_revision_1_record_comes_back_at_2_and_writes_once_its_audience_arrives(self):
        self.assertEqual(self.local(S, access="private", shares=(B,))["policyRev"], 1)
        sminos.view_of(self.p)
        self.assertEqual(self.kinds(stream(S, [A, B])), ["joined"])
        rec = self.lose()
        self.assertEqual((rec["access"], rec["shares"]), ("private", []))
        self.assertGreaterEqual(rec["policyRev"], 2)
        with self.assertRaises(au.StreamUnknown):
            sminos.own_stream(self.p, S)
        self.audience(S, [A], [A], rec["policyRev"])
        self.assertEqual(au.entry_of(S)["policyRev"], rec["policyRev"], "kept over the revision-1 entry")
        got = sminos.lifecycle(self.p, S, "state", state="idle", machine="testhost")
        self.assertEqual([e["writer"] for e in got], [stream(S, [A])])

    def test_above_a_pending_change_the_endpoint_never_answered(self):
        self.local(S, access="private", shares=(B, C))
        sminos.view_of(self.p)
        vis.set_visibility(S, share=(C, None), operator=False)   # policyRev 2, unanswered
        self.assertEqual(vis.transitions()[S]["policyRev"], 2)
        self.assertGreaterEqual(self.lose()["policyRev"], 3)

    def test_a_continuation_comes_back_above_its_own_revision_not_at_its_predecessors(self):
        """A recreated record taking its predecessor's policy (inherited)
        carries the predecessor's policyRev; the floor still raises it above
        the continuation's own revisions kept here."""
        pred = "6d0000c3-0000-4000-8000-0000000000c3"
        self.assertEqual(self.local(pred, access="private", shares=(B,))["policyRev"], 1)
        self.local(S, access="private", shares=(B,))
        records.set_policy(S, lambda a, s: (a, [{"member": B, "grade": "view"}]))
        self.audience(S, [A], [A, B], 2)
        os.unlink(records.record_path(S))
        sminos.forget_caches()
        rec = sminos.ensure_record(self.p, S, former=[pred])
        self.assertEqual((rec["access"], rec.get("former")), ("private", [pred]), "its predecessor's policy")
        self.assertGreaterEqual(rec["policyRev"], 3)

    def kinds(self, writer):
        return [e["kind"] for e in self.events(writer)]


# ------------------------------------------------------------- unlisting, through the hub stand-in's filter


class Unlisting(Base):
    """testhost (this machine, its sessions owned by A) uploads what sminos
    wrote, `audience` and `policyRev` added as its endpoint signs them, to
    the hub stand-in over DX2; `other` (B's) and `third` (C's) read through
    its filter. Each reader's log is what the stand-in serves it, laid into
    a sminos installation of its own, whose CLI is asked."""

    @classmethod
    def setUpClass(cls):
        cls.hub = tr.Hub()
        token = cls.hub.call("POST", "/control/enrollment", {})[1]["token"]
        got = cls.hub.call("POST", "/machine/enroll", {"token": token, "machine": "third"})[1]
        cls.hub.creds["third"] = (got["client_id"], got["client_secret"])

    @classmethod
    def tearDownClass(cls):
        cls.hub.stop()

    def setUp(self):
        super().setUp()
        # The stand-in's registry is the org's, across tests: a session of its own for each.
        self.sid = "6d%06x-0000-4000-8000-0000000000a1" % (int(time.time() * 1e3) % (1 << 24))
        self.session(self.p, self.sid, name="kept")
        self.readers = {"testhost": [A], "other": [B], "third": [C]}
        for machine, owners in self.readers.items():
            self.hub.call("POST", "/control/reader", {"machine": machine, "owners": owners,
                                                      "streams": machine != "testhost"})
        self.machines = {m: tr.Machine(self.hub, m) for m in self.readers}
        for m in self.machines.values():
            m.hello(self.p.id)
        self.hl = hublog.HubLog(self.p, {"key": None, "machine": "testhost"}, coded=False)
        self.hl.have = {}

    def tearDown(self):
        for machine in self.readers:
            self.hub.call("POST", "/control/reader", {"machine": machine, "owners": [], "streams": False})

    def upload(self, rev):
        """What this machine owes the hub, each event as its endpoint signs
        it: its stream's audience, and `rev` on a snapshot or notice."""
        a = self.machines["testhost"]
        m = a.mark()
        for frame, reach in self.hl.uploads():
            events = []
            for e in frame["events"]:
                e = {**e, "mac": tr.mac()}
                aud = au.stream_audience(self.p, e["writer"])
                if aud is not None:
                    e["audience"] = aud
                if e["kind"] in ("joined", "state", "unlisted"):
                    e["policyRev"] = rev
                events.append(e)
            a.post({"t": "events", "project": self.p.id, "events": events})
            self.hl.took(reach)
        time.sleep(0.2)
        self.assertEqual(a.since(m, "refused"), [], "the hub admits each")

    def reader(self, machine):
        """A sminos installation for `machine` holding what the hub serves it
        of the project: (its env, the events)."""
        got = [{k: v for k, v in e.items() if k != "mac"} for f in self.machines[machine].hello(self.p.id)
               if f["t"] == "events" for e in f["events"]]
        home = tempfile.mkdtemp(dir=self.home)
        env = {**self.env(), "HOME": os.path.join(home, "h"), "SMINOS_HOME": os.path.join(home, "s")}
        os.makedirs(os.path.join(env["SMINOS_HOME"], "daemon"))
        os.makedirs(os.path.join(env["HOME"], ".claude", "sessions"))
        sminos.write_json(os.path.join(env["SMINOS_HOME"], "daemon", "hub.json"),
                          {"hub": "http://127.0.0.1:9", "org": "org-1", "machine": machine, "client_id": "c",
                           "client_secret": "s", "key": tw.KEY, "former": {}, "enrolled": "2026-10-01T00:00:00Z"},
                          mode=0o600)
        reg = json.loads(Path(self.p.home, "project.json").read_text())
        pdir = os.path.join(env["SMINOS_HOME"], "projects", self.p.id)
        os.makedirs(os.path.join(pdir, "log"))
        Path(pdir, "project.json").write_text(json.dumps({**reg, "root": ""}))
        for e in sorted(got, key=lambda e: (e["writer"], e["seq"])):
            with open(os.path.join(pdir, "log", e["writer"].replace("/", ".") + ".jsonl"), "a") as f:
                f.write(json.dumps(e) + "\n")
        return env, got

    def ask(self, env, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), *args], cwd=self.home, env=env,
                              capture_output=True, text=True, timeout=60)

    def listed(self, env):
        got = self.ask(env, "list", "--org", "--json")
        self.assertEqual(got.returncode, 0, got.stderr)
        return {m["session"] for m in json.loads(got.stdout)}

    def test_a_removed_share_drops_the_session_for_that_member_alone(self):
        rec = self.local(self.sid, access="private", shares=(B, C))
        sminos.view_of(self.p)
        sminos.lifecycle(self.p, self.sid, "state", state="idle", machine="testhost")
        self.upload(rec["policyRev"])
        for machine in ("other", "third"):
            env, _ = self.reader(machine)
            self.assertIn(self.sid, self.listed(env), "shared: %s sees it" % machine)

        link = self.link()
        link.welcomed_rl10({"t": "welcome", "capabilities": ["access", "reach"], "policy": None})
        link.members(0.0)
        vis.set_visibility(self.sid, share=(B, None), operator=False)
        rev = rec["policyRev"] + 1
        link.members(0.0)
        link.dispatch({"t": "audience", **endpoint_standin.audience_frame(self.sid, [A], [A, C], rev)}, None)
        self.upload(rev)

        env, got = self.reader("other")
        self.assertIn("unlisted", [e["kind"] for e in got], "the withdrawn member gets the notice")
        self.assertNotIn(self.sid, self.listed(env), "list --org")
        found = self.ask(env, "find", "kept")
        self.assertNotIn(self.sid[:8], found.stdout)
        said = self.ask(env, "say", "--in", "work", "@%s hello" % self.sid[:8])
        self.assertNotEqual(said.returncode, 0, said.stdout)
        self.assertIn("no member", said.stderr)
        everyone = self.ask(env, "say", "--in", "work", "@all hello")
        self.assertNotIn(self.sid, everyone.stdout + everyone.stderr, "a broadcast skips what it can't see")

        env, got = self.reader("third")
        self.assertNotIn("unlisted", [e["kind"] for e in got], "still in the audience: no notice")
        self.assertIn(self.sid, self.listed(env))
        self.assertIn(self.sid[:8], self.ask(env, "find", "kept").stdout)
        said = self.ask(env, "say", "--in", "work", "@%s hello" % self.sid[:8])
        self.assertEqual(said.returncode, 0, said.stderr)

    def test_a_later_snapshot_it_sees_brings_the_session_back(self):
        rec = self.local(self.sid, access="private", shares=(B,))
        sminos.view_of(self.p)
        self.upload(rec["policyRev"])
        link = self.link()
        link.welcomed_rl10({"t": "welcome", "capabilities": ["access", "reach"], "policy": None})
        link.members(0.0)
        vis.set_visibility(self.sid, share=(B, None), operator=False)
        link.members(0.0)
        link.dispatch({"t": "audience", **endpoint_standin.audience_frame(self.sid, [A], [A], rec["policyRev"] + 1)}, None)
        self.upload(rec["policyRev"] + 1)
        env, _ = self.reader("other")
        self.assertNotIn(self.sid, self.listed(env))
        vis.set_visibility(self.sid, share=(B, "list"), operator=True)
        link.members(0.0)
        link.dispatch({"t": "audience", **endpoint_standin.audience_frame(self.sid, [A], [A, B], rec["policyRev"] + 2)},
                      None)
        self.upload(rec["policyRev"] + 2)
        env, _ = self.reader("other")
        self.assertIn(self.sid, self.listed(env), "shared again: its snapshot at a later policyRev")


if __name__ == "__main__":
    unittest.main()
