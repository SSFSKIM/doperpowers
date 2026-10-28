"""The lease on a host (Design §4.1): the lifecycle lock, `devcloud lease set`,
the lease service's run, the creator's warning, and the scan for unpushed
work it names.

The descriptor's `DEVCLOUD_EXPIRES` is the lease's authority. The lifecycle
lock, `/run/devcloud/lifecycle.lock`, serializes every lease write, the lease
service's decision, and the departure and release (each of which re-reads the
lease under it); the periodic jobs take it shared, and exit at once while the
departure has started. The lease service never departs in-process: it starts
the departure (the release, on an adopted machine) as a transient unit, since
both stop devcloud's services, the lease service's own unit among them."""

import contextlib
import datetime
import fcntl
import json
import os
import pathlib
import subprocess
import sys
import time

from . import descriptor, idle, nodekind, notices, proc, status
from .proc import StepError

LOCK = pathlib.Path("/run/devcloud/lifecycle.lock")
# Which lease value the warning went out for: one warning per value, so an
# extension re-arms it.
STATE = pathlib.Path("/var/lib/devcloud/lease.json")
ENV_PATH = "/etc/devcloud/env"
DEVCLOUD = "/usr/local/bin/devcloud"
WARN_BEFORE = 30 * 60
PROJECTS_ROOT = "Developer/GitHub"
# The transient units the lease service starts (I16).
DEPART_UNIT, RELEASE_UNIT = "devcloud-depart", "devcloud-release"


@contextlib.contextmanager
def locked(shared=False, path=None, timeout=None):
    """The lifecycle lock, exclusive or shared. With `timeout` (seconds) a
    lock not had by then raises TimeoutError."""
    path = pathlib.Path(path or LOCK)
    path.parent.mkdir(mode=0o711, parents=True, exist_ok=True)
    with open(path, "a") as f:
        mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
        if timeout is None:
            fcntl.flock(f, mode)
        else:
            end = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(f, mode | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= end:
                        raise TimeoutError("the lifecycle lock is held") from None
                    time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


@contextlib.contextmanager
def admitted(job, say=print, lock_path=None, status_path=None):
    """A periodic job's (or the enroll job's) admission: the lifecycle lock
    held shared for the job's run, and whether the job may run — not once
    the departure has started, since each of them can restart the sminos
    daemon and so reopen admission on a departing host."""
    with locked(shared=True, path=lock_path):
        if status.departure_started(**({"path": status_path} if status_path else {})):
            say(f"devcloud {job}: the departure has started; nothing to do")
            yield False
        else:
            yield True


def iso(unix):
    return datetime.datetime.fromtimestamp(unix, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


# --- lease set -----------------------------------------------------------------

def _stderr(message):
    print(message, file=sys.stderr, flush=True)


OVER_CAP = 4    # `lease set --cap`: past the cap and later than the lease in force


def parse_set(args):
    """`lease set`'s arguments: `<unix> [--cap <unix>]` → (value, cap), or
    `keep` → (None, None) (no lease: the driver passes it only with the
    person's yes, so it takes no cap); None when they are not that."""
    if args == ["keep"]:
        return None, None
    if len(args) not in (1, 3) or not all(a.isdigit() for a in args[::2]):
        return None
    if len(args) == 3 and args[1] != "--cap":
        return None
    return int(args[0]), (int(args[2]) if len(args) == 3 else None)


def set_lease(value, cap=None, desc_path=descriptor.PATH, lock_path=None, status_path=None, out=_stderr,
              allow_http=False, kind_path=None, start=None):
    """`devcloud lease set <unix|keep> [--cap <unix>]`: rewrites
    DEVCLOUD_EXPIRES (`keep`, None: removes it) under the lock and prints the
    lease read back under it, `keep` for none. When the tailnet node's kind
    no longer follows the lease, it starts the rejoin as a transient unit,
    which waits for this lock, and first prints `rejoin <kind>` (§4.1). Exit 3 once the
    departure has started (its sessions are already ended); 1 when the
    descriptor cannot be read or would not parse. `--cap` is the driver's
    lifetime cap for a request the person did not confirm: past it, the
    lease may only be shortened, so a value past the cap and later than the
    lease in force (a host with no lease has none to shorten) is refused
    with exit 4, decided under the same lock as the write."""
    status_kw = {"path": status_path} if status_path else {}
    with locked(path=lock_path):
        if status.departure_started(**status_kw):
            out(f"devcloud lease set: the departure has started ({status.lifecycle(**status_kw)['state']}); "
                "the lease stays as it is")
            return 3
        path = pathlib.Path(desc_path)
        try:
            text = path.read_text()
            current = descriptor.parse(text, allow_http=allow_http).expires
            new = descriptor.set_expires(text, value)
            descriptor.parse(new, allow_http=allow_http)
        except (OSError, descriptor.DescriptorError) as error:
            out(f"devcloud lease set: {error}")
            return 1
        if cap is not None and value is not None and value > cap and (current is None or value > current):
            in_force = iso(current) if current is not None else "none (keep)"
            out(f"devcloud lease set: {iso(value)} is past the lifetime cap ({iso(cap)}) and later than the lease "
                f"in force ({in_force}); the lease stays as it is")
            return OVER_CAP
        mode = path.stat().st_mode & 0o7777
        proc.write_file(path, new, mode=mode, dir_mode=0o755)
        d = descriptor.load(path, allow_http=allow_http)
        if nodekind.behind(d, kind_path):
            # Said before the unit runs, so a reader never takes an earlier rejoin's end for this one's.
            was = nodekind.recorded(kind_path)
            nodekind.record(was.get("ephemeral"), nodekind.wanted(d), nodekind.REJOINING,
                            f"the lease changed; {nodekind.UNIT} rejoins as {nodekind.name(nodekind.wanted(d))}",
                            name=was.get("name"), path=kind_path)
            try:
                (start or start_transient)(nodekind.UNIT, [DEVCLOUD, "rejoin"], what="so the tailnet node follows its lease")
            except StepError as error:
                out(f"devcloud lease set: the rejoin did not start ({error}); the lease service starts it")
            print(f"rejoin {nodekind.name(nodekind.wanted(d))}", flush=True)
        print(d.expires if d.leased else "keep", flush=True)
        return 0


# --- the lease service -----------------------------------------------------------

def _read_state(path):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _write_state(data, path):
    proc.write_file(path, json.dumps(data) + "\n", mode=0o644, dir_mode=0o755)


def unit_active(unit, run=subprocess.run):
    result = run(["systemctl", "is-active", f"{unit}.service"], capture_output=True, text=True, timeout=30)
    return result.stdout.strip() in ("active", "activating", "deactivating", "reloading")


# The boot's stand-in switches (its tests'), passed to the transient unit, which
# gets the manager's environment rather than the lease service's.
PASSED_ENV = ("DEVCLOUD_ALLOW_HTTP", "DEVCLOUD_SM_ENDPOINT", "GCE_METADATA_HOST")


def start_transient(unit, argv, run=proc.run, environ=os.environ, what="at the lease end"):
    """The departure, the release or the rejoin as its own transient unit,
    collected when it ends: stopping devcloud's services stops the lease
    service, not it, and a rejoin cuts the connection that asked for it."""
    passed = [f"--setenv={name}={environ[name]}" for name in PASSED_ENV if environ.get(name)]
    run(["systemd-run", "--unit", unit, "--collect", "--description",
         f"devcloud: {argv[-1]} {what} (Design §4)", *passed, *argv], log="lease", timeout=60)


def tick(user, desc_path=descriptor.PATH, lock_path=None, status_path=None, state_path=None, now=time.time,
         active=unit_active, start=start_transient, warn=None, allow_http=False, say=_stderr, kind_path=None):
    """Queue any tailnet recovery before deciding departure. Activity probes,
    checkout scans and delivery run outside the lifecycle lock. A separate
    nonblocking lock serializes sends; delivery markers advance only after
    each notice completes, so an interrupted or failed send stays retryable.
    """
    status_kw = {"path": status_path} if status_path else {}
    state_path = state_path or STATE

    def departure_due(d):
        # Called under the lock. Sample time after the potentially blocking
        # unit query, never before activity checks or notice delivery.
        record = status.lifecycle(**status_kw)
        if record and record.get("state") == "departed":
            return True, now()
        unit, op = (RELEASE_UNIT, "release") if d.adopted else (DEPART_UNIT, "depart")
        if d.leased and active(unit):
            say(f"devcloud lease: {unit} is already under way")
            return True, now()
        current = now()
        if d.leased and current >= d.expires:
            start(unit, [DEVCLOUD, op])
            say(f"devcloud lease: the lease ended at {iso(d.expires)}; {unit} started")
            return True, current
        return False, current

    def load():
        try:
            return descriptor.load(desc_path, allow_http=allow_http)
        except descriptor.DescriptorError as error:
            say(f"devcloud lease: {error}")
            return None

    with locked(path=lock_path):
        d = load()
        if d is None:
            return 1
        proc.know_host(user, d.seed_path if d.seed_kind == "file" else None, env_path=ENV_PATH)
        if nodekind.behind(d, kind_path) and not status.departure_started(**status_kw) \
                and not active(nodekind.UNIT):
            try:
                start(nodekind.UNIT, [DEVCLOUD, "rejoin"], what="so the tailnet node follows its lease")
                say(f"devcloud lease: the tailnet node is not {nodekind.name(nodekind.wanted(d))}; "
                    f"{nodekind.UNIT} started")
            except StepError as error:
                say(f"devcloud lease: {nodekind.UNIT} did not start ({error})")
        if departure_due(d)[0]:
            return 0
        observe = not status.departure_started(**status_kw)

    observation = None
    if observe:
        try:
            observation = idle.observe(user, d, now=now)
        except (OSError, ValueError, IndexError, StepError) as error:
            say(f"devcloud lease: idle check failed ({error}); will retry")

    # Acquire this before deciding which notices are due: otherwise a sender
    # that finished between our decision and acquisition would be repeated.
    # Never wait for it, and never hold the lifecycle lock while delivering.
    with contextlib.ExitStack() as sending_lock:
        sending = True
        try:
            sending_lock.enter_context(locked(path=pathlib.Path(lock_path or LOCK).with_name("notices.lock"),
                                              timeout=0))
        except TimeoutError:
            sending = False
        with locked(path=lock_path):
            d = load()
            if d is None:
                return 1
            done, current = departure_due(d)
            if done:
                return 0
            pending = None
            if not status.departure_started(**status_kw):
                try:
                    pending = idle.check(d, observation, now=lambda: current)
                except (OSError, ValueError, IndexError, StepError) as error:
                    say(f"devcloud lease: idle check failed ({error}); will retry")
            warning = d.leased and current >= d.expires - WARN_BEFORE and (
                _read_state(state_path).get("warned_for") != d.expires)

        try:
            if sending and warning:
                try:
                    (warn or (lambda desc: warn_creator(user, desc, say=say)))(d)
                    with locked(path=lock_path):
                        # A release may have removed the host while delivery ran.
                        if pathlib.Path(desc_path).exists():
                            _write_state({**_read_state(state_path), "warned_for": d.expires}, state_path)
                except Exception as error:  # either notice can fail without suppressing the other
                    say(f"devcloud lease: warning failed ({error}); will retry")
            if sending and pending is not None:
                try:
                    idle.send(user, d, pending, say=say)
                    with locked(path=lock_path):
                        idle.delivered(pending, now=now)
                except Exception as error:
                    say(f"devcloud lease: idle notice failed ({error}); will retry")
        finally:
            # A lease can be added or shortened while a send runs. Always
            # reload its authority; the pre-delivery descriptor is stale.
            with locked(path=lock_path):
                if not status.departure_started(**status_kw):
                    fresh = load()
                    if fresh is not None:
                        departure_due(fresh)
    return 0


# --- the warning -----------------------------------------------------------------

def warning_text(name, expires, found):
    unpushed = ", ".join(f"{repo} ({what})" for repo, what in found) if found else "none"
    return f"devcloud on {name}: lease ends at {iso(expires)}; unpushed: {unpushed}"


def warn_creator(user, d, call=proc.call, say=print, scan=None):
    """The lease end and unpushed work, through the idle notice's delivery."""
    found = (scan or (lambda: unpushed(user)))()
    notices.deliver(user, d, warning_text(d.name, d.expires, found), call=call, say=say)


# --- unpushed work ----------------------------------------------------------------

def _git(run, user, *args):
    return run(["git", *args], user=user, env=user.env({"GIT_TERMINAL_PROMPT": "0"}) if user else None,
               capture=True, timeout=60)


def _worktrees(run, user, checkout):
    try:
        listing = _git(run, user, "-C", str(checkout), "worktree", "list", "--porcelain")
    except StepError:
        return [checkout]
    paths = [pathlib.Path(line[len("worktree "):]) for line in listing.splitlines() if line.startswith("worktree ")]
    return [p for p in paths if p.is_dir()] or [checkout]


def _what(run, user, tree, nested=()):
    """What `tree` holds that no remote has; `nested`, the checkout's linked
    worktrees inside it, which its status lists as untracked and are scanned
    on their own."""
    what = []
    try:
        listing = _git(run, user, "-C", str(tree), "status", "--porcelain", "--untracked-files=all")
        skip = {str(p.relative_to(tree)).rstrip("/") + "/" for p in nested if p != tree and _inside(p, tree)}
        if any(line[3:] not in skip for line in listing.splitlines() if line.strip()):
            what.append("uncommitted changes")
    except StepError:
        what.append("unreadable")
        return what
    try:
        ahead = int(_git(run, user, "-C", str(tree), "rev-list", "--count", "HEAD", "--not", "--remotes").strip())
    except (StepError, ValueError):
        ahead = 0       # no commit yet: its files count as uncommitted
    if ahead:
        what.insert(0, f"{ahead} unpushed commit{'s' if ahead != 1 else ''}")
    return what


def _inside(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def unpushed(user, root=None, run=proc.run):
    """Each git checkout under ~/Developer/GitHub, and each of its worktrees,
    holding commits on no remote or uncommitted changes: [(name, what)],
    `name` relative to the root. Read as the user."""
    root = pathlib.Path(root or user.home / PROJECTS_ROOT)
    run_as = None if user is None or os.geteuid() != 0 else user
    found = []
    if not root.is_dir():
        return found
    for checkout in sorted(root.iterdir()):
        if not (checkout / ".git").exists():
            continue
        trees = _worktrees(run, run_as, checkout)
        for tree in trees:
            what = _what(run, run_as, tree, nested=trees)
            if what:
                try:
                    name = str(tree.resolve().relative_to(root.resolve()))
                except ValueError:
                    name = str(tree)
                found.append((name, ", ".join(what)))
    return found
