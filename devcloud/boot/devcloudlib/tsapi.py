"""The Tailscale API, from the standard library, with the host's OAuth client
(the same secret that joins it): a token, and the removal of a node that a
logout leaves listed. A non-ephemeral node stays in the tailnet after
`tailscale logout`, expired, under its name, so the next join of the host
would be given `<name>-1` (measured 2026-10-22); only the API removes it, and
only a client with the `devices:core` scope may.

`DEVCLOUD_TS_API` points it at a stand-in (the tests'); the default is
https://api.tailscale.com. Messages name statuses, never a secret."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .proc import StepError

DELETE_SCOPES = ("devices:core", "all")


def _endpoint():
    return os.environ.get("DEVCLOUD_TS_API", "https://api.tailscale.com").rstrip("/")


def client_id(secret):
    """An OAuth client secret is `tskey-client-<id>-<rest>`."""
    parts = secret.split("-")
    if len(parts) < 4 or parts[:2] != ["tskey", "client"]:
        raise StepError("the Tailscale OAuth client secret is not tskey-client-<id>-…")
    return parts[2]


class Token:
    def __init__(self, access, scopes):
        self.access = access
        self.scopes = scopes

    @property
    def can_delete(self):
        return any(scope in DELETE_SCOPES for scope in self.scopes)


def token(secret, urlopen=urllib.request.urlopen):
    body = urllib.parse.urlencode({"client_id": client_id(secret), "client_secret": secret}).encode()
    request = urllib.request.Request(f"{_endpoint()}/api/v2/oauth/token", data=body, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        raise StepError(f"the Tailscale API refused the OAuth client's token (HTTP {error.code})") from None
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise StepError(f"the Tailscale API's token: {type(error).__name__}") from None
    if not isinstance(data, dict) or not data.get("access_token"):
        raise StepError("the Tailscale API gave no token")
    return Token(data["access_token"], (data.get("scope") or "").split())


def delete_node(tok, node_id, urlopen=urllib.request.urlopen):
    """The node removed from the tailnet; a node already gone (404) counts."""
    request = urllib.request.Request(f"{_endpoint()}/api/v2/device/{urllib.parse.quote(node_id, safe='')}",
                                     method="DELETE", headers={"Authorization": f"Bearer {tok.access}"})
    try:
        with urlopen(request, timeout=30):
            return "removed"
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return "already gone"
        raise StepError(f"the Tailscale API did not remove node {node_id} (HTTP {error.code})") from None
    except (urllib.error.URLError, OSError) as error:
        raise StepError(f"removing node {node_id}: {type(error).__name__}") from None
