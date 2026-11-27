"""Acceptance 5: trust."""
import re
import unittest

from harness import ADDRESS, ME, OUTSIDER, REPO, BoardCase, board_file

BODY = "Original text.\n\n```task-record\nregistered-by: %s\nspec: docs/specs/a.md\n```" % ADDRESS


class TrustTest(BoardCase):
    def setUp(self):
        super().setUp()
        self.ticket(5, body=BODY, editor=OUTSIDER)

    def test_the_trusted_account_is_the_client_login(self):
        self.state["repos"][REPO]["files"][".doperpowers/board.json"] = board_file(account=OUTSIDER)
        self.save()
        t = self.json("show", "5")
        self.assertFalse(t["body_trusted"])
        self.assertIsNone(t["record"])
        self.state["login"] = OUTSIDER
        self.save()
        self.ticket(6, author=OUTSIDER, body=BODY)
        self.assertTrue(self.json("show", "6")["body_trusted"])

    def test_an_edited_body_is_not_read_and_show_says_so(self):
        code, out, _ = self.task("show", "5")
        self.assertEqual(code, 0)
        self.assertIn("NOT trusted", out)
        self.assertIn(OUTSIDER, out)
        self.ticket(7, body=BODY, author=OUTSIDER)
        t = self.json("show", "7")
        self.assertFalse(t["body_trusted"])
        self.assertIsNone(t["record"])

    def test_set_refuses_every_body_write_on_an_untrusted_body(self):
        for flags in (["--body-file", self.body_file("new")], ["--due", "2027-01-01"], ["--spec", "x.md"],
                      ["--no-spec"], ["--to", "reviewer"], ["--readiness", "need-design", "--due", "2027-01-01"]):
            with self.subTest(flags=flags):
                self.clear_log()
                code, _, err = self.task("set", "5", *flags)
                self.assertEqual(code, 3, err)
                self.assertIn("trusted", err)
                self.assertEqual(self.writes(), [])
        t = self.json("show", "5")
        self.assertFalse(t["body_trusted"])
        self.assertIsNone(t["record"])
        self.assertEqual(self.task("set", "5", "--readiness", "need-design")[0], 0)
        self.assertIn("need-design", self.gh_issue(5)["labels"])
        self.assertEqual(self.gh_issue(5)["body"], BODY)

    def test_adopt_with_the_digest_show_printed(self):
        digest = self.json("show", "5")["body_digest"]
        code, _, err = self.task("adopt", "5", "--digest", digest)
        self.assertEqual(code, 0, err)
        body = self.gh_issue(5)["body"]
        m = re.fullmatch(re.escape(BODY[:-3]) + r"adopted: (\S+) by (.+)\n```", body)
        self.assertTrue(m, body)
        self.assertRegex(m.group(1), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(m.group(2), ADDRESS)
        t = self.json("show", "5")
        self.assertTrue(t["body_trusted"])
        self.assertEqual(t["record"]["spec"], "docs/specs/a.md")
        self.assertEqual(t["record"]["adopted"], "%s by %s" % (m.group(1), ADDRESS))

    def test_adopt_without_a_session(self):
        digest = self.json("show", "5")["body_digest"]
        self.assertEqual(self.task("adopt", "5", "--digest", digest, session="")[0], 0)
        self.assertRegex(self.gh_issue(5)["body"], r"\nadopted: \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\n```$")

    def test_adopt_a_body_with_no_block(self):
        self.ticket(8, body="Just text.", editor=OUTSIDER)
        digest = self.json("show", "8")["body_digest"]
        self.assertEqual(self.task("adopt", "8", "--digest", digest)[0], 0)
        self.assertRegex(self.gh_issue(8)["body"], r"^Just text\.\n\n```task-record\nadopted: \S+ by .+\n```$")

    def test_adopt_refuses_an_older_digest(self):
        old = self.json("show", "5")["body_digest"]
        self.ticket(5, body=BODY + "\n", editor=OUTSIDER)
        self.clear_log()
        self.assertEqual(self.task("adopt", "5", "--digest", old)[0], 3)
        self.assertEqual(self.writes(), [])

    def test_adopt_refuses_an_outsiders_issue(self):
        self.ticket(9, author=OUTSIDER, body="Please add a feature.")
        digest = self.json("show", "9")["body_digest"]
        self.clear_log()
        self.assertEqual(self.task("adopt", "9", "--digest", digest)[0], 3)
        self.assertEqual(self.writes(), [])

    def test_adopt_of_a_trusted_body_writes_nothing(self):
        self.ticket(10, body=BODY, editor=ME)
        digest = self.json("show", "10")["body_digest"]
        self.clear_log()
        self.assertEqual(self.task("adopt", "10", "--digest", digest)[0], 0)
        self.assertEqual(self.writes(), [])


if __name__ == "__main__":
    unittest.main()
