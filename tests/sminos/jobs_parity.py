"""Parity of sminos_jobs with DX4's shared vectors (dx4-jobs.json, written by
dx4-jobs.gen.py and vendored by DC9's fake machine): the normalization table,
every case's widened `subagents` body ({subagents, jobs, mcp}) from its rows,
metas, agent files and bridge state, and every `output` case answered over a
file layout made under a temporary directory.
Prints one `ok <name>` or `FAIL <name>` line per check, for
run-sminos-tests.sh to count.

    python3 jobs_parity.py <skills/sminos/scripts> <dx4-jobs.json>
"""

import atexit
import json
import os
import shutil
import sys
import tempfile

# sminos_jobs opens nothing of its own; HOME and SMINOS_HOME are temporary anyway, as for every run of sminos code.
HOME = tempfile.mkdtemp(prefix="jobs-parity-")
atexit.register(shutil.rmtree, HOME, True)
os.environ["HOME"], os.environ["SMINOS_HOME"] = HOME, os.path.join(HOME, "sminos")
sys.path.insert(0, sys.argv[1])
import sminos_jobs as jobs  # noqa: E402

VECTORS = json.load(open(sys.argv[2], encoding="utf-8"))
FAILED = []


def check(name, ok, detail=""):
    print(("ok " if ok else "FAIL ") + name + ("" if ok else " — %s" % detail))
    if not ok:
        FAILED.append(name)


def ledger_of(rows):
    ledger = jobs.Ledger()
    ledger.feed(rows)
    return ledger


def diff(want, got):
    return "\n    expected: %s\n    actual:   %s" % (json.dumps(want, sort_keys=True), json.dumps(got, sort_keys=True))


# ---- the table
table = [{"raw": raw, "status": status, "terminal": terminal} for raw, (status, terminal) in jobs.TABLE.items()]
check("the normalization table is DX4's", table == VECTORS["table"], diff(VECTORS["table"], table))

# ---- the body
for case in VECTORS["cases"]:
    inp = case["input"]
    agent_files = inp["agentFiles"]
    parents, files = {}, {}
    for agent_id, f in agent_files.items():
        parents[agent_id] = ledger_of(f["rows"]) if f is not None else None
        if f is not None:
            files[agent_id] = jobs.file_facts(f["rows"], f["size"], f["mtimeMs"])
    bridge = inp["bridge"]["agents"] if inp["bridge"] is not None else None
    got = jobs.derive(ledger_of(inp["main"]), inp["metas"], bridge=bridge, files=files, parents=parents,
                      session_running=inp["session"]["running"])
    for part in ("subagents", "jobs", "mcp"):
        check("%s: %s" % (case["name"], part), got.get(part) == case["expect"][part],
              diff(case["expect"][part], got.get(part)))


# ---- output
def materialize(value, root):
    return json.loads(json.dumps(value).replace("<ROOT>", root))


for case in VECTORS["outputCases"]:
    tmp = tempfile.mkdtemp(prefix="dx4-output-")
    try:
        root = os.path.realpath(tmp)
        c = materialize(case, root)
        inp = c["input"]
        for item in inp["layout"]:
            path = item["path"]
            os.makedirs(path if item.get("dir") else os.path.dirname(path), exist_ok=True)
            if "file" in item:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(item["file"])
            elif "symlink" in item:
                os.symlink(item["symlink"], path)
        got = jobs.output_answer(inp["request"], ledger_of(inp["main"]), inp["session"], inp["roots"])
        want = c["expect"]
        if want.get("result") == "refused":
            reason = got.pop("reason", None) if isinstance(got, dict) else None
            check("output %s: reason is a sentence" % case["name"], isinstance(reason, str) and reason.strip() != "",
                  repr(reason))
        check("output %s" % case["name"], got == want, diff(want, got))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

sys.exit(1 if FAILED else 0)
