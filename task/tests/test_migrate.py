"""Acceptance 8: the relabel, `task migrate plan` and `task migrate apply`
(D6, Interfaces §8)."""
import json
import os
import shutil
import stat
import sys
import unittest

from harness import OUTSIDER, REPO, TASK, BoardCase, board_file

sys.path.insert(0, str(TASK.parent.parent / "cli"))
import record  # noqa: E402

META_BODY = ("Build the thing.\n\nIt has two parts.\n\n<!-- board:meta\nspawned-by: #3\nrelates-to: #4 #5\n"
             "branch: feat/thing\npr: https://github.com/acme/widgets/pull/77\n"
             "plan: docs/specs/thing.md@0123abc\nnote: waits on the vendor's answer\n-->\n")
META_AFTER = ("Build the thing.\n\nIt has two parts.\n\nSpawned by: #3\n\nRelated: #4 #5\n\nBranch: feat/thing\n\n"
              "Pull request: https://github.com/acme/widgets/pull/77\n\nBoard note: waits on the vendor's answer\n\n"
              "```task-record\nspec: docs/specs/thing.md@0123abc\n```")
NOTE_BODY = "Ask the owner which vendor.\n\n<!-- board:meta\nnote: 1. which vendor? 2. by when?\n-->\n"
BANNER = ("`arkho-board:ticket:66` — mirrored from the Arkho board.\n"
          "**Read-only.** Edits here are reverted; closing this issue does not close the ticket. The board is the "
          "source of truth.\n"
          "Board ticket: https://board.example.invalid/ui/t/66\n")
BANNER_REST = "\n---\n\nThe prompt still pastes the whole task.\n\nKeep it short.\n"
BANNER_BODY = BANNER + BANNER_REST
BANNER_AFTER = "_Moved from board ticket 66 on the retired board service._\n" + BANNER_REST
ON_BOARD_BODY = "Already moved.\n\n<!-- board:meta\nrelates-to: #1\n-->\n"
ON_BOARD_AFTER = "Already moved.\n\nRelated: #1\n"

# number -> (status labels, readiness, horizon, basis) as the plan proposes them.
EXPECTED = {
    1: (["status:ready-for-implementer"], "ready-to-work", "expected", "mechanical"),
    2: (["status:ready-for-architect"], "need-design", "planned", "mechanical"),
    3: (["status:interactive-preferred"], "need-design", "expected", "mechanical"),
    4: (["status:needs-human"], "need-input", "expected", "mechanical"),
    5: (["status:needs-info"], "need-input", "expected", "mechanical"),
    6: (["status:blocked"], "need-input", "expected", "mechanical"),
    7: (["status:ready-for-agent"], "ready-to-work", "expected", "mechanical"),
    8: (["status:deferred"], "need-design", "undecided", "decision"),
    9: (["status:in-design"], "need-design", "expected", "decision"),
    10: (["status:in-progress"], "ready-to-work", "expected", "decision"),
    11: (["status:in-review"], "ready-to-work", "expected", "decision"),
    12: (["status:confident-ready"], "ready-to-work", "expected", "decision"),
    13: (["status:ready-for-implementer", "status:deferred"], "need-design", "undecided", "decision"),
    14: ([], "need-design", "undecided", "decision"),
    16: (["status:ready-for-implementer"], "ready-to-work", "expected", "mechanical"),
}


class MigrateCase(BoardCase):
    def setUp(self):
        super().setUp()
        self.state["repos"][REPO]["files"][".doperpowers/board.json"] = board_file(binding="gh")
        for n, (statuses, _, _, _) in EXPECTED.items():
            self.issue(n, title="ticket %d" % n, labels=statuses + ["priority:P3", "bug"])
        self.issue(1, title="ticket 1", body=META_BODY, labels=["status:ready-for-implementer", "priority:P3", "bug"])
        self.issue(2, title="ticket 2", labels=["status:ready-for-architect", "priority:P2", "enhancement"],
                   blocked_by=[3])
        self.issue(4, title="ticket 4", body=NOTE_BODY, labels=["status:needs-human", "priority:P3", "bug"])
        self.issue(8, title="ticket 8", body=BANNER_BODY, labels=["status:deferred", "priority:P3", "bug"])
        self.issue(9, title="ticket 9", labels=["status:in-design", "priority:P3", "bug"], blocked_by=[18])
        self.issue(15, title="a visitor's report", labels=["bug"], author=OUTSIDER)
        self.issue(16, title="ticket 16", body=META_BODY, editor=OUTSIDER,
                   labels=["status:ready-for-implementer", "priority:P3", "bug"])
        self.ticket(17, body=ON_BOARD_BODY)
        self.issue(18, title="closed long ago", labels=["status:ready-for-implementer", "bug"], state="CLOSED")
        self.state["repos"][REPO]["labels"] = {"status:deferred": {"color": "cccccc", "description": "old"}}
        self.save()
        self.plan_path = self.tmp / "plans" / "plan.json"

    # ── helpers ──────────────────────────────────────────────────────────
    def load_plan(self):
        return json.loads(self.plan_path.read_text())

    def plan(self, *extra):
        code, out, err = self.task("migrate", "plan", "--out", str(self.plan_path), *extra)
        self.assertEqual(code, 0, err)
        return json.loads(self.plan_path.read_text()), out

    def rows(self, plan):
        return {r["number"]: r for r in plan["rows"]}

    def decide(self, plan, **choices):
        """Settle every decision row: `choices[n]` is (readiness, horizon) or "leave"; the fallback otherwise."""
        for r in plan["rows"]:
            if r["decided"]:
                continue
            choice = choices.get("n%d" % r["number"])
            if choice == "leave":
                r["action"] = "leave"
            elif choice:
                r["readiness"], r["horizon"] = choice
            r["why"] = "read it: a test's choice"
            r["decided"] = True
        self.plan_path.write_text(json.dumps(plan))

    def flip(self):
        self.load()
        self.state["repos"][REPO]["files"][".doperpowers/board.json"] = board_file()
        self.save()

    def apply(self):
        return self.task("migrate", "apply", str(self.plan_path))

    def decided_plan(self):
        plan, _ = self.plan()
        self.decide(plan, n14="leave", n10=("ready-to-work", "expected"))
        self.flip()
        return plan

    def board_labels(self, n):
        return sorted(l for l in self.gh_issue(n)["labels"]
                      if l.startswith("status:") or l in ("ready-to-work", "need-design", "need-input", "planned",
                                                          "expected", "undecided"))

    def issue_writes(self, n):
        """The writes the log holds for issue n, each as (method, path, data)."""
        out = []
        for c in self.writes():
            if "graphql" in c["argv"]:
                continue
            method, path, data = self.rest(c)
            if path == "repos/%s/issues/%d" % (REPO, n) or path.startswith("repos/%s/issues/%d/" % (REPO, n)):
                out.append((method, path, json.dumps(data, sort_keys=True)))
        return out


class PlanTest(MigrateCase):
    def test_the_plan_marks_each_row_and_records_what_it_read(self):
        plan, out = self.plan()
        self.assertEqual(plan["v"], 1)
        self.assertEqual(plan["repo"], REPO)
        self.assertEqual(plan["incoming"], [15])
        rows = self.rows(plan)
        self.assertEqual(sorted(rows), sorted(list(EXPECTED) + [17]))
        for n, (statuses, readiness, horizon, basis) in EXPECTED.items():
            with self.subTest(n=n):
                r = rows[n]
                self.assertEqual((r["readiness"], r["horizon"], r["basis"]), (readiness, horizon, basis))
                self.assertEqual(r["action"], "relabel")
                self.assertEqual(r["decided"], basis == "mechanical")
                issue = self.gh_issue(n)
                self.assertEqual(r["seen"]["state"], "open")
                self.assertEqual(r["seen"]["labels"], issue["labels"])
                self.assertEqual(r["seen"]["body"], record.digest(issue["body"]))
                self.assertEqual(r["title"], issue["title"])
                if basis == "decision":
                    self.assertTrue(r["question"], r)
        self.assertEqual(rows[2]["seen"]["blockers"], [{"repo": REPO, "number": 3, "state": "open"}])
        self.assertEqual(rows[9]["seen"]["blockers"], [{"repo": REPO, "number": 18, "state": "completed"}])
        self.assertTrue(rows[1]["seen"]["body_trusted"])
        self.assertFalse(rows[16]["seen"]["body_trusted"])
        self.assertEqual(rows[1]["body_after"], META_AFTER)
        self.assertEqual(rows[8]["body_after"], BANNER_AFTER)
        self.assertIsNone(rows[16]["body_after"])
        self.assertIsNone(rows[3]["body_after"])
        self.assertEqual(rows[17]["action"], "body")
        self.assertEqual((rows[17]["readiness"], rows[17]["horizon"]), ("ready-to-work", "expected"))
        self.assertEqual(rows[17]["body_after"], ON_BOARD_AFTER)
        self.assertTrue(rows[17]["decided"])
        self.assertEqual(self.writes(), [])

    def test_the_summary_counts_and_names_the_decisions(self):
        _, out = self.plan()
        self.assertIn("16 rows: 9 mechanical, 7 decisions; incoming: 1", out)
        for n in (8, 9, 10, 11, 12, 13, 14):
            self.assertIn("#%d " % n, out)

    def test_the_plan_is_the_owners_alone_and_outside_any_tree(self):
        self.plan()
        self.assertEqual(stat.S_IMODE(os.stat(self.plan_path).st_mode), 0o600)
        clone = self.clone()
        code, _, err = self.task("migrate", "plan", "--out", str(clone / "plan.json"))
        self.assertEqual(code, 2, err)
        self.assertIn("outside", err)
        self.assertFalse((clone / "plan.json").exists())

    def test_a_plan_is_not_written_where_git_cannot_say_there_is_no_tree(self):
        # No git on the PATH: nothing tells the directory is outside every tree.
        nogit = self.tmp / "nogit"
        nogit.mkdir()
        for tool in ("gh", "python3", "bash", "dirname", "readlink"):
            found = self.bin / tool if tool == "gh" else shutil.which(tool)
            (nogit / tool).symlink_to(sys.executable if tool == "python3" else found)
        code, _, err = self.task("migrate", "plan", "--out", str(self.plan_path), env={"PATH": str(nogit)})
        self.assertEqual(code, 1, err)
        self.assertIn("could not tell whether", err)
        self.assertFalse(self.plan_path.exists())
        # Inside a repository's git directory: git declines to answer for a work tree, which decides nothing either.
        clone = self.clone()
        code, _, err = self.task("migrate", "plan", "--out", str(clone / ".git" / "plan.json"))
        self.assertEqual(code, 1, err)
        self.assertIn("could not tell whether", err)
        self.assertFalse((clone / ".git" / "plan.json").exists())
        # Outside every tree in another language, git's answer is still read as no tree.
        code, _, err = self.task("migrate", "plan", "--out", str(self.plan_path), env={"LANG": "ko_KR.UTF-8"})
        self.assertEqual(code, 0, err)
        self.assertTrue(self.plan_path.exists())

    def test_the_probe_ignores_gits_environment(self):
        # As a hook runs: GIT_DIR relative, or a ceiling that hides the checkout from the directory below it.
        clone = self.clone()
        for name, env in (("GIT_DIR", {"GIT_DIR": ".git"}), ("ceiling", {"GIT_CEILING_DIRECTORIES": str(clone)})):
            with self.subTest(env=name):
                out = clone / "sub" / ("plan-%s.json" % name)
                code, _, err = self.task("migrate", "plan", "--out", str(out), env=env)
                self.assertEqual(code, 2, err)
                self.assertIn("inside the work tree", err)
                self.assertFalse(out.exists())

    def test_without_out_the_plan_goes_to_the_plugins_home(self):
        code, out, err = self.task("migrate", "plan")
        self.assertEqual(code, 0, err)
        path = out.splitlines()[0].split("plan: ", 1)[1]
        self.assertTrue(path.startswith(str((self.tmp / "task-home").resolve())), path)
        with open(path) as f:
            self.assertEqual(json.load(f)["repo"], REPO)
        code, out2, err = self.task("migrate", "plan")
        self.assertEqual(code, 0, err)
        self.assertNotEqual(out2.splitlines()[0], out.splitlines()[0])

    def test_a_plan_never_overwrites_a_file_or_follows_a_link(self):
        self.plan_path.parent.mkdir()
        self.plan_path.write_text("someone's file\n")
        target = self.tmp / "elsewhere.txt"
        target.write_text("another file\n")
        link = self.tmp / "plans" / "link.json"
        link.symlink_to(target)
        for path in (self.plan_path, link):
            with self.subTest(path=path.name):
                code, _, err = self.task("migrate", "plan", "--out", str(path))
                self.assertEqual(code, 2, err)
                self.assertIn("exists", err)
        self.assertEqual(self.plan_path.read_text(), "someone's file\n")
        self.assertEqual(target.read_text(), "another file\n")

    def test_plan_needs_only_a_repository(self):
        self.state["repos"][REPO]["files"] = {}
        self.save()
        self.assertEqual(len(self.plan()[0]["rows"]), 16)
        self.plan_path.unlink()
        clone = self.clone(defaults={"origin": self.NOREF})
        code, _, err = self.task("migrate", "plan", "--out", str(self.plan_path), cwd=clone, repo=False)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(self.plan_path.read_text())["repo"], REPO)

    def test_a_board_meta_block_in_quoted_prose_is_not_the_block(self):
        quoted = ("The block looks like this:\n\n    <!-- board:meta\n    note: an example\n    -->\n\nThat is all."
                  "\n\n<!-- board:meta\nnote: the real one\n-->\n")
        self.issue(20, title="quoting", body=quoted, labels=["status:ready-for-implementer"])
        rows = self.rows(self.plan()[0])
        self.assertEqual(rows[20]["body_after"], quoted.split("\n\n<!-- board:meta\nnote: the real")[0]
                         + "\n\nBoard note: the real one\n")

    def test_a_banner_that_differs_is_not_touched(self):
        near = BANNER.replace("Edits here are reverted;", "Edits here may be reverted;") + BANNER_REST
        self.issue(21, title="near", body=near, labels=["status:ready-for-implementer"])
        late = "Text first.\n\n" + BANNER_BODY
        self.issue(22, title="late", body=late, labels=["status:ready-for-implementer"])
        rows = self.rows(self.plan()[0])
        self.assertIsNone(rows[21]["body_after"])
        self.assertIsNone(rows[22]["body_after"])

    def test_a_record_block_stays_last_and_keeps_its_spec(self):
        body = ("Moved early.\n\n<!-- board:meta\nplan: docs/b.md@abc\n-->\n\n```task-record\n"
                "registered-by: someone\nspec: docs/a.md\n```")
        self.ticket(23, body=body)
        rows = self.rows(self.plan()[0])
        self.assertEqual(rows[23]["body_after"], "Moved early.\n\nPlan: docs/b.md@abc\n\n```task-record\n"
                         "registered-by: someone\nspec: docs/a.md\n```")


class BodyTest(MigrateCase):
    def test_an_in_flight_ticket_says_which_state_branch_and_pull_request_it_had(self):
        self.issue(25, title="halfway", labels=["status:in-progress", "bug"], body=(
            "Work.\n\n<!-- board:meta\nbranch: feat/x\npr: https://github.com/acme/widgets/pull/9\nnote: halfway\n"
            "-->\n"))
        self.issue(26, title="theirs", labels=["status:in-review", "bug"], editor=OUTSIDER)
        rows = self.rows(self.plan()[0])
        for n, state in ((9, "in-design"), (10, "in-progress"), (11, "in-review"), (12, "confident-ready")):
            self.assertEqual(rows[n]["body_after"], "Something to do.\n\nBoard state before the relabel: %s." % state)
        self.assertEqual(rows[25]["body_after"], "Work.\n\nBoard note: halfway\n\nBoard state before the relabel: "
                         "in-progress, on branch feat/x, with pull request https://github.com/acme/widgets/pull/9.\n")
        self.assertIsNone(rows[26]["body_after"])
        self.assertEqual(rows[9]["basis"], "decision")
        self.decide(self.load_plan())
        self.flip()
        code, out, err = self.apply()
        self.assertEqual(code, 0, out + err)
        for n in (9, 10, 11, 12, 25):
            self.assertEqual(self.gh_issue(n)["body"], rows[n]["body_after"], n)
        self.assertEqual(self.gh_issue(26)["body"], "Something to do.")

    def test_an_in_flight_line_names_what_github_links_when_the_old_block_did_not(self):
        pr = {"number": 41, "state": "OPEN", "updatedAt": "2026-11-20T00:00:00Z",
              "url": "https://github.com/acme/widgets/pull/41"}
        elsewhere = {"number": 5, "state": "OPEN", "updatedAt": "2026-11-20T00:00:00Z",
                     "url": "https://github.com/acme/private-thing/pull/5"}
        self.issue(31, title="linked", labels=["status:in-progress", "bug"], body="Plain.", prs=[elsewhere, pr],
                   branches=[{"name": "feat/linked", "committedDate": "2026-11-20T00:00:00Z"}])
        self.issue(32, title="both", labels=["status:in-review", "bug"], prs=[pr], body=(
            "Old.\n\n<!-- board:meta\nbranch: feat/old\npr: https://github.com/acme/widgets/pull/7\n-->\n"))
        self.issue(33, title="branch only in the block", labels=["status:in-design", "bug"], prs=[pr], body=(
            "Half.\n\n<!-- board:meta\nbranch: feat/half\n-->\n"))
        self.issue(36, title="only elsewhere", labels=["status:in-progress", "bug"], body="Plain.", prs=[elsewhere])
        rows = self.rows(self.plan()[0])
        self.assertEqual(rows[31]["body_after"], "Plain.\n\nBoard state before the relabel: in-progress, with "
                         "linked branch feat/linked, with linked pull request "
                         "https://github.com/acme/widgets/pull/41.")
        self.assertEqual(rows[32]["body_after"], "Old.\n\nBoard state before the relabel: in-review, on branch "
                         "feat/old, with pull request https://github.com/acme/widgets/pull/7.\n")
        self.assertEqual(rows[33]["body_after"], "Half.\n\nBoard state before the relabel: in-design, on branch "
                         "feat/half, with linked pull request https://github.com/acme/widgets/pull/41.\n")
        self.assertEqual(rows[9]["body_after"], "Something to do.\n\nBoard state before the relabel: in-design.")
        self.assertEqual(rows[36]["body_after"], "Plain.\n\nBoard state before the relabel: in-progress.")
        self.assertNotIn("private-thing", json.dumps(self.load_plan()))

    def test_a_pinned_plan_keeps_the_line_endings_before_its_new_record(self):
        self.issue(34, title="pinned", labels=["status:needs-info"],
                   body="Text.\n\n<!-- board:meta\nnote: n\nplan: docs/a.md@abc\n-->\n\n\n\n")
        self.issue(35, title="tight", labels=["status:needs-info"],
                   body="Text.\n\n<!-- board:meta\nnote: n\nplan: docs/a.md@abc\n-->")
        rows = self.rows(self.plan()[0])
        self.assertEqual(rows[34]["body_after"],
                         "Text.\n\nBoard note: n\n\n\n\n```task-record\nspec: docs/a.md@abc\n```")
        self.assertEqual(rows[35]["body_after"], "Text.\n\nBoard note: n\n\n```task-record\nspec: docs/a.md@abc\n```")

    def test_only_the_legacy_spans_change(self):
        banner = BANNER + "\n---\n\nLine one  \nline two\t \n\n\n```task-record\nregistered-by: someone\n```"
        meta = ("Text  \nmore\t\n\n<!-- board:meta\nnote: n\n-->\n\n\n```task-record\nspec: a.md\n```")
        crlf = "Windows text  \r\nhere\r\n\r\n<!-- board:meta\nnote: n\n-->\n"
        self.ticket(27, body=banner)
        self.issue(28, title="meta", labels=["status:needs-info"], body=meta)
        self.issue(29, title="crlf", labels=["status:needs-info"], body=crlf)
        rows = self.rows(self.plan()[0])
        self.assertEqual(rows[27]["body_after"], "_Moved from board ticket 66 on the retired board service._\n\n---\n\n"
                         "Line one  \nline two\t \n\n\n```task-record\nregistered-by: someone\n```")
        self.assertEqual(rows[28]["body_after"], "Text  \nmore\t\n\nBoard note: n\n\n\n```task-record\nspec: a.md\n```")
        self.assertEqual(rows[29]["body_after"], "Windows text  \r\nhere\r\n\r\nBoard note: n\n")

    def test_an_outsiders_issue_with_an_old_label_is_relabelled_and_never_takeable(self):
        self.issue(24, title="a visitor's, enrolled", labels=["status:ready-for-implementer", "priority:P3", "bug"],
                   author=OUTSIDER, body=META_BODY)
        rows = self.rows(self.plan()[0])
        self.assertNotIn(24, self.load_plan()["incoming"])
        r = rows[24]
        self.assertEqual((r["action"], r["readiness"], r["horizon"], r["basis"]),
                         ("relabel", "ready-to-work", "expected", "mechanical"))
        self.assertFalse(r["seen"]["body_trusted"])
        self.assertIsNone(r["body_after"])
        self.decide(self.load_plan())
        self.flip()
        self.assertEqual(self.apply()[0], 0)
        self.assertEqual(self.board_labels(24), ["expected", "ready-to-work"])
        self.assertEqual(self.gh_issue(24)["body"], META_BODY)
        self.assertNotIn(24, [t["number"] for t in self.json("list", "--takeable")["tickets"]])
        listed = next(t for t in self.json("list")["tickets"] if t["number"] == 24)
        self.assertIn("untrusted-body", listed["not_takeable"])


class ApplyRefusalTest(MigrateCase):
    def test_apply_needs_the_board_to_say_task(self):
        plan, _ = self.plan()
        self.decide(plan)
        self.clear_log()
        code, _, err = self.apply()
        self.assertEqual(code, 1, err)
        self.assertIn('binding "gh"', err)
        self.assertEqual(self.writes(), [])

    def test_apply_refuses_a_plan_for_another_repository(self):
        plan, _ = self.plan()
        self.decide(plan)
        plan["repo"] = "acme/gears"
        self.plan_path.write_text(json.dumps(plan))
        self.flip()
        self.clear_log()
        code, _, err = self.apply()
        self.assertEqual(code, 1, err)
        self.assertIn("acme/gears", err)
        self.assertEqual(self.writes(), [])

    def test_apply_refuses_while_a_decision_is_open(self):
        plan, _ = self.plan()
        self.flip()
        self.clear_log()
        code, _, err = self.apply()
        self.assertEqual(code, 3, err)
        for n in (8, 9, 10, 11, 12, 13, 14):
            self.assertIn("#%d" % n, err)
        self.assertEqual(self.writes(), [])

    def test_a_bad_row_anywhere_stops_the_apply_before_any_write(self):
        good, _ = self.plan()
        self.decide(good)
        self.flip()
        last = max(r["number"] for r in good["rows"])
        breaks = (("decided", lambda r: r.update(decided="yes")),
                  ("why", lambda r: r.update(basis="decision", why=" ")),
                  ("labels", lambda r: r["seen"].update(labels="status:deferred")),
                  ("blockers", lambda r: r["seen"].update(blockers=[{"repo": REPO, "number": "3", "state": "open"}])),
                  ("body", lambda r: r["seen"].update(body="sha256:abc")),
                  ("state", lambda r: r["seen"].update(state="closed")),
                  ("twice", None))
        for name, spoil in breaks:
            with self.subTest(spoil=name):
                plan = json.loads(json.dumps(good))
                row = next(r for r in plan["rows"] if r["number"] == last)
                if spoil is None:
                    plan["rows"].append(json.loads(json.dumps(plan["rows"][0])))
                else:
                    spoil(row)
                self.plan_path.write_text(json.dumps(plan))
                self.clear_log()
                code, _, err = self.apply()
                self.assertEqual(code, 2, err)
                self.assertIn("nothing was written", err)
                self.assertEqual(self.writes(), [])

    def test_a_plan_that_is_no_plan_is_usage(self):
        self.flip()
        for text in ("not json", json.dumps({"v": 2, "repo": REPO, "rows": []}),
                     json.dumps({"v": 1, "repo": REPO, "rows": [{"number": 1, "action": "relabel", "decided": True,
                                                                  "readiness": "soon", "horizon": "expected"}]})):
            with self.subTest(text=text[:20]):
                self.plan_path.parent.mkdir(exist_ok=True)
                self.plan_path.write_text(text)
                code, _, err = self.apply()
                self.assertEqual(code, 2, err)
                self.assertEqual(self.writes(), [])


class ApplyTest(MigrateCase):
    def test_apply_writes_what_was_reviewed(self):
        self.decided_plan()
        before = {n: self.gh_issue(n) for n in (14, 15, 18)}
        definitions = dict(self.load()["repos"][REPO]["labels"])
        self.clear_log()
        code, out, err = self.apply()
        self.assertEqual(code, 0, err + out)
        for n in EXPECTED:
            if n == 14:
                continue
            with self.subTest(n=n):
                labels = self.gh_issue(n)["labels"]
                self.assertEqual(len([l for l in labels if l in ("ready-to-work", "need-design", "need-input")]), 1)
                self.assertEqual(len([l for l in labels if l in ("planned", "expected", "undecided")]), 1)
                self.assertEqual([l for l in labels if l.startswith("status:")], [])
                self.assertIn("priority:", " ".join(labels))
        self.assertEqual(self.board_labels(2), ["need-design", "planned"])
        self.assertEqual(self.board_labels(10), ["expected", "ready-to-work"])
        self.assertEqual(self.gh_issue(1)["body"], META_AFTER)
        t = self.json("show", "1")
        self.assertTrue(t["body_trusted"])
        self.assertEqual(t["record"]["spec"], "docs/specs/thing.md@0123abc")
        self.assertEqual(self.gh_issue(4)["body"], "Ask the owner which vendor.\n\nBoard note: 1. which vendor? "
                         "2. by when?\n")
        self.assertEqual(self.gh_issue(8)["body"], BANNER_AFTER)
        self.assertEqual(self.gh_issue(16)["body"], META_BODY)
        self.assertFalse(self.json("show", "16")["body_trusted"])
        self.assertEqual(self.gh_issue(17)["body"], ON_BOARD_AFTER)
        self.assertEqual(self.label_writes(17), [])
        for n, issue in before.items():
            self.assertEqual(self.gh_issue(n), issue, n)
        for c in self.writes():
            if "graphql" in c["argv"]:
                continue
            method, path, _ = self.rest(c)
            self.assertFalse(path.startswith("repos/%s/labels/" % REPO), path)
            self.assertNotIn("/issues/18", path)
        after = self.load()["repos"][REPO]["labels"]
        for name, definition in definitions.items():
            self.assertEqual(after[name], definition)
        self.assertIn("still carrying an old status label: none", out)
        self.clear_log()
        code, out, err = self.apply()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.writes(), [])
        self.assertIn("writes: 0", out)
        code, out, err = self.task("lint")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("FAIL #", out)

    def test_a_crash_after_each_write_of_a_row_is_finished_by_the_next_apply(self):
        steps = (("repos/%s/issues/1 -X PATCH" % REPO, None),
                 ("repos/%s/issues/1/labels -X POST" % REPO, "expected"),
                 ("repos/%s/issues/1/labels -X POST" % REPO, "ready-to-work"),
                 ("repos/%s/issues/1/labels/status" % REPO, None))
        for match, stdin in steps:
            with self.subTest(after=(match, stdin)):
                self.setUp()
                self.decided_plan()
                self.clear_log()
                self.fail_on(match, stdin=stdin, after=True, status=None, message="connection reset")
                code, out, err = self.apply()
                self.assertEqual(code, 1, out + err)
                self.assertIn("#1", out + err)
                code, out, err = self.apply()
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.gh_issue(1)["body"], META_AFTER)
                self.assertEqual(self.board_labels(1), ["expected", "ready-to-work"])
                writes = self.issue_writes(1)
                self.assertEqual(len(writes), len(set(writes)), writes)
                self.assertEqual(len(writes), 4, writes)

    def test_labels_at_target_over_the_body_as_read_is_someones_edit(self):
        self.decided_plan()
        self.load()
        self.state["repos"][REPO]["issues"]["1"]["labels"] = ["ready-to-work", "expected", "priority:P3", "bug"]
        self.save()
        self.clear_log()
        code, out, err = self.apply()
        self.assertEqual(code, 0, err)
        self.assertIn("#1 skipped", out)
        self.assertEqual(self.gh_issue(1)["body"], META_BODY)
        self.assertEqual(self.issue_writes(1), [])

    def test_a_body_no_longer_trusted_is_not_written(self):
        self.decided_plan()
        self.load()
        self.state["repos"][REPO]["issues"]["1"]["editor"] = OUTSIDER
        self.save()
        self.clear_log()
        code, out, err = self.apply()
        self.assertEqual(code, 0, err)
        self.assertIn("#1 skipped", out)
        self.assertIn("trusted", out)
        self.assertEqual(self.gh_issue(1)["body"], META_BODY)
        self.assertEqual(self.issue_writes(1), [])

    def test_changes_after_the_plan_are_skipped_and_named(self):
        self.decided_plan()
        self.load()
        issues = self.state["repos"][REPO]["issues"]
        issues["4"]["body"] = NOTE_BODY.replace("which vendor.", "which vendor, and why.")
        issues["5"]["state"], issues["5"]["stateReason"] = "CLOSED", "COMPLETED"
        issues["3"]["state"], issues["3"]["stateReason"] = "CLOSED", "COMPLETED"
        issues["7"]["labels"].append("need-design")
        self.save()
        self.clear_log()
        code, out, err = self.apply()
        self.assertEqual(code, 0, err)
        for n, what in ((4, "body"), (5, "closed"), (2, "blocker"), (7, "label")):
            with self.subTest(n=n):
                line = next(l for l in out.splitlines() if l.startswith("#%d skipped" % n))
                self.assertIn(what, line)
                self.assertEqual(self.issue_writes(n), [])
        self.assertEqual(self.gh_issue(4)["body"], NOTE_BODY.replace("which vendor.", "which vendor, and why."))

    def test_a_row_a_conflict_left_midway_is_taken_up_by_a_fresh_plan(self):
        self.decided_plan()
        self.clear_log()
        self.fail_on("repos/%s/issues/2/labels -X POST" % REPO, stdin="need-design", status=500,
                     message="Server Error")
        self.assertEqual(self.apply()[0], 1)
        self.assertEqual(self.board_labels(2), ["planned", "status:ready-for-architect"])
        self.load()
        self.state["repos"][REPO]["issues"]["2"]["labels"] += ["undecided", "need-input"]
        self.save()
        code, out, _ = self.apply()
        self.assertIn("#2 skipped", out)
        self.plan_path.unlink()
        plan, _ = self.plan()
        self.assertEqual(self.rows(plan)[2]["seen"]["labels"][-2:], ["undecided", "need-input"])
        self.decide(plan)
        code, out, err = self.apply()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.board_labels(2), ["need-design", "planned"])

    def test_an_issue_opened_since_the_plan_is_named_at_the_end(self):
        self.decided_plan()
        self.issue(30, title="new", labels=["status:needs-info", "bug"])
        code, out, err = self.apply()
        self.assertEqual(code, 0, err)
        self.assertRegex(out, r"still carrying an old status label: .*#30")
        self.assertEqual(self.gh_issue(30)["labels"], ["status:needs-info", "bug"])


if __name__ == "__main__":
    unittest.main()
