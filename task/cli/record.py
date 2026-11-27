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
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def digest(body):
    """`sha256:` and the hex SHA-256 of the body as the API returns it."""
    return "sha256:" + hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def valid_date(text):
    if not _DATE.fullmatch(text or ""):
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _strip_eol(line):
    return line.rstrip("\r\n")


class Parsed:
    """`text`: the body above the block (the whole body when it has none).
    `block`: the block's raw text from its opening line to the body's end,
    or None. `fields`: the keys read, empty unless `readable`. `problems`:
    why the record cannot be read (§3: an unknown key, a second block, one
    that is not last, a line that is no `key: value`)."""

    def __init__(self, text, block, fields, problems):
        self.text, self.block, self.fields, self.problems = text, block, fields, problems

    @property
    def readable(self):
        return not self.problems

    def values(self):
        """§5's `record`: every key, null where absent."""
        return {k: self.fields.get(k) for k in KEYS}


def parse(body):
    body = body or ""
    lines = body.splitlines(keepends=True)
    opens = [i for i, line in enumerate(lines) if _strip_eol(line).rstrip() == OPEN]
    if not opens:
        return Parsed(body, None, {}, [])
    problems = []
    if len(opens) > 1:
        problems.append("more than one task-record block")
    k = opens[-1]
    close = next((j for j in range(k + 1, len(lines)) if _strip_eol(lines[j]).rstrip() == CLOSE), None)
    if close is None or any(line.strip() for line in lines[close + 1:]):
        problems.append("a task-record block that is not the last thing in the body")
        return Parsed(body, None, {}, problems)
    offset = sum(len(line) for line in lines[:k])
    fields = {}
    for line in lines[k + 1:close]:
        m = _LINE.fullmatch(_strip_eol(line).rstrip())
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
    return Parsed(body[:offset], body[offset:], fields if not problems else {}, problems)


def _join(text, block):
    text = text.rstrip()
    return block if not text else text + "\n\n" + block


def with_text(body, new_text):
    """The body with its text replaced and its block, if any, unchanged."""
    p = parse(body)
    if p.block is None:
        return new_text
    return _join(new_text, p.block)


def with_keys(body, updates):
    """The body with each key of `updates` set (None: removed) in its record
    block; every other line of the block and the text above it unchanged. A
    block left with no line is dropped; a body without one gains one."""
    p = parse(body)
    if p.block is None:
        added = [(k, v) for k, v in updates.items() if v is not None]
        if not added:
            return body
        return _join(p.text, OPEN + "\n" + "".join("%s: %s\n" % kv for kv in added) + CLOSE)
    lines = p.block.splitlines(keepends=True)
    close = next(j for j in range(1, len(lines)) if _strip_eol(lines[j]).rstrip() == CLOSE)
    inner, done = [], set()
    for line in lines[1:close]:
        m = _LINE.fullmatch(_strip_eol(line).rstrip())
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
        return p.text.rstrip()
    return p.text + lines[0] + "".join(inner) + "".join(lines[close:])
