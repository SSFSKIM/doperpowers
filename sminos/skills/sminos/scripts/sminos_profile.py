#!/usr/bin/env python3
"""sminos_profile — `sminos daemon profile [--seconds S] [--of uplink|run]`:
the running uplink (the default) or `daemon run` profiles itself for S
seconds (default 20) and the verb prints where its time went: what has the
most time of its own, the file calls' counts, the calls a second and the
process's CPU over the window. A live daemon cannot be profiled from outside
at the Python level on the owner's Macs (`sample` sees native frames,
`fs_usage` and py-spy want privilege), so the process does it.

The request rides the nudge both loops already watch (sminos.nudge_daemon):
the verb creates `daemon/profile-<of>.request` and nudges, and a loop that
sees a new nudge opens its own request file once (`Watch.look`, `noticed`).
With no nudge nothing here is read, stated or timed. The request is the
verb's by its id: created whole and only where none waits (one younger than
STALE is another profile being asked for, and the verb refuses), taken once
the file no longer holds that id, and withdrawn only while it still does, so
two verbs never overwrite or withdraw each other's. A process on older code
takes no request: the nudge gives it one tick, and the verb, which waits
TAKE_WITHIN for the file to be taken, withdraws it and says so. The window
begins after the pass the nudge brought (`after_pass`), so the profile is of
the loop as it runs, not of the scan a nudge asks for, and ends on a timer
thread of its own: on Python 3.12 and later cProfile, built on
sys.monitoring, sees every thread of the process and can be stopped from
any of them. Call counts are exact; own time is approximate while threads
overlap, since one profiler stack serves every thread and a frame's time
can land on another thread's frame, and caller edges across threads do not
hold. Before 3.12 the request is refused, since a profile would see one
thread alone. Nothing here raises into a loop: a failure is a refusal,
written if it can be, else a line in daemon.log, and a window whose start
fails is rolled back.

What it writes, under `daemon/`, mode 0600: `profile-<of>-<id>.prof`, the
pstats dump (marshal of {(file, line, function): counts and times}: names
and counts, never an argument or a file's contents; `python3 -m pstats`
reads it), then `profile-<of>-<id>.json`, the window: pid, Python, its wall
bounds, the process's CPU over it (getrusage, every thread, the profiler's
own cost included) — or `refused` with why. The newest KEEP of each are kept.
"""

import json
import marshal
import os
import re
import resource
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402

TARGETS = ("uplink", "run")
NAMES = {"uplink": "the uplink", "run": "daemon run"}
MAX_SECONDS = 600
TAKE_WITHIN = 20.0      # how long the verb waits for the process to take its request
RENUDGE_AT = (5.0, 10.0)   # the verb nudges again then: a nudge an uplink's own nudge swallowed
STALE = 120.0           # a request older than this is withdrawn by whoever finds it
RESULT_GRACE = 30.0     # beyond its seconds, for the pass before the window and the dump after
KEEP = 5
ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{8}")
# The file calls the table always counts, by cProfile's name for each.
FILE_CALLS = (("posix.stat", "<built-in method posix.stat>"), ("posix.lstat", "<built-in method posix.lstat>"),
              ("open", "<built-in method _io.open>"), ("os.open", "<built-in method posix.open>"),
              ("listdir", "<built-in method posix.listdir>"), ("scandir", "<built-in method posix.scandir>"))
# The other file calls, counted when made.
FILE_EXTRA = re.compile(r"<built-in method (posix\.(?:fstat|access|readlink|utime|rename|replace|unlink|mkdir|rmdir|"
                        r"chmod|truncate|fsync))>")
# A function whose own time is a wait, left out of the table's own time: a
# blocking builtin, or the standard library's Python around one (on 3.12 one
# profiler stack serves every thread, so a blocked frame's wall time lands
# in whatever frame is on it when it wakes).
WAITS = re.compile(r"acquire|select|poll|sleep|recv|accept|'wait'|\.wait>|connect|sendall|send'|readinto|"
                   r"_thread\.lock|epoll|kqueue|waitpid|read'")
STDLIB_WAITS = re.compile(r"(threading|queue|selectors|socket|subprocess|socketserver)\.py")
STDLIB_WAIT_NAMES = {"wait", "wait_for", "get", "put", "join", "select", "_wait_for_tstate_lock", "communicate",
                     "readline", "recv_into", "serve_forever", "_try_wait", "accept"}


def is_wait(key):
    fn, _, name = key
    if fn == "~":
        return bool(WAITS.search(name))
    return name in STDLIB_WAIT_NAMES and bool(STDLIB_WAITS.fullmatch(os.path.basename(fn)))


def daemon_dir():
    return os.path.join(sminos.root(), "daemon")


def request_path(of):
    return os.path.join(daemon_dir(), "profile-%s.request" % of)


def result_path(of, rid, ext):
    return os.path.join(daemon_dir(), "profile-%s-%s%s" % (of, rid, ext))


def new_request(of, seconds):
    rid = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    return {"v": 1, "id": rid, "of": of, "seconds": seconds, "at": time.time(), "by": os.getpid()}


# ------------------------------------------------------------- in the profiled process

_STATE = {"pending": None, "running": None}   # (of, request) taken; the running window's end
_LOCK = threading.Lock()


def _reset():
    """Tests: forget a pending request (a running window ends on its own)."""
    _STATE["pending"] = None


def take(of):
    """The request waiting for `of`, taken (its file removed), or None: none
    there, one the verb withdrew first, a stale or malformed one (removed).
    Called only once a new nudge was seen."""
    path = request_path(of)
    try:
        with open(path) as f:
            req = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        req = None
    try:
        os.unlink(path)
    except OSError:
        return None   # withdrawn as it was read: the verb says it was not taken
    if not isinstance(req, dict) or not isinstance(req.get("id"), str) or not ID.fullmatch(req["id"]):
        return None
    seconds, at = req.get("seconds"), req.get("at")
    if type(seconds) not in (int, float) or not 0 < seconds <= MAX_SECONDS:
        return None
    if type(at) not in (int, float) or abs(time.time() - at) > STALE:
        return None
    return req


def _logged(line):
    try:
        sminos.daemon_log(line)
    except Exception:  # noqa: BLE001 — a profile never stops the loop, daemon.log unwritable included
        pass


def noticed(of):
    """A new nudge was seen by `of`'s loop: its request, if one waits, taken
    to begin after the pass in hand."""
    try:
        req = take(of)
    except Exception as e:  # noqa: BLE001 — a profile never stops the loop
        _logged("profile request of %s (pid %d) not read: %r" % (NAMES[of], os.getpid(), e))
        return
    if req is not None:
        _STATE["pending"] = (of, req)


def after_pass():
    """The end of a loop's pass: a window taken during it begins. With none
    taken, one look at memory."""
    if _STATE["pending"] is None:
        return
    of, req = _STATE["pending"]
    _STATE["pending"] = None
    try:
        _begin(of, req)
    except Exception as e:  # noqa: BLE001 — a profile never stops the loop
        _refuse(of, req, "the profile could not begin (%r)" % e)


class Watch:
    """`daemon run`'s look at its nudge: a request is looked for only at a
    nudge it has not seen (and once at its start)."""

    def __init__(self, of):
        self.of, self.seen = of, None

    def look(self, nudge):
        if nudge != self.seen:
            self.seen = nudge
            noticed(self.of)

    def after_pass(self):
        after_pass()


def _cpu():
    ru = resource.getrusage(resource.RUSAGE_SELF)
    return ru.ru_utime + ru.ru_stime


def _private(path, write):
    """`write(f)` into `path` whole, by rename, mode 0600 from its creation."""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            write(f)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _said(of, req, fields):
    window = {"v": 1, "id": req["id"], "of": of, "pid": os.getpid(),
              "python": "%d.%d.%d" % sys.version_info[:3], **fields}
    _private(result_path(of, req["id"], ".json"), lambda f: f.write(json.dumps(window).encode() + b"\n"))


def _refuse(of, req, why):
    """The refusal written for the verb, best effort: one that cannot be
    written is said in daemon.log (the verb then says no profile came back)."""
    try:
        _said(of, req, {"refused": why})
    except Exception as e:  # noqa: BLE001 — a profile never stops the loop
        _logged("profile refusal of %s (pid %d) not written: %s (%r)" % (NAMES[of], os.getpid(), why, e))


def _begin(of, req):
    import cProfile
    with _LOCK:
        running = _STATE["running"]
        if running is not None:
            _refuse(of, req, "a profile already runs in this process, until %s"
                    % time.strftime("%H:%M:%S", time.localtime(running)))
            return
        if sys.version_info < (3, 12):
            _refuse(of, req, "this process runs Python %d.%d: a profile of every thread needs 3.12 or later"
                    % sys.version_info[:2])
            return
        pr = cProfile.Profile()
        try:
            pr.enable()
        except ValueError as e:   # another profiler holds sys.monitoring's slot
            _refuse(of, req, "cProfile could not start here (%s)" % e)
            return
        try:
            began, cpu = time.time(), _cpu()
            _STATE["running"] = began + req["seconds"]
            timer = threading.Timer(req["seconds"], _end, (of, req, pr, began, cpu))
            timer.name, timer.daemon = "sminos-profile", True
            timer.start()   # _end waits for _LOCK, so it never runs before this returns
        except BaseException:
            _STATE["running"] = None
            try:
                pr.disable()
            except Exception:  # noqa: BLE001 — the start's own failure is the one said
                pass
            raise


def _end(of, req, pr, began, cpu):
    try:
        try:
            pr.disable()
            ended, spent = time.time(), _cpu() - cpu
        finally:
            with _LOCK:
                _STATE["running"] = None
        pr.create_stats()
        _private(result_path(of, req["id"], ".prof"), lambda f: marshal.dump(pr.stats, f))
        _said(of, req, {"from": began, "to": ended, "cpu": spent, "threads": threading.active_count()})
        _sweep(of)
    except Exception as e:  # noqa: BLE001 — said, and the verb says no profile came back
        _logged("profile of %s (pid %d) not written: %r" % (NAMES[of], os.getpid(), e))


def _sweep(of):
    """The newest KEEP profiles of `of` kept, each with its window, newest by
    the files' mtimes (two ids of one second sort by their random part)."""
    prefix, made = "profile-%s-" % of, {}
    for n in os.listdir(daemon_dir()):
        if n.startswith(prefix) and n.endswith((".prof", ".json")):
            try:
                at = os.stat(os.path.join(daemon_dir(), n)).st_mtime_ns
            except FileNotFoundError:
                continue
            rid = n[len(prefix):].rsplit(".", 1)[0]
            made[rid] = max(made.get(rid, 0), at)
    for rid in sorted(made, key=made.get)[:-KEEP]:
        for ext in (".prof", ".json"):
            try:
                os.unlink(result_path(of, rid, ext))
            except FileNotFoundError:
                pass


# ------------------------------------------------------------- the verb


def _pid(held):
    m = re.match(r"pid (\d+)", held)
    return m.group(1) if m else "unknown"


def _read(path):
    """The request at `path` as a dict, None when it is not one; absent raises."""
    try:
        with open(path) as f:
            req = json.load(f)
    except FileNotFoundError:
        raise
    except (OSError, ValueError):
        return None
    return req if isinstance(req, dict) else None


def _stale(req):
    at = req.get("at") if req is not None else None
    return type(at) not in (int, float) or abs(time.time() - at) > STALE


def _ask(path, req):
    """Create the request at `path` whole, only where none waits; a stale or
    malformed one there is replaced. None once created, else the request
    that waits (a dict, possibly empty)."""
    tmp = "%s.%s.tmp" % (path, req["id"])
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    there = {}
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(req) + "\n")
        for _ in range(3):
            try:
                os.link(tmp, path)
                return None
            except FileExistsError:
                pass
            try:
                there = _read(path)
            except FileNotFoundError:
                continue   # taken or withdrawn meanwhile: try again
            if not _stale(there):
                return there
            _withdraw(path, None, stale=True)
        return there or {}
    finally:
        os.unlink(tmp)


def _withdraw(path, rid, stale=False):
    """Remove the request at `path` only while it is `rid`'s (with `stale`, a
    stale or malformed one, whatever its id): it is moved aside first, so a
    request that replaced it meanwhile is put back, never removed. True when
    this call removed it."""
    aside = "%s.%s.%d.aside" % (path, uuid.uuid4().hex[:8], os.getpid())
    try:
        os.rename(path, aside)
    except FileNotFoundError:
        return False
    try:
        try:
            there = _read(aside)
        except FileNotFoundError:
            return False
        if (stale and _stale(there)) or (there is not None and rid is not None and there.get("id") == rid):
            return True
        try:
            os.link(aside, path)   # another's: back where it was, unless a newer one is there already
        except FileExistsError:
            pass
        return False
    finally:
        try:
            os.unlink(aside)
        except FileNotFoundError:
            pass


def _holds(path, rid):
    """The request at `path` is still `rid`'s (not yet taken)."""
    try:
        there = _read(path)
    except FileNotFoundError:
        return False
    return there is not None and there.get("id") == rid


def cmd_profile(a):
    daemon = sminos.sibling_module("sminos_daemon")
    of, seconds = a.of, a.seconds
    if not 0 < seconds <= MAX_SECONDS:
        sminos.die("--seconds is a number of seconds above 0, at most %d" % MAX_SECONDS)
    run = daemon.held_by(daemon.run_lock_path())
    if not run:
        sminos.die("no daemon runs here (sminos daemon status): nothing to profile", 1)
    held = run
    if of == "uplink":
        held = daemon.held_by(daemon.daemon_path("uplink.lock"))
        if not held:
            why = "; ".join(daemon.uplink_status()) or "this machine is not cut over to an endpoint"
            sminos.die("no uplink runs here (%s): nothing to profile; `--of run` profiles daemon run" % why, 1)
    pid = _pid(held)
    req = new_request(of, seconds)
    path = request_path(of)
    os.makedirs(daemon_dir(), mode=0o700, exist_ok=True)
    waiting = _ask(path, req)
    if waiting is not None:
        by = waiting.get("by")
        sminos.die("a profile request for %s (pid %s) is already waiting%s: another profile is being asked for; try "
                   "again once it is taken or withdrawn (within %.0f s)"
                   % (NAMES[of], pid, " (asked by pid %d)" % by if type(by) is int else "", TAKE_WITHIN), 1)
    sminos.nudge_daemon()
    asked, renudge = time.time(), list(RENUDGE_AT)
    while _holds(path, req["id"]):
        waited = time.time() - asked
        if waited >= TAKE_WITHIN:
            if not _withdraw(path, req["id"]):
                break   # taken as it was withdrawn
            sminos.die("%s (pid %s) did not take the profile request in %.0f s: it runs code older than this "
                       "sminos's (the request needs 1.46.2 or later), or is not looking (a long pass; an uplink "
                       "not connected to its endpoint). The request is withdrawn and nothing else was asked of it."
                       % (NAMES[of], pid, waited), 1)
        if renudge and waited >= renudge[0]:
            renudge.pop(0)
            sminos.nudge_daemon()
        time.sleep(0.1)
    window_path = result_path(of, req["id"], ".json")
    deadline = time.time() + seconds + RESULT_GRACE
    print("%s (pid %s) took the request: profiling for %g s" % (NAMES[of], pid, seconds), flush=True)
    while not os.path.exists(window_path):
        if time.time() > deadline:
            sminos.die("%s (pid %s) took the request but no profile came back in %.0f s: it may have restarted "
                       "(daemon.log)" % (NAMES[of], pid, seconds + RESULT_GRACE), 1)
        time.sleep(0.2)
    with open(window_path) as f:
        window = json.load(f)
    if window.get("refused"):
        sminos.die("%s (pid %s) refused the profile: %s" % (NAMES[of], window.get("pid"), window["refused"]), 1)
    prof = result_path(of, req["id"], ".prof")
    with open(prof, "rb") as f:
        stats = marshal.load(f)
    for line in table(of, window, stats, prof):
        print(line)


def _label(key):
    fn, line, name = key
    return name if fn == "~" else "%s:%d %s" % (os.path.basename(fn), line, name)


def table(of, window, stats, prof, top=20):
    """The verb's lines: the window, its CPU and calls, the file calls and
    the functions with the most time of their own (waits left out)."""
    secs = max(window["to"] - window["from"], 1e-9)
    total = sum(v[1] for v in stats.values())
    out = ["profile of %s (pid %s, Python %s): %.1f s, CPU %.2f s, %.1f%% of a core (under the profiler, which adds "
           "its own)" % (NAMES[of], window["pid"], window["python"], secs, window["cpu"], 100 * window["cpu"] / secs),
           "written to %s (pstats: python3 -m pstats <file>)" % prof,
           "calls: %d in all, %.0f calls a second, %d threads at the end" % (total, total / secs,
                                                                             window.get("threads", 0))]
    named = {name: label for label, name in FILE_CALLS}
    counts = {label: 0 for label, _ in FILE_CALLS}
    for (fn, _, name), v in stats.items():
        if fn != "~":
            continue
        label = named.get(name)
        if label is None:
            m = FILE_EXTRA.fullmatch(name)
            label = m.group(1) if m else None
        if label is not None:
            counts[label] = counts.get(label, 0) + v[1]
    out.append("file calls: " + ", ".join("%s %d (%.0f/s)" % (k, n, n / secs) for k, n in counts.items()
                                           if n or k in dict(FILE_CALLS)))
    own = sorted(((k, v) for k, v in stats.items() if not is_wait(k)), key=lambda kv: -kv[1][2])
    out.append("most time of their own (wall time, waits left out; % of the window; approximate while threads "
               "overlap, calls exact):")
    out.append("  %8s %6s %10s  %s" % ("own s", "%", "calls", "function"))
    for k, v in own[:top]:
        out.append("  %8.3f %6.2f %10d  %s" % (v[2], 100 * v[2] / secs, v[1], _label(k)))
    return out
