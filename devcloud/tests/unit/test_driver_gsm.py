"""The driver's Secret Manager (§8.2): a token from the seed by the JWT-bearer
grant, its RS256 signature made with the standard library, then a secret's
latest version. Stand-in servers for Google's token and Secret Manager
endpoints; a throwaway RSA key made by openssl for each run."""
import base64
import hashlib
import http.server
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.parse
from unittest import mock

import _path  # noqa: F401
from driver import gsm
from driver.errors import DriverError


def b64url_decode(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@unittest.skipUnless(shutil.which("openssl"), "openssl makes the test key")
class SecretManagerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-gsm-"))
        key = cls.tmp / "key.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                        "-out", str(key)], check=True, capture_output=True)
        cls.pem = key.read_text()
        cls.public = cls.tmp / "public.pem"
        subprocess.run(["openssl", "pkey", "-in", str(key), "-pubout", "-out", str(cls.public)], check=True,
                       capture_output=True)
        test = cls

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                time.sleep(test.delay)
                body = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
                test.assertions.append(body)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"access_token": "made-up-access-token-77"}).encode())

            def do_GET(self):
                time.sleep(test.delay)
                test.gets.append((self.path, self.headers.get("Authorization")))
                if "missing" in self.path:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"payload": {"data": base64.b64encode(b"the-value\n").decode()}}).encode())

        cls.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        cls.server.handle_error = lambda request, address: None   # a client that gave up mid-answer
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, True)

    def setUp(self):
        type(self).assertions = []
        type(self).gets = []
        type(self).delay = 0
        self.seed = self.tmp / "seed.json"
        self.seed.write_text(json.dumps({"type": "service_account", "client_email": "driver@example.iam",
                                         "private_key_id": "kid1", "private_key": self.pem,
                                         "token_uri": f"{self.base}/token"}))
        patch = mock.patch.dict(os.environ, {"DEVCLOUD_SM_ENDPOINT": self.base})
        patch.start()
        self.addCleanup(patch.stop)

    def test_signs_a_jwt_google_accepts_and_reads_the_secret(self):
        sm = gsm.SecretManager(self.seed, "example-project", clock=lambda: 1_792_000_000)
        self.assertEqual(sm.access("hcloud-token"), "the-value\n")
        self.assertEqual(sm.access("other"), "the-value\n")
        self.assertEqual(len(self.assertions), 1, "one token per process")
        body = self.assertions[0]
        self.assertEqual(body["grant_type"], ["urn:ietf:params:oauth:grant-type:jwt-bearer"])
        header, claims, signature = body["assertion"][0].split(".")
        self.assertEqual(json.loads(b64url_decode(header)), {"alg": "RS256", "typ": "JWT", "kid": "kid1"})
        self.assertEqual(json.loads(b64url_decode(claims)),
                         {"iss": "driver@example.iam", "scope": gsm.SCOPE, "aud": f"{self.base}/token",
                          "iat": 1_792_000_000, "exp": 1_792_003_600})
        # openssl verifies the signature: the standard-library RSA is RS256 as Google reads it.
        signed = self.tmp / "signed"
        signed.write_bytes(f"{header}.{claims}".encode())
        sig = self.tmp / "sig"
        sig.write_bytes(b64url_decode(signature))
        verify = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(self.public), "-signature", str(sig),
                                 str(signed)], capture_output=True, text=True)
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
        path, auth = self.gets[0]
        self.assertEqual(path, "/v1/projects/example-project/secrets/hcloud-token/versions/latest:access")
        self.assertEqual(auth, "Bearer made-up-access-token-77")

    def test_one_deadline_covers_the_token_exchange_and_the_secret_request(self):
        # An uncached token: the exchange spends part of the budget, and the secret request gets only the
        # rest, not the whole budget again (two 0.6 s answers inside 1 s are 1.2 s otherwise).
        type(self).delay = 0.6
        sm = gsm.SecretManager(self.seed, "example-project")
        started = time.monotonic()
        with self.assertRaises(DriverError):
            sm.access("hcloud-token", timeout=1.0)
        self.assertLess(time.monotonic() - started, 1.15)
        self.assertEqual(len(self.assertions), 1, "the token exchange ran")

    def test_no_request_starts_once_the_deadline_has_passed(self):
        ticks = iter([100.0, 100.5, 102.0])     # the deadline set, the exchange started, then past it
        sm = gsm.SecretManager(self.seed, "example-project", monotonic=lambda: next(ticks))
        with self.assertRaises(DriverError) as caught:
            sm.access("hcloud-token", timeout=1.0)
        self.assertIn("time is spent", str(caught.exception))
        self.assertEqual(len(self.assertions), 1)
        self.assertEqual(self.gets, [], "the secret request never started")

    def test_a_missing_secret_is_a_failure_naming_it(self):
        with self.assertRaises(DriverError) as caught:
            gsm.SecretManager(self.seed, "example-project").access("missing-one")
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("missing-one", str(caught.exception))

    def test_no_seed_is_not_a_driver(self):
        with self.assertRaises(DriverError) as caught:
            gsm.SecretManager(self.tmp / "nope.json", "p").access("x")
        self.assertEqual(caught.exception.code, 6)

    def test_pkcs1_keys_too(self):
        rsa = self.tmp / "rsa.pem"
        key = self.tmp / "key.pem"
        for flags in (["-traditional"], []):   # OpenSSL 3 needs the flag; LibreSSL writes PKCS#1 without it
            subprocess.run(["openssl", "rsa", "-in", str(key), *flags, "-out", str(rsa)], capture_output=True)
            if rsa.exists() and "BEGIN RSA PRIVATE KEY" in rsa.read_text():
                break
        if not rsa.exists() or "BEGIN RSA PRIVATE KEY" not in rsa.read_text():
            self.skipTest("this openssl writes no PKCS#1")
        self.assertEqual(gsm.private_key(rsa.read_text()), gsm.private_key(self.pem))
        n, e, d = gsm.private_key(self.pem)
        self.assertEqual(pow(pow(12345, e, n), d, n), 12345)
        self.assertEqual(len(gsm.sign(b"x", (n, e, d))), (n.bit_length() + 7) // 8)
        self.assertEqual(hashlib.sha256(b"x").digest(), pow(int.from_bytes(gsm.sign(b"x", (n, e, d)), "big"), e, n)
                         .to_bytes((n.bit_length() + 7) // 8, "big")[-32:])


if __name__ == "__main__":
    unittest.main()
