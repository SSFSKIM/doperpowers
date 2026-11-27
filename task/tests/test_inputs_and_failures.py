"""What the CLI takes and how it fails: the host and the ref it trusts, an
option given empty, a body file that is not prose, and a failure after an
issue exists or from GitHub at large."""
import shlex
import unittest

from harness import REPO, REVIEWER, BoardCase, board_file


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

    def test_a_failed_readiness_write_says_how_to_finish(self):
        self.fail_on("repos/%s/issues/1/labels" % REPO, status=502, message="Bad Gateway")
        code, out, err = self.create("--to", "reviewer")
        self.assertEqual(code, 1, err)
        self.assertEqual(out.split(), ["1", "https://github.com/%s/issues/1" % REPO])
        self.assertIn("untracked", err)
        self.assertIn("task set 1 --readiness ready-to-work", err)
        self.assertIn("Bad Gateway", err)
        self.assertIn("no message was sent", err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("ready-to-work", self.gh_issue(1)["labels"])
        self.assertEqual([c for c in self.sminos_calls() if c[0] == "say"], [])

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


if __name__ == "__main__":
    unittest.main()
