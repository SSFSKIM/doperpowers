"""Claim records (D3, Interfaces §4) and the fold that says who holds a
ticket.

A claim record is a comment whose first fenced block opens with
```task-claim: `op` (claim, release, takeover), `holder` and `attempt` on a
claim and a takeover, `of` and `reason` on a release and a takeover. A
claim's id is the id of the comment that made it. The fold reads the
trusted records of the ticket's open interval in ascending id and applies
D3's table; every reader computes it the same way, and nothing reads the
`claimed` label to decide."""
import datetime
import re
import secrets

import record

OPEN = "```task-claim"
CLOSE = "```"
OPS = ("claim", "release", "takeover")
_KEY = re.compile(r"([a-z]+): (\S.*)")
_TOKEN = re.compile(r"[0-9a-f]{16}")
_ID = re.compile(r"[1-9][0-9]*")
_KEYS = {"claim": {"op", "holder", "attempt"}, "release": {"op", "of", "reason"},
         "takeover": {"op", "of", "holder", "attempt", "reason"}}
FORCED = "forced: "


def mint():
    """An attempt token: sixteen hex digits from the system's random
    source, derived from nothing."""
    return secrets.token_hex(8)


def _bare(line):
    return line.rstrip("\n").rstrip("\r").rstrip(" \t")


def _valid_reason(op, reason):
    fixed = {"release": ("released", "ended"), "takeover": ("cleared",)}[op]
    return reason in fixed or (reason.startswith(FORCED) and bool(reason[len(FORCED):].strip()))


def parse(body):
    """The keys of a comment's claim record, or None: its first fenced
    block must be a well-formed ```task-claim block of one op."""
    lines = record.lines_of(body or "")
    for i, line in enumerate(lines):
        bare = _bare(line).lstrip(" ")
        if not (bare.startswith("```") or bare.startswith("~~~")):
            continue
        if _bare(line) != OPEN:
            return None
        keys = {}
        for inner in lines[i + 1:]:
            b = _bare(inner)
            if b == CLOSE:
                return keys if _well_formed(keys) else None
            m = _KEY.fullmatch(b)
            if not m or m.group(1) in keys:
                return None
            keys[m.group(1)] = m.group(2)
        return None
    return None


def _well_formed(keys):
    op = keys.get("op")
    if op not in OPS or set(keys) != _KEYS[op]:
        return False
    if "attempt" in keys and not _TOKEN.fullmatch(keys["attempt"]):
        return False
    if "of" in keys and not _ID.fullmatch(keys["of"]):
        return False
    return "reason" not in keys or _valid_reason(op, keys["reason"])


def compose(op, prose=None, **keys):
    """A claim record's comment: the block, then the prose a writer adds."""
    keys = dict(op=op, **keys)
    for k, v in keys.items():
        if not record.one_line(v):
            raise record.ValueNotOneLine("a claim record's %s must be one line, and %r is not" % (k, v))
    order = ("op", "holder", "attempt", "of", "reason")
    block = OPEN + "\n" + "".join("%s: %s\n" % (k, keys[k]) for k in order if k in keys) + CLOSE
    return block + ("\n\n" + prose.strip() + "\n" if prose and prose.strip() else "")


def second(stamp):
    """A GitHub time, to the second."""
    return datetime.datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)


class Record:
    def __init__(self, comment, keys):
        self.id = int(comment["fullDatabaseId"] if "fullDatabaseId" in comment else comment["id"])
        self.created = comment["createdAt"]
        self.op = keys["op"]
        self.holder = keys.get("holder")
        self.attempt = keys.get("attempt")
        self.of = int(keys["of"]) if "of" in keys else None
        self.reason = keys.get("reason")

    @property
    def makes_holder(self):
        return self.op in ("claim", "takeover")

    def describe(self):
        if self.op == "release":
            return "a release of claim %d (%s)" % (self.of, self.reason)
        if self.op == "takeover":
            return "a takeover by %s (claim %d, %s)" % (self.holder, self.id, self.reason)
        return "a claim by %s (claim %d)" % (self.holder, self.id)


def records(comments, is_trusted):
    """The trusted claim records among `comments`, in ascending id."""
    out = []
    for c in comments:
        if not is_trusted(c):
            continue
        keys = parse(c.get("body"))
        if keys is not None:
            out.append(Record(c, keys))
    return sorted(out, key=lambda r: r.id)


# What a writer's own record did (D3, Arbitration).
CURRENT, SUPERSEDED, VOID, SHUT_OUT, OUTSIDE, CLOSED, MISSING = (
    "current", "superseded", "void", "shut-out", "outside", "closed", "missing")


class Fold:
    """Who holds a ticket. `holder`: the record (a claim or a takeover) that
    holds it, or None. `effect`: id → whether that record took effect.
    `ended_by`: a claim's id → the record that ended it. `met`: id → the
    holder when that record was applied (None: unheld)."""

    def __init__(self, recs, is_open, reopened):
        self.records = recs
        self.is_open = is_open
        self.reopened = second(reopened) if reopened else None
        self.holder = None
        self.effect = {}
        self.ended_by = {}
        self.met = {}
        self.inside = [r for r in recs if self._inside(r)]
        for r in self.inside:
            held = self.holder
            self.met[r.id] = held
            if r.op == "claim":
                took = held is None
                if took:
                    self.holder = r
            else:
                took = held is not None and r.of == held.id
                if took:
                    self.ended_by[held.id] = r
                    self.holder = r if r.op == "takeover" else None
            self.effect[r.id] = took

    def _inside(self, r):
        """In the ticket's current open interval: every record of a ticket
        never closed, else those dated after the second of its last
        reopening (a record of that very second is outside, whichever of
        the two came first)."""
        return self.is_open and (self.reopened is None or second(r.created) > self.reopened)

    def by_id(self, rid):
        return next((r for r in self.records if r.id == rid), None)

    def by_attempt(self, token):
        return next((r for r in self.records if r.attempt == token), None)

    def outcome(self, rid):
        """(kind, other) for the writer's own record `rid`: `other` is the
        record that superseded it, or, for a void one, the holder it met at
        its place."""
        r = self.by_id(rid)
        if r is None:
            return MISSING, self.holder
        if not self.is_open:
            return CLOSED, None
        if r.id not in self.effect:
            if self.reopened is not None and second(r.created) == self.reopened:
                return SHUT_OUT, None
            return OUTSIDE, None
        if not self.effect[r.id]:
            return VOID, self.met[r.id]
        if self.holder is not None and self.holder.id == r.id:
            return CURRENT, None
        return (SUPERSEDED if r.makes_holder else CURRENT), self.ended_by.get(r.id)
