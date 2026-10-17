#!/usr/bin/env python3
"""The jobs ledger (sminos_jobs, DC8 M1 of the desk): what jobs_parity.py does
not pin. Rows fed in batches, at any split, or one at a time, leave the ledger
with the same facts and the same body as rows fed at once (the subscription
feeds a ledger a few rows at a time after its open); a copy is independent of
the ledger it was taken from (the open builds one on a worker and hands it
over); what is not a row is passed over.

Pure: sminos_jobs opens nothing; HOME and SMINOS_HOME are made temporary anyway,
as for every run of sminos code here.
"""

import atexit
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = tempfile.mkdtemp(prefix="test-jobs-")
atexit.register(shutil.rmtree, HOME, True)
os.environ["HOME"], os.environ["SMINOS_HOME"] = HOME, os.path.join(HOME, "sminos")
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "sminos", "scripts"))
import sminos_jobs as jobs  # noqa: E402

VECTORS = json.load(open(os.path.join(HERE, "dx4-jobs.json"), encoding="utf-8"))


def fed(*batches):
    ledger = jobs.Ledger()
    for batch in batches:
        ledger.feed(batch)
    return ledger


def body(ledger, case):
    inp = case["input"]
    parents = {a: (fed(f["rows"]) if f else None) for a, f in inp["agentFiles"].items()}
    return jobs.derive(ledger, inp["metas"], bridge=(inp["bridge"] or {}).get("agents"), files={},
                       parents=parents, session_running=inp["session"]["running"])


class Incremental(unittest.TestCase):
    def test_any_split_gives_the_same_facts_and_body(self):
        for case in VECTORS["cases"] + VECTORS["outputCases"]:
            rows = case["input"]["main"]
            whole = fed(rows)
            for cut in range(len(rows) + 1):
                split = fed(rows[:cut], rows[cut:])
                self.assertEqual(vars(split), vars(whole), "%s, cut at %d" % (case["name"], cut))
            self.assertEqual(vars(fed(*[[r] for r in rows])), vars(whole), case["name"])
            if "metas" in case["input"]:
                self.assertEqual(body(fed(rows[:len(rows) // 2], rows[len(rows) // 2:]), case), body(whole, case))

    def test_a_copy_is_independent(self):
        case = next(c for c in VECTORS["cases"] if c["name"] == "background shells and monitors")
        rows = case["input"]["main"]
        half = len(rows) // 2
        ledger = fed(rows[:half])
        before = json.dumps(vars(ledger), sort_keys=True)
        copy = ledger.copy()
        copy.feed(rows[half:])
        self.assertEqual(json.dumps(vars(ledger), sort_keys=True), before)
        self.assertEqual(vars(copy), vars(fed(rows)))

    def test_what_is_not_a_row_is_passed_over(self):
        case = next(c for c in VECTORS["cases"] if c["name"] == "background shells and monitors")
        rows = case["input"]["main"]
        noise = [None, 3, "text", [], {}, {"type": "user", "message": "plain"}, {"message": {"content": [None, 7]}},
                 {"attachment": "x"}, {"attachment": {"type": "task_status"}},
                 {"attachment": {"type": "queued_command", "commandMode": "task-notification", "prompt": 5}},
                 {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_none"}]}}]
        mixed = []
        for i, row in enumerate(rows):
            mixed.append(row)
            mixed.append(noise[i % len(noise)])
        self.assertEqual(body(fed(mixed), case), body(fed(rows), case))


class Table(unittest.TestCase):
    def test_words(self):
        self.assertEqual(jobs.normalize("killed"), ("stopped", True))
        self.assertEqual(jobs.normalize("pending"), ("running", False))
        self.assertIsNone(jobs.normalize("suspended"))
        self.assertIsNone(jobs.normalize(None))


if __name__ == "__main__":
    unittest.main(verbosity=1)
