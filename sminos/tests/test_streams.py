#!/usr/bin/env python3
"""Audience streams on the writing side (P5 O18 M3; MAWS's
docs/doperpowers/plans/2026-11-05-p5-o18-message-reach.md D4, D6, D7, D9,
D10): the stream names and sessionRefs against MAWS's vectors
(audience-vectors.json); where a session's own events go as its policy
moves; the endpoint's capabilities and `audience` frames, and the member
frame's visibility; the stream choice of an addressed event (D4's S→R
intersection, splitting per audience with each split's own tags, the
private sender's refusal, cross-project copies); provenance redaction; an
unreadable established record failing closed.

Each test is a fresh machine (test_words.Machine: its own HOME and
SMINOS_HOME), enrolled as `testhost` of org-1 and cut over to its endpoint.
The endpoint's word is kept as the uplink keeps it (sminos_audience's
keep_capabilities and keep_audience), or sent by the endpoint stand-in to a
Link; `say` runs as the CLI, a subprocess.

Run: python3 -B sminos/tests/test_streams.py
"""

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_words as tw  # noqa: E402 — its machine: HOME, SMINOS_HOME, the enrollment, sessions, a Link

import endpoint_standin  # noqa: E402
import sminos  # noqa: E402
import sminos_audience as au  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_records as records  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

SCRIPTS = tw.SCRIPTS
A, B, C = "a" * 32, "b" * 32, "c" * 32          # member ids
S = "6d0000a1-0000-4000-8000-0000000000a1"      # a local session, the sender
T = "6d0000a2-0000-4000-8000-0000000000a2"      # a second local session
R = "12345678-0000-4000-8000-0000000000b1"      # another machine's session (short 12345678)
U = "6d0000b2-0000-4000-8000-0000000000b2"      # another machine's session
OTHER = "othermachine"
VECTORS = json.loads((HERE / "audience-vectors.json").read_text())


def stream(sid, members, machine="testhost"):
    return "%s/%s~%s" % (machine, sid, sminos.audience_digest(members))


def next_ms():
    """Wait for the log's millisecond clock to move on: across a session's
    streams `ts` is the only order, so events a test orders across them
    each need one of their own."""
    t = sminos.now(ms=True)
    while sminos.now(ms=True) == t:
        time.sleep(0.0002)


class Vectors(unittest.TestCase):
    """The names and the extractor, as MAWS's org-protocol pins them."""

    def test_the_digest_the_stream_names_and_the_session_of_a_writer(self):
        for v in VECTORS["digest"]:
            self.assertEqual(sminos.audience_digest(v["members"]), v["digest"])
        for v in VECTORS["streamOf"]:
            self.assertEqual(sminos.stream_of(v["writer"]), (v["base"], v["digest"]), v["writer"])
        for v in VECTORS["streamWriter"]:
            self.assertEqual(sminos.stream_writer(v["base"], v["audience"]), v["writer"])
        for v in VECTORS["writerSession"]:
            self.assertEqual(sminos.writer_session(v["writer"]) or None, v["session"], v["writer"])

    def test_session_refs(self):
        for v in VECTORS["sessionRefs"]:
            self.assertEqual(au.session_refs(v["event"]), v["refs"], v["event"])


class Streams(tw.Machine):
    def setUp(self):
        super().setUp()
        self.cut_over()
        self.p = self.project("work", hub=True)

    # ---- the endpoint's word, as the uplink keeps it

    def capable(self, caps=("access", "reach")):
        au.keep_capabilities(list(caps))

    def audience(self, sid, owners, members=None, rev=0):
        self.assertTrue(au.keep_audience({"t": "audience", **endpoint_standin.audience_frame(sid, owners, members, rev)}))

    def local(self, sid, owners=(A,), access="listed", shares=()):
        """A session of this machine with a final record owned by `owners`
        and, for a policy other than the default, that policy set."""
        prov = {**records.default_provenance("launch"), "owners": list(owners)}
        records.establish(sid, prov)
        if access != "listed" or shares:
            rec, _ = records.set_policy(sid, lambda _a, _s: (access, [{"member": m, "grade": "list"} for m in shares]))
            return rec
        return records.read(sid)

    def remote(self, sid, alias, project=None, owners=(A,)):
        """Another machine's member: its `joined` as it arrives over RL10."""
        project = project or self.p
        e = {"ts": "2026-11-05T01:00:00.000Z", "writer": "%s/%s" % (OTHER, sid), "seq": 1, "kind": "joined",
             "session": sid, "alias": alias, "name_source": "set", "machine": OTHER, "cwd": "/w", "worktree": "",
             "role": "", "seat": "", "by": "", "session_kind": "interactive", "owners": list(owners),
             "origin": {"kind": "terminal"},
             "verified": {"signer": {"kind": "machine", "ref": "ref-o", "name": OTHER, "keyId": "k"}}}
        self.assertEqual(hublog.append_verbatim(project, e), "appended")
        sminos.forget_caches()

    def files(self, project=None):
        project = project or self.p
        return sorted(n for n in os.listdir(os.path.join(project.home, "log")) if n.endswith(".jsonl"))

    def events(self, writer, project=None, kinds=None):
        try:
            got = tw.read_lines(sminos.writer_path(project or self.p, writer))
        except FileNotFoundError:
            return []
        return [e for e in got if kinds is None or e["kind"] in kinds]

    def says(self, writer, project=None):
        """The messages under a writer (its session's own lifecycle aside)."""
        return self.events(writer, project, ("say", "human"))

    def said(self, project=None):
        """Every message this machine wrote in the project."""
        project = project or self.p
        return [e for e in sminos.log_read(project) if e["writer"].startswith("testhost/")
                and e["kind"] in ("say", "human")]

    def say(self, text, session=S, cwd=None):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        if session:
            env["CLAUDE_CODE_SESSION_ID"] = session
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "say", text], cwd=cwd or self.p.root,
                              env=env, capture_output=True, text=True, timeout=60)

    # ---- a session's own events

    def test_a_private_sessions_own_events_go_under_its_stream_and_follow_its_policy(self):
        self.capable()
        rec = self.local(S, access="private", shares=(B,))
        self.audience(S, [A], [A, B], rec["policyRev"])
        sminos.lifecycle(self.p, S, "state", state="working", machine="testhost")
        first = stream(S, [A, B])
        self.assertEqual([e["kind"] for e in self.events(first)], ["state"])
        self.assertEqual(au.stream_audience(self.p, first), [A, B], "its audience kept for the uplink's voids")
        self.assertNotIn("testhost.%s.jsonl" % S, self.files(), "nothing under its plain writer")
        self.assertNotIn("audience", self.events(first)[0], "the endpoint adds the audience; sminos claims none")

        rec, _ = records.set_policy(S, lambda a, s: (a, []))   # its share removed: a higher policyRev
        self.assertGreater(rec["policyRev"], 1)
        self.assertEqual(sminos.lifecycle(self.p, S, "state", required=False, state="idle", machine="testhost"), [],
                         "a policy the endpoint has not given an audience for writes nothing yet")
        self.audience(S, [A], [A], rec["policyRev"])
        next_ms()
        sminos.lifecycle(self.p, S, "state", state="idle", machine="testhost")
        self.assertEqual([e["state"] for e in self.events(stream(S, [A]))], ["idle"], "a new stream")

        rec, _ = records.set_policy(S, lambda a, s: ("listed", s))
        self.audience(S, [A], None, rec["policyRev"])
        next_ms()
        sminos.lifecycle(self.p, S, "state", state="working", machine="testhost")
        self.assertEqual([e["state"] for e in self.events("testhost/" + S)], ["working"], "listed: the plain writer")
        self.assertEqual({sminos.writer_session(e["writer"]) for e in sminos.log_read(self.p)}, {S},
                         "every stream is the one session's")
        self.assertEqual([e["state"] for e in sminos._own_events(self.p, S)], ["working", "idle", "working"],
                         "its own history, across its streams, in order")

    def test_a_private_session_whose_audience_is_not_known_writes_nothing(self):
        self.capable()
        rec = self.local(S, access="private")
        self.audience(S, [A], [A], rec["policyRev"] - 1 if rec["policyRev"] else 7)
        with self.assertRaises(sminos.LogWriteFailed):
            sminos.lifecycle(self.p, S, "state", state="working", machine="testhost")
        self.assertEqual(self.files(), [])

    def test_with_an_endpoint_that_cannot_carry_it_nothing_changes(self):
        self.capable(())
        self.local(S)
        self.audience(S, [A], [A], 0)   # an endpoint's word is no stream without `access`
        sminos.lifecycle(self.p, S, "state", state="working", machine="testhost")
        self.assertEqual(self.files(), ["testhost.%s.jsonl" % S])
        self.local(T, access="private")
        with self.assertRaises(sminos.LogWriteFailed):
            sminos.lifecycle(self.p, T, "state", state="working", machine="testhost")

    def test_outside_a_hub_project_every_event_is_plain(self):
        self.capable()
        rec = self.local(S, access="private")
        self.audience(S, [A], [A], rec["policyRev"])
        local = self.project("local")
        sminos.lifecycle(local, S, "state", state="working", machine="testhost")
        self.assertEqual(self.files(local), ["testhost.%s.jsonl" % S])

    # ---- the endpoint's frames and the member frame

    def test_the_welcome_and_audience_frames_are_kept_and_the_member_frame_carries_visibility(self):
        link = self.link()
        link.welcomed_rl10({"t": "welcome", "capabilities": ["access", "reach"], "policy": None})
        self.assertTrue(link.visibility and au.capable())
        link.dispatch({"t": "audience", **endpoint_standin.audience_frame(R, [B], [B, C], 4)}, None)
        link.dispatch({"t": "audience", **endpoint_standin.audience_frame(R, [B], None, 3)}, None)   # older: kept out
        link.dispatch({"t": "audience", "session": R, "owners": [B], "members": [B], "digest": "0" * 16,
                       "policyRev": 9}, None)   # a digest not its members': passed by
        self.assertEqual(au.audience_of(R), [B, C])
        self.assertEqual(au.owners_of(R), [B])
        rec = self.local(S, access="private", shares=(B,))
        frame = uplink.member_frame(self.p.id, tw.member(S, record=rec), visibility=True)
        self.assertEqual((frame["access"], frame["shares"], frame["policyRev"]),
                         ("private", [{"member": B, "grade": "list"}], rec["policyRev"]))
        self.assertEqual(uplink.member_frame(self.p.id, tw.member(T, record=None), visibility=True)["access"],
                         "listed", "a session with no record: the defaults")
        plain = uplink.member_frame(self.p.id, tw.member(S, record=rec))
        self.assertFalse({"access", "shares", "policyRev"} & set(plain), "an endpoint without `access` gets none")
        link.welcomed_rl10({"t": "welcome", "capabilities": [], "policy": None})
        self.assertFalse(link.visibility or au.capable())

    def test_the_hello_advertises_audience(self):
        import sminos_rl10 as rl10
        self.assertEqual(rl10.hello_frame("t" * 64, "1", None)["capabilities"], ["audience"])

    # ---- addressed events

    def test_D4s_example_takes_the_intersection(self):
        """S, private with audience {A, B}, messages R, private with audience
        {A, C}, both owned by A: the event's audience is {A}."""
        self.capable()
        rec = self.local(S, access="private", shares=(B,))
        self.audience(S, [A], [A, B], rec["policyRev"])
        self.audience(R, [A], [A, C], 2)
        got = au.stream_for(self.p, S, [{"session": R, "alias": "r"}])
        self.assertEqual(got, [(stream(S, [A]), [A], [{"session": R, "alias": "r"}], None)])

    def test_a_private_sender_outside_a_recipients_reach_is_refused_and_nothing_is_written(self):
        self.capable()
        self.session(self.p, S, name="sender")
        rec = self.local(S, access="private")
        self.audience(S, [A], [A], rec["policyRev"])
        self.remote(U, "carol", owners=[C])
        self.audience(U, [C], None, 0)
        got = self.say("@carol hello")
        self.assertEqual(got.returncode, 4, got.stderr)
        self.assertIn("carol can't be reached from this session: this session is unlisted; share it as Can message "
                      "with %s first" % C, got.stderr)
        self.assertEqual(self.said(), [], "nothing written")

    def test_a_say_splits_per_audience_each_with_its_own_tags(self):
        """From a listed sender, `@private#12345678 @public hello`: a public
        event naming neither the private alias nor its short, a private one
        naming only it; an @ after the leading run is text."""
        self.capable()
        self.session(self.p, S, name="sender")
        self.local(S)
        self.audience(S, [A], None, 0)
        self.remote(R, "private")
        self.audience(R, [A], [A, C], 3)
        self.remote(U, "public", owners=[B])
        self.audience(U, [B], None, 0)
        got = self.say("@private#12345678 @public hello, cc @private")
        self.assertEqual(got.returncode, 0, got.stderr)
        public = self.says("testhost/" + S)
        private = self.says(stream(S, [A, C]))
        self.assertEqual([(e["text"], [r["session"] for r in e["to"]]) for e in public],
                         [("@public hello, cc @private", [U])])
        self.assertEqual([(e["text"], [r["session"] for r in e["to"]]) for e in private],
                         [("@private#12345678 hello, cc @private", [R])])
        self.assertNotIn("12345678", json.dumps(public))

    def test_two_private_recipients_of_different_audiences_make_two_events(self):
        self.capable()
        self.session(self.p, S, name="sender")
        self.local(S)
        self.audience(S, [A], None, 0)
        self.remote(R, "r1")
        self.audience(R, [A], [A, B], 1)
        self.remote(U, "u1")
        self.audience(U, [A], [A, C], 1)
        got = self.say("@r1 @u1 both of you")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual([e["text"] for e in self.says(stream(S, [A, B]))], ["@r1 both of you"])
        self.assertEqual([e["text"] for e in self.says(stream(S, [A, C]))], ["@u1 both of you"])
        self.assertEqual(self.says("testhost/" + S), [])

    def test_a_cross_project_copy_carries_its_originals_audience_split_the_same_way(self):
        self.capable()
        other = self.project("other", hub=True)
        self.session(self.p, S, name="sender")
        self.local(S)
        self.audience(S, [A], None, 0)
        self.remote(R, "private", project=other)
        self.audience(R, [A], [A, C], 3)
        self.remote(U, "public", project=other, owners=[B])
        self.audience(U, [B], None, 0)
        got = self.say("@other/private @other/public hi")
        self.assertEqual(got.returncode, 0, got.stderr)
        for project in (other, self.p):
            self.assertEqual([e["text"] for e in self.says(stream(S, [A, C]), project)], ["@other/private hi"])
            self.assertEqual([e["text"] for e in self.says("testhost/" + S, project)], ["@other/public hi"])
        copies = [e for w in (stream(S, [A, C]), "testhost/" + S) for e in self.says(w, self.p)]
        self.assertTrue(all("copy" in e for e in copies), "the home project's events are the copies")
        self.assertEqual(au.stream_audience(self.p, stream(S, [A, C])), [A, C],
                         "the copy's stream is kept in its home with its audience, as in the delivering project")
        self.assertFalse({"audience", "policyRev"} & {k for e in copies for k in e}, "no policy fields stored")

    def test_a_copy_whose_stream_cannot_be_kept_at_home_is_a_copy_failure_and_the_say_is_delivered(self):
        self.capable()
        other = self.project("other", hub=True)
        self.session(self.p, S, name="sender")
        self.local(S)
        self.audience(S, [A], None, 0)
        self.remote(R, "private", project=other)
        self.audience(R, [A], [A, C], 3)
        os.makedirs(sminos.project_path(self.p, au.STREAMS) + ".lock")   # the home's stream index cannot be written
        got = self.say("@other/private hi")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertIn("delivered, but its copy could not be recorded in work", got.stderr)
        self.assertIn("private: recorded (on %s)" % OTHER, got.stdout, "delivery went on")
        self.assertEqual([e["text"] for e in self.says(stream(S, [A, C]), other)], ["@other/private hi"])
        self.assertEqual(self.says(stream(S, [A, C])), [], "no copy at home")

    def test_no_copy_of_a_stream_event_goes_into_a_home_that_keeps_no_streams(self):
        """A session in a local project (its log git-mirrored or kept here,
        never filtered by audience) tags a private session in a hub project:
        delivered under the stream there, and no copy of it at home."""
        self.capable()
        home = self.project("local")
        self.session(home, S, name="sender")
        self.local(S)
        self.audience(S, [A], None, 0)
        self.remote(R, "private")
        self.audience(R, [A], [A, C], 3)
        got = self.say("@work/private hi", cwd=home.root)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual([e["text"] for e in self.says(stream(S, [A, C]))], ["@work/private hi"], "delivered")
        self.assertIn("delivered; its copy is not kept in local", got.stderr)
        self.assertEqual([e for e in sminos.log_read(home) if e["kind"] in ("say", "human")], [],
                         "no copy in the home's log, under any writer")
        self.assertNotIn("private hi", "".join(Path(home.home, "log", n).read_text() for n in self.files(home)))

    def test_a_listed_sender_never_writes_toward_a_private_session_its_owners_are_outside_of(self):
        self.capable()
        self.session(self.p, S, name="sender")
        self.local(S, owners=(B,))
        self.audience(S, [B], None, 0)
        self.remote(R, "private")
        self.audience(R, [A], [A], 2)
        got = self.say("@private hi")
        self.assertEqual(got.returncode, 4, got.stderr)
        self.assertIn("no member @private", got.stderr)
        self.assertEqual(self.said(), [])

    def test_an_operator_say_to_a_private_session_goes_under_its_human_stream(self):
        self.capable()
        self.remote(R, "private")
        self.audience(R, [A], [A, C], 2)
        got = self.say("@private hi", session="")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual([e["kind"] for e in self.events(stream("human", [A, C]))], ["human"])
        e = self.events(stream("human", [A, C]))[0]
        self.assertTrue(sminos.own_operator_event(e) and sminos.receipted(self.p, e),
                        "its own operator's words, receipted, under the stream")

    def test_under_a_new_enrolment_an_operator_say_to_a_private_session_waits_for_its_streams_head(self):
        """The machine was re-enrolled (marked) and the hub holds positions of
        the operator's stream already: the say queues, and lands above the
        stream's head once the log reached it (#147, for the stream)."""
        self.capable()
        self.remote(R, "private")
        self.audience(R, [A], [A, C], 2)
        sminos.mark_enrolled(*sminos.enrolment_stamp())
        writer = stream("human", [A, C])
        got = self.say("@private hi", session="")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertIn("waits", got.stdout)
        self.assertEqual(self.events(writer), [], "no seq taken before the stream's head is known")
        self.assertEqual([e["text"] for e in sminos.queued_read(self.p, writer)], ["@private hi"])
        hl = hublog.HubLog(self.p, {"key": None, "machine": "testhost"}, coded=False)
        hl.on_have({"have": {writer: 2}})
        self.assertEqual(self.events(writer), [])
        for seq in (1, 2):
            hl.spend(writer, seq, "conflict")   # what the endpoint never signed here, as RL10 spends it
        self.assertEqual([(e["seq"], e["text"]) for e in self.events(writer)], [(3, "@private hi")])
        self.assertEqual(sminos.queued_operators(self.p), {})

    def test_with_no_capability_a_say_is_as_before(self):
        self.capable(())
        self.session(self.p, S, name="sender")
        self.local(S)
        self.remote(R, "private")
        self.audience(R, [A], [A, C], 3)
        got = self.say("@private hi")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual([e["text"] for e in self.says("testhost/" + S)], ["@private hi"])

    # ---- provenance

    def test_a_spawner_narrower_than_the_session_is_named_to_no_one(self):
        self.capable()
        rec = self.local(S, access="private")
        self.audience(S, [A], [A], rec["policyRev"])
        prov = {**records.default_provenance("launch"), "owners": [A],
                "origin": {"kind": "sminos-spawn", "spawnerSession": S}}
        records.establish(T, prov)
        self.audience(T, [A], None, 0)
        self.assertIsNone(sminos.published_provenance(T)["origin"]["spawnerSession"],
                          "a listed child of a private parent")
        records.set_policy(T, lambda a, s: ("private", s))
        self.audience(T, [A], [A], records.read(T)["policyRev"])
        self.assertEqual(sminos.published_provenance(T)["origin"]["spawnerSession"], S,
                         "within the parent's audience it is named")

    def test_a_continuation_to_a_narrower_successor_names_none(self):
        self.capable()
        self.local(S)
        self.audience(S, [A], None, 0)
        rec = self.local(T, access="private")
        self.audience(T, [A], [A], rec["policyRev"])
        e = sminos.lifecycle(self.p, S, "retired", by="", reason="continued", to=T)[0]
        self.assertIsNone(e["to"])

    # ---- an unreadable record

    def test_a_member_frame_is_built_from_the_record_as_it_reads_at_its_publication(self):
        """A private record corrupted, the plane refreshed (its row's record
        None, the listing withdrawn), the file repaired before the plane reads
        it again: the next publication sends the private frame, never the
        defaults the stale row would give."""
        self.capable()
        self.session(self.p, S, name="kept")
        rec = self.local(S, access="private")
        self.audience(S, [A], [A], rec["policyRev"])
        sminos.view_of(self.p)
        link = self.link()
        link.welcomed_rl10({"t": "welcome", "capabilities": ["access", "reach"], "policy": None})
        link.members(0.0)
        self.assertEqual(link.members_sent[S]["access"], "private")
        link.log_lane.take()
        path = records.record_path(S)
        good = Path(path).read_bytes()
        Path(path).write_text("{not json")
        sminos.forget_caches()
        link.plane.refresh(self.p)
        self.assertIsNone(link.plane.member_rows[self.p.id][S].record, "the plane's row: no record")
        link.publish_members(0.0)
        self.assertIn({"t": "member", "session": S, "gone": True}, link.log_lane.take())
        Path(path).write_bytes(good)
        os.chmod(path, 0o600)
        sminos.forget_caches()
        link.publish_members(0.0)   # before the plane reads it again
        sent = [f for f in link.log_lane.take() if f.get("session") == S]
        self.assertEqual([(f.get("access"), f.get("policyRev")) for f in sent], [("private", rec["policyRev"])])
        self.assertTrue(link.members_before(self.p, {S}))
        self.assertEqual(link.log_lane.take(), [], "members_before compares the same fresh record: nothing changed")

    def test_an_unreadable_established_record_fails_closed_until_it_reads_again(self):
        self.capable()
        self.session(self.p, S, name="kept")
        rec = self.local(S, access="private")
        self.audience(S, [A], [A], rec["policyRev"])
        sminos.view_of(self.p)
        link = self.link()
        link.welcomed_rl10({"t": "welcome", "capabilities": ["access", "reach"], "policy": None})
        link.members(0.0)
        self.assertIn(S, link.members_sent, "listed while its record reads")
        sent_before = len(link.log_lane.take())
        self.assertGreater(sent_before, 0)
        path = records.record_path(S)
        good = Path(path).read_bytes()
        Path(path).write_text("{not json")
        sminos.forget_caches()
        link.publish_members(0.0)
        self.assertIn({"t": "member", "session": S, "gone": True}, link.log_lane.take(), "its listing withdrawn")
        before = self.files()
        self.assertEqual(sminos.lifecycle(self.p, S, "state", required=False, state="working", machine="testhost"), [])
        with self.assertRaises(SystemExit):
            sminos.addressed_append(self.p, S, [{"session": T, "alias": "t"}], "say", {"text": "x"}, "not sent")
        self.assertEqual(self.files(), before, "nothing written under any of its writers")
        Path(path).write_bytes(good)
        os.chmod(path, 0o600)
        sminos.forget_caches()
        link.publish_members(0.0)
        self.assertIn(S, link.members_sent, "listed again once it reads")
        self.assertEqual(len(sminos.lifecycle(self.p, S, "state", state="working", machine="testhost")), 1)


if __name__ == "__main__":
    unittest.main()
