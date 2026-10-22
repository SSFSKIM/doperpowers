#!/usr/bin/env python3
"""Display-only folding of stopped sessions, through the real CLI in a temp home."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "skills/sminos/scripts/sminos.py"
STOPPED = "abc00001-0000-4000-8000-000000000001"
GONE = "abc00002-0000-4000-8000-000000000002"

class ListFold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="sminos-fold-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.home = Path(cls.temp.name)
        cls.cwd = cls.home / "fold"
        cls.cwd.mkdir()
        (cls.home / "other").mkdir()
        (cls.home / "sleepers").mkdir()
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith(("SMINOS_", "SMNS_", "CLAUDE_CODE_"))}
        cls.env.update(HOME=str(cls.home), SMINOS_HOME=str(cls.home / "registry"), DAEMON_HOST="testhost")
        subprocess.run(["git", "init", "-q", str(cls.cwd)], env=cls.env, check=True)
        cls.cli("project", "init", "--name", "fold")
        cls.cli("seat", "add", "fold", "stopped-seat", "--session", STOPPED)
        cls.cli("seat", "add", "fold", "gone-seat", "--session", GONE)
        cls.cli("seat", "add", "fold", "retired-seat")
        cls.cli("meta", "set", "fold/retired-seat", "status", "retired")
        cls.cli("seat", "add", "fold", "vacant-seat")
        cls.cli("seat", "add", "other", "other-vacant", cwd=cls.home / "other")
        cls.cli("seat", "add", "sleepers", "only-stopped", "--session",
                "abc00003-0000-4000-8000-000000000003", cwd=cls.home / "sleepers")
        transcripts = cls.home / ".claude/projects/fake-project"
        transcripts.mkdir(parents=True)
        for session in (STOPPED, "abc00003-0000-4000-8000-000000000003"):
            (transcripts / (session + ".jsonl")).write_text(
                json.dumps({"type": "user", "message": {"role": "user", "content": "start"}}) + "\n")

    @classmethod
    def cli(cls, *args, cwd=None):
        r = subprocess.run([sys.executable, str(CLI), *args], cwd=cwd or cls.cwd, env=cls.env, text=True, capture_output=True)
        if r.returncode:
            raise AssertionError(f"{args}: {r.returncode}\n{r.stdout}\n{r.stderr}")
        return r.stdout

    def assert_folded(self, text, stopped=False):
        self.assertIn("vacant-seat", text)
        self.assertNotIn("retired-seat", text)
        self.assertNotIn("gone-seat", text)
        (self.assertIn if stopped else self.assertNotIn)("stopped-seat", text)

    def test_default_text_scopes_fold_stopped(self):
        for args in [(), ("fold",), ("--org",), ("--here",), ("--project", "fold"), ("--machine", "testhost")]:
            with self.subTest(args=args):
                text = self.cli("list", *args)
                self.assert_folded(text)
                hidden = 4 if args in (("--org",), ("--here",), ("--machine", "testhost")) else 3
                self.assertIn(f"+{hidden} hidden (stopped, retired, gone)", text)
                self.assertIn("--stopped", text)
                self.assertIn("--all", text)

    def test_stopped_option_adds_only_stopped_and_keeps_filters(self):
        for args in [(), ("--org",), ("--here",), ("--project", "fold")]:
            with self.subTest(args=args):
                text = self.cli("list", *args, "--stopped")
                self.assert_folded(text, stopped=True)
                self.assertIn("+2 hidden (retired, gone)", text)
                self.assertNotIn("--stopped", text)
        text = self.cli("list", "--stopped", "--state", "vacant")
        self.assertNotIn("stopped-seat", text)
        self.assertIn("vacant-seat", text)
        self.assertNotIn("hidden", text)

    def test_explicit_state_all_and_json_keep_members(self):
        for state in ("stopped", "retired", "gone"):
            text = self.cli("list", "--state", state)
            self.assertIn(state + "-seat", text)
            self.assertNotIn("hidden", text)
        text = self.cli("list", "--all")
        self.assertNotIn("hidden", text)
        for alias in ("stopped-seat", "gone-seat", "retired-seat", "vacant-seat"):
            self.assertIn(alias, text)
        for flags in [(), ("--stopped",), ("--all",)]:
            rows = json.loads(self.cli("list", "--json", *flags))
            self.assertEqual({row["state"] for row in rows}, {"stopped", "retired", "gone", "vacant"})

    def test_find_shares_fold_options(self):
        self.assertNotIn("stopped-seat", self.cli("find", "stopped-seat"))
        self.assertIn("stopped-seat", self.cli("find", "stopped-seat", "--stopped"))

    def test_visibility_options_do_not_widen_default_scope(self):
        for command in ("list", "chart"):
            for flags in ((), ("--stopped",)):
                with self.subTest(command=command, flags=flags):
                    text = self.cli(command, *flags)
                    self.assertNotIn("other-vacant", text)
                    self.assertNotIn("only-stopped", text)
        self.assertIn("other-vacant", self.cli("list", "--org", "--stopped"))

    def test_stopped_only_empty_views_explain_how_to_unfold(self):
        chart = self.cli("chart", "sleepers")
        self.assertIn("no members to chart", chart)
        self.assertIn("1 hidden", chart)
        self.assertIn("--stopped", chart)
        self.assertIn("--all", chart)
        self.assertIn("only-stopped", self.cli("chart", "sleepers", "--stopped"))
        tui = self.cli("tui", "sleepers", "--headless", "--width", "180", "--height", "50")
        self.assertIn("hidden (stopped, retired or gone)", tui)
        self.assertIn("press a to show them", tui)
        help_text = self.cli("tui", "fold", "--headless", "--width", "180", "--height", "50", "--keys", "?")
        self.assertIn("a — show / hide stopped, retired and gone members", help_text)

    def test_chart_folds_stopped_and_can_add_only_stopped(self):
        self.assert_folded(self.cli("chart", "fold"))
        text = self.cli("chart", "fold", "--stopped")
        self.assert_folded(text, stopped=True)
        self.assertIn("2 hidden", text)
        text = self.cli("chart", "fold")
        self.assertIn("3 hidden", text)
        self.assertIn("--stopped", text)
        self.assertIn("--all", text)
        for alias in ("stopped-seat", "gone-seat", "retired-seat"):
            self.assertIn(alias, self.cli("chart", "fold", "--all"))

    def test_tui_default_folds_stopped_and_a_unfolds(self):
        self.assert_folded(self.cli("tui", "fold", "--headless", "--width", "160", "--height", "50"))
        text = self.cli("tui", "fold", "--headless", "--width", "160", "--height", "50", "--keys", "a")
        for alias in ("stopped-seat", "gone-seat", "retired-seat", "vacant-seat"):
            self.assertIn(alias, text)

if __name__ == "__main__":
    unittest.main()
