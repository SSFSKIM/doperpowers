"""The boot steps (Design §4) and the runs made of them: a boot (1-12), a
reconcile (5-11), the config pull job (5, then 6-11 when the commit moved),
the secrets refresh (7, 10, 11) and the mirror refresh (no step of its own).
Each step is recorded in the status file; a failed step stops the run, and the
next run retries from its top. Runs hold one lock, so a job never interleaves
with a boot."""

import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import socket
import time
import urllib.error
import urllib.request
import uuid

from . import descriptor, envfile, proc, profile as profile_mod, projects as projects_mod, redact, secrets, \
    services, status
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
        self.profile = None
        self.commit = None
        self.secret_env = {}
        self.env_changed = False

    def load(self):
        if self.desc is None:
            self.desc = descriptor.load(allow_http=os.environ.get("DEVCLOUD_ALLOW_HTTP") == "1")
            self.user = User.from_image()
            self.tokens = Tokens(self.desc)
            proc.KNOWN.update(redact.host_values(self.user, env_path=ENV_PATH))
            if self.desc.seed_kind == "file":
                _know_seed(self.desc.seed_path)

    @property
    def claude_dir(self):
        return self.user.home / ".claude"

    def base_env(self):
        """What profile.env's references expand against: the user's login
        environment and the host's identity."""
        return self.user.env(_read_env(IDENTITY_ENV))


def _know_seed(path):
    """The seed key's secret fields, so no log can hold them."""
    try:
        key = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return
    if isinstance(key, dict):
        proc.KNOWN.update(str(key[f]) for f in ("private_key", "private_key_id") if key.get(f))
        if isinstance(key.get("private_key"), str):
            proc.KNOWN.update(line for line in key["private_key"].splitlines() if len(line) >= 40)


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


# --- 2-4. tailnet, seed, bootstrap secret --------------------------------------

def tailnet_attach(r):
    d = r.desc
    if d.tailscale != "join":
        return "through the host's tailnet" if d.tailscale == "host" else "no tailnet"
    if services.systemd_is_init():
        run(["systemctl", "enable", "--now", "tailscaled"], log="tailnet", timeout=120)
    key = pathlib.Path(d.ts_authkey_file)
    if key.exists():
        try:
            run(["tailscale", "up", f"--auth-key=file:{key}", f"--hostname={d.name}"], log="tailnet", timeout=180)
        finally:
            key.unlink(missing_ok=True)
        return "joined; the auth key file is deleted"
    try:
        out = run(["tailscale", "status", "--json"], log="tailnet", capture=True, timeout=30)
    except StepError:
        out = ""
    if '"BackendState": "Running"' in out or '"BackendState":"Running"' in out:
        return "already joined"
    raise StepError(f"not joined, and no auth key at {key}")


def seed(r):
    r.tokens.activate()
    r.tokens.token()
    return "key file activated (root-private gcloud configuration)" if r.desc.seed_kind == "file" \
        else "GCE metadata server"


def _fetch_bootstrap(r):
    name = r.desc.config_token_secret
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
    r.bootstrap = text


def bootstrap_secret(r):
    _fetch_bootstrap(r)
    return r.desc.config_token_secret


# --- 5. configuration ----------------------------------------------------------

@contextlib.contextmanager
def _token_file(r):
    """The GitHub token in a root-owned file only the user's group can read,
    for the length of the git calls."""
    RUN_DIR.mkdir(mode=0o711, parents=True, exist_ok=True)
    path = RUN_DIR / f"git-token-{os.getpid()}"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o440)
    try:
        os.fchown(fd, 0, r.user.gid)
        os.fchmod(fd, 0o440)
        os.write(fd, r.bootstrap.encode())
        os.close(fd)
        yield path
    finally:
        path.unlink(missing_ok=True)


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
    out = secrets.materialize(r.profile.secrets, fetch, r.user.home, as_user=lambda fn: as_user(r.user, fn))
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
    return "; ".join(parts)


def apply(r):
    script = r.claude_dir / "sync/apply.py"
    if not script.is_file():
        raise StepError("sync/apply.py is absent from the configuration repository")
    run(["/usr/bin/python3", str(script)], user=r.user, env=r.user.env(), log="apply", cwd=str(r.claude_dir),
        timeout=1800)
    return "sync/apply.py ran"


def settings_and_env(r):
    p = r.profile
    settings_changed = write_file(MANAGED_SETTINGS, p.managed_settings, mode=0o644, dir_mode=0o755)
    pairs = dict(_read_env(IDENTITY_ENV))
    pairs.update(p.env)
    pairs.update(r.secret_env)
    r.env_changed = _write_env_file(pairs.items(), r.user.gid)
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
    return (f"managed settings {'updated' if settings_changed else 'unchanged'}; "
            f"{len(pairs)} variables in {ENV_PATH} ({'changed' if r.env_changed else 'unchanged'})")


def services_step(r):
    if services.systemd_is_init():
        return services.apply_systemd(r.user, r.env_changed)
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


def boot():
    with _locked():
        status.reset()
        r = Run("boot")
        steps = (("identity", identity), ("tailnet-attach", tailnet_attach), ("seed", seed),
                 ("bootstrap-secret", bootstrap_secret), ("configuration", configuration),
                 RECONCILE[0], RECONCILE[1], RECONCILE[2], RECONCILE[3], RECONCILE[4], RECONCILE[5])
        code = _run(steps, r, done=lambda: _mark_applied(r))
        if code == 0 and _run((("projects", projects),), r):
            # The host works without a project: the failure is recorded, and
            # its own exit status lets the services start all the same.
            return PROJECTS_FAILED
        return code


def reconcile():
    with _locked():
        r = Run("reconcile")
        return _run((("configuration", configuration),) + RECONCILE, r, done=lambda: _mark_applied(r))


def pull_config():
    with _locked():
        r = Run("pull-config")
        if _run((("configuration", configuration),), r):
            return 1
        if r.commit == _applied():
            _say(f"configuration unchanged at {r.commit[:12]}; nothing to reconcile")
            return 0
        return _run(RECONCILE, r, done=lambda: _mark_applied(r))


def refresh_mirrors():
    """Fetches the mirrors a persistent host keeps for its sandboxes; nothing
    on a sandbox. Exit 1 when a mirror's fetch failed (its log: projects)."""
    with _locked():
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
    with _locked():
        r = Run("refresh-secrets")

        def secrets_from_clone(r):
            read_profile(r)
            return secrets_step(r)
        return _run((("secrets", secrets_from_clone), ("settings-and-env", settings_and_env),
                     ("services", services_step)), r)
