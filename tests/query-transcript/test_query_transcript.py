#!/usr/bin/env python3
"""query-transcript against a stand-in `claude` (fake_claude.py): no model calls.

Each test gets its own HOME and CLAUDE_CONFIG_DIR, a fixture session under
projects/, and the CLI run through its launcher in bin/."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
LAUNCHER = ROOT / "bin" / "query-transcript"
sys.path.insert(0, str(ROOT / "skills" / "query-transcript" / "scripts"))
import query_transcript as qt  # noqa: E402

SID = "11111111-2222-4333-8444-555555555555"
OTHER = "11119999-2222-4333-8444-555555555555"


def user(uuid, ts, text, **kw):
    return {"parentUuid": None, "isSidechain": False, "type": "user", "message": {"role": "user", "content": text},
            "uuid": uuid, "timestamp": ts, "sessionId": SID, **kw}


def assistant(uuid, ts, text, usage=None):
    msg = {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "SIGNATURE-TEXT"},
                                            {"type": "text", "text": text}]}
    if usage:
        msg["usage"] = usage
    return {"parentUuid": None, "isSidechain": False, "type": "assistant", "message": msg, "uuid": uuid,
            "timestamp": ts, "sessionId": SID}


def tool_result(uuid, ts, text):
    return user(uuid, ts, [{"type": "tool_result", "tool_use_id": "toolu_1", "content": text}])


def boundary(uuid, ts, pre):
    return {"parentUuid": None, "isSidechain": False, "type": "system", "subtype": "compact_boundary",
            "content": "Conversation compacted", "uuid": uuid, "timestamp": ts, "sessionId": SID,
            "compactMetadata": {"trigger": "auto", "preTokens": pre}}


def rows():
    """Three segments: two compactions; a partial last line."""
    return [
        {"type": "mode", "mode": "normal", "sessionId": SID},
        user("aaaa0001-0000-4000-8000-000000000001", "2026-11-01T10:00:00.100Z",
             "Please fix the build. It fails on   the token step.", origin={"kind": "human"}),
        assistant("aaaa0002-0000-4000-8000-000000000002", "2026-11-01T10:00:05.000Z",
                  "I will look at the **CI config** first, then `ci.yml`.",
                  {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 99,
                   "output_tokens": 1}),
        tool_result("aaaa0003-0000-4000-8000-000000000003", "2026-11-01T10:00:10.000Z",
                    "exit 1: missing token GH_TOKEN"),
        {"type": "api-request", "sessionId": SID, "timestamp": "2026-11-01T10:00:11.000Z",
         "params": {"messages": [{"content": "ONLY-IN-THE-REQUEST-LOG"}]}},
        {"parentUuid": None, "isSidechain": False, "type": "attachment", "uuid": "aaaa0004-0000-4000-8000-000000000004",
         "timestamp": "2026-11-01T10:00:20.000Z", "sessionId": SID,
         "attachment": {"type": "queued_command", "prompt": "<task-notification><task-id>abc123</task-id>"
                        "</task-notification>", "origin": {"kind": "task-notification"}}},
        boundary("bbbb0001-0000-4000-8000-000000000001", "2026-11-01T10:05:00.000Z", 1234),
        user("bbbb0002-0000-4000-8000-000000000002", "2026-11-01T10:05:01.000Z",
             "Summary: the build was fixed by adding the token.", isCompactSummary=True),
        assistant("bbbb0003-0000-4000-8000-000000000003", "2026-11-01T10:06:00.000Z",
                  "Next I will open the pull request. @@seg1"),
        user("bbbb0004-0000-4000-8000-000000000004", "2026-11-01T10:07:00.000Z", "ship it",
             origin={"kind": "human"}),
        boundary("cccc0001-0000-4000-8000-000000000001", "2026-11-01T11:00:00.000Z", 5678),
        user("cccc0002-0000-4000-8000-000000000002", "2026-11-01T11:00:01.000Z", "Summary: shipped.",
             isCompactSummary=True),
        assistant("cccc0003-0000-4000-8000-000000000003", "2026-11-01T11:01:00.000Z", "Merged.",
                  {"input_tokens": 10, "cache_creation_input_tokens": 20, "cache_read_input_tokens": 300,
                   "output_tokens": 5}),
        {"type": "system", "subtype": "turn_duration", "uuid": "cccc0004-0000-4000-8000-000000000004",
         "timestamp": "2026-11-01T11:02:00.000Z", "sessionId": SID, "isSidechain": False},
    ]


def dump(rs):
    return "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rs)


PARTIAL = '{"type":"user","timestamp":"2026-11-01T11:03:00.000Z","message":{"content":"@@partial'


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qt-"))
        self.home = self.tmp / "home"
        self.config = self.tmp / "config"
        self.state = self.tmp / "state"
        self.bin = self.tmp / "bin"
        for d in (self.home, self.config, self.state, self.bin):
            d.mkdir()
        (self.bin / "claude").symlink_to(HERE / "fake_claude.py")
        self.project = self.config / "projects" / "-some-project"
        self.project.mkdir(parents=True)
        self.path = self.project / (SID + ".jsonl")
        self.path.write_text(dump(rows()) + PARTIAL)
        self.env = {**os.environ, "HOME": str(self.home), "CLAUDE_CONFIG_DIR": str(self.config),
                    "FAKE_CLAUDE_STATE": str(self.state), "PATH": "%s:%s" % (self.bin, os.environ["PATH"])}
        for k in ("SMNS_INTERNAL", "DISABLE_PROMPT_CACHING"):
            self.env.pop(k, None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args, timeout=60):
        return subprocess.run([str(LAUNCHER), *args], env=self.env, capture_output=True, text=True, timeout=timeout)

    def calls(self):
        d = self.state / "calls"
        return [json.loads(p.read_text()) for p in sorted(d.iterdir())] if d.exists() else []

    def copy_rows(self, call):
        return [json.loads(line) for line in call["copy"].splitlines()]

    @property
    def work_folder(self):
        work = os.path.realpath(self.home / ".cache" / "query-transcript" / "work")
        return self.config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", work)

    def answer(self, text):
        (self.state / "answer.txt").write_text(text)


class Segments(Case):
    def test_list_numbers_segments_with_times_and_tokens(self):
        r = self.run_cli(SID, "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertRegex(lines[1], r"^0\s+2026-11-01T10:00:00Z\s+2026-11-01T10:05:00Z\s+1,234$")
        self.assertRegex(lines[2], r"^1\s+2026-11-01T10:05:00Z\s+2026-11-01T11:00:00Z\s+5,678$")
        # The last segment: tokens from its last usage row; it ends at its last complete row.
        self.assertRegex(lines[3], r"^2\s+2026-11-01T11:00:00Z\s+2026-11-01T11:02:00Z\s+335$")
        self.assertIn("3 segments", lines[4])
        self.assertEqual(self.calls(), [])

    def test_list_json(self):
        r = self.run_cli(SID, "--list", "--json")
        d = json.loads(r.stdout)
        self.assertEqual([s["segment"] for s in d["segments"]], [0, 1, 2])
        self.assertEqual(d["segments"][1], {"segment": 1, "start": "2026-11-01T10:05:00Z",
                                            "end": "2026-11-01T11:00:00Z", "tokens": 5678})
        self.assertEqual(d["tokens"], 1234 + 5678 + 335)

    def test_default_is_the_last_segment_from_its_boundary_without_the_partial_line(self):
        r = self.run_cli(SID, "what happened?")
        self.assertEqual(r.returncode, 0, r.stderr)
        (call,) = self.calls()
        got = self.copy_rows(call)
        self.assertEqual(got[0]["uuid"], "cccc0001-0000-4000-8000-000000000001")
        self.assertEqual(got[-1]["uuid"], "cccc0004-0000-4000-8000-000000000004")
        self.assertNotIn("@@partial", call["copy"])

    def test_segment_zero_runs_from_the_start_to_the_first_boundary(self):
        self.run_cli(SID, "q", "--segment", "0")
        got = self.copy_rows(self.calls()[0])
        self.assertEqual(got[0]["type"], "mode")
        self.assertEqual(got[-1]["uuid"], "aaaa0004-0000-4000-8000-000000000004")
        self.assertEqual(len(got), 6)

    def test_segment_out_of_range_is_a_usage_error(self):
        r = self.run_cli(SID, "q", "--segment", "3")
        self.assertEqual(r.returncode, 2)
        self.assertIn("0-2", r.stderr)


class Until(Case):
    def test_by_time_picks_the_segment_and_ends_before_the_next_row(self):
        r = self.run_cli(SID, "q", "--until", "2026-11-01T10:06:30Z")
        self.assertEqual(r.returncode, 0, r.stderr)
        got = self.copy_rows(self.calls()[0])
        self.assertEqual([x["uuid"] for x in got], ["bbbb0001-0000-4000-8000-000000000001",
                                                   "bbbb0002-0000-4000-8000-000000000002",
                                                   "bbbb0003-0000-4000-8000-000000000003"])
        self.assertIn("segment 1 · 2026-11-01T10:05:00Z → 2026-11-01T11:00:00Z · until 2026-11-01T10:06:30Z",
                      r.stdout)

    def test_by_time_at_a_row_keeps_that_row_and_a_zoneless_time_is_utc(self):
        self.run_cli(SID, "q", "--until", "2026-11-01 10:00:05")
        got = self.copy_rows(self.calls()[0])
        self.assertEqual(got[-1]["uuid"], "aaaa0002-0000-4000-8000-000000000002")

    def test_by_uuid_prefix_ends_with_that_row(self):
        r = self.run_cli(SID, "q", "--until", "aaaa0003")
        self.assertEqual(r.returncode, 0, r.stderr)
        got = self.copy_rows(self.calls()[0])
        self.assertEqual(got[0]["type"], "mode")
        self.assertEqual(got[-1]["uuid"], "aaaa0003-0000-4000-8000-000000000003")

    def test_ambiguous_uuid_prefix(self):
        r = self.run_cli(SID, "q", "--until", "aaaa000")
        self.assertEqual(r.returncode, 2)
        self.assertIn("matches 4 rows", r.stderr)

    def test_a_segment_that_does_not_hold_it(self):
        for until in ("2026-11-01T10:06:30Z", "bbbb0003"):
            r = self.run_cli(SID, "q", "--until", until, "--segment", "0")
            self.assertEqual(r.returncode, 2, until)
            self.assertIn("segment 1", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_before_the_session_or_unknown(self):
        self.assertEqual(self.run_cli(SID, "q", "--until", "2026-10-01T00:00:00Z").returncode, 2)
        self.assertEqual(self.run_cli(SID, "q", "--until", "ffff9999").returncode, 2)

    def test_not_with_several_segments(self):
        self.assertEqual(self.run_cli(SID, "q", "--until", "aaaa0003", "--all").returncode, 2)
        self.assertEqual(self.run_cli(SID, "q", "--until", "aaaa0003", "--segments", "0-1").returncode, 2)


class Resolve(Case):
    def test_prefix_and_path(self):
        self.assertEqual(qt_resolve(self, SID[:8]), str(self.path))
        self.assertEqual(qt_resolve(self, str(self.path)), str(self.path))

    def test_ambiguous_prefix_lists_its_matches(self):
        (self.project / (OTHER + ".jsonl")).write_text(dump(rows()))
        r = self.run_cli("1111", "q")
        self.assertEqual(r.returncode, 2)
        self.assertIn(SID, r.stderr)
        self.assertIn(OTHER, r.stderr)

    def test_a_symlinked_project_folder_is_one_transcript(self):
        (self.config / "projects" / "-moved-project").symlink_to(self.project)
        self.assertEqual(qt_resolve(self, SID), str(self.path))

    def test_missing(self):
        r = self.run_cli("deadbeef", "q")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.run_cli(str(self.tmp / "nope.jsonl"), "q").returncode, 2)


def qt_resolve(case, arg):
    old = {k: os.environ.get(k) for k in ("HOME", "CLAUDE_CONFIG_DIR")}
    os.environ.update(HOME=str(case.home), CLAUDE_CONFIG_DIR=str(case.config))
    try:
        return qt.resolve(arg)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TheFork(Case):
    def test_command_line_environment_and_rewrite(self):
        r = self.run_cli(SID, "Why did it add the token?", "--segment", "0")
        self.assertEqual(r.returncode, 0, r.stderr)
        (call,) = self.calls()
        a = call["args"]
        copy_id, fork_id = a[a.index("--resume") + 1], a[a.index("--session-id") + 1]
        self.assertNotEqual(copy_id, fork_id)
        self.assertEqual(a[:-1], ["-p", "--resume", copy_id, "--fork-session", "--session-id", fork_id,
                                  "--safe-mode", "--no-session-persistence", "--model", "haiku", "--effort", "high",
                                  "--tools", "", "--output-format", "json"])
        self.assertTrue(a[-1].startswith("You are not the model that worked"))
        self.assertTrue(a[-1].endswith("Why did it add the token?"))
        self.assertIn("previous session ended", a[-1])
        self.assertNotIn("nothing relevant", a[-1])
        self.assertEqual(call["env"], {"SMNS_INTERNAL": "1", "DISABLE_PROMPT_CACHING": "1"})
        self.assertEqual(os.path.realpath(call["cwd"]),
                         os.path.realpath(self.home / ".cache" / "query-transcript" / "work"))
        self.assertEqual(call["folder"], str(self.work_folder))
        got = self.copy_rows(call)
        self.assertTrue(all(x["sessionId"] == copy_id for x in got if "sessionId" in x))
        self.assertNotIn(SID, call["copy"])
        # Nothing else in a row changes: the original, with the id swapped back, is the copy.
        original = self.path.read_text().splitlines(keepends=True)[:6]
        self.assertEqual(call["copy"].replace(copy_id, SID), "".join(original))

    def test_a_subagent_transcript_has_its_sidechain_flag_cleared(self):
        agent = self.project / SID / "subagents" / "agent-a1b2c3.jsonl"
        agent.parent.mkdir(parents=True)
        side = [dict(r, isSidechain=True, agentId="a1b2c3") for r in rows()[1:4]]
        agent.write_text(dump(side))
        r = self.run_cli(str(agent), "what was it asked?")
        self.assertEqual(r.returncode, 0, r.stderr)
        call = self.calls()[0]
        self.assertNotIn('"isSidechain":true', call["copy"])
        self.assertEqual(len(self.copy_rows(call)), 3)
        self.assertTrue(all(x["isSidechain"] is False for x in self.copy_rows(call)))

    def assertClean(self):
        left = sorted(os.listdir(self.work_folder)) if self.work_folder.exists() else []
        self.assertEqual(left, [])

    def test_cleanup_on_success(self):
        self.assertEqual(self.run_cli(SID, "q").returncode, 0)
        self.assertClean()

    def test_cleanup_on_failure(self):
        self.path.write_text(dump(rows()[:3] + [user("dddd0001-0000-4000-8000-000000000001",
                                                     "2026-11-01T10:00:06Z", "@@fail")]))
        r = self.run_cli(SID, "q")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAILED: claude failed (exit 1): API Error: prompt is too long", r.stdout)
        self.assertClean()

    def test_cleanup_on_timeout(self):
        self.path.write_text(dump(rows()[:3] + [user("dddd0001-0000-4000-8000-000000000001",
                                                     "2026-11-01T10:00:06Z", "@@sleep")]))
        t0 = time.time()
        r = self.run_cli(SID, "q", "--timeout", "2")
        self.assertLess(time.time() - t0, 30)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAILED: timed out after 2s", r.stdout)
        self.assertClean()

    def test_an_error_result_and_an_empty_answer_fail(self):
        for directive, why in (("@@error", "Prompt is too long"), ("@@empty", "answered nothing")):
            self.path.write_text(dump(rows()[:3] + [user("dddd0001-0000-4000-8000-000000000001",
                                                         "2026-11-01T10:00:06Z", directive)]))
            r = self.run_cli(SID, "q")
            self.assertEqual(r.returncode, 1, directive)
            self.assertIn(why, r.stdout)
            self.assertClean()

    def test_a_crashed_runs_copy_is_swept_after_a_day(self):
        self.work_folder.mkdir(parents=True)
        old, fresh = self.work_folder / "old.jsonl", self.work_folder / "fresh.jsonl"
        old.write_text("{}\n")
        fresh.write_text("{}\n")
        os.utime(old, (time.time() - 2 * 86400,) * 2)
        self.run_cli(SID, "q")
        self.assertEqual(sorted(os.listdir(self.work_folder)), ["fresh.jsonl"])

    def test_usage_line(self):
        r = self.run_cli(SID, "q")
        self.assertRegex(r.stdout, r"via haiku · 1,002 in · 50 out · \$0\.01 · \d+ s")


class Quotes(Case):
    def check(self, answer, segment="0"):
        self.answer(answer)
        r = self.run_cli(SID, "q", "--segment", segment, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["segments"][0]["quotes"]

    def test_found_elided_and_not_found(self):
        qs = self.check("The human asked:\n\n> Please fix the build. It fails on the token step.\n\n"
                        "Then the tool said\n> exit 1: ... GH_TOKEN\n\nand\n\n> the session gave up\n\n"
                        "> ONLY-IN-THE-REQUEST-LOG\n")
        self.assertEqual([q["found"] for q in qs], [True, True, False, False])
        self.assertEqual((qs[0]["time"], qs[0]["kind"], qs[0]["uuid"]),
                         ("2026-11-01T10:00:00Z", "human", "aaaa0001-0000-4000-8000-000000000001"))
        self.assertEqual((qs[1]["time"], qs[1]["kind"]), ("2026-11-01T10:00:10Z", "tool result"))

    def test_pieces_must_be_in_order_in_one_row(self):
        qs = self.check("> GH_TOKEN ... exit 1\n\n> Please fix ... exit 1\n")
        self.assertEqual([q["found"] for q in qs], [False, False])

    def test_kinds_quote_marks_and_markdown(self):
        qs = self.check('> "I will look at the CI config first, then ci.yml."\n\n'
                        "> <task-id>abc123</task-id>\n\n"
                        "```\n> not a quote\n```\n")
        self.assertEqual(len(qs), 2)
        self.assertEqual((qs[0]["found"], qs[0]["kind"]), (True, "session"))
        self.assertEqual((qs[1]["found"], qs[1]["kind"]), (True, "notice"))
        qs = self.check("> Summary: the build was fixed\n", segment="1")
        self.assertEqual((qs[0]["found"], qs[0]["kind"]), (True, "summary"))

    def test_text_output_stamps_quotes(self):
        self.answer("> ship it\n\n> never said\n")
        r = self.run_cli(SID, "q", "--segment", "1")
        self.assertIn('  2026-11-01T10:07:00Z  human  bbbb0004  "ship it"', r.stdout)
        self.assertIn('  not found in the record  "never said"', r.stdout)

    def test_a_thinking_signature_is_not_the_record(self):
        self.assertEqual(self.check("> SIGNATURE-TEXT\n")[0]["found"], False)


class Several(Case):
    def test_order_collapse_and_a_failed_segment(self):
        rs = rows()
        rs[8]["message"]["content"][1]["text"] += " @@nothing"
        rs[12]["message"]["content"][1]["text"] += " @@fail"
        self.path.write_text(dump(rs))
        self.answer("Answer with no quotes.")
        r = self.run_cli(SID, "q", "--all", "--jobs", "3")
        self.assertEqual(r.returncode, 1)
        heads = [line for line in r.stdout.splitlines() if line.startswith("== ")]
        self.assertEqual(len(heads), 3)
        self.assertTrue(heads[0].startswith("== segment 0 · 2026-11-01T10:00:00Z → 2026-11-01T10:05:00Z"))
        self.assertRegex(heads[1], r"^== segment 1 · .* · nothing relevant · via haiku · ")
        self.assertRegex(heads[2], r"^== segment 2 · .* · FAILED: claude failed \(exit 1\)")
        self.assertIn("Answer with no quotes.", r.stdout)
        self.assertIn("3 segments, 7,247 tokens, at most $0.00", r.stderr)
        prompts = [c["args"][-1] for c in self.calls()]
        self.assertTrue(all("reply with exactly: nothing relevant" in p for p in prompts))

    def test_segments_range_and_json(self):
        self.answer("> ship it\n")
        r = self.run_cli(SID, "q", "--segments", "1-", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual(d["session"], SID)
        self.assertEqual(d["transcript"], str(self.path))
        self.assertEqual([s["segment"] for s in d["segments"]], [1, 2])
        s1 = d["segments"][0]
        self.assertEqual(s1["answer"], "> ship it")
        self.assertEqual(s1["usage"]["model"], "haiku")
        self.assertEqual(s1["usage"]["input"], 1002)
        self.assertTrue(s1["quotes"][0]["found"])
        self.assertFalse(d["segments"][1]["quotes"][0]["found"])
        self.assertEqual(len(self.calls()), 2)

    def test_bad_range(self):
        for spec in ("2-1", "0-9", "x"):
            self.assertEqual(self.run_cli(SID, "q", "--segments", spec).returncode, 2, spec)


class Usage(Case):
    def test_a_query_is_required(self):
        self.assertEqual(self.run_cli(SID).returncode, 2)

    def test_segment_flags_exclude_each_other(self):
        self.assertEqual(self.run_cli(SID, "q", "--segment", "0", "--all").returncode, 2)


if __name__ == "__main__":
    unittest.main()
