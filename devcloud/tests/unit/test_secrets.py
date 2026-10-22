import json
import os
import pathlib
import stat
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import secrets
from devcloudlib.secretmanager import AccessError

TOML = '''
[[secret]]
name = "gh-token"
store = "GH_TOKEN"
file = "~/.config/gh/hosts.yml"
template = """github.com:
    oauth_token: {value}
    git_protocol: https
"""

[[secret]]
name = "api-key"
env = "EXAMPLE_API_KEY"

[[secret]]
name = "pgpass"
file = "~/.pgpass"
mode = "0600"

[[secret]]
name = "later"
store = "LATER"
optional = true
'''


class ParseTest(unittest.TestCase):
    def test_reads_every_field_with_defaults(self):
        entries = secrets.parse(TOML)
        self.assertEqual([e.name for e in entries], ["gh-token", "api-key", "pgpass", "later"])
        gh = entries[0]
        self.assertEqual((gh.store, gh.env, gh.file, gh.mode, gh.optional), ("GH_TOKEN", None, "~/.config/gh/hosts.yml", 0o600, False))
        self.assertIn("{value}", gh.template)
        self.assertTrue(entries[3].optional)

    def test_refuses_what_it_cannot_honor(self):
        cases = {
            "name": '[[secret]]\nstore = "K"\n',
            "unknown": '[[secret]]\nname = "a"\nstore = "K"\noptinal = true\n',
            "target": '[[secret]]\nname = "a"\n',
            "store": '[[secret]]\nname = "a"\nstore = "1BAD"\n',
            "env": '[[secret]]\nname = "a"\nenv = "A-B"\n',
            "~/": '[[secret]]\nname = "a"\nfile = "/etc/passwd"\n',
            "inside": '[[secret]]\nname = "a"\nfile = "~/../../etc/x"\n',
            "template": '[[secret]]\nname = "a"\nenv = "A"\ntemplate = "x{value}"\n',
            "mode": '[[secret]]\nname = "a"\nfile = "~/x"\nmode = "rw"\n',
            "TOML": '[[secret]\nname = "a"\n',
            "twice": '[[secret]]\nname = "a"\nenv = "A"\n[[secret]]\nname = "b"\nenv = "A"\n',
        }
        for word, body in cases.items():
            with self.subTest(word=word), self.assertRaisesRegex(secrets.ProfileError, word):
                secrets.parse(body)

    def test_a_file_that_leaves_the_home_or_is_the_home_is_refused(self):
        """`~//etc/passwd` starts with ~/ and holds no `..`, but joined to the
        home it is /etc/passwd: listed in the ledger, the release would
        remove it as root. The home itself is no file either."""
        for file in ("~//etc/passwd", "~/", "~/.", "~/./", "~/a/../../x"):
            with self.subTest(file=file), self.assertRaisesRegex(secrets.ProfileError, "inside the home"):
                secrets.parse(f'[[secret]]\nname = "a"\nfile = "{file}"\n')

    def test_an_empty_or_absent_list_is_nothing_to_do(self):
        self.assertEqual(secrets.parse(""), [])


class MaterializeTest(unittest.TestCase):
    VALUES = {
        "gh-token": b"made-up-gh-value\n",
        "api-key": b"made-up-api-value\n",
        "pgpass": b"host:5432:db:user:made-up-pg-value\n",
    }

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        self.home = root / "home"
        self.home.mkdir()
        self.manifest = root / "state/secrets-manifest.json"
        patch = mock.patch.object(secrets, "MANIFEST", self.manifest, create=True)
        patch.start()
        self.addCleanup(patch.stop)

    def run_with(self, values, toml=TOML):
        def fetch(name):
            value = values.get(name)
            if isinstance(value, Exception):
                raise value
            return value
        return secrets.materialize(secrets.parse(toml), fetch, self.home)

    def test_writes_store_files_and_env_targets(self):
        out = self.run_with(self.VALUES)
        store = self.home / ".config/claude-secrets"
        self.assertEqual(stat.S_IMODE(store.stat().st_mode), 0o700)
        key = store / "GH_TOKEN"
        self.assertEqual(key.read_bytes(), b"made-up-gh-value\n")
        self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
        hosts = self.home / ".config/gh/hosts.yml"
        self.assertEqual(hosts.read_text(), "github.com:\n    oauth_token: made-up-gh-value\n    git_protocol: https\n")
        self.assertEqual(stat.S_IMODE(hosts.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(hosts.parent.stat().st_mode), 0o700)
        self.assertEqual((self.home / ".pgpass").read_bytes(), self.VALUES["pgpass"])
        self.assertEqual(out.env, {"EXAMPLE_API_KEY": "made-up-api-value"})
        self.assertEqual(out.state, "missing")
        self.assertTrue(out.detail.startswith("3 written; missing: later"))

    def test_all_present_is_ok(self):
        out = self.run_with(dict(self.VALUES, later=b"x"))
        self.assertEqual(out.state, "ok")
        self.assertTrue(out.detail.startswith("4 written"))

    def test_a_required_absence_or_error_fails_after_trying_the_rest(self):
        values = dict(self.VALUES, later=b"x")
        del values["api-key"]
        values["pgpass"] = AccessError("HTTP 403")
        out = self.run_with(values)
        self.assertEqual(out.state, "failed")
        self.assertTrue(out.detail.startswith("2 written; failed: api-key (absent from Secret Manager), pgpass (HTTP 403)"))
        self.assertTrue((self.home / ".config/claude-secrets/LATER").exists())

    def test_a_rerun_converges_and_follows_a_rotation(self):
        self.run_with(self.VALUES)
        rotated = dict(self.VALUES, **{"gh-token": b"rotated-made-up\n"})
        self.run_with(rotated)
        self.assertEqual((self.home / ".config/claude-secrets/GH_TOKEN").read_bytes(), b"rotated-made-up\n")
        leftovers = [p.name for p in (self.home / ".config/claude-secrets").iterdir() if p.name.startswith(".")]
        self.assertEqual(leftovers, [])

    def test_never_follows_a_symlink_planted_at_a_target(self):
        victim = self.home / "victim"
        victim.write_text("untouched")
        (self.home / ".pgpass").symlink_to(victim)
        self.run_with(self.VALUES)
        self.assertEqual(victim.read_text(), "untouched")
        self.assertFalse((self.home / ".pgpass").is_symlink())

    def test_removed_entries_delete_owned_files_and_drop_env_but_not_user_files(self):
        self.run_with(self.VALUES)
        user_file = self.home / ".config/claude-secrets/USER_KEY"
        user_file.write_text("made-up-user-key")
        out = self.run_with({}, toml="")
        self.assertEqual((out.state, out.env), ("ok", {}))
        for target in (".config/claude-secrets/GH_TOKEN", ".config/gh/hosts.yml", ".pgpass"):
            self.assertFalse((self.home / target).exists(), target)
        self.assertEqual(user_file.read_text(), "made-up-user-key")
        self.assertEqual(self.run_with({}, toml="").state, "ok")

    def test_renamed_targets_remove_old_files_and_keep_new_ones(self):
        self.run_with(self.VALUES)
        renamed = TOML.replace('store = "GH_TOKEN"', 'store = "NEW_TOKEN"').replace(
            'file = "~/.config/gh/hosts.yml"', 'file = "~/.config/gh/new.yml"')
        self.run_with(self.VALUES, toml=renamed)
        self.assertFalse((self.home / ".config/claude-secrets/GH_TOKEN").exists())
        self.assertFalse((self.home / ".config/gh/hosts.yml").exists())
        self.assertEqual((self.home / ".config/claude-secrets/NEW_TOKEN").read_bytes(), self.VALUES["gh-token"])
        self.assertTrue((self.home / ".config/gh/new.yml").exists())
        self.assertTrue((self.home / ".pgpass").exists())

    def test_user_edits_replacements_symlinks_and_directories_survive_removal(self):
        for replacement in ("edit", "same-content", "symlink", "directory"):
            with self.subTest(replacement=replacement):
                self.run_with(self.VALUES)
                path = self.home / ".pgpass"
                if replacement == "edit":
                    path.write_text("made-up-user-edit")
                else:
                    path.unlink()
                    if replacement == "same-content":
                        other = self.home / "replacement"
                        other.write_bytes(self.VALUES["pgpass"])
                        other.replace(path)
                    elif replacement == "symlink":
                        path.symlink_to("missing-user-target")
                    else:
                        path.mkdir()
                        (path / "user-file").write_text("keep")
                out = self.run_with({}, toml="")
                self.assertEqual(out.state, "ok")
                self.assertTrue(os.path.lexists(path))
                if path.is_dir():
                    (path / "user-file").unlink()
                    path.rmdir()
                else:
                    path.unlink()

    def test_matching_file_is_removed_regardless_of_parent_route(self):
        self.run_with(self.VALUES)
        parent = self.home / ".config/gh"
        moved = self.home / "user-gh"
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
        self.run_with({}, toml="")
        self.assertFalse((moved / "hosts.yml").exists())
        self.assertTrue(parent.is_symlink())

    def test_unchanged_symlinked_config_route_retires_actual_writes(self):
        config = self.home / "config-files"
        config.mkdir()
        (self.home / ".config").symlink_to(config, target_is_directory=True)
        self.run_with(self.VALUES)
        # Unrelated directory changes and an identical refresh do not forfeit
        # ownership of the files written through this pre-existing route.
        (config / "user-file").write_text("keep")
        self.run_with(self.VALUES)
        self.assertEqual(self.run_with({}, toml="").state, "ok")
        self.assertFalse((config / "claude-secrets/GH_TOKEN").exists())
        self.assertFalse((config / "gh/hosts.yml").exists())
        self.assertEqual((config / "user-file").read_text(), "keep")
        self.assertTrue((self.home / ".config").is_symlink())

    def test_manifestless_host_does_not_claim_an_unchanged_existing_file(self):
        path = self.home / ".pgpass"
        path.write_bytes(self.VALUES["pgpass"])
        path.chmod(0o600)
        self.run_with(self.VALUES)
        self.run_with({}, toml="")
        self.assertEqual(path.read_bytes(), self.VALUES["pgpass"])
        self.assertFalse((self.home / ".config/claude-secrets/GH_TOKEN").exists())

    def test_unchanged_user_replacement_is_not_reclaimed_by_refresh(self):
        self.run_with(self.VALUES)
        path = self.home / ".pgpass"
        other = self.home / "replacement"
        other.write_bytes(path.read_bytes())
        other.chmod(0o600)
        other.replace(path)
        self.run_with(self.VALUES)
        self.run_with({}, toml="")
        self.assertEqual(path.read_bytes(), self.VALUES["pgpass"])

    def test_failed_fetch_keeps_current_files_and_their_cleanup_ownership(self):
        self.run_with(self.VALUES)
        out = self.run_with({"gh-token": AccessError("HTTP 403")})
        self.assertEqual(out.state, "failed")
        self.assertTrue((self.home / ".pgpass").exists())
        self.run_with({}, toml="")
        self.assertFalse((self.home / ".pgpass").exists())
        self.assertFalse((self.home / ".config/claude-secrets/GH_TOKEN").exists())

    def test_partial_entry_write_is_tracked_even_when_its_second_target_fails(self):
        (self.home / "blocked").write_text("user-owned")
        toml = '[[secret]]\nname = "a"\nstore = "FIRST"\nfile = "~/blocked/second"\n'
        out = self.run_with({"a": b"made-up"}, toml=toml)
        self.assertEqual(out.state, "failed")
        self.assertTrue((self.home / ".config/claude-secrets/FIRST").exists())
        self.run_with({}, toml="")
        self.assertFalse((self.home / ".config/claude-secrets/FIRST").exists())
        self.assertEqual((self.home / "blocked").read_text(), "user-owned")

    def test_failed_cleanup_retries_without_forgetting_owned_file(self):
        self.run_with(self.VALUES)
        original = os.unlink

        def deny_pgpass(path, *args, **kwargs):
            if pathlib.Path(path).name == ".pgpass":
                raise PermissionError("cleanup denied")
            return original(path, *args, **kwargs)

        with mock.patch.object(os, "unlink", side_effect=deny_pgpass):
            out = self.run_with({}, toml="")
        self.assertEqual(out.state, "failed")
        self.assertTrue((self.home / ".pgpass").exists())
        self.assertEqual(self.run_with({}, toml="").state, "ok")
        self.assertFalse((self.home / ".pgpass").exists())

    def test_bookkeeping_survives_a_forking_as_user_callback(self):
        def as_user(fn):
            pid = os.fork()
            if pid == 0:
                try:
                    fn()
                except BaseException:
                    os._exit(1)
                os._exit(0)
            _, status = os.waitpid(pid, 0)
            if os.waitstatus_to_exitcode(status) != 0:
                raise RuntimeError("child failed")

        entries = secrets.parse('[[secret]]\nname = "a"\nstore = "KEY"\n')
        self.assertEqual(secrets.materialize(entries, lambda name: b"made-up", self.home, as_user=as_user).state, "ok")
        self.assertTrue((self.home / ".config/claude-secrets/KEY").exists())
        self.assertEqual(secrets.materialize([], lambda name: None, self.home, as_user=as_user).state, "ok")
        self.assertFalse((self.home / ".config/claude-secrets/KEY").exists())

    def test_missing_manifest_preserves_old_files_but_tracks_new_writes(self):
        self.run_with(self.VALUES)
        self.manifest.unlink()
        out = self.run_with({"a": b"made-up-new"}, toml='[[secret]]\nname = "a"\nfile = "~/new"\n')
        self.assertEqual(out.state, "ok")
        self.assertIn("manifest missing", out.detail)
        self.assertIn("no prior ownership", out.detail)
        self.assertTrue((self.home / ".pgpass").exists())
        self.assertEqual((self.home / "new").read_bytes(), b"made-up-new")
        self.run_with({}, toml="")
        self.assertFalse((self.home / "new").exists())
        self.assertTrue((self.home / ".pgpass").exists())

    def test_unreadable_manifest_does_not_authorize_cleanup_or_block_writes(self):
        self.run_with(self.VALUES)
        read_text = pathlib.Path.read_text

        def deny_manifest(path, *args, **kwargs):
            if path == self.manifest:
                raise PermissionError("made-up-sensitive-error")
            return read_text(path, *args, **kwargs)

        with mock.patch.object(pathlib.Path, "read_text", deny_manifest):
            out = self.run_with({"a": b"made-up-new"}, toml='[[secret]]\nname = "a"\nfile = "~/new"\n')
        self.assertEqual(out.state, "ok")
        self.assertIn("manifest unreadable", out.detail)
        self.assertIn("no prior ownership", out.detail)
        self.assertNotIn("made-up-sensitive-error", out.detail)
        self.assertTrue((self.home / ".pgpass").exists())
        self.assertEqual((self.home / "new").read_bytes(), b"made-up-new")
        self.run_with({}, toml="")
        self.assertFalse((self.home / "new").exists())
        self.assertTrue((self.home / ".pgpass").exists())

    def test_invalid_manifest_preserves_files_without_blocking_new_writes(self):
        self.run_with(self.VALUES)
        valid = json.loads(self.manifest.read_text())
        identity = next(iter(valid["files"].values()))
        cases = [b"not JSON", b"\xff", b"null", b"[]",
                 json.dumps(dict(valid, files={"../outside": identity})).encode(),
                 json.dumps(dict(valid, files={".pgpass": [1]})).encode()]
        for data in cases:
            with self.subTest(data=data):
                self.manifest.write_bytes(data)
                out = self.run_with({"a": b"made-up-new"}, toml='[[secret]]\nname = "a"\nfile = "~/new"\n')
                self.assertEqual(out.state, "ok")
                self.assertIn("manifest invalid", out.detail)
                self.assertIn("no prior ownership", out.detail)
                self.assertTrue((self.home / ".pgpass").exists())
                self.assertEqual((self.home / "new").read_bytes(), b"made-up-new")
                self.run_with({}, toml="")
                self.assertFalse((self.home / "new").exists())
                self.assertTrue((self.home / ".pgpass").exists())

    def test_unusable_manifest_path_does_not_stop_any_secret_target(self):
        # A directory cannot be read as JSON or replaced by a manifest file.
        self.manifest.mkdir(parents=True)
        out = self.run_with(dict(self.VALUES, later=b"made-up-later"))
        self.assertEqual(out.state, "ok")
        self.assertIn("manifest unreadable", out.detail)
        self.assertIn("manifest save failed", out.detail)
        self.assertIn("cleanup ownership", out.detail)
        self.assertEqual(out.env, {"EXAMPLE_API_KEY": "made-up-api-value"})
        self.assertEqual((self.home / ".config/claude-secrets/GH_TOKEN").read_bytes(), self.VALUES["gh-token"])
        self.assertTrue((self.home / ".config/gh/hosts.yml").exists())
        self.assertEqual((self.home / ".pgpass").read_bytes(), self.VALUES["pgpass"])
        self.assertEqual((self.home / ".config/claude-secrets/LATER").read_bytes(), b"made-up-later")

    def test_transient_manifest_save_failure_retains_partial_write_ownership(self):
        (self.home / "blocked").write_text("user-owned")
        write_file = secrets.write_file
        attempts = 0

        def deny_first_saves(path, *args, **kwargs):
            nonlocal attempts
            if path == self.manifest:
                attempts += 1
                if attempts <= 2:  # Initial save and the entry's first target.
                    raise PermissionError("made-up-sensitive-error")
            return write_file(path, *args, **kwargs)

        toml = '[[secret]]\nname = "a"\nstore = "FIRST"\nfile = "~/blocked/second"\n'
        with mock.patch.object(secrets, "write_file", side_effect=deny_first_saves):
            out = self.run_with({"a": b"made-up"}, toml=toml)
        self.assertEqual(out.state, "failed")  # The second target, not bookkeeping.
        self.assertIn("a (", out.detail)
        self.assertNotIn("made-up-sensitive-error", out.detail)
        self.assertTrue((self.home / ".config/claude-secrets/FIRST").exists())
        self.assertEqual(self.run_with({}, toml="").state, "ok")
        self.assertFalse((self.home / ".config/claude-secrets/FIRST").exists())
        self.assertEqual((self.home / "blocked").read_text(), "user-owned")

    def test_manifest_is_private_and_contains_no_payload(self):
        self.run_with(self.VALUES)
        self.assertEqual(stat.S_IMODE(self.manifest.stat().st_mode), 0o600)
        text = self.manifest.read_text()
        json.loads(text)
        for payload in self.VALUES.values():
            self.assertNotIn(payload.decode().strip(), text)

    def test_a_multi_line_value_cannot_be_an_env_target(self):
        out = self.run_with(dict(self.VALUES, **{"api-key": b"line one\nline two\n"}))
        self.assertEqual(out.state, "failed")
        self.assertIn("api-key (", out.detail)
        self.assertNotIn("line one", out.detail)

    def test_an_entry_outside_the_home_is_never_ledgered_nor_written(self):
        """An entry made without parse (a later caller) is held to the same
        boundary before the ledger hears of it."""
        listed = []
        outside = pathlib.Path(tempfile.mkdtemp()) / "outside"
        entry = secrets.Entry(name="pgpass", file="~/" + str(outside))
        out = secrets.materialize([entry], lambda name: b"made-up\n", self.home, before_write=listed.append)
        self.assertEqual(out.state, "failed")
        self.assertIn("inside the home", out.detail)
        self.assertEqual(listed, [])
        self.assertFalse(outside.exists())


if __name__ == "__main__":
    unittest.main()
