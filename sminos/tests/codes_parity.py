"""Parity of sminos_codes with DX1 (the desk composite's authentication code):
every number, digest, vector, and negative of dx1-codes.json, copied
verbatim from MAWS commit e6bb0160
(apps/desk-hub/src/protocol/vectors/codes.json, written by generate.py beside
it), reproduced byte for byte or refused, each negative by the first check
that refuses it, as its `fails_by` names (DX1's order: the encoding of its
code and nonce, a `hub/` event's position, the code); then what DX1 refuses
that the file does not hold — lone surrogates, NaN and the infinities, a code
or nonce that is not the canonical base64url of 32 or 16 bytes — and the
position cases generate.py asserts but does not write out.
Prints one `ok <name>` or `FAIL <name>` line per case, for
run-sminos-tests.sh to count.

    python3 codes_parity.py <skills/sminos/scripts> <dx1-codes.json>
"""

import copy
import json
import sys

sys.path.insert(0, sys.argv[1])
import sminos_codes as codes  # noqa: E402

VECTORS = json.load(open(sys.argv[2], encoding="utf-8"))
KIND_OF = {domain: kind for kind, domain in codes.DOMAINS.items()}
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

for v in VECTORS["vectors"]:
    kind, key = KIND_OF[v["domain"]], codes.b64url_bytes(v["org_key"], 32)
    shape = codes.loads(json.dumps(v["input"], ensure_ascii=False))
    raw = codes.covered_bytes(kind, v["project"], shape)
    check("vector %s: covered bytes" % v["name"], raw == bytes.fromhex(v["covered_hex"]), raw[:120])
    check("vector %s: covered text" % v["name"], raw.decode("utf-8") == v["covered"])
    got = codes.code(key, kind, v["project"], shape)
    check("vector %s: code" % v["name"], got == v["code"], got)
    check("vector %s: verifies" % v["name"], codes.verifies(key, kind, v["project"], shape))

for neg in VECTORS["negatives"]:
    kind, key = KIND_OF[neg["domain"]], codes.b64url_bytes(neg["org_key"], 32)
    shape = codes.loads(json.dumps(neg["input"], ensure_ascii=False))
    check("negative %s (%s): refused" % (neg["name"], neg["why"]), not codes.verifies(key, kind, neg["project"], shape))
    by = codes.failure(key, kind, neg["project"], shape)
    check("negative %s: fails by %s" % (neg["name"], neg.get("fails_by")), by == neg.get("fails_by"), by)
    # Each label checked by its own means too: an encoding refused by the strict decoder, a position by the shape
    # check, a code by a computed code that differs from the stored one.
    value = shape.get("mac") if kind == "rpc" else (shape.get("mac") or {}).get("value")
    nonce = shape.get("nonce") if kind == "rpc" else (shape.get("mac") or {}).get("nonce")
    if neg.get("fails_by") == "encoding":
        check("negative %s: its code or nonce is not canonical base64url" % neg["name"],
              codes.b64url_bytes(value, 32) is None or codes.b64url_bytes(nonce, 16) is None)
    elif neg.get("fails_by") == "position":
        check("negative %s: its position fails its shape" % neg["name"], not codes.is_hub_position(shape))
    else:
        check("negative %s: its code differs" % neg["name"], codes.code(key, kind, neg["project"], shape) != value)

# ---- what the canonical form refuses
KEY = bytes(range(32))
VEC = {v["name"]: v for v in VECTORS["vectors"]}
SAY = VEC["say-ascii"]["input"]
HUB = VEC["hub-human"]["input"]
RPC = VEC["rpc-decide"]["input"]
PROJECT = VEC["say-ascii"]["project"]


def altered(event, fn):
    e = copy.deepcopy(event)
    fn(e)
    return e


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

def respelled(text):
    """The canonical spelling's last character with a spare bit set: the same bytes, written another way."""
    i = codes.B64URL_ALPHABET.index(text[-1])
    assert i & 3 == 0, text  # a 43-character code has 2 spare bits, a 22-character nonce 4: clear in the original
    return text[:-1] + codes.B64URL_ALPHABET[i | 1]


# What the file does not carry (it carries a padded value, and spare bits in an event's value and nonce and in an
# RPC's code), each with the first check that refuses it.
for name, fails_by, fn in (
    ("a lone surrogate in a covered field", "code", lambda e: e.update(text="x \udc00")),
    ("a lone surrogate in an unknown field's key", "code", lambda e: e.update({"m\ud83d": "x"})),
    ("NaN in an unknown field", "code", lambda e: e.update(n=float("nan"))),
    ("an infinity in an unknown field", "code", lambda e: e.update(n=float("inf"))),
    ("no mac", "encoding", lambda e: e.pop("mac")),
    ("a mac that is not an object", "encoding", lambda e: e.update(mac="x")),
    ("a mac without a nonce", "encoding", lambda e: e["mac"].pop("nonce")),
    ("a null nonce", "encoding", lambda e: e["mac"].update(nonce=None)),
    ("a numeric nonce", "encoding", lambda e: e["mac"].update(nonce=1)),
    ("an empty nonce", "encoding", lambda e: e["mac"].update(nonce="")),
    ("a nonce one byte short", "encoding", lambda e: e["mac"].update(nonce=codes.b64url(bytes(15)))),
    ("a nonce one byte long", "encoding", lambda e: e["mac"].update(nonce=codes.b64url(bytes(17)))),
    ("a padded nonce", "encoding", lambda e: e["mac"].update(nonce=e["mac"]["nonce"] + "==")),
    ("a nonce outside base64url", "encoding", lambda e: e["mac"].update(nonce="!" * 22)),
    ("no value", "encoding", lambda e: e["mac"].pop("value")),
    ("a numeric value", "encoding", lambda e: e["mac"].update(value=7)),
    ("a value outside base64url", "encoding", lambda e: e["mac"].update(value="!" * 43)),
    ("a value in standard base64", "encoding",
     lambda e: e["mac"].update(value=e["mac"]["value"].replace("_", "/").replace("-", "+"))),
    ("a value one byte short", "encoding", lambda e: e["mac"].update(value=codes.b64url(bytes(31)))),
    ("a value one byte long", "encoding", lambda e: e["mac"].update(value=codes.b64url(bytes(33)))),
    ("an empty value", "encoding", lambda e: e["mac"].update(value="")),
):
    e = altered(SAY, fn)
    by = codes.failure(KEY, "log", PROJECT, e)
    check("an event with %s fails by %s" % (name, fails_by), by == fails_by and not codes.verifies(KEY, "log", PROJECT, e), by)

for name, fails_by, fn in (
    ("no nonce", "encoding", lambda r: r.pop("nonce")),
    ("a numeric nonce", "encoding", lambda r: r.update(nonce=5)),
    ("a nonce one byte short", "encoding", lambda r: r.update(nonce=codes.b64url(bytes(15)))),
    ("its nonce's spare bits set", "encoding", lambda r: r.update(nonce=respelled(r["nonce"]))),
    ("a code that is not a string", "encoding", lambda r: r.update(mac={"value": r["mac"]})),
    ("no code", "encoding", lambda r: r.pop("mac")),
):
    r = altered(RPC, fn)
    by = codes.failure(KEY, "rpc", PROJECT, r)
    check("an RPC with %s fails by %s" % (name, fails_by), by == fails_by and not codes.verifies(KEY, "rpc", PROJECT, r), by)
DRAFT = {k: v for k, v in SAY.items() if k != "mac"}
for name, nonce in (("15 bytes", codes.b64url(bytes(15))), ("any string", "any-string-at-all"), ("empty", "")):
    sealed = codes.seal(KEY, "log", PROJECT, DRAFT, nonce)
    check("an event sealed under a nonce that is not 16 canonical bytes (%s) fails by encoding, its code good though" % name,
          codes.failure(KEY, "log", PROJECT, sealed) == "encoding" and not codes.verifies(KEY, "log", PROJECT, sealed))
check("what is not an object is refused", codes.failure(KEY, "log", PROJECT, ["not", "an", "event"]) == "encoding")
check("encoding is checked before position: a moved hub/ event with a padded value fails by encoding",
      codes.failure(KEY, "log", PROJECT, altered(HUB, lambda e: (e.update(writer="hub/" + "0" * 32),
                                                                e["mac"].update(value=e["mac"]["value"] + "=")))) == "encoding")
check("the strict decoder never normalizes: a respelled value decodes to nothing, not to the original bytes",
      codes.b64url_bytes(respelled(SAY["mac"]["value"]), 32) is None)
check("an org key that is not canonical base64url is refused (hub.json's key)",
      codes.b64url_bytes(respelled(codes.b64url(KEY)), 32) is None and codes.b64url_bytes(codes.b64url(KEY), 32) == KEY)
check("a sealed event verifies, and its code is the vector's",
      codes.seal(KEY, "log", PROJECT, {k: v for k, v in SAY.items() if k != "mac"}, SAY["mac"]["nonce"]) == SAY)

calls = []
real_compare = codes.hmac.compare_digest
codes.hmac.compare_digest = lambda a, b: calls.append((a, b)) or real_compare(a, b)
codes.verifies(KEY, "log", PROJECT, SAY)
codes.verifies(KEY, "log", PROJECT, altered(SAY, lambda e: e.update(text="changed")))
codes.hmac.compare_digest = real_compare
check("the code is compared in constant time (hmac.compare_digest, on the 32 bytes)",
      len(calls) == 2 and all(len(a) == len(b) == 32 for a, b in calls))

# ---- a hub/ event's position (writer, seq, ts — what its code leaves out), checked by shape. The file's position
# negatives are pinned above; these are the cases generate.py at MAWS e6bb0160 (committed) asserts of
# is_hub_position without writing them to codes.json, plus one this test adds from DX1's text (the member's own form).
OTHER_MEMBER = "0123456789abcdef0123456789abcdef"
check("the hub/ vector's position holds", codes.is_hub_position(HUB))
for name, change in (
    ("the largest safe seq and a leap day", {"seq": 2 ** 53 - 1, "ts": "2024-02-29T23:59:59.999Z"}),
    ("seq 3.0, the number 3 as JSON.parse reads it", {"seq": 3.0}),
):
    check("position holds with %s" % name, codes.is_hub_position(dict(HUB, **change)))
for name, change in (
    ("an upper-case member in the writer", {"writer": HUB["writer"].upper().replace("HUB/", "hub/")}),
    ("seq 1.5", {"seq": 1.5}),
    ("seq 2^53", {"seq": 2 ** 53}),
    ("seq as a string", {"seq": "1"}),
    ("seq true", {"seq": True}),
    ("a ts with an offset", {"ts": "2026-10-15T08:00:00.000+09:00"}),
    ("a lower-case z", {"ts": "2026-10-15T08:00:00.000z"}),
    ("February 29 of a common year", {"ts": "2026-02-29T08:00:00.000Z"}),
    ("hour 24", {"ts": "2026-10-15T24:00:00.000Z"}),
    ("second 60", {"ts": "2026-12-31T23:59:60.000Z"}),
    ("a full-width digit", {"ts": "２026-10-15T08:00:00.000Z"}),
    ("month 13", {"ts": "2026-13-01T08:00:00.000Z"}),
    ("a member that is not 32 lower-case hex (DX1's text; not in generate.py)",
     {"member": "4F3A2B1C0D9E8F7A6B5C4D3E2F1A0B9C"}),
):
    e = dict(HUB, **change)
    check("position fails with %s" % name, not codes.is_hub_position(e))
    check("and the event is refused (%s)" % name, not codes.verifies(KEY, "log", PROJECT, e))
check("a hub/ event's code leaves its position out: a moved one still has a good code",
      codes.code(KEY, "log", PROJECT, dict(HUB, writer="hub/" + OTHER_MEMBER, seq=9)) == HUB["mac"]["value"])

sys.exit(1 if FAILED else 0)
