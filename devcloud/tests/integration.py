#!/usr/bin/env python3
"""devcloud's integration tests: the image built by image/Dockerfile, booted
in containers against stand-ins (tests/fixtures/fakes.py) for Secret Manager,
the GCE metadata server, the configuration repository and the gateway.

Proves acceptance 3 (container, stand-in profile, and step 12 with a stand-in
`devenv` runner: a test repository and this checkout's own devenv/), 5
(container, a reconciled profile change), 6 (a credential-free image), 7
(sminos: a stand-in daemon under a systemd container, a sandbox's identity
hygiene) and the host half of 8 (projects from the descriptor, the mirror cache
on a persistent host), plus the boot's failure paths; and the VM driver's
host side (its M2): plugins seated outside the guard with the guard active from
the first session, a departure held and a reboot during it, a release run by
the lease service as a transient unit, and setup.sh's refusal of a user made
otherwise. Prints one line per case, "ok <case>" or "FAIL <case>: why";
exits 1 when a case failed. Every secret here is made up.

    python3 devcloud/tests/integration.py <image>
"""

import atexit
import base64
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]  # the checkout under test, served as example/doperpowers
sys.path.insert(0, str(HERE))
import check_image  # noqa: E402

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
    for container in (HOST, FX, VM, SEATED, ADOPTED, SPOT):
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    subprocess.run(["docker", "rmi", "-f", SYSTEMD_IMAGE, PLANTED, BROKEN_DPKG], capture_output=True)
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


def descriptor(name="sbx-test", branch="main", role="sandbox", token="config-token", projects="", mirror="",
               extra=""):
    path = TMP / f"boot-{name}-{branch}-{role}-{token}.env"
    path.write_text(extra + 
        f"DEVCLOUD_NAME={name}\nDEVCLOUD_KIND=container\nDEVCLOUD_ROLE={role}\nDEVCLOUD_TAILSCALE=host\n"
        "DEVCLOUD_SEED=gce-metadata\nDEVCLOUD_SM_PROJECT=devcloud-test-project\n"
        "DEVCLOUD_CONFIG_REPO=http://fixtures:8083/config.git\n"
        f"DEVCLOUD_CONFIG_BRANCH={branch}\nDEVCLOUD_CONFIG_TOKEN_SECRET={token}\n"
        + (f'DEVCLOUD_PROJECTS="{projects}"\n' if projects else "")
        + (f"DEVCLOUD_MIRROR_DIR={mirror}\n" if mirror else ""))
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


def boot_once(name, desc, hostname=None, after="true", timeout=600, before="true"):
    """devcloud-boot in a fresh container (after the `before` script, as
    root), then its status, whether the store exists, and what the `after`
    script prints; the container goes."""
    result = docker("run", "--rm", "--network", NET, "--hostname", hostname or name, *ENV,
                    "-v", f"{desc}:/etc/devcloud/boot.env:ro", "--entrypoint", "sh", IMAGE, "-c",
                    f'{{ {before}; }} >/dev/null; '
                    'devcloud-boot >/tmp/boot.out 2>&1; echo "rc=$?"; echo "--status"; '
                    'cat /var/lib/devcloud/status.json; echo "--store"; '
                    f'test -d {HOME}/.config/claude-secrets && echo store-present || echo store-absent; '
                    f'echo "--after"; {after}',
                    check_rc=False, timeout=timeout)
    rc_line, _, rest = result.stdout.partition("\n--status\n")
    status_text, _, rest = rest.partition("\n--store\n")
    store, _, extra = rest.partition("\n--after\n")
    status = json.loads(status_text)
    return int(rc_line.split("=")[1]), {s["name"]: s for s in status["steps"]}, store.strip(), extra


# --- acceptance 6 ------------------------------------------------------------------

def _planted_image():
    """A small image holding one of each thing the check exists to catch."""
    planted = SECRETS["api-key"].encode()
    token = "gh" + "p_" + "x7Kq" * 9
    dockerfile = (
        "FROM ubuntu:24.04\n"
        f"RUN mkdir -p /opt/app && echo {base64.b64encode(planted).decode()} > /opt/app/config"
        f" && echo 'machine example.com login x password y' > /root/.netrc && echo 'GITHUB_TOKEN={token}' > /opt/app/env"
        f" && printf 'bin\\000ary %s\\000' {planted.decode()} > /opt/app/blob\n")
    docker("build", "-t", PLANTED, "-", input=dockerfile, timeout=600)
    return PLANTED


PLANTED = f"{TAG}-planted"
BROKEN_DPKG = f"{TAG}-broken-dpkg"


@case("the image check catches a planted value, a credential file and a token (acceptance 6's own test)")
def image_check_catches():
    found = check_image.check(_planted_image(), "/root", values=list(SECRETS.values()))
    check(found["known"] == ["/opt/app/blob\tvalue#4", "/opt/app/config\tvalue#4", "docker history\tvalue#4"],
          f"known {found['known']}")
    check("/root/.netrc" in found["credential"], f"credential {found['credential']}")
    check(any(line.startswith("/opt/app/env\t") for line in found["pattern"]), f"pattern {found['pattern']}")


@case("the image check fails closed: a scanner that fails or reads nothing, an export that fails")
def image_check_fails_closed():
    for scanner in (["sh", "-c", "echo crashed >&2; exit 3", "scanner"],
                    ["sh", "-c", "echo 'scanned 0 files, 0 values' >&2", "scanner"]):
        try:
            check_image.scanner_output(["scan", str(TMP)], "[]", scanner)
        except check_image.CheckError:
            continue
        raise Fail(f"a scanner {scanner[2]!r} passed")
    unreadable = TMP / "unreadable"
    (unreadable / "locked").mkdir(parents=True)
    (unreadable / "locked").chmod(0)
    try:
        check_image.scanner_output(["scan", str(unreadable)], "[]")
        raise Fail("a scan with an unreadable directory passed")
    except check_image.CheckError as error:
        check("unreadable" in str(error), str(error))
    finally:
        (unreadable / "locked").chmod(0o755)
    try:
        check_image.export(f"{TAG}-no-such-image", TMP)
        raise Fail("exporting a missing image passed")
    except check_image.CheckError:
        pass
    docker("build", "-t", BROKEN_DPKG, "-", input="FROM ubuntu:24.04\nRUN rm /var/lib/dpkg/status\n", timeout=600)
    try:
        check_image._package_pristine(BROKEN_DPKG, {"/usr/bin/dpkg"})
        raise Fail("package verification with a broken dpkg database passed")
    except check_image.CheckError as error:
        check("dpkg" in str(error), str(error))
    check(check_image._package_pristine(PLANTED, {"/usr/bin/dpkg", "/opt/app/env"}) == {"/usr/bin/dpkg"},
          "an unchanged package file is pristine and a planted one is not")


@case("the image holds no secret (acceptance 6)")
def image_is_clean():
    found = check_image.check(IMAGE, HOME, values=list(SECRETS.values()) + [ROTATED_GH])
    print(f"  ({found['allowed']} pattern detections inside package-owned trees)")
    check(found["known"] == [], f"(a) known values found: {found['known']}")
    check(found["credential"] == [], f"(b) credential files found: {found['credential']}")
    check(found["pattern"] == [], "(c) detections outside package-owned trees:\n  " + "\n  ".join(found["pattern"][:60]))


# --- the stand-ins -----------------------------------------------------------------

@case("the stand-ins start")
def fixtures():
    docker("network", "create", NET)
    docker("run", "-d", "--name", FX, "--network", NET, "--network-alias", "fixtures",
           "-v", f"{HERE / 'fixtures'}:/fixtures:ro", "-v", f"{REPO}:/repo:ro",
           "--entrypoint", "python3", IMAGE, "/fixtures/fakes.py")
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
    own = re.search(r'^DAEMON_BOOT_ID="([^"]+)"$', env, re.M)
    check(own, "a container gets its own DAEMON_BOOT_ID")
    check(own.group(1) != out(HOST, "cat /proc/sys/kernel/random/boot_id").strip(),
          "the container's DAEMON_BOOT_ID is its host's (acceptance 7)")
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


@case("apply.py ran as the user; managed settings are the profile's, seating no security default")
def apply_and_settings():
    check(out(HOST, f"cut -d' ' -f1 {STATE}/apply.log").split() == [UID], "apply.py ran once, as the user")
    managed = json.loads(out(HOST, "cat /etc/claude-code/managed-settings.json"))
    fixture = json.loads((HERE / "fixtures/config/devcloud/managed-settings.json").read_text())
    check(managed == {**fixture, "prependPlugins": []}, f"managed settings {managed!r}")


@case("services run under devcloud-services as PID 1, with the host environment")
def services_running():
    check(out(HOST, "cat /run/devcloud/services.pid").strip() == "1", "the supervisor is PID 1")
    ship = json.loads(out(HOST, f"cat {STATE}/ship.json"))
    check(ship["uid"] == int(UID) and ship["SESSION_MIRROR_HOST"] == "sbx-test", f"ship env {ship}")
    check(ship["EXAMPLE_API_KEY set"] and ship["DEVCLOUD_PROBE_PROFILE"] == "profile-1", f"ship env {ship}")
    check("a sandbox, not a sminos machine" in steps(HOST)["services"]["detail"], steps(HOST)["services"]["detail"])
    check(sh(HOST, f"test -e {HOME}/.claude/sminos/daemon", check_rc=False).returncode != 0,
          "a sandbox carries $SMINOS_HOME/daemon/ (acceptance 7)")


@case("claude -p answers through the gateway, no security default seated; managed env merges key by key")
def claude_through_gateway():
    sh(FX, ": > /srv/fakes/gateway.jsonl")
    result = sh(HOST, f"cd {HOME} && claude -p 'reply ok' --allowedTools Bash --debug-file {STATE}/claude-debug.log",
                user=USER, check_rc=False, timeout=180)
    check(result.returncode == 0 and result.stdout.strip() == "ok",
          f"claude -p printed {result.stdout.strip()[-300:]!r} (exit {result.returncode}) {result.stderr[-600:]!r}")
    seat = [line for line in out(HOST, f"cat {STATE}/claude-debug.log").splitlines() if "sec-default@builtin" in line]
    check(any("cc-plugin-sec-default@builtin not seated" in line for line in seat),
          f"the engine's security default is seated on a host (Design §6): {seat[:3]!r}")
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
    check("session-mirror: shipping with key [secret]" in texts["host logs"],
          "the shipper's output was not forwarded, scrubbed, to the container log")


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


@case("step 11 stops a service whose program a pull removed, and starts it when a pull brings it back")
def services_follow_the_configuration():
    def ship_log():
        return out(HOST, f"cat {STATE}/ship.log").split("\n")
    running = json.loads(out(HOST, f"cat {STATE}/ship.json"))["pid"]
    commit_profile("git rm -q tools/session-mirror", "no shipper")
    check(sh(HOST, "devcloud pull-config", check_rc=False).returncode == 0, "pull-config failed")
    end = time.monotonic() + 15
    while f"term {running}" not in ship_log():
        check(time.monotonic() < end, "the removed shipper was never stopped")
        time.sleep(0.5)
    starts = sum(1 for line in ship_log() if line.startswith("start"))
    time.sleep(5)
    check(sum(1 for line in ship_log() if line.startswith("start")) == starts, "the removed shipper restarted")
    check("not run: session-mirror" in steps(HOST)["services"]["detail"], steps(HOST)["services"]["detail"])
    sh(FX, "cd /srv/work && git revert --no-edit HEAD >/dev/null && git push -q origin main")
    check(sh(HOST, "devcloud pull-config", check_rc=False).returncode == 0, "pull-config failed")
    end = time.monotonic() + 15
    while sum(1 for line in ship_log() if line.startswith("start")) == starts:
        check(time.monotonic() < end, "the shipper did not start when its program came back")
        time.sleep(0.5)


@case("the tools the guard's notices suggest are on the user's PATH: python3 (3.11+), jq, perl, xxd, gh")
def guard_tools():
    for tool in ("python3", "jq", "perl", "xxd", "gh"):
        found = sh(HOST, f"zsh -c 'command -v {tool}'", user=USER, check_rc=False)
        check(found.returncode == 0 and found.stdout.strip(), f"{tool} is not on the user's PATH")
    version = out(HOST, "python3 -c 'import sys, tomllib; print(sys.version_info >= (3, 11))'", user=USER)
    check(version.strip() == "True", "python3 lacks 3.11's tomllib")


@case("the image user has passwordless sudo, from a validated drop-in")
def sudo():
    check(sh(HOST, "sudo -n true", user=USER, check_rc=False).returncode == 0, "sudo -n true failed for the user")
    check(out(HOST, "stat -c '%a %U' /etc/sudoers.d/devcloud-user").split() == ["440", "root"], "drop-in mode")


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


# --- acceptance 8, the host's half: projects ----------------------------------------------

@case("step 12 runs devenv up per descriptor entry, as the user with the host's environment (acceptance 3, 8)")
def projects_set_up():
    desc = descriptor("sbx-proj", projects="example/app example/doperpowers@under-test", mirror="/srv/host-mirrors")
    validate = f"runuser -l {USER} -c 'cd ~/src/doperpowers && bash devenv/validate.sh' >/tmp/validate.out 2>&1"
    rc, got, _, extra = boot_once("sbx-proj", desc, timeout=1800, after=(
        f"cat {STATE}/devenv.log {STATE}/app-setup.log; echo '--validate'; {validate}; "
        "echo \"rc=$?\"; tail -n 20 /tmp/validate.out"))
    projects = got.get("projects", {})
    check(rc == 0 and projects.get("state") == "ok", f"rc={rc} projects={projects}\n{extra[-3000:]}")
    check(projects["detail"] == "example/app ok; example/doperpowers@under-test ok", projects["detail"])
    logs, _, validated = extra.partition("--validate\n")
    check(logs.splitlines() == [
        "up app --url https://github.com/example/app.git | mirror=/srv/host-mirrors",
        "up doperpowers --url https://github.com/example/doperpowers.git --ref under-test | mirror=/srv/host-mirrors",
        f"setup as {USER} in {HOME}/src/app api-key=set"], logs)
    check(validated.startswith("rc=0"), f"doperpowers' devenv/validate.sh after its setup.sh:\n{validated[-2000:]}")


@case("a project that fails is recorded failed; the boot exits 3 and the container's services start")
def project_fails():
    rc, got, _, _ = boot_once("sbx-noproj", descriptor("sbx-noproj", projects="example/app example/missing"))
    projects = got.get("projects", {})
    check(rc == 3 and projects.get("state") == "failed", f"rc={rc} projects={projects}")
    check(projects["detail"].startswith("example/app ok; example/missing failed (devenv up exited"), projects["detail"])
    check(all(s["state"] == "ok" for name, s in got.items() if name != "projects"), str(got))
    # Through the image's own entrypoint: the supervisor runs after a boot that exited 3.
    name = f"{TAG}-noproj"
    docker("run", "-d", "--name", name, "--hostname", "sbx-noproj2", "--network", NET, *ENV,
           "-v", f"{descriptor('sbx-noproj2', projects='example/missing')}:/etc/devcloud/boot.env:ro", IMAGE)
    try:
        end = time.monotonic() + 300
        while sh(name, "test -s /run/devcloud/services.pid", check_rc=False).returncode != 0:
            state = docker("inspect", "-f", "{{.State.Running}}", name).stdout.strip()
            check(state == "true", "the container exited after a boot whose only failure was a project:\n"
                  + docker("logs", name, check_rc=False).stdout[-1500:])
            check(time.monotonic() < end, "devcloud-services never started")
            time.sleep(2)
        check(out(name, "cat /run/devcloud/services.pid").strip() == "1", "the supervisor is not PID 1")
        check(steps(name)["projects"]["state"] == "failed", "the status does not name the failed project")
    finally:
        docker("rm", "-f", name, check_rc=False)


# --- under systemd ---------------------------------------------------------------------

SYSTEMD_IMAGE = f"{TAG}-systemd"
VM = f"{TAG}-vm"
# Under systemd, units get none of the container's environment: a drop-in
# points the boot and the jobs at the stand-ins.
SYSTEMD_DOCKERFILE = f"""
FROM {IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends systemd systemd-sysv dbus libpam-systemd \\
 && rm -rf /var/lib/apt/lists/* && systemctl enable devcloud-boot.service \\
 && for unit in devcloud-boot devcloud-pull-config devcloud-refresh-secrets devcloud-refresh-mirrors \\
                devcloud-lease devcloud-enroll; do \\
      mkdir -p /etc/systemd/system/$unit.service.d \\
      && printf '[Service]\\nEnvironment=GCE_METADATA_HOST=fixtures:8082 DEVCLOUD_SM_ENDPOINT=http://fixtures:8081 DEVCLOUD_ALLOW_HTTP=1\\n' \\
         > /etc/systemd/system/$unit.service.d/stand-ins.conf; done
STOPSIGNAL SIGRTMIN+3
ENTRYPOINT ["/sbin/init"]
"""


STAND_INS = "env GCE_METADATA_HOST=fixtures:8082 DEVCLOUD_SM_ENDPOINT=http://fixtures:8081 DEVCLOUD_ALLOW_HTTP=1"
RECONCILE_WITH_STAND_INS = ("env GCE_METADATA_HOST=fixtures:8082 DEVCLOUD_SM_ENDPOINT=http://fixtures:8081 "
                            "DEVCLOUD_ALLOW_HTTP=1 devcloud reconcile")
SMINOS_UNIT = f"{HOME}/.config/systemd/user/sminos-daemon.service"
MARKETPLACE = f"{HOME}/.claude/plugins/marketplaces/doperpowers"


def user_unit_active(unit):
    return sh(VM, f"XDG_RUNTIME_DIR=/run/user/{UID} systemctl --user is-active {unit}", user=USER,
              check_rc=False).stdout.strip() == "active"


def wait_systemd_boot(timeout=300):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = sh(VM, "systemctl is-active devcloud-boot.service", check_rc=False).stdout.strip()
        if state == "active":
            return
        if state == "failed":
            raise Fail("devcloud-boot.service failed:\n" + _systemd_diagnostics())
        time.sleep(2)
    raise Fail("devcloud-boot.service never finished:\n" + _systemd_diagnostics())


def wait_active(unit, timeout=30):
    end = time.monotonic() + timeout
    while out(VM, f"systemctl is-active {unit} || true").strip() != "active":
        check(time.monotonic() < end, f"{unit} is not active: " + out(VM, f"systemctl status {unit} --no-pager || true"))
        time.sleep(1)


def _systemd_diagnostics():
    return sh(VM, "cat /var/lib/devcloud/status.json; systemctl status devcloud-boot --no-pager -l; "
                  "journalctl -u devcloud-boot --no-pager -n 60; systemctl --failed --no-pager", check_rc=False,
              timeout=60).stdout[-4000:]


@case("with systemd as PID 1, a persistent host boots from its unit and runs the services as units")
def under_systemd():
    docker("build", "-t", SYSTEMD_IMAGE, "-", input=SYSTEMD_DOCKERFILE, timeout=900)
    desc = TMP / "boot-vm.env"
    desc.write_text(descriptor("sbx-vm", projects="example/app").read_text().replace("KIND=container", "KIND=vm")
                    .replace("ROLE=sandbox", "ROLE=persistent").replace("TAILSCALE=host", "TAILSCALE=none"))
    docker("run", "-d", "--name", VM, "--hostname", "sbx-vm", "--network", NET, "--privileged",
           "--cgroupns=host", "-v", "/sys/fs/cgroup:/sys/fs/cgroup:rw", "--tmpfs", "/run", "--tmpfs", "/run/lock",
           "-v", f"{desc}:/etc/devcloud/boot.env:ro", SYSTEMD_IMAGE)
    wait_systemd_boot()
    check(sh(VM, "devcloud status", check_rc=False).returncode == 0, out(VM, "devcloud status"))
    check("3" in out(VM, "systemctl show -p SuccessExitStatus devcloud-boot.service"),
          "the boot unit does not count exit 3 (only projects failed) as success")
    for unit in ("devcloud-session-mirror.service", "devcloud-pull-config.timer", "devcloud-refresh-secrets.timer",
                 "devcloud-refresh-mirrors.timer", "devcloud-lease.timer", "devcloud-enroll.timer"):
        wait_active(unit)
    check(out(VM, "systemctl is-enabled devcloud-spot.service || true").strip() == "disabled",
          "the spot unit is enabled on a VM that is not spot")
    check("ConditionPathExists=/etc/devcloud/boot.env" in out(VM, "systemctl cat devcloud-boot.service"),
          "the boot unit runs without a descriptor")
    check(sh(VM, "command -v nft", check_rc=False).returncode == 0, "nft is not installed")
    for path in ("/etc/devcloud/boot.env", "/etc/devcloud/env", "/etc/claude-code/managed-settings.json",
                 f"{HOME}/.config/claude-secrets/GH_TOKEN", f"{HOME}/.pgpass", f"{HOME}/.config/gcloud"):
        check(path in out(VM, "cat /var/lib/devcloud/credentials.ledger"), f"{path} is not in the credential ledger")
    check(out(VM, "stat -c '%a %U' /var/lib/devcloud/credentials.ledger").split() == ["600", "root"], "ledger mode")
    lease_tick = sh(VM, "systemctl start devcloud-lease.service", check_rc=False)
    check(lease_tick.returncode == 0, "the lease service failed on a host with no lease")
    end = time.monotonic() + 30
    while "shipping with key [secret]" not in out(VM, "journalctl -u devcloud-session-mirror -o cat --no-pager"):
        check(time.monotonic() < end, "the shipper's output never reached the journal, scrubbed: "
              + out(VM, "journalctl -u devcloud-session-mirror -o cat --no-pager | tail -5"))
        time.sleep(1)
    journal = out(VM, "journalctl -o cat --no-pager")
    for name, value in SECRETS.items():
        check(value.strip() not in journal, f"{name}'s value is in the journal")
    ship = json.loads(out(VM, f"cat {STATE}/ship.json"))
    check(ship["uid"] == int(UID) and ship["SESSION_MIRROR_HOST"] == "sbx-vm" and ship["EXAMPLE_API_KEY set"],
          f"the shipper's unit environment {ship}")
    pulled = sh(VM, "systemctl start devcloud-pull-config.service", check_rc=False)
    check(pulled.returncode == 0, "the pull job's unit failed")
    check("sminos: not enrolled, local-only" in steps(VM)["services"]["detail"], steps(VM)["services"]["detail"])
    check(sh(VM, f"test -e {SMINOS_UNIT}", check_rc=False).returncode != 0, "a sminos unit on an unenrolled host")


@case("once enrolled, a reconcile installs the sminos daemon as a lingering user unit (acceptance 7)")
def enrolled_daemon():
    # The clone's sminos CLI where the sminos plugin keeps it (its sminos/ folder).
    scripts = f"{MARKETPLACE}/sminos/skills/sminos/scripts"
    sh(VM, f"install -d -o {USER} -g {USER} {HOME}/.claude/plugins {MARKETPLACE} {MARKETPLACE}/sminos "
           f"{MARKETPLACE}/sminos/skills {MARKETPLACE}/sminos/skills/sminos {scripts} {HOME}/.claude/sminos "
           f"{HOME}/.claude/sminos/daemon")
    docker("cp", str(HERE / "fixtures/sminos.py"), f"{VM}:{scripts}/sminos.py")
    known = json.dumps({"doperpowers": {"source": {"source": "github", "repo": "example/doperpowers"},
                                        "installLocation": MARKETPLACE}})
    sh(VM, f"echo '{known}' > {HOME}/.claude/plugins/known_marketplaces.json && "
           f"echo '{{\"machine\": \"sbx-vm\"}}' > {HOME}/.claude/sminos/daemon/hub.json && "
           f"chown {USER}:{USER} {scripts}/sminos.py {HOME}/.claude/plugins/known_marketplaces.json "
           f"{HOME}/.claude/sminos/daemon/hub.json")
    # As the units run it: a docker exec gets none of their drop-ins' stand-in environment.
    reconciled = sh(VM, RECONCILE_WITH_STAND_INS, check_rc=False, timeout=600)
    check(reconciled.returncode == 0, f"reconcile exited {reconciled.returncode}: {reconciled.stdout[-800:]}\n"
          + _systemd_diagnostics())
    detail = steps(VM)["services"]["detail"]
    check("sminos daemon: sminos-daemon.service enabled" in detail, detail)
    check(out(VM, f"loginctl show-user {USER} --property=Linger").strip() == "Linger=yes", "lingering is off")
    end = time.monotonic() + 30
    while not user_unit_active("sminos-daemon.service"):
        check(time.monotonic() < end, "the sminos user unit is not active: " + out(
            VM, f"XDG_RUNTIME_DIR=/run/user/{UID} runuser -u {USER} -- systemctl --user status sminos-daemon "
                "--no-pager || true"))
        time.sleep(1)
    end = time.monotonic() + 15
    while sh(VM, f"test -s {STATE}/sminos.json", check_rc=False).returncode != 0:
        check(time.monotonic() < end, "the stand-in daemon never recorded its environment")
        time.sleep(0.5)
    seen = json.loads(out(VM, f"cat {STATE}/sminos.json"))
    check(seen["SESSION_MIRROR_HOST"] == "sbx-vm", f"the daemon lacks the host environment: {seen}")
    again = sh(VM, RECONCILE_WITH_STAND_INS, check_rc=False, timeout=600)
    check(again.returncode == 0 and "sminos-daemon.service enabled and running" in steps(VM)["services"]["detail"],
          "a second reconcile restarted an unchanged daemon: " + steps(VM)["services"]["detail"])


@case("a persistent host keeps a mirror of its projects' repositories and refreshes it (Design §7)")
def mirror_cache():
    projects = steps(VM)["projects"]
    check(projects["state"] == "ok" and projects["detail"] == "example/app ok; mirrors: example/app", str(projects))
    mirror = "/srv/devcloud/mirrors/example/app.git"
    check(out(VM, f"stat -c '%U' {mirror}").strip() == USER, "the mirror is the user's")
    check(out(VM, f"git -C {mirror} rev-parse --is-bare-repository", user=USER).strip() == "true", "not a bare mirror")
    check(sh(VM, f"test -e {mirror}/objects/info/alternates", check_rc=False).returncode != 0,
          "the mirror depends on the checkout")
    sh(FX, "cd /srv/app-work && echo v2 > app.lock && git -c user.name=f -c user.email=f@example.com commit -qam two "
           "&& git push -q /srv/git/example/app.git main")
    refreshed = sh(VM, "systemctl start devcloud-refresh-mirrors.service", check_rc=False)
    check(refreshed.returncode == 0, "the mirror refresh unit failed:\n" + _systemd_diagnostics())
    head = out(VM, f"git -C {mirror} log -1 --format=%s main", user=USER).strip()
    check(head == "two", f"the mirror was not refreshed (main is {head!r})")


@case("after a restart, systemd boots the host again and the units come back (acceptance 4, in a container)")
def systemd_restart():
    docker("restart", "-t", "30", VM)
    time.sleep(3)
    wait_systemd_boot()
    check(sh(VM, "devcloud status", check_rc=False).returncode == 0, out(VM, "devcloud status"))
    wait_active("devcloud-session-mirror.service")
    end = time.monotonic() + 30
    while not user_unit_active("sminos-daemon.service"):
        check(time.monotonic() < end, "the sminos daemon did not come back after the restart (acceptance 7)")
        time.sleep(1)


FAIL_BOOT = "/etc/systemd/system/devcloud-boot.service.d/zz-fail.conf"


def wait_boot_state(wanted, timeout=300):
    end = time.monotonic() + timeout
    while (state := sh(VM, "systemctl is-active devcloud-boot.service", check_rc=False).stdout.strip()) != wanted:
        check(time.monotonic() < end, f"devcloud-boot.service is {state}, not {wanted}:\n" + _systemd_diagnostics())
        time.sleep(2)


@case("after a boot that failed, the shipper does not start; a boot that succeeds starts it again")
def failed_boot_keeps_services_down():
    # Secret Manager unreachable from the boot's unit: bootstrap-secrets fails, so step 11 never runs.
    sh(VM, f"printf '[Service]\\nEnvironment=DEVCLOUD_SM_ENDPOINT=http://fixtures:9\\n' > {FAIL_BOOT}")
    docker("restart", "-t", "30", VM)
    time.sleep(3)
    wait_boot_state("failed")
    time.sleep(5)
    state = out(VM, "systemctl is-active devcloud-session-mirror.service || true").strip()
    check(state == "inactive", f"the shipper is {state} after a failed boot")
    check(sh(VM, "test -e /run/devcloud/booted", check_rc=False).returncode != 0, "a failed boot left the marker")
    sh(VM, f"rm {FAIL_BOOT}")
    docker("restart", "-t", "30", VM)
    time.sleep(3)
    wait_systemd_boot()
    wait_active("devcloud-session-mirror.service")


@case("devcloud-boot run by hand on a systemd host leaves the shipper running")
def boot_run_by_hand():
    # No boot-unit job is pending, so the shipper's start from step 11 is not
    # ordered after anything: its condition is read while the boot still runs.
    sh(VM, "systemctl stop devcloud-session-mirror.service")
    booted = sh(VM, RECONCILE_WITH_STAND_INS.replace("devcloud reconcile", "devcloud-boot"), check_rc=False,
                timeout=900)
    check(booted.returncode in (0, 3), f"devcloud-boot exited {booted.returncode}: {booted.stdout[-800:]}")
    wait_active("devcloud-session-mirror.service")


@case("a held departure closes admission, and a reboot during it reopens none (the driver's §4.2)")
def held_departure_and_reboot():
    # The enrolled VM above: its daemon runs. The ship fails, so the departure holds.
    sh(VM, f"touch {STATE}/ship-fail && chown {USER}:{USER} {STATE}/ship-fail")
    held = sh(VM, f"{STAND_INS} devcloud depart --force --no-poweroff", check_rc=False, timeout=600)
    check(held.returncode == 4, f"depart exited {held.returncode}, not 4 (held): {held.stdout[-1500:]}")
    lifecycle = json.loads(out(VM, "cat /var/lib/devcloud/status.json"))["lifecycle"]
    check((lifecycle["state"], lifecycle["detail"]) == ("held", "held (ship failed)"), str(lifecycle))
    check("once" in out(VM, f"cat {STATE}/ship.log"), "the departure never shipped")
    check(not user_unit_active("sminos-daemon.service"), "the daemon runs after the departure closed admission")

    def closed():
        for timer in ("pull-config", "refresh-secrets", "refresh-mirrors", "enroll"):
            state = out(VM, f"systemctl is-enabled devcloud-{timer}.timer || true").strip()
            check(state == "disabled", f"devcloud-{timer}.timer is {state} during a held departure")
            state = out(VM, f"systemctl is-active devcloud-{timer}.timer || true").strip()
            check(state == "inactive", f"devcloud-{timer}.timer is {state} during a held departure")
        enabled = sh(VM, f"XDG_RUNTIME_DIR=/run/user/{UID} systemctl --user is-enabled sminos-daemon.service",
                     user=USER, check_rc=False).stdout.strip()
        check(enabled == "disabled", f"the daemon's unit is {enabled}")
        wait_active("devcloud-lease.timer")
    closed()
    job = sh(VM, RECONCILE_WITH_STAND_INS.replace("reconcile", "refresh-secrets"), check_rc=False, timeout=300)
    check(job.returncode == 0 and "the departure has started" in job.stdout + job.stderr,
          f"refresh-secrets ran during a held departure: {job.stdout[-600:]}")
    check(not user_unit_active("sminos-daemon.service"), "a job restarted the daemon during a hold")
    docker("restart", "-t", "30", VM)
    time.sleep(3)
    wait_systemd_boot()
    time.sleep(5)
    closed()
    check(not user_unit_active("sminos-daemon.service"), "the reboot started the daemon during a held departure")
    check("the daemon stays stopped" in steps(VM)["services"]["detail"], steps(VM)["services"]["detail"])
    sh(VM, f"rm {STATE}/ship-fail")
    done = sh(VM, f"{STAND_INS} devcloud depart --force --no-poweroff", check_rc=False, timeout=600)
    check(done.returncode == 0 and "devcloud-depart: ready-to-logout" in done.stdout,
          f"the retried departure exited {done.returncode}: {done.stdout[-1500:]}")
    check(json.loads(out(VM, "cat /var/lib/devcloud/status.json"))["lifecycle"]["state"] == "departed", "not departed")
    check(sh(VM, f"test -e {HOME}/.claude/sminos/daemon/hub.json", check_rc=False).returncode != 0,
          "the departure did not leave the desk")
    leave = [json.loads(line)["argv"] for line in out(VM, f"cat {STATE}/calls.jsonl").splitlines()]
    check(["hub", "leave"] in leave, f"no hub leave: {leave}")


@case("a sandbox carrying a sminos machine identity fails services (acceptance 7)")
def sandbox_with_identity():
    plant = (f"mkdir -p {HOME}/.claude/sminos/daemon && echo '{{}}' > {HOME}/.claude/sminos/daemon/machine.json "
             f"&& chown -R {USER}:{USER} {HOME}/.claude")
    rc, got, _, _ = boot_once("sbx-clone", descriptor("sbx-clone"), before=plant)
    check(rc == 1 and got["services"]["state"] == "failed", str(got.get("services")))
    check("machine.json" in got["services"]["detail"] and "sandbox" in got["services"]["detail"], str(got["services"]))


# --- the VM driver's host side ------------------------------------------------------------

ADOPTED = f"{TAG}-adopted"
SEATED = f"{TAG}-seated"
SPOT = f"{TAG}-spot"
MARKETPLACE_COPY = "/var/lib/devcloud/marketplaces/doperpowers"


@case("a spot VM boots to its end and its reclaim unit starts after the boot (no wait on a unit ordered after it)")
def spot_vm_boots():
    desc = descriptor("dc-spot-5e6f", extra="DEVCLOUD_SPOT=1\n")
    desc.write_text(desc.read_text().replace("KIND=container", "KIND=vm").replace("ROLE=sandbox", "ROLE=persistent")
                    .replace("TAILSCALE=host", "TAILSCALE=none"))
    docker("run", "-d", "--name", SPOT, "--hostname", "dc-spot-5e6f", "--network", NET, "--privileged",
           "--cgroupns=host", "-v", "/sys/fs/cgroup:/sys/fs/cgroup:rw", "--tmpfs", "/run", "--tmpfs", "/run/lock",
           "-v", f"{desc}:/etc/devcloud/boot.env:ro", SYSTEMD_IMAGE)
    end = time.monotonic() + 300
    while (state := sh(SPOT, "systemctl is-active devcloud-boot.service", check_rc=False).stdout.strip()) != "active":
        check(state != "failed" and time.monotonic() < end, f"devcloud-boot.service is {state} on a spot VM: " + sh(
            SPOT, "cat /var/lib/devcloud/status.json; systemctl list-jobs --no-pager; "
                  "journalctl -u devcloud-boot --no-pager -n 40", check_rc=False).stdout[-2500:])
        time.sleep(2)
    check(sh(SPOT, "devcloud status", check_rc=False).returncode == 0, out(SPOT, "devcloud status || true"))
    check(out(SPOT, "systemctl is-enabled devcloud-spot.service || true").strip() == "enabled",
          "the spot unit is not enabled on a spot VM")
    end = time.monotonic() + 30
    while out(SPOT, "systemctl is-active devcloud-spot.service || true").strip() != "active":
        check(time.monotonic() < end, "the spot unit never started: "
              + out(SPOT, "systemctl status devcloud-spot.service --no-pager || true"))
        time.sleep(1)
    check("devcloud-spot.service enabled" in steps(SPOT)["services"]["detail"], steps(SPOT)["services"]["detail"])
    docker("rm", "-f", SPOT)


@case("an adopted machine's lease end releases it through the lease service's transient unit (the driver's §6.5)")
def release_through_the_lease_service():
    desc = descriptor("dc-adp-1a2b", projects="", extra="DEVCLOUD_ADOPTED=1\nDEVCLOUD_EXPIRES=4102444800\n")
    desc.write_text(desc.read_text().replace("KIND=container", "KIND=vm").replace("ROLE=sandbox", "ROLE=persistent")
                    .replace("TAILSCALE=host", "TAILSCALE=none"))
    docker("create", "--name", ADOPTED, "--hostname", "dc-adp-1a2b", "--network", NET, "--privileged",
           "--cgroupns=host", "-v", "/sys/fs/cgroup:/sys/fs/cgroup:rw", "--tmpfs", "/run", "--tmpfs", "/run/lock",
           "-v", f"{HERE / 'fixtures'}:/fixtures:ro", SYSTEMD_IMAGE)
    docker("cp", str(desc), f"{ADOPTED}:/etc/devcloud/boot.env")
    # What adopt saved before it changed anything (M5 writes it): root had a key.
    saved = TMP / "adopt"
    saved.mkdir()
    (saved / "root.authorized_keys").write_text("ssh-ed25519 AAAAoriginalKey person@laptop\n")
    (saved / "keys.json").write_text(json.dumps({"keys": [
        {"path": "/root/.ssh/authorized_keys", "owner": "root", "saved": "root.authorized_keys"}]}))
    docker("cp", str(saved), f"{ADOPTED}:/var/lib/devcloud-adopt")
    docker("start", ADOPTED)
    end = time.monotonic() + 300
    while sh(ADOPTED, "systemctl is-active devcloud-boot.service", check_rc=False).stdout.strip() != "active":
        check(time.monotonic() < end, "the adopted machine never booted: " + sh(
            ADOPTED, "cat /var/lib/devcloud/status.json; journalctl -u devcloud-boot --no-pager -n 40",
            check_rc=False).stdout[-2500:])
        time.sleep(2)
    listed = out(ADOPTED, "cat /var/lib/devcloud/credentials.ledger").split()
    check(len(listed) >= 6, f"the ledger lists {listed}")
    sh(ADOPTED, f"echo 'my own notes' > {HOME}/notes.txt && chown {USER}:{USER} {HOME}/notes.txt")
    sh(ADOPTED, f"runuser -l {USER} -c 'setsid /fixtures/claude </dev/null >/dev/null 2>&1 &'")
    end = time.monotonic() + 15
    while "start" not in sh(ADOPTED, f"cat {STATE}/claude.log", check_rc=False).stdout:
        check(time.monotonic() < end, "the stand-in session never started")
        time.sleep(0.5)
    # The lease ends; the lease service's next run starts the release.
    past = int(time.time()) - 60
    printed = out(ADOPTED, f"{STAND_INS} devcloud lease set {past}").strip()
    check(printed == str(past), f"lease set printed {printed!r}")
    tick = sh(ADOPTED, "systemctl start devcloud-lease.service", check_rc=False)
    check(tick.returncode == 0, "the lease service's run failed: " + out(
        ADOPTED, "journalctl -u devcloud-lease --no-pager -n 30 || true"))
    # A completed release ends by removing devcloud's state directory, its own record with it.
    end = time.monotonic() + 180
    while True:
        journal = out(ADOPTED, "journalctl -u devcloud-release --no-pager -o cat || true")
        if "devcloud release: released" in journal:
            break
        check(time.monotonic() < end and "failed; nothing after it ran" not in journal,
              f"the release never ended: {journal[-2500:]}")
        time.sleep(2)
    check("remove-credentials: ok" in journal, f"the transient unit's journal: {journal[-1500:]}")
    check(sh(ADOPTED, "test -e /var/lib/devcloud", check_rc=False).returncode != 0,
          "/var/lib/devcloud remains, so setup.sh would refuse to adopt the machine again")
    remembered = out(ADOPTED, "systemctl list-units --all --no-legend --plain 'devcloud-*' | grep not-found || true")
    check(remembered.strip() == "", f"systemd still lists removed units: {remembered}")
    for path in listed:
        check(sh(ADOPTED, f"test -e {path}", check_rc=False).returncode != 0, f"{path} survived the release")
    check(sh(ADOPTED, "test -e /var/lib/devcloud/credentials.ledger", check_rc=False).returncode != 0, "the ledger")
    units = out(ADOPTED, "ls /etc/systemd/system | grep '^devcloud-' || true").split()
    check(units == [], f"devcloud units remain: {units}")
    check(out(ADOPTED, "cat /root/.ssh/authorized_keys") == "ssh-ed25519 AAAAoriginalKey person@laptop\n",
          "root's keys were not restored")
    check(sh(ADOPTED, "test -e /var/lib/devcloud-adopt", check_rc=False).returncode != 0, "the saved keys remain")
    check("term" in out(ADOPTED, f"cat {STATE}/claude.log"), "the session was not ended")
    check("once" in out(ADOPTED, f"cat {STATE}/ship.log"), "the release never shipped")
    check(out(ADOPTED, f"cat {HOME}/notes.txt").strip() == "my own notes", "the person's file went")
    check(out(ADOPTED, f"id -u {USER}").strip() == UID, "the user went")
    docker("rm", "-f", ADOPTED)


@case("plugins seated outside the guard: the bridge runs and the guard scrubs from the first session (the driver's §10)")
def plugins_seated():
    docker("run", "-d", "--name", SEATED, "--hostname", "sbx-seated", "--network", NET, *ENV,
           "-v", f"{descriptor('sbx-seated', branch='plugins')}:/etc/devcloud/boot.env:ro", IMAGE)
    wait_healthy(SEATED, timeout=600)
    detail = steps(SEATED)["settings-and-env"]["detail"]
    check(f"plugins seated from {MARKETPLACE_COPY}" in detail, detail)
    managed = json.loads(out(SEATED, "cat /etc/claude-code/managed-settings.json"))
    check(managed["prependPlugins"] == ["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"],
          f"managed prependPlugins {managed.get('prependPlugins')}")
    check(managed["extraKnownMarketplaces"]["doperpowers"] == {"source": {"source": "directory",
                                                                          "path": MARKETPLACE_COPY}}, str(managed))
    known = json.loads(out(SEATED, f"cat {HOME}/.claude/plugins/known_marketplaces.json"))["doperpowers"]
    check(known["installLocation"] == MARKETPLACE_COPY, f"the record {known}")
    check(out(SEATED, f"stat -c '%U' {MARKETPLACE_COPY}").strip() == "root", "the copy is not root's")
    # A reconcile (the apply step installs from the recorded marketplace) keeps the record where it is.
    reconciled = sh(SEATED, "devcloud reconcile", check_rc=False, timeout=900)
    check(reconciled.returncode == 0, f"reconcile exited {reconciled.returncode}: {reconciled.stdout[-1500:]}\n"
          + out(SEATED, f"cat {STATE}/apply.log"))
    known = json.loads(out(SEATED, f"cat {HOME}/.claude/plugins/known_marketplaces.json"))["doperpowers"]
    check(known["installLocation"] == MARKETPLACE_COPY, f"a reconcile reverted the record: {known}")
    installed = json.loads(out(SEATED, f"cat {HOME}/.claude/plugins/installed_plugins.json"))["plugins"]
    check({"devcloud@doperpowers", "sminos@doperpowers"} <= set(installed), f"installed {sorted(installed)}\n"
          + out(SEATED, f"cat {STATE}/apply.log"))
    sh(FX, ": > /srv/fakes/gateway.jsonl")
    debug = f"{STATE}/seated-debug.log"
    session = sh(SEATED, f"cd {HOME} && claude -p 'devcloud-bridge-probe' --allowedTools Bash --debug-file {debug}",
                 user=USER, check_rc=False, timeout=300)
    log = out(SEATED, f"cat {debug}")
    check(session.returncode == 0, f"the session exited {session.returncode}: {session.stdout[-500:]} "
          f"{session.stderr[-800:]}")
    check("the bridge is off" not in log, "the bridge turned itself off: " + "\n".join(
        line for line in log.splitlines() if "bridge" in line)[-1500:])
    results = [r for line in out(FX, "cat /srv/fakes/gateway.jsonl").splitlines()
               for r in json.loads(line)["tool_results"]]
    probe = [r for r in results if "redacted" in r or "ghp_" in r]
    check(probe, f"the probe's result never reached the gateway: {results}")
    sockets, _, token = probe[0].partition("\n")
    check(sockets.strip().isdigit() and int(sockets) >= 1, f"no bridge socket during the session: {probe[0]!r}")
    check("ghp_Zq9XwT4" not in probe[0] and "[redacted:" in token, f"the guard did not scrub: {probe[0]!r}")
    transcripts = out(SEATED, f"cat {HOME}/.claude/projects/*/*.jsonl")
    check("ghp_Zq9XwT4" not in transcripts, "the token is raw in the transcript")
    docker("rm", "-f", SEATED)


@case("setup.sh refuses an existing user whose uid or home differs, naming both (M1's GCE finding)")
def setup_refuses_another_user():
    result = docker("run", "--rm", "--entrypoint", "bash", "-v", f"{REPO / 'devcloud'}:/tmp/devcloud:ro", IMAGE, "-c",
                    "useradd -u 2345 -d /home/person -m person && DEVCLOUD_USER=person DEVCLOUD_UID=1001 "
                    "DEVCLOUD_HOME=/Users/person bash /tmp/devcloud/image/setup.sh", check_rc=False, timeout=300)
    check(result.returncode == 1, f"setup.sh exited {result.returncode}")
    line = result.stderr.strip().splitlines()[-1]
    check(line == "user person exists with uid 2345 and home /home/person; this image needs uid 1001 and home "
                  "/Users/person", line)


# --- the boot's failure paths ------------------------------------------------------------

@case("a persistent role without systemd fails identity (acceptance 7's last line)")
def persistent_needs_systemd():
    rc, got, _, _ = boot_once("sbx-persist", descriptor("sbx-persist", role="persistent"))
    check(rc == 1 and got["identity"]["state"] == "failed" and "systemd" in got["identity"]["detail"], str(got))
    check(list(got) == ["identity"], "the boot went past identity")


@case("a container started without --hostname fails identity")
def hostname_mismatch():
    rc, got, _, _ = boot_once("sbx-named", descriptor("sbx-named"), hostname="sbx-other")
    check(rc == 1 and "--hostname sbx-named" in got["identity"]["detail"], str(got))


@case("an optional secret absent reads missing and the boot goes on")
def optional_missing():
    rc, got, _, _ = boot_once("sbx-opt", descriptor("sbx-opt", branch="optional-missing"))
    check(rc == 0 and got["secrets"]["state"] == "missing", str(got.get("secrets")))
    check("not-uploaded-yet" in got["secrets"]["detail"] and got["services"]["state"] == "ok", str(got))


@case("a required secret absent fails the secrets step and stops the boot")
def required_missing():
    rc, got, _, _ = boot_once("sbx-req", descriptor("sbx-req", branch="required-missing"))
    check(rc == 1 and got["secrets"]["state"] == "failed" and "not-uploaded-yet" in got["secrets"]["detail"],
          str(got.get("secrets")))
    check("home" not in got, "the boot went past the failed step")


@case("a gateway that does not answer stops the boot before any secret is written")
def gateway_down():
    rc, got, store, _ = boot_once("sbx-gw", descriptor("sbx-gw", branch="gateway-down"))
    check(rc == 1 and got["tailnet-check"]["state"] == "failed", str(got.get("tailnet-check")))
    check("secrets" not in got and store == "store-absent", "secrets were written past a failed gateway check")


@case("a failing step whose command prints a secret leaves no value in any log")
def leaking_apply_is_scrubbed():
    value = SECRETS["gh-token"]
    b64 = base64.b64encode(value.encode()).decode()
    rc, got, _, extra = boot_once("sbx-leak", descriptor("sbx-leak", branch="apply-leaks"), after=(
        f"cat /var/log/devcloud/apply.log; echo '--boot-output'; cat /tmp/boot.out; echo '--grep'; "
        f"grep -rlF -e {value} -e {b64} /var/log/devcloud /var/lib/devcloud /tmp/boot.out || echo none"))
    check(rc == 1 and got["apply"]["state"] == "failed", str(got.get("apply")))
    log, _, rest = extra.partition("--boot-output")
    boot_output, _, grep = rest.partition("--grep")
    check(grep.strip() == "none", f"a value is in {grep.strip()}")
    check("leaking [secret]" in log and "leaking b64 [secret]" in log, f"the log lost its diagnostic: {log[-400:]!r}")
    check(value not in got["apply"]["detail"] and value not in boot_output, "a value in the status or output")


@case("a wrong repository token fails configuration")
def wrong_token():
    rc, got, _, _ = boot_once("sbx-tok", descriptor("sbx-tok", token="wrong-token"))
    check(rc == 1 and got["configuration"]["state"] == "failed", str(got.get("configuration")))


if __name__ == "__main__":
    # The cases ran as they were defined, in order; atexit removes the containers.
    if failures:
        print(f"{len(failures)} case(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("every case ok")
