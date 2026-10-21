import pathlib
import stat
import tempfile
import unittest

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
        self.home = pathlib.Path(tempfile.mkdtemp())

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
        self.assertEqual((out.state, out.detail), ("missing", "3 written; missing: later"))

    def test_all_present_is_ok(self):
        out = self.run_with(dict(self.VALUES, later=b"x"))
        self.assertEqual((out.state, out.detail), ("ok", "4 written"))

    def test_a_required_absence_or_error_fails_after_trying_the_rest(self):
        values = dict(self.VALUES, later=b"x")
        del values["api-key"]
        values["pgpass"] = AccessError("HTTP 403")
        out = self.run_with(values)
        self.assertEqual(out.state, "failed")
        self.assertEqual(out.detail, "2 written; failed: api-key (absent from Secret Manager), pgpass (HTTP 403)")
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
