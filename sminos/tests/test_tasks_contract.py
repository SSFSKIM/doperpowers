#!/usr/bin/env python3
"""The Task Board's published set (sminos/types/tasks/) and the commands held to it (the execution document
docs/doperpowers/plans/2026-11-27-task-board-b1.md, M1: gate G1; contracts X1 to X3 and X6).

- The set: the generator (tasks-contract.gen.py --check) reproduces it byte for byte; the manifest is its files';
  every schema keeps to the sheet's keyword subset; every store, line, verdict and reader example validates.
- Every published fixture replays: the command run in-process over its `before/` home with its clock, its
  caller and its standard input prints the fixture's output, exits as it says, and leaves its `after/`.
- The readers' --json over every fixture's `after/` validates against the readers' schemas.
- The texts: each example of texts.examples.json is what the module composes from its fields, and the notice's
  published pattern reads each notice and nothing else.

Run: python3 -B sminos/tests/test_tasks_contract.py   (ends `test_tasks_contract: N passed`)
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
PLUGIN = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN, "skills", "sminos", "scripts")
SET = os.path.join(PLUGIN, "types", "tasks")
GEN = os.path.join(HERE, "tasks-contract.gen.py")
BASE = os.path.realpath(tempfile.mkdtemp(prefix="tasksc."))
for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "SMNS_INTERNAL", "DAEMON_HOME", "AGORA_HOME", "CLAUDE_CONFIG_DIR",
            "SMINOS_RL10", "MAWS_USER_DATA", "SMNS_MEMBER", "MAWS_LANE", "SMINOS_LAUNCH"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), DAEMON_HOST="testhost")
sys.path.insert(0, HERE)
sys.path.insert(0, SCRIPTS)
import sminos  # noqa: E402
import sheet_schema  # noqa: E402 — the validator of the sheet's subset, which this set keeps to
tasks = sminos.sibling_module("sminos_tasks")

CASES = sorted(os.listdir(os.path.join(SET, "fixtures")))
SCHEMAS = ("state", "act-line", "verdict", "list", "show", "waiting")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


SCHEMA = {n: load(os.path.join(SET, "schema", n + ".schema.json")) for n in SCHEMAS}


def valid(test, name, instance, where):
    errs = sheet_schema.errors(SCHEMA[name], instance)
    test.assertEqual(errs, [], "%s against %s" % (where, name))


def epoch(ts):
    return tasks.epoch(ts)


class Stdin:
    """Standard input as a command reads it: bytes, and not a terminal."""

    def __init__(self, data):
        self.buffer = io.BytesIO(data)

    def isatty(self):
        return False


def replay(home, argv, now, session=None, stdin=None):
    """One command in this process over the home `home`: (exit, stdout, stderr)."""
    env = {"SMINOS_HOME": home, "HOME": os.path.join(os.path.dirname(home), "h")}
    os.makedirs(os.path.join(env["HOME"], ".claude", "sessions"), exist_ok=True)
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, env), mock.patch.object(tasks, "clock", return_value=now), \
            mock.patch.object(sys, "stdin", Stdin((stdin or "").encode())), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        if session:
            os.environ["CLAUDE_CODE_SESSION_ID"] = session
        sminos.forget_caches()
        try:
            sminos.main(list(argv))
            code = 0
        except SystemExit as e:
            code = e.code or 0
        finally:
            sminos.forget_caches()
    return code, out.getvalue(), err.getvalue()


def home_from(side):
    """A fresh $SMINOS_HOME holding the fixture side's files (an empty one for a side that is not there)."""
    d = tempfile.mkdtemp(dir=BASE)
    home = os.path.join(d, "s")
    if os.path.isdir(side):
        shutil.copytree(side, home)
    else:
        os.makedirs(home)
    os.chmod(home, 0o700)   # as a home sminos made is: no migration speaks up during a replay
    return home


def raw(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def tree(root, sub):
    out = {}
    base = os.path.join(root, sub)
    for d, _, names in os.walk(base):
        for n in names:
            with open(os.path.join(d, n), "rb") as f:
                out[os.path.relpath(os.path.join(d, n), base)] = f.read()
    return out


class TheSet(unittest.TestCase):
    def test_the_generator_reproduces_the_set_byte_for_byte(self):
        got = subprocess.run([sys.executable, "-B", GEN, "--check"], capture_output=True, text=True)
        self.assertEqual(got.returncode, 0, got.stderr)

    def test_the_manifest_is_its_files(self):
        m = load(os.path.join(SET, "MANIFEST.json"))
        have = {}
        for d, _, names in os.walk(SET):
            for n in names:
                p = os.path.relpath(os.path.join(d, n), SET)
                if p != "MANIFEST.json":
                    with open(os.path.join(d, n), "rb") as f:
                        have[p] = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(m["files"], have)
        self.assertEqual((m["v"], m["version"]), (1, 1))
        lines = "".join("%s  %s\n" % (h, p) for p, h in sorted(have.items()))
        self.assertEqual(m["digest"], hashlib.sha256(lines.encode()).hexdigest())

    def test_every_schema_keeps_to_the_subset(self):
        allowed = sheet_schema.KEYWORDS | sheet_schema.ANNOTATIONS

        def walk(node, path):
            if isinstance(node, dict):
                for k, v in node.items():
                    if path.endswith(("properties", "$defs")):
                        walk(v, path + "." + k)
                        continue
                    self.assertIn(k, allowed, "%s.%s" % (path, k))
                    walk(v, path + "." + k)
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, "%s[%d]" % (path, i))
        for name, s in SCHEMA.items():
            walk(s, name)

    def test_every_example_validates(self):
        ex = os.path.join(SET, "examples")
        valid(self, "state", load(os.path.join(ex, "state.json")), "examples/state.json")
        for name in ("list", "show", "waiting"):
            valid(self, name, load(os.path.join(ex, name + ".json")), "examples/%s.json" % name)
        for i, line in enumerate(load(os.path.join(ex, "lines.json"))):
            valid(self, "act-line", line, "examples/lines.json[%d]" % i)
            self.assertEqual(tasks.check_line(dict(line)), line, "the door takes what the schema takes")
        for i, v in enumerate(load(os.path.join(ex, "verdicts.json"))):
            valid(self, "verdict", v, "examples/verdicts.json[%d]" % i)

    def test_the_every_value_store_holds_every_told_and_every_send(self):
        s = load(os.path.join(SET, "examples", "state.json"))
        told = {a["verdict"]["told"] for a in s["applied"].values()}
        self.assertEqual(told, {"now", "wake", "next-start", "ended", "maws"})
        sends = set()
        for t in s["tasks"].values():
            for o in t["outcomes"]:
                d = o["send"]
                sends.add("null" if d is None else "%s/%s/%s/%s" % (d["state"], d.get("how", ""),
                                                                    d.get("liveOnly", ""), d.get("why", "")))
        self.assertEqual(sends, {"null", "due///", "sent/tell/True/", "sent/notice/True/", "sent/notice/False/",
                                 "none///not-addressable", "none///no-writer", "none///log-refused"})

    def test_each_example_is_one_a_step_can_reach(self):
        """What §3's table guarantees of an outcome, and no more: a send only under `now` or `wake`, none under
        `ended` or `maws`; a notice for the live alone only for an outcome that may not wake, one that may wake only
        for one that may; an ended line only on `ended`; the seqs within the store's. A reader's target, by §2: a
        task with no thread is its asker's session's; a target reached through a /clear's pair (`via: cleared`) has
        a thread to have been followed, and the pair is in the store. Nothing is read back from a target's state
        now into what a sending was allowed to do then."""
        ex = os.path.join(SET, "examples")
        s = load(os.path.join(ex, "state.json"))
        told = {a["verdict"]["outcome"]: a["verdict"]["told"] for a in s["applied"].values()}
        for t in s["tasks"].values():
            for o in t["outcomes"]:
                with self.subTest(outcome=o["key"]):
                    send = o["send"] or {}
                    if o["send"] is not None:
                        self.assertIn(told[o["key"]], ("now", "wake"))
                    if told[o["key"]] in ("ended", "maws"):
                        self.assertIsNone(o["send"])
                    if send.get("how") == "notice":
                        self.assertEqual(o["wake"], not send["liveOnly"])
                    if o["endedLine"] is not None:
                        self.assertEqual(told[o["key"]], "ended")
                    self.assertLessEqual(o["seq"], s["seq"])
            with self.subTest(task=t["id"]):
                for f in ("born", "agentSeq", "seenSeq"):
                    self.assertLessEqual(t[f], s["seq"], f)
                self.assertLessEqual((t["closed"] or {}).get("seq", 0), s["seq"], "closed")
        waiting = load(os.path.join(ex, "waiting.json"))
        self.assertEqual(waiting["seq"], s["seq"], "the snapshot is of this store")
        pairs = s["successors"]
        rows = [t for t in load(os.path.join(ex, "list.json"))["tasks"]] + [load(os.path.join(ex, "show.json"))["task"]]
        rows += [dict(s["tasks"][w["task"]], target=w["target"]) for w in load(os.path.join(ex, "waiting.json"))["waiting"]]
        for t in rows:
            first, target = t["askers"][0], t["target"]
            with self.subTest(task=t["id"], target=target["session"]):
                if first["thread"] is None:
                    self.assertEqual((target["session"], target["thread"], target["via"]),
                                     (first["session"], None, "self"))
                if target["via"] == "cleared":
                    self.assertIsNotNone(first["thread"])
                    self.assertTrue([p for p in pairs.values() if p["session"] == target["session"] or
                                     (p["thread"] and p["thread"] == target["thread"])],
                                    "a pair in examples/state.json leads to the target")

    def test_an_id_is_one_rule_in_the_schema_and_the_door(self):
        line = load(os.path.join(SET, "examples", "lines.json"))[0]
        for task_id, ok in (("t1", True), ("t1234567890123", True), ("t0", False), ("t01", False), ("t", False),
                            ("T1", False), ("t1.1", False)):
            with self.subTest(task=task_id):
                this = dict(line, task=task_id)
                self.assertEqual(sheet_schema.errors(SCHEMA["act-line"], this) == [], ok)
                if ok:
                    self.assertEqual(tasks.check_line(dict(this)), this)
                else:
                    with self.assertRaises(tasks.Refused):
                        tasks.check_line(dict(this))
        shown = {"v": 1, "key": line["key"], "act": "shown", "task": "t1", "session": "5eed0000-0000-4000-8000-0000000000a1"}
        for k, ok in (("t1.1", True), ("t12345678901.12345678901", True), ("t1.0", False), ("t1.01", False)):
            with self.subTest(key=k):
                this = dict(shown, keys=[k])
                self.assertEqual(sheet_schema.errors(SCHEMA["act-line"], this) == [], ok)
                if ok:
                    self.assertEqual(tasks.check_line(dict(this)), this)
                else:
                    with self.assertRaises(tasks.Refused):
                        tasks.check_line(dict(this))

    def test_the_schemas_refuse_what_they_must(self):
        line = load(os.path.join(SET, "examples", "lines.json"))[0]
        for bad in (dict(line, extra=1), {k: v for k, v in line.items() if k != "wake"}, dict(line, key="K"),
                    dict(line, task="7"), dict(line, revision=0), dict(line, act="close")):
            with self.subTest(bad=bad):
                self.assertNotEqual(sheet_schema.errors(SCHEMA["act-line"], bad), [])
                with self.assertRaises(tasks.Refused) as got:
                    tasks.check_line(dict(bad))
                self.assertEqual(got.exception.code, 2)
        self.assertNotEqual(sheet_schema.errors(SCHEMA["act-line"], dict(line, act="decline", text="")), [])


class Fixtures(unittest.TestCase):
    def test_every_fixture_replays(self):
        for name in CASES:
            with self.subTest(case=name):
                d = os.path.join(SET, "fixtures", name)
                case = load(os.path.join(d, "case.json"))
                home = home_from(os.path.join(d, "before"))
                threads_before = tree(home, "threads")
                code, out, err = replay(home, case["argv"], epoch(case["now"]), case["session"], case["stdin"])
                self.assertEqual((code, out), (case["exit"], case["stdout"]), err)
                self.assertEqual(err, case["stderr"])
                want = os.path.join(d, "after", "tasks", "state.json")
                got = os.path.join(home, "tasks", "state.json")
                if os.path.exists(want):
                    self.assertEqual(json.dumps(load(got), sort_keys=True, indent=1),
                                     json.dumps(load(want), sort_keys=True, indent=1))
                else:
                    self.assertFalse(os.path.exists(got))
                self.assertEqual(tree(home, "threads"), threads_before, "no step changes a thread record")
                left = [n for n in os.listdir(os.path.join(home, "tasks"))] if os.path.isdir(
                    os.path.join(home, "tasks")) else []
                self.assertFalse([n for n in left if n.startswith(".tmp-")])

    def test_every_fixtures_store_and_verdicts_validate(self):
        for name in CASES:
            d = os.path.join(SET, "fixtures", name)
            case = load(os.path.join(d, "case.json"))
            for side in ("before", "after"):
                p = os.path.join(d, side, "tasks", "state.json")
                if os.path.exists(p):
                    valid(self, "state", load(p), "%s/%s" % (name, side))
            if case["argv"][:2] == ["task", "act"]:
                for i, s in enumerate(case["stdin"].splitlines()):
                    valid(self, "act-line", json.loads(s), "%s line %d" % (name, i))
                for i, s in enumerate(case["stdout"].splitlines()):
                    valid(self, "verdict", json.loads(s), "%s verdict %d" % (name, i))

    def test_each_rejected_line_passes_the_schema_and_the_door_refuses_it(self):
        vectors = load(os.path.join(SET, "examples", "rejected.json"))
        self.assertTrue(vectors)
        for v in vectors:
            with self.subTest(why=v["why"]):
                self.assertEqual(sheet_schema.errors(SCHEMA["act-line"], json.loads(v["line"])), [],
                                 "the schema takes it")
                home = home_from(os.path.join(SET, v["home"]))
                path = os.path.join(home, "tasks", "state.json")
                before = raw(path)
                code, out, err = replay(home, ["task", "act"], epoch("2026-11-27T16:30:00.000Z"),
                                        stdin=v["line"] + "\n")
                self.assertEqual((code, out), (2, ""), err)
                self.assertEqual(raw(path), before, "nothing applied")

    def test_every_fixtures_store_is_one_steps_reach(self):
        """Every store a fixture or the examples publish could have been written by the steps: each outcome made by
        a door line kept under its key (an outcome is made nowhere else), each shown to a session that can have
        been its target (a task with no thread has only its asker's), every seq within the store's."""
        stores = [("examples", load(os.path.join(SET, "examples", "state.json")))]
        for name in CASES:
            for side in ("before", "after"):
                p = os.path.join(SET, "fixtures", name, side, "tasks", "state.json")
                if os.path.exists(p):
                    stores.append(("%s/%s" % (name, side), load(p)))
        for where, st in stores:
            made = {a["verdict"].get("outcome") for a in st["applied"].values()
                    if a["verdict"]["verdict"] == "applied"}
            for t in st["tasks"].values():
                for o in t["outcomes"]:
                    with self.subTest(store=where, outcome=o["key"]):
                        self.assertIn(o["key"], made, "an outcome its line made, kept by its key")
                        self.assertLessEqual(o["seq"], st["seq"])
                        if o["shown"] is not None and t["askers"][0]["thread"] is None:
                            self.assertEqual(o["shown"]["session"], t["askers"][0]["session"])

    def test_the_readers_over_every_fixture_validate_and_write_nothing(self):
        for name in CASES:
            d = os.path.join(SET, "fixtures", name)
            case = load(os.path.join(d, "case.json"))
            home = home_from(os.path.join(d, "after"))
            path = os.path.join(home, "tasks", "state.json")
            before = raw(path)
            for argv, schema in ((["task", "list", "--all", "--json"], "list"),
                                 (["task", "waiting", "--json"], "waiting")):
                code, out, err = replay(home, argv, epoch(case["now"]))
                self.assertEqual(code, 0, err)
                valid(self, schema, json.loads(out), "%s %s" % (name, schema))
            state = load(path) if before is not None else {"tasks": {}}
            for tid in state["tasks"]:
                code, out, err = replay(home, ["task", "show", tid, "--json"], epoch(case["now"]))
                self.assertEqual(code, 0, err)
                valid(self, "show", json.loads(out), "%s show %s" % (name, tid))
            self.assertEqual(raw(path), before,
                             "%s: a reader writes nothing" % name)


class Texts(unittest.TestCase):
    EXAMPLES = load(os.path.join(SET, "grammar", "texts.examples.json"))

    def test_each_example_is_what_the_module_composes(self):
        for ex in self.EXAMPLES:
            with self.subTest(ex=ex["text"][:60]):
                if ex["form"] == "notice":
                    got = tasks.notice_text(ex["clause"], ex["kind"], ex["task"], ex["agent"])
                elif ex["form"] == "ended":
                    got = tasks.ended_line(ex["kind"], ex["task"])
                elif ex["form"] == "start":
                    got = tasks.start_line(ex["open"], ex["blocking"],
                                           [(o["kind"], o["task"]) for o in ex["outcomes"]], ex["more"])
                else:
                    got = tasks.FORK
                self.assertEqual(got, ex["text"])

    def test_the_published_notice_pattern_reads_each_notice_and_no_other_text(self):
        with open(os.path.join(SET, "grammar", "texts.md"), encoding="utf-8") as f:
            pattern = next(ln.strip() for ln in f if ln.strip().startswith("^\\[tasks v1\\]"))
        rx = re.compile(sheet_schema.ecma(pattern))
        for ex in self.EXAMPLES:
            self.assertEqual(bool(rx.search(ex["text"])), ex["form"] == "notice", ex["text"])
            if ex["form"] == "notice":
                self.assertIsNone(rx.search(ex["text"] + "\n"), "a trailing newline is no notice")


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    shutil.rmtree(BASE, ignore_errors=True)
    n = result.testsRun - len(result.failures) - len(result.errors)
    print("test_tasks_contract: %d passed" % n)
    sys.exit(0 if result.wasSuccessful() else 1)
