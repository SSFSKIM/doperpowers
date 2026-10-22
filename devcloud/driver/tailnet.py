"""The tailnet nodes of a host the driver is done with, removed through the
Tailscale API (board #118): after a VM's delete has succeeded, and after an
adopted machine's release was verified, whatever the API still lists of that
host goes. A kept host removes its own node right after its departure's
logout, but that comes after the logout has cut the driver's connection, and
the delete that follows can cut it short; a host deleted unreachable never
departs at all.

Which nodes are the host's is decided exactly: tagged `tag:devcloud`, and
reported under the hostname the host joined with (`--hostname=<name>`), equal
to its name. Never a prefix or a pattern, never an untagged node; each is
removed by its node id. The client is the hosts' own (the profile's
`[host].tailscale_secret`), which holds `devices:core` on `tag:devcloud`."""

from devcloudlib import tsapi
from devcloudlib.proc import StepError

from .errors import DriverError

TAG = "tag:devcloud"
MIN_LEFT = 2            # a bounded run with less left asks the API nothing
TIME_SPENT = "the bounded run's time is spent"
HINT = "remove it in the Tailscale admin console if it is listed"


class Api:
    """tsapi with the token kept for the command's length (a reaper run may
    delete several hosts)."""

    def __init__(self):
        self._tokens = {}

    def token(self, secret, timeout):
        if secret not in self._tokens:
            self._tokens[secret] = tsapi.token(secret, timeout=timeout)
        return self._tokens[secret]

    def devices(self, tok, timeout):
        return tsapi.devices(tok, timeout=timeout)

    def delete_node(self, tok, node_id, timeout):
        return tsapi.delete_node(tok, node_id, timeout=timeout)


def nodes_of(devices, name):
    """The host `name`'s nodes among the API's devices: tagged tag:devcloud
    and reported under exactly that hostname."""
    return [d for d in devices if TAG in (d.get("tags") or []) and d.get("hostname") == name
            and (d.get("nodeId") or d.get("id"))]


def remove(ctx, name):
    """Every node the tailnet lists of host `name`, removed by node id. Call
    it only once the host is gone: its VM deleted, or its release verified.
    Returns the note the deletion's line ends with: each node id removed, or
    why none could be; "" when none is listed. Never raises: the deletion
    has happened, and a node left is named, not a failure of it."""
    try:
        return _remove(ctx, name)
    except Exception as error:      # whatever the API or its data did that was not foreseen
        return f"; its tailnet node was not removed ({type(error).__name__}): {HINT}"


def _remove(ctx, name):
    def timeout():
        left = ctx.remaining()
        return tsapi.TIMEOUT if left is None else max(1, min(tsapi.TIMEOUT, left))

    def spent():
        left = ctx.remaining()
        return left is not None and left < MIN_LEFT

    def request(call):
        """One API request, asked only while the bounded run has time left."""
        if spent():
            raise StepError(TIME_SPENT)
        return call()

    if spent():
        return f"; its tailnet node was not looked for: {TIME_SPENT} ({HINT})"
    api = ctx.tailnet_api
    try:
        secret = request(lambda: ctx.secrets.access(ctx.profile.host.tailscale_secret, timeout=timeout())).strip()
        tok = request(lambda: api.token(secret, timeout()))
        if not tok.can_delete:
            raise StepError("the Tailscale OAuth client may not remove nodes (it lacks the devices:core scope)")
        found = nodes_of(request(lambda: api.devices(tok, timeout())), name)
    except (DriverError, StepError) as error:
        return f"; its tailnet node was not removed ({error}): {HINT}"
    said, failed, skipped = [], [], []
    for node in found:
        node_id = node.get("nodeId") or node.get("id")
        if spent():
            skipped.append(node_id)
            continue
        try:
            said.append(f"{node_id} {api.delete_node(tok, node_id, timeout())}")
        except StepError as error:
            failed.append(f"{node_id} ({error})")
    note = ""
    if said:
        note += f"; its tailnet node{'s' if len(said) > 1 else ''} {', '.join(said)} through the Tailscale API"
    if failed:
        note += f"; its tailnet node{'s' if len(failed) > 1 else ''} {', '.join(failed)} not removed: {HINT}"
    if skipped:
        note += (f"; its tailnet node{'s' if len(skipped) > 1 else ''} {', '.join(skipped)} not removed: "
                 f"{TIME_SPENT} ({HINT})")
    return note
