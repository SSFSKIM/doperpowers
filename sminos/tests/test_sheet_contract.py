#!/usr/bin/env python3
"""The question sheet's published set (sminos/types/sheet/) and the two verbs that read and append to a record
(plan docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, M1's Proves).

- The set: the generator (sheet-contract.gen.py) reproduces it byte for byte; the manifest is its files'; every
  file validates against its schema (sheet_schema.py), the schemas held to the keywords I1 names; the
  imported-legacy record is valid where the tool's input refuses its question and its label.
- The reader: `show --json` over every fixture's before and after is the fixture's.
- The envelopes: keys as many as answered and dismissed together, in that order; the block names the ids the
  prose names; the two limits; no text past 500 in the block and picks that are places; only outcomes pending
  for the recipient; `more` exactly where more is pending; `long` and `more` sized as I7's table says; every
  texts/ file named by its hash.
- The result's grammar: each stored call's first line matches the published pattern and parses to `parsed`.
- The door: a call appended whole (at filled, one batch on several), `queued`; each refusal exits 2 with nothing
  appended; no record exits 3; a held lock exits 75; eight processes of twenty-five calls each leave every call's
  lines whole and together; a file without its last newline gets one first; a stand-in bridge's verdicts are
  printed, and a bridge that does not know the op reads queued. `--session` runs before the migration.

Run: python3 -B sminos/tests/test_sheet_contract.py   (ends `test_sheet_contract: N passed`)
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
PLUGIN = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN, "skills", "sminos", "scripts")
CLI = os.path.join(SCRIPTS, "sminos")
SET = os.path.join(PLUGIN, "types", "sheet")
GEN = os.path.join(HERE, "sheet-contract.gen.py")
# Under /tmp: a bridge's socket, $SMINOS_HOME/bridge/<session>.sock, must fit a Unix socket's path.
BASE = tempfile.mkdtemp(prefix="sheetc.", dir="/tmp")
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"))
os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
sys.path.insert(0, HERE)
sys.path.insert(0, SCRIPTS)
import sminos  # noqa: E402
import sheet_schema  # noqa: E402
import bridge_standin  # noqa: E402
sheet = sminos.sibling_module("sminos_sheet")

ALLOWED = sheet_schema.KEYWORDS | sheet_schema.ANNOTATIONS
CASES = sorted(os.listdir(os.path.join(SET, "fixtures")))
EXAMPLES = sorted(d for d in os.listdir(os.path.join(SET, "examples")) if os.path.isdir(os.path.join(SET, "examples", d)))
EXAMPLES.append("split/then")       # the second envelope of split's Send
BUDGET, KEYS_MAX, TEXT_MAX = 60000, 200, 500


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


SCHEMA = {n: load(os.path.join(SET, "schema", n + ".schema.json")) for n in
          ("state", "inbox-line", "show", "delivery", "surface", "tool-input")}


def files(root):
    out = {}
    for d, _, names in os.walk(root):
        for n in names:
            p = os.path.join(d, n)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = f.read()
    return out


def write(path, data, mode="w"):
    with open(path, mode) as f:
        f.write(data)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def raw_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def units(s):
    return len(s.encode("utf-16-le")) // 2


def home(case, side):
    """A scratch $SMINOS_HOME holding a fixture's `before` or `after`, set as the process's."""
    h = tempfile.mkdtemp(prefix="h.", dir=BASE)
    src = os.path.join(SET, "fixtures", case, side)
    if os.path.isdir(src):
        shutil.copytree(src, h, dirs_exist_ok=True)
    os.environ["SMINOS_HOME"] = h
    return h


def run(args, stdin=b"", env=None):
    p = subprocess.run([CLI] + args, input=stdin, capture_output=True,
                       env=dict(os.environ, **(env or {})), timeout=120)
    return p.returncode, p.stdout.decode(), p.stderr.decode()


class TheSet(unittest.TestCase):
    def test_the_generator_reproduces_the_set(self):
        out = os.path.join(BASE, "gen")
        p = subprocess.run([sys.executable, "-B", GEN, "--out", out], capture_output=True, text=True, check=True)
        self.assertRegex(p.stdout, r"^sheet-contract: 21 cases, 6 examples, digest [0-9a-f]{64}\n$")
        made, have = files(out), files(SET)
        self.assertEqual(sorted(made), sorted(have), "the same files")
        self.assertEqual([p for p in made if made[p] != have[p]], [], "byte for byte")
        self.assertEqual(subprocess.run([sys.executable, "-B", GEN, "--check"], capture_output=True).returncode, 0)

    def test_the_manifest_is_the_files(self):
        m = load(os.path.join(SET, "MANIFEST.json"))
        self.assertEqual((m["v"], m["version"]), (1, 1))
        have = {p: hashlib.sha256(d).hexdigest() for p, d in files(SET).items() if p != "MANIFEST.json"}
        self.assertEqual(m["files"], have)
        lines = "".join("%s  %s\n" % (h, p) for p, h in sorted(have.items()))
        self.assertEqual(m["digest"], hashlib.sha256(lines.encode()).hexdigest())

    def test_the_schemas_use_only_the_named_keywords(self):
        def walk(node, where):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in ("properties", "$defs"):
                        for name, sub in v.items():
                            walk(sub, "%s.%s.%s" % (where, k, name))
                        continue
                    self.assertIn(k, ALLOWED, where)
                    if k in ("items", "additionalProperties") and isinstance(v, dict):
                        walk(v, where + "." + k)
                    if k == "oneOf":
                        for i, sub in enumerate(v):
                            walk(sub, "%s.oneOf[%d]" % (where, i))
                    if k == "$ref":
                        self.assertTrue(v.startswith("#/$defs/") and v[8:] in SCHEMA[where.split(".")[0]]["$defs"],
                                        (where, v))
        for name, s in SCHEMA.items():
            walk(s, name)

    def test_every_file_validates(self):
        bad_lines = []
        for path in glob.glob(os.path.join(SET, "**", "*"), recursive=True):
            rel = os.path.relpath(path, SET)
            if rel.endswith("state.json"):
                self.assertEqual(sheet_schema.errors(SCHEMA["state"], load(path)), [], rel)
            elif rel.endswith("inbox.jsonl"):
                data = raw_bytes(path)
                whole = data[:data.rfind(b"\n") + 1].splitlines()
                for n, raw in enumerate(whole, 1):
                    try:
                        errs = sheet_schema.errors(SCHEMA["inbox-line"], json.loads(raw))
                    except ValueError:
                        errs = ["not JSON"]
                    if errs:
                        bad_lines.append((rel.split("/")[1], n))
                if not data.endswith(b"\n") and data:      # an unfinished write: a whole object, its newline lost
                    tail = data[data.rfind(b"\n") + 1:]
                    self.assertEqual(sheet_schema.errors(SCHEMA["inbox-line"], json.loads(tail)), [], rel)
            elif re.search(r"show\.(before|after)\.json$", rel):
                m = load(path)
                if m is not None:
                    self.assertEqual(sheet_schema.errors(SCHEMA["show"], m), [], rel)
        # Three of skipped-and-unknown's four U2 lines, in its before and its after, are the only lines the schema
        # refuses; the fourth is well formed and picks no label of its question, which only the record can tell.
        self.assertEqual(sorted(bad_lines), sorted([("skipped-and-unknown", n) for n in (1, 2, 3)] * 2))
        self.assertEqual(sheet_schema.errors(SCHEMA["surface"], load(os.path.join(SET, "examples", "surface.json"))),
                         [])
        for name in EXAMPLES:
            self.assertEqual(sheet_schema.errors(SCHEMA["delivery"], block(envelope(name))), [], name)
        for c in load(os.path.join(SET, "grammar", "result.examples.json")):
            self.assertEqual(sheet_schema.errors(SCHEMA["tool-input"], c["input"]), [], c["result"])

    def test_every_png_decodes(self):
        import struct
        import zlib
        found = [p for p in glob.glob(os.path.join(SET, "**", "*"), recursive=True)
                 if os.path.isfile(p) and raw_bytes(p).startswith(b"\x89PNG\r\n\x1a\n")]
        self.assertGreaterEqual(len(found), 3)
        for p in found:
            data, at, idat = raw_bytes(p), 8, b""
            while at < len(data):
                n, = struct.unpack(">I", data[at:at + 4])
                kind, body = data[at + 4:at + 8], data[at + 8:at + 8 + n]
                self.assertEqual(struct.unpack(">I", data[at + 8 + n:at + 12 + n])[0], zlib.crc32(kind + body), p)
                idat += body if kind == b"IDAT" else b""
                at += 12 + n
            self.assertEqual(zlib.decompress(idat), b"\x00\xff\xff\xff\xff", "one white pixel")

    def test_the_schemas_refuse_what_their_shapes_forbid(self):
        rec = load(glob.glob(os.path.join(SET, "fixtures", "references", "before", "sheet", "*", "state.json"))[0])
        text, image = rec["questions"][0]["references"][0], rec["questions"][0]["references"][2]
        ref = {"$ref": "#/$defs/reference", "$defs": SCHEMA["state"]["$defs"]}
        self.assertEqual(sheet_schema.errors(ref, text), [])
        self.assertNotEqual(sheet_schema.errors(ref, {k: v for k, v in text.items() if k != "totalLines"}), [])
        self.assertNotEqual(sheet_schema.errors(ref, {k: v for k, v in image.items() if k != "mediaType"}), [])
        verdict = {"$ref": "#/$defs/verdict", "$defs": SCHEMA["state"]["$defs"]}
        unseen = {"verdict": "retracted", "kind": "unseen", "at": "2026-11-23T10:00:00.000Z", "by": "page-0901r001"}
        self.assertEqual(sheet_schema.errors(verdict, unseen), [])
        self.assertNotEqual(sheet_schema.errors(verdict, {k: v for k, v in unseen.items() if k != "by"}), [])
        # A line range out of order or from 0 is an entry's own refusal (U14), not the whole call's.
        for lines in ([0, 3], [9, 2]):
            self.assertEqual(sheet_schema.errors(SCHEMA["tool-input"], {"ask": [
                {"question": "x?", "references": [{"path": "a.ts", "lines": lines}]}]}), [])
        D = SCHEMA["state"]["$defs"]
        T = "2026-11-23T10:00:00.000Z"
        bad_verdicts = {
            "stale without current": {"verdict": "stale", "kind": "answer", "at": T, "id": "q1"},
            "closed without how": {"verdict": "closed", "kind": "answer", "at": T, "id": "q1"},
            "a retract's without target": {"verdict": "too-late", "kind": "retract", "at": T},
            "unseen applied": {"verdict": "applied", "kind": "unseen", "at": T, "by": "page-0901r001"},
            "unseen with an id": dict(unseen, id="q1"),
            "applied answer without id": {"verdict": "applied", "kind": "answer", "at": T},
            "stale on a dismissal": {"verdict": "stale", "kind": "dismiss", "at": T, "id": "q1", "current": 2}}
        for why, v in bad_verdicts.items():
            self.assertNotEqual(sheet_schema.errors(verdict, v), [], why)
        outcome = {"$ref": "#/$defs/outcome", "$defs": D}
        after = load(glob.glob(os.path.join(SET, "fixtures", "batch", "after", "sheet", "*", "state.json"))[0])
        dismissal = next(o for o in after["pending"] if o["kind"] == "dismiss")
        self.assertEqual(sheet_schema.errors(outcome, dismissal), [])
        for f, v in (("picks", []), ("text", ""), ("images", [])):
            self.assertNotEqual(sheet_schema.errors(outcome, dict(dismissal, **{f: v})), [], "a dismissal with " + f)
        closed = {"$ref": "#/$defs/closed", "$defs": D}
        withdrawn = load(glob.glob(os.path.join(SET, "fixtures", "closed-withdrawn", "before", "sheet", "*",
                                                "state.json"))[0])["closed"]["q2"]
        self.assertEqual(sheet_schema.errors(closed, withdrawn), [])
        self.assertNotEqual(sheet_schema.errors(closed, dict(withdrawn, receipt="Yes")), [])
        self.assertNotEqual(sheet_schema.errors(closed, dict(withdrawn, deliveredAt=T)), [], "a withdrawal is delivered "
                                                                                            "to nobody (U5)")
        sent = {"$ref": "#/$defs/sent", "$defs": SCHEMA["show"]["$defs"]}
        own = {"key": "maws-1101d003", "state": "delivered", "verdict": "applied", "kind": "delivered", "at": T}
        self.assertEqual(sheet_schema.errors(sent, own), [])
        self.assertNotEqual(sheet_schema.errors(sent, dict(own, state="accepted")), [], "never pending itself")
        q = {"key": "page-0701r002", "kind": "retract", "state": "queued", "target": "page-0701a001"}
        self.assertEqual(sheet_schema.errors(sent, q), [])
        for bad in (dict(q, id="q1"), dict(q, cancelled=True), {k: v for k, v in q.items() if k != "target"},
                    {"key": "page-0701a001", "kind": "answer", "state": "queued", "target": "page-0701r002", "id": "q1"},
                    {"key": "maws-1101d003", "kind": "delivered", "state": "queued", "id": "q1"}):
            self.assertNotEqual(sheet_schema.errors(sent, bad), [], bad)
        shown = load(os.path.join(SET, "fixtures", "batch", "show.after.json"))
        self.assertEqual(sheet_schema.errors(SCHEMA["show"], shown), [])
        for path, value in ((("question", "header"), "x" * 61), (("question", "question"), "x" * 2001),
                            (("picks",), ["x" * 201])):
            o = json.loads(json.dumps(shown["pending"][0]))
            target = o
            for k in path[:-1]:
                target = target[k]
            target[path[-1]] = value
            self.assertNotEqual(sheet_schema.errors(SCHEMA["show"], dict(shown, pending=[o])), [], path)
        self.assertEqual(sheet_schema.errors({"$ref": "#/$defs/question", "$defs": D},
                                             dict(after["questions"][0] if after["questions"] else
                                                  load(glob.glob(os.path.join(SET, "fixtures", "imported-legacy",
                                                       "after", "sheet", "*", "state.json"))[0])["questions"][0])), [],
                         "the record's strings unbounded")
        self.assertNotEqual(sheet_schema.errors(SCHEMA["inbox-line"], {"v": 1, "key": "page-00000001", "kind": "dismiss",
                                                                     "id": "q1234567890", "by": "page"}), [])
        answered = after["closed"]["q1"]
        self.assertNotEqual(sheet_schema.errors(closed, {k: v for k, v in answered.items() if k != "places"}), [])
        # Patterns end at the end of input (ECMA-262): a key with a newline after it is no key.
        self.assertNotEqual(sheet_schema.errors(SCHEMA["inbox-line"], {"v": 1, "key": "test-key-1\n",
                                                                     "kind": "dismiss", "id": "q1", "by": "cli"}), [])
        line = {"v": 1, "key": "page-00000001", "kind": "answer", "id": "q1", "revision": 1, "picks": [""], "by": "page"}
        self.assertEqual(sheet_schema.errors(SCHEMA["inbox-line"], line), [], "a pick of an empty label")
        self.assertEqual(sheet_schema.errors(SCHEMA["inbox-line"], dict(line, revision=1.0)), [], "1.0 is 1")
        self.assertIsNone(sheet.line_error(dict(line, revision=1.0)))

    def test_imported_legacy_is_a_record_and_no_input(self):
        rec = load(glob.glob(os.path.join(SET, "fixtures", "imported-legacy", "after", "sheet", "*", "state.json"))[0])
        self.assertEqual(sheet_schema.errors(SCHEMA["state"], rec), [])
        self.assertEqual([q.get("importedFrom", {}).get("index") for q in rec["questions"]], [0, 1, 2])
        entries = [{k: q[k] for k in ("question", "header", "options", "multiSelect")} for q in rec["questions"]]
        long_q, long_label, preview = entries
        self.assertEqual(len(long_q["question"]), 2001)
        self.assertEqual(len(long_label["options"][0]["label"]), 201)
        for e in (long_q, long_label):
            self.assertNotEqual(sheet_schema.errors(SCHEMA["tool-input"], {"ask": [e]}), [], e["header"])
        # A preview on a multi-select question is an entry's own rule (U14), refused alone and not by the schema,
        # which would deny the whole call.
        self.assertTrue(preview["multiSelect"] and any("preview" in o for o in preview["options"]))
        # Valid under today's tool: a header, two to four options, a description on each.
        for e in entries:
            self.assertTrue(isinstance(e["header"], str) and 2 <= len(e["options"]) <= 4)
            self.assertTrue(all(isinstance(o.get("description"), str) for o in e["options"]))
        self.assertEqual(sheet_schema.errors(SCHEMA["tool-input"], {"ask": [preview]}), [])

    def test_case_files(self):
        self.assertEqual(len(CASES), 21)
        for n, case in enumerate(CASES):
            c = load(os.path.join(SET, "fixtures", case, "case.json"))
            self.assertEqual(sorted(c), ["covers", "event", "name", "now", "session", "verdicts"], case)
            self.assertEqual(c["name"], case)
            for v in c["verdicts"].values():
                self.assertEqual(sheet_schema.errors({"$ref": "#/$defs/verdict", "$defs": SCHEMA["state"]["$defs"]},
                                                     v), [])
            after = os.path.join(SET, "fixtures", case, "after", "sheet", c["session"], "state.json")
            got = load(after)["verdicts"]
            for k, v in c["verdicts"].items():
                self.assertEqual(got[k], v, (case, k))


class TheReader(unittest.TestCase):
    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_show_json_is_every_fixtures(self):
        for case in CASES:
            c = load(os.path.join(SET, "fixtures", case, "case.json"))
            for side in ("before", "after"):
                with self.subTest(case=case, side=side):
                    home(case, side)
                    want = load(os.path.join(SET, "fixtures", case, "show.%s.json" % side))
                    self.assertEqual(sheet.model(c["session"]), want)

    def test_the_first_copy_is_the_one_applied(self):
        rec = load(glob.glob(os.path.join(SET, "fixtures", "torn-tail-resent", "after", "sheet", "*", "state.json"))[0])
        lines = [json.loads(x) for x in raw_bytes(glob.glob(os.path.join(SET, "fixtures", "torn-tail-resent", "after",
                                                                     "sheet", "*", "inbox.jsonl"))[0]).splitlines()]
        self.assertNotEqual(lines[0]["at"], lines[1]["at"])
        self.assertEqual(rec["pending"][0]["at"], lines[0]["at"])

    def test_a_lone_surrogate_in_the_record_is_printed_as_a_replacement(self):
        h = home("references", "before")
        s = load(os.path.join(SET, "fixtures", "references", "case.json"))["session"]
        path = os.path.join(h, "sheet", s, "state.json")
        write(path, raw_bytes(path).decode().replace('"label": "No"', '"label": "N\\ud83do"', 1))
        for args in (["--json"], []):
            rc, out, err = run(["sheet", "show", "--session", s] + args)
            self.assertEqual(rc, 0, err)
            self.assertIn("N\ufffdo", out)
        self.assertEqual(sheet_schema.errors(SCHEMA["show"], json.loads(run(["sheet", "show", "--session", s,
                                                                             "--json"])[1])), [])

    def test_a_queued_line_without_its_time(self):
        h = home("references", "before")
        s = load(os.path.join(SET, "fixtures", "references", "case.json"))["session"]
        write(os.path.join(h, "sheet", s, "inbox.jsonl"),
              '{"v":1,"key":"maws-00000001","kind":"answer","id":"q1","revision":1,"picks":["No"],"by":"maws"}\n')
        m = sheet.model(s)
        self.assertEqual(m["open"][0]["queued"]["key"], "maws-00000001")
        self.assertNotIn("at", m["open"][0]["queued"])
        self.assertEqual(sheet_schema.errors(SCHEMA["show"], m), [])

    def test_a_seq_that_keeps_moving_is_read_again(self):
        home("retract-unseen-late", "before")
        s = load(os.path.join(SET, "fixtures", "retract-unseen-late", "case.json"))["session"]
        real, n = sheet._read_json, [0]

        def moving(path):
            got = real(path)
            n[0] += 1
            got["seq"] = n[0]
            return got
        sheet._read_json = moving
        try:
            with self.assertRaises(sheet.Busy):
                sheet.model(s)
        finally:
            sheet._read_json = real
        self.assertEqual(n[0], 8, "state, inbox, state again, four times; no pair it did not verify")

    def test_a_bad_line_does_not_stop_the_reader(self):
        h = home("references", "before")
        s = load(os.path.join(SET, "fixtures", "references", "case.json"))["session"]
        good = '{"v":1,"key":"maws-00000002","kind":"answer","id":"q2","revision":1,"picks":["No"],"by":"maws"}\n'
        bad = ['{"v":1e999,"key":"maws-00000001","kind":"dismiss","id":"q1","by":"maws"}\n',
               '{"v":1,"key":"maws-00000003","kind":"dismiss","id":"q1","by":"maws","text":NaN}\n',
               '{"v":1,"key":"maws-00000004","kind":"answer","id":"q2","revision":1,"text":"\\ud83d","by":"maws"}\n',
               '{"v":1,"key":"maws-0000005\\n","kind":"dismiss","id":"q1","by":"maws"}\n',
               '{"v":1,"key":"maws-00000006","kind":"answer","id":"q2","revision":1,"picks":["Yes","No"],"by":"maws"}\n',
               '{"v":1,"key":"maws-00000007","kind":"dismiss","id":"q1","by":"maws","x":%s1%s}\n' % ("[" * 100000,
                                                                                                    "]" * 100000),
               '{"v":1,"key":"maws-00000008","kind":"dismiss","id":"q1","by":"maws","x":[%s]}\n' % (
                   "[" * 700 + '"\\ud83d"' + "]" * 700)]
        write(os.path.join(h, "sheet", s, "inbox.jsonl"), "".join(bad) + good)
        m = sheet.model(s)
        self.assertEqual([x["key"] for x in m["sent"]], ["maws-00000002"], "each bad line skipped (U2), the good read")
        self.assertEqual(m["open"][1]["queued"]["key"], "maws-00000002")
        self.assertEqual(sheet_schema.errors(SCHEMA["show"], m), [])

    def test_show_keys(self):
        c = load(os.path.join(SET, "fixtures", "batch", "case.json"))
        home("batch", "after")
        full = sheet.model(c["session"])
        got = sheet.model(c["session"], ["page-1401a002", "page-1401d003"])
        self.assertEqual(sorted(got), ["pending", "sent", "seq", "session", "v"])
        self.assertEqual([o["key"] for o in got["pending"]], ["page-1401a002", "page-1401d003"])
        self.assertEqual(got["sent"], [s for s in full["sent"] if s["key"] in ("page-1401a002", "page-1401d003")])
        self.assertEqual(sheet_schema.errors(SCHEMA["show"], got), [])

    def test_the_keyed_form_holds_texts_to_500(self):
        c = load(os.path.join(SET, "fixtures", "long-text", "case.json"))
        h = home("long-text", "after")
        o = sheet.model(c["session"], ["page-1501a001"])["pending"][0]
        self.assertEqual((len(o["text"]), o["textCut"], o["textFile"][:6]), (500, True, "texts/"))
        self.assertEqual(len(sheet.model(c["session"])["pending"][0]["text"]), 18214, "unkeyed: whole")
        # Fifty outcomes at every bound of the line and the question, in four-byte characters.
        path = os.path.join(h, "sheet", c["session"], "state.json")
        rec = load(path)
        big = rec["pending"][0]
        big["text"] = "\U0001F600" * 20000
        big["question"] = dict(big["question"], question="\U0001F600" * 2000, options=["\U0001F600" * 200] * 12)
        rec["pending"] = [dict(big, key="page-%08d" % n) for n in range(50)]
        write(path, json.dumps(rec, ensure_ascii=False))
        keys = ",".join("page-%08d" % n for n in range(50))
        rc, out, err = run(["sheet", "show", "--session", c["session"], "--json", "--keys", keys])
        self.assertEqual(rc, 0, err)
        self.assertLess(len(out.encode()), 4 * 1024 * 1024 // 2, "far under what a hook's process call returns")
        # An imported question has no input bounds: a pick, a header, a label and an asker's name at absurd lengths.
        huge = "\U0001F600" * 87000
        big = dict(big, text="short", picks=[huge + "1"], question=dict(
            big["question"], header=huge, options=[huge + "1", huge + "2"], asker={"agentId": "a1b2c3", "name": huge}))
        rec["pending"] = [dict(big, key="page-%08d" % n) for n in range(50)]
        rec["verdicts"] = {"page-%08d" % n: {"verdict": "applied", "kind": "answer", "at": big["acceptedAt"],
                                             "id": "q999999999"} for n in range(50)}
        write(path, json.dumps(rec, ensure_ascii=False))
        rc, out, err = run(["sheet", "show", "--session", c["session"], "--json", "--keys", keys])
        self.assertEqual(rc, 0, err)
        self.assertLess(len(out.encode()), 4 * 1024 * 1024 // 2)
        sent = json.loads(out)["sent"]
        self.assertEqual(len(sent), 50)
        self.assertTrue(all(len(json.dumps(x, ensure_ascii=False)) < 400 for x in sent), "each sent entry bounded")
        o = json.loads(out)["pending"][0]
        self.assertEqual((o["places"], len(o["picks"][0]), len(o["question"]["header"]),
                          len(o["question"]["options"][1]), len(o["question"]["asker"]["name"])), ([1], 200, 60, 200, 200))

    def test_a_pending_question_is_bounded(self):
        h = home("answer-applied", "after")
        c = load(os.path.join(SET, "fixtures", "answer-applied", "case.json"))
        path = os.path.join(h, "sheet", c["session"], "state.json")
        rec = load(path)
        rec["pending"][0]["question"]["question"] = "x" * 2500
        rec["pending"][0]["question"]["options"][0] = "y" * 250
        write(path, json.dumps(rec))
        q = sheet.model(c["session"])["pending"][0]["question"]
        self.assertEqual((len(q["question"]), len(q["options"][0])), (2000, 200))
        self.assertEqual(len(load(path)["pending"][0]["question"]["question"]), 2500, "the record unchanged")

    def test_a_reference_unchanged_and_changed(self):
        h = home("references", "before")
        c = load(os.path.join(SET, "fixtures", "references", "case.json"))
        path = os.path.join(h, "sheet", c["session"], "state.json")
        rec = load(path)
        f = os.path.join(h, "here.ts")
        write(f, "x\n")
        st = os.stat(f)
        rec["questions"][0]["references"][0].update(abs=f, size=st.st_size, mtimeMs=st.st_mtime_ns // 1000000)
        write(path, json.dumps(rec))
        refs = sheet.model(c["session"])["open"][0]["references"]
        self.assertEqual([r["changed"] for r in refs], [False, True, True])
        write(f, "y\n", "a")
        self.assertTrue(sheet.model(c["session"])["open"][0]["references"][0]["changed"])

    def test_through_the_command_before_any_migration(self):
        h = home("references", "before")
        s = load(os.path.join(SET, "fixtures", "references", "case.json"))["session"]
        rc, out, err = run(["sheet", "show", "--session", s])
        self.assertEqual(rc, 0, err)
        self.assertRegex(out, r"(?m)^q1  Session check$")
        self.assertIn("  file: src/auth.ts:40-80  (changed since asked)", out)
        self.assertIn("  queued (cli-1901a001): Yes", out)
        line = '{"v":1,"key":"demo-0001","kind":"dismiss","id":"q1","by":"cli"}\n'
        rc, out, err = run(["sheet", "put", "--session", s], line.encode())
        self.assertEqual((rc, json.loads(out)), (0, {"session": s, "results": [{"key": "demo-0001",
                                                                                 "state": "queued"}]}), err)
        rc, out, _ = run(["sheet", "show", "--session", s])
        self.assertNotRegex(out, r"(?m)^q1\b")
        self.assertIn("dismissed, not yet applied: q1", out)
        rc, out, _ = run(["sheet", "show", "--session", s, "--json"])
        self.assertEqual(json.loads(out)["hidden"], [{"id": "q1", "key": "demo-0001"}])
        self.assertEqual(sorted(os.listdir(h)), ["sheet"], "no registry read or migrated")
        rc, _, err = run(["sheet", "show", "--session", "5eed0000-0000-4000-8000-0000000000ff"])
        self.assertEqual((rc, err.strip()), (3, "sminos: no sheet: 5eed0000-0000-4000-8000-0000000000ff has no "
                                                "question sheet on this machine"))
        self.assertEqual(run(["sheet", "show", "--session", "../x"])[0], 2)
        self.assertEqual(run(["sheet", "show"])[0], 2)


# ------------------------------------------------------------------ the envelopes


def envelope(name):
    with open(os.path.join(SET, "examples", name, "envelope.txt"), encoding="utf-8") as f:
        return f.read()


def block(text):
    last = text.split("\n")[-1]
    m = re.fullmatch(r"<sheet-delivery>(.*)</sheet-delivery>", last)
    assert m, last[:80]
    return json.loads(m.group(1))


def example_record(name):
    return load(glob.glob(os.path.join(SET, "examples", name, "input", "sheet", "*", "state.json"))[0])


class TheEnvelopes(unittest.TestCase):
    def test_each_envelope(self):
        for name in EXAMPLES:
            with self.subTest(name):
                text, case, rec = envelope(name), load(os.path.join(SET, "examples", name, "case.json")), \
                    example_record(name)
                self.assertFalse(text.endswith("\n"))
                b = block(text)
                last = text.split("\n")[-1]
                self.assertNotRegex(last[len("<sheet-delivery>"):-len("</sheet-delivery>")], r"[<>&\u2028\u2029]")
                outcomes = {o["key"]: o for o in rec["pending"]}
                mine = [o for o in rec["pending"] if o["recipient"] == case["recipient"]]
                self.assertEqual(len(b["keys"]), len(b["answered"]) + len(b["dismissed"]))
                self.assertTrue(set(b["keys"]) <= {o["key"] for o in mine}, "only its recipient's pending outcomes")
                ids = [outcomes[k]["id"] for k in b["keys"]]
                self.assertEqual(ids, [a["id"] for a in b["answered"]] + b["dismissed"], "keys in that order")
                self.assertEqual([outcomes[k]["kind"] for k in b["keys"]],
                                 ["answer"] * len(b["answered"]) + ["dismiss"] * len(b["dismissed"]))
                for part in (b["answered"], b["dismissed"]):
                    nums = [int((x["id"] if isinstance(x, dict) else x)[1:]) for x in part]
                    self.assertEqual(nums, sorted(nums), "listed by the id's number")
                prose = text.split("\n")[:-1]
                named = set(re.findall(r"^(q[0-9]+)\b", "\n".join(prose), re.M))
                for ln in prose:
                    if ln.startswith("Dismissed: "):
                        named |= set(ln[len("Dismissed: "):-1].split(", "))
                self.assertEqual(named, {a["id"] for a in b["answered"]} | set(b["dismissed"]))
                self.assertLessEqual(units(text), BUDGET)
                self.assertLessEqual(len(b["keys"]), KEYS_MAX)
                for a in b["answered"]:
                    o = outcomes[b["keys"][[x["id"] for x in b["answered"]].index(a["id"])]]
                    self.assertLessEqual(len(a["text"]), TEXT_MAX)
                    self.assertEqual(a["text"], o["text"][:TEXT_MAX])
                    self.assertEqual(a.get("textCut", False), len(o["text"]) > TEXT_MAX)
                    self.assertEqual("textFile" in a, "textFile" in o)
                    labels = o["question"]["options"]
                    self.assertEqual([labels[p - 1] for p in a["picks"]], o["picks"], "picks are places")
                    self.assertEqual(a["revision"], o["revision"])
                more = len(mine) > len(b["keys"])
                self.assertEqual(b.get("more", False), more)
                self.assertEqual(text.split("\n")[0 if name != "subagent" else 1].endswith(" More follows."), more)

    def test_every_texts_file_is_named_by_its_hash(self):
        found = glob.glob(os.path.join(SET, "**", "texts", "*"), recursive=True)
        self.assertGreaterEqual(len(found), 5)
        for p in found:
            self.assertEqual(os.path.basename(p), hashlib.sha256(raw_bytes(p)).hexdigest() + ".txt", p)

    def test_long_is_sized_as_the_table_says(self):
        text, rec = envelope("long"), example_record("long")
        lines = text.split("\n")
        self.assertEqual(sum(1 for ln in lines if " is in " in ln and "and begins: " in ln), 2)
        full = {}
        for o in rec["pending"]:
            q = json.dumps(o["question"]["question"], ensure_ascii=False)
            full[o["id"]] = '%s %s → their text: %s' % (o["id"], q, json.dumps(o["text"], ensure_ascii=False))
            self.assertEqual(len(o["text"]), 20000)
        carried = {ln.split(" ")[0]: ln for ln in lines if " is in " in ln}
        self.assertEqual(sorted(carried), ["q1", "q2"], "the earlier of equal lengths first")
        two = units(text)
        one = two + units(full["q2"]) - units(carried["q2"])
        none = one + units(full["q1"]) - units(carried["q1"])
        self.assertLessEqual(two, BUDGET)
        self.assertGreater(one, BUDGET)
        self.assertGreater(none, BUDGET)
        for o in rec["pending"]:
            if o["id"] in carried:
                self.assertIn(o["textFile"], carried[o["id"]])
                self.assertIn(json.dumps(o["text"][:500] + "…", ensure_ascii=False), carried[o["id"]])
            else:
                self.assertIn(full[o["id"]], lines)

    def test_more_stops_at_two_hundred_keys(self):
        b, rec = block(envelope("more")), example_record("more")
        batches = {}
        for o in rec["pending"]:
            batches.setdefault(o["batch"], []).append(o["key"])
        self.assertEqual([len(v) for v in batches.values()], [50] * 5)
        first4 = [k for v in list(batches.values())[:4] for k in v]
        self.assertEqual(b["keys"], first4)
        self.assertEqual(len(first4) + 50, 250, "the fifth Send would make 250 keys")
        self.assertTrue(b["more"])

    def test_split_leaves_in_two_envelopes(self):
        first, then, rec = block(envelope("split")), block(envelope("split/then")), example_record("split")
        send = [o["key"] for o in rec["pending"]]
        self.assertEqual(len({o["batch"] for o in rec["pending"]}), 1, "one Send")
        self.assertLessEqual(len(send), 50, "one call of the door")
        self.assertTrue(all(len(o["text"]) == 2000 and "textFile" not in o for o in rec["pending"]))
        self.assertEqual(first["keys"] + then["keys"], send, "every key of the Send once, in order")
        self.assertTrue(first["more"])
        self.assertNotIn("more", then)
        self.assertTrue(envelope("split").split("\n")[0].endswith(" More follows."))
        self.assertFalse(envelope("split/then").split("\n")[0].endswith(" More follows."))
        answered_last = [k for k, c in rec["closed"].items() if "answer" in c]
        self.assertEqual(sorted(answered_last, key=lambda k: int(k[1:])), ["q%d" % n for n in range(9, 41)],
                         "the 32 answered last keep their answer's line")
        landed = example_record("split/then")
        self.assertEqual([o["key"] for o in landed["pending"]], then["keys"])
        for o in rec["pending"]:
            self.assertEqual("deliveredAt" in landed["closed"][o["id"]], o["key"] in first["keys"])

    def test_the_steer_carries_the_same_block(self):
        steer = read_text(os.path.join(SET, "examples", "terminal", "steer.txt"))
        self.assertEqual(steer.split("\n")[-1], envelope("terminal").split("\n")[-1])
        self.assertNotIn("Which auth method", steer, "no text a model wrote")

    def test_the_imported_label_is_cut_in_the_prose_only(self):
        text, rec = envelope("imported"), example_record("imported")
        label, options = rec["pending"][0]["picks"][0], rec["pending"][0]["question"]["options"]
        self.assertGreater(len(label), 200)
        self.assertEqual(options[1][:200], options[2][:200], "two labels share their first 200 characters")
        self.assertIn("→ %s…." % label[:200], text)
        self.assertEqual(block(text)["answered"][0]["picks"], [3])
        # The reader's model names the pick by its place too, read before any label is cut.
        os.environ["SMINOS_HOME"] = os.path.dirname(glob.glob(os.path.join(SET, "examples", "imported", "input",
                                                                         "sheet"))[0])
        try:
            m = sheet.model(rec["session"])
        finally:
            os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")
        o = m["pending"][0]
        self.assertEqual(o["places"], [3])
        self.assertEqual(o["question"]["options"][1], o["question"]["options"][2], "cut alike")
        self.assertEqual(m["closed"]["q1"]["places"], [3])
        self.assertEqual(sheet_schema.errors(SCHEMA["show"], m), [])

    def test_the_subagent_envelope_opens_with_whose_it_is(self):
        text = envelope("subagent")
        self.assertTrue(text.startswith("From the human, through the question tool, not from your coordinator: "
                                        "answers to questions you put on the sheet.\n[sheet v1] "))


# ------------------------------------------------------------------ the result's grammar


class TheGrammar(unittest.TestCase):
    def test_each_stored_call_parses(self):
        md = read_text(os.path.join(SET, "grammar", "result.md"))
        pattern = re.search(r"## The pattern a reader matches\n\n.*?\n\n    (\^.*\$)\n", md, re.S).group(1)
        for c in load(os.path.join(SET, "grammar", "result.examples.json")):
            first = c["result"].split("\n")[0]
            with self.subTest(first):
                self.assertRegex(first, pattern)
                self.assertEqual(parse(first), c["parsed"])
        for bad in ("Added q1,q2.", "Revised q3.", "Withdrew q2. Added q1.", "Added q1. ", "Nothing done"):
            self.assertNotRegex(bad, pattern)


def parse(first):
    if first == "Nothing done.":
        return {"form": "nothing"}
    if first == "Outcome not known yet.":
        return {"form": "unknown"}
    out = {"form": "sentences", "added": [], "revised": [], "withdrew": []}
    for word, body in re.findall(r"(Added|Revised|Withdrew) ([^.]*)\.", first):
        for m in re.finditer(r"(q[0-9]+)(?: \((?:entry ([0-9]+))?(?:, )?(?:revision ([0-9]+))?\))?", body):
            x = {"id": m.group(1)}
            if m.group(2):
                x["entry"] = int(m.group(2))
            if m.group(3):
                x["revision"] = int(m.group(3))
            out[{"Added": "added", "Revised": "revised", "Withdrew": "withdrew"}[word]].append(
                x["id"] if word == "Withdrew" else x)
    return out


# ------------------------------------------------------------------ the door


def answer(key, id_, revision=1, **f):
    return {"v": 1, "key": key, "kind": "answer", "id": id_, "revision": revision, "by": "cli", **f}


class TheDoor(unittest.TestCase):
    def setUp(self):
        self.h = home("answer-applied", "before")
        self.s = load(os.path.join(SET, "fixtures", "answer-applied", "case.json"))["session"]
        self.inbox = os.path.join(self.h, "sheet", self.s, "inbox.jsonl")
        self.was = raw_bytes(self.inbox)

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def put(self, lines, *flags):
        data = "".join(json.dumps(x) + "\n" for x in lines).encode()
        return run(["sheet", "put", "--session", self.s, *flags], data)

    def added(self):
        return [json.loads(x) for x in raw_bytes(self.inbox)[len(self.was):].splitlines()]

    def test_a_call_is_appended_whole_and_reads_queued(self):
        lines = [answer("cli-test0001", "q2", picks=["Yes"]),
                 {"v": 1, "key": "cli-test0002", "kind": "retract", "target": "cli-test0001", "by": "cli",
                  "at": "2026-11-23T12:00:00.000Z"}]
        rc, out, err = self.put(lines)
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out), {"session": self.s, "results": [
            {"key": "cli-test0001", "state": "queued"}, {"key": "cli-test0002", "state": "queued"}]})
        got = self.added()
        self.assertEqual([x["key"] for x in got], ["cli-test0001", "cli-test0002"])
        self.assertRegex(got[0]["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
        self.assertEqual(got[1]["at"], "2026-11-23T12:00:00.000Z", "a given time is kept")
        self.assertEqual(len({x["batch"] for x in got}), 1)
        self.assertRegex(got[0]["batch"], r"^[A-Za-z0-9._:-]{8,128}$")
        for x in got:
            self.assertEqual(sheet_schema.errors(SCHEMA["inbox-line"], x), [])
        rc, out, _ = self.put([answer("cli-test0003", "q2", picks=["No"])], "--no-wait")
        self.assertEqual((rc, "batch" in self.added()[-1]), (0, False), "one line: no batch")

    def test_each_refusal_appends_nothing(self):
        cases = {
            "fails the schema": [answer("cli-test0001", "q2")],
            "an unknown field": [answer("cli-test0001", "q2", picks=["Yes"], extra=1)],
            "a key too short": [answer("short", "q2", picks=["Yes"])],
            "an image that is not there": [answer("cli-test0001", "q1", picks=["OAuth"],
                                                  images=["uploads/missing.png"])],
            "a pick that is no label": [answer("cli-test0001", "q2", picks=["Maybe"])],
            "two picks on a single-select question": [answer("cli-test0001", "q1", picks=["OAuth", "Passkeys"])],
            "one bad line of two": [answer("cli-test0001", "q2", picks=["Yes"]), answer("cli-test0002", "q2")],
        }
        os.makedirs(os.path.join(self.h, "sheet", self.s, "uploads", "dir.png"))
        cases["an image that is a directory"] = [answer("cli-test0001", "q1", text="see", images=["uploads/dir.png"])]
        for why, lines in cases.items():
            with self.subTest(why):
                rc, _, err = self.put(lines)
                self.assertEqual(rc, 2, err)
                self.assertIn("nothing appended", err)
                self.assertEqual(raw_bytes(self.inbox), self.was)
        rc, _, _ = run(["sheet", "put", "--session", self.s], b"not json\n")
        self.assertEqual(rc, 2)
        rc, _, _ = run(["sheet", "put", "--session", self.s], b"".join(
            json.dumps(answer("cli-t%07d" % n, "q2", picks=["Yes"])).encode() + b"\n" for n in range(51)))
        self.assertEqual(rc, 2, "fifty lines a call at most")
        self.assertEqual(raw_bytes(self.inbox), self.was)
        # A pick checked only at the question's current revision: a stale answer passes the door, as §4.2 wants.
        rc, _, err = self.put([answer("cli-test0009", "q2", revision=3, picks=["Whatever"])])
        self.assertEqual(rc, 0, err)

    def test_a_text_with_line_separators_and_a_revision_of_one_point_oh(self):
        data = '{"v":1,"key":"cli-test0001","kind":"answer","id":"q2","revision":1.0,"text":"a\u2028b\u2029c\u0085d","by":"cli"}\n'
        rc, _, err = run(["sheet", "put", "--session", self.s, "--no-wait"], data.encode())
        self.assertEqual(rc, 0, err)
        got = self.added()[0]
        self.assertEqual((got["text"], got["revision"], type(got["revision"])), ("a\u2028b\u2029c\u0085d", 1, int))

    def test_lines_no_other_reader_could_read_are_refused(self):
        write(os.path.join(self.h, "sheet", self.s, "uploads", "a" * 251 + ".png"), b"x", "wb")   # it is there
        for why, data in (
                ("an infinity", '{"v":1e999,"key":"cli-test0001","kind":"dismiss","id":"q2","by":"cli"}'),
                ("NaN", '{"v":1,"key":"cli-test0001","kind":"answer","id":"q2","revision":NaN,"text":"x","by":"cli"}'),
                ("a lone surrogate", '{"v":1,"key":"cli-test0001","kind":"answer","id":"q2","revision":1,'
                                     '"text":"half \\ud83d","by":"cli"}'),
                ("a key ending in a newline", '{"v":1,"key":"test-key-1\\n","kind":"dismiss","id":"q2","by":"cli"}'),
                ("an upload name past 250", '{"v":1,"key":"cli-test0001","kind":"answer","id":"q1","revision":1,'
                                            '"text":"x","images":["uploads/%s.png"],"by":"cli"}' % ("a" * 251)),
                ("an id past q999999999", '{"v":1,"key":"cli-test0001","kind":"dismiss","id":"q1234567890",'
                                          '"by":"cli"}'),
                ("a value nested past the decoder", '{"v":1,"key":"cli-test0001","kind":"dismiss","id":"q2",'
                                                    '"by":"cli","x":%s1%s}' % ("[" * 100000, "]" * 100000))):
            with self.subTest(why):
                rc, _, err = run(["sheet", "put", "--session", self.s, "--no-wait"], (data + "\n").encode())
                self.assertEqual(rc, 2, err)
                self.assertNotIn("Traceback", err)
                self.assertEqual(raw_bytes(self.inbox), self.was)

    def test_a_short_write_is_completed_under_the_lock(self):
        real, calls = os.write, []

        import fcntl

        def short(fd, data):
            calls.append(len(data))
            probe = os.open(sheet.lock_path(self.s), os.O_RDWR)
            try:
                with self.assertRaises(BlockingIOError, msg="the lock is held while the write goes on"):
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(probe)
            return real(fd, bytes(data)[:max(1, len(data) // 3)])
        lines = [answer("cli-test0001", "q2", picks=["Yes"]), answer("cli-test0002", "q1", picks=["OAuth"])]
        os.write = short
        try:
            sheet.append(self.s, lines)
        finally:
            os.write = real
        self.assertGreater(len(calls), 1, "the write came back short")
        self.assertEqual([x["key"] for x in self.added()], ["cli-test0001", "cli-test0002"], "and was completed")

    def test_a_write_that_fails_leaves_nothing(self):
        import contextlib
        import io
        real, calls = os.write, []

        def failing(fd, data):
            calls.append(1)
            if len(calls) == 1:              # a whole first line reaches the file, then the disk is full
                return real(fd, bytes(data)[:bytes(data).index(b"\n") + 1])
            raise OSError(28, "No space left on device")
        os.write = failing
        err = io.StringIO()
        try:
            with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(err):
                sheet.append(self.s, [answer("cli-test0001", "q2", picks=["Yes"]),
                                      answer("cli-test0002", "q1", picks=["OAuth"])])
        finally:
            os.write = real
        self.assertEqual(e.exception.code, 1)
        self.assertIn("nothing appended", err.getvalue())
        self.assertEqual(raw_bytes(self.inbox), self.was, "cut back to its length before the call")

    def test_no_record_exits_3(self):
        rc, _, err = run(["sheet", "put", "--session", "5eed0000-0000-4000-8000-0000000000ff"],
                         (json.dumps(answer("cli-test0001", "q1", text="x")) + "\n").encode())
        self.assertEqual(rc, 3)
        self.assertIn("no sheet", err)
        self.assertFalse(os.path.exists(os.path.join(self.h, "sheet", "5eed0000-0000-4000-8000-0000000000ff")))

    def test_a_held_lock_exits_75(self):
        import fcntl
        fd = os.open(sheet.lock_path(self.s), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        old, sheet.LOCK_WAIT_S = sheet.LOCK_WAIT_S, 0.2
        try:
            import contextlib
            import io
            err = io.StringIO()
            with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(err):
                sheet.append(self.s, [answer("cli-test0001", "q2", picks=["Yes"])])
            self.assertEqual(e.exception.code, 75)
            self.assertIn("is busy", err.getvalue())
        finally:
            sheet.LOCK_WAIT_S = old
            os.close(fd)
        self.assertEqual(raw_bytes(self.inbox), self.was)
        self.assertTrue(os.path.exists(sheet.lock_path(self.s)), "the lock file stays")

    def test_a_missing_last_newline_is_written_first(self):
        write(self.inbox, b'{"v":1,"key":"page-torn0001"', "ab")
        rc, _, err = self.put([answer("cli-test0001", "q2", picks=["Yes"])], "--no-wait")
        self.assertEqual(rc, 0, err)
        data = raw_bytes(self.inbox)
        self.assertTrue(data.endswith(b'"page-torn0001"\n' + data.split(b"\n")[-2] + b"\n"))
        self.assertEqual(json.loads(data.split(b"\n")[-2])["key"], "cli-test0001")

    def test_eight_doors_at_once_keep_each_call_whole(self):
        script = (
            "import os, sys; sys.path.insert(0, %r); import sminos\n"
            "sh = sminos.sibling_module('sminos_sheet')\n"
            "w = int(sys.argv[1])\n"
            "for c in range(25):\n"
            "    lines = [{'v': 1, 'key': 'cli-w%%d-c%%02d-l%%d' %% (w, c, n), 'kind': 'dismiss', 'id': 'q2', 'by': 'cli',"
            " 'text': 'x' * 3000} for n in range(3)]\n"
            "    sh.append(%r, lines)\n") % (SCRIPTS, self.s)
        procs = [subprocess.Popen([sys.executable, "-B", "-c", script, str(w)], env=dict(os.environ))
                 for w in range(8)]
        for p in procs:
            self.assertEqual(p.wait(120), 0)
        got = self.added()
        self.assertEqual(len(got), 600)
        for i in range(0, 600, 3):
            call = got[i:i + 3]
            self.assertEqual(len({x["batch"] for x in call}), 1, "a call's lines together")
            self.assertEqual([x["key"][-2:] for x in call], ["l0", "l1", "l2"])
            self.assertEqual(len({x["key"][:-3] for x in call}), 1)
        self.assertEqual(len({x["batch"] for x in got}), 200)

    def test_a_record_path_that_is_a_link_is_refused_and_nothing_outside_is_written(self):
        outside = tempfile.mkdtemp(prefix="outside.")
        self.addCleanup(shutil.rmtree, outside)
        rec = os.path.join(self.h, "sheet", self.s)
        # The inbox a link to a file outside the record: the door refuses, exit 1, the outside file as it was.
        target = os.path.join(outside, "elsewhere.jsonl")
        write(target, b"not the record's\n", "wb")
        os.unlink(self.inbox)
        os.symlink(target, self.inbox)
        rc, out, err = self.put([answer("cli-test0001", "q2", picks=["Yes"])], "--no-wait")
        self.assertEqual((rc, out), (1, ""), err)
        self.assertIn("inbox.jsonl is not a file; nothing appended", err)
        self.assertEqual(raw_bytes(target), b"not the record's\n")
        # A step on that record reads nothing through the link and writes nothing: it answers bad-record.
        before = {n: raw_bytes(os.path.join(rec, n)) for n in ("state.json",)}
        rc, out, err = run(["sheet", "step", "--session", self.s], json.dumps({"event": "drain", "runner": "terminal"}).encode())
        self.assertEqual(json.loads(out), {"ok": False, "code": "bad-record", "error": "the record's inbox.jsonl is not a file"}, err)
        self.assertEqual({n: raw_bytes(os.path.join(rec, n)) for n in before}, before)
        self.assertEqual(raw_bytes(target), b"not the record's\n")
        os.unlink(self.inbox)
        write(self.inbox, self.was, "wb")
        # The record directory itself a link to one outside: refused too, the outside inbox unchanged.
        moved = os.path.join(outside, "record")
        shutil.move(rec, moved)
        os.symlink(moved, rec)
        rc, out, err = self.put([answer("cli-test0002", "q2", picks=["Yes"])], "--no-wait")
        self.assertEqual(rc, 1, err)
        self.assertIn("is not a directory; nothing appended", err)
        self.assertEqual(raw_bytes(os.path.join(moved, "inbox.jsonl")), self.was)

    def test_a_bridge_answers_the_verdicts(self):
        # The stand-in's socket is named through a short link to SMINOS_HOME: a socket's path is bounded.
        link = os.path.join(tempfile.mkdtemp(prefix="sb.", dir="/tmp"), "s")
        os.symlink(self.h, link)
        self.addCleanup(shutil.rmtree, os.path.dirname(link))
        os.environ["SMINOS_HOME"] = link
        verdict = {"verdict": "stale", "kind": "answer", "at": "2026-11-23T12:00:01.000Z", "id": "q2", "current": 2}
        standin = bridge_standin.StandIn(CLI, self.s, ops=["sheet"], env=dict(os.environ),
                                         results={"sheet": {"verdicts": {"cli-test0001": verdict}}})
        self.addCleanup(standin.stop)
        rc, out, err = self.put([answer("cli-test0001", "q2", picks=["Yes"]),
                                 answer("cli-test0002", "q1", picks=["OAuth"])])
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out)["results"], [{"key": "cli-test0001", "state": "stale", **verdict},
                                                      {"key": "cli-test0002", "state": "queued"}])
        sent = [c for c in standin.commands if c.get("op") == "sheet"]
        self.assertEqual([c["keys"] for c in sent], [["cli-test0001", "cli-test0002"]])
        rc, out, _ = self.put([answer("cli-test0003", "q2", picks=["Yes"])], "--no-wait")
        self.assertEqual(json.loads(out)["results"], [{"key": "cli-test0003", "state": "queued"}])
        self.assertEqual(len([c for c in standin.commands if c.get("op") == "sheet"]), 1, "--no-wait tells no one")
        standin.stop()
        other = bridge_standin.StandIn(CLI, self.s, ops=["btw"], env=dict(os.environ))
        self.addCleanup(other.stop)
        rc, out, _ = self.put([answer("cli-test0004", "q2", picks=["Yes"])])
        self.assertEqual(json.loads(out)["results"], [{"key": "cli-test0004", "state": "queued"}],
                         "a bridge that does not know the op")


if __name__ == "__main__":
    try:
        result = unittest.main(exit=False, verbosity=1).result
    finally:
        shutil.rmtree(BASE, ignore_errors=True)
    ok = result.wasSuccessful()
    print("test_sheet_contract: %d %s" % (result.testsRun - len(result.failures) - len(result.errors) - len(
        result.skipped), "passed" if ok else "passed, %d failed" % (len(result.failures) + len(result.errors))))
    sys.exit(0 if ok else 1)
