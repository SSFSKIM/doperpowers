"""The claim verbs (D3): claim, release, takeover, close's respect for a
holder, held and settle, and the settle that `list` and `claim` run for
their board first.

A claim and a takeover go in one order, which is what makes a crash at any
point come out right: the session's thread asked of sminos (a definite
answer, or nothing is written), the pending row with its attempt token,
the read and fold, the append, the confirming read and fold, the outcome of
its own record at its place, the label and the look after it, the row held
or lapsed. A release: the record, the label and the look, the row."""
import datetime
import json
import os
import sys
import time

import board as B
import claims as C
import index as I
import record
import settle as S
import sminos_client as sminos
from common import FAILED, OK, REFUSED, failed, refused, usage
from github import GitHubError

SETTLE_EVERY = 600  # seconds: a board's pass that completed this recently is not run again before list or claim
SETTLE_DEADLINE = 20  # seconds the settle before list or claim may take
TRIES = 3  # appends of one claim, when the second of a reopening shuts the record out


# ── who is asking ─────────────────────────────────────────────────────────
def my_address(ctx):
    address = ctx.address()
    if address is None:
        raise failed("sminos gives no address for this session (no session id, no sminos, or a session it does "
                     "not know): a claim belongs to a session sminos knows; nothing was written")
    return address


def my_thread(ctx):
    """The calling session's thread id ("": sminos says it is no thread),
    from a definite answer only: one that names this very session as its
    thread's current one, on this machine. Asked once a run."""
    if getattr(ctx, "_thread", None) is not None:
        return ctx._thread
    sid = sminos.session_id()
    if not sid:
        raise failed("no session id in the environment: a claim belongs to a session sminos knows; nothing was "
                     "written")
    answer, why = sminos.thread(sid)
    if answer is None:
        raise failed("sminos gave no answer about this session's thread (%s): nothing was written" % why)
    if answer["session"] != sid or not answer["local"]:
        raise failed("sminos answered about another session than this one, or of another machine: this session's "
                     "thread is not known, and nothing was written")
    if answer["ended"]:
        raise failed("sminos says this session's thread has ended: a claim of it would be released by the next "
                     "settle; nothing was written")
    ctx._thread = answer["thread"]
    return ctx._thread


def holds(ctx, t, holder):
    """Whether the calling session's thread holds `holder` (D3, Takeover):
    where this machine has the claim's row (by its id, or by its attempt
    token for a row still pending), the row's thread decides (for a row
    with no thread, its session); the address only where it has none."""
    row = I.row_of_holder(I.read(), t.repo, t.number, holder)
    if row is not None:
        if row["thread"]:
            return my_thread(ctx) == row["thread"]
        return sminos.session_id() == row["session"]
    address = ctx.address()
    if address is None:
        raise failed("sminos gives no address for this session, so whether it holds #%d cannot be told"
                     % t.number)
    return address == holder.holder


def ago(stamp):
    seconds = int(I.age(stamp).total_seconds())
    if seconds < 0:
        return "just now"
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    return ("%dd %dh" % (days, hours) if days else "%dh %dm" % (hours, minutes) if hours else "%dm" % minutes) + " ago"


def holder_text(t, holder=None):
    """The holder with its age and the linked activity: what lets a reader
    judge a claim that has gone quiet."""
    h = holder or t.holder
    out = "%s (claim %d, since %s, %s)" % (h.holder, h.id, h.created, ago(h.created))
    activity = []
    for l in t.linked:
        if l["kind"] == "pr":
            activity.append("pull request #%d %s, updated %s" % (l["number"], l["state"], l["updated"]))
        else:
            activity.append("branch %s, last commit %s" % (l["name"], l["updated"] or "unknown"))
    return out + "; linked: " + ("; ".join(activity) if activity else "nothing")


# ── the test seams of acceptance 23 ───────────────────────────────────────
def _trace(read, t, own=None):
    """TASK_TRACE: a file that receives what each of the claim's reads saw."""
    path = os.environ.get("TASK_TRACE")
    if not path:
        return
    line = {"pid": os.getpid(), "read": read, "repo": t.repo, "number": t.number, "own": own,
            "claims": [r.id for r in t.fold.records if r.op == "claim"],
            "holder": t.holder.id if t.holder else None}
    with open(path, "a") as f:
        f.write(json.dumps(line) + "\n")


def _barrier(suffix):
    """TASK_CLAIM_BARRIER: a file the claim waits for, at most a minute,
    after its first read found the ticket unheld (and the file with
    `.confirmed` after its confirming read)."""
    path = os.environ.get("TASK_CLAIM_BARRIER")
    if not path:
        return
    trace = os.environ.get("TASK_TRACE")
    if trace:  # arrived: every call before the append (the label's discovery among them) is behind it
        with open(trace, "a") as f:
            f.write(json.dumps({"pid": os.getpid(), "read": "at-barrier" + suffix}) + "\n")
    deadline = time.monotonic() + 60
    while not os.path.exists(path + suffix):
        if time.monotonic() > deadline:
            raise failed("the claim's barrier %s was not released within a minute" % (path + suffix))
        time.sleep(0.02)


# ── the settle before list and claim, and the owed releases ───────────────
def _alive(run):
    try:
        os.kill(int(run["pid"]), 0)
    except (OSError, ValueError, KeyError):
        return False
    return I.age(run.get("at")).total_seconds() < 600


def housekeep(ctx, regular):
    """This machine's housekeeping on the verb's board, and no other
    board's: its owed releases first (each on sminos's word of this
    moment), then, with `regular`, the settle of every row, unless a pass
    over them completed within TASK_SETTLE_EVERY (ten minutes). One budget
    (20 s; TASK_SETTLE_DEADLINE for tests) bounds every call of it, under
    the board's running mark, so that two verbs started together run one.
    Run once a verb's preflight has passed (its arguments; for `claim` and
    `takeover` the session's address and thread; for `release` and `close`
    the holder judged on a read; for `migrate apply` the plan), so a verb
    that refuses on that first judgment has written nothing, and before it
    reads what it acts on. A verb whose judgment housekeeping can change
    judges again after it ran: a refusal then has written no record of its
    own, though housekeeping may have written an owed release. Its failure, its bookkeeping's among it, goes to stderr and fails
    nothing. Whether a pass ran (and may have written)."""
    repo = ctx.repo
    key = I.board_key(repo)
    every = float(os.environ.get("TASK_SETTLE_EVERY") or SETTLE_EVERY)
    try:
        with I.locked() as data:
            rows = [r for r in data["rows"] if r["repo"].lower() == key and r["state"] != I.LAPSED]
            last = data["settled"].get(key)
            due = regular and bool(rows) and not (last and I.age(last).total_seconds() < every)
            owed = any(r["state"] == I.OWED for r in rows)
            if not (due or owed):
                return False
            running = data["running"].get(key)
            if running and _alive(running):
                return False
            data["running"][key] = {"pid": os.getpid(), "at": I.now()}
    except Exception as e:  # noqa: BLE001 — an unreadable index fails no verb
        sys.stderr.write("task: the settle of %s's claims did not run: %s\n" % (repo, getattr(e, "message", e)))
        return False
    complete = set()
    try:
        budget = float(os.environ.get("TASK_SETTLE_DEADLINE") or SETTLE_DEADLINE)
        states = (I.PENDING, I.HELD, I.OWED) if due else (I.OWED,)
        report, complete = S.run(ctx.client, repo=repo, deadline=time.monotonic() + budget, states=states,
                                 verified=(repo,))  # the verb has read its board's configuration
        for u in report["unreachable"]:
            sys.stderr.write("task: the settle of %s's claims stopped: %s\n" % (u["repo"], u["said"]))
    except Exception as e:  # noqa: BLE001 — the verb goes on whatever the settle met
        sys.stderr.write("task: the settle of %s's claims failed: %s\n" % (repo, getattr(e, "message", e)))
    try:
        with I.locked() as data:
            if (data["running"].get(key) or {}).get("pid") == os.getpid():
                del data["running"][key]
            if due and any(I.board_key(b) == key for b in complete):
                data["settled"][key] = I.now()
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("task: the settle of %s's claims could not be recorded: %s\n"
                         % (repo, getattr(e, "message", e)))
    return True


def auto_settle(ctx):
    """The housekeeping of `list` and `claim`: owed releases, then the
    board's settle when it is due."""
    return housekeep(ctx, regular=True)


def retry_owed(ctx):
    """The housekeeping of every other verb that writes to GitHub: the
    releases this machine owes on its board."""
    return housekeep(ctx, regular=False)


def report_lapsed():
    """One line on stderr for each lapsed row, less than seven days old,
    that the calling session made: what a returning thread reads."""
    sid = sminos.session_id()
    if not sid:
        return
    try:
        rows = I.read()["rows"]
    except Exception:  # noqa: BLE001 — a warning, never a failure
        return
    for r in rows:
        if r["session"] == sid and r["state"] == I.LAPSED and I.age(r["at"]) < I.LAPSED_KEPT:
            sys.stderr.write("task: your claim on %s#%d lapsed (%s, %s): claim it again before you continue\n"
                             % (r["repo"], r["number"], r["reason"] or "ended", r["at"]))


# ── claim ─────────────────────────────────────────────────────────────────
class Result:
    def __init__(self, code, text):
        self.code, self.text = code, text


def _wait_past(reopened):
    """Until the second of the reopening has passed on this machine's clock."""
    while datetime.datetime.now(datetime.timezone.utc) < reopened + datetime.timedelta(seconds=1.2):
        time.sleep(0.1)


def _lapse_reason(other):
    return "taken-over" if other is not None and other.op == "takeover" else "forced"


def _ended_by(other):
    return other.describe() if other is not None else "a later record"


def _append_and_confirm(ctx, t, token, body):
    """Append a record and read again: (its id, the confirming read). An
    append GitHub refused leaves nothing; one whose answer was never heard
    may have landed, so its pending row stays for settle to find."""
    try:
        made = ctx.client.comment(t.repo, t.number, body)
    except GitHubError as e:
        if e.refused:
            I.remove(token)
            raise failed("GitHub refused the record on #%d: %s" % (t.number, e.message))
        raise failed("the record on #%d had no answer (%s): it may have landed; the next settle finds it by its "
                     "token" % (t.number, e.message))
    own = int(made["id"])
    try:
        return own, S.read(ctx.client, ctx.client.login(), t.repo, t.number)
    except GitHubError as e:
        raise failed("the record on #%d was written (comment %d) and the confirming read failed (%s): the next "
                     "settle settles it" % (t.number, own, e.message))


def _claim_one(ctx, number, address, thread):
    repo, session = ctx.repo, sminos.session_id()
    token = C.mint()
    template = I.new_row(repo, number, "", "", token, session, thread, address)
    I.add(template)
    appended = False
    try:
        for attempt in range(TRIES):
            t = ctx.ticket(number)
            I.change(token, title=t.node["title"], url=t.node["url"])
            template.update(title=t.node["title"], url=t.node["url"])
            _trace("first", t)
            if t.state != "open":
                I.remove(token)
                return Result(REFUSED, "#%d is closed: a closed ticket is not claimed" % number)
            if t.holder is not None:
                if holds(ctx, t, t.holder):
                    I.remove(token)
                    S.converge(ctx.client, t.login, t)
                    return Result(OK, "#%d: already yours (claim %d)" % (number, t.holder.id))
                I.remove(token)
                return Result(REFUSED, "#%d is held by %s" % (number, holder_text(t)))
            unmet = [r for r in t.not_takeable(lambda: address) if r not in ("closed", "held")]
            ctx.client.ensure_labels(repo, {B.CLAIMED: B.label_spec(B.CLAIMED)})
            _barrier("")
            appended = True
            own, t2 = _append_and_confirm(ctx, t, token, C.compose("claim", holder=address, attempt=token))
            _trace("confirm", t2, own)
            _barrier(".confirmed")
            kind, other = t2.fold.outcome(own)
            if kind in (C.CURRENT, C.SUPERSEDED):
                # It took effect. The label and the look; then the outcome is judged on the last read, since a
                # takeover or a release may have landed by then.
                last = S.converge(ctx.client, t.login, t2)
                kind, other = last.fold.outcome(own)
                # A loss is applied from any state not yet final: a settle may have made the row held meanwhile.
                pending = (I.PENDING,)
                if kind == C.CURRENT:
                    I.change(token, expect=pending, state=I.HELD, claim=own, since=last.fold.by_id(own).created)
                    note = ("; it is not takeable on a session's own initiative (%s)" % ", ".join(unmet)) if unmet else ""
                    return Result(OK, "#%d: claimed (claim %d)%s" % (number, own, note))
                if kind == C.SUPERSEDED:
                    I.change(token, expect=I.ACTIVE, state=I.LAPSED, reason=_lapse_reason(other), claim=own,
                             since=last.fold.by_id(own).created)
                    return Result(REFUSED, "#%d: the claim (%d) took effect and was then ended by %s: it was taken "
                                           "on purpose, so it is not claimed again" % (number, own, _ended_by(other)))
                if kind != C.MISSING:  # closed, or closed and reopened, since it took effect
                    I.remove(token, expect=I.ACTIVE)
                    return Result(REFUSED, "#%d: the claim (%d) took effect and the ticket was closed since"
                                  % (number, own))
            if kind == C.MISSING:
                return Result(FAILED, "#%d: the confirming read did not show this claim's own record (comment %d): "
                                      "the next settle settles it by its token" % (number, own))
            ctx.client.delete_comment(repo, own)
            if kind == C.SHUT_OUT and attempt + 1 < TRIES:
                _wait_past(t2.fold.reopened)
                new = C.mint()
                I.renew(token, new, template)  # the next try's pending row, written again if a settle removed it
                token, appended = new, False
                continue
            S.converge(ctx.client, t.login, t2)
            I.remove(token)
            if kind == C.VOID:
                return Result(REFUSED, "#%d was claimed first by %s" % (number, holder_text(t2, other))
                              if other else "#%d: the claim met no holder and was void" % number)
            return Result(REFUSED, "#%d was closed, or closed and reopened, as the claim landed: claim it again if "
                                   "it is open" % number)
        return Result(FAILED, "#%d: every try was shut out by a reopening of the same second" % number)
    except Exception:
        if not appended:
            I.remove(token)
        raise


def claim(ctx):
    a = ctx.args
    if bool(a.numbers) == (a.batch is not None):
        raise usage("task claim takes ticket numbers, or --batch NAME")
    address = my_address(ctx)
    thread = my_thread(ctx)
    auto_settle(ctx)
    numbers = list(a.numbers)
    if a.batch is not None:
        try:
            nodes = ctx.client.open_issues(ctx.repo)
        except GitHubError as e:
            raise failed(e.message)
        label = B.BATCH_PREFIX + a.batch
        numbers = sorted(n["number"] for n in nodes if label in [l["name"] for l in n["labels"]["nodes"]])
        if not numbers:
            raise refused("no open ticket carries %s" % label)
    results = []
    for n in numbers:
        try:
            results.append((n, _claim_one(ctx, n, address, thread)))
        except Exception as e:  # noqa: BLE001 — one ticket's failure is reported, and the others go on
            if len(numbers) == 1:
                raise
            results.append((n, Result(getattr(e, "code", FAILED), getattr(e, "message", None) or str(e))))
    report_lapsed()
    if len(results) == 1:
        r = results[0][1]
        if r.code == OK:
            print(r.text)
            return
        raise _stop(r)
    won = [n for n, r in results if r.code == OK]
    for n, r in results:
        print("%s %s" % ("won " if r.code == OK else "lost", r.text))
    print("won: %s" % (", ".join("#%d" % n for n in won) or "none"))
    codes = [r.code for _, r in results]
    if FAILED in codes:
        raise _stop(Result(FAILED, ""))
    if REFUSED in codes:
        raise _stop(Result(REFUSED, ""))


def _stop(result):
    return (failed if result.code == FAILED else refused)(result.text)


# ── release, takeover, close ──────────────────────────────────────────────
def _force_reason(text, flag="--force"):
    if text is None:
        return None
    if not text.strip() or not record.one_line(text):
        raise usage("%s takes a reason: one non-empty line" % flag)
    return C.FORCED + text.strip()


def _release_check(ctx, a, forced, again=False):
    """Read the ticket and judge the release: (the ticket, its holder), or
    the refusal. Before housekeeping a refusal has written nothing; `again`
    (after housekeeping wrote) it has written no release of this one."""
    unwritten = "no bound release was written" if again else "nothing was written"
    t = ctx.ticket(a.number)
    if t.state != "open":
        raise refused("#%d is closed: its close ended every claim, and there is nothing to release" % a.number)
    h = t.holder
    if h is None:
        raise refused("#%d is unheld: there is nothing to release" % a.number)
    if a.of is not None and h.id != a.of:
        raise refused("claim %d does not hold #%d: it is held by %s; %s" % (a.of, a.number, holder_text(t),
                                                                          unwritten))
    if forced is None and not holds(ctx, t, h):
        raise refused("#%d is held by %s, not by this session's thread: the holder releases its own claim, and "
                      "anyone else gives %s" % (a.number, holder_text(t), ctx.cmd(
                          'release %d --force "<reason>"' % a.number)))
    return t, h


def release(ctx):
    from verbs import read_body_file
    a = ctx.args
    if a.of is not None and a.force is None:
        raise usage("--of binds a forced release to one claim: give it with --force")
    forced = _force_reason(a.force)
    prose = read_body_file(a.body_file) if a.body_file is not None else None
    # Judged before the housekeeping writes anything, and again after it if it ran: it can change the holder.
    t, h = _release_check(ctx, a, forced)
    if retry_owed(ctx):
        t, h = _release_check(ctx, a, forced, again=True)
    row = I.row_of_holder(I.read(), t.repo, t.number, h)
    try:
        kind, other, _ = S.write_release(ctx.client, t.login, t.repo, t.number, h.id, forced or "released", prose)
    except GitHubError as e:
        raise failed("the release of #%d: %s" % (a.number, e.message))
    if kind == C.MISSING:
        raise failed("#%d: the release was written and the confirming read did not show it: read the ticket with "
                     "%s before writing again" % (a.number, ctx.cmd("show %d" % a.number)))
    if kind == C.CLOSED:
        raise refused("#%d was closed as the release landed: the close ended claim %d, and the release record "
                      "stays, of no effect" % (a.number, h.id))
    if kind == C.OUTSIDE:
        raise refused("#%d was closed and reopened as the release landed: claim %d ended with the close, and the "
                      "release record stays, of no effect" % (a.number, h.id))
    if kind != C.CURRENT:
        if row is not None:
            I.lapse(row["attempt"], _lapse_reason(other), expect=(row["state"],))
        raise refused("#%d: claim %d was ended first (%s): this release was void and is deleted"
                      % (a.number, h.id, _ended_by(other)))
    if row is not None:
        if forced is None:
            I.remove(row["attempt"], expect=(row["state"],))
        else:
            I.lapse(row["attempt"], "forced", expect=(row["state"],))
    print("#%d: released (claim %d%s)" % (a.number, h.id, ", " + forced if forced else ""))


def takeover(ctx):
    a = ctx.args
    forced = _force_reason(a.force)
    address = my_address(ctx)
    thread = my_thread(ctx)
    retry_owed(ctx)
    repo, session, number = ctx.repo, sminos.session_id(), a.number
    token = C.mint()
    I.add(I.new_row(repo, number, "", "", token, session, thread, address))
    appended = False
    try:
        t = ctx.ticket(number)
        I.change(token, title=t.node["title"], url=t.node["url"])
        h = t.holder
        if t.state != "open" or h is None:
            I.remove(token)
            raise refused("#%d is %s: there is no claim to take over; %s" % (
                number, "closed" if t.state != "open" else "unheld", ctx.cmd("claim %d" % number)))
        if holds(ctx, t, h):
            I.remove(token)
            print("#%d: already yours (claim %d)" % (number, h.id))
            return
        left = I.row_of_holder(I.read(), repo, number, h)
        grant = left if left is not None and left["state"] == I.HELD and left["successor"] == session else None
        if forced is None and grant is None:
            I.remove(token)
            raise refused("#%d is held by %s, and no /clear granted this session its takeover: taking a live "
                          "thread's ticket is the owner's call, with %s"
                          % (number, holder_text(t), ctx.cmd('takeover %d --force "<reason>"' % number)))
        ctx.client.ensure_labels(repo, {B.CLAIMED: B.label_spec(B.CLAIMED)})
        appended = True
        own, t2 = _append_and_confirm(ctx, t, token, C.compose(
            "takeover", holder=address, attempt=token, of=str(h.id), reason=forced or "cleared"))
        kind, other = t2.fold.outcome(own)
        if kind in (C.CURRENT, C.SUPERSEDED):
            # It took effect, ending the claim it named. The label and the look; then the outcome on the last read.
            if left is not None:
                I.lapse(left["attempt"], "taken-over", expect=(I.HELD, I.OWED))
            last = S.converge(ctx.client, t.login, t2)
            kind, other = last.fold.outcome(own)
            pending = (I.PENDING,)  # a loss, as for a claim, from any state not yet final
            if kind == C.CURRENT:
                I.change(token, expect=pending, state=I.HELD, claim=own, since=last.fold.by_id(own).created)
                print("#%d: taken over (claim %d, of %d, %s)" % (number, own, h.id, forced or "cleared"))
                return
            if kind == C.SUPERSEDED:
                I.change(token, expect=I.ACTIVE, state=I.LAPSED, reason=_lapse_reason(other), claim=own,
                         since=last.fold.by_id(own).created)
                raise refused("#%d: the takeover (%d) took effect and was then ended by %s" % (number, own,
                                                                                            _ended_by(other)))
            if kind != C.MISSING:
                I.remove(token, expect=I.ACTIVE)
                raise refused("#%d: the takeover (%d) took effect and the ticket was closed since" % (number, own))
        if kind == C.MISSING:
            raise failed("#%d: the confirming read did not show the takeover's own record (comment %d): the next "
                         "settle settles it by its token" % (number, own))
        ctx.client.delete_comment(repo, own)
        S.converge(ctx.client, t.login, t2)
        I.remove(token)
        raise refused("#%d: claim %d was no longer current when the takeover landed (%s): the takeover was void "
                      "and is deleted" % (number, h.id, "held by " + holder_text(t2) if t2.holder else "unheld"))
    except Exception:
        if not appended:
            I.remove(token)
        raise


def _close_check(ctx, a, forced):
    """Read the ticket and judge the close: (the ticket, its holder or
    None), or the refusal, with nothing written. An unheld ticket asks
    nothing of sminos."""
    t = ctx.ticket(a.number)
    h = t.holder
    if h is not None and forced is None and not holds(ctx, t, h):
        raise refused("#%d is held by %s, another thread: it closes its own ticket, and anyone else gives %s"
                      % (a.number, holder_text(t), ctx.cmd('close %d --force "<reason>"' % a.number)))
    return t, h


def close(ctx):
    from verbs import read_body_file
    a = ctx.args
    forced = _force_reason(a.force)
    text = read_body_file(a.body_file) if a.body_file is not None else None
    reason = "not_planned" if a.not_planned else "completed"
    t, h = _close_check(ctx, a, forced)
    if retry_owed(ctx):
        t, h = _close_check(ctx, a, forced)
    try:
        if text is not None:
            ctx.client.comment(ctx.repo, a.number, text)
        if h is not None and forced is not None:
            ctx.client.comment(ctx.repo, a.number, "Closed over the claim of %s (claim %d): %s"
                               % (h.holder, h.id, forced[len(C.FORCED):]))
        ctx.client.edit_issue(ctx.repo, a.number, state="closed", state_reason=reason)
    except GitHubError as e:
        raise failed(e.message)
    ended = I.row_of_holder(I.read(), t.repo, t.number, h) if h is not None else None
    try:
        S.converge(ctx.client, t.login, S.read(ctx.client, t.login, t.repo, t.number))
    except GitHubError as e:
        # The row of the claim the close ended stays: settle finds the ticket closed and repairs its label. With no
        # such row on this machine, nothing will visit it: the repair is the reader's.
        repair = "the next settle repairs it" if ended is not None else "repair it with %s" % ctx.cmd(
            "show %d" % a.number)
        sys.stderr.write("task: #%d is closed, and its claimed label could not be made to agree: %s (%s)\n"
                         % (a.number, e.message, repair))
    else:
        if ended is not None:  # the claim the close ended; any other row on the ticket is settle's to judge
            I.remove(ended["attempt"], expect=(ended["state"],))
    print("#%d closed, %s" % (a.number, reason.replace("_", " ")))


# ── held and settle: what sminos calls (§9) ───────────────────────────────
def _brief(row, *keys):
    return {k: row[k] for k in ("repo", "number", "title", "url") + keys}


def held(ctx):
    """`task held --session S [--thread T] [--cleared-from L] --json`,
    sminos's call (§9, frozen at M3's review): the index only, from any
    directory, exit 0 whenever it could answer."""
    a = ctx.args
    for flag in ("session", "thread", "cleared_from"):
        value = getattr(a, flag)
        if value is not None and not value.strip():
            raise usage("--%s takes an id" % flag.replace("_", "-"))
    with I.locked() as data:
        I.prune(data)
        if a.cleared_from:
            for r in data["rows"]:
                if r["thread"] == a.cleared_from and r["state"] == I.HELD:
                    r["successor"] = a.session
        rows = [dict(r) for r in data["rows"]]
    mine = [r for r in rows if a.thread and r["thread"] == a.thread]
    out = {"v": 1,
           # An owed row's claim stands on GitHub until its release is written: it is still held.
           "held": [_brief(r, "claim", "since") for r in mine if r["state"] in (I.HELD, I.OWED)],
           "lapsed": [dict(_brief(r), reason=r["reason"], at=r["at"]) for r in mine if r["state"] == I.LAPSED],
           "offered": [_brief(r, "claim", "since") for r in rows if r["state"] == I.HELD
                       and r["successor"] == a.session]}
    if a.json:
        print(json.dumps(out, indent=1))
        return
    lines = ["held: %s#%d %s (claim %d, since %s)" % (r["repo"], r["number"], r["title"], r["claim"], r["since"])
             for r in out["held"]]
    lines += ["lapsed: %s#%d %s (%s, %s): claim it again before you continue" % (
        r["repo"], r["number"], r["title"], r["reason"], r["at"]) for r in out["lapsed"]]
    lines += ["offered: %s#%d %s (claim %d): task takeover %d --repo %s" % (
        r["repo"], r["number"], r["title"], r["claim"], r["number"], r["repo"]) for r in out["offered"]]
    print("\n".join(lines) or "nothing held, lapsed or offered")


def settle(ctx):
    """`task settle [--thread T] --json`, sminos's call (§9, frozen at M3's
    review): from any directory, exit 0 whenever it could answer. The call
    states nothing about any thread: settle asks sminos about each itself,
    and `--thread` only limits the run to that thread's rows."""
    a = ctx.args
    if a.thread is not None and not a.thread.strip():
        raise usage("--thread takes a thread id")
    report, complete = S.run(ctx.client, thread=a.thread)
    if a.thread is None and complete:
        with I.locked() as data:
            for repo in complete:
                data["settled"][I.board_key(repo)] = I.now()
    if a.json:
        print(json.dumps(report, indent=1))
        return
    lines = ["released: %s#%d (claim %d, %s)" % (r["repo"], r["number"], r["claim"], r["reason"])
             for r in report["released"]]
    lines += ["closed: %s#%d" % (r["repo"], r["number"]) for r in report["closed"]]
    lines += ["lapsed: %s#%d (%s)" % (r["repo"], r["number"], r["reason"]) for r in report["lapsed"]]
    lines += ["unknown: %s#%d (claim %d, thread %s): sminos said %s" % (
        r["repo"], r["number"], r["claim"], r["thread"], r["said"]) for r in report["unknown"]]
    lines += ["unreachable: %s: %s" % (r["repo"], r["said"]) for r in report["unreachable"]]
    lines.append("owed: %d" % report["owed"])
    print("\n".join(lines))
