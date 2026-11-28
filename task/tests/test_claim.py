"""Acceptance 10: claim."""
import unittest

from harness import (ADDRESS, OTHER_ADDRESS, OTHER_SESSION, REPO, SESSION, THREAD, BoardCase, claim_body,
                     release_body, thread_answer)

COMMENTS = "repos/%s/issues/5/comments" % REPO


class ClaimCase(BoardCase):
    def comments(self, n=5):
        return self.gh_issue(n)["comments"]

    def records(self, n=5):
        return [c for c in self.comments(n) if c["body"].startswith("```task-claim")]

    def holder(self, n=5):
        return self.json("show", str(n))["holder"]

    def ops(self):
        """The log as the steps it took: reads, record appends, label writes, deletes."""
        out = []
        for c in self.calls():
            argv = " ".join(c["argv"])
            if "TaskIssue(" in argv or "query TaskIssue" in argv:
                out.append("read")
            elif c["stdin"] and "task-claim" in c["stdin"]:
                out.append("record")
            elif "/labels" in argv and "issues/" in argv:
                out.append("label")
            elif "issues/comments/" in argv:
                out.append("delete")
        return out


class ClaimTest(ClaimCase):
    def test_an_unheld_ticket(self):
        self.ticket(5)
        code, out, err = self.task("claim", "5")
        self.assertEqual(code, 0, err)
        self.assertIn("#5: claimed", out)
        self.assertEqual(self.sminos_calls()[:2], [["who"], ["who", "--thread=%s" % SESSION]])
        self.assertEqual(self.ops(), ["read", "record", "read", "label", "read"])
        [rec] = self.records()
        [row] = self.rows()
        self.assertIn("op: claim\nholder: %s\nattempt: %s\n" % (ADDRESS, row["attempt"]), rec["body"])
        self.assertEqual((row["state"], row["claim"], row["thread"], row["session"], row["address"]),
                         ("held", rec["id"], THREAD, SESSION, ADDRESS))
        self.assertRegex(row["attempt"], "^[0-9a-f]{16}$")
        self.assertIn("claimed", self.gh_issue(5)["labels"])

    def test_the_pending_row_comes_before_the_append(self):
        self.ticket(5)
        self.hook(COMMENTS, [{"kill": True}], stdin="op: claim")
        code, _, _ = self.task("claim", "5")
        self.assertLess(code, 0)
        self.assertEqual(self.records(), [])
        [row] = self.rows()
        self.assertEqual((row["state"], row["claim"]), ("pending", None))

    def test_a_held_ticket(self):
        self.ticket(5, comments=[{"id": 70, "author": "acme-owner", "editor": None,
                                  "createdAt": "2026-11-02T00:00:00Z", "body": claim_body(OTHER_ADDRESS)}],
                    prs=[{"number": 640, "state": "OPEN", "updatedAt": "2026-11-05T00:00:00Z",
                          "url": "https://github.com/acme/widgets/pull/640"}])
        code, _, err = self.task("claim", "5")
        self.assertEqual(code, 3)
        for words in (OTHER_ADDRESS, "claim 70", "since 2026-11-02T00:00:00Z", "ago", "pull request #640"):
            self.assertIn(words, err)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.rows(), [])

    def test_a_rival_between_the_read_and_the_append(self):
        self.ticket(5)
        self.hook(COMMENTS, [{"comment": {"number": 5, "body": claim_body(OTHER_ADDRESS)}}], stdin="op: claim")
        code, _, err = self.task("claim", "5")
        self.assertEqual(code, 3, err)
        self.assertIn("claimed first by %s" % OTHER_ADDRESS, err)
        [rival] = self.records()
        self.assertIn(OTHER_ADDRESS, rival["body"])
        self.assertIn("delete", self.ops())
        self.assertEqual(self.rows(), [])
        self.assertIn("claimed", self.gh_issue(5)["labels"])
        self.assertEqual(self.holder()["claim"], rival["id"])

    def test_a_forced_takeover_before_the_confirming_read(self):
        self.ticket(5)
        taker = "```task-claim\nop: takeover\nholder: %s\nattempt: fedcba9876543210\nof: {last}\nreason: forced: " \
                "the owner said so\n```" % OTHER_ADDRESS
        self.hook(COMMENTS, [{"comment": {"number": 5, "body": taker}}], when="after", stdin="op: claim")
        code, _, err = self.task("claim", "5")
        self.assertEqual(code, 3, err)
        self.assertIn("ended by a takeover by %s" % OTHER_ADDRESS, err)
        own, take = self.records()
        self.assertIn(ADDRESS, own["body"])
        [row] = self.rows()
        self.assertEqual((row["state"], row["reason"], row["claim"]), ("lapsed", "taken-over", own["id"]))
        self.assertEqual(self.holder()["claim"], take["id"])
        self.assertEqual(self.ops().count("record"), 1)

    def test_a_forced_release_before_the_confirming_read(self):
        self.ticket(5)
        self.hook(COMMENTS, [{"comment": {"number": 5, "body": "```task-claim\nop: release\nof: {last}\nreason: "
                                                               "forced: stale\n```"}}],
                  when="after", stdin="op: claim")
        code, _, err = self.task("claim", "5")
        self.assertEqual(code, 3, err)
        self.assertIn("ended by a release", err)
        self.assertEqual(len(self.records()), 2)
        [row] = self.rows()
        self.assertEqual((row["state"], row["reason"]), ("lapsed", "forced"))
        self.assertIsNone(self.holder())
        self.assertNotIn("claimed", self.gh_issue(5)["labels"])

    def test_shut_out_by_the_second_of_a_reopening(self):
        # The stand-in stamps its first write 2026-11-01T00:00:01Z: the reopening is dated that very second.
        self.ticket(5)
        self.state["repos"][REPO]["issues"]["5"]["reopened"] = ["2026-11-01T00:00:01Z"]
        self.save()
        code, out, err = self.task("claim", "5")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.ops().count("record"), 2)
        self.assertEqual(self.ops().count("delete"), 1)
        [rec] = self.records()
        self.assertEqual(self.holder()["claim"], rec["id"])
        [row] = self.rows()
        self.assertEqual((row["state"], row["claim"]), ("held", rec["id"]))
        self.assertIn(row["attempt"], rec["body"])

    def test_already_yours(self):
        self.ticket(5)
        self.task("claim", "5")
        self.clear_log()
        code, out, _ = self.task("claim", "5")
        self.assertEqual(code, 0)
        self.assertIn("already yours", out)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual([r["state"] for r in self.rows()], ["held"])
        self.assertNotIn("record", self.ops())

    def test_registered_for_another_thread_is_claimed_saying_so(self):
        body = "Body.\n\n```task-record\nfor: %s\n```" % OTHER_ADDRESS
        self.ticket(5, body=body)
        code, out, err = self.task("claim", "5")
        self.assertEqual(code, 0, err)
        self.assertIn("not takeable", out)
        self.assertIn("for-another", out)
        [rec] = self.records()
        self.assertEqual(self.holder()["claim"], rec["id"])
        self.assertEqual([r["state"] for r in self.rows()], ["held"])
        self.assertEqual(self.gh_issue(5)["body"], body)  # `for:` still names its addressee

    def test_a_ticket_that_is_not_takeable_is_claimed_saying_why(self):
        self.ticket(5, readiness="need-design", horizon="undecided")
        code, out, _ = self.task("claim", "5")
        self.assertEqual(code, 0)
        self.assertIn("not takeable", out)
        self.assertIn("readiness, horizon", out)
        self.assertEqual(len(self.records()), 1)

    def test_no_address(self):
        self.ticket(5)
        self.sminos["addresses"] = {}
        self.save()
        code, _, err = self.task("claim", "5")
        self.assertEqual(code, 1)
        self.assertIn("no address", err)
        self.assertEqual((self.records(), self.rows()), ([], []))

    def test_no_definite_thread(self):
        self.ticket(5)
        for case, answer in (("unanswered", {"exit": 1, "said": "busy"}), ("exit 4", None),
                             ("another session", thread_answer(THREAD, OTHER_SESSION)),
                             ("another machine", thread_answer(THREAD, SESSION, local=False)),
                             ("ended", thread_answer(THREAD, SESSION, ended=True))):
            with self.subTest(case=case):
                if answer is None:
                    self.sminos["threads"].pop(SESSION, None)
                else:
                    self.sminos["threads"][SESSION] = answer
                self.save()
                code, _, err = self.task("claim", "5")
                self.assertEqual(code, 1, err)
                self.assertIn("nothing was written", err)
                self.assertEqual((self.records(), self.rows()), ([], []))

    def test_a_session_that_is_no_thread(self):
        self.ticket(5)
        self.sminos["threads"][SESSION] = thread_answer("", SESSION)
        self.save()
        code, _, err = self.task("claim", "5")
        self.assertEqual(code, 0, err)
        [row] = self.rows()
        self.assertEqual((row["thread"], row["state"]), ("", "held"))

    def test_killed_after_the_append_the_next_settle_adopts_it(self):
        # The ticket also holds an earlier claim of the same address, released: the token, not the address, finds it.
        self.ticket(5, comments=[{"id": 70, "author": "acme-owner", "editor": None,
                                  "createdAt": "2026-10-02T00:00:00Z", "body": claim_body(ADDRESS)},
                                 {"id": 71, "author": "acme-owner", "editor": None,
                                  "createdAt": "2026-10-02T00:00:01Z", "body": release_body(70)}])
        self.hook(COMMENTS, [{"kill": True}], when="after", stdin="op: claim")
        code, _, _ = self.task("claim", "5")
        self.assertLess(code, 0)
        [row] = self.rows()
        self.assertEqual(row["state"], "pending")
        code, out, err = self.task("settle", "--json", repo=False)
        self.assertEqual(code, 0, err)
        own = self.records()[-1]
        [row] = self.rows()
        self.assertEqual((row["state"], row["claim"]), ("held", own["id"]))
        self.assertIn("claimed", self.gh_issue(5)["labels"])

    def test_a_batch(self):
        self.ticket(5, extra=["batch:polish"])
        self.ticket(6, extra=["batch:polish"], comments=[{"id": 70, "author": "acme-owner", "editor": None,
                                                           "createdAt": "2026-11-02T00:00:00Z",
                                                           "body": claim_body(OTHER_ADDRESS)}])
        self.ticket(7, extra=["batch:other"])
        code, out, _ = self.task("claim", "--batch", "polish")
        self.assertEqual(code, 3)
        self.assertIn("won  #5: claimed", out)
        self.assertIn("lost #6 is held by", out)
        self.assertIn("won: #5", out)
        self.assertEqual(len(self.records(7)), 0)

    def test_numbers_or_a_batch(self):
        self.assertEqual(self.task("claim")[0], 2)
        self.assertEqual(self.task("claim", "5", "--batch", "x")[0], 2)


if __name__ == "__main__":
    unittest.main()
