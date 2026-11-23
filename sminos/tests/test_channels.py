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
import time
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

    def test_an_older_copys_hubless_registration_of_a_channel_the_org_lists_is_completed(self):
        """The frontier review's B2: an older copy registered a `.smns` that
        named a channel's id and no hub, rooted at its folder; the org's
        directory lists the channel, and adoption completes the
        registration as the directory registers a channel (no root, the
        enrollment's hub), so its log is opened. One that names a hub
        already is kept as it is."""
        root = os.path.join(self.home, "legacy")
        os.makedirs(root)
        sminos.register_if_absent(sminos.make_project(DESK, "desk-integration", "", root, None))
        sminos.register_if_absent(sminos.make_project(ROOM1, "room", "", root, HUB))
        sminos.forget_caches()
        self.assertNotIn(DESK, uplink.hub_projects(CRED), "as the older copy left it: no hub, never opened")
        frame = {"projects": [{"id": DESK, "name": "desk-integration", "kind": "hub", "retired": False},
                              {"id": ROOM1, "name": "room", "kind": "hub", "retired": False}],
                 "machines": [{"name": MACHINE, "online": False}]}
        self.assertTrue(uplink.keep_org(frame, CRED))
        sminos.forget_caches()
        c = sminos.known_project(DESK)
        self.assertEqual((c.root, c.hub), ("", HUB))
        self.assertIn(DESK, uplink.hub_projects(CRED), "its log is opened")
        self.assertEqual(sminos.known_project(ROOM1).root, root, "a registration naming a hub is kept as it is")

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
    def test_a_project_named_like_a_channels_id_is_tagged_by_its_id_and_init_refuses_such_a_name(self):
        """The frontier review's B4: a name of a channel's id's form is read
        as a channel at every door, so a tag naming the project by it would be
        refused. One that exists is tagged by its id; `project init` refuses
        such a name, nothing written."""
        p = self.project(PROJ, DESK)
        self.assertEqual(sminos.tag_project(p), PROJ)
        self.assertEqual(sminos.tag_project(self.project(TWIN1, "app")), "app", "any other name as today")
        repo = os.path.join(self.home, "repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        rc, out, err = self.cli("project", "init", "--name", ROOM1, cwd=repo)
        self.assertEqual(rc, 2, out + err)
        self.assertIn("a project name cannot have a channel id's form: %r" % ROOM1, err)
        self.assertFalse(os.path.exists(os.path.join(repo, ".smns")))
        rc, out, err = self.cli("project", "init", "--name", "app2", cwd=repo)
        self.assertEqual(rc, 0, out + err)

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
        rc, out, err = self.cli("list", "--project", DESK)
        self.assertEqual(rc, 4)
        self.assertIn("is a channel, not a project: sminos channel show", err)
        for verb in (("chat", "desk-integration"), ("list", "desk-integration")):
            rc, out, err = self.cli(*verb)   # a read of the channel's own (CH2's M4), before a project is asked for
            self.assertEqual(rc, 0, (verb, err))


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
        with mock.patch.object(sminos, "_session_project", lambda *a, **k: sminos.known_project(DESK)):
            sminos.forget_caches()   # a resolution that gave a channel all the same: the seat is in none
            self.assertIsNone(sminos.seat_project(seat))
            self.assertEqual([p.id for p in sminos.known_projects([seat])], [PROJ], "a seat's fallback holds none")

    def test_a_say_whose_destination_is_a_channel_is_refused(self):
        with mock.patch.object(sminos, "caller_project", lambda caller=None: sminos.known_project(DESK)):
            code, said = exits(sminos.main, ["say", "hello"])
        self.assertEqual(code, 1)
        self.assertIn("app is a channel, and no directory's project: say --in app to speak in it", said,
                      "a channel is spoken in only by naming it (CH2's M4)")
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

    def test_an_entry_an_older_copy_left_owing_a_channel_is_voided_before_its_join_is_undone(self):
        """The frontier review's B1: an older copy that took the channel for
        the session's project left a journal entry owing its `joined` (an
        interrupted return) or its `renamed` (an interrupted release) there,
        which this code's lifecycle never appends. The cleanup voids it, says
        so in daemon.log, and then undoes the join: the thread is a member of
        its own project again, and the channel's log gains nothing but the
        `retired` that undoes a live `joined`."""
        threads = sminos.threads_module()
        for n, op in ((3, "return"), (4, "release")):
            sid = "6c00000%d-0000-4000-8000-0000000000d%d" % (n, n)
            records.establish(sid, records.default_provenance())
            self.live(sid, self.root)
            self.tick()
            tid = threads.thread_of(sid)["thread"]
            self.assertEqual(threads.get(tid)["opened"], "human", op)
            # The older copy's `join desk-integration`: the override, the move out of the project, the joined.
            sminos.write_override(sid, DESK)
            sminos.log_append_batch(self.p, "%s/%s" % (MACHINE, sid), [{
                "kind": "retired", "session": sid, "by": "join", "reason": "moved", "project": DESK, "thread": tid}])
            self.older_join(sid)
            if op == "return":
                # It then ended the thread there and began its return, cut after the record's write.
                sminos.log_append(self.c, "%s/%s" % (MACHINE, sid), "retired", session=sid, by="", reason="ended",
                                  thread=tid)
                owed = {"kind": "joined", "session": sid, "alias": "worker", "name_source": "user",
                        "machine": MACHINE, "cwd": self.root, "worktree": "", "role": "", "seat": "", "by": "",
                        "thread": tid}
            else:
                # A /clear's release, begun where it read the session a member, cut the same way.
                owed = {"kind": "renamed", "session": sid, "alias": sid[:8], "name_source": "derived"}

            def cut(view, raw, owed=owed, op=op):
                raw["pending"] = {"id": "e%031d" % n, "op": op, "at": sminos.now(), "project": DESK,
                                  "events": [owed]}
                if op == "release":
                    raw["released"] = {"alias": "worker", "at": sminos.now()}
                return True
            self.assertTrue(threads._change(tid, cut))
            for _ in range(2):
                self.tick()
            self.assertIsNone(threads.get(tid).get("pending"), "%s: the entry owing the channel is voided" % op)
            with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
                said = f.read()
            self.assertIn("voiding: thread %s's %s entry, which owes %s to channel desk-integration: none of that "
                          "is replayed; its local steps are finished" % (
                              tid[:8], op, "joined" if op == "return" else "renamed"), said, op)
            want = [("joined", None), ("retired", "ended")] if op == "return" else \
                [("joined", None), ("retired", "moved")]
            self.assertEqual(self.kinds(DESK, sid), want, "%s: nothing of this code's but the undo" % op)
            self.assertEqual(sminos.threads_module().in_effect(sminos.own_events_of(self.p, sid))["kind"], "joined",
                             "%s: a member of its own project again" % op)
            self.assertIn(sid, [m.session for m in sminos.view_of(self.p).members], op)

    def thread_for(self, sid):
        records.establish(sid, records.default_provenance())
        self.live(sid, self.root)
        self.tick()
        return sminos.threads_module().thread_of(sid)["thread"]

    def older_entry(self, tid, entry, **fields):
        """An entry an older copy began addressed to the channel, cut after the record's write: `fields` the
        record's change, the entry's `was` and `unset` (as 1.51.0 and 1.52.0 keep them for an absorption)."""
        threads = sminos.threads_module()

        def cut(view, raw):
            keys = [*fields, "sessions"]
            entry.setdefault("was", {k: raw[k] for k in keys if k in raw})
            entry.setdefault("unset", [k for k in keys if k not in raw])
            raw.update(fields)
            if fields.get("current"):
                raw["sessions"] = [x for x in raw.get("sessions") or [] if x != fields["current"]] + [fields["current"]]
            raw["pending"] = {"id": "f%031d" % len(raw["sessions"]), "at": sminos.now(), "project": DESK, **entry}
            return True
        self.assertTrue(threads._change(tid, cut))
        sminos.forget_caches()
        return threads.get(tid)["pending"]

    def absorption(self, n, cut, prepare=None):
        """An absorption an older copy began in the channel's log: `a`'s thread taking `job`, whose own provisional
        record it absorbs, cut with the job current on the continuing record and the provisional one `cut` as
        "present", "reserved" (its mark on it), "deleted" (the claim committed) or "lost" (no longer absorbable)."""
        threads = sminos.threads_module()
        a, job = "6c00002%d-0000-4000-8000-0000000000f%d" % (n, n), "6c00003%d-0000-4000-8000-0000000000f%d" % (n, n)
        tid = self.thread_for(a)
        self.older_join(a)
        other = self.thread_for(job)
        self.assertNotEqual(other, tid)
        entry = self.older_entry(tid, {"op": "absorb", "other": other, "carry": [a, job], "events": [
            {"kind": "retired", "session": a, "by": "", "reason": "continued", "to": job, "thread": tid},
            {"kind": "joined", "session": job, "alias": "worker", "thread": tid}]}, current=job)
        mark = {"id": entry["id"], "op": threads.RESERVED, "by": tid, "at": sminos.now(), "project": DESK,
                "events": []}
        change = {"reserved": lambda view, raw: raw.update(pending=mark) or True,
                  "deleted": lambda view, raw: "delete",
                  "lost": lambda view, raw: raw.update(ended={"at": sminos.now(), "reason": "ended", "by": "",
                                                              "pid": None}) or True}.get(cut)
        if change:
            self.assertTrue(threads._change(other, change))
        if prepare:
            prepare(a, job)
        sminos.forget_caches()
        self.assertEqual(threads.get(tid)["current"], job, "cut: the job current on the continuing record")
        for _ in range(2):
            self.tick()
        self.assertNotIn(("retired", "continued"), self.kinds(DESK, a), cut)
        self.assertEqual(self.kinds(DESK, job), [], "%s: nothing of the job in the channel's log" % cut)
        return a, job, tid, other

    def test_a_legacy_absorption_into_a_channel_is_finished_locally_one_owner_kept(self):
        """M8's review: an absorption an older copy began in the channel's log, cut with the provisional record
        still there (reserved or not), is finished as any absorption is, its channel's effects voided: the
        provisional record held, merged and deleted, the continuing record the job's one owner."""
        threads = sminos.threads_module()
        for n, cut in ((5, "present"), (6, "reserved")):
            a, job, tid, other = self.absorption(n, cut)
            t = threads.get(tid)
            self.assertEqual((t["current"], t.get("pending")), (job, None), cut)
            self.assertIsNone(threads.get(other), "%s: the provisional record absorbed" % cut)
            self.assertEqual(threads.thread_of(job)["thread"], tid, cut)

    def test_a_legacy_absorption_carries_its_predecessors_reach(self):
        """M8's review, round 3: the hand-off's carry is the session's provenance and reach as well as the channel's
        cursor and override. Cut before it, the private predecessor's process gone and the job not yet inheriting,
        the finish carries the reach from the journal's pair before it clears the entry: the job ends private, as
        its predecessor, not with its own broader reach."""
        sessions = {}

        def prepare(a, job):
            # The older copy's `join desk-integration` moved `a` out of its project before the hand-off.
            sminos.write_override(a, DESK)
            sminos.log_append_batch(self.p, "%s/%s" % (MACHINE, a), [{
                "kind": "retired", "session": a, "by": "join", "reason": "moved", "project": DESK,
                "thread": sminos.threads_module().thread_of(a)["thread"]}])
            records.establish(a, records.default_provenance("launch"))
            records.set_policy(a, lambda access, shares: ("private", shares))
            self.procs[-2].kill()   # the predecessor's process gone
            self.procs[-2].wait()
            self.assertNotEqual(records.read(job).get("access"), "private", "the job's own, not yet inherited")
            sessions.update(a=a)
        a, job, tid, other = self.absorption(9, "present", prepare)
        rec = records.read(job)
        self.assertEqual(rec.get("access"), "private", "the predecessor's reach")
        self.assertIn(sessions["a"], rec.get("former") or [])
        self.assertEqual(sminos.threads_module().get(tid).get("pending"), None)

    def test_a_legacy_absorption_whose_predecessors_record_was_lost_carries_its_published_reach(self):
        """The frontier's second review (C2): a restore kept the private predecessor's publication and the journal,
        not its session record. The carry of an entry owed to a channel withholds only what concerns the channel
        (its cursor, its override, a publication there): the predecessor's reach is read from its publication in
        the log the entry names, read-only, as for a project's entry, so the job ends private, not listed."""
        sessions = {}

        def prepare(a, job):
            threads = sminos.threads_module()
            sminos.write_override(a, DESK)
            sminos.log_append_batch(self.p, "%s/%s" % (MACHINE, a), [{
                "kind": "retired", "session": a, "by": "join", "reason": "moved", "project": DESK,
                "thread": threads.thread_of(a)["thread"]}])
            # The older copy's `joined` of the private session into the channel, under its stream: it publishes.
            stream = "%s/%s~%s" % (MACHINE, a, sminos.audience_digest(["member-1"]))
            sminos.keep_stream(self.c, stream, ["member-1"])
            sminos.log_append(self.c, stream, "joined", session=a, alias="worker", name_source="user",
                              machine=MACHINE, cwd=self.root, worktree="", role="", seat="", by="join",
                              origin={"kind": "terminal"})
            os.unlink(records.record_path(a))   # the restore kept no record of it
            self.procs[-2].kill()
            self.procs[-2].wait()
            self.assertNotEqual((records.read(job) or {}).get("access"), "private", "the job's own, not inherited")
            sessions.update(a=a)
        a, job, tid, other = self.absorption(4, "present", prepare)
        rec = records.read(job)
        self.assertEqual(rec.get("access"), "private", "the predecessor's reach, from its publication")
        self.assertIn(sessions["a"], rec.get("former") or [])
        self.assertEqual(sminos.threads_module().get(tid).get("pending"), None)
        self.assertEqual([e["kind"] for e in self.log_events(DESK) if e.get("session") == job], [],
                         "nothing published in the channel's log")

    def test_a_legacy_absorption_owed_an_unregistered_channel_reads_its_log_by_its_id(self):
        """The holder's reading, D1: the channel's registration cannot be read (known_project None) and the
        predecessor's record is gone. The carry reads the channel's log by its id's path, registering nothing, and
        finds the predecessor's publication there: never called complete with no evidence read."""
        sessions = {}

        def prepare(a, job):
            threads = sminos.threads_module()
            sminos.write_override(a, DESK)
            sminos.log_append_batch(self.p, "%s/%s" % (MACHINE, a), [{
                "kind": "retired", "session": a, "by": "join", "reason": "moved", "project": DESK,
                "thread": threads.thread_of(a)["thread"]}])
            stream = "%s/%s~%s" % (MACHINE, a, sminos.audience_digest(["member-1"]))
            sminos.keep_stream(self.c, stream, ["member-1"])
            sminos.log_append(self.c, stream, "joined", session=a, alias="worker", name_source="user",
                              machine=MACHINE, cwd=self.root, worktree="", role="", seat="", by="join",
                              origin={"kind": "terminal"})
            os.unlink(records.record_path(a))
            self.procs[-2].kill()
            self.procs[-2].wait()
            with open(os.path.join(self.c.home, "project.json"), "w") as f:
                f.write("not a registration")
            sminos.forget_caches()
            self.assertIsNone(sminos.known_project(DESK))
            sessions.update(a=a, job=job)
        threads = sminos.threads_module()
        a, job = "6c000023-0000-4000-8000-0000000000f3", "6c000033-0000-4000-8000-0000000000f3"
        tid = self.thread_for(a)
        self.older_join(a)
        other = self.thread_for(job)
        self.older_entry(tid, {"op": "absorb", "other": other, "carry": [a, job], "events": [
            {"kind": "retired", "session": a, "by": "", "reason": "continued", "to": job, "thread": tid},
            {"kind": "joined", "session": job, "alias": "worker", "thread": tid}]}, current=job)
        prepare(a, job)
        with contextlib.redirect_stderr(io.StringIO()):
            sminos.finish_thread(tid)   # an explicit finisher: no reconciliation reads an unregistered channel
        rec = records.read(job)
        self.assertEqual(rec.get("access"), "private", "the predecessor's reach, from the channel's log by its path")
        self.assertIn(a, rec.get("former") or [])
        self.assertIsNone(threads.get(tid).get("pending"))
        with open(os.path.join(self.c.home, "project.json")) as f:
            self.assertEqual(f.read(), "not a registration", "nothing registered")

    def test_a_legacy_absorption_cut_after_its_deletion_keeps_its_claim(self):
        """M8's review, round 2: cut after the provisional record's deletion, the claim is committed: kept, not
        rolled back, the continuing record the job's one owner and the entry cleared."""
        threads = sminos.threads_module()
        a, job, tid, other = self.absorption(7, "deleted")
        t = threads.get(tid)
        self.assertEqual((t["current"], t.get("pending")), (job, None))
        self.assertIn(job, t["sessions"])
        self.assertIsNone(threads.get(other))
        self.assertEqual(threads.thread_of(job)["thread"], tid, "the job has its owner")

    def test_a_legacy_absorption_whose_record_is_no_longer_absorbable_is_undone(self):
        """A claim never committed (the provisional record changed before it was held) is undone as any lost
        hand-off's: the continuing record has its session again, the other record keeps the job."""
        threads = sminos.threads_module()
        a, job, tid, other = self.absorption(8, "lost")
        t, o = threads.get(tid), threads.get(other)
        self.assertEqual((t["current"], t.get("pending")), (a, None))
        self.assertNotIn(job, t["sessions"])
        self.assertEqual(o["current"], job)
        self.assertEqual(threads.thread_of(a)["thread"], tid)

    def test_a_legacy_purge_into_a_channel_stops_its_process_and_keeps_its_end(self):
        """M8's review, round 2: an older copy's purge owing its `retired` to the channel's log, its process still
        live: the finisher voids the retirement and stops the process the end recorded, as every purge does; the
        ended record, the one statement of the end left once its retirement is voided, is kept, so the session
        is not adopted again as a new thread."""
        threads = sminos.threads_module()
        b = "6c000044-0000-4000-8000-0000000000a4"
        tid = self.thread_for(b)
        proc = self.procs[-1]
        # The older copy's `join desk-integration` (the override, the move out of the project, the joined), then
        # its purge, cut after the record's write.
        sminos.write_override(b, DESK)
        sminos.log_append_batch(self.p, "%s/%s" % (MACHINE, b), [{
            "kind": "retired", "session": b, "by": "join", "reason": "moved", "project": DESK, "thread": tid}])
        self.older_join(b)
        self.older_entry(tid, {"op": "end", "last": "purge", "settle": b, "events": [
            {"kind": "retired", "session": b, "by": "", "reason": "ended", "thread": tid}]},
            ended={"at": sminos.now(), "reason": "ended", "by": "", "pid": proc.pid})
        stopped = []

        def stop(record, entry):   # as a stop that is slow or fails leaves it: the process still runs
            stopped.append((record["thread"], entry["last"], threads.get(tid) is not None))
        with mock.patch.object(sminos, "purge_stop", side_effect=stop):
            for _ in range(2):
                self.tick()
        self.assertEqual(stopped, [(tid, "purge", True)], "stopped once, while its record still named it")
        t = threads.get(tid)
        self.assertEqual((t["current"], t.get("pending"), threads.record_ended(t)), (b, None, True),
                         "the ended record kept: the one statement left that the session ended")
        self.assertEqual(threads.thread_of(b)["thread"], tid, "its session not adopted again as a new thread")
        self.assertFalse(threads.member(sminos.own_events_of(self.p, b)), "nor joined to its project again")
        self.assertNotIn(("retired", "ended"), self.kinds(DESK, b))

    def test_ordinary_replay_appends_no_retirement_into_a_channel(self):
        """M8's review: a project's own pass (the daemon ticks projects before channels; join on sight finishes an
        open entry) meets an older copy's hand-off owing `retired` `continued` and `joined` in the channel's log,
        and an end owing `retired` `ended` there: none of it is appended, and the cleanup still undoes the live
        older `joined` with its `retired` `moved`."""
        threads = sminos.threads_module()
        a, job = "6c000041-0000-4000-8000-0000000000a1", "6c000042-0000-4000-8000-0000000000a2"
        tid = self.thread_for(a)
        self.older_join(a)
        self.live(job, self.root)
        self.older_entry(tid, {"op": "advance", "events": [
            {"kind": "retired", "session": a, "by": "", "reason": "continued", "to": job, "thread": tid},
            {"kind": "joined", "session": job, "alias": "worker", "thread": tid}]}, current=job)
        sminos.forget_caches()
        sminos.finish_thread(tid, project=self.p)   # a project's replay, as join on sight makes it
        self.assertEqual(self.kinds(DESK, a), [("joined", None)], "the replay appended nothing to the channel")
        self.assertEqual(threads.get(tid).get("pending"), None)
        self.tick()
        self.assertEqual(self.kinds(DESK, a), [("joined", None), ("retired", "moved")], "the cleanup's undo")
        self.assertEqual(self.kinds(DESK, job), [])
        b = "6c000043-0000-4000-8000-0000000000a3"
        tid = self.thread_for(b)
        self.procs[-1].kill()   # its terminal closed: nothing holds it
        self.procs[-1].wait()
        self.older_join(b)
        self.older_entry(tid, {"op": "end", "last": "aside", "events": [
            {"kind": "retired", "session": b, "by": "", "reason": "ended", "thread": tid}]},
            ended={"at": sminos.now(), "reason": "ended", "by": "", "pid": None})
        for _ in range(2):
            self.tick()
        self.assertEqual(self.kinds(DESK, b), [("joined", None)], "an end's retirement is not appended there either")
        self.assertIsNone((threads.get(tid) or {}).get("pending"))
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
            written = [line for line in f if line.split(" ", 1)[1].startswith("voiding: thread %s's end entry" % tid[:8])]
        self.assertEqual(len(written), 1, "said once")

    def test_a_resumes_roster_gives_no_tag_through_a_channel(self):
        """The frontier review's B3: a message an older copy sent to a peer
        it read as a member of the channel names the channel as the peer's
        project, and no thread. The roster a resume reads gives no tag into
        the channel: the peer is in no project known here while its legacy
        `joined` stands, and in its own project once this code's `retired`
        `moved` names it. (An entry that names a thread is found by its
        thread from CH2's M9 on: test_a_peer_met_in_a_channel_...)"""
        sid, peer = "6c000010-0000-4000-8000-0000000000e1", "6c000011-0000-4000-8000-0000000000e2"
        self.live(sid, self.root)
        self.tick()
        self.older_join(peer)
        sminos.log_append_batch(self.p, "%s/%s" % (MACHINE, sid), [{
            "kind": "say", "text": "@worker hello", "copy": "c-1",
            "to": [{"session": peer, "project": DESK, "alias": "worker"}]}])
        sminos.forget_caches()
        said = sminos.roster_text(sid, self.root)
        self.assertNotIn("@desk-integration/", said)
        self.assertIn("worker [6c000011], in no project known here", said)
        sminos.log_append_batch(self.c, "%s/%s" % (MACHINE, peer), [{
            "kind": "retired", "session": peer, "by": "", "reason": "moved", "project": PROJ}])
        sminos.log_append(self.p, "%s/%s" % (MACHINE, peer), "joined", session=peer, alias="worker",
                          name_source="user", machine=MACHINE, cwd=self.root, worktree="", role="", seat="", by="")
        sminos.forget_caches()
        said = sminos.roster_text(sid, self.root)
        self.assertNotIn("@desk-integration/", said)
        self.assertIn("@worker#6c000011  worker [6c000011], app on %s" % MACHINE, said, "the sender is a worker too")

    def test_an_import_into_a_channel_delivers_nothing(self):
        calls = []
        with mock.patch.object(sminos, "view_of", lambda *a, **k: calls.append(a) or None), \
                mock.patch.object(daemon, "deliver_owed", lambda *a, **k: calls.append(a) or (0, [])):
            hublog.HubLog(self.c, CRED).deliver()
        self.assertEqual(calls, [])


class Roster(Machine):
    """The exchanges a compaction or a resume lists, through a channel (CH2's M9): a peer met in a channel is its
    thread, found now by its stamp wherever its session went; the reader's channels are its thread's statements,
    whichever of its sessions wrote them; read-only, and inside the roster's one deadline."""

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.home, "app")
        os.makedirs(self.root)
        with open(os.path.join(self.root, ".smns"), "w") as f:
            json.dump({"project": PROJ, "name": "app", "hub": {"org": ORG}}, f)
        self.p = self.project(PROJ, "app", self.root)
        self.c = self.channel(DESK, "desk-integration")

    def live(self, sid, cwd, name="worker"):
        return ChannelReconcile.live(self, sid, cwd, name)

    def tick(self):
        return ChannelReconcile.tick(self)

    def joined(self, sid, alias, thread, p=None, machine="beta"):
        sminos.log_append(p or self.p, "%s/%s" % (machine, sid), "joined", session=sid, alias=alias,
                          name_source="user", machine=machine, cwd="/d", worktree="", role="", seat="", by="",
                          thread=thread)

    def retired(self, sid, reason, p=None, machine="beta", **fields):
        sminos.log_append(p or self.p, "%s/%s" % (machine, sid), "retired", session=sid, by="", reason=reason,
                          **fields)

    def reader(self, thread="7e000000-0000-4000-8000-0000000000aa", sid="7e000001-0000-4000-8000-0000000000a1"):
        """A session of app whose thread's statement names the channel, written as its own writer writes them:
        its session. A reader in a channel, so a tag it reads names the project, its own too."""
        self.joined(sid, "reader", thread, machine=MACHINE)
        sminos.log_append(self.p, "%s/%s" % (MACHINE, sid), "channels", session=sid, thread=thread, channels=[DESK],
                          op="add")
        return sid, thread

    def said(self, sid, thread, alias, to, c=None, text="hi"):
        """A member's message in the channel's log from another machine's session, naming each (session, thread)
        of `to`."""
        sminos.log_append(c or self.c, "beta/%s" % sid, "say", **{
            "from": alias, "thread": thread, "text": text,
            "to": [{"session": s, "alias": "reader", "thread": t} for s, t in to]})
        sminos.forget_caches()

    def roster(self, sid):
        sminos.forget_caches()
        return sminos.roster_text(sid, self.root)

    def stated(self, sid):
        """The live session `sid` of app, made a thread by a tick, with a statement of its own naming the channel,
        as `channel add` leaves one: its thread."""
        self.live(sid, self.root)
        self.tick()
        tid = sminos.threads_module().stamp(sid)
        self.assertTrue(tid)
        sminos.log_append(self.p, "%s/%s" % (MACHINE, sid), "channels", session=sid, thread=tid, channels=[DESK],
                          op="add")
        sminos.forget_caches()
        return tid

    def test_a_peer_met_in_a_channel_that_no_project_here_holds_is_named_as_its_message_named_it(self):
        """CH2's M9: a peer met only in a channel, on a machine whose projects this one does not hold, is listed
        by the name its message gave it, with no tag; and one whose session's row here is another thread's is not
        taken for it."""
        sid, far, reused = ("6c00002%d-0000-4000-8000-0000000000f%d" % (n, n) for n in (1, 2, 3))
        tid = self.stated(sid)
        self.live(reused, self.root, name="reused")
        self.tick()
        self.assertNotEqual(sminos.threads_module().stamp(reused), "")
        for writer, thread, alias, text in (("beta/%s" % far, "6c0000a2-0000-4000-8000-0000000000a2", "far-peer", "a"),
                                            ("%s/%s" % (MACHINE, reused), "6c0000a3-0000-4000-8000-0000000000a3",
                                             "old-name", "b")):
            sminos.log_append(self.c, writer, "say", **{"from": alias, "thread": thread, "text": text,
                                                         "to": [{"session": sid, "alias": "worker", "thread": tid}]})
        sminos.log_append(self.c, "beta/%s" % far, "say", **{"from": "far-peer", "thread": "x", "text": "c",
                                                              "to": "*"})
        sminos.forget_caches()
        said = sminos.roster_text(sid, self.root)
        self.assertIn("far-peer [6c000022], met in a channel: no project known here holds its thread now, no tag"
                      " reaches it", said)
        self.assertIn("old-name [6c000023], met in a channel: no project known here holds its thread now", said,
                      "a session whose row here is another thread's is not the peer")
        self.assertNotIn("reused [", said)
        self.assertNotIn("desk-integration", said)

    def test_a_session_whose_thread_made_no_statement_reads_no_channel(self):
        """B11's cost: a session in no channel reads no channel's log and no registration of one."""
        sid = "6c000030-0000-4000-8000-0000000000f4"
        self.live(sid, self.root)
        self.tick()
        sminos.log_append(self.c, "beta/6c000031-0000-4000-8000-0000000000f5", "say",
                          **{"from": "far-peer", "thread": "t", "text": "a",
                             "to": [{"session": sid, "alias": "worker",
                                     "thread": sminos.threads_module().stamp(sid)}]})
        sminos.forget_caches()
        read, real = [], sminos.log_read
        with mock.patch.object(sminos, "log_read", lambda p, *a, **k: read.append(p.id) or real(p, *a, **k)), \
                mock.patch.object(sminos, "known_channels", side_effect=AssertionError("no registration read")):
            self.assertEqual(sminos.roster_text(sid, self.root), "")
        self.assertNotIn(DESK, read)

    def test_a_peer_refilled_in_its_project_is_its_new_session_and_live(self):
        """A refill retires the session it replaces as `replaced`, naming no successor: the thread is found by its
        stamp, never through the session its message named."""
        rsid, rt = self.reader()
        old, new, pt = ("7e0000b%d-0000-4000-8000-0000000000b%d" % (n, n) for n in (1, 2, 9))
        self.joined(old, "peer-a", pt)
        self.said(old, pt, "peer-a", [(rsid, rt)])
        self.retired(old, "replaced")
        self.joined(new, "peer-a", pt)
        said = self.roster(rsid)
        self.assertIn("@app/peer-a  peer-a [%s], app on beta" % new[:8], said)
        self.assertNotIn("ended", said)

    def test_a_peer_handed_off_whose_old_session_another_thread_reuses_is_the_session_it_continues_in(self):
        rsid, rt = self.reader()
        old, new, pt, other = ("7e0000c%d-0000-4000-8000-0000000000c%d" % (n, n) for n in (1, 2, 3, 4))
        self.joined(old, "peer-h", pt)
        self.said(old, pt, "peer-h", [(rsid, rt)])
        self.retired(old, "continued", to=new)
        self.joined(new, "peer-h", pt)
        self.joined(old, "reuser", other)   # the old session runs again as another thread
        said = self.roster(rsid)
        self.assertIn("@app/peer-h  peer-h [%s], app on beta" % new[:8], said)
        self.assertNotIn("reuser", said)

    def test_a_peer_whose_move_reads_destination_first_is_tagged_in_the_project_it_moved_to(self):
        rsid, rt = self.reader()
        sid, pt = "7e0000d1-0000-4000-8000-0000000000d1", "7e0000d9-0000-4000-8000-0000000000d9"
        dest = self.project("9f2e3d4c-5b6a-4789-8abc-def012345678", "elsewhere")
        self.joined(sid, "peer-m", pt)
        self.said(sid, pt, "peer-m", [(rsid, rt)])
        time.sleep(0.002)
        self.joined(sid, "peer-m", pt, p=dest)   # its retirement in app not imported yet
        said = self.roster(rsid)
        self.assertIn("@elsewhere/peer-m  peer-m [%s], elsewhere on beta" % sid[:8], said)
        # Round 3's A: written in app's log too, whose row of it is the one the move left: one peer, its tag now.
        sminos.log_append(self.p, "%s/%s" % (MACHINE, rsid), "say", **{
            "from": "reader", "text": "hi", "to": [{"session": sid, "alias": "peer-m"}]})
        said = self.roster(rsid)
        self.assertEqual(said.count("peer-m [%s]" % sid[:8]), 1, said)
        self.assertIn("@elsewhere/peer-m  peer-m [%s], elsewhere on beta" % sid[:8], said)
        self.assertNotIn("@app/peer-m", said)
        self.assertIn("last: you wrote it", said, "the project's exchange, the latest, is the row's")

    def test_one_thread_met_under_two_sessions_in_two_channels_is_one_row_named_as_it_was_last(self):
        rsid, rt = self.reader()
        lobby = self.channel("0123abcd-4567-8abc-a123-456789abcdef", "lobby")
        sminos.log_append(self.p, "%s/%s" % (MACHINE, rsid), "channels", session=rsid, thread=rt,
                          channels=[DESK, lobby.id], op="add")
        a, b, pt = ("7e0000e%d-0000-4000-8000-0000000000e%d" % (n, n) for n in (1, 2, 9))
        self.said(a, pt, "first-name", [(rsid, rt)])
        time.sleep(0.002)
        self.said(b, pt, "later-name", [(rsid, rt)], c=lobby)
        said = self.roster(rsid)
        self.assertEqual(said.count("met in a channel"), 1, said)
        self.assertIn("later-name [%s], met in a channel" % b[:8], said)
        self.assertNotIn("first-name", said)

    def test_a_reader_refilled_after_its_old_session_named_the_channel_still_reads_it(self):
        """Leave the seat, a refill in the same project, a resume: the statement naming the channel is the old
        occupant's, of the same thread, and the new session continues none of it."""
        old, new, rt = ("7e0000f%d-0000-4000-8000-0000000000f%d" % (n, n) for n in (1, 2, 9))
        self.reader(rt, old)
        self.retired(old, "replaced", machine=MACHINE)
        self.joined(new, "reader", rt, machine=MACHINE)
        peer, pt = "7e0000f3-0000-4000-8000-0000000000f3", "7e0000f8-0000-4000-8000-0000000000f8"
        self.joined(peer, "peer-r", pt)
        self.said(peer, pt, "peer-r", [(old, rt)])
        self.assertIn("@app/peer-r  peer-r [%s], app on beta" % peer[:8], self.roster(new))

    def test_an_ended_peer_met_in_a_channel_is_named_as_its_message_named_it(self):
        rsid, rt = self.reader()
        sid, pt = "7e000101-0000-4000-8000-000000000101", "7e000109-0000-4000-8000-000000000109"
        self.joined(sid, "the-name-then", pt)
        self.said(sid, pt, "the-name-then", [(rsid, rt)])
        self.joined(sid, "renamed-since", pt)
        self.retired(sid, "retire")
        said = self.roster(rsid)
        self.assertIn("the-name-then [%s], app on beta: its session ended, no tag reaches it" % sid[:8], said)
        self.assertNotIn("renamed-since", said)

    def clock(self, at=0.0):
        """The roster's clock made a test's: `moved()` puts it past every deadline the roster read from it."""
        now = [at]
        patch = mock.patch.object(sminos, "roster_clock", lambda: now[0])
        patch.start()
        self.addCleanup(patch.stop)
        return lambda: now.__setitem__(0, now[0] + 2 * sminos.ROSTER_BUDGET)

    def moved_peer(self, rsid, rt):
        """A project peer of app the reader wrote, and a peer met in the channel whose row moved to elsewhere,
        its retirement in app not imported yet: its app row is stale. The peers' sessions."""
        ordinary, sid, pt = ("7e0002%d1-0000-4000-8000-0000000002%d1" % (n, n) for n in (0, 1, 9))
        self.joined(ordinary, "in-app", "7e000209-0000-4000-8000-000000000209")
        sminos.log_append(self.p, "%s/%s" % (MACHINE, rsid), "say", **{
            "from": "reader", "text": "hi", "to": [{"session": ordinary, "alias": "in-app"}]})
        dest = self.project("9f2e3d4c-5b6a-4789-8abc-def012345678", "elsewhere")
        self.joined(sid, "channel-peer", pt)
        self.said(sid, pt, "channel-peer", [(rsid, rt)])
        time.sleep(0.002)
        self.joined(sid, "channel-peer", pt, p=dest)
        return ordinary, sid

    def test_a_deadline_crossed_in_the_thread_scan_names_the_channel_peer_untagged_and_keeps_the_project_peer(self):
        """Round 2's finding 1: a thread's row is never chosen from the projects read before the deadline, where
        the one it moved to was not; a project's peer, looked for first, keeps its tag."""
        rsid, rt = self.reader()
        ordinary, sid = self.moved_peer(rsid, rt)
        whole = self.roster(rsid)
        self.assertIn("@elsewhere/channel-peer  channel-peer [%s]" % sid[:8], whole)
        self.assertIn("@app/in-app  in-app [%s]" % ordinary[:8], whole)
        move = self.clock()
        real_index, real_known, scanning = sminos._roster_thread_index, sminos.known_project, []

        def known(name, *a, **k):
            p = real_known(name, *a, **k)
            if scanning and name == PROJ:
                move()   # app read; elsewhere, after it in the scan's order, is not begun
            return p
        with mock.patch.object(sminos, "_roster_thread_index", lambda *a, **k: scanning.append(1) or real_index(*a, **k)), \
                mock.patch.object(sminos, "known_project", known):
            said = self.roster(rsid)
        self.assertTrue(scanning)
        self.assertIn("@app/in-app  in-app [%s]" % ordinary[:8], said)
        self.assertIn("channel-peer [%s], met in a channel: where its thread is now was not read in time, no tag"
                      " given" % sid[:8], said)
        self.assertNotIn("@channel-peer", said)
        self.assertNotIn("@app/channel-peer", said)

    def test_past_the_deadline_no_channel_is_looked_for_and_no_project_read_for_a_thread(self):
        """Round 2's finding 2: no unit of work begins past the deadline: a statement log's replay, the
        registrations, a channel's log, a project of the thread index."""
        rsid, rt = self.reader()
        self.said("7e000202-0000-4000-8000-000000000202", "7e000208-0000-4000-8000-000000000208", "far",
                  [(rsid, rt)])
        rows, context = sminos._roster_exchanges(rsid, [self.p])
        self.assertTrue(context["stated"])
        move = self.clock()
        move()
        with mock.patch.object(sminos, "known_channels", side_effect=AssertionError("no channel looked for")), \
                mock.patch.object(sminos, "_roster_statements", side_effect=AssertionError("no log replayed")):
            self.assertTrue(sminos._roster_channel_exchanges(rows, context, until=0.0),
                            "a replay not finished qualifies tags")
        self.assertEqual(rows, {})
        index = {"read": set(), "rows": {}, "complete": False}
        self.assertEqual(sminos._roster_thread_row("7e000208-0000-4000-8000-000000000208", sminos.seats(), index,
                                                   until=0.0), (None, False))
        self.assertEqual(index["read"], set(), "no project read past the deadline")

    def test_past_the_deadline_on_a_channels_read_it_is_not_scanned_and_the_next_not_read(self):
        rsid, rt = self.reader()
        lobby = self.channel("0123abcd-4567-8abc-a123-456789abcdef", "lobby")
        sminos.log_append(self.p, "%s/%s" % (MACHINE, rsid), "channels", session=rsid, thread=rt,
                          channels=[DESK, lobby.id], op="add")
        self.said("7e000301-0000-4000-8000-000000000301", "7e000309-0000-4000-8000-000000000309", "at-desk",
                  [(rsid, rt)])
        self.said("7e000302-0000-4000-8000-000000000302", "7e000308-0000-4000-8000-000000000308", "at-lobby",
                  [(rsid, rt)], c=lobby)
        move, read, real = self.clock(), [], sminos.log_read

        def log_read(p, *a, **k):
            if sminos.is_channel_id(p.id):
                read.append(p.id)
                move()
            return real(p, *a, **k)
        rows, context = sminos._roster_exchanges(rsid, [self.p])
        with mock.patch.object(sminos, "log_read", log_read):
            sminos._roster_channel_exchanges(rows, context, until=1.0)
        self.assertEqual(len(read), 1, read)
        self.assertEqual(rows, {}, "round 3's B: a log whose read returned past the deadline is not scanned")

    def test_a_deadline_crossed_on_the_thread_scans_last_read_builds_no_member_and_gives_no_tag(self):
        """Round 3's B: every project read, but the last read returned past the deadline: no member is built
        (it reads the engine's state), and the channel peer is named untagged as one not read in time."""
        rsid, rt = self.reader()
        ordinary, sid = self.moved_peer(rsid, rt)
        names = sorted(n for n in os.listdir(sminos.projects_root())
                       if not n.startswith(".") and not sminos.is_channel_id(n))
        move = self.clock()
        real_index, real_known, scanning, members = sminos._roster_thread_index, sminos.known_project, [], []

        def known(name, *a, **k):
            if scanning and name == names[-1]:
                move()
            return real_known(name, *a, **k)
        real_member = sminos._member
        with mock.patch.object(sminos, "_roster_thread_index", lambda *a, **k: scanning.append(1) or real_index(*a, **k)), \
                mock.patch.object(sminos, "known_project", known), \
                mock.patch.object(sminos, "_member", lambda *a, **k: members.append(scanning[:]) or real_member(*a, **k)):
            said = self.roster(rsid)
        self.assertEqual(set(map(len, members)), {0}, "no member built once the scan began")
        self.assertIn("@app/in-app  in-app [%s]" % ordinary[:8], said)
        self.assertIn("channel-peer [%s], met in a channel: where its thread is now was not read in time, no tag"
                      " given" % sid[:8], said)
        self.assertNotIn("@elsewhere/channel-peer", said)

    def test_a_peer_met_first_in_its_project_and_last_in_a_channel_that_ended_is_named_as_the_channel_named_it(self):
        """Round 3's C: the name and the way met are the latest exchange's, whichever key found the peer."""
        rsid, rt = self.reader()
        sid, pt = "7e000701-0000-4000-8000-000000000701", "7e000709-0000-4000-8000-000000000709"
        self.joined(sid, "first-name", pt)
        sminos.log_append(self.p, "%s/%s" % (MACHINE, rsid), "say", **{
            "from": "reader", "text": "hi", "to": [{"session": sid, "alias": "first-name"}]})
        time.sleep(0.002)
        self.said(sid, pt, "chan-name", [(rsid, rt)])
        self.joined(sid, "renamed-since", pt)
        self.retired(sid, "retire")
        said = self.roster(rsid)
        self.assertIn("chan-name [%s], app on beta: its session ended, no tag reaches it" % sid[:8], said)
        self.assertNotIn("renamed-since", said)
        self.assertEqual(said.count("[%s]" % sid[:8]), 1, said)

    def test_a_reader_in_no_channel_reads_no_thread_record_for_its_project_roster(self):
        """Round 2's finding 3: whether the reader holds a channel is read from its project's statements, already
        read; a reader with none never asks the thread records, and its project peer's tag is the bare one."""
        rsid, peer = "7e000401-0000-4000-8000-000000000401", "7e000402-0000-4000-8000-000000000402"
        self.joined(rsid, "reader", "7e000409-0000-4000-8000-000000000409", machine=MACHINE)
        self.joined(peer, "in-app", "7e000408-0000-4000-8000-000000000408")
        sminos.log_append(self.p, "%s/%s" % (MACHINE, rsid), "say", **{
            "from": "reader", "text": "hi", "to": [{"session": peer, "alias": "in-app"}]})
        threads, read, real = sminos.threads_module(), [], sminos.log_read
        with mock.patch.object(sminos.channels_module(), "channels_of", side_effect=AssertionError("channels_of")), \
                mock.patch.object(threads, "current_record", side_effect=AssertionError("a thread record read")), \
                mock.patch.object(sminos, "known_channels", side_effect=AssertionError("a registration read")), \
                mock.patch.object(sminos, "log_read", lambda p, *a, **k: read.append(p.id) or real(p, *a, **k)):
            said = self.roster(rsid)
        self.assertIn("@in-app  in-app [%s], app on beta" % peer[:8], said)
        self.assertNotIn(DESK, read)

    def test_a_reader_whose_statements_leave_every_channel_is_tagged_as_in_none(self):
        rsid, rt = self.reader()
        time.sleep(0.002)
        sminos.log_append(self.p, "%s/%s" % (MACHINE, rsid), "channels", session=rsid, thread=rt, channels=[],
                          op="remove")
        peer = "7e000501-0000-4000-8000-000000000501"
        self.joined(peer, "in-app", "7e000509-0000-4000-8000-000000000509")
        sminos.log_append(self.p, "%s/%s" % (MACHINE, rsid), "say", **{
            "from": "reader", "text": "hi", "to": [{"session": peer, "alias": "in-app"}]})
        self.assertIn("@in-app  in-app [%s]" % peer[:8], self.roster(rsid))

    def test_a_peer_whose_machine_the_org_retired_reads_as_ended_by_its_name(self):
        """Round 2's finding 4: a `joined` on a machine the org retired is no live row (has_ended, as the resolver
        reads it): the peer is ended, named as its message named it, and given no tag."""
        rsid, rt = self.reader()
        sid, pt = "7e000601-0000-4000-8000-000000000601", "7e000609-0000-4000-8000-000000000609"
        self.joined(sid, "row-name", pt)
        self.said(sid, pt, "said-name", [(rsid, rt)])
        self.assertIn("@app/row-name  row-name [%s]" % sid[:8], self.roster(rsid))
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "org.json"), {
            "projects": [], "machines": [{"name": "beta", "retired": True}], "at": sminos.now(ms=True)})
        said = self.roster(rsid)
        self.assertIn("said-name [%s], app on beta: its session ended, no tag reaches it" % sid[:8], said)
        self.assertNotIn("@app/row-name", said)


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
        self.assertEqual(rc, 4, err)
        self.assertIn("one message, one log: the tags name desk-integration; @worker resolves outside "
                      "desk-integration", err, "a bare name, beside the channel, named as the tag it is (CH2's M4)")
        self.assertEqual(self.log_events(PROJ) + self.log_events(DESK), [],
                         "the refusal names the bare tag's log with no member looked up: nothing reconciled, nothing "
                         "recorded")

    def test_a_channel_qualifier_by_its_whole_id_unquoted_is_refused_too(self):
        """The holder's reading, D3: the qualifier is decided by the name resolver, whole: `log_label`'s
        `<name>#<whole id>` spelling (what it prints when eight digits name no one log) is refused as the short one."""
        sid = "6c00000c-0000-4000-8000-0000000000cc"
        self.live(sid, self.root)
        q = "desk-integration#%s" % DESK
        for argv in (("say", "@%s/worker hello" % q), ("say", "--here", "@%s/worker hello" % q)):
            rc, out, err = self.cli(*argv, cwd=self.root)
            self.assertEqual(rc, 1, (argv, err))
            self.assertIn("@%s/worker opens no tag (a tag's qualifier takes no #)" % q, err, argv)
        rc, out, err = self.cli("say", "@nobody#1234abcd/worker: not a log, just words", cwd=self.root)
        self.assertEqual(rc, 0, err)
        self.assertEqual([e.get("text") for e in self.log_events(PROJ) if e["kind"] in ("human", "say")],
                         ["@nobody#1234abcd/worker: not a log, just words"], "only the words, recorded as before")

    def test_a_shortened_channel_qualifier_unquoted_is_refused_before_anything_is_recorded(self):
        """`@desk-integration#5c2a9e10/worker`, unquoted: the tag parser reads no `#` in a qualifier, so it opens no
        tag; it is refused as the quoted form is, wherever the leading run meets it, and nothing is recorded."""
        sid = "6c00000a-0000-4000-8000-0000000000ca"
        self.live(sid, self.root)
        q = "desk-integration#%s" % DESK[:8]
        for text in ("@%s/worker hello" % q, "@worker @%s/worker hello" % q, "@%s/worker: hello" % q):
            rc, out, err = self.cli("say", text, cwd=self.root)
            self.assertEqual(rc, 1, (text, err))
            self.assertIn("@%s/worker opens no tag (a tag's qualifier takes no #)" % q, err, text)
        self.assertEqual(self.log_events(PROJ), [], "nothing recorded")

    def test_a_shortened_channel_qualifier_is_refused_under_a_selector_too(self):
        """A selector names its recipients itself, and a text opening with the unquoted shortened channel tag would
        be broadcast as words: refused before the selector is read, nothing appended anywhere."""
        sid = "6c00000b-0000-4000-8000-0000000000cb"
        self.live(sid, self.root)
        sminos.forget_caches()
        self.assertTrue(sminos.members(self.p), "the selector has recipients")
        logs = os.path.join(os.environ["SMINOS_HOME"], "projects")

        def sizes():
            return sorted((os.path.join(d, f), os.path.getsize(os.path.join(d, f))) for d, _, fs in os.walk(logs)
                          for f in fs if f.endswith(".jsonl") and os.sep + "log" in d)
        before = sizes()
        q = "desk-integration#%s" % DESK[:8]
        for argv in (("say", "--here", "@%s/worker hello" % q), ("say", "--project", "app", "@%s/worker hi" % q)):
            rc, out, err = self.cli(*argv, cwd=self.root)
            self.assertEqual(rc, 1, (argv, err))
            self.assertIn("@%s/worker opens no tag (a tag's qualifier takes no #)" % q, err, argv)
        self.assertEqual(sizes(), before, "nothing appended")

    def test_an_unregistered_channel_id_is_a_channel_at_every_door(self):
        other = "9e000001-0000-8000-8000-0000000000e1"
        self.assertTrue(sminos.is_channel_id(other))
        unknown = "no channel '%s' is known on this machine" % other   # spoken in only once registered (CH2's M4)
        for args, code, words in ((("say", "--in", other, "hi"), 4, unknown),
                                  (("say", "@%s/worker hi" % other), 4, unknown),
                                  (("charge", "%s/worker" % other, "x"), 4, "no member worker in channel %s" % other)):
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


class Round2(Machine):
    def test_an_unregistered_channel_id_is_no_project(self):
        other = "9e000001-0000-8000-8000-0000000000e1"
        self.project(PROJ, "app")
        for verb in (("chat", other), ("list", other), ("list", "--project", other)):
            rc, out, err = self.cli(*verb)
            self.assertEqual(rc, 4, verb)
            self.assertIn("'%s' is a channel, not a project" % other, err, verb)
        for fn in (sminos.find_project, sminos.project_tiers):
            self.assertEqual(exits(fn, other)[0], sminos.EXIT_UNKNOWN)
        self.assertIsNone(sminos.find_project(other, required=False))
        self.assertEqual(exits(channels.find_channel, other)[1].strip(),
                         "sminos: no channel '%s' is known on this machine" % other)
        # A project whose exact name is a channel's id shadows nothing: the id is a channel's, the project its own.
        named = self.project(TWIN1, other)
        for verb in (("list", other), ("chat", other)):
            rc, out, err = self.cli(*verb)
            self.assertEqual(rc, 4, verb)
            self.assertIn("'%s' is a channel, not a project" % other, err, verb)
        self.assertIsNone(sminos.find_project(other, required=False))
        self.assertEqual(sminos.find_project(TWIN1).id, named.id)
        self.assertEqual([p.id for p in sminos.project_tiers(TWIN1)], [TWIN1])

    def test_every_label_of_the_refusal_names_its_own_log(self):
        root = os.path.join(self.home, "w")
        os.makedirs(root)
        self.channel(DESK, "desk")
        self.project(PROJ, "desk")
        third = self.project(TWIN1, "desk#" + DESK[:8])   # a project literally named as the channel's short label
        rc, out, err = self.cli("say", "--in", "desk", "hi", cwd=root)
        self.assertEqual(rc, 4)
        labels = ["desk#%s (channel)" % DESK, "desk#%s (project)" % PROJ[:8]]
        self.assertEqual(err.strip(), "sminos: ambiguous name 'desk': %s — name one as listed, or by its id"
                         % ", ".join(sorted(labels)))
        rc, out, err = self.cli("say", "--in", "desk#" + DESK, "hi", cwd=root)
        self.assertEqual(rc, 0, err)
        self.assertEqual([e["kind"] for e in self.log_events(DESK)], ["human"],
                         "the channel's, by the whole id: said into it (CH2's M4)")
        rc, out, err = self.cli("say", "--in", "desk#" + PROJ[:8], "hi", cwd=root)
        self.assertEqual(rc, 0, err)
        self.assertEqual([e["kind"] for e in self.log_events(PROJ)], ["human"])
        self.assertEqual((len(self.log_events(DESK)), self.log_events(third.id)), (1, []))
        rc, out, err = self.cli("say", "--in", "desk#" + DESK[:8], "hi", cwd=root)
        self.assertEqual(rc, 0, err)
        self.assertEqual([e["kind"] for e in self.log_events(third.id)], ["human"], "the exact name is the third's")

    def test_the_order_of_a_say_s_refusals_with_no_channel(self):
        root = os.path.join(self.home, "w")
        os.makedirs(root)
        self.project(TWIN1, "twin")
        self.project(TWIN2, "twin")
        rc, out, err = self.cli("say", "--in", TWIN1, "@missing @twin/worker hi", cwd=root)
        self.assertEqual(rc, 4)
        self.assertIn("@missing", err)
        self.assertNotIn("ambiguous", err, "the first tag is refused first, as before channels")
        rc, out, err = self.cli("say", "--in", TWIN1, "@twin/worker @missing hi", cwd=root)
        self.assertEqual(rc, 4)
        self.assertIn("ambiguous name 'twin'", err)
        self.assertEqual(self.log_events(TWIN1) + self.log_events(TWIN2), [])
        self.assertIsNone(sminos.names_channel("twin"), "a clash of projects alone is no channel's")


if __name__ == "__main__":
    unittest.main()
