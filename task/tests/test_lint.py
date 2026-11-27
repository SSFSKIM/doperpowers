"""Acceptance 6: lint, the FAILs of Interfaces §6 and the WARNs that need no
fold."""
import json
import unittest

from harness import OUTSIDER, BoardCase

GOOD = ["ready-to-work", "expected", "priority:P3", "bug"]


class LintTest(BoardCase):
    def lint(self):
        self.clear_log()
        code, out, err = self.task("lint")
        self.assertEqual(self.writes(), [])
        return code, out

    def assert_finds(self, level, n, words, labels=GOOD, **kw):
        self.issue(n, labels=labels, **kw)
        code, out = self.lint()
        lines = [l for l in out.splitlines() if l.startswith(level) and ("#%d " % n) in l]
        self.assertTrue(lines, out)
        self.assertIn(words, lines[0])
        self.assertIn("task ", lines[0])  # names the repair
        self.assertEqual(code, 3 if level == "FAIL" else 0, out)
        del self.state["repos"]["acme/widgets"]["issues"][str(n)]
        self.save()

    def test_a_clean_board(self):
        self.issue(1, labels=GOOD)
        self.issue(2, labels=["bug"], author=OUTSIDER)    # untracked, with a category: neither
        code, out = self.lint()
        self.assertEqual(code, 0, out)
        self.assertFalse([l for l in out.splitlines() if l.startswith(("FAIL", "WARN"))], out)
        self.assertIn("1 untracked", out)

    def test_each_fail(self):
        cases = [
            (["ready-to-work", "need-design", "expected", "priority:P3", "bug"], "readiness", {}),
            (["ready-to-work", "priority:P3", "bug"], "horizon", {}),
            (["ready-to-work", "expected", "planned", "priority:P3", "bug"], "horizon", {}),
            (["expected", "bug"], "no readiness", {}),
            (["claimed", "bug"], "no readiness", {}),
            (GOOD + ["priority:P1"], "priorit", {}),
            (GOOD + ["spike"], "categor", {}),
            (GOOD + ["status:deferred"], "status:deferred", {}),
            (["status:in-design", "bug"], "status:in-design", {}),
            (GOOD, "record", {"body": "Text.\n\n```task-record\nowner: x\n```"}),
            (GOOD, "record", {"body": "Text.\n\n```task-record\ndue: someday\n```"}),
            (GOOD, "record", {"body": "```task-record\ndue: 2027-01-01\n```\n\nText after."}),
            (GOOD, "record", {"body": "```task-record\nspec: a\n```\n\n```task-record\nspec: b\n```"}),
        ]
        for i, (labels, words, kw) in enumerate(cases):
            with self.subTest(case=i, words=words):
                self.assert_finds("FAIL", 40 + i, words, labels, **kw)

    def test_a_malformed_block_in_an_untrusted_body_is_not_judged(self):
        self.issue(5, labels=GOOD, editor=OUTSIDER, body="Text.\n\n```task-record\nowner: x\n```")
        code, out = self.lint()
        self.assertEqual(code, 0, out)

    def test_a_cycle(self):
        self.issue(1, labels=GOOD, blocked_by=[3])
        self.issue(2, labels=GOOD, blocked_by=[1])
        self.issue(3, labels=GOOD, blocked_by=[2])
        code, out = self.lint()
        self.assertEqual(code, 3)
        lines = [l for l in out.splitlines() if "cycle" in l]
        self.assertEqual(len(lines), 1, out)
        self.assertIn("task edge", lines[0])

    def test_each_warn(self):
        self.issue(90, labels=GOOD, state="CLOSED", reason="NOT_PLANNED")
        cases = [
            (["ready-to-work", "planned", "priority:P3", "bug"], "planned", {}),
            (GOOD, "not planned", {"blocked_by": [90]}),
            (["ready-to-work", "expected", "bug"], "priority", {}),
            (["ready-to-work", "expected", "priority:P3"], "category", {}),
        ]
        for i, (labels, words, kw) in enumerate(cases):
            with self.subTest(case=i, words=words):
                self.assert_finds("WARN", 60 + i, words, labels, **kw)

    def test_a_stuck_repair_names_a_usable_blocker(self):
        self.add_repo("acme/gears")
        self.issue(7, repo="acme/gears", labels=GOOD, state="CLOSED", reason="NOT_PLANNED")
        self.issue(90, labels=GOOD, state="CLOSED", reason="NOT_PLANNED")
        self.issue(91, labels=GOOD, state="CLOSED", reason=None)
        self.issue(1, labels=GOOD, blocked_by=[90, 91, ("acme/gears", 7)])
        code, out = self.lint()
        lines = [l for l in out.splitlines() if l.startswith("WARN #1 ")]
        self.assertEqual(len(lines), 3, out)
        self.assertIn("task edge 1 --unblock 90,", lines[0] + lines[1] + lines[2])
        self.assertIn("task edge 1 --unblock 91,", "".join(lines))
        self.assertIn("task edge 1 --unblock 'acme/gears#7',", "".join(lines))

    def test_json(self):
        self.issue(1, labels=GOOD + ["status:deferred"])
        self.issue(2, labels=["bug"])
        code, out, _ = self.task("lint", "--json")
        self.assertEqual(code, 3)
        data = json.loads(out)
        self.assertEqual([f["number"] for f in data["fail"]], [1])
        self.assertEqual(data["untracked"], 1)


if __name__ == "__main__":
    unittest.main()
