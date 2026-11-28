"""Acceptance 12: takeover."""
import unittest

from harness import ADDRESS, OTHER_ADDRESS, OTHER_SESSION, OTHER_THREAD, REPO, THREAD, release_body
from test_claim import ClaimCase

COMMENTS = REPO + "/issues/5/comments"


class TakeoverTest(ClaimCase):
    def setUp(self):
        super().setUp()
        self.ticket(5)
        code, _, err = self.task("claim", "5")
        self.assertEqual(code, 0, err)
        self.claim = self.records()[-1]["id"]

    def grant(self):
        code, out, err = self.task("held", "--session", OTHER_SESSION, "--thread", OTHER_THREAD, "--cleared-from",
                                   THREAD, "--json", repo=False)
        self.assertEqual(code, 0, err)
        self.clear_log()

    def row(self, thread):
        [row] = [r for r in self.rows() if r["thread"] == thread]
        return row

    def test_along_a_grant(self):
        self.grant()
        code, out, err = self.task("takeover", "5", session=OTHER_SESSION)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sminos_calls()[:2], [["who"], ["who", "--thread=%s" % OTHER_SESSION]])
        self.assertEqual(self.ops(), ["read", "record", "read"])
        rec = self.records()[-1]
        mine = self.row(OTHER_THREAD)
        self.assertIn("op: takeover\nholder: %s\nattempt: %s\nof: %d\nreason: cleared\n"
                      % (OTHER_ADDRESS, mine["attempt"], self.claim), rec["body"])
        self.assertEqual((mine["state"], mine["claim"]), ("held", rec["id"]))
        left = self.row(THREAD)
        self.assertEqual((left["state"], left["reason"]), ("lapsed", "taken-over"))
        self.assertEqual(self.holder()["address"], OTHER_ADDRESS)
        self.assertIn("claimed", self.gh_issue(5)["labels"])

    def test_without_a_grant(self):
        code, _, err = self.task("takeover", "5", session=OTHER_SESSION)
        self.assertEqual(code, 3)
        self.assertIn("--force", err)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual([r["thread"] for r in self.rows()], [THREAD])
        code, _, err = self.task("takeover", "5", "--force", "the owner moved it", session=OTHER_SESSION)
        self.assertEqual(code, 0, err)
        self.assertIn("reason: forced: the owner moved it\n", self.records()[-1]["body"])
        self.assertEqual(self.holder()["address"], OTHER_ADDRESS)

    def test_its_claim_no_longer_current(self):
        self.grant()
        self.hook(COMMENTS, [{"comment": {"number": 5, "body": release_body(self.claim)}}], stdin="op: takeover")
        code, _, err = self.task("takeover", "5", session=OTHER_SESSION)
        self.assertEqual(code, 3, err)
        self.assertIn("void", err)
        self.assertNotIn("op: takeover", "".join(c["body"] for c in self.records()))
        self.assertEqual([r["thread"] for r in self.rows()], [THREAD])

    def test_taken_over_itself_before_its_confirming_read(self):
        self.grant()
        third = "```task-claim\nop: takeover\nholder: x#99999999 (widgets on desk)\nattempt: 00000000000000bb\n" \
                "of: {last}\nreason: forced: the owner moved it\n```"
        self.hook(COMMENTS, [{"comment": {"number": 5, "body": third}}], when="after", stdin="op: takeover")
        code, _, err = self.task("takeover", "5", session=OTHER_SESSION)
        self.assertEqual(code, 3, err)
        self.assertEqual(len(self.records()), 3)
        mine = self.row(OTHER_THREAD)
        self.assertEqual((mine["state"], mine["reason"]), ("lapsed", "taken-over"))
        self.assertEqual(self.holder()["address"], "x#99999999 (widgets on desk)")

    def test_killed_after_the_append_the_next_settle_adopts_it(self):
        self.grant()
        self.hook(COMMENTS, [{"kill": True}], when="after", stdin="op: takeover")
        code, _, _ = self.task("takeover", "5", session=OTHER_SESSION)
        self.assertLess(code, 0)
        self.assertEqual(self.row(OTHER_THREAD)["state"], "pending")
        code, _, err = self.task("settle", repo=False)
        self.assertEqual(code, 0, err)
        rec = self.records()[-1]
        mine = self.row(OTHER_THREAD)
        self.assertEqual((mine["state"], mine["claim"]), ("held", rec["id"]))
        self.assertEqual(self.row(THREAD)["state"], "lapsed")

    def test_already_yours_and_unheld(self):
        code, out, _ = self.task("takeover", "5")
        self.assertEqual(code, 0)
        self.assertIn("already yours", out)
        self.task("release", "5")
        code, _, err = self.task("takeover", "5", "--force", "x", session=OTHER_SESSION)
        self.assertEqual(code, 3)
        self.assertIn("unheld", err)
        self.assertNotIn(ADDRESS + "x", err)


if __name__ == "__main__":
    unittest.main()
