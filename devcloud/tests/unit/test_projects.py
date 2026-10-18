"""Boot step 12 (Design §7): descriptor entries bridged to `devenv up`, run as
the user with the host's environment, and the mirror cache a persistent host
keeps. A fake `devenv` records its calls; git runs for real against local
repositories that stand in for GitHub (an insteadOf rule)."""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import descriptor, proc, projects
from devcloudlib.proc import User

FAKE_DEVENV = """#!/bin/sh
# records each call; `up` fails for a project named broken; `show` answers from
# $FAKE_SHOW/<name>.json
echo "$* | mirror=${DEVENV_MIRROR_DIR-unset} probe=${PROBE-unset}" >> "$FAKE_CALLS"
case "$1" in
  up) [ "$2" = broken ] && { echo "setup failed for broken"; exit 2; }; exit 0 ;;
  show) cat "$FAKE_SHOW/$2.json" ;;
esac
"""


class BridgeTest(unittest.TestCase):
    def test_entries_become_devenv_up_arguments(self):
        cases = {
            "doperpowers": ("doperpowers", ["doperpowers"]),
            "doperpowers@devcloud": ("doperpowers", ["doperpowers", "--ref", "devcloud"]),
            "example/app": ("app", ["app", "--url", "https://github.com/example/app.git"]),
            "example/app@v2": ("app", ["app", "--url", "https://github.com/example/app.git", "--ref", "v2"]),
        }
        for entry, want in cases.items():
            with self.subTest(entry=entry):
                self.assertEqual(projects.devenv_args(entry), want)

    def test_a_mirror_is_kept_only_for_a_github_repository(self):
        base = pathlib.Path("/m")
        self.assertEqual(projects.mirror_of("https://github.com/example/app.git", base),
                         base / "example" / "app.git")
        self.assertEqual(projects.mirror_of("https://github.com/example/app", base), base / "example" / "app.git")
        for url in ("https://gitlab.com/example/app.git", "https://github.com/../app.git",
                    "https://github.com/example/.git", "/local/path"):
            with self.subTest(url=url):
                self.assertIsNone(projects.mirror_of(url, base))


class SetUpTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name).resolve()
        self.home = self.root / "home"
        (self.home / ".local/bin").mkdir(parents=True)
        self.devenv = self.home / ".local/bin/devenv"
        self.devenv.write_text(FAKE_DEVENV)
        self.devenv.chmod(0o755)
        self.calls = self.root / "calls"
        self.show = self.root / "show"
        self.show.mkdir()
        self.mirrors = self.root / "mirrors"
        self.user = User(name="dev", uid=os.getuid(), gid=os.getgid(), home=self.home)
        patcher = mock.patch.object(proc, "LOG_DIR", self.root / "logs")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.git_env = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(self.root / "gitconfig"),
                        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        # "GitHub" is a directory of local repositories here.
        (self.root / "gitconfig").write_text(f'[url "{self.root}/github/"]\n\tinsteadOf = https://github.com/\n')

    def env(self, **extra):
        return dict(os.environ, **self.git_env, FAKE_CALLS=str(self.calls), FAKE_SHOW=str(self.show),
                    PROBE="from-the-host-env", **extra)

    def desc(self, projects_="", role="sandbox", mirror=None):
        text = ("DEVCLOUD_NAME=sbx-a\nDEVCLOUD_KIND=container\nDEVCLOUD_TAILSCALE=host\n"
                "DEVCLOUD_SEED=gce-metadata\nDEVCLOUD_SM_PROJECT=p\nDEVCLOUD_CONFIG_REPO=https://example.invalid/c.git\n"
                f"DEVCLOUD_CONFIG_TOKEN_SECRET=t\nDEVCLOUD_ROLE={role}\nDEVCLOUD_PROJECTS=\"{projects_}\"\n")
        if mirror:
            text += f"DEVCLOUD_MIRROR_DIR={mirror}\n"
        if role == "persistent":
            text = text.replace("KIND=container", "KIND=vm")
        return descriptor.parse(text)

    def set_up(self, desc):
        return projects.set_up(self.user, desc, self.env(), mirrors=self.mirrors)

    def recorded(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def github_repo(self, owner, name):
        repo = self.root / "github" / owner / f"{name}.git"
        work = self.root / "work" / name
        work.mkdir(parents=True)
        for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "one"]):
            subprocess.run(["git", *args], cwd=work, env=self.env(), check=True)
        subprocess.run(["git", "clone", "-q", "--bare", str(work), str(repo)], env=self.env(), check=True)
        return work, repo

    def test_no_projects_is_skipped(self):
        self.assertEqual(self.set_up(self.desc()), ("skipped", "no projects named"))

    def test_each_entry_runs_devenv_up_with_the_host_environment(self):
        state, detail = self.set_up(self.desc("doperpowers@devcloud example/app", mirror="/srv/host-mirrors"))
        self.assertEqual(state, "ok", detail)
        self.assertEqual(self.recorded(), [
            "up doperpowers --ref devcloud | mirror=/srv/host-mirrors probe=from-the-host-env",
            "up app --url https://github.com/example/app.git | mirror=/srv/host-mirrors probe=from-the-host-env"])
        self.assertEqual(detail, "doperpowers@devcloud ok; example/app ok")

    def test_one_failing_project_fails_the_step_after_every_project_ran(self):
        state, detail = self.set_up(self.desc("broken other"))
        self.assertEqual(state, "failed")
        self.assertEqual([c.split(" |")[0] for c in self.recorded()], ["up broken", "up other"])
        self.assertIn("broken failed (devenv up exited 2", detail)
        self.assertIn("other ok", detail)
        self.assertIn("setup failed for broken", (self.root / "logs/projects.log").read_text())

    def test_no_devenv_runner_fails_the_step_naming_it(self):
        self.devenv.unlink()
        with self.assertRaises(proc.StepError) as cm:  # the step records it as failed
            self.set_up(self.desc("doperpowers"))
        self.assertIn("sync/apply.py", str(cm.exception))

    def test_a_persistent_host_mirrors_its_projects_github_repositories_and_refreshes_them(self):
        work, _ = self.github_repo("example", "app")
        checkout = self.root / "checkouts" / "app"
        subprocess.run(["git", "clone", "-q", "https://github.com/example/app.git", str(checkout)],
                       env=self.env(), check=True)
        (self.show / "app.json").write_text(json.dumps({"repos": [
            {"name": "app", "url": "https://github.com/example/app.git", "path": str(checkout)},
            {"name": "local", "path": str(self.root / "elsewhere")}]}))
        state, detail = self.set_up(self.desc("example/app", role="persistent"))
        self.assertEqual(state, "ok", detail)
        self.assertEqual(detail, "example/app ok; mirrors: example/app")
        mirror = self.mirrors / "example" / "app.git"
        self.assertEqual(subprocess.run(["git", "-C", str(mirror), "rev-parse", "--is-bare-repository"],
                                        capture_output=True, text=True).stdout.strip(), "true")
        self.assertFalse((mirror / "objects/info/alternates").exists(), "the mirror depends on the checkout")
        self.assertIn("mirror=unset", self.recorded()[0], "a persistent host's own clones do not borrow")
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "two"], cwd=work, env=self.env(), check=True)
        subprocess.run(["git", "push", "-q", str(self.root / "github/example/app.git"), "main"], cwd=work,
                       env=self.env(), check=True)
        self.assertEqual(projects.refresh(self.user, self.env(), mirrors=self.mirrors), (["example/app"], []))
        head = subprocess.run(["git", "-C", str(mirror), "log", "-1", "--format=%s", "main"],
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(head, "two")

    def test_a_sandbox_keeps_no_mirror(self):
        (self.show / "app.json").write_text(json.dumps({"repos": [
            {"name": "app", "url": "https://github.com/example/app.git"}]}))
        self.set_up(self.desc("example/app"))
        self.assertFalse(self.mirrors.exists())
        self.assertEqual([c.split(" |")[0] for c in self.recorded()],
                         ["up app --url https://github.com/example/app.git"])

    def test_a_mirror_that_cannot_be_made_fails_the_step(self):
        (self.show / "app.json").write_text(json.dumps({"repos": [
            {"name": "app", "url": "https://github.com/example/absent.git", "path": "/nowhere"}]}))
        state, detail = self.set_up(self.desc("example/app", role="persistent"))
        self.assertEqual(state, "failed")
        self.assertIn("mirror of example/absent failed", detail)


if __name__ == "__main__":
    unittest.main()
