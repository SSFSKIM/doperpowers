"""A minimal WebSocket client (RFC 6455) for the session plane's tests: the
browser's side of DX3 against DC3's local hub, which only a browser socket can
ask for a subscription. Text frames only, client frames masked, pings
answered; every JSON frame received is kept in order, DX2/DX3 `part` sets
joined. For tests: no TLS, no extensions."""

import base64
import json
import os
import socket
import struct
import threading
import urllib.parse


class WebSocket:
    def __init__(self, url, timeout=10):
        u = urllib.parse.urlsplit(url)
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = (u.path or "/") + ("?" + u.query if u.query else "")
        self.sock.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
                           % (path, u.hostname, u.port or 80, key)).encode())
        head = b""
        try:
            while b"\r\n\r\n" not in head:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise OSError("the hub closed the upgrade")
                head += chunk
            head, self.buf = head.split(b"\r\n\r\n", 1)
            status = head.split(b"\r\n", 1)[0]
            if b" 101 " not in status + b" ":
                raise OSError("the upgrade was refused: %s" % head.decode("utf-8", "replace")[:300])
        except OSError:
            self.sock.close()
            raise
        self.sock.settimeout(None)
        self.frames = []
        self.lock = threading.Lock()
        self.parts = {}
        self.closed = False
        self.send_lock = threading.Lock()
        threading.Thread(target=self.read_loop, daemon=True).start()

    def read_exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise OSError("closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def raw_send(self, opcode, payload):
        mask = os.urandom(4)
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 1 << 16:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self.send_lock:
            self.sock.sendall(head + mask + body)

    def send(self, frame):
        self.raw_send(0x1, json.dumps(frame).encode())

    def read_loop(self):
        message = b""
        try:
            while True:
                b0, b1 = self.read_exact(2)
                opcode, n = b0 & 0x0F, b1 & 0x7F
                if n == 126:
                    n = struct.unpack(">H", self.read_exact(2))[0]
                elif n == 127:
                    n = struct.unpack(">Q", self.read_exact(8))[0]
                mask = self.read_exact(4) if b1 & 0x80 else None
                payload = self.read_exact(n)
                if mask:
                    payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
                if opcode == 0x9:
                    self.raw_send(0xA, payload)
                elif opcode == 0x8:
                    return
                elif opcode in (0x0, 0x1):
                    message += payload
                    if b0 & 0x80:
                        self.take(json.loads(message))
                        message = b""
        except (OSError, ValueError):
            pass
        finally:
            self.closed = True

    def take(self, frame):
        if frame.get("t") == "part":
            held = self.parts.setdefault(frame["id"], {})
            held[frame["index"]] = frame["data"]
            if len(held) < frame["count"]:
                return
            del self.parts[frame["id"]]
            frame = json.loads("".join(held[i] for i in range(frame["count"])))
        with self.lock:
            self.frames.append(frame)

    def received(self):
        with self.lock:
            return list(self.frames)

    def close(self):
        try:
            self.raw_send(0x8, b"")
        except OSError:
            pass
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
