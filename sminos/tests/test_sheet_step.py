#!/usr/bin/env python3
"""The question sheet's step (plan docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, M2's Proves).

Run: python3 -B sminos/tests/test_sheet_step.py   (ends `test_sheet_step: N passed`)
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import base64
import contextlib
import copy
import datetime
import errno
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
PLUGIN = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN, "skills", "sminos", "scripts")
CLI = os.path.join(SCRIPTS, "sminos")
SET = os.path.join(PLUGIN, "types", "sheet")
VECTORS = os.path.join(HERE, "sheet-vectors")
VECTORS_GEN = os.path.join(HERE, "sheet-vectors.gen.py")
BASE = tempfile.mkdtemp(prefix="sheets.", dir="/tmp")
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"))
os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
sys.path.insert(0, HERE)
sys.path.insert(0, SCRIPTS)
import sminos  # noqa: E402
sheet = sminos.sibling_module("sminos_sheet")
step_module = sminos.sibling_module("sminos_sheet_step")
UTC = datetime.timezone.utc
REAL_REPLACE, REAL_WRITE = os.replace, os.write    # a death is a patched os call, restored after each test
REAL_RMTREE, REAL_SHUTIL_RMTREE = sheet._rmtree, shutil.rmtree
REAL_RENAME = os.rename


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(obj):
    """The generator's serialization (I1): what a step's output is compared in."""
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode()


def tree(root):
    """Every file under root, a JSON document re-serialized as the generator writes it."""
    out = {}
    for d, _, names in os.walk(root):
        for n in names:
            p = os.path.join(d, n)
            rel = os.path.relpath(p, root)
            with open(p, "rb") as f:
                data = f.read()
            out[rel] = dump(json.loads(data)) if n in ("state.json", ".start-receipt.json") else data
    return out


def scratch(src=None):
    """A new $SMINOS_HOME, holding a copy of `src` when given, set as the process's."""
    h = tempfile.mkdtemp(prefix="h.", dir=BASE)
    if src and os.path.isdir(src):
        shutil.copytree(src, h, dirs_exist_ok=True)
    os.environ["SMINOS_HOME"] = h
    return h


def content(c):
    """A vector's file content as bytes: a JSON document as the set writes one, a string as given, base64 bytes."""
    if isinstance(c, dict) and set(c) == {"$base64"}:
        return base64.b64decode(c["$base64"])
    if isinstance(c, (dict, list)):
        return dump(c)
    return c.encode()


def materialize(files):
    h = scratch()
    for rel, c in files.items():
        p = os.path.join(h, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(content(c))
    return h


def without_locks(t):
    return {p: d for p, d in t.items() if not p.endswith(".lock")}


class Replay(unittest.TestCase):
    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_every_published_fixture_replays(self):
        for case in sorted(os.listdir(os.path.join(SET, "fixtures"))):
            with self.subTest(case=case):
                c = load(os.path.join(SET, "fixtures", case, "case.json"))
                h = scratch(os.path.join(SET, "fixtures", case, "before"))
                out = sheet.run_step(c["session"], json.dumps(c["event"]).encode(), now=c["now"], tz=UTC)
                self.assertTrue(out["ok"], out)
                self.assertEqual(out["effects"]["verdicts"], {k: v for k, v in c["verdicts"].items()
                                                              if k in c["event"].get("keys", [])})
                # a fixture is the record's: the staging, the mod's own place, is the vectors' to pin
                want = tree(os.path.join(SET, "fixtures", case, "after"))
                got = {p: d for p, d in tree(h).items() if p.startswith("sheet/%s/" % c["session"])}
                self.assertEqual(sorted(got), sorted(want))
                for p in want:
                    self.assertEqual(got[p], want[p], p)


    def test_the_vectors_are_the_generators(self):
        p = subprocess.run([sys.executable, "-B", VECTORS_GEN, "--check"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_every_vector_replays(self):
        names = sorted(os.listdir(VECTORS))
        self.assertGreaterEqual(len(names), 28)
        for n in names:
            v = load(os.path.join(VECTORS, n))
            with self.subTest(vector=v["name"]):
                h = materialize(v["before"])
                out = sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)
                self.assertEqual(out["ok"], v["answer"]["ok"], out)
                if out["ok"]:
                    self.assertEqual(out["effects"], v["answer"]["effects"])
                else:
                    self.assertEqual(out["code"], v["answer"]["code"])
                want = {rel: (dump(json.loads(content(c))) if rel.endswith(("state.json", ".start-receipt.json"))
                              else content(c)) for rel, c in v["after"].items()}
                got = without_locks(tree(h))
                self.assertEqual(sorted(got), sorted(want))
                for p in want:
                    self.assertEqual(got[p], want[p], p)


class Envelopes(unittest.TestCase):
    def test_each_published_example_is_composed(self):
        names = sorted(d for d in os.listdir(os.path.join(SET, "examples"))
                       if os.path.isdir(os.path.join(SET, "examples", d))) + ["split/then"]
        for name in names:
            with self.subTest(example=name):
                base = os.path.join(SET, "examples", name)
                c = load(os.path.join(base, "case.json"))
                sess = os.listdir(os.path.join(base, "input", "sheet"))[0]
                h = scratch(os.path.join(base, "input"))
                state = load(os.path.join(h, "sheet", sess, "state.json"))
                got = step_module.envelope(state, c["recipient"], os.path.join(h, "sheet", sess), UTC, running=())
                with open(os.path.join(base, "envelope.txt"), encoding="utf-8") as f:
                    want = f.read().replace("{HOME}", h)
                self.assertIsNotNone(got)
                self.assertEqual(got["text"], want)


# ------------------------------------------------------------------ helpers for records built here

NOW = "2026-11-24T10:00:00.000Z"
SESSION = "5eed0000-0000-4000-8000-0000000002aa"


def ev(name, **f):
    e = {"event": name, "runner": "terminal", "remote": False, "acked": []}
    e.update(f)
    return e


def step(event, now=NOW, session=SESSION):
    return sheet.run_step(session, json.dumps(event).encode(), now=now, tz=UTC)


def state_of(session=SESSION):
    return load(os.path.join(os.environ["SMINOS_HOME"], "sheet", session, "state.json"))


def vector_home(name):
    v = load(os.path.join(VECTORS, name + ".json"))
    return v, materialize(v["before"])


def run_cli(args, stdin=b"", env=None):
    p = subprocess.run([CLI] + args, input=stdin, capture_output=True, env=dict(os.environ, **(env or {})),
                       timeout=120)
    return p.returncode, p.stdout.decode(), p.stderr.decode()


def opts(*labels):
    return [{"label": x} for x in labels]


def inline_call(call_id, entries=(), withdraw=(), asker="main", floor=None):
    c = {"callId": call_id, "asker": asker, "entries": list(entries), "withdraw": list(withdraw)}
    if floor is not None:
        c["floor"] = floor
    return ev("call", call=c)


def ask_all(prefix, entries):
    """Entries asked through calls of at most 20 (the tool's own limit), in order."""
    for n in range(0, len(entries), 20):
        assert step(inline_call("%s%d" % (prefix, n), entries[n:n + 20]))["ok"]


def line(key, kind, by="page", at="2026-11-24T09:59:00.000Z", **f):
    out = {"v": 1, "key": key, "kind": kind}
    out.update(f)
    out.update(by=by, at=at)
    return out


def put_raw(session, lines):
    """Lines appended as the door appends them, without its process."""
    path = os.path.join(os.environ["SMINOS_HOME"], "sheet", session, "inbox.jsonl")
    with open(path, "ab") as f:
        for x in lines:
            f.write((json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n").encode())


# ------------------------------------------------------------------ twice is once; the calls' horizon


class Repeats(unittest.TestCase):
    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def twice(self, home, session, event, now=NOW):
        first = sheet.run_step(session, json.dumps(event).encode(), now=now, tz=UTC)
        after_one = without_locks(tree(home))
        second = sheet.run_step(session, json.dumps(event).encode(), now=now, tz=UTC)
        self.assertTrue(first["ok"] and second["ok"], (first, second))
        self.assertEqual(without_locks(tree(home)), after_one)
        self.assertEqual(second["seq"], first["seq"])
        return first, second

    def test_a_drain_a_landed_a_reroute_and_a_start_ordered_twice_equal_once(self):
        for case in ("batch", "stopped-queue", "retract-too-late"):
            c = load(os.path.join(SET, "fixtures", case, "case.json"))
            h = scratch(os.path.join(SET, "fixtures", case, "before"))
            self.twice(h, c["session"], c["event"], c["now"])
        for name in ("landed", "reroute", "start-existing", "start-import", "agents-ended"):
            v, h = vector_home(name)
            self.twice(h, v["session"], v["event"], v["now"])

    def test_a_call_ordered_twice_answers_its_first_result_and_adds_nothing(self):
        v, h = vector_home("call-add")
        first, second = self.twice(h, v["session"], v["event"], v["now"])
        self.assertEqual(second["effects"]["result"], first["effects"]["result"])
        self.assertEqual(len(second["view"]["open"]), 3)

    def test_settle_after_a_committed_call_answers_its_result(self):
        v, h = vector_home("call-add")
        first = sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)
        settled = sheet.run_step(v["session"], json.dumps(ev("settle", call={"callId": "toolu_v01"})).encode(),
                                 now=v["now"], tz=UTC)
        self.assertEqual(settled["effects"]["result"], first["effects"]["result"])
        self.assertNotIn("foreclosed", settled["effects"])

    def test_settle_first_forecloses_and_the_call_then_commits_nothing(self):
        v, h = vector_home("call-add")
        settled = sheet.run_step(v["session"], json.dumps(ev("settle", call={"callId": "toolu_v01"})).encode(),
                                 now=v["now"], tz=UTC)
        self.assertTrue(settled["effects"]["foreclosed"])
        late = sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)
        self.assertTrue(late["effects"]["foreclosed"])
        self.assertNotIn("result", late["effects"])
        self.assertEqual([q["id"] for q in state_of(v["session"])["questions"]], ["q1"])
        self.assertFalse(os.path.isdir(os.path.join(h, "sheet", v["session"], "refs")), "nothing captured is kept")

    def test_a_call_ordered_after_its_acknowledgement_is_gone(self):
        for name, call_id in (("call-add", "toolu_v01"), ("call-withdraw-only", "toolu_v08"),
                              ("call-all-refused", "toolu_v09")):
            with self.subTest(vector=name):
                v, h = vector_home(name)
                self.assertTrue(sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"],
                                               tz=UTC)["ok"])
                acked = sheet.run_step(v["session"], json.dumps(ev("drain", acked=[call_id])).encode(), now=v["now"],
                                       tz=UTC)
                self.assertEqual(state_of(v["session"])["calls"], [])
                self.assertFalse(os.path.exists(os.path.join(h, "sheet", ".staging", v["session"], call_id)))
                before = without_locks(tree(h))
                late = sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)
                self.assertEqual(late["code"], "gone")
                self.assertEqual(without_locks(tree(h)), before)
                self.assertEqual(acked["seq"], state_of(v["session"])["seq"])

    def test_no_event_but_start_makes_a_record(self):
        events = [ev("drain"), ev("landed", keys=["page-00000001"]), ev("reroute", keys=["page-00000001"]),
                  ev("settle", call={"callId": "toolu_x"}), inline_call("toolu_y", [{"question": "Ship?"}])]
        for e in events:
            with self.subTest(event=e["event"]):
                h = scratch()
                out = step(e)
                self.assertEqual((out["ok"], out["code"]), (False, "no-record"))
                self.assertFalse(os.path.exists(os.path.join(h, "sheet", SESSION)))

    def test_a_bad_event_changes_nothing(self):
        h = scratch()
        self.assertTrue(step(ev("start", start={"source": "startup"}))["ok"])
        before = without_locks(tree(h))
        for raw in (b"not json", b"[]", b'{"event": "explode"}', json.dumps(ev("call", call={"callId": "../x"})).encode(),
                    json.dumps(ev("start", start={"source": "compact"})).encode(),
                    json.dumps(inline_call("toolu_z", [{"question": ""}])).encode(),
                    json.dumps(inline_call("toolu_z", [{"question": "x?", "references": [{"path": "a"}]}])).encode(),
                    json.dumps(ev("call", call={"callId": "toolu_q"}, acked=["toolu_q"])).encode(),
                    json.dumps(ev("start", start={"source": "resume", "today": {"definite": True, "asks": [
                        {"file": "../../../etc/passwd"}]}})).encode()):
            with self.subTest(raw=raw[:60]):
                out = sheet.run_step(SESSION, raw, now=NOW, tz=UTC)
                self.assertEqual((out["ok"], out["code"]), (False, "bad-event"), out)
                self.assertEqual(without_locks(tree(h)), before)


# ------------------------------------------------------------------ deaths, in process


class Deaths(unittest.TestCase):
    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")
        os.replace, os.write = REAL_REPLACE, REAL_WRITE

    def clean(self, case):
        c = load(os.path.join(SET, "fixtures", case, "case.json"))
        h = scratch(os.path.join(SET, "fixtures", case, "before"))
        sheet.run_step(c["session"], json.dumps(c["event"]).encode(), now=c["now"], tz=UTC)
        return without_locks(tree(h))

    def test_a_replace_that_raises_then_the_same_event_is_one_clean_step(self):
        want = self.clean("batch")
        c = load(os.path.join(SET, "fixtures", "batch", "case.json"))
        h = scratch(os.path.join(SET, "fixtures", "batch", "before"))

        def failing(src, dst):
            if dst.endswith("state.json"):
                raise OSError(5, "the disk said no")
            return REAL_REPLACE(src, dst)

        os.replace = failing
        with self.assertRaises(OSError):
            sheet.run_step(c["session"], json.dumps(c["event"]).encode(), now=c["now"], tz=UTC)
        os.replace = REAL_REPLACE
        self.assertTrue(any(n.startswith(".tmp-") for n in os.listdir(os.path.join(h, "sheet", c["session"]))))
        self.assertEqual(tree(h)["sheet/%s/state.json" % c["session"]],
                         dump(load(os.path.join(SET, "fixtures", "batch", "before", "sheet", c["session"],
                                                "state.json"))), "the record as it was")
        self.assertTrue(sheet.run_step(c["session"], json.dumps(c["event"]).encode(), now=c["now"], tz=UTC)["ok"])
        self.assertEqual(without_locks(tree(h)), want)

    def test_a_write_cut_short_then_the_same_event_is_one_clean_step(self):
        want = self.clean("long-text")
        c = load(os.path.join(SET, "fixtures", "long-text", "case.json"))
        h = scratch(os.path.join(SET, "fixtures", "long-text", "before"))
        calls = []

        def short(fd, data):
            calls.append(len(data))
            if len(calls) == 2:           # texts/ first, then state.json's temporary file: half of it, then death
                REAL_WRITE(fd, bytes(data[:len(data) // 2]))
                raise OSError(28, "no space left")
            return REAL_WRITE(fd, data)

        os.write = short
        with self.assertRaises(OSError):
            sheet.run_step(c["session"], json.dumps(c["event"]).encode(), now=c["now"], tz=UTC)
        os.write = REAL_WRITE
        self.assertTrue(sheet.run_step(c["session"], json.dumps(c["event"]).encode(), now=c["now"], tz=UTC)["ok"])
        self.assertEqual(without_locks(tree(h)), want)

    def test_a_call_whose_replace_raised_is_settled_as_foreclosed(self):
        v, h = vector_home("call-add")
        os.replace = lambda src, dst: (_ for _ in ()).throw(OSError(5, "no")) if dst.endswith("state.json") \
            else REAL_REPLACE(src, dst)
        with self.assertRaises(OSError):
            sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)
        os.replace = REAL_REPLACE
        out = sheet.run_step(v["session"], json.dumps(ev("settle", call={"callId": "toolu_v01"})).encode(),
                             now=v["now"], tz=UTC)
        self.assertTrue(out["effects"]["foreclosed"])
        st = state_of(v["session"])
        self.assertEqual(([q["id"] for q in st["questions"]], st["calls"]),
                         (["q1"], [{"callId": "toolu_v01", "foreclosed": True}]))

    def test_a_step_killed_after_its_replace_is_ordered_again_or_settled(self):
        v, h = vector_home("call-add")
        sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)    # its answer lost
        out = sheet.run_step(v["session"], json.dumps(ev("settle", call={"callId": "toolu_v01"})).encode(),
                             now=v["now"], tz=UTC)
        self.assertEqual(out["effects"]["result"], "Added q2, q3.")


# ------------------------------------------------------------------ the command's verbs


class Verbs(unittest.TestCase):
    def setUp(self):
        self.home = scratch()
        self.assertTrue(step(ev("start", start={"source": "startup"}))["ok"])
        self.assertTrue(step(inline_call("toolu_c1", [
            {"question": "Which auth method?", "header": "Auth", "options": opts("OAuth", "Passkeys")},
            {"question": "Ship today?", "options": opts("Yes", "No")},
            {"question": "Which screens?", "options": opts("Home", "Settings", "Billing"), "multiSelect": True},
            {"question": "What should the empty state say?"}]))["ok"])

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def cli(self, *args, env=None):
        return run_cli(["sheet"] + list(args), env=env)

    def verdicts(self, keys):
        return step(ev("drain", keys=keys))["effects"]["verdicts"]

    def test_a_handle_names_the_revision_the_human_saw(self):
        code, out, _ = self.cli("show", "--session", SESSION)
        self.assertEqual(code, 0)
        self.assertIn("q2", out)
        self.assertTrue(step(inline_call("toolu_c2", [{"id": "q2", "question": "Ship today, after the freeze?",
                                                       "options": opts("Wait", "Yes", "No")}]))["ok"])
        code, _, err = self.cli("answer", "--session", SESSION, "q2", "--pick", "1")
        self.assertEqual(code, 2)
        self.assertIn("q2 is at revision 2: show it again, then answer q2@2", err)
        code, _, err = self.cli("answer", "--session", SESSION, "q2@1", "--pick", "1")
        self.assertEqual(code, 2)
        self.assertIn("answer q2@2", err)
        code, out, _ = self.cli("answer", "--session", SESSION, "q2@2", "--pick", "1")
        self.assertEqual(code, 0, out)
        key = json.loads(out)["results"][0]["key"]
        self.assertEqual(json.loads(out)["results"][0]["state"], "queued")
        self.assertEqual(self.verdicts([key])[key]["verdict"], "applied")
        o = state_of()["pending"][0]
        self.assertEqual((o["picks"], o["revision"]), (["Wait"], 2), "the new first option")

    def test_the_bands_command_reads_a_sheet_whose_session_is_no_member(self):
        """M5: the band's unreachable-page form prints `sminos sheet show <first 8>`; the session need not be a
        member, so the verbs also take a unique prefix (8 characters or more) of a session that has a record."""
        band = "4 open questions · the page is unreachable: sminos sheet show %s" % SESSION[:8]
        printed = band.split(": ", 1)[1].split()
        self.assertEqual(printed[0], "sminos")
        code, out, err = run_cli(printed[1:])
        self.assertEqual(code, 0, err)
        self.assertIn("Which auth method?", out)
        code, out, err = self.cli("answer", SESSION[:13], "q2", "--pick", "1")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["results"][0]["state"], "queued")
        # Shorter than 8, or matching no record, it is no session's: the member resolver's refusal stands.
        for who in (SESSION[:7], "5eed0001"):
            code, _, err = self.cli("show", who)
            self.assertNotEqual(code, 0)
            self.assertIn("no member matching", err)
        # Two records sharing it: refused, naming both.
        other = SESSION[:-1] + "b"
        self.assertTrue(step(ev("start", start={"source": "startup"}), session=other)["ok"])
        code, _, err = self.cli("show", SESSION[:8])
        self.assertNotEqual(code, 0)
        self.assertIn(SESSION, err)
        self.assertIn(other, err)

    def test_the_prefix_and_the_member_are_looked_up_once(self):
        """The prefix fallback and the member it falls back to share one lookup (find_target reconciles projects)."""
        real, seen = sminos.find_target, []
        sminos.find_target = lambda q: (seen.append(q), real(q))[1]
        try:
            ns = type("A", (), {"member": SESSION[:8], "session": None})()
            self.assertEqual(sheet.resolve(ns, "show"), SESSION)
            self.assertEqual(seen, [SESSION[:8]])
            del seen[:]
            ns = type("A", (), {"member": "5eed0001", "session": None})()
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()) as err:
                sheet.resolve(ns, "show")
            self.assertIn("no member matching", err.getvalue())
            self.assertEqual(seen, ["5eed0001"])
        finally:
            sminos.find_target = real

    def test_a_line_sent_against_the_old_wording_is_stale_with_current(self):
        stale = line("page-00000001", "answer", id="q2", revision=1, picks=["Yes"])
        self.assertTrue(step(inline_call("toolu_c2", [{"id": "q2", "question": "Ship today?",
                                                       "options": opts("Yes", "No", "Later")}]))["ok"])
        code, out, err = run_cli(["sheet", "put", "--session", SESSION, "--no-wait"],
                                 stdin=(json.dumps(stale) + "\n").encode())
        self.assertEqual(code, 0, err)
        v = self.verdicts(["page-00000001"])["page-00000001"]
        self.assertEqual((v["verdict"], v["current"]), ("stale", 2))

    def test_picks_by_place_or_by_label_in_any_case(self):
        code, out, err = self.cli("answer", "--session", SESSION, "q3", "--pick", "home", "--pick", "3",
                                  "--text", "and the footer")
        self.assertEqual(code, 0, err)
        key = json.loads(out)["results"][0]["key"]
        self.verdicts([key])
        o = state_of()["pending"][0]
        self.assertEqual((o["picks"], o["text"]), (["Home", "Billing"], "and the footer"))
        for args, why in ((["q1", "--pick", "1", "--pick", "2"], "takes one pick"),
                          (["q1", "--pick", "Magic"], "has no option"), (["q1"], "--pick or --text"),
                          (["q9", "--pick", "1"], "q9 is not open"), (["q4", "--pick", "1"], "has no option")):
            with self.subTest(args=args):
                code, _, err = self.cli("answer", "--session", SESSION, *args)
                self.assertEqual(code, 2)
                self.assertIn(why, err)

    def test_an_image_is_copied_into_uploads_and_named(self):
        img = os.path.join(BASE, "shot.PNG")
        with open(img, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        code, out, err = self.cli("answer", "--session", SESSION, "q4", "--text", "see the sketch", "--image", img)
        self.assertEqual(code, 0, err)
        key = json.loads(out)["results"][0]["key"]
        self.verdicts([key])
        o = state_of()["pending"][0]
        self.assertRegex(o["images"][0], r"^uploads/cli-[0-9a-f]{16}\.png$")
        self.assertTrue(os.path.isfile(os.path.join(self.home, "sheet", SESSION, o["images"][0])))

    def test_dismiss_is_one_batch_and_retract_takes_a_queued_answer_back(self):
        code, out, err = self.cli("dismiss", "--session", SESSION, "q1", "q2")
        self.assertEqual(code, 0, err)
        keys = [r["key"] for r in json.loads(out)["results"]]
        with open(os.path.join(self.home, "sheet", SESSION, "inbox.jsonl")) as f:
            tail = f.read().splitlines()
        self.assertEqual(len({json.loads(x)["batch"] for x in tail}), 1)
        code, out, _ = self.cli("answer", "--session", SESSION, "q3", "--pick", "Home")
        akey = json.loads(out)["results"][0]["key"]
        code, out, _ = self.cli("retract", "--session", SESSION, akey)
        self.assertEqual(code, 0)
        rkey = json.loads(out)["results"][0]["key"]
        m = sheet.model(SESSION)
        self.assertTrue(next(s for s in m["sent"] if s["key"] == akey)["cancelled"])
        v = self.verdicts(keys + [akey, rkey])
        self.assertEqual([v[k]["verdict"] for k in keys + [akey, rkey]], ["applied", "applied", "retracted",
                                                                          "retracted"])
        code, _, err = self.cli("dismiss", "--session", SESSION, "q1")
        self.assertEqual(code, 2)
        self.assertIn("q1 is not open", err)

    def test_a_session_does_not_act_on_its_own_sheet(self):
        for args in (("answer", "--session", SESSION, "q1", "--pick", "1"), ("dismiss", "--session", SESSION, "q1"),
                     ("retract", "--session", SESSION, "page-00000001")):
            with self.subTest(verb=args[0]):
                code, _, err = self.cli(*args, env={"CLAUDE_CODE_SESSION_ID": SESSION})
                self.assertEqual(code, 2)
                self.assertIn("its own sheet", err)

    def test_the_queue_while_stopped_then_a_start(self):
        """Acceptance 6 at the record's level: queued, a retract takes one back, a start applies the rest owed
        across a stop."""
        _, out, _ = self.cli("answer", "--session", SESSION, "q1", "--pick", "OAuth")
        k1 = json.loads(out)["results"][0]["key"]
        _, out, _ = self.cli("answer", "--session", SESSION, "q2", "--pick", "Yes")
        k2 = json.loads(out)["results"][0]["key"]
        m = sheet.model(SESSION)
        self.assertEqual({s["key"]: s["state"] for s in m["sent"]}, {k1: "queued", k2: "queued"})
        self.cli("retract", "--session", SESSION, k1)
        out = step(ev("start", start={"source": "resume"}), now="2026-11-24T11:00:00.000Z")
        self.assertEqual(out["effects"]["applied"], [k2])
        st = state_of()
        self.assertEqual([(o["key"], o["acrossStop"]) for o in st["pending"]], [(k2, True)])
        self.assertIn("q1", [q["id"] for q in st["questions"]])
        self.assertEqual(st["verdicts"][k1]["verdict"], "retracted")
        self.assertEqual(out["view"]["owedAcrossStop"], 1)
        self.assertFalse(out["view"]["ready"][0]["wakes"])

    def test_two_surfaces_answer_one_question(self):
        """Acceptance 19's first half: the first line applied wins, the second reads closed."""
        a = line("page-00000002", "answer", id="q2", revision=1, picks=["Yes"])
        b = line("cli-00000003", "answer", by="cli", id="q2", revision=1, picks=["No"])
        for x in (a, b):
            run_cli(["sheet", "put", "--session", SESSION, "--no-wait"], stdin=(json.dumps(x) + "\n").encode())
        v = self.verdicts([a["key"], b["key"]])
        self.assertEqual((v[a["key"]]["verdict"], v[b["key"]]["verdict"], v[b["key"]]["how"]),
                         ("applied", "closed", "answered"))

    def test_remove(self):
        stage = os.path.join(self.home, "sheet", ".staging", SESSION, "toolu_r")
        os.makedirs(stage)
        sminos.session_running = lambda s: {"sessionId": s, "pid": 1}
        try:
            with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()) as err:
                sheet.remove(SESSION)
            self.assertIn("runs; its sheet goes when it stops", err.getvalue())
            self.assertEqual(e.exception.code, 2)
            self.assertTrue(os.path.isdir(os.path.join(self.home, "sheet", SESSION)))
            sheet.remove(SESSION, cleared=True)
        finally:
            del sminos.session_running
        self.assertFalse(os.path.exists(os.path.join(self.home, "sheet", SESSION)))
        self.assertFalse(os.path.exists(stage))
        self.assertTrue(os.path.isfile(os.path.join(self.home, "sheet", SESSION + ".lock")))
        code, out, _ = self.cli("remove", "--session", SESSION)
        self.assertEqual(code, 3)

    def test_remove_through_the_command(self):
        code, out, err = self.cli("remove", "--session", SESSION)
        self.assertEqual(code, 0, err)
        self.assertIn("removed", out)
        self.assertEqual(self.cli("show", "--session", SESSION)[0], 3)


class Surfaces(unittest.TestCase):
    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def register(self, h, name, pid, reach="local", age=5, now=NOW):
        t = sheet.STEP().when(now) - datetime.timedelta(seconds=age)
        d = os.path.join(h, "sheet", "surfaces")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name + ".json"), "w") as f:
            json.dump({"v": 1, "name": name, "pid": pid, "url": "http://%s.localhost" % name, "reach": reach,
                       "heartbeatAt": t.strftime("%Y-%m-%dT%H:%M:%S.000Z")}, f)

    def test_alive_and_suiting(self):
        h = scratch()
        dead = subprocess.Popen(["true"])
        dead.wait()
        self.register(h, "a-old", 1, age=31)
        self.register(h, "b-gone", dead.pid)
        self.register(h, "c-local", 1)
        self.register(h, "d-remote", 1, reach="remote")
        with open(os.path.join(h, "sheet", "surfaces", "e-bad.json"), "w") as f:
            f.write('{"v": 1, "name": "e bad"}')
        regs = sheet.surfaces(NOW)
        self.assertEqual([(r["name"], r["alive"]) for r in regs],
                         [("a-old", False), ("b-gone", False), ("c-local", True), ("d-remote", True)])
        self.assertEqual(sheet.suiting(regs, False)[0]["name"], "c-local")
        self.assertEqual(sheet.suiting(regs, True), (regs[3], 2))
        self.assertEqual(step(ev("start", start={"source": "startup"}, remote=True))["view"]["surface"]["name"],
                         "d-remote")

    def test_a_file_that_vanished_or_is_half_written_is_passed_over(self):
        h = scratch()
        self.register(h, "standin", 1)
        d = os.path.join(h, "sheet", "surfaces")
        os.symlink(os.path.join(d, "nowhere.json"), os.path.join(d, "gone.json"))     # listed, then not there
        os.mkdir(os.path.join(d, "dir.json"))
        with open(os.path.join(d, "half.json"), "w") as f:
            f.write('{"v": 1, "name": "mawsd", "pid": 1, "url": "http://ma')
        with open(os.path.join(d, "bytes.json"), "wb") as f:
            f.write(b"\xff\xfe not text")
        with open(os.path.join(d, "mawsd.json.tmp-77"), "w") as f:          # a writer's temporary file
            json.dump({"v": 1, "name": "mawsd", "pid": 1, "url": "http://tmp.localhost", "reach": "local",
                       "heartbeatAt": "2026-11-24T09:59:59.000Z"}, f)
        self.assertEqual([r["name"] for r in sheet.surfaces(NOW)], ["standin"])
        self.assertEqual(sheet.suiting(sheet.surfaces(NOW), False)[1], 1)

    def test_mawsd_first_then_by_name_never_the_listing(self):
        h = scratch()
        self.register(h, "a-file", 1)
        self.register(h, "m-file", 1)
        self.register(h, "z-file", 1)
        d = os.path.join(h, "sheet", "surfaces")
        for f, name in (("a-file", "zeta"), ("m-file", "alpha"), ("z-file", "mawsd")):
            with open(os.path.join(d, f + ".json")) as fh:
                r = json.load(fh)
            with open(os.path.join(d, f + ".json"), "w") as fh:
                json.dump(dict(r, name=name), fh)
        self.assertEqual([r["name"] for r in sheet.surfaces(NOW)], ["mawsd", "alpha", "zeta"])
        self.assertEqual(step(ev("start", start={"source": "startup"}))["view"]["surface"]["name"], "mawsd")
        os.unlink(os.path.join(d, "z-file.json"))
        self.assertEqual(sheet.suiting(sheet.surfaces(NOW), False)[0]["name"], "alpha")

    def test_the_url_loses_one_trailing_slash(self):
        h = scratch()
        self.register(h, "mawsd", 1)
        p = os.path.join(h, "sheet", "surfaces", "mawsd.json")
        with open(p) as f:
            r = json.load(f)
        with open(p, "w") as f:
            json.dump(dict(r, url="http://sheet.localhost:47590/"), f)
        out = step(ev("start", start={"source": "startup"}))
        self.assertEqual(out["view"]["surface"], {"name": "mawsd", "url": "http://sheet.localhost:47590",
                                                  "reach": "local"})
        self.assertEqual(out["view"]["surface"]["url"] + "/s/" + SESSION,
                         "http://sheet.localhost:47590/s/" + SESSION, "the link")

    def test_the_plain_listing_prints_no_control_character_a_registration_holds(self):
        """S1: a registration's URL is printed to a terminal: C0 and C1 controls (ESC among them) are taken out and
        a line break is a space, so a registration can neither forge a line nor drive the terminal. JSON is as
        written."""
        h = scratch()
        url = "http://127.0.0.1:1/\x1b[31mred\x1b[0m\x1b]8;;http://x\x07link\x1b]8;;\x07\rback\nnext\u0085nel\x9bcsi"
        self.register(h, "standin", os.getpid())
        p = os.path.join(h, "sheet", "surfaces", "standin.json")
        reg = load(p)
        reg["url"] = url
        with open(p, "w") as f:
            json.dump(reg, f)
        code, out, err = run_cli(["sheet", "surfaces"])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("\n"), 1, out)
        self.assertFalse(any(ord(c) < 0x20 or 0x7f <= ord(c) <= 0x9f for c in out.rstrip("\n")), repr(out))
        self.assertIn("http://127.0.0.1:1/[31mred[0m]8;;http://xlink]8;; back next nelcsi", out)
        code, out, _ = run_cli(["sheet", "surfaces", "--json"])
        self.assertEqual(json.loads(out)["surfaces"][0]["url"], url)

    def test_the_stand_in_surface(self):
        h = scratch()
        p = subprocess.Popen([sys.executable, "-B", os.path.join(HERE, "sheet_surface.py"), "--every", "0.2"])
        try:
            path = os.path.join(h, "sheet", "surfaces", "standin.json")
            for _ in range(100):
                if os.path.exists(path):
                    break
                import time
                time.sleep(0.05)
            code, out, err = run_cli(["sheet", "surfaces", "--json"])
            self.assertEqual(code, 0, err)
            self.assertEqual([(r["name"], r["alive"]) for r in json.loads(out)["surfaces"]], [("standin", True)])
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(run_cli(["sheet", "surfaces"])[1].split()[-1], "alive")
        finally:
            p.terminate()
            p.wait()
        self.assertFalse(os.path.exists(path), "removed when it stops")

    def test_probe(self):
        h = scratch()
        code, out, _ = run_cli(["sheet", "probe", "--session", SESSION])
        self.assertEqual((code, json.loads(out)), (0, {"record": False, "open": 0, "pending": 0, "queued": 0,
                                                      "surface": None, "surfaces": 0}))
        step(ev("start", start={"source": "startup"}))
        step(inline_call("toolu_p", [{"question": "Ship?", "options": opts("Yes", "No")}, {"question": "Why?"}]))
        put_raw(SESSION, [line("page-00000009", "answer", id="q1", revision=1, picks=["Yes"])])
        self.register(h, "standin", 1, now=sheet._now_ms())
        code, out, _ = run_cli(["sheet", "probe", "--session", SESSION, "--remote"])
        self.assertEqual(json.loads(out), {"record": True, "open": 2, "pending": 0, "queued": 1, "surface": None,
                                           "surfaces": 1})


# ------------------------------------------------------------------ the composer's packing, on records built in process

SURF = {"name": "standin", "url": "http://sheet.localhost:47590", "reach": "local"}
WHERE = "/sheets/" + SESSION         # a record's absolute path, as the composer is given it


def built(entries, start_now=NOW):
    """A record holding `entries` as open questions q1..qN, made by the pure step."""
    st, _, _ = step_module.apply(None, b"", {"event": "start", "start": {"source": "startup"}}, start_now, SESSION)
    call = {"callId": "toolu_b", "asker": "main", "entries": [{"entry": e, "captures": []} for e in entries],
            "withdraw": []}
    st, fx, _ = step_module.apply(st, b"", {"event": "call", "call": call}, start_now, SESSION, SURF)
    st["seq"] += 2
    return st


def lines_bytes(lines):
    return b"".join((json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n").encode() for x in lines)


def drained(st, lines, event="drain", now=NOW):
    e = {"event": event}
    if event == "start":
        e["start"] = {"source": "resume"}
    st2, fx, writes = step_module.apply(st, lines_bytes(lines), e, now, SESSION)
    return st2, fx, writes


def answers(ids, text, batch=None, at="2026-11-24T09:59:00.000Z"):
    out = []
    for i in ids:
        x = {"v": 1, "key": "page-%08d" % i, "kind": "answer", "id": "q%d" % i, "revision": 1, "text": text(i)}
        if batch:
            x["batch"] = batch
        x.update(by="page", at=at)
        out.append(x)
    return out


def land(st, keys):
    return step_module.apply(st, b"", {"event": "landed", "keys": keys}, NOW, SESSION)[0]


def delivered_all(test, st, recipient="main"):
    """Envelopes composed and landed one by one until nothing is pending: each checked against I7's limits."""
    out = []
    while step_module.mine(st, recipient):
        before = copy.deepcopy(st)
        e = step_module.envelope(st, recipient, WHERE, UTC)
        test.assertEqual(st, before, "composing changes nothing")
        test.assertLessEqual(step_module.units(e["text"]), 60000)
        test.assertLessEqual(len(e["keys"]), 200)
        test.assertTrue(e["keys"])
        out.append(e)
        st = land(st, e["keys"])
    for e in out[:-1]:
        test.assertTrue(e["more"] and " More follows." in e["text"].splitlines()[0] and '"more":true' in e["text"])
    test.assertFalse(out[-1]["more"])
    return out


class Packing(unittest.TestCase):
    def test_fifty_answers_of_twenty_thousand(self):
        st = built([{"question": "Section %d?" % i} for i in range(1, 51)])
        texts = {i: ("Answer %d, every word of it. " % i * 1000)[:20000] for i in range(1, 51)}
        st, fx, writes = drained(st, answers(range(1, 51), texts.get, batch="page-b0000001"))
        self.assertEqual(len(writes), 50, "each text past 2,000 has its file")
        envs = delivered_all(self, st)
        self.assertGreater(len(envs), 1)
        seen = []
        for e in envs:
            for k in e["keys"]:
                i = int(k[5:])
                whole = json.dumps(texts[i], ensure_ascii=False) in e["text"]
                filed = ("their text, 20,000 characters, is in %s/texts/%s.txt and begins: "
                         % (WHERE, step_module.sha(texts[i].encode()))) in e["text"]
                self.assertTrue(whole != filed, (k, whole, filed))
                seen.append(k)
        self.assertEqual(sorted(seen), sorted("page-%08d" % i for i in range(1, 51)), "each once")

    def test_what_one_envelope_left_packs_with_a_later_batch(self):
        st = built([{"question": "Wording %d?" % i} for i in range(1, 43)])
        st, _, _ = drained(st, answers(range(1, 41), lambda i: ("Wording %d. " % i * 300)[:2000], batch="page-b000000A"))
        first = step_module.envelope(st, "main", WHERE, UTC)
        self.assertTrue(first["more"])
        st, _, _ = drained(st, answers((41, 42), lambda i: "short", batch="page-b000000B"))
        st = land(st, first["keys"])
        second = step_module.envelope(st, "main", WHERE, UTC)
        self.assertEqual(set(second["keys"]), {"page-%08d" % i for i in range(len(first["keys"]) + 1, 43)})
        self.assertFalse(second["more"])

    def test_two_batches_that_fit_leave_together(self):
        st = built([{"question": "Q%d?" % i} for i in range(1, 5)])
        st, _, _ = drained(st, answers((1, 2), lambda i: "one", batch="page-b000000A") +
                           answers((3, 4), lambda i: "two", batch="page-b000000B"))
        e = step_module.envelope(st, "main", WHERE, UTC)
        self.assertEqual((len(e["keys"]), e["more"], e["wakes"]), (4, False, True))

    def test_two_hundred_and_one_keys_leave_as_two_hundred_and_one(self):
        st = built([{"question": "Keep %d?" % i} for i in range(1, 202)])
        dis = [{"v": 1, "key": "page-d%07d" % i, "kind": "dismiss", "id": "q%d" % i, "by": "page",
                "at": "2026-11-24T09:59:00.000Z"} for i in range(1, 202)]
        st, _, _ = drained(st, dis)
        envs = delivered_all(self, st)
        self.assertEqual([len(e["keys"]) for e in envs], [200, 1])
        self.assertFalse(any(e["wakes"] for e in envs), "a dismissal never wakes")

    def test_a_fresh_answer_goes_in_the_first_envelope(self):
        st = built([{"question": "Old %d?" % i} for i in range(1, 62)])
        st, _, _ = drained(st, answers(range(1, 61), lambda i: ("Old answer %d. " % i * 200)[:2000]), "start")
        old = step_module.envelope(st, "main", WHERE, UTC)
        self.assertTrue(old["more"] and not old["wakes"], "sixty old answers fill an envelope and wake nothing")
        st, _, _ = drained(st, answers([61], lambda i: "fresh"))
        e = step_module.envelope(st, "main", WHERE, UTC)
        self.assertIn("page-00000061", e["keys"])
        self.assertTrue(e["wakes"])
        self.assertLessEqual(step_module.units(e["text"]), 60000)


class TheCap(unittest.TestCase):
    def test_the_sheet_holds_five_hundred_open(self):
        """U7: an add past 500 open questions is refused with the reason; a revise still applies."""
        st = built([{"question": "Keep %d?" % i} for i in range(1, 501)])
        self.assertEqual(len(st["questions"]), 500)
        call = {"callId": "toolu_cap", "asker": "main", "withdraw": [], "entries": [
            {"entry": {"question": "One more?"}, "captures": []},
            {"entry": {"id": "q1", "question": "Keep 1, still?"}, "captures": []}]}
        st2, fx, _ = step_module.apply(st, b"", {"event": "call", "call": call}, NOW, SESSION, SURF, UTC)
        self.assertEqual(fx["result"], "Revised q1 (entry 2, revision 2).\n"
                                       "Not done: entry 1, the sheet holds 500 open questions.")
        self.assertEqual((len(st2["questions"]), st2["nextId"]), (500, 501))
        st3, fx, _ = step_module.apply(st2, b"", {"event": "call", "call": dict(call, callId="toolu_cap2", entries=[],
                                                                                 withdraw=["q2"])},
                                       NOW, SESSION, SURF, UTC)
        call3 = dict(call, callId="toolu_cap3", entries=call["entries"][:1])
        st4, fx, _ = step_module.apply(st3, b"", {"event": "call", "call": call3}, NOW, SESSION, SURF, UTC)
        self.assertEqual(fx["result"], "Added q501.", "one withdrawn, one more fits")


class TheContext(unittest.TestCase):
    def entries(self, n, qlen=2000, labels=12):
        return [{"question": ("Question %d: " % i + "why " * 600)[:qlen], "header": "H%d" % i,
                 "options": [{"label": ("Option %d of %d " % (j, i) + "o" * 200)[:200]} for j in range(labels)]}
                for i in range(1, n + 1)]

    def test_whole_when_it_fits(self):
        st = built(self.entries(3, qlen=40, labels=2))
        c = step_module.context(st, SESSION, "a resume")
        self.assertEqual(c.splitlines()[0], "[sheet v1] Your question sheet, after a resume.")
        self.assertEqual(len(c.splitlines()), 5)
        self.assertNotIn("…", c)

    def test_cut_at_its_budget(self):
        st = built(self.entries(20))
        c = step_module.context(st, SESSION, "a compaction")
        self.assertLessEqual(step_module.units(c), 60000)
        self.assertEqual(len(c.splitlines()), 22, "every question, each cut")
        self.assertIn("…", c)
        line = c.splitlines()[1]
        self.assertLessEqual(len(line), 400 + 12 * 90)

    def test_stopped_at_its_budget(self):
        st = built(self.entries(500))
        c = step_module.context(st, SESSION, "a compaction")
        self.assertLessEqual(step_module.units(c), 60000)
        lines = c.splitlines()
        self.assertEqual(lines[-1], "New ids continue from q501.")
        self.assertRegex(lines[-2], r"^and \d+ more open, q\d+ to q500: sminos sheet show --session %s prints them\.$"
                         % SESSION)
        shown = len(lines) - 3
        self.assertIn(" %d more open, q%d to" % (500 - shown, shown + 1), lines[-2])


# ------------------------------------------------------------------ bounds


FOUR = "\U0001F600"                   # four bytes in UTF-8, two UTF-16 units


def at_bounds(i):
    """A question at every bound of the input, in four-byte characters."""
    return {"question": "%d" % i + FOUR * 1999, "header": FOUR * 60, "context": FOUR * 8000,
            "options": [{"label": "%d-%d" % (i, j) + FOUR * 190, "description": FOUR * 500, "preview": FOUR * 8000}
                        for j in range(12)]}


class Bounds(unittest.TestCase):
    """A record at every bound answers a step under 3 MiB and a probe under 4 KiB (I5)."""

    def tearDown(self):
        shutil.rmtree(os.environ["SMINOS_HOME"], ignore_errors=True)     # some hundreds of megabytes each
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def write_state(self, h, st, inbox=b""):
        d = os.path.join(h, "sheet", SESSION)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "state.json"), "wb") as f:
            f.write(json.dumps(st, ensure_ascii=False, separators=(",", ":")).encode())
        with open(os.path.join(d, "inbox.jsonl"), "wb") as f:
            f.write(inbox)

    def test_a_record_at_every_bound(self):
        h = scratch()
        st = step_module.empty_record(SESSION)
        qs = []
        for i in range(1, 501):
            q = step_module.question_of(at_bounds(i), "q%d" % i, 1, "main", NOW, "toolu_b", [])
            qs.append(q)
        snap = step_module.snapshot(qs[0])
        pend = [{"key": "page-%08d" % i, "kind": "answer", "id": "q%d" % (1000 + i), "revision": 1, "picks": [],
                 "text": FOUR * 20000, "textFile": "texts/%064d.txt" % i, "images": [], "by": "page", "at": NOW,
                 "acceptedAt": NOW, "recipient": "main", "taken": False, "acrossStop": False, "question": snap}
                for i in range(1, 301)]
        closed = {"q%d" % (1000 + i): {"how": "answered", "at": NOW, "revision": 1, "asker": "main",
                                       "header": FOUR * 60, "question": FOUR * 200, "receipt": FOUR * 80,
                                       "places": [], "key": "page-%08d" % i, "answer": FOUR * 2000}
                  for i in range(1, 2001)}
        st.update(seq=9, nextId=3001, questions=qs, pending=pend, closed=closed)
        self.write_state(h, st)
        os.makedirs(os.path.join(h, "sheet", "surfaces"))
        for n in range(40):
            with open(os.path.join(h, "sheet", "surfaces", "s%02d.json" % n), "w") as f:
                json.dump({"v": 1, "name": "s%02d" % n, "pid": 1, "url": "http://s%02d.localhost" % n,
                           "reach": "local", "heartbeatAt": "2026-11-24T09:59:59.000Z"}, f)
        out = step(ev("drain"))
        size = len(json.dumps(out, ensure_ascii=False).encode())
        self.assertTrue(out["ok"])
        self.assertLess(size, 3 << 20, size)
        self.assertEqual((out["view"]["surfaces"], out["view"]["pendingCount"], len(out["view"]["pending"])),
                         (40, 300, 200))
        code, probe_out, err = run_cli(["sheet", "probe", "--session", SESSION])
        self.assertEqual(code, 0, err)
        self.assertLess(len(probe_out.encode()), 4096)
        self.assertEqual(json.loads(probe_out)["open"], 500)

    def test_a_start_that_applies_five_hundred_answers_at_the_bounds(self):
        h = scratch()
        st = step_module.empty_record(SESSION)
        st.update(seq=3, nextId=501,
                  questions=[step_module.question_of(at_bounds(i), "q%d" % i, 1, "main", NOW, "toolu_b", [])
                             for i in range(1, 501)])
        lines = answers(range(1, 501), lambda i: "%d" % i + FOUR * 19990)
        for n, x in enumerate(lines):
            x["batch"] = "page-b%07d" % (n // 50)
            x["picks"] = ["%d-0" % (n + 1) + FOUR * 190]
        self.write_state(h, st, lines_bytes(lines))
        out = step(ev("start", start={"source": "resume"}), now="2026-11-24T11:00:00.000Z")
        self.assertTrue(out["ok"])
        self.assertLess(len(json.dumps(out, ensure_ascii=False).encode()), 3 << 20)
        self.assertEqual((len(out["effects"]["applied"]), out["view"]["pendingCount"], out["view"]["answeredCount"],
                          len(out["view"]["answered"])), (500, 500, 500, 32))
        self.assertLessEqual(step_module.units(out["view"]["ready"][0]["text"]), 60000)
        again = step(ev("drain"), now="2026-11-24T11:00:01.000Z")
        self.assertEqual((again["view"]["answered"], again["view"]["answeredCount"]),
                         (out["view"]["answered"], out["view"]["answeredCount"]))

    def test_an_answer_past_three_mib_is_bounded(self):
        out = {"ok": True, "seq": 1, "effects": {}, "view": {
            "ready": [{"text": "x" * (1 << 20)} for _ in range(4)],
            "closed": {"q%d" % i: {"how": "answered", "receipt": "y" * 2000} for i in range(1, 1001)}}}
        b = sheet._bounded(out)
        self.assertLessEqual(len(json.dumps(b).encode()), 3 << 20)
        self.assertEqual(len(b["view"]["ready"]), 1)
        self.assertEqual(len(b["view"]["closed"]), 1000, "envelopes go first")
        out["view"]["ready"] = [{"text": "x" * (3 << 20)}]
        b = sheet._bounded(out)
        self.assertLessEqual(len(json.dumps(b).encode()), 3 << 20)
        self.assertEqual(b["view"]["ready"], [])


# ------------------------------------------------------------------ at once


class AtOnce(unittest.TestCase):
    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_a_reader_through_two_hundred_doors_and_fifty_steps(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        h = scratch()
        step(ev("start", start={"source": "startup"}))
        ask_all("toolu_c", [{"question": "Q%d?" % i, "options": opts("Yes", "No")} for i in range(1, 151)])
        path = os.path.join(h, "sheet", SESSION, "state.json")
        stop, seen, bad, failed = threading.Event(), [], [], []

        def reader():
            try:
                while not stop.is_set():
                    with open(path, "rb") as f:
                        raw = f.read()
                    try:
                        seen.append(json.loads(raw)["seq"])
                    except ValueError:
                        bad.append(raw[:80])
                    try:
                        sheet.model(SESSION)
                    except sheet.Busy:
                        pass
            except BaseException as e:    # a reader that fails fails the test
                failed.append(repr(e))

        def door(i):
            x = line("page-%08d" % i, "answer", id="q%d" % (i % 150 + 1), revision=1, picks=["Yes" if i % 2 else "No"])
            return run_cli(["sheet", "put", "--session", SESSION, "--no-wait"], stdin=(json.dumps(x) + "\n").encode())

        def a_step(i):
            if i % 10 == 9:
                m = sheet.model(SESSION, None)
                return run_cli(["sheet", "step", "--session", SESSION],
                               stdin=json.dumps(ev("landed", keys=[o["key"] for o in m["pending"][:5]])).encode())
            return run_cli(["sheet", "step", "--session", SESSION], stdin=json.dumps(ev("drain")).encode())

        t = threading.Thread(target=reader)
        t.start()
        try:
            with ThreadPoolExecutor(12) as pool:
                # interleaved: a step after every four doors, so steps run while doors still append
                order = [("door", i) for i in range(200)]
                for n in range(50):
                    order.insert(n * 5 + 4, ("step", n))
                jobs = [(kind, pool.submit(door if kind == "door" else a_step, i)) for kind, i in order]
                results = [j.result() for kind, j in jobs if kind == "door"] + \
                    [j.result() for kind, j in jobs if kind == "step"]
        finally:
            stop.set()
            t.join()
        self.assertEqual([r for r in results if r[0] != 0], [])
        for r in results[200:]:
            self.assertTrue(json.loads(r[1])["ok"], r)
        step(ev("drain"))
        self.assertEqual(failed, [])
        self.assertEqual(bad, [])
        self.assertEqual(seen, sorted(seen), "seq only rises")
        self.assertGreater(len(set(seen)), 10, "the reader saw the record change under it")
        st = state_of()
        keys = ["page-%08d" % i for i in range(200)]
        self.assertEqual([k for k in keys if k not in st["verdicts"]], [], "every key has its verdict")
        self.assertEqual(sum(1 for k in keys if st["verdicts"][k]["verdict"] == "applied"), 150)
        pending = {o["key"] for o in st["pending"]}
        for k in keys:
            v = st["verdicts"][k]
            if v["verdict"] == "applied":
                self.assertTrue(k in pending or "deliveredAt" in st["closed"][v["id"]], k)
        with open(os.path.join(h, "sheet", SESSION, "inbox.jsonl"), "rb") as f:
            self.assertEqual(len(f.read().splitlines()), 200, "no line lost")

    def test_a_record_removed_while_a_door_waits(self):
        h = scratch()
        step(ev("start", start={"source": "startup"}))
        step(inline_call("toolu_c", [{"question": "Ship?", "options": opts("Yes", "No")}]))
        x = line("page-00000001", "dismiss", id="q1")
        with sheet.Lock(SESSION):
            p = subprocess.Popen([CLI, "sheet", "put", "--session", SESSION, "--no-wait"], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            p.stdin.write((json.dumps(x) + "\n").encode())
            p.stdin.close()
            import time
            time.sleep(1.0)               # the door is past its checks and waits on the lock
            shutil.rmtree(os.path.join(h, "sheet", SESSION))
        p.wait(timeout=30)
        err = p.stderr.read()
        p.stdout.close()
        p.stderr.close()
        self.assertEqual(p.returncode, 3, err)
        self.assertIn(b"no sheet", err)
        self.assertTrue(os.path.isfile(os.path.join(h, "sheet", SESSION + ".lock")))


# ------------------------------------------------------------------ fix wave 1 (the task review of M2)


class TheAcknowledgementWindow(unittest.TestCase):
    """Finding 1: what the replace forgets is made unavailable before it, so a death at either side of the replace
    never lets a late step of the call apply again."""

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")
        os.replace = REAL_REPLACE
        sheet._rmtree = REAL_RMTREE

    def committed(self, name="call-add"):
        v, h = vector_home(name)
        self.assertTrue(sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)["ok"])
        return v, h

    def late(self, v):
        return sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)

    def die_after_the_replace(self, v, event):
        def death(path):
            raise KeyboardInterrupt("killed after the replace")
        sheet._rmtree = death
        with self.assertRaises(KeyboardInterrupt):
            sheet.run_step(v["session"], json.dumps(event).encode(), now=v["now"], tz=UTC)
        sheet._rmtree = REAL_RMTREE

    def test_an_acknowledgement_killed_after_its_replace(self):
        v, h = self.committed()
        self.die_after_the_replace(v, ev("drain", acked=["toolu_v01"]))
        self.assertEqual(state_of(v["session"])["calls"], [])
        late = self.late(v)
        self.assertEqual(late.get("code"), "gone", late)
        self.assertEqual(len(state_of(v["session"])["questions"]), 3, "q2 and q3 once")

    def test_an_acknowledgement_killed_before_its_replace(self):
        v, h = self.committed()
        os.replace = lambda src, dst: (_ for _ in ()).throw(KeyboardInterrupt()) if dst.endswith("state.json") \
            else REAL_REPLACE(src, dst)
        with self.assertRaises(KeyboardInterrupt):
            sheet.run_step(v["session"], json.dumps(ev("drain", acked=["toolu_v01"])).encode(), now=v["now"], tz=UTC)
        os.replace = REAL_REPLACE
        late = self.late(v)
        self.assertEqual(late["effects"]["result"], "Added q2, q3.", "the recorded outcome answers it")
        self.assertEqual(len(state_of(v["session"])["questions"]), 3)
        self.assertTrue(step(ev("drain", acked=["toolu_v01"]), session=v["session"], now=v["now"])["ok"])
        self.assertEqual(self.late(v)["code"], "gone")

    def test_a_foreclosed_call_acknowledged_and_killed(self):
        v, h = vector_home("settle-forecloses")
        self.assertTrue(sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)["ok"])
        self.die_after_the_replace(v, ev("drain", acked=["toolu_s02"]))
        late = sheet.run_step(v["session"], json.dumps(ev("call", call={"callId": "toolu_s02"})).encode(),
                              now=v["now"], tz=UTC)
        self.assertEqual(late.get("code"), "gone", late)
        self.assertEqual(len(state_of(v["session"])["questions"]), 1)

    def test_a_start_that_forgets_the_calls_killed_after_its_replace(self):
        v, h = self.committed()
        self.die_after_the_replace(v, ev("start", start={"source": "resume"}))
        self.assertEqual(state_of(v["session"])["calls"], [])
        self.assertEqual(self.late(v).get("code"), "gone")
        self.assertEqual(len(state_of(v["session"])["questions"]), 3)


class AnImportWithTheFloorUnknown(unittest.TestCase):
    """M5's fix wave 3: a start whose conversation's ids are not known (the mod's floor search failed) sends its asks
    with `today.floorUnknown`; under the lock the step imports them only into a record that has assigned an id, whose
    next id is past every id the conversation holds; into one that has not, it imports nothing and records nothing,
    and the next start reads again. No published fixture's event carries the flag."""

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def start(self, nonce, asks, floor_unknown=True, floor=None):
        s = {"source": "resume", "nonce": nonce, "today": {"definite": True, "asks": asks}}
        if floor_unknown:
            s["today"]["floorUnknown"] = True
        if floor is not None:
            s["floor"] = floor
        return step(ev("start", start=s))

    def test_a_record_that_assigned_an_id_imports(self):
        scratch()
        self.assertTrue(step(ev("start", start={"source": "startup"}))["ok"])
        self.assertTrue(step(inline_call("toolu_a1", [{"question": "First?"}]))["ok"])
        b = self.start("n-known", [an_ask("toolu_old1", "Which port?")])
        self.assertTrue(b["ok"], b)
        st = state_of()
        self.assertEqual([q["id"] for q in st["questions"]], ["q1", "q2"])
        self.assertEqual(st["import"]["calls"], {"toolu_old1": ["q2"]})
        self.assertIn("Moved onto the sheet", b["effects"]["context"])

    def test_a_record_that_assigned_none_defers_and_records_nothing(self):
        scratch()
        b = self.start("n-1", [an_ask("toolu_old1", "Which port?")])
        self.assertTrue(b["ok"], b)
        st = state_of()
        self.assertEqual((st["questions"], st["import"]["calls"], st["nextId"]), ([], {}, 1))
        self.assertNotIn("Moved onto the sheet", b["effects"].get("context") or "")
        # The next start, its floor known, imports past it.
        b = self.start("n-2", [an_ask("toolu_old1", "Which port?")], floor_unknown=False, floor=26)
        self.assertTrue(b["ok"], b)
        self.assertEqual(state_of()["import"]["calls"], {"toolu_old1": ["q27"]})

    def test_the_flag_is_a_boolean(self):
        scratch()
        b = step(ev("start", start={"source": "resume", "today": {"definite": True, "asks": [], "floorUnknown": "yes"}}))
        self.assertFalse(b["ok"])
        self.assertEqual(b["code"], "bad-event")


class AStartOrderedAgain(unittest.TestCase):
    """Finding 2: a start ordered again answers what the first did."""

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")
        os.replace = REAL_REPLACE

    def twice(self, name):
        v, h = vector_home(name)
        first = sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)
        again = sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now="2026-11-24T10:00:03.000Z", tz=UTC)
        self.assertEqual((again["seq"], again["effects"]), (first["seq"], first["effects"]))
        return v, first

    def test_a_fork_a_lost_record_and_an_import(self):
        self.assertIn("This conversation is a copy", self.twice("start-fork")[1]["effects"]["context"])
        self.assertIn("record was not found", self.twice("start-lost")[1]["effects"]["context"])
        v, first = self.twice("start-import")
        self.assertIn("Moved onto the sheet", first["effects"]["context"])

    def test_an_import_whose_replace_failed_is_imported_by_the_retry(self):
        v, h = vector_home("start-import")
        os.replace = lambda src, dst: (_ for _ in ()).throw(OSError(5, "no")) if dst.endswith("state.json") \
            else REAL_REPLACE(src, dst)
        with self.assertRaises(OSError):
            sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)
        os.replace = REAL_REPLACE
        out = sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)
        self.assertEqual(out["effects"], v["answer"]["effects"])
        self.assertEqual([q["id"] for q in state_of(v["session"])["questions"]], ["q1", "q2", "q3"])

    def test_a_later_start_is_not_the_first_one_again(self):
        v, h = vector_home("start-lost")
        sheet.run_step(v["session"], json.dumps(v["event"]).encode(), now=v["now"], tz=UTC)
        later = json.loads(json.dumps(v["event"]))
        later["start"]["nonce"] = "0002"
        later = sheet.run_step(v["session"], json.dumps(later).encode(), now=v["now"], tz=UTC)
        self.assertEqual((later["effects"]["start"]["empty"], later["effects"]["context"]), (None, ""))

    def test_a_staged_ask_that_is_missing_is_no_evidence(self):
        v, h = vector_home("start-import")
        e = json.loads(json.dumps(v["event"]))
        e["start"]["today"]["asks"].append({"file": "start-0002/ask-9.json"})
        before = without_locks(tree(h))
        out = sheet.run_step(v["session"], json.dumps(e).encode(), now=v["now"], tz=UTC)
        self.assertEqual(out["code"], "bad-event")
        self.assertEqual(without_locks(tree(h)), before)


class BadRegistrations(unittest.TestCase):
    """Finding 3: a registration that cannot be read as alive is not alive, and masks no other."""

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_an_impossible_date_and_a_pid_past_the_platform(self):
        h = scratch()
        d = os.path.join(h, "sheet", "surfaces")
        os.makedirs(d)
        good = {"v": 1, "name": "mawsd", "pid": 1, "url": "http://ok.localhost", "reach": "local",
                "heartbeatAt": "2026-11-24T09:59:59.000Z"}
        for name, reg in (("a-date", dict(good, name="a-date", heartbeatAt="2026-02-30T09:59:59.000Z")),
                          ("b-pid", dict(good, name="b-pid", pid=2 ** 70)), ("mawsd", good)):
            with open(os.path.join(d, name + ".json"), "w") as f:
                json.dump(reg, f)
        self.assertEqual([(r["name"], r["alive"]) for r in sheet.surfaces(NOW)],
                         [("mawsd", True), ("a-date", False), ("b-pid", False)])
        out = step(ev("start", start={"source": "startup"}))
        self.assertEqual((out["view"]["surface"]["name"], out["view"]["surfaces"]), ("mawsd", 1))
        with open(os.path.join(d, "mawsd.json"), "w") as f:      # the probe runs on the machine's clock
            json.dump(dict(good, heartbeatAt=sheet._now_ms()), f)
        code, probe_out, err = run_cli(["sheet", "probe", "--session", SESSION])
        self.assertEqual((code, json.loads(probe_out)["surfaces"]), (0, 1), err)


class NoCalendarDate(unittest.TestCase):
    """Finding 4: a line's `at` that matches the pattern and is no calendar date is kept as the door took it, and no
    composer fails on it."""

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_february_the_thirtieth_through_put_then_a_start_and_a_drain(self):
        scratch()
        step(ev("start", start={"source": "startup"}))
        step(inline_call("toolu_d", [{"question": "Ship?", "options": opts("Yes", "No")}]))
        x = line("page-00000030", "answer", at="2026-02-30T10:00:00.000Z", id="q1", revision=1, picks=["Yes"])
        code, out, err = run_cli(["sheet", "put", "--session", SESSION, "--no-wait"],
                                 stdin=(json.dumps(x) + "\n").encode())
        self.assertEqual(code, 0, err)
        started = step(ev("start", start={"source": "resume"}), now="2026-11-24T11:00:00.000Z")
        self.assertTrue(started["ok"], started)
        self.assertIn("answered 2026-02-30T10:00:00.000Z, while this session was stopped",
                      started["view"]["ready"][0]["text"])
        self.assertTrue(step(ev("drain"), now="2026-11-24T11:00:01.000Z")["ok"])

    def test_a_composer_that_fails_commits_nothing(self):
        scratch()
        step(ev("start", start={"source": "startup"}))
        put_raw(SESSION, [line("page-00000031", "dismiss", id="q9")])
        before = state_of()
        real = step_module.view
        step_module.view = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("a composer failed"))
        try:
            with self.assertRaises(RuntimeError):
                step(ev("drain"))
        finally:
            step_module.view = real
        self.assertEqual(state_of(), before)


class TheImportsBudget(unittest.TestCase):
    """Finding 5: the import's summary is budgeted like the open list; `New ids` always ends the context."""

    def test_a_start_that_imports_one_hundred_and_eighty(self):
        asks = [{"callId": "toolu_i%02d" % c, "askedAt": "2026-11-23T08:00:00.000Z",
                 "questions": [{"question": ("Imported question %d.%d: " % (c, n) + "why " * 600)[:2000],
                                "header": "H", "options": [{"label": "L%d" % j} for j in range(4)],
                                "multiSelect": False} for n in range(4)]} for c in range(45)]
        st, fx, _ = step_module.apply(None, b"", {"event": "start", "start": {
            "source": "resume", "today": {"definite": True, "asks": asks}}}, NOW, SESSION)
        self.assertEqual(len(st["questions"]), 180)
        c = step_module.context(st, SESSION, "a resume", imported=[a["callId"] for a in asks])
        self.assertLessEqual(step_module.units(c), 60000)
        lines = c.splitlines()
        self.assertEqual(lines[-1], "New ids continue from q181.")
        self.assertTrue(lines[-2].startswith("Moved onto the sheet from the earlier question tool: q1 "))
        self.assertRegex(lines[-2], r", and \d+ more, q\d+ to q180: sminos sheet show --session %s prints them\.$"
                         % SESSION)
        self.assertLessEqual(step_module.units(lines[-2]), step_module.IMPORT_BUDGET)


class TheWholeAnswerIsBounded(unittest.TestCase):
    """Finding 6: start.before is the first 200 and a count; an event's keys are at most 200; the answer is measured
    as it is printed."""

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_a_start_after_a_large_backlog(self):
        h = scratch()
        st = built([{"question": "Q%d?" % i} for i in range(1, 501)])      # at most 500 open at once
        st, _, _ = drained(st, answers(range(1, 501), lambda i: "yes"))
        call = {"callId": "toolu_b2", "asker": "main", "withdraw": [],
                "entries": [{"entry": {"question": "Q%d?" % i}, "captures": []} for i in range(501, 1001)]}
        st, _, _ = step_module.apply(st, b"", {"event": "call", "call": call}, NOW, SESSION, SURF)
        st, _, _ = drained(st, answers(range(501, 1001), lambda i: "yes"))
        self.assertEqual(len(st["pending"]), 1000)
        d = os.path.join(h, "sheet", SESSION)
        os.makedirs(d)
        with open(os.path.join(d, "state.json"), "w") as f:
            json.dump(st, f)
        open(os.path.join(d, "inbox.jsonl"), "w").close()
        code, out, err = run_cli(["sheet", "step", "--session", SESSION],
                                 stdin=json.dumps(ev("start", start={"source": "resume"})).encode())
        o = json.loads(out)
        self.assertEqual((len(o["effects"]["start"]["before"]), o["effects"]["start"]["beforeCount"]), (200, 1000))
        self.assertEqual(out.strip(), json.dumps(o, ensure_ascii=False, separators=(",", ":")), "printed as measured")

    def test_more_than_two_hundred_keys_is_a_bad_event(self):
        scratch()
        step(ev("start", start={"source": "startup"}))
        out = step(ev("drain", keys=["page-%08d" % i for i in range(201)]))
        self.assertEqual(out["code"], "bad-event")

    def test_every_part_of_the_view_is_cut_until_it_fits(self):
        big = {"ok": True, "seq": 1, "effects": {"applied": []}, "view": {
            "ready": [], "closed": {}, "answered": [],
            "open": [{"id": "q%d" % i, "question": FOUR * 300, "header": FOUR * 60} for i in range(1, 3001)]}}
        b = sheet._bounded(big)
        self.assertLessEqual(len(sheet._dumps(b).encode()), sheet.ANSWER_MAX)
        self.assertEqual(b["view"]["open"][0]["id"], "q1", "the newest go first")


class RemoveUnderTheLock(unittest.TestCase):
    """Finding 7: liveness again under the lock; a deletion that fails is said."""

    def setUp(self):
        self.home = scratch()
        step(ev("start", start={"source": "startup"}))

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")
        shutil.rmtree = REAL_SHUTIL_RMTREE
        sminos.__dict__.pop("session_running", None)

    def test_a_session_that_started_while_remove_waited(self):
        answers_ = iter([None, {"sessionId": SESSION, "pid": 1}])
        sminos.session_running = lambda s: next(answers_)
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()) as err:
            sheet.remove(SESSION)
        self.assertEqual(e.exception.code, 2)
        self.assertIn("started while this waited", err.getvalue())
        self.assertTrue(os.path.isfile(os.path.join(self.home, "sheet", SESSION, "state.json")))

    def test_a_deletion_that_fails_is_said(self):
        def failing(path, *a, **k):
            raise OSError(13, "permission denied")
        shutil.rmtree = failing
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()) as err:
            sheet.remove(SESSION, cleared=True)
        shutil.rmtree = REAL_SHUTIL_RMTREE
        self.assertEqual(e.exception.code, 1)
        self.assertIn("could not be deleted", err.getvalue())
        self.assertIn(".removed-", err.getvalue())
        self.assertIsNone(sheet.model(SESSION), "the record is detached all the same")


class ClosingOrder(unittest.TestCase):
    """Finding 8: ties in closing time are broken by the order questions closed, not by their ids."""

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_a_batch_in_reverse_id_order(self):
        scratch()
        step(ev("start", start={"source": "startup"}))
        ask_all("toolu_r", [{"question": "Q%d?" % i} for i in range(1, 42)])
        put_raw(SESSION, answers(range(40, 0, -1), lambda i: "a%d" % i, batch="page-b00000rv"))
        out = step(ev("drain"))
        kept = [i for i, c in state_of()["closed"].items() if "answer" in c]
        self.assertEqual(sorted(kept, key=lambda i: int(i[1:])), ["q%d" % i for i in range(1, 33)])
        self.assertEqual([a["id"] for a in out["view"]["answered"]], ["q%d" % i for i in range(32, 0, -1)])
        put_raw(SESSION, answers([41], lambda i: "later"))
        out = step(ev("drain"), now="2026-11-24T10:00:01.000Z")
        self.assertNotIn("answer", state_of()["closed"]["q32"], "q32 closed first among the 32 kept")
        self.assertIn("answer", state_of()["closed"]["q1"])
        self.assertEqual(out["view"]["answered"][0]["id"], "q31")


class PicksAreAsciiDigits(unittest.TestCase):
    """Finding 9."""

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_a_label_that_is_a_superscript_digit(self):
        scratch()
        step(ev("start", start={"source": "startup"}))
        step(inline_call("toolu_s", [{"question": "Which power?", "options": opts("x", "²")}]))
        code, out, err = run_cli(["sheet", "answer", "--session", SESSION, "q1", "--pick", "²"])
        self.assertEqual(code, 0, err)
        step(ev("drain"))
        self.assertEqual(state_of()["pending"][0]["picks"], ["²"])


class APickIsMatchedExactlyFirst(unittest.TestCase):
    """S3: a label is matched as written before any whitespace is forgiven."""

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_labels_that_differ_only_by_surrounding_whitespace(self):
        scratch()
        step(ev("start", start={"source": "startup"}))
        self.assertTrue(step(inline_call("toolu_w", [{"question": "Which?", "options": opts("Yes", " Yes ")},
                                                     {"question": "Lone?", "options": opts(" Lone ", "Other")}]))["ok"])
        for handle, pick, want in (("q1", " Yes ", [" Yes "]), ("q1", "Yes", ["Yes"]), ("q2", " Lone ", [" Lone "]),
                                   ("q2", "lone", [" Lone "]), ("q2", "  other", ["Other"])):
            with self.subTest(pick=pick):
                code, out, err = run_cli(["sheet", "answer", "--session", SESSION, handle, "--pick", pick])
                self.assertEqual(code, 0, err)
                key = json.loads(out)["results"][0]["key"]
                with open(os.path.join(os.environ["SMINOS_HOME"], "sheet", SESSION, "inbox.jsonl"),
                          encoding="utf-8") as f:
                    lines = [json.loads(x) for x in f if x.strip()]
                self.assertEqual(next(x for x in lines if x["key"] == key)["picks"], want)
        code, _, err = run_cli(["sheet", "answer", "--session", SESSION, "q1", "--pick", "  Yes"])
        self.assertEqual(code, 2, "two labels forgive to it: neither is chosen")
        self.assertIn("has no option", err)


class ShowsPlainPrint(unittest.TestCase):
    """show without --json prints what a model and a person wrote to a terminal: C0 and C1 controls (ESC among
    them) taken out, a line break a space, as the surfaces listing does (S1); --json and the record as written."""

    EVIL = "a\x1b[31mred\x1b[0m \x1b]8;;http://x\x07link\x1b]8;;\x07\rback\nnext\u0085nel\u2028sep\x9bcsi"

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_a_questions_own_lines_stay_and_cannot_pose_as_another_question(self):
        scratch()
        step(ev("start", start={"source": "startup"}))
        self.assertTrue(step(inline_call("toolu_f", [{"question": "Which one?\nq9  Forged header\r\n  1. Forged",
                                                      "options": opts("Real")}]))["ok"])
        code, out, err = run_cli(["sheet", "show", "--session", SESSION])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.rstrip("\n").split("\n"),
                         ["q1", "  Which one?", "    q9  Forged header", "      1. Forged", "  1. Real"])

    def test_a_queued_answers_text_is_cleaned_before_it_is_quoted(self):
        scratch()
        step(ev("start", start={"source": "startup"}))
        step(inline_call("toolu_t", [{"question": "Say?"}]))
        put_raw(SESSION, [line("page-0000t001", "answer", id="q1", revision=1, text='one\ntwo\rthree\u2028four "q"')])
        code, out, err = run_cli(["sheet", "show", "--session", SESSION])
        self.assertEqual(code, 0, err)
        self.assertIn('  queued (page-0000t001): "one two three four \\"q\\""', out.split("\n"))

    def test_the_model_and_the_person_cannot_forge_a_line_or_drive_the_terminal(self):
        scratch()
        step(ev("start", start={"source": "startup"}))
        e = self.EVIL
        self.assertTrue(step(inline_call("toolu_p", [{"question": "Q " + e, "header": "H\x1b[2J" + "\n", "options":
                                                      opts("L " + e, "Plain")}],
                                         asker={"agentId": "ag\x1b[1m1", "name": "N " + e}))["ok"])
        put_raw(SESSION, [line("page-0000p001", "answer", id="q1", revision=1, picks=["L " + e], text="T " + e)])
        code, out, err = run_cli(["sheet", "show", "--session", SESSION])
        self.assertEqual(code, 0, err)
        lines = out.rstrip("\n").split("\n")
        self.assertFalse([c for c in out.rstrip("\n") if c != "\n" and (ord(c) < 0x20 or 0x7f <= ord(c) <= 0x9f
                                                                       or c in "\u2028\u2029")], repr(out))
        clean = "a[31mred[0m ]8;;http://xlink]8;; back next nel sepcsi"
        self.assertEqual(lines[0], "q1  asked by the subagent N %s (ag[1m1)  H[2J " % clean)
        # The question keeps its own line breaks (LF), a CR dropped, each line after the first indented under it.
        self.assertEqual(lines[1:3], ["  Q a[31mred[0m ]8;;http://xlink]8;;back", "    next nel sepcsi"])
        self.assertEqual(lines[3], "  1. L " + clean)
        self.assertEqual(lines[4], "  2. Plain")
        self.assertTrue(lines[5].startswith("  queued (page-0000p001): L " + clean), lines[5])
        self.assertEqual(len(lines), 6, out)
        code, out, _ = run_cli(["sheet", "show", "--session", SESSION, "--json"])
        q = json.loads(out)["open"][0]
        self.assertEqual((q["question"], q["options"][0]["label"], q["asker"]["name"]), ("Q " + e, "L " + e, "N " + e))
        self.assertEqual(state_of()["questions"][0]["question"], "Q " + e)


class AnAnswersImagesGoWithItOrNotAtAll(unittest.TestCase):
    """S4: an answer's images are copied only once the whole request is checked, and taken back when the door
    appends nothing."""

    def setUp(self):
        self.home = scratch()
        step(ev("start", start={"source": "startup"}))
        step(inline_call("toolu_i", [{"question": "Sketch?"}]))
        self.uploads = os.path.join(self.home, "sheet", SESSION, "uploads")
        self.img = os.path.join(BASE, "shot-s4.png")
        with open(self.img, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def uploaded(self):
        return sorted(os.listdir(self.uploads)) if os.path.isdir(self.uploads) else []

    def test_a_later_image_that_is_not_there_copies_none(self):
        code, _, err = run_cli(["sheet", "answer", "--session", SESSION, "q1", "--text", "see", "--image", self.img,
                                "--image", os.path.join(BASE, "missing.png")])
        self.assertEqual(code, 2, err)
        self.assertEqual(self.uploaded(), [])

    def answer_here(self, *images):
        argv = ["sheet", "answer", "--session", SESSION, "q1", "--text", "see"]
        for img in images:
            argv += ["--image", img]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                sminos.main(argv)
            except SystemExit as e:
                return e.code
        return 0

    def test_a_copy_that_fails_midway_leaves_no_upload_and_no_temporary_file(self):
        real, calls = shutil.copyfile, []

        def full_disk(src, dst, *a, **k):
            calls.append(dst)
            if len(calls) == 2:
                with open(dst, "wb") as f:
                    f.write(b"\x89PN")          # part of it written, then the disk is full
                raise OSError(errno.ENOSPC, "no space left on device")
            return real(src, dst, *a, **k)
        with mock.patch.object(shutil, "copyfile", side_effect=full_disk):
            with self.assertRaises(OSError), contextlib.redirect_stdout(io.StringIO()):
                sminos.main(["sheet", "answer", "--session", SESSION, "q1", "--text", "see", "--image", self.img,
                             "--image", self.img])
        self.assertEqual(self.uploaded(), [], "no upload, and no temporary file")
        self.assertEqual(state_of()["inbox"]["offset"], os.path.getsize(os.path.join(self.home, "sheet", SESSION,
                                                                                     "inbox.jsonl")))

    def test_an_answer_the_door_appended_keeps_its_images_whatever_fails_after(self):
        with mock.patch.object(sheet, "nudge", side_effect=OSError(errno.EPIPE, "broken pipe")):
            with self.assertRaises(OSError), contextlib.redirect_stdout(io.StringIO()):
                sminos.main(["sheet", "answer", "--session", SESSION, "q1", "--text", "see", "--image", self.img])
        self.assertEqual(len(self.uploaded()), 1, "the line is in the inbox, naming it")
        self.assertEqual(len(sheet.model(SESSION)["open"][0]["queued"]["images"]), 1)

    def test_a_line_the_door_refuses_takes_its_images_back(self):
        def refused(session, lines):
            sminos.die("sheet put: line 1 refused: the question closed meanwhile; nothing appended", 2)
        with mock.patch.object(sheet, "append", side_effect=refused):
            self.assertEqual(self.answer_here(self.img, self.img), 2)
        self.assertEqual(self.uploaded(), [])
        def busy(session, lines):
            sminos.die("sheet put: busy; send again", sheet.EXIT_BUSY)
        with mock.patch.object(sheet, "append", side_effect=busy):
            self.assertEqual(self.answer_here(self.img), sheet.EXIT_BUSY)
        self.assertEqual(self.uploaded(), [])
        self.assertEqual(self.answer_here(self.img), 0)
        self.assertEqual(len(self.uploaded()), 1, "an answer the door took keeps its image")


class QueuedEntriesByKind(unittest.TestCase):
    """Finding 11 (M1's reader): a queued `sent` entry shows only its own kind's fields."""

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_a_field_of_another_kind_is_not_shown(self):
        import sheet_schema
        scratch()
        step(ev("start", start={"source": "startup"}))
        step(inline_call("toolu_k", [{"question": "Ship?", "options": opts("Yes", "No")}, {"question": "Why?"}]))
        lines = [line("page-0000000a", "answer", id="q1", revision=1, picks=["Yes"], target="page-0000000z"),
                 line("page-0000000b", "dismiss", id="q2", target="page-0000000z"),
                 line("page-0000000c", "retract", target="page-0000000z", id="q1"),
                 line("page-0000000d", "delivered", keys=["page-0000000z"], id="q1", target="page-0000000z")]
        code, _, err = run_cli(["sheet", "put", "--session", SESSION, "--no-wait"],
                               stdin="".join(json.dumps(x) + "\n" for x in lines).encode())
        self.assertEqual(code, 0, err)
        code, out, err = run_cli(["sheet", "show", "--session", SESSION, "--json"])
        m = json.loads(out)
        self.assertEqual({x["key"]: sorted(x) for x in m["sent"]}, {
            "page-0000000a": ["id", "key", "kind", "state"], "page-0000000b": ["id", "key", "kind", "state"],
            "page-0000000c": ["key", "kind", "state", "target"], "page-0000000d": ["key", "kind", "state"]})
        self.assertEqual(sheet_schema.errors(load(os.path.join(SET, "schema", "show.schema.json")), m), [])



# ------------------------------------------------------------------ fix wave 2


def stage_ask(nonce, n, ask, session=SESSION):
    d = os.path.join(os.environ["SMINOS_HOME"], "sheet", ".staging", session, "start-" + nonce)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "ask-%d.json" % n), "w") as f:
        json.dump(ask, f)
    return {"file": "start-%s/ask-%d.json" % (nonce, n)}


def an_ask(call_id, question):
    return {"callId": call_id, "askedAt": "2026-11-24T09:00:00.000Z",
            "questions": [{"question": question, "options": [], "multiSelect": False}]}


def a_start(nonce=None, source="resume", floor=None, asks=None):
    s = {"source": source, "today": {"definite": asks is not None, "asks": asks or []}}
    if floor is not None:
        s["floor"] = floor
    if nonce is not None:
        s["nonce"] = nonce
    return ev("start", start=s)


class AStartIsKnownByItsNonce(unittest.TestCase):
    """Fix wave 2: a retry is the start whose nonce is the receipt's; every other start is new, and `before` is
    always what is pending ahead of this step's drain."""

    def setUp(self):
        scratch()
        step(a_start("s0", source="startup", floor=1))
        self.assertTrue(step(inline_call("toolu_n1", [{"question": "Ship?"}]))["ok"])
        put_raw(SESSION, [line("page-0000n001", "answer", id="q2", revision=1, text="yes")])

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def test_starts_at_one_floor_each_name_what_is_pending(self):
        first = step(a_start("r1", floor=1))
        self.assertEqual((first["effects"]["start"]["before"], first["effects"]["applied"]), ([], ["page-0000n001"]))
        second = step(a_start("r2", floor=1))
        self.assertEqual(second["effects"]["start"]["before"], ["page-0000n001"])
        self.assertEqual(second["effects"]["start"]["beforeCount"], 1)

    def test_a_retry_lists_what_its_first_attempt_applied(self):
        e = a_start("r1", floor=1)
        step(e)
        self.assertEqual(step(e)["effects"]["start"]["before"], ["page-0000n001"], "a harmless superset")

    def test_a_second_definite_import_reports_its_own(self):
        a = stage_ask("r1", 1, an_ask("toolu_A", "Gate?"))
        one = step(a_start("r1", floor=1, asks=[a]))
        self.assertEqual(one["effects"]["start"]["imported"], [{"callId": "toolu_A", "ids": ["q3"]}])
        a2, b2 = stage_ask("r2", 1, an_ask("toolu_A", "Gate?")), stage_ask("r2", 2, an_ask("toolu_B", "Layout?"))
        two = step(a_start("r2", floor=1, asks=[a2, b2]))
        self.assertEqual(two["effects"]["start"]["imported"], [{"callId": "toolu_B", "ids": ["q4"]}])
        self.assertIn('q4 "Layout?"', two["effects"]["context"])
        self.assertNotIn('q3 "Gate?" (call', two["effects"]["context"])

    def test_the_same_nonce_twice_answers_the_same(self):
        e = a_start("r1", floor=1, asks=[stage_ask("r1", 1, an_ask("toolu_A", "Gate?"))])
        one = step(e)
        step(ev("drain"))                                 # a step between: the nonce still names the same start
        two = step(e)
        pick = lambda o: (o["effects"]["start"]["empty"], o["effects"]["start"]["imported"], o["effects"]["context"])
        self.assertEqual(pick(two), pick(one))
        self.assertEqual(one["effects"]["start"]["imported"], [{"callId": "toolu_A", "ids": ["q3"]}])

    def test_a_start_with_no_nonce_is_new(self):
        scratch()
        one = step(a_start(source="fork", floor=3))
        two = step(a_start(source="fork", floor=3))
        self.assertEqual((one["effects"]["start"]["empty"], two["effects"]["start"]["empty"]), ("fork", None))
        self.assertFalse(os.path.exists(os.path.join(sheet.staging_dir(SESSION), sheet.RECEIPT)))

    def test_a_nonce_is_a_name(self):
        self.assertEqual(step(a_start("../x", floor=1))["code"], "bad-event")


class TheImportsBudgetByLessThanAnItem(unittest.TestCase):
    """Fix wave 2: a summary over its budget by less than its last item stops before it."""

    def test_twenty_three_questions_of_two_hundred(self):
        qs = [{"id": "q%d" % i, "question": "x" * 200, "importedFrom": {"callId": "toolu_%03d" % i, "index": 0}}
              for i in range(1, 24)]
        old = step_module.IMPORT_BUDGET
        try:
            step_module.IMPORT_BUDGET = 10 ** 9
            whole = step_module.units(step_module.moved(qs, SESSION))
            step_module.IMPORT_BUDGET = whole - 5           # over by less than the last item
            s = step_module.moved(qs, SESSION)
        finally:
            step_module.IMPORT_BUDGET = old
        self.assertRegex(s, r", and \d+ more, q\d+(?: to q23)?: sminos sheet show --session %s prints them\.$"
                         % SESSION)
        self.assertLessEqual(step_module.units(s), whole - 5)


class TheResultIsBoundedAtItsSource(unittest.TestCase):
    """Fix wave 2: every clause's free text is cut, so a call's result has a hard maximum."""

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def worst(self):
        scratch()
        step(a_start("s0", source="startup"))
        big = "p" * 100000
        entries = [{"entry": {"question": "Q?", "references": [{"path": big}]},
                    "captures": [{"ok": False, "reason": "r" * 1000000}]} for _ in range(10)]
        entries += [{"refused": "the mod's clause " + "m" * 1000000} for _ in range(10)]
        asker = {"agentId": "a" * 128, "name": "n" * 100000}
        return inline_call("toolu_w1", entries, withdraw=["q%d" % i for i in range(1, 501)], asker=asker)

    def test_the_worst_call_has_a_small_answer(self):
        out = step(self.worst())
        r = out["effects"]["result"]
        self.assertLessEqual(len(r), step_module.RESULT_MAX)
        self.assertLessEqual(len(sheet._dumps(out).encode()), 64 * 1024)
        self.assertIn("p" * 200 + "…", r)
        self.assertNotIn("p" * 201, r)
        self.assertIn("r" * 500 + "…", r)
        self.assertNotIn("m" * 501, r)
        self.assertEqual(state_of()["calls"][0]["result"], r, "settle repeats the bounded text")

    def test_more_than_twenty_entries_is_a_bad_event(self):
        scratch()
        step(a_start("s0", source="startup"))
        out = step(inline_call("toolu_w2", [{"question": "Q%d?" % i} for i in range(21)]))
        self.assertEqual(out["code"], "bad-event")

    def test_withdrawals_past_any_open_question_are_counted_not_listed(self):
        scratch()
        step(a_start("s0", source="startup"))
        out = step(inline_call("toolu_w3", withdraw=["q%d" % i for i in range(1, 100001)]))
        r = out["effects"]["result"]
        self.assertLessEqual(len(r), step_module.RESULT_MAX)
        not_done = next(x for x in r.splitlines() if x.startswith("Not done: "))
        self.assertRegex(not_done, r"\. And \d+ more withdrawals not done\.$")

    def test_an_empty_view_leaves_the_answer_under_its_bound(self):
        out = step(self.worst())
        out["view"] = {"ready": [], "closed": {}, "open": [], "answered": []}
        self.assertLessEqual(len(sheet._dumps(sheet._bounded(out)).encode()), sheet.ANSWER_MAX)


class ADamagedRecord(unittest.TestCase):
    """What an unclean stop can leave in a record, read so that nothing is applied twice or lost (R4, R6, R7)."""

    def setUp(self):
        self.home = scratch()
        self.rec = os.path.join(self.home, "sheet", SESSION)
        self.inbox = os.path.join(self.rec, "inbox.jsonl")

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")

    def door(self, *lines):
        data = "".join(json.dumps(x) + "\n" for x in lines).encode()
        return [r["state"] for r in sheet.put(SESSION, data, wait=False)["results"]]

    def test_an_inbox_cut_below_the_committed_offset_takes_its_next_answer_once(self):
        """R4: state.json synced, the inbox's last appends lost (a power loss): everything below the offset was
        applied, so the offset is held to the inbox's size, by the step and by the door alike."""
        for order in ("put first", "step first"):
            with self.subTest(order=order):
                self.home = scratch()
                self.rec = os.path.join(self.home, "sheet", SESSION)
                self.inbox = os.path.join(self.rec, "inbox.jsonl")
                step(ev("start", start={"source": "startup"}))
                step(inline_call("toolu_d1", [{"question": "One?", "options": opts("Yes", "No")},
                                              {"question": "Two?", "options": opts("Yes", "No")}]))
                self.door(line("page-0000d001", "answer", id="q1", revision=1, picks=["Yes"]))
                step(ev("drain"))
                offset = state_of()["inbox"]["offset"]
                self.assertEqual(offset, os.path.getsize(self.inbox))
                with open(self.inbox, "r+b") as f:
                    f.truncate(offset - 9)           # the last line's end lost
                cut = offset - 9
                if order == "step first":
                    # (b) A step before any put: the offset is held to the inbox's size, and committed.
                    out = step(ev("drain"))
                    self.assertEqual((out["effects"]["applied"], out["effects"]["skipped"]), ([], 0))
                    self.assertEqual(state_of()["inbox"]["offset"], cut)
                self.assertEqual(self.door(line("page-0000d002", "answer", id="q2", revision=1, picks=["No"])),
                                 ["queued"])
                with open(self.inbox, "rb") as f:
                    data = f.read()
                if order == "put first":
                    # (a) The door's padding: blank lines up to the offset, the call from it.
                    self.assertEqual(data[cut:offset], b"\n" * (offset - cut))
                    self.assertTrue(data[offset:].startswith(b'{"v":1,"key":"page-0000d002"'), data[offset:])
                self.assertEqual([q["queued"]["key"] for q in sheet.model(SESSION)["open"] if q.get("queued")],
                                 ["page-0000d002"], "show lists what the step will read")
                out = step(ev("drain"))
                self.assertEqual(out["effects"]["applied"], ["page-0000d002"])
                self.assertEqual(out["effects"]["skipped"], 0, "nothing below the offset, padding or fragment, read")
                self.assertEqual(state_of()["inbox"]["offset"], os.path.getsize(self.inbox))
                self.assertEqual(out["effects"]["verdicts"].get("page-0000d002", {}).get("verdict", "applied"),
                                 "applied")
                self.assertEqual(step(ev("drain"))["effects"]["applied"], [], "once")
                self.assertEqual(sorted(o["id"] for o in state_of()["pending"]), ["q1", "q2"])

    def test_a_new_record_beside_an_inbox_a_record_left_starts_at_its_end(self):
        """R7: the door never appends without a state, so an inbox with no state.json beside it is what a record
        left; a start that makes a state there replays none of it into the new record."""
        os.makedirs(self.rec)
        with open(self.inbox, "wb") as f:
            f.write((json.dumps(line("page-0000d003", "answer", id="q1", revision=1, text="the old answer"))
                     + "\n").encode())
        size = os.path.getsize(self.inbox)
        out = step(a_start("s1", source="startup", floor=0, asks=[stage_ask("s1", 1, an_ask("toolu_A", "Gate?"))]))
        self.assertTrue(out["ok"], out)
        self.assertEqual(state_of()["inbox"]["offset"], size)
        self.assertEqual([q["id"] for q in state_of()["questions"]], ["q1"])
        out = step(ev("drain"))
        self.assertEqual((out["effects"]["applied"], out["effects"]["skipped"]), ([], 0))
        self.assertEqual([q["id"] for q in state_of()["questions"]], ["q1"], "the new q1 stays open")

    def test_a_body_whose_file_an_unclean_stop_damaged_is_written_again(self):
        """R6: a reused text or reference file is the bytes its name states, not merely as long."""
        step(ev("start", start={"source": "startup"}))
        step(inline_call("toolu_d2", [{"question": "First?"}, {"question": "Second?"}]))
        text = "x" * 2500
        self.door(line("page-0000d004", "answer", id="q1", revision=1, text=text))
        step(ev("drain"))
        rel = state_of()["pending"][0]["textFile"]
        path = os.path.join(self.rec, rel)
        with open(path, "wb") as f:
            f.write(b"\0" * len(text))               # as long, and not the text
        self.door(line("page-0000d005", "answer", id="q2", revision=1, text=text))
        step(ev("drain"))
        self.assertEqual(state_of()["pending"][1]["textFile"], rel)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), text.encode())


class RemoveDetachesTheStagingFirst(unittest.TestCase):
    """Fix wave 2: a rename that fails leaves the sheet whole; what a removal left is deleted by the next one."""

    def setUp(self):
        self.home = scratch()
        step(a_start("s0", source="startup"))
        os.makedirs(os.path.join(sheet.staging_dir(SESSION), "toolu_x"))

    def tearDown(self):
        os.environ["SMINOS_HOME"] = os.path.join(BASE, "s")
        os.rename = REAL_RENAME

    def failing_for(self, path):
        def rename(src, dst):
            if os.path.abspath(src) == os.path.abspath(path):
                raise OSError(1, "operation not permitted")
            return REAL_RENAME(src, dst)
        os.rename = rename

    def leftovers(self):
        return [n for n in os.listdir(os.path.join(self.home, "sheet")) if n.startswith(".removed-")]

    def test_a_staging_that_cannot_be_detached(self):
        self.failing_for(sheet.staging_dir(SESSION))
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()):
            sheet.remove(SESSION, cleared=True)
        self.assertEqual(e.exception.code, 1)
        self.assertIsNotNone(sheet.model(SESSION), "the record stays")
        self.assertTrue(os.path.isdir(os.path.join(sheet.staging_dir(SESSION), "toolu_x")))
        self.assertEqual(self.leftovers(), [])

    def test_a_record_that_cannot_be_detached(self):
        self.failing_for(sheet.record_dir(SESSION))
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()):
            sheet.remove(SESSION, cleared=True)
        self.assertEqual(e.exception.code, 1)
        self.assertIsNotNone(sheet.model(SESSION))
        self.assertTrue(os.path.isdir(os.path.join(sheet.staging_dir(SESSION), "toolu_x")), "the staging is back")
        self.assertEqual(self.leftovers(), [])

    def test_a_record_directory_that_is_a_link_is_refused_with_every_path_left(self):
        rec = sheet.record_dir(SESSION)
        other = tempfile.mkdtemp(prefix="other-record.")
        self.addCleanup(shutil.rmtree, other, True)
        moved = os.path.join(other, "record")
        shutil.move(rec, moved)
        os.symlink(moved, rec)
        held = sorted(os.listdir(moved))
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()) as err:
            sheet.remove(SESSION, cleared=True)
        self.assertEqual(e.exception.code, 1)
        self.assertIn("is not a directory; nothing removed", err.getvalue())
        self.assertTrue(os.path.islink(rec))
        self.assertEqual(sorted(os.listdir(moved)), held)
        self.assertTrue(os.path.isdir(os.path.join(sheet.staging_dir(SESSION), "toolu_x")), "the staging stays")
        self.assertEqual(self.leftovers(), [])

    def test_a_record_holding_a_link_is_removed_and_what_the_link_names_is_not(self):
        outside = tempfile.mkdtemp(prefix="outside.")
        self.addCleanup(shutil.rmtree, outside, True)
        target = os.path.join(outside, "elsewhere.jsonl")
        with open(target, "wb") as f:
            f.write(b"not the record's\n")
        os.makedirs(os.path.join(outside, "refs"))
        with open(os.path.join(outside, "refs", "kept"), "wb") as f:
            f.write(b"kept")
        rec = sheet.record_dir(SESSION)
        os.unlink(os.path.join(rec, "inbox.jsonl"))
        os.symlink(target, os.path.join(rec, "inbox.jsonl"))
        os.symlink(os.path.join(outside, "refs"), os.path.join(rec, "refs"))
        sheet.remove(SESSION, cleared=True)
        self.assertFalse(os.path.lexists(rec))
        with open(target, "rb") as f:
            self.assertEqual(f.read(), b"not the record's\n")
        self.assertEqual(os.listdir(os.path.join(outside, "refs")), ["kept"])

    def test_the_next_remove_deletes_what_an_earlier_one_left(self):
        root = os.path.join(self.home, "sheet")
        old = os.path.join(root, ".removed-%d-%s" % (int(datetime.datetime.now().timestamp()) - 120, "a" * 32))
        fresh = os.path.join(root, ".removed-%d-%s" % (int(datetime.datetime.now().timestamp()), "b" * 32))
        os.makedirs(os.path.join(old, "texts"))
        os.makedirs(fresh)
        sheet.remove(SESSION, cleared=True)
        self.assertEqual(self.leftovers(), [os.path.basename(fresh)], "one in progress elsewhere is left to it")

if __name__ == "__main__":
    try:
        r = unittest.main(exit=False, verbosity=1).result
    finally:
        shutil.rmtree(BASE, ignore_errors=True)
    ok = r.wasSuccessful()
    print("test_sheet_step: %d %s" % (r.testsRun, "passed" if ok else "run, %d failed" % (len(r.failures) + len(r.errors))))
    sys.exit(0 if ok else 1)
