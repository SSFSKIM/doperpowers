"""What the old board left in an issue's body, and the body the relabel
rewrites it to (D6): the trailing `board:meta` block, an HTML comment the
issue's page never shows, made visible; and the retired board service's
mirror header, which tells a reader GitHub is not the ticket, replaced.

The block is found as the old scripts find it (`meta_match` in the
issue-tracker skill's `_board.py`, ported here, not imported): a body that
documents the block in its prose holds a marker-shaped example above the
real one, and neither the first nor the last opener is the real one by
position alone."""
import re

import record

META_RE = re.compile(r"\n?<!-- board:meta\n(.*?)\n-->\s*$", re.S)
# Every boundary `str.splitlines` honors: the old parser read the block's lines by those.
_LINE_SEP = re.compile("\r\n|[\n\r\v\f\x1c\x1d\x1e\x85  ]")
META_KEYS = ("spawned-by", "relates-to", "branch", "pr", "plan", "pre-park", "parent-pin", "note")
_OPENER = "<!-- board:meta"

# The retired service's mirror header, recognized by its exact lines. The third names the service's address,
# matched by form so that no host is written here; its ticket number must be the first line's.
_BANNER_1 = re.compile(r"`arkho-board:ticket:(\d+)` — mirrored from the Arkho board\.")
_BANNER_2 = ("**Read-only.** Edits here are reverted; closing this issue does not close the ticket. The board is the "
             "source of truth.")
_BANNER_3 = re.compile(r"Board ticket: https://[^\s/]+/ui/t/(\d+)")
BANNER_LINE = "_Moved from board ticket %s on the retired board service._"

# How each key of the block reads as a line of the body: a mention stays a mention.
_LINE_OF = {"note": "Board note", "relates-to": "Related", "spawned-by": "Spawned by", "branch": "Branch",
            "pr": "Pull request", "plan": "Plan", "pre-park": "Board pre-park", "parent-pin": "Board parent-pin"}
_MENTIONS = ("relates-to", "spawned-by")


def _block_line(line):
    return ":" in line and line.split(":", 1)[0].strip() in META_KEYS


def meta_match(body):
    """The match of the body's real trailing block, or None: the first
    opener standing after the last line that cannot be block interior; when
    none does (a noncanonical block), the first opener of the last run."""
    m0 = META_RE.search(body)
    if not m0:
        return None
    head = len(_OPENER) + 1
    close = m0.end(1)
    first = m0.start() + (1 if body[m0.start()] == "\n" else 0)
    opens, fence, pos = [], first, first
    while pos < close:
        sep = _LINE_SEP.search(body, pos, close)
        line = body[pos:sep.start() if sep else close]
        marker = line.lstrip()
        if marker == _OPENER:
            cand = pos + (len(line) - len(marker))
            if sep is not None and sep.group() == "\n" and cand + head <= close:
                opens.append((cand, fence))
        elif not _block_line(line):
            fence = sep.end() if sep else close
        pos = sep.end() if sep else close
    for start, _ in opens:
        if start >= fence:
            return META_RE.search(body, start)
    floor = opens[-1][1]
    return META_RE.search(body, next(s for s, _ in opens if s >= floor))


def _mentions(value):
    return " ".join("#" + t if t.isdigit() else t for t in value.split())


def _visible(interior, keep_plan):
    """The block's lines as the body's (each its own paragraph), and the
    pinned plan when it is to become the record's `spec:`."""
    lines, spec = [], None
    for raw in interior.splitlines():
        if not raw.strip():
            continue
        key, colon, value = raw.partition(":")
        key, value = key.strip(), value.strip()
        if not colon or not value:
            lines.append(raw.strip())
        elif key == "plan" and "@" in value and keep_plan and spec is None:
            spec = value
        elif key in _LINE_OF:
            lines.append("%s: %s" % (_LINE_OF[key], _mentions(value) if key in _MENTIONS else value))
        else:
            lines.append("Board %s: %s" % (key, value))
    return lines, spec


def _without_banner(text):
    """The text with the mirror header that opens it replaced, or None when
    it opens with no such header."""
    lines = record.lines_of(text)
    if len(lines) < 3:
        return None
    bare = [l.rstrip("\n").rstrip("\r") for l in lines[:3]]
    one, three = _BANNER_1.fullmatch(bare[0]), _BANNER_3.fullmatch(bare[2])
    if not (one and three and bare[1] == _BANNER_2 and one.group(1) == three.group(1)):
        return None
    eol = lines[2][len(bare[2]):]
    return BANNER_LINE % one.group(1) + eol + "".join(lines[3:])


def rewrite(body):
    """The body the relabel writes, or None when it holds neither a
    `board:meta` block nor the mirror header. Everything else stays byte
    for byte; a record block stays last, and a pinned `plan:` becomes its
    `spec:` when it has none."""
    body = body or ""
    parsed = record.parse(body)
    if parsed.misplaced or not parsed.readable:
        return None  # a record the CLI cannot read is not rewritten around
    prose = parsed.text[:-len(record.SEPARATOR)] if parsed.block and parsed.text.endswith(record.SEPARATOR) \
        else parsed.text
    changed, spec = False, None
    banner = _without_banner(prose)
    if banner is not None:
        prose, changed = banner, True
    m = meta_match(prose)
    if m:
        lines, spec = _visible(m.group(1), keep_plan="spec" not in parsed.fields)
        above = prose[:m.start()].rstrip("\n")
        shown = "\n\n".join(lines)
        prose = (above + "\n\n" + shown if above and shown else above or shown) + "\n"
        changed = True
    if not changed:
        return None
    if parsed.block is not None:
        out = record.with_text(body, prose)
        return record.with_keys(out, {"spec": spec}) if spec else out
    return record.compose(prose, {"spec": spec}) if spec else prose
