"""Parity of sminos.machine_project_id with the hub's machine project id (the
org directory's M2): every vector of machine-project-id.json, copied verbatim
from MAWS commit 3165ebafb (apps/desk-hub/src/protocol/vectors/
machine-project.json, written by generate-machine-project.py beside it),
reproduced from its org and machine name, and the hashed name it states
being the one the id is the UUID v5 of (the URL namespace).
Prints one `ok <name>` or `FAIL <name>` line per case, for
run-sminos-tests.sh to count.

    python3 machine_project_parity.py <skills/sminos/scripts> <machine-project-id.json>
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
    got = sminos.machine_project_id(v["org"], v["machine"])
    check("%s/%s (%s)" % (v["org"], v["machine"], v["why"]), got == v["id"] and
          str(uuid.uuid5(uuid.NAMESPACE_URL, v["name"])) == v["id"], "got %s, want %s" % (got, v["id"]))
check("the vectors are not empty", len(VECTORS["vectors"]) >= 3)
sys.exit(1 if FAILED else 0)
