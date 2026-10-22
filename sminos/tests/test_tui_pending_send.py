#!/usr/bin/env python3
"""Pending TUI sends survive stopped-member folding, never target removal.

Exercise the real snapshot, layout, keymap and headless send action. Only the
registry/harness inputs and external CLI process are stand-ins; no harness or
runtime configuration is read. HOME and SMINOS_HOME are temporary throughout.
"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "sminos" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sminos  # noqa: E402
import sminos_tui as tui  # noqa: E402


class PendingSend(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory(prefix="sminos-tui-"))
        self.enterContext(mock.patch.dict(os.environ, {
            "HOME": temp + "/home", "SMINOS_HOME": temp + "/sminos",
        }))
        self.project = sminos.make_project("local-compose", "compose", "", temp)
        self.target = self.member("11111111-1111-4111-8111-111111111111", "writer")
        self.other = self.member("22222222-2222-4222-8222-222222222222", "other")
        self.rows = [self.target, self.other]
        self.enterContext(mock.patch.object(sminos, "view_projects", return_value=([self.project], False)))
        self.enterContext(mock.patch.object(sminos, "project_rows", side_effect=lambda _: self.rows))
        self.enterContext(mock.patch.object(sminos, "harness_row", return_value={"id": "11111111"}))
        self.run_cli = self.enterContext(mock.patch.object(
            tui.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "sent", "")))
        self.state = tui.new_state(project="compose")
        tui.resnapshot(self.state)
        self.target_id = self.state["focus"]
        self.actions = tui.HeadlessActions(self.state)
        self.keys("s", *"pending message")
        self.assertIsNotNone(self.state["input"])

    def member(self, sid, alias, state="busy"):
        return sminos.Member(
            session=sid, short=sid[:8], alias=alias, name_source="seat", machine="testhost", local=True,
            state=state, state_age=None, charge="", charge_source="", status="", by="", worktree="",
            seat={"seat_id": sid, "group": "compose", "alias": alias, "current": sid, "short": sid[:8]},
        )

    def keys(self, *keys):
        for key in keys:
            tui.handle_key(self.state, key, self.actions)

    def resnapshot_with(self, *rows):
        self.rows = list(rows)
        tui.resnapshot(self.state)
        self.assertNotIn(self.target_id, self.state["lay"]["by_id"])

    def assert_sent_to_target(self):
        self.keys("enter")
        self.run_cli.assert_called_once_with(
            [sminos.LAUNCHER, "send", self.target.seat["seat_id"], "pending message"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertIsNone(self.state["input"])
        self.assertIsNone(self.state["input_target"])

    def assert_not_sent(self):
        self.keys("enter")
        self.run_cli.assert_not_called()
        self.assertIn("nothing was sent", self.state["flash"][0])
        self.assertIsNone(self.state["input"])
        self.assertIsNone(self.state["input_target"])

    def test_stopping_during_composition_does_not_discard_send(self):
        self.resnapshot_with(self.target._replace(state="stopped"))
        self.assertIsNone(self.state["focus"])
        self.assert_sent_to_target()

    def test_stopped_target_is_not_replaced_by_refresh_focus(self):
        self.resnapshot_with(self.target._replace(state="stopped"), self.other)
        self.assertEqual(tui.focused_node(self.state)["ref"], self.other.seat["seat_id"])
        self.assert_sent_to_target()

    def test_focus_change_does_not_retarget_a_live_send(self):
        tui.drive(self.state, "!focus:compose/other")
        self.assert_sent_to_target()

    def test_removed_stopped_target_is_not_sent_from_a_stale_capture(self):
        self.resnapshot_with(self.target._replace(state="stopped"), self.other)
        self.resnapshot_with(self.other)
        self.assert_not_sent()

    def test_same_alias_on_a_new_stopped_seat_does_not_replace_removed_target(self):
        replacement = self.member("33333333-3333-4333-8333-333333333333", "writer", "stopped")
        self.resnapshot_with(replacement, self.other)
        self.assert_not_sent()

    def test_dropped_live_box_is_still_refused(self):
        tui.drive(self.state, "!drop:compose/writer")
        self.assert_not_sent()

    def test_hidden_retired_or_gone_target_is_still_refused(self):
        for state in ("retired", "gone"):
            with self.subTest(state=state):
                self.rows = [self.target, self.other]
                tui.resnapshot(self.state)
                tui.drive(self.state, "!focus:compose/writer")
                self.keys("s", *"pending message")
                self.resnapshot_with(self.target._replace(state=state), self.other)
                self.assert_not_sent()


if __name__ == "__main__":
    unittest.main()
