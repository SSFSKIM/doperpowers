#!/usr/bin/env python3
"""devcloud's integration tests: the image built by image/Dockerfile, booted
in containers against stand-ins (tests/fixtures/fakes.py) for Secret Manager,
the GCE metadata server, the configuration repository and the gateway.

Proves acceptance 3 (container, stand-in profile, no projects), 5 (container,
a reconciled profile change) and 6 (a credential-free image), plus the boot's
failure paths. Prints one line per case, "ok <case>" or "FAIL <case>: why";
exits 1 when a case failed. Every secret here is made up.

    python3 devcloud/tests/integration.py <image>
"""

import atexit
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent
IMAGE = sys.argv[1] if len(sys.argv) > 1 else "devcloud-test"
USER, UID, HOME = "dev", "1001", "/Users/dev"
TAG = f"devcloud-it-{os.getpid()}"
NET, FX, HOST = TAG, f"{TAG}-fixtures", f"{TAG}-host"
STATE = f"{HOME}/.local/state/devcloud-test"
SECRETS = {
    "config-token": "made-up-config-token-7Qx2Lk9Pz",
    "wrong-token": "made-up-wrong-token-3Fz8Yv1Ke",
    "gh-token": "made-up-gh-token-4Rt8Vn1Ws",
    "api-key": "made-up-api-key-2Hy6Jm3Bq",
    "pgpass": "fixtures:5432:sessions:mirror:made-up-pg-password-8Kd5Nf0Zc\n",
}
ROTATED_GH = "made-up-gh-token-rotated-6Pq1Ld"
ENV = ["-e", "GCE_METADATA_HOST=fixtures:8082", "-e", "DEVCLOUD_SM_ENDPOINT=http://fixtures:8081",
       "-e", "DEVCLOUD_ALLOW_HTTP=1"]
TMP = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-it-"))
failures = []


def cleanup():
    for container in (HOST, FX, VM):
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    subprocess.run(["docker", "rmi", "-f", SYSTEMD_IMAGE], capture_output=True)
    subprocess.run(["docker", "network", "rm", NET], capture_output=True)
    subprocess.run(["rm", "-rf", str(TMP)])


atexit.register(cleanup)


class Fail(Exception):
    pass


def check(condition, message):
    if not condition:
        raise Fail(message)


def docker(*args, input=None, check_rc=True, timeout=600):
    result = subprocess.run(["docker", *args], input=input, capture_output=True, text=True, timeout=timeout)
    if check_rc and result.returncode != 0:
        raise Fail(f"docker {' '.join(args[:3])} exited {result.returncode}: {result.stderr.strip()[-600:]}")
    return result


def sh(container, script, user=None, check_rc=True, timeout=300):
    args = ["exec"] + (["-u", user] if user else []) + [container, "sh", "-c", script]
    return docker(*args, check_rc=check_rc, timeout=timeout)


def out(container, script, user=None):
    return sh(container, script, user).stdout


def case(name):
    def run(fn):
        try:
            fn()
            print(f"ok {name}", flush=True)
        except Exception as error:  # noqa: BLE001 — every case reports, the run goes on
            detail = str(error) if isinstance(error, Fail) else traceback.format_exc(limit=3)
            print(f"FAIL {name}: {detail}", flush=True)
            failures.append(name)
        return fn
    return run


def descriptor(name="sbx-test", branch="main", role="sandbox", token="config-token"):
    path = TMP / f"boot-{name}-{branch}-{role}-{token}.env"
    path.write_text(
        f"DEVCLOUD_NAME={name}\nDEVCLOUD_KIND=container\nDEVCLOUD_ROLE={role}\nDEVCLOUD_TAILSCALE=host\n"
        "DEVCLOUD_SEED=gce-metadata\nDEVCLOUD_SM_PROJECT=devcloud-test-project\n"
        "DEVCLOUD_CONFIG_REPO=http://fixtures:8083/config.git\n"
        f"DEVCLOUD_CONFIG_BRANCH={branch}\nDEVCLOUD_CONFIG_TOKEN_SECRET={token}\n")
    path.chmod(0o644)
    return path


def steps(container):
    raw = out(container, "cat /var/lib/devcloud/status.json")
    return {s["name"]: s for s in json.loads(raw)["steps"]}


def wait_healthy(container, timeout=300):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = docker("inspect", "-f", "{{.State.Running}}", container).stdout.strip()
        if state != "true":
            logs = docker("logs", container, check_rc=False)
            raise Fail(f"the container stopped while booting:\n{(logs.stdout + logs.stderr)[-2000:]}")
        if sh(container, "devcloud status >/dev/null 2>&1", check_rc=False).returncode == 0:
            return
        time.sleep(2)
    raise Fail("not healthy after %ds:\n%s" % (timeout, sh(container, "devcloud status", check_rc=False).stdout))


def put_secrets(values):
    docker("exec", "-i", FX, "sh", "-c", "cat > /srv/fakes/secrets.json.tmp && "
           "mv /srv/fakes/secrets.json.tmp /srv/fakes/secrets.json", input=json.dumps(values))


def commit_profile(script, message):
    sh(FX, f"cd /srv/work && {script} && git commit -qam '{message}' && git push -q origin main")


def boot_once(name, desc, hostname=None):
    """devcloud-boot in a fresh container, then its status; the container goes."""
    result = docker("run", "--rm", "--network", NET, "--hostname", hostname or name, *ENV,
                    "-v", f"{desc}:/etc/devcloud/boot.env:ro", "--entrypoint", "sh", IMAGE, "-c",
                    'devcloud-boot >/dev/null 2>&1; echo "rc=$?"; cat /var/lib/devcloud/status.json; '
                    f'test -d {HOME}/.config/claude-secrets && echo store-present || echo store-absent',
                    check_rc=False, timeout=600)
    text = result.stdout
    rc_line, _, rest = text.partition("\n")
    status_text, _, store = rest.rpartition("}")
    status = json.loads(status_text + "}")
    return int(rc_line.split("=")[1]), {s["name"]: s for s in status["steps"]}, store.strip()


# Detector findings the image carries from software it installs, not from
# devcloud or the person: published example keys in vendored libraries' tests.
THIRD_PARTY = ()


def _third_party(path):
    return any(path.startswith(prefix) for prefix in THIRD_PARTY)


# --- acceptance 6 ------------------------------------------------------------------

@case("the image holds no secret (acceptance 6)")
def image_is_clean():
    absent = [
        "/etc/devcloud/boot.env", "/var/lib/devcloud", f"{HOME}/.claude/.git", f"{HOME}/.config/claude-secrets",
        f"{HOME}/.config/gcloud", f"{HOME}/.config/gh", f"{HOME}/.claude/sminos/daemon", "/root/.config/gcloud",
    ]
    present = docker("run", "--rm", "--entrypoint", "sh", IMAGE, "-c",
                     "for p in " + " ".join(absent) + '; do test -e "$p" && echo "$p"; done; true').stdout.split()
    check(present == [], f"the image holds {present}")
    root = TMP / "rootfs"
    root.mkdir()
    export = subprocess.Popen(["docker", "run", "--rm", "--entrypoint", "tar", IMAGE, "-C", "/", "-cf", "-",
                               "--exclude=./proc", "--exclude=./sys", "--exclude=./dev", "."],
                              stdout=subprocess.PIPE)
    subprocess.run(["tar", "-xf", "-", "-C", str(root), "--no-same-owner", "--no-same-permissions"],
                   stdin=export.stdout, stderr=subprocess.DEVNULL)
    export.wait()
    history = docker("history", "--no-trunc", "--format", "{{.CreatedBy}}", IMAGE).stdout
    scan = HERE / "scan-secrets.ts"
    found = subprocess.run(["bun", str(scan), str(root)], capture_output=True, text=True).stdout.splitlines()
    found += subprocess.run(["bun", str(scan), "-"], input=history, capture_output=True, text=True).stdout.splitlines()
    allowed = [line for line in found if _third_party(line.split("\t")[0][len(str(root)):])]
    findings = [line[len(str(root)):] if line.startswith(str(root)) else line for line in found
                if line not in allowed]
    if allowed:
        print(f"  ({len(allowed)} detector findings in vendored third-party test material, listed as allowed)")
    check(findings == [], "the detector found, outside vendored test material:\n  " + "\n  ".join(findings[:40]))
    for value in SECRETS.values():
        hit = subprocess.run(["grep", "-rlF", value.strip(), str(root)], capture_output=True, text=True).stdout
        check(not hit, "a test value is in the image")


# --- the stand-ins -----------------------------------------------------------------

@case("the stand-ins start")
def fixtures():
    docker("network", "create", NET)
    docker("run", "-d", "--name", FX, "--network", NET, "--network-alias", "fixtures",
           "-v", f"{HERE / 'fixtures'}:/fixtures:ro", "--entrypoint", "python3", IMAGE, "/fixtures/fakes.py")
    sh(FX, "bash /fixtures/make-repo.sh")
    put_secrets(SECRETS)
    end = time.monotonic() + 30
    while sh(FX, "python3 -c 'import urllib.request as u; u.urlopen(\"http://localhost:8084/\")'",
             check_rc=False).returncode != 0:
        check(time.monotonic() < end, "the fakes never answered")
        time.sleep(0.5)


# --- acceptance 3: one boot, a working host -----------------------------------------

@case("a container boots to every step ok, projects skipped (acceptance 3)")
def boot():
    docker("run", "-d", "--name", HOST, "--hostname", "sbx-test", "--network", NET, *ENV,
           "-e", "DEVCLOUD_JOB_INTERVAL=40", "-v", f"{descriptor()}:/etc/devcloud/boot.env:ro", IMAGE)
    started = time.monotonic()
    wait_healthy(HOST)
    print(f"  (healthy after {time.monotonic() - started:.0f}s)")
    got = {name: s["state"] for name, s in steps(HOST).items()}
    want = {name: "ok" for name in got}
    want["projects"] = "skipped"
    check(got == want and len(got) == 12, f"states {got}")
    lines = out(HOST, "devcloud status").splitlines()
    check(len(lines) == 12 and lines[0].startswith("identity"), "devcloud status prints a line per step")


@case("identity and the environment file")
def identity_and_env():
    check(out(HOST, "hostname").strip() == "sbx-test", "hostname")
    env = out(HOST, "cat /etc/devcloud/env")
    for line in ('SESSION_MIRROR_HOST="sbx-test"', 'DEVCLOUD_PROBE_PROFILE="profile-1"', 'TZ="Europe/Berlin"',
                 f'EXAMPLE_API_KEY="{SECRETS["api-key"]}"', f'PATH="{HOME}/bin:{HOME}/.local/bin:'):
        check(line in env, f"/etc/devcloud/env lacks {line.split('=')[0]}")
    check("DAEMON_BOOT_ID=" in env, "a container gets its own DAEMON_BOOT_ID")
    check(out(HOST, "stat -c '%a %U %G' /etc/devcloud/env").split() == ["640", "root", USER], "env file mode")
    check(out(HOST, "readlink /etc/localtime").strip().endswith("Europe/Berlin"), "TZ sets the system zone")


@case("secrets materialized as the user, in place")
def secrets_on_disk():
    listing = out(HOST, f"stat -c '%n %a %U' {HOME}/.config/claude-secrets {HOME}/.config/claude-secrets/GH_TOKEN "
                        f"{HOME}/.config/gh/hosts.yml {HOME}/.pgpass").splitlines()
    check([line.split()[1:] for line in listing] == [["700", USER], ["600", USER], ["600", USER], ["600", USER]],
          f"modes and owners {listing}")
    check(out(HOST, f"cat {HOME}/.config/claude-secrets/GH_TOKEN") == SECRETS["gh-token"], "store value")
    hosts = out(HOST, f"cat {HOME}/.config/gh/hosts.yml")
    check(f"oauth_token: {SECRETS['gh-token']}\n" in hosts and "user: devcloud-test" in hosts, "hosts.yml template")
    check(out(HOST, f"cat {HOME}/.pgpass") == SECRETS["pgpass"], ".pgpass is the payload byte for byte")


@case("the user's shells read the environment; root's do not")
def shells():
    check(out(HOST, f"getent passwd {USER}").strip().endswith(":/usr/bin/zsh"), "zsh is the login shell")
    for shell in ("zsh -c", "zsh -lic", "bash -lc"):
        value = out(HOST, f"{shell} 'echo $EXAMPLE_API_KEY'", user=USER).strip().splitlines()[-1:]
        check(value == [SECRETS["api-key"]], f"{shell} sees {value!r}")
    check(out(HOST, "zsh -c 'echo x$EXAMPLE_API_KEY'").strip() == "x", "root's zsh skips the env file")
    check(out(HOST, "zsh -c 'command -v claude'", user=USER).strip() == f"{HOME}/.local/bin/claude", "claude on PATH")


@case("~/.claude is a receive-only clone with no token in it")
def configuration():
    git = f"git -C {HOME}/.claude"
    check(out(HOST, f"{git} config --get remote.origin.url", user=USER).strip() == "http://fixtures:8083/config.git",
          "url")
    check("DISABLED" in out(HOST, f"{git} config --get remote.origin.pushurl", user=USER), "push URL disabled")
    push = sh(HOST, f"{git} push origin main 2>&1", user=USER, check_rc=False)
    check(push.returncode != 0, "git push fails")
    check(out(HOST, f"{git} status --porcelain --untracked-files=no", user=USER) == "", "no tracked change")
    check(out(HOST, "ls /run/devcloud | grep -c git-token || true").strip() == "0", "the token file is gone")
    leaked = out(HOST, f"grep -rlF {SECRETS['config-token']} {HOME}/.claude/.git {HOME}/.gitconfig "
                       f"{HOME}/.git-credentials 2>/dev/null || true").strip()
    check(not leaked, f"the bootstrap token is on disk: {leaked}")


@case("home files, gcloud and gh's git helper")
def home_files():
    check(out(HOST, "git config --global user.email", user=USER).strip() == "devcloud-test@example.com", "identity")
    helpers = out(HOST, "git config --global --get-all credential.https://github.com.helper", user=USER)
    check("gh auth git-credential" in helpers, f"gh setup-git helper: {helpers!r}")
    check(out(HOST, "grep -c DEVCLOUD_PROBE_ZSHRC ~/.zshrc", user=USER).strip() == "1", ".zshrc copied")
    check(out(HOST, f"cat {HOME}/.config/example/settings.json").strip() == '{"nested": true}', "nested home file")
    project = out(HOST, "gcloud config get-value project 2>/dev/null", user=USER).strip()
    check(project == "devcloud-test-project", f"gcloud project {project!r}")


@case("apply.py ran as the user; managed settings copied")
def apply_and_settings():
    check(out(HOST, f"cut -d' ' -f1 {STATE}/apply.log").split() == [UID], "apply.py ran once, as the user")
    managed = json.loads(out(HOST, "cat /etc/claude-code/managed-settings.json"))
    fixture = json.loads((HERE / "fixtures/config/devcloud/managed-settings.json").read_text())
    check(managed == fixture, "managed settings are the profile's")


@case("services run under devcloud-services as PID 1, with the host environment")
def services_running():
    check(out(HOST, "cat /run/devcloud/services.pid").strip() == "1", "the supervisor is PID 1")
    ship = json.loads(out(HOST, f"cat {STATE}/ship.json"))
    check(ship["uid"] == int(UID) and ship["SESSION_MIRROR_HOST"] == "sbx-test", f"ship env {ship}")
    check(ship["EXAMPLE_API_KEY set"] and ship["DEVCLOUD_PROBE_PROFILE"] == "profile-1", f"ship env {ship}")


@case("claude -p answers through the gateway; managed env merges key by key")
def claude_through_gateway():
    sh(FX, ": > /srv/fakes/gateway.jsonl")
    result = sh(HOST, f"cd {HOME} && claude -p 'reply ok' --allowedTools Bash", user=USER, check_rc=False,
                timeout=180)
    check(result.returncode == 0 and result.stdout.strip() == "ok",
          f"claude -p printed {result.stdout.strip()[-300:]!r} (exit {result.returncode}) {result.stderr[-600:]!r}")
    log = [json.loads(line) for line in out(FX, "cat /srv/fakes/gateway.jsonl").splitlines()]
    results = [r for entry in log for r in entry["tool_results"]]
    check("synced-1|managed-1|http://fixtures:8084" in results,
          f"the Bash call saw {results!r}: synced settings.json env and managed env should both hold")
    check(all(entry["authorization"] == "Bearer marker" for entry in log), "the marker token was sent")


@case("no secret value in logs, status or process lists")
def nothing_printed():
    texts = {
        "host logs": (lambda r: r.stdout + r.stderr)(docker("logs", HOST)),
        "status": out(HOST, "cat /var/lib/devcloud/status.json"),
        "devcloud logs": out(HOST, "cat /var/log/devcloud/*.log"),
        "processes": out(HOST, "ps -eo args"),
    }
    for where, text in texts.items():
        for name, value in SECRETS.items():
            check(value.strip() not in text, f"{name}'s value is in the {where}")


@case("a second boot converges")
def idempotent():
    files = f"/etc/devcloud/env {HOME}/.gitconfig /etc/claude-code/managed-settings.json"
    before = out(HOST, f"sha256sum {files}")
    rerun = sh(HOST, "devcloud-boot", check_rc=False)
    check(rerun.returncode == 0, f"second boot exited {rerun.returncode}: {rerun.stdout[-800:]}")
    check(out(HOST, f"sha256sum {files}") == before, "files changed on a second boot")
    check(sh(HOST, "devcloud status", check_rc=False).returncode == 0, "status healthy")


# --- acceptance 5: receive-only configuration, reconciled ------------------------------

@case("pull-config drops a local edit (acceptance 5)")
def pull_drops_edit():
    settings = f"{HOME}/.claude/settings.json"
    original = out(HOST, f"cat {settings}")
    sh(HOST, f"echo '{{\"model\": \"edited-on-host\"}}' > {settings}", user=USER)
    pulled = sh(HOST, "devcloud pull-config", check_rc=False)
    check(pulled.returncode == 0, f"pull-config exited {pulled.returncode}: {pulled.stdout[-500:]}")
    check(out(HOST, f"cat {settings}") == original, "the edit survived the pull")
    check(out(HOST, f"git -C {HOME}/.claude status --porcelain --untracked-files=no", user=USER) == "",
          "a tracked change remains")


@case("a profile change committed upstream reaches managed settings and the services (acceptance 5)")
def pull_reconciles():
    old_pid = json.loads(out(HOST, f"cat {STATE}/ship.json"))["pid"]
    commit_profile("sed -i s/managed-1/managed-2/ devcloud/managed-settings.json && "
                   "sed -i s/profile-1/profile-2/ devcloud/profile.env", "profile change")
    pulled = sh(HOST, "devcloud pull-config", check_rc=False)
    check(pulled.returncode == 0, f"pull-config exited {pulled.returncode}: {pulled.stdout[-500:]}")
    check('"managed-2"' in out(HOST, "cat /etc/claude-code/managed-settings.json"), "managed settings not updated")
    check('DEVCLOUD_PROBE_PROFILE="profile-2"' in out(HOST, "cat /etc/devcloud/env"), "env not updated")
    end = time.monotonic() + 15
    while json.loads(out(HOST, f"cat {STATE}/ship.json"))["DEVCLOUD_PROBE_PROFILE"] != "profile-2":
        check(time.monotonic() < end, "the shipper was not restarted with the new environment")
        time.sleep(0.5)
    check(f"term {old_pid}" in out(HOST, f"cat {STATE}/ship.log"), "the old shipper got SIGTERM")


@case("refresh-secrets follows a rotation")
def refresh_rotation():
    put_secrets(dict(SECRETS, **{"gh-token": ROTATED_GH}))
    refreshed = sh(HOST, "devcloud refresh-secrets", check_rc=False)
    check(refreshed.returncode == 0, f"refresh-secrets exited {refreshed.returncode}: {refreshed.stdout[-500:]}")
    check(out(HOST, f"cat {HOME}/.config/claude-secrets/GH_TOKEN") == ROTATED_GH, "store not rotated")
    check(ROTATED_GH in out(HOST, f"cat {HOME}/.config/gh/hosts.yml"), "hosts.yml not rotated")


@case("the supervisor runs pull-config on its schedule")
def periodic_pull():
    commit_profile("sed -i s/profile-2/profile-3/ devcloud/profile.env", "scheduled change")
    end = time.monotonic() + 120
    while 'DEVCLOUD_PROBE_PROFILE="profile-3"' not in out(HOST, "cat /etc/devcloud/env"):
        check(time.monotonic() < end, "no scheduled pull applied the change within 120s")
        time.sleep(2)


@case("docker stop forwards SIGTERM to the services; a restart boots again with a new boot id")
def stop_and_restart():
    boot_id = out(HOST, "grep DAEMON_BOOT_ID /etc/devcloud/env")
    shipper = json.loads(out(HOST, f"cat {STATE}/ship.json"))["pid"]
    started = time.monotonic()
    docker("stop", "-t", "20", HOST)
    check(time.monotonic() - started < 15, "the supervisor did not exit promptly on SIGTERM")
    docker("start", HOST)
    wait_healthy(HOST)
    check(f"term {shipper}" in out(HOST, f"cat {STATE}/ship.log"), "the shipper never got its final pass")
    check(out(HOST, "grep DAEMON_BOOT_ID /etc/devcloud/env") != boot_id, "DAEMON_BOOT_ID did not change")


# --- under systemd ---------------------------------------------------------------------

SYSTEMD_IMAGE = f"{TAG}-systemd"
VM = f"{TAG}-vm"
# Under systemd, units get none of the container's environment: a drop-in
# points the boot and the jobs at the stand-ins.
SYSTEMD_DOCKERFILE = f"""
FROM {IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends systemd systemd-sysv dbus \\
 && rm -rf /var/lib/apt/lists/* && systemctl enable devcloud-boot.service \\
 && for unit in devcloud-boot devcloud-pull-config devcloud-refresh-secrets; do \\
      mkdir -p /etc/systemd/system/$unit.service.d \\
      && printf '[Service]\\nEnvironment=GCE_METADATA_HOST=fixtures:8082 DEVCLOUD_SM_ENDPOINT=http://fixtures:8081 DEVCLOUD_ALLOW_HTTP=1\\n' \\
         > /etc/systemd/system/$unit.service.d/stand-ins.conf; done
STOPSIGNAL SIGRTMIN+3
ENTRYPOINT ["/sbin/init"]
"""


def wait_systemd_boot(timeout=300):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = sh(VM, "systemctl is-active devcloud-boot.service", check_rc=False).stdout.strip()
        if state == "active":
            return
        if state == "failed":
            raise Fail("devcloud-boot.service failed:\n" + sh(VM, "devcloud status; journalctl -u devcloud-boot "
                                                              "--no-pager | tail -40", check_rc=False).stdout)
        time.sleep(2)
    raise Fail("devcloud-boot.service never finished: " + sh(VM, "systemctl status devcloud-boot --no-pager",
                                                            check_rc=False).stdout[-1500:])


@case("with systemd as PID 1, a persistent host boots from its unit and runs the services as units")
def under_systemd():
    docker("build", "-t", SYSTEMD_IMAGE, "-", input=SYSTEMD_DOCKERFILE, timeout=900)
    desc = TMP / "boot-vm.env"
    desc.write_text(descriptor("sbx-vm").read_text().replace("KIND=container", "KIND=vm")
                    .replace("ROLE=sandbox", "ROLE=persistent").replace("TAILSCALE=host", "TAILSCALE=none"))
    docker("run", "-d", "--name", VM, "--hostname", "sbx-vm", "--network", NET, "--privileged",
           "--cgroupns=host", "-v", "/sys/fs/cgroup:/sys/fs/cgroup:rw", "--tmpfs", "/run", "--tmpfs", "/run/lock",
           "-v", f"{desc}:/etc/devcloud/boot.env:ro", SYSTEMD_IMAGE)
    wait_systemd_boot()
    check(sh(VM, "devcloud status", check_rc=False).returncode == 0, out(VM, "devcloud status"))
    for unit in ("devcloud-session-mirror.service", "devcloud-pull-config.timer", "devcloud-refresh-secrets.timer"):
        check(out(VM, f"systemctl is-active {unit} || true").strip() == "active", f"{unit} is not active")
    ship = json.loads(out(VM, f"cat {STATE}/ship.json"))
    check(ship["uid"] == int(UID) and ship["SESSION_MIRROR_HOST"] == "sbx-vm" and ship["EXAMPLE_API_KEY set"],
          f"the shipper's unit environment {ship}")
    pulled = sh(VM, "systemctl start devcloud-pull-config.service", check_rc=False)
    check(pulled.returncode == 0, "the pull job's unit failed")


@case("after a restart, systemd boots the host again and the units come back (acceptance 4, in a container)")
def systemd_restart():
    docker("restart", "-t", "30", VM)
    time.sleep(3)
    wait_systemd_boot()
    check(sh(VM, "devcloud status", check_rc=False).returncode == 0, out(VM, "devcloud status"))
    check(out(VM, "systemctl is-active devcloud-session-mirror.service || true").strip() == "active",
          "the shipper did not come back")


# --- the boot's failure paths ------------------------------------------------------------

@case("a persistent role without systemd fails identity (acceptance 7's last line)")
def persistent_needs_systemd():
    rc, got, _ = boot_once("sbx-persist", descriptor("sbx-persist", role="persistent"))
    check(rc == 1 and got["identity"]["state"] == "failed" and "systemd" in got["identity"]["detail"], str(got))
    check(list(got) == ["identity"], "the boot went past identity")


@case("a container started without --hostname fails identity")
def hostname_mismatch():
    rc, got, _ = boot_once("sbx-named", descriptor("sbx-named"), hostname="sbx-other")
    check(rc == 1 and "--hostname sbx-named" in got["identity"]["detail"], str(got))


@case("an optional secret absent reads missing and the boot goes on")
def optional_missing():
    rc, got, _ = boot_once("sbx-opt", descriptor("sbx-opt", branch="optional-missing"))
    check(rc == 0 and got["secrets"]["state"] == "missing", str(got.get("secrets")))
    check("not-uploaded-yet" in got["secrets"]["detail"] and got["services"]["state"] == "ok", str(got))


@case("a required secret absent fails the secrets step and stops the boot")
def required_missing():
    rc, got, _ = boot_once("sbx-req", descriptor("sbx-req", branch="required-missing"))
    check(rc == 1 and got["secrets"]["state"] == "failed" and "not-uploaded-yet" in got["secrets"]["detail"],
          str(got.get("secrets")))
    check("home" not in got, "the boot went past the failed step")


@case("a gateway that does not answer stops the boot before any secret is written")
def gateway_down():
    rc, got, store = boot_once("sbx-gw", descriptor("sbx-gw", branch="gateway-down"))
    check(rc == 1 and got["tailnet-check"]["state"] == "failed", str(got.get("tailnet-check")))
    check("secrets" not in got and store == "store-absent", "secrets were written past a failed gateway check")


@case("a wrong repository token fails configuration")
def wrong_token():
    rc, got, _ = boot_once("sbx-tok", descriptor("sbx-tok", token="wrong-token"))
    check(rc == 1 and got["configuration"]["state"] == "failed", str(got.get("configuration")))


if __name__ == "__main__":
    # The cases ran as they were defined, in order; atexit removes the containers.
    if failures:
        print(f"{len(failures)} case(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("every case ok")
