#!/usr/bin/env python3
"""A machine the org's directory retires (board #171): its sessions read
`gone` in list, find, chart and --json, folded behind `+N hidden` and shown
by --all; `machines` says `retired`; and on a machine cut over to its endpoint
(RL10), which carries no presence, `machines` and the directory's age line say
only what RL10 does. The events are fabricated in this process; every reading
is the real CLI's. Each test has its own HOME, SMINOS_HOME and MAWS_USER_DATA.
Run: python3 -B sminos/tests/test_org_retired.py
"""

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "sminos" / "scripts"
CLI = SCRIPTS / "sminos.py"
BASE = tempfile.mkdtemp(prefix="sminos-retired-")
for var in [v for v in os.environ if v.startswith(("SMINOS_", "SMNS_", "CLAUDE_CODE_", "MAWS_"))] \
        + ["DAEMON_HOME", "DAEMON_HOST", "AGORA_HOME", "CLAUDE_CONFIG_DIR"]:
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"),
                  MAWS_USER_DATA=os.path.join(BASE, "m"))
sys.path.insert(0, str(SCRIPTS))

import sminos  # noqa: E402

ORG = "org-1"
PG = "0c0c0c0a-1111-4222-8333-44445555666a"
GONE1 = "0d0d0d01-0000-4000-8000-000000000001"
GONE2 = "0d0d0d02-0000-4000-8000-000000000002"
OFF = "0d0d0d03-0000-4000-8000-000000000003"


def ago(seconds):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (t.microsecond // 1000)


def write(path, d):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "w") as f:
        json.dump(d, f)
    os.chmod(path, 0o600)


class Rows:
    """testhost, enrolled in org-1 (enroll), follows the hub project `pg`,
    where dc-gone ran two sessions (idle and busy, as last published) and
    delta, offline, one (idle)."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"),
                          MAWS_USER_DATA=os.path.join(home, "m"))
        self.sh = os.environ["SMINOS_HOME"]
        self.cwd = os.path.join(home, "bare")
        for d in (os.environ["HOME"] + "/.claude/sessions", self.sh + "/daemon", self.cwd):
            os.makedirs(d, mode=0o700, exist_ok=True)
        self.enroll()
        write(os.path.join(self.sh, "projects", PG, "project.json"),
              {"project": PG, "name": "pg", "remote": "", "root": "", "hub": {"url": "", "org": ORG}})
        sminos.forget_caches()
        project = sminos.find_project("pg")
        for machine, sid, alias, word in (("dc-gone", GONE1, "vm-idler", "idle"), ("dc-gone", GONE2, "vm-busy", "busy"),
                                          ("delta", OFF, "offliner", "idle")):
            sminos.log_append(project, "%s/%s" % (machine, sid), "joined", session=sid, alias=alias, name_source="user",
                              machine=machine, cwd="/d", worktree="", role="", seat="", by="")
            sminos.log_append(project, "%s/%s" % (machine, sid), "state", session=sid, state=word)
        sminos.forget_caches()

    def directory(self, machines, projects=(), at=None):
        """daemon/org.json as keep_org writes it."""
        write(os.path.join(self.sh, "daemon", "org.json"),
              {"projects": [{"id": PG, "name": "pg", "kind": "hub", "retired": False}, *projects],
               "machines": machines, "at": at or ago(0)})

    @staticmethod
    def machine_project(name, retired):
        return {"id": sminos.machine_project_id(ORG, name), "name": name, "kind": "machine", "machine": name,
                "retired": retired}

    def cli(self, *args):
        r = subprocess.run([sys.executable, "-B", str(CLI), *args], cwd=self.cwd, env=dict(os.environ), text=True,
                           capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, "%s: %s\n%s" % (args, r.stdout, r.stderr))
        return r.stdout

    def row(self, text, alias):
        """The member's row, its columns one space apart."""
        return next((" ".join(line.split()) for line in text.splitlines() if line.lstrip().startswith(alias + " [")), None)

    def machine_row(self, text, name):
        return next((" ".join(line.split()) for line in text.splitlines() if line.split()[:1] == [name]), None)

    def states(self):
        return {r["alias"]: r["state"] for r in json.loads(self.cli("list", "--org", "--json"))}

    # ---- the sessions of a retired machine

    def test_retired_machines_entry_makes_its_rows_gone_and_folded(self):
        self.directory([{"name": "testhost", "online": True, "seen": None},
                        {"name": "delta", "online": False, "seen": ago(7200)},
                        {"name": "dc-gone", "online": False, "seen": ago(86400), "retired": True}],
                       [self.machine_project("dc-gone", True)])
        text = self.cli("list", "--org")
        self.assertIsNone(self.row(text, "vm-idler"), text)
        self.assertIsNone(self.row(text, "vm-busy"), text)
        self.assertIn("idle @delta", self.row(text, "offliner") or "", "an offline machine keeps its published word")
        self.assertIn("+2 hidden (stopped, retired, gone)", text)
        every = self.cli("list", "--org", "--all")
        for alias in ("vm-idler", "vm-busy"):
            self.assertIn("gone @dc-gone", self.row(every, alias) or "", every)
        self.assertNotIn("hidden", every)
        chosen = self.cli("list", "--org", "--state", "gone")
        self.assertIsNotNone(self.row(chosen, "vm-idler"), chosen)
        self.assertIsNone(self.row(chosen, "offliner"), chosen)
        self.assertEqual(self.states(), {"vm-idler": "gone", "vm-busy": "gone", "offliner": "idle"})
        self.assertIsNone(self.row(self.cli("find", "vm-idler"), "vm-idler"))
        self.assertIsNotNone(self.row(self.cli("find", "vm-idler", "--all"), "vm-idler"))
        chart = self.cli("chart", "pg")
        self.assertNotIn("vm-idler", chart)
        self.assertIn("offliner", chart)
        self.assertIn("vm-idler", self.cli("chart", "pg", "--all"))
        # The machine's live count leaves it, as projects' does.
        self.assertEqual(self.machine_row(self.cli("machines"), "dc-gone"), "dc-gone retired 0 -")

    def test_a_retired_machine_project_alone_retires_it_by_name_in_any_case(self):
        # The hub drops a revoked machine's machines entry and retires its project.
        self.directory([{"name": "testhost", "online": True, "seen": None}],
                       [self.machine_project("DC-Gone", True)])
        self.assertEqual(self.states(), {"vm-idler": "gone", "vm-busy": "gone", "offliner": "idle"})

    def test_a_directory_without_the_field_changes_nothing(self):
        self.assertEqual(self.states(), {"vm-idler": "idle", "vm-busy": "busy", "offliner": "idle"},
                         "no directory yet")
        # An older endpoint's: no machines entry carries the field, and every machine project goes retired: false.
        self.directory([{"name": "testhost", "online": False, "seen": None},
                        {"name": "dc-gone", "online": False, "seen": None},
                        {"name": "delta", "online": False, "seen": None}],
                       [self.machine_project("dc-gone", False), self.machine_project("delta", False)])
        self.assertEqual(self.states(), {"vm-idler": "idle", "vm-busy": "busy", "offliner": "idle"})
        text = self.cli("list", "--org")
        self.assertIn("idle @dc-gone", self.row(text, "vm-idler") or "", text)
        self.assertNotIn("hidden", text)


class CutOver(Rows, unittest.TestCase):
    """Cut over to its endpoint (RL10): identity.json, and a directory as
    RL10's endpoint builds it, every machine `online: false` and `seen` only
    as of its last restatement. (Its DX2 twin, a hub.json enrolment with the
    hub's presence, went in #153 M4.)"""

    def enroll(self):
        write(os.path.join(self.sh, "daemon", "identity.json"),
              {"org": ORG, "hub": "http://127.0.0.1:9", "name": "testhost", "former": {}, "ref": "r",
               "enrolled": "2026-10-01T00:00:00Z", "cutover": "2026-10-02T00:00:00Z", "build": "b"})

    def test_machines_say_what_rl10_carries(self):
        self.directory([{"name": "testhost", "online": False, "seen": None},
                        {"name": "delta", "online": False, "seen": None},
                        {"name": "echo", "online": False, "seen": ago(7200)},
                        {"name": "foxtrot", "online": False, "seen": None},
                        {"name": "dc-gone", "online": False, "seen": None, "retired": True}],
                       [self.machine_project("dc-gone", True)], at=ago(16 * 3600))
        text = self.cli("machines")
        self.assertEqual(self.machine_row(text, "testhost"), "testhost this machine 0 -")
        self.assertRegex(self.machine_row(text, "delta"), r"^delta last event \d+s ago 1 pg$",
                         "a machine whose events are relayed: its newest event held here")
        self.assertEqual(self.machine_row(text, "echo"), "echo last event 2h ago 0 -", "else the frame's seen")
        self.assertEqual(self.machine_row(text, "foxtrot"), "foxtrot no event yet 0 -")
        self.assertEqual(self.machine_row(text, "dc-gone"), "dc-gone retired 0 -")
        self.assertNotIn("never seen", text)
        self.assertNotIn("online", text)
        line = "(the org's directory is 16h old: the endpoint restates it only when the org changes or the daemon reconnects)"
        self.assertIn(line, text)
        self.assertNotIn("said nothing newer", text)
        self.assertIn(line, self.cli("projects"))

    def test_no_directory_yet(self):
        text = self.cli("machines")
        self.assertIn("no org directory yet: the endpoint has not sent one", text)
        self.assertNotIn("hub", text)
        self.assertTrue(re.search(r"^testhost +this machine", text, re.M), text)


if __name__ == "__main__":
    unittest.main()
