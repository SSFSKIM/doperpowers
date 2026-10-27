#!/usr/bin/env python3
"""sminos under its endpoint (RL10, O12 M5): discovery of rl10.json, the
hello and its welcome, the cutover's identity (daemon/identity.json, a rename
the endpoint made included), the revocation set (daemon/revoked.json), the
endpoint's policy as the machine's, and the DX1 key's handover — the uplink
run in this process (`sminos_uplink.run_rl10`) against sminos's own endpoint
stand-in (endpoint_standin.py), in process too.

What a whole `daemon run` does with it (the supervisor's switch, `daemon
status`, no connection to the hub) is test-uplink.sh's RL10 section; the hub
verbs on a cut-over machine are test-hub.sh's.

Hermetic: every test has its own HOME, SMINOS_HOME and MAWS_USER_DATA under
one temporary directory; nothing listens beyond a Unix socket there.
Run: python3 -B sminos/tests/test_rl10.py
"""

import base64
import glob
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "sminos" / "scripts"
BASE = tempfile.mkdtemp(prefix="smr.", dir="/tmp")   # short: a Unix socket's path is bounded
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "XDG_CONFIG_HOME"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import endpoint_standin  # noqa: E402
import sminos  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_policy as policy  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

KEY = base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode()
S1 = "6c000001-0000-4000-8000-0000000000c1"
S2 = "6c000002-0000-4000-8000-0000000000c2"
S3 = "6c000003-0000-4000-8000-0000000000c3"
S0 = "6c000000-0000-4000-8000-0000000000c0"


def wait_for(pred, timeout=30, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = pred()
        if got:
            return got
        time.sleep(step)
    return pred()


def daemon_log():
    try:
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
            return f.read()
    except OSError:
        return ""


def read(path):
    with open(path) as f:
        return json.load(f)


class Machine(unittest.TestCase):
    """A fresh installation per test: its HOME, SMINOS_HOME and the
    endpoint's directory under MAWS_USER_DATA."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"),
                          MAWS_USER_DATA=os.path.join(home, "m"))
        os.environ.pop("SMINOS_RL10", None)
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        self.epdir = os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint")
        sminos.forget_caches()
        rl10._SAID.update(find=None, revoked=None)

    def hub_json(self, machine="testhost", org="org-1", former=None):
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json")
        sminos.write_json(path, {"hub": "http://127.0.0.1:9", "org": org, "machine": machine, "client_id": "c",
                                 "client_secret": "s", "key": KEY, "former": former or {},
                                 "enrolled": "2026-10-01T00:00:00Z"}, mode=0o600)
        sminos.forget_caches()

    def endpoint(self, **fields):
        ep = endpoint_standin.Endpoint(self.epdir, **fields)
        ep.start()
        self.addCleanup(ep.stop)
        return ep

    def uplink(self):
        """`sminos daemon uplink`'s RL10 loop, in this process, until the test ends."""
        halt, box = threading.Event(), {}
        thread = threading.Thread(target=lambda: box.update(kept=uplink.run_rl10(halt.is_set, halt)), daemon=True)
        thread.start()

        def stop():
            halt.set()
            thread.join(30)
            if box.get("kept") is not None:
                box["kept"].close()
        self.addCleanup(stop)
        return stop

    def identity(self):
        path = rl10.identity_path()
        return read(path) if os.path.exists(path) else None


# ------------------------------------------------------------- discovery


class Discovery(Machine):
    def write(self, mode=0o600, **override):
        os.makedirs(self.epdir, exist_ok=True)
        d = {"socket": os.path.join(self.epdir, "rl10.sock"), "pid": 1, "build": "b", "token": "ab" * 32,
             "protocol": 1, **override}
        path = os.path.join(self.epdir, "rl10.json")
        with open(path, "w") as f:
            json.dump(d, f)
        os.chmod(path, mode)
        return path

    def test_where_the_file_is(self):
        self.assertEqual(rl10.path(), os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint", "rl10.json"))
        os.environ["SMINOS_RL10"] = "/elsewhere/rl10.json"
        self.assertEqual(rl10.path(), "/elsewhere/rl10.json", "SMINOS_RL10 names it for a test")
        del os.environ["SMINOS_RL10"]
        del os.environ["MAWS_USER_DATA"]
        home = os.environ["HOME"]
        with mock.patch.object(rl10.sys, "platform", "darwin"):
            self.assertEqual(rl10.path(), home + "/Library/Application Support/MAWS/mawsd/endpoint/rl10.json")
        with mock.patch.object(rl10.sys, "platform", "linux"):
            self.assertEqual(rl10.path(), home + "/.config/MAWS/mawsd/endpoint/rl10.json")
            with mock.patch.dict(os.environ, XDG_CONFIG_HOME="/x"):
                self.assertEqual(rl10.path(), "/x/MAWS/mawsd/endpoint/rl10.json")

    def test_no_file_is_no_endpoint_and_says_nothing(self):
        self.assertIsNone(rl10.find())
        self.assertNotIn("rl10:", daemon_log())

    def test_a_good_file(self):
        self.write()
        info = rl10.find()
        self.assertEqual((info["socket"], info["token"], info["protocol"]),
                         (os.path.join(self.epdir, "rl10.sock"), "ab" * 32, 1))

    def test_what_is_no_endpoint_is_said_once(self):
        other_uid = os.getuid() + 1
        cases = [
            ("mode 644", lambda: self.write(0o644), "is mode 644, not 600"),
            ("another uid", lambda: self.write(), "not this one (%d)" % other_uid),
            ("protocol 2", lambda: self.write(protocol=2), "speaks protocol 2, not 1"),
            ("a short token", lambda: self.write(token="ab" * 31), "has no token of 64 hex characters"),
            ("no socket", lambda: self.write(socket=""), "names no socket"),
        ]
        for label, make, words in cases:
            with self.subTest(label):
                make()
                patch = mock.patch.object(rl10.os, "getuid", return_value=other_uid) if label == "another uid" \
                    else mock.patch.object(rl10, "PROTOCOL", rl10.PROTOCOL)
                with patch:
                    self.assertIsNone(rl10.find())
                    self.assertIsNone(rl10.find())
                self.assertEqual(daemon_log().count(words), 1, "%s: said once" % label)
                self.assertNotIn("ab" * 31, daemon_log(), "the token is never written")

    def test_a_link_is_no_endpoint(self):
        target = self.write()
        os.rename(target, target + ".real")
        os.symlink(target + ".real", target)
        self.assertIsNone(rl10.find())
        self.assertIn("cannot be opened", daemon_log())


# ------------------------------------------------------------- the hello, the welcome, the identity


class Welcome(Machine):
    def test_a_wrong_token_is_closed_and_backed_off_and_cuts_nothing_over(self):
        self.hub_json()
        ep = self.endpoint()
        ep.token = "cd" * 32   # rl10.json still names the old one
        self.uplink()
        self.assertTrue(wait_for(lambda: len(ep.refused) >= 2, 10), "dialled again after its backoff")
        time.sleep(1.2)
        self.assertLessEqual(len(ep.refused), 3, "backing off: 1 s, then 2 s")
        self.assertEqual(ep.hellos, [])
        self.assertIsNone(self.identity(), "no identity.json is written")
        self.assertFalse(rl10.cut_over())
        self.assertIn("the endpoint did not welcome this machine: the endpoint closed the socket", daemon_log())

    def test_a_refuse_is_said(self):
        ep = self.endpoint(refuse_reason="token")
        ep.token = "cd" * 32
        self.uplink()
        wait_for(lambda: "refused the hello: token" in daemon_log(), 10)
        self.assertIn("the endpoint refused the hello: token", daemon_log())

    def test_a_welcome_without_the_whole_identity_cuts_nothing_over(self):
        self.hub_json()
        ep = self.endpoint()
        ep.identity = {k: v for k, v in ep.identity.items() if k not in ("org", "ref")}
        self.uplink()
        self.assertTrue(wait_for(lambda: len(ep.hellos) >= 2, 10), "dialled again after its backoff")
        self.assertIsNone(self.identity(), "no identity.json is written")
        self.assertFalse(rl10.cut_over())
        self.assertIn("a welcome whose identity has no org, ref: the endpoint is not enrolled", daemon_log())
        self.assertEqual([f["t"] for f in ep.frames()], ["hello"] * len(ep.hellos), "nothing but the hello goes up")

    def probe(self):
        return subprocess.run([sys.executable, str(SCRIPTS / "sminos.py"), "daemon", "probe"], capture_output=True,
                              text=True, timeout=60)

    def test_the_probe_cuts_over_only_on_a_whole_welcome(self):
        self.hub_json()
        out = self.probe()
        self.assertEqual((out.returncode, out.stdout.split(":")[0]), (1, "no endpoint"))
        ep = self.endpoint()
        ep.identity = {**ep.identity, "enrolled": ""}
        out = self.probe()
        self.assertEqual(out.returncode, 1)
        self.assertIn("present but not enrolled (a welcome whose identity has no enrolled", out.stdout)
        ep.identity, token = {**ep.identity, "enrolled": "2026-10-27T00:00:00.000Z"}, ep.token
        ep.token = "cd" * 32
        out = self.probe()
        self.assertEqual(out.returncode, 1)
        self.assertIn("it did not welcome this machine (the endpoint closed the socket", out.stdout)
        ep.refuse_reason = "not-listed"
        out = self.probe()
        self.assertIn("the endpoint refused the hello: not-listed", out.stdout)
        self.assertIsNone(self.identity(), "nothing cut over yet")
        self.assertEqual([f["t"] for f in ep.frames()], ["hello"], "a probe sends nothing but its hello")
        ep.token, ep.refuse_reason = token, None
        out = self.probe()
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("welcomed as testhost of org org-1: this machine is cut over", out.stdout)
        self.assertEqual(self.identity()["name"], "testhost")

    def test_the_first_welcome_cuts_over(self):
        self.hub_json(former={"older": [S0]})
        ep = self.endpoint(policy={"read_only": False, "ceiling": "default"})
        self.uplink()
        hello = ep.wait(lambda f: f["t"] == "hello")
        self.assertEqual(ep.hellos[0][1], hello, "the hello is the connection's first line")
        self.assertEqual(hello["token"], ep.token)
        self.assertEqual(hello["protocol"], {"major": 1, "minor": 0})
        self.assertEqual(hello["capabilities"], [])
        self.assertIsInstance(hello["sminos"]["version"], str)
        self.assertEqual(set(hello["policy"]), {"read_only", "ceiling"})
        ident = wait_for(self.identity)
        self.assertEqual(stat.S_IMODE(os.stat(rl10.identity_path()).st_mode), 0o600)
        self.assertEqual({k: ident[k] for k in ("org", "hub", "name", "ref", "enrolled", "build", "former")},
                         {"org": "org-1", "hub": ep.identity["hub"], "name": "testhost", "ref": "machine-ref-1",
                          "enrolled": ep.identity["enrolled"], "build": ep.build, "former": {"older": [S0]}},
                         "the welcome's identity, and hub.json's former names with their sessions")
        self.assertTrue(ident["cutover"])
        sminos.forget_caches()
        self.assertEqual(sminos.enrollment(), {"url": ep.identity["hub"], "org": "org-1", "machine": "testhost"},
                         "enrollment() reads identity.json, not hub.json's hub")
        self.assertEqual(sminos.machine_identity(), ("testhost", {"older": frozenset({S0})}))
        self.assertTrue(sminos.is_self("older", S0))
        self.assertEqual(daemon.enrolled_at(), sminos._ts_epoch(ep.identity["enrolled"]))
        self.assertTrue(rl10.cut_over())
        self.assertIn("rl10: cut over: this machine is testhost of org org-1", daemon_log())

    def test_the_machines_own_project_is_opened_on_the_socket(self):
        self.hub_json()
        ep = self.endpoint()
        self.uplink()
        own = sminos.machine_project_id("org-1", "testhost")
        hello = ep.wait(lambda f: f["t"] == "hello" and f.get("project") == own)
        self.assertEqual(hello["name"], "testhost")
        machine = ep.wait(lambda f: f["t"] == "session" and f["message"]["kind"] == "machine")
        self.assertEqual(machine["message"]["project"], own)
        self.assertNotIn('"mac":', json.dumps(ep.frames()), "no code on anything")

    def test_a_welcome_that_renames_the_machine(self):
        self.hub_json(machine="oldname")
        pid = "7e000001-0000-4000-8000-0000000000e1"
        log = os.path.join(os.environ["SMINOS_HOME"], "projects", pid, "log")
        os.makedirs(log)
        for writer in ("oldname." + S2, "ancient." + S3, "oldname.human"):
            Path(log, writer + ".jsonl").write_text("")
        for seat, sid in (("seat-a", S1), ("seat-b", S0)):
            Path(os.environ["SMINOS_HOME"], seat + ".json").write_text(json.dumps(
                {"alias": seat, "host": "oldname", "current": sid, "group": "fleet"}))
        ep = self.endpoint()
        ep.identity = {**ep.identity, "name": "newname", "former": ["oldname", "ancient"]}
        self.uplink()
        ident = wait_for(self.identity)
        self.assertEqual(ident["name"], "newname")
        self.assertEqual(ident["former"], {"oldname": sorted([S0, S1, S2]), "ancient": [S3]},
                         "the sessions held under the old name, and under a former name the welcome lists")
        sminos.forget_caches()
        for name, sid in (("oldname", S0), ("oldname", S1), ("oldname", S2), ("ancient", S3)):
            self.assertTrue(sminos.is_self(name, sid), "%s under %s stays this machine's" % (sid, name))
        self.assertFalse(sminos.is_self("oldname", "6c0000ff-0000-4000-8000-0000000000ff"),
                         "another machine under the old name stays another")
        self.assertEqual(sminos.own_machine_project().id, sminos.machine_project_id("org-1", "newname"),
                         "the machine's own project follows the new name")
        ep.wait(lambda f: f["t"] == "hello" and f.get("project") == sminos.machine_project_id("org-1", "newname"))
        first = dict(ident)

        # A later welcome refreshes what it says and keeps the cutover and the former sessions.
        ep.identity = {**ep.identity, "ref": "machine-ref-2", "enrolled": "2026-10-27T01:02:03.000Z", "former": []}
        ep.build = "endpoint-standin-2"
        ep.drop()
        later = wait_for(lambda: (self.identity() or {}).get("ref") == "machine-ref-2" and self.identity())
        self.assertEqual((later["enrolled"], later["build"]), ("2026-10-27T01:02:03.000Z", "endpoint-standin-2"))
        self.assertEqual(later["cutover"], first["cutover"], "the cutover's time never moves")
        self.assertEqual(later["former"], first["former"], "former's sessions are kept")
        self.assertIn("the endpoint renamed this machine newname (it was oldname)", daemon_log())


# ------------------------------------------------------------- the revocation set


class Revoked(Machine):
    def test_kept_whole_merged_and_never_older(self):
        self.assertEqual(rl10.revoked(), {"version": 0, "devices": [], "members": [], "keys": []},
                         "empty sets when none was kept")
        self.hub_json()
        ep = self.endpoint(revoked={"version": 3, "devices": ["d1"], "members": [], "keys": ["k1"]})
        self.uplink()
        wait_for(lambda: os.path.exists(rl10.revoked_path()))
        self.assertEqual(rl10.revoked(), {"version": 3, "devices": ["d1"], "members": [], "keys": ["k1"]})
        self.assertEqual(stat.S_IMODE(os.stat(rl10.revoked_path()).st_mode), 0o600)
        ep.send({"t": "revoked", "version": 4, "devices": [], "members": ["m1"], "keys": ["k2"]})
        wait_for(lambda: rl10.revoked()["version"] == 4)
        self.assertEqual(rl10.revoked(), {"version": 4, "devices": ["d1"], "members": ["m1"], "keys": ["k1", "k2"]},
                         "a later set is merged into the welcome's")
        for _ in range(2):
            ep.send({"t": "revoked", "version": 2, "devices": [], "members": [], "keys": []})
        ep.send({"t": "revoked", "version": 4, "devices": ["d9"], "members": [], "keys": []})
        wait_for(lambda: "d9" in rl10.revoked()["devices"])
        self.assertEqual(rl10.revoked()["keys"], ["k1", "k2"], "an older set changed nothing")
        self.assertEqual(daemon_log().count("a revocation set of version 2, older than the one kept (4): ignored"), 1,
                         "said once")
        ep.revoked = {"version": 5, "devices": [], "members": [], "keys": ["k2"]}
        ep.drop()
        wait_for(lambda: rl10.revoked()["version"] == 5)
        self.assertEqual(rl10.revoked(), {"version": 5, "devices": [], "members": [], "keys": ["k2"]},
                         "the set after a welcome replaces the file whole")

    def test_an_unreadable_file_is_never_an_empty_set(self):
        Path(rl10.revoked_path()).write_text("{not json")
        with self.assertRaises(rl10.RevokedUnreadable):
            rl10.revoked()
        self.assertTrue(rl10.keep_revoked({"version": 1, "devices": [], "members": [], "keys": ["k"]}, False))
        self.assertEqual(rl10.revoked()["keys"], ["k"], "the endpoint's set replaces it")


# ------------------------------------------------------------- the policy


class Policy(Machine):
    def cli_policy(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "sminos.py"), "daemon", "policy", *args],
                              capture_output=True, text=True, timeout=60)

    def test_the_endpoints_policy_is_the_machines(self):
        self.hub_json()
        ep = self.endpoint(policy={"read_only": True, "ceiling": "plan"})
        self.uplink()
        wait_for(lambda: policy.stored().get("endpoint"))
        self.assertTrue(policy.read_only(), "the welcome's policy is the file deliver_next reads")
        self.assertEqual(policy.load()["ceiling"], "plan")
        ep.send({"t": "policy", "read_only": False, "ceiling": "default"})
        wait_for(lambda: not policy.read_only())
        self.assertEqual(policy.machine_policy(), {"read_only": False, "ceiling": "default"})
        ep.send({"t": "policy", "read_only": "yes", "ceiling": "default"})
        wait_for(lambda: "a policy from the endpoint that is no policy" in daemon_log(), 5)
        self.assertFalse(policy.read_only(), "a malformed policy changes nothing")

    def test_daemon_policy_asks_the_endpoint_and_settles_on_its_answer(self):
        self.hub_json()
        ep = self.endpoint(policy={"read_only": False, "ceiling": "default"})
        self.uplink()
        wait_for(lambda: policy.stored().get("endpoint"))
        out = self.cli_policy("--read-only", "on")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("This machine's policy is its endpoint's", out.stdout)
        asked = ep.wait(lambda f: f["t"] == "policy-set")
        self.assertEqual(asked, {"t": "policy-set", "read_only": True}, "only the field that differs")
        wait_for(lambda: policy.stored().get("endpoint", {}).get("read_only") is True)
        self.assertEqual(policy.stored(), {"read_only": True, "ceiling": "default",
                                           "endpoint": {"read_only": True, "ceiling": "default"}})
        self.assertEqual(ep.policy, {"read_only": True, "ceiling": "default"})

    def test_a_change_made_while_the_endpoint_was_away_is_asked_for_not_overwritten(self):
        self.hub_json()
        ep = self.endpoint(policy={"read_only": False, "ceiling": "default"}, answer_policy=False)
        self.uplink()
        wait_for(lambda: policy.stored().get("endpoint"))
        self.cli_policy("--read-only", "on")
        ep.wait(lambda f: f["t"] == "policy-set")
        self.assertTrue(policy.read_only(), "the change holds here meanwhile")
        ep.answer_policy = True
        ep.drop()   # the endpoint restarts holding its old policy
        ep.wait_until(lambda: len(ep.hellos) >= 2)
        self.assertTrue(wait_for(lambda: policy.stored().get("endpoint", {}).get("read_only") is True),
                        "the welcome's older policy did not overwrite the change: it was asked for again")
        self.assertEqual(len(ep.frames("policy-set", conn=ep.hellos[1][0])), 1)
        self.assertTrue(policy.read_only())


# ------------------------------------------------------------- the DX1 key


class LegacyKey(Machine):
    def test_handed_over_as_often_as_asked_and_never_logged(self):
        self.hub_json()
        ep = self.endpoint(persist_legacy=False)   # it dies before it keeps the key
        self.uplink()
        first = ep.wait(lambda f: f["t"] == "legacy-key")
        self.assertEqual(first, {"t": "legacy-key", "org": "org-1", "key": KEY})
        self.assertIsNone(ep.legacy())
        ep.persist_legacy = True
        ep.restart()
        ep.wait_until(lambda: len(ep.frames("legacy-key")) >= 2)
        self.assertEqual(ep.frames("legacy-key")[1], first, "asked again after its restart: the same key")
        wait_for(lambda: ep.legacy() is not None)
        self.assertEqual(ep.legacy(), {"org": "org-1", "key": KEY})
        self.assertNotIn(KEY, daemon_log(), "the key is in no log line")
        self.assertIn("legacy-key?: answered with hub.json's DX1 key of org org-1", daemon_log())

    def test_an_endpoint_of_another_org_is_refused(self):
        self.hub_json(org="org-2")
        ep = self.endpoint()
        self.uplink()
        wait_for(lambda: "legacy-key?: refused" in daemon_log(), 10)
        self.assertIn("legacy-key?: refused: the endpoint welcomed this machine for org org-1, and hub.json's key is "
                      "org org-2's", daemon_log())
        self.assertEqual(ep.frames("legacy-key"), [])
        self.assertNotIn(KEY, daemon_log())


# ------------------------------------------------------------- the stream


class Stream(Machine):
    def test_a_frame_past_a_line_comes_as_parts(self):
        self.hub_json()
        ep = self.endpoint()
        self.uplink()
        ep.wait(lambda f: f["t"] == "hello" and "project" in f)
        projects = [{"id": "7e00%04x-0000-4000-8000-%012x" % (i, i), "name": "p%d-%s" % (i, "x" * 200), "kind": "hub",
                     "retired": True} for i in range(6000)]
        ep.send({"t": "org", "projects": projects, "machines": [{"name": "testhost", "online": True, "seen": None}]})
        org = wait_for(lambda: os.path.exists(sminos.org_path()) and read(sminos.org_path()))
        self.assertEqual(len(org["projects"]), 6000, "joined from its parts and kept")


def tearDownModule():
    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
