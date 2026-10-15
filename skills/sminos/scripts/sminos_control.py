"""The control verbs and a delivery's last hop (DC2 M2, contract DX5).

`sminos steer|interrupt|model|compact <member>` act on a session through its
bridge: a command on the session's endpoint (sminos_bridge), answered by the
bridge mod. A session with no bridge falls back as the desk's design (§5) has
it: a steer to a --bg job goes through the engine supervisor's `reply`, to a
terminal session as a cross-session frame on its inbox; interrupt, model and
compact need the bridge and are refused, saying so.

`push_live` is a delivery's last hop to a live session, for the log's
delivery and `send` alike: the bridge, which submits the text as the human's
words, keyed by the log event (a key it has already submitted is dropped, so
delivery stays at least once); else, for a human's event to a --bg job, the
supervisor's `reply` (human-origin input); else the inbox frame. Each path
carries the frame the inbox would, so the model reads the same addressing.
"""

import hashlib
import http.client
import json
import os
import queue
import re
import socket
import threading
import time

import sminos as S
import sminos_bridge as B

COMMAND_WAIT_MS = 10000     # the mod answers these at once; this bounds a session gone quiet
COMPACT_WAIT_S = 300        # an idle compaction runs about 20 s; its outcome is waited for this long
SUPERVISOR_TIMEOUT = 5      # the engine's own control client waits 5 s
SHORT_RE = re.compile(r"^[a-f0-9]{8}$")
KEY_RE = re.compile(r"^[0-9a-f]{32}$")
EFFORTS = ("low", "medium", "high", "xhigh", "max")


class Unanswered(Exception):
    """A command reached the endpoint and no answer came back: it may have
    reached the mod."""


# ------------------------------------------------------------------ the bridge


def post_command(path, body, wait_ms=COMMAND_WAIT_MS):
    """One command on a session's endpoint, waiting for the mod's answer:
    (status, body). None when no bridge listens there (a stale socket file is
    removed). Unanswered when the request went and no answer came."""
    c = B._UnixConnection(path, timeout=wait_ms / 1000.0 + 5)
    try:
        try:
            c.connect()
        except OSError:
            B.remove_stale(path)
            return None
        try:
            c.request("POST", "/command?wait=%d" % wait_ms, body=json.dumps(body).encode(),
                      headers={"content-type": "application/json"})
            r = c.getresponse()
            text = r.read().decode()
        except (OSError, http.client.HTTPException) as e:
            raise Unanswered(str(e) or type(e).__name__)
        try:
            return r.status, (json.loads(text) if text else None)
        except ValueError:
            return r.status, None
    finally:
        c.close()


def deliver(session, event, text):
    """The bridge's submission of a log event: True once submitted (or found
    already submitted), None when the session has no bridge, False when the
    bridge refused it (nothing was submitted). Raises SendFailed("after")
    when the bridge took it and gave no answer: it may have been submitted."""
    body = {"op": "deliver", "key": {"writer": event["writer"], "seq": event["seq"]}, "text": text}
    try:
        r = post_command(B.endpoint(session), body)
    except Unanswered as e:
        raise S.SendFailed("after", "the bridge gave no answer: %s" % e)
    if r is None:
        return None
    status, out = r
    if status == 200 and isinstance(out, dict) and out.get("ok"):
        return True
    if status == 504:
        raise S.SendFailed("after", "the bridge's session did not answer")
    S.warn("the bridge of session %s refused a delivery (%s); it goes as an inbox frame" % (
        session[:8], (out or {}).get("error") if isinstance(out, dict) else status))
    return False


# ------------------------------------------------------------------ the engine supervisor


def supervisor_socket():
    """The engine supervisor's control socket for this user's config
    (~/.claude, as sminos reads every engine file): /tmp/cc-daemon-<uid>/
    <sha256 of the config dir's absolute path, first 8>/control.sock."""
    cfg = os.path.abspath(os.path.join(S.home_dir(), ".claude"))
    return os.path.join("/tmp", "cc-daemon-%d" % os.getuid(), hashlib.sha256(cfg.encode()).hexdigest()[:8],
                        "control.sock")


def supervisor_key():
    try:
        with open(os.path.join(S.home_dir(), ".claude", "daemon", "control.key")) as f:
            key = f.read().strip()
    except OSError:
        return ""
    return key if KEY_RE.match(key) else ""


def bg_job(peer):
    """The --bg job a live session runs as (its 8-hex short), or ""."""
    short = str((peer or {}).get("jobId") or "")
    return short if (peer or {}).get("kind") == "bg" and SHORT_RE.match(short) else ""


def supervisor_reply(short, text):
    """The supervisor's `reply` to a --bg job: queued input of human origin,
    read at the job's next step. `nextTurn` keeps it from answering a question
    dialog that happens to be open. True when the supervisor took it, else
    why not (nothing reached the job). Raises SendFailed("after") when the
    request went and no answer came."""
    key = supervisor_key()
    if not key:
        return "no supervisor control key"
    req = {"proto": 1, "op": "reply", "short": short, "text": text, "auth": key, "nextTurn": True}
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(SUPERVISOR_TIMEOUT)
    try:
        try:
            s.connect(supervisor_socket())
            s.sendall((json.dumps(req) + "\n").encode())
        except OSError as e:
            return "no supervisor took it (%s)" % e
        data = b""
        try:
            while not data.endswith(b"\n"):
                piece = s.recv(65536)
                if not piece:
                    break
                data += piece
        except OSError as e:
            raise S.SendFailed("after", "the supervisor gave no answer (%s)" % e)
    finally:
        s.close()
    try:
        answer = json.loads(data.decode())
    except ValueError:
        raise S.SendFailed("after", "the supervisor's answer was not JSON")
    if isinstance(answer, dict) and answer.get("ok"):
        return True
    answer = answer if isinstance(answer, dict) else {}
    return "%s: %s" % (answer.get("code"), answer.get("error"))


# ------------------------------------------------------------------ delivery


def push_live(peer, session, text, event=None):
    """A delivery's last hop to a live session, `event` the last log event the
    text carries (None for a frame no log holds). Raises SendFailed as
    send_frame does: "before" when nothing reached the session, "after" when
    it may have."""
    if event is not None and deliver(session, event, text):
        return
    if event is not None and event.get("kind") == "human" and bg_job(peer):
        took = supervisor_reply(bg_job(peer), text)
        if took is True:
            return
    S.send_frame(S.socket_path_of(peer), text)


# ------------------------------------------------------------------ the verbs


def no_bridge(member, verb):
    S.die("%s has no bridge on this machine: %s needs one (the session runs without the bridge mod)" % (
        member, verb), S.EXIT_UNKNOWN)


def bridged(member, verb, body, wait_ms=COMMAND_WAIT_MS):
    """(session, the mod's result) for a command on the member's bridge;
    result None when it has none. A refusal or a silence exits 1, saying why."""
    session = B.watch_session(member)
    try:
        r = post_command(B.endpoint(session), body, wait_ms)
    except Unanswered as e:
        S.die("%s: %s's bridge gave no answer (%s)" % (verb, member, e), 1)
    if r is None:
        return session, None
    status, out = r
    out = out if isinstance(out, dict) else {}
    if status == 504:
        S.die("%s: %s did not answer within %d s" % (verb, member, wait_ms // 1000), 1)
    if status != 200:
        S.die("%s: %s's bridge answered %d: %s" % (verb, member, status, out.get("error")), 1)
    if not out.get("ok"):
        S.die("%s: %s refused: %s" % (verb, member, out.get("error")), 1)
    return session, dict(out.get("result") or {}, id=out.get("id"))


def cmd_steer(a):
    session, result = bridged(a.member, "steer", {"op": "steer", "text": a.text})
    if result is not None:
        print("steered %s: its next model request reads it (row %s)" % (a.member, result.get("row")))
        return
    peer = S.peer_for_session(session)
    if peer is None:
        S.die("%s is not live: a steer reaches a running session" % a.member, S.EXIT_UNKNOWN)
    short = bg_job(peer)
    try:
        if short:
            took = supervisor_reply(short, a.text)
            if took is True:
                print("steered %s through the engine supervisor (no bridge): read at its next step" % a.member)
                return
            S.warn("the supervisor did not take the steer (%s); it goes as a cross-session frame" % took)
        S.send_frame(S.socket_path_of(peer), "[sminos steer from human]\n%s" % a.text)
    except S.SendFailed as e:
        if e.phase == "after":
            S.die("the steer to %s is UNCERTAIN (%s); do not blindly repeat it" % (a.member, e), 1)
        S.die("%s went away mid-steer (%s)" % (a.member, e), S.EXIT_UNKNOWN)
    print("steered %s as a cross-session frame (no bridge): read at its next tool round" % a.member)


def cmd_interrupt(a):
    _, result = bridged(a.member, "interrupt", {"op": "interrupt"})
    if result is None:
        no_bridge(a.member, "interrupt")
    if not result.get("turnId"):
        print("%s is idle: nothing to interrupt" % a.member)
        return
    stopped = result.get("stopped") or []
    running = result.get("running") or []
    print("interrupted %s: turn %s stopped%s" % (
        a.member, str(result["turnId"])[:8],
        "; background task%s %s stopped" % ("s" if len(stopped) > 1 else "", ", ".join(stopped)) if stopped else ""))
    if running:
        S.die("interrupt of %s is incomplete: background task%s %s still running (TaskStop failed)" % (
            a.member, "s" if len(running) > 1 else "", ", ".join(running)), 1)


def cmd_model(a):
    model = None if a.model == "default" else a.model
    _, result = bridged(a.member, "model", {"op": "model", "model": model, "effort": a.effort})
    if result is None:
        no_bridge(a.member, "model")
    if result.get("model") is None and result.get("effort") is None:
        print("%s is back on its own model and effort" % a.member)
        return
    print("%s now runs on %s at %s effort (this session only)" % (
        a.member, result.get("model") or "its own model", result.get("effort") or "its own"))


def cmd_compact(a):
    """Asked during a turn, the compaction runs when the turn ends; asked
    idle, it runs at once and this waits for its outcome, on the stream
    subscribed before the command went."""
    session = B.watch_session(a.member)
    path = B.endpoint(session)
    if B.probe(path) is None:
        B.remove_stale(path)
        no_bridge(a.member, "compact")
    events = queue.Queue()

    def follow():
        try:
            for e in B.subscribe(path):
                events.put(e)
        except (OSError, http.client.HTTPException, ValueError):
            pass
        events.put(None)

    threading.Thread(target=follow, daemon=True).start()
    try:
        first = events.get(timeout=5)
    except queue.Empty:
        first = None
    if not first or first.get("type") != "snapshot":
        S.die("compact: %s's bridge did not stream" % a.member, 1)
    body = {"op": "compact"}
    if a.instructions:
        body["instructions"] = a.instructions
    _, result = bridged(a.member, "compact", body)
    if result is None:
        no_bridge(a.member, "compact")
    if result.get("queued"):
        print("compaction of %s queued: it runs when the running turn ends" % a.member)
        return
    deadline = time.monotonic() + COMPACT_WAIT_S
    while True:
        try:
            e = events.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            S.die("compact: no outcome from %s within %d s (it may still be compacting)" % (a.member, COMPACT_WAIT_S), 1)
        if e is None:
            S.die("compact: %s's bridge ended before the compaction did" % a.member, 1)
        if e.get("type") == "compact" and e.get("phase") == "end" and e.get("id") == result.get("id"):
            break
    if e.get("error"):
        S.die("compact: %s: %s" % (a.member, e["error"]), 1)
    if e.get("skip"):
        print("%s was not compacted: %s" % (a.member, e["skip"]))
        return
    counts = ""
    if e.get("tokensBefore") is not None and e.get("tokensAfter") is not None:
        counts = ": %s → %s tokens" % (format(e["tokensBefore"], ","), format(e["tokensAfter"], ","))
    print("compacted %s%s" % (a.member, counts))
