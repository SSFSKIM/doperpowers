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


def board_key():
    """This binding's identity as the daemon registry spells it — the same
    `api:<url>` board-bind.sh stamps and board-transition.sh's fence compares."""
    return "api:" + api_url()


def meta_is_mine(meta, board, repo_key=""):
    """Does this daemon-registry meta belong to the binding the caller holds?

    $DAEMON_HOME is machine-global while a board is not, so EVERY scan over it
    has to ask — a scan that does not is acting on a neighbour's workers.

    Two dimensions, because neither settles it alone: `board` names the
    SERVICE (`api:<url>`, or `gh:<owner/name>`), and two repos served by one
    api service share it; `board_repo` names the repo within that service, and
    two services could each call a repo `docs`. gh mode passes no repo_key —
    there the owner/name inside `board` is already the whole identity.

    PURE, and takes the identity rather than reading it: these scans run under
    both bindings, several of them in scripts that never resolve an api url at
    all, so a version that read the environment would either die there or
    quietly compare against nothing.

    A meta missing EITHER field is legacy — written before that field existed —
    and is read as the caller's. That is the safe direction: skipping an
    unstamped meta would strand a live run with no renewal, no relay and no
    answer, while honouring one costs nothing on a machine whose only stamped
    metas belong to somebody. Every meta written from now on carries both.
    """
    mboard = str(meta.get("board") or "").strip()
    if mboard and board and mboard.rstrip("/") != str(board).rstrip("/"):
        return False
    mrepo = str(meta.get("board_repo") or "").strip()
    return not (mrepo and repo_key) or mrepo == repo_key


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


def _registry_root():
    """The seat registry, by the ONE rule the sminos CLI and _lib.sh apply:
    $SMINOS_HOME, then $DAEMON_HOME, then the default. Resolved here rather
    than taken from a caller because this module is reached from shells that
    never sourced _lib.sh (a bare `python3 -c` in a worker's own hands).

    A root overridden only in a dispatcher's own process never reaches the
    worker it spawns, so the worker reads the default one — which is sminos's
    own standing assumption, not a new exposure this adds: the spawn preamble
    has every worker run `sminos topology`/`post`/`status` from its own shell,
    and those resolve the root by this same rule. An override has to be
    machine-wide (a shell profile, a launchd environment) for the fleet to work
    at all, and where it is, self-location reads exactly what sminos wrote.
    """
    return (os.environ.get("SMINOS_HOME") or os.environ.get("DAEMON_HOME")
            or os.path.join(os.path.expanduser("~"), ".claude", "sminos"))


_OWN_SEAT = {}          # per-process memo: this session's record, found once
_SEAT_POLL = 0.5        # the bind lands in one write; this only has to notice
_SEAT_BIND_WAIT = 30.0  # seconds, from the RECORD's last write — see own_seat
# The role literals a board dispatcher launches a seat with. Both dispatchers
# pass `--role` to `sminos spawn`, so the record carries one from BIRTH — before
# any bind — and that is the only thing on a pre-bind record that says whether
# this session was spawned to do run work or is somebody's own. The same four
# strings the post-bind stamps write, so the field never changes value; they are
# already the shared vocabulary board-answer and the sweep read roles back by.
_DISPATCH_ROLES = ("IMPLEMENT", "ARCHITECT", "SPIKE", "QAGENT")


def _is_dispatch_seat(rec):
    return str(rec.get("role") or "").strip() in _DISPATCH_ROLES


def _seat_bind_wait():
    try:
        v = float(os.environ.get("BOARD_SEAT_BIND_WAIT") or _SEAT_BIND_WAIT)
    except ValueError:
        return _SEAT_BIND_WAIT
    return max(0.0, v)


def _seat_of_session(session):
    """(seat id, record, mtime) for THIS session — or None. The BOARD is not
    examined here: a record can name this session before it names any board,
    and telling those two absences apart is the whole of the wait below."""
    prefix_hit = None
    root = _registry_root()
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return None
    for name in names:
        if not name.endswith(".json") or name.endswith(".reply.json"):
            continue
        path = os.path.join(root, name)
        try:
            with open(path) as f:
                rec = json.load(f)
            mtime = os.stat(path).st_mtime
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict):
            continue
        if str(rec.get("current") or "") == session:
            return (name[:-5], rec, mtime)   # the exact match always wins
        short = str(rec.get("short") or "")
        if short and prefix_hit is None and session.startswith(short):
            prefix_hit = (name[:-5], rec, mtime)
    return prefix_hit


def _seat_verdict(rec, board, repo_key):
    """`mine`, `pending` or `no`, for a record that IS this session's.

    THE BOARD KEY IS THE WHOLE CLOCK. board-bind.sh writes `board`,
    `board_repo`, `run_id`, `fence`, `run_bearer` and `bind_confirmed` in ONE
    locked write, so under an api binding a record naming no board is a bind
    that has not landed yet — and one naming this board without a confirmation
    is a bind that has been UNDONE, which is the end-of-run strip
    (`_retire_run_locally` pops the run, the bearer, the fence and the
    confirmation and leaves `board` standing). The first is worth waiting for;
    the second is over, and waiting on it would only delay the fall-back that
    is already the right answer.

    A `pending` verdict that never resolves is not always survivable, and
    own_seat decides that by asking whose seat it is — see the fail-closed rule
    there.

    `no` also covers this session bound somewhere that is not this checkout.
    The url names the SERVICE, and one instance serves several repos out of one
    ticket namespace, so the url alone does not separate them: a record stamped
    for a neighbour repo would otherwise have this checkout's verbs acting on
    that repo's run. The repo is compared only when the caller HAS one — the
    repo-less-head fallback in _binding.sh asks this question precisely because
    it does not — and only when the record carries one, since a bind predating
    dp#33 stamped no repo and is still this session's own.
    """
    stamped = str(rec.get("board") or "").rstrip("/")
    if not stamped:
        return "pending"
    if stamped != board:
        return "no"
    mrepo = str(rec.get("board_repo") or "").strip()
    if repo_key and mrepo and mrepo != repo_key:
        return "no"
    if rec.get("bind_confirmed") and str(rec.get("run_bearer") or ""):
        return "mine"
    return "no"


def own_seat():
    """This session's OWN seat record on THIS board — (seat id, record) — or
    None.

    A worker's shells are handed nothing: `claude --bg` drops the dispatcher's
    whole spawn env prefix (measured twice, harness v2.1.261), so the bearer,
    the run id and the fence never reach the process that needs them. What DOES
    survive is $CLAUDE_CODE_SESSION_ID — and that is the very key the dispatcher
    already indexed the run by: `sminos spawn` writes the record's `short` (the
    launch banner's 8 hex) and then `current` (the full uuid), and board-bind.sh
    stamps run_id, fence, run_bearer, bind_confirmed, board and board_repo onto
    it. Everything the prefix was meant to deliver is on disk under a name the
    worker can read off its own environment.

    `current` is the exact match and wins; `short` is a PREFIX of the session
    uuid, which is all a worker has in the seconds before the uuid poll returns.

    THE BIND CAN STILL BE IN FLIGHT. execute-dispatch.sh spawns the worker and
    binds it afterwards, and the executor lane has no startup barrier to hold
    the worker in the meantime — so a worker's first board command can land
    between the two writes and find a record that names no board yet. Resolving
    `None` there is the very failure this mechanism exists to remove, one race
    narrower. So: no record for this session at all is an answer, returned at
    once; a record whose bind has not landed is a bind to WAIT for.

    A BIND THAT NEVER LANDS IS NOT ALWAYS A FALL-BACK. The dispatcher can die
    between the spawn and the bind: the claim is outstanding, the worker is
    live, and its record stays pre-bind forever. Falling back there is the worst
    answer available — the worker's human-defaulted verbs would act as the
    OPERATOR, unfenced, on a ticket a claimed run still owns, and a
    wrong-principal write cannot be taken back. So a seat the DISPATCHER
    launched (`role` is one of _DISPATCH_ROLES, written by `sminos spawn
    --role` before any bind) refuses to act as anyone at all once its wait is
    spent. A seat nobody dispatched — an operator's own joined session — has no
    run to fail closed on and keeps the ordinary fall-back.

    The budget is measured from the RECORD's last write, not from the caller's
    clock, and that is what keeps an ordinary shell fast. An operator's own
    joined seat is byte-indistinguishable from a pre-bind one — sminos writes no
    board key for either — so the only thing separating "a bind is in flight"
    from "this seat is not a board worker" is how long ago somebody wrote it. A
    record older than the budget cannot be mid-handover, and is not waited on.
    $BOARD_SEAT_BIND_WAIT tunes it; 0 disables the wait entirely.

    The BOARD guard is strict here, unlike meta_is_mine's: the registry is
    machine-global, and a record that names a different service — or a different
    repo on the same one — is not evidence that this checkout's board handed
    this session a run. meta_is_mine reads an unstamped record as the caller's
    because SKIPPING one there would strand a live run with no renewal; here the
    safe direction is the opposite one, since adopting the wrong record makes
    every verb act as a principal nobody chose.

    $BOARD_NO_SELF_LOCATE is a process saying it is not its session: the two
    dispatchers and the sweep declare it ahead of the binding they resolve (THE
    TICK IS AUTOMATION, FULL STOP), because a tick launched from a worker's own
    session would otherwise act as that worker. It shuts the whole record off,
    the repo key included — a tick has its own binding to read one from, and a
    neighbour's record is not it. It cannot reach a spawned worker as a
    suppression: that worker either loses the entire env prefix, which takes
    this with it, or keeps it and keeps the explicit bearer beside it, which is
    resolved first.
    """
    if "v" in _OWN_SEAT:
        return _OWN_SEAT["v"]
    _OWN_SEAT["v"] = None
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    board = "api:" + os.environ.get("BOARD_API_URL", "").rstrip("/")
    if not session or board == "api:" or os.environ.get("BOARD_NO_SELF_LOCATE"):
        return None
    repo_key = os.environ.get("BOARD_REPO", "").strip()
    hit = _seat_of_session(session)
    if hit is None:
        return None
    verdict = _seat_verdict(hit[1], board, repo_key)
    if verdict == "pending":
        deadline = hit[2] + _seat_bind_wait()
        while verdict == "pending" and time.time() < deadline:
            time.sleep(_SEAT_POLL)
            again = _seat_of_session(session)
            if again is None:
                break            # the record went away; there is nothing to wait for
            hit = again
            verdict = _seat_verdict(hit[1], board, repo_key)
    if verdict != "mine" and verdict != "pending":
        return None
    if verdict == "pending" and _is_dispatch_seat(hit[1]):
        die("this session was spawned for run work (role %s) and its bind never "
            "landed, so it holds no run to speak as — refusing to act as any "
            "other principal on a ticket a claimed run still owns. The "
            "reconciler retires an unbound worker and releases its run; there "
            "is nothing to do here but stop."
            % str(hit[1].get("role") or "").strip())
    # An undispatched seat's unlanded bind is returned as it stands:
    # run_context() reads no bearer on it and falls back, which is the same
    # answer as no record at all — reached the slow way, once, because it was
    # worth waiting to be sure.
    _OWN_SEAT["v"] = (hit[0], hit[1])
    return _OWN_SEAT["v"]


_RUN_CTX = {}    # per-process memo: resolved once, logged once


def run_context():
    """The run this process speaks as — {bearer, run_id, fence} — or None.

    Resolution order, once per process:

      1. an explicit BOARD_RUN_TOKEN (with BOARD_RUN_ID / BOARD_RUN_FENCE).
         The dispatchers' and the sweep's per-command prefix, and a foreground
         harness that keeps env. Consulted FIRST, so a bearer the caller just
         handed can never be displaced by a record.
      2. this session's own seat record, if its bind confirmed and it still
         holds a bearer. That is the channel `claude --bg` actually delivers.
      3. neither — no run context at all, which is an ordinary operator shell.

    Rule 2 is own_seat(), so $BOARD_NO_SELF_LOCATE closes it here too.
    """
    if "v" in _RUN_CTX:
        return _RUN_CTX["v"]
    _RUN_CTX["v"] = None
    run_tok = os.environ.get("BOARD_RUN_TOKEN", "")
    if run_tok:
        _RUN_CTX["v"] = {"bearer": run_tok,
                         "run_id": os.environ.get("BOARD_RUN_ID", "") or None,
                         "fence": os.environ.get("BOARD_RUN_FENCE", "") or None}
        return _RUN_CTX["v"]
    found = own_seat()
    if not found:
        return None
    seat_id, rec = found
    bearer = str(rec.get("run_bearer") or "")
    run_id = str(rec.get("run_id") or "")
    # A record whose bind never confirmed names a run the server may never have
    # given this session, and one stripped of its bearer is a run that ENDED —
    # the sweep's _retire_run_locally pops both the moment it posts /end.
    # Either way the answer is "no run", never a 401 on every verb after it.
    if not bearer or not run_id or not rec.get("bind_confirmed"):
        return None
    # ONE line, on stderr, once: a transcript should show which principal acted.
    # The run and the seat say that; the bearer would only put a live credential
    # into a log nobody meant to write.
    print("speaking as run %s via seat %s" % (run_id, seat_id), file=sys.stderr)
    _RUN_CTX["v"] = {"bearer": bearer, "run_id": run_id,
                     "fence": str(rec.get("fence") or "") or None}
    return _RUN_CTX["v"]


def token(principal):
    """principal: 'auto' (run token or die), 'automation', 'human'."""
    ctx = run_context()
    if ctx:                          # a run context always speaks as the run
        return ctx["bearer"]
    if principal == "auto":
        die("no BOARD_RUN_TOKEN in env, and this session's seat record carries "
            "no confirmed bind to speak for — and the caller demanded the run "
            "principal; this verb is worker-context-only here")
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
    it cannot read. token() speaks as the run whenever this process HAS
    a run context, so the refusal is deterministic — die here, before any
    request, with the reason instead of a bare `forbidden`."""
    if run_context():
        die("%s is claim-gated for runs (arkho#12): this process speaks "
            "as its run and the server refuses q/include=body to run "
            "bearers — a run reads its statement of work from the claim "
            "payload" % what)


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
