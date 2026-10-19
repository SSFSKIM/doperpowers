#!/usr/bin/env python3
"""The hub's connections on a network that blackholes IPv6: the hub's name
resolves to IPv6 addresses first, connects to them get no answer at all, and
IPv4 answers. The uplink's stream and POSTs (sminos_uplink.connection) and
enrollment (sminos_hub.redeem_once) each connect within a small part of their
timeout, an address family that drops everything costing a stagger, not a
timeout per address; a connect nothing answers fails once its timeout is out,
naming what failed.

The dead addresses are listeners on loopback that never accept, their queue
filled, so the kernel drops a SYN to them unanswered as a blackholed route
does; getaddrinfo answers for the hub's name with those first and a live
listener after. On loopback without IPv6 the dead addresses are IPv4 ones and
the order check is skipped. Hermetic: HOME and SMINOS_HOME are temporary;
nothing leaves loopback.
"""

import http.server
import os
import select
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN_ROOT, "skills", "sminos", "scripts")
T = tempfile.mkdtemp(prefix="she.", dir="/tmp")
os.environ.update(HOME=os.path.join(T, "home"), SMINOS_HOME=os.path.join(T, "s"))
os.makedirs(os.environ["HOME"])
os.makedirs(os.environ["SMINOS_HOME"])
sys.path.insert(0, SCRIPTS)

import sminos_hub as hub  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

HUB = "hub.test"
TIMEOUT = 2.0


def dead_listener(family, host):
    """(listener, the connections that fill its queue, port): it never
    accepts, so once its queue is full a connect to it gets no answer."""
    lst = socket.socket(family, socket.SOCK_STREAM)
    lst.bind((host, 0))
    lst.listen(1)
    port = lst.getsockname()[1]
    fillers = []
    for _ in range(512):
        c = socket.socket(family, socket.SOCK_STREAM)
        c.setblocking(False)
        c.connect_ex((host, port))
        fillers.append(c)
        if not select.select([], [c], [], 0.2)[1]:
            return lst, fillers, port
    raise RuntimeError("the listen queue on %s never filled" % host)


class Answer(http.server.BaseHTTPRequestHandler):
    def answer(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = answer

    def log_message(self, *args):
        pass


class HappyEyeballs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.dead = dead_listener(socket.AF_INET6, "::1")
            cls.dead_info = (socket.AF_INET6, ("::1", cls.dead[2], 0, 0))
        except OSError:
            cls.dead = dead_listener(socket.AF_INET, "127.0.0.1")
            cls.dead_info = (socket.AF_INET, ("127.0.0.1", cls.dead[2]))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Answer)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.live = ("127.0.0.1", cls.server.server_address[1])
        closed = socket.socket()
        closed.bind(("127.0.0.1", 0))
        cls.refused = ("127.0.0.1", closed.getsockname()[1])
        closed.close()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        lst, fillers, _ = cls.dead
        for c in fillers:
            c.close()
        lst.close()
        shutil.rmtree(T, ignore_errors=True)

    def resolving(self, *addrs):
        """getaddrinfo answering for the hub's name with these, in order:
        "dead" (no answer), "live" (the HTTP listener), "refused"."""
        real = socket.getaddrinfo
        infos = []
        for a in addrs:
            family, sockaddr = self.dead_info if a == "dead" else (socket.AF_INET, getattr(self, a))
            infos.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr))

        def fake(host, *args, **kwargs):
            return list(infos) if host == HUB else real(host, *args, **kwargs)

        return mock.patch.object(socket, "getaddrinfo", fake)

    def test_uplink_connects_past_dead_ipv6(self):
        with self.resolving("dead", "dead", "live", "live"):
            conn = uplink.connection({"hub": "http://%s:%d" % (HUB, self.live[1])}, TIMEOUT)
            start = time.monotonic()
            conn.connect()
            took = time.monotonic() - start
            self.assertLess(took, TIMEOUT / 2, "the connect took %.2fs of a %gs timeout" % (took, TIMEOUT))
            self.assertEqual(conn.sock.gettimeout(), TIMEOUT, "the I/O bound is the caller's timeout")
            conn.request("GET", "/machine/stream")
            self.assertEqual(conn.getresponse().status, 200)
            conn.close()

    def test_enrollment_connects_past_dead_ipv6(self):
        with self.resolving("dead", "dead", "live", "live"), mock.patch.object(hub, "TIMEOUT", TIMEOUT):
            start = time.monotonic()
            status, answer = hub.redeem_once("http://%s:%d" % (HUB, self.live[1]), "token", "m")
            took = time.monotonic() - start
        self.assertEqual((status, answer), (200, {"ok": True}))
        self.assertLess(took, TIMEOUT / 2, "the redemption took %.2fs of a %gs timeout" % (took, TIMEOUT))

    def test_families_interleaved(self):
        if self.dead_info[0] != socket.AF_INET6:
            self.skipTest("no IPv6 on loopback")
        with self.resolving("dead", "dead", "dead", "dead", "live"):
            conn = uplink.connection({"hub": "http://%s:%d" % (HUB, self.live[1])}, 3.0)
            start = time.monotonic()
            conn.connect()
            took = time.monotonic() - start
            conn.close()
        # Interleaved, IPv4 is the second attempt, one stagger in; in order,
        # the fifth, four staggers in.
        self.assertLess(took, 0.75, "IPv4 was tried %.2fs in, behind the IPv6 addresses" % took)

    def test_nothing_answers(self):
        with self.resolving("dead", "refused", "dead"):
            conn = uplink.connection({"hub": "http://%s:%d" % (HUB, self.live[1])}, TIMEOUT)
            start = time.monotonic()
            with self.assertRaises(OSError) as raised:
                conn.connect()
            took = time.monotonic() - start
            conn.close()
        self.assertLess(took, TIMEOUT + 0.75, "a connect bounded by %gs took %.2fs" % (TIMEOUT, took))
        self.assertIn("Connection refused", str(raised.exception))
        self.assertIn(HUB, str(raised.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
