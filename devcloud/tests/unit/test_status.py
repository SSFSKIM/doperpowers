import json
import pathlib
import stat
import tempfile
import unittest

import _path  # noqa: F401
from devcloudlib import status


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "status.json"

    def test_records_steps_in_boot_order_whatever_order_they_run(self):
        status.record("secrets", "ok", "2 written", path=self.path)
        status.record("identity", "ok", "sbx-1", path=self.path)
        status.record("configuration", "failed", "fetch failed", path=self.path)
        steps = json.loads(self.path.read_text())["steps"]
        self.assertEqual([s["name"] for s in steps], ["identity", "configuration", "secrets"])
        self.assertEqual(set(steps[0]), {"name", "state", "at", "detail"})
        self.assertRegex(steps[0]["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o644)

    def test_a_step_run_again_replaces_its_entry(self):
        status.record("seed", "failed", "no token", path=self.path)
        status.record("seed", "ok", "gce-metadata", path=self.path)
        self.assertEqual(status.load(self.path)["steps"], [dict(status.load(self.path)["steps"][0], state="ok")])
        self.assertEqual(status.load(self.path)["steps"][0]["detail"], "gce-metadata")

    def test_reset_starts_a_boot_from_nothing(self):
        status.record("seed", "ok", "", path=self.path)
        status.reset(path=self.path)
        self.assertEqual(status.load(self.path), {"steps": []})

    def test_refuses_an_unknown_step_or_state(self):
        with self.assertRaises(ValueError):
            status.record("lunch", "ok", "", path=self.path)
        with self.assertRaises(ValueError):
            status.record("seed", "fine", "", path=self.path)

    def test_render_and_health(self):
        self.assertFalse(status.healthy(status.load(self.path)))
        for name in status.STEPS:
            status.record(name, "skipped" if name == "projects" else "ok", f"{name} detail", path=self.path)
        data = status.load(self.path)
        self.assertTrue(status.healthy(data))
        lines = status.render(data).splitlines()
        self.assertEqual(len(lines), len(status.STEPS))
        self.assertRegex(lines[0], r"^identity\s+ok\s+\S+\s+identity detail$")
        status.record("apply", "failed", "exit 1", path=self.path)
        self.assertFalse(status.healthy(status.load(self.path)))


if __name__ == "__main__":
    unittest.main()
