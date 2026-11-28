"""The machine's index of the claims it wrote (D3, Interfaces §7):
`claims.json` in the plugin's home, one row per claim not yet seen to end.

It is one JSON file, rewritten by atomic replace under a lock held across
the read and the write, since several sessions of one machine claim at
once. The lock is never held across a call to GitHub or to sminos: a
caller reads, lets go, calls, and takes the lock again to write what it
learned, finding its row again by its attempt token. Beside the rows it keeps, per
board, when its last settle completed (`settled`) and a mark while a pass
runs there (`running`), so verbs started together run one."""
import contextlib
import datetime
import fcntl
import json
import os
import pathlib

from common import failed

LAPSED_KEPT = datetime.timedelta(days=7)
# The states of §7: a pending row's record is not yet confirmed; an owed row's release is due.
PENDING, HELD, OWED, LAPSED = "pending", "held", "owed", "lapsed"
ACTIVE = (PENDING, HELD, OWED)  # a row not yet settled for good


def home():
    return pathlib.Path(os.environ.get("TASK_HOME") or pathlib.Path.home() / ".claude" / "task")


def path():
    return home() / "claims.json"


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age(stamp):
    """How long ago a time of the index's (or of GitHub's) was."""
    if not stamp:
        return datetime.timedelta.max
    then = datetime.datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc) - then


def _empty():
    return {"v": 1, "settled": {}, "running": {}, "rows": []}


def _load():
    p = path()
    try:
        text = p.read_text()
    except FileNotFoundError:
        return _empty()
    except OSError as e:
        raise failed("the index %s cannot be read: %s" % (p, e.strerror))
    try:
        data = json.loads(text)
    except ValueError:
        raise failed("the index %s is not JSON: task leaves it as it is (move it aside to start a new one)" % p)
    if not isinstance(data, dict) or data.get("v") != 1 or not isinstance(data.get("rows"), list):
        raise failed("the index %s is not an index of this version (v 1)" % p)
    data.setdefault("settled", {})
    data.setdefault("running", {})
    return data


def _save(data):
    p = path()
    tmp = p.with_name(p.name + ".%d.tmp" % os.getpid())
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    os.replace(str(tmp), str(p))


@contextlib.contextmanager
def locked():
    """The index, to change: written back when the block ends without an
    error."""
    h = home()
    h.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(h / "claims.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        data = _load()
        before = json.dumps(data, sort_keys=True)
        yield data
        if json.dumps(data, sort_keys=True) != before:
            _save(data)
    finally:
        os.close(fd)


def read():
    """The index as it stands (a snapshot: replace is atomic, so no lock)."""
    return _load()


def new_row(repo, number, title, url, attempt, session, thread, address):
    t = now()
    return {"repo": repo, "number": number, "title": title, "url": url, "claim": None, "attempt": attempt,
            "session": session, "thread": thread, "address": address, "since": t, "successor": "",
            "state": PENDING, "reason": "", "at": t, "visited": "", "tries": 0}


def find(data, attempt):
    return next((r for r in data["rows"] if r["attempt"] == attempt), None)


def add(row):
    with locked() as data:
        data["rows"].append(row)


def change(token, expect=None, **fields):
    """Set fields of the row with this attempt token (`state` stamps `at`);
    a row gone meanwhile is left gone. With `expect` (states), only a row
    still in one of them is changed: a transition decided from a read made
    before a network call applies only to the state it was decided from,
    so a concurrent writer's later transition is never undone. The row as
    it now is, or None when nothing was changed."""
    with locked() as data:
        row = find(data, token)
        if row is None or (expect is not None and row["state"] not in expect):
            return None
        if "state" in fields and fields["state"] != row["state"]:
            row["at"] = now()
        row.update(fields)
        return dict(row)


def remove(token, expect=None):
    """Remove the row with this token (with `expect`, only while it is in
    one of those states). Whether a row was removed."""
    with locked() as data:
        row = find(data, token)
        if row is None or (expect is not None and row["state"] not in expect):
            return False
        data["rows"].remove(row)
        return True


def lapse(token, reason, expect=None):
    return change(token, expect=expect, state=LAPSED, reason=reason)


def renew(token, new, template):
    """The pending row of a claim's next try: the row with `token` takes the
    new token, pending again, or, when another writer removed it
    meanwhile, `template` is written anew with the new token. Under the
    lock, before the try's append, so that no append is made without its
    row."""
    with locked() as data:
        row = find(data, token)
        if row is None:
            row = dict(template)
            data["rows"].append(row)
        row.update(attempt=new, state=PENDING, claim=None, reason="", at=now())
        return dict(row)


def prune(data):
    """Drop the lapsed rows seven days old."""
    data["rows"] = [r for r in data["rows"] if not (r["state"] == LAPSED and age(r["at"]) >= LAPSED_KEPT)]


def same_ticket(row, repo, number):
    return row["repo"].lower() == repo.lower() and row["number"] == number


def board_key(repo):
    """The key of `settled` and `running`: a board's name as rows are matched, without regard to case."""
    return repo.lower()


def row_of_holder(data, repo, number, holder):
    """This machine's row for the claim the fold says holds: by the claim's
    id among held and owed rows, else by its attempt token among the rows
    not lapsed (a pending row whose record took effect). None when the
    machine has none."""
    row = row_of_claim(data, repo, number, holder.id)
    if row is None and holder.attempt:
        row = next((r for r in data["rows"] if same_ticket(r, repo, number) and r["attempt"] == holder.attempt
                    and r["state"] != LAPSED), None)
    return row


def row_of_claim(data, repo, number, claim):
    """The held or owed row of this machine for that claim, or None."""
    return next((r for r in data["rows"] if same_ticket(r, repo, number) and r["claim"] == claim
                 and r["state"] in (HELD, OWED)), None)
