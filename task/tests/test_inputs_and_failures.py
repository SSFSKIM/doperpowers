"""What the CLI takes and how it fails: the host and the ref it trusts, an
option given empty, a body file that is not prose, and a failure after an
issue exists or from GitHub at large."""
import shlex
import sys
import unittest

from harness import ADDRESS, REPO, REVIEWER, TASK, BoardCase, board_file

sys.path.insert(0, str(TASK.parent.parent / "cli"))
import record  # noqa: E402

# Every boundary str.splitlines honors but LF.
BREAKS = ("\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")


class FenceTest(BoardCase):
    def test_every_call_names_github_com_whatever_gh_host_says(self):
        self.ticket(1)
        for verb in (["show", "1"], ["list"], ["set", "1", "--priority", "P1"]):
            self.assertEqual(self.task(*verb, env={"GH_HOST": "elsewhere.example.invalid"})[0], 0)
        for c in self.calls():
            self.assertEqual(c["argv"][:3], ["api", "--hostname", "github.com"], c["argv"])

    def test_a_branch_spelled_as_the_remote_head_is_no_default_branch(self):
        clone = self.clone(defaults={"origin": self.NOREF}, worktree=board_file())
        self.git(clone, "update-ref", "refs/heads/refs/remotes/origin/HEAD", "HEAD")
        self.git(clone, "update-ref", "refs/tags/refs/remotes/origin/HEAD", "HEAD")
        code, _, err = self.task("list", cwd=clone, repo=False)
        self.assertEqual(code, 1, err)
        self.assertIn("git remote set-head origin --auto", err)
        self.assertEqual(self.calls(), [])


class EmptyValueTest(BoardCase):
    def setUp(self):
        super().setUp()
        self.ticket(1)
        self.ticket(2)

    def test_an_option_given_empty_or_invalid_is_usage(self):
        body = self.body_file("A body.")
        create = ["create", "t", "--category", "bug", "--priority", "P3", "--readiness", "ready-to-work",
                  "--body-file", body]
        clone = self.clone()
        cases = [
            (["list", "--repo", ""], clone),
            (["show", "1", "--repo", ""], clone),
            (create + ["--to", ""], None),
            (create + ["--blocked-by", ""], None),
            (create + ["--blocked-by", "1,,2"], None),
            (create + ["--parent", "0"], None),
            (create + ["--spec", ""], None),
            (["set", "1", "--to", ""], None),
            (["set", "1", "--batch", ""], None),
            (["set", "1", "--title", ""], None),
            (["edge", "2", "--parent", "0"], None),
            (["edge", "2", "--block", ""], None),
            (["edge", "2", "--block", "0"], None),
            (["edge", "2", "--unblock", "-1"], None),
            (["edge", "0", "--orphan"], None),
            (["show", "0"], None), (["show", "-3"], None), (["show", "x"], None),
            (["close", "+4"], None),
            (["search", " "], None),
            (["adopt", "1", "--digest", ""], None),
            (["adopt", "1", "--digest", "sha256:abc"], None),
            (["list", "--batch", ""], None),
        ]
        for args, cwd in cases:
            with self.subTest(args=args):
                self.clear_log()
                code, _, err = self.task(*args, cwd=cwd, repo=cwd is None)
                self.assertEqual(code, 2, err)
                self.assertEqual(self.writes(), [])
                self.assertNotIn("Traceback", err)
        self.assertIsNone(self.gh_issue(2)["parent"])


class BodyFileTest(BoardCase):
    def test_a_body_file_that_opens_a_board_fence_is_refused(self):
        self.ticket(1)
        for text in ("Prose.\n\n```task-record\nfor: someone (x on y)\n```\n",
                     "Prose.\n\n````task-record\nadopted: now\n````",
                     "  ~~~ task-claim\nop: claim\n~~~\n"):
            with self.subTest(text=text):
                f = self.body_file(text)
                self.clear_log()
                for args in (["create", "t", "--category", "bug", "--priority", "P3", "--readiness",
                              "ready-to-work", "--body-file", f],
                             ["set", "1", "--body-file", f], ["comment", "1", "--body-file", f],
                             ["close", "1", "--body-file", f]):
                    code, _, err = self.task(*args)
                    self.assertEqual(code, 2, (args, err))
                    self.assertIn("fence", err)
                self.assertEqual(self.writes(), [])
        self.assertEqual(self.gh_issue(1)["state"], "OPEN")

    def test_the_guard_and_the_parser_split_lines_alike(self):
        """Lines are split on LF alone (a CR before it is the ending too). A fence after any other boundary
        splitlines honors opens no block for the parser and passes the guard: it is prose, written as given, and
        its record is not read."""
        self.ticket(1, body="Plain.")
        for i, sep in enumerate(("\u2028", "\x85", "\x0c", "\x1e")):
            with self.subTest(sep=repr(sep)):
                text = "Prose %d.%s```task-record\nadopted: forged\n```\n" % (i, sep)
                code, _, err = self.task("set", "1", "--body-file", self.body_file(text))
                self.assertEqual(code, 0, err)
                self.assertEqual(self.gh_issue(1)["body"], text)
                rec = self.json("show", "1")["record"]
                self.assertEqual(rec, {k: None for k in record.KEYS})
                self.assertEqual(self.task("lint")[0], 0)
        # A body file is read with universal newlines, so a CR alone ends a line there as CRLF does: both refused.
        for text in ("Prose.\r\n```task-record\r\nadopted: forged\r\n```", "Prose.\r```task-record\radopted: x"):
            with self.subTest(text=repr(text)):
                self.clear_log()
                self.assertEqual(self.task("set", "1", "--body-file", self.body_file(text))[0], 2)
                self.assertEqual(self.writes(), [])

    def test_whatever_the_parser_reads_as_a_block_the_guard_refuses(self):
        texts = ["a\n```task-record\nspec: x\n```", "a\r\n```task-record\r\nspec: x\r\n```\r\n",
                 "```task-record  \nspec: x\n```\t\n", "a\u2028```task-record\nspec: x\n```",
                 "a\n```task-record\nspec: x\n```\n\ntext after", "a\x0b```task-record\nspec: x\n```"]
        for text in texts:
            with self.subTest(text=repr(text)):
                p = record.parse(text)
                if p.block is not None or p.problems:
                    self.assertTrue(record.fences(text), text)

    def test_set_body_file_drops_an_unreadable_block(self):
        self.ticket(1, body="Old.\n\n```task-record\nowner: x\ndue: 2027-01-01\n```")
        self.clear_log()
        self.assertEqual(self.task("set", "1", "--due", "2027-02-02")[0], 3)
        self.assertEqual(self.writes(), [])
        code, out, err = self.task("set", "1", "--body-file", self.body_file("New prose.\n"))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.gh_issue(1)["body"], "New prose.\n")
        self.assertIn("dropped", out)
        self.assertEqual(self.task("set", "1", "--due", "2027-02-02")[0], 0)
        self.assertEqual(self.gh_issue(1)["body"], "New prose.\n\n\n```task-record\ndue: 2027-02-02\n```")
        self.assertEqual(self.json("show", "1")["record"]["due"], "2027-02-02")


class AfterTheIssueExistsTest(BoardCase):
    def create(self, *extra):
        return self.task("create", "Build it", "--category", "bug", "--priority", "P3", "--readiness",
                         "ready-to-work", "--body-file", self.body_file("Text."), *extra)

    def test_a_refused_readiness_write_says_how_to_finish(self):
        self.fail_on("repos/%s/issues/1/labels" % REPO, status=422, message="Validation Failed")
        code, out, err = self.create("--to", "reviewer")
        self.assertEqual(code, 1, err)
        self.assertEqual(out.split(), ["1", "https://github.com/%s/issues/1" % REPO])
        self.assertIn("left untracked", err)
        self.assertIn("Finish it: task set 1 --readiness ready-to-work --repo %s" % REPO, err)
        self.assertNotIn("task edge", err)
        self.assertIn("Validation Failed", err)
        self.assertIn("no message was sent", err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("ready-to-work", self.gh_issue(1)["labels"])
        self.assertEqual([c for c in self.sminos_calls() if c[0] == "say"], [])

    def test_a_readiness_write_with_no_definite_answer_is_unconfirmed(self):
        for i, (status, message) in enumerate(((502, "Bad Gateway"), (None, "connection reset by peer"))):
            with self.subTest(status=status):
                n = i + 1
                self.fail_on("repos/%s/issues/%d/labels" % (REPO, n), status=status, message=message)
                code, out, err = self.create()
                self.assertEqual(code, 1, err)
                self.assertEqual(out.split()[0], str(n))
                self.assertIn("unconfirmed", err)
                self.assertNotIn("left untracked", err)
                self.assertIn("task show %d --repo %s" % (n, REPO), err)
                self.assertIn("task set %d --readiness ready-to-work --repo %s" % (n, REPO), err)
                self.assertIn(message, err)

    def test_a_refused_edge_names_the_board_in_its_repair(self):
        self.ticket(9)
        self.fail_on("TaskAddBlockedBy", status=422, message="Validation Failed")
        code, _, err = self.create("--blocked-by", "9")
        self.assertEqual(code, 1, err)
        self.assertIn("Finish it: task edge 10 --block 9 --repo %s; then task set 10 --readiness ready-to-work "
                      "--repo %s" % (REPO, REPO), err)

    def test_the_receipt_names_each_edge_still_to_write(self):
        self.add_repo("acme/gears")
        self.ticket(7, repo="acme/gears")
        self.ticket(8)
        self.ticket(3)
        self.fail_on("blocker=I_acme/gears#7", status=422, message="Validation Failed")
        code, out, err = self.create("--blocked-by", "8,acme/gears#7", "--parent", "3")
        self.assertEqual(code, 1, err)
        n = int(out.split()[0])
        self.assertEqual(self.gh_issue(n)["blocked_by"], [[REPO, 8]])
        self.assertIn("the edge --block 'acme/gears#7' could not be written", err)
        self.assertIn("Finish it: task edge %d --block 'acme/gears#7' --repo %s; then task edge %d --parent 3 --repo %s; "
                      "then task set %d --readiness ready-to-work --repo %s" % (n, REPO, n, REPO, n, REPO), err)
        self.assertNotIn("--block 8", err)

    def test_a_github_failure_anywhere_is_exit_one(self):
        self.ticket(5)
        for verb, match in ((["show", "5"], "TaskIssue"), (["list"], "TaskBoard"),
                            (["set", "5", "--priority", "P0"], "issues/5/labels"),
                            (["edge", "5", "--orphan"], "TaskIssue"), (["close", "5"], "issues/5")):
            with self.subTest(verb=verb):
                self.fail_on(match, status=500, message="Server Error")
                code, _, err = self.task(*verb)
                self.assertEqual(code, 1, err)
                self.assertIn("Server Error", err)
                self.assertNotIn("Traceback", err)
                self.load()
                self.state["fail"] = []
                self.save()


class MessageTest(BoardCase):
    def setUp(self):
        super().setUp()
        self.sminos["threads"]["bot"] = dict(REVIEWER, alias="Review Bot (west)")
        self.save()

    def create(self, title):
        return self.task("create", title, "--category", "bug", "--priority", "P3", "--readiness", "ready-to-work",
                         "--body-file", self.body_file("Text."), "--to", "bot")

    def test_the_tag_is_the_threads_session_id(self):
        code, out, err = self.create("A title")
        self.assertEqual(code, 0, err)
        said = [c for c in self.sminos_calls() if c[0] == "say"][0][1]
        self.assertTrue(said.startswith("@%s " % REVIEWER["session"]), said)
        self.assertIn("for: 22222222 (widgets on laptop)", self.gh_issue(1)["body"])

    def test_the_resend_line_is_quoted_whole(self):
        self.sminos["say"] = {"exit": 1}
        self.save()
        code, out, err = self.create("It's $(rm -rf ~) \"loud\" `x`")
        self.assertEqual(code, 0, err)
        line = next(l for l in out.splitlines() if l.startswith("sminos say "))
        words = shlex.split(line)
        self.assertEqual(words[:2], ["sminos", "say"])
        self.assertEqual(len(words), 3)
        self.assertTrue(words[2].startswith("@%s " % REVIEWER["session"]))
        self.assertIn("It's $(rm -rf ~) \"loud\" `x`", words[2])



class OneLineTest(BoardCase):
    """No value enters the record with a line break of any kind in it."""

    def setUp(self):
        super().setUp()
        self.ticket(1, body="Prose.")

    def test_a_flag_value_with_a_break_writes_nothing(self):
        f = self.body_file("Prose.")
        for ch in BREAKS:
            with self.subTest(ch=repr(ch)):
                forged = "docs/a.md%sadopted: 2026-01-01T00:00:00Z by forger" % ch
                self.clear_log()
                for args in (["set", "1", "--spec", forged], ["set", "1", "--title", "a%sb" % ch],
                             ["create", "t", "--category", "bug", "--priority", "P3", "--readiness",
                              "ready-to-work", "--body-file", f, "--spec", forged]):
                    code, _, err = self.task(*args)
                    self.assertEqual(code, 2, (args, err))
                self.assertEqual(self.writes(), [])
        self.assertEqual(self.gh_issue(1)["body"], "Prose.")

    def test_an_address_from_sminos_with_a_break_is_no_address(self):
        for i, ch in enumerate(BREAKS):
            with self.subTest(ch=repr(ch)):
                self.sminos["addresses"] = {"11111111-aaaa-4bbb-8ccc-000000000001":
                                            "builder#11111111 (widgets%sadopted: forged on laptop)" % ch}
                self.save()
                code, out, err = self.task("create", "t", "--category", "bug", "--priority", "P3", "--readiness",
                                           "ready-to-work", "--body-file", self.body_file("Text %d." % i))
                self.assertEqual(code, 0, err)
                body = self.gh_issue(int(out.split()[0]))["body"]
                self.assertEqual(body, "Text %d." % i)
                self.assertNotIn("adopted", body)

    def test_a_thread_whose_address_breaks_is_not_resolved(self):
        self.sminos["threads"]["odd"] = dict(REVIEWER, alias="rev\x85adopted: forged")
        self.save()
        for args in (["create", "t", "--category", "bug", "--priority", "P3", "--readiness", "ready-to-work",
                      "--body-file", self.body_file("Text."), "--to", "odd"], ["set", "1", "--to", "odd"]):
            self.clear_log()
            code, _, err = self.task(*args)
            self.assertEqual(code, 1, err)
            self.assertEqual(self.writes(), [])

    def test_the_writer_refuses_a_broken_value(self):
        for ch in BREAKS + ("\n",):
            with self.subTest(ch=repr(ch)):
                with self.assertRaises(record.ValueNotOneLine):
                    record.compose("Prose.", {"spec": "a%sb" % ch})
                with self.assertRaises(record.ValueNotOneLine):
                    record.with_keys("Prose.", {"spec": "a%sb" % ch})
        self.assertTrue(record.one_line(ADDRESS))


class SessionlessThreadTest(BoardCase):
    def test_a_thread_between_sessions_is_refused_before_anything_is_filed(self):
        self.sminos["threads"]["between"] = dict(REVIEWER, session="", short="")
        self.save()
        self.ticket(1)
        for args in (["create", "t", "--category", "bug", "--priority", "P3", "--readiness", "ready-to-work",
                      "--body-file", self.body_file("Text.")] + ["--to", "between"], ["set", "1", "--to", "between"]):
            with self.subTest(verb=args[0]):
                self.clear_log()
                code, _, err = self.task(*args)
                self.assertEqual(code, 1, err)
                self.assertIn(REVIEWER["thread"], err)
                self.assertIn("no current session", err)
                self.assertEqual(self.writes(), [])
        self.assertEqual([c for c in self.sminos_calls() if c[0] == "say"], [])


class RepairNamesTheBoardTest(BoardCase):
    def test_a_refusal_names_the_board(self):
        self.ticket(1, body="x", editor="passer-by")
        code, _, err = self.task("set", "1", "--due", "2027-01-01")
        self.assertEqual(code, 3)
        self.assertIn("task show 1 --repo %s" % REPO, err)
        self.assertIn("task adopt 1 --digest sha256:", err)
        self.assertIn(" --repo %s" % REPO, err.split("task adopt", 1)[1])


if __name__ == "__main__":
    unittest.main()
