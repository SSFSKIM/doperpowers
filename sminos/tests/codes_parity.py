"""Parity of sminos_codes's canonical JSON with the desk's TypeScript: every
number and digest of dx1-codes.json, copied verbatim from MAWS commit
e6bb0160 (apps/desk-hub/src/protocol/vectors/codes.json, written by
generate.py beside it; its code vectors and negatives went with DX1's codes,
#153), reproduced byte for byte; then what the canonical form refuses that
the file does not hold — lone surrogates, NaN and the infinities — the
canonical text against its definition written out here (every Unicode
scalar value, every surrogate, random strings and values, the key order,
integers about 2^53), base64url's one spelling of 32 and 16 bytes and what
it refuses, and a log position's seq and ts by shape (is_log_seq,
is_iso_millis). Prints one `ok <name>` or `FAIL <name>` line per case, for
run-sminos-tests.sh to count.

    python3 codes_parity.py <skills/sminos/scripts> <dx1-codes.json>
"""

import json
import random
import sys

sys.path.insert(0, sys.argv[1])
import sminos_codes as codes  # noqa: E402

VECTORS = json.load(open(sys.argv[2], encoding="utf-8"))
FAILED = []


def check(name, ok, detail=""):
    print(("ok " if ok else "FAIL ") + name + ("" if ok else " — %s" % detail))
    if not ok:
        FAILED.append(name)


def raises(fn, *args):
    try:
        fn(*args)
    except codes.NotCanonical:
        return True
    return False


# ---- the file, every entry
for n in VECTORS["numbers"]:
    got = codes.canonical(codes.loads(n["json"]))
    check("number %s → %s (%s)" % (n["json"], n["canonical"], n["why"]), got == n["canonical"], got)

for d in VECTORS["digests"]:
    got = codes.canonical(d["input"])
    check("digest %s: canonical" % d["name"], got == d["canonical"], got)
    got = codes.input_sha256(d["input"])
    check("digest %s: input_sha256" % d["name"], got == d["input_sha256"], got)

# ---- what the canonical form refuses
for name, value in (
    ("a lone high surrogate in a string", {"text": "a \ud83d b"}),
    ("a lone low surrogate in a string", {"text": "\ude00"}),
    ("a lone surrogate in a key", {"k\ud800": 1}),
    ("a lone surrogate in a nested array", {"a": [["\udfff"]]}),
    ("NaN", {"n": float("nan")}),
    ("infinity", {"n": float("inf")}),
    ("negative infinity", {"n": float("-inf")}),
    ("an integer past the largest double", {"n": 10 ** 400}),
    ("a non-string key", {1: "one"}),
    ("a value JSON has no word for", {"b": b"bytes"}),
):
    check("canonical refuses %s" % name, raises(codes.canonical, value))

for text in ("NaN", "Infinity", "-Infinity", '{"n": NaN}', "[Infinity]", "1e400", "-1e400", '{"n": 1e999}'):
    check("loads refuses %s" % text, raises(codes.loads, text))
check("loads reads a lone surrogate escape (canonical refuses it)", raises(codes.canonical, codes.loads('"\\ud800"')))
check("loads reads an escaped surrogate pair as one character", codes.loads('"\\ud83d\\ude00"') == "\U0001f600")

# ---- the encoder against its definition, past the vectors: a string as JSON.stringify writes it, one character at a
# time (sminos_codes's own encoder until it took the json module's C quoting), an object's keys in the order of their
# UTF-16 code units, an integer as the double it is.
SHORT = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def defined(value):
    """The RFC 8785 text of a value, written out by the definition; None where there is none."""
    if isinstance(value, str):
        if any("\ud800" <= ch <= "\udfff" for ch in value):
            return None
        return '"' + "".join(SHORT.get(ch) or ("\\u%04x" % ord(ch) if ch < " " else ch) for ch in value) + '"'
    if isinstance(value, list):
        items = [defined(item) for item in value]
        return None if None in items else "[" + ",".join(items) + "]"
    if isinstance(value, dict):
        texts = {k: (defined(k), defined(v)) for k, v in value.items()}
        if any(None in pair for pair in texts.values()):
            return None  # a lone surrogate in a key is refused before the sort, which cannot encode one
        return "{" + ",".join("%s:%s" % texts[k] for k in sorted(value, key=lambda k: k.encode("utf-16-be"))) + "}"
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    try:
        return written(codes.number, float(value))
    except OverflowError:
        return None


def written(fn, value):
    try:
        return fn(value)
    except codes.NotCanonical:
        return None


def agree(name, values, fn=codes.canonical):
    n, differ = 0, []
    for value in values:
        n += 1
        if written(fn, value) != defined(value):
            differ.append(value)
    check("%s: as defined (%d)" % (name, n), not differ, "%d differ, the first %r" % (len(differ), differ[:1]))


SCALARS = [c for c in range(0x110000) if not 0xD800 <= c <= 0xDFFF]
agree("every Unicode scalar value, alone", (chr(c) for c in SCALARS), codes.string)
agree("every Unicode scalar value, in runs of 61 beside its neighbours",
      ("".join(chr(c) for c in SCALARS[i:i + 61]) for i in range(0, len(SCALARS), 61)), codes.string)
agree("every surrogate code point, alone and amid ASCII, Latin-1, Hangul and astral text (refused)",
      (pre + chr(c) + post for c in range(0xD800, 0xE000)
       for pre, post in (("", ""), ("x", "\u00e9"), ("\ud55c", "\U0001F600"), ("\U0001F600", "\n"))), codes.string)
rng = random.Random(8785)
RANGES = ((0, 0x20), (0x20, 0x7F), (0x7F, 0x100), (0x100, 0xD800), (0xE000, 0x10000), (0x10000, 0x110000))
NAMED = '"\\\b\f\n\r\t\x00\x1f\x7f\u2028\u2029\ufeff\uffff\ue000\U00010000\U0001F600\U0010FFFF'


def any_string(most=24):
    return "".join(rng.choice(NAMED) if rng.random() < 0.3 else chr(rng.randrange(*rng.choice(RANGES)))
                   for _ in range(rng.randrange(most)))


def any_value(depth=0):
    x = rng.random()
    if depth > 2 or x < 0.4:
        return any_string()
    if x < 0.55:
        return rng.choice([None, True, False, 0, -1, 2 ** 53, -(2 ** 53) - 1, 1.5, 1e21, 1e-7, float("nan")])
    if x < 0.7:
        return [any_value(depth + 1) for _ in range(rng.randrange(4))]
    ascii_keys = rng.random() < 0.5
    return {("".join(chr(rng.randrange(0x20, 0x7F)) for _ in range(rng.randrange(5))) if ascii_keys else any_string(6)):
            any_value(depth + 1) for _ in range(rng.randrange(8))}


agree("random strings of controls, escapes, U+007F, U+2028/2029, BMP and astral characters",
      (any_string() for _ in range(30000)), codes.string)
agree("random strings with a lone surrogate among them (refused)",
      (s[:i] + chr(rng.randrange(0xD800, 0xE000)) + s[i:] for s in (any_string() for _ in range(3000))
       for i in (rng.randrange(len(s) + 1),)), codes.string)
agree("random values: objects of ASCII keys and of any keys, nested", (any_value() for _ in range(10000)))
ORDER = ["\uffff", "\U0001F600", "\ue000", "\U00010000", "\ud7ff", "a", "", "\x7f", "\u2028", "\U0010FFFF", "ab",
         "a\U0001F600", "a\uffff", "\u00e9", "Z"]
agree("objects whose keys' UTF-16 order is not their code point order, shuffled",
      ({k: i for i, k in enumerate(rng.sample(ORDER, len(ORDER)))} for _ in range(500)))


class Folded(str):
    """A key that compares without case: its place is still that of its UTF-16 code units."""

    def __lt__(self, other):
        return self.casefold() < other.casefold()


agree("an object whose keys are a str subclass with an order of its own", [{Folded("a"): 1, Folded("Z"): 2, Folded("b"): 3}])
agree("integers about 2^53, 10^21 and past the largest double, and of every bit length to 64",
      [s * x for s in (1, -1) for x in (2 ** 53 - 1, 2 ** 53, 2 ** 53 + 1, 2 ** 53 + 2, 10 ** 21, 10 ** 21 + 1, 2 ** 1024)]
      + [s * rng.getrandbits(b) for b in range(65) for s in (1, -1) for _ in range(40)], codes.number)

def respelled(text):
    """The canonical spelling's last character with a spare bit set: the same bytes, written another way."""
    i = codes.B64URL_ALPHABET.index(text[-1])
    assert i & 3 == 0, text  # a 43-character code has 2 spare bits, a 22-character nonce 4: clear in the original
    return text[:-1] + codes.B64URL_ALPHABET[i | 1]


KEY = bytes(range(32))
check("the strict decoder never normalizes: 32 bytes respelled decode to nothing, their one spelling to the bytes",
      codes.b64url_bytes(respelled(codes.b64url(KEY)), 32) is None and codes.b64url_bytes(codes.b64url(KEY), 32) == KEY)
NONCE = KEY[:codes.NONCE_BYTES]
check("and so do a nonce's 16 bytes (an RPC's nonce)",
      codes.b64url_bytes(respelled(codes.b64url(NONCE)), codes.NONCE_BYTES) is None
      and codes.b64url_bytes(codes.b64url(NONCE), codes.NONCE_BYTES) == NONCE)
check("the empty string is no code's or nonce's bytes (it encodes none)",
      codes.b64url_bytes("", 32) is None and codes.b64url_bytes("", codes.NONCE_BYTES) is None)
for name, text in (
    ("what is not a string", 3),
    ("characters outside the alphabet (standard base64's + and /)", codes.b64url(KEY).replace("A", "+", 1) + "/"),
    ("padding", codes.b64url(NONCE) + "=="),
):
    check("base64url refuses %s" % name, codes.b64url_decode(text) is None and codes.b64url_bytes(text, 32) is None)

# ---- a log position's seq and ts, by shape: what RL10's refusal, runs and spent positions read
# (hublog.refusal, runs_of, spent; records' proofs). The cases DX1's hub/ position tests held.
for name, seq in (("1", 1), ("the largest safe seq", 2 ** 53 - 1), ("3.0, the number 3 as JSON.parse reads it", 3.0)):
    check("a log seq holds: %s" % name, codes.is_log_seq(seq))
for name, seq in (("0", 0), ("-1", -1), ("1.5", 1.5), ("2^53", 2 ** 53), ("a string", "1"), ("true", True),
                  ("false", False), ("null", None)):
    check("a log seq fails: %s" % name, not codes.is_log_seq(seq))
for name, ts in (("a common day", "2026-10-15T08:00:00.000Z"), ("a leap day", "2024-02-29T23:59:59.999Z"),
                 ("2000's leap day", "2000-02-29T00:00:00.000Z")):
    check("an ISO ts holds: %s" % name, codes.is_iso_millis(ts))
for name, ts in (
    ("February 29 of a common year", "2026-02-29T08:00:00.000Z"),
    ("1900's February 29, a century not a leap year", "1900-02-29T08:00:00.000Z"),
    ("month 13", "2026-13-01T08:00:00.000Z"),
    ("day 0", "2026-10-00T08:00:00.000Z"),
    ("hour 24", "2026-10-15T24:00:00.000Z"),
    ("second 60", "2026-12-31T23:59:60.000Z"),
    ("an offset", "2026-10-15T08:00:00.000+09:00"),
    ("a lower-case z", "2026-10-15T08:00:00.000z"),
    ("a full-width digit", "\uff12026-10-15T08:00:00.000Z"),
    ("whole seconds", "2026-10-15T08:00:00Z"),
    ("what is not a string", 1761000000000),
):
    check("an ISO ts fails: %s" % name, not codes.is_iso_millis(ts))

sys.exit(1 if FAILED else 0)
