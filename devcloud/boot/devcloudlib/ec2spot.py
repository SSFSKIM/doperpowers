"""EC2's spot interruption notice (the VM driver's Design §6.6, §4.2).

EC2 schedules a spot instance's interruption two minutes ahead and says so
through IMDSv2 at `meta-data/spot/instance-action`, which answers 404 until
then; it does not run the guest's shutdown in time for a departure, as GCE's
reclaim does. So a spot host runs `devcloud depart --spot-notice`
(devcloud-spot-notice.service, enabled by the boot while DEVCLOUD_SPOT=1),
which asks every 5 seconds and starts the fast departure once when the
notice appears. On GCE the same ask finds no notice and departs nothing."""

import json
import os
import time
import urllib.error
import urllib.request

ROOT = "http://169.254.169.254"
# The AWS SDKs' override of IMDS's address; the tests point it at a stand-in.
ENDPOINT_VAR = "AWS_EC2_METADATA_SERVICE_ENDPOINT"
TOKEN_TTL = 21600           # seconds; IMDSv2's longest session
EVERY = 5
TIMEOUT = 2
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # link-local: never a proxy


class Imds:
    """IMDSv2 with its session token kept, and renewed when it expires or
    IMDS no longer takes it (401)."""

    def __init__(self, root=None, clock=time.monotonic, timeout=TIMEOUT):
        self.root = (root or os.environ.get(ENDPOINT_VAR) or ROOT).rstrip("/")
        self.clock = clock
        self.timeout = timeout
        self._token = None
        self._renew_at = 0.0

    def _session(self):
        if self._token is None or self.clock() >= self._renew_at:
            request = urllib.request.Request(f"{self.root}/latest/api/token", method="PUT",
                                             headers={"X-aws-ec2-metadata-token-ttl-seconds": str(TOKEN_TTL)})
            with _DIRECT.open(request, timeout=self.timeout) as response:
                self._token = response.read().decode().strip()
            self._renew_at = self.clock() + TOKEN_TTL - 60
        return self._token

    def instance_action(self):
        """EC2's scheduled interruption ({"action", "time"}), or None: none
        scheduled yet (404), or no IMDS that answers (not EC2, or unreachable)."""
        for retry in (False, True):
            try:
                request = urllib.request.Request(f"{self.root}/latest/meta-data/spot/instance-action",
                                                 headers={"X-aws-ec2-metadata-token": self._session()})
                with _DIRECT.open(request, timeout=self.timeout) as response:
                    body = response.read()
            except urllib.error.HTTPError as error:
                if error.code == 401 and not retry:
                    self._token = None
                    continue
                return None
            except (OSError, ValueError):
                return None
            try:
                action = json.loads(body)
            except ValueError:
                return None
            return action if isinstance(action, dict) and action.get("action") else None
        return None


def watch(imds, depart, say, sleep=time.sleep, every=EVERY):
    """Asks for the notice every `every` seconds; when it appears, runs
    `depart` once and returns 0 whatever its outcome, so the unit is not
    started again (the departure's status says how it went)."""
    while True:
        action = imds.instance_action()
        if action is not None:
            say(f"devcloud depart: EC2 scheduled this spot VM's {action['action']} at {action.get('time', '?')}; "
                "departing")
            say(f"devcloud depart: the reclaim departure exited {depart()}")
            return 0
        sleep(every)
