#!/usr/bin/env python3
"""sminos_profile — `sminos daemon profile [--seconds S] [--of uplink|run]`:
the running uplink (the default) or `daemon run` profiles itself for S
seconds (default 20) and the verb prints where its time went: what has the
most time of its own, the file calls' counts, the calls a second and the
process's CPU over the window. A live daemon cannot be profiled from outside
at the Python level on the owner's Macs (`sample` sees native frames,
`fs_usage` and py-spy want privilege), so the process does it.

The request rides the nudge both loops already watch (sminos.nudge_daemon):
the verb writes `daemon/profile-<of>.request` and nudges, and a loop that
sees a new nudge opens its own request file once (`Watch.look`, `noticed`).
With no nudge nothing here is read, stated or timed. A process on older code
takes no request: the nudge gives it one tick, and the verb, which waits
TAKE_WITHIN for the file to be taken, withdraws it and says so. The window
begins after the pass the nudge brought (`after_pass`), so the profile is of
the loop as it runs, not of the scan a nudge asks for, and ends on a timer
thread of its own: on Python 3.12 and later cProfile, built on
sys.monitoring, sees every thread of the process and can be stopped from
any of them (own time per function holds; caller edges across threads do
not). Before 3.12 the request is refused, since a profile would see one
thread alone.

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


def noticed(of):
    """A new nudge was seen by `of`'s loop: its request, if one waits, taken
    to begin after the pass in hand."""
    req = take(of)
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
        _said(of, req, {"refused": "the profile could not begin (%r)" % e})


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


def _begin(of, req):
    import cProfile
    with _LOCK:
        running = _STATE["running"]
        if running is not None:
            _said(of, req, {"refused": "a profile already runs in this process, until %s"
                            % time.strftime("%H:%M:%S", time.localtime(running))})
            return
        if sys.version_info < (3, 12):
            _said(of, req, {"refused": "this process runs Python %d.%d: a profile of every thread needs 3.12 or later"
                            % sys.version_info[:2]})
            return
        pr = cProfile.Profile()
        try:
            pr.enable()
        except ValueError as e:   # another profiler holds sys.monitoring's slot
            _said(of, req, {"refused": "cProfile could not start here (%s)" % e})
            return
        began, cpu = time.time(), _cpu()
        _STATE["running"] = began + req["seconds"]
    timer = threading.Timer(req["seconds"], _end, (of, req, pr, began, cpu))
    timer.name, timer.daemon = "sminos-profile", True
    timer.start()


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
        sminos.daemon_log("profile of %s (pid %d) not written: %r" % (NAMES[of], os.getpid(), e))


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
    sminos.write_json(path, req)
    sminos.nudge_daemon()
    asked, renudge = time.time(), list(RENUDGE_AT)
    while os.path.exists(path):
        waited = time.time() - asked
        if waited >= TAKE_WITHIN:
            try:
                os.unlink(path)
            except FileNotFoundError:
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
    out.append("most time of their own (wall time, waits left out; % of the window):")
    out.append("  %8s %6s %10s  %s" % ("own s", "%", "calls", "function"))
    for k, v in own[:top]:
        out.append("  %8.3f %6.2f %10d  %s" % (v[2], 100 * v[2] / secs, v[1], _label(k)))
    return out
