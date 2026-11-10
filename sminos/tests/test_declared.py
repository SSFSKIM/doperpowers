#!/usr/bin/env python3
"""Declared locations (the project registry's M4; MAWS
docs/doperpowers/plans/2026-11-10-project-registry.md, Interfaces §E.2): each
entry of org.json's `locations` that is neither `missing` nor `replaced` is a
known checkout of its project, which a spawn is admitted into and the
machine's presence lists; where the entry does not say `hub: false` and its
project is not this machine's own, the project is registered rooted there
with this org's hub, so the uplink holds it (its hello says no `follow`).
An entry that says `hub: false` keeps the registration and transport it has
today, and a machine-project entry registers nothing.

Hermetic: HOME and SMINOS_HOME are temporary, the org file is written
directly as the endpoint's frame would leave it, no git run, no daemon.
Run: python3 -B -I sminos/tests/test_declared.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
T = os.path.realpath(tempfile.mkdtemp(prefix="smdecl.", dir="/tmp"))
for k in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
          "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(k, None)
os.environ.update(HOME=os.path.join(T, "home"), SMINOS_HOME=os.path.join(T, "s"), SMINOS_DERIVE_EVERY="0")
os.makedirs(os.path.join(T, "s", "daemon"))
os.makedirs(os.path.join(T, "home", ".claude", "sessions"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts"))
import sminos  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_policy as policy  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_rpc as rpc  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

ORG, MACHINE, URL = "org-decl", "decl-mac", "http://127.0.0.1:9"
CRED = {"org": ORG, "hub": URL, "machine": MACHINE, "key": None}
MINTED = "11111111-1111-4111-8111-111111111111"
NOHUB = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
MISSING = "44444444-4444-4444-8444-444444444444"
REPLACED = "55555555-5555-4555-8555-555555555555"


def folder(name, smns=None):
    d = os.path.join(T, "w", name)
    os.makedirs(d, exist_ok=True)
    if smns is not None:
        with open(os.path.join(d, ".smns"), "w") as f:
            json.dump(smns, f)
    return d


def minted(path, pid, **more):
    st = os.stat(path)
    birth = sminos.birth_ns(getattr(st, "st_birthtime", 0))
    return {"path": sminos.canonical(path), "project": pid, "stated": "minted",
            "anchor": {"dev": str(st.st_dev), "ino": str(st.st_ino), "birth": str(int(birth or 0))}, **more}


def keep_org(at):
    """org.json as a frame with `locations` leaves it (at None: none)."""
    org = {"projects": [], "machines": [], "at": ""}
    if at is not None:
        org["locations"] = {"gen": 1, "at": at}
    sminos.write_json(sminos.org_path(), org)
    sminos.forget_caches()


def registration_file(pid):
    try:
        with open(os.path.join(sminos.projects_root(), pid, "project.json")) as f:
            return f.read()
    except FileNotFoundError:
        return None


def paths(checkouts):
    return [c["path"] for c in checkouts]


def admitted(path, checkouts):
    args = {"checkout": path}
    rpc.admit_spawn(args, "default", checkouts)
    return args["checkout"]


class Lane:
    """A Link's lane that keeps what it is sent, written as taken."""

    def __init__(self):
        self.sent = []

    def send(self, frames, then=None):
        self.sent += frames
        if then is not None:
            then()

    def posting(self):
        return False

    def queued(self):
        return 0

    def close(self):
        pass


class Declared(unittest.TestCase):
    """One machine of ORG with a declared plain folder (minted, two
    locations), a folder whose .smns names no hub (registered by a session
    before, git-mirrored), one whose .smns names another org's hub, a
    folder in the machine's own project, and a `missing` and a `replaced`
    entry."""

    @classmethod
    def setUpClass(cls):
        sminos.write_json(rl10.identity_path(), {
            "org": ORG, "hub": URL, "name": MACHINE, "former": {}, "ref": "machine-ref-1",
            "enrolled": "2026-11-10T00:00:00.000Z", "cutover": "2026-11-10T00:00:01.000Z", "build": "b"}, mode=0o600)
        sminos.forget_caches()
        cls.plain, cls.plain2 = folder("plain"), folder("plain-two")
        cls.nohub = folder("nohub", {"project": NOHUB, "name": "nohub", "remote": "git@example.com:o/nohub.git"})
        cls.other = folder("other", {"project": OTHER, "name": "other", "hub": {"org": "org-elsewhere"}})
        cls.stray = folder("stray")
        cls.accented = folder("caf\u00e9")   # NFC, as MAWS writes a path
        cls.missing = folder("missing", {"project": MISSING, "name": "missing", "hub": {"org": ORG}})
        cls.replaced = folder("replaced", {"project": REPLACED, "name": "replaced", "hub": {"org": ORG}})
        cls.own = sminos.machine_project_id(ORG, MACHINE)
        # The no-hub folder's project as a session there registered it: git-mirrored.
        sminos.project_path(sminos.resolve_project(cls.nohub), "log")
        cls.nohub_before = registration_file(NOHUB)
        keep_org([
            minted(cls.plain, MINTED), minted(cls.plain2, MINTED),
            {"path": sminos.canonical(cls.nohub), "project": NOHUB, "hub": False},
            {"path": sminos.canonical(cls.other), "project": OTHER, "hub": False},
            {"path": sminos.canonical(cls.stray), "project": cls.own},
            {"path": sminos.canonical(cls.accented), "project": cls.own},
            {"path": sminos.canonical(cls.missing), "project": MISSING, "state": "missing"},
            minted(cls.replaced, REPLACED, state="replaced"),
        ])
        cls.known = uplink.hub_projects(CRED)   # the uplink's scan: declared projects registered first

    def setUp(self):
        sminos.forget_caches()

    def test_a_declared_folder_with_no_session_is_registered_rooted_there_with_the_hub(self):
        self.assertIn(MINTED, self.known)
        reg = sminos.registration(MINTED)
        self.assertEqual((reg["root"], reg["hub"]), (self.plain, {"url": URL, "org": ORG}))
        # A project with two locations here keeps one root, whichever registered first.
        uplink.hub_projects(CRED)
        self.assertEqual(sminos.registration(MINTED)["root"], self.plain)

    def test_b_a_declared_folder_takes_a_spawn_and_is_in_the_presence(self):
        project = self.known[MINTED]
        checkouts = policy.known_checkouts(project)
        self.assertEqual(paths(checkouts), [self.plain, self.plain2], "its root and its other location")
        self.assertEqual(admitted(self.plain2, checkouts), self.plain2)
        machine = hublog.HubLog(project, CRED).presence()
        self.assertEqual(paths(machine["message"]["body"]["checkouts"]), [self.plain, self.plain2])

    def test_c_its_hello_holds_it(self):
        link = uplink.Link(CRED, {}, transport=mock.Mock(number=1))
        self.addCleanup(link.close)
        link.generation = 1
        link.log_lane = link.session_lane = Lane()
        link.open(link.log_of(MINTED, self.known))
        hello = next(f for f in link.log_lane.sent if f.get("t") == "hello" and f["project"] == MINTED)
        self.assertNotIn("follow", hello)
        self.assertTrue(link.holds(MINTED))
        machine = next(f for f in link.log_lane.sent if f.get("t") == "session"
                       and f["message"]["kind"] == "machine" and f["message"]["project"] == MINTED)
        self.assertEqual(paths(machine["message"]["body"]["checkouts"]), [self.plain, self.plain2])

    def test_d_hub_false_folders_take_a_spawn_and_keep_todays_registration(self):
        for path, pid in ((self.nohub, NOHUB), (self.other, OTHER)):
            project = sminos.resolve_project(path)
            self.assertEqual(project.id, pid)
            self.assertEqual(admitted(path, policy.known_checkouts(project)), path, pid)
            self.assertNotIn(pid, self.known, "%s: never streamed to this org's hub" % pid)
        self.assertEqual(registration_file(NOHUB), self.nohub_before, "the no-hub project's registration as it was")
        self.assertIsNone(sminos.registration(NOHUB).get("hub"), "and still git-mirrored")
        self.assertIsNone(registration_file(OTHER), "the other org's project, unregistered as it was")

    def test_e_a_machine_project_folder_takes_a_spawn_and_registers_nothing(self):
        mp = sminos.own_machine_project()
        checkouts = policy.known_checkouts(mp)
        self.assertEqual(paths(checkouts), [self.stray, self.accented])
        self.assertEqual(admitted(self.stray, checkouts), self.stray)
        # Asked for in another normalization of its name, the declared folder
        # is the one the spawn runs in.
        decomposed = os.path.join(os.path.dirname(self.accented), "cafe\u0301")
        self.assertEqual(admitted(decomposed, checkouts), os.path.realpath(self.accented))
        self.assertIn(sminos.registration(self.own).get("root", ""), ("",), "the machine project is rooted nowhere")
        self.assertEqual([pid for pid in os.listdir(sminos.projects_root())
                          if sminos.registration(pid).get("root") == self.stray], [])

    def test_f_missing_and_replaced_entries_are_no_checkouts(self):
        for path, pid in ((self.missing, MISSING), (self.replaced, REPLACED)):
            self.assertNotIn(pid, [loc.project for loc in sminos.declared_here()])
            self.assertIsNone(registration_file(pid), "%s: not registered by its declaration" % pid)
            followed = sminos.make_project(pid, pid, "", "", {"url": URL, "org": ORG})   # as the directory registers it
            self.assertEqual(policy.known_checkouts(followed), [])
            with self.assertRaises(rpc.Refused) as refused:
                admitted(path, policy.known_checkouts(followed))
            self.assertEqual(refused.exception.outcome["error"]["code"], "unknown-checkout")

    def test_g_a_used_home_is_registered_rooted_there(self):
        """A followed, rootless registration whose home was already used in
        the uplink's cache generation (an upload's callback before the
        scan) is still rooted at its declared location by the scan."""
        hub = {"url": URL, "org": ORG}
        sminos.write_json(os.path.join(sminos.projects_root(), MINTED, "project.json"),
                          {"project": MINTED, "name": "plain", "remote": "", "root": "", "hub": hub})
        sminos.forget_caches()
        sminos.project_path(sminos.make_project(MINTED, "plain", "", "", hub), "log")
        self.assertEqual(sminos.registration(MINTED)["root"], "")
        uplink.hub_projects(CRED)
        self.assertEqual(sminos.registration(MINTED)["root"], self.plain)


class NoLocations(unittest.TestCase):
    """An org file with no `locations` declares nothing (constraint 1)."""

    def test_nothing_declared(self):
        keep_org(None)
        try:
            self.assertEqual(sminos.declared_here(), [])
            self.assertEqual(policy.known_checkouts(sminos.own_machine_project()), [])
        finally:
            sminos.forget_caches()


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(T, ignore_errors=True)
