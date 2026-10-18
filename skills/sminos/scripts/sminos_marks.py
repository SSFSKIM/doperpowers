"""The marks a session writes to its human, read the way the `to-human` mod
reads them for display: a Python port of `parse` in to-human/hooks/mods/to-human.tsx.

`<message>` is the one mark; the old `<to-human>`, `<essential>`,
`<need-input>` and `<insight>` read as its aliases. A tag inside inline code
or a fenced block is literal; marks may nest, and each contiguous run of text
under one mark is a span of its own; an unclosed mark runs to the end of the
text. A text the streaming hook (hooks/to-human-stream.sh) already drew — its
headers in color, its record dimmed — is read in that form.

The port keeps JavaScript's meanings where Python's differ: `.` stops at
\\r, U+2028 and U+2029 as well as \\n, `$` is the end of the string, and
`trim()` strips JavaScript's whitespace set. tests/sminos/marks_parity.py
holds the mod's own fixtures (tests/mods/to-human.test.ts) and pins them.
"""

import bisect
import re

KIND = "message"
_NAMES = "message|to-human|essential|need-input|insight"
# JavaScript's `.`: anything but a line terminator.
_ANY = "[^\n\r  ]"
# JavaScript's String.prototype.trim(): WhiteSpace and LineTerminator.
_JS_SPACE = "\t\n\x0b\x0c\r              " \
            "    　﻿"


def js_trim(s):
    return s.strip(_JS_SPACE)


# A fence line's two patterns: group 1 the fence run, group 2 what follows it
# on the line (an opening fence's info string; a closing fence's trailing mark
# tags, empty in the strict reading).
STRICT = (re.compile(r"[ \t]*(`{3,}|~{3,})(" + _ANY + r"*)\Z"),
          re.compile(r"[ \t]*(`{3,}|~{3,})[ \t]*()\Z"))
# The glued recovery reading: mark tags are transparent at a fence line's
# edges, so a tag glued before an opening fence or after a closing one still
# means the fence. A recovery only: a text the strict reading balances never
# reads through it.
_MARK_TAGS = r"(?:</?(?:" + _NAMES + r")>[ \t]*)*"
GLUED = (re.compile(r"[ \t]*" + _MARK_TAGS + r"(`{3,}|~{3,})(" + _ANY + r"*)\Z"),
         re.compile(r"[ \t]*(`{3,}|~{3,})[ \t]*(" + _MARK_TAGS + r")\Z"))
TAG = re.compile(r"<(/?)(" + _NAMES + r")>")
_TICKS = re.compile(r"`+")


def _inline_spans(text, start, end, regions):
    """A run of N backticks opens a span closed by the next run of exactly N;
    a run with no partner is literal backticks."""
    runs = list(_TICKS.finditer(text, start, end))
    nxt = [-1] * len(runs)
    latest = {}
    for i, run in enumerate(runs):
        previous = latest.get(len(run.group()))
        if previous is not None:
            nxt[previous] = i
        latest[len(run.group())] = i
    i = 0
    while i < len(runs):
        close = nxt[i]
        if close != -1:
            regions.append((runs[i].start(), runs[close].end()))
            i = close
        i += 1


def code_regions(text, fences=STRICT):
    """Half-open [start, end) offsets of the text's code: fenced blocks (an
    unclosed fence runs to the end) and, within each paragraph, inline spans."""
    regions = []
    paragraph = None
    fence = None  # (char, length, start)
    at, n = 0, len(text)
    while at <= n:
        newline = text.find("\n", at)
        end = n if newline == -1 else newline
        line = text[at:end]
        if fence is not None:
            close = fences[1].match(line)
            if close and close.group(1)[0] == fence[0] and len(close.group(1)) >= fence[1]:
                regions.append((fence[2], end - len(close.group(2))))
                fence = None
        else:
            opened = fences[0].match(line)
            # A backtick fence's info string holds no backtick; such a line is an inline span instead.
            if opened and not (opened.group(1)[0] == "`" and "`" in opened.group(2)):
                if paragraph is not None:
                    _inline_spans(text, paragraph[0], paragraph[1], regions)
                    paragraph = None
                fence = (opened.group(1)[0], len(opened.group(1)), end - len(opened.group(1)) - len(opened.group(2)))
            elif js_trim(line) == "":
                if paragraph is not None:
                    _inline_spans(text, paragraph[0], paragraph[1], regions)
                    paragraph = None
            else:
                paragraph = (at, end) if paragraph is None else (paragraph[0], end)
        at = end + 1
    if fence is not None:
        regions.append((fence[2], n))
    if paragraph is not None:
        _inline_spans(text, paragraph[0], paragraph[1], regions)
    return sorted(regions)


def _inside(regions):
    starts = [r[0] for r in regions]

    def inside(offset):
        i = bisect.bisect_right(starts, offset) - 1
        return i >= 0 and offset < regions[i][1]
    return inside


def _reading(text, regions):
    inside = _inside(regions)
    tokens = [m for m in TAG.finditer(text) if not inside(m.start())]
    stack, balanced = [], True
    for token in tokens:
        if not token.group(1):
            stack.append(token.group(2))
        elif stack and stack[-1] == token.group(2):
            stack.pop()
        else:
            balanced = False
            stack.clear()
    return tokens, balanced and not stack


def _span(text, is_open):
    return {"kind": KIND, "text": text, "isOpen": is_open}


def _parse_marked(text):
    tokens, balanced = _reading(text, code_regions(text))
    if not balanced:
        glued, glued_balanced = _reading(text, code_regions(text, GLUED))
        if glued_balanced:
            tokens = glued
    spans = []
    # One entry per open mark, innermost last: [tag, its current run of text,
    # or None once an inner mark has interrupted it].
    stack = []
    outside = []

    def take(piece):
        if not stack:
            outside.append(piece)
        elif stack[-1][1] is not None:
            stack[-1][1]["text"] += piece
        elif js_trim(piece) != "":
            stack[-1][1] = _span(piece, True)
            spans.append(stack[-1][1])

    def close(entry):
        if entry[1] is not None:
            entry[1]["isOpen"] = False
        entry[1] = None

    last = 0
    for token in tokens:
        take(text[last:token.start()])
        last = token.end()
        if token.group(1) == "":
            if stack:
                close(stack[-1])
            span = _span("", True)
            spans.append(span)
            stack.append([token.group(2), span])
        else:
            tags = [entry[0] for entry in stack]
            if token.group(2) not in tags:
                continue  # a stray closing tag: nothing to close
            depth = len(tags) - 1 - tags[::-1].index(token.group(2))
            while len(stack) > depth:
                close(stack.pop())
    take(text[last:])
    for span in spans:
        span["text"] = js_trim(span["text"])
    return {"spans": [s for s in spans if s["text"] != "" or s["isOpen"]],
            "hasRecord": js_trim("".join(outside)) != ""}


_LABELS = "message|to human|essential|need input|insight"
RENDERED = re.compile("\x1b\\[1;(3[2356]|38;2;215;119;87)m(?:" + _LABELS + ")\x1b\\[0m|\x1b\\[2m([\\s\\S]*?)\x1b\\[0m")
HEADER = re.compile("\x1b\\[1;(?:3[2356]|38;2;215;119;87)m(?:" + _LABELS + ")\x1b\\[0m")
SGR = re.compile("\x1b\\[[0-9;]*m")


def _parse_rendered(text):
    """A header opens a span that runs to the next header; a dimmed run is
    record and ends the span it follows. None when no header is real."""
    inside = _inside(code_regions(SGR.sub("", text)))
    spans, outside = [], []
    current = None
    last = visible_at = 0
    has_header = False

    def take(piece):
        if piece == "":
            return
        if current is not None:
            current["text"] += piece
        else:
            outside.append(piece)

    for match in RENDERED.finditer(text):
        whole, color, dimmed = match.group(0), match.group(1), match.group(2)
        before = text[last:match.start()]
        take(before)
        visible_at += len(SGR.sub("", before))
        last = match.end()
        if color is not None and inside(visible_at):
            take(whole)
        elif color is not None:
            has_header = True
            current = _span("", False)
            spans.append(current)
        else:
            current = None
            outside.append(dimmed or "")
        visible_at += len(SGR.sub("", whole))
    take(text[last:])
    for span in spans:
        span["text"] = js_trim(span["text"])
    if not has_header:
        return None
    return {"spans": [s for s in spans if s["text"] != ""], "hasRecord": js_trim("".join(outside)) != ""}


def parse(text):
    """{"spans": [{"kind", "text", "isOpen"}], "hasRecord"}: one assistant
    text's marked spans, as the mod's `parse` returns them."""
    parsed = _parse_rendered(text) if HEADER.search(text) else None
    return parsed if parsed is not None else _parse_marked(text)
