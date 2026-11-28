"""Settle (D3): the one routine that makes this machine's claims true, and
the two writes every writer of a claim record shares: the label made to
agree with the fold, and a release confirmed like a claim.

Settle takes no caller's word that a thread has ended: for each held row
with a thread id it asks sminos about that very id as it runs, and only an
answer carrying that id, of this machine, saying it has ended, releases.
Every call is only a trigger."""
import time

import board as B
import claims as C
import index as I
import sminos_client as sminos
from common import Stop
from github import GitHubError, OutOfTime

PENDING_KEPT = 3600  # seconds a pending row whose record is not found is kept
ENDED, LIVE, UNKNOWN = "ended", "live", "unknown"


# ── the label ─────────────────────────────────────────────────────────────
def _write_label(client, repo, number, on):
    if on:
        client.ensure_labels(repo, {B.CLAIMED: B.label_spec(B.CLAIMED)})
        client.add_label(repo, number, B.CLAIMED)
    else:
        client.remove_label(repo, number, B.CLAIMED)


def read(client, login, repo, number):
    return B.Ticket(repo, client.issue(repo, number), login)


def converge(client, login, t):
    """Make `claimed` show what the fold of `t` (the latest read) says, then
    look once more and correct it if the fold moved under the write. No
    order of label writes keeps the label right by itself: the look is what
    does. Returns the ticket as last read, its labels as left."""
    if t.label_agrees:
        return t
    _write_label(client, t.repo, t.number, t.holder is not None)
    look = read(client, login, t.repo, t.number)
    if not look.label_agrees:
        on = look.holder is not None
        _write_label(client, t.repo, t.number, on)
        look.labels = [l for l in look.labels if l != B.CLAIMED] + ([B.CLAIMED] if on else [])
    return look


# ── a release ─────────────────────────────────────────────────────────────
def lapse_reason(fold, claim):
    """§7's reason for a row whose claim the fold no longer names, from the
    record that ended it (None: its holder released it)."""
    ender = fold.ended_by.get(claim)
    if ender is None:
        return "forced"
    if ender.op == "takeover":
        return "taken-over"
    if ender.reason == "released":
        return None
    return "ended" if ender.reason == "ended" else "forced"


def write_release(client, login, repo, number, claim, reason, prose=None):
    """Append a release of `claim` and confirm it as a claim is confirmed:
    a release proved void at its place is deleted, and nothing else is (one
    the confirming read does not show, MISSING, stays for the next settle
    to find in the fold). Then the label and the look. (kind, the record
    it met, the ticket as last read)."""
    made = client.comment(repo, number, C.compose("release", prose, of=str(claim), reason=reason))
    t = read(client, login, repo, number)
    kind, other = t.fold.outcome(int(made["id"]))
    if kind in (C.VOID, C.SHUT_OUT):
        client.delete_comment(repo, int(made["id"]))
    return kind, other, converge(client, login, t)


# ── asking sminos ─────────────────────────────────────────────────────────
def asker(deadline=None):
    """Ask sminos once per thread id per run: (verdict, said). Under a
    deadline each question is cut to the time left, and one the deadline
    cut short is OutOfTime, not an answer."""
    cache = {}

    def ask(thread):
        if thread not in cache:
            timeout, bounded = sminos.TIMEOUT, False
            if deadline is not None:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise OutOfTime("the pass ran out of time before sminos was asked about %s" % thread)
                if left < timeout:
                    timeout, bounded = left, True
            answer, why = sminos.thread(thread, timeout)
            if answer is None and why == "timeout" and bounded:
                raise OutOfTime("the pass ran out of time while sminos was asked about %s" % thread)
            if answer is None:
                cache[thread] = (UNKNOWN, why.split(":")[0])
            elif answer["thread"] != thread:
                cache[thread] = (UNKNOWN, "another thread")
            elif not answer["local"]:
                cache[thread] = (UNKNOWN, "not local")
            else:
                cache[thread] = (ENDED if answer["ended"] else LIVE, "")
        return cache[thread]
    return ask


# ── the routine ───────────────────────────────────────────────────────────
def empty_report():
    return {"v": 1, "released": [], "closed": [], "lapsed": [], "owed": 0, "unknown": [], "unreachable": []}


def _selected(row, thread, repo, states):
    return (row["state"] in states and (thread is None or row["thread"] == thread)
            and (repo is None or row["repo"].lower() == repo.lower()))


def run(client, thread=None, repo=None, deadline=None, states=(I.PENDING, I.HELD, I.OWED)):
    """One pass over this machine's rows (of one thread, of one board, or
    all), least recently visited first. A `deadline` (a time.monotonic()
    value) bounds every call made in the pass; when it is reached each row
    keeps the state it had reached, and the board's pass is incomplete.
    (report, the boards whose every selected row was reached)."""
    report = empty_report()
    with I.locked() as data:
        I.prune(data)
        rows = [dict(r) for r in data["rows"] if _selected(r, thread, repo, states)]
    # Least recently visited first over every row, so that a pass resumes past a row whose read ran out of time;
    # among rows equally due, owed releases first.
    rows.sort(key=lambda r: (r["visited"], r["state"] != I.OWED))
    boards = []
    for r in rows:
        if r["repo"] not in boards:
            boards.append(r["repo"])
    ask = asker(deadline)
    complete = set()
    before, client.deadline = client.deadline, deadline
    try:
        try:
            login = client.login()
        except OutOfTime:
            boards = []  # the budget was spent before the pass began: incomplete, not unreachable
        except Stop as e:
            report["unreachable"] = [{"repo": b, "said": e.message} for b in boards]
            boards = []
        for b in boards:
            reached = True
            for row in (r for r in rows if r["repo"] == b):
                try:
                    _settle_row(client, login, b, row, ask, report)
                except OutOfTime:
                    reached = False
                    break
                except GitHubError as e:
                    report["unreachable"].append({"repo": b, "said": e.message})
                    reached = False
                    break
            if reached:
                complete.add(b)
    finally:
        client.deadline = before
    report["owed"] = sum(1 for r in I.read()["rows"] if r["state"] == I.OWED and _selected(r, thread, repo, (I.OWED,)))
    return report, complete


def _entry(row, **more):
    out = {"repo": row["repo"], "number": row["number"]}
    out.update(more)
    return out


def _settle_row(client, login, repo, row, ask, report):
    token, number = row["attempt"], row["number"]
    # Visited as it is reached, so that a pass whose budget runs out in this read resumes past it next time.
    I.change(token, visited=I.now())
    try:
        t = read(client, login, repo, number)
    except GitHubError as e:
        if not e.not_found or isinstance(e, OutOfTime):
            raise
        I.remove(token)  # the repository answered, and the issue is gone: no claim on it can stand
        report["closed"].append(_entry(row))
        return
    I.change(token, title=t.node["title"], url=t.node["url"])
    if t.state != "open":
        converge(client, login, t)
        I.remove(token)
        report["closed"].append(_entry(row))
        return
    if row["state"] == I.PENDING:
        row = _settle_pending(client, login, t, row, report)
        if row is None:
            return
    if t.holder is None or t.holder.id != row["claim"]:
        # Its claim was ended: by this machine's own release before a crash (an owed row, whose reason stands), by
        # its holder, or by another session's takeover or forced release. Nothing is asked.
        if row["state"] == I.OWED:
            reason = row["reason"] or "ended"
        else:
            reason = lapse_reason(t.fold, row["claim"])
        converge(client, login, t)
        if reason is None:
            I.remove(token)
            return
        I.lapse(token, reason)
        report["lapsed"].append(_entry(row, reason=reason))
        return
    t = converge(client, login, t)
    if not row["thread"]:
        if row["state"] == I.OWED:  # no thread to ask about, so no end to stand on
            I.change(token, state=I.HELD, reason="")
        return  # no thread (O4): no machine learns that it ended
    # An owed row's claim still stands: its release is written only on sminos's word of this moment, as any other.
    verdict, said = ask(row["thread"])
    if verdict == LIVE:
        if row["state"] == I.OWED:
            I.change(token, state=I.HELD, reason="")  # it returned before the release was written
        return
    if verdict != ENDED:
        report["unknown"].append(_entry(row, title=t.node["title"], url=t.node["url"], claim=row["claim"],
                                        thread=row["thread"], said=said))
        return
    I.change(token, state=I.OWED, reason="ended")
    _release(client, login, t, row, report)


def _release(client, login, t, row, report):
    """An owed row's release: the record, the label and the look, the row
    lapsed. A failure, or a release the confirming read does not show,
    leaves the row owed, for the next settle or writing verb on this board."""
    token = row["attempt"]
    try:
        kind, _, last = write_release(client, login, t.repo, t.number, row["claim"], "ended")
    except GitHubError:
        I.change(token, tries=row["tries"] + 1)
        raise
    if kind == C.MISSING:
        I.change(token, tries=row["tries"] + 1)
        return
    reason = "ended" if kind == C.CURRENT else (lapse_reason(last.fold, row["claim"]) or "ended")
    I.lapse(token, reason)
    if kind == C.CURRENT:
        report["released"].append(_entry(row, title=t.node["title"], url=t.node["url"], claim=row["claim"],
                                         reason="ended"))
    else:
        report["lapsed"].append(_entry(row, reason=reason))


def _settle_pending(client, login, t, row, report):
    """A row whose record was appended and never confirmed, on an open
    ticket: the record that carries its token is found, and the row follows
    its outcome. One in effect and current becomes held, and is returned
    to go on as any held row in the same pass; None when the row is done."""
    token = row["attempt"]
    rec = t.fold.by_attempt(token)
    if rec is None:
        if I.age(row["at"]).total_seconds() >= PENDING_KEPT:
            I.remove(token)
        return None
    kind, other = t.fold.outcome(rec.id)
    if kind == C.CURRENT:
        held = I.change(token, state=I.HELD, claim=rec.id, since=rec.created)
        return held
    if kind == C.SUPERSEDED:
        reason = lapse_reason(t.fold, rec.id) or "forced"
        I.change(token, claim=rec.id, since=rec.created)
        I.lapse(token, reason)
        converge(client, login, t)
        report["lapsed"].append(_entry(row, reason=reason))
    elif kind in (C.VOID, C.SHUT_OUT):
        client.delete_comment(t.repo, rec.id)
        I.remove(token)
        converge(client, login, t)
    else:  # of an earlier open interval: it may have taken effect there, so it stays
        I.remove(token)
        converge(client, login, t)
    return None
