"""The driver's profile (I10's driver.toml), durations, labels (I14) and the
caps of §2."""
import pathlib
import tempfile
import unittest

import _path  # noqa: F401
from driver import caps, labels, profile
from driver.errors import DriverError

from driver_fixtures import DRIVER_TOML


def load(text):
    d = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-profile-"))
    (d / "driver.toml").write_text(text)
    return profile.load(d)


GOOD = DRIVER_TOML.replace("{state}", "/tmp/x").replace("{registered}", "ab" * 32)


class ProfileTest(unittest.TestCase):
    def test_reads_every_section(self):
        p = load(GOOD)
        self.assertEqual(p.caps, profile.Caps(unconfirmed=3, lease_default=None, vcpu_max=8, max_disk_gb=200))
        self.assertEqual(p.default_account, "main")
        self.assertEqual(p.host.sm_project, "example-project")
        self.assertEqual(p.host.config_branch, "main")
        account = p.account("main")
        self.assertEqual((account.provider, account.location, account.type), ("fake", "here", "medium"))
        self.assertEqual(account.env, {"FAKE_TOKEN": "fake-token-secret"})
        self.assertEqual(account.registered, "ab" * 32)
        self.assertIsNone(p.desk_secret)

    def test_unknown_keys_are_refused_naming_them(self):
        for text, key in ((GOOD + "\n[mystery]\nx = 1\n", "mystery"),
                          (GOOD.replace("vcpu_max = 8", "vcpu_max = 8\ncores = 2"), "cores"),
                          (GOOD.replace('type = "medium"', 'type = "medium"\ncommand = "rm"'), "command")):
            with self.subTest(key=key), self.assertRaises(DriverError) as caught:
                load(text)
            self.assertEqual(caught.exception.code, 2)
            self.assertIn(key, str(caught.exception))

    def test_the_default_account_must_exist(self):
        with self.assertRaises(DriverError) as caught:
            load(GOOD.replace('account = "main"', 'account = "nowhere"'))
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("nowhere", str(caught.exception))

    def test_an_unknown_account_is_usage(self):
        with self.assertRaises(DriverError) as caught:
            load(GOOD).account("other")
        self.assertEqual(caught.exception.code, 2)

    def test_no_profile_is_usage(self):
        with self.assertRaises(DriverError) as caught:
            profile.load(pathlib.Path(tempfile.mkdtemp()))
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("driver.toml", str(caught.exception))

    def test_bad_values(self):
        for old, new in (("unconfirmed = 3", 'unconfirmed = 3\nlease_default = "soon"'),
                         ("unconfirmed = 3", 'unconfirmed = "3"'),
                         ('sm_project = "example-project"', ""), ('name = "main"', 'name = "Main Account"'),
                         ('provider = "fake"', 'provider = "../evil"')):
            with self.subTest(new=new), self.assertRaises(DriverError) as caught:
                load(GOOD.replace(old, new))
            self.assertEqual(caught.exception.code, 2)

    def test_lease_default_is_keep_unless_it_names_a_duration(self):
        self.assertIsNone(load(GOOD).caps.lease_default)
        self.assertIsNone(load(GOOD.replace("unconfirmed = 3", 'unconfirmed = 3\nlease_default = "keep"')).caps.lease_default)
        self.assertEqual(load(GOOD.replace("unconfirmed = 3", 'unconfirmed = 3\nlease_default = "12h"')).caps.lease_default,
                         12 * 3600)

    def test_a_replaced_cap_key_is_refused_naming_what_replaced_it(self):
        for old, new, says in (("unconfirmed = 3", "throwaway = 3", "renamed unconfirmed"),
                               ("unconfirmed = 3", 'unconfirmed = 3\nlease_max = "72h"', "no lifetime cap")):
            with self.subTest(new=new), self.assertRaises(DriverError) as caught:
                load(GOOD.replace(old, new))
            self.assertEqual(caught.exception.code, 2)
            self.assertIn(says, str(caught.exception))

    def test_build_env(self):
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "driver.toml").write_text(GOOD)
        (d / "build.env").write_text("DEVCLOUD_USER=dev\nDEVCLOUD_UID=1001\nDEVCLOUD_HOME=/Users/dev\n")
        self.assertEqual(profile.load(d).build, {"DEVCLOUD_USER": "dev", "DEVCLOUD_UID": "1001",
                                                  "DEVCLOUD_HOME": "/Users/dev"})


class DurationTest(unittest.TestCase):
    def test_parse_and_format(self):
        for text, seconds in (("35m", 2100), ("12h", 43200), ("3d", 259200), ("90s", 90), ("1h30m", 5400)):
            self.assertEqual(profile.duration(text), seconds)
        self.assertEqual(profile.format_duration(5400), "1h30m")
        self.assertEqual(profile.format_duration(72 * 3600), "72h")
        for bad in ("", "12", "h", "-5m", "1.5h", "0m"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                profile.duration(bad)


class LabelsTest(unittest.TestCase):
    def test_the_set_i14_allows(self):
        labels.check({"devcloud": "vm", "devcloud-lifetime": "ttl", "devcloud-expires": "1792000000",
                      "devcloud-by": "sk", "devcloud-creator": "abcd1234", "devcloud-recipe": "0123456789ab",
                      "devcloud-confirmed": "1", "devcloud-enroll": "code", "devcloud-held": "1",
                      "devcloud-bake": "failed-setup", "devcloud-test": "m3-run-1"})

    def test_anything_else_is_a_bug_refused_before_a_provider_runs(self):
        for bad in ({"devcloud": "server"}, {"devcloud": "vm", "owner": "me"}, {"devcloud": "vm", "devcloud-by": "SK"},
                    {"devcloud": "vm", "devcloud-test": "a" * 64}, {"devcloud": "vm", "devcloud-held": "yes"},
                    {"devcloud-lifetime": "ttl"}):
            with self.subTest(bad=bad), self.assertRaises(DriverError) as caught:
                labels.check(bad)
            self.assertEqual(caught.exception.code, 1)

    def test_machine_names_become_label_values(self):
        self.assertEqual(labels.machine("SK"), "sk")
        self.assertEqual(labels.machine("Studio-2.local"), "studio-2")
        self.assertEqual(labels.machine("Kim's Mac_Book"), "kim-s-mac-book")


def vm(lifetime="keep", confirmed=False, kind="vm", **labels_):
    lab = {"devcloud": kind, "devcloud-lifetime": lifetime, **labels_}
    if confirmed:
        lab["devcloud-confirmed"] = "1"
    return {"id": "1", "name": "n", "labels": lab, "created": 0}


CAPS = profile.Caps(unconfirmed=3, vcpu_max=8, max_disk_gb=200)


def request(**kw):
    base = dict(type="medium", vcpus=4, type_disk_gb=160, disk_gb=None, confirmed=False)
    base.update(kw)
    return caps.Request(**base)


class CapsTest(unittest.TestCase):
    def test_unconfirmed_vms_count_kept_or_leased(self):
        fleet = [vm(), vm(lifetime="ttl"), vm(confirmed=True), vm(lifetime="ttl", confirmed=True),
                 vm(kind="builder"), vm(kind="test")]
        self.assertEqual(len(caps.unconfirmed(fleet)), 2)

    def test_within_every_cap(self):
        verdict = caps.check(request(), CAPS, alive=2)
        self.assertIsNone(verdict.refusal)
        self.assertEqual(verdict.line, "unconfirmed 2/3 ok, size 4/8 vCPU ok, disk 160/200 GB ok")

    def test_each_cap_refuses_and_names_itself_and_confirmed(self):
        cases = (
            (dict(), 3, "over the count cap (3 unconfirmed alive, cap 3)"),
            (dict(type="big", vcpus=16, type_disk_gb=360), 0, "over the size cap (8 vCPU)"),
            (dict(type="small", vcpus=2, type_disk_gb=40, disk_gb=500), 0, "500 GB is over the disk cap (200 GB)"),
        )
        for kw, alive, text in cases:
            with self.subTest(text=text):
                verdict = caps.check(request(**kw), CAPS, alive=alive)
                self.assertIsNotNone(verdict.refusal)
                self.assertIn(text, verdict.refusal)
                self.assertIn("--confirmed", verdict.refusal)
                self.assertIsNone(caps.check(request(confirmed=True, **kw), CAPS, alive=alive).refusal)

    def test_the_count_message_is_the_one_the_spec_shows(self):
        self.assertEqual(caps.check(request(), CAPS, alive=3).refusal,
                         "over the count cap (3 unconfirmed alive, cap 3): ask the person, then pass --confirmed")
        self.assertEqual(caps.check(request(type="small", vcpus=2, type_disk_gb=40, disk_gb=500), CAPS, 0).refusal,
                         "500 GB is over the disk cap (200 GB): ask the person, then pass --confirmed")

    def test_a_types_own_disk_is_never_capped(self):
        # A type within the size cap whose own disk is above the disk cap.
        self.assertIsNone(caps.check(request(type="bigdisk", vcpus=8, type_disk_gb=600), CAPS, 0).refusal)
        self.assertIsNone(caps.check(request(type="bigdisk", vcpus=8, type_disk_gb=600, disk_gb=600), CAPS, 0).refusal)
        # A requested disk above the cap but not above the type's own is the type's own.
        self.assertIsNone(caps.check(request(type="bigdisk", vcpus=8, type_disk_gb=600, disk_gb=300), CAPS, 0).refusal)
        # Above the type's own, within the cap.
        self.assertIsNone(caps.check(request(type="small", vcpus=2, type_disk_gb=40, disk_gb=200), CAPS, 0).refusal)

    def test_a_confirmed_request_passes_a_full_count(self):
        verdict = caps.check(request(confirmed=True), CAPS, alive=3)
        self.assertIsNone(verdict.refusal)
        self.assertEqual(verdict.line, "unconfirmed 3/3 confirmed, size 4/8 vCPU ok, disk 160/200 GB ok")


if __name__ == "__main__":
    unittest.main()
