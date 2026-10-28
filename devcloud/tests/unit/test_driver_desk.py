"""The desk as the driver reads it: `sminos machines`, in the shapes the
sminos CLI prints (sminos/skills/sminos/scripts/sminos.py, `cmd_machines` and
`org_age_line`), and the reaper's note on what a deletion leaves there."""

import unittest

import _path  # noqa: F401
from driver import context, images, reaper
from driver_fixtures import DriverBase, NOW, vm_labels

MIN, HOUR = 60, 3600

UNENROLLED = ("this machine is not enrolled at a desk hub (sminos hub enroll): it knows only itself\n"
              "MACHINE  STATE         LIVE  PROJECTS\n"
              "sk       this machine  3     doperpowers\n")
NO_ORG = ("no org directory yet: the daemon has not connected to the hub (sminos daemon run)\n"
          "MACHINE  STATE         LIVE  PROJECTS\n"
          "macbook  this machine  2     -\n")
CURRENT = ("MACHINE      STATE           LIVE  PROJECTS\n"
           "devcloud-m5  never seen      0     -\n"
           "macbook      online          20    doperpowers, macbook\n"
           "mini         last seen 3m ago  2     mini\n")


def aged(listing, age):
    return listing + f"(the org's directory is {age} old: the daemon's stream has said nothing newer)\n"


class ParseTest(unittest.TestCase):
    def test_a_current_listing_of_an_enrolled_machine(self):
        found = context.parse_machines(CURRENT)
        self.assertTrue(found.org)
        self.assertEqual(found.names, ["devcloud-m5", "macbook", "mini"])
        self.assertEqual(found.age, 60, "no age line: the directory is at most a minute old")

    def test_the_directorys_age_is_read_as_its_upper_bound(self):
        self.assertEqual(context.parse_machines(aged(CURRENT, "25m")).age, 26 * 60)
        self.assertEqual(context.parse_machines(aged(CURRENT, "2h")).age, 3 * 3600)
        self.assertEqual(context.parse_machines(aged(CURRENT, "1d")).age, 2 * 86400)

    def test_a_self_only_table_is_no_org_listing_and_never_names_the_header(self):
        for text in (UNENROLLED, NO_ORG):
            found = context.parse_machines(text)
            self.assertFalse(found.org)
            self.assertNotIn("MACHINE", found.names)
            self.assertEqual(len(found.names), 1)

    def test_nothing_parsable_is_none(self):
        self.assertIsNone(context.parse_machines(None))
        self.assertIsNone(context.parse_machines(""))


class DeskNoteTest(DriverBase):
    LISTED = ("stays in the desk's Machines until an admin drops it: run `zsh apps/desk-hub/deploy/production-run.sh admin machine drop dc-a-0001` "
              "(the owner, in a MAWS worktree)")
    UNKNOWN = "may still be in the desk's Machines; if so, run `zsh apps/desk-hub/deploy/production-run.sh admin machine drop "

    def setUp(self):
        super().setUp()
        images.record_build(self.ctx, "main", NOW)      # the daily build is test_driver_images'

    def expired(self, name="dc-a-0001", past=20 * MIN):
        self.add_server(name, vm_labels(expires=NOW - past, **{"devcloud-enroll": "key"}), state="off")

    def log(self):
        return self.paths.reap_log.read_text()

    def test_absence_from_a_listing_newer_than_the_lease_end_needs_no_note(self):
        # The VM departed at its lease end, left the desk, powered off; the reaper deletes it unseen.
        self.desk_output = aged(CURRENT, "5m")
        self.expired()
        reaper.run(self.ctx)
        self.assertNotIn("dc-a-0001", self.servers())
        self.assertNotIn("desk's Machines", self.log())

    def test_absence_from_a_listing_older_than_the_lease_end_proves_nothing(self):
        self.desk_output = aged(CURRENT, "25m")
        self.expired()
        reaper.run(self.ctx)
        self.assertIn(self.UNKNOWN, self.log())

    def test_a_listing_that_still_names_the_vm(self):
        self.desk_output = CURRENT.replace("mini ", "dc-a-0001 ", 1)
        self.expired()
        reaper.run(self.ctx)
        self.assertIn(self.LISTED, self.log())

    def test_an_unenrolled_driver_or_one_without_an_org_directory_cannot_tell(self):
        for i, text in enumerate((UNENROLLED, NO_ORG)):
            self.desk_output = text
            self.expired(name=f"dc-a-000{i}")
            reaper.run(self.ctx)
            self.assertIn(f"dc-a-000{i}", self.log())
            self.assertIn(self.UNKNOWN, self.log().splitlines()[-1])

    def test_no_sminos_cannot_tell(self):
        self.desk_output = None
        self.expired()
        reaper.run(self.ctx)
        self.assertIn(self.UNKNOWN, self.log())

    def test_the_lookup_takes_its_timeout_from_the_bounded_runs_budget(self):
        self.desk_output = aged(CURRENT, "5m")
        self.expired()
        reaper.run(self.ctx, bounded=True)
        self.assertNotIn("dc-a-0001", self.servers())
        [timeout] = self.desk_timeouts
        self.assertLessEqual(timeout, reaper.BOUND)

    def test_a_spent_budget_starts_no_lookup_and_writes_the_cautious_note(self):
        self.desk_output = aged(CURRENT, "5m")
        self.expired()
        with self.ctx.bounded(0.5):
            note = reaper.desk_note(self.ctx, self.servers()["dc-a-0001"], left_desk=False)
        self.assertEqual(self.desk_timeouts, [], "no subprocess once the budget is spent")
        self.assertIn(self.UNKNOWN, note)

    def test_down_without_a_lease_end_behind_it_never_trusts_absence(self):
        # An unreachable VM forced down mid-lease: no moment after which absence would mean it left.
        self.desk_output = CURRENT
        self.add_server("dc-k-0001", vm_labels(expires=NOW + HOUR, **{"devcloud-enroll": "key"}), sid="502")
        note = reaper.desk_note(self.ctx, self.servers()["dc-k-0001"], left_desk=False)
        self.assertIn(self.UNKNOWN, note)


if __name__ == "__main__":
    unittest.main()
