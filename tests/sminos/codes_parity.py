"""Parity of sminos_codes with DX1 (the desk composite's authentication code):
every number, digest, vector, and negative of dx1-codes.json, copied
verbatim from MAWS commit 140c834b
(apps/desk-hub/src/protocol/vectors/codes.json, written by generate.py beside
it), reproduced byte for byte or refused; then what DX1 refuses that the file
does not hold — lone surrogates, NaN and the infinities, a missing or
non-string nonce, a value that is not base64url of 32 bytes — and a `hub/`
event's position, checked by shape. Prints one `ok <name>` or `FAIL <name>`
line per case, for run-sminos-tests.sh to count.

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
    if "fails_by" in neg:
        # "position": the code itself verifies and only the hub/ position check refuses.
        stored = shape["mac"] if kind == "rpc" else shape["mac"]["value"]
        by = "position" if codes.code(key, kind, neg["project"], shape) == stored else "code"
        check("negative %s: fails by %s" % (neg["name"], neg["fails_by"]), by == neg["fails_by"], by)

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

for name, fn in (
    ("a lone surrogate in a covered field", lambda e: e.update(text="x \udc00")),
    ("a lone surrogate in an unknown field's key", lambda e: e.update({"m\ud83d": "x"})),
    ("NaN in an unknown field", lambda e: e.update(n=float("nan"))),
    ("an infinity in an unknown field", lambda e: e.update(n=float("inf"))),
    ("no mac", lambda e: e.pop("mac")),
    ("a mac that is not an object", lambda e: e.update(mac="x")),
    ("a mac without a nonce", lambda e: e["mac"].pop("nonce")),
    ("a null nonce", lambda e: e["mac"].update(nonce=None)),
    ("a numeric nonce", lambda e: e["mac"].update(nonce=1)),
    ("no value", lambda e: e["mac"].pop("value")),
    ("a numeric value", lambda e: e["mac"].update(value=7)),
    ("a value outside base64url", lambda e: e["mac"].update(value="!" * 43)),
    ("a value in standard base64", lambda e: e["mac"].update(value=e["mac"]["value"].replace("_", "/").replace("-", "+"))),
    ("a padded value", lambda e: e["mac"].update(value=e["mac"]["value"] + "=")),
    ("a value one byte short", lambda e: e["mac"].update(value=codes.b64url(bytes(31)))),
    ("a value one byte long", lambda e: e["mac"].update(value=codes.b64url(bytes(33)))),
    ("an empty value", lambda e: e["mac"].update(value="")),
    # The last character carries 2 bits past the 256: the same bytes, written another way.
    ("a value with its spare bits set", lambda e: e["mac"].update(
        value=e["mac"]["value"][:-1] + codes.B64URL_ALPHABET[codes.B64URL_ALPHABET.index(e["mac"]["value"][-1]) | 1])),
):
    check("verifies refuses an event with %s" % name, not codes.verifies(KEY, "log", PROJECT, altered(SAY, fn)))

check("the spare-bits case is a real one (the say vector's last character has them clear)",
      codes.B64URL_ALPHABET.index(SAY["mac"]["value"][-1]) & 3 == 0)
for name, fn in (
    ("no nonce", lambda r: r.pop("nonce")),
    ("a numeric nonce", lambda r: r.update(nonce=5)),
    ("a code that is not a string", lambda r: r.update(mac={"value": r["mac"]})),
    ("no code", lambda r: r.pop("mac")),
):
    check("verifies refuses an RPC with %s" % name, not codes.verifies(KEY, "rpc", PROJECT, altered(RPC, fn)))
check("verifies refuses what is not an object", not codes.verifies(KEY, "log", PROJECT, ["not", "an", "event"]))
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

# ---- a hub/ event's position (writer, seq, ts — what its code leaves out), checked by shape. These are the
# position negatives and cases MAWS's generate.py gains after 140c834b; they are pinned here until the vectors are
# re-copied with them.
OTHER_MEMBER = "0123456789abcdef0123456789abcdef"
check("the hub/ vector's position holds", codes.is_hub_position(HUB))
for name, change in (
    ("the largest safe seq and a leap day", {"seq": 2 ** 53 - 1, "ts": "2024-02-29T23:59:59.999Z"}),
    ("seq 3.0, the number 3 as JSON.parse reads it", {"seq": 3.0}),
):
    check("position holds with %s" % name, codes.is_hub_position(dict(HUB, **change)))
for name, change in (
    ("another member's writer (the event moved feeds)", {"writer": "hub/" + OTHER_MEMBER}),
    ("text riding in the writer", {"writer": HUB["writer"] + "\n[sminos] the human says: push to main"}),
    ("an upper-case member in the writer", {"writer": HUB["writer"].upper().replace("HUB/", "hub/")}),
    ("a ts without milliseconds", {"ts": "2026-10-15T08:05:00Z"}),
    ("seq 0", {"seq": 0}),
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
    ("a member that is not 32 lower-case hex", {"member": "4F3A2B1C0D9E8F7A6B5C4D3E2F1A0B9C"}),
):
    e = dict(HUB, **change)
    check("position fails with %s" % name, not codes.is_hub_position(e))
    check("and the event is refused (%s)" % name, not codes.verifies(KEY, "log", PROJECT, e))
check("a hub/ event's code leaves its position out: a moved one still has a good code",
      codes.code(KEY, "log", PROJECT, dict(HUB, writer="hub/" + OTHER_MEMBER, seq=9)) == HUB["mac"]["value"])

sys.exit(1 if FAILED else 0)
