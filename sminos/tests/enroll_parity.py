"""Parity of sminos_hub's code decoder with DX7's (`decodeCode`): every case
of dx7-enroll-codes.json — one-time enrollment codes and provisioning codes
the hub's own encoders built, and damaged ones — decoded to the same tagged
fields or refused with the same message, in the hub's words, whole. The file
was written by dx7-enroll-codes.gen.mjs over MAWS commit 0602580be
(apps/desk-hub/src/protocol/identity.ts and base64url.ts). Then the hub
spellings the CLI refuses beyond the hub's decoder: a hub URL no browser's
origin serializes to (the code's hub is `location.origin`), which WHATWG's
parser would normalize and the uplink could not reach as written.
Prints one `ok <name>` or `FAIL <name>` line per case, for the suite to count.

    python3 enroll_parity.py <skills/sminos/scripts> <dx7-enroll-codes.json>
"""

import base64
import json
import sys

sys.path.insert(0, sys.argv[1])
import sminos_hub as hub  # noqa: E402

CASES = json.load(open(sys.argv[2], encoding="utf-8"))
FAILED = []


def check(name, ok, detail=""):
    print(("ok " if ok else "FAIL ") + name + ("" if ok else " — %s" % detail))
    if not ok:
        FAILED.append(name)


def verdict(text):
    try:
        return True, hub.decode_code(text)
    except hub.CodeRefused as e:
        return False, str(e)


for case in CASES:
    ok, got = verdict(case["text"])
    want = case["decoded"] if case["ok"] else case["error"]
    check(("decodes: " if case["ok"] else "refuses: ") + case["note"], (ok, got) == (case["ok"], want),
          "got %r" % (got,))

for kind, words in (("enroll", "enrollment code: "), ("provision", "provisioning code: ")):
    check("the file holds a decoded case of kind %s" % kind, any(c["ok"] and c["decoded"]["kind"] == kind for c in CASES))
    check("the file holds refused cases of kind %s" % kind,
          any(not c["ok"] and c["error"].startswith(words) for c in CASES))

for kind, prefix in (("enroll", "smns-enroll-v1."), ("provision", "smns-provision-v1.")):
    base = {k: v for k, v in next(c["decoded"] for c in CASES if c["ok"] and c["decoded"]["kind"] == kind).items()
            if k != "kind"}

    def code_of(**fields):
        body = json.dumps({**base, **fields}, separators=(",", ":"), ensure_ascii=False).encode()
        return prefix + base64.urlsafe_b64encode(body).rstrip(b"=").decode()

    for name, url in (("an IPv4 loopback in short form", "http://127.1:8747"),
                      ("an IPv6 loopback written out", "http://[0:0:0:0:0:0:0:1]:8747"),
                      ("https without its slashes", "https:desk.example.com"),
                      ("a hub with leading space", " https://desk.example.com"),
                      ("a hub with a tab inside", "https://desk.exa\tmple.com")):
        ok, why = verdict(code_of(hub=url))
        check("refuses beyond the hub's decoder (%s): %s" % (kind, name), not ok and "hub" in why, why)

for name in ("SK-2.local", "a", "Mac_mini-2.lan", "x" * 63, "hubs", "legacy2"):
    check("an admitted name: %s" % name, hub.is_machine_name(name))
for name in ("hub", "Hub", "LEGACY", "", "-a", "a b", "a\n", "x" * 64, "ü", None):
    check("not an admitted name: %r" % (name,), not hub.is_machine_name(name))

sys.exit(1 if FAILED else 0)
