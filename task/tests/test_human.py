"""The human's board's verbs (B1's M3, the Task Board's D2 and X5): each runs
the matching `sminos task` verb, its arguments, standard input, output and
exit passed through, ahead of everything of the ticket board."""
import base64
import shlex
import signal
import subprocess
import unittest

from harness import SESSION, TASK, BoardCase

BODY = "Sign in to the cloud console.\n\n  Done when the dashboard loads: ✓ \n\tEOF is not the end\nlast line"

FORMS = [
    (["assign-human", "--class", "blocking", "--title", "Log in to the \"console\"", "--tag", "ops",
      "--due", "2027-01-05"],
     ["assign", "--class", "blocking", "--title", "Log in to the \"console\"", "--tag", "ops", "--due", "2027-01-05"]),
    (["assign-human", "--asker-agent", "a1b2c3d4e5f60718", "--asker-name", "reviewer", "--class", "needed",
      "--title", "x"],
     ["assign", "--asker-agent", "a1b2c3d4e5f60718", "--asker-name", "reviewer", "--class", "needed", "--title", "x"]),
    (["show", "t7"], ["show", "t7"]),
    (["show", "t12", "--json"], ["show", "t12", "--json"]),
    (["comment", "t7", "a short text; with $signs and 'quotes'"],
     ["comment", "t7", "a short text; with $signs and 'quotes'"]),
    (["comment", "t7", "--body-file", "-"], ["comment", "t7", "--body-file", "-"]),
    (["list", "--human"], ["list"]),
    (["list", "--human", "--mine", "--json"], ["list", "--mine", "--json"]),
    (["list", "--json", "--human", "--closed"], ["list", "--json", "--closed"]),
    (["revise", "t7", "--title", "T", "--no-tags"], ["revise", "t7", "--title", "T", "--no-tags"]),
    (["revise"], ["revise"]),
    (["withdraw", "t7", "--reason", "no longer needed"], ["withdraw", "t7", "--reason", "no longer needed"]),
    (["reopen", "t7", "--comment", "the console still asks for a login"],
     ["reopen", "t7", "--comment", "the console still asks for a login"]),
]


class HumanBoardCase(BoardCase):
    def answer(self, stdout="", stderr="", exit=0, sig=None):
        self.sminos["task"] = {"stdout": stdout, "stderr": stderr, "exit": exit}
        if sig:
            self.sminos["task"]["signal"] = sig
        self.save()

    def task_calls(self):
        return [e for e in self.sminos_calls(whole=True) if e["argv"][:1] == ["task"]]

    def stdin_of(self, entry):
        return base64.b64decode(entry["stdin"]).decode()


class PassThroughTest(HumanBoardCase):
    def test_each_form_runs_its_sminos_task_verb_with_its_arguments(self):
        for argv, expected in FORMS:
            with self.subTest(argv=argv):
                self.clear_log()
                code, _, err = self.task(*argv, repo=False)
                self.assertEqual(code, 0, err)
                calls = self.task_calls()
                self.assertEqual([c["argv"] for c in calls], [["task"] + expected])
                self.assertEqual(calls[0]["session"], SESSION)
                self.assertEqual(self.calls(), [], "the ticket board was looked at")

    def test_output_and_the_exits_sminos_shares_pass_through(self):
        for exit in (0, 2, 3):
            with self.subTest(exit=exit):
                self.answer(stdout='t7 blocking "Log in to the console"\n', stderr="said on stderr\n", exit=exit)
                code, out, err = self.task("assign-human", "--class", "blocking", "--title", "x", repo=False)
                self.assertEqual((code, out, err), (exit, 't7 blocking "Log in to the console"\n', "said on stderr\n"))

    def test_any_other_exit_is_1(self):
        for exit, sig in ((1, None), (4, None), (5, None), (75, None), (0, signal.SIGTERM)):
            with self.subTest(exit=exit, signal=sig):
                self.answer(stdout="partial\n", stderr="the store is busy\n", exit=exit, sig=sig)
                code, out, err = self.task("show", "t7", repo=False)
                self.assertEqual(code, 1)
                self.assertEqual(out, "partial\n")
                self.assertIn("the store is busy\n", err)

    def test_standard_input_reaches_sminos_unchanged(self):
        for argv in (["assign-human", "--class", "needed", "--title", "x", "--body-file", "-"],
                     ["comment", "t3", "--body-file", "-"], ["revise", "t3", "--body-file", "-"]):
            with self.subTest(argv=argv[0]):
                self.clear_log()
                code, _, err = self.task(*argv, repo=False, input=BODY)
                self.assertEqual(code, 0, err)
                self.assertEqual(self.stdin_of(self.task_calls()[0]), BODY)

    def test_no_sminos_exits_1_saying_sminos_keeps_the_human_board(self):
        for where in ("", str(self.tmp / "no-such-sminos")):
            for argv in (["assign-human", "--class", "blocking", "--title", "x"], ["show", "t7"],
                         ["list", "--human"], ["reopen", "t7", "--comment", "y"]):
                with self.subTest(where=where, argv=argv[0]):
                    code, out, err = self.task(*argv, repo=False, env={"TASK_SMINOS": where})
                    self.assertEqual(code, 1)
                    self.assertEqual(out, "")
                    self.assertIn("human's board is kept by sminos", err)
                    self.assertIn("not installed", err)


class OutsideTheTicketBoardTest(HumanBoardCase):
    def heredoc(self, cwd):
        """`task assign-human` with a heredoc body, then `task show`, as one shell runs them."""
        script = ("%s assign-human --class blocking --title 'Log in to the console' --body-file - <<'EOF'\n%s\nEOF\n"
                  "%s show t7\n" % (shlex.quote(str(TASK)), BODY, shlex.quote(str(TASK))))
        return subprocess.run(["bash", "-c", script], cwd=str(cwd), env=self.env(), capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60)

    def test_in_a_directory_that_is_no_repository_and_a_clone_with_no_board(self):
        self.answer(stdout="ok\n")
        no_board = self.clone("no-board", defaults={"origin": None})
        for cwd in (self.outside, no_board):
            with self.subTest(cwd=cwd.name):
                self.clear_log()
                done = self.heredoc(cwd)
                self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "ok\nok\n", ""))
                calls = self.task_calls()
                self.assertEqual([c["argv"][:2] for c in calls], [["task", "assign"], ["task", "show"]])
                self.assertEqual(self.stdin_of(calls[0]), BODY + "\n")  # a heredoc ends its last line
                self.assertEqual(self.calls(), [])

    def test_a_ticket_number_is_still_the_ticket_board(self):
        self.ticket(7)
        for argv in (["show", "7"], ["comment", "7", "--body-file", self.body_file("a note")], ["list"]):
            with self.subTest(argv=argv[0]):
                self.clear_log()
                code, _, err = self.task(*argv)
                self.assertEqual(code, 0, err)
                self.assertTrue(self.calls())
                self.assertEqual(self.task_calls(), [])

    def test_a_prefix_argparse_would_take_for_human_is_the_human_board(self):
        self.ticket(7)
        for flag in ("--hu", "--hum", "--huma"):
            with self.subTest(flag=flag):
                self.clear_log()
                code, _, err = self.task("list", flag, "--json")
                self.assertEqual(code, 0, err)
                self.assertEqual([c["argv"] for c in self.task_calls()], [["task", "list", "--json", "--repo",
                                                                           "acme/widgets"]])
                self.assertEqual(self.calls(), [])

    def test_a_task_id_not_first_or_not_whole_is_no_human_form(self):
        for argv in (["show", "t07"], ["show", "t7x"], ["show", "T7"], ["comment", "--body-file", "f", "t7"]):
            with self.subTest(argv=argv):
                self.clear_log()
                self.assertEqual(self.task(*argv, repo=False)[0], 2)
                self.assertEqual(self.task_calls(), [])

    def test_the_human_board_verbs_given_a_ticket_number_exit_2(self):
        for argv in (["revise", "7", "--title", "x"], ["withdraw", "7"], ["reopen", "7", "--comment", "y"]):
            with self.subTest(argv=argv[0]):
                self.clear_log()
                code, _, err = self.task(*argv, repo=False)
                self.assertEqual(code, 2)
                self.assertIn("t<n>", err)
                self.assertEqual(self.sminos_calls(), [])
                self.assertEqual(self.calls(), [])

    def test_a_human_verbs_help_is_sminos_tasks_named_for_the_verb_task_runs(self):
        self.answer(stdout="usage: sminos task assign [-h] --class ...\n")
        code, out, _ = self.task("assign-human", "--help", repo=False)
        self.assertEqual(code, 0)
        self.assertEqual([c["argv"] for c in self.task_calls()], [["task", "assign", "--help"]])
        self.assertEqual(out, "task assign-human runs sminos task assign, whose help this is:\n"
                              "usage: sminos task assign [-h] --class ...\n")
        for argv in (["show", "t7", "--help"], ["revise", "-h"], ["assign-human", "--title", "x", "--", "--help"]):
            with self.subTest(argv=argv):
                self.clear_log()
                self.answer(stdout="usage\n")
                code, out, _ = self.task(*argv, repo=False)
                self.assertEqual((code, out), (0, "usage\n"))

    def test_help_lists_the_human_board_verbs_as_built(self):
        code, out, _ = self.task("--help", repo=False)
        self.assertEqual(code, 0)
        for verb in ("assign-human", "revise", "withdraw", "reopen"):
            self.assertIn(verb, out)
        self.assertNotIn("not built", out)
        self.assertIn("task <verb> --help", out)


if __name__ == "__main__":
    unittest.main()
