"""`KEY=value` files: the profile's `profile.env`, the boot descriptor, and
`/etc/devcloud/env`, which every reader must see alike — zsh and bash source
it, systemd reads it as an `EnvironmentFile`, and `devcloud-services` parses
it here.

`format` writes every value double-quoted with `\\`, `"`, `$` and a backtick
escaped, the one quoting POSIX shells and systemd both read the same way, and
refuses what neither can hold on one line. `parse` reads that, single quotes,
bare words and `export`, and expands `$NAME` / `${NAME}` outside single quotes
from the file's earlier lines and then `base` (an unknown name is empty, as in
a shell), so a profile line like `PATH="$HOME/bin:$PATH"` is resolved once and
every reader gets the same value. Errors name the line, never its value.
"""

import re

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_ASSIGN = re.compile(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=")
_REF = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
_ESCAPED = '"\\$`'


def _expand(text, scope):
    return _REF.sub(lambda m: scope.get(m.group(1) or m.group(2), ""), text)


def _value(rest, scope):
    """The value an assignment's right-hand side holds, and what follows it."""
    out = []
    i = 0
    while i < len(rest) and not rest[i].isspace():
        c = rest[i]
        if c == "'":
            end = rest.find("'", i + 1)
            if end < 0:
                raise ValueError("unterminated single quote")
            out.append(rest[i + 1:end])
            i = end + 1
        elif c == '"':
            i += 1
            chunk = []
            while True:
                if i >= len(rest):
                    raise ValueError("unterminated double quote")
                c = rest[i]
                if c == '"':
                    i += 1
                    break
                if c == "\\" and i + 1 < len(rest) and rest[i + 1] in _ESCAPED:
                    # An escaped `$` stays out of expansion: mark it, restore after.
                    chunk.append("\0" if rest[i + 1] == "$" else rest[i + 1])
                    i += 2
                    continue
                chunk.append(c)
                i += 1
            out.append(_expand("".join(chunk), scope).replace("\0", "$"))
        else:
            j = i
            while j < len(rest) and not rest[j].isspace() and rest[j] not in "'\"":
                j += 1
            word = rest[i:j]
            if "\\" in word:
                raise ValueError("a backslash outside quotes")
            out.append(_expand(word, scope))
            i = j
    return "".join(out), rest[i:]


def parse(text, base=None):
    """The assignments in `text`, in order, expanded against `base`."""
    scope = dict(base or {})
    result = {}
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGN.match(line)
        if not match:
            raise ValueError(f"line {number}: not a KEY=value assignment")
        try:
            value, after = _value(line[match.end():], scope)
        except ValueError as error:
            raise ValueError(f"line {number}: {error}") from None
        after = after.strip()
        if after and not after.startswith("#"):
            raise ValueError(f"line {number}: unquoted whitespace in the value (quote it)")
        key = match.group(1)
        result[key] = value
        scope[key] = value
    return result


def quote(value):
    return '"' + "".join("\\" + c if c in _ESCAPED else c for c in value) + '"'


def format(pairs):
    """`KEY="value"` lines for (key, value) pairs."""
    lines = []
    for key, value in pairs:
        if not NAME.match(key):
            raise ValueError(f"{key!r} is not an environment variable name")
        if "\n" in value or "\r" in value or "\0" in value:
            raise ValueError(f"{key}: a value spanning lines or holding NUL cannot go in an env file")
        lines.append(f"{key}={quote(value)}\n")
    return "".join(lines)
