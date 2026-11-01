"""The manager's state file, version 2: the subscriptions and the ledger (the owner's items, the work's outcomes,
the latest brief per initiative), and `apply`, the one way an update changes it.

`$SMINOS_HOME/managers/<name>.json`, mode 0600, written whole through a temporary file and a rename; every
read-modify-write holds an exclusive flock on `<name>.lock` beside it (`lock`). Done and overtaken items whose
`changed` is more than 30 days old move to `<name>.archive.jsonl`. A version 1 file (M1's carry list) migrates
in memory on read and is stored as version 2 at the next write.

Times are stored in one form, UTC with milliseconds (`stamp`); any ISO-8601 time is accepted (`parse`, a time
with no zone read as local, as the command line's T is).
"""

import contextlib
import copy
import datetime
import fcntl
import json
import os

import sminos as S

VERSION = 2
ARCHIVE_AFTER = 30 * 86400
RECENT_DONE = 7 * 86400
FIRST_WINDOW = 86400            # a subscription's first `covered`: this long before it was added

LANES = ("yours", "work")
YOURS_TYPES = ("decide", "judge", "act", "answer", "other")
YOURS_STATUSES = ("pending", "answered", "done", "overtaken")
WORK_STATUSES = ("in progress", "done", "stalled")
WORK_ORDER = ("in progress", "stalled", "done")       # as the ledger shows them
RESOLVED = ("done", "overtaken")

# Each lane's fields: (kind, required). Kinds: text, bool, time, texts (a list of strings); `?` allows null.
# Requirement beyond these (evidence and status_at past pending; waits_on when stalled; finished when done) is
# in _check_item.
FIELDS = {
    "yours": {"initiative": ("text", True), "member": ("text", True), "session": ("text", True),
              "type": ("text", True), "blocking": ("bool", True), "need": ("text", True), "why": ("text?", False),
              "raised": ("time", True), "source": ("text", True), "status": ("text", True),
              "status_at": ("time?", False), "evidence": ("text?", False), "unverified": ("bool", False),
              "seen": ("bool", False)},
    "work": {"initiative": ("text", True), "members": ("texts", False), "title": ("text", True),
             "meaning": ("text", True), "status": ("text", True), "waits_on": ("text?", False),
             "started": ("time", True), "finished": ("time?", False), "refs": ("texts", False)},
}
DEFAULTS = {"yours": {"why": None, "status_at": None, "evidence": None, "unverified": False, "seen": False},
            "work": {"members": [], "waits_on": None, "finished": None, "refs": []}}
# A change to one of these stamps `changed`; any other field given replaces the one held without it.
SUBSTANTIVE = {"yours": ("type", "blocking", "need", "status", "evidence"),
               "work": ("title", "meaning", "status", "waits_on")}
# `id` and `lane` name the item; `reported` and `changed` are apply's stamps, kept from the item held.
OWN = ("id", "lane", "reported", "changed")
DOC_KEYS = ("window", "sessions", "items", "briefs")


class Invalid(Exception):
    """A document or a state file that does not hold: every problem, one line each."""

    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = list(problems)


# ------------------------------------------------------------------ time

def parse(ts):
    """An ISO-8601 time as epoch seconds; None for anything else."""
    if not isinstance(ts, str) or not ts.strip():
        return None
    try:
        at = datetime.datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (at if at.tzinfo else at.astimezone()).timestamp()


def stamp(t):
    """Epoch seconds in the stored form: UTC, milliseconds, `Z`."""
    at = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    return at.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (at.microsecond // 1000)


def _norm_time(ts):
    t = parse(ts)
    return stamp(t) if t is not None else ts


# ------------------------------------------------------------------ the file

def path(name):
    return os.path.join(S.root(), "managers", name + ".json")


def archive_path(name):
    return os.path.join(S.root(), "managers", name + ".archive.jsonl")


@contextlib.contextmanager
def lock(name):
    """An exclusive flock on `<name>.lock`, held for one read-modify-write of the state."""
    os.makedirs(os.path.dirname(path(name)), mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(S.root(), "managers", name + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def load(name):
    """The state, normalized to version 2 (empty when there is no file). OSError and ValueError for a file that
    cannot be read or parsed; Invalid for one whose content does not hold."""
    try:
        with open(path(name)) as f:
            raw = json.load(f)
    except FileNotFoundError:
        raw = {}
    return normalize(raw)


def save(name, st):
    os.makedirs(os.path.dirname(path(name)), mode=0o700, exist_ok=True)
    S.write_json(path(name), st, mode=0o600)


def append_archive(name, items):
    """The items appended to the archive, one per line (the file 0600)."""
    if not items:
        return
    fd = os.open(archive_path(name), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ normalizing

def _subscription(e, briefed):
    out = dict(e)
    covered = e.get("covered") or briefed
    if not covered and parse(e.get("added")) is not None:
        covered = stamp(parse(e["added"]) - FIRST_WINDOW)
    out["covered"] = _norm_time(covered) if covered else None
    out["seen"] = _norm_time(e["seen"]) if e.get("seen") else None
    return out


def _carried(st, carry, briefed):
    """Version 1's carry entries as yours items: type `other`, status `pending`, the initiative of the subscription
    holding its session."""
    initiative = {e.get("session"): i.get("name") for i in st["initiatives"] for e in i.get("sessions") or []}
    items = []
    for n, c in enumerate(c for c in carry if isinstance(c, dict)):
        item = {"id": "y%d" % (n + 1), "lane": "yours", "initiative": initiative.get(c.get("session")),
                "member": c.get("member"), "session": c.get("session"), "type": "other",
                "blocking": c.get("blocking", False), "need": c.get("need"), "raised": c.get("raised"),
                "source": c.get("source"), "status": "pending", "reported": briefed, "changed": briefed}
        item.update({k: c[k] for k in ("why", "evidence", "unverified", "seen") if k in c})
        items.append(item)
    return items


def normalize(raw):
    """A state file's content as version 2: a version 1 file migrated (its carry list becomes yours items, `briefed`
    becomes `updated` and every subscription's `covered`), missing keys filled, every item validated as `apply`
    validates (Invalid naming every problem)."""
    raw = raw if isinstance(raw, dict) else {}
    briefed = _norm_time(raw.get("briefed")) if raw.get("briefed") else None
    st = {"version": VERSION, "initiatives": [], "updated": None, "window": None, "next": {"y": 1, "w": 1},
          "items": [], "briefs": []}
    for i in raw.get("initiatives") or []:
        if isinstance(i, dict) and i.get("name"):
            st["initiatives"].append({**i, "sessions": [_subscription(e, briefed) for e in i.get("sessions") or []
                                                        if isinstance(e, dict)]})
    if raw.get("version", 1) == 1 and "items" not in raw:
        st["updated"] = briefed
        st["items"] = _carried(st, raw.get("carry") or [], briefed)
    else:
        st["updated"] = raw.get("updated")
        st["window"] = raw.get("window")
        st["items"] = [dict(i) for i in raw.get("items") or [] if isinstance(i, dict)]
        st["briefs"] = [dict(b) for b in raw.get("briefs") or [] if isinstance(b, dict)]
    held = raw.get("next") if isinstance(raw.get("next"), dict) else {}
    for lane in "yw":
        used = [int(i["id"][1:]) for i in st["items"]
                if isinstance(i.get("id"), str) and i["id"][:1] == lane and i["id"][1:].isdigit()]
        st["next"][lane] = max([held.get(lane) or 1] + [n + 1 for n in used])
    problems = []
    for i in st["items"]:
        lane = i.get("lane")
        if not (isinstance(i.get("id"), str) and i["id"].strip()):
            problems.append("an item's id %r is not text" % (i.get("id"),))
            continue
        if not (isinstance(lane, str) and lane in LANES):
            problems.append("%s: lane %r is not one of %s" % (i["id"], lane, ", ".join(LANES)))
            continue
        _fill(i)
        problems += _check_item(i, str(i.get("id")))
    if problems:
        raise Invalid(problems)
    return st


def _fill(item):
    for k, v in DEFAULTS[item["lane"]].items():
        item.setdefault(k, copy.copy(v))
    for k, (kind, _) in FIELDS[item["lane"]].items():
        if kind.startswith("time") and isinstance(item.get(k), str):
            item[k] = _norm_time(item[k])


# ------------------------------------------------------------------ validation

def _check_item(item, where):
    """The problems of one item as it would stand: its lane's fields, kinds, enumerations, and what its status
    requires."""
    lane = item["lane"]
    fields, problems = FIELDS[lane], []
    for k in item:
        if k not in fields and k not in OWN:
            problems.append("%s: no %s item has a field '%s'" % (where, lane, k))
    good = {}       # the fields whose value holds its kind, the only ones the checks below read
    for k, (kind, required) in fields.items():
        if k not in item or item[k] is None:
            if required:
                problems.append("%s: %s is required" % (where, k))
            elif k in item and not kind.endswith("?"):
                problems.append("%s: %s cannot be null" % (where, k))
            continue
        v, base = item[k], kind.rstrip("?")
        if base == "text" and not isinstance(v, str):
            problems.append("%s: %s must be text" % (where, k))
        elif base == "text" and not v.strip():
            problems.append("%s: %s %s" % (where, k, "is required" if required else
                                           "cannot be blank (leave it out, or null)"))
        elif base == "bool" and not isinstance(v, bool):
            problems.append("%s: %s must be true or false" % (where, k))
        elif base == "time" and parse(v) is None:
            problems.append("%s: %s %r is not an ISO-8601 time" % (where, k, v))
        elif base == "texts" and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            problems.append("%s: %s must be a list of text" % (where, k))
        else:
            good[k] = v
    status = good.get("status")
    if lane == "yours":
        if "type" in good and good["type"] not in YOURS_TYPES:
            problems.append("%s: type '%s' is not one of %s" % (where, good["type"], ", ".join(YOURS_TYPES)))
        if status is not None and status not in YOURS_STATUSES:
            problems.append("%s: status '%s' is not one of %s" % (where, status, ", ".join(YOURS_STATUSES)))
        elif status is not None and status != "pending":
            for k in ("evidence", "status_at"):
                if k not in good and (k not in item or item[k] is None):
                    problems.append("%s: %s is required once its status is %s" % (where, k, status))
    else:
        if status is not None and status not in WORK_STATUSES:
            problems.append("%s: status '%s' is not one of %s" % (where, status, ", ".join(WORK_STATUSES)))
        for k, needs in (("waits_on", "stalled"), ("finished", "done")):
            if status == needs and k not in good and (k not in item or item[k] is None):
                problems.append("%s: %s is required once its status is %s" % (where, k, needs))
    return problems


def _is_open(item):
    return item.get("status") not in RESOLVED


# ------------------------------------------------------------------ apply

def apply(st, doc, now):
    """One update's ledger change, applied to a copy of `st` at `now` (epoch seconds): (the new state, the report).
    The whole document is validated first, every item as it would stand after the merge; any problem raises
    Invalid naming each, and nothing is changed. The report: `new` (ids created), `changed` (ids changed in a
    substantive field), `unchanged_open` (open items it left as they were), `archived` (the items moved out),
    `briefs` (the initiatives whose brief it replaced)."""
    problems = []
    if not isinstance(doc, dict):
        raise Invalid(["the update is a JSON object with window, sessions, items and briefs"])
    for k in doc:
        if k not in DOC_KEYS:
            problems.append("the update has no field '%s' (it holds %s)" % (k, ", ".join(DOC_KEYS)))
    window = doc.get("window")
    sessions, items, briefs = (doc.get(k, []) for k in ("sessions", "items", "briefs"))    # only absent is empty
    if not isinstance(window, dict) or parse(window.get("since")) is None or parse(window.get("until")) is None:
        problems.append("window: since and until, both ISO-8601 times, are required")
    elif parse(window["until"]) < parse(window["since"]):
        problems.append("window: until is earlier than since")
    for k, v in (("sessions", sessions), ("items", items), ("briefs", briefs)):
        if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
            problems.append("%s: a list of objects" % k)
    if problems:
        raise Invalid(problems)

    out = copy.deepcopy(st)
    subs = {e.get("session"): e for i in out["initiatives"] for e in i["sessions"]}
    seen_sessions = set()
    for n, s in enumerate(sessions):
        sid, where = s.get("session"), "sessions[%d]" % n
        if not isinstance(sid, str):
            problems.append("%s: session must be a subscription's session id" % where)
        elif sid not in subs:
            problems.append("%s: %s is not a subscription" % (where, sid))
        elif sid in seen_sessions:
            problems.append("%s: %s is listed twice" % (where, sid))
        else:
            seen_sessions.add(sid)
        for k in ("from", "covered"):
            if parse(s.get(k)) is None:
                problems.append("%s: %s, an ISO-8601 time, is required" % (where, k))
        if s.get("seen") is not None and parse(s.get("seen")) is None:
            problems.append("%s: seen '%s' is not an ISO-8601 time" % (where, s.get("seen")))
        if parse(s.get("from")) is not None and parse(s.get("covered")) is not None \
                and parse(s["covered"]) < parse(s["from"]):
            problems.append("%s: covered is earlier than from" % where)

    held = {i["id"]: i for i in out["items"]}
    merged, given_ids = [], set()
    for n, given in enumerate(items):
        iid = given.get("id")
        if "id" in given and not (isinstance(iid, str) and iid.strip()):
            problems.append("items[%d]: id must be a held item's id (a new item has none)" % n)
            continue
        where = "items[%d] (%s)" % (n, iid if iid is not None else "new")
        fields = {k: v for k, v in given.items() if k not in ("reported", "changed")}
        if "lane" in fields and not (isinstance(fields["lane"], str) and fields["lane"] in LANES):
            problems.append("%s: lane %r is not one of %s" % (where, fields["lane"], ", ".join(LANES)))
            continue
        if iid is None:
            lane = fields.get("lane")
            if lane is None:
                problems.append("%s: lane is required (%s)" % (where, ", ".join(LANES)))
                continue
            item = dict(fields)
            _fill(item)
            problems += _check_item(item, where)
            merged.append((None, item))
            continue
        if iid not in held:
            problems.append("%s: unknown id %s" % (where, iid))
            continue
        if iid in given_ids:
            problems.append("%s: %s is changed twice in one update" % (where, iid))
        given_ids.add(iid)
        before = held[iid]
        if "lane" in fields and fields["lane"] != before["lane"]:
            problems.append("%s: lane cannot change (%s → %s)" % (where, before["lane"], fields["lane"]))
            continue
        item = {**before, **fields}
        _fill(item)
        problems += _check_item(item, where)
        if before.get("seen") is True and item.get("seen") is not True:
            problems.append("%s: seen cannot turn back to false" % where)
        merged.append((iid, item))

    seen_briefs = set()
    for n, b in enumerate(briefs):
        where = "briefs[%d]" % n
        for k in ("initiative", "text"):
            if not isinstance(b.get(k), str) or not b[k].strip():
                problems.append("%s: %s is required, as text" % (where, k))
        if parse(b.get("since")) is None:
            problems.append("%s: since, an ISO-8601 time, is required" % where)
        initiative = b.get("initiative")
        if isinstance(initiative, str) and initiative in seen_briefs:
            problems.append("%s: a second brief for %s" % (where, initiative))
        elif isinstance(initiative, str):
            seen_briefs.add(initiative)
        for k in b:
            if k not in ("initiative", "since", "text"):
                problems.append("%s: a brief has no field '%s'" % (where, k))
    if problems:
        raise Invalid(problems)

    at = stamp(now)
    new, changed = [], []
    for iid, item in merged:
        if iid is None:
            prefix = "y" if item["lane"] == "yours" else "w"
            item["id"] = "%s%d" % (prefix, out["next"][prefix])
            out["next"][prefix] += 1
            item["reported"] = item["changed"] = at
            out["items"].append({"id": item["id"], "lane": item["lane"],
                                 **{k: v for k, v in item.items() if k not in ("id", "lane")}})
            new.append(item["id"])
            continue
        before = held[iid]
        if any(item.get(k) != before.get(k) for k in SUBSTANTIVE[item["lane"]]):
            item["changed"] = at
            changed.append(iid)
        out["items"] = [item if i is before else i for i in out["items"]]
        held[iid] = item

    for s in sessions:
        e = subs[s["session"]]
        frm, covered = parse(s["from"]), parse(s["covered"])
        if e.get("covered") is None or frm <= parse(e["covered"]):
            e["covered"] = stamp(max(covered, parse(e["covered"]) if e.get("covered") else covered))
        if s.get("seen") is not None and (e.get("seen") is None or parse(s["seen"]) > parse(e["seen"])):
            e["seen"] = stamp(parse(s["seen"]))

    out["updated"] = at
    out["window"] = {"since": stamp(parse(window["since"])), "until": stamp(parse(window["until"]))}
    for b in briefs:
        out["briefs"] = [x for x in out["briefs"] if x.get("initiative") != b["initiative"]]
        out["briefs"].append({"initiative": b["initiative"], "written": at, "since": stamp(parse(b["since"])),
                              "text": b["text"]})

    archived = [i for i in out["items"] if i.get("status") in RESOLVED and parse(i.get("changed")) is not None
                and now - parse(i["changed"]) > ARCHIVE_AFTER]
    gone = {i["id"] for i in archived}
    out["items"] = [i for i in out["items"] if i["id"] not in gone]
    done = set(new) | set(changed)
    unchanged = [i["id"] for i in out["items"] if _is_open(i) and i["id"] not in done]
    return out, {"new": new, "changed": changed, "unchanged_open": unchanged, "archived": archived,
                 "briefs": [b["initiative"] for b in briefs]}


# ------------------------------------------------------------------ the view

def initiative_names(st):
    """Every initiative the state names, in order: the subscriptions', then any only an item or a brief names."""
    names = [i["name"] for i in st["initiatives"]]
    for x in st["items"] + st["briefs"]:
        if x.get("initiative") and x["initiative"] not in names:
            names.append(x["initiative"])
    return names


def _order(item):
    """The owner's items by status (pending first; within it blocking, then unseen), then work in progress,
    stalled and done; each group oldest first."""
    if item["lane"] == "yours":
        rank = YOURS_STATUSES.index(item["status"]) if item["status"] in YOURS_STATUSES else len(YOURS_STATUSES)
        pending = item["status"] == "pending"
        return (0, rank, pending and not item.get("blocking"), pending and bool(item.get("seen")),
                parse(item.get("raised")) or 0)
    rank = WORK_ORDER.index(item["status"]) if item["status"] in WORK_ORDER else len(WORK_ORDER)
    return (1, rank, False, False, parse(item.get("started")) or 0)


def view(st, now=None):
    """`manager ledger --json`, the shape the page serves: {updated, window, initiatives: [{name, items, brief}]},
    every item held, in the order the ledger shows them."""
    out = []
    for name in initiative_names(st):
        items = sorted((i for i in st["items"] if i.get("initiative") == name), key=_order)
        brief = next((b for b in st["briefs"] if b.get("initiative") == name), None)
        out.append({"name": name, "items": items, "brief": brief})
    return {"updated": st["updated"], "window": st["window"], "initiatives": out}


def clock(ts, now):
    t = parse(ts)
    if t is None:
        return "?"
    at, today = datetime.datetime.fromtimestamp(t), datetime.datetime.fromtimestamp(now)
    return at.strftime("%H:%M") if at.date() == today.date() else at.strftime("%m-%d %H:%M")


def _line(item, updated, now):
    """One item, for the manager model: compact, its id first so an update can name it."""
    if item["lane"] == "yours":
        status = "answered?" if item["status"] == "answered" and item.get("unverified") else item["status"]
        marks = " ".join(m for m in ("unseen" if not item.get("seen") and _is_open(item) else "",
                                     "new" if item.get("reported") and item["reported"] == updated else "") if m)
        text = "  %-4s %-9s %-6s %-8s %-10s %s %s  %s" % (
            item["id"], status, item["type"], "blocking" if item.get("blocking") else "optional", marks,
            item["member"], clock(item["raised"], now), item["need"].replace("\n", " "))
        if item["status"] != "pending" and item.get("evidence"):
            text += "  — %s %s" % (clock(item.get("status_at"), now), item["evidence"].replace("\n", " "))
        return text
    text = "  %-4s %-11s  %s" % (item["id"], item["status"], item["title"].replace("\n", " "))
    if item["status"] == "stalled" and item.get("waits_on"):
        text += "  (waits on %s)" % item["waits_on"]
    if item.get("refs"):
        text += "  [%s]" % ", ".join(item["refs"])
    return text


def render(v, now):
    """The ledger as text: per initiative, a header with the last update's time and window, one line per item
    (done and overtaken ones only from the last 7 days, the rest counted), then the latest brief's time."""
    if not v["initiatives"]:
        return "The ledger is empty: nothing is subscribed and no update has run."
    window = v.get("window") or {}
    head = "updated %s (covering %s–%s)" % (clock(v["updated"], now), clock(window.get("since"), now),
                                           clock(window.get("until"), now)) if v.get("updated") else "no update yet"
    lines = []
    for ini in v["initiatives"]:
        lines.append("%s · %s" % (ini["name"], head))
        older = 0
        for item in ini["items"]:
            if item["status"] in RESOLVED and now - (parse(item.get("changed")) or now) > RECENT_DONE:
                older += 1
                continue
            lines.append(_line(item, v.get("updated"), now))
        if not ini["items"]:
            lines.append("  (no items)")
        if older:
            lines.append("  (%d done or overtaken more than 7 days ago, in `ledger --json`)" % older)
        b = ini["brief"]
        if b:
            lines.append("  brief written %s, covering since %s" % (clock(b.get("written"), now),
                                                                    clock(b.get("since"), now)))
    return "\n".join(lines)


def summary(st, report):
    """`apply`'s text: one line per initiative, `P5: 2 new · 3 changed · 5 still open · brief written`."""
    by_id = {i["id"]: i for i in st["items"]}
    lines = []
    for name in initiative_names(st):
        def count(ids):
            return sum(1 for x in ids if x in by_id and by_id[x].get("initiative") == name)
        line = "%s: %d new · %d changed · %d still open" % (
            name, count(report["new"]), count(report["changed"]), count(report["unchanged_open"]))
        lines.append(line + (" · brief written" if name in report["briefs"] else ""))
    if report["archived"]:
        lines.append("archived %d done or overtaken item(s) older than 30 days" % len(report["archived"]))
    return "\n".join(lines)
