#!/usr/bin/env python3
"""sminos's question to devcloud for `channel show` (EN.G2's M2:
docs/doperpowers/plans/2026-11-23-sminos-environments-en-g2.md, Interfaces
§2 and §3): `sminos_threads.vm_info`.

- Asked: `devcloud vm info --within <the cutoff less the margin, at least 1>
  -- <names>`, the cutoff the smaller of 20 seconds and devcloud_timeout();
  the replies its stand-in plays are built by devcloud's own `info` module
  from this tree (driver/info.py), so a change of the reply on either side
  fails here; a whole reply is read as asked, with what it holds, a
  creator that is a label word and no short id among it.
- Unavailable, devcloud not run: no CLI, a copy older than 0.19.0 or of no
  readable version; and exit 6.
- Failed: a copy that cannot be run, no answer within the bound (stopped),
  another exit, and each reply that is not whole (Interfaces §3): NaN or an
  infinity, a boolean or a string where a number goes, a provider's host
  with `created` null, an adopted host with a number there, a negative
  number, an integer past a float's range, a host without `creator` or
  `provider`, an entry of `unknown` that is no object or lacks `account`,
  a host whose name was not asked, output that is not JSON; nothing of
  such a reply is said back.

Hermetic: test_threads.Machine's temporary HOME and SMINOS_HOME, and the
suite's stand-in for devcloud (devcloud_standin.py); the driver's module
is imported, never run, under a Python devcloud accepts (test_on's
devcloud_python), and skipped where there is none.
Run: python3 -B sminos/tests/test_vm_info.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_on import DEVCLOUD, devcloud_python  # noqa: E402
from test_threads import Machine, sminos, threads  # noqa: E402
from test_threads_owner import launcher  # noqa: E402

# What the replies are built from: devcloud's own builders, imported from this tree and printed as it prints them.
BUILD = """import json, sys
sys.path[:0] = sys.argv[1:3]
from driver import info
vm = info.provider_host("dc-x-0001", "main", "hetzner", "1a2b3c4d", 1763850000, 0.47, "EUR")
box = info.adopted_host("Box-1", "5e6f7a8b")
nobody = info.adopted_host("box-2", None)
time_ = info.missing("spare", "gce", "time", "provider gce/spare: list timed out after 3 s")
unused = info.reply([], [], ["main"], ["far"])
def bad(**over):
    return info.reply([dict(vm, **over)], [], ["main"], [])
print(json.dumps({
    "whole": info.reply([vm, box, nobody], [time_], ["main"], ["far"]),
    "a label": info.reply([info.provider_host("dc-x-0001", "main", "hetzner", "retired-worker", 1763850000, 0.47,
                                              "EUR"), box], [], ["main"], []),
    "empty": info.reply([], [], ["main"], []),
    "unused": unused,
    "nan": info.reply([info.provider_host("dc-x-0001", "main", "hetzner", None, 1763850000, float("nan"), "EUR")],
                      [], ["main"], []),
    "infinity": bad(created=float("inf")),
    "minus infinity": bad(spent=float("-inf")),
    "a boolean": bad(spent=True),
    "a string": bad(created="1763850000"),
    "a provider's host with created null": bad(created=None),
    "an adopted host with a number": info.reply([dict(box, created=1763850000)], [], [], []),
    "a negative number": bad(spent=-0.5),
    "an unknown that is no object": info.reply([], ["spare"], ["main"], []),
    "an unknown with no account": info.reply([], [{k: v for k, v in time_.items() if k != "account"}], [], []),
    "a host not asked": info.reply([dict(vm, name="dc-x-0002")], [], ["main"], []),
}))"""


def built():
    """The replies above as devcloud's module builds and prints them (json.dumps, NaN as NaN)."""
    py = devcloud_python()
    if py is None:
        raise unittest.SkipTest("devcloud's info module needs Python 3.11 or later, and none is on PATH")
    done = subprocess.run([py, "-B", "-I", "-c", BUILD, DEVCLOUD, os.path.join(DEVCLOUD, "boot")],
                          capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise AssertionError("devcloud's info module did not build the replies: %s" % done.stderr)
    return {k: json.dumps(v) for k, v in json.loads(done.stdout).items()}


NAMES = ["dc-x-0001", "box-1", "box-2"]


class VmInfo(Machine):
    @classmethod
    def setUpClass(cls):
        cls.replies = None

    def setUp(self):
        super().setUp()
        os.environ.pop("SMINOS_DEVCLOUD_TIMEOUT", None)
        self.addCleanup(os.environ.pop, "SMINOS_DEVCLOUD_TIMEOUT", None)

    def reply(self, name):
        if VmInfo.replies is None:
            VmInfo.replies = built()
        return VmInfo.replies[name]

    def standin(self, **info):
        with open(os.path.join(os.environ["HOME"], "devcloud-standin.json"), "w") as f:
            json.dump({"info": info}, f)

    def calls(self):
        try:
            with open(os.path.join(os.environ["HOME"], "devcloud-standin.calls")) as f:
                return [json.loads(line) for line in f if line.strip()]
        except OSError:
            return []

    def ask(self, names=NAMES):
        return threads.vm_info(names)

    # --- asked

    def test_the_question_and_its_bound(self):
        self.standin(stdout=self.reply("empty"))
        for timeout, within in ((None, "15"), ("60", "15"), ("8", "3"), ("3", "1"), ("0.5", "1")):
            with self.subTest(timeout=timeout):
                env = {"SMINOS_DEVCLOUD_TIMEOUT": timeout} if timeout else {}
                with mock.patch.dict(os.environ, env):
                    self.assertEqual(self.ask().state, "asked")
                self.assertEqual(self.calls()[-1]["argv"], ["vm", "info", "--within", within, "--"] + NAMES)

    def test_a_whole_reply_built_by_devcloud_is_read_as_asked_with_what_it_holds(self):
        self.standin(stdout=self.reply("whole"))
        got = self.ask()
        self.assertEqual((got.state, got.why), ("asked", ""))
        self.assertEqual(got.reply, json.loads(self.reply("whole")))
        self.assertEqual([h["name"] for h in got.reply["hosts"]], ["dc-x-0001", "Box-1", "box-2"],
                         "a name of another case is a name asked")

    def test_a_creator_label_that_is_no_short_id_is_whole(self):
        # The driver takes any label word for `devcloud-creator`, and says it as `@<label>`: the reply stays whole,
        # and the host keeps its age and cost (channel show names no thread for it).
        self.standin(stdout=self.reply("a label"))
        got = self.ask()
        self.assertEqual(got.state, "asked")
        self.assertEqual([h["creator"] for h in got.reply["hosts"]], ["@retired-worker", "@5e6f7a8b"])
        for creator in ("@", "@two words", "@line\nbreak", "@\x1b[2J", "retired-worker", 7):
            with self.subTest(creator=creator):
                d = json.loads(self.reply("a label"))
                d["hosts"][0]["creator"] = creator
                self.assertFalse(threads.info_reply(d, NAMES), "no word a line can print")

    def test_the_copy_sminos_devcloud_names_is_taken_at_its_word(self):
        cli = os.path.join(self.home, "bare", "devcloud")
        launcher(cli, "printf '%s\\n' '" + self.reply("unused") + "'")
        with mock.patch.dict(os.environ, {"SMINOS_DEVCLOUD": cli}):
            got = self.ask()
        self.assertEqual((got.state, got.reply["unused"]), ("asked", ["far"]))

    # --- unavailable: devcloud not run, or its word that its driver does not run here

    def test_no_cli(self):
        with mock.patch.object(threads, "find_devcloud", return_value=(None, "PATH (none)")):
            got = self.ask()
        self.assertEqual(got.state, "unavailable")
        self.assertIn("no devcloud CLI was found", got.why)
        self.assertIsNone(got.reply)

    def test_an_older_copy_and_one_of_no_readable_version_are_not_run(self):
        ran = os.path.join(self.home, "ran")
        for version, words in (("0.18.1", "0.18.1, older than 0.19.0"), ("x", "of no readable version")):
            with self.subTest(version=version):
                cli = os.path.join(self.home, "dc-" + version, "bin", "devcloud")
                launcher(cli, "touch %s; exit 0" % ran, version=version)
                with mock.patch.object(threads, "find_devcloud", return_value=("PATH", cli)):
                    got = self.ask()
                self.assertEqual(got.state, "unavailable")
                self.assertIn(words, got.why)
                self.assertFalse(os.path.exists(ran), "not run")
        cli = os.path.join(self.home, "dc-new", "bin", "devcloud")
        launcher(cli, "printf '%s\\n' '" + self.reply("empty") + "'", version="0.19.0")
        with mock.patch.object(threads, "find_devcloud", return_value=("PATH", cli)):
            self.assertEqual(self.ask().state, "asked", "0.19.0 is asked")

    def test_exit_6(self):
        self.standin(exit=6, stderr="devcloud vm: this machine is a devcloud host; drive from a Mac\n")
        got = self.ask()
        self.assertEqual(got.state, "unavailable")
        self.assertIn("does not run on this machine", got.why)

    # --- failed

    def test_a_copy_that_cannot_be_run(self):
        cli = os.path.join(self.home, "unrunnable", "devcloud")
        launcher(cli, "exit 0")
        os.chmod(cli, 0o644)
        with mock.patch.dict(os.environ, {"SMINOS_DEVCLOUD": cli}):
            got = self.ask()
        self.assertEqual(got.state, "failed")
        self.assertIn("could not be run", got.why)

    def test_no_answer_within_the_bound_is_stopped(self):
        self.standin(hang=True)
        began = time.monotonic()
        with mock.patch.dict(os.environ, {"SMINOS_DEVCLOUD_TIMEOUT": "1"}):
            got = self.ask()
        self.assertLess(time.monotonic() - began, 1 + 5 + 2, "the bound, then the stop's grace at most")
        self.assertEqual(got.state, "failed")
        self.assertIn("no answer within 1s", got.why)
        pid = self.calls()[-1]["pid"]
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_another_exit(self):
        self.standin(exit=1, stderr="devcloud: needs Python 3.11 or later on PATH\n")
        got = self.ask()
        self.assertEqual(got.state, "failed")
        self.assertEqual(got.why, "devcloud vm info exited 1: devcloud: needs Python 3.11 or later on PATH")

    def test_each_reply_that_is_not_whole(self):
        cases = ["nan", "infinity", "minus infinity", "a boolean", "a string", "a provider's host with created null",
                 "an adopted host with a number", "a negative number", "an unknown that is no object",
                 "an unknown with no account", "a host not asked"]
        for case in cases:
            with self.subTest(case):
                self.standin(stdout=self.reply(case))
                got = self.ask()
                self.assertEqual((got.state, got.reply, got.why),
                                 ("failed", None, "devcloud vm info gave no whole answer"), "nothing of it said")
        for stdout in ("not json", "[]", '{"hosts": []}', json.dumps(dict(json.loads(self.reply("empty")), listed=[""])),
                       self.reply("empty").replace('"listed"', '"listed_"')):
            with self.subTest(stdout=stdout):
                self.standin(stdout=stdout)
                self.assertEqual(self.ask().state, "failed")
        whole = json.loads(self.reply("whole"))
        no_creator = json.loads(self.reply("whole"))
        del no_creator["hosts"][0]["creator"]
        no_provider = json.loads(self.reply("whole"))
        del no_provider["hosts"][1]["provider"]
        for why, d in (("a host with no creator", no_creator), ("an adopted host with no provider", no_provider)):
            with self.subTest(why):
                self.standin(stdout=json.dumps(d))
                self.assertEqual(self.ask().state, "failed")
        for key in ("created", "spent"):
            with self.subTest("an integer past a float's range in " + key):
                d = json.loads(self.reply("whole"))
                d["hosts"][0][key] = 10 ** 400
                self.standin(stdout=json.dumps(d))
                got = self.ask()
                self.assertEqual((got.state, got.why), ("failed", "devcloud vm info gave no whole answer"))
        self.assertTrue(threads.info_reply(whole, NAMES), "the whole one, read the same way, is whole")
        big = json.loads(self.reply("whole"))
        big["hosts"][0]["spent"] = 1
        self.standin(stdout=json.dumps(big).replace('"spent": 1', '"spent": 1e400'))
        self.assertEqual(self.ask().state, "failed", "a number past a float's range reads as an infinity")


if __name__ == "__main__":
    unittest.main()
