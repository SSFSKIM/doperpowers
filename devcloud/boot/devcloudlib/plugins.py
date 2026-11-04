"""Seating a host's plugins the way the Macs do (Design §10, the parent's
option E): to-human, sminos and doperpowers in the prepend tier, outside
devcloud's secrets guard, so the sminos bridge runs and the desk can steer a
host's sessions, with the guard active from the first one.

The engine gives a managed `prependPlugins` entry its tier only when the
plugin is read in place from a local folder its marketplace is registered
from. So the boot keeps a root-owned copy of the doperpowers marketplace at a
fixed path, `COPY`: a clone of the source the synced settings declare
(`extraKnownMarketplaces.doperpowers` in `~/.claude/settings.json`, the source
the configuration's own apply step adds the marketplace from), kept at that
source's head as the Macs' marketplace auto-update keeps theirs. Managed
settings then declare the marketplace as that directory, and the user's
record of it is moved there (`claude plugin marketplace add <COPY>`) before
any session starts: with the managed declaration and a record that still
names GitHub, a session loads no plugin of the marketplace at all, the guard
included (M1). The copy is refreshed at every boot, reconcile, secrets
refresh and configuration pull, and after the settings step's and the pull's
refresh the user's installs move to the versions it carries (`update`)."""

import json
import os
import pathlib
import re
import shutil
import time

from .proc import StepError, run as proc_run

NAME = "doperpowers"
COPY = pathlib.Path("/var/lib/devcloud/marketplaces/doperpowers")
# Outermost first, as the Macs' synced prependPlugins has them.
OUTER = ("to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers")
_CREDENTIAL = re.compile(r"^[a-z][a-z0-9+.-]*://[^/@]*@")


class Unavailable(Exception):
    """No copy to seat from; the message says why, naming no value."""


class NotDeclared(Unavailable):
    """The synced settings declare no doperpowers marketplace, and no copy exists."""


def declared_source(claude_dir):
    """(url, ref) of the doperpowers marketplace the synced settings declare,
    or None: a `github` source as its https clone URL, a `git` source's URL.
    A URL carrying a credential is refused (git authenticates otherwise)."""
    try:
        settings = json.loads((pathlib.Path(claude_dir) / "settings.json").read_text())
        source = settings["extraKnownMarketplaces"][NAME]["source"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(source, dict):
        return None
    kind = source.get("source")
    if kind == "github" and isinstance(source.get("repo"), str) and re.fullmatch(r"[\w.-]+/[\w.-]+", source["repo"]):
        url = f"https://github.com/{source['repo']}.git"
    elif kind == "git" and isinstance(source.get("url"), str) and source["url"]:
        url = source["url"]
    else:
        return None
    if _CREDENTIAL.match(url):
        raise Unavailable("the declared doperpowers marketplace URL carries a credential")
    ref = source.get("ref") if isinstance(source.get("ref"), str) and source.get("ref") else None
    return url, ref


def _git(*args, cwd=None, run=proc_run, capture=False):
    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "GIT_TERMINAL_PROMPT": "0",
           "HOME": "/root", "LANG": "C.UTF-8"}
    return run(["git", *(["-C", str(cwd)] if cwd else []), *args], env=env, log="plugins", capture=capture,
               timeout=600)


def refresh(claude_dir, copy=None, run=proc_run):
    """Brings the root-owned copy to the declared source's head; returns
    (commit, note). Without a declaration, the copy as it is; when the fetch
    fails, the copy as it is with the failure noted. Raises Unavailable when
    there is no copy to seat from."""
    copy = pathlib.Path(copy or COPY)
    present = (copy / ".git").is_dir()
    try:
        source = declared_source(claude_dir)
    except Unavailable:
        if not present:
            raise
        source, note = None, "the declared source carries a credential; the copy kept as it is"
    else:
        note = ""
    if source is None:
        if not present:
            raise NotDeclared("the synced settings declare no doperpowers marketplace (extraKnownMarketplaces)")
        note = note or "no source declared; the copy kept as it is"
        return _git("rev-parse", "HEAD", cwd=copy, run=run, capture=True).strip(), note
    url, ref = source
    try:
        if not present:
            if copy.exists():
                shutil.rmtree(copy)
            copy.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            _git("clone", "-q", "--depth", "1", "--no-tags", *(["--branch", ref] if ref else []), url, str(copy),
                 run=run)
        else:
            _git("remote", "set-url", "origin", url, cwd=copy, run=run)
            _git("fetch", "-q", "--depth", "1", "--no-tags", "origin", ref or "HEAD", cwd=copy, run=run)
            fetched = _git("rev-parse", "FETCH_HEAD", cwd=copy, run=run, capture=True).strip()
            if fetched != _git("rev-parse", "HEAD", cwd=copy, run=run, capture=True).strip():
                _git("reset", "-q", "--hard", fetched, cwd=copy, run=run)
                _git("clean", "-q", "-ffdx", cwd=copy, run=run)
    except StepError as error:
        if not (copy / ".git").is_dir():
            raise Unavailable(f"the marketplace could not be cloned ({error})") from None
        note = f"the fetch failed ({error}); the copy kept as it is"
    return _git("rev-parse", "HEAD", cwd=copy, run=run, capture=True).strip(), note


def recorded(user, copy=None):
    """Whether the user's record of the marketplace is the copy already."""
    copy = copy or COPY
    try:
        known = json.loads((user.home / ".claude/plugins/known_marketplaces.json").read_text())
        entry = known[NAME]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    source = entry.get("source") if isinstance(entry, dict) else None
    if not (isinstance(source, dict) and source.get("source") == "directory"):
        return False
    here = os.path.realpath(copy)
    return any(isinstance(p, str) and os.path.realpath(p) == here
               for p in (source.get("path"), entry.get("installLocation")))


def record(user, env, copy=None, run=proc_run):
    """Moves the user's record of the marketplace to the copy, as the user,
    once; a record already there is left alone."""
    copy = copy or COPY
    if recorded(user, copy):
        return "recorded already"
    run(["claude", "plugin", "marketplace", "add", str(copy)], user=user, env=env, log="plugins",
        cwd=str(user.home), timeout=180)
    if not recorded(user, copy):
        raise StepError("claude plugin marketplace add left the record elsewhere")
    return "recorded"


def versions(copy=None):
    """{catalog name: (version, same-marketplace dependencies)} of each
    valid plugin the copy carries in its own tree. The manifest supplies the
    version, falling back to the catalog when absent; another source (ci-kit,
    a git URL) is not the copy's to say."""
    copy = pathlib.Path(copy or COPY)
    try:
        catalog = json.loads((copy / ".claude-plugin/marketplace.json").read_text())
    except (OSError, ValueError):
        return {}
    listed = catalog.get("plugins") if isinstance(catalog, dict) else None
    if not isinstance(listed, list):
        return {}
    root, out = copy.resolve(), {}
    for entry in listed:
        if not isinstance(entry, dict):
            continue
        name, source = entry.get("name"), entry.get("source")
        if not (isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name)
                and isinstance(source, str) and source.startswith("./")):
            continue
        try:
            tree = (copy / source).resolve()
            if tree != root and root not in tree.parents:
                continue
            manifest = json.loads((tree / ".claude-plugin/plugin.json").read_text())
        except (OSError, ValueError, RuntimeError):
            continue
        if not isinstance(manifest, dict):
            continue
        version = manifest.get("version", entry.get("version"))
        deps = manifest.get("dependencies", [])
        if not (isinstance(version, str) and version.strip() and isinstance(deps, list)
                and all(isinstance(d, str) for d in deps)):
            continue
        local_deps = []
        for dependency in deps:
            dep, separator, market = dependency.partition("@")
            if not separator or market == NAME:
                local_deps.append(dep)
        out[name] = (version, local_deps)
    return out


def outdated(user, copy=None):
    """[(key, scope, installed, wanted)] for each of the user's records of a
    copy's plugin, at user or managed scope, whose version is not the copy's;
    a plugin's dependencies come before it. Project and local records belong
    to a directory and are left to the sessions there."""
    wanted = versions(copy)
    try:
        installed = json.loads((user.home / ".claude/plugins/installed_plugins.json").read_text())["plugins"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    found = {}
    for key, records in (installed.items() if isinstance(installed, dict) else ()):
        name, _, market = key.partition("@")
        if market != NAME or name not in wanted or not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, dict) and record.get("scope") in ("user", "managed") \
                    and record.get("version") != wanted[name][0]:
                found.setdefault(name, {})[record["scope"]] = (key, record["scope"], record.get("version"), wanted[name][0])
    ordered, done = [], set()
    while len(done) < len(found):
        ready = sorted(n for n in found if n not in done
                       and all(d in done or d not in found for d in wanted[n][1]))
        for name in ready or sorted(set(found) - done):   # a cycle: the rest as they come
            ordered.extend(found[name].values())
            done.add(name)
    return ordered


def update(user, env, copy=None, run=proc_run):
    """`claude plugin update` as the user for each plugin installed at a
    version the copy no longer carries, so a host's installs follow the copy
    as the Macs' follow their marketplace: the engine installs new versions
    only at a session's start, and a session that keeps running would never
    get them. Its sessions' reload mod sees installed_plugins.json change and
    reloads. The batch gets five minutes, not 180 seconds per installed
    record without a bound. Returns a note; a failed update is named, never
    raised, so it cannot undo seating or fail the pull job."""
    deadline = time.monotonic() + 300
    try:
        pending = outdated(user, copy)
    except Exception as error:  # A broken inventory must not undo seating either.
        return f"plugin inventory failed ({type(error).__name__}); updates left for the next run"
    done, failed, left = [], [], []
    for index, (key, scope, old, new) in enumerate(pending):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            left = [f"{key} ({scope})" for key, scope, _, _ in pending[index:]]
            break
        try:
            run(["claude", "plugin", "update", key, "--scope", scope], user=user, env=env, log="plugins",
                cwd=str(user.home), timeout=min(180, remaining))
            done.append(f"{key} {old} to {new}")
        except (StepError, OSError) as error:
            failed.append(f"{key} ({error})")
    if not done and not failed and not left:
        return "plugins current"
    return "; ".join(filter(None, ["updated " + ", ".join(done) if done else "",
                                   "update failed: " + ", ".join(failed) if failed else "",
                                   "left for the next run: " + ", ".join(left) if left else ""]))


def managed(settings, copy=None):
    """The managed settings with the marketplace seated from `copy`: the
    profile's own `prependPlugins` stands when it sets one (it ordered its
    plugins itself), else the Macs' three outer plugins; each of them enabled
    by policy unless the profile says otherwise; the marketplace declared as
    the copy whatever the profile says — a managed declaration the user's
    record does not match loads none of the marketplace's plugins, the guard
    among them. The security default stays unseated: `prependPlugins` is set,
    and leaves it out."""
    copy = copy or COPY
    out = dict(settings)
    prepend = out.setdefault("prependPlugins", list(OUTER))
    enabled = dict(out.get("enabledPlugins") or {})
    for plugin in prepend:
        if isinstance(plugin, str) and plugin.endswith(f"@{NAME}"):
            enabled.setdefault(plugin, True)
    if enabled:
        out["enabledPlugins"] = enabled
    markets = dict(out.get("extraKnownMarketplaces") or {})
    markets[NAME] = {"source": {"source": "directory", "path": str(copy)}}
    out["extraKnownMarketplaces"] = markets
    return out
