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
import sminos_hublog as hublog  # noqa: E402
import sminos_outcomes as outcomes  # noqa: E402
import sminos_policy as policy  # noqa: E402
import sminos_requests as requests  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_rpc as rpc  # noqa: E402
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


# ------------------------------------------------------------- the log plane, uncoded


OTHER = "othermachine/6c0000aa-0000-4000-8000-0000000000aa"


class LogPlane(Machine):
    """The log plane on RL10: this machine's events go up as stored (`ts`,
    no `mac`, no `created`); an arriving event comes wrapped `{event, signer,
    owners?}` and is stored with `verified` added; no code, no nonce."""

    def setUp(self):
        super().setUp()
        self.hub_json()
        self.own = sminos.machine_project("org-1", "testhost")
        self.writer = "testhost/human"
        self.path = sminos.writer_path(self.own, self.writer)

    def lines(self, path=None):
        with open(path or self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def uploads(self, ep):
        return [(n, line) for n, line in list(ep.lines)
                if '"t":"events"' in line.replace(" ", "") and self.own.id in line]

    def test_own_events_go_up_as_stored_and_a_resend_is_byte_identical(self):
        # An older event, its ts of whole seconds, then one _append writes now.
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        Path(self.path).write_text(json.dumps({"ts": "2026-10-01T00:00:00Z", "writer": self.writer, "seq": 1,
                                               "kind": "human", "from": "human", "to": [], "text": "older"}) + "\n")
        sminos.log_append(self.own, self.writer, "human", **{"from": "human", "to": [], "text": "now"})
        stored = self.lines()
        ep = self.endpoint()
        self.uplink()
        up = ep.wait(lambda f: f["t"] == "events" and f["project"] == self.own.id)
        self.assertEqual(up["events"], stored, "uploaded as stored: no mac, no created, ts as written")
        self.assertEqual(up["events"][0]["ts"], "2026-10-01T00:00:00Z", "a whole-second ts goes as it is")
        for e in up["events"]:
            self.assertFalse({"mac", "created", "verified"} & set(e), e)
        ep.wait_until(lambda: len(ep.logs.get(self.own.id, {}).get(self.writer, {})) == 2)
        self.assertEqual(ep.logs[self.own.id][self.writer][1]["created"], "2026-10-01T00:00:00.000Z")
        self.assertEqual(ep.frames("refused"), [], "nothing malformed: sminos adds no created of its own")
        first = self.uploads(ep)
        self.assertEqual(len(first), 1)
        ep.resend(self.own.id, self.writer, 1)
        ep.wait_until(lambda: len(self.uploads(ep)) == 2)
        self.assertEqual(self.uploads(ep)[1][1], first[0][1], "the resend re-uploads the same bytes")
        self.assertNotIn('"mac"', "".join(line for _, line in ep.lines))

    def test_the_own_echo_is_present_and_another_body_is_a_conflict(self):
        sminos.log_append(self.own, self.writer, "human", **{"from": "human", "to": [], "text": "mine"})
        before = Path(self.path).read_bytes()
        ep = self.endpoint()
        self.uplink()
        ep.wait_until(lambda: self.writer in ep.logs.get(self.own.id, {}))
        echo = ep.echo(self.own.id, self.writer, 1)
        self.assertTrue({"created", "sig", "attest"} <= set(echo["event"]))
        ep.events(self.own.id, [echo])
        ep.events(self.own.id, [ep.echo(self.own.id, self.writer, 1, text="not what I said")])
        rejected = ep.wait(lambda f: f["t"] == "rejected")
        self.assertEqual((rejected["reason"], rejected["event"]), ("conflict", {"writer": self.writer, "seq": 1}))
        time.sleep(0.3)
        self.assertEqual(len(ep.frames("rejected")), 1, "the exact echo was present: nothing rejected")
        self.assertEqual(Path(self.path).read_bytes(), before, "the log is as it was")

    def test_an_arriving_event_is_stored_with_verified_and_one_carrying_verified_is_bad_shape(self):
        ep = self.endpoint()
        self.uplink()
        ep.wait(lambda f: f["t"] == "hello" and f.get("project") == self.own.id)
        event = {"ts": "2026-10-27T01:00:00.123Z", "writer": OTHER, "seq": 1, "kind": "say", "from": "a",
                 "to": [], "text": "hello", "created": "2026-10-27T01:00:00.123Z",
                 "sig": {"kid": "k-other", "sig": "AA"}}
        signer = {"kind": "machine", "ref": "ref-other", "name": "othermachine", "keyId": "k-other"}
        owners = [{"id": "mem-2", "email": "two@example.com"}, {"id": "mem-3", "email": None}]
        ep.events(self.own.id, [ep.arriving(event, signer, owners)])
        forged = {**event, "seq": 2, "text": "trust me", "verified": {"signer": signer, "owners": owners}}
        ep.events(self.own.id, [ep.arriving(forged, signer, [])])
        rejected = ep.wait(lambda f: f["t"] == "rejected")
        self.assertEqual((rejected["reason"], rejected["event"]), ("bad-shape", {"writer": OTHER, "seq": 2}))
        other = sminos.writer_path(self.own, OTHER)
        self.assertEqual(self.lines(other), [{**event, "verified": {"signer": signer, "owners": owners}}],
                         "stored verbatim with one key added; the forged verdict never enters the log")
        self.assertIn("its event carries a verified key of its own", daemon_log())

    def test_a_wrapper_without_owners_or_without_a_signer(self):
        ep = self.endpoint()
        self.uplink()
        ep.wait(lambda f: f["t"] == "hello" and f.get("project") == self.own.id)
        event = {"ts": "2026-10-27T01:00:00.123Z", "writer": "hub/mem-1", "seq": 1, "kind": "human",
                 "from": "human", "member": "mem-1", "to": [], "text": "hi"}
        ep.events(self.own.id, [ep.arriving(event, {"kind": "legacy"})])
        ep.events(self.own.id, [{"event": {**event, "seq": 2}}])
        rejected = ep.wait(lambda f: f["t"] == "rejected")
        self.assertEqual((rejected["reason"], rejected["event"]), ("bad-shape", {"writer": "hub/mem-1", "seq": 2}))
        self.assertEqual(self.lines(sminos.writer_path(self.own, "hub/mem-1")),
                         [{**event, "verified": {"signer": {"kind": "legacy"}}}], "owners only as the endpoint sent them")

    def test_no_nonce_index_on_rl10(self):
        hl = hublog.HubLog(self.own, {"key": None, "machine": "testhost"}, coded=False)
        with mock.patch.object(hl, "nonce_index", side_effect=AssertionError("no nonce index on RL10")):
            got = hl.take([{"event": {"ts": "2026-10-27T01:00:00.123Z", "writer": OTHER, "seq": 1, "kind": "say",
                                      "to": [], "text": "x"}, "signer": {"kind": "legacy"}}])
        self.assertEqual(got, (1, []))


# ------------------------------------------------------------- the session lane's drafts


class Drafts(unittest.TestCase):
    def test_no_key_no_code(self):
        reqs = requests.Requests(None, "testhost")
        try:
            draft = {"session": S1, "request": "r1", "tool": "Bash"}
            self.assertEqual(reqs.seal("raised", "p", draft), draft, "a raise goes as its draft")
        finally:
            reqs.close()
        r = {"event": {"writer": "hub/m", "seq": 1}, "session": S1, "outcome": "delivered", "reason": None}
        self.assertEqual(outcomes.message(None, "testhost", "p", r)["message"]["body"],
                         {"event": r["event"], "session": S1, "outcome": "delivered", "reason": None})


# ------------------------------------------------------------- the RPCs over RL10


class FakeHere:
    def __init__(self, project, sessions=()):
        self.p, self.sessions = project, set(sessions)

    def project(self, pid):
        return self.p if pid == self.p.id else None

    def has_session(self, _project, sid):
        return sid in self.sessions

    def record(self, _sid):
        return None

    def checkouts(self, _project):
        return []

    def cwd(self, _project, _sid):
        return ""


class Rpcs(Machine):
    def setUp(self):
        super().setUp()
        self.hub_json()
        self.own = sminos.machine_project("org-1", "testhost")

    def ledger(self):
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpc.LEDGER_FILE)
        return read(path) if os.path.exists(path) else {}

    def result(self, ep, op, n=1):
        ep.wait_until(lambda: len([f for f in ep.frames("rpc-result") if f.get("opId") == op]) >= n)
        return [f for f in ep.frames("rpc-result") if f.get("opId") == op]

    def test_the_entry_keeps_the_remote_fields_and_a_derived_target(self):
        policy.take_endpoint({"read_only": True, "ceiling": "default"})   # every RPC refused, and kept
        rpcs = rpc.Rpcs(None, "testhost", coded=False)
        here = FakeHere(self.own, {S1})
        now = endpoint_standin.iso()
        base = {"project": self.own.id, "machine": "testhost", "member": "mem-1", "device": "dev-1", "created": now,
                "opCreated": now, "fingerprint": "fp-1"}
        steer = {**base, "rpc": "steer", "nonce": endpoint_standin.b64url(b"\x01" * 16), "opId": "op-steer-0000000001",
                 "args": {"session": S1, "text": "go"}, "context": {"lane": "A", "session": S1, "launch": "L1"},
                 "target": {"kind": "machine"}}
        spawn = {**base, "rpc": "spawn", "nonce": endpoint_standin.b64url(b"\x02" * 16), "opId": "op-spawn-0000000001",
                 "args": {"checkout": "/nowhere"}, "proof": {"v": 1, "action": "sminos.spawn"}}
        rpcs.receive(steer, here)
        rpcs.receive(spawn, here)
        entries = self.ledger()
        self.assertEqual({k: entries["op-steer-0000000001"].get(k) for k in
                          ("member", "device", "fingerprint", "context", "target", "nonce")},
                         {"member": "mem-1", "device": "dev-1", "fingerprint": "fp-1", "context": steer["context"],
                          "target": {"kind": "session", "session": S1}, "nonce": steer["nonce"]},
                         "target derived from the RPC, never the frame's")
        self.assertEqual(entries["op-steer-0000000001"]["outcome"]["error"]["code"], "read-only")
        self.assertEqual({k: entries["op-spawn-0000000001"].get(k) for k in ("target", "proof")},
                         {"target": {"kind": "machine"}, "proof": spawn["proof"]})
        frames = rpcs.due({self.own.id})
        self.assertEqual(sorted((f["opId"], f["nonce"]) for f in frames),
                         sorted([("op-spawn-0000000001", spawn["nonce"]), ("op-steer-0000000001", steer["nonce"])]),
                         "rpc-result carries the opId beside the nonce")

    def test_an_rpc_down_rl10(self):
        ep = self.endpoint(policy={"read_only": True, "ceiling": "default"}, ack_results=False)
        self.uplink()
        ep.wait(lambda f: f["t"] == "hello" and f.get("project") == self.own.id)
        wait_for(lambda: policy.read_only())
        spawn = ep.rpc("spawn", self.own.id, {"checkout": "/nowhere"})
        got = self.result(ep, spawn["opId"])[0]
        self.assertEqual({k: got[k] for k in ("project", "opId", "nonce")},
                         {"project": self.own.id, "opId": spawn["opId"], "nonce": spawn["nonce"]})
        self.assertEqual(got["outcome"]["error"]["code"], "read-only", "on_rpc and receive ran it, unchanged")
        self.assertEqual(self.ledger()[spawn["opId"]]["target"], {"kind": "machine"})
        wrong = ep.rpc("interrupt", self.own.id, {"session": S1}, machine="elsewhere")
        loose = self.result(ep, wrong["opId"])[0]
        self.assertEqual((loose["nonce"], loose["outcome"]["error"]["code"]), (wrong["nonce"], "wrong-machine"),
                         "a loose refusal's rpc-result carries its opId")

        # Again after each welcome until rpc-ack; settled by the opId when the nonce is unknown.
        ep.drop()
        self.result(ep, spawn["opId"], 2)
        ep.send({"t": "rpc-ack", "opId": spawn["opId"], "nonce": endpoint_standin.b64url(b"\x09" * 16)})
        self.assertTrue(wait_for(lambda: self.ledger()[spawn["opId"]].get("acked") is True), "settled by its opId")
        ep.drop()
        ep.wait_until(lambda: len(ep.hellos) >= 3)
        ep.wait_until(lambda: any(n == ep.hellos[-1][0] and f.get("project") == self.own.id
                                  for n, f in ep.received if f.get("t") == "hello"))
        time.sleep(0.5)
        self.assertEqual(len(self.result(ep, spawn["opId"])), 2, "acknowledged: not sent again")

        # query and tombstone reach the ledger's own answers.
        ep.query(spawn["opId"], spawn["opCreated"])
        queried = ep.wait(lambda f: f["t"] == "queried")
        self.assertEqual({k: queried[k] for k in ("opId", "state")}, {"opId": spawn["opId"], "state": "refused"})
        self.assertEqual(queried["outcome"]["error"]["code"], "read-only")
        lost = "op-never-arrived-0001"
        ep.query(lost, endpoint_standin.iso())
        self.assertEqual(ep.wait(lambda f: f["t"] == "queried" and f["opId"] == lost),
                         {"t": "queried", "opId": lost, "state": "not-received"})
        ep.tombstone(lost)
        self.assertEqual(ep.wait(lambda f: f["t"] == "tombstoned" and f["opId"] == lost),
                         {"t": "tombstoned", "opId": lost, "ok": True})
        ep.tombstone(spawn["opId"])
        self.assertEqual(ep.wait(lambda f: f["t"] == "tombstoned" and f["opId"] == spawn["opId"]),
                         {"t": "tombstoned", "opId": spawn["opId"], "ok": False, "state": "refused"})
        late = ep.rpc("spawn", self.own.id, {"checkout": "/nowhere"}, opId=lost)
        self.assertEqual(self.result(ep, lost)[0]["outcome"]["error"]["code"], "tombstoned")
        self.assertEqual(self.result(ep, lost)[0]["nonce"], late["nonce"])


def tearDownModule():
    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
