"""A project's `devenv/host.toml` (I11, §9): its validation, where it is read
from (the session's checkout, else GitHub), and how `up` applies it — flags
over the file over the profile, the caps applied, every refusal before
anything is created."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import _path  # noqa: F401
from driver import hostfile
from driver.errors import DriverError

from driver_fixtures import NOW, DriverBase, vm_labels
from test_driver_up import UpBase

TWO = """\
[[account]]
name = "other"
provider = "fake"
location = "there"
type = "small"
vars = { FAKE_PROVIDER_STATE = "{state}" }
registered = "{registered}"
"""


class ParseTest(DriverBase):
    def parse(self, text):
        return hostfile.parse(text, self.ctx.profile, "example/repo", "the test")

    def refused(self, text):
        with self.assertRaises(DriverError) as caught:
            self.parse(text)
        return caught.exception.code, str(caught.exception)

    def test_every_key(self):
        wanted = self.parse('account = "main"\ntype = "small"\nlocation = "here"\ndisk_gb = 80\nspot = false\n')
        self.assertEqual((wanted.account, wanted.type, wanted.location, wanted.disk_gb, wanted.spot),
                         ("main", "small", "here", 80, False))
        empty = self.parse("")
        self.assertEqual((empty.account, empty.type, empty.location, empty.disk_gb, empty.spot),
                         (None, None, None, None, None))

    def test_an_unknown_key_is_usage_naming_it(self):
        for key in ("provider", "command", "executable", "address", "env", "Account"):
            with self.subTest(key=key):
                code, message = self.refused(f'{key} = "x"\n')
                self.assertEqual(code, 2)
                self.assertIn(key, message)
                self.assertIn("devenv/host.toml", message)
        code, message = self.refused('[account]\nname = "main"\n')
        self.assertEqual(code, 2)

    def test_an_account_the_profile_lacks_is_usage_naming_it(self):
        code, message = self.refused('account = "elsewhere"\n')
        self.assertEqual(code, 2)
        self.assertIn("elsewhere", message)

    def test_values_of_the_wrong_kind(self):
        for text in ('disk_gb = "big"\n', "disk_gb = 0\n", "disk_gb = true\n", 'spot = "yes"\n', "type = 3\n",
                     'location = ""\n', "account = [1]\n", "not toml at all ===\n"):
            with self.subTest(text=text):
                self.assertEqual(self.refused(text)[0], 2)


class ReadTest(unittest.TestCase):
    """Where the file comes from: the session's own checkout of the project,
    else GitHub at the requested ref through `gh api`."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-hostfile-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.env = {"PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": str(self.tmp)}

    def checkout(self, url):
        repo = self.tmp / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", url], check=True)
        (repo / "devenv").mkdir()
        (repo / "devenv/host.toml").write_text('type = "small"\n')
        (repo / "sub").mkdir()
        return repo

    def gh(self, code=0, out="", err=""):
        log = self.tmp / "gh.args"
        script = self.bin / "gh"
        script.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {log}\nprintf '%s' '{out}'\nprintf '%s' '{err}' >&2\n"
                          f"exit {code}\n")
        script.chmod(0o755)
        return log

    def test_the_sessions_checkout_is_read_from_its_working_tree(self):
        for url in ("https://github.com/Example/Repo.git", "git@github.com:example/repo.git",
                    "ssh://git@github.com/example/repo"):
            with self.subTest(url=url):
                shutil.rmtree(self.tmp / "repo", True)
                repo = self.checkout(url)
                log = self.gh(out='type = "big"\n')
                text, source = hostfile.read("example/repo@feature", repo / "sub", self.env)
                self.assertEqual(text, 'type = "small"\n', "uncommitted edits are read: it can be iterated")
                self.assertIn(str(repo), source)
                self.assertFalse(log.exists(), "GitHub is not asked")

    def test_a_checkout_without_the_file_has_none(self):
        repo = self.checkout("https://github.com/example/repo.git")
        (repo / "devenv/host.toml").unlink()
        self.assertIsNone(hostfile.read("example/repo", repo, self.env)[0])

    def test_another_project_is_read_from_github_at_its_ref(self):
        repo = self.checkout("https://github.com/example/repo.git")
        log = self.gh(out='type = "big"\n')
        text, source = hostfile.read("example/other@feature/x", repo, self.env)
        self.assertEqual(text, 'type = "big"\n')
        args = log.read_text().splitlines()
        self.assertIn("repos/example/other/contents/devenv/host.toml?ref=feature%2Fx", args)
        self.assertIn("GitHub", source)
        hostfile.read("example/other", self.tmp, self.env)
        self.assertIn("repos/example/other/contents/devenv/host.toml", log.read_text().splitlines())

    def test_no_file_on_github_is_none_and_another_failure_is_exit_1(self):
        self.gh(code=1, err="gh: Not Found (HTTP 404)")
        self.assertIsNone(hostfile.read("example/other", self.tmp, self.env)[0])
        self.gh(code=1, err="gh: Bad credentials (HTTP 401)")
        with self.assertRaises(DriverError) as caught:
            hostfile.read("example/other", self.tmp, self.env)
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("example/other", str(caught.exception))

    def test_a_registry_name_is_read_only_from_its_checkout(self):
        repo = self.checkout("https://github.com/example/repo.git")
        log = self.gh(out='type = "big"\n')
        self.assertEqual(hostfile.read("repo", repo, self.env)[0], 'type = "small"\n')
        self.assertIsNone(hostfile.read("elsewhere", repo, self.env)[0])
        self.assertFalse(log.exists())


class UpHostFileTest(UpBase):
    """`up --project` with the project's host.toml (acceptance 8)."""

    def setUp(self):
        super().setUp()
        self.files = {}
        self.ctx = self.make_ctx(token_hex=lambda: next(self.hexes),
                                 host_file=lambda project: (self.files.get(project), f"the test's {project}"))

    def with_other_account(self):
        text = (self.profile_dir / "driver.toml").read_text()
        (self.profile_dir / "driver.toml").write_text(
            text + "\n" + TWO.replace("{state}", str(self.state_file)).replace("{registered}", self.sha))
        import shutil as sh
        sh.copy(self.profile_dir / "providers/.pass/main", self.profile_dir / "providers/.pass/other")
        (self.profile_dir / "providers/other.pass.json").write_text(
            (self.profile_dir / "providers/main.pass.json").read_text())
        self.ctx.reload_profile()

    def create(self):
        return [c for c in self.state()["calls"] if c["op"] == "create"][0]["input"]

    def test_the_file_chooses_type_location_and_disk(self):
        self.files["example/repo"] = 'type = "small"\nlocation = "there"\ndisk_gb = 30\n'
        self.assertEqual(self.up(project=["example/repo"]), 0)
        create = self.create()
        self.assertEqual((create["type"], create["location"], create["disk_gb"]), ("small", "there", 30))
        self.assertIn("host.toml", self.out.getvalue())

    def test_flags_win_over_the_file(self):
        self.files["example/repo"] = 'type = "small"\nlocation = "there"\ndisk_gb = 30\n'
        self.assertEqual(self.up(project=["example/repo"], type="medium", location="here", disk=170), 0)
        create = self.create()
        self.assertEqual((create["type"], create["location"], create["disk_gb"]), ("medium", "here", 170))

    def test_the_file_chooses_among_the_profiles_accounts(self):
        self.with_other_account()
        self.files["example/repo"] = 'account = "other"\n'
        self.assertEqual(self.up(project=["example/repo"], dry_run=True), 0)
        out = self.out.getvalue()
        self.assertIn("account   other (fake)  location there  type small", out)

    def test_a_flag_account_drops_the_files_account_bound_choices(self):
        self.with_other_account()
        self.files["example/repo"] = 'account = "other"\ntype = "big"\nlocation = "there"\ndisk_gb = 30\n'
        self.assertEqual(self.up(project=["example/repo"], account="main", dry_run=True), 0)
        out = self.out.getvalue()
        self.assertIn("account   main (fake)  location here  type medium", out)
        self.assertIn("30 GB requested", out, "the disk is not bound to an account")
        self.assertIn("ignored", out)

    def test_the_caps_apply_to_the_files_choices(self):
        self.files["example/repo"] = 'type = "big"\n'
        code, message = self.refused(project=["example/repo"], dry_run=True)
        self.assertEqual(code, 4)
        self.assertIn("size cap", message)
        self.files["example/repo"] = 'type = "small"\ndisk_gb = 500\n'
        code, message = self.refused(project=["example/repo"], dry_run=True)
        self.assertEqual((code, message), (4, "500 GB is over the disk cap (200 GB): ask the person, then pass "
                                              "--confirmed"))

    def test_spot_on_a_provider_without_it_is_exit_3(self):
        self.files["example/repo"] = "spot = true\n"
        code, message = self.refused(project=["example/repo"], dry_run=True)
        self.assertEqual(code, 3)
        self.assertIn("spot", message)

    def test_a_bad_file_exits_2_before_any_provider_is_called(self):
        for text, named in (('provider = "evil"\n', "provider"), ('command = "rm -rf /"\n', "command"),
                            ('executable = "/tmp/x"\n', "executable"), ('account = "nowhere"\n', "nowhere")):
            with self.subTest(text=text):
                self.files["example/repo"] = text
                code, message = self.refused(project=["example/repo"])
                self.assertEqual(code, 2)
                self.assertIn(named, message)
        self.assertEqual(self.state()["calls"], [], "nothing created, no provider run, not even the reaper")

    def test_the_first_project_governs_and_the_others_are_reported(self):
        self.files["example/repo"] = 'type = "small"\n'
        self.files["example/second"] = 'type = "big"\n'
        self.assertEqual(self.up(project=["example/repo", "example/second", "example/third"], dry_run=True), 0)
        out = self.out.getvalue()
        self.assertIn("type small", out)
        self.assertIn("example/second", out)
        self.assertIn("ignored", out)
        self.assertNotIn("example/third", out, "a project with no file has nothing to report")

    def test_an_ignored_projects_bad_file_does_not_stop_up(self):
        self.files["example/second"] = 'provider = "evil"\n'
        self.assertEqual(self.up(project=["example/repo", "example/second"], dry_run=True), 0)

    def test_no_project_reads_no_file(self):
        self.ctx = self.make_ctx(token_hex=lambda: next(self.hexes), host_file=self.fail)
        self.assertEqual(self.up(dry_run=True), 0)

    def fail(self, project):
        raise AssertionError("read a host file with no project")


if __name__ == "__main__":
    unittest.main()
