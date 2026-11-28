"""Acceptance 9: the fold (D3's table, the open interval, trust)."""
import sys
import unittest

from harness import (ADDRESS, HERE, ME, OTHER_ADDRESS, OUTSIDER, BoardCase, claim_body, release_body,
                     takeover_body)

sys.path.insert(0, str(HERE.parent / "cli"))
import claims  # noqa: E402


def comment(cid, body, created="2026-11-02T00:00:00Z", author=ME, editor=None):
    return {"fullDatabaseId": str(cid), "createdAt": created,
            "body": body, "author": {"login": author}, "editor": {"login": editor} if editor else None}


def fold(*comments, is_open=True, reopened=None):
    recs = claims.records(comments, lambda c: c["author"]["login"] == ME and not c.get("editor"))
    return claims.Fold(recs, is_open, reopened)


class TableTest(unittest.TestCase):
    """Each cell of D3's table, as the record meets an unheld ticket and one
    held by claim c."""

    def test_claim(self):
        f = fold(comment(1, claim_body()))
        self.assertEqual(f.holder.id, 1)                                    # unheld: held by k
        f = fold(comment(1, claim_body()), comment(2, claim_body(OTHER_ADDRESS)))
        self.assertEqual((f.holder.id, f.effect[2]), (1, False))             # held: void

    def test_release(self):
        f = fold(comment(1, release_body(7)))
        self.assertEqual((f.holder, f.effect[1]), (None, False))            # unheld: void
        f = fold(comment(1, claim_body()), comment(2, release_body(1)))
        self.assertIsNone(f.holder)                                          # of c: unheld
        f = fold(comment(1, claim_body()), comment(2, release_body(9)))
        self.assertEqual((f.holder.id, f.effect[2]), (1, False))             # of another: void

    def test_takeover(self):
        f = fold(comment(1, takeover_body(7)))
        self.assertEqual((f.holder, f.effect[1]), (None, False))            # unheld: void
        f = fold(comment(1, claim_body()), comment(2, takeover_body(1)))
        self.assertEqual(f.holder.id, 2)                                     # of c: held by k
        f = fold(comment(1, claim_body()), comment(2, takeover_body(9)))
        self.assertEqual((f.holder.id, f.effect[2]), (1, False))             # of another: void

    def test_ascending_id_not_list_order(self):
        f = fold(comment(2, claim_body(OTHER_ADDRESS)), comment(1, claim_body()))
        self.assertEqual(f.holder.id, 1)

    def test_a_malformed_record_is_no_record(self):
        for body in ("```task-claim\nop: claim\nholder: %s\n```" % ADDRESS,             # no attempt
                     "```task-claim\nop: claim\nholder: x\nattempt: 0123\n```",          # a short token
                     "```task-claim\nop: grab\nholder: x\nattempt: 0123456789abcdef\n```",
                     "```task-claim\nop: release\nof: 1\nreason: because\n```",
                     "prose\n```python\nx\n```\n" + claim_body()):                      # not the first fence
            with self.subTest(body=body):
                self.assertEqual(fold(comment(1, body)).records, [])


class IntervalTest(BoardCase):
    def held(self, n):
        return self.json("show", str(n))["holder"]

    def test_closed_ticket_is_unheld(self):
        self.ticket(5, state="CLOSED", comments=[comment_seed(1, claim_body())])
        self.assertIsNone(self.held(5))

    def test_reopened_ticket_starts_unheld(self):
        self.ticket(5, comments=[comment_seed(1, claim_body(), "2026-11-02T00:00:00Z")])
        self.gh_issue(5)
        self.state["repos"]["acme/widgets"]["issues"]["5"]["reopened"] = ["2026-11-03T00:00:00Z"]
        self.save()
        self.assertIsNone(self.held(5))

    def test_a_claim_made_while_closed_does_not_hold_after_the_reopening(self):
        self.ticket(5, state="CLOSED")
        self.hook("TaskIssue", [{"comment": {"number": 5, "body": claim_body(), "createdAt": "2026-11-02T00:00:00Z"}},
                                {"reopen": {"number": 5, "at": "2026-11-02T00:00:05Z"}}])
        self.assertIsNone(self.held(5))
        self.assertEqual(self.gh_issue(5)["state"], "OPEN")

    def test_a_claim_of_the_reopening_second_does_not_hold(self):
        second = "2026-11-02T00:00:05Z"
        for order in ("before", "after"):
            with self.subTest(comment=order):
                n = 5 if order == "before" else 6
                self.ticket(n, state="CLOSED")
                write = {"comment": {"number": n, "body": claim_body(), "createdAt": second}}
                reopen = {"reopen": {"number": n, "at": second}}
                self.hook("TaskIssue", [write, reopen] if order == "before" else [reopen, write])
                self.assertIsNone(self.held(n))
                self.load()
                self.assertEqual(len(self.gh_issue(n)["comments"]), 1)
        # A second later, it holds.
        self.ticket(7, comments=[comment_seed(1, claim_body(), "2026-11-02T00:00:06Z")])
        self.state["repos"]["acme/widgets"]["issues"]["7"]["reopened"] = [second]
        self.save()
        self.assertEqual(self.held(7)["claim"], 1)

    def test_records_another_account_wrote_or_edited_change_no_holder(self):
        self.ticket(5, comments=[comment_seed(1, claim_body(OTHER_ADDRESS), author=OUTSIDER),
                                 comment_seed(2, claim_body())])
        self.assertEqual(self.held(5)["claim"], 2)
        self.ticket(6, comments=[comment_seed(1, claim_body()),
                                 comment_seed(2, release_body(1), editor=OUTSIDER),
                                 comment_seed(3, takeover_body(1), author=OUTSIDER)])
        self.assertEqual(self.held(6), {"address": ADDRESS, "claim": 1, "since": "2026-11-02T00:00:00Z"})


def comment_seed(cid, body, created="2026-11-02T00:00:00Z", author=ME, editor=None):
    return {"id": cid, "author": author, "editor": editor, "createdAt": created, "body": body}


if __name__ == "__main__":
    unittest.main()
