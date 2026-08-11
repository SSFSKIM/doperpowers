"""_board_api.py — the toolkit's ONLY HTTP surface for the Arkho board API.

Thin by design (spec: verb-level thin client): request assembly, principal
resolution, contract error mapping, retry. No state-machine logic — the
server enforces legality, and _board.py's state-machine half (legality
table, mutation, epic pulls, pick order) is never EXERCISED in API mode.
That is the invariant, not "_board is never imported": a read verb may still
import it for a pure derivation it renders (board-map.sh calls B.eligible to
label a node), which shares the single source of that derivation rather than
forking a second, drifting copy of it.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

SENTINEL = "[board-relay answer:%s]"
_RETRIES = 3          # transport-level, idempotent requests only
_RETRY_WAIT = 2.0


class RunEnded(Exception):
    """409 run-ended — the caller's run was reaped; callers route, not die."""


def die(msg):
    print("error: %s" % msg, file=sys.stderr)
    raise SystemExit(1)


def ref(raw):
    """A ticket ref — '#42'/'42' → 42, same refusal as gh mode's B.resolve.

    Refs are argv, so a junk one is a caller mistake and dies here rather
    than as a traceback or a request the server has to reject.
    """
    n = str(raw).lstrip("#")
    if not n.isdigit():
        die("not an issue number: %s" % raw)
    return int(n)


def api_url():
    url = os.environ.get("BOARD_API_URL", "").rstrip("/")
    if not url:
        die("BOARD_API_URL is not set — is this repo bound to a board API? "
            "(.doperpowers/board.json)")
    return url


def _creds():
    path = os.environ.get("BOARD_CREDENTIALS_FILE", "")
    if not path or not os.path.isfile(path):
        die("board credentials file not found at %r — create it with "
            "BOARD_AUTOMATION_TOKEN=… and BOARD_HUMAN_TOKEN=… lines" % path)
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def token(principal):
    """principal: 'auto' (run token or die), 'automation', 'human'."""
    run_tok = os.environ.get("BOARD_RUN_TOKEN", "")
    if run_tok:                      # a run context always speaks as the run
        return run_tok
    if principal == "auto":
        die("no BOARD_RUN_TOKEN in env and the caller demanded the run "
            "principal — this verb is worker-context-only here")
    key = {"automation": "BOARD_AUTOMATION_TOKEN",
           "human": "BOARD_HUMAN_TOKEN"}[principal]
    val = _creds().get(key, "")
    if not val:
        die("%s missing from %s" % (key, os.environ.get("BOARD_CREDENTIALS_FILE")))
    return val


def _error(payload, status):
    """Unwrap the contract's error envelope: {"error": {"code", "message"}}.

    Anything that is not that shape — a proxy's HTML 502, an empty 404, a
    body carrying `error` as a bare string — degrades to the status code
    rather than crashing or pretending to a contract identifier. This is the
    one place a foreign process's bytes enter, so it may not assume them.
    """
    try:
        env = json.loads(payload)["error"]
    except (ValueError, TypeError, KeyError):
        env = None
    if not isinstance(env, dict):
        env = {}
    return (env.get("code") or "http-%s" % status,
            env.get("message") or payload[:400])


def request(method, path, body=None, principal="auto", ok=(200,), retry=None):
    """One HTTP exchange. Dies with the contract's error identifier on
    refusal; raises RunEnded on 409 run-ended (callers route on it)."""
    if retry is None:
        retry = method == "GET"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api_url() + path, data=data, method=method)
    req.add_header("authorization", "Bearer " + token(principal))
    if data is not None:
        req.add_header("content-type", "application/json")
    attempts = _RETRIES if retry else 1
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = resp.read().decode() or "{}"
                if resp.status in ok:
                    return json.loads(payload)
                die("%s %s answered %s: %s" % (method, path, resp.status, payload))
        except urllib.error.HTTPError as e:
            code, message = _error(e.read().decode(), e.code)
            if code == "run-ended":
                raise RunEnded(message) from None
            # a refusal is an answer, never retried
            die("%s %s refused: %s — %s" % (method, path, code, message))
        except (urllib.error.URLError, OSError) as e:
            last = e
            if i + 1 < attempts:
                time.sleep(_RETRY_WAIT)
    die("%s %s unreachable after %d attempts: %s" % (method, path, attempts, last))


# ---- route helpers (payload shapes verbatim from API.md) -------------------

def claim(lane, nonce, lease_minutes=None, lane_cap=None):
    body = {"lane": lane, "dispatchNonce": nonce}
    if lease_minutes is not None:
        body["leaseMinutes"] = lease_minutes
    if lane_cap is not None:
        body["laneCap"] = lane_cap
    return request("POST", "/runs/claim", body, "automation", retry=True)


def claim_successor(ticket_id, nonce, lease_minutes=None):
    body = {"ticketId": int(ticket_id), "dispatchNonce": nonce}
    if lease_minutes is not None:
        body["leaseMinutes"] = lease_minutes
    return request("POST", "/runs/claim-successor", body, "automation", retry=True)


def needing_resume():
    return request("GET", "/runs/needing-resume", principal="automation")


def unrelayed():
    return request("GET", "/answers/unrelayed", principal="automation")


def ack(answer_event_id):
    return request("POST", "/answers/%s/ack" % int(answer_event_id),
                   {}, "automation", retry=True)   # set-once idempotent


def renew(run_id):
    return request("POST", "/runs/%s/renew" % int(run_id), {}, "automation")


def bind(run_id, store_ns, project_key, session_id):
    # `auto`, not `automation`: a bind is only ever posted for a run whose
    # bearer the caller holds (board-bind.sh refuses without one), and token()
    # hands back the run token for whatever principal is named once one is in
    # env — so naming `automation` here was dead text that read as a fallback
    # this route does not have. Demanding the run principal makes the missing
    # bearer a refusal rather than a bind posted as the whole fleet.
    return request("POST", "/runs/%s/bind" % int(run_id),
                   {"storeNs": store_ns, "projectKey": project_key,
                    "sessionId": session_id}, "auto")


def end_run(run_id, reason="completed"):
    return request("POST", "/runs/%s/end" % int(run_id),
                   {"reason": reason}, "automation")


def register(payload, principal="human"):
    return request("POST", "/tickets", payload, principal)


def transition(tid, to, note=None, pr=None, plan=None, branch=None,
               fence=None, principal="human"):
    body = {"to": to}
    for k, v in (("note", note), ("pr", pr), ("plan", plan),
                 ("branch", branch), ("fence", fence)):
        if v is not None:
            body[k] = v
    return request("POST", "/tickets/%s/transition" % int(tid), body, principal)


def comment(tid, kind="comment", text=None, body=None, principal="human"):
    payload = {"kind": kind}
    if text is not None:
        payload["text"] = text
    if body is not None:
        payload["body"] = body
    return request("POST", "/tickets/%s/comment" % int(tid), payload, principal)


def park_answer(tid, replies, to=None, correlation_id=None):
    body = {"replies": replies}
    if to is not None:
        body["to"] = to
    if correlation_id is not None:
        body["correlationId"] = correlation_id
    return request("POST", "/tickets/%s/park-answer" % int(tid), body, "human")


def tickets(state=None, category=None, principal="human"):
    qs = "&".join("%s=%s" % (k, v) for k, v in
                  (("state", state), ("category", category)) if v)
    return request("GET", "/tickets" + ("?" + qs if qs else ""),
                   principal=principal)


def timeline(tid, principal="human"):
    return request("GET", "/tickets/%s/timeline" % int(tid), principal=principal)


def queue_decisions():
    return request("GET", "/queue/decisions", principal="human")


# The five routes below are human-only server-side: a run's bearer is refused
# on all of them. `principal="human"` is therefore stated, not defaulted.

def edge(tid, op, blocked_by):
    return request("POST", "/tickets/%s/edges" % int(tid),
                   {"op": op, "blockedBy": int(blocked_by)}, "human")


def set_parent(tid, parent):
    # Orphaning writes an explicit null rather than dropping the key. The
    # service reads absent and null the same way today, so this is for
    # legibility and robustness: an explicit null states "no parent"
    # unambiguously and still means that if the contract ever tightens.
    return request("POST", "/tickets/%s/parent" % int(tid),
                   {"parent": int(parent) if parent is not None else None},
                   "human")


def relate(tid, op, other):
    return request("POST", "/tickets/%s/relates" % int(tid),
                   {"op": op, "ticket": int(other)}, "human")


def set_priority(tid, priority):
    return request("POST", "/tickets/%s/priority" % int(tid),
                   {"priority": priority}, "human")


def set_body(tid, body):
    return request("POST", "/tickets/%s/body" % int(tid),
                   {"body": body}, "human")
