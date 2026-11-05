"""EC2's spot interruption notice (the driver's Design §6.6, §4.2): IMDSv2 as a
stand-in HTTP server on loopback — its session token, the 404 it answers until
EC2 has scheduled the interruption, the 401 of an expired token — and the
watch that starts the fast departure once when the notice appears."""

import http.server
import json
import threading
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import departure, ec2spot


class Imds(http.server.BaseHTTPRequestHandler):
    """IMDSv2: PUT /latest/api/token gives a token; a GET without a live one is 401."""
    world = None

    def log_message(self, *args):
        pass

    def do_PUT(self):
        w = self.world
        w.requests.append(("PUT", self.path, self.headers.get("X-aws-ec2-metadata-token-ttl-seconds")))
        if self.path != "/latest/api/token" or not self.headers.get("X-aws-ec2-metadata-token-ttl-seconds"):
            return self.answer(400, b"")
        w.issued += 1
        token = f"token-{w.issued}"
        w.live.add(token)
        self.answer(200, token.encode())

    def do_GET(self):
        w = self.world
        token = self.headers.get("X-aws-ec2-metadata-token")
        w.requests.append(("GET", self.path, token))
        if token not in w.live:
            return self.answer(401, b"")
        if self.path != "/latest/meta-data/spot/instance-action" or w.action is None:
            return self.answer(404, b"<?xml version=\"1.0\"?><title>404 - Not Found</title>")
        self.answer(200, json.dumps(w.action).encode())

    def answer(self, code, body):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class World:
    def __init__(self):
        self.requests = []
        self.issued = 0
        self.live = set()
        self.action = None


class ImdsBase(unittest.TestCase):
    def setUp(self):
        self.world = World()
        handler = type("Handler", (Imds,), {"world": self.world})
        self.server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.root = f"http://127.0.0.1:{self.server.server_port}"
        self.clock = 1000.0

    def imds(self, root=None):
        return ec2spot.Imds(root=root or self.root, clock=lambda: self.clock)


class NoticeTest(ImdsBase):
    def test_no_notice_until_ec2_schedules_one(self):
        imds = self.imds()
        self.assertIsNone(imds.instance_action(), "a 404 is no notice")
        self.world.action = {"action": "terminate", "time": "2026-11-04T10:02:00Z"}
        self.assertEqual(imds.instance_action(), {"action": "terminate", "time": "2026-11-04T10:02:00Z"})
        puts = [r for r in self.world.requests if r[0] == "PUT"]
        self.assertEqual(len(puts), 1, "the session token is kept between asks")
        self.assertEqual(puts[0][2], str(ec2spot.TOKEN_TTL))

    def test_the_session_token_is_renewed_when_it_expires(self):
        imds = self.imds()
        imds.instance_action()
        self.clock += ec2spot.TOKEN_TTL
        imds.instance_action()
        self.assertEqual(self.world.issued, 2, "an expired token was used again")
        # A token EC2 no longer takes (401) before its time is renewed at once, and the ask repeated.
        self.world.live.clear()
        self.world.action = {"action": "stop", "time": "2026-11-04T10:02:00Z"}
        self.assertEqual(imds.instance_action()["action"], "stop")
        self.assertEqual(self.world.issued, 3)

    def test_an_unreachable_or_strange_imds_is_no_notice(self):
        self.server.shutdown()
        self.server.server_close()
        self.assertIsNone(self.imds().instance_action())
        self.assertIsNone(self.imds(root="http://127.0.0.1:9").instance_action())

    def test_an_answer_without_an_action_is_no_notice(self):
        self.world.action = {"note": "not a notice"}
        self.assertIsNone(self.imds().instance_action())


class WatchTest(ImdsBase):
    def watch(self, appear_after=None, polls=5):
        """The watch's exit, or None when it was still polling after `polls`
        sleeps; the departures it started; its sleeps."""
        departed, sleeps = [], []

        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == appear_after:
                self.world.action = {"action": "terminate", "time": "2026-11-04T10:02:00Z"}
            if len(sleeps) >= polls:
                raise StopIteration
        try:
            code = ec2spot.watch(self.imds(), lambda: departed.append(1) or departure.FAILED, say=lambda line: None,
                                 sleep=sleep)
        except StopIteration:
            code = None
        return code, departed, sleeps

    def test_a_notice_starts_one_departure_and_the_watch_ends(self):
        code, departed, sleeps = self.watch(appear_after=3)
        self.assertEqual((code, departed), (0, [1]), "once, whatever the departure's outcome")
        self.assertEqual(sleeps, [ec2spot.EVERY] * 3)
        self.assertEqual(self.world.issued, 1)

    def test_no_notice_departs_nothing(self):
        self.assertEqual(self.watch()[:2], (None, []))

    def test_an_unreachable_imds_departs_nothing(self):
        self.server.shutdown()
        self.server.server_close()
        self.assertEqual(self.watch()[:2], (None, []))


class PreemptedTest(ImdsBase):
    """`preempted()`, which the shutdown unit's and the watch's departure ask:
    GCE's metadata server first, then EC2's notice."""

    def test_ec2_s_notice_counts_when_gce_answers_nothing(self):
        env = {"GCE_METADATA_HOST": "127.0.0.1:9", ec2spot.ENDPOINT_VAR: self.root}
        with mock.patch.dict("os.environ", env):
            self.assertFalse(departure._preempted())
            self.world.action = {"action": "terminate", "time": "2026-11-04T10:02:00Z"}
            self.assertTrue(departure._preempted())


if __name__ == "__main__":
    unittest.main()
