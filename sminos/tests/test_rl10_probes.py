#!/usr/bin/env python3
"""rl10_probes.py, what the conformance replay checks in place of its probes,
over a conversation that holds more than one project and a channel (MAWS's
cases for a message under a channel's id): a position is a log's, a words?
is held to the log it names, and a session is this machine's when the replay
staged it here."""

import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import rl10_probes as probes  # noqa: E402

P, Q, C = "p-id", "q-id", "5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c"
S1, S2, S8 = "s1", "s2", "s8"


def ev(writer, seq, text, **more):
    return {"ts": "2026-10-27T18:11:00.000Z", "writer": writer, "seq": seq, "kind": "human", "from": "human",
            "to": [{"session": S8, "alias": "integrator"}], "text": text, **more}


class Bodies(unittest.TestCase):
    def test_one_writer_in_two_logs_is_two_positions(self):
        """The operator's writer holds seq 1 in a project's log and in a channel's."""
        self.assertEqual(probes.bodies_twice([(P, ev("host/human", 1, "run the tests")),
                                              (C, ev("host/human", 1, "pick up the review"))]), [])

    def test_another_body_at_one_position_is_found(self):
        self.assertEqual(probes.bodies_twice([(P, ev("host/human", 1, "a")), (P, ev("host/human", 1, "b"))]),
                         [(P, "host/human", 1)])

    def test_the_same_body_resent_is_one(self):
        self.assertEqual(probes.bodies_twice([(C, ev("host/human", 2, "a")), (C, ev("host/human", 2, "a"))]), [])


class Asks(unittest.TestCase):
    def setUp(self):
        self.held = {P: {}, Q: {}, C: {("host/human", 1): {**ev("host/human", 1, "pick up"), "verified": {"x": 1}}}}
        self.logs = {pid: (lambda w, s, pid=pid: self.held[pid].get((w, s))) for pid in (P, Q, C)}

    def ask(self, project, event, session=S8, i="w1"):
        return {"t": "words?", "id": i, "project": project, "session": session, "event": event}

    def test_a_channel_s_event_is_read_from_the_channel_s_log(self):
        asks = [self.ask(C, ev("host/human", 1, "pick up"))]
        self.assertEqual(probes.not_as_stored(asks, self.logs), [])
        self.assertEqual(probes.not_in_its_log(asks, self.logs), [])

    def test_another_body_than_the_one_stored_is_found(self):
        asks = [self.ask(C, ev("host/human", 1, "another body"))]
        self.assertEqual(probes.not_as_stored(asks, self.logs), ["w1"])

    def test_a_log_that_holds_no_such_event_or_none_is_found(self):
        asks = [self.ask(P, ev("host/human", 1, "pick up"), i="w1"), self.ask(None, ev("host/human", 1, "x"), i="w2")]
        self.assertEqual(probes.not_in_its_log(asks, self.logs), ["w1", "w2"])

    def test_a_session_staged_here_later_is_a_member(self):
        members = [S1, S2, "s3", "s4", "s5", S8]
        asks = [self.ask(C, ev("host/human", 1, "pick up"), session=S8, i="w1"),
                self.ask(C, ev("host/human", 1, "pick up"), session="elsewhere", i="w2")]
        self.assertEqual(probes.not_members(asks, members), ["w2"])


class Revoked(unittest.TestCase):
    def test_the_same_position_in_another_log_is_another_event(self):
        e = {"writer": "hub/m-b", "seq": 1}
        asks = [{"id": "w1", "project": P, "event": e}, {"id": "w2", "project": C, "event": e}]
        self.assertEqual(probes.asked_again(asks, P, "hub/m-b", 1), ["w1"])


class MachineEvent(unittest.TestCase):
    STEP = {"machine": "b-mini", "session": "human", "seq": 1, "body": {"kind": "human", "text": "hi"}}

    def test_a_scene_with_no_owners_is_unattested(self):
        e = probes.machine_event(self.STEP, "2026-10-27T18:00:00.000Z", "kid")
        self.assertNotIn("attest", e)
        self.assertEqual(e["writer"], "b-mini/human")
        self.assertEqual(e["sig"], {"kid": "kid", "value": "AQ"})

    def test_a_scene_with_owners_is_attested_to_them(self):
        e = probes.machine_event({**self.STEP, "owners": ["m-b"]}, "2026-10-27T18:00:00.000Z", "kid")
        self.assertEqual(e["attest"]["owners"], ["m-b"])


class Order(unittest.TestCase):
    """A channel's line waits for the lines the fixture puts before it: a
    session's member frame before an event that writes to it or from it
    goes up and before an ask about it, and an own event's upload before
    an ask about that event. The edges come from the lines themselves, so
    a line MAWS inserts between them leaves them standing."""

    CH, S8, S7 = "{{channel:C}}", "{{session:S8}}", "{{session:S7}}"

    def member(self, session):
        return {"up": {"t": "member", "session": session, "alias": "a", "project": "{{project:P}}"}}

    def upload(self, writer, seq, to):
        return {"up": {"t": "events", "project": self.CH, "events": [
            {"writer": writer, "seq": seq, "kind": "say", "to": [{"session": s, "alias": "a"} for s in to]}]}}

    def ask(self, session, event, t="words?"):
        return {"up": {"t": t, "id": "w", "project": self.CH, "session": session, "event": event}, "vary": ["id"]}

    def cases(self):
        return [
            {"steps": [self.member(self.S8), self.member(self.S7),
                       self.upload("{{name}}/" + self.S7, 1, [self.S8]),
                       {"down": {"t": "audience", "session": self.S8}},
                       self.ask(self.S8, {"writer": "{{name}}/" + self.S7, "seq": 1, "kind": "say"})]},
            {"steps": [self.member(self.S8),
                       self.ask(self.S8, "{{say:M1}}", t="reach?"),
                       {"up": {"t": "words?", "id": "w", "project": "{{project:P}}", "session": self.S8,
                               "event": {"writer": "{{name}}/human", "seq": 3}}}]},
        ]

    def test_an_upload_waits_for_its_writer_s_and_its_recipients_member_frames(self):
        self.assertEqual(sorted(probes.order_edges(self.cases())[(0, 2)]), [(0, 0), (0, 1)])

    def test_an_ask_about_an_own_event_waits_for_its_member_frame_and_its_upload(self):
        self.assertEqual(sorted(probes.order_edges(self.cases())[(0, 4)]), [(0, 0), (0, 2)])

    def test_an_upload_to_everyone_waits_for_its_writer_s_member_frame_alone(self):
        to_all = {"up": {"t": "events", "project": self.CH, "events": [
            {"writer": "{{name}}/" + self.S7, "seq": 1, "kind": "say", "to": "*"}]}}
        cases = [{"steps": [self.member(self.S8), self.member(self.S7), to_all]}]
        self.assertEqual(probes.order_edges(cases)[(0, 2)], [(0, 1)])

    def test_an_ask_waits_for_the_latest_member_frame_before_it(self):
        self.assertEqual(probes.order_edges(self.cases())[(1, 1)], [(1, 0)])

    def test_a_line_of_no_channel_is_given_no_edge(self):
        self.assertNotIn((1, 2), probes.order_edges(self.cases()))

    def test_a_line_sent_before_what_it_waits_for_fails_though_it_is_sent_again_after(self):
        """The second reading (G13): `ask, predecessor, ask` is the ordering broken, whatever a retry does after:
        the line's first transmission not matched to another line is the one held to its edges."""
        ask = {"t": "words?", "event": "e"}
        frames = [ask, {"t": "member"}, {"t": "events"}, ask]
        matched = {(0, 1): (1, 1), (0, 2): (1, 2)}
        after = probes.after_index([(0, 1), (0, 2)], matched, 1)
        self.assertEqual(after, 2)
        self.assertEqual(probes.early_match(frames, lambda f: f == ask, after, set()), 0)
        self.assertIsNone(probes.early_match(frames[1:], lambda f: f == ask, after - 1, set()), "in order")
        self.assertIsNone(probes.early_match(frames, lambda f: f == ask, after, {0}),
                          "an earlier frame matched to another line is that line's")

    def test_an_upload_sent_first_in_a_batch_of_another_shape_is_sent_before_what_it_waits_for(self):
        """The final reading (H7): an upload line is followed by its events' identity (log, writer, seq), not the
        batch's shape: its event gone up at 0 beside another, ahead of the member frame it waits for, is early,
        though the frame the fixture names (the event alone) comes after."""
        e1 = {"writer": "h/s7", "seq": 1, "kind": "say", "text": "a"}
        e2 = {"writer": "h/s7", "seq": 2, "kind": "say", "text": "b"}
        want = {"t": "events", "project": "C", "events": [e1]}
        frames = [{"t": "events", "project": "C", "events": [e1, e2]}, {"t": "member"},
                  {"t": "events", "project": "C", "events": [e1]}]
        exact = lambda f: f == want  # noqa: E731
        self.assertEqual(probes.early_match(frames, probes.sent_as(want, exact), 1, set()), 0)
        self.assertIsNone(probes.early_match(frames, probes.sent_as(want, exact), 1, {0}),
                          "a batch matched to another line is that line's")
        other = [{"t": "events", "project": "Q", "events": [e1]}, {"t": "events", "project": "C", "events": [e2]}]
        self.assertIsNone(probes.early_match(other, probes.sent_as(want, exact), 1, set()),
                          "the same position in another log, or another position, is another event")
        self.assertIs(probes.sent_as({"t": "member"}, exact), exact, "a line that is no upload: as matched")

    def test_a_line_matched_on_another_connection_or_not_at_all_does_not_hold_one_back(self):
        self.assertEqual(probes.after_index([(0, 1), (0, 2)], {(0, 1): (0, 7)}, 1), -1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
