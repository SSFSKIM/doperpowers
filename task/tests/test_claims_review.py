"""M3's review, fix waves 1 to 3: one test per behavior a wave changed (owed
rows, releases the confirming read does not show, pending rows, holder
identity, the settle's deadline, housekeeping after preflight, a
repository that cannot be read, close, the void claim's report, the board
key, the label's 422)."""
import json
import time
import unittest

from harness import (ADDRESS, OTHER_ADDRESS, OTHER_SESSION, OTHER_THREAD, REPO, SESSION, THREAD, claim_body,
                     takeover_body, thread_answer)
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


# ── fix wave 2 ────────────────────────────────────────────────────────────
class WaveTwoTest(SettleCase):
    def owe(self, n):
        claim = self.claimed(n)
        self.ended()
        self.fail_on(REPO + "/issues/%d/comments" % n, status=502, stdin="reason: ended")
        self.settle()
        self.assertEqual(self.row(n)["state"], "owed")
        self.clear_log()
        return claim

    def test_a_stale_bound_release_writes_nothing_anywhere(self):                              # 1
        self.owe(6)
        claim = 9800
        self.ticket(5, extra=["claimed"], comments=[{"id": claim, "author": "acme-owner", "editor": None,
                                                     "createdAt": "2026-11-02T00:00:00Z",
                                                     "body": claim_body(OTHER_ADDRESS)}])
        self.clear_log()
        code, _, err = self.task("release", "5", "--force", "stale", "--of", str(claim + 1))
        self.assertEqual(code, 3, err)
        self.assertIn("nothing was written", err)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.row(6)["state"], "owed")
        self.assertIn("claimed", self.gh_issue(6)["labels"])

    def test_close_of_an_unheld_ticket_asks_no_identity(self):                                 # 2
        self.claimed(5)
        self.load()
        self.state["repos"][REPO]["issues"]["5"]["reopened"] = ["2026-12-01T00:00:00Z"]  # after the claim: unheld
        self.save()
        self.clear_log()
        code, _, err = self.task("close", "5", session=None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.gh_issue(5)["state"], "CLOSED")
        self.assertEqual([c for c in self.sminos_calls() if c[:1] == ["who"]], [])

    def test_close_keeps_the_row_when_the_label_is_not_repaired(self):                         # 3
        self.claimed(5)
        self.fail_on(REPO + "/issues/5/labels/claimed", status=502)
        code, _, err = self.task("close", "5")
        self.assertEqual(code, 0, err)
        self.assertIn("next settle repairs it", err)
        self.assertEqual(self.row(5)["state"], "held")
        report = self.settle()
        self.assertEqual(report["closed"], [{"repo": REPO, "number": 5}])
        self.assertNotIn("claimed", self.gh_issue(5)["labels"])
        self.assertIsNone(self.row(5))

    def test_a_repository_gone_on_a_later_page_keeps_the_row(self):                            # 4
        comments = [{"id": i, "author": "acme-owner", "editor": None, "createdAt": "2026-11-02T00:00:00Z",
                     "body": "c%d" % i} for i in range(1, 151)]
        self.ticket(5, comments=comments)
        code, _, err = self.task("claim", "5")
        self.assertEqual(code, 0, err)
        self.ended()
        self.hook("query TaskComments", [{"vanish": {"repo": REPO}}])
        report = self.settle()
        self.assertEqual([u["repo"] for u in report["unreachable"]], [REPO])
        self.assertEqual(report["closed"], [])
        self.assertEqual(self.row(5)["state"], "held")

    def test_owed_rows_are_retried_when_the_regular_pass_is_throttled(self):                   # 5
        self.owe(5)
        self.set_rows(lambda d: d["settled"].update({"acme/widgets": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                                    time.gmtime())}))
        code, _, err = self.task("list", env={"TASK_SETTLE_EVERY": "3600"})
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.releases(5)), 1)
        self.assertEqual(self.row(5)["state"], "lapsed")

    def test_claim_housekeeping_has_one_budget(self):                                          # 5
        self.owe(5)
        self.ticket(6)
        self.hook("query TaskIssue", [{"sleep": 30}])  # the owed row's read
        started = time.monotonic()
        code, _, err = self.task("claim", "6", env={"TASK_SETTLE_DEADLINE": "2", "TASK_SETTLE_EVERY": "0"})
        self.assertEqual(code, 0, err)
        self.assertLess(time.monotonic() - started, 25)
        self.assertEqual(self.row(5)["state"], "owed")
        self.assertNotEqual(self.row(5)["visited"], "")  # advanced as it was reached
        self.assertEqual(self.index()["running"], {})

    def test_a_row_whose_read_ran_out_is_not_first_next_time(self):                            # 5
        self.claimed(5)
        self.claimed(6)
        self.set_rows(lambda d: [r.update(visited="") for r in d["rows"]] and None)
        self.hook("query TaskIssue", [{"sleep": 30}])
        env = {"TASK_SETTLE_DEADLINE": "2", "TASK_SETTLE_EVERY": "0"}
        self.task("list", env=env)
        first = [r["number"] for r in self.rows() if r["visited"]]
        self.assertEqual(len(first), 1)
        self.clear_log()
        self.task("list", env=env)
        reads = [c for c in self.calls() if "query TaskIssue" in " ".join(c["argv"])]
        number = next(a for a in reads[0]["argv"] if a.startswith("number=")).split("=")[1]
        self.assertNotEqual(int(number), first[0])

    def test_a_budget_spent_in_the_login_is_no_authentication_failure(self):                   # 6
        self.claimed(5)
        self.set_rows(lambda d: d["settled"].clear())
        self.hook("api --hostname github.com user", [{"sleep": 30}])
        code, _, err = self.task("list", env={"TASK_SETTLE_DEADLINE": "2", "TASK_SETTLE_EVERY": "0"})
        self.assertEqual(code, 0, err)
        self.assertNotIn("not authenticated", err)
        self.assertNotIn("acme/widgets", self.index()["settled"])

    def test_a_release_that_meets_a_close_says_so(self):                                       # 6
        self.claimed(5)
        self.hook(COMMENTS, [{"close": {"number": 5}}], when="after", stdin="op: release")
        code, _, err = self.task("release", "5")
        self.assertEqual(code, 3, err)
        self.assertIn("was closed as the release landed", err)
        self.assertNotIn("deleted", err)
        self.assertEqual(len(self.releases(5)), 1)


# ── fix wave 3 ────────────────────────────────────────────────────────────
class WaveThreeTest(SettleCase):
    def test_a_pass_resumes_past_an_owed_row_that_ran_out(self):                               # 1
        # #5 owed, its read slower than the budget each time; #6 held by a thread that has ended since.
        self.claimed(5)
        self.claimed(6, session=OTHER_SESSION)
        self.ended()
        self.fail_on(REPO + "/issues/5/comments", status=502, stdin="reason: ended")
        self.settle("--thread", THREAD)
        self.assertEqual(self.row(5)["state"], "owed")
        self.ended(OTHER_THREAD, OTHER_SESSION)

        def due(d):
            d["settled"].clear()
            for r in d["rows"]:
                r["visited"] = {5: "2026-11-01T00:00:00Z", 6: "2026-11-01T00:00:01Z"}[r["number"]]
        self.set_rows(due)
        self.hook("-F number=5 ", [{"sleep": 30}], times=2)
        env = {"TASK_SETTLE_DEADLINE": "2", "TASK_SETTLE_EVERY": "0"}
        self.task("list", env=env)
        self.assertEqual(self.row(6)["state"], "held")
        self.task("list", env=env)
        self.assertEqual((self.row(6)["state"], self.row(6)["reason"]), ("lapsed", "ended"))
        self.assertEqual(len(self.releases(6)), 1)

    def test_the_second_bound_check_says_what_was_written(self):                               # 2
        # The bound claim is current at the first check; the owed release housekeeping writes moves it.
        claim = self.claimed(5)
        self.ended()
        self.fail_on(REPO + "/issues/5/comments", status=502, stdin="reason: ended")
        self.settle()
        self.assertEqual(self.row(5)["state"], "owed")
        # Another session claims the moment the owed release lands, so the second check finds another holder.
        self.hook(COMMENTS, [{"comment": {"number": 5, "body": claim_body(OTHER_ADDRESS, "00000000000000ff")}}],
                  when="after", stdin="reason: ended")
        code, _, err = self.task("release", "5", "--force", "stale", "--of", str(claim), session=OTHER_SESSION)
        self.assertEqual(code, 3, err)
        self.assertIn("claim %d does not hold #5" % claim, err)
        self.assertIn("no bound release was written", err)
        self.assertNotIn("nothing was written", err)
        self.assertEqual(len(self.releases(5)), 1)

    def test_a_close_with_no_row_names_the_repair(self):                                       # 2
        self.ticket(5, extra=["claimed"])  # unheld, a stale label, no row on this machine
        self.fail_on(REPO + "/issues/5/labels/claimed", status=502)
        code, _, err = self.task("close", "5")
        self.assertEqual(code, 0, err)
        self.assertIn("task show 5 --repo acme/widgets", err)
        self.assertNotIn("next settle", err)


if __name__ == "__main__":
    unittest.main()
