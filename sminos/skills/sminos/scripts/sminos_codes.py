#!/usr/bin/env python3
"""sminos_codes — canonical JSON and base64url, as the desk's TypeScript
writes them.

What RL10 checks byte for byte goes through here: a record act's proof
(sminos_rpc.record_proof), an RPC's nonce and an operation's id, a decide
request's digest (`input_sha256`), a part's id, a log seq's and a
timestamp's shape.

The canonical form is the hub's TypeScript byte for byte (pinned by
tests/codes_parity.py against the desk's shared numbers and digests,
tests/dx1-codes.json): keys ordered by
UTF-16 code units, strings as ECMAScript's JSON.stringify writes them, every
number as the IEEE-754 double nearest it written as ECMAScript's
Number::toString writes that double. What I-JSON forbids is refused: a lone
surrogate (a str here holds no surrogate pairs, so any surrogate code point is
one), NaN, and the infinities. Base64url is canonical (RFC 4648 §3.5): no
padding, the unused low bits of the last character zero, one spelling per
byte string; every other spelling is refused, never normalized.

Stdlib only: sminos installs nothing beside itself, and runs on any Python of
sminos.MIN_PYTHON or newer (macOS's own /usr/bin/python3 is older).
"""

import base64
import binascii
import hashlib
import json
import json.encoder
import math
import re

NONCE_BYTES = 16
B64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
B64URL_RE = re.compile(r"[A-Za-z0-9_-]*")
SURROGATE_RE = re.compile("[\ud800-\udfff]")
MEMBER_RE = re.compile(r"[0-9a-f]{32}")
ISO_MILLIS_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})\.[0-9]{3}Z")
MAX_SAFE = 2 ** 53 - 1
EXACT = 2 ** 53  # every integer no larger in magnitude is a double exactly
_quoted = json.encoder.encode_basestring  # string()'s writer: the json module's own (C) quoting


class NotCanonical(ValueError):
    """A value the canonical form refuses: not JSON, or not I-JSON."""


# ------------------------------------------------------------- base64url


def b64url(raw):
    """Base64url without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text):
    """The bytes `text` encodes, or None: anything but the one unpadded
    base64url encoding of some bytes (another alphabet, padding, a length no
    encoding has, spare bits set) is not a value."""
    if not isinstance(text, str) or not B64URL_RE.fullmatch(text):
        return None
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        return None
    return raw if b64url(raw) == text else None


def b64url_bytes(text, size):
    """The `size` bytes `text` encodes, or None (b64url_decode, of exactly
    `size` bytes)."""
    raw = b64url_decode(text)
    return raw if raw is not None and len(raw) == size else None


# ------------------------------------------------------------- JSON in


def _no_constant(name):
    raise NotCanonical("%s is not a JSON number" % name)


def _finite(text):
    x = float(text)
    if math.isinf(x):
        raise NotCanonical("%s overflows a double" % text)
    return x


def loads(text):
    """JSON as the wire carries it: Python's reader without its NaN and
    Infinity words, and refusing a number that overflows a double."""
    try:
        return json.loads(text, parse_constant=_no_constant, parse_float=_finite)
    except RecursionError as e:
        raise NotCanonical("nested too deep") from e


# ------------------------------------------------------------- canonical JSON


def number(value):
    """ECMAScript's Number::toString of the double nearest `value` (RFC 8785
    §3.2.2.3). repr() of a float is its shortest round-tripping digits, as
    ECMAScript's are; the layout is ECMAScript's: for digits s (k of them) and
    value 0.s × 10^n, plain while -6 < n <= 21, else d[.ddd]e±(n-1). An
    integer a double holds exactly (no larger in magnitude than 2^53, at most
    16 digits) is that layout's plain case: its own digits."""
    if type(value) is int and -EXACT <= value <= EXACT:
        return str(value)
    try:
        x = float(value)
    except OverflowError as e:
        raise NotCanonical("%r is past the largest double" % (value,)) from e
    if not math.isfinite(x):
        raise NotCanonical("%r is not a JSON number" % (value,))
    if x == 0:
        return "0"  # negative zero too
    sign = "-" if x < 0 else ""
    mantissa, _, exp = repr(abs(x)).partition("e")
    whole, _, frac = mantissa.partition(".")
    digits = (whole + frac).lstrip("0")
    scale = int(exp or 0) - len(frac)  # the value is int(digits) × 10^scale
    stripped = digits.rstrip("0")
    scale += len(digits) - len(stripped)
    s, k = stripped, len(stripped)
    n = k + scale
    if k <= n <= 21:
        out = s + "0" * (n - k)
    elif 0 < n <= 21:
        out = s[:n] + "." + s[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * -n + s
    else:
        out = s[0] + ("." + s[1:] if k > 1 else "") + "e" + ("+" if n - 1 >= 0 else "-") + str(abs(n - 1))
    return sign + out


def string(text):
    """A string as ECMAScript's JSON.stringify writes it; a lone surrogate is
    refused. Python's JSON encoder with ensure_ascii off (its C function)
    writes exactly that: `"` and `\\` escaped, every character below U+0020
    as JSON.stringify's short escape (\\b \\t \\n \\f \\r) or else \\u00xx in
    lower-case hex, and every other character as itself (U+007F, U+2028,
    U+2029 and astral characters too). An ASCII string holds no surrogate."""
    if not text.isascii() and SURROGATE_RE.search(text):
        raise NotCanonical("a string holds a lone surrogate")
    return _quoted(text)


def canonical(value):
    """RFC 8785 (JCS) text of a JSON value."""
    if type(value) is str:  # most of what an event holds
        return string(value)
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return number(value)
    if isinstance(value, str):
        return string(value)
    # The joins take generators, not lists: a list comprehension is inlined since Python 3.12, which would let
    # canonical() write nesting twice as deep as it refuses (RecursionError) now.
    if isinstance(value, list):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise NotCanonical("an object key that is not a string")
        if all(type(k) is str and k.isascii() for k in value):
            # No surrogate to refuse, and the keys' own order is that of their UTF-16 code units (a str
            # subclass may compare otherwise).
            return "{" + ",".join(_quoted(k) + ":" + canonical(value[k]) for k in sorted(value)) + "}"
        keyed = [(string(k), k) for k in value]  # refuses a lone surrogate before the sort encodes it
        keyed.sort(key=lambda pair: pair[1].encode("utf-16-be"))
        return "{" + ",".join(text + ":" + canonical(value[k]) for text, k in keyed) + "}"
    raise NotCanonical("%s is not JSON" % type(value).__name__)


# ------------------------------------------------------------- digests


def input_sha256(tool_input):
    """The request digest's `input_sha256`: lowercase hex SHA-256 of the tool
    input's canonical JSON."""
    return hashlib.sha256(canonical(tool_input).encode("utf-8")).hexdigest()


# ------------------------------------------------------------- shapes


def is_log_seq(seq):
    """A JSON number whose value is a positive integer no larger than 2^53 - 1
    (a bool is not a number; 3.0 is the number 3)."""
    if isinstance(seq, bool) or not isinstance(seq, (int, float)):
        return False
    if isinstance(seq, float) and not seq.is_integer():
        return False
    return 1 <= seq <= MAX_SAFE


def is_iso_millis(ts):
    """YYYY-MM-DDTHH:MM:SS.mmmZ naming a real calendar day (Gregorian leap
    years), an hour below 24, minutes and seconds below 60 — by these rules,
    not a date library's, so the hub's TypeScript and this agree on every
    string."""
    m = ISO_MILLIS_RE.fullmatch(ts) if isinstance(ts, str) else None
    if not m:
        return False
    year, month, day, hour, minute, second = (int(g) for g in m.groups())
    if not 1 <= month <= 12:
        return False
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    days = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]
    return 1 <= day <= days and hour < 24 and minute < 60 and second < 60
