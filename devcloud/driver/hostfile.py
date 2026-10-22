"""A project's `devenv/host.toml` (I11, §9): which of the person's accounts,
and what type, location, disk and spot its VMs want. It may only choose among
the accounts the person's profile registers — never a provider, an
executable, a command, a credential or an address — and it is checked like
flags: an unknown key or account is exit 2 before anything is created, and
the caps apply to what it chooses.

`up --project` reads it from the session's own checkout when the working
tree is that repository (so an edit is tried before it is pushed), else from
GitHub at the requested ref (`gh api`). With several projects the first
one's file governs."""

import dataclasses
import pathlib
import re
import subprocess
import tomllib
import urllib.parse

from .errors import FAILED, USAGE, DriverError

PATH = "devenv/host.toml"
KEYS = ("account", "type", "location", "disk_gb", "spot")
_GITHUB = re.compile(r"(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)"
                     r"([^/]+)/([^/]+?)(?:\.git)?/?\Z", re.I)


@dataclasses.dataclass(frozen=True)
class HostFile:
    project: str
    source: str
    account: str | None = None
    type: str | None = None
    location: str | None = None
    disk_gb: int | None = None
    spot: bool | None = None


def _bad(project, message):
    return DriverError(USAGE, f"{PATH} of {project}: {message}")


def parse(text, profile, project, source):
    """The file's choices, each checked; exit 2 naming the key or account."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise _bad(project, f"does not parse ({error})") from None
    unknown = sorted(set(data) - set(KEYS))
    if unknown:
        raise _bad(project, f"unknown key {', '.join(unknown)} (it may set only {', '.join(KEYS)})")
    for key in ("account", "type", "location"):
        if key in data and (not isinstance(data[key], str) or not data[key]):
            raise _bad(project, f"{key} is not a name")
    if "disk_gb" in data and (not isinstance(data["disk_gb"], int) or isinstance(data["disk_gb"], bool)
                              or data["disk_gb"] <= 0):
        raise _bad(project, "disk_gb is not a positive whole number of GB")
    if "spot" in data and not isinstance(data["spot"], bool):
        raise _bad(project, "spot is not true or false")
    if "account" in data and data["account"] not in profile.accounts:
        raise _bad(project, f"names account {data['account']!r}, which the person's profile does not have "
                            f"(it has {', '.join(sorted(profile.accounts))})")
    return HostFile(project=project, source=source, **{k: data.get(k) for k in KEYS})


def _split(project):
    """(owner or None, repository, ref or None) of `owner/repo[@ref]` or `name[@ref]`."""
    spec, _, ref = project.partition("@")
    owner, _, repo = spec.rpartition("/")
    return owner or None, repo, ref or None


def _checkout(cwd):
    """(top level, owner, repository) of the git checkout at `cwd` whose
    origin is on GitHub, or None."""
    def git(*args):
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=30)
    try:
        top = git("rev-parse", "--show-toplevel")
        origin = git("config", "--get", "remote.origin.url")
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _GITHUB.match(origin.stdout.strip()) if top.returncode == 0 and origin.returncode == 0 else None
    return (pathlib.Path(top.stdout.strip()), match.group(1), match.group(2)) if match else None


def read(project, cwd, env):
    """(the file's text or None, where it was read)."""
    owner, repo, ref = _split(project)
    local = _checkout(cwd)
    if local and local[2].lower() == repo.lower() and (owner is None or local[1].lower() == owner.lower()):
        path = local[0] / PATH
        return (path.read_text() if path.is_file() else None), f"the local checkout {local[0]}"
    if owner is None:
        # A registry name: only its checkout says which repository it is.
        return None, f"no local checkout of {project}"
    api = f"repos/{owner}/{repo}/contents/{PATH}" + (f"?ref={urllib.parse.quote(ref, safe='')}" if ref else "")
    try:
        done = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.raw+json", api],
                              capture_output=True, text=True, timeout=60, env=env)
    except FileNotFoundError:
        raise DriverError(FAILED, f"reading {PATH} of {project} needs gh, which is not on PATH") from None
    except subprocess.TimeoutExpired:
        raise DriverError(FAILED, f"gh api did not answer in 60 s for {PATH} of {project}") from None
    where = f"GitHub at {ref or 'the default branch'}"
    if done.returncode == 0:
        return done.stdout, where
    if "HTTP 404" in done.stderr:
        return None, where
    reason = (done.stderr.strip().splitlines() or [f"exit {done.returncode}"])[-1]
    raise DriverError(FAILED, f"could not read {PATH} of {project} from GitHub ({reason})")


def governing(ctx, projects):
    """The first project's file, parsed (None without one); the others' are
    named and ignored (§9)."""
    if not projects:
        return None
    text, source = ctx.host_file(projects[0])
    wanted = parse(text, ctx.profile, projects[0], source) if text is not None else None
    for project in projects[1:]:
        try:
            other = ctx.host_file(project)[0]
        except DriverError as error:
            ctx.warn(f"devcloud vm up: {error} (ignored: the first project's file governs)")
            continue
        if other is not None:
            ctx.say(f"host.toml of {project} is ignored: the first project's governs")
    return wanted
