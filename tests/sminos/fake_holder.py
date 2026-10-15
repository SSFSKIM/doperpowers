#!/usr/bin/env python3
"""A session's process for the `claude` stand-in (fake_claude.py): it listens
on its inbox socket, appends each frame's text to its log as a JSON string
per line, and runs until it is stopped."""
import json
import socket
import sys

path, out = sys.argv[1], sys.argv[2]
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(path)
s.listen(16)
while True:
    c, _ = s.accept()
    data = b""
    while True:
        chunk = c.recv(65536)
        if not chunk:
            break
        data += chunk
    c.close()
    with open(out, "a") as f:
        for line in data.decode().splitlines():
            if line.strip():
                f.write(json.dumps(json.loads(line)["message"]["content"]) + "\n")
