"""The GPU step (the VM driver's Design §6.7) against a stand-in machine: a fake
sysfs, and stub `apt-get`, `apt-cache`, `dpkg-query`, `modprobe`,
`nvidia-smi`, `nvidia-ctk`, `docker`, `systemctl`, `getent`, `usermod` and
`curl` sharing one JSON state. A package the stub `apt-get` installs puts its
commands on the PATH (nvidia-utils → nvidia-smi, docker-ce → dockerd, the
toolkit → nvidia-ctk), so the step finds a part present only once something
installed it. gpg is the real one, reading NVIDIA's real key. The PATH holds
the stubs and gpg alone: a command the step runs that has no stub fails the
test rather than touching the machine running it."""
import contextlib
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import gpu, proc
from devcloudlib.proc import StepError, User

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "gpu"
NVIDIA_KEY = FIXTURES / "nvidia-container-toolkit.asc"
OTHER_KEY = FIXTURES / "another-key.asc"
GPG = shutil.which("gpg")

OLD, NEW = "6.8.0-1010-aws", "6.8.0-1021-aws"
B = gpu.BRANCH
EXACT_OLD = f"linux-modules-nvidia-{B}-server-open-{OLD}"
EXACT_NEW = f"linux-modules-nvidia-{B}-server-open-{NEW}"
META = f"linux-modules-nvidia-{B}-server-open-aws"
UTILS = f"nvidia-utils-{B}-server"
TOOLKIT = "nvidia-container-toolkit"

COMMANDS = ("apt-get", "apt-cache", "dpkg-query", "modprobe", "nvidia-smi", "nvidia-ctk", "docker", "dockerd",
            "systemctl", "getent", "usermod", "curl")
# What a package puts on the PATH.
PROVIDES = {UTILS: "nvidia-smi", "docker-ce": "dockerd", TOOLKIT: "nvidia-ctk"}

FAKE = r'''#!PYTHON
import json, os, pathlib, sys

STATE = pathlib.Path(os.environ["FAKE_GPU_STATE"])
s = json.loads(STATE.read_text())
cmd, args = os.path.basename(sys.argv[0]), sys.argv[1:]
s["calls"].append([cmd] + args)


def save():
    STATE.write_text(json.dumps(s))


def done(code=0, out="", err=""):
    save()
    sys.stdout.write(out)
    sys.stderr.write(err)
    sys.exit(code)


def available(package):
    # NVIDIA's packages are found only once its source is written.
    if package == "nvidia-container-toolkit" and not os.path.exists(s["toolkit_source"]):
        return False
    return package in s["archive"]


def put(command):
    link = os.path.join(s["bin"], command)
    if not os.path.lexists(link):
        os.symlink(s["fake"], link)


def loaded_driver():
    return s["own_driver"] or any(p.startswith("linux-modules-nvidia-") and p.endswith("-" + s["kernel"])
                                  for p in s["installed"])


if cmd == "apt-get":
    if "update" in args:
        done()
    i = args.index("install")
    packages = [a for a in args[i + 1:] if not a.startswith("-") and "::" not in a]
    for package in packages:
        if not available(package):
            done(100, err=f"E: Unable to locate package {package}\n")
    for package in packages:
        s["installed"].append(package)
        if package in s["provides"]:
            put(s["provides"][package])
        if package == s["meta"]:
            # The flavour's metapackage: the newer kernel and its modules.
            s["installed"].append(s["exact_next"])
    done()
if cmd == "apt-cache":
    package = args[-1]
    done(0, out=f"Package: {package}\nVersion: 1\n") if available(package) else \
        done(100, err=f"E: No packages found\n")
if cmd == "dpkg-query":
    done(0, out="".join(f"{name} installed\n" for name in s["images"]))
if cmd == "modprobe":
    if args == ["nvidia"]:
        if not loaded_driver():
            done(1, err="modprobe: FATAL: Module nvidia not found\n")
        s["loaded"] = True
        done()
    if args == ["nvidia_uvm"]:
        done() if s["loaded"] or s["own_driver"] else done(1, err="modprobe: FATAL: Module nvidia_uvm not found\n")
if cmd == "nvidia-smi":
    if s["own_driver"] or (s["loaded"] and loaded_driver()):
        done(0, out="".join(f"{name}, {s['version']}\n" for name in s["gpus"]))
    done(9, out="NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.\n")
if cmd == "systemctl":
    if args == ["restart", "docker.service"] and s["restart_fails"] > 0:
        s["restart_fails"] -= 1
        done(1, err="Job for docker.service failed because the control process exited with error code.\n")
    if args == ["restart", "docker.service"]:
        s["restarted_with"] = pathlib.Path(s["daemon_json"]).read_text()
    if args == ["enable", "--now", "docker.service"]:
        if not os.path.lexists(os.path.join(s["bin"], "dockerd")):
            done(1, err="Failed to enable unit: Unit file docker.service does not exist.\n")
        s["docker_active"] = True
    done()
if cmd == "getent":
    if not os.path.lexists(os.path.join(s["bin"], "dockerd")):
        done(2)
    done(0, out=f"docker:x:999:{','.join(s['docker_members'])}\n")
if cmd == "usermod":
    s["docker_members"].append(args[-1])
    done()
if cmd == "curl":
    done(0, out=pathlib.Path(s["key_file"]).read_text())
if cmd == "nvidia-ctk":
    path = pathlib.Path(s["daemon_json"])
    config = json.loads(path.read_text()) if path.exists() else {}
    config.setdefault("runtimes", {})["nvidia"] = {"args": [], "path": "nvidia-container-runtime"}
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(config, indent=4) + "\n"
    if not path.exists() or path.read_text() != text:
        path.write_text(text)
    done()
if cmd == "docker":
    path = pathlib.Path(s["daemon_json"])
    runtime = path.exists() and "nvidia" in json.loads(path.read_text()).get("runtimes", {})
    # The daemon runs the runtime it read when it last (re)started.
    runtime = runtime and "nvidia" in json.loads(s["restarted_with"] or "{}").get("runtimes", {})
    if not (s["docker_active"] and runtime and (s["loaded"] or s["own_driver"])) or s["container_blind"]:
        done(125, err='docker: Error response from daemon: could not select device driver "" with capabilities: '
                      '[[gpu]].\n')
    # The image's NVIDIA_REQUIRE_CUDA (cuda>=13.0), checked by the toolkit's hook unless disabled.
    disabled = any(a == "NVIDIA_DISABLE_REQUIRE=true" for a in args)
    if not disabled and tuple(map(int, s["cuda"].split("."))) < (13, 0):
        done(125, err="docker: Error response from daemon: failed to create task for container: "
                      "nvidia-container-cli: requirement error: unsatisfied condition: cuda>=13.0, please update "
                      "your driver to a newer version, or use an earlier cuda container\n")
    done(0, out="".join(f"GPU {i}: {name} (UUID: GPU-{i})\n" for i, name in enumerate(s["gpus"])))
done(127, err=f"the fake has no {cmd} {args}\n")
'''


class Machine:
    """A stand-in GPU machine: its sysfs, kernel, archive and packages."""

    def __init__(self, root, kind_of_gpu=("NVIDIA L4",)):
        self.root = root
        self.bin = root / "bin"
        self.bin.mkdir()
        self.fake = root / "fake-command"
        self.fake.write_text(FAKE.replace("#!PYTHON", "#!" + sys.executable))
        self.fake.chmod(0o755)
        tools = root / "tools"
        tools.mkdir()
        if GPG:
            (tools / "gpg").symlink_to(GPG)
        self.path = f"{self.bin}:{tools}"
        self.sysfs = root / "sys/bus/pci/devices"
        self.sysfs.mkdir(parents=True)
        self.osrelease = root / "osrelease"
        self.boot_id = root / "boot_id"
        self.state_path = root / "state.json"
        self.state = {
            "bin": str(self.bin), "fake": str(self.fake), "calls": [], "provides": PROVIDES,
            "kernel": OLD, "meta": META, "exact_next": EXACT_NEW,
            "archive": [EXACT_OLD, UTILS, META, "docker-ce", "containerd.io", TOOLKIT],
            "installed": ["docker-ce-cli"], "images": ["linux-image-aws", f"linux-image-{OLD}"],
            "own_driver": False, "loaded": False, "gpus": list(kind_of_gpu), "version": "580.178.04",
            "cuda": "13.0", "restart_fails": 0, "restarted_with": None,
            "docker_active": False, "docker_members": [], "container_blind": False,
            "toolkit_source": str(root / "etc/apt/sources.list.d/nvidia-container-toolkit.list"),
            "daemon_json": str(root / "etc/docker/daemon.json"), "key_file": str(NVIDIA_KEY),
        }
        for command in ("apt-get", "apt-cache", "dpkg-query", "modprobe", "systemctl", "getent", "usermod", "curl",
                        "docker"):
            (self.bin / command).symlink_to(self.fake)
        self.boot(OLD, "boot-1")

    def boot(self, kernel, boot_id):
        """A (re)boot into `kernel`: nothing loaded yet."""
        self.update(kernel=kernel, loaded=False, docker_active=False)
        self.osrelease.write_text(kernel + "\n")
        self.boot_id.write_text(boot_id + "\n")

    def device(self, address, vendor="0x10de", klass="0x030200"):
        d = self.sysfs / address
        d.mkdir()
        (d / "vendor").write_text(vendor + "\n")
        (d / "class").write_text(klass + "\n")

    def read(self):
        return json.loads(self.state_path.read_text())

    def update(self, **changes):
        state = self.read() if self.state_path.exists() else self.state
        state.update(changes)
        self.state_path.write_text(json.dumps(state))

    def has(self, command):
        return (self.bin / command).exists()

    def install_already(self, *packages):
        """Packages present before the step runs, their commands on the PATH."""
        state = self.read()
        state["installed"] += packages
        self.state_path.write_text(json.dumps(state))
        for package in packages:
            if package in PROVIDES and not self.has(PROVIDES[package]):
                (self.bin / PROVIDES[package]).symlink_to(self.fake)

    def calls(self, command=None):
        return [c for c in self.read()["calls"] if command is None or c[0] == command]

    def installs(self):
        return [[a for a in c[c.index("install") + 1:] if not a.startswith("-") and "::" not in a]
                for c in self.calls("apt-get") if "install" in c]

    def clear_calls(self):
        self.update(calls=[])


@unittest.skipUnless(GPG, "gpg reads the toolkit's key")
class GpuStepTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name).resolve()
        self.m = Machine(self.root)
        self.user = User(name="dev", uid=os.getuid(), gid=os.getgid(), home=self.root / "home")
        etc = self.root / "etc"
        for name, value in (("SYSFS", self.m.sysfs), ("OSRELEASE", self.m.osrelease), ("BOOT_ID", self.m.boot_id),
                            ("MARKER", self.root / "var/lib/devcloud/gpu-reboot.json"),
                            ("TOOLKIT_KEY", etc / "apt/keyrings/nvidia-container-toolkit.asc"),
                            ("TOOLKIT_SOURCE", etc / "apt/sources.list.d/nvidia-container-toolkit.list"),
                            ("DAEMON_JSON", etc / "docker/daemon.json"),
                            ("RESTART_OWED", self.root / "run/devcloud/gpu-docker-restart-owed")):
            patch = mock.patch.object(gpu, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        for patch in (mock.patch.object(proc, "LOG_DIR", self.root / "log"),
                      mock.patch.object(gpu, "APT_ENV", dict(gpu.APT_ENV, PATH=self.m.path, FAKE_GPU_STATE=str(self.m.state_path))),
                      mock.patch.dict(os.environ, {"PATH": self.m.path, "FAKE_GPU_STATE": str(self.m.state_path)})):
            patch.start()
            self.addCleanup(patch.stop)

    def step(self, kind="vm"):
        return gpu.reconcile(kind, self.user)

    def failed(self, kind="vm"):
        with self.assertRaises(StepError) as caught:
            self.step(kind)
        return str(caught.exception)

    # --- where the step does nothing ---

    def test_no_nvidia_device_does_nothing(self):
        self.m.device("0000:00:03.0", vendor="0x1d0f", klass="0x030000")   # Amazon's display
        self.m.device("0000:00:1f.0", vendor="0x10de", klass="0x040300")   # an NVIDIA audio function
        outcome = self.step()
        self.assertEqual((outcome.state, outcome.reboot), ("skipped", False))
        self.assertEqual(outcome.detail, "no NVIDIA GPU")
        self.assertEqual(self.m.calls(), [])

    def test_a_container_or_microvm_with_a_visible_gpu_does_nothing(self):
        self.m.device("0000:00:1e.0")
        for kind in ("container", "microvm"):
            with self.subTest(kind=kind):
                outcome = self.step(kind)
                self.assertEqual(outcome.state, "skipped")
                self.assertIn("kernel is not its own", outcome.detail)
        self.assertEqual(self.m.calls(), [])

    # --- a clean install, and a second boot ---

    def test_a_clean_install_completes_all_four_parts(self):
        self.m.device("0000:00:1e.0")
        outcome = self.step()
        self.assertEqual(outcome.state, "ok", outcome.detail)
        self.assertTrue(outcome.detail.startswith("NVIDIA L4 (driver 580.178.04); a CUDA container"), outcome.detail)
        for said in (f"installed the driver (branch {B} for kernel {OLD})", "installed Docker Engine",
                     "installed NVIDIA's container toolkit", "configured the NVIDIA runtime for Docker",
                     "dev added to the docker group"):
            self.assertIn(said, outcome.detail)
        self.assertEqual(self.m.installs(), [[EXACT_OLD, UTILS], ["docker-ce", "containerd.io"], [TOOLKIT]])
        for call in self.m.calls("apt-get"):
            if "install" in call:
                self.assertIn("--no-remove", call, "apt never removes what the machine has")
        # The key is NVIDIA's, armored, and the source names it.
        self.assertEqual(gpu.TOOLKIT_KEY.read_text(), NVIDIA_KEY.read_text())
        self.assertEqual(gpu.TOOLKIT_SOURCE.read_text(),
                         f"deb [signed-by={gpu.TOOLKIT_KEY}] https://nvidia.github.io/libnvidia-container/stable/deb/"
                         "$(ARCH) /\n")
        # The lists are fetched once, and again after NVIDIA's source was added.
        updates = [c for c in self.m.calls("apt-get") if "update" in c]
        self.assertEqual(len(updates), 2)
        self.assertIn(["modprobe", "nvidia"], self.m.calls())
        self.assertIn(["modprobe", "nvidia_uvm"], self.m.calls())
        self.assertIn(["systemctl", "restart", "docker.service"], self.m.calls())
        self.assertIn(["docker", "run", "--rm", "--gpus", "all", "-e", "NVIDIA_DISABLE_REQUIRE=true", gpu.CUDA_IMAGE,
                       "nvidia-smi", "-L"], self.m.calls())
        self.assertEqual(self.m.read()["docker_members"], ["dev"])
        self.assertFalse(gpu.MARKER.exists())

    def test_the_next_boot_installs_nothing_and_restarts_nothing(self):
        self.m.device("0000:00:1e.0")
        self.step()
        self.m.boot(OLD, "boot-2")
        # The module loads by its PCI alias at boot; the daemon reads its configuration as it starts.
        self.m.update(loaded=True, restarted_with=gpu.DAEMON_JSON.read_text())
        self.m.clear_calls()
        outcome = self.step()
        self.assertEqual(outcome.state, "ok")
        self.assertTrue(outcome.detail.endswith("lists it"), outcome.detail)
        self.assertEqual(self.m.installs(), [])
        self.assertEqual(self.m.calls("apt-get"), [], "nothing to install: the lists are not even fetched")
        self.assertNotIn(["systemctl", "restart", "docker.service"], self.m.calls())
        self.assertIn(["systemctl", "enable", "--now", "docker.service"], self.m.calls())

    # --- each part missing alone is completed alone ---

    def _everything_but(self, missing):
        self.m.device("0000:00:1e.0")
        self.step()
        self.m.boot(OLD, "boot-2")
        self.m.update(loaded=True, docker_active=True, restarted_with=gpu.DAEMON_JSON.read_text())
        state = self.m.read()
        if missing == "driver":
            state["installed"] = [p for p in state["installed"] if p not in (EXACT_OLD, UTILS)]
            state["loaded"] = False
            (self.m.bin / "nvidia-smi").unlink()
        if missing == "docker":
            state["installed"] = [p for p in state["installed"] if p not in ("docker-ce", "containerd.io")]
            state["docker_active"] = False
            (self.m.bin / "dockerd").unlink()
        if missing == "toolkit":
            state["installed"].remove(TOOLKIT)
            (self.m.bin / "nvidia-ctk").unlink()
        if missing == "runtime":
            gpu.DAEMON_JSON.unlink()
            state["restarted_with"] = None
        state["calls"] = []
        self.m.state_path.write_text(json.dumps(state))

    def _completed_alone(self, missing, installs, said):
        self._everything_but(missing)
        outcome = self.step()
        self.assertEqual(outcome.state, "ok", outcome.detail)
        self.assertEqual(self.m.installs(), installs)
        self.assertEqual(outcome.detail.split("; ")[2:], [said])
        restarted = ["systemctl", "restart", "docker.service"] in self.m.calls()
        self.assertEqual(restarted, missing == "runtime",
                         "the daemon restarts only when the runtime's configuration changed")

    def test_the_driver_missing_alone_is_installed_alone(self):
        self._completed_alone("driver", [[EXACT_OLD, UTILS]], f"installed the driver (branch {B} for kernel {OLD})")

    def test_docker_engine_missing_alone_is_installed_alone(self):
        self._completed_alone("docker", [["docker-ce", "containerd.io"]], "installed Docker Engine")

    def test_the_toolkit_missing_alone_is_installed_alone(self):
        self._completed_alone("toolkit", [[TOOLKIT]], "installed NVIDIA's container toolkit")

    def test_the_runtime_unconfigured_alone_is_configured_alone(self):
        self._completed_alone("runtime", [], "configured the NVIDIA runtime for Docker")

    def test_the_toolkit_missing_after_a_failed_boot_is_installed_with_the_driver_left_alone(self):
        # The driver came through on the first boot; the toolkit's source did not answer.
        self.m.device("0000:00:1e.0")
        self.m.update(key_file=str(self.root / "no-such-key"))
        detail = self.failed()
        self.assertTrue(detail.startswith("the container toolkit: curl -fsSL exited 1"), detail)
        self.m.boot(OLD, "boot-2")
        self.m.update(loaded=True, key_file=str(NVIDIA_KEY))
        self.m.clear_calls()
        outcome = self.step()
        self.assertEqual(outcome.state, "ok", outcome.detail)
        self.assertEqual(self.m.installs(), [[TOOLKIT]])

    def test_an_adopted_machines_own_driver_and_docker_are_kept(self):
        self.m.device("0000:00:1e.0")
        self.m.update(own_driver=True, version="550.163.01", cuda="12.4")
        (self.m.bin / "nvidia-smi").symlink_to(self.m.fake)     # the person's own install
        self.m.install_already("docker-ce")
        outcome = self.step()
        self.assertEqual(outcome.state, "ok", outcome.detail)
        self.assertIn("(driver 550.163.01)", outcome.detail)
        self.assertEqual(self.m.installs(), [[TOOLKIT]])

    def test_an_adopted_machines_older_driver_passes_the_container_check(self):
        # R525 supports CUDA 12.0; the check image asks for 13.0, which the check does not need.
        self.m.device("0000:00:1e.0")
        self.m.update(own_driver=True, version="525.147.05", cuda="12.0")
        (self.m.bin / "nvidia-smi").symlink_to(self.m.fake)
        outcome = self.step()
        self.assertEqual(outcome.state, "ok", outcome.detail)
        self.assertIn("(driver 525.147.05)", outcome.detail)

    def test_a_failed_docker_restart_is_owed_until_one_succeeds(self):
        self.m.device("0000:00:1e.0")
        self.m.update(restart_fails=1)
        self.assertTrue(self.failed().startswith("the runtime: systemctl restart exited 1"))
        self.m.clear_calls()
        outcome = self.step()   # the same boot: daemon.json already holds the runtime
        self.assertEqual(outcome.state, "ok", outcome.detail)
        self.assertIn(["systemctl", "restart", "docker.service"], self.m.calls())
        self.assertIn("configured the NVIDIA runtime for Docker", outcome.detail)
        self.m.clear_calls()
        self.step()
        self.assertNotIn(["systemctl", "restart", "docker.service"], self.m.calls(), "paid once, not again")

    # --- the kernel the archive has no modules for ---

    def test_no_exact_package_takes_one_reboot_into_the_newer_kernel(self):
        self.m.device("0000:00:1e.0")
        self.m.update(archive=[UTILS, META, EXACT_NEW, "docker-ce", "containerd.io", TOOLKIT])
        outcome = self.step()
        self.assertEqual((outcome.state, outcome.reboot), ("deferred", True))
        self.assertIn(f"no {EXACT_OLD}: installed {META}", outcome.detail)
        self.assertEqual(self.m.installs(), [[META, UTILS]])
        self.assertTrue(gpu.MARKER.exists())
        # The reboot comes up on the newer kernel, whose modules the metapackage brought.
        self.m.boot(NEW, "boot-2")
        self.m.clear_calls()
        outcome = self.step()
        self.assertEqual((outcome.state, outcome.reboot), ("ok", False), outcome.detail)
        self.assertIn(f"installed the driver (branch {B} for kernel {NEW})", outcome.detail)
        self.assertFalse(gpu.MARKER.exists(), "the marker goes once the driver answers")

    def test_still_missing_after_the_reboot_fails_naming_the_kernel_and_branch(self):
        self.m.device("0000:00:1e.0")
        self.m.update(archive=[UTILS, META, "docker-ce", "containerd.io", TOOLKIT])
        self.assertTrue(self.step().reboot)
        self.m.boot(OLD, "boot-2")    # it came up on the same kernel
        self.m.clear_calls()
        detail = self.failed()
        self.assertEqual(detail, f"the driver: still no driver after the reboot: Ubuntu's archive has no {EXACT_OLD} "
                                 f"for the running kernel {OLD} (branch {B})")
        self.assertEqual(self.m.installs(), [], "no second metapackage, no second reboot")

    def test_a_step_rerun_before_the_reboot_asks_for_it_again(self):
        self.m.device("0000:00:1e.0")
        self.m.update(archive=[UTILS, META, "docker-ce", "containerd.io", TOOLKIT])
        self.assertTrue(self.step().reboot)
        self.m.clear_calls()
        outcome = self.step()      # the same boot: the reboot was never taken
        self.assertTrue(outcome.reboot, outcome.detail)
        self.assertEqual(self.m.installs(), [])

    def test_no_package_for_the_kernel_nor_its_flavour_fails_naming_both(self):
        self.m.device("0000:00:1e.0")
        self.m.update(archive=[UTILS], images=["linux-image-virtual", f"linux-image-{OLD}"])
        detail = self.failed()
        self.assertEqual(detail, f"the driver: Ubuntu's archive has no linux-modules-nvidia-{B}-server-open package "
                                 f"for the running kernel {OLD}, nor for its flavour (linux-image-virtual)")
        self.assertFalse(gpu.MARKER.exists())

    # --- the failures that name their part ---

    def test_a_key_that_is_not_nvidias_writes_nothing(self):
        self.m.device("0000:00:1e.0")
        self.m.update(key_file=str(OTHER_KEY))
        detail = self.failed()
        self.assertTrue(detail.startswith("the container toolkit: the key at https://nvidia.github.io/"), detail)
        self.assertIn(f"not {gpu.TOOLKIT_FINGERPRINT}: nothing written", detail)
        self.assertFalse(gpu.TOOLKIT_KEY.exists())
        self.assertFalse(gpu.TOOLKIT_SOURCE.exists())
        self.assertNotIn([TOOLKIT], self.m.installs())

    def test_a_container_that_does_not_see_the_gpu_fails_the_check(self):
        self.m.device("0000:00:1e.0")
        self.m.update(container_blind=True)
        detail = self.failed()
        self.assertTrue(detail.startswith("the GPU container check: docker run exited 125"), detail)

    def test_several_gpus_are_counted(self):
        m = self.m
        m.device("0000:00:1b.0")
        m.device("0000:00:1c.0")
        m.update(gpus=["NVIDIA A10G", "NVIDIA A10G"])
        outcome = self.step()
        self.assertTrue(outcome.detail.startswith("2 × NVIDIA A10G (driver"), outcome.detail)


@unittest.skipUnless(GPG, "gpg reads the keys")
class FingerprintTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tools = pathlib.Path(tmp.name)
        (tools / "gpg").symlink_to(GPG)
        patch = mock.patch.dict(os.environ, {"PATH": str(tools)})
        patch.start()
        self.addCleanup(patch.stop)

    def test_nvidias_key_is_one_primary_key_its_subkey_left_out(self):
        self.assertEqual(gpu.primary_fingerprints(NVIDIA_KEY.read_text()), [gpu.TOOLKIT_FINGERPRINT])

    def test_another_key_and_no_key(self):
        self.assertEqual(gpu.primary_fingerprints(OTHER_KEY.read_text()), ["21B51CB77437100F66C15B47F75DD08EBF72FD40"])
        self.assertEqual(gpu.primary_fingerprints("<html>not a key</html>"), [])

    def test_two_keys_in_one_block_are_both_named(self):
        both = NVIDIA_KEY.read_text() + OTHER_KEY.read_text()
        self.assertEqual(len(gpu.primary_fingerprints(both)), 2)


if __name__ == "__main__":
    unittest.main()
