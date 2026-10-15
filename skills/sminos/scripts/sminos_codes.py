#!/usr/bin/env python3
"""sminos_codes — the desk's authentication codes (DX1 of the desk composite).

Everything the hub carries that can cause execution carries a code: HMAC-SHA256,
keyed with the org key (which the hub never holds), over the bytes

    <domain> LF <project id> LF <RFC 8785 canonical JSON of the covered object>

The covered object is the shape without the code's own value: a shape whose
`mac` is {nonce, value} is covered with `mac` reduced to {nonce}; a log event
of a `hub/` writer leaves out `writer`, `seq`, and `ts` too (the hub assigns
them after the browser computed the code), so those are checked by shape
instead (`is_hub_position`); an RPC carries its nonce as its own field and the
value alone as `mac`, and is covered without `mac`.

The canonical form is the hub's TypeScript byte for byte (pinned by
tests/sminos/codes_parity.py against the shared vectors): keys ordered by
UTF-16 code units, strings as ECMAScript's JSON.stringify writes them, every
number as the IEEE-754 double nearest it written as ECMAScript's
Number::toString writes that double. What I-JSON forbids is refused: a lone
surrogate (a str here holds no surrogate pairs, so any surrogate code point is
one), NaN, and the infinities. Base64url is canonical (RFC 4648 §3.5): no
padding, the unused low bits of the last character zero, one spelling per
byte string; every other spelling is refused, never normalized. A verifier
never raises: whatever the canonical form refuses, a code value that is not
the canonical spelling of 32 bytes, or a nonce not that of 16, fails; the code
is compared in constant time.

Stdlib only: the daemon runs on the system's Python.
"""

import base64
import binascii
import hashlib
import hmac
import json
import math
import re

DOMAINS = {
    "log": "smns-hub-log-v1",
    "rpc": "smns-hub-rpc-v1",
    "raised": "smns-hub-raised-v1",
    "settled": "smns-hub-settled-v1",
    "delivery": "smns-hub-delivery-v1",
}
CODE_BYTES = 32
NONCE_BYTES = 16
HUB_PREFIX = "hub/"
B64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
B64URL_RE = re.compile(r"[A-Za-z0-9_-]*")
SURROGATE_RE = re.compile("[\ud800-\udfff]")
SHORT_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}
MEMBER_RE = re.compile(r"[0-9a-f]{32}")
ISO_MILLIS_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})\.[0-9]{3}Z")
MAX_SAFE = 2 ** 53 - 1


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
    value 0.s × 10^n, plain while -6 < n <= 21, else d[.ddd]e±(n-1)."""
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
    """A string as ECMAScript's JSON.stringify writes it; a lone surrogate is refused."""
    if SURROGATE_RE.search(text):
        raise NotCanonical("a string holds a lone surrogate")
    out = ['"']
    for ch in text:
        if ch in SHORT_ESCAPES:
            out.append(SHORT_ESCAPES[ch])
        elif ch < " ":
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def canonical(value):
    """RFC 8785 (JCS) text of a JSON value."""
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
    if isinstance(value, list):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise NotCanonical("an object key that is not a string")
        keyed = [(string(k), k) for k in value]  # refuses a lone surrogate before the sort encodes it
        keyed.sort(key=lambda pair: pair[1].encode("utf-16-be"))
        return "{" + ",".join(text + ":" + canonical(value[k]) for text, k in keyed) + "}"
    raise NotCanonical("%s is not JSON" % type(value).__name__)


# ------------------------------------------------------------- the code


def is_hub_writer(writer):
    return isinstance(writer, str) and writer.startswith(HUB_PREFIX)


def covered(kind, shape):
    """The object the code covers. NotCanonical when there is none: not an
    object, or no string nonce."""
    if not isinstance(shape, dict):
        raise NotCanonical("a shape is an object")
    out = dict(shape)
    if kind == "rpc":
        if not isinstance(shape.get("nonce"), str):
            raise NotCanonical("an RPC carries a string nonce")
        out.pop("mac", None)
        return out
    mac = shape.get("mac")
    if not (isinstance(mac, dict) and isinstance(mac.get("nonce"), str)):
        raise NotCanonical("the shape carries no mac nonce")
    out["mac"] = {"nonce": mac["nonce"]}
    if kind == "log" and is_hub_writer(shape.get("writer")):
        for field in ("writer", "seq", "ts"):
            out.pop(field, None)
    return out


def covered_bytes(kind, project, shape):
    return (DOMAINS[kind] + "\n" + project + "\n" + canonical(covered(kind, shape))).encode("utf-8")


def _digest(key, kind, project, shape):
    return hmac.new(key, covered_bytes(kind, project, shape), hashlib.sha256).digest()


def code(key, kind, project, shape):
    """The shape's code, base64url (43 characters)."""
    return b64url(_digest(key, kind, project, shape))


def seal(key, kind, project, draft, nonce):
    """A shape drawn up without its code (`mac`), sealed under `nonce`. An RPC
    carries its nonce already, as its id, and gets the code alone as `mac`."""
    if kind == "rpc":
        return {**draft, "mac": code(key, kind, project, draft)}
    shape = {**draft, "mac": {"nonce": nonce}}
    return {**draft, "mac": {"nonce": nonce, "value": code(key, kind, project, shape)}}


def failure(key, kind, project, shape):
    """What an importer checks before anything enters the log or is acted on,
    in DX1's order, and the first that refuses: "encoding" (the code's value
    and its nonce are not the canonical base64url of 32 and 16 bytes),
    "position" (a `hub/` log event's writer, seq, or ts fails its shape), or
    "code" (the code does not match, or the shape has no canonical form). None
    when the shape verifies. Never raises."""
    if not isinstance(shape, dict):
        return "encoding"
    mac = shape.get("mac")
    if kind == "rpc":
        value, nonce = mac, shape.get("nonce")
    else:
        value, nonce = (mac.get("value"), mac.get("nonce")) if isinstance(mac, dict) else (None, None)
    want = b64url_bytes(value, CODE_BYTES)
    if want is None or b64url_bytes(nonce, NONCE_BYTES) is None:
        return "encoding"
    if kind == "log" and is_hub_writer(shape.get("writer")) and not is_hub_position(shape):
        return "position"
    try:
        got = _digest(key, kind, project, shape)
    except (NotCanonical, RecursionError):
        return "code"
    return None if hmac.compare_digest(got, want) else "code"


def verifies(key, kind, project, shape):
    """Whether a shape verifies (`failure` finds nothing)."""
    return failure(key, kind, project, shape) is None


def input_sha256(tool_input):
    """The request digest's `input_sha256`: lowercase hex SHA-256 of the tool
    input's canonical JSON."""
    return hashlib.sha256(canonical(tool_input).encode("utf-8")).hexdigest()


# ------------------------------------------------------------- a hub/ event's position


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


def is_hub_position(event):
    """What a `hub/` event's code leaves out, checked by shape (DX1): its
    writer is exactly `hub/` and its own member (32 lower-case hex, which the
    code covers), its seq a positive integer, its ts ISO 8601 UTC with
    milliseconds. Delivery writes the writer into the frame a session reads,
    so an unchecked one would carry text no code covers."""
    member = event.get("member")
    return (isinstance(member, str) and MEMBER_RE.fullmatch(member) is not None
            and event.get("writer") == HUB_PREFIX + member
            and is_log_seq(event.get("seq")) and is_iso_millis(event.get("ts")))
