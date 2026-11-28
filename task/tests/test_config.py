"""Acceptance 1 (the configuration is the default branch's, the repository
the designated remote's) and 7 (the seam)."""
import json
import unittest

from harness import REPO, TASK, BoardCase, board_file

A, B = REPO, "upstream-co/widgets"


class ConfigurationTest(BoardCase):
    def setUp(self):
        super().setUp()
        self.add_repo(B)
        self.ticket(1)
        self.issue(1, repo=B, labels=["ready-to-work", "expected"])
        self.save()

    def assert_names_only(self, repo):
        calls = self.calls()
        self.assertTrue(calls, "no call was logged")
        for c in calls:
            argv = c["argv"]
            self.assertEqual(argv[:3], ["api", "--hostname", "github.com"], argv)
            joined = " ".join(argv)
            self.assertNotIn("{owner}", joined)
            self.assertNotIn("{repo}", joined)
            path = self.path_of(c)
            if path == "user":
                continue
            if path == "graphql":
                fields = dict(a.split("=", 1) for a in argv if "=" in a and not a.startswith("query="))
                if "owner" in fields:
                    self.assertEqual("%s/%s" % (fields["owner"], fields["name"]), repo, argv)
                else:
                    self.assertTrue(all(repo in v for k, v in fields.items() if k != "replace"), argv)
            elif path.startswith("search/"):
                self.assertIn("repo:%s" % repo, joined)
            else:
                self.assertTrue(path.startswith("repos/%s/" % repo), argv)

    def run_board_verbs(self, cwd):
        self.assertEqual(self.task("list", cwd=cwd, repo=False)[0], 0)
        self.assertEqual(self.task("show", "1", cwd=cwd, repo=False)[0], 0)
        code, _, err = self.task("comment", "1", "--body-file", self.body_file("a note"), cwd=cwd, repo=False)
        self.assertEqual(code, 0, err)

    def test_the_default_branch_file_decides_whatever_the_working_tree_says(self):
        for name, worktree in (("says-gh", board_file("gh")), ("names-b", board_file("task", B)),
                               ("absent", None)):
            with self.subTest(worktree=name):
                self.clear_log()
                clone = self.clone(name, worktree=worktree)
                self.run_board_verbs(clone)
                self.assert_names_only(A)
                self.assertTrue(self.gh_issue(1)["comments"])

    def test_a_linked_worktree_on_an_old_branch_reads_the_shared_ref(self):
        clone = self.clone(worktree=board_file("gh"))
        linked = self.tmp / "linked"
        self.git(clone, "worktree", "add", "-q", "-b", "before-the-flip", str(linked))
        self.run_board_verbs(linked)
        self.assert_names_only(A)

    def test_a_working_tree_that_says_task_does_not_make_a_board(self):
        for name, default in (("default-gh", board_file("gh")), ("default-none", None)):
            with self.subTest(default=name):
                self.clear_log()
                clone = self.clone(name, defaults={"origin": default}, worktree=board_file())
                for verb in (["list"], ["show", "1"], ["lint"], ["comment", "1", "--body-file", self.body_file("x")],
                             ["set", "1", "--priority", "P1"], ["search", "x"]):
                    code, _, err = self.task(*verb, cwd=clone, repo=False)
                    self.assertEqual(code, 1, (verb, err))
                    self.assertIn("refs/remotes/origin/HEAD", err)
                    self.assertIn("gh" if default else "no .doperpowers/board.json", err)
                self.assertEqual(self.calls(), [])

    def test_a_file_naming_another_repository_is_refused(self):
        clone = self.clone(remotes={"origin": "https://github.com/%s.git" % A,
                                    "upstream": "https://github.com/%s.git" % B},
                           defaults={"origin": board_file("task", B), "upstream": board_file("task", B)})
        code, _, err = self.task("list", cwd=clone, repo=False)
        self.assertEqual(code, 1)
        self.assertIn(A, err)
        self.assertIn(B, err)
        self.assertEqual(self.calls(), [])

    def test_task_remote_designates_another_remote(self):
        clone = self.clone(remotes={"origin": "git@github.com:%s.git" % A,
                                    "upstream": "ssh://git@github.com/%s" % B},
                           defaults={"origin": board_file("task", B), "upstream": board_file("task", B)})
        self.git(clone, "config", "task.remote", "upstream")
        self.run_board_verbs(clone)
        self.assert_names_only(B)

    def test_no_remote_tracking_default_branch(self):
        clone = self.clone(defaults={"origin": self.NOREF})
        code, _, err = self.task("list", cwd=clone, repo=False)
        self.assertEqual(code, 1)
        self.assertIn("refs/remotes/origin/HEAD", err)
        self.assertIn("git remote set-head origin --auto", err)
        self.assertEqual(self.calls(), [])

    def test_the_repair_quotes_the_remote_for_a_shell(self):
        clone = self.clone(remotes={"up$tream;x": "https://github.com/%s.git" % A},
                           defaults={"up$tream;x": self.NOREF})
        self.git(clone, "config", "task.remote", "up$tream;x")
        code, _, err = self.task("list", cwd=clone, repo=False)
        self.assertEqual(code, 1)
        self.assertIn("git remote set-head 'up$tream;x' --auto", err)

    def test_a_remote_that_is_no_github_repository(self):
        for url in ("https://gitlab.example.com/acme/widgets.git", "/srv/git/widgets.git"):
            with self.subTest(url=url):
                clone = self.clone(url.split("/")[2] or "local", remotes={"origin": url})
                code, _, err = self.task("list", cwd=clone, repo=False)
                self.assertEqual(code, 1)
                self.assertIn(url, err)
                self.assertEqual(self.calls(), [])

    def test_url_forms_git_writes(self):
        for i, url in enumerate(("https://github.com/acme/widgets", "https://github.com/Acme/Widgets.git",
                                 "git@github.com:acme/widgets", "ssh://git@github.com/acme/widgets.git")):
            with self.subTest(url=url):
                clone = self.clone("form-%d" % i, remotes={"origin": url})
                self.assertEqual(self.task("list", cwd=clone, repo=False)[0], 0)

    def test_repo_flag_inside_and_outside_a_clone(self):
        clone = self.clone(remotes={"origin": "https://github.com/%s.git" % A,
                                    "upstream": "https://github.com/%s.git" % B},
                           defaults={"origin": board_file(), "upstream": board_file("task", B)})
        for cwd in (clone, self.outside):
            with self.subTest(cwd=cwd.name):
                self.clear_log()
                self.assertEqual(self.task("list", cwd=cwd, repo=B)[0], 0)
                self.assertEqual(self.task("show", "1", cwd=cwd, repo=B)[0], 0)
                self.assert_names_only(B)
                contents = [c for c in self.calls() if "contents/.doperpowers/board.json" in self.path_of(c)]
                self.assertEqual([self.path_of(c) for c in contents][:1],
                                 ["repos/%s/contents/.doperpowers/board.json" % B])

    def test_repo_flag_reads_that_repository_binding(self):
        self.state["repos"][B]["files"][".doperpowers/board.json"] = board_file("gh", B)
        self.save()
        code, _, err = self.task("list", repo=B)
        self.assertEqual(code, 1)
        self.assertIn("gh", err)
        self.state["repos"][B]["files"] = {}
        self.save()
        code, _, err = self.task("list", repo=B)
        self.assertEqual(code, 1)
        self.assertIn("no .doperpowers/board.json", err)

    def test_outside_a_clone_without_repo(self):
        code, _, err = self.task("list", repo=False)
        self.assertEqual(code, 1)
        self.assertIn("--repo", err)
        self.assertEqual(self.calls(), [])

    def test_help_and_version_outside_a_repository(self):
        code, out, _ = self.task("--help", repo=False)
        self.assertEqual(code, 0)
        self.assertIn("create", out)
        code, out, _ = self.task("--version", repo=False)
        self.assertEqual(code, 0)
        version = json.loads((TASK.parent.parent / ".claude-plugin" / "plugin.json").read_text())["version"]
        self.assertEqual(out.strip(), "task %s (the task plugin of the doperpowers marketplace)" % version)
        self.assertEqual(self.calls(), [])


class SeamTest(BoardCase):
    """The seam's own case went with the human's board's verbs (test_human.py)."""

    def test_an_unknown_verb_is_usage(self):
        self.assertEqual(self.task("frobnicate", repo=False)[0], 2)


if __name__ == "__main__":
    unittest.main()
