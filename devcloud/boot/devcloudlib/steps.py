"""The boot steps (Design §4) and the runs made of them: a boot (1-12), a
reconcile (5-11), the config pull job (5, then 6-11 when the commit moved),
the secrets refresh (7, 10, 11) and the mirror refresh (no step of its own).
Each step is recorded in the status file; a failed step stops the run, and the
next run retries from its top. Runs hold one lock, so a job never interleaves
with a boot. Every job also takes the lifecycle lock shared and does nothing
once a departure has started (Design §4.1), and every credential a step
writes is listed in the credential ledger first (§6.5)."""

import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import pwd
import socket
import time
import urllib.error
import urllib.request
import uuid

from . import descriptor, envfile, inbound, lease, ledger, plugins, proc, profile as profile_mod, \
    projects as projects_mod, secrets, services, sminos_host, status
from .descriptor import DescriptorError
from .proc import StepError, User, as_user, run, write_file
from .secretmanager import AccessError, Tokens

RUN_DIR = pathlib.Path("/run/devcloud")
# devcloud-boot's exit status when steps 1-11 made the host and only step 12
# (projects) failed: the entrypoint and the boot unit still start the services.
PROJECTS_FAILED = 3
STATE_DIR = pathlib.Path("/var/lib/devcloud")
IDENTITY_ENV = STATE_DIR / "identity.env"
APPLIED = STATE_DIR / "applied-commit"
ENV_PATH = pathlib.Path(services.ENV_PATH)
MANAGED_SETTINGS = pathlib.Path("/etc/claude-code/managed-settings.json")
# Where a push from a host's ~/.claude goes: nowhere, loudly.
PUSH_URL = "DISABLED--a-devcloud-host-only-receives-its-configuration"
ENV_HEADER = ("# Written by devcloud (boot step 10, reconcile, refresh-secrets): the identity of\n"
              "# boot step 1, the profile's profile.env, and secrets.toml's env targets.\n"
              "# Edits here are lost at the next reconcile.\n")


class Stop(Exception):
    """A step failed; the run ends."""


class Run:
    def __init__(self, kind):
        self.kind = kind
        self.desc = None
        self.user = None
        self.tokens = None
        self.bootstrap = None
        self.ts_secret = None
        self.profile = None
        self.commit = None
        self.secret_env = {}
        self.env_changed = False

    def load(self):
        if self.desc is None:
            self.desc = descriptor.load(allow_http=os.environ.get("DEVCLOUD_ALLOW_HTTP") == "1")
            self.user = User.from_image()
            self.tokens = Tokens(self.desc)
            proc.know_host(self.user, self.desc.seed_path if self.desc.seed_kind == "file" else None,
                           env_path=ENV_PATH)

    @property
    def claude_dir(self):
        return self.user.home / ".claude"

    def base_env(self):
        """What profile.env's references expand against: the user's login
        environment and the host's identity."""
        return self.user.env(_read_env(IDENTITY_ENV))


def _read_env(path):
    try:
        return envfile.parse(pathlib.Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _say(message):
    print(f"devcloud: {message}", flush=True)


def step(r, name, fn):
    try:
        result = fn(r)
    except (StepError, DescriptorError, secrets.ProfileError) as error:
        result = ("failed", str(error))
    except Exception as error:  # noqa: BLE001 — recorded, never raised past the step
        result = ("failed", f"{type(error).__name__}: {error}"[:300])
    state, detail = result if isinstance(result, tuple) else ("ok", result)
    detail = proc.KNOWN.scrub(detail)
    status.record(name, state, detail)
    _say(f"{name}: {state}" + (f" — {detail}" if detail else ""))
    if state == "failed":
        raise Stop(name)


# --- 1. identity -------------------------------------------------------------

def _boot_id(name):
    """A container sees its host's boot id, so it gets one of its own: stable
    for the life of its PID 1, fresh on every container start."""
    with open("/proc/sys/kernel/random/boot_id") as f:
        host_boot = f.read().strip()
    with open("/proc/1/stat") as f:
        pid1_start = f.read().rsplit(")", 1)[1].split()[19]
    digest = hashlib.sha256(f"{host_boot}\0{pid1_start}\0{name}".encode()).digest()
    return str(uuid.UUID(bytes=digest[:16], version=4))


def _write_env_file(pairs, gid):
    """/etc/devcloud/env: root's, readable by the user's group (it may hold
    secrets.toml's env values). Returns whether its content changed."""
    ledger.add(ENV_PATH)
    changed = write_file(ENV_PATH, ENV_HEADER + envfile.format(pairs), mode=0o640, dir_mode=0o755)
    os.chown(ENV_PATH, 0, gid)
    return changed


def identity(r):
    r.load()
    d = r.desc
    if d.role == "persistent" and not services.systemd_is_init():
        try:
            init = pathlib.Path("/proc/1/comm").read_text().strip()
        except OSError:
            init = "unknown"
        raise StepError(f"DEVCLOUD_ROLE=persistent needs systemd as PID 1; PID 1 here is {init}")
    for path, mode in ((STATE_DIR, 0o755), (RUN_DIR, 0o711)):
        path.mkdir(mode=mode, parents=True, exist_ok=True)
    ledger.add(descriptor.PATH)
    current = socket.gethostname()
    if d.kind == "container":
        if current != d.name:
            raise StepError(f"the container's host name is {current}, the descriptor names {d.name}: "
                            f"start it with --hostname {d.name}")
    elif current != d.name:
        if services.systemd_is_init():
            run(["hostnamectl", "set-hostname", d.name], log="identity", timeout=60)
        else:
            pathlib.Path("/etc/hostname").write_text(d.name + "\n")
            run(["hostname", d.name], log="identity", timeout=60)
    if d.kind != "container":
        _hosts_entry(d.name)
    ident = {"SESSION_MIRROR_HOST": d.name}
    if d.kind == "container":
        ident["DAEMON_BOOT_ID"] = _boot_id(d.name)
    write_file(IDENTITY_ENV, envfile.format(ident.items()), mode=0o644, dir_mode=0o755)
    merged = _read_env(ENV_PATH)
    merged.update(ident)
    _write_env_file(merged.items(), r.user.gid)
    return f"{d.name} ({d.kind}, {d.role})"


def _hosts_entry(name):
    path = pathlib.Path("/etc/hosts")
    lines = path.read_text().splitlines() if path.exists() else []
    kept = [line for line in lines if not line.startswith("127.0.1.1")]
    wanted = kept + [f"127.0.1.1\t{name}"]
    if wanted != lines:
        path.write_text("\n".join(wanted) + "\n")


# --- 2-4. seed, bootstrap secrets, tailnet ---------------------------------------

TS_TAG = "tag:devcloud"


def ts_client_attributes(d):
    """The OAuth client's node: tagged and admitted at once; ephemeral when
    the host is leased, so a VM that dies without departing still leaves the
    tailnet (the coordination server removes it 30-60 minutes after it went
    offline, and at once on logout); kept across reboots otherwise."""
    return f"?ephemeral={'true' if d.leased else 'false'}&preauthorized=true"


def seed(r):
    if r.desc.seed_kind == "file":
        ledger.add(r.desc.seed_path)
    r.tokens.activate()
    r.tokens.token()
    return "key file activated (root-private gcloud configuration)" if r.desc.seed_kind == "file" \
        else "GCE metadata server"


def _fetch_text(r, name):
    """Secret `name`'s latest value as text, one trailing newline dropped,
    known to every log from here on."""
    try:
        value = r.tokens.access(name)
    except AccessError as error:
        raise StepError(f"{name}: {error}") from None
    if value is None:
        raise StepError(f"{name} is absent from Secret Manager")
    try:
        text = value.decode("utf-8").rstrip("\n")
    except UnicodeDecodeError:
        raise StepError(f"{name} is not UTF-8 text") from None
    if not text:
        raise StepError(f"{name} is empty")
    proc.KNOWN.add(text)
    return text


def _fetch_bootstrap(r):
    r.bootstrap = _fetch_text(r, r.desc.config_token_secret)


def bootstrap_secrets(r):
    _fetch_bootstrap(r)
    names = [r.desc.config_token_secret]
    if r.desc.ts_secret:
        r.ts_secret = _fetch_text(r, r.desc.ts_secret)
        names.append(r.desc.ts_secret)
    return ", ".join(names)


def _joined():
    try:
        out = run(["tailscale", "status", "--json"], log="tailnet", capture=True, timeout=30)
        return json.loads(out).get("BackendState") == "Running"
    except (StepError, ValueError, AttributeError):
        return False


def tailnet_attach(r):
    d = r.desc
    if d.tailscale != "join":
        return "through the host's tailnet" if d.tailscale == "host" else "no tailnet"
    if services.systemd_is_init():
        run(["systemctl", "enable", "--now", "tailscaled"], log="tailnet", timeout=120)
    detail = _join(r)
    if d.inbound == "tailnet" and d.kind != "container":
        # Right after the join, so the driver's first contact over the public
        # address ends here; a connection already open stays (established).
        detail += "; " + inbound.apply()
    return detail


def _join(r):
    d = r.desc
    key = pathlib.Path(d.ts_authkey_file) if d.ts_authkey_file else None
    if _joined():
        if key:
            key.unlink(missing_ok=True)
        return "already joined"
    up = ["tailscale", "up", f"--hostname={d.name}"]
    if d.ts_secret:
        # The client secret reaches tailscale as a file's path, never in an
        # argument list another process can read.
        with _secret_file("tailscale-auth", r.ts_secret + ts_client_attributes(d)) as path:
            run(up + [f"--auth-key=file:{path}", f"--advertise-tags={TS_TAG}"], log="tailnet", timeout=180)
        return (f"joined with the OAuth client {d.ts_secret} as {TS_TAG}"
                + (", ephemeral (leased)" if d.leased else ""))
    if not key.exists():
        raise StepError(f"not joined, and no auth key at {key}")
    try:
        run(up + [f"--auth-key=file:{key}"], log="tailnet", timeout=180)
    finally:
        key.unlink(missing_ok=True)
    return "joined with the auth key file; the file is deleted"


@contextlib.contextmanager
def _secret_file(name, value, gid=None):
    """`value` in a root-owned file under /run/devcloud for the length of the
    block: readable by root alone, or also by group `gid` when given."""
    RUN_DIR.mkdir(mode=0o711, parents=True, exist_ok=True)
    path = RUN_DIR / f"{name}-{os.getpid()}"
    mode = 0o600 if gid is None else 0o440
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    try:
        if gid is not None:
            os.fchown(fd, 0, gid)
        os.fchmod(fd, mode)
        os.write(fd, value.encode())
        os.close(fd)
        yield path
    finally:
        path.unlink(missing_ok=True)


# --- 5. configuration ----------------------------------------------------------

def _token_file(r):
    """The GitHub token in a root-owned file only the user's group can read,
    for the length of the git calls."""
    return _secret_file("git-token", r.bootstrap, gid=r.user.gid)


def _git(r, *args, capture=False, helper=None):
    pre = ["git", "-C", str(r.claude_dir)]
    if helper:
        pre += ["-c", "credential.helper=", "-c", f"credential.helper={helper}",
                "-c", "credential.interactive=never"]
    return run(pre + list(args), user=r.user, env=r.user.env({"GIT_TERMINAL_PROMPT": "0"}),
               log="configuration", capture=capture, timeout=600)


def configuration(r):
    r.load()
    if r.bootstrap is None:
        _fetch_bootstrap(r)
    d = r.desc
    as_user(r.user, lambda: r.claude_dir.mkdir(mode=0o755, exist_ok=True))
    if not (r.claude_dir / ".git").is_dir():
        _git(r, "init", "-q", "-b", d.config_branch)
    remotes = _git(r, "remote", capture=True).split()
    _git(r, "remote", "set-url" if "origin" in remotes else "add", "origin", d.config_repo)
    _git(r, "remote", "set-url", "--push", "origin", PUSH_URL)
    with _token_file(r) as token:
        helper = (f"!f() {{ test \"$1\" = get || exit 0; echo username=x-access-token; "
                  f"printf 'password=%s\\n' \"$(cat {token})\"; }}; f")
        _git(r, "fetch", "--prune", "--no-tags", "origin",
             f"+refs/heads/{d.config_branch}:refs/remotes/origin/{d.config_branch}", helper=helper)
    _git(r, "checkout", "-q", "-f", "-B", d.config_branch, f"refs/remotes/origin/{d.config_branch}")
    r.commit = _git(r, "rev-parse", "HEAD", capture=True).strip()
    r.profile = profile_mod.read(r.claude_dir, r.base_env())
    return f"{r.commit[:12]} of {d.config_branch}"


def read_profile(r):
    """The profile as the clone holds it, for a run that does not fetch."""
    r.load()
    r.profile = profile_mod.read(r.claude_dir, r.base_env())


# --- 6-12 ----------------------------------------------------------------------

def tailnet_check(r):
    url = r.profile.gateway
    if not url:
        return ("skipped", "managed-settings.json names no env.ANTHROPIC_BASE_URL")
    last = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=10) as response:
                return f"the gateway answered (HTTP {response.status})"
        except urllib.error.HTTPError as error:
            return f"the gateway answered (HTTP {error.code})"
        except (urllib.error.URLError, OSError, ValueError) as error:
            last = getattr(error, "reason", error)
        if attempt < 5:
            time.sleep(5)
    raise StepError(f"the gateway in managed-settings.json does not answer ({last})")


def secrets_step(r):
    def fetch(name):
        value = r.tokens.access(name)
        if value:
            proc.KNOWN.add(value)
        return value
    out = secrets.materialize(r.profile.secrets, fetch, r.user.home, as_user=lambda fn: as_user(r.user, fn),
                              before_write=ledger.add)
    r.secret_env = out.env
    return (out.state, out.detail)


def home(r):
    u = r.user
    env = u.env({"CLOUDSDK_CORE_DISABLE_PROMPTS": "1"})
    parts = []
    if r.profile.home:
        src = r.profile.home
        files = [p for p in sorted(src.rglob("*")) if p.is_file() and not p.is_symlink()]

        def copy():
            for path in files:
                mode = 0o755 if os.access(path, os.X_OK) else 0o644
                write_file(u.home / path.relative_to(src), path.read_bytes(), mode=mode, dir_mode=0o755)
        as_user(u, copy)
        parts.append(f"{len(files)} home files")
    # The user's gcloud and gh configuration hold credentials (ADC, the
    # active account's tokens, gh's): listed whole before anything writes them.
    for config in (".config/gcloud", ".config/gh"):
        ledger.add(u.home / config)
    if r.desc.seed_kind == "file":
        key = pathlib.Path(r.desc.seed_path).read_bytes()
        adc = u.home / ".config/gcloud/application_default_credentials.json"
        as_user(u, lambda: write_file(adc, key, mode=0o600))
        run(["gcloud", "auth", "activate-service-account", f"--key-file={adc}", "--quiet"],
            user=u, env=env, log="home", timeout=120)
        parts.append("gcloud and ADC from the seed key")
    else:
        parts.append("gcloud and ADC from the metadata server")
    run(["gcloud", "config", "set", "project", r.desc.sm_project, "--quiet"], user=u, env=env, log="home",
        timeout=120)
    if (u.home / ".config/gh/hosts.yml").exists():
        run(["gh", "auth", "setup-git"], user=u, env=u.env(), log="home", timeout=60)
        parts.append("gh setup-git")
    else:
        parts.append("gh not configured (no ~/.config/gh/hosts.yml)")
    parts.append(authorized_keys(r))
    return "; ".join(parts)


AUTHORIZED_KEYS_HEADER = ("# Written by devcloud (boot step 8) from the profile's driver-keys/: the driver\n"
                          "# Macs' keys. Edits here are lost at the next reconcile.\n")


def authorized_keys(r, root_home=None):
    """Root's and the user's authorized_keys kept equal to the profile's
    driver-keys/ (Design §8.3), so a VM one Mac made is reachable from the
    other, the always-on Mac's reaper included. Without a key there, both
    are left as they are."""
    keys, skipped = r.profile.driver_keys()
    note = f" ({skipped} lines that are not keys skipped)" if skipped else ""
    if not keys:
        return "authorized_keys left as they are (no driver keys)" + note
    text = AUTHORIZED_KEYS_HEADER + "".join(key + "\n" for key in keys)
    root = pathlib.Path(root_home or pwd.getpwuid(0).pw_dir)
    write_file(root / ".ssh/authorized_keys", text, mode=0o600, dir_mode=0o700)
    as_user(r.user, lambda: write_file(r.user.home / ".ssh/authorized_keys", text, mode=0o600, dir_mode=0o700))
    return f"authorized_keys: {len(keys)} driver keys for root and {r.user.name}" + note


def apply(r):
    script = r.claude_dir / "sync/apply.py"
    if not script.is_file():
        raise StepError("sync/apply.py is absent from the configuration repository")
    run(["/usr/bin/python3", str(script)], user=r.user, env=r.user.env(), log="apply", cwd=str(r.claude_dir),
        timeout=1800)
    return "sync/apply.py ran"


# Per-host identity: the session store's host name, sminos's machine name
# and boot id. Only boot step 1 sets them; the profile is every host's.
IDENTITY_KEYS = ("SESSION_MIRROR_HOST", "DAEMON_HOST", "DAEMON_BOOT_ID")


def host_env(identity, profile_env, secret_env):
    """/etc/devcloud/env's pairs: the identity, then profile.env, then
    secrets.toml's env targets; and the identity keys the latter two tried to
    set, which are dropped (hosts would share a name or a boot id)."""
    pairs = dict(identity)
    ignored = set()
    for source in (profile_env, secret_env):
        for key, value in source.items():
            if key in IDENTITY_KEYS:
                ignored.add(key)
            else:
                pairs[key] = value
    return pairs, sorted(ignored)


def settings_and_env(r):
    p = r.profile
    copy, state, seating = _marketplace(r)
    ledger.add(MANAGED_SETTINGS)
    settings_changed = write_file(MANAGED_SETTINGS, p.host_settings(copy), mode=0o644, dir_mode=0o755)
    pairs, ignored = host_env(_read_env(IDENTITY_ENV), p.env, r.secret_env)
    r.env_changed = _write_env_file(pairs.items(), r.user.gid)
    if copy is not None:
        # The record moves after the managed declaration names the copy: the
        # engine adds a marketplace the synced settings declare only from the
        # source the settings it reads declare.
        try:
            seating += "; " + plugins.record(r.user, r.user.env(pairs))
        except StepError as error:
            # A managed declaration the user's record does not match loads none
            # of the marketplace's plugins, the guard among them: back to the
            # user tier, which keeps the guard and turns the bridge off.
            write_file(MANAGED_SETTINGS, p.host_settings(None), mode=0o644, dir_mode=0o755)
            state, seating = "missing", f"plugins in the user tier: the marketplace's record failed ({error})"
    tz = p.env.get("TZ")
    if tz:
        zone = pathlib.Path("/usr/share/zoneinfo") / tz
        if ".." in pathlib.PurePosixPath(tz).parts or not zone.is_file():
            raise StepError(f"TZ={tz} is not a zone under /usr/share/zoneinfo")
        localtime = pathlib.Path("/etc/localtime")
        if not localtime.is_symlink() or os.readlink(localtime) != str(zone):
            tmp = localtime.with_name(".localtime.devcloud")
            tmp.unlink(missing_ok=True)
            tmp.symlink_to(zone)
            os.replace(tmp, localtime)
        write_file("/etc/timezone", tz + "\n", mode=0o644)
    note = f"; the profile's {', '.join(ignored)} ignored (a per-host identity)" if ignored else ""
    return (state, f"managed settings {'updated' if settings_changed else 'unchanged'}; "
            f"{len(pairs)} variables in {ENV_PATH} ({'changed' if r.env_changed else 'unchanged'}){note}; {seating}")


def _marketplace(r):
    """The marketplace copy to seat the plugins from (Design §10), refreshed:
    (copy, state, detail). No copy: (None, "ok") when the synced settings
    declare no marketplace, (None, "missing") when the declared one could
    not be had — the guard stays active either way, the bridge off."""
    try:
        commit, note = plugins.refresh(r.claude_dir)
    except plugins.NotDeclared as error:
        return None, "ok", f"plugins in the user tier: {error}"
    except plugins.Unavailable as error:
        return None, "missing", f"plugins in the user tier: {error}"
    return (plugins.COPY, "ok",
            f"plugins seated from {plugins.COPY} at {commit[:12]}" + (f" ({note})" if note else ""))


def services_step(r):
    """`sminos` linked onto every shell's PATH, the devcloud services, then
    sminos's part — the desk's enrollment
    (§10), then the daemon — each tried even when another failed, so a
    failure in one never costs another a restart it owes (each records its
    own, to be made by a later run). Under the lifecycle lock, shared: once a
    departure has started, the services that could reopen admission stay
    stopped (§4.2's second guard), and a departure never starts between the
    read of its state and a start here. An enrollment the desk left
    undecided makes the step `deferred`, which counts as done."""
    env = _read_env(ENV_PATH)
    sminos_host.check_role(r.user, r.desc.role, env)
    parts, failures, state = [], [], "ok"
    try:
        sminos_host.link_cli(r.user)
    except OSError as error:
        failures.append(f"linking {sminos_host.LINK}: {error}")
    with lease.locked(shared=True):
        record = status.lifecycle()
        try:
            parts.append(_devcloud_services(r, record))
        except StepError as error:
            failures.append(str(error))
        if services.admission(record) != "open":
            parts.append("sminos: the departure has started; the daemon stays stopped")
        else:
            try:
                enrolled = _enroll(r, env)
                if enrolled.detail:
                    parts.append(f"sminos: {enrolled.detail}")
                if enrolled.state == "deferred":
                    state = "deferred"
            except StepError as error:
                failures.append(str(error))
            try:
                parts.append(sminos_host.converge(r.user, r.desc.role, env, r.env_changed))
            except StepError as error:
                failures.append(str(error))
    if failures:
        raise StepError("; ".join(failures))
    return (state, "; ".join(parts))


def _enroll(r, env):
    """Step 11's enrollment at the desk, its deferral kept in the status."""
    if sminos_host.CODE_FILE.exists():
        ledger.add(sminos_host.CODE_FILE)
    result = sminos_host.enroll(r.user, r.desc, env, fetch_key=lambda name: _fetch_text(r, name),
                                ledger_add=ledger.add)
    if result.state == "deferred":
        status.set_enroll_deferred(True)
    elif result.state in ("accepted", "enrolled"):
        status.set_enroll_deferred(False)
    if result.state == "enrolled":
        sminos_host.owe_restart()
    return result


def _devcloud_services(r, lifecycle=None):
    if services.systemd_is_init():
        return services.apply_systemd(r.user, r.env_changed, persistent=r.desc.role == "persistent",
                                      lifecycle=lifecycle, spot=r.desc.spot)
    names = services.desired_names(r.user)
    services.write_desired(names)
    absent = [s for s in services.service_list(r.user) if s.name not in names]
    note = "; not run: " + ", ".join(f"{s.name} ({s.argv[0]} absent)" for s in absent) if absent else ""
    pid = services.supervisor_running()
    if pid:
        return (f"{', '.join(names)} under devcloud-services (pid {pid}), which follows "
                f"{services.DESIRED} and restarts them when {ENV_PATH} changes{note}")
    return f"{', '.join(names)}: devcloud-services starts them when the boot ends{note}"


def projects(r):
    return projects_mod.set_up(r.user, r.desc, r.user.env(_read_env(ENV_PATH)))


# --- runs ----------------------------------------------------------------------

@contextlib.contextmanager
def _locked():
    RUN_DIR.mkdir(mode=0o711, parents=True, exist_ok=True)
    with open(RUN_DIR / "lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _applied():
    try:
        return APPLIED.read_text().strip()
    except FileNotFoundError:
        return None


RECONCILE = (("tailnet-check", tailnet_check), ("secrets", secrets_step), ("home", home), ("apply", apply),
             ("settings-and-env", settings_and_env), ("services", services_step))


def _run(steps, r, done=None):
    try:
        for name, fn in steps:
            step(r, name, fn)
    except Stop:
        return 1
    if done:
        done()
    return 0


def _mark_applied(r):
    write_file(APPLIED, r.commit + "\n", mode=0o644, dir_mode=0o755)


# Steps 2-4 reach only the public internet (Google's APIs, then the tailnet's
# control plane); the tailnet's own services wait for the profile (5) to name them.
BOOT = (("identity", identity), ("seed", seed), ("bootstrap-secrets", bootstrap_secrets),
        ("tailnet-attach", tailnet_attach), ("configuration", configuration)) + RECONCILE


def boot():
    with _locked():
        status.reset()
        services.mark_booted(False)
        r = Run("boot")
        code = _run(BOOT, r, done=lambda: _mark_applied(r))
        if code == 0 and _run((("projects", projects),), r):
            # The host works without a project: the failure is recorded, and
            # its own exit status lets the services start all the same.
            code = PROJECTS_FAILED
        made = code in (0, PROJECTS_FAILED)
        services.mark_booted(made)
        if made and services.systemd_is_init():
            # Step 11 left the continuous units for now: their condition is the
            # marker just written.
            try:
                services.start_gated(r.user, lifecycle=status.lifecycle())
            except StepError as error:
                status.record("services", "failed", proc.KNOWN.scrub(f"starting the services: {error}"))
                _say(f"services: failed — {proc.KNOWN.scrub(str(error))}")
                return 1
        return code


@contextlib.contextmanager
def _job(name):
    """A job's admission and the run lock: whether it may run (not once a
    departure has started: each job can restart the sminos daemon)."""
    with lease.admitted(name, say=_say) as admitted, _locked():
        yield admitted


def reconcile():
    with _job("reconcile") as admitted:
        if not admitted:
            return 0
        r = Run("reconcile")
        return _run((("configuration", configuration),) + RECONCILE, r, done=lambda: _mark_applied(r))


def pull_config():
    with _job("pull-config") as admitted:
        if not admitted:
            return 0
        r = Run("pull-config")
        if _run((("configuration", configuration),), r):
            return 1
        if r.commit == _applied():
            _say(f"configuration unchanged at {r.commit[:12]}; nothing to reconcile")
            _refresh_marketplace(r)
            return 0
        return _run(RECONCILE, r, done=lambda: _mark_applied(r))


def _refresh_marketplace(r):
    """The marketplace copy kept at its source's head between reconciles (a
    pull with no new configuration commit runs no settings step)."""
    if plugins.recorded(r.user):
        try:
            plugins.refresh(r.claude_dir)
        except plugins.Unavailable as error:
            _say(f"marketplace: {proc.KNOWN.scrub(str(error))}")


def refresh_mirrors():
    """Fetches the mirrors a persistent host keeps for its sandboxes; nothing
    on a sandbox. Exit 1 when a mirror's fetch failed (its log: projects)."""
    with _job("refresh-mirrors") as admitted:
        if not admitted:
            return 0
        r = Run("refresh-mirrors")
        try:
            r.load()
        except (StepError, DescriptorError) as error:
            _say(f"refresh-mirrors: {proc.KNOWN.scrub(str(error))}")
            return 1
        if r.desc.role != "persistent":
            return 0
        done, failed = projects_mod.refresh(r.user, r.user.env(_read_env(ENV_PATH)))
        if done or failed:
            _say(f"mirrors refreshed: {', '.join(done) or 'none'}"
                 + (f"; failed: {', '.join(failed)}" if failed else ""))
        return 1 if failed else 0


def refresh_secrets():
    with _job("refresh-secrets") as admitted:
        if not admitted:
            return 0
        r = Run("refresh-secrets")

        def secrets_from_clone(r):
            read_profile(r)
            return secrets_step(r)
        return _run((("secrets", secrets_from_clone), ("settings-and-env", settings_and_env),
                     ("services", services_step)), r)


def enroll():
    """The `devcloud-enroll` service's run (§10): nothing unless step 11's
    enrollment was deferred; then the desk asked again, and on its 0, 1 or 3
    the step finished as step 11 would, the daemon (re)started."""
    with _job("enroll") as admitted:
        if not admitted or not status.enroll_deferred():
            return 0
        r = Run("enroll")

        def finish(r):
            r.load()
            env = _read_env(ENV_PATH)
            result = _enroll(r, env)
            if result.state == "deferred":
                return ("deferred", f"sminos: {result.detail}")
            return f"sminos: {result.detail}; {sminos_host.converge(r.user, r.desc.role, env, False)}"
        return _run((("services", finish),), r)
