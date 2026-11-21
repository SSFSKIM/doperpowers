#!/usr/bin/env python3
"""A channel id is told from a project's at every door (CH1's M1:
docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md, the milestone's
"Proves"; Interfaces §1 and §8).

- `is_channel_id` on every entry of MAWS's shared vectors' `ids`.
- A channel's kind is `channel`, whatever the org's directory calls it; it
  is no project to a listing (`projects`, `list --org`, `list --org --json`,
  `machines` print what they print without it), and a log to what opens,
  reconciles or leaves logs.
- Names: a hub project and a machine project of one name, no channel
  present, found as today; the one refusal for a name a channel and a
  project share, two channels share, and two projects of one tier share,
  each log reached by `name#short`; a project lookup refuses a channel.
- The `.smns` rule: a `.smns` naming a channel's id files its directory in
  the machine's project and says so once (sminos's own rule, beside the
  parity suite, project_rule_parity.py, whose shared cases hold no
  version-8 id), on a machine not enrolled the last rungs'.
- An override naming a channel (an older copy's `join`) is read as absent,
  and the running session is moved back: a `retired` `moved` in the
  channel's log, no `joined` of this code's there, the session a member of
  its project.
- A channel's view has no members whatever its log holds, its plane maps
  are empty, `lifecycle` appends nothing but a `retired` there and
  `append_host` raises; the daemon ticks no channel as a project and its
  channel pass reconciles one: it undoes an older copy's `joined` only while
  a process or a seat holds the session, a closed session's left as it is
  until it runs again, and an import into a channel delivers nothing.
- The doors classify an explicit channel id by its form, registered or not
  (`say --in`, a tag's qualifier, `join`, a verb's target), a say's tags all
  checked before any member is looked up, `join` refusing a channel before a
  seat; a rooted registration an older copy made of a channel is no project
  (registered_guess, a seat's fallback, a say's destination); a location
  statement naming a channel is no statement; a channel entry of kind
  `machine` retires no machine; a record's `channels` that is no list holds
  none.
- `#` in a project's name: an exact name first, a qualifier read from the
  right.

Hermetic: HOME and SMINOS_HOME are temporary, fresh for each test; the one
live session is a `sleep` with an engine record the test writes.
Run: python3 -B sminos/tests/test_channels.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import glob
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts")
BASE = os.path.realpath(tempfile.mkdtemp(prefix="smch."))
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "MAWS_LANE",
            "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR", "SMINOS_LAUNCH", "CLAUDE_PID",
            "MAWS_LAUNCHED_BY"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), DAEMON_HOST="testhost",
                  SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, SCRIPTS)

import sminos  # noqa: E402
import sminos_channels as channels  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_plane as plane  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_records as records  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

VECTORS = os.path.join(HERE, "vectors", "maws", "channel-rule.json")
ORG, MACHINE, URL = "org-1", "testhost", "http://127.0.0.1:9"
CRED = {"org": ORG, "hub": URL, "machine": MACHINE, "key": None}
HUB = {"url": URL, "org": ORG}
DESK = "5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c"     # a channel, the fixture's
ROOM1 = "0123abcd-4567-8abc-a123-456789abcdef"    # two channels of one name
ROOM2 = "0123abce-4567-8abc-a123-456789abcdef"
PROJ = "7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d"     # a project (version 4)
TWIN1 = "7d2b9c41-1f3e-4a6b-8c5d-9e0f1a2b3c4d"
TWIN2 = "7d2b9c42-1f3e-4a6b-8c5d-9e0f1a2b3c4d"
REMOTE = "6b000001-0000-4000-8000-0000000000b1"   # another machine's session


def exits(fn, *args):
    """(exit code, what was said on stderr) of a call that dies."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        try:
            fn(*args)
        except SystemExit as e:
            return e.code, err.getvalue()
    raise AssertionError("%s%r did not exit; it said %r" % (fn.__name__, args, err.getvalue()))


def tree(root):
    """Every file under `root` with its bytes: what a refusal must leave as it was."""
    out = {}
    for path in glob.glob(os.path.join(root, "**", "*"), recursive=True):
        if os.path.isfile(path) and not path.endswith(".lock"):
            with open(path, "rb") as f:
                out[os.path.relpath(path, root)] = f.read()
    return out


class Machine(unittest.TestCase):
    """A fresh installation per test, cut over to its endpoint as MACHINE of ORG."""

    enrolled = True

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"))
        for d in (os.path.join(os.environ["HOME"], ".claude", "sessions"), os.path.join(os.environ["SMINOS_HOME"],
                                                                                         "daemon")):
            os.makedirs(d, mode=0o700)
        self.home = home
        self.procs = []
        self.addCleanup(self.stop_all)
        if self.enrolled:
            sminos.write_json(rl10.identity_path(), {
                "org": ORG, "hub": URL, "name": MACHINE, "former": {}, "ref": "machine-ref-1",
                "enrolled": "2026-11-10T00:00:00.000Z", "cutover": "2026-11-10T00:00:01.000Z", "build": "b"},
                mode=0o600)
        sminos.forget_caches()

    def stop_all(self):
        for proc in self.procs:
            proc.kill()
            proc.wait()
        sminos.forget_caches()

    def project(self, pid, name, root=""):
        sminos.register_if_absent(sminos.make_project(pid, name, "", root, HUB))
        sminos.forget_caches()
        return sminos.known_project(pid)

    def channel(self, cid, name):
        return channels.register(cid, name)

    def remote_member(self, p, sid=REMOTE, alias="faraway"):
        sminos.log_append(p, "other/%s" % sid, "joined", session=sid, alias=alias, name_source="user",
                          machine="other", cwd="/d", worktree="", role="", seat="", by="")
        sminos.forget_caches()

    def cli(self, *args, env=None, cwd=None):
        r = subprocess.run([sys.executable, "-B", "-I", os.path.join(SCRIPTS, "sminos.py"), *args],
                           cwd=cwd or os.environ["HOME"], env=dict(os.environ, **(env or {})), capture_output=True,
                           text=True, timeout=60)
        return r.returncode, r.stdout, r.stderr

    def live(self, sid, cwd, name="worker"):
        """A live session of this machine: its engine record names a `sleep`."""
        proc = subprocess.Popen(["sleep", "600"])
        self.procs.append(proc)
        with open(os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % proc.pid), "w") as f:
            json.dump({"pid": proc.pid, "sessionId": sid, "cwd": cwd, "kind": "interactive", "name": name,
                       "nameSource": "user", "status": "idle"}, f)
        sminos.forget_caches()
        return proc

    def log_events(self, pid):
        out = []
        for path in sorted(glob.glob(os.path.join(sminos.projects_root(), pid, "log", "*.jsonl"))):
            with open(path) as f:
                out += [json.loads(line) for line in f if line.strip()]
        return out


class Ids(unittest.TestCase):
    def test_every_id_of_the_shared_vectors(self):
        with open(VECTORS) as f:
            ids = json.load(f)["ids"]
        self.assertGreater(len(ids), 20)
        for case in ids:
            self.assertIs(sminos.is_channel_id(case["id"]), case["channel"], case["why"])
        for other in (None, 8, ["5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c"], b"5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c"):
            self.assertFalse(sminos.is_channel_id(other))


class Kinds(Machine):
    def test_a_channel_is_a_channel_whatever_the_directory_calls_it(self):
        frame = {"projects": [{"id": DESK, "name": "desk-integration", "kind": "machine", "retired": False},
                              {"id": PROJ, "name": "app", "kind": "hub", "retired": False}],
                 "machines": [{"name": MACHINE, "online": False}]}
        self.assertTrue(uplink.keep_org(frame, CRED))
        sminos.forget_caches()
        c, p = sminos.known_project(DESK), sminos.known_project(PROJ)
        self.assertEqual(sminos.project_kind(c), "channel")
        self.assertEqual(sminos.project_kind(p), "hub")
        self.assertEqual([x.id for x in sminos.known_projects()], [PROJ])
        self.assertEqual([x.id for x in sminos.known_channels()], [DESK])
        self.assertEqual(sorted(x.id for x in sminos.known_logs()), sorted([DESK, PROJ]))
        self.assertEqual(sorted(uplink.hub_projects(CRED)), sorted([DESK, PROJ]), "its log is opened")
        self.assertNotIn(DESK, {x.id for x in sminos.org_scope()})
        self.assertEqual(sminos.project_label(DESK), "desk-integration")

    def test_register_takes_a_channel_id_alone(self):
        c = self.channel(DESK, "desk-integration")
        self.assertEqual((c.id, c.name, c.root, c.hub), (DESK, "desk-integration", "", HUB))
        with self.assertRaises(ValueError):
            channels.register(PROJ, "app")

    def test_listings_with_a_channel_beside_them_print_what_they_printed(self):
        p = self.project(PROJ, "app")
        self.remote_member(p)
        verbs = (("projects",), ("projects", "--all"), ("list", "--org"), ("list", "--org", "--json"),
                 ("list", "--org", "--all"), ("machines",), ("list", "--org", "faraway"), ("find", "faraway"))
        before = {v: self.cli(*v) for v in verbs}
        for v, (rc, out, _) in before.items():
            self.assertEqual(rc, 0, v)
        self.assertIn("faraway", before[("list", "--org")][1])
        c = self.channel(DESK, "desk-integration")
        self.remote_member(c, sid="6b000002-0000-4000-8000-0000000000b2", alias="oldjoin")   # an older copy's join
        for v in verbs:
            rc, out, err = self.cli(*v)
            self.assertEqual((rc, out), before[v][:2], v)
            self.assertNotIn("desk-integration", out + err, v)


class Names(Machine):
    def test_a_hub_project_and_a_machine_project_of_one_name_as_today(self):
        uplink.register_own(CRED)
        own = sminos.machine_project_id(ORG, MACHINE)
        hub = self.project(PROJ, MACHINE)
        self.assertEqual([p.id for p in sminos.project_tiers(MACHINE)], [hub.id, own])
        self.assertEqual(sminos.find_project(MACHINE).id, hub.id)
        self.assertEqual(sminos.tag_project(sminos.known_project(own)), MACHINE, "read in turn: the name reaches it")

    def assert_refused(self, fn, q, labels):
        code, said = exits(fn, q)
        self.assertEqual(code, sminos.EXIT_UNKNOWN)
        self.assertEqual(said.strip(), "sminos: ambiguous name '%s': %s — name one as listed, or by its id"
                         % (q, ", ".join(labels)))

    def test_a_name_a_channel_and_a_project_share(self):
        p = self.project(PROJ, "desk")
        c = self.channel(DESK, "desk")
        labels = ["desk#%s (channel)" % DESK[:8], "desk#%s (project)" % PROJ[:8]]
        for fn in (sminos.find_project, sminos.project_tiers, channels.find_channel, sminos.names_channel):
            self.assert_refused(fn, "desk", labels)
        self.assertEqual(channels.find_channel("desk#" + DESK[:8]).id, c.id)
        self.assertEqual(channels.find_channel(DESK).id, c.id)
        self.assertEqual(sminos.find_project("desk#" + PROJ[:8]).id, p.id)
        self.assertEqual(sminos.find_project("desk#" + PROJ).id, p.id, "a longer short, the whole id")
        self.assertEqual(sminos.tag_project(p), PROJ, "a tag names it by its id")
        code, said = exits(sminos.find_project, "desk#" + DESK[:8])
        self.assertEqual((code, said.strip()), (sminos.EXIT_UNKNOWN, "sminos: 'desk#%s' is a channel, not a project: "
                                                "sminos channel show desk#%s prints it" % (DESK[:8], DESK[:8])))
        code, said = exits(channels.find_channel, "desk#" + PROJ[:8])
        self.assertEqual(said.strip(), "sminos: 'desk#%s' is a project, not a channel" % PROJ[:8])
        self.assertIsNone(sminos.find_project("desk#" + DESK[:8], required=False))
        self.assertIsNone(sminos.find_project("desk#0000000000", required=False), "a short that names none")

    def test_a_name_two_channels_share(self):
        self.channel(ROOM1, "room")
        self.channel(ROOM2, "room")
        self.assert_refused(channels.find_channel, "room", ["room#0123abcd (channel)", "room#0123abce (channel)"])
        self.assertEqual(channels.find_channel("room#0123abcd").id, ROOM1)
        self.assertEqual(channels.find_channel("room#0123abce").id, ROOM2)
        self.assertEqual(exits(channels.find_channel, "room#0123")[0], sminos.EXIT_UNKNOWN, "fewer than eight")
        self.assertIsNone(channels.find_channel("nothing", required=False))
        code, said = exits(channels.find_channel, "nothing")
        self.assertEqual(said.strip(), "sminos: no channel 'nothing' is known on this machine")

    def test_a_name_two_projects_of_one_tier_share(self):
        self.project(TWIN1, "twin")
        self.project(TWIN2, "twin")
        self.assert_refused(sminos.find_project, "twin", ["twin#7d2b9c41 (project)", "twin#7d2b9c42 (project)"])
        self.assertEqual(sminos.find_project("twin#7d2b9c42").id, TWIN2)
        # Local projects, whose ids are no UUIDs, are listed by their whole id, which names them.
        for pid in ("local-one", "local-two"):
            sminos.register_if_absent(sminos.make_project(pid, "lp", "", os.path.join(self.home, pid)))
        sminos.forget_caches()
        self.assert_refused(sminos.find_project, "lp", ["lp#local-one (local project)", "lp#local-two (local project)"])
        self.assertEqual(sminos.find_project("lp#local-two").id, "local-two")

    def test_a_project_lookup_refuses_a_channel(self):
        self.channel(DESK, "desk-integration")
        for fn in (sminos.find_project, sminos.project_tiers):
            code, said = exits(fn, "desk-integration")
            self.assertEqual((code, said.strip()), (sminos.EXIT_UNKNOWN, "sminos: 'desk-integration' is a channel, "
                                                    "not a project: sminos channel show desk-integration prints it"))
        self.assertIsNone(sminos.find_project("desk-integration", required=False))
        self.assertIsNone(sminos.find_project(DESK, required=False))
        self.assertEqual(sminos.names_channel("desk-integration").id, DESK)
        self.assertIsNone(sminos.names_channel("nothing"))
        for verb in (("chat", "desk-integration"), ("list", "desk-integration"), ("list", "--project", DESK)):
            rc, out, err = self.cli(*verb)
            self.assertEqual(rc, 4, verb)
            self.assertIn("is a channel, not a project: sminos channel show", err, verb)


class Smns(Machine):
    def test_a_smns_naming_a_channel_files_its_directory_in_the_machine_project(self):
        d = os.path.join(self.home, "w")
        os.makedirs(d)
        with open(os.path.join(d, ".smns"), "w") as f:
            json.dump({"project": DESK, "name": "desk-integration", "hub": {"org": ORG}}, f)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            first = sminos.decision(d)
            sminos.forget_caches()
            again = sminos.resolve_project(d)
        own = sminos.machine_project_id(ORG, MACHINE)
        self.assertEqual((first.by, first.project.id), ("machine", own))
        self.assertEqual(again.id, own)
        self.assertEqual(err.getvalue(), "sminos: warning: ignoring %s: it names a channel's id, and a channel is no "
                         "project; this directory is in the machine's project\n" % os.path.join(d, ".smns"))
        self.assertNotIn(DESK, os.listdir(sminos.projects_root()) if os.path.isdir(sminos.projects_root()) else [])


class SmnsNotEnrolled(Machine):
    enrolled = False

    def test_on_a_machine_not_enrolled_the_last_rungs(self):
        d = os.path.join(self.home, "repo")
        subprocess.run(["git", "init", "-q", d], check=True)
        with open(os.path.join(d, ".smns"), "w") as f:
            json.dump({"project": DESK, "name": "desk-integration"}, f)
        with contextlib.redirect_stderr(io.StringIO()):
            got = sminos.decision(d)
        self.assertEqual((got.by, got.project.id), ("local", "local-repo"))


class OlderJoin(Machine):
    def test_an_override_naming_a_channel_is_absent_and_the_running_session_moves_back(self):
        root = os.path.join(self.home, "app")
        os.makedirs(root)
        with open(os.path.join(root, ".smns"), "w") as f:
            json.dump({"project": PROJ, "name": "app", "hub": {"org": ORG}}, f)
        p = self.project(PROJ, "app", root)
        c = self.channel(DESK, "desk-integration")
        sid = "6c000001-0000-4000-8000-0000000000c1"
        self.live(sid, root)
        # What an older copy's `sminos join desk-integration` leaves: the override, and a joined in the channel.
        sminos.write_override(sid, DESK)
        sminos.log_append(c, "%s/%s" % (MACHINE, sid), "joined", session=sid, alias="worker", name_source="user",
                          machine=MACHINE, cwd=root, worktree="", role="", seat="", by="join")
        sminos.forget_caches()
        self.assertEqual(sminos.session_project(sid, root).id, PROJ, "the override is read as absent")
        self.assertIn("it is a channel, not a project — sminos channel add desk-integration places a thread in it",
                      sminos.join_refusal(c))
        self.assertEqual(sminos.view_of(c).members, [])
        sminos.forget_caches()
        self.assertEqual([m.session for m in sminos.view_of(p).members], [sid])
        evs = [e for e in self.log_events(DESK) if e.get("session") == sid]
        self.assertEqual([(e["kind"], e.get("reason"), e.get("project")) for e in evs],
                         [("joined", None, None), ("retired", "moved", PROJ)], "the older joined, then this code's undo")
        # Read again, nothing more is written there.
        sminos.forget_caches()
        sminos.view_of(c)
        with contextlib.redirect_stdout(io.StringIO()):
            daemon.tick_all(quiet=True)
        self.assertEqual(len([e for e in self.log_events(DESK) if e.get("session") == sid]), 2)
        self.assertEqual([e["kind"] for e in self.log_events(PROJ) if e.get("session") == sid].count("joined"), 1)


class NoMembers(Machine):
    def test_a_channel_view_and_its_plane_maps_hold_no_member(self):
        c = self.channel(DESK, "desk-integration")
        self.remote_member(c)
        sminos.log_append(c, "other/%s" % REMOTE, "state", session=REMOTE, state="idle")
        sminos.forget_caches()
        view = sminos.view_of(c)
        self.assertEqual((view.members, view.rows, view.retired, view.info), ([], [], [], {}))
        self.assertEqual(len(view.events), 2)
        pl = plane.Plane(MACHINE, lambda: None)
        self.addCleanup(pl.close)
        pl.refresh(c)
        self.assertEqual((pl.here[DESK], pl.member_rows[DESK], pl.members[DESK], pl.left[DESK]), ({}, {}, set(), {}))
        self.assertEqual(pl.presence(DESK, force=True), [])

    def test_nothing_but_a_retired_is_appended_and_no_host_event(self):
        c = self.channel(DESK, "desk-integration")
        sid = "6c000002-0000-4000-8000-0000000000c2"
        for kind, fields in (("joined", {"alias": "x", "machine": MACHINE, "cwd": "/w"}), ("state", {"state": "idle"}),
                             ("titled", {"title": "t"}), ("in-charge", {"text": "x"}), ("status", {"text": "x"}),
                             ("renamed", {"alias": "y"}), ("channels", {"channels": []})):
            self.assertEqual(sminos.lifecycle(c, sid, kind, **fields), [], kind)
        self.assertEqual(self.log_events(DESK), [])
        got = sminos.lifecycle(c, sid, "retired", by="", reason="moved", project=PROJ)
        self.assertEqual([e["kind"] for e in got], ["retired"])
        with self.assertRaises(sminos.LogWriteFailed):
            sminos.append_host(c, sid, [{"kind": "message", "text": "hi", "src": "s1", "ts": sminos.now()}])
        self.assertFalse(os.path.exists(os.path.join(c.home, sminos.HOST_STORE)))


class Tick(Machine):
    def test_the_daemon_ticks_no_channel_as_a_project(self):
        p = self.project(PROJ, "app")
        c = self.channel(DESK, "desk-integration")
        self.remote_member(c)
        before = tree(c.home)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            daemon.tick_all()
        self.assertIn("app:", out.getvalue())
        self.assertNotIn("desk-integration", out.getvalue(), "no tick line of a channel")
        self.assertEqual(tree(c.home), before, "nothing written in a channel's home: no daemon.json, no event")
        self.assertTrue(os.path.exists(os.path.join(p.home, "daemon.json")))

    def test_a_failing_channel_pass_is_said_once(self):
        c = self.channel(DESK, "desk-integration")
        calls = []

        def boom(project, *a, **k):
            calls.append(project.id)
            raise OSError("disk")
        real = sminos.view_of
        sminos.view_of = boom
        try:
            daemon.channel_pass([c], [])
            daemon.channel_pass([c], [])
        finally:
            sminos.view_of = real
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
            said = [line for line in f if "the pass of channel desk-integration failed" in line]
        self.assertEqual((calls, len(said)), ([DESK, DESK], 1))


class LegacyRoot(Machine):
    """A channel registered rooted at a folder, as an older copy registered a
    channel-valued .smns in a protected folder."""

    def setUp(self):
        super().setUp()
        self.root = os.path.join(os.environ["HOME"], "Documents", "desk")
        os.makedirs(os.path.join(self.root, "w"))
        sminos.register_if_absent(sminos.make_project(DESK, "app", "", self.root, HUB))
        self.project(PROJ, "app")
        sminos.forget_caches()

    def test_a_rooted_channel_registration_is_no_project(self):
        sid = "6c000005-0000-4000-8000-0000000000c5"
        seat = {"cwd": os.path.join(self.root, "w"), "current": sid, "group": "g", "status": "idle"}
        with mock.patch.object(sminos, "TCC", True):
            sminos.forget_caches()
            self.assertIsNone(sminos.registered_guess(os.path.join(self.root, "w")))
            self.assertEqual([p.id for p in sminos.known_projects([seat])], [PROJ])
        self.assertEqual([p.id for p in sminos.known_channels()], [DESK])
        with mock.patch.object(sminos, "seat_project", lambda s, fresh=False: sminos.known_project(DESK)):
            sminos.forget_caches()
            self.assertEqual([p.id for p in sminos.known_projects([seat])], [PROJ], "a seat's fallback holds none")

    def test_a_say_whose_destination_is_a_channel_is_refused(self):
        with mock.patch.object(sminos, "caller_project", lambda caller=None: sminos.known_project(DESK)):
            code, said = exits(sminos.main, ["say", "hello"])
        self.assertEqual(code, 1)
        self.assertIn("is a channel, and speaking in a channel is not available", said)
        self.assertEqual(self.log_events(DESK), [])


class ChannelReconcile(Machine):
    """A channel's reconciliation undoes an older copy's `joined` only while a
    process or a seat holds the session."""

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.home, "app")
        os.makedirs(self.root)
        with open(os.path.join(self.root, ".smns"), "w") as f:
            json.dump({"project": PROJ, "name": "app", "hub": {"org": ORG}}, f)
        self.p = self.project(PROJ, "app", self.root)
        self.c = self.channel(DESK, "desk-integration")

    def older_join(self, sid):
        sminos.log_append(self.c, "%s/%s" % (MACHINE, sid), "joined", session=sid, alias="worker",
                          name_source="user", machine=MACHINE, cwd=self.root, worktree="", role="", seat="", by="join")
        sminos.forget_caches()

    def kinds(self, pid, sid):
        return [(e["kind"], e.get("reason")) for e in self.log_events(pid) if e.get("session") == sid]

    def tick(self):
        sminos.forget_caches()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            daemon.tick_all(quiet=True)

    def test_a_closed_session_is_left_until_it_runs_again(self):
        for n, lane in ((6, "B"), (7, "A")):
            sid = "6c00000%d-0000-4000-8000-0000000000c%d" % (n, n)
            records.establish(sid, records.default_provenance())
            if lane == "B":
                records.set_controller(sid, "B")
            self.older_join(sid)
            for _ in range(2):
                self.tick()
            self.assertEqual(self.kinds(DESK, sid), [("joined", None)], "lane %s: nothing written for it" % lane)
            self.assertIsNone(sminos.threads_module().thread_of(sid), "lane %s: no thread made for it" % lane)
            proc = self.live(sid, self.root)
            self.tick()
            self.assertEqual(self.kinds(DESK, sid), [("joined", None), ("retired", "moved")], lane)
            self.assertIn(("joined", None), self.kinds(PROJ, sid), lane)
            proc.kill()
            proc.wait()

    def test_an_import_into_a_channel_delivers_nothing(self):
        calls = []
        with mock.patch.object(sminos, "view_of", lambda *a, **k: calls.append(a) or None), \
                mock.patch.object(daemon, "deliver_owed", lambda *a, **k: calls.append(a) or (0, [])):
            hublog.HubLog(self.c, CRED).deliver()
        self.assertEqual(calls, [])


class Doors(Machine):
    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.home, "app")
        os.makedirs(self.root)
        with open(os.path.join(self.root, ".smns"), "w") as f:
            json.dump({"project": PROJ, "name": "app", "hub": {"org": ORG}}, f)
        self.p = self.project(PROJ, "app", self.root)
        self.channel(DESK, "desk-integration")

    def test_a_say_checks_every_tag_before_any_member_is_looked_up(self):
        sid = "6c000008-0000-4000-8000-0000000000c8"
        self.live(sid, self.root)
        rc, out, err = self.cli("say", "@worker @desk-integration/worker hello", cwd=self.root)
        self.assertEqual(rc, 1, err)
        self.assertIn("desk-integration is a channel", err)
        self.assertEqual(self.log_events(PROJ), [], "no member was looked up: nothing reconciled, nothing recorded")

    def test_an_unregistered_channel_id_is_a_channel_at_every_door(self):
        other = "9e000001-0000-8000-8000-0000000000e1"
        self.assertTrue(sminos.is_channel_id(other))
        for args, code, words in ((("say", "--in", other, "hi"), 1, "%s is a channel" % other),
                                  (("say", "@%s/worker hi" % other), 1, "%s is a channel" % other),
                                  (("charge", "%s/worker" % other, "x"), 4, "names a thread through a channel")):
            rc, out, err = self.cli(*args, cwd=self.root)
            self.assertEqual(rc, code, (args, err))
            self.assertIn(words, err, args)
        self.assertEqual(self.log_events(PROJ), [])

    def test_join_refuses_a_channel_before_a_seat(self):
        sid = "6c000009-0000-4000-8000-0000000000c9"
        other = "9e000001-0000-8000-8000-0000000000e1"
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}), \
                mock.patch.object(sminos, "caller_seat", lambda: {"current": sid, "alias": "w"}):
            for q in ("desk-integration", DESK, other):
                code, said = exits(sminos.main, ["join", q])
                self.assertEqual(code, 1, q)
                self.assertIn("cannot join %s: it is a channel, not a project — sminos channel add %s" % (q, q),
                              said)

    def test_a_location_statement_naming_a_channel_is_no_statement(self):
        d = os.path.join(self.home, "stated")
        os.makedirs(d)
        st = os.stat(d)
        birth = sminos.birth_ns(getattr(st, "st_birthtime", 0))
        frame = {"t": "org", "projects": [{"id": DESK, "name": "desk-integration", "kind": "hub", "retired": False}],
                 "machines": [{"name": MACHINE, "online": False}],
                 "locations": {"gen": 1, "at": [{"path": sminos.canonical(d), "project": DESK, "stated": "linked",
                                                 "anchor": {"dev": str(st.st_dev), "ino": str(st.st_ino),
                                                            "birth": str(int(birth or 0))}}]}}
        self.assertTrue(uplink.keep_org(frame, CRED))
        sminos.forget_caches()
        self.assertEqual(sminos.stated_here(), {})
        got = sminos.decision(d)
        self.assertEqual((got.by, got.project.id), ("machine", sminos.machine_project_id(ORG, MACHINE)))

    def test_a_channel_entry_of_kind_machine_retires_no_machine(self):
        frame = {"t": "org", "projects": [{"id": DESK, "name": "elsewhere", "machine": "elsewhere", "kind": "machine",
                                           "retired": True}],
                 "machines": [{"name": MACHINE, "online": False}, {"name": "elsewhere", "online": False}]}
        self.assertTrue(uplink.keep_org(frame, CRED))
        sminos.forget_caches()
        self.assertFalse(sminos.machine_retired("elsewhere"))

    def test_a_record_whose_channels_is_no_list_holds_none(self):
        threads = sminos.threads_module()
        rows = [{"thread": "t1", "channels": "5c2a9e10"}, {"thread": "t2", "channels": 7}, {"thread": "t3",
                                                                                            "channels": [DESK]}]
        channels._HELD.clear()
        with mock.patch.object(threads, "all_threads", lambda: rows), \
                mock.patch.object(threads, "record_ended", lambda t: False):
            self.assertEqual(channels.held_channels(), frozenset([DESK]))
        channels._HELD.clear()


class HashNames(Machine):
    def test_an_exact_name_first_and_a_qualifier_from_the_right(self):
        p = self.project(PROJ, "release#42")
        self.assertEqual(sminos.find_project("release#42").id, p.id)
        self.assertEqual([x.id for x in sminos.project_tiers("release#42")], [PROJ])
        rc, out, err = self.cli("list", "release#42")
        self.assertEqual(rc, 0, err)
        self.project(TWIN1, "a#b")
        self.assertEqual(sminos.find_project("a#b#" + TWIN1[:8]).id, TWIN1, "the qualifier from the right")
        # An exact name that is also a qualified spelling of another: the exact name wins.
        self.project(TWIN2, "twin")
        exact = self.project("7d2b9c43-1f3e-4a6b-8c5d-9e0f1a2b3c4d", "twin#" + TWIN2[:8])
        self.assertEqual(sminos.find_project("twin#" + TWIN2[:8]).id, exact.id)
        self.assertEqual(sminos.find_project("twin#" + TWIN2).id, TWIN2, "the whole id reaches the other")


if __name__ == "__main__":
    unittest.main()
