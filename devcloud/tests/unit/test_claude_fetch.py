"""The cached download must reject bad releases before publishing executable bytes."""
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "image" / "fetch-claude.sh"
BINARY = b"#!/bin/sh\necho fixture-native-binary\n"
VERSION = "2.1.308"


class ClaudeFetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.destination = self.root / "cached"
        self.requests = []
        self.replies = {
            "/latest": VERSION.encode(),
            f"/{VERSION}/manifest.json": json.dumps({"version": VERSION, "platforms": {
                p: {"checksum": hashlib.sha256(BINARY).hexdigest(), "size": len(BINARY)}
                for p in ("linux-x64", "linux-arm64")}}).encode(),
            f"/{VERSION}/linux-x64/claude": BINARY,
            f"/{VERSION}/linux-arm64/claude": BINARY,
        }
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append(self.path)
                body = owner.replies.get(self.path)
                self.send_response(200 if body is not None else 403)
                self.end_headers()
                self.wfile.write(body or b"refused")

            def log_message(self, *_):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        # uname is the external architecture boundary; all download and hash work is real.
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def stop_server(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def fetch(self, arch="x86_64"):
        uname = self.bin / "uname"
        uname.write_text(f"#!/bin/sh\necho {arch}\n")
        uname.chmod(0o755)
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                   DEVCLOUD_CLAUDE_RELEASE_URL=f"http://127.0.0.1:{self.server.server_port}")
        return subprocess.run(["bash", str(SCRIPT), str(self.destination)], env=env,
                              text=True, capture_output=True, timeout=30)

    def test_fetches_and_checks_both_image_architectures(self):
        for arch, platform in (("x86_64", "linux-x64"), ("aarch64", "linux-arm64")):
            with self.subTest(arch=arch):
                result = self.fetch(arch)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((self.destination / "claude").read_bytes(), BINARY)
                self.assertEqual((self.destination / "version").read_text().strip(), VERSION)
                self.assertTrue(os.access(self.destination / "claude", os.X_OK))
                self.assertIn(f"/{VERSION}/{platform}/claude", self.requests)

    def test_refusing_endpoint_fails_without_publishing(self):
        self.replies.clear()
        result = self.fetch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("403", result.stderr)
        self.assertFalse((self.destination / "claude").exists())

    def test_checksum_mismatch_fails_without_publishing(self):
        self.replies[f"/{VERSION}/linux-x64/claude"] = b"corrupted binary"
        result = self.fetch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum", result.stderr.lower())
        self.assertFalse((self.destination / "claude").exists())

    def test_missing_platform_checksum_fails_before_binary_fetch(self):
        self.replies[f"/{VERSION}/manifest.json"] = b'{"platforms": {}}'
        result = self.fetch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum", result.stderr.lower())
        self.assertNotIn(f"/{VERSION}/linux-x64/claude", self.requests)

    def test_non_version_response_is_not_used_as_a_path(self):
        self.replies["/latest"] = b"2.1.308/../../unexpected"
        result = self.fetch()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.requests, ["/latest"])
        self.assertIn("version", result.stderr.lower())

    def test_unsupported_architecture_fails_before_network(self):
        result = self.fetch("s390x")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.requests, [])
        self.assertIn("architecture", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
