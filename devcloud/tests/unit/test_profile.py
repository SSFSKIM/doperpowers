import json
import pathlib
import tempfile
import unittest

import _path  # noqa: F401
from devcloudlib import profile
from devcloudlib.secrets import ProfileError

BASE = {"HOME": "/Users/dev", "PATH": "/usr/bin"}


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.claude = pathlib.Path(tempfile.mkdtemp())
        self.root = self.claude / "devcloud"
        self.root.mkdir()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_reads_every_part(self):
        self.write("managed-settings.json", json.dumps({"env": {"ANTHROPIC_BASE_URL": "http://gateway.example:8080"}}))
        self.write("profile.env", 'TZ=Europe/Berlin\nPATH="$HOME/.local/bin:$PATH"\n')
        self.write("secrets.toml", '[[secret]]\nname = "a"\nenv = "A"\n')
        self.write("home/.gitconfig", "[user]\n\tname = Example\n")
        p = profile.read(self.claude, BASE)
        self.assertEqual(p.gateway, "http://gateway.example:8080")
        self.assertEqual(p.env, {"TZ": "Europe/Berlin", "PATH": "/Users/dev/.local/bin:/usr/bin"})
        self.assertEqual([e.name for e in p.secrets], ["a"])
        self.assertEqual(p.home, self.root / "home")

    def test_only_managed_settings_is_required(self):
        self.write("managed-settings.json", "{}")
        p = profile.read(self.claude, BASE)
        self.assertEqual((p.env, p.secrets, p.home, p.gateway), ({}, [], None, None))

    def test_a_host_seats_no_security_default(self):
        # Any managed settings seat cc-plugin-sec-default@builtin outermost unless managed
        # prependPlugins is set, and the seated default passes installed plugins over.
        settings = {"env": {"ANTHROPIC_BASE_URL": "http://gateway.example:8080", "EMPTY": ""}}
        self.write("managed-settings.json", json.dumps(settings))
        host = json.loads(profile.read(self.claude, BASE).host_settings())
        self.assertEqual(host, {**settings, "prependPlugins": []})

    def test_an_empty_managed_file_stays_empty(self):
        # The engine counts managed settings only when they hold a key: an empty file seats
        # nothing and leaves the synced prependPlugins in force, which a key here would override.
        self.write("managed-settings.json", "{}\n")
        self.assertEqual(profile.read(self.claude, BASE).host_settings(), b"{}\n")

    def test_a_profile_that_sets_prepend_plugins_keeps_its_own(self):
        text = '{"env": {}, "prependPlugins": ["cc-plugin-sec-default@builtin"]}\n'
        self.write("managed-settings.json", text)
        self.assertEqual(profile.read(self.claude, BASE).host_settings(), text.encode())

    def test_refuses_a_broken_profile(self):
        cases = {
            "no devcloud/ profile": None,
            "managed-settings.json is absent": {},
            "not a JSON object": {"managed-settings.json": "[1]"},
            "profile.env: line 1": {"managed-settings.json": "{}", "profile.env": "A=b c\n"},
            "set by both": {"managed-settings.json": "{}", "profile.env": "A=1\n",
                            "secrets.toml": '[[secret]]\nname = "a"\nenv = "A"\n'},
        }
        for message, files in cases.items():
            with self.subTest(message=message):
                claude = pathlib.Path(tempfile.mkdtemp())
                if files is not None:
                    (claude / "devcloud").mkdir()
                    for name, text in files.items():
                        (claude / "devcloud" / name).write_text(text)
                with self.assertRaisesRegex(ProfileError, message):
                    profile.read(claude, BASE)


if __name__ == "__main__":
    unittest.main()
