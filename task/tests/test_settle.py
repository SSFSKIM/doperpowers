"""Acceptance 13 (holders in what is read), 14 (settle) and 15 (held)."""
import json
import subprocess
import time
import unittest

from harness import (ADDRESS, ME, OTHER_ADDRESS, OTHER_SESSION, OTHER_THREAD, REPO, SESSION, TASK, THREAD,
                     board_file, claim_body, release_body, takeover_body, thread_answer)
from test_claim import ClaimCase

GEARS = "acme/gears"


class SettleCase(ClaimCase):
    def claimed(self, n=5, session=SESSION, repo=REPO, **kw):
        self.ticket(n, repo=repo, **kw)
        code, _, err = self.task("claim", str(n), session=session, repo=repo)
        self.assertEqual(code, 0, err)
        return self.records_of(n, repo)[-1]["id"]

    def records_of(self, n, repo=REPO):
        return [c for c in self.gh_issue(n, repo)["comments"] if c["body"].startswith("```task-claim")]

    def ended(self, thread=THREAD, session=SESSION, **kw):
        self.sminos["threads"][thread] = thread_answer(thread, session, ended=True, **kw)
        self.save()

    def settle(self, *args, **kw):
        code, out, err = self.task("settle", "--json", *args, repo=False, **kw)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def row(self, n, repo=REPO):
        rows = [r for r in self.rows() if r["number"] == n and r["repo"] == repo]
        return rows[0] if rows else None

    def set_rows(self, fn):
        p = self.tmp / "task-home" / "claims.json"
        data = json.loads(p.read_text())
        fn(data)
        p.write_text(json.dumps(data))

    def releases(self, n=5, repo=REPO):
        return [c for c in self.records_of(n, repo) if "op: release" in c["body"]]


class HoldersTest(SettleCase):
    def test_show_and_list_name_the_holder(self):
        claim = self.claimed()
        self.assertEqual(self.json("show", "5")["holder"], {"address": ADDRESS, "claim": claim,
                                                           "since": self.records()[0]["createdAt"]})
        self.assertEqual(self.json("list")["tickets"][0]["holder"]["claim"], claim)
        self.assertEqual(self.json("list", "--claimed")["tickets"][0]["number"], 5)
        self.assertEqual(self.json("list", "--unclaimed")["tickets"], [])

    def test_a_holder_without_the_label(self):
        for verb in ("show", "list"):
            with self.subTest(verb=verb):
                n = 5 if verb == "show" else 6
                self.ticket(n, comments=[{"id": 70 + n, "author": ME, "editor": None,
                                          "createdAt": "2026-11-02T00:00:00Z", "body": claim_body(OTHER_ADDRESS)}])
                code, out, _ = self.task("lint")
                self.assertIn("WARN #%d held by %s" % (n, OTHER_ADDRESS), out)
                self.assertIn("task show %d --repo %s" % (n, REPO), out)
                self.assertEqual(self.writes(), [])
                if verb == "show":
                    v = self.json("show", str(n))
                else:
                    v = next(t for t in self.json("list")["tickets"] if t["number"] == n)
                self.assertEqual(v["holder"]["address"], OTHER_ADDRESS)
                self.assertIn("held", v["not_takeable"])
                self.assertNotIn(n, [t["number"] for t in self.json("list", "--takeable")["tickets"]])
                self.assertIn("claimed", self.gh_issue(n)["labels"])
                self.clear_log()

    def test_the_label_without_a_holder(self):
        for verb in ("show", "list"):
            with self.subTest(verb=verb):
                n = 5 if verb == "show" else 6
                self.ticket(n, extra=["claimed"])
                code, out, _ = self.task("lint")
                self.assertIn("WARN #%d `claimed`, and its claims leave it unheld" % n, out)
                self.assertEqual(self.writes(), [])
                if verb == "show":
                    v = self.json("show", str(n))
                else:
                    v = next(t for t in self.json("list")["tickets"] if t["number"] == n)
                self.assertIsNone(v["holder"])
                self.assertNotIn("claimed", self.gh_issue(n)["labels"])
                self.assertIn(n, [t["number"] for t in self.json("list", "--takeable")["tickets"]])
                self.clear_log()


class SettleTest(SettleCase):
    def test_a_thread_that_has_ended(self):                                                      # (a)
        claim = self.claimed()
        self.ended()
        report = self.settle()
        self.assertEqual(report["released"], [{"repo": REPO, "number": 5, "title": "a ticket",
                                               "url": "https://github.com/acme/widgets/issues/5", "claim": claim,
                                               "reason": "ended"}])
        [rel] = self.releases()
        self.assertIn("of: %d\nreason: ended\n" % claim, rel["body"])
        self.assertNotIn("claimed", self.gh_issue(5)["labels"])
        self.assertEqual((self.row(5)["state"], self.row(5)["reason"]), ("lapsed", "ended"))
        self.assertEqual(report["owed"], 0)

    def test_answers_that_do_not_release(self):                                                  # (b), (c)
        self.claimed()
        for case, answer, said in (("another thread", thread_answer(OTHER_THREAD, SESSION, ended=True),
                                    "another thread"),
                                   ("not local", thread_answer(THREAD, SESSION, ended=True, local=False), "not local"),
                                   ("exit 4", None, "exit 4"),
                                   ("live", thread_answer(THREAD, SESSION), None)):
            with self.subTest(case=case):
                if answer is None:
                    self.sminos["threads"].pop(THREAD, None)
                else:
                    self.sminos["threads"][THREAD] = answer
                self.save()
                self.clear_log()
                report = self.settle()
                self.assertEqual(self.writes(), [])
                self.assertEqual(report["released"], [])
                if said:
                    [u] = report["unknown"]
                    self.assertEqual((u["number"], u["thread"], u["said"]), (5, THREAD, said))
                else:
                    self.assertEqual(report["unknown"], [])
                self.assertEqual(self.row(5)["state"], "held")
                self.assertEqual(self.sminos_calls(), [["who", "--thread=%s" % THREAD]])

    def test_one_thread(self):                                                                   # (d)
        self.claimed(5)
        self.claimed(7, session=OTHER_SESSION)
        self.ended(OTHER_THREAD, OTHER_SESSION)
        self.ended()
        self.claimed(6)  # sminos then called it ended; it has returned since, and claimed again
        self.sminos["threads"][THREAD] = thread_answer(THREAD, SESSION)
        self.save()
        self.clear_log()
        report = self.settle("--thread", THREAD)
        self.assertEqual((report["released"], report["unknown"]), ([], []))
        self.assertEqual(self.sminos_calls(), [["who", "--thread=%s" % THREAD]])
        self.assertEqual([self.row(n)["state"] for n in (5, 6, 7)], ["held", "held", "held"])
        self.assertEqual(self.writes(), [])

    def test_a_closed_ticket(self):                                                               # (e)
        self.claimed()
        self.load()
        self.state["repos"][REPO]["issues"]["5"]["state"] = "CLOSED"
        self.save()
        report = self.settle()
        self.assertEqual(report["closed"], [{"repo": REPO, "number": 5}])
        self.assertNotIn("claimed", self.gh_issue(5)["labels"])
        self.assertIsNone(self.row(5))

    def test_no_sminos(self):                                                                    # (f)
        self.claimed()
        self.clear_log()
        report = self.settle(env={"TASK_SMINOS": ""})
        self.assertEqual(report["unknown"][0]["said"], "no sminos")
        self.assertEqual(self.writes(), [])

    def test_github_failing_the_release_is_owed(self):                                            # (g)
        for then in ("settle", "a writing verb"):
            with self.subTest(then=then):
                n = 5 if then == "settle" else 6
                self.claimed(n)
                self.ended()
                self.fail_on(REPO + "/issues/%d/comments" % n, status=502, stdin="reason: ended")
                report = self.settle()
                self.assertEqual(report["owed"], 1)
                self.assertEqual(self.row(n)["state"], "owed")
                self.assertEqual(report["unreachable"][0]["repo"], REPO)
                self.assertEqual(self.releases(n), [])
                if then == "settle":
                    self.assertEqual(self.settle()["owed"], 0)
                else:
                    code, _, err = self.task("comment", str(n), "--body-file", self.body_file("Noted.\n"))
                    self.assertEqual(code, 0, err)
                self.assertEqual(len(self.releases(n)), 1)
                self.assertEqual(self.row(n)["state"], "lapsed")
                self.settle()
                self.assertEqual(len(self.releases(n)), 1)
                self.sminos["threads"][THREAD] = thread_answer(THREAD, SESSION)
                self.save()

    def test_killed_after_the_release_was_accepted(self):                                          # (h)
        claim = self.claimed()
        self.ended()
        self.hook(REPO + "/issues/5/comments", [{"kill": True}], when="after", stdin="reason: ended")
        code, _, _ = self.task("settle", repo=False)
        self.assertLess(code, 0)
        self.assertEqual(self.row(5)["state"], "owed")
        self.clear_log()
        self.settle()
        self.assertEqual((self.row(5)["state"], self.row(5)["reason"]), ("lapsed", "ended"))
        self.assertEqual(len(self.releases()), 1)
        self.assertIn("of: %d" % claim, self.releases()[0]["body"])
        self.assertFalse(any(c["stdin"] and "task-claim" in c["stdin"] for c in self.writes()))

    def test_a_row_with_no_thread(self):                                                           # (i)
        self.sminos["threads"][SESSION] = thread_answer("", SESSION)
        self.save()
        self.claimed()
        self.clear_log()
        report = self.settle()
        self.assertEqual((report["released"], report["unknown"]), ([], []))
        self.assertEqual(self.sminos_calls(), [])
        self.assertEqual(self.row(5)["state"], "held")

    def test_a_claim_another_session_took_over(self):                                              # (j)
        claim = self.claimed()
        self.comment(5, takeover_body(claim), 9500, created="2026-11-03T00:00:00Z")
        self.load()
        self.state["repos"][REPO]["issues"]["5"]["labels"].remove("claimed")
        self.save()
        report = self.settle()
        self.assertEqual(report["lapsed"], [{"repo": REPO, "number": 5, "reason": "taken-over"}])
        self.assertEqual(self.row(5)["state"], "lapsed")
        self.assertIn("claimed", self.gh_issue(5)["labels"])
        self.assertEqual(self.json("show", "5")["holder"]["address"], OTHER_ADDRESS)

    def test_a_held_row_whose_label_is_lost(self):                                                 # (k)
        self.claimed()
        self.load()
        self.state["repos"][REPO]["issues"]["5"]["labels"].remove("claimed")
        self.save()
        self.settle()
        self.assertIn("claimed", self.gh_issue(5)["labels"])
        self.assertEqual(self.row(5)["state"], "held")

    def test_one_board_refused(self):                                                              # (l)
        self.add_repo(GEARS)
        self.save()
        self.claimed(5)
        self.claimed(8, repo=GEARS)
        self.ended()
        self.fail_on("owner=acme -f name=gears", times=5, status=502)
        report = self.settle()
        self.assertEqual([r["number"] for r in report["released"]], [5])
        self.assertEqual([u["repo"] for u in report["unreachable"]], [GEARS])
        self.assertEqual(self.row(8, GEARS)["state"], "held")

    def test_pending_rows(self):                                                                   # (m)
        for case in ("current", "void", "taken", "missing"):
            with self.subTest(case=case):
                n = {"current": 5, "void": 6, "taken": 7, "missing": 8}[case]
                self.ticket(n)
                token = "%016x" % n
                if case == "void":
                    self.comment(n, claim_body(OTHER_ADDRESS, "00000000000000cc"), 9400 + n)
                self.comment(n, claim_body(ADDRESS, token) if case != "missing" else "Unrelated.", 9500 + n,
                             created="2026-11-03T00:00:00Z")
                if case == "taken":
                    self.comment(n, takeover_body(9500 + n), 9600 + n, created="2026-11-04T00:00:00Z")

                def add(data, n=n, token=token):
                    data["rows"].append({"repo": REPO, "number": n, "title": "", "url": "", "claim": None,
                                         "attempt": token, "session": SESSION, "thread": THREAD, "address": ADDRESS,
                                         "since": "2026-11-03T00:00:00Z", "successor": "", "state": "pending",
                                         "reason": "", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                         "visited": "", "tries": 0})
                (self.tmp / "task-home").mkdir(exist_ok=True)
                p = self.tmp / "task-home" / "claims.json"
                if not p.exists():
                    p.write_text(json.dumps({"v": 1, "settled": {}, "rows": []}))
                self.set_rows(add)
                self.settle()
                row = self.row(n)
                if case == "current":
                    self.assertEqual((row["state"], row["claim"]), ("held", 9500 + n))
                    self.assertIn("claimed", self.gh_issue(n)["labels"])
                elif case == "void":
                    self.assertIsNone(row)
                    self.assertNotIn(9500 + n, [c["id"] for c in self.gh_issue(n)["comments"]])
                elif case == "taken":
                    self.assertEqual((row["state"], row["reason"]), ("lapsed", "taken-over"))
                    self.assertIn(9500 + n, [c["id"] for c in self.gh_issue(n)["comments"]])
                    self.assertEqual(self.json("show", str(n))["holder"]["claim"], 9600 + n)
                else:
                    self.assertEqual(row["state"], "pending")

                    def age(data, n=n):
                        for r in data["rows"]:
                            if r["number"] == n:
                                r["at"] = "2026-11-01T00:00:00Z"
                    self.set_rows(age)
                    self.settle()
                    self.assertIsNone(self.row(n))

    def test_before_list_and_claim(self):                                                          # (n), (o)
        self.add_repo(GEARS)
        self.save()
        self.claimed(5)
        self.claimed(8, repo=GEARS)
        self.ended()
        every = {"TASK_SETTLE_EVERY": "3600"}
        self.set_rows(lambda d: d["settled"].update({REPO: "2026-11-01T00:00:00Z"}))
        # Within the interval of a pass that completed: no settle.
        self.set_rows(lambda d: d["settled"].update({REPO: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
        self.clear_log()
        self.json("list", env=every)
        self.assertEqual(self.sminos_calls(), [])
        # Older than the interval: list settles its board's rows, and no other board's.
        self.set_rows(lambda d: d["settled"].update({REPO: "2026-11-01T00:00:00Z"}))
        [t] = self.json("list", env=every)["tickets"]
        self.assertIsNone(t["holder"])
        self.assertEqual(self.row(5)["state"], "lapsed")
        self.assertEqual(self.row(8, GEARS)["state"], "held")
        self.assertNotEqual(self.index()["settled"][REPO], "2026-11-01T00:00:00Z")
        # From the board's own clone, and with --repo, the other board's row stays.
        clone = self.clone()
        self.ticket(6)
        self.set_rows(lambda d: d["settled"].clear())
        self.clear_log()
        code, _, err = self.task("claim", "6", cwd=clone, repo=False, env=every)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.row(8, GEARS)["state"], "held")
        self.assertFalse(any("gears" in " ".join(c["argv"]) for c in self.calls()))

    def test_a_failing_settle_fails_no_verb(self):
        self.claimed()
        self.ended()
        self.set_rows(lambda d: d["settled"].clear())
        self.fail_on("reason: ended", status=502)
        self.fail_on(REPO + "/issues/5/comments", status=502, stdin="reason: ended")
        code, out, err = self.task("list", "--json", env={"TASK_SETTLE_EVERY": "0"})
        self.assertEqual(code, 0, err)
        self.assertIn("settle", err)
        self.assertEqual(self.row(5)["state"], "owed")

    def test_two_verbs_started_together_run_one_settle(self):
        self.claimed()
        self.set_rows(lambda d: d["settled"].clear())
        self.hook("query TaskIssue", [{"sleep": 2}])  # the first pass reads its row slowly
        self.clear_log()
        env = dict(self.env(), TASK_SETTLE_EVERY="0")
        argv = [str(TASK), "list", "--json", "--repo", REPO]
        first = subprocess.Popen(argv, cwd=str(self.outside), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(1)
        second = subprocess.run(argv, cwd=str(self.outside), env=env, capture_output=True, timeout=60)
        first.communicate(timeout=60)
        self.assertEqual((first.returncode, second.returncode), (0, 0))
        self.assertEqual(self.sminos_calls().count(["who", "--thread=%s" % THREAD]), 1)


class HeldTest(SettleCase):
    def heldjson(self, *args, **kw):
        code, out, err = self.task("held", *args, "--json", repo=False, **kw)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_held_lapsed_and_offered(self):
        claim = self.claimed(5)
        self.claimed(6)
        self.claimed(7, session=OTHER_SESSION)
        self.comment(6, takeover_body(self.records_of(6)[-1]["id"]), 9700, created="2026-11-03T00:00:00Z")
        self.settle("--thread", THREAD)
        for _ in range(2):  # on every call, not once
            out = self.heldjson("--session", SESSION, "--thread", THREAD)
            self.assertEqual([(h["number"], h["claim"]) for h in out["held"]], [(5, claim)])
            self.assertEqual([(l["number"], l["reason"]) for l in out["lapsed"]], [(6, "taken-over")])
            self.assertEqual(out["offered"], [])
        out = self.heldjson("--session", "88888888-aaaa-4bbb-8ccc-000000000008", "--cleared-from", THREAD)
        self.assertEqual(([o["number"] for o in out["offered"]], out["held"], out["lapsed"]), ([5], [], []))
        self.assertEqual(self.row(7)["successor"], "")
        self.assertEqual(set(out), {"v", "held", "lapsed", "offered"})
        self.assertEqual(set(out["offered"][0]), {"repo", "number", "title", "url", "claim", "since"})

    def test_a_lapsed_row_is_reported_for_seven_days(self):
        self.claimed(5)
        self.set_rows(lambda d: d["rows"][0].update(state="lapsed", reason="ended",
                                                    at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        self.assertEqual(len(self.heldjson("--session", SESSION, "--thread", THREAD)["lapsed"]), 1)
        code, _, err = self.task("list")
        self.assertIn("your claim on %s#5 lapsed (ended" % REPO, err)
        self.ticket(6)
        code, _, err = self.task("claim", "6")
        self.assertIn("your claim on %s#5 lapsed" % REPO, err)
        code, _, err = self.task("list", session=OTHER_SESSION)
        self.assertNotIn("lapsed", err)
        self.set_rows(lambda d: d["rows"][0].update(at="2026-11-01T00:00:00Z"))
        self.assertEqual(self.heldjson("--session", SESSION, "--thread", THREAD)["lapsed"], [])
        self.assertIsNone(self.row(5))

    def test_no_network_and_no_repository(self):
        self.claimed(5)
        self.fail_on("", times=100, status=502)
        self.clear_log()
        out = self.heldjson("--session", SESSION, "--thread", THREAD)
        self.assertEqual([h["number"] for h in out["held"]], [5])
        self.assertEqual(self.calls(), [])

    def test_settle_with_github_failing_every_call_still_answers(self):
        self.claimed(5)
        self.fail_on("", times=100, status=502)
        report = self.settle()
        self.assertEqual(report["unreachable"][0]["repo"], REPO)


if __name__ == "__main__":
    unittest.main()
