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
import urllib.parse
import urllib.request
from typing import NoReturn

SENTINEL = "[board-relay answer:%s]"
_RETRIES = 3          # transport-level, idempotent requests only
_RETRY_WAIT = 2.0


class RunEnded(Exception):
    """409 run-ended — the caller's run was reaped; callers route, not die."""


class ClaimObsolete(Exception):
    """A 409 saying the caller's CLAIM HANDLE is spent, not that the board is
    sick — `nonce-consumed` (the predecessor's run ended, so that nonce can
    never be replayed) and `stale-resume` (the ticket moved after the feed
    read). Routed, not died on: the caller drops its journal uncharged and the
    ticket comes back around on a fresh nonce. Carries `.code` so the caller
    can say which one it met.
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def die(msg) -> NoReturn:
    # NoReturn, not decoration: callers treat `die` as terminal, so without it
    # a checker reads every `x = die(...) or x` path as reachable with x=None.
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


def repo():
    """The repo key this checkout speaks for — `.doperpowers/board.json`'s
    `repo`, handed over by _binding.sh (which refuses an api binding without
    one).

    One board service serves several repositories out of ONE ticket namespace,
    so a request that names no repo is not repo-neutral: the server picks. On an
    ordinary write it picks its founding repo, on a list read it picks EVERY
    repo — which is how a register run from a neighbouring checkout filed its
    ticket here, and how a sweep read another repo's board. There is therefore
    no default to fall back to: an unset BOARD_REPO is a broken hand-over, not a
    request for the server's choice.
    """
    # Stripped, and a blank spelled as whitespace refused like an absent one:
    # `%20` on the wire is not a repo, and the server reads a blank `repo=` as
    # NO filter — the widening this parameter exists to close.
    key = os.environ.get("BOARD_REPO", "").strip()
    if not key:
        die("BOARD_REPO is unset — an api binding declares its repo in "
            ".doperpowers/board.json (\"repo\": \"<name>\") and _binding.sh "
            "passes it through; sending none would let the server choose one")
    return key


def _scoped(path, all_repos=False):
    """`path` with `repo=` appended — for the routes whose repo dimension is a
    QUERY parameter (the list-shaped reads, whose server-side default is every
    repo). Appended after whatever the caller already assembled, so a walk's
    `&cursor=` still lands last and a prefix-matching fixture still matches.

    `all_repos` is the browse verbs' deliberate widening (board-list.sh /
    board-search.sh `--all-repos`): the read then carries no repo at all and the
    server answers across the namespace.
    """
    if all_repos:
        return path
    return "%s%srepo=%s" % (path, "&" if "?" in path else "?",
                            urllib.parse.quote(repo(), safe=""))


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


def request(method, path, body=None, principal="auto", ok=(200,), retry=None,
            obsolete_codes=(), absent=()):
    """One HTTP exchange. Dies with the contract's error identifier on
    refusal; raises RunEnded on 409 run-ended (callers route on it), and
    ClaimObsolete on any code the caller named in `obsolete_codes` — named
    per route rather than globally, because the same code is a routable
    outcome on one route and an ordinary refusal on another. `absent` names
    the codes whose whole meaning is "the row you asked for is not there",
    which is an answer rather than a fault: those return None."""
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
            if code in obsolete_codes:
                raise ClaimObsolete(code, message) from None
            if code in absent:
                return None
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
    # A DISPATCH NAMES ITS REPO. This route is dispatch-shaped, so the server
    # refuses an unscoped credential that names none (`repo-required`) rather
    # than picking — and a name a scoped credential contradicts is
    # `repo-mismatch`, which is a checkout being told it is dispatching for
    # someone else's board instead of quietly doing it.
    body["repo"] = repo()
    return request("POST", "/runs/claim", body, "automation", retry=True)


def claim_successor(ticket_id, nonce, lease_minutes=None):
    body = {"ticketId": int(ticket_id), "dispatchNonce": nonce}
    if lease_minutes is not None:
        body["leaseMinutes"] = lease_minutes
    # A SUCCESSOR CLAIM IS A DISPATCH, and the server resolves it through the
    # same dispatch rule /runs/claim uses. Naming the ticket is not naming the
    # repo — that rule reads the credential and the request, never the row the
    # id points at — so an unscoped credential that sent none would be refused
    # `repo-required` and every reclaimed run would stick in the recovery loop.
    body["repo"] = repo()
    return request("POST", "/runs/claim-successor", body, "automation", retry=True,
                   obsolete_codes=("nonce-consumed", "stale-resume"))


# Both feeds are list-shaped and repo-dimensioned: unnarrowed they answer for
# EVERY repo the service holds, so a tick in this checkout would try to resume
# and relay another repo's runs. (An unscoped credential is refused
# `repo-required` on them outright; a scoped one gets the cross-check.)
def needing_resume():
    return request("GET", _scoped("/runs/needing-resume"),
                   principal="automation")


def unrelayed():
    return request("GET", _scoped("/answers/unrelayed"),
                   principal="automation")


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
    # A BIRTH NAMES ITS REPO. Unnamed, an unscoped credential lands the ticket
    # in the service's founding repo; named, a credential that contradicts it is
    # refused `repo-mismatch` rather than filing somewhere quietly. Sent for a
    # scoped token too, where it is redundant with what the server derives —
    # that redundancy IS the cross-check.
    return request("POST", "/tickets", dict(payload, repo=repo()), principal)


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


def timeline(tid, principal="human"):
    return request("GET", "/tickets/%s/timeline" % int(tid), principal=principal)


# ---- paged read surface (spec: board-client-paged-reads v1.1) --------------

_PAGE_LIMIT = 200   # explicit limit= is the envelope opt-in
_MAX_IDS = 200      # documented ids= cap (arkho API.md §1)
_MAX_BODY_IDS = 20  # include=body chunk cap (arkho API.md §1)
_SURFACE = {"proven": False}   # per-process: has any envelope read succeeded?


def _envelope(payload, path, context=""):
    """A paged read must answer the COMPLETE envelope. A bare array means
    the server predates the read surface; a dict missing `next` (or carrying
    a wrong-typed member) is a malformed or version-skewed page — and
    treating a MISSING `next` like the contract's `next: null` would end the
    walk early and hand the caller a partial board as if complete. An EMPTY
    `next` is malformed too, and it is the one shape a type check alone lets
    through: the walk appends no cursor, refetches page 1 and never ends. So
    `next` is null or a NON-EMPTY cursor, nothing else. Strict or dead: no
    partial result may escape.

    `context` appends the caller's own diagnosis to the die, for the callers
    that know something this function cannot — the rollback probe knows a
    404 preceded it, and that is what makes the failure legible."""
    if (not isinstance(payload, dict)
            or not isinstance(payload.get("items"), list)
            or "next" not in payload
            or not (payload["next"] is None
                    or (isinstance(payload["next"], str) and payload["next"]))
            or not isinstance(payload.get("as_of"), int)):
        die("GET %s answered no complete paged envelope ({items, next, "
            "as_of}, where next is null or a NON-EMPTY cursor) — a "
            "pre-read-surface or malformed server; refusing to guess%s"
            % (path, context))
    _SURFACE["proven"] = True
    return payload


def _walk(base, principal):
    """Every row of a COMPLETE cursor walk, as a list. The `next` token is
    passed back VERBATIM. Materializing here rather than yielding is what makes
    the no-partial-board rule structural: a failed page dies inside request()
    before this returns, so the rows read so far are unreachable — a partial
    board is unrepresentable, not merely unconsumed by today's callers.

    A cursor is followed at most ONCE. `_envelope` rejects the empty `next`
    that would refetch page 1 forever, but a well-formed cursor that REPEATS —
    the same token again, or a cycle A→B→A — walks just as endlessly, and a
    hang or an exhausted heap is not the fail-closed death this module owes
    its callers. The first page carries no cursor and cannot collide with one,
    since a cursor is a non-empty string, so the set of followed tokens is the
    whole guard."""
    rows = []
    cursor = None
    followed = set()
    while True:
        path = base + ("&cursor=%s" % cursor if cursor else "")
        page = _envelope(request("GET", path, principal=principal), path)
        rows.extend(page["items"])
        cursor = page["next"]   # _envelope proved it null or a NON-EMPTY token
        if cursor is None:
            return rows
        if cursor in followed:
            die("GET %s answered a cursor already followed — a looping or "
                "version-skewed server; refusing an unbounded walk" % path)
        followed.add(cursor)


def _claim_gated(what):
    """q and include=body are refused to run bearers server-side
    (arkho#12): a run's statement of work arrives in its claim payload,
    and a run's search would be a term-membership oracle over body text
    it cannot read. token() speaks as the run whenever BOARD_RUN_TOKEN
    is set, so the refusal is deterministic — die here, before any
    request, with the reason instead of a bare `forbidden`."""
    if os.environ.get("BOARD_RUN_TOKEN"):
        die("%s is claim-gated for runs (arkho#12): this process speaks "
            "as its run (BOARD_RUN_TOKEN is set) and the server refuses "
            "q/include=body to run bearers — a run reads its statement "
            "of work from the claim payload" % what)


def ticket(tid, principal="human", include_body=False):
    """GET /tickets/{id}. None = the ticket does not exist, and that answer
    is AUTHORITATIVE (action-grade) — unlike walk absence, which is
    report-grade (spec § Helper primitives). Rollback guard: route-level and
    row-level 404 share one stable code, so an unproven process probes the
    paged surface once before trusting a 404 as a real absence.

    The evidence an authoritative None rests on is a 404 OBSERVED ON A PROVEN
    surface. A 404 that arrived before the proof is not that evidence, and the
    probe cannot retroactively make it so, so the read is re-issued and the
    second answer is the one returned."""
    path = "/tickets/%s" % int(tid)
    if include_body:
        _claim_gated("include=body")
        path += "?include=body"
    out = request("GET", path, principal=principal, absent=("not-found",))
    if out is None and not _SURFACE["proven"]:
        # The probe is held to the FULL envelope, not merely to carrying an
        # `items` key: a rolled-back or version-skewed answer may not be the
        # thing that proves the surface, because proving it is what turns this
        # 404 into an authoritative absence — and board-lint retires live
        # daemons on that answer. _envelope marks the surface proven itself.
        probe = _scoped("/tickets?limit=1")
        _envelope(request("GET", probe, principal=principal), probe,
                  " — so the not-found on GET %s is a route-level "
                  "404 from a pre-read-surface server, not a missing ticket"
                  % path)
        # The probe proves the surface exists NOW; it says nothing about the
        # instance that served the 404 a moment ago. Across a version
        # transition the two requests can land on different instances — the
        # 404 from one that predates the read surface, the envelope from one
        # that has it — and taking the probe as proof would then authenticate
        # a route-level 404 as a missing ticket, which is the whole hazard
        # this guard exists for. So the read is re-asked with the surface
        # proven in-process: a row rescues the false absence, and a second
        # 404 is the authoritative one.
        out = request("GET", path, principal=principal, absent=("not-found",))
    if out is not None:
        _SURFACE["proven"] = True
    return out


def tickets_by_ids(ids, principal="human", include_body=False,
                   all_repos=False):
    """ids= batch read, chunked at the documented cap. Returns {int_id: row}.
    An id absent from the completed result is authoritatively absent — a
    targeted read, not a walk. (The board has no delete path today, so an
    absent id here means the id never named a ticket.)

    include_body hydrates each row's statement of work: the chunk cap
    drops to the server's 20-id bound and `include=body` rides each
    chunk's read. The 8 MiB serialized budget is not a reachable bound at
    this toolkit's body sizes (KBs) — a budget 400 passes through as the
    server's own message (spec Decision Log)."""
    if include_body:
        _claim_gated("include=body")
    ids = [int(i) for i in ids]
    out = {}
    cap = _MAX_BODY_IDS if include_body else _MAX_IDS
    for i in range(0, len(ids), cap):
        chunk = ids[i:i + cap]
        base = "/tickets?limit=%d&ids=%s" % (
            _PAGE_LIMIT, ",".join(str(c) for c in chunk))
        if include_body:
            base += "&include=body"
        base = _scoped(base, all_repos)
        for row in _walk(base, principal):
            out[int(row["id"])] = row
    return out


def tickets_all(states=None, principal="human", all_repos=False):
    """Complete cursor walk of /tickets. REPORT-grade completeness: contains
    every row whose sort position was stable while the walk ran; a row
    reprioritized behind an already-passed cursor mid-walk is missing from
    every page. Absence that drives an ACTION needs ticket() instead.
    Dedupe: a moved row can also be re-served — later data wins, first-seen
    position kept (dict overwrite)."""
    base = "/tickets?limit=%d" % _PAGE_LIMIT
    if states:
        base += "&states=%s" % states
    # Narrowed to this checkout's repo BEFORE the walk, so every page carries
    # it: _walk appends only `&cursor=`, and a page that dropped the filter
    # would splice another repo's rows into the middle of the result.
    base = _scoped(base, all_repos)
    seen = {}
    for row in _walk(base, principal):
        seen[int(row["id"])] = row
    return list(seen.values())


def tickets_search(q, states=None, principal="automation", all_repos=False):
    """Complete cursor walk of /tickets?q= — the server's websearch filter
    over title+body (arkho#12: unquoted terms AND, `or`, `-` negation,
    quoted phrases; the grammar is the server's to judge). Report-grade
    completeness and id-keyed dedupe, same as tickets_all. The query
    rides urlencoded inside ONE parameter — quote(q, safe=""), never
    quote_plus, whose space-as-+ is a different wire spelling."""
    _claim_gated("search (?q=)")
    base = "/tickets?limit=%d&q=%s" % (
        _PAGE_LIMIT, urllib.parse.quote(q, safe=""))
    if states:
        base += "&states=%s" % states
    base = _scoped(base, all_repos)
    seen = {}
    for row in _walk(base, principal):
        seen[int(row["id"])] = row
    return list(seen.values())


def queue_decisions_all():
    """Complete cursor walk of /queue/decisions. Identity is correlation_id
    (queue rows carry no `id`); the keyset (raised_at, correlation_id) is
    immutable so re-serves are impossible — no dedupe. Walk absence is
    report-grade here too: a park COMMITTING during the walk can land behind
    the cursor — action-grade absence is a second walk started after the
    first finished (board-answer's retry)."""
    return list(_walk(_scoped("/queue/decisions?limit=%d" % _PAGE_LIMIT),
                      "human"))


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
