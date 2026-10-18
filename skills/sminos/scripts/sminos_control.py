"""The control verbs and a delivery's last hop (DC2 M2, contract DX5).

`sminos steer|interrupt|stop|model|compact <member>` act on a session through its
bridge: a command on the session's endpoint (sminos_bridge), answered by the
bridge mod. A session with no bridge falls back as the desk's design (§5) has
it: a steer to a --bg job goes through the engine supervisor's `reply`, to a
terminal session as a cross-session frame on its inbox; interrupt, stop, model
and compact need the bridge and are refused, saying so.

`push_live` is a delivery's last hop to a live session, for the log's
delivery and `send` alike. A peer's event (any but the owner's, S.owner_event)
is the inbox frame: the engine delivers it as a message from another Claude
session, never as its user's words. The owner's goes through the bridge,
which submits the text as the human's words, keyed by the log event and its
project (a key it has already submitted is dropped); else, to a --bg job, the
supervisor's `reply` (human-origin input); else the inbox frame. Each path
carries the same frame text, so the model reads the same addressing.
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
SETTLE_WAIT_S = 30          # a decision taken is settled within seconds (a background window's at its deadline)
FIRST_WAIT_S = 8            # a subscription's snapshot: the child holds it up to 5 s for the mod's first resync
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


def deliver(session, project, event, text):
    """The bridge's submission of a log event of the project `project` (its
    id): True once submitted (or found already submitted), None when the
    session has no bridge, False when the bridge refused it (nothing was
    submitted). Raises SendFailed("after") when the bridge took it and gave no
    answer: it may have been submitted. The key names the project, since
    every project numbers a writer's events on its own. A duplicate is taken
    as delivered, since it was submitted before, but said: were it not, the
    event would be lost with no other trace."""
    body = {"op": "deliver", "key": {"project": project, "writer": event["writer"], "seq": event["seq"]}, "text": text}
    try:
        r = post_command(B.endpoint(session), body)
    except Unanswered as e:
        raise S.SendFailed("after", "the bridge gave no answer: %s" % e)
    if r is None:
        return None
    status, out = r
    if status == 200 and isinstance(out, dict) and out.get("ok"):
        if (out.get("result") or {}).get("duplicate"):
            line = "the bridge of session %s took %s as already delivered" % (session, S.event_ref(event))
            S.warn(line)
            S.daemon_log(line)
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


def push_live(peer, session, text, event=None, project=None):
    """A delivery's last hop to a live session, `event` the last log event the
    text carries (None for a frame no log holds; every event of one push is
    one writer's, so one side's) and `project` the id of the project whose
    log holds it. Only the owner's events take the bridge or the supervisor,
    the human's channels; a peer's is the inbox frame, named by its sender
    and closed by how to answer it (S.reply_line). Raises SendFailed as
    send_frame does: "before" when nothing reached the session, "after" when
    it may have."""
    owner = event is not None and S.owner_event(event)
    if owner and deliver(session, project, event, text):
        return
    if owner and bg_job(peer):
        took = supervisor_reply(bg_job(peer), text)
        if took is True:
            return
    sender = str(event.get("via") or event.get("from") or "") if event is not None else ""
    S.send_frame(S.socket_path_of(peer), text, sender, S.writer_session(event["writer"]) if event is not None else "",
                 project or "")


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
        S.send_frame(S.socket_path_of(peer), "[sminos steer from human]\n%s" % a.text, "human")
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


def cmd_stop(a):
    """A background shell or monitor of the member's stopped with TaskStop,
    the main loop's or a subagent's."""
    _, result = bridged(a.member, "stop", {"op": "stop", "taskId": a.task})
    if result is None:
        no_bridge(a.member, "stop")
    print("stopped %s's background task %s" % (a.member, result.get("taskId") or a.task))


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
    events = follow_stream(path)
    try:
        first = events.get(timeout=FIRST_WAIT_S)
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


# ------------------------------------------------------------------ requests from outside


def follow_stream(path):
    """The endpoint's stream on a thread: a queue of its events (the
    snapshot first), then None at its end. A stream the child ended because
    the mod resent its state is followed on at once: the fresh snapshot comes
    next in the queue, so a settlement that happened in between is read from
    its `settled`. A child not ready yet (503: the mod's first resync has
    not reached it) is asked again until the first snapshot's window
    (FIRST_WAIT_S) runs out."""
    events = queue.Queue()
    first_by = time.monotonic() + FIRST_WAIT_S

    def follow():
        pid = None
        while True:
            try:
                for e in B.subscribe(path):
                    if e.get("type") == "snapshot":
                        if pid is not None and e.get("pid") != pid:
                            break   # another child: what this one followed is gone
                        pid = e.get("pid")
                    events.put(e)
            except B.NotReady:
                if pid is None and time.monotonic() < first_by:
                    time.sleep(0.1)
                    continue
                break
            except (OSError, http.client.HTTPException, ValueError):
                break
            status = B.probe(path)
            if pid is None or status is None or status.get("pid") != pid:
                break
        events.put(None)

    threading.Thread(target=follow, daemon=True).start()
    return events


def find_request(member, verb, want):
    """(path, the stream, the pending request `want` names): by its id or a
    unique prefix of it, read from a snapshot subscribed before the decision
    goes. Exits 1 when no pending request matches (saying so when it is
    already settled), 4 when the member has no bridge."""
    session = B.watch_session(member)
    path = B.endpoint(session)
    if B.probe(path) is None:
        B.remove_stale(path)
        no_bridge(member, verb)
    events = follow_stream(path)
    try:
        snap = events.get(timeout=FIRST_WAIT_S)
    except queue.Empty:
        snap = None
    if not snap or snap.get("type") != "snapshot":
        S.die("%s: %s's bridge did not stream" % (verb, member), 1)

    def named(items):
        exact = [r for r in items if r.get("request") == want]
        return exact or [r for r in items if str(r.get("request", "")).startswith(want)]

    hits = named(snap.get("pending") or [])
    if len(hits) > 1:
        S.die("%s: '%s' names %d pending requests of %s: %s" % (
            verb, want, len(hits), member, ", ".join(r["request"] for r in hits)), 1)
    if hits:
        return path, events, hits[0]
    done = named(snap.get("settled") or [])
    if done:
        s = done[-1]
        S.die("%s: request %s of %s is already settled: %s (%s)" % (
            verb, s["request"], member, s.get("outcome"), s.get("by")), 1)
    S.die("%s: %s has no pending request '%s'" % (verb, member, want), 1)


def settle_decision(member, verb, path, events, raised, body):
    """Posts the decision, then waits for the request's settlement on the
    stream subscribed before it went: exit 0 when the engine used this
    answer, 1 when it used another side's or the decision was refused."""
    rid = raised["request"]
    try:
        status, out = B.request(path, "POST", "/requests/%s/decision" % rid, body)
    except (OSError, http.client.HTTPException) as e:
        S.die("%s: %s's bridge gave no answer (%s)" % (verb, member, e), 1)
    out = out if isinstance(out, dict) else {}
    if status == 400:
        S.die("%s: %s" % (verb, out.get("error")), 2)
    if status == 409 and isinstance(out.get("settled"), dict):
        s = out["settled"]
        S.die("%s: request %s is already settled: %s (%s)" % (verb, rid, s.get("outcome"), s.get("by")), 1)
    if status != 200:
        S.die("%s: request %s: %s" % (verb, rid, out.get("error") or "the bridge answered %d" % status), 1)
    deadline = time.monotonic() + SETTLE_WAIT_S
    while True:
        try:
            e = events.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            S.die("%s: request %s took the decision; no settlement came within %d s" % (verb, rid, SETTLE_WAIT_S), 1)
        if e is None:
            S.die("%s: %s's bridge ended before request %s settled" % (verb, member, rid), 1)
        if e.get("type") == "snapshot":
            e = next((x for x in e.get("settled") or [] if x.get("request") == rid), None)
            if e is not None:
                break
            continue
        if e.get("type") == "settled" and e.get("request") == rid:
            break
    if e.get("by") != body["by"]:
        S.die("%s: request %s settled with the %s's answer: %s (%s)" % (
            verb, rid, e.get("winner"), e.get("outcome"), e.get("by")), 1)
    print("%s: request %s settled from here: %s" % (member, rid, e.get("outcome")))


def resolve_answer(question, text):
    """An answer as the dialog records it: an option's label (named by its
    number, or its label in any case), a multi-select's labels joined with
    ", ", else the text as typed."""
    labels = [str(o.get("label")) for o in question.get("options") or [] if isinstance(o, dict)]

    def option(t):
        t = t.strip()
        if t.isdigit() and 1 <= int(t) <= len(labels):
            return labels[int(t) - 1]
        return next((label for label in labels if label.lower() == t.lower()), None)

    if question.get("multiSelect"):
        picked = [option(p) for p in text.split(",")]
        return ", ".join(picked) if picked and all(picked) else text
    return option(text) or text


def cmd_decide(a):
    path, events, raised = find_request(a.member, "decide", a.request)
    body = {"behavior": a.behavior, "by": "cli"}
    if a.message:
        body["message"] = a.message
    settle_decision(a.member, "decide", path, events, raised, body)


def cmd_answer(a):
    path, events, raised = find_request(a.member, "answer", a.request)
    questions = [q for q in ((raised.get("input") or {}).get("questions") or []) if isinstance(q, dict)]
    if not B.is_question(raised) or not questions:
        S.die("answer: request %s asks no question (%s): decide it with allow or deny" % (
            raised["request"], raised.get("tool")), 2)
    if len(a.answers) != len(questions):
        S.die("answer: request %s asks %d question%s; give one answer each, in order: %s" % (
            raised["request"], len(questions), "" if len(questions) == 1 else "s",
            " | ".join(str(q.get("question", "?")) for q in questions)), 2)
    answers = {q["question"]: resolve_answer(q, t) for q, t in zip(questions, a.answers)}
    body = {"behavior": "allow", "updatedInput": {"answers": answers}, "by": "cli"}
    settle_decision(a.member, "answer", path, events, raised, body)
