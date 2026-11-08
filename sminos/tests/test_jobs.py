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
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = tempfile.mkdtemp(prefix="test-jobs-")
atexit.register(shutil.rmtree, HOME, True)
os.environ["HOME"], os.environ["SMINOS_HOME"] = HOME, os.path.join(HOME, "sminos")
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills", "sminos", "scripts"))
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


class Containment(unittest.TestCase):
    """The pathname checked is not the file opened: a directory above the output file swapped for a link between
    the check and the open must not lead the read outside every root (O_NOFOLLOW guards only the last component)."""

    def test_a_parent_swapped_for_a_link_before_the_open_is_refused(self):
        base = os.path.realpath(tempfile.mkdtemp(dir=HOME))
        session, task = "d0c8a000-0000-4000-8000-0000000000aa", "bswap0001"
        root = os.path.join(base, "claude-501", "-proj", session, "tasks")
        outside = os.path.join(base, "elsewhere")
        named = os.path.join(root, task + ".output")
        for directory, text in ((root, "ours\n"), (outside, "not ours\n")):
            os.makedirs(directory)
            with open(os.path.join(directory, task + ".output"), "w") as f:
                f.write(text)
        ledger = fed([
            {"type": "assistant", "uuid": "u1", "timestamp": "2026-10-17T09:00:01.000Z", "message": {"content": [
                {"type": "tool_use", "id": "toolu_swap", "name": "Bash",
                 "input": {"command": "make", "description": "Make", "run_in_background": True}}]}},
            {"type": "user", "uuid": "u2", "timestamp": "2026-10-17T09:00:02.000Z", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "toolu_swap", "is_error": False,
                 "content": "Command running in background with ID: %s. Output is being written to: %s." % (task, named)}]},
             "toolUseResult": {"backgroundTaskId": task}},
        ])
        request = {"taskId": task, "tail": 100}
        self.assertEqual(jobs.output_answer(request, ledger, session, [root])["text"], "ours\n")
        real_open = os.open

        def swap_then_open(path, flags, *rest):
            if path == named:  # the checks have passed: put a link to elsewhere in the tasks directory's place
                os.rename(root, root + ".moved")
                os.symlink(outside, root)
            return real_open(path, flags, *rest)

        with mock.patch.object(jobs.os, "open", side_effect=swap_then_open):
            got = jobs.output_answer(request, ledger, session, [root])
        self.assertEqual(got["result"], "refused", got)
        self.assertEqual(got["path"], named)
        self.assertNotIn("text", got)


class TaskIndex(unittest.TestCase):
    """A task's rows (`task_rows`, what the subagents' outcomes read): only
    the rows that name a task and the calls they name, never the engine's
    request records, and the status the whole loop gives it; a subagent's
    task stopped through the bridge is recorded in the main loop's rows."""

    def write(self, path, rows, requests=True):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
                if requests:
                    # A request record repeats the conversation so far, task ids and all, and is no row.
                    # Written compact, as the engine writes it (REQUEST_RECORD is its prefix).
                    f.write(json.dumps({"type": "api-request", "sessionId": "s", "uuid": "not-a-row",
                                        "body": {"messages": [row]}}, separators=(",", ":")) + "\n")
        return path

    def test_every_vector_job_has_the_status_the_whole_loop_gives_it(self):
        n = 0
        for i, case in enumerate(VECTORS["cases"]):
            if not case["input"]["session"]["running"]:
                continue
            main = self.write(os.path.join(HOME, "idx", "c%d.jsonl" % i), case["input"]["main"])
            for job in case["expect"]["jobs"]:
                n += 1
                ledger = fed(jobs.task_rows(main, job["taskId"]))
                got = [j for j in ledger.jobs_body(True) if j["taskId"] == job["taskId"]]
                self.assertEqual(got, [job], "%s: %s" % (case["name"], job["taskId"]))
        self.assertGreater(n, 10)

    def test_a_subagents_task_stopped_through_the_bridge_is_recorded_in_the_main_loop(self):
        main = os.path.join(HOME, "idx", "sess.jsonl")
        agent = os.path.join(HOME, "idx", "sess", "subagents", "agent-a1.jsonl")
        call = {"type": "assistant", "uuid": "u1", "timestamp": "2026-10-18T00:00:01Z", "message": {"content": [
            {"type": "tool_use", "id": "toolu_M", "name": "Monitor", "input": {"command": "tail -F x", "description": "x"}}]}}
        started = {"type": "user", "uuid": "u2", "timestamp": "2026-10-18T00:00:02Z",
                   "toolUseResult": {"taskId": "mon01", "timeoutMs": 1, "persistent": False},
                   "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_M", "content": "started"}]}}
        note = {"type": "user", "uuid": "u3", "timestamp": "2026-10-18T00:00:03Z", "isMeta": True,
                "origin": {"kind": "plugin", "name": "doperpowers"}, "message": {"content": [
                    {"type": "text", "text": "Task mon01, a background task, was stopped from the desk: it is not running."}]}}
        self.write(agent, [call, started])
        self.write(main, [{"type": "user", "uuid": "u0", "timestamp": "2026-10-18T00:00:00Z",
                           "message": {"content": "go"}}])
        self.assertEqual(jobs.task_rows(main, "mon01"), [], "the main loop names no task yet")
        self.assertEqual(jobs.task_rows(agent, "mon02"), [], "a task nobody started")
        self.assertEqual(fed(jobs.task_rows(agent, "a1")).jobs_body(True), [], "an agent is no job")
        self.write(main, [note])
        self.assertEqual([r["uuid"] for r in jobs.task_rows(main, "mon01")], ["u3"], "stopped: the main loop's record")
        own = fed(jobs.task_rows(agent, "mon01"))
        self.assertEqual(own.jobs_body(True)[0]["status"], "running", "the subagent's own rows alone")
        stopped = own.jobs_body(True, fed([note]))[0]
        self.assertEqual((stopped["status"], stopped["endedAt"]), ("stopped", "2026-10-18T00:00:03Z"))

    def test_a_short_id_reads_only_the_rows_that_name_it(self):
        # Ids are matched as references, not as bytes: `a` is in every row here, and names no task.
        rows = []
        for i in range(200):
            tid, task = "toolu_a%03d" % i, "ba%05d" % i
            rows.append({"type": "assistant", "uuid": "c%d" % i, "timestamp": "2026-10-18T00:00:00Z",
                         "message": {"content": [{"type": "tool_use", "id": tid, "name": "Bash", "input": {
                             "command": "sleep a", "description": "a task", "run_in_background": True}}]}})
            rows.append({"type": "user", "uuid": "r%d" % i, "timestamp": "2026-10-18T00:00:01Z",
                         "toolUseResult": {"backgroundTaskId": task, "stdout": "", "stderr": ""},
                         "message": {"content": [{"type": "tool_result", "tool_use_id": tid,
                                                  "content": "Command running in background with ID: %s." % task}]}})
        rows.append({"type": "attachment", "uuid": "n7", "timestamp": "2026-10-18T00:00:02Z", "attachment": {
            "type": "queued_command", "commandMode": "task-notification",
            "prompt": "<task-notification>\n<task-id>ba00007</task-id>\n<tool-use-id>toolu_a007</tool-use-id>\n"
                      "<status>completed</status>\n</task-notification>"}})
        main = self.write(os.path.join(HOME, "idx", "short.jsonl"), rows)
        for short in ("a", "b", "0", "toolu"):
            self.assertEqual(jobs.task_rows(main, short), [], short)
        self.assertEqual([r["uuid"] for r in jobs.task_rows(main, "ba00003")], ["c3", "r3"])
        self.assertEqual([r["uuid"] for r in jobs.task_rows(main, "ba00007")], ["c7", "r7", "n7"])

    def test_a_row_of_several_notifications_ends_each_task(self):
        # A 2.1.318 subagent's row, cut down: the engine joined two notifications it delivered at once into one row
        # (its preamble, then each block after a blank line; joinedNoticeLengths the blocks' lengths). Only the
        # first task used to end, so the agent read as waiting on background for good.
        rows, tasks = [], {"budz9680h": "toolu_01J1", "b7nq313fl": "toolu_01J2"}
        for n, (task, tid) in enumerate(tasks.items()):
            rows.append({"type": "assistant", "uuid": "c%d" % n, "timestamp": "2026-11-07T06:1%d:00.000Z" % n,
                         "message": {"content": [{"type": "tool_use", "id": tid, "name": "Bash", "input": {
                             "command": "sleep 900", "description": "Wait for run %d" % n}}]}})
            rows.append({"type": "user", "uuid": "r%d" % n, "timestamp": "2026-11-07T06:2%d:00.000Z" % n,
                         "toolUseResult": {"stdout": "", "backgroundTaskId": task, "timedOutAfterMs": 600000},
                         "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "is_error": False,
                                                  "content": "Command did not complete within its 600s timeout and "
                                                             "was moved to the background (ID: %s)." % task}]}})
        blocks = ["<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>%s</tool-use-id>\n<status>failed</status>"
                  "\n<summary>Background command \"%s\" failed with exit code 144</summary>\n</task-notification>"
                  % (task, tid, task) for task, tid in reversed(tasks.items())]
        rows.append({"type": "user", "uuid": "j1", "timestamp": "2026-11-08T01:45:43.491Z", "isMeta": True,
                     "origin": {"kind": "task-notification", "producer": "session-task"},
                     "message": {"role": "user", "content": "[SYSTEM NOTIFICATION - NOT USER INPUT]\nThis is an "
                                 "automated background-task event.\n\n" + "\n\n".join(blocks)},
                     "joinedNoticeLengths": [len(b) for b in blocks], "joinedNoticeOwn": [True, True],
                     "joinedNoticeRunIds": ["0mw60n8tf-ed6c2aa4", "0mw60a9vs-28a81efc"]})
        path = self.write(os.path.join(HOME, "idx", "joined", "subagents", "agent-a5661.jsonl"), rows)
        for task in tasks:
            [job] = fed(jobs.task_rows(path, task)).jobs_body(True)
            self.assertEqual((job["taskId"], job["status"], job.get("endedAt"), job.get("summary")),
                             (task, "failed", "2026-11-08T01:45:43.491Z",
                              'Background command "%s" failed with exit code 144' % task))

    def test_a_subagents_tasks_end_on_the_notices_queued_in_the_main_loop(self):
        # 2.1.319: a monitor's stream ended as its agent handed back; the engine enqueued the notice for the agent in
        # the main loop's transcript and never handed it over. The agent's own rows leave its tasks running.
        agent = os.path.join(HOME, "idx", "queued", "subagents", "agent-a1cff.jsonl")
        main = os.path.join(HOME, "idx", "queued.jsonl")
        rows, kinds = [], {"bmon1": "Monitor", "bmon2": "Monitor", "bsh3": "Bash"}
        for n, (task, name) in enumerate(kinds.items()):
            tid = "toolu_q%d" % n
            rows.append({"type": "assistant", "uuid": "c%d" % n, "timestamp": "2026-11-08T01:29:4%d.000Z" % n,
                         "message": {"content": [{"type": "tool_use", "id": tid, "name": name,
                                                  "input": {"command": "watch %d" % n, "description": "w%d" % n}}]}})
            tur = {"taskId": task, "timeoutMs": 1800000} if name == "Monitor" else {"backgroundTaskId": task}
            rows.append({"type": "user", "uuid": "r%d" % n, "timestamp": "2026-11-08T01:29:5%d.000Z" % n,
                         "toolUseResult": tur,
                         "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": "started"}]}})
        self.write(agent, rows)
        notice = "<task-notification>\n<task-id>%s</task-id>\n%s</task-notification>"
        queued = [{"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-11-08T01:44:06.648Z",
                   "sessionId": "s", "content": notice % ("bmon1", "<status>completed</status>\n")},
                  {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-11-08T02:00:00.000Z",
                   "sessionId": "s", "content": notice % ("bmon2", "<event>[Monitor expired after 30m]</event>\n")},
                  {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-11-08T02:00:01.000Z",
                   "sessionId": "s", "content": notice % ("bsh3", "<event>[Monitor expired after 30m]</event>\n")}]
        self.write(main, [{"type": "user", "uuid": "u0", "timestamp": "2026-11-08T01:00:00Z",
                           "message": {"content": "go"}}] + queued)
        statuses = {}
        for task in kinds:
            own = fed(jobs.task_rows(agent, task))
            also = fed(jobs.task_rows(main, task))
            self.assertEqual(own.jobs_body(True)[0]["status"], "running", "%s: the agent's own rows alone" % task)
            statuses[task] = own.jobs_body(True, also)[0]["status"]
        self.assertEqual(statuses, {"bmon1": "completed", "bmon2": "completed", "bsh3": "running"},
                         "the queued end counts, an expiry for the subagent's monitor, not for its shell")

    def test_a_missing_or_empty_transcript_holds_no_task(self):
        self.assertEqual(jobs.task_rows(os.path.join(HOME, "nowhere.jsonl"), "b1"), [])
        empty = self.write(os.path.join(HOME, "idx", "empty.jsonl"), [])
        self.assertEqual(jobs.task_rows(empty, "b1"), [])


class Table(unittest.TestCase):
    def test_words(self):
        self.assertEqual(jobs.normalize("killed"), ("stopped", True))
        self.assertEqual(jobs.normalize("pending"), ("running", False))
        self.assertIsNone(jobs.normalize("suspended"))
        self.assertIsNone(jobs.normalize(None))


if __name__ == "__main__":
    unittest.main(verbosity=1)
