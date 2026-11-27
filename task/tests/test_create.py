"""Acceptance 2: create."""
import unittest

from harness import ADDRESS, REPO, REVIEWER, REVIEWER_ADDRESS, BoardCase

RECORD_OPEN = "```task-record"


class CreateTest(BoardCase):
    def create(self, *extra, body="Build the widget.\n", session=None, **kw):
        args = ["create", "Build the widget", "--category", "enhancement", "--priority", "P2",
                "--readiness", "ready-to-work", "--body-file", self.body_file(body)] + list(extra)
        if session is not None:
            return self.task(*args, session=session, **kw)
        return self.task(*args, **kw)

    def test_required_options_are_usage(self):
        full = {"--category": "bug", "--priority": "P3", "--readiness": "ready-to-work",
                "--body-file": self.body_file("text")}
        for missing in full:
            with self.subTest(missing=missing):
                args = ["create", "a title"]
                for k, v in full.items():
                    if k != missing:
                        args += [k, v]
                self.assertEqual(self.task(*args)[0], 2)
        self.assertEqual(self.task("create", "t", "--category", "bug", "--priority", "P3", "--readiness",
                                   "ready-to-work", "--body-file", self.body_file("  \n"))[0], 2)
        for bad in (["--category", "chore"], ["--priority", "P4"], ["--readiness", "in-progress"],
                    ["--horizon", "soon"], ["--due", "2027-13-01"], ["--batch", "two words"]):
            with self.subTest(bad=bad):
                self.assertEqual(self.create(*bad)[0], 2)
        self.assertEqual(self.writes(), [])

    def test_labels_and_record(self):
        code, out, err = self.create()
        self.assertEqual(code, 0, err)
        n, url = out.split()
        self.assertEqual(url, "https://github.com/%s/issues/%s" % (REPO, n))
        it = self.gh_issue(int(n))
        self.assertEqual(sorted(it["labels"]), ["enhancement", "expected", "priority:P2", "ready-to-work"])
        self.assertTrue(it["body"].startswith("Build the widget."))
        self.assertTrue(it["body"].rstrip().endswith("```"))
        self.assertIn("%s\nregistered-by: %s\n```" % (RECORD_OPEN, ADDRESS), it["body"])

    def test_horizon_batch_due_spec(self):
        code, out, err = self.create("--horizon", "undecided", "--batch", "polish", "--due", "2027-01-05",
                                     "--spec", "docs/specs/widget.md@abc123")
        self.assertEqual(code, 0, err)
        it = self.gh_issue(int(out.split()[0]))
        self.assertIn("undecided", it["labels"])
        self.assertNotIn("expected", it["labels"])
        self.assertIn("batch:polish", it["labels"])
        self.assertTrue(it["body"].endswith("registered-by: %s\ndue: 2027-01-05\nspec: docs/specs/widget.md@abc123\n```"
                                            % ADDRESS), it["body"])

    def test_new_labels_are_created_with_their_axis(self):
        self.assertEqual(self.create("--batch", "polish")[0], 0)
        labels = self.load()["repos"][REPO]["labels"]
        for name, axis in (("ready-to-work", "readiness"), ("expected", "horizon"), ("priority:P2", "priority"),
                           ("enhancement", "category"), ("batch:polish", "batch")):
            self.assertIn(axis, labels[name]["description"], name)

    def test_no_session_no_record(self):
        code, out, err = self.create(session="")
        self.assertEqual(code, 0, err)
        it = self.gh_issue(int(out.split()[0]))
        self.assertNotIn(RECORD_OPEN, it["body"])
        self.assertEqual(it["body"], "Build the widget.\n")
        self.assertEqual(self.sminos_calls(), [])

    def test_no_address_from_sminos_no_record(self):
        self.sminos["addresses"] = {}
        self.save()
        code, out, err = self.create()
        self.assertEqual(code, 0, err)
        self.assertNotIn(RECORD_OPEN, self.gh_issue(int(out.split()[0]))["body"])

    def test_edges_then_readiness_last(self):
        self.ticket(1)
        self.ticket(2)
        self.ticket(3, repo=REPO)
        code, out, err = self.create("--blocked-by", "1,2", "--parent", "3", "--horizon", "planned")
        self.assertEqual(code, 0, err)
        n = int(out.split()[0])
        it = self.gh_issue(n)
        self.assertEqual(it["blocked_by"], [[REPO, 1], [REPO, 2]])
        self.assertEqual(it["parent"], [REPO, 3])
        last = self.writes()[-1]
        method, path, data = self.rest(last)
        self.assertEqual((method, path, data), ("POST", "repos/%s/issues/%d/labels" % (REPO, n),
                                                {"labels": ["ready-to-work"]}))
        create = next(self.rest(c) for c in self.writes() if self.rest(c)[1] == "repos/%s/issues" % REPO)
        self.assertNotIn("ready-to-work", create[2]["labels"])

    def test_cross_repository_blocker(self):
        self.add_repo("acme/gears")
        self.ticket(7, repo="acme/gears")
        code, out, err = self.create("--blocked-by", "acme/gears#7")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.gh_issue(int(out.split()[0]))["blocked_by"], [["acme/gears", 7]])

    def test_a_refused_edge_leaves_the_issue_untracked(self):
        self.ticket(1)
        self.fail_on("TaskAddBlockedBy", message="Validation Failed")
        code, out, err = self.create("--blocked-by", "1")
        self.assertEqual(code, 1)
        n = int(out.split()[0])
        it = self.gh_issue(n)
        self.assertNotIn("ready-to-work", it["labels"])
        self.assertIn("untracked", err)
        self.assertIn("Validation Failed", err)

    def test_to_a_thread_records_for_and_sends_one_message(self):
        code, out, err = self.create("--to", "reviewer")
        self.assertEqual(code, 0, err)
        n = int(out.split()[0])
        self.assertIn("for: %s\n" % REVIEWER_ADDRESS, self.gh_issue(n)["body"])
        says = [c for c in self.sminos_calls() if c[0] == "say"]
        self.assertEqual(len(says), 1)
        self.assertTrue(says[0][1].startswith("@%s " % REVIEWER["session"]), says)
        self.assertIn("%s#%d" % (REPO, n), says[0][1])
        self.assertIn("--thread=reviewer", [a for c in self.sminos_calls() for a in c])

    def test_a_failed_send_prints_the_line_to_send(self):
        self.sminos["say"] = {"exit": 1}
        self.save()
        code, out, err = self.create("--to", "reviewer")
        self.assertEqual(code, 0, err)
        n = int(out.splitlines()[0].split()[0])
        self.assertIn("for: %s" % REVIEWER_ADDRESS, self.gh_issue(n)["body"])
        self.assertIn("sminos say '@%s " % REVIEWER["session"], out)

    def test_to_an_unknown_name_creates_nothing(self):
        for name, answer in (("nobody", None), ("broken", {"exit": 1, "said": "boom"}),
                             ("half", {"thread": "x"})):
            with self.subTest(name=name):
                if answer is not None:
                    self.sminos["threads"][name] = answer
                    self.save()
                code, _, err = self.create("--to", name)
                self.assertEqual(code, 1, err)
                self.assertEqual(self.writes(), [])

    def test_an_unnamed_thread_is_addressed_by_its_short(self):
        self.sminos["threads"]["plain"] = dict(REVIEWER, alias="")
        self.save()
        code, out, err = self.create("--to", "plain")
        self.assertEqual(code, 0, err)
        self.assertIn("for: 22222222 (widgets on laptop)\n", self.gh_issue(int(out.split()[0]))["body"])
        self.assertTrue([c for c in self.sminos_calls() if c[0] == "say"][0][1].startswith("@%s " % REVIEWER["session"]))


if __name__ == "__main__":
    unittest.main()
