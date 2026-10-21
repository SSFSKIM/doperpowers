"""Google Cloud Secret Manager's REST API from the standard library, and the
access tokens that call it — from the seed key activated into a root-private
gcloud configuration, or from the GCE metadata server. The user's own gcloud
state is never this path's.

Two environment variables point these at stand-ins (the tests' fakes):
`DEVCLOUD_SM_ENDPOINT` (default https://secretmanager.googleapis.com) and
`GCE_METADATA_HOST`, the variable Google's client libraries read (default
metadata.google.internal)."""

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from . import ledger, proc
from .proc import StepError, run

GCLOUD_CONFIG = "/var/lib/devcloud/gcloud"


class AccessError(Exception):
    """A secret could not be read; the message names a status, never a value."""


def _endpoint():
    return os.environ.get("DEVCLOUD_SM_ENDPOINT", "https://secretmanager.googleapis.com").rstrip("/")


def _metadata_root():
    return f"http://{os.environ.get('GCE_METADATA_HOST', 'metadata.google.internal')}/computeMetadata/v1"


def _gcloud_env():
    env = dict(os.environ, CLOUDSDK_CONFIG=GCLOUD_CONFIG, CLOUDSDK_CORE_DISABLE_PROMPTS="1")
    return env


class Tokens:
    """Access tokens for the seed the descriptor names; one per run, cached."""

    def __init__(self, desc):
        self.desc = desc
        self._token = None

    def activate(self):
        """Step 3 for a key-file seed: the key activated into the root-private
        configuration every later token comes from."""
        if self.desc.seed_kind != "file":
            return
        if not os.path.isfile(self.desc.seed_path):
            raise StepError(f"no seed key at {self.desc.seed_path}")
        ledger.add(GCLOUD_CONFIG)    # the activated key and its tokens (Design §6.5)
        os.makedirs(GCLOUD_CONFIG, mode=0o700, exist_ok=True)
        os.chmod(GCLOUD_CONFIG, 0o700)
        run(["gcloud", "auth", "activate-service-account", f"--key-file={self.desc.seed_path}", "--quiet"],
            env=_gcloud_env(), log="seed", timeout=120)

    def token(self):
        if self._token is None:
            self._token = self._fetch()
        return self._token

    def _fetch(self):
        if self.desc.seed_kind == "file":
            out = run(["gcloud", "auth", "print-access-token", "--quiet"], env=_gcloud_env(), log="seed",
                      capture=True, timeout=120)
            token = out.strip()
        else:
            request = urllib.request.Request(f"{_metadata_root()}/instance/service-accounts/default/token",
                                             headers={"Metadata-Flavor": "Google"})
            try:
                with _retrying(lambda: urllib.request.urlopen(request, timeout=10)) as response:
                    token = json.load(response).get("access_token", "")
            except (urllib.error.URLError, OSError, ValueError) as error:
                raise StepError(f"the metadata server gave no token ({_reason(error)})") from None
        if not token:
            raise StepError("the seed yielded an empty access token")
        proc.KNOWN.add(token)
        return token

    def access(self, secret_id):
        """The latest version's payload bytes, or None when the secret or its
        version does not exist."""
        url = (f"{_endpoint()}/v1/projects/{urllib.parse.quote(self.desc.sm_project, safe='')}"
               f"/secrets/{urllib.parse.quote(secret_id, safe='')}/versions/latest:access")
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token()}"})
        try:
            with _retrying(lambda: urllib.request.urlopen(request, timeout=30)) as response:
                body = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise AccessError(f"HTTP {error.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise AccessError(_reason(error)) from None
        try:
            return base64.b64decode(body["payload"]["data"], validate=True)
        except (KeyError, TypeError, ValueError):
            raise AccessError("a response without a payload") from None


def _reason(error):
    reason = getattr(error, "reason", None) or error
    return type(reason).__name__ if not isinstance(reason, str) else reason


def _retrying(call, attempts=4):
    """`call()` again after a connection failure, a 429 or a 5xx, waiting 1, 2, 4 s."""
    for attempt in range(attempts):
        try:
            return call()
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500 or attempt == attempts - 1:
                raise
        except (urllib.error.URLError, OSError):
            if attempt == attempts - 1:
                raise
        time.sleep(2 ** attempt)
