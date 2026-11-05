"""The GPU step (the VM driver's Design §6.7): a VM or an adopted machine with
an NVIDIA GPU gets its driver and GPU containers at every boot, without anyone
asking. Four parts, each checked and completed on its own, so a boot that
stopped halfway finishes the rest at the next, and a machine that already has
a part (an adopted one's own driver, its own Docker) keeps it:

1. the driver: Ubuntu's precompiled, signed `-server-open` modules for the
   exact running kernel, with the branch's utilities (no DKMS build, nothing
   for Secure Boot to refuse). An archive with no package for the running
   kernel (an image baked before a kernel update) gets the flavour's
   metapackage, which brings the newer kernel with its modules, and one
   reboot, bounded by a marker;
2. Docker Engine, from the Docker source the image configured (the image
   installs only the client), with the user in its group;
3. NVIDIA's container toolkit, from NVIDIA's repository, its key checked
   against the pinned fingerprint before apt trusts it;
4. the runtime, configured for Docker, the daemon restarted when that
   changed its configuration.

Then a CUDA base container run with `--gpus all` must list the GPU. Nothing
runs in a container or a microVM (their kernel is not theirs), nor on a
machine with no NVIDIA display-class PCI device. apt never removes a package
here (`--no-remove`): on an adopted machine a conflict fails the step, naming
it, rather than replacing what the person installed."""

import dataclasses
import json
import os
import pathlib
import re
import shutil
import tempfile

from . import proc
from .proc import StepError

# NVIDIA's current long-term branch, as -server-open: hosts are long-lived, and
# it is supported to 2028 and kept in Ubuntu's restricted component, where the
# newer branches (595, 615) sit in multiverse and go end-of-life within about a
# year. The L4, L40S and A10G are in its driver's Modaliases; noble-updates had
# 580.178.04 on 2026-11-04, with exact module packages for every current
# kernel flavour (aws, gcp, generic and their LTS and HWE lines).
BRANCH = "580"
NVIDIA_VENDOR = "0x10de"
SYSFS = pathlib.Path("/sys/bus/pci/devices")
OSRELEASE = pathlib.Path("/proc/sys/kernel/osrelease")
BOOT_ID = pathlib.Path("/proc/sys/kernel/random/boot_id")
# Present once the step installed the flavour's metapackage and rebooted for
# it; removed once the driver answers. Bounds the reboot to one.
MARKER = pathlib.Path("/var/lib/devcloud/gpu-reboot.json")

TOOLKIT_KEY_URL = "https://nvidia.github.io/libnvidia-container/gpgkey"
# NVIDIA CORPORATION (Open Source Projects) <cudatools@nvidia.com>, the key
# that signs https://nvidia.github.io/libnvidia-container.
TOOLKIT_FINGERPRINT = "C95B321B61E88C1809C4F759DDCAE044F796ECB0"
TOOLKIT_KEY = pathlib.Path("/etc/apt/keyrings/nvidia-container-toolkit.asc")
TOOLKIT_SOURCE = pathlib.Path("/etc/apt/sources.list.d/nvidia-container-toolkit.list")
TOOLKIT_REPO = "https://nvidia.github.io/libnvidia-container/stable/deb/$(ARCH) /"
DAEMON_JSON = pathlib.Path("/etc/docker/daemon.json")
# The runtime's configuration changed and Docker has not yet restarted onto
# it: kept until a restart succeeds, so a retry in the same boot still owes
# it. Under /run: a reboot restarts the daemon anyway.
RESTART_OWED = pathlib.Path("/run/devcloud/gpu-docker-restart-owed")
# The check container. Its NVIDIA_REQUIRE_CUDA (cuda>=13.0) is turned off with
# NVIDIA_DISABLE_REQUIRE: the check proves the GPU reaches a container, and an
# adopted machine's own older driver (R525: CUDA 12.0) must pass it.
CUDA_IMAGE = "nvidia/cuda:13.0.3-base-ubuntu24.04"

LOG = "gpu"
APT_ENV = {"PATH": proc.SYSTEM_PATH, "DEBIAN_FRONTEND": "noninteractive", "LANG": "C.UTF-8"}
# apt-get waits for a dpkg lock someone else holds (unattended-upgrades at a
# VM's first boot) rather than failing at once.
APT_LOCK = ["-o", "DPkg::Lock::Timeout=600"]


@dataclasses.dataclass
class Outcome:
    state: str
    detail: str
    reboot: bool = False    # the boot reboots now, into the kernel the driver's modules are for


class _Reboot(Exception):
    pass


def nvidia_gpus(root=None):
    """The PCI addresses of the NVIDIA display controllers (class 0x03xxxx:
    VGA or 3D) the kernel sees; an NVIDIA audio or bridge function is not a GPU."""
    found = []
    try:
        devices = sorted((root or SYSFS).iterdir())
    except FileNotFoundError:
        return found
    for device in devices:
        try:
            vendor = (device / "vendor").read_text().strip().lower()
            klass = (device / "class").read_text().strip().lower()
        except OSError:
            continue
        if vendor == NVIDIA_VENDOR and klass.startswith("0x03"):
            found.append(device.name)
    return found


def reconcile(kind, user):
    """The step's outcome on this machine. Raises StepError naming the part
    that failed."""
    if kind != "vm":
        return Outcome("skipped", f"a {kind}'s kernel is not its own")
    gpus = nvidia_gpus()
    if not gpus:
        return Outcome("skipped", "no NVIDIA GPU")
    apt = _Apt()
    did = []
    part = "the driver"
    try:
        listed = _driver(apt, did)
        part = "Docker Engine"
        _docker(apt, user, did)
        part = "the container toolkit"
        _toolkit(apt, did)
        part = "the runtime"
        _runtime(did)
        part = "the GPU container check"
        _check_container(listed)
    except _Reboot as reboot:
        return Outcome("deferred", str(reboot), reboot=True)
    except StepError as error:
        raise StepError(f"{part}: {error}") from None
    names = _names(listed)
    return Outcome("ok", f"{names} (driver {listed[0][1]}); a CUDA container with --gpus all lists it"
                         + (f"; {', '.join(did)}" if did else ""))


def _names(listed):
    counts = {}
    for name, _ in listed:
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(name if n == 1 else f"{n} × {name}" for name, n in counts.items())


# --- 1. the driver ---------------------------------------------------------------

def _listed():
    """The GPUs nvidia-smi lists, [(name, driver version)], or [] when it
    lists none: not installed, or no driver loaded."""
    code, out, _ = proc.call(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                             log=LOG, timeout=120)
    if code != 0:
        return []
    rows = [[cell.strip() for cell in line.split(",")] for line in out.splitlines() if line.strip()]
    return [(row[0], row[1]) for row in rows if len(row) >= 2 and row[0]]


def _kernel():
    return OSRELEASE.read_text().strip()


def _driver(apt, did):
    listed = _listed()
    if listed:
        MARKER.unlink(missing_ok=True)
        _load_uvm()
        return listed
    kernel = _kernel()
    exact = f"linux-modules-nvidia-{BRANCH}-server-open-{kernel}"
    utils = f"nvidia-utils-{BRANCH}-server"
    if apt.has(exact):
        apt.install(exact, utils)
        proc.run(["modprobe", "nvidia"], log=LOG, timeout=120)
        listed = _listed()
        if not listed:
            raise StepError(f"{exact} and {utils} are installed and the module loaded, but nvidia-smi lists no GPU "
                            f"(kernel {kernel}, branch {BRANCH}; log {proc.log_path(LOG)})")
        MARKER.unlink(missing_ok=True)
        _load_uvm()
        did.append(f"installed the driver (branch {BRANCH} for kernel {kernel})")
        return listed
    marker = _marker()
    if marker is not None and marker.get("boot_id") != _boot_id():
        raise StepError(f"still no driver after the reboot: Ubuntu's archive has no {exact} for the running kernel "
                        f"{kernel} (branch {BRANCH})")
    if marker is None:
        meta = _flavour_meta(apt, kernel)
        apt.install(meta, utils)
        # Before the reboot is asked for: a step that stops between the two
        # finds the marker of this boot and asks again.
        proc.write_file(MARKER, json.dumps({"boot_id": _boot_id(), "kernel": kernel, "branch": BRANCH,
                                            "metapackage": meta}) + "\n", mode=0o644, dir_mode=0o755)
    else:
        meta = marker.get("metapackage")
    raise _Reboot(f"Ubuntu's archive has no {exact}: installed {meta}, which brings a newer kernel with the "
                  "driver's modules; rebooting into it once")


def _boot_id():
    return BOOT_ID.read_text().strip()


def _marker():
    """The reboot the step took for the driver, or None."""
    try:
        record = json.loads(MARKER.read_text())
    except FileNotFoundError:
        return None
    except ValueError:
        return {}
    return record if isinstance(record, dict) else {}


def _load_uvm():
    """The unified memory module CUDA needs, which no device loads on its own."""
    proc.run(["modprobe", "nvidia_uvm"], log=LOG, timeout=120)


_VERSIONED_IMAGE = re.compile(r"linux-image-(?:unsigned-)?[0-9]")


def _flavour_meta(apt, kernel):
    """The branch's modules metapackage for the kernel flavour installed
    (linux-image-aws → linux-modules-nvidia-<branch>-server-open-aws), as
    ubuntu-drivers names it."""
    code, out, _ = proc.call(["dpkg-query", "-W", "-f", "${Package} ${db:Status-Status}\n", "linux-image-*"],
                             log=LOG, timeout=60)
    metas = [name for name, _, state in (line.partition(" ") for line in out.splitlines())
             if state.strip() == "installed" and not _VERSIONED_IMAGE.match(name)] if code in (0, 1) else []
    for meta in metas:
        candidate = f"linux-modules-nvidia-{BRANCH}-server-open-{meta[len('linux-image-'):]}"
        if apt.has(candidate):
            return candidate
    raise StepError(f"Ubuntu's archive has no linux-modules-nvidia-{BRANCH}-server-open package for the running "
                    f"kernel {kernel}, nor for its flavour ({', '.join(metas) or 'no linux-image metapackage installed'})")


# --- 2. Docker Engine ------------------------------------------------------------

def _docker(apt, user, did):
    if shutil.which("dockerd") is None:
        apt.install("docker-ce", "containerd.io")
        did.append("installed Docker Engine")
    proc.run(["systemctl", "enable", "--now", "docker.service"], log=LOG, timeout=300)
    if user is not None and user.name not in _docker_group():
        proc.run(["usermod", "-aG", "docker", user.name], log=LOG, timeout=60)
        did.append(f"{user.name} added to the docker group (its next login)")


def _docker_group():
    """The docker group's members; an empty list when there is none."""
    code, out, _ = proc.call(["getent", "group", "docker"], timeout=30)
    if code != 0:
        return []
    return [name for name in out.strip().split(":")[-1].split(",") if name]


# --- 3. the container toolkit ----------------------------------------------------

def _toolkit(apt, did):
    if shutil.which("nvidia-ctk") is not None:
        return
    key = proc.run(["curl", "-fsSL", "--retry", "3", TOOLKIT_KEY_URL], log=LOG, capture=True, timeout=120)
    found = primary_fingerprints(key)
    if found != [TOOLKIT_FINGERPRINT]:
        raise StepError(f"the key at {TOOLKIT_KEY_URL} is {', '.join(found) or 'no OpenPGP key'}, "
                        f"not {TOOLKIT_FINGERPRINT}: nothing written")
    proc.write_file(TOOLKIT_KEY, key, mode=0o644, dir_mode=0o755)
    proc.write_file(TOOLKIT_SOURCE, f"deb [signed-by={TOOLKIT_KEY}] {TOOLKIT_REPO}\n", mode=0o644, dir_mode=0o755)
    apt.update(again=True)
    apt.install("nvidia-container-toolkit")
    did.append("installed NVIDIA's container toolkit")


def primary_fingerprints(armored):
    """The fingerprints of the primary keys in an armored OpenPGP block, as
    gpg reads them (subkeys left out), in a keyring of its own."""
    with tempfile.TemporaryDirectory(prefix="devcloud-gpg-") as home:
        path = pathlib.Path(home) / "key.asc"
        path.write_text(armored)
        code, out, _ = proc.call(["gpg", "--batch", "--no-tty", "--with-colons", "--show-keys", str(path)],
                                 env={"PATH": os.environ.get("PATH", proc.SYSTEM_PATH), "GNUPGHOME": home,
                                      "LANG": "C.UTF-8"}, timeout=60)
    if code != 0:
        return []
    found, primary = [], False
    for line in out.splitlines():
        fields = line.split(":")
        if fields[0] in ("pub", "sub", "sec", "ssb"):
            primary = fields[0] in ("pub", "sec")
        elif fields[0] == "fpr" and primary and len(fields) > 9:
            found.append(fields[9])
            primary = False
    return found


# --- 4. the runtime --------------------------------------------------------------

def _read(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _runtime(did):
    before = _read(DAEMON_JSON)
    proc.run(["nvidia-ctk", "runtime", "configure", "--runtime=docker"], log=LOG, timeout=120)
    if _read(DAEMON_JSON) != before:
        proc.write_file(RESTART_OWED, "", mode=0o600, dir_mode=0o711)
    if RESTART_OWED.exists():
        proc.run(["systemctl", "restart", "docker.service"], log=LOG, timeout=300)
        RESTART_OWED.unlink()
        did.append("configured the NVIDIA runtime for Docker")


def _check_container(listed):
    out = proc.run(["docker", "run", "--rm", "--gpus", "all", "-e", "NVIDIA_DISABLE_REQUIRE=true", CUDA_IMAGE,
                    "nvidia-smi", "-L"],
                   log=LOG, capture=True, timeout=900)
    seen = [line for line in out.splitlines() if line.startswith("GPU ")]
    if not any(listed[0][0] in line for line in seen):
        raise StepError(f"{CUDA_IMAGE} with --gpus all lists {len(seen)} GPUs, not the {listed[0][0]} "
                        f"(log {proc.log_path(LOG)})")


# --- apt -------------------------------------------------------------------------

class _Apt:
    """apt-get with its lists fetched once per run (the image ships none),
    and again after a source was added."""

    def __init__(self):
        self.updated = False

    def update(self, again=False):
        if self.updated and not again:
            return
        proc.run(["apt-get", "update", *APT_LOCK], env=APT_ENV, log=LOG, timeout=600)
        self.updated = True

    def has(self, package):
        self.update()
        code, out, _ = proc.call(["apt-cache", "show", "--no-all-versions", package], env=APT_ENV, timeout=60)
        return code == 0 and f"Package: {package}" in out

    def install(self, *packages):
        self.update()
        proc.run(["apt-get", "install", *APT_LOCK, "-y", "--no-install-recommends", "--no-remove", *packages],
                 env=APT_ENV, log=LOG, timeout=1800)
