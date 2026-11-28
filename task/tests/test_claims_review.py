"""M3's review, fix wave 1: one test per behavior the wave changed (owed
rows, releases the confirming read does not show, pending rows, holder
identity, the settle's deadline, housekeeping after preflight, a
repository that cannot be read, close, the void claim's report, the board
key, the label's 422)."""
import json
import time
import unittest

from harness import (ADDRESS, OTHER_ADDRESS, OTHER_SESSION, REPO, SESSION, THREAD, claim_body, takeover_body,
                     thread_answer)
from test_settle import SettleCase

COMMENTS = REPO + "/issues/5/comments"


class OwedTest(SettleCase):
    def owe(self, n=5):
        """A held row whose thread ended and whose release GitHub refused: owed."""
        claim = self.claimed(n)
        self.ended()
        self.fail_on(REPO + "/issues/%d/comments" % n, status=502, stdin="reason: ended")
        self.settle()
        self.assertEqual(self.row(n)["state"], "owed")
        return claim

    def test_an_owed_row_is_held_not_lapsed(self):                                              # 1
        claim = self.owe()
        code, out, err = self.task("held", "--session", SESSION, "--thread", THREAD, "--json", repo=False)
        data = json.loads(out)
        self.assertEqual([(h["number"], h["claim"]) for h in data["held"]], [(5, claim)])
        self.assertEqual(data["lapsed"], [])
        self.sminos["threads"][THREAD] = thread_answer(THREAD, SESSION)  # the retry inside list puts it back
        self.save()
        self.set_rows(lambda d: d["rows"][0].update(state="owed"))
        code, _, err = self.task("list", env={"TASK_SETTLE_EVERY": "3600"})
        self.assertNotIn("lapsed", err)

    def test_an_owed_retry_asks_sminos_again(self):                                             # 3
        for answer, state, unknown in ((thread_answer(THREAD, SESSION), "held", False),
                                       ({"exit": 4}, "owed", True)):
            with self.subTest(state=state):
                self.load()
                self.state["repos"][REPO]["issues"].clear()
                self.save()
                self.set_rows(lambda d: d["rows"].clear()) if (self.tmp / "task-home" / "claims.json").exists() \
                    else None
                self.owe()
                self.sminos["threads"][THREAD] = answer
                self.save()
                self.clear_log()
                report = self.settle()
                self.assertEqual(self.releases(), [])
                self.assertEqual(self.row(5)["state"], state)
                self.assertEqual(bool(report["unknown"]), unknown)
                self.assertIn(["who", "--thread=%s" % THREAD], self.sminos_calls())

    def test_a_writing_verb_asks_too(self):                                                     # 3
        self.owe()
        self.sminos["threads"][THREAD] = thread_answer(THREAD, SESSION)
        self.save()
        code, _, err = self.task("comment", "5", "--body-file", self.body_file("Noted.\n"))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.releases(), [])
        self.assertEqual(self.row(5)["state"], "held")

    def test_a_release_already_in_the_fold_is_reconciled_without_a_question(self):              # 3
        claim = self.owe()
        self.comment(5, "```task-claim\nop: release\nof: %d\nreason: ended\n```" % claim, 9900,
                     created="2026-11-05T00:00:00Z")
        self.clear_log()
        self.settle()
        self.assertEqual((self.row(5)["state"], self.row(5)["reason"]), ("lapsed", "ended"))
        self.assertEqual(self.sminos_calls(), [])


class MissingReleaseTest(SettleCase):
    def test_a_release_the_confirming_read_does_not_show_is_kept(self):                         # 2
        self.claimed()
        self.ended()
        self.hook(COMMENTS, [{"hide": {"number": 5}}], when="after", stdin="reason: ended")
        self.clear_log()
        self.settle()
        self.assertFalse(any("issues/comments/" in " ".join(c["argv"]) for c in self.calls()), "a delete")
        self.assertEqual(len(self.releases()), 1)
        self.assertEqual(self.row(5)["state"], "owed")

    def test_the_release_verb_does_not_delete_it_either(self):                                  # 2
        self.claimed()
        self.hook(COMMENTS, [{"hide": {"number": 5}}], when="after", stdin="op: release")
        self.clear_log()
        code, _, err = self.task("release", "5")
        self.assertEqual(code, 1, err)
        self.assertIn("did not show it", err)
        self.assertFalse(any("issues/comments/" in " ".join(c["argv"]) for c in self.calls()))
        self.assertEqual(len(self.releases()), 1)


class PendingTest(SettleCase):
    def pending(self, n=5):
        self.ticket(n)
        self.hook(REPO + "/issues/%d/comments" % n, [{"kill": True}], when="after", stdin="op: claim")
        self.assertLess(self.task("claim", str(n))[0], 0)
        self.assertEqual(self.row(n)["state"], "pending")

    def test_a_pending_row_on_a_closed_ticket(self):                                           # 4
        self.pending()
        self.load()
        issue = self.state["repos"][REPO]["issues"]["5"]
        issue["state"] = "CLOSED"
        issue["labels"].append("claimed")
        self.save()
        report = self.settle()
        self.assertEqual(report["closed"], [{"repo": REPO, "number": 5}])
        self.assertIsNone(self.row(5))
        self.assertNotIn("claimed", self.gh_issue(5)["labels"])

    def test_a_pending_row_of_an_ended_thread_is_released_in_one_pass(self):                    # 4
        self.pending()
        self.ended()
        report = self.settle()
        self.assertEqual([r["number"] for r in report["released"]], [5])
        self.assertEqual((self.row(5)["state"], self.row(5)["reason"]), ("lapsed", "ended"))

    def test_a_pending_row_decides_who_holds(self):                                             # 5
        # The record took effect and the row is still pending; the session's address has changed since, so only
        # the attempt token ties the folded holder to this machine's row (and its thread).
        self.pending()
        self.load()
        self.sminos["addresses"][SESSION] = "builder#11111111 (widgets on desk)"
        self.save()
        code, _, err = self.task("release", "5")
        self.assertEqual(code, 0, err)
        self.assertIsNone(self.row(5))
        self.assertIsNone(self.holder())


class DeadlineTest(SettleCase):
    def test_a_slow_gh_call_is_cut_at_the_deadline(self):                                      # 6
        self.claimed()
        self.ended()
        self.set_rows(lambda d: d["settled"].clear())
        self.hook("query TaskIssue", [{"sleep": 30}])  # the settle's read of its row
        started = time.monotonic()
        code, out, err = self.task("list", "--json", env={"TASK_SETTLE_EVERY": "0", "TASK_SETTLE_DEADLINE": "2"})
        self.assertEqual(code, 0, err)
        self.assertLess(time.monotonic() - started, 25)
        self.assertEqual(self.row(5)["state"], "held")
        self.assertEqual(self.releases(), [])
        self.assertNotIn("acme/widgets", self.index()["settled"])
        self.assertEqual(self.index()["running"], {})

    def test_a_slow_sminos_answer_is_cut_at_the_deadline(self):                                # 6
        self.claimed()
        self.sminos["threads"][THREAD] = dict(thread_answer(THREAD, SESSION, ended=True), sleep=30)
        self.save()
        self.set_rows(lambda d: d["settled"].clear())
        started = time.monotonic()
        code, _, err = self.task("list", env={"TASK_SETTLE_EVERY": "0", "TASK_SETTLE_DEADLINE": "2"})
        self.assertEqual(code, 0, err)
        self.assertLess(time.monotonic() - started, 25)
        self.assertEqual(self.row(5)["state"], "held")
        self.assertNotIn("acme/widgets", self.index()["settled"])


class HousekeepingTest(SettleCase):
    def owed(self):
        self.claimed()
        self.ended()
        self.fail_on(COMMENTS, status=502, stdin="reason: ended")
        self.settle()
        self.assertEqual(self.row(5)["state"], "owed")
        self.clear_log()

    def test_a_verb_that_fails_its_preflight_writes_nothing(self):                             # 7
        self.owed()
        self.ticket(6)
        self.sminos["addresses"] = {}
        self.save()
        self.assertEqual(self.task("claim", "6")[0], 1)                       # no address
        self.assertEqual(self.task("takeover", "5", "--force", "x")[0], 1)    # no address
        self.assertEqual(self.task("set", "6", "--due", "someday")[0], 2)     # usage
        self.assertEqual(self.task("set", "6", "--to", "nobody")[0], 1)       # sminos names no such thread
        self.assertEqual(self.task("edge", "6", "--block", "x#y")[0], 2)
        self.assertEqual(self.task("release", "5", "--of", "1")[0], 2)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.row(5)["state"], "owed")

    def test_migrate_apply_with_an_unsettled_plan_writes_nothing(self):                        # 7
        self.owed()
        plan = self.tmp / "plan.json"
        plan.write_text(json.dumps({"v": 1, "repo": REPO, "read_at": "2026-11-27T00:00:00Z", "incoming": [],
                                    "rows": [{"number": 6, "title": "t", "seen": {}, "action": "relabel",
                                              "readiness": "need-design", "horizon": "undecided",
                                              "basis": "decision", "decided": False, "why": "",
                                              "body_after": None, "question": "q"}]}))
        code, _, err = self.task("migrate", "apply", str(plan))
        self.assertNotEqual(code, 0)
        self.assertEqual(self.writes(), [])

    def test_the_holder_condition_is_read_after_housekeeping(self):                            # 7
        # The owed release is written first; the holder's own release then finds the ticket unheld.
        self.owed()
        code, _, err = self.task("release", "5")
        self.assertEqual(code, 3, err)
        self.assertIn("unheld", err)
        self.assertEqual(len(self.releases()), 1)


class UnreadableRepositoryTest(SettleCase):
    def test_a_repository_that_cannot_be_read_keeps_its_rows(self):                            # 8
        self.claimed()
        self.ended()
        self.load()
        self.state["repos"]["acme/elsewhere"] = self.state["repos"].pop(REPO)  # the board's repository is gone
        self.save()
        report = self.settle()
        self.assertEqual([u["repo"] for u in report["unreachable"]], [REPO])
        self.assertEqual(report["closed"], [])
        self.assertEqual(self.row(5)["state"], "held")


class CloseTest(SettleCase):
    def test_close_removes_only_the_rows_of_the_claim_it_ended(self):                          # 9
        # This machine's row is of a claim another machine took over by force; the close ends the taker's claim,
        # and the row it does not name stays for settle, which tells its thread the claim was taken over.
        claim = self.claimed()
        self.comment(5, takeover_body(claim), 9500, created="2026-11-03T00:00:00Z")
        code, _, err = self.task("close", "5", "--force", "done elsewhere", session=OTHER_SESSION)
        self.assertEqual(code, 0, err)
        [row] = self.rows()
        self.assertEqual((row["state"], row["claim"]), ("held", claim))
        self.assertNotIn("claimed", self.gh_issue(5)["labels"])
        reads = [c for c in self.calls() if "query TaskIssue" in " ".join(c["argv"])]
        self.assertGreaterEqual(len(reads), 2)  # the label is judged on a read after the close

    def test_close_by_the_holder_removes_its_row(self):                                        # 9
        self.claimed()
        code, _, err = self.task("close", "5")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.rows(), [])


class SmallTest(SettleCase):
    def test_a_void_claim_names_the_holder_at_its_place(self):                                 # 12
        self.ticket(5)
        third = "x#99999999 (widgets on desk)"
        self.hook(COMMENTS, [{"comment": {"number": 5, "body": claim_body(OTHER_ADDRESS, "00000000000000ee")}}],
                  stdin="op: claim")
        self.hook(COMMENTS, [{"comment": {"number": 5, "body": takeover_body(9000, holder=third)}}],
                  when="after", stdin="op: claim")
        code, _, err = self.task("claim", "5")
        self.assertEqual(code, 3, err)
        self.assertIn("claimed first by %s" % OTHER_ADDRESS, err)
        self.assertNotIn(third, err)

    def test_the_board_key_has_no_case(self):                                                  # 12
        self.claimed()
        self.set_rows(lambda d: d["settled"].clear())
        code, _, err = self.task("list", repo="ACME/Widgets", env={"TASK_SETTLE_EVERY": "0"})
        self.assertEqual(code, 0, err)
        self.assertEqual(list(self.index()["settled"]), ["acme/widgets"])

    def test_a_label_another_writer_made_a_moment_ago(self):                                   # 12
        self.ticket(5)
        self.hook(REPO + "/labels", [{"define": {"name": "claimed"}}], stdin='"name": "claimed"')
        code, _, err = self.task("claim", "5")
        self.assertEqual(code, 0, err)
        self.load()
        self.ticket(6)
        self.state["repos"][REPO]["labels"].pop("claimed")
        self.save()
        self.fail_on(REPO + "/labels", status=422, message="Validation Failed", stdin='"name": "claimed"')
        code, _, err = self.task("claim", "6")
        self.assertEqual(code, 1)
        self.assertEqual(self.records(6), [])


if __name__ == "__main__":
    unittest.main()
