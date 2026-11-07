#!/usr/bin/env python3
"""Message reach on the log plane (P5 O18 M3; MAWS's
docs/doperpowers/plans/2026-11-05-p5-o18-message-reach.md, D5 and D6):
sminos's side of the hub's refusals and admission.

- Admitted: what a `have` confirms for the archive (`archive_have`), and the
  projection copy_log writes from it.
- Retry: a `state-unavailable` position on a direct stream goes up again
  after the wait, with no reconnect and no further write.
- Dead: an `audience` refusal stops its writer past the stream; an event
  appended to it revives it, a `void` at each refused position; a `void`
  from elsewhere is nothing to a reader.

Hermetic: HOME and SMINOS_HOME are temporary, one pair per test.
Run: python3 -B sminos/tests/test_reach.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "sminos" / "scripts"
BASE = tempfile.mkdtemp(prefix="smr.", dir="/tmp")
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR", "SMINOS_ASK_MS"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import sminos  # noqa: E402
import sminos_archive as archive  # noqa: E402
import sminos_audience  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import endpoint_standin  # noqa: E402
from rl10_identity import write_identity  # noqa: E402

RAW_KEY = bytes(range(32))
SID = "6e000001-0000-4000-8000-0000000000a1"
OTHER_SID = "6e000001-0000-4000-8000-0000000000b2"
M1, M2 = "4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c", "5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d"


# ------------------------------------------------------------- sminos's side


class Plane(unittest.TestCase):
    """A fresh installation per test, `testhost` cut over into org-1 (its
    endpoint's identity, `oldname` a former name), with one hub project,
    `work`, whose remote archives it."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"))
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        write_identity(os.environ["SMINOS_HOME"], former={"oldname": []})
        sminos.forget_caches()
        self.p = sminos.make_project("6e000004-0000-4000-8000-000000000001", "work", "", "",
                                     {"url": "http://127.0.0.1:9", "org": "org-1"})
        sminos.project_path(self.p, "log")

    coded = True   # DX2's codes; an OnRl10 twin runs the same tests uncoded, as a cut-over machine does (#153)

    def hl(self, coded=None, machine="testhost"):
        """`machine`: another name than this machine's now, as the uplink saw it before a rename."""
        coded = self.coded if coded is None else coded
        return hublog.HubLog(self.p, {"key": RAW_KEY if coded else None, "machine": machine}, coded=coded)

    def put(self, writer, *events):
        """Events as they are, into a writer file (another machine's as imported, an own one as written)."""
        path = sminos.writer_path(self.p, writer)
        with open(path, "a") as f:
            for seq, fields in events:
                f.write(json.dumps({"ts": "2026-11-05T00:00:%02d.000Z" % seq, "writer": writer, "seq": seq,
                                    "kind": "say", "from": "x", "to": "*", **fields}) + "\n")
        return path

    def say(self, writer, text, **fields):
        return sminos.log_append(self.p, writer, "say", **{"from": "x", "to": "*", "text": text, **fields})

    def uploaded(self, hl):
        return [(e["writer"], e["seq"], e["kind"], e.get("text")) for frame, _ in hl.uploads() for e in frame["events"]]

    def uplink(self):
        return json.loads(Path(self.p.home, hublog.STATE_FILE).read_text())


class Admitted:
    """What a `have` confirms for the archive, run by AdmittedOnRl10 (its
    coded DX2 arm went in #153 M4)."""

    def copied(self, writer, archived=None):
        """`archived`: the lines the archive's clone already holds for `writer` (the remote's file)."""
        clone = tempfile.mkdtemp(dir=BASE)
        path = os.path.join(clone, writer.replace("/", ".") + ".jsonl")
        if archived is not None:
            Path(path).write_text("".join(json.dumps(e) + "\n" for e in archived))
        names = archive.copy_log(self.p, clone)
        path = os.path.join(clone, writer.replace("/", ".") + ".jsonl")
        held = [json.loads(line) for line in Path(path).read_text().splitlines()] if os.path.exists(path) else None
        return names, held

    def test_a_have_saves_its_own_writers_vector_and_withheld_list_beside_archive_at(self):
        self.hl(machine="oldname").on_have({"have": {"oldname/" + SID: 2}, "withheld": {"oldname/" + SID: [1]},
                                            "archive": True})
        self.hl().on_have({"have": {"testhost/human": 5, "oldname/" + SID: 2, "other/human": 9},
                           "withheld": {"testhost/human": [2, [4, 5]]}, "archive": True})
        d = self.uplink()
        self.assertEqual(d["archive_have"], {"have": {"testhost/human": 5, "oldname/" + SID: 2},
                                             "withheld": {"testhost/human": [2, [4, 5]], "oldname/" + SID: [1]}},
                         "own writers only, a former name's among them, never another machine's")
        self.assertIsInstance(d["archive_at"], float)
        self.assertNotIn("archive_have_error", d)

    def test_a_former_names_withheld_positions_outlive_the_rename(self):
        """The hub lists only the name now's withheld positions: a former
        name's, listed before the rename, are kept, so the archive still
        tombstones them."""
        self.hl(machine="oldname").on_have({"have": {"oldname/" + SID: 3}, "withheld": {"oldname/" + SID: [2]},
                                            "archive": True})
        self.hl().on_have({"have": {"oldname/" + SID: 3, "testhost/human": 1}, "withheld": {}, "archive": True})
        self.assertEqual(self.uplink()["archive_have"]["withheld"], {"oldname/" + SID: [2]})

    def test_a_former_names_entry_is_frozen_at_the_last_have_that_listed_it(self):
        """A stale message under the name then is withheld, the connection
        drops before a `have` confirms it, and the machine is renamed: the
        next `have` carries the former writer's head but lists the name now's
        withheld positions alone. The former writer's entry stays as the last
        `have` taken under its name saved it, so its refused body never
        reaches the archive; with no such entry, it is not copied at all."""
        old = "oldname/human"
        self.put(old, (1, {"text": "public"}), (2, {"text": "the refused private body"}))
        self.hl(machine="oldname").on_have({"have": {old: 1}, "withheld": {}, "archive": True})
        # ... seq 2 withheld upstream, the refusal lost to the drop; then the rename.
        self.hl().on_have({"have": {old: 2, "testhost/human": 0}, "withheld": {}, "archive": True})
        self.assertEqual(self.uplink()["archive_have"]["have"].get(old), 1, "frozen, not the hub's head now")
        names, held = self.copied(old)
        self.assertEqual([e.get("text") for e in held], ["public"])
        self.assertNotIn("refused private body", json.dumps(held))
        self.hl().on_have({"have": {old: 2}, "withheld": {}, "archive": True})
        self.assertEqual([e.get("text") for e in self.copied(old)[1]], ["public"], "still frozen a have later")

        Path(self.p.home, hublog.STATE_FILE).unlink()   # no `have` saved under the former name
        self.hl().on_have({"have": {old: 2}, "withheld": {}, "archive": True})
        self.assertNotIn(old, self.uplink()["archive_have"]["have"])
        names, held = self.copied(old)
        self.assertNotIn("oldname.human.jsonl", names)
        self.assertIsNone(held, "excluded: never the hub's head without the list that came with it")

    def test_a_withheld_list_that_disagrees_with_its_vector_confirms_nothing(self):
        for withheld, why in (({"testhost/human": [7]}, "past that writer's head"),
                              ({"testhost/human": [[3, 2]]}, "not seqs"),
                              ({"testhost/human": "1-3"}, "not seqs"),
                              ([1, 2], "is not {writer")):
            self.hl().on_have({"have": {"testhost/human": 5}, "withheld": withheld, "archive": True})
            d = self.uplink()
            self.assertIsNone(d["archive_have"], withheld)
            self.assertIn(why, d["archive_have_error"])
            with self.assertRaises(daemon.SyncFailed) as raised:
                archive.copy_log(self.p, tempfile.mkdtemp(dir=BASE))
            self.assertIn(why, str(raised.exception), "the run fails, saying why")

    def test_a_hub_before_message_reach_lists_no_withheld_and_the_archive_copies_up_to_its_vector(self):
        """Today's hub (before MAWS O18 M1) sends a `have` with no `withheld`:
        nothing is withheld there, so its vector confirms every own position
        up to it, as the archive copied before."""
        own = "testhost/human"
        self.put(own, (1, {"text": "one"}), (2, {"text": "two"}), (3, {"text": "not admitted yet"}))
        self.put("other/human", (1, {"text": "theirs"}))
        self.hl().on_have({"have": {own: 2, "other/human": 1}, "archive": True})
        d = self.uplink()
        self.assertEqual(d["archive_have"], {"have": {own: 2}, "withheld": {}})
        self.assertNotIn("archive_have_error", d)
        self.assertEqual([e["text"] for e in self.copied(own)[1]], ["one", "two"])
        self.assertEqual([e["text"] for e in self.copied("other/human")[1]], ["theirs"])

    def test_no_have_yet_fails_the_run(self):
        with self.assertRaises(daemon.SyncFailed):
            archive.copy_log(self.p, tempfile.mkdtemp(dir=BASE))

    def test_the_projection_is_plain_writers_admitted_and_withheld_positions_as_tombstones(self):
        own = "testhost/human"
        self.put(own, (1, {"text": "one"}), (2, {"text": "refused, body kept here"}), (3, {"text": "three"}),
                 (4, {"text": "not admitted yet"}))
        self.put("other/human", (1, {"text": "theirs"}), (3, {"text": "past a spent hole"}))
        self.put("oldname/" + SID, (1, {"text": "a former name's"}), (2, {"text": "held back"}))
        stream = "testhost/%s~%s" % (SID, sminos.audience_digest([M1]))
        self.put(stream, (1, {"text": "private"}))
        self.put("other/%s~%s" % (OTHER_SID, sminos.audience_digest([M1])), (1, {"text": "theirs, private"}))
        self.hl(machine="oldname").on_have({"have": {"oldname/" + SID: 1}, "archive": True})
        self.hl().on_have({"have": {own: 3, "oldname/" + SID: 2, "other/human": 3, stream: 1},
                           "withheld": {own: [2]}, "archive": True})
        names, held = self.copied(own)
        self.assertEqual([(e["seq"], e.get("text"), e.get("withheld")) for e in held],
                         [(1, "one", None), (2, None, True), (3, "three", None)],
                         "up to the hub's vector, the withheld position its tombstone, whatever the file holds")
        self.assertEqual(held[1], {"writer": own, "seq": 2, "withheld": True})
        self.assertEqual([e["text"] for e in self.copied("other/human")[1]], ["theirs", "past a spent hole"],
                         "another machine's as imported, whole")
        self.assertEqual([e["text"] for e in self.copied("oldname/" + SID)[1]], ["a former name's"],
                         "a former name's writer is this machine's: up to the vector of the last have under it")
        self.assertEqual(sorted(names), sorted(["testhost.human.jsonl", "other.human.jsonl",
                                                "oldname.%s.jsonl" % SID]), "no stream file")

    def test_a_refusal_the_have_names_is_honoured_whatever_the_local_file_holds(self):
        own = "testhost/human"
        self.put(own, (1, {"text": "one"}), (3, {"text": "three"}))   # 2 spent here
        self.hl().on_have({"have": {own: 3}, "withheld": {own: [2, 3]}, "archive": True})
        self.assertEqual(self.copied(own)[1], [{"ts": "2026-11-05T00:00:01.000Z", "writer": own, "seq": 1,
                                                "kind": "say", "from": "x", "to": "*", "text": "one"},
                                               {"writer": own, "seq": 2, "withheld": True},
                                               {"writer": own, "seq": 3, "withheld": True}])

    def test_positions_refused_audience_or_voided_here_are_tombstones_whatever_the_have_says(self):
        own = "testhost/human"
        self.put(own, (1, {"text": "one"}), (2, {"text": "refused audience"}), (3, {"text": "voided"}),
                 (4, {"text": "four"}))
        self.hl().on_have({"have": {own: 4}, "archive": True})
        d = self.uplink()
        d.update(dead={own: {"at": [2], "last": 4}}, voided={own: [3]})
        Path(self.p.home, hublog.STATE_FILE).write_text(json.dumps(d))
        self.assertEqual([e.get("text", "tombstone") for e in self.copied(own)[1]],
                         ["one", "tombstone", "tombstone", "four"])

    def test_nothing_is_copied_from_a_conflict_kept_on(self):
        own = "testhost/human"
        self.put(own, (1, {"text": "one"}), (2, {"text": "the hub holds another"}))
        hl = self.hl()
        hl.on_have({"have": {own: 2}, "archive": True})
        hl.bound(own, 1, conflict=True)
        self.assertEqual([e["text"] for e in self.copied(own)[1]], ["one"])
        theirs = {"ts": "t", "writer": own, "seq": 2, "kind": "say", "text": "the hub's, archived by another"}
        self.assertEqual([e["text"] for e in self.copied(own, [theirs])[1]], ["one", "the hub's, archived by another"],
                         "the archive keeps what it holds past the conflict")

    def test_the_archive_keeps_every_position_it_holds_past_what_this_run_confirms(self):
        """A former name's frontier is frozen below what the archive already
        holds of its writer (another archiver copied it as the hub served it):
        the confirmed prefix is the local projection, the rest stays as the
        archive holds it — a tombstone too —, never the local body past the
        frontier; a position this machine recorded voided is a tombstone there
        as well."""
        old = "oldname/human"
        self.put(old, (1, {"text": "public"}), (2, {"text": "local, unconfirmed"}), (3, {"text": "voided here"}),
                 (4, {"text": "withheld upstream"}))
        self.hl(machine="oldname").on_have({"have": {old: 1}, "withheld": {}, "archive": True})
        self.hl().on_have({"have": {old: 4, "testhost/human": 0}, "withheld": {}, "archive": True})
        d = self.uplink()
        d["voided"] = {old: [3]}
        Path(self.p.home, hublog.STATE_FILE).write_text(json.dumps(d))
        archived = [{"ts": "t", "writer": old, "seq": 1, "kind": "say", "text": "stale"},
                    {"ts": "t", "writer": old, "seq": 2, "kind": "say", "text": "the hub's two"},
                    {"ts": "t", "writer": old, "seq": 3, "kind": "say", "text": "the hub's three"},
                    hublog.tombstone(old, 4)]
        held = self.copied(old, archived)[1]
        self.assertEqual([e.get("text", "tombstone") for e in held], ["public", "the hub's two", "tombstone", "tombstone"])
        self.assertNotIn("unconfirmed", json.dumps(held))
        self.assertNotIn("withheld upstream", json.dumps(held))

        own = "testhost/human"
        self.put(own, (1, {"text": "one"}), (2, {"text": "two"}))
        self.hl().on_have({"have": {own: 2}, "withheld": {}, "archive": True})
        edited = [{"ts": "t", "writer": own, "seq": 1, "kind": "say", "text": "edited in git"},
                  {"ts": "t", "writer": own, "seq": 3, "kind": "say", "text": "past anything written"}]
        self.assertEqual([e["text"] for e in self.copied(own, edited)[1]], ["one", "two"],
                         "the confirmed prefix is the log's, and past what this machine or the hub held, nothing")


class AdmittedOnRl10(Admitted, Plane):
    """Admitted's tests uncoded, as a machine cut over to its endpoint runs
    them (RL10, #153 M3a): the endpoint relays the hub's `have`, its
    `withheld` and `archive` among it."""

    coded = False


class Retry(Plane):
    def refuse(self, hl, writer, seq, reason="state-unavailable"):
        hl.on_refused({"t": "refused", "project": self.p.id,
                       "refusal": {"reason": reason, "writer": writer, "seq": seq, "message": "m"}})

    def test_a_position_the_registry_could_not_check_goes_up_again_after_the_wait(self):
        os.environ["SMINOS_ASK_MS"] = "30000"
        self.addCleanup(os.environ.pop, "SMINOS_ASK_MS")
        own = "testhost/human"
        for i in (1, 2, 3):
            self.say(own, "s%d" % i)
        hl = self.hl()
        hl.on_have({"have": {own: 1}})
        self.assertEqual([x[1] for x in self.uploaded(hl)], [2, 3])
        hl.took({own: 3})
        clock = [1000.0]
        with mock.patch.object(hublog.time, "monotonic", lambda: clock[0]):
            self.refuse(hl, own, 2)
            self.assertEqual(self.uploaded(hl), [], "nothing before the wait")
            hl.on_resend({"project": self.p.id, "writer": own, "from": 2})   # a later frame's gap
            self.assertEqual(self.uploaded(hl), [], "a resend meanwhile does not cut the wait short")
            clock[0] += 29.9
            self.assertEqual(self.uploaded(hl), [])
            clock[0] += 0.2
            self.assertEqual([x[1] for x in self.uploaded(hl)], [2, 3], "from the refused position, unasked")
            hl.took({own: 3})
            self.refuse(hl, own, 2)
            self.refuse(hl, own, 3)
            clock[0] += 15
            self.refuse(hl, own, 2)   # another refusal within the wait: the retry stays where it was
            clock[0] += 15.1
            self.assertEqual([x[1] for x in self.uploaded(hl)], [2, 3], "one retry per writer per wait")
        self.assertEqual(hl.taken().get(own, 0), 1, "never taken past what the hub could not check")

    def test_the_endpoint_rewinds_on_rl10_and_a_new_stream_starts_from_the_have(self):
        own = "testhost/human"
        self.say(own, "s1")
        hl = self.hl(coded=False)
        hl.on_have({"have": {}})
        hl.took({own: 1})
        self.refuse(hl, own, 1)
        self.assertEqual(hl.paused, {}, "RL10: no pause here; the endpoint opens the hole")
        hl = self.hl()
        hl.on_have({"have": {}})
        hl.took({own: 1})
        self.refuse(hl, own, 1)
        hl.reset()
        hl.on_have({"have": {}})
        self.assertEqual([x[1] for x in self.uploaded(hl)], [1], "a new stream starts again from the hub's have")


class Dead(Plane):
    def refuse(self, hl, writer, seq):
        hl.on_refused({"t": "refused", "project": self.p.id,
                       "refusal": {"reason": "audience", "writer": writer, "seq": seq, "message": "stale"}})

    def check_revival(self, writer, audience=None):
        sminos_audience.keep_stream(self.p, writer, audience)
        self.say(writer, "one")
        hl = self.hl(coded=False)
        hl.on_have({"have": {}})
        self.assertEqual([x[1] for x in self.uploaded(hl)], [1])
        hl.took({writer: 1})
        self.refuse(hl, writer, 1)
        self.assertEqual(self.uploaded(hl), [], "a stop: no retry")
        hl.reset()
        hl.on_have({"have": {}})   # a reconnect
        self.assertEqual(self.uploaded(hl), [], "dead across a reconnect")
        self.assertEqual(self.uplink()["dead"], {writer: {"at": [1], "last": 1}}, "kept in uplink.json")
        self.say(writer, "two")
        frames = [e for frame, _ in hl.uploads() for e in frame["events"]]
        void = {"ts": frames[0]["ts"], "writer": writer, "seq": 1, "kind": "void", "of": 1,
                **({"audience": audience} if audience else {})}
        self.assertEqual(frames[0], void, "revived: a content-free void at the refused position")
        self.assertEqual((frames[1]["seq"], frames[1]["text"]), (2, "two"), "then the rest as stored")
        self.assertEqual([e["text"] for e in sminos.log_read(self.p) if e["writer"] == writer], ["one", "two"],
                         "the local file keeps the original body")
        self.assertEqual(self.uplink()["voided"], {writer: [1]})
        self.assertNotIn(writer, self.uplink()["dead"])
        hl.took({writer: 2})
        echo = {"event": {**void, "created": void["ts"], "sig": {"kid": "k", "sig": "s"}, "attest": {},
                          "audience": audience or [M1], "policyRev": 3},
                "signer": {"kind": "machine", "name": "testhost"}}
        self.assertEqual(hl.take([echo]), (0, []), "the void's echo reads present")
        hl.reset()
        hl.on_have({"have": {}})
        self.assertEqual([e["kind"] for frame, _ in hl.uploads() for e in frame["events"]], ["void", "say"],
                         "a later upload of the position sends the void again")

    def test_a_void_the_endpoint_refuses_conflict_stops_its_writer_for_good(self):
        """The endpoint had signed another body at the refused position: its
        ledger refuses the void `conflict`, which is final, never retried on
        a reconnect or revived by a later event."""
        writer = "testhost/" + SID
        self.say(writer, "one")
        hl = self.hl(coded=False)
        hl.on_have({"have": {}})
        hl.took({writer: 1})
        self.refuse(hl, writer, 1)
        self.say(writer, "two")
        self.assertEqual([e["kind"] for frame, _ in hl.uploads() for e in frame["events"]], ["void", "say"])
        hl.on_refused({"t": "refused", "project": self.p.id,
                       "refusal": {"reason": "conflict", "writer": writer, "seq": 1, "message": "signed"}})
        self.assertTrue(self.uplink()["dead"][writer].get("final"))
        hl.reset()
        hl.on_have({"have": {}})
        self.say(writer, "three")
        self.assertEqual(self.uploaded(hl), [], "neither a reconnect nor a later event takes it up again")

    def test_a_plain_writer_refused_audience_stays_dead_until_written_again(self):
        self.check_revival("testhost/" + SID)

    def test_a_stream_writer_revives_with_its_audience_claimed(self):
        self.check_revival("testhost/%s~%s" % (SID, sminos.audience_digest([M1, M2])), [M1, M2])

    def test_an_operator_stream_whose_first_position_was_refused(self):
        self.check_revival("testhost/human~%s" % sminos.audience_digest([M1]), [M1])

    def test_a_stream_whose_audience_is_not_known_here_stays_put(self):
        writer = "testhost/%s~%s" % (SID, sminos.audience_digest([M1]))
        self.say(writer, "one")
        hl = self.hl(coded=False)
        hl.on_have({"have": {}})
        hl.took({writer: 1})
        self.refuse(hl, writer, 1)
        self.say(writer, "two")
        self.assertEqual(self.uploaded(hl), [], "no claim to make: nothing goes up in its place")

    def test_a_void_from_elsewhere_is_nothing_to_a_reader(self):
        hl = self.hl()
        hl.on_have({"have": {}})
        v = hublog.seal(RAW_KEY, self.p.id, {"ts": "2026-11-05T00:00:01.000Z", "writer": "other/" + OTHER_SID,
                                              "seq": 1, "kind": "void", "of": 1, "audience": [M1]})
        self.assertEqual(hl.take([v]), (1, []), "imported as the hub sent it")
        sminos.forget_caches()
        self.assertEqual(sminos.view_of(self.p, titles=False).members, [], "no member of it")
        out = subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "chat", "work", "-n", "5"],
                             capture_output=True, text=True, timeout=60, cwd=BASE)
        self.assertIn("(no messages)", out.stdout, out.stdout + out.stderr)
        self.assertEqual(sminos._owed(sminos.log_read(self.p), SID, {}), [], "owed to no one")

    def test_a_void_from_elsewhere_is_nothing_to_a_reader_on_rl10(self):
        """The same void as the endpoint sends it down (RL10), verified."""
        hl = self.hl(coded=False)
        hl.on_have({"have": {}})
        v = endpoint_standin.Endpoint.arriving({"ts": "2026-11-05T00:00:01.000Z", "writer": "other/" + OTHER_SID,
                                               "seq": 1, "kind": "void", "of": 1, "audience": [M1]})
        self.assertEqual(hl.take([v]), (1, []), "imported as the endpoint sent it")
        sminos.forget_caches()
        self.assertEqual(sminos.view_of(self.p, titles=False).members, [], "no member of it")
        out = subprocess.run([sys.executable, "-B", str(SCRIPTS / "sminos.py"), "chat", "work", "-n", "5"],
                             capture_output=True, text=True, timeout=60, cwd=BASE)
        self.assertIn("(no messages)", out.stdout, out.stdout + out.stderr)
        self.assertEqual(sminos._owed(sminos.log_read(self.p), SID, {}), [], "owed to no one")

    def test_a_tombstone_the_hub_sends_is_a_spent_position_never_reported(self):
        hl = self.hl()
        hl.on_have({"have": {}})
        w = "other/human"
        after = hublog.seal(RAW_KEY, self.p.id, {"ts": "2026-11-05T00:00:02.000Z", "writer": w, "seq": 2,
                                                  "kind": "say", "from": "o", "to": "*", "text": "after"})
        self.assertEqual(hl.take([{"writer": w, "seq": 1, "withheld": True}, after]), (1, []),
                         "the tombstone spent, nothing rejected, the writer's next event appended")
        self.assertEqual(hl.spent(), {w: {1}})
        self.assertEqual(hl.vector()[w], 2)


def tearDownModule():
    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
