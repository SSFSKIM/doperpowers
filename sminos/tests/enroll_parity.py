"""Parity of sminos_hub's enrollment-code decoder with DX7's
(`decodeEnrollmentCode`): every case of dx7-enroll-codes.json — codes the
hub's own `encodeEnrollmentCode` built, and damaged ones — decoded to the same
fields or refused for the same reason, in the hub's words. The file was
written by dx7-enroll-codes.gen.mjs over MAWS commit bd266073
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
        return False, "enrollment code: %s" % e


for case in CASES:
    ok, got = verdict(case["text"])
    want = case["decoded"] if case["ok"] else case["error"]
    check(("decodes: " if case["ok"] else "refuses: ") + case["note"], (ok, got) == (case["ok"], want),
          "got %r" % (got,))

check("the file holds both kinds", any(c["ok"] for c in CASES) and any(not c["ok"] for c in CASES))

BASE = next(c["decoded"] for c in CASES if c["ok"])


def code_of(**fields):
    body = json.dumps({**BASE, **fields}, separators=(",", ":"), ensure_ascii=False).encode()
    return hub.CODE_PREFIX + base64.urlsafe_b64encode(body).rstrip(b"=").decode()


for name, url in (("an IPv4 loopback in short form", "http://127.1:8747"),
                  ("an IPv6 loopback written out", "http://[0:0:0:0:0:0:0:1]:8747"),
                  ("https without its slashes", "https:desk.example.com"),
                  ("a hub with leading space", " https://desk.example.com"),
                  ("a hub with a tab inside", "https://desk.exa\tmple.com")):
    ok, why = verdict(code_of(hub=url))
    check("refuses beyond the hub's decoder: %s" % name, not ok and "hub" in why, why)

for name in ("SK-2.local", "a", "Mac_mini-2.lan", "x" * 63, "hubs", "legacy2"):
    check("an admitted name: %s" % name, hub.is_machine_name(name))
for name in ("hub", "Hub", "LEGACY", "", "-a", "a b", "a\n", "x" * 64, "ü", None):
    check("not an admitted name: %r" % (name,), not hub.is_machine_name(name))

sys.exit(1 if FAILED else 0)
