"""Secret Manager for the driver (§8.2): an access token taken from the seed
key file, then each account credential read on every provider call (§6.1).

The token comes from Google's OAuth JWT-bearer grant: a JWT signed with the
seed's RSA key (RS256, PKCS#1 v1.5 over SHA-256, done here with Python's
integers, since the standard library has no RSA), exchanged at the key's
`token_uri`. Nothing is written to disk and no gcloud configuration is
touched, so the always-on Mac's own gcloud account stays as it is; and no
gcloud start-up is paid on a loaded Mac. `DEVCLOUD_SM_ENDPOINT` points the
reads at a stand-in, as on hosts."""

import base64
import hashlib
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

from .errors import FAILED, NOT_DRIVER, DriverError, Spent

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
# DigestInfo for SHA-256 (RFC 8017 §9.2, note 1).
SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


# --- the seed's RSA key ------------------------------------------------------------

def _der(data, i):
    """(tag, value, next index) of the DER element at `i`."""
    tag = data[i]
    length = data[i + 1]
    i += 2
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[i:i + count], "big")
        i += count
    return tag, data[i:i + length], i + length


def _sequence(data):
    items, i = [], 0
    while i < len(data):
        tag, value, i = _der(data, i)
        items.append((tag, value))
    return items


def private_key(pem):
    """(n, e, d) of a PKCS#8 (`BEGIN PRIVATE KEY`) or PKCS#1 (`BEGIN RSA
    PRIVATE KEY`) RSA key."""
    lines = [line.strip() for line in pem.strip().splitlines()]
    body = base64.b64decode("".join(line for line in lines if line and not line.startswith("-----")))
    tag, outer, _ = _der(body, 0)
    items = _sequence(outer)
    if len(items) >= 3 and items[1][0] == 0x30 and items[2][0] == 0x04:      # PKCS#8 → the inner PKCS#1
        _, outer, _ = _der(items[2][1], 0)
        items = _sequence(outer)
    numbers = [int.from_bytes(value, "big") for tag, value in items if tag == 0x02]
    if len(numbers) < 4:
        raise ValueError("not an RSA private key")
    _, n, e, d = numbers[:4]
    return n, e, d


def sign(message, key):
    """RS256: PKCS#1 v1.5 over SHA-256 of `message` with key (n, e, d)."""
    n, _, d = key
    size = (n.bit_length() + 7) // 8
    digest = SHA256_PREFIX + hashlib.sha256(message).digest()
    encoded = b"\x00\x01" + b"\xff" * (size - len(digest) - 3) + b"\x00" + digest
    return pow(int.from_bytes(encoded, "big"), d, n).to_bytes(size, "big")


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def assertion(seed, now):
    header = {"alg": "RS256", "typ": "JWT"}
    if seed.get("private_key_id"):
        header["kid"] = seed["private_key_id"]
    claims = {"iss": seed["client_email"], "scope": SCOPE, "aud": seed["token_uri"], "iat": int(now),
              "exp": int(now) + 3600}
    signing = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
    return f"{signing}.{_b64url(sign(signing.encode(), private_key(seed['private_key'])))}"


# --- Secret Manager -----------------------------------------------------------------

REQUEST_TIMEOUT = 30


class SecretManager:
    """`access(secret_id)` → the latest version's value (str). The token is
    taken once per process. `timeout`, when given, is one deadline for the
    whole read: the token exchange, when it runs, and the secret request each
    get what is left of it, and neither starts once it has passed (a bounded
    run's budget)."""

    def __init__(self, seed_path, project, clock=time.time, monotonic=time.monotonic):
        self.seed_path = seed_path
        self.project = project
        self.clock = clock
        self.monotonic = monotonic
        self._token = None

    def _left(self, deadline, what):
        """The next request's timeout: at most REQUEST_TIMEOUT, and what is
        left before `deadline`; Spent once nothing is."""
        if deadline is None:
            return REQUEST_TIMEOUT
        left = deadline - self.monotonic()
        if left <= 0:
            raise Spent(f"Secret Manager: {what} not started: the bounded run's time is spent")
        return min(REQUEST_TIMEOUT, left)

    def _seed(self):
        try:
            seed = json.loads(pathlib.Path(self.seed_path).read_text())
        except FileNotFoundError:
            raise DriverError(NOT_DRIVER, f"no seed key at {self.seed_path}: this machine is not a driver") from None
        except ValueError:
            raise DriverError(FAILED, f"the seed key at {self.seed_path} is not JSON") from None
        if seed.get("type") != "service_account" or not all(
                seed.get(k) for k in ("client_email", "private_key", "token_uri")):
            raise DriverError(FAILED, f"the seed at {self.seed_path} is not a service-account key file")
        return seed

    def token(self, deadline=None):
        if self._token is None:
            seed = self._seed()
            try:
                body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                               "assertion": assertion(seed, self.clock())}).encode()
            except ValueError:
                raise DriverError(FAILED, "the seed's private key is not an RSA key") from None
            request = urllib.request.Request(seed["token_uri"], data=body,
                                             headers={"Content-Type": "application/x-www-form-urlencoded"})
            try:
                timeout = self._left(deadline, "the token exchange")
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    self._token = json.load(response).get("access_token")
            except urllib.error.HTTPError as error:
                error.close()
                raise DriverError(FAILED, f"the seed's token exchange was refused (HTTP {error.code})") from None
            except (urllib.error.URLError, OSError, ValueError) as error:
                raise DriverError(FAILED, f"the seed's token exchange failed ({type(error).__name__})") from None
            if not self._token:
                raise DriverError(FAILED, "the seed's token exchange returned no token")
        return self._token

    def access(self, secret_id, timeout=None):
        deadline = None if timeout is None else self.monotonic() + timeout
        endpoint = os.environ.get("DEVCLOUD_SM_ENDPOINT", "https://secretmanager.googleapis.com").rstrip("/")
        url = (f"{endpoint}/v1/projects/{urllib.parse.quote(self.project, safe='')}"
               f"/secrets/{urllib.parse.quote(secret_id, safe='')}/versions/latest:access")
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token(deadline)}"})
        try:
            timeout = self._left(deadline, f"the read of {secret_id}")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.load(response)
        except urllib.error.HTTPError as error:
            error.close()
            raise DriverError(FAILED, f"Secret Manager refused {secret_id} (HTTP {error.code})") from None
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise DriverError(FAILED, f"Secret Manager did not answer for {secret_id} ({type(error).__name__})") from None
        try:
            return base64.b64decode(body["payload"]["data"], validate=True).decode()
        except (KeyError, TypeError, ValueError):
            raise DriverError(FAILED, f"Secret Manager's answer for {secret_id} has no payload") from None
