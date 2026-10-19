#!/usr/bin/env python3
"""The receiver's contract of a session's inbox socket, as the engine keeps it,
and the suites' stand-in for it (inbox_standin.py) and sminos's sender
(send_frame) held to it.

Watched on Claude Code 2.1.303, engine to engine and engine to stand-in
(#100): a session's inbox reads the newline-ended JSON lines a sender writes,
writes nothing back on the connection, and ends its side once the sender has
ended its own. The engine's own sender (SendMessage) writes its line, ends
its side (150 ms later on macOS) and waits for the close, never reading: an
inbox that wrote back an acknowledgement made every SendMessage to it time
out at 5 s and report "Failed to send" although the frame had arrived, and
the model sent it again. A stand-in that answers is a receiver no engine is,
so this pins the stand-in, and send_frame's wait for the close, to the
engine's side.

Hermetic: HOME and SMINOS_HOME are temporary; nothing reaches beyond this
run's directory.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", "sminos", "scripts")
STANDIN = os.path.join(HERE, "inbox_standin.py")
T = tempfile.mkdtemp(prefix="smi.", dir="/tmp")
os.environ.update(HOME=os.path.join(T, "home"), SMINOS_HOME=os.path.join(T, "s"), DAEMON_HOST="testhost")
for k in ("CLAUDE_CODE_SESSION_ID", "SMNS_INTERNAL", "DAEMON_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(k, None)
os.makedirs(os.path.join(os.environ["HOME"], ".claude", "sessions"))
os.makedirs(os.environ["SMINOS_HOME"])
sys.path.insert(0, SCRIPTS)

import sminos  # noqa: E402

LINE = json.dumps({"type": "user", "message": {"role": "user", "content": "hello"}}) + "\n"


def wait_for(test, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if test():
            return True
        time.sleep(0.02)
    return False


class Contract(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=T)
        self.sock = os.path.join(self.dir, "in.sock")
        self.received = os.path.join(self.dir, "in.received")
        self.proc = subprocess.Popen([sys.executable, STANDIN, self.sock, self.received])
        self.assertTrue(wait_for(lambda: os.path.exists(self.sock)), "the stand-in never listened")

    def tearDown(self):
        self.proc.kill()
        self.proc.wait()
        shutil.rmtree(self.dir, ignore_errors=True)

    def frames(self):
        try:
            with open(self.received) as f:
                return [line for line in f.read().splitlines() if line.strip()]
        except FileNotFoundError:
            return []

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(self.sock)
        return s

    def test_an_engine_sender_gets_nothing_back_and_the_close_after_its_end(self):
        """The engine's sender: its line, its end 150 ms later, then it waits
        for the close and fails on a timeout. Not a byte comes back, and the
        close follows its end at once."""
        s = self.connect()
        try:
            s.sendall(LINE.encode())
            time.sleep(0.15)
            s.shutdown(socket.SHUT_WR)
            ended = time.time()
            got = s.recv(4096)
            self.assertEqual(got, b"", "the inbox wrote back on the connection")
            self.assertLess(time.time() - ended, 2.0, "the close did not follow the sender's end")
        finally:
            s.close()
        self.assertEqual(self.frames(), [LINE.strip()])

    def test_the_inbox_keeps_the_connection_until_the_senders_end(self):
        """It reads to the sender's end: a sender that has written its line
        and not yet ended its side sees neither a byte nor a close."""
        s = self.connect()
        try:
            s.sendall(LINE.encode())
            s.settimeout(0.5)
            with self.assertRaises(socket.timeout):
                s.recv(4096)
            s.settimeout(5)
            s.shutdown(socket.SHUT_WR)
            self.assertEqual(s.recv(4096), b"")
        finally:
            s.close()

    def test_a_probe_leaves_nothing(self):
        """A liveness probe connects and closes: nothing is recorded, and the
        next frame is served."""
        self.assertTrue(sminos.socket_ok(self.sock))
        sminos.send_frame(self.sock, "after the probe", "tester")
        self.assertEqual(len(self.frames()), 1)

    def test_send_frame_delivers_once_and_returns_at_the_close(self):
        started = time.time()
        sminos.send_frame(self.sock, "hello there", "tester")
        self.assertLess(time.time() - started, 2.0, "send_frame waited for something the inbox never sends")
        frames = self.frames()
        self.assertEqual(len(frames), 1, frames)
        frame = json.loads(frames[0])
        self.assertEqual(frame["type"], "user")
        self.assertIn("hello there", frame["message"]["content"])

    def test_send_frame_waits_for_the_inbox_close(self):
        """send_frame returns at the receiver's close, not at an answer: while
        the stand-in holds the close, the sender is still waiting."""
        open(self.received + ".hold", "w").close()
        done = threading.Event()
        threading.Thread(target=lambda: (sminos.send_frame(self.sock, "held", "tester"), done.set()),
                         daemon=True).start()
        self.assertTrue(wait_for(lambda: os.path.exists(self.received + ".held")), "the frame never arrived")
        self.assertFalse(done.wait(0.3), "send_frame returned before the inbox closed")
        os.unlink(self.received + ".hold")
        self.assertTrue(done.wait(2), "send_frame did not return at the close")
        self.assertEqual(len(self.frames()), 1)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(T, ignore_errors=True)
