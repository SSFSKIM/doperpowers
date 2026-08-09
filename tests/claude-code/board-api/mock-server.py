#!/usr/bin/env python3
"""Fixture-driven mock of the A1 board API for the hermetic unit tier.

Usage: mock-server.py <fixtures.json> <port>
fixtures.json: [{"method": "POST", "path": "/tickets", "status": 200,
                 "body": {...}, "once": false}, ...]
First match wins; "once" entries are consumed. Every request is appended to
<fixtures.json>.log as {"method","path","auth","body"} — tests assert on it.
Responses are contract-shaped (API.md); awkward cases (409 bodies, empty
lists) come from the real service's observed output — note that the error
envelope is NESTED: {"error": {"code": ..., "message": ...}}.
"""
import json, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

FIXTURES = json.load(open(sys.argv[1]))
LOG = open(sys.argv[1] + ".log", "a")
LOCK = threading.Lock()

class H(BaseHTTPRequestHandler):
    def _handle(self):
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length).decode() if length else ""
        with LOCK:
            LOG.write(json.dumps({"method": self.command, "path": self.path,
                                  "auth": self.headers.get("authorization", ""),
                                  "body": raw}) + "\n"); LOG.flush()
            for f in FIXTURES:
                if f.get("used"): continue
                if f["method"] == self.command and self.path.startswith(f["path"]):
                    if f.get("once"): f["used"] = True
                    body = json.dumps(f.get("body", {})).encode()
                    self.send_response(f.get("status", 200))
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(body)))
                    self.end_headers(); self.wfile.write(body); return
        self.send_response(404); self.end_headers()
    do_GET = do_POST = do_PUT = _handle
    def log_message(self, *a): pass

HTTPServer(("127.0.0.1", int(sys.argv[2])), H).serve_forever()
