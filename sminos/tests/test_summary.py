#!/usr/bin/env python3
"""A session's summary (docs/doperpowers/specs/2026-11-23-sminos-session-search-design.md,
§1, §2 and §4; its acceptance 1-4).

- Every derive asks for three lines, `doing:`, `made:` and `next:`, after
  the line (and after the charge name, when one is asked), and records
  them as the `summary` of the in-charge event it writes; a summary line is
  cut to 200 characters.
- The answer is read by one reader (`answer_fields`): labelled lines
  anywhere, marked or not, the line the first unlabelled one of the
  marked text, else of the unmarked; a summary only when all three are
  there, and an answer without one still records its line.
- Every compaction derives: two `--compacted` derives in a row fork twice,
  and nothing is counted under `$SMINOS_HOME/compactions/`.
- `who @<session>` and `who <commit>` show the summary with its age;
  `list` does not, `list --json` carries it; a summary from another
  machine's writer shows; a withdrawn session's summary never does, through
  a session that continues it or `who <commit>`'s history; the reach lines
  of a local `gone` member and of a remote one held for `transcript`.

Hermetic: test_threads.Machine's temporary HOME and SMINOS_HOME, sessions
that are `sleep` processes, the headless fork stood in for by a function
that answers what the test gives it.
Run: python3 -B sminos/tests/test_summary.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import json
import os
import subprocess
import sys
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import Machine, sminos, threads  # noqa: E402

FORK = sminos.sibling_module("sminos_fork")
SUMMARY = {"doing": "rewriting the parser's error paths, half done",
           "made": "sminos/parser.py, PR #12 in example/repo, the decision to keep one reader",
           "next": "waiting on the review of PR #12, then the docs"}
THREE = "\n".join("%s: %s" % (k, SUMMARY[k]) for k in ("doing", "made", "next"))


class Reading(unittest.TestCase):
    """answer_fields, the one reader of a derive's answer (§1b)."""

    def test_an_unmarked_answer_reads_as_today(self):
        got = sminos.answer_fields("Owns the parser.\nA second line.")
        self.assertEqual(got, sminos.AnswerFields("Owns the parser.", None, None))
        self.assertEqual(sminos.answer_line("Owns the parser.\nname: parser-owner"), "Owns the parser.")
        self.assertEqual(sminos.answer_name("Owns the parser.\nname: `Parser-Owner`."), "parser-owner")

    def test_labels_are_case_insensitive_after_whitespace_and_their_values_trimmed(self):
        got = sminos.answer_fields('Owns it.\n  Doing: "a"\nMADE: `b`\nnext:  c  ')
        self.assertEqual(got.summary, {"doing": "a", "made": "b", "next": "c"})

    def test_backticks_inside_a_value_are_kept(self):
        got = sminos.answer_fields("Owns it.\ndoing: x\nmade: `a.py` and `b.py`\nnext: y")
        self.assertEqual(got.summary["made"], "`a.py` and `b.py`")

    def test_an_empty_value_is_no_summary(self):
        self.assertIsNone(sminos.answer_fields("Owns it.\ndoing: x\nmade:\nnext: y").summary)

    def test_a_value_of_delimiters_alone_is_empty_and_a_name_in_them_is_kept(self):
        self.assertIsNone(sminos.answer_fields("Owns it.\ndoing: x\nmade: ```\nnext: y").summary)
        self.assertIsNone(sminos.answer_fields("Owns it.\ndoing: x\nmade: \"'`\nnext: y").summary)
        self.assertEqual(sminos.answer_fields("Owns it.\ndoing: x\nmade: `a.py`\nnext: y").summary["made"], "a.py")

    def test_text_beside_a_mark_on_its_line_is_not_read_into_the_marked_fields(self):
        got = sminos.answer_fields("name: parser-owner<message>Owns the parser.\n%s</message>said after it" % THREE)
        self.assertEqual(got, sminos.AnswerFields("Owns the parser.", "parser-owner", SUMMARY))
        got = sminos.answer_fields("Owns the parser.<message>%s</message>and words after" % THREE)
        self.assertEqual(got, sminos.AnswerFields("Owns the parser.", None, SUMMARY))

    def test_a_labelled_line_is_never_the_line(self):
        self.assertEqual(sminos.answer_fields("doing: x\nmade: y\nnext: z").line, "")


class Deriving(Machine):
    """A derive of a live member, its fork answering `answer`."""

    def member(self, sid):
        sminos.forget_caches()
        return next(m for m in sminos.members(self.p) if m.session == sid)

    def tools(self, sid, n=10):
        """The session's transcript, its model's `n` tool calls: derive's threshold."""
        d = os.path.join(os.environ["HOME"], ".claude", "projects", "p-work")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, sid + ".jsonl"), "a") as f:
            for i in range(n):
                f.write(json.dumps({"type": "assistant", "isSidechain": False, "uuid": str(uuidlib.uuid4()),
                                    "message": {"role": "assistant", "content": [
                                        {"type": "tool_use", "id": "tu-%s-%d" % (sid[:4], i), "name": "Bash",
                                         "input": {}}]}}) + "\n")
        sminos.forget_caches()
        sminos.transcripts_now()

    def live(self, named="user"):
        """A live member with ten tool calls; `named` its engine name's source (derived: sminos may name it)."""
        sid, proc = self.session()
        self.peer_set(proc, nameSource=named)
        self.reconcile()
        self.tools(sid)
        return sid, proc

    def derive(self, sid, answer, *argv):
        """`derive <sid> [argv]` with the fork answering `answer`: (exit, output, prompts asked)."""
        prompts = []

        def fork(project, m, prompt, **kw):
            prompts.append(prompt)
            return FORK.ForkAnswer(answer, "headless fork", {"input": 0, "output": 0, "cacheRead": 0,
                                                              "cacheWrite": 0}, False)
        with mock.patch.object(FORK, "headless_fork", fork), mock.patch.object(FORK, "bridge_offers",
                                                                             return_value=False):
            code, out = self.cli("derive", sid, *argv)
        return code, out, prompts

    def charge(self, sid):
        return [e for e in self.own(sid) if e["kind"] == "in-charge"][-1]


class Derive(Deriving):
    # ---- acceptance 1: asked and recorded

    def test_the_prompt_asks_for_the_summary_after_the_line_and_ends_with_four_lines(self):
        sid, _ = self.live()
        code, out, prompts = self.derive(sid, "Owns the parser.\n" + THREE)
        self.assertEqual(code, 0, out)
        prompt = prompts[0]
        self.assertTrue(prompt.startswith(sminos.DERIVE_QUESTION), prompt)
        self.assertIn(sminos.SUMMARY_ASK, prompt)
        self.assertLess(prompt.index(sminos.DERIVE_QUESTION), prompt.index(sminos.SUMMARY_ASK))
        self.assertTrue(prompt.endswith(sminos.SUMMARY_ASK + "\nAnswer with these four lines only."), prompt)
        e = self.charge(sid)
        self.assertEqual((e["text"], e["source"], e["summary"]), ("Owns the parser.", "derived", SUMMARY))

    def test_with_a_current_line_the_keep_bar_comes_before_the_summary_ask(self):
        sid, _ = self.live()
        self.derive(sid, "Owns the parser.\n" + THREE)
        _, _, prompts = self.derive(sid, "Owns the parser.\n" + THREE, "--compacted")
        prompt = prompts[0]
        keep = sminos.DERIVE_KEEP % "Owns the parser."
        self.assertTrue(prompt.startswith(sminos.DERIVE_QUESTION + keep + "\n" + sminos.SUMMARY_ASK), prompt)
        self.assertTrue(prompt.endswith("\nAnswer with these four lines only."), prompt)

    def test_with_a_charge_name_asked_the_summary_ask_follows_it_and_ends_with_five_lines(self):
        sid, _ = self.live(named="derived")
        code, out, prompts = self.derive(sid, "Owns the parser.\nname: parser-owner\n" + THREE)
        self.assertEqual(code, 0, out)
        prompt = prompts[0]
        self.assertLess(prompt.index(sminos.NAMING_ASK), prompt.index(sminos.SUMMARY_ASK))
        self.assertTrue(prompt.endswith(sminos.SUMMARY_ASK + "\nAnswer with these five lines only."), prompt)
        e = self.charge(sid)
        self.assertEqual((e["text"], e.get("name"), e["summary"]), ("Owns the parser.", "parser-owner", SUMMARY))

    def test_a_summary_line_over_200_characters_is_cut_to_200(self):
        sid, _ = self.live()
        self.derive(sid, "Owns the parser.\ndoing: %s\nmade: m\nnext: n" % ("x" * 260))
        self.assertEqual(self.charge(sid)["summary"]["doing"], "x" * 200)

    # ---- acceptance 2: the answer read

    def case(self, answer, named="user"):
        sid, _ = self.live(named=named)
        code, out, _ = self.derive(sid, answer)
        self.assertEqual(code, 0, out)
        return self.charge(sid)

    def test_labelled_lines_before_the_line(self):
        e = self.case(THREE + "\nOwns the parser.")
        self.assertEqual((e["text"], e["summary"]), ("Owns the parser.", SUMMARY))

    def test_a_name_line_among_them(self):
        e = self.case("doing: %s\nname: parser-owner\nOwns the parser.\nmade: %s\nnext: %s"
                      % (SUMMARY["doing"], SUMMARY["made"], SUMMARY["next"]), named="derived")
        self.assertEqual((e["text"], e.get("name"), e["summary"]), ("Owns the parser.", "parser-owner", SUMMARY))

    def test_the_five_lines_split_across_two_spans(self):
        e = self.case("<message>Owns the parser.\nname: parser-owner</message>\nSome thinking.\n<message>%s</message>"
                      % THREE, named="derived")
        self.assertEqual((e["text"], e.get("name"), e["summary"]), ("Owns the parser.", "parser-owner", SUMMARY))

    def test_only_the_summary_marked_the_line_and_name_unmarked(self):
        e = self.case("Owns the parser.\nname: parser-owner\n<message>%s</message>" % THREE, named="derived")
        self.assertEqual((e["text"], e.get("name"), e["summary"]), ("Owns the parser.", "parser-owner", SUMMARY))

    def test_the_line_marked_with_commentary_outside_the_marks(self):
        e = self.case("Here is my answer:\n<message>Owns the parser.\n%s</message>\nHope that helps." % THREE)
        self.assertEqual((e["text"], e["summary"]), ("Owns the parser.", SUMMARY))

    def test_a_mark_beside_unmarked_text_on_the_same_line(self):
        e = self.case("name: parser-owner<message>%s</message>Owns the parser." % THREE, named="derived")
        self.assertEqual((e["text"], e.get("name"), e["summary"]), ("Owns the parser.", "parser-owner", SUMMARY))
        e = self.case("Owns the parser.<message>%s</message>and so on" % THREE)
        self.assertEqual((e["text"], e["summary"]), ("Owns the parser.", SUMMARY))

    def test_an_unmarked_answer_as_today(self):
        e = self.case("Owns the parser.\nA second line.")
        self.assertEqual(e["text"], "Owns the parser.")
        self.assertNotIn("summary", e)

    def test_an_answer_missing_next_records_the_line_alone(self):
        sid, _ = self.live()
        code, out, _ = self.derive(sid, "Owns the parser.\ndoing: a\nmade: b")
        self.assertEqual(code, 0, out)
        e = self.charge(sid)
        self.assertEqual(e["text"], "Owns the parser.")
        self.assertNotIn("summary", e, "a partial summary is none")

    # ---- acceptance 3: every compaction derives

    def test_two_compactions_in_a_row_both_fork_and_nothing_is_counted(self):
        sid, _ = self.live()
        self.derive(sid, "Owns the parser.\n" + THREE)
        forks = 0
        for _ in range(2):
            code, out, prompts = self.derive(sid, "Owns the parser.\n" + THREE, "--compacted")
            self.assertEqual(code, 0, out)
            forks += len(prompts)
        self.assertEqual(forks, 2, "each compaction forks")
        self.assertFalse(os.path.exists(os.path.join(os.environ["SMINOS_HOME"], "compactions")))


def git(root, *argv):
    subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@t", *argv], check=True,
                   capture_output=True)


class Who(Deriving):
    """`who @<session>`, `who <commit>`, and `list`, with summaries."""

    def remote(self, machine="beta", alias="far", summary=None, state="idle", **state_fields):
        """Another machine's member, in this project's log under that machine's writer."""
        sid = str(uuidlib.uuid4())
        w = "%s/%s" % (machine, sid)
        sminos.log_append(self.p, w, "joined", session=sid, alias=alias, name_source="user", machine=machine,
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive",
                          thread=str(uuidlib.uuid4()))
        sminos.log_append(self.p, w, "state", session=sid, state=state, machine=machine, **state_fields)
        if summary:
            sminos.log_append(self.p, w, "in-charge", session=sid, text="Runs far things.", source="derived",
                              summary=summary)
        sminos.forget_caches()
        return sid

    def commit(self, line):
        with open(os.path.join(self.root, "f"), "a") as f:
            f.write(line + "\n")
        git(self.root, "add", "f")
        git(self.root, "commit", "-q", "-m", "work\n\n" + line)
        return subprocess.run(["git", "-C", self.root, "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()

    def test_who_at_short_alias_and_project_alias_print_the_summary_with_its_age(self):
        sid, _ = self.live()
        self.derive(sid, "Owns the parser.\n" + THREE)
        m = self.member(sid)
        for tag in ("@" + sid[:8], "@" + m.alias, "@%s/%s" % (self.p.name, m.alias)):
            with self.subTest(tag=tag):
                code, out = self.cli("who", tag)
                self.assertEqual(code, 0, out)
                self.assertIn("now %s#%s" % (m.alias, sid[:8]), out)
                self.assertIn("  in charge: Owns the parser.", out)
                self.assertRegex(out, r"\n  doing \([^)]+\): %s\n" % SUMMARY["doing"])
                self.assertIn("\n  made: %s\n" % SUMMARY["made"], out)
                self.assertIn("\n  next: %s\n" % SUMMARY["next"], out)
                self.assertIn('reach: sminos say "@%s ..."' % sid[:8], out)

    def test_who_at_a_name_no_session_answers_exits_4(self):
        code, out = self.cli("who", "@nobody-here")
        self.assertEqual(code, 4, out)
        self.assertIn("no member @nobody-here", out)

    def test_who_commit_shows_it_and_list_does_not_and_list_json_carries_it(self):
        sid, _ = self.live()
        self.derive(sid, "Owns the parser.\n" + THREE)
        m = self.member(sid)
        sha = self.commit("Sminos-Session: %s#%s (%s on %s)" % (m.alias, sid[:8], self.p.name, m.machine))
        code, out = self.cli("who", sha)
        self.assertEqual(code, 0, out)
        self.assertIn("\n  made: %s\n" % SUMMARY["made"], out)
        code, out = self.cli("list")
        self.assertEqual(code, 0, out)
        self.assertNotIn("doing:", out)
        self.assertNotIn(SUMMARY["made"], out)
        code, out = self.cli("list", "--json")
        row = next(r for r in json.loads(out) if r["session"] == sid)
        self.assertEqual(row["summary"], SUMMARY)
        self.assertIsInstance(row["summary_age"], (int, float))
        other, _ = self.session()
        self.reconcile()
        code, out = self.cli("list", "--json")
        row = next(r for r in json.loads(out) if r["session"] == other)
        self.assertEqual((row["summary"], row["summary_age"]), (None, None))

    def test_a_summary_another_machine_wrote_shows(self):
        sid = self.remote(summary=SUMMARY)
        code, out = self.cli("who", "@" + sid[:8])
        self.assertEqual(code, 0, out)
        self.assertIn("now far#%s, %s on beta: idle" % (sid[:8], self.p.name), out)
        self.assertIn("\n  next: %s\n" % SUMMARY["next"], out)

    def test_a_malformed_summary_is_none(self):
        sid = self.remote(summary={"doing": "a", "made": "", "next": "c"})
        self.assertIsNone(self.member(sid).summary)
        sid = self.remote(summary="doing: a")
        self.assertIsNone(self.member(sid).summary)

    def test_a_later_set_line_keeps_the_summary(self):
        sid = self.remote(summary=SUMMARY)
        sminos.log_append(self.p, "beta/%s" % sid, "in-charge", session=sid, text="Set by hand.", source="set")
        m = self.member(sid)
        self.assertEqual((m.charge, m.summary), ("Set by hand.", SUMMARY))

    def test_a_remote_member_held_for_transcript_says_a_message_waits_and_no_resume(self):
        sid = self.remote(state="gone", wake="held", why="transcript")
        code, out = self.cli("who", "@" + sid[:8])
        self.assertEqual(code, 0, out)
        self.assertIn('leave it a message, held until a process of it runs (%s): sminos say "@%s ..."'
                      % (sminos.HOLD_WORDS["transcript"], sid[:8]), out)
        self.assertNotIn("claude --resume", out)

    def test_a_local_gone_member_with_no_seat_says_nothing_here_resumes_it(self):
        sid, proc = self.session()   # no transcript of it here
        self.reconcile()
        self.end(proc)
        # A session its human opened is stopped by its record (stopped_human): `gone` is a seatless member's with
        # neither that record nor a transcript here.
        with mock.patch.object(threads, "stopped_human", return_value=False):
            code, out = self.cli("who", "@" + sid[:8])
        self.assertEqual(code, 0, out)
        self.assertIn(": gone", out)
        self.assertIn("  nothing on this machine resumes it", out)
        self.assertNotIn("claude --resume", out)

    def withdrawn(self, sid, rev=1):
        """The owner's withdrawal of this machine's view of a remote session: the `unlisted` notice."""
        sminos.log_append(self.p, "beta/%s" % sid, "unlisted", session=sid, policyRev=rev)
        sminos.forget_caches()

    def test_a_session_that_continues_a_withdrawn_one_carries_no_summary_from_it(self):
        former = self.remote(summary={**SUMMARY, "made": "WITHDRAWN-SECRET plans"})
        later = self.remote(alias="far2")
        sminos.log_append(self.p, "beta/%s" % former, "retired", session=former, reason="continued", to=later)
        sminos.forget_caches()
        self.assertEqual(self.member(later).former, (former,), "it continues the former")
        self.assertEqual(self.member(later).summary["made"], "WITHDRAWN-SECRET plans", "visible, it carries it")
        self.withdrawn(former)
        self.assertIsNone(self.member(later).summary)
        code, out = self.cli("who", "@" + later[:8])
        self.assertEqual(code, 0, out)
        self.assertNotIn("WITHDRAWN-SECRET", out)
        code, out = self.cli("list", "--json")
        self.assertNotIn("WITHDRAWN-SECRET", out)

    def test_who_commit_naming_a_retired_withdrawn_session_prints_no_summary(self):
        sid = self.remote(summary={**SUMMARY, "doing": "WITHDRAWN-SECRET work"})
        sminos.log_append(self.p, "beta/%s" % sid, "retired", session=sid, reason="retired")
        self.withdrawn(sid)
        sha = self.commit("Sminos-Session: far#%s (%s on beta)" % (sid[:8], self.p.name))
        code, out = self.cli("who", sha)
        self.assertEqual(code, 0, out)
        self.assertIn("far#%s" % sid[:8], out, "the session is still said")
        self.assertNotIn("WITHDRAWN-SECRET", out)

    def test_who_commit_naming_a_retired_withdrawn_successor_prints_no_summary_from_its_visible_predecessor(self):
        before = self.remote(summary={**SUMMARY, "made": "PREDECESSOR-SECRET plans"})
        after = self.remote(alias="far2")
        sminos.log_append(self.p, "beta/%s" % before, "retired", session=before, reason="continued", to=after)
        sminos.log_append(self.p, "beta/%s" % after, "retired", session=after, reason="retired")
        sminos.forget_caches()
        sha = self.commit("Sminos-Session: far2#%s (%s on beta)" % (after[:8], self.p.name))
        code, out = self.cli("who", sha)
        self.assertEqual(code, 0, out)
        self.assertIn("PREDECESSOR-SECRET", out, "visible, the successor carries its predecessor's summary")
        self.withdrawn(after)
        code, out = self.cli("who", sha)
        self.assertEqual(code, 0, out)
        self.assertIn("far2#%s" % after[:8], out, "the session is still said")
        self.assertNotIn("PREDECESSOR-SECRET", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
