"""Acceptance 3: set, edge and close."""
import unittest

from harness import ADDRESS, REPO, REVIEWER_ADDRESS, BoardCase

BLOCK = "```task-record\nregistered-by: %s\nspec: docs/specs/a.md\n```" % ADDRESS


def readiness(labels):
    return [l for l in labels if l in ("ready-to-work", "need-design", "need-input")]


def horizon(labels):
    return [l for l in labels if l in ("planned", "expected", "undecided")]


class SetTest(BoardCase):
    def test_any_sequence_leaves_one_readiness_and_one_horizon(self):
        self.ticket(5, extra=["claimed", "tech-debt"])
        steps = [["--readiness", "need-design"], ["--horizon", "undecided"],
                 ["--readiness", "need-input", "--horizon", "planned"], ["--readiness", "need-input"],
                 ["--readiness", "ready-to-work", "--horizon", "expected", "--priority", "P1"],
                 ["--category", "spike"], ["--batch", "one"], ["--batch", "two"], ["--no-batch"]]
        for step in steps:
            with self.subTest(step=step):
                code, _, err = self.task("set", "5", *step)
                self.assertEqual(code, 0, err)
                labels = self.gh_issue(5)["labels"]
                self.assertEqual(len(readiness(labels)), 1, labels)
                self.assertEqual(len(horizon(labels)), 1, labels)
                self.label_writes(5)  # fails on any replacement of the label set
        labels = self.gh_issue(5)["labels"]
        self.assertEqual(sorted(labels), ["claimed", "expected", "priority:P1", "ready-to-work", "spike",
                                          "tech-debt"])

    def test_a_ticket_with_two_readiness_labels_ends_with_one(self):
        self.ticket(5, extra=["need-design"])
        self.assertEqual(self.task("set", "5", "--readiness", "need-input")[0], 0)
        self.assertEqual(readiness(self.gh_issue(5)["labels"]), ["need-input"])

    def test_single_label_writes(self):
        self.ticket(5)
        self.clear_log()
        self.assertEqual(self.task("set", "5", "--readiness", "need-design")[0], 0)
        self.assertEqual(self.label_writes(5), [("+", "need-design"), ("-", "ready-to-work")])

    def test_setting_a_readiness_takes_status_labels_off(self):
        self.issue(5, labels=["status:deferred", "status:in-design", "priority:P3", "bug"])
        self.assertEqual(self.task("set", "5", "--readiness", "need-design", "--horizon", "undecided")[0], 0)
        self.assertEqual(sorted(self.gh_issue(5)["labels"]), ["bug", "need-design", "priority:P3", "undecided"])

    def test_body_file_keeps_the_block_byte_for_byte(self):
        self.ticket(5, body="Old text.\n\n" + BLOCK + "\n")
        self.clear_log()
        code, _, err = self.task("set", "5", "--body-file", self.body_file("New text,\nin two lines.\n"))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.gh_issue(5)["body"], "New text,\nin two lines.\n\n" + BLOCK + "\n")
        reads = [i for i, c in enumerate(self.calls()) if "query TaskIssue(" in " ".join(c["argv"])]
        write = next(i for i, c in enumerate(self.calls()) if self.is_write(c))
        self.assertTrue(reads and reads[-1] < write)

    def test_due_and_spec_change_only_the_block(self):
        self.ticket(5, body="Text stays.\r\nExactly.\n\n" + BLOCK)
        self.assertEqual(self.task("set", "5", "--due", "2027-02-01")[0], 0)
        self.assertEqual(self.gh_issue(5)["body"], "Text stays.\r\nExactly.\n\n```task-record\nregistered-by: %s\n"
                         "spec: docs/specs/a.md\ndue: 2027-02-01\n```" % ADDRESS)
        self.assertEqual(self.task("set", "5", "--spec", "docs/specs/c.md", "--no-due")[0], 0)
        self.assertEqual(self.gh_issue(5)["body"], "Text stays.\r\nExactly.\n\n```task-record\nregistered-by: %s\n"
                         "spec: docs/specs/c.md\n```" % ADDRESS)
        self.assertEqual(self.task("set", "5", "--no-spec")[0], 0)
        self.assertEqual(self.task("set", "5", "--to", "reviewer")[0], 0)
        self.assertEqual(self.gh_issue(5)["body"], "Text stays.\r\nExactly.\n\n```task-record\nregistered-by: %s\n"
                         "for: %s\n```" % (ADDRESS, REVIEWER_ADDRESS))
        self.assertEqual([c for c in self.sminos_calls() if c[0] == "say"], [])

    def test_a_block_is_added_and_dropped(self):
        self.ticket(5, body="Plain.")
        self.assertEqual(self.task("set", "5", "--due", "2027-02-01")[0], 0)
        self.assertEqual(self.gh_issue(5)["body"], "Plain.\n\n```task-record\ndue: 2027-02-01\n```")
        self.assertEqual(self.task("set", "5", "--no-due")[0], 0)
        self.assertEqual(self.gh_issue(5)["body"], "Plain.")

    def test_a_record_change_keeps_every_byte_of_the_prose(self):
        for prose in ("Para.\n", "Para.", "Para.\n\n", "  indented\r\n  lines  "):
            with self.subTest(prose=prose):
                self.ticket(5, body=prose)
                self.assertEqual(self.task("set", "5", "--due", "2027-02-01")[0], 0)
                self.assertEqual(self.gh_issue(5)["body"], prose + "\n\n```task-record\ndue: 2027-02-01\n```")
                self.assertEqual(self.task("set", "5", "--spec", "docs/a.md")[0], 0)
                self.assertEqual(self.task("set", "5", "--no-due", "--no-spec")[0], 0)
                self.assertEqual(self.gh_issue(5)["body"], prose)

    def test_an_unchanged_block_writes_nothing(self):
        self.ticket(5, body="Plain.")
        self.clear_log()
        self.assertEqual(self.task("set", "5", "--no-due")[0], 0)
        self.assertEqual(self.writes(), [])

    def test_to_unresolved_writes_nothing(self):
        self.ticket(5)
        self.clear_log()
        self.assertEqual(self.task("set", "5", "--to", "nobody", "--priority", "P0")[0], 1)
        self.assertEqual(self.writes(), [])

    def test_title(self):
        self.ticket(5)
        self.assertEqual(self.task("set", "5", "--title", "A better title")[0], 0)
        self.assertEqual(self.gh_issue(5)["title"], "A better title")

    def test_nothing_to_set_is_usage(self):
        self.ticket(5)
        self.assertEqual(self.task("set", "5")[0], 2)
        self.assertEqual(self.task("set", "5", "--due", "x", "--no-due")[0], 2)


class EdgeTest(BoardCase):
    def setUp(self):
        super().setUp()
        for n in (1, 2, 3, 4):
            self.ticket(n)

    def test_block_and_unblock(self):
        self.assertEqual(self.task("edge", "2", "--block", "1")[0], 0)
        self.assertEqual(self.gh_issue(2)["blocked_by"], [[REPO, 1]])
        self.assertEqual(self.task("edge", "2", "--unblock", "1")[0], 0)
        self.assertEqual(self.gh_issue(2)["blocked_by"], [])

    def test_a_self_edge_is_refused(self):
        self.clear_log()
        self.assertEqual(self.task("edge", "2", "--block", "2")[0], 3)
        self.assertEqual(self.task("edge", "2", "--block", "%s#2" % REPO)[0], 3)
        self.assertEqual(self.task("edge", "2", "--parent", "2")[0], 3)
        self.assertEqual(self.writes(), [])

    def test_a_cycle_is_refused(self):
        self.issue(2, labels=["ready-to-work"], blocked_by=[1])
        self.issue(3, labels=["ready-to-work"], blocked_by=[2])
        self.clear_log()
        code, _, err = self.task("edge", "1", "--block", "3")
        self.assertEqual(code, 3)
        self.assertIn("cycle", err)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.task("edge", "3", "--block", "1")[0], 0)

    def test_parent_and_orphan(self):
        self.assertEqual(self.task("edge", "2", "--parent", "1")[0], 0)
        self.assertEqual(self.gh_issue(2)["parent"], [REPO, 1])
        self.assertEqual(self.task("edge", "2", "--parent", "3")[0], 0)
        self.assertEqual(self.gh_issue(2)["parent"], [REPO, 3])
        self.assertEqual(self.task("edge", "2", "--orphan")[0], 0)
        self.assertIsNone(self.gh_issue(2)["parent"])
        self.assertEqual(self.task("edge", "2", "--orphan")[0], 0)

    def test_one_edge_at_a_time(self):
        self.assertEqual(self.task("edge", "2")[0], 2)
        self.assertEqual(self.task("edge", "2", "--block", "1", "--orphan")[0], 2)


class CloseTest(BoardCase):
    def test_completed_and_not_planned(self):
        self.ticket(5)
        self.ticket(6)
        self.assertEqual(self.task("close", "5")[0], 0)
        self.assertEqual((self.gh_issue(5)["state"], self.gh_issue(5)["stateReason"]), ("CLOSED", "COMPLETED"))
        code, _, err = self.task("close", "6", "--not-planned", "--body-file", self.body_file("Dropped: superseded."))
        self.assertEqual(code, 0, err)
        it = self.gh_issue(6)
        self.assertEqual((it["state"], it["stateReason"]), ("CLOSED", "NOT_PLANNED"))
        self.assertEqual(it["comments"][-1]["body"], "Dropped: superseded.")


class CommentTest(BoardCase):
    def test_comment(self):
        self.ticket(5)
        code, out, err = self.task("comment", "5", "--body-file", self.body_file("Where it stands."))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.gh_issue(5)["comments"][-1]["body"], "Where it stands.")
        self.assertIn("issuecomment-", out)

    def test_a_pull_requests_number_is_no_ticket(self):
        self.ticket(5)
        self.state["repos"][REPO]["issues"]["5"]["pull"] = True
        self.save()
        code, _, err = self.task("comment", "5", "--body-file", self.body_file("Where it stands."))
        self.assertEqual(code, 1, err)
        self.assertIn("has no issue #5", err)
        self.assertEqual(self.gh_issue(5)["comments"], [])
        self.assertEqual(self.writes(), [])


if __name__ == "__main__":
    unittest.main()
