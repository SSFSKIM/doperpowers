"""Acceptance 11: release, close and the label."""
import unittest

from harness import (ADDRESS, OTHER_ADDRESS, OTHER_SESSION, REPO, SESSION, THREAD, claim_body, release_body,
                     thread_answer)
from test_claim import ClaimCase

NEW_THREAD = "77777777-aaaa-4bbb-8ccc-000000000007"


class ReleaseTest(ClaimCase):
    def claimed(self, n=5, **kw):
        self.ticket(n, **kw)
        code, _, err = self.task("claim", str(n))
        self.assertEqual(code, 0, err)
        self.clear_log()
        return self.records(n)[-1]["id"]

    def test_by_the_holder(self):
        claim = self.claimed()
        code, out, err = self.task("release", "5", "--body-file", self.body_file("Halfway: the parser is done.\n"))
        self.assertEqual(code, 0, err)
        rec = self.records()[-1]
        self.assertTrue(rec["body"].startswith("```task-claim\nop: release\nof: %d\nreason: released\n```" % claim))
        self.assertIn("Halfway: the parser is done.", rec["body"])
        self.assertEqual(self.ops(), ["read", "record", "read", "label", "read"])
        self.assertNotIn("claimed", self.gh_issue(5)["labels"])
        self.assertEqual(self.rows(), [])

    def test_by_another_session(self):
        claim = self.claimed()
        code, _, err = self.task("release", "5", session=OTHER_SESSION)
        self.assertEqual(code, 3)
        self.assertIn("--force", err)
        self.assertEqual(len(self.records()), 1)
        code, _, err = self.task("release", "5", "--force", "its session is gone", session=OTHER_SESSION)
        self.assertEqual(code, 0, err)
        self.assertIn("of: %d\nreason: forced: its session is gone\n" % claim, self.records()[-1]["body"])
        self.assertIsNone(self.holder())

    def test_bound_to_one_claim(self):
        claim = self.claimed()
        code, _, err = self.task("release", "5", "--force", "stale", "--of", str(claim + 1), session=OTHER_SESSION)
        self.assertEqual(code, 3)
        self.assertIn("held by %s" % ADDRESS, err)
        self.assertIn("nothing was written", err)
        self.assertEqual(len(self.records()), 1)
        code, _, err = self.task("release", "5", "--force", "stale", "--of", str(claim), session=OTHER_SESSION)
        self.assertEqual(code, 0, err)
        self.assertIsNone(self.holder())
        self.assertEqual(self.task("release", "5", "--of", str(claim))[0], 2)

    def test_the_address_is_not_the_thread(self):
        # An old session id reopened as a thread of its own: the same address, another thread than the row's.
        self.claimed()
        self.sminos["threads"][SESSION] = thread_answer(NEW_THREAD, SESSION)
        self.save()
        code, _, err = self.task("release", "5")
        self.assertEqual(code, 3, err)
        self.assertEqual(len(self.records()), 1)

    def test_the_address_decides_where_the_machine_has_no_row(self):
        self.ticket(5, comments=[{"id": 70, "author": "acme-owner", "editor": None,
                                  "createdAt": "2026-11-02T00:00:00Z", "body": claim_body(ADDRESS)}])
        code, _, err = self.task("release", "5")
        self.assertEqual(code, 0, err)
        self.assertIsNone(self.holder())
        code, _, err = self.task("release", "5", session=OTHER_SESSION)
        self.assertEqual(code, 3)
        self.assertIn("unheld", err)

    def test_close_by_the_holder(self):
        self.claimed()
        code, out, err = self.task("close", "5")
        self.assertEqual(code, 0, err)
        issue = self.gh_issue(5)
        self.assertEqual((issue["state"], issue["stateReason"]), ("CLOSED", "COMPLETED"))
        self.assertNotIn("claimed", issue["labels"])
        self.assertEqual(self.rows(), [])

    def test_close_of_a_ticket_another_thread_holds(self):
        self.claimed()
        code, _, err = self.task("close", "5", session=OTHER_SESSION)
        self.assertEqual(code, 3)
        self.assertIn("--force", err)
        self.assertEqual(self.gh_issue(5)["state"], "OPEN")
        code, _, err = self.task("close", "5", "--not-planned", "--force", "superseded by #9", session=OTHER_SESSION)
        self.assertEqual(code, 0, err)
        issue = self.gh_issue(5)
        self.assertEqual((issue["state"], issue["stateReason"]), ("CLOSED", "NOT_PLANNED"))
        self.assertIn("superseded by #9", issue["comments"][-1]["body"])

    def test_two_releases_interleaved_with_a_new_claim(self):
        # The holder's release lands first; settle's release (its thread ended) is then void and reads the ticket
        # unheld; a new claim is made and labelled; settle writes the label off; its look puts it back.
        claim = self.claimed()
        self.sminos["threads"][THREAD] = thread_answer(THREAD, SESSION, ended=True)
        self.save()
        self.hook(REPO + "/issues/5/comments", [{"comment": {"number": 5, "body": release_body(claim)}}],
                  stdin="reason: ended")
        self.hook(REPO + "/issues/5/labels/claimed", [
            {"comment": {"number": 5, "body": claim_body(OTHER_ADDRESS, "00000000000000aa")}},
            {"label": {"number": 5, "add": "claimed"}}])
        code, out, err = self.task("settle", "--json", repo=False)
        self.assertEqual(code, 0, err)
        new = self.records()[-1]
        self.assertIn(OTHER_ADDRESS, new["body"])
        self.assertEqual(self.holder()["claim"], new["id"])
        self.assertIn("claimed", self.gh_issue(5)["labels"])
        self.assertNotIn("reason: ended", "".join(c["body"] for c in self.records()))

    def test_a_writer_killed_between_its_record_and_its_label(self):
        self.claimed()
        self.hook(REPO + "/issues/5/comments", [{"kill": True}], when="after", stdin="op: release")
        code, _, _ = self.task("release", "5")
        self.assertLess(code, 0)
        self.assertIn("claimed", self.gh_issue(5)["labels"])
        self.assertIsNone(self.json("list")["tickets"][0]["holder"])
        self.assertNotIn("claimed", self.gh_issue(5)["labels"])


if __name__ == "__main__":
    unittest.main()
