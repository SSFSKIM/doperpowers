"""The Tailscale API, from the standard library, with the host's OAuth client
(the same secret that joins it): a token, the tailnet's devices, and the
removal of a node that a logout leaves listed. The driver uses it too, for
the nodes of a host it deletes (board #118). A non-ephemeral node stays in the tailnet after
`tailscale logout`, expired, under its name, so the next join of the host
would be given `<name>-1` (measured 2026-10-22); only the API removes it, and
only a client with the `devices:core` scope may.

`DEVCLOUD_TS_API` points it at a stand-in (the tests'); the default is
https://api.tailscale.com. Messages name statuses, never a secret."""

import http.client
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


TIMEOUT = 30


def token(secret, urlopen=urllib.request.urlopen, timeout=TIMEOUT):
    body = urllib.parse.urlencode({"client_id": client_id(secret), "client_secret": secret}).encode()
    request = urllib.request.Request(f"{_endpoint()}/api/v2/oauth/token", data=body, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        raise StepError(f"the Tailscale API refused the OAuth client's token (HTTP {error.code})") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as error:
        raise StepError(f"the Tailscale API's token: {type(error).__name__}") from None
    if not isinstance(data, dict) or not data.get("access_token"):
        raise StepError("the Tailscale API gave no token")
    return Token(data["access_token"], (data.get("scope") or "").split())


def devices(tok, urlopen=urllib.request.urlopen, timeout=TIMEOUT):
    """The tailnet's devices, as the API lists them to this client: each a
    dict with `nodeId`, `hostname` (the name the node reported: a devcloud
    host's `--hostname`, its name, whatever name the tailnet gave the node),
    `name` (its MagicDNS name) and `tags`."""
    request = urllib.request.Request(f"{_endpoint()}/api/v2/tailnet/-/devices",
                                     headers={"Authorization": f"Bearer {tok.access}"})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        raise StepError(f"the Tailscale API did not list the devices (HTTP {error.code})") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as error:
        raise StepError(f"listing the devices: {type(error).__name__}") from None
    listed = data.get("devices") if isinstance(data, dict) else None
    if not isinstance(listed, list):
        raise StepError("the Tailscale API's device list has no devices")
    return [device for device in listed if isinstance(device, dict)]


def delete_node(tok, node_id, urlopen=urllib.request.urlopen, timeout=TIMEOUT):
    """The node removed from the tailnet; a node already gone (404) counts."""
    request = urllib.request.Request(f"{_endpoint()}/api/v2/device/{urllib.parse.quote(node_id, safe='')}",
                                     method="DELETE", headers={"Authorization": f"Bearer {tok.access}"})
    try:
        with urlopen(request, timeout=timeout):
            return "removed"
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return "already gone"
        raise StepError(f"the Tailscale API did not remove node {node_id} (HTTP {error.code})") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
        raise StepError(f"removing node {node_id}: {type(error).__name__}") from None
