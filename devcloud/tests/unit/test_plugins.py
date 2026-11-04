"""A host's plugins seated as the Macs seat them (the driver's Design §10, the
parent's option E): a root-owned copy of the doperpowers marketplace kept at
its declared source's head, the managed settings naming it, the user's record
moved to it before any session — and, when any of that cannot be had, the
parent's user-tier layout, which keeps the guard active. Plus the driver keys
(§8.3) the home step writes. Real git for the copy; a stand-in `claude`."""

import contextlib
import json
import os
import pathlib
import pwd
import subprocess
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import plugins, proc, profile, steps
from devcloudlib.proc import StepError, User

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.com", GIT_CONFIG_GLOBAL="/dev/null")
KEY_A = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMadeUpKeyForTheMacBook macbook"
KEY_B = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMadeUpKeyForTheOtherMac mac-studio"


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True,
                          text=True).stdout.strip()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-plugins-"))
        self.claude = self.tmp / "home/.claude"
        self.claude.mkdir(parents=True)
        self.copy = self.tmp / "marketplaces/doperpowers"
        me = pwd.getpwuid(os.getuid())
        self.user = User(name=me.pw_name, uid=me.pw_uid, gid=me.pw_gid, home=self.tmp / "home")
        patch = mock.patch.object(proc, "LOG_DIR", self.tmp / "log")
        patch.start()
        self.addCleanup(patch.stop)

    def declare(self, source):
        (self.claude / "settings.json").write_text(json.dumps({"extraKnownMarketplaces": {"doperpowers": {
            "source": source}}}))

    def upstream(self):
        work = self.tmp / "upstream"
        work.mkdir()
        git("init", "-q", "-b", "main", cwd=work)
        (work / ".claude-plugin").mkdir()
        (work / ".claude-plugin/marketplace.json").write_text('{"name": "doperpowers"}\n')
        git("add", "-A", cwd=work)
        git("commit", "-qm", "one", cwd=work)
        return work


class DeclaredSourceTest(Base):
    def test_github_and_git_sources(self):
        self.declare({"source": "github", "repo": "example/doperpowers"})
        self.assertEqual(plugins.declared_source(self.claude), ("https://github.com/example/doperpowers.git", None))
        self.declare({"source": "git", "url": "https://git.example.com/doperpowers.git", "ref": "stable"})
        self.assertEqual(plugins.declared_source(self.claude), ("https://git.example.com/doperpowers.git", "stable"))

    def test_none_without_a_declaration_or_for_a_directory(self):
        self.assertIsNone(plugins.declared_source(self.claude))
        self.declare({"source": "directory", "path": "/Users/dev/src/doperpowers"})
        self.assertIsNone(plugins.declared_source(self.claude))

    def test_a_url_carrying_a_credential_is_refused(self):
        self.declare({"source": "git", "url": "https://user:made-up-pass@git.example.com/d.git"})
        with self.assertRaises(plugins.Unavailable):
            plugins.declared_source(self.claude)


class RefreshTest(Base):
    def test_clones_then_follows_the_sources_head(self):
        work = self.upstream()
        self.declare({"source": "git", "url": f"file://{work}"})
        commit, note = plugins.refresh(self.claude, copy=self.copy)
        self.assertEqual((commit, note), (git("rev-parse", "HEAD", cwd=work), ""))
        (work / "new").write_text("x")
        git("add", "new", cwd=work)
        git("commit", "-qm", "two", cwd=work)
        (self.copy / "stray").write_text("left by nobody")
        commit, _ = plugins.refresh(self.claude, copy=self.copy)
        self.assertEqual(commit, git("rev-parse", "HEAD", cwd=work))
        self.assertTrue((self.copy / "new").exists())
        self.assertFalse((self.copy / "stray").exists(), "the copy is not the source's tree")

    def test_a_failed_fetch_keeps_the_copy_and_says_so(self):
        work = self.upstream()
        self.declare({"source": "git", "url": f"file://{work}"})
        first, _ = plugins.refresh(self.claude, copy=self.copy)
        self.declare({"source": "git", "url": f"file://{self.tmp}/gone"})
        commit, note = plugins.refresh(self.claude, copy=self.copy)
        self.assertEqual(commit, first)
        self.assertIn("the fetch failed", note)

    def test_no_copy_to_seat_from(self):
        with self.assertRaises(plugins.NotDeclared):
            plugins.refresh(self.claude, copy=self.copy)
        self.declare({"source": "git", "url": f"file://{self.tmp}/gone"})
        with self.assertRaises(plugins.Unavailable) as caught:
            plugins.refresh(self.claude, copy=self.copy)
        self.assertNotIsInstance(caught.exception, plugins.NotDeclared)


class RecordTest(Base):
    def known(self, entry):
        path = self.claude / "plugins/known_marketplaces.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"doperpowers": entry}))

    def test_moves_the_record_to_the_copy_once(self):
        self.known({"source": {"source": "github", "repo": "example/doperpowers"},
                    "installLocation": str(self.claude / "plugins/marketplaces/doperpowers")})
        calls = []

        def claude(argv, **kwargs):
            calls.append((argv, kwargs["user"]))
            self.known({"source": {"source": "directory", "path": argv[-1]}, "installLocation": argv[-1]})
        self.assertEqual(plugins.record(self.user, {}, copy=self.copy, run=claude), "recorded")
        self.assertEqual(calls, [(["claude", "plugin", "marketplace", "add", str(self.copy)], self.user)])
        self.assertEqual(plugins.record(self.user, {}, copy=self.copy, run=claude), "recorded already")
        self.assertEqual(len(calls), 1)

    def test_a_record_left_elsewhere_fails(self):
        with self.assertRaises(StepError):
            plugins.record(self.user, {}, copy=self.copy, run=lambda argv, **kw: None)


class UpdateTest(Base):
    """Installs follow the copy: an installed version the copy no longer
    carries is updated as the user, at the record's scope, dependencies
    first; a plugin from another source and a project's record are left."""

    def setUp(self):
        super().setUp()
        self.carry({"doperpowers": ("./", "7.2.0", None), "to-human": ("./to-human", "0.8.0", ["sminos"]),
                    "sminos": ("./sminos", "1.3.0", None)},
                   extra=[{"name": "ci-kit", "source": {"source": "url", "url": "https://example.com/ci-kit.git"}},
                          {"name": "escape", "source": "./../outside"}])

    def carry(self, plugins_, extra=()):
        entries = list(extra)
        for name, (source, version, deps) in plugins_.items():
            tree = self.copy / source
            (tree / ".claude-plugin").mkdir(parents=True, exist_ok=True)
            manifest = {"name": name, "version": version, **({"dependencies": deps} if deps else {})}
            (tree / ".claude-plugin/plugin.json").write_text(json.dumps(manifest))
            entries.append({"name": name, "source": source})
        (self.copy / ".claude-plugin/marketplace.json").write_text(json.dumps({"name": "doperpowers",
                                                                              "plugins": entries}))
        outside = self.tmp / "marketplaces/outside/.claude-plugin"
        outside.mkdir(parents=True, exist_ok=True)
        (outside / "plugin.json").write_text('{"name": "escape", "version": "9"}')

    def installed(self, records):
        path = self.claude / "plugins/installed_plugins.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"version": 2, "plugins": {
            key: [{"scope": scope, "version": version, **({"projectPath": "/work"} if scope == "project" else {})}]
            for key, (scope, version) in records.items()}}))

    def test_versions_are_the_copys_own_plugins_only(self):
        self.assertEqual(plugins.versions(self.copy), {"doperpowers": ("7.2.0", []),
                                                       "to-human": ("0.8.0", ["sminos"]),
                                                       "sminos": ("1.3.0", [])})

    def test_updates_what_the_copy_moved_past_dependencies_first(self):
        self.installed({"to-human@doperpowers": ("managed", "0.7.0"), "sminos@doperpowers": ("managed", "1.2.0"),
                        "doperpowers@doperpowers": ("user", "7.2.0"), "ci-kit@doperpowers": ("user", "abc123"),
                        "web@doperpowers": ("user", "0.1.0"), "sminos@other": ("user", "0.0.1")})
        calls = []
        note = plugins.update(self.user, {"HOME": "h"}, copy=self.copy,
                              run=lambda argv, **kw: calls.append((argv, kw["user"], kw["env"])))
        self.assertEqual([c[0] for c in calls], [
            ["claude", "plugin", "update", "sminos@doperpowers", "--scope", "managed"],
            ["claude", "plugin", "update", "to-human@doperpowers", "--scope", "managed"]])
        self.assertEqual({(c[1], c[2]["HOME"]) for c in calls}, {(self.user, "h")})
        self.assertEqual(note, "updated sminos@doperpowers 1.2.0 to 1.3.0, to-human@doperpowers 0.7.0 to 0.8.0")

    def test_a_projects_record_is_left_and_current_installs_need_nothing(self):
        self.installed({"sminos@doperpowers": ("project", "1.0.0"), "doperpowers@doperpowers": ("user", "7.2.0")})
        note = plugins.update(self.user, {}, copy=self.copy, run=mock.Mock(side_effect=AssertionError("ran")))
        self.assertEqual(note, "plugins current")

    def test_a_failed_update_is_named_and_the_rest_still_run(self):
        self.installed({"sminos@doperpowers": ("user", "1.2.0"), "doperpowers@doperpowers": ("user", "7.1.0")})

        def claude(argv, **kw):
            if argv[3] == "doperpowers@doperpowers":
                raise StepError("claude plugin exited 1")
        note = plugins.update(self.user, {}, copy=self.copy, run=claude)
        self.assertEqual(note, "updated sminos@doperpowers 1.2.0 to 1.3.0; "
                               "update failed: doperpowers@doperpowers (claude plugin exited 1)")

    def test_no_registry_or_no_catalog_is_nothing_to_do(self):
        run = mock.Mock(side_effect=AssertionError("ran"))
        self.assertEqual(plugins.update(self.user, {}, copy=self.copy, run=run), "plugins current")
        self.installed({"sminos@doperpowers": ("user", "1.2.0")})
        self.assertEqual(plugins.update(self.user, {}, copy=self.tmp / "nowhere", run=run), "plugins current")


class ManagedTest(unittest.TestCase):
    COPY = pathlib.Path("/var/lib/devcloud/marketplaces/doperpowers")
    DIRECTORY = {"source": {"source": "directory", "path": str(COPY)}}

    def test_seats_the_three_outer_plugins_from_the_copy(self):
        out = plugins.managed({"env": {"A": "1"}}, self.COPY)
        self.assertEqual(out, {"env": {"A": "1"},
                               "prependPlugins": ["to-human@doperpowers", "sminos@doperpowers",
                                                  "doperpowers@doperpowers"],
                               "enabledPlugins": {p: True for p in plugins.OUTER},
                               "extraKnownMarketplaces": {"doperpowers": self.DIRECTORY}})
        self.assertNotIn("cc-plugin-sec-default@builtin", out["prependPlugins"])

    def test_a_profiles_own_order_stands_and_the_marketplace_is_always_the_copy(self):
        settings = {"prependPlugins": ["sminos@doperpowers", "other@elsewhere"],
                    "enabledPlugins": {"sminos@doperpowers": False},
                    "extraKnownMarketplaces": {"doperpowers": {"source": {"source": "github", "repo": "x/y"}},
                                               "elsewhere": {"source": {"source": "github", "repo": "e/e"}}}}
        out = plugins.managed(settings, self.COPY)
        self.assertEqual(out["prependPlugins"], ["sminos@doperpowers", "other@elsewhere"])
        self.assertEqual(out["enabledPlugins"], {"sminos@doperpowers": False})
        self.assertEqual(out["extraKnownMarketplaces"]["doperpowers"], self.DIRECTORY)
        self.assertEqual(out["extraKnownMarketplaces"]["elsewhere"], settings["extraKnownMarketplaces"]["elsewhere"])

    def test_host_settings_seats_with_a_copy_and_keeps_the_parents_layout_without(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "devcloud").mkdir()
        (tmp / "devcloud/managed-settings.json").write_text("{}\n")
        p = profile.read(tmp, {})
        self.assertEqual(p.host_settings(), b"{}\n")
        self.assertEqual(json.loads(p.host_settings(self.COPY))["prependPlugins"], list(plugins.OUTER))


class SettingsStepTest(Base):
    """Step 10: the managed settings name the copy before the record moves;
    a record that fails puts the user tier back."""

    def setUp(self):
        super().setUp()
        (self.claude / "devcloud").mkdir()
        (self.claude / "devcloud/managed-settings.json").write_text('{"env": {"A": "1"}}\n')
        self.managed = self.tmp / "managed-settings.json"
        self.seen_at_record = None
        for patch in (mock.patch.object(steps, "MANAGED_SETTINGS", self.managed),
                      mock.patch.object(steps, "ENV_PATH", self.tmp / "env"),
                      mock.patch.object(steps, "IDENTITY_ENV", self.tmp / "identity.env"),
                      mock.patch.object(steps.ledger, "add", lambda path: None),
                      mock.patch.object(steps.os, "chown", lambda *a: None),
                      mock.patch.object(plugins, "COPY", self.copy)):
            patch.start()
            self.addCleanup(patch.stop)

    def step(self, record):
        r = steps.Run("boot")
        r.user = self.user
        r.desc = mock.Mock(role="persistent")
        r.profile = profile.read(self.claude, {})
        with mock.patch.object(plugins, "record", record):
            return steps.settings_and_env(r)

    def test_seats_from_the_copy_when_the_marketplace_is_declared(self):
        work = self.upstream()
        self.declare({"source": "git", "url": f"file://{work}"})

        def record(user, env):
            self.seen_at_record = json.loads(self.managed.read_text())
            return "recorded"
        state, detail = self.step(record)
        self.assertEqual(state, "ok")
        self.assertIn(f"plugins seated from {self.copy}", detail)
        self.assertEqual(self.seen_at_record["extraKnownMarketplaces"]["doperpowers"]["source"]["path"],
                         str(self.copy), "the record moved before the managed settings named the copy")
        self.assertEqual(json.loads(self.managed.read_text())["prependPlugins"], list(plugins.OUTER))
        self.assertTrue(detail.endswith("; recorded; plugins current"), detail)

    def test_a_failed_record_puts_the_user_tier_back(self):
        work = self.upstream()
        self.declare({"source": "git", "url": f"file://{work}"})
        state, detail = self.step(mock.Mock(side_effect=StepError("claude plugin exited 1")))
        self.assertEqual(state, "missing")
        self.assertEqual(json.loads(self.managed.read_text()), {"env": {"A": "1"}, "prependPlugins": []})
        self.assertIn("record failed", detail)

    def test_an_undeclared_marketplace_keeps_the_user_tier_quietly(self):
        state, detail = self.step(mock.Mock(side_effect=AssertionError("recorded")))
        self.assertEqual(state, "ok")
        self.assertEqual(json.loads(self.managed.read_text())["prependPlugins"], [])
        self.assertIn("declare no doperpowers marketplace", detail)

    def test_a_declared_marketplace_that_cannot_be_had_is_missing(self):
        self.declare({"source": "git", "url": f"file://{self.tmp}/gone"})
        state, _ = self.step(mock.Mock(side_effect=AssertionError("recorded")))
        self.assertEqual(state, "missing")
        self.assertEqual(json.loads(self.managed.read_text())["prependPlugins"], [])


class PullRefreshTest(Base):
    """A pull with no new configuration commit refreshes the copy and moves
    the installs to it; a copy that cannot be had updates nothing."""

    def run_refresh(self, refresh):
        r = steps.Run("pull-config")
        r.user = self.user
        said = []
        with mock.patch.object(plugins, "recorded", lambda user: True), \
                mock.patch.object(plugins, "refresh", refresh), \
                mock.patch.object(plugins, "update", lambda user, env: f"updated for {env['HOME']}"), \
                mock.patch.object(steps, "ENV_PATH", self.tmp / "env"), \
                mock.patch.object(steps, "_say", said.append):
            steps._refresh_marketplace(r)
        return said

    def test_the_update_follows_the_refresh(self):
        self.assertEqual(self.run_refresh(lambda claude_dir: ("abc", "")), [f"marketplace: updated for {self.user.home}"])

    def test_no_copy_no_update(self):
        said = self.run_refresh(mock.Mock(side_effect=plugins.Unavailable("the marketplace could not be cloned")))
        self.assertEqual(said, ["marketplace: the marketplace could not be cloned"])


class DriverKeysTest(Base):
    def setUp(self):
        super().setUp()
        (self.claude / "devcloud").mkdir()
        (self.claude / "devcloud/managed-settings.json").write_text("{}\n")

    def keys(self, files):
        directory = self.claude / "devcloud/driver-keys"
        directory.mkdir(exist_ok=True)
        for name, text in files.items():
            (directory / name).write_text(text)

    def run_(self):
        r = steps.Run("boot")
        r.user = self.user
        r.profile = profile.read(self.claude, {})
        return r

    def test_root_and_the_user_get_every_drivers_key(self):
        self.keys({"mac-studio.pub": KEY_B + "\n", "macbook.pub": f"# the MacBook\n{KEY_A}\nnot a key\n",
                   "notes.txt": KEY_A + "x\n"})
        root = self.tmp / "root"
        detail = steps.authorized_keys(self.run_(), root_home=root)
        want = steps.AUTHORIZED_KEYS_HEADER + f"{KEY_B}\n{KEY_A}\n"
        for path in (root / ".ssh/authorized_keys", self.user.home / ".ssh/authorized_keys"):
            self.assertEqual(path.read_text(), want)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertIn("2 driver keys", detail)
        self.assertIn("1 lines that are not keys skipped", detail)

    def test_without_driver_keys_both_are_left_as_they_are(self):
        root = self.tmp / "root"
        (root / ".ssh").mkdir(parents=True)
        (root / ".ssh/authorized_keys").write_text("the provider's key\n")
        self.assertIn("left as they are", steps.authorized_keys(self.run_(), root_home=root))
        self.keys({})
        self.assertIn("left as they are", steps.authorized_keys(self.run_(), root_home=root))
        self.assertEqual((root / ".ssh/authorized_keys").read_text(), "the provider's key\n")


if __name__ == "__main__":
    unittest.main()
