#!/usr/bin/env python3
"""A live session's inbox socket, as the engine serves one, for the suites:
inbox_standin.py <socket> <received>.

The receiver's side of the contract, as Claude Code 2.1.303 serves a
session's inbox (watched engine to engine, #100): it reads the newline-ended
JSON lines a sender writes, writes nothing back on the connection, and ends
its side once the sender has ended its own. The engine's own sender
(SendMessage) never reads its socket: a byte written back keeps that socket
from closing, and the send is reported failed at its 5 s timeout although the
frame arrived. sminos's sender (send_frame) ends its side after its line and
returns at the receiver's close. test_inbox_contract.py holds this stand-in
and send_frame to that contract.

Each connection's bytes are appended to <received> before the close, so a
sender that has returned finds them there; connections are served one at a
time. While <received>.hold exists, a frame is written and marked
(<received>.held) but the close waits for the hold to lift: a deliverer
killed in that window has pushed without settling. A connection that sends
nothing (a liveness probe connects and closes) is never held: the mark means
a frame arrived.
"""
import os
import socket
import sys
import time

path, out = sys.argv[1], sys.argv[2]
try:
    os.unlink(path)
except FileNotFoundError:
    pass
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
# The path appears only once the socket is listening: waiters treat the file
# as "listening". Bound under a short temporary name beside it (a unix socket
# path is limited to about 104 bytes), then renamed.
tmp = os.path.join(os.path.dirname(path) or ".", ".inbox-%d" % os.getpid())
try:
    os.unlink(tmp)
except FileNotFoundError:
    pass
srv.bind(tmp)
srv.listen(8)
os.rename(tmp, path)
while True:
    c, _ = srv.accept()
    buf = b""
    try:
        while True:
            chunk = c.recv(65536)
            if not chunk:
                break
            buf += chunk
    except OSError:
        pass
    with open(out, "ab") as f:
        f.write(buf)
    if buf and os.path.exists(out + ".hold"):
        open(out + ".held", "w").close()
        while os.path.exists(out + ".hold"):
            time.sleep(0.02)
    c.close()
