"""The record block (D2, Interfaces §3) and a body's digest.

A body is split into its text and its record block: the last fenced block
whose opening line is ```task-record, closed by a ``` line and followed by
nothing but whitespace. The block is kept as raw text, so that a write
which changes only the text above it keeps it byte for byte, and a write
which changes one key edits that key's line and no other."""
import datetime
import hashlib
import re

OPEN = "```task-record"
CLOSE = "```"
KEYS = ("registered-by", "for", "due", "spec", "adopted")
_LINE = re.compile(r"([a-z-]+): (\S.*)")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def digest(body):
    """`sha256:` and the hex SHA-256 of the body as the API returns it."""
    return "sha256:" + hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def one_line(value):
    """Whether a value is one line by every boundary `str.splitlines`
    honors (CR, VT, FF, the separators \x1c-\x1e, NEL, U+2028, U+2029, as
    well as LF): the parser reads a body by those, so any of them in a
    value would start a key of its own."""
    return isinstance(value, str) and value.splitlines() == [value]


class ValueNotOneLine(ValueError):
    pass


def _check_values(keys):
    for key, value in keys.items():
        if value is not None and not one_line(value):
            raise ValueNotOneLine("the record's %s must be one line, and %r is not" % (key, value))


def valid_date(text):
    if not _DATE.fullmatch(text or ""):
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def lines_of(text):
    """The text's lines, each with its ending: split on LF alone, as GitHub
    renders a fence (a CR before the LF is the line's ending too). The
    parser and the prose guard both read lines this way, so no text opens a
    block for one and not the other."""
    parts = (text or "").split("\n")
    return [p + "\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _bare(line):
    """A line without its ending and its trailing blanks, for matching a fence."""
    return line.rstrip("\n").rstrip("\r").rstrip(" \t")


def _strip_eol(line):
    return line.rstrip("\r\n")


class Parsed:
    """`text`: the body above the block (the whole body when it has none).
    `block`: the block's raw text from its opening line to the body's end,
    or None. `misplaced`: a second block, or one that is not last. `fields`: the keys read, empty unless `readable`. `problems`:
    why the record cannot be read (§3: an unknown key, a second block, one
    that is not last, a line that is no `key: value`)."""

    def __init__(self, text, block, fields, problems, misplaced=False):
        self.text, self.block, self.fields, self.problems = text, block, fields, problems
        # A block that is doubled or not last: no write can set a key in it without making a second one.
        self.misplaced = misplaced

    @property
    def readable(self):
        return not self.problems

    def values(self):
        """§5's `record`: every key, null where absent."""
        return {k: self.fields.get(k) for k in KEYS}


def parse(body):
    body = body or ""
    lines = lines_of(body)
    opens = [i for i, line in enumerate(lines) if _bare(line) == OPEN]
    if not opens:
        return Parsed(body, None, {}, [])
    problems = []
    if len(opens) > 1:
        problems.append("more than one task-record block")
    k = opens[-1]
    close = next((j for j in range(k + 1, len(lines)) if _bare(lines[j]) == CLOSE), None)
    if close is None or any(line.strip() for line in lines[close + 1:]):
        problems.append("a task-record block that is not the last thing in the body")
        return Parsed(body, None, {}, problems, misplaced=True)
    offset = sum(len(line) for line in lines[:k])
    fields = {}
    for line in lines[k + 1:close]:
        m = _LINE.fullmatch(_bare(line))
        if not m:
            problems.append("a line that is not `key: value`: %r" % _strip_eol(line))
            continue
        key, value = m.group(1), m.group(2)
        if key not in KEYS:
            problems.append("an unknown key: %s" % key)
        elif key in fields:
            problems.append("a key given twice: %s" % key)
        elif key == "due" and not valid_date(value):
            problems.append("a due that is no YYYY-MM-DD date: %s" % value)
        else:
            fields[key] = value
    return Parsed(body[:offset], body[offset:], fields if not problems else {}, problems,
                  misplaced=len(opens) > 1)


# Between the prose and the block the CLI writes exactly this, and takes exactly this away with the block's last
# key, so that a change of the record alone leaves every byte of the prose as it was.
SEPARATOR = "\n\n"
_FENCE_RE = re.compile(r"[ \t]*(`{3,}|~{3,})[ \t]*task-(record|claim)\b")


def fences(text):
    """The task-record or task-claim fences a text opens, as written: on any
    of its lines as `lines_of` splits them (more forms than the parser
    reads as a block, never fewer)."""
    found = (_FENCE_RE.match(line) for line in lines_of(text))
    return [m.group(0).strip() for m in found if m]


def _append(prose, block):
    return prose + SEPARATOR + block if prose else block


def compose(prose, keys):
    """A new body: the prose, then a block of `keys` (in order; None
    skipped) when there is one."""
    _check_values(keys)
    lines = "".join("%s: %s\n" % (k, v) for k, v in keys.items() if v is not None)
    return _append(prose.rstrip(), OPEN + "\n" + lines + CLOSE) if lines else prose


def with_text(body, new_text):
    """The body with its prose replaced and its block, if any, unchanged."""
    p = parse(body)
    if p.block is None:
        return new_text
    return _append(new_text.rstrip(), p.block)


def with_keys(body, updates):
    """The body with each key of `updates` set (None: removed) in its record
    block; every other line of the block and the text above it unchanged. A
    block left with no line is dropped; a body without one gains one."""
    _check_values(updates)
    p = parse(body)
    if p.misplaced:
        raise ValueError("a record block that is doubled or not last takes no key")
    if p.block is None:
        added = [(k, v) for k, v in updates.items() if v is not None]
        if not added:
            return body
        return _append(body, OPEN + "\n" + "".join("%s: %s\n" % kv for kv in added) + CLOSE)
    lines = lines_of(p.block)
    close = next(j for j in range(1, len(lines)) if _bare(lines[j]) == CLOSE)
    inner, done = [], set()
    for line in lines[1:close]:
        m = _LINE.fullmatch(_bare(line))
        key = m.group(1) if m else None
        if key in updates:
            done.add(key)
            if updates[key] is not None:
                eol = line[len(_strip_eol(line)):] or "\n"
                inner.append("%s: %s%s" % (key, updates[key], eol))
            continue
        inner.append(line)
    for key, value in updates.items():
        if key not in done and value is not None:
            if inner and not inner[-1].endswith("\n"):
                inner[-1] += "\n"
            inner.append("%s: %s\n" % (key, value))
    if not inner:
        return p.text[:-len(SEPARATOR)] if p.text.endswith(SEPARATOR) else p.text
    return p.text + lines[0] + "".join(inner) + "".join(lines[close:])
