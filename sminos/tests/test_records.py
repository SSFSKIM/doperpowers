#!/usr/bin/env python3
"""Each session's machine-held record (O12 M1; the remote layer's RL6):
`$SMINOS_HOME/session-records/<session>.json`, written once, mode 0600, by
the path that first joins the session — the hook from the session's own
environment, a spawn from its launch (a pending provenance the child claims
at its SessionStart), a continuation from its predecessor's record — and
read back by `list --json`; `origin`, and `owners` that name members (never
the `@machine` token, which stays on the machine), ride on `joined` only once
the record is final.

Hermetic: every machine here is a temporary HOME and SMINOS_HOME (one test
leaves SMINOS_HOME unset, the default home under its temporary HOME), with a
`claude` stand-in first on PATH. Run: python3 -B -I sminos/tests/test_records.py
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import fcntl
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "sminos" / "scripts"
CLI = SCRIPTS / "sminos.py"
MEMBER = "0123456789abcdef0123456789abcdef"
OTHER = "fedcba9876543210fedcba9876543210"
SECRET = "sk-test-not-a-real-token-5b1e"
SEAT_RE = re.compile(r"\[[0-9a-f]+ / ([0-9a-f-]{36})\]")

T0 = "7a000001-0000-4000-8000-00000000007a"
TB = "7b000002-0000-4000-8000-00000000007b"
TX = "7c000003-0000-4000-8000-00000000007c"
TD = "7d000004-0000-4000-8000-00000000007d"

# The `claude` stand-in: `agents` lists its launches, and a `--bg` launch
# registers one row. With REC_STUB_HOOK_FIRST set, the launched session runs
# its SessionStart hook before the launch returns (before the spawner's poll
# can learn its id), in the environment the engine would give it: the
# spawner's, the session's own id, and its `--settings` file's `env`.
STUB = r'''#!/usr/bin/env python3
import glob, json, os, subprocess, sys
jload = lambda p: json.loads(open(p).read())
state = os.environ["REC_STUB_STATE"]
os.makedirs(os.path.join(state, "agents"), exist_ok=True)
args = sys.argv[1:]
with open(os.path.join(state, "calls.log"), "a") as f:
    f.write(json.dumps({"args": args, "launch_env": os.environ.get("SMINOS_LAUNCH", ""),
                        "proof_env": os.environ.get("SMINOS_DESK_PROOF")}) + "\n")
if args[:1] == ["agents"]:
    print(json.dumps([jload(p) for p in sorted(glob.glob(os.path.join(state, "agents", "*.json")))]))
    sys.exit(0)
if "--bg" not in args:
    sys.exit(0)
counter = os.path.join(state, "counter")
n = int(open(counter).read()) + 1 if os.path.exists(counter) else 1
open(counter, "w").write(str(n))
short, sid = "%08x" % (0xc0de0000 + n), "%08x-0000-4000-8000-%012x" % (0xc0de0000 + n, n)
name = args[args.index("-n") + 1] if "-n" in args else ""
settings = args[args.index("--settings") + 1] if "--settings" in args else ""
env = dict(os.environ, CLAUDE_CODE_SESSION_ID=sid)
if settings and not settings.lstrip().startswith("{"):
    env.update(jload(settings).get("env") or {})
tdir = os.path.join(os.environ["HOME"], ".claude", "projects", "rec")
os.makedirs(tdir, exist_ok=True)
tpath = os.path.join(tdir, sid + ".jsonl")
with open(tpath, "w") as f:
    f.write(json.dumps({"type": "user", "cwd": os.getcwd(), "message": {"role": "user", "content": "go"}}) + "\n")
if os.environ.get("REC_STUB_HOOK_FIRST"):
    payload = {"session_id": sid, "transcript_path": tpath, "cwd": os.getcwd(),
               "hook_event_name": "SessionStart", "source": "startup"}
    subprocess.run([sys.executable, os.environ["REC_STUB_SMINOS"], "record"], input=json.dumps(payload),
                   env=env, text=True, capture_output=True)
with open(os.path.join(state, "agents", short + ".json"), "w") as f:
    json.dump({"id": short, "sessionId": sid, "kind": "background", "name": name, "state": "working",
               "status": "", "cwd": os.getcwd()}, f)
print("backgrounded · %s · %s" % (short, name))
'''


def jload(path):
    return json.loads(Path(path).read_text())


def lines(path):
    return [x for x in Path(path).read_text().splitlines() if x.strip()]


def clean_env():
    drop = ("SMINOS_", "SMNS_", "CLAUDE_", "ANTHROPIC_", "DAEMON_", "AGORA_", "REC_STUB_", "CLODEX_")
    return {k: v for k, v in os.environ.items() if not k.startswith(drop)}


class Machine:
    """One machine: its HOME, its registry, one project (a git repository)."""

    def __init__(self, tc, host="testhost", default_home=False, project_from=None):
        self.tc = tc
        self.dir = Path(tempfile.mkdtemp(prefix="sminos-rec-"))
        tc.addCleanup(shutil.rmtree, self.dir, True)
        self.home = self.dir / "home"
        (self.home / ".claude" / "sessions").mkdir(parents=True)
        self.reg = self.home / ".claude" / "sminos" if default_home else self.dir / "registry"
        self.repo = self.dir / "repo"
        self.repo.mkdir()
        self.state = self.dir / "stub"
        self.state.mkdir()
        bindir = self.dir / "bin"
        bindir.mkdir()
        (bindir / "claude").write_text(STUB)
        (bindir / "claude").chmod(0o755)
        self.env = clean_env()
        self.env.update(HOME=str(self.home), DAEMON_HOST=host, REC_STUB_STATE=str(self.state),
                        REC_STUB_SMINOS=str(CLI), SMINOS_POLL_INTERVAL="0.05", SMINOS_UUID_POLL="100",
                        SMINOS_DERIVE_EVERY="0", SMINOS_NO_EXEC="1", PATH="%s:%s" % (bindir, os.environ["PATH"]))
        if not default_home:
            self.env["SMINOS_HOME"] = str(self.reg)
        subprocess.run(["git", "init", "-q", str(self.repo)], env=self.env, check=True)
        if project_from is not None:
            shutil.copy(project_from.repo / ".smns", self.repo / ".smns")
        else:
            self.cli("project", "init", "--name", "rec")
        self.project = json.loads((self.repo / ".smns").read_text())["project"]

    # ---- driving it

    def cli(self, *args, env=None, check=True, inp=None):
        r = subprocess.run([sys.executable, "-B", str(CLI), *args], cwd=self.repo, env={**self.env, **(env or {})},
                           text=True, capture_output=True, input=inp)
        if check and r.returncode:
            raise AssertionError("sminos %s: %d\n%s\n%s" % (" ".join(args), r.returncode, r.stdout, r.stderr))
        return r

    def py(self, code, *args, env=None):
        """Python against this machine's sminos, in its environment."""
        prelude = "import sys; sys.path.insert(0, %r); import sminos\n" % str(SCRIPTS)
        r = subprocess.run([sys.executable, "-B", "-c", prelude + code, *args], cwd=self.repo,
                           env={**self.env, **(env or {})}, text=True, capture_output=True)
        if r.returncode:
            raise AssertionError("python: %d\n%s\n%s" % (r.returncode, r.stdout, r.stderr))
        return r.stdout

    def live(self):
        """A running process to stand for a session's engine; its parent is this test."""
        p = subprocess.Popen(["sleep", "600"])
        self.tc.addCleanup(p.wait)
        self.tc.addCleanup(p.kill)
        return p.pid

    def peer(self, sid, name, kind="interactive", pid=None, entrypoint=None, name_source="derived"):
        rec = {"pid": pid or self.live(), "sessionId": sid, "name": name, "nameSource": name_source, "kind": kind,
               "status": "idle", "cwd": str(self.repo)}
        if entrypoint:
            rec["entrypoint"] = entrypoint
        (self.home / ".claude" / "sessions" / ("rec-%s.json" % name)).write_text(json.dumps(rec) + "\n")
        return rec["pid"]

    def unpeer(self, name):
        (self.home / ".claude" / "sessions" / ("rec-%s.json" % name)).unlink()

    def transcript(self, sid, *rows):
        d = self.home / ".claude" / "projects" / "rec"
        d.mkdir(parents=True, exist_ok=True)
        p = d / (sid + ".jsonl")
        if not p.exists():
            p.write_text(json.dumps({"type": "user", "cwd": str(self.repo),
                                     "message": {"role": "user", "content": "start"}}) + "\n")
        with open(p, "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return p

    def hand_off_transcript(self, old, new):
        """The old session's transcript as the engine leaves it when it hands the session to a job."""
        self.transcript(old, {"type": "assistant", "uuid": "h1", "message": {
            "role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]}},
            {"type": "continued-in", "sessionId": old, "continuedInSessionId": new})

    def hook(self, event, sid, source="startup", env=None):
        payload = {"session_id": sid, "transcript_path": str(self.transcript(sid)), "cwd": str(self.repo),
                   "hook_event_name": event, "source": source}
        return self.cli("record", env=env, inp=json.dumps(payload))

    def spawn(self, alias, *flags, env=None):
        out = self.cli("spawn", *flags, "--", alias, "the task", env=env).stdout
        m = SEAT_RE.search(out)
        self.tc.assertTrue(m, out)
        return m.group(1)

    # ---- reading it

    def write_record(self, sid, **fields):
        """A record as a launch would have left it (a fixture), on top of the defaults."""
        rec = {"session": sid, "source": "launch", "basis": "launch", "origin": {"kind": "terminal"},
               "owners": ["@machine"], "ownersProof": [], "principal": "@machine",
               "inference": slot(self), "created": "2026-10-27T00:00:00Z", "former": [], **fields}
        self.record_path(sid).parent.mkdir(parents=True, exist_ok=True)
        self.record_path(sid).write_text(json.dumps(rec))

    def continued(self, old, new):
        """The `continued` retirement a hand-off writes, naming the session it went on in."""
        self.py("p = sminos.resolve_project(sys.argv[1])\n"
                "sminos.lifecycle(p, sys.argv[2], 'retired', by='', reason='continued', to=sys.argv[3])",
                str(self.repo), old, new)

    def publications(self, sid):
        return [{k: j[k] for k in ("owners", "origin") if k in j} for j in self.own_joined(sid)
                if "owners" in j or "origin" in j]

    def record_path(self, sid):
        return self.reg / "session-records" / (sid + ".json")

    def record(self, sid):
        p = self.record_path(sid)
        return json.loads(p.read_text()) if p.exists() else None

    def pending(self):
        return sorted(glob.glob(str(self.reg / "session-records" / "pending" / "*.json")))

    def rows(self):
        return json.loads(self.cli("list", "--all", "--json").stdout)

    def row(self, sid):
        got = [r for r in self.rows() if r.get("session") == sid]
        self.tc.assertEqual(len(got), 1, "one row for %s in %s" % (sid, [r.get("session") for r in self.rows()]))
        return got[0]

    def log_dir(self):
        return self.reg / "projects" / self.project / "log"

    def events(self, sid=None):
        out = []
        for p in sorted(glob.glob(str(self.log_dir() / "*.jsonl"))):
            for line in lines(p):
                e = json.loads(line)
                if sid is None or e.get("session") == sid:
                    out.append(e)
        return out

    def own_joined(self, sid):
        """The joined events in the session's own writer file, oldest first."""
        p = self.log_dir() / ("%s.%s.jsonl" % (self.env["DAEMON_HOST"], sid))
        if not p.exists():
            return []
        return [e for e in map(json.loads, lines(p)) if e["kind"] == "joined"]

    def assert_private(self):
        """principal, inference, controller and source never leave the machine (RL §6.2)."""
        for p in glob.glob(str(self.reg / "projects" / "*" / "log" / "*.jsonl")):
            text = Path(p).read_text()
            for word in ("principal", "inference", "controller", "settingsRef", "configDir", "@machine"):
                self.tc.assertNotIn('"%s' % word, text, "%s in a log event (%s)" % (word, p))

    def copy_log_to(self, other):
        dst = other.reg / "projects" / self.project / "log"
        dst.mkdir(parents=True, exist_ok=True)
        for p in glob.glob(str(self.log_dir() / "*.jsonl")):
            shutil.copy(p, dst / os.path.basename(p))


def slot(m):
    return {"kind": "slot", "configDir": str(m.home / ".claude")}


class TheRecord(unittest.TestCase):

    def test_a_terminal_session_from_its_hook(self):
        m = Machine(self)
        m.peer(T0, "term")
        m.hook("SessionStart", T0)
        rec = m.record(T0)
        self.assertIsNotNone(rec, "the hook writes the record")
        self.assertEqual(os.stat(m.record_path(T0)).st_mode & 0o777, 0o600)
        self.assertEqual(rec["session"], T0)
        self.assertEqual(rec["owners"], ["@machine"])
        self.assertEqual(rec["ownersProof"], [])
        self.assertEqual(rec["origin"], {"kind": "terminal"})
        self.assertEqual(rec["principal"], "@machine")
        self.assertEqual(rec["inference"], slot(m))
        self.assertEqual(rec["source"], "hook", "the session's own environment is final evidence")
        self.assertTrue(rec["created"].endswith("Z"))
        joined = m.own_joined(T0)
        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0]["origin"], {"kind": "terminal"}, "a final record's origin rides on joined")
        self.assertNotIn("owners", joined[0], "@machine never leaves the machine")
        row = m.row(T0)
        self.assertEqual((row["owners"], row["origin"]), (["@machine"], {"kind": "terminal"}))
        self.assertEqual((row["principal"], row["inference"], row["controller"]), ("@machine", slot(m), None))
        m.hook("Stop", T0, source="")
        self.assertEqual(m.record(T0), rec, "a later hook leaves it as it is")
        self.assertEqual(len(m.own_joined(T0)), 1)
        m.assert_private()

    def test_a_machine_owned_session_publishes_its_origin_and_reads_back_as_the_machines(self):
        a = Machine(self)
        a.peer(T0, "term")
        a.hook("SessionStart", T0)
        seat = a.spawn("kid", env={"CLAUDE_CODE_SESSION_ID": T0})
        for sid in (T0, seat):
            self.assertEqual(a.record(sid)["owners"], ["@machine"])
            self.assertIn(a.record(sid)["source"], ("hook", "launch"))
            joined = a.own_joined(sid)
            self.assertTrue(joined and all("owners" not in j and j.get("origin") for j in joined), joined)
        a.assert_private()
        b = Machine(self, host="otherhost", project_from=a)
        a.copy_log_to(b)
        self.assertEqual((b.row(T0)["owners"], b.row(T0)["origin"]), (["@machine"], {"kind": "terminal"}))
        self.assertEqual((b.row(seat)["owners"], b.row(seat)["origin"]),
                         (["@machine"], {"kind": "sminos-spawn", "spawnerSession": T0}),
                         "another machine reads the machine's owners, and the published origin")
        b.assert_private()

    def test_the_route_is_read_from_the_sessions_environment(self):
        m = Machine(self)
        m.peer(T0, "gw")
        m.hook("SessionStart", T0, env={"ANTHROPIC_BASE_URL": "https://u:pw@Gw.Example.com:8443/v1/x?k=" + SECRET})
        self.assertEqual(m.record(T0)["inference"], {"kind": "route",
                                                     "settingsRef": "base-url:https://gw.example.com:8443"},
                         "scheme, host and port only: no credentials, path or query")
        m.peer(TB, "slot2")
        m.hook("SessionStart", TB, env={"CLAUDE_CONFIG_DIR": str(m.dir / "slot2")})
        self.assertEqual(m.record(TB)["inference"], {"kind": "slot", "configDir": str(m.dir / "slot2")})
        self.assertNotIn(SECRET, m.record_path(T0).read_text())
        m.assert_private()

    def test_a_maws_session_its_host_marked(self):
        m = Machine(self)
        m.peer(T0, "engine", entrypoint="sdk-ts")
        m.hook("SessionStart", T0, env={"SMNS_MEMBER": str(os.getpid())})
        self.assertEqual(m.record(T0)["origin"], {"kind": "maws"})
        self.assertEqual(m.record(T0)["owners"], ["@machine"])

    def test_a_seat_spawned_from_a_session_carries_its_owners(self):
        m = Machine(self)
        m.peer(T0, "parent")
        m.hook("SessionStart", T0, env={"CLAUDE_CONFIG_DIR": str(m.dir / "parent-slot")})
        parent = m.record(T0)
        child = m.spawn("kid", env={"CLAUDE_CODE_SESSION_ID": T0})
        rec = m.record(child)
        self.assertEqual(rec["origin"], {"kind": "sminos-spawn", "spawnerSession": T0})
        for k in ("owners", "ownersProof", "principal", "inference"):
            self.assertEqual(rec[k], parent[k], k + " copied from the spawning session's record")
        self.assertEqual(rec["source"], "launch")
        self.assertEqual(m.pending(), [], "the launch was claimed")
        row = m.row(child)
        self.assertEqual((row["owners"], row["origin"]), (["@machine"], {"kind": "sminos-spawn", "spawnerSession": T0}))
        self.assertEqual((row["principal"], row["inference"]), ("@machine", parent["inference"]))
        joined = m.own_joined(child)
        self.assertEqual([(j.get("owners"), j.get("origin")) for j in joined],
                         [(None, {"kind": "sminos-spawn", "spawnerSession": T0})])
        # A seat with settings of its own runs on them: its route is the merged launch file, never its content.
        routed = m.spawn("routed", "--settings", json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": SECRET}}),
                         env={"CLAUDE_CODE_SESSION_ID": T0})
        inf = m.record(routed)["inference"]
        self.assertEqual(inf["kind"], "route")
        self.assertTrue(inf["settingsRef"].startswith(str(m.reg / "settings") + "/"), inf)
        self.assertNotIn(SECRET, m.record_path(routed).read_text())
        self.assertEqual(jload(inf["settingsRef"])["env"]["ANTHROPIC_AUTH_TOKEN"], SECRET,
                         "the route names the file the seat launched with")
        m.assert_private()

    def test_a_seat_spawned_from_a_seat_copies_the_grandparents_owners(self):
        m = Machine(self)
        first = m.spawn("first", env={"SMINOS_DESK_MEMBER": MEMBER})
        second = m.spawn("second", env={"CLAUDE_CODE_SESSION_ID": first})
        rec = m.record(second)
        self.assertEqual(rec["owners"], [MEMBER])
        self.assertEqual(rec["principal"], MEMBER)
        self.assertEqual(rec["origin"], {"kind": "sminos-spawn", "spawnerSession": first})
        self.assertEqual(m.row(second)["owners"], [MEMBER])

    def test_a_desk_spawn_is_owned_by_its_requester(self):
        m = Machine(self)
        sid = m.spawn("deskseat", env={"SMINOS_DESK_MEMBER": MEMBER})
        rec = m.record(sid)
        self.assertEqual(rec["owners"], [MEMBER])
        self.assertEqual(rec["principal"], MEMBER)
        self.assertEqual(rec["origin"], {"kind": "maws", "requester": MEMBER})
        self.assertEqual(rec["source"], "launch")
        row = m.row(sid)
        self.assertEqual((row["owners"], row["origin"]), ([MEMBER], {"kind": "maws", "requester": MEMBER}))
        self.assertEqual([(j.get("owners"), j.get("origin")) for j in m.own_joined(sid)],
                         [([MEMBER], {"kind": "maws", "requester": MEMBER})], "member owners ride on joined")
        # The RPC's own path: sminos_rpc.spawn runs the verb as the member.
        out = m.py("import json, sminos_rpc as r\n"
                   "print(json.dumps(r.spawn({'brief': 'b', 'permission_mode': 'auto'}, 'AAAAAAAAAAAAAAAAAAAAAA', "
                   "sys.argv[1], sys.argv[2])))", str(m.repo), MEMBER)
        sid2 = json.loads(out)["result"]["session"]
        self.assertEqual(m.record(sid2)["origin"], {"kind": "maws", "requester": MEMBER})
        self.assertEqual(m.record(sid2)["owners"], [MEMBER])
        m.assert_private()

    def test_a_desk_spawns_proof_is_its_records_ownersProof(self):
        """O12 M7: a remote desk spawn's proof, handed by the daemon to the
        verb (SMINOS_DESK_PROOF), is the new session's `ownersProof`, which
        `list --json` shows; neither the launch's environment nor its
        settings carry it, and a seat the session spawns copies it. One that
        does not parse is [] and said in daemon.log, never a refusal; a spawn
        the daemon handed none (DX2's) keeps [] and says nothing."""
        m = Machine(self)
        proof = {"v": 1, "action": {"name": "sminos.spawn", "opId": "op-proof-00000001"}, "sig": "proof-signature"}
        out = m.py("import json, sminos_rpc as r\n"
                   "print(json.dumps(r.spawn({'brief': 'b', 'permission_mode': 'auto'}, 'BBBBBBBBBBBBBBBBBBBBBB', "
                   "sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))))", str(m.repo), MEMBER, json.dumps(proof))
        sid = json.loads(out)["result"]["session"]
        self.assertEqual(m.record(sid)["ownersProof"], [proof])
        self.assertEqual(m.row(sid)["ownersProof"], [proof], "list --json shows it")
        launches = [json.loads(x) for x in lines(m.state / "calls.log") if "--bg" in json.loads(x)["args"]]
        self.assertEqual([c["proof_env"] for c in launches], [None], "the session's environment carries no proof")
        for p in glob.glob(str(m.reg / "settings" / "*.json")):
            self.assertNotIn("proof-signature", Path(p).read_text(), "nor do its launch settings")
        kid = m.spawn("kid", env={"CLAUDE_CODE_SESSION_ID": sid})
        self.assertEqual(m.record(kid)["ownersProof"], [proof], "a seat it spawns copies it")
        bad = m.spawn("badproof", env={"SMINOS_DESK_MEMBER": MEMBER, "SMINOS_DESK_PROOF": "{not json"})
        self.assertEqual((m.record(bad)["ownersProof"], m.record(bad)["owners"]), ([], [MEMBER]),
                         "spawned all the same")
        said = (m.reg / "daemon.log").read_text()
        self.assertEqual(said.count("proof does not parse"), 1, said)
        plain = m.spawn("dx2", env={"SMINOS_DESK_MEMBER": MEMBER})
        self.assertEqual(m.record(plain)["ownersProof"], [])
        self.assertEqual((m.reg / "daemon.log").read_text().count("proof"), said.count("proof"), "nothing said")
        m.assert_private()

    def test_a_child_whose_hook_runs_before_the_poll_claims_its_launch(self):
        m = Machine(self)
        sid = m.spawn("early", env={"SMINOS_DESK_MEMBER": MEMBER, "REC_STUB_HOOK_FIRST": "1"})
        rec = m.record(sid)
        self.assertEqual((rec["owners"], rec["source"]), ([MEMBER], "launch"),
                         "the child claimed its pending provenance before its spawner knew its id")
        self.assertEqual(m.pending(), [])
        launches = [json.loads(x) for x in lines(m.state / "calls.log") if '"--bg"' in x]
        settings = launches[-1]["args"][launches[-1]["args"].index("--settings") + 1]
        self.assertRegex(jload(settings)["env"]["SMINOS_LAUNCH"], r"^[0-9a-f]{32}$",
                         "the launch id travels in the merged settings file")

    def test_a_claude_started_from_a_seats_bash_claims_nothing(self):
        m = Machine(self)
        seat = m.spawn("holder", env={"SMINOS_DESK_MEMBER": MEMBER, "REC_STUB_HOOK_FIRST": "1"})
        launches = [json.loads(x) for x in lines(m.state / "calls.log") if '"--bg"' in x]
        settings = launches[-1]["args"][launches[-1]["args"].index("--settings") + 1]
        launch = jload(settings)["env"]["SMINOS_LAUNCH"]
        before = m.record_path(seat).read_bytes()
        # The seat's Bash runs `claude`: the variable is inherited, the session is another.
        m.peer(TX, "bashclaude")
        m.hook("SessionStart", TX, env={"SMINOS_LAUNCH": launch, "CLAUDE_CODE_SESSION_ID": TX})
        self.assertEqual(m.record_path(seat).read_bytes(), before, "the seat keeps its claim")
        self.assertEqual(m.record(TX)["origin"], {"kind": "terminal"})
        self.assertEqual(m.record(TX)["owners"], ["@machine"])
        self.assertEqual(m.record(TX)["source"], "hook")
        # A pending launch is never claimed by a session that is not new.
        m.py("import sminos_records as R\nR.write_pending(sys.argv[1], R.default_provenance())", "f" * 32)
        m.peer(TB, "resumed")
        m.hook("SessionStart", TB, source="resume", env={"SMINOS_LAUNCH": "f" * 32})
        m.hook("SessionStart", TX, env={"SMINOS_LAUNCH": "f" * 32})
        self.assertEqual(len(m.pending()), 1, "a resume and a session with a record claim nothing")
        self.assertEqual(m.record(TB)["source"], "hook")
        # Nor does a `sminos spawn` from the seat pass the variable on.
        m.spawn("grandkid", env={"CLAUDE_CODE_SESSION_ID": seat, "SMINOS_LAUNCH": launch})
        last = [json.loads(x) for x in lines(m.state / "calls.log") if '"--bg"' in x][-1]
        self.assertEqual(last["launch_env"], "", "launch_env drops SMINOS_LAUNCH")

    def test_a_seat_whose_first_hook_cannot_register_still_claims(self):
        m = Machine(self)
        # The hook runs before the engine's registry or the agents row hold the session: it claims all the same.
        seat = m.spawn("unreg", env={"SMINOS_DESK_MEMBER": MEMBER, "REC_STUB_HOOK_FIRST": "1"})
        self.assertEqual(m.record(seat)["source"], "launch")
        self.assertEqual(m.record(seat)["owners"], [MEMBER])

    def test_a_hand_off_carries_the_record_to_the_job(self):
        m = Machine(self)
        m.peer(T0, "handy")
        m.hook("SessionStart", T0)
        # A record the desk's spawn would have written: owners other than the machine's.
        desk = dict(m.record(T0), owners=[MEMBER], principal=MEMBER, origin={"kind": "maws", "requester": MEMBER},
                    source="launch")
        m.record_path(T0).write_text(json.dumps(desk))
        m.hand_off_transcript(T0, TB)
        m.peer(TB, "handyjob", kind="bg", name_source="auto")
        m.hook("SessionStart", TB)
        rec = m.record(TB)
        self.assertEqual(rec["owners"], [MEMBER])
        self.assertEqual(rec["origin"], {"kind": "maws", "requester": MEMBER})
        self.assertEqual(rec["principal"], MEMBER)
        self.assertEqual(rec["former"], [T0])
        self.assertEqual(rec["source"], "lineage")
        self.assertEqual(os.stat(m.record_path(TB)).st_mode & 0o777, 0o600)
        self.assertEqual([j.get("owners") for j in m.own_joined(TB)], [[MEMBER]])
        self.assertEqual(m.row(TB)["owners"], [MEMBER])

    def test_a_continuation_of_a_provisional_record_stays_provisional(self):
        m = Machine(self)
        m.peer(T0, "prov")
        m.transcript(T0)
        m.rows()   # reconciliation joins it: no environment, so defaults, provisional
        self.assertEqual(m.record(T0)["source"], "default")
        self.assertEqual([(j.get("owners"), j.get("origin")) for j in m.own_joined(T0)], [(None, None)],
                         "a provisional record publishes nothing")
        m.hand_off_transcript(T0, TB)
        m.peer(TB, "provjob", kind="bg", name_source="auto")
        m.hook("SessionStart", TB)
        rec = m.record(TB)
        self.assertEqual((rec["source"], rec["owners"], rec["former"]), ("default", ["@machine"], [T0]))
        self.assertEqual([(j.get("owners"), j.get("origin")) for j in m.own_joined(TB)], [(None, None)])
        self.assertEqual(m.row(TB)["owners"], ["@machine"], "read back as the default")

    def test_a_reconciled_session_is_published_once_its_hook_runs(self):
        m = Machine(self)
        m.peer(T0, "late")
        m.transcript(T0)
        m.rows()
        self.assertEqual(m.record(T0)["source"], "default")
        m.hook("Stop", T0, source="")
        self.assertEqual(m.record(T0)["source"], "hook", "the hook's evidence replaces the provisional default")
        self.assertEqual([(j.get("owners"), j.get("origin")) for j in m.own_joined(T0)],
                         [(None, None), (None, {"kind": "terminal"})],
                         "and the final record is published by a joined of its own, its origin without @machine")
        m.hook("Stop", T0, source="")
        m.rows()
        self.assertEqual(len(m.own_joined(T0)), 2, "once")

    def test_an_older_binarys_hand_off_is_recovered_not_frozen(self):
        a = Machine(self)
        a.peer(T0, "ancestor")
        a.hook("SessionStart", T0)
        desk = dict(a.record(T0), owners=[MEMBER], principal=MEMBER, origin={"kind": "maws", "requester": MEMBER},
                    source="launch")
        a.record_path(T0).write_text(json.dumps(desk))
        a.peer(TB, "job", kind="bg", name_source="auto")
        a.transcript(TB)
        a.rows()   # the job joins before any hand-off is known: provisional defaults
        self.assertEqual(a.record(TB)["source"], "default")
        # An older binary's hand-off: the retirement naming the job, no record copied.
        a.py("p = sminos.resolve_project(sys.argv[1])\n"
             "sminos.lifecycle(p, sys.argv[2], 'retired', by='', reason='continued', to=sys.argv[3])",
             str(a.repo), T0, TB)
        a.unpeer("ancestor")
        a.rows()
        rec = a.record(TB)
        self.assertEqual((rec["owners"], rec["source"], rec["former"]), ([MEMBER], "lineage", [T0]),
                         "the ancestor's owners recovered, the provisional default replaced")
        self.assertEqual(a.own_joined(TB)[-1].get("owners"), [MEMBER], "and published")
        # Another machine, which read the job's provisional join, reads it corrected.
        b = Machine(self, host="otherhost", project_from=a)
        a.copy_log_to(b)
        row = b.row(TB)
        self.assertFalse(row["local"])
        self.assertEqual((row["owners"], row["origin"]), ([MEMBER], {"kind": "maws", "requester": MEMBER}))
        self.assertNotIn("principal", row, "a remote member's private fields are not known here")

    def test_older_joined_events_read_back(self):
        a = Machine(self)
        a.peer(T0, "owned")
        a.hook("SessionStart", T0)
        # A session whose log predates the record: an older binary's joined, no record.
        a.py("p = sminos.resolve_project(sys.argv[1])\n"
             "sminos.lifecycle(p, sys.argv[2], 'joined', **sminos.joined_fields('legacy', 'derived', sys.argv[1]))",
             str(a.repo), TX)
        # And an older daemon's later joined of the owned session, without owners.
        a.py("p = sminos.resolve_project(sys.argv[1])\n"
             "sminos.lifecycle(p, sys.argv[2], 'joined', **sminos.joined_fields('owned', 'derived', sys.argv[1]))",
             str(a.repo), T0)
        b = Machine(self, host="otherhost", project_from=a)
        a.copy_log_to(b)
        self.assertEqual((b.row(T0)["owners"], b.row(T0)["origin"]), (["@machine"], {"kind": "terminal"}))
        self.assertEqual((b.row(TX)["owners"], b.row(TX)["origin"]), (["@machine"], {"kind": "terminal"}),
                         "a member with neither reads as the machine's own terminal session")
        # Owned by someone else: an older joined after it does not erase them.
        c = Machine(self, host="thirdhost")
        # Written raw, as that session's machine wrote them (a joined's provenance through
        # lifecycle is always this machine's record as it is).
        c.py("p = sminos.resolve_project(sys.argv[1]); sid = sys.argv[2]\n"
             "f = sminos.joined_fields('x', 'derived', sys.argv[1])\n"
             "sminos._append(p, sminos.writer_id(sid), [{'kind': 'joined', 'session': sid, **f,"
             " 'owners': [sys.argv[3]], 'origin': {'kind': 'maws', 'requester': sys.argv[3]}}])\n"
             "sminos._append(p, sminos.writer_id(sid), [{'kind': 'joined', 'session': sid, **f}])",
             str(c.repo), TB, MEMBER)
        d = Machine(self, host="fourthhost", project_from=c)
        c.copy_log_to(d)
        self.assertEqual(d.row(TB)["owners"], [MEMBER], "an older joined that publishes nothing never erases them")

    def test_a_move_leaves_the_record_as_it_is(self):
        m = Machine(self)
        other = m.dir / "other"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], env=m.env, check=True)
        r = subprocess.run([sys.executable, "-B", str(CLI), "project", "init", "--name", "elsewhere"], cwd=other,
                           env=m.env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        m.peer(T0, "mover")
        m.hook("SessionStart", T0)
        before = m.record_path(T0).read_bytes()
        m.cli("join", "elsewhere", env={"CLAUDE_CODE_SESSION_ID": T0})
        self.assertEqual(m.record_path(T0).read_bytes(), before)

    def test_the_record_survives_a_restart_and_a_reload(self):
        m = Machine(self)
        sid = m.spawn("durable", env={"SMINOS_DESK_MEMBER": MEMBER})
        before = m.record_path(sid).read_bytes()
        m.cli("daemon", "tick")
        m.peer(sid, "durable", kind="bg")
        m.py("import sminos_records as R\nR.write_pending(sys.argv[1], R.default_provenance())", "e" * 32)
        m.hook("SessionStart", sid, env={"SMINOS_LAUNCH": "e" * 32})   # a /reload-plugins' hooks, say
        m.hook("SessionStart", sid, source="resume")
        m.cli("daemon", "tick")
        m.rows()
        self.assertEqual(m.record_path(sid).read_bytes(), before)

    def test_inline_settings_never_reach_the_record_under_the_default_home(self):
        m = Machine(self, default_home=True)
        self.assertNotIn("SMINOS_HOME", m.env)
        sid = m.spawn("inline", "--settings", json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": SECRET}}))
        rec = m.record(sid)
        self.assertIsNotNone(rec, "written under the default home")
        ref = rec["inference"]["settingsRef"]
        self.assertTrue(ref.startswith(str(m.home / ".claude" / "sminos" / "settings") + "/"), ref)
        for p in glob.glob(str(m.reg / "session-records" / "**" / "*.json"), recursive=True):
            self.assertNotIn(SECRET, Path(p).read_text(), p)
        merged = jload(ref)
        self.assertRegex(merged["env"]["SMINOS_LAUNCH"], r"^[0-9a-f]{32}$")
        self.assertEqual(os.stat(ref).st_mode & 0o777, 0o600)

    def test_an_operators_spawn(self):
        m = Machine(self)
        sid = m.spawn("byhand")
        rec = m.record(sid)
        self.assertEqual((rec["owners"], rec["principal"], rec["origin"], rec["source"]),
                         (["@machine"], "@machine", {"kind": "sminos-spawn"}, "launch"))
        self.assertEqual(rec["inference"], slot(m))


class TheFixes(unittest.TestCase):
    """Fix 2 of the review: the launch's binding, precedence, publication, the org's view."""

    def test_a_claim_the_lock_held_up_cannot_be_stolen_by_a_descendant(self):
        m = Machine(self)
        launch = "a" * 32
        m.py("import sminos_records as R\nR.write_pending(sys.argv[1], dict(R.default_provenance('launch'), "
             "owners=[sys.argv[2]], principal=sys.argv[2], origin={'kind': 'maws', 'requester': sys.argv[2]}))",
             launch, MEMBER)
        lock = m.reg / "session-records" / ".lock"
        with open(lock, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            m.hook("SessionStart", TD, env={"SMINOS_LAUNCH": launch, "SMNS_RECORD_TIMEOUT": "1"})
            fcntl.flock(lf, fcntl.LOCK_UN)
        self.assertEqual(len(m.pending()), 1, "the lock held the seat's claim off")
        bound = (m.reg / "session-records" / "pending" / (launch + ".session")).read_text().strip()
        self.assertEqual(bound, TD, "but its SessionStart bound the launch to it, taking no lock")
        # The spawner is gone; the seat's Bash starts a `claude` that inherits the variable.
        m.peer(TX, "descendant")
        m.hook("SessionStart", TX, env={"SMINOS_LAUNCH": launch, "CLAUDE_CODE_SESSION_ID": TX})
        self.assertEqual(len(m.pending()), 1, "the descendant claims nothing")
        self.assertEqual((m.record(TX)["origin"], m.record(TX)["owners"]), ({"kind": "terminal"}, ["@machine"]))
        m.py("import sminos_records as R\nprint(R.bind(sys.argv[1], sys.argv[2]))", launch, TX)
        self.assertEqual(len(m.pending()), 1, "nor does a spawner naming another session")
        # The seat's next hook claims it.
        m.hook("Stop", TD, source="", env={"SMINOS_LAUNCH": launch})
        self.assertEqual(m.pending(), [])
        rec = m.record(TD)
        self.assertEqual((rec["owners"], rec["source"], rec["basis"]), ([MEMBER], "launch", "launch"))

    def test_a_provisional_intermediate_never_hides_a_final_ancestor(self):
        m = Machine(self)
        m.write_record(T0, owners=[MEMBER], principal=MEMBER, origin={"kind": "maws", "requester": MEMBER})
        m.write_record(TB, source="default", basis="lineage", former=[T0])
        m.continued(T0, TB)
        m.continued(TB, TX)
        m.peer(TX, "grandchild", kind="bg", name_source="auto")
        m.transcript(TX)
        m.rows()
        rec = m.record(TX)
        self.assertEqual((rec["owners"], rec["source"], rec["former"]), ([MEMBER], "lineage", [TB, T0]))

    def test_a_claimed_spawn_keeps_its_launch_against_the_hook(self):
        m = Machine(self)
        launch = "b" * 32
        m.py("import sminos_records as R\nR.write_pending(sys.argv[1], dict(R.default_provenance(), basis='launch', "
             "origin={'kind': 'sminos-spawn', 'spawnerSession': sys.argv[2]}, "
             "inference={'kind': 'route', 'settingsRef': '/x/settings.json'}))", launch, T0)
        m.peer(TD, "seatless")   # no seat binds it: its seat record lost, say
        m.hook("SessionStart", TD, env={"SMINOS_LAUNCH": launch})
        before = m.record(TD)
        self.assertEqual((before["origin"]["kind"], before["source"], before["basis"]),
                         ("sminos-spawn", "default", "launch"), "claimed, provisional as its parent was")
        m.hook("Stop", TD, source="", env={"SMINOS_LAUNCH": launch})
        m.hook("Stop", TD, source="")
        m.rows()
        self.assertEqual(m.record(TD), before, "the hook's evidence never replaces a launch's")

    def test_a_job_whose_hook_ran_before_its_hand_off_takes_its_lineage(self):
        a = Machine(self)
        a.write_record(T0, owners=[MEMBER], principal=MEMBER, origin={"kind": "maws", "requester": MEMBER})
        a.peer(TB, "job", kind="bg", name_source="auto")
        a.hook("SessionStart", TB)
        self.assertEqual((a.record(TB)["source"], a.publications(TB)), ("hook", [{"origin": {"kind": "terminal"}}]))
        a.continued(T0, TB)   # the hand-off recorded after the job's hook
        a.rows()
        rec = a.record(TB)
        self.assertEqual((rec["owners"], rec["source"], rec["former"]), ([MEMBER], "lineage", [T0]),
                         "lineage outranks the hook")
        self.assertEqual(a.publications(TB), [{"origin": {"kind": "terminal"}},
                                              {"owners": [MEMBER], "origin": {"kind": "maws", "requester": MEMBER}}],
                         "and the replacement is published")
        b = Machine(self, host="otherhost", project_from=a)
        a.copy_log_to(b)
        self.assertEqual(b.row(TB)["owners"], [MEMBER], "another machine reads the latest publication")
        # Equal evidence never flips it back: a second lineage read with other owners, a second hook.
        a.write_record(T0, owners=[OTHER], principal=OTHER, origin={"kind": "maws", "requester": OTHER})
        a.rows()
        a.hook("Stop", TB, source="")
        self.assertEqual(a.record(TB), rec)
        self.assertEqual(len(a.publications(TB)), 2, "nothing more to publish")
        a.assert_private()

    def test_a_publication_that_failed_is_made_on_the_next_pass(self):
        m = Machine(self)
        m.peer(T0, "late")
        m.transcript(T0)
        m.rows()
        self.assertEqual((m.record(T0)["source"], m.publications(T0)), ("default", []))
        m.py("p = sminos.resolve_project(sys.argv[1])\n"
             "real = sminos._append\n"
             "def failing(*a, **k):\n    raise OSError('injected: the log is unwritable')\n"
             "sminos._append = failing\n"
             "sminos.ensure_record(p, sys.argv[2], evidence=sminos.records_module().hook_provenance(False))\n"
             "sminos._append = real",
             str(m.repo), T0)
        self.assertEqual((m.record(T0)["source"], m.publications(T0)), ("hook", []),
                         "final, its publication lost to the append")
        m.py("sminos.ensure_record(sminos.resolve_project(sys.argv[1]), sys.argv[2])", str(m.repo), T0)
        self.assertEqual(m.publications(T0), [{"origin": {"kind": "terminal"}}], "published on the next pass")
        m.rows()
        self.assertEqual(len(m.publications(T0)), 1, "once")

    def test_a_records_own_publication_is_no_lineage(self):
        """hook, reconcile, reconcile, hand-off, reconcile: the job's own
        publication never promotes its record, so the hand-off still can."""
        m = Machine(self)
        m.write_record(T0, owners=[MEMBER], principal=MEMBER, origin={"kind": "maws", "requester": MEMBER})
        m.peer(TB, "job", kind="bg", name_source="auto")
        m.hook("SessionStart", TB)
        hooked = m.record(TB)
        m.rows()
        m.rows()
        self.assertEqual(m.record(TB), hooked, "its own publication is not evidence")
        m.continued(T0, TB)
        m.rows()
        rec = m.record(TB)
        self.assertEqual((rec["owners"], rec["source"], rec["former"]), ([MEMBER], "lineage", [T0]))
        self.assertEqual(m.publications(TB)[-1], {"owners": [MEMBER], "origin": {"kind": "maws", "requester": MEMBER}})

    def test_a_writer_that_paused_never_appends_older_provenance(self):
        """A joined prepared from the hook's record, held up before the
        file's lock while another writer replaces the record with a launch's
        and publishes it: what it appends is the record as it is then."""
        m = Machine(self)
        m.peer(T0, "racer")
        m.hook("SessionStart", T0)
        self.assertEqual(m.publications(T0), [{"origin": {"kind": "terminal"}}])
        out = m.py(r"""
import json, sminos_records as R
p = sminos.resolve_project(sys.argv[1]); sid = sys.argv[2]; member = sys.argv[3]
real = sminos._append
def the_other_writer():
    rec = R.read(sid)
    rec.update(basis="launch", source="launch", owners=[member], principal=member,
               origin={"kind": "maws", "requester": member})
    sminos._write_record(R.record_path(sid), rec)
    sminos.publish_owners(p, sid)
# 1. publish_owners itself: it read the hook's provenance, then pauses before the lock.
stale = sminos.published_provenance(sid)
R.establish(sid, dict(R.default_provenance("lineage"), origin={"kind": "sminos-spawn"}))  # what it will publish
calls = []
def paused(*a, **k):
    if not calls:
        calls.append(1)
        sminos._append = real
        the_other_writer()
    return real(*a, **k)
sminos._append = paused
sminos.publish_owners(p, sid)
sminos._append = real
# 2. any joined writer: fields prepared before the lock, the record replaced meanwhile.
fields = sminos.joined_fields("racer", "derived", sys.argv[1], session=sid)
rec = R.read(sid); rec["owners"] = ["f" * 32]; rec["origin"] = {"kind": "maws", "requester": "f" * 32}
sminos._write_record(R.record_path(sid), rec)
sminos.lifecycle(p, sid, "joined", required=False, **fields)
print(json.dumps(stale))
""", str(m.repo), T0, MEMBER)
        self.assertEqual(json.loads(out), {"origin": {"kind": "terminal"}})
        pubs = m.publications(T0)
        self.assertEqual(pubs[-2:], [{"owners": [MEMBER], "origin": {"kind": "maws", "requester": MEMBER}},
                                     {"owners": ["f" * 32], "origin": {"kind": "maws", "requester": "f" * 32}}],
                         "the paused publisher appended nothing older; the other writer's joined carried the record "
                         "as it was under the lock")
        self.assertNotIn({"origin": {"kind": "sminos-spawn"}}, pubs)
        self.assertEqual(len(pubs), 3)

    def test_a_current_publication_costs_no_scan(self):
        m = Machine(self)
        for i, sid in enumerate((T0, TB, TX)):
            m.peer(sid, "m%d" % i)
            m.hook("SessionStart", sid)
        out = m.py(r"""
p = sminos.resolve_project(sys.argv[1])
events = sminos.log_read(p)
scans = []
real = sminos.own_events_of
sminos.own_events_of = lambda *a, **k: scans.append(a[1]) or real(*a, **k)
for sid in sys.argv[2:]:
    sminos.ensure_record(p, sid, events=events)
print(len(scans))
""", str(m.repo), T0, TB, TX)
        self.assertEqual(out.strip(), "0", "members whose publication is current are told from the index")

    def test_the_orgs_listing_carries_no_private_field(self):
        m = Machine(self)
        m.peer(T0, "mine")
        m.hook("SessionStart", T0)
        rows = [r for r in json.loads(m.cli("list", "--org", "--json").stdout) if r.get("session") == T0]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["local"])
        for k in ("principal", "inference", "controller"):
            self.assertNotIn(k, rows[0])
        self.assertEqual((rows[0]["owners"], rows[0]["origin"]), (["@machine"], {"kind": "terminal"}))
        self.assertIn("principal", m.row(T0), "the project's own listing keeps them")


class TheStore(unittest.TestCase):
    """sminos_records in process, against a temporary registry."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sminos-rec-store-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        saved = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(saved)))
        for k in [k for k in os.environ if k.startswith(("SMINOS_", "DAEMON_", "AGORA_"))]:
            del os.environ[k]
        os.environ["SMINOS_HOME"] = self.dir
        os.environ["HOME"] = self.dir
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import sminos_records
        self.R = sminos_records

    def test_the_controller_changes_and_provenance_does_not(self):
        R = self.R
        self.assertFalse(R.set_controller(T0, "B"), "no record, nothing written")
        self.assertIsNone(R.read(T0))
        rec, changed = R.establish(T0, R.default_provenance(source="hook"))
        self.assertTrue(changed)
        self.assertEqual(rec["basis"], "hook")
        before = {k: v for k, v in rec.items()}
        self.assertTrue(R.set_controller(T0, "B", since="2026-10-27T00:00:00Z"))
        after = R.read(T0)
        self.assertEqual(after["controller"], {"lane": "B", "since": "2026-10-27T00:00:00Z"})
        self.assertEqual({k: v for k, v in after.items() if k != "controller"}, before)
        self.assertTrue(R.set_controller(T0, "A"))
        self.assertEqual(R.read(T0)["controller"]["lane"], "A")
        self.assertTrue(R.read(T0)["controller"]["since"].endswith("Z"))
        with self.assertRaises(ValueError):
            R.set_controller(T0, "C")
        # Replaced only by strictly stronger evidence: a second hook's changes nothing.
        again, changed = R.establish(T0, dict(R.default_provenance(source="hook"), origin={"kind": "maws"}))
        self.assertFalse(changed)
        self.assertEqual(again["origin"], {"kind": "terminal"})

    def test_a_provisional_record_is_replaced_by_final_evidence_keeping_its_controller(self):
        R = self.R
        R.establish(T0, R.default_provenance())
        R.set_controller(T0, "A", since="2026-10-27T00:00:00Z")
        rec, changed = R.establish(T0, R.default_provenance())
        self.assertFalse(changed, "provisional over provisional changes nothing")
        rec, changed = R.establish(T0, dict(R.default_provenance(source="lineage"), owners=[MEMBER]))
        self.assertTrue(changed)
        self.assertEqual((rec["owners"], rec["source"]), ([MEMBER], "lineage"))
        self.assertEqual(rec["controller"], {"lane": "A", "since": "2026-10-27T00:00:00Z"})

    def test_replacement_is_strictly_upward(self):
        R = self.R
        lineage = dict(R.default_provenance(source="lineage"), owners=[MEMBER])
        R.establish(T0, R.default_provenance(source="hook"))
        self.assertTrue(R.establish(T0, lineage)[1], "lineage outranks the hook")
        self.assertFalse(R.establish(T0, dict(lineage, owners=[OTHER]))[1], "a second lineage read never flips it")
        self.assertFalse(R.establish(T0, R.default_provenance(source="hook"))[1], "nor does a hook")
        self.assertFalse(R.establish(T0, R.default_provenance())[1])
        self.assertEqual(R.read(T0)["owners"], [MEMBER])
        launched = dict(R.default_provenance(source="launch"), owners=[OTHER])
        self.assertTrue(R.establish(T0, launched)[1], "a launch outranks a lineage")
        provisional = dict(R.default_provenance(), basis="lineage")
        self.assertFalse(R.establish(T0, provisional)[1])
        # A provisional launch (a spawn of a provisional parent) is never replaced by a final lineage or hook.
        R.establish(TB, dict(R.default_provenance(), basis="launch", origin={"kind": "sminos-spawn"}))
        self.assertFalse(R.establish(TB, lineage)[1])
        self.assertFalse(R.establish(TB, R.default_provenance(source="hook"))[1])
        self.assertEqual(R.read(TB)["origin"], {"kind": "sminos-spawn"})
        self.assertEqual(R.strength(R.read(TB)), (3, False))

    def test_pending_launches_older_than_a_day_are_swept(self):
        R = self.R
        R.write_pending("a" * 32, R.default_provenance())
        R.write_pending("b" * 32, R.default_provenance())
        R.bind("a" * 32, T0)
        old = time.time() - 2 * 86400
        os.utime(R.pending_path("a" * 32), (old, old))
        os.utime(R.binding_path("a" * 32), (old, old))
        self.assertEqual(R.sweep_pending(), ["a" * 32])
        self.assertFalse(os.path.exists(R.pending_path("a" * 32)))
        self.assertFalse(os.path.exists(R.binding_path("a" * 32)), "and its binding")
        self.assertTrue(os.path.exists(R.pending_path("b" * 32)))

    def test_a_claim_is_one_rename(self):
        R = self.R
        R.write_pending("c" * 32, dict(R.default_provenance(source="launch"), owners=[MEMBER]))
        self.assertEqual(os.stat(R.pending_path("c" * 32)).st_mode & 0o777, 0o600)
        self.assertIsNone(R.claim("c" * 32, T0), "an unbound launch is claimed by no one")
        self.assertEqual(R.bind("c" * 32, T0), T0)
        self.assertEqual(R.bind("c" * 32, TB), T0, "the first session to bind it keeps it")
        self.assertEqual(os.stat(R.binding_path("c" * 32)).st_mode & 0o777, 0o600)
        got = R.claim("c" * 32, T0)
        self.assertEqual((got["session"], got["owners"], got["source"]), (T0, [MEMBER], "launch"))
        self.assertIsNone(R.claim("c" * 32, TB), "another session is refused")
        self.assertIsNone(R.read(TB))
        R.write_pending("d" * 32, R.default_provenance(source="launch"))
        R.bind("d" * 32, T0)
        self.assertIsNone(R.claim("d" * 32, T0), "a session a launch established claims nothing more")
        self.assertTrue(os.path.exists(R.pending_path("d" * 32)))
        self.assertIsNone(R.claim("../x", T0))

    def test_owners_never_mix_the_machine_with_members(self):
        R = self.R
        mixed = dict(R.default_provenance(source="launch"), owners=["@machine", MEMBER])
        with self.assertRaises(ValueError):
            R.establish(T0, mixed)
        self.assertIsNone(R.read(T0))
        with self.assertRaises(ValueError):
            R.write_pending("e" * 32, mixed)
        self.assertFalse(os.path.exists(R.pending_path("e" * 32)))
        R.establish(T0, R.default_provenance())
        with self.assertRaises(ValueError):
            R.establish(T0, dict(mixed, source="lineage"))
        self.assertEqual(R.read(T0)["owners"], ["@machine"], "a provisional record is not replaced by a mixed list")
        for bad in ([], ["@machine", "@machine"], [""], "@machine"):
            with self.assertRaises(ValueError):
                R.checked_owners(bad)
        self.assertEqual(R.checked_owners([MEMBER, "f" * 32]), [MEMBER, "f" * 32])
        # A pending file this code never wrote: the claim stands, its owners do not.
        os.makedirs(os.path.dirname(R.pending_path("a" * 32)), exist_ok=True)
        with open(R.pending_path("a" * 32), "w") as f:
            json.dump(mixed, f)
        R.bind("a" * 32, TB)
        got = R.claim("a" * 32, TB)
        self.assertEqual((got["owners"], got["source"]), (["@machine"], "default"))

    def test_base_url_routes(self):
        R = self.R
        self.assertEqual(R.base_url_ref("http://127.0.0.1:8787"), "base-url:http://127.0.0.1:8787")
        self.assertEqual(R.base_url_ref("https://[::1]:9/p"), "base-url:https://[::1]:9")
        self.assertEqual(R.base_url_ref("https://gw.example.com/path?token=x"), "base-url:https://gw.example.com")
        self.assertIsNone(R.base_url_ref("not a url"))


if __name__ == "__main__":
    unittest.main()
