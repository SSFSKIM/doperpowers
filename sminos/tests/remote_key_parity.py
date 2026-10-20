"""Parity of sminos's remote key and remote-derived project id with
remote-key.json (written by remote-key.gen.py beside it, from the rules of
docs/doperpowers/specs/2026-10-19-smns-remote-identity-design.md §1): every
vector's URL to its key and name, and its key and org to its id, the hashed
name it states being the one the id is the UUID v5 of (the URL namespace); a
URL with no key derives no project. Prints one `ok <name>` or `FAIL <name>`
line per case, for run-sminos-tests.sh to count.

    python3 remote_key_parity.py <skills/sminos/scripts> <remote-key.json>
"""

import json
import os
import sys
import tempfile
import uuid

# sminos reads its home at import; nothing here touches it, but a run never
# points at the real one.
os.environ["SMINOS_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, sys.argv[1])
import sminos  # noqa: E402

VECTORS = json.load(open(sys.argv[2], encoding="utf-8"))
FAILED = []


def check(name, ok, detail=""):
    print(("ok " if ok else "FAIL ") + name + ("" if ok else " — %s" % detail))
    if not ok:
        FAILED.append(name)


check("the namespace is the URL namespace", VECTORS["namespace"] == str(uuid.NAMESPACE_URL), VECTORS["namespace"])
for v in VECTORS["vectors"]:
    label = "%s (%s)" % (v["url"] or '""', v["why"])
    got = (sminos.remote_key(v["url"]), sminos.remote_name(v["url"]))
    check(label, got == (v["key"], v["name"]), "got %r, want %r" % (got, (v["key"], v["name"])))
    if v["key"]:
        pid = sminos.repo_project_id(v["org"], v["key"])
        check("%s/%s → its id" % (v["org"], v["key"]), pid == v["id"] and v["hashed"] == "smns-repo:%s:%s" % (
            v["org"], v["key"]) and str(uuid.uuid5(uuid.NAMESPACE_URL, v["hashed"])) == v["id"],
            "got %s, want %s" % (pid, v["id"]))
check("the vectors cover keys and refusals", sum(1 for v in VECTORS["vectors"] if v["key"]) >= 10
      and sum(1 for v in VECTORS["vectors"] if not v["key"]) >= 5)
sys.exit(1 if FAILED else 0)
