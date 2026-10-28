"""Boot step 12 (Design §7): each DEVCLOUD_PROJECTS entry set up by the
person's `devenv` runner, run as the user with the host's environment; and the
mirror cache sandboxes clone from. Where systemd is init, the user's manager
is started first and every entry gets its bus, since a project's setup may
install a user unit (MAWS's mawsd) and `systemctl --user` reaches no manager
without it.

An entry `<name>` runs `devenv up <name>` against the registry; `<owner>/<repo>`
runs `devenv up <repo> --url https://github.com/<owner>/<repo>.git`, which
writes a registry entry when there is none; `@<ref>` on either is passed as
`--ref`, a one-run override of the root repository's ref.

A persistent host keeps a bare mirror of each of its projects' GitHub
repositories at <mirrors>/<owner>/<repo>.git, made at boot and refreshed by the
refresh-mirrors job. A sandbox's descriptor names where its host's mirrors are
mounted (DEVCLOUD_MIRROR_DIR); `devenv` borrows objects from them when it
clones (DEVENV_MIRROR_DIR), so a checkout takes seconds."""

import json
import os
import pathlib
import re

from .proc import StepError, as_user, run, start_user_manager

MIRRORS = pathlib.Path("/srv/devcloud/mirrors")
# devenv's own limit on setup.sh is 30 minutes; a clone and a mirror come on top.
PROJECT_TIMEOUT = 2 * 3600
_PART = r"[A-Za-z0-9_-][A-Za-z0-9._-]*"
_GITHUB = re.compile(rf"https://github\.com/({_PART})/({_PART}?)(?:\.git)?/?")


def devenv_args(entry):
    """A DEVCLOUD_PROJECTS entry as (project name, `devenv up` arguments)."""
    spec, _, ref = entry.partition("@")
    if "/" in spec:
        owner, repo = spec.split("/", 1)
        args = [repo, "--url", f"https://github.com/{owner}/{repo}.git"]
    else:
        repo, args = spec, [spec]
    return repo, args + (["--ref", ref] if ref else [])


def mirror_of(url, mirrors=MIRRORS):
    """Where the mirror of a GitHub repository lives; None for any other URL."""
    match = _GITHUB.fullmatch(url)
    if not match or match.group(2) in ("", ".git"):
        return None
    return mirrors / match.group(1) / f"{match.group(2)}.git"


def _git(user, env, *args, timeout=1800):
    run(["git", *args], user=user, env=dict(env, GIT_TERMINAL_PROMPT="0"), log="projects", timeout=timeout)


def _ensure_mirrors_dir(user, mirrors):
    if os.geteuid() == 0:
        mirrors.mkdir(mode=0o755, parents=True, exist_ok=True)
        os.chown(mirrors, user.uid, user.gid)
    else:
        as_user(user, lambda: mirrors.mkdir(parents=True, exist_ok=True))


def _keep_mirrors(user, env, devenv, name, mirrors):
    """Makes or refreshes the mirror of each GitHub repository of project
    `name` (as `devenv show` lists them). A new mirror borrows the checkout's
    objects and then copies them (--dissociate), so it depends on nothing.
    Returns the mirrors' <owner>/<repo> names."""
    shown = json.loads(run([str(devenv), "show", name], user=user, env=env, log="projects", capture=True,
                           timeout=120))
    kept = []
    for repo in shown.get("repos", []):
        path = mirror_of(repo.get("url", ""), mirrors)
        if path is None:
            continue
        label = f"{path.parent.name}/{path.name[:-4]}"
        _ensure_mirrors_dir(user, mirrors)
        try:
            if (path / "HEAD").is_file():
                _git(user, env, "-C", str(path), "fetch", "--prune", "--quiet")
            else:
                borrow = ["--reference-if-able", repo["path"], "--dissociate"] if repo.get("path") else []
                _git(user, env, "clone", "--mirror", "--quiet", *borrow, repo["url"], str(path))
        except StepError as error:
            raise StepError(f"mirror of {label} failed ({error})") from None
        kept.append(label)
    return kept


def set_up(user, desc, env, mirrors=MIRRORS, user_manager=False):
    """Runs `devenv up` for every entry, then (on a persistent host) keeps its
    mirrors; with `user_manager` (systemd is init), the user's manager is
    started first. Every entry is tried; the step fails when any failed.
    Returns (state, detail)."""
    if not desc.projects:
        return ("skipped", "no projects named")
    devenv = user.home / ".local/bin/devenv"
    if not os.access(devenv, os.X_OK):
        raise StepError(f"{devenv} is absent (the configuration's sync/apply.py links it)")
    env = dict(env)
    if desc.mirror_dir:
        env["DEVENV_MIRROR_DIR"] = desc.mirror_dir
    if user_manager:
        env = start_user_manager(user, env, log="projects")
    parts, mirrored, failed = [], [], False
    for entry in desc.projects:
        name, args = devenv_args(entry)
        try:
            run([str(devenv), "up", *args], user=user, env=env, log="projects", cwd=str(user.home),
                timeout=PROJECT_TIMEOUT)
            if desc.role == "persistent":
                mirrored += _keep_mirrors(user, env, devenv, name, mirrors)
            parts.append(f"{entry} ok")
        except StepError as error:
            failed = True
            parts.append(f"{entry} failed ({error})")
    if mirrored:
        parts.append("mirrors: " + ", ".join(dict.fromkeys(mirrored)))
    return ("failed" if failed else "ok", "; ".join(parts))


def refresh(user, env, mirrors=MIRRORS):
    """Fetches every mirror under `mirrors`. Returns (refreshed, failed), each
    a list of <owner>/<repo> names."""
    done, failed = [], []
    for path in sorted(mirrors.glob("*/*.git")):
        if not (path / "HEAD").is_file():
            continue
        label = f"{path.parent.name}/{path.name[:-4]}"
        try:
            _git(user, env, "-C", str(path), "fetch", "--prune", "--quiet")
            done.append(label)
        except StepError:
            failed.append(label)
    return done, failed
