#!/usr/bin/env python3
"""`sminos find "<question>"`, the org's search
(docs/doperpowers/specs/2026-11-23-sminos-session-search-design.md, §3;
its acceptance 5, 6 and 6a).

- The call: one internal process (`SMNS_INTERNAL=1`, its marker present
  while it runs), `claude -p --safe-mode --no-session-persistence --model
  haiku --tools ""`, never `--bare`, the corpus then the question on its
  standard input, from $SMINOS_HOME, on the caller's first-party login: no
  gateway variable, no ANTHROPIC_*, no provider switch reaches it, and
  CLAUDE_CODE_OAUTH_TOKEN and CLAUDE_CONFIG_DIR reach it unchanged.
- The corpus: list --org's rows, live and stopped, never the caller, a
  retired or ended member (but with --all), a project that has left this
  machine, or a session withdrawn from this machine's view; every field
  capped, and a prompt over budget refused before any call.
- The answer: shorts checked against the corpus (an unknown one dropped and
  counted, a repeat dropped, five at most), each match its row, why,
  summary and reach lines; none is exit 4; a malformed answer, a crash or a
  timeout exit 1, in text and in --json.
- The gate (run_internal): a gate closed without its release starts
  nothing; a marker that cannot be written kills and reaps the child.

Hermetic: test_threads.Machine's temporary HOME and SMINOS_HOME, the
`claude` stand-in (fake_claude.py) first on PATH, or ask_model stood in for by a
function where only the answer matters.
Run: python3 -B sminos/tests/test_find.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import BASE, Machine, sminos  # noqa: E402

FORK = sminos.sibling_module("sminos_fork")
SUMMARY = {"doing": "moving the CI of three repositories onto one runner",
           "made": "ci-kit's gate list, PR #41 in example/ci-kit, the decision to pin runners",
           "next": "waiting on the runner image, then the docs"}

# The `claude` stand-in (fake_claude.py) first on PATH: a `-p` call's argv, environment, working directory,
# marker and standard input go to find-calls.log; it answers $FAKE_CLAUDE_FIND_RESULT, or crashes, errs or sleeps
# by $FAKE_CLAUDE_FIND_MODE.
FAKE_BIN = os.path.join(BASE, "find-bin")
FAKE = os.path.join(FAKE_BIN, "claude")
os.makedirs(FAKE_BIN, exist_ok=True)
if not os.path.lexists(FAKE):
    os.symlink(os.path.join(HERE, "fake_claude.py"), FAKE)

NONE = json.dumps({"matches": [], "note": ""})


class Finding(Machine):
    def setUp(self):
        super().setUp()
        state = os.path.join(self.home, "fake-claude")
        self.log = os.path.join(state, "find-calls.log")
        for k in ("CLAUDE_CODE_SESSION_ID", "FAKE_CLAUDE_FIND_MODE", "FAKE_CLAUDE_FIND_RESULT", "SMINOS_FIND_TIMEOUT",
                  "FAKE_CLAUDE_STATE"):
            self.addCleanup(os.environ.pop, k, None)
            os.environ.pop(k, None)
        os.environ["FAKE_CLAUDE_STATE"] = state
        path = os.environ["PATH"]
        self.addCleanup(os.environ.__setitem__, "PATH", path)
        os.environ["PATH"] = FAKE_BIN + os.pathsep + path

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return [json.loads(line) for line in f if line.strip()]

    def run_cli(self, *argv):
        """The CLI in this process: (exit, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        here = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    sminos.main(list(argv))
                    code = 0
                except SystemExit as e:
                    code = e.code or 0
        finally:
            os.chdir(here)
            sminos.forget_caches()
        return code, out.getvalue(), err.getvalue()

    def answered(self, text, *argv):
        """`find <argv>` with the model answering `text`: (exit, stdout, stderr, the prompts it was asked)."""
        prompts = []

        def ask(prompt, **kw):
            prompts.append(prompt)
            return FORK.ForkAnswer(text, "model", {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, False)
        with mock.patch.object(FORK, "ask_model", ask):
            code, out, err = self.run_cli("find", *argv)
        return code, out, err, prompts

    def remote(self, machine="beta", alias="far", summary=None, state="idle", charge="Runs far things.", p=None,
               branch="main", **state_fields):
        """Another machine's member, in the project's log under that machine's writer."""
        p = p or self.p
        sid = str(uuidlib.uuid4())
        w = "%s/%s" % (machine, sid)
        sminos.log_append(p, w, "joined", session=sid, alias=alias, name_source="user", machine=machine,
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive", repo="repo",
                          branch=branch, thread=str(uuidlib.uuid4()))
        sminos.log_append(p, w, "state", session=sid, state=state, machine=machine, **state_fields)
        sminos.log_append(p, w, "in-charge", session=sid, text=charge, source="derived",
                          **({"summary": summary} if summary else {}))
        sminos.forget_caches()
        return sid


# ---------------------------------------------------------------- acceptance 5: the call


class Call(Finding):
    def test_one_internal_process_on_the_first_party_login_the_question_after_the_corpus(self):
        sid = self.remote(alias="ci-owner", summary=SUMMARY)
        gateway = os.path.join(self.home, "gateway-settings.json")
        with open(gateway, "w") as f:
            json.dump({"env": {"GATEWAY_ONLY_KEY": "g", "ANTHROPIC_BASE_URL": "http://gateway.invalid"}}, f)
        config = os.path.join(os.environ["HOME"], ".claude")
        caller = {"CLODEX_SETTINGS": gateway, "GATEWAY_ONLY_KEY": "g", "ANTHROPIC_BASE_URL": "http://gateway.invalid",
                  "ANTHROPIC_AUTH_TOKEN": "tok", "ANTHROPIC_API_KEY": "key", "ANTHROPIC_MODEL": "a-model",
                  "CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_USE_VERTEX": "1", "CLAUDE_CODE_SUBAGENT_MODEL": "m",
                  "MAWS_LANE": "B", "CLAUDE_CODE_OAUTH_TOKEN": "first-party", "CLAUDE_CONFIG_DIR": config,
                  "FAKE_CLAUDE_FIND_RESULT": json.dumps({"matches": [{"short": sid[:8], "why": "owns the CI"}]})}
        with mock.patch.dict(os.environ, caller):
            code, out, err = self.run_cli("find", "who", "runs", "CI")
        self.assertEqual(code, 0, out + err)
        calls = self.calls()
        self.assertEqual(len(calls), 1, "one call")
        c = calls[0]
        argv = c["argv"]
        self.assertEqual(argv[0], "-p")
        for flags in (["--safe-mode"], ["--no-session-persistence"], ["--model", "haiku"], ["--effort", "medium"],
                      ["--tools", ""], ["--output-format", "json"]):
            at = argv.index(flags[0])
            self.assertEqual(argv[at:at + len(flags)], flags)
        for absent in ("--bare", "--resume", "--fork-session"):
            self.assertNotIn(absent, argv)
        self.assertEqual(c["env"]["internal"], "1")
        self.assertTrue(c["marker"], "its pid is marked internal while it runs")
        self.assertEqual(os.listdir(os.path.join(os.environ["SMINOS_HOME"], "internal")), [], "and unmarked after")
        self.assertEqual(os.path.realpath(c["cwd"]), os.path.realpath(os.environ["SMINOS_HOME"]))
        for gone in ("CLODEX_SETTINGS", "GATEWAY_ONLY_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN",
                     "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
                     "CLAUDE_CODE_SUBAGENT_MODEL", "MAWS_LANE"):
            self.assertNotIn(gone, c["env"]["set"])
        self.assertEqual(c["env"]["set"], ["CLAUDE_CODE_OAUTH_TOKEN"], "of the transport and login variables, the token")
        self.assertEqual(c["env"]["oauth"], "first-party", "unchanged")
        self.assertEqual(c["env"]["config"], config)
        self.assertEqual(c["env"]["path"], os.environ["PATH"])
        stdin = c["stdin"]
        self.assertTrue(stdin.endswith("Question: who runs CI"), stdin[-200:])
        self.assertLess(stdin.index("[%s] ci-owner" % sid[:8]), stdin.index("Question: who runs CI"))
        self.assertTrue(stdin.startswith(sminos.FIND_PROMPT.split("%s")[0]), "the instructions first")
        self.assertIn("ci-owner [%s]" % sid[:8], out)

    def test_no_words_is_usage_and_the_old_flags_are_refused(self):
        for argv in (["find"], ["find", "  "], ["find", "x", "--org"], ["find", "x", "--stopped"]):
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual(code, 2, out + err)
        self.assertEqual(self.calls(), [], "nothing is asked")


# ---------------------------------------------------------------- acceptance 5: the corpus


class Corpus(Finding):
    def test_live_and_stopped_with_their_summaries_never_the_caller_retired_or_ended(self):
        live = self.remote(alias="live-one", summary=SUMMARY)
        stopped = self.remote(alias="stopped-one", state="stopped", wake="woken")
        ended = self.remote(alias="ended-one")
        sminos.log_append(self.p, "beta/%s" % ended, "retired", session=ended, reason="retire")
        retired_machine = self.remote(machine="gamma", alias="on-gamma")
        os.makedirs(os.path.join(os.environ["SMINOS_HOME"], "daemon"), exist_ok=True)
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "org.json"), {
            "projects": [], "machines": [{"name": "beta"}, {"name": "gamma", "retired": True}], "at": sminos.now()})
        me, _ = self.session()
        self.reconcile()
        sminos.forget_caches()
        os.environ["CLAUDE_CODE_SESSION_ID"] = me
        code, out, err, prompts = self.answered(NONE, "anything")
        self.assertEqual(code, 4, out + err)
        prompt = prompts[0]
        self.assertIn("[%s] live-one" % live[:8], prompt)
        self.assertIn("doing (", prompt)
        self.assertIn("made: %s" % SUMMARY["made"], prompt)
        self.assertIn("[%s] stopped-one" % stopped[:8], prompt)
        for absent in (me, ended, retired_machine):
            self.assertNotIn("[%s]" % absent[:8], prompt)

        code, out, err, prompts = self.answered(NONE, "anything", "--all")
        prompt = prompts[0]
        self.assertIn("[%s] ended-one" % ended[:8], prompt, "a seatless ended thread, with --all")
        self.assertIn("[%s] on-gamma" % retired_machine[:8], prompt, "a retired machine's member, with --all")
        self.assertNotIn("[%s]" % me[:8], prompt, "never the caller")

    def test_a_project_that_has_left_this_machine_contributes_nothing(self):
        other = self.project_of(self.repo("other"))
        gone = self.remote(alias="left-behind", p=other)
        here = self.remote(alias="still-here")
        os.makedirs(os.path.dirname(sminos.leaving_path()), exist_ok=True)
        sminos.write_json(sminos.leaving_path(), {"counted": {}, "left": [other.id]})
        sminos.forget_caches()
        for argv in (("q",), ("q", "--all")):
            with self.subTest(argv=argv):
                _, _, _, prompts = self.answered(NONE, *argv)
                self.assertIn("[%s]" % here[:8], prompts[0])
                self.assertNotIn("[%s]" % gone[:8], prompts[0])

    def test_a_session_withdrawn_from_this_machine_never_reaches_the_model(self):
        withdrawn = self.remote(alias="private-one", summary={**SUMMARY, "made": "WITHDRAWN-SECRET"})
        kept = self.remote(alias="kept-one")
        sminos.log_append(self.p, "beta/%s" % withdrawn, "unlisted", session=withdrawn, policyRev=1)
        sminos.forget_caches()
        for argv in (("q",), ("q", "--all")):
            with self.subTest(argv=argv):
                _, _, _, prompts = self.answered(NONE, *argv)
                self.assertIn("[%s]" % kept[:8], prompts[0])
                self.assertNotIn(withdrawn[:8], prompts[0])
                self.assertNotIn("WITHDRAWN-SECRET", prompts[0])

    def test_a_member_in_two_projects_is_one_entry_in_the_project_it_joined_last(self):
        """A move's dual membership: the row of the project it moved to, as a name resolves (one_per_session)."""
        other = self.project_of(self.repo("zz-destination"))
        sid = self.remote(alias="mover")
        time.sleep(0.01)
        w = "beta/%s" % sid
        sminos.log_append(other, w, "joined", session=sid, alias="mover", name_source="user", machine="beta",
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive")
        sminos.log_append(other, w, "state", session=sid, state="idle", machine="beta")
        sminos.forget_caches()
        _, _, _, prompts = self.answered(NONE, "q")
        self.assertEqual(prompts[0].count("[%s]" % sid[:8]), 1)
        self.assertIn("[%s] mover — %s on beta" % (sid[:8], other.name), prompts[0], "the destination's row")

    def test_a_thread_the_caller_has_left_is_in_the_corpus(self):
        """Only the caller's current thread is its own: the session that went on with a thread it left is not."""
        before = self.remote(alias="earlier")
        later = self.remote(alias="went-on")
        sminos.log_append(self.p, "beta/%s" % before, "retired", session=before, reason="continued", to=later)
        sminos.forget_caches()
        self.assertIn(before, next(m for m in sminos.members(self.p) if m.session == later).former)
        os.environ["CLAUDE_CODE_SESSION_ID"] = before
        _, _, _, prompts = self.answered(NONE, "q")
        self.assertIn("[%s] went-on" % later[:8], prompts[0])

    def test_every_field_is_capped_and_normalized(self):
        sid = self.remote(alias="long", branch="b" * 300, charge="x")
        sminos.log_append(self.p, "beta/%s" % sid, "in-charge", session=sid, text="L" * 5000, source="set")
        weird = self.remote(alias="weird", charge="line\x07 with\n\tbreaks   and  runs")
        sminos.forget_caches()
        _, _, _, prompts = self.answered(NONE, "q")
        prompt = prompts[0]
        self.assertIn("): " + "L" * 200 + "\n", prompt, "a 5,000-character set line reaches the corpus as 200")
        self.assertNotIn("L" * 201, prompt)
        self.assertIn("repo@" + "b" * 64 + ";", prompt, "a 300-character branch as 64")
        self.assertNotIn("b" * 65, prompt)
        self.assertIn("): line with breaks and runs\n", prompt)
        self.assertIn("[%s] weird" % weird[:8], prompt)
        entry = sminos.find_entry(self.p, next(m for m in sminos.members(self.p) if m.session == sid))
        self.assertTrue(entry.startswith("[%s] long — %s on beta; idle (interactive); repo@%s" % (
            sid[:8], self.p.name, "b" * 64)), entry)

    def test_a_question_that_tips_the_prompt_over_budget_starts_nothing(self):
        self.remote(alias="someone")
        _, _, _, prompts = self.answered(NONE, "short question")
        budget = len(prompts[0]) + 100
        with mock.patch.object(sminos, "FIND_PROMPT_MAX", budget):
            code, out, err, prompts = self.answered(NONE, "short question")
            self.assertEqual(code, 4, out + err)
            self.assertEqual(len(prompts), 1, "within the budget, asked")
            code, out, err, prompts = self.answered(NONE, "q" * 2500)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(prompts, [], "no call")
        self.assertEqual(err, "sminos: find: the prompt is %d characters, over find's budget of %d; narrow it with "
                              "list --org <words>\n" % (budget - 100 - len("short question") + 1000, budget))

    def test_the_question_is_capped_at_a_thousand_characters(self):
        self.remote(alias="someone")
        _, _, _, prompts = self.answered(NONE, "w" * 1500)
        self.assertTrue(prompts[0].endswith("Question: " + "w" * 1000), prompts[0][-50:])


# ---------------------------------------------------------------- acceptance 6: the answer


class Answer(Finding):
    def test_matches_print_in_the_model_order_an_unknown_and_a_repeat_dropped(self):
        live = self.remote(alias="ci-owner", summary=SUMMARY)
        stopped = self.remote(alias="sleeper", state="stopped", wake="woken")
        text = json.dumps({"matches": [{"short": stopped[:8], "why": "made the runner image\nlast week"},
                                       {"short": "deadbeef", "why": "made up"},
                                       {"short": live[:8], "why": "owns the CI"},
                                       {"short": stopped[:8], "why": "again"}], "note": ""})
        code, out, err, _ = self.answered("```json\n%s\n```" % text, "who runs CI")
        self.assertEqual(code, 0, out + err)
        lines = out.splitlines()
        first = next(i for i, x in enumerate(lines) if x.startswith("sleeper [%s]" % stopped[:8]))
        second = next(i for i, x in enumerate(lines) if x.startswith("ci-owner [%s]" % live[:8]))
        self.assertLess(first, second, "the model's order")
        self.assertIn("@beta", lines[first])
        self.assertIn(self.p.name, lines[first], "the row names its project")
        self.assertEqual(lines[first + 1], "  why: made the runner image last week")
        self.assertIn('  or message it, which wakes it: sminos say "@%s ..."' % stopped[:8], lines[first:second])
        self.assertEqual(lines[second + 1], "  why: owns the CI")
        self.assertRegex(lines[second + 2], r"^  doing \([^)]+\): %s$" % SUMMARY["doing"])
        self.assertEqual(lines[second + 3:second + 5], ["  made: %s" % SUMMARY["made"], "  next: %s" % SUMMARY["next"]])
        self.assertEqual(lines[second + 5], '  reach: sminos say "@%s ..."' % live[:8])
        self.assertEqual(out.count("sleeper ["), 1, "a repeat is dropped")
        self.assertNotIn("again", out)
        self.assertEqual(lines[-1], "(the model named 1 session that is not in the directory; left out)")

        code, out, err, _ = self.answered(text, "who runs CI", "--json")
        self.assertEqual(code, 0, err)
        d = json.loads(out)
        self.assertEqual(set(d), {"question", "corpus", "matches", "note", "dropped"})
        self.assertEqual(d["question"], "who runs CI")
        self.assertEqual([m["session"] for m in d["matches"]], [stopped, live])
        self.assertEqual(d["matches"][1]["why"], "owns the CI")
        self.assertEqual(d["matches"][1]["summary"], SUMMARY)
        self.assertEqual(d["matches"][1]["project"], self.p.name)
        self.assertNotIn("ownersProof", d["matches"][1])
        self.assertEqual(d["dropped"], 1)
        self.assertTrue(any(e.startswith("[%s] ci-owner" % live[:8]) for e in d["corpus"]))

    def test_a_retired_machines_member_under_all_says_it_cannot_be_reached(self):
        sid = self.remote(machine="gamma", alias="on-gamma")
        os.makedirs(os.path.join(os.environ["SMINOS_HOME"], "daemon"), exist_ok=True)
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "org.json"), {
            "projects": [], "machines": [{"name": "gamma", "retired": True}], "at": sminos.now()})
        sminos.forget_caches()
        code, out, err, _ = self.answered(json.dumps({"matches": [{"short": sid[:8], "why": "w"}]}), "q", "--all")
        self.assertEqual(code, 0, out + err)
        m = next(m for p, m in sminos.find_corpus("", True) if m.session == sid)
        self.assertIn("  " + sminos.retired_machine_words(m), out.splitlines())
        self.assertIn("gamma was retired", out)

    def test_the_note_is_one_clean_line_and_why_is_always_said(self):
        sid = self.remote(alias="someone")
        code, out, err, _ = self.answered(json.dumps({"matches": [{"short": sid[:8]}], "note": "a\x07b\n\tc"}), "q")
        self.assertEqual(code, 0, out + err)
        lines = out.splitlines()
        at = next(i for i, x in enumerate(lines) if x.startswith("someone [%s]" % sid[:8]))
        self.assertEqual(lines[at + 1], "  why:", "the why line, empty")
        self.assertIn("note: ab c", lines)

    def test_a_timeout_that_is_no_number_of_seconds_is_refused_before_any_call(self):
        self.remote(alias="someone")
        for value in ("abc", "0", "-3", "inf", "nan"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"SMINOS_FIND_TIMEOUT": value}):
                code, out, err = self.run_cli("find", "q")
                self.assertEqual(code, 1, out + err)
                self.assertEqual(err, "sminos: find: SMINOS_FIND_TIMEOUT is %r, not a number of seconds above 0\n"
                                 % value)
        self.assertEqual(self.calls(), [])

    def test_seven_valid_shorts_print_five(self):
        sids = [self.remote(alias="m%d" % i) for i in range(7)]
        code, out, err, _ = self.answered(json.dumps({"matches": [{"short": s[:8], "why": "w"} for s in sids]}), "q")
        self.assertEqual(code, 0, out + err)
        shown = [s for s in sids if "[%s]" % s[:8] in out]
        self.assertEqual(shown, sids[:5])

    def test_no_match_prints_the_note_and_exits_4(self):
        self.remote(alias="someone")
        code, out, err, _ = self.answered(json.dumps({"matches": [], "note": "nobody translates dictionaries"}), "q")
        self.assertEqual((code, out), (4, "no session matches: nobody translates dictionaries\n"), err)
        code, out, _, _ = self.answered(NONE, "q")
        self.assertEqual((code, out), (4, "no session matches\n"))
        code, out, _, _ = self.answered(json.dumps({"matches": [], "note": "none"}), "q", "--json")
        self.assertEqual(code, 4)
        d = json.loads(out)
        self.assertEqual((d["matches"], d["note"], d["dropped"]), ([], "none", 0))

    def test_only_unknown_shorts_is_no_match_and_says_so(self):
        self.remote(alias="someone")
        code, out, _, _ = self.answered(json.dumps({"matches": [{"short": "deadbeef"}, {"short": "feedface"}]}), "q")
        self.assertEqual(code, 4, out)
        self.assertIn("(the model named 2 sessions that are not in the directory; left out)", out)
        self.assertIn("no session matches", out)

    def test_a_malformed_answer_exits_1_with_its_reason(self):
        self.remote(alias="someone")
        for label, text in (("no matches list", "{}"), ("null matches", '{"matches": null}'),
                            ("no valid item", json.dumps({"matches": [1, {"why": "x"}]})),
                            ("no JSON object", "I could not find anyone.")):
            for json_flag in ((), ("--json",)):
                with self.subTest(label=label, json=bool(json_flag)):
                    code, out, err, _ = self.answered(text, "q", *json_flag)
                    self.assertEqual(code, 1, out + err)
                    self.assertEqual(out, "", "no match")
                    self.assertRegex(err, r"^sminos: find: .+; list --org <words> lists the sessions some words "
                                          r"match\n$")

    def test_a_crash_an_error_and_a_timeout_exit_1_with_the_reason(self):
        self.remote(alias="someone")
        for mode, said in (("crash", "the model call failed (exit 3): fake: the engine crashed"),
                           ("error", "the model call failed (exit 1)"),
                           ("sleep:5", "the model call timed out after 1s")):
            for json_flag in ((), ("--json",)):
                with self.subTest(mode=mode, json=bool(json_flag)):
                    with mock.patch.dict(os.environ, {"FAKE_CLAUDE_FIND_MODE": mode, "SMINOS_FIND_TIMEOUT": "1",
                                                      "FAKE_CLAUDE_FIND_RESULT": NONE}):
                        code, out, err = self.run_cli("find", "q", *json_flag)
                    self.assertEqual(code, 1, out + err)
                    self.assertEqual(out, "")
                    self.assertIn("sminos: find: " + said, err)
                    self.assertIn("; list --org <words> lists the sessions some words match", err)
        self.assertEqual(os.listdir(os.path.join(os.environ["SMINOS_HOME"], "internal")), [], "no marker is left")

    def test_parse_find_reads_the_first_object_and_checks_it(self):
        self.assertEqual(sminos.parse_find('noise {"matches": [{"short": "a1b2c3d4", "why": "w"}], "note": 3} {"x":1}'),
                         ([{"short": "a1b2c3d4", "why": "w"}], ""))
        self.assertEqual(sminos.parse_find('{"matches": [{"short": "a1b2c3d4", "why": 7}, "x"], "note": "n"}'),
                         ([{"short": "a1b2c3d4", "why": ""}], "n"))
        self.assertEqual(sminos.parse_find('{"matches": [{"short": "s", "why": "%s"}]}' % ("y" * 300))[0][0]["why"],
                         "y" * 200)
        for bad in ("", "[]", "{}", '{"matches": {}}', '{"matches": [{"short": 5}]}'):
            with self.subTest(bad=bad), self.assertRaises(sminos.FindFailed):
                sminos.parse_find(bad)


# ---------------------------------------------------------------- acceptance 6a: the gate


class Gate(Finding):
    def test_a_gate_closed_without_its_release_starts_nothing(self):
        r, w = os.pipe()
        proc = subprocess.Popen(["/bin/sh", "-c", FORK.GATE % (r, r), "sh", FAKE, "-p"], pass_fds=(r,),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.close(r)
        os.close(w)   # end of file: the parent went before the release
        proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.calls(), [], "the engine never started")

    def test_a_marker_that_cannot_be_written_kills_and_reaps_the_child(self):
        with open(os.path.join(os.environ["SMINOS_HOME"], "internal"), "w"):
            pass   # a file where the markers' directory goes
        started = []
        real = subprocess.Popen

        def popen(*a, **kw):
            started.append(real(*a, **kw))
            return started[-1]
        with mock.patch.object(FORK.subprocess, "Popen", popen):
            with self.assertRaises(FORK.ForkFailed) as e:
                FORK.ask_model("a question", timeout=30)
        self.assertIn("could not be marked internal", e.exception.reason)
        self.assertEqual(len(started), 1)
        self.assertIsNotNone(started[0].returncode, "reaped")
        time.sleep(0.2)
        self.assertEqual(self.calls(), [], "the engine never started")

    def test_the_headless_fork_runs_through_the_same_helper(self):
        sid, _ = self.session()
        self.reconcile()
        m = next(x for x in sminos.members(self.p) if x.session == sid)
        with mock.patch.dict(os.environ, {"FAKE_CLAUDE_FIND_RESULT": "From the fork."}):
            with mock.patch.object(FORK, "run_internal", wraps=FORK.run_internal) as helper:
                got = FORK.headless_fork(self.p, m, "the question", tools=False, cache=False, timeout=30)
        self.assertEqual((got.text, got.via), ("From the fork.", "headless fork"))
        self.assertEqual(helper.call_count, 1)
        c = self.calls()[0]
        self.assertTrue(c["marker"])
        self.assertEqual(c["env"]["internal"], "1")
        self.assertEqual(c["argv"][:4], ["-p", "--resume", sid, "--fork-session"])
        self.assertEqual(c["argv"][-1], "the question")


    def test_only_the_minted_transcript_is_removed_under_the_childs_config_dir(self):
        config = os.path.join(self.home, "other-config")
        unrelated = str(uuidlib.uuid4())
        kept = os.path.join(os.environ["HOME"], ".claude", "projects", "-elsewhere", unrelated + ".jsonl")
        os.makedirs(os.path.dirname(kept))
        with open(kept, "w") as f:
            f.write("{}\n")
        sminos.forget_caches()
        sminos.transcripts_now()
        self.assertEqual(sminos.transcript_now(unrelated), kept, "a transcript this machine knows")
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": config, "FAKE_CLAUDE_FIND_TRANSCRIPT": "1",
                                          "FAKE_CLAUDE_FIND_SESSION": unrelated, "FAKE_CLAUDE_FIND_RESULT": NONE}):
            FORK.ask_model("a question", timeout=30)
        minted = self.calls()[0]["argv"][self.calls()[0]["argv"].index("--session-id") + 1]
        self.assertEqual(self.calls()[0]["env"]["config"], config)
        self.assertEqual([os.path.basename(x) for x in sorted(
            os.path.join(r, n) for r, _, ns in os.walk(os.path.join(config, "projects")) for n in ns)], [],
            "the minted transcript (%s) is removed from the child's config dir" % minted)
        self.assertTrue(os.path.exists(kept), "the transcript of an id the result named is not find's to remove")

    def test_a_cleanup_that_fails_still_removes_the_marker(self):
        def cleanup(obj):
            raise OSError("cannot remove")
        with mock.patch.dict(os.environ, {"FAKE_CLAUDE_FIND_RESULT": NONE}), self.assertRaises(OSError):
            FORK.run_internal([FAKE, "-p"], cwd=self.home, env=dict(os.environ, SMNS_INTERNAL="1"), timeout=30,
                              stdin_text="q", cleanup=cleanup)
        self.assertTrue(self.calls()[0]["marker"], "it ran marked")
        self.assertEqual(os.listdir(os.path.join(os.environ["SMINOS_HOME"], "internal")), [], "and was unmarked")


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(BASE, ignore_errors=True)   # the fixtures' scratch, the stand-in's logs among it
