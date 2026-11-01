#!/usr/bin/env python3
"""The session manager's page (sminos/skills/manager/scripts/manager_serve.py): `manager serve`, its identity
check, `/ledger.json`, `/events`, its restart on new code, and `--install` / `--status`.

The server runs as a child process on a random local port, in a temporary HOME and SMINOS_HOME, under an audit
hook that records (and refuses) any subprocess or outbound connection it attempts. `tailscale` and `launchctl` are
stubs on PATH that log their arguments; nothing here runs the real ones or writes under the real
~/Library/LaunchAgents.

Run: python3 -B sminos/tests/test_manager_serve.py
"""
import http.client
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
SCRIPTS = PLUGIN / "skills" / "sminos" / "scripts"
SKILL = PLUGIN / "skills" / "manager"
MANAGER_PY = SKILL / "scripts" / "manager.py"
BASE = tempfile.mkdtemp(prefix="smms.", dir="/tmp")
for var in ("SMINOS_RL10", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "SMNS_MEMBER", "SMNS_INTERNAL",
            "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(var, None)
FAKE_BIN = os.path.join(BASE, "fake-bin")
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), DAEMON_HOST="testhost",
                  PATH=FAKE_BIN + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
                  STUB_LOG=os.path.join(BASE, "stub.log"))
os.makedirs(os.environ["HOME"])
os.makedirs(FAKE_BIN)
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SKILL / "scripts"))

import manager_ledger as L  # noqa: E402

OWNER = "owner@github"
DNS = "mac.tail0000.ts.net"

# The stubs: each logs its argv as one JSON line to $STUB_LOG and answers from files the test writes.
STUB = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["STUB_LOG"], "a") as f:
    f.write(json.dumps([os.path.basename(sys.argv[0])] + sys.argv[1:]) + "\\n")
name, argv = os.path.basename(sys.argv[0]), sys.argv[1:]
answer = os.path.join(os.environ.get("STUB_DIR", ""), "%s %s" % (name, " ".join(a for a in argv if not a.startswith("gui/"))))
if os.path.exists(answer):
    sys.stdout.write(open(answer).read())
    sys.exit(0)
sys.stderr.write("%s: stub has no answer for %s\\n" % (name, argv))
sys.exit(1)
"""
for _name in ("tailscale", "launchctl"):
    with open(os.path.join(FAKE_BIN, _name), "w") as _f:
        _f.write(STUB)
    os.chmod(os.path.join(FAKE_BIN, _name), 0o755)

# Runs a script under an audit hook: any subprocess, exec, fork or outbound connection is written to the log
# named first and refused.
GUARD = os.path.join(BASE, "guard.py")
with open(GUARD, "w") as _f:
    _f.write("""import os, runpy, sys
log, script = sys.argv[1], sys.argv[2]
BANNED = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
          "socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.sendto")
def hook(event, args):
    if event in BANNED:
        with open(log, "a") as f:
            f.write("%s %r\\n" % (event, args[:2]))
        raise RuntimeError("refused by the test: " + event)
sys.addaudithook(hook)
sys.argv = [script] + sys.argv[3:]
sys.path[0] = os.path.dirname(os.path.realpath(script))
runpy.run_path(script, run_name="__main__")
""")
# `--install` writes a launchd agent and refuses off macOS; the CI runs Linux, so the install's tests run the CLI
# with sys.platform reading darwin (the standard modules that branch on it at import are imported first).
AS_MAC = os.path.join(BASE, "as_mac.py")
with open(AS_MAC, "w") as _f:
    _f.write("import os, runpy, sys, subprocess, json, urllib.request\nsys.platform = 'darwin'\nscript = sys.argv[1]\nsys.argv = sys.argv[1:]\n"
             "sys.path[0] = os.path.dirname(os.path.realpath(script))\n"
             "runpy.run_path(script, run_name='__main__')\n")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stub_dir(answers):
    """A fresh directory of stub answers: {"tailscale status --json": text, ...}."""
    d = tempfile.mkdtemp(dir=BASE)
    for k, v in answers.items():
        with open(os.path.join(d, k), "w") as f:
            f.write(v)
    return d


def stub_calls():
    try:
        with open(os.environ["STUB_LOG"]) as f:
            return [json.loads(line) for line in f]
    except FileNotFoundError:
        return []


def ts_status(tags=None, state="Running"):
    me = {"ID": "n1", "UserID": 42, "DNSName": DNS + ".", "HostName": "mac"}
    if tags:
        me["Tags"] = tags
    return json.dumps({"BackendState": state, "Self": me,
                       "User": {"42": {"ID": 42, "LoginName": OWNER}, "7": {"ID": 7, "LoginName": "other@github"}}})


def write_settings(name, port, owner=OWNER):
    os.makedirs(os.path.join(os.environ["SMINOS_HOME"], "managers"), exist_ok=True)
    with open(os.path.join(os.environ["SMINOS_HOME"], "managers", name + ".serve.json"), "w") as f:
        json.dump({"port": port, "https_port": port, "owner": owner}, f)


def manager(*args, env=None, script=MANAGER_PY, as_mac=False):
    argv = [sys.executable, "-B"] + ([AS_MAC] if as_mac else []) + [str(script)] + list(args)
    return subprocess.run(argv, capture_output=True, text=True, env=env or os.environ.copy(), timeout=60)


def apply_doc(title):
    return {"window": {"since": "2026-11-01T00:00:00Z", "until": "2026-11-01T01:00:00Z"},
            "items": [{"lane": "work", "initiative": "P5", "title": title, "meaning": "it matters",
                       "status": "in progress", "started": "2026-11-01T00:10:00Z"}]}


class Server:
    """`manager serve` in a child process, under the audit guard unless `guarded` is false."""

    def __init__(self, name, script=MANAGER_PY, guarded=True):
        self.name, self.port = name, free_port()
        write_settings(name, self.port)
        self.violations = os.path.join(BASE, "violations-%s.log" % name)
        self.err = open(os.path.join(BASE, "serve-%s.err" % name), "w+")
        pre = [GUARD, self.violations] if guarded else []
        self.proc = subprocess.Popen([sys.executable, "-B"] + pre + [str(script), "serve", "--name", name],
                                     stdout=subprocess.DEVNULL, stderr=self.err)
        self.wait_up()

    def wait_up(self, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if self.proc.poll() is not None:
                raise AssertionError("manager serve exited %s: %s" % (self.proc.returncode, self.stderr()))
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.5).close()
                return
            except OSError:
                time.sleep(0.1)
        raise AssertionError("manager serve did not listen: %s" % self.stderr())

    def stderr(self):
        self.err.flush()
        with open(self.err.name) as f:
            return f.read()

    def request(self, path, method="GET", login=OWNER, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        if login is not None:
            h["Tailscale-User-Login"] = login
        c.request(method, path, headers=h)
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, dict(r.getheaders()), body

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.err.close()


class EventStream:
    """A raw connection to /events: the response's lines as they arrive."""

    def __init__(self, port, login=OWNER):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        self.sock.sendall(("GET /events HTTP/1.1\r\nHost: x\r\nTailscale-User-Login: %s\r\n\r\n" % login).encode())
        self.buf = b""

    def read_for(self, seconds):
        """Everything that arrives within `seconds`."""
        end, got = time.time() + seconds, b""
        while time.time() < end:
            self.sock.settimeout(max(0.05, end - time.time()))
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            got += chunk
        self.buf += got
        return got.decode()

    def close(self):
        self.sock.close()


def seed_state(name):
    L.save(name, L.normalize({}))


def mirror_tree(root):
    """The plugin's two script directories and the page, copied into `root` in the layout manager.py resolves
    (skills/manager/scripts beside skills/sminos/scripts): its manager.py."""
    ignore = shutil.ignore_patterns("__pycache__")
    shutil.copytree(SCRIPTS, os.path.join(root, "skills", "sminos", "scripts"), ignore=ignore)
    for part in ("scripts", "assets", "references"):
        shutil.copytree(SKILL / part, os.path.join(root, "skills", "manager", part), ignore=ignore)
    return Path(root) / "skills" / "manager" / "scripts" / "manager.py"


class Serving(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_state("page")
        cls.server = Server("page")

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_the_owners_login_alone_gets_in(self):
        s = self.server
        self.assertEqual(s.request("/", login=None)[0], 403)              # a direct local request: no header
        self.assertEqual(s.request("/ledger.json", login=None)[0], 403)
        status, _, body = s.request("/", login="other@github")
        self.assertEqual(status, 403)
        self.assertEqual(body.decode().count("\n"), 1)                    # a one-line body
        self.assertEqual(s.request("/", login=OWNER.upper())[0], 403)     # exact, not case-folded
        self.assertEqual(s.request("/", login="")[0], 403)
        self.assertEqual(s.request("/")[0], 200)
        self.assertEqual(s.request("/ledger.json")[0], 200)

    def test_two_identity_headers_are_refused(self):
        c = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=10)
        c.putrequest("GET", "/")
        c.putheader("Tailscale-User-Login", OWNER)
        c.putheader("Tailscale-User-Login", "other@github")
        c.endheaders()
        self.assertEqual(c.getresponse().status, 403)
        c.close()

    def test_the_page_is_the_assets_file(self):
        status, headers, body = self.server.request("/")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertEqual(body, (SKILL / "assets" / "page.html").read_bytes())
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.server.request("/?x=1")[0], 200)            # a query string is the same page

    def test_ledger_json_is_manager_ledger_json(self):
        seed = apply_doc("Sessions can be asked questions without disturbing them")
        r = subprocess.run([sys.executable, "-B", str(MANAGER_PY), "ledger", "apply", "-", "--name", "page"],
                           input=json.dumps(seed), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        status, headers, body = self.server.request("/ledger.json")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        cli = manager("ledger", "--json", "--name", "page")
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertEqual(json.loads(body), json.loads(cli.stdout))
        self.assertEqual(json.loads(body)["initiatives"][0]["name"], "P5")

    def test_unknown_paths_404_and_other_methods_405(self):
        s = self.server
        self.assertEqual(s.request("/nope")[0], 404)
        self.assertEqual(s.request("/ledger.json/x")[0], 404)
        for method in ("POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "FROB"):
            status, headers, _ = s.request("/ledger.json", method=method)
            self.assertEqual(status, 405, method)
            self.assertEqual(headers.get("Allow"), "GET")
        self.assertEqual(s.request("/ledger.json", method="POST", login=None)[0], 403)   # identity is checked first

    def test_events_announce_an_apply_and_nothing_else(self):
        ev = EventStream(self.server.port)
        try:
            head = ev.read_for(2.5)
            self.assertIn("200", head.split("\r\n")[0])
            self.assertIn("text/event-stream", head)
            self.assertNotIn("event:", head)                              # the file did not change: nothing sent
            r = subprocess.run([sys.executable, "-B", str(MANAGER_PY), "ledger", "apply", "-", "--name", "page"],
                               input=json.dumps(apply_doc("Derive costs a seventh of what it did")),
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            applied = time.time()
            got = ""
            while "event: changed" not in got and time.time() - applied < 2:
                got += ev.read_for(0.1)
            self.assertIn("event: changed", got)
            self.assertLess(time.time() - applied, 2.0)
            self.assertIn("data: %s" % L.load("page")["updated"], got)
            self.assertNotIn("event:", ev.read_for(2.0))                  # and once only
        finally:
            ev.close()

    def test_events_need_the_owner_too(self):
        ev = EventStream(self.server.port, login="other@github")
        try:
            self.assertIn("403", ev.read_for(1.0).split("\r\n")[0])
        finally:
            ev.close()

    def test_zz_serving_started_no_process_and_opened_no_connection(self):
        # Runs last in this class (unittest orders by name): every request above went through the guarded server.
        self.assertEqual(self.server.request("/")[0], 200)
        self.assertFalse(os.path.exists(self.server.violations),
                         Path(self.server.violations).read_text() if os.path.exists(self.server.violations) else "")
        self.assertIsNone(self.server.proc.poll())

    def test_the_guard_catches_a_process(self):
        # The audit guard itself works: a script that starts a process is caught.
        probe, log = os.path.join(BASE, "probe.py"), os.path.join(BASE, "probe.log")
        with open(probe, "w") as f:
            f.write("import subprocess\ntry:\n    subprocess.run(['true'])\nexcept RuntimeError:\n    pass\n"
                    "import socket\ntry:\n    socket.socket().connect(('127.0.0.1', 9))\nexcept (RuntimeError, OSError):\n"
                    "    pass\n")
        subprocess.run([sys.executable, GUARD, log, probe], timeout=30)
        text = Path(log).read_text()
        self.assertIn("subprocess.Popen", text)
        self.assertIn("socket.connect", text)


class Foreground(unittest.TestCase):
    def test_serve_without_settings_says_to_install(self):
        r = manager("serve", "--name", "nosettings")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--install", r.stderr)

    def test_a_missing_state_serves_an_empty_ledger(self):
        s = Server("empty")
        try:
            status, _, body = s.request("/ledger.json")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["initiatives"], [])
        finally:
            s.stop()


class NewCode(unittest.TestCase):
    def test_new_scripts_restart_it_in_place_and_the_page_is_read_per_request(self):
        script = mirror_tree(tempfile.mkdtemp(dir=BASE))
        seed_state("code")
        s = Server("code", script=script, guarded=False)
        try:
            page = script.parent.parent / "assets" / "page.html"
            page.write_text("<!doctype html><title>first</title>")
            self.assertIn(b"first", s.request("/")[2])
            page.write_text("<!doctype html><title>second</title>")
            self.assertIn(b"second", s.request("/")[2])                   # no restart needed for the page
            self.assertNotIn("restarting", s.stderr())
            serve_py = script.parent / "manager_serve.py"
            serve_py.write_text(serve_py.read_text() + "\n# a plugin update\n")
            end = time.time() + 20
            while "restarting" not in s.stderr() and time.time() < end:
                time.sleep(0.2)
            self.assertIn("restarting", s.stderr())
            s.wait_up()
            self.assertEqual(s.request("/")[0], 200)
            self.assertIsNone(s.proc.poll())                              # the same process, executed again
        finally:
            s.stop()


class Install(unittest.TestCase):
    def setUp(self):
        open(os.environ["STUB_LOG"], "w").close()
        self.env = os.environ.copy()

    def plist(self, name="default"):
        return os.path.join(os.environ["HOME"], "Library", "LaunchAgents",
                            "com.doperpowers.sminos-manager.%s.plist" % name)

    def test_install_writes_the_agent_and_settings_and_runs_nothing(self):
        self.env["STUB_DIR"] = stub_dir({"tailscale status --json": ts_status()})
        r = manager("serve", "--install", "--port", "47555", env=self.env, as_mac=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        plist = self.plist()
        self.assertEqual(stat.S_IMODE(os.stat(plist).st_mode), 0o600)
        text = Path(plist).read_text()
        self.assertIn("<string>%s</string>" % sys.executable, text)
        self.assertIn("<string>%s</string>" % os.path.realpath(MANAGER_PY), text)
        self.assertIn("<string>serve</string>", text)
        self.assertIn("<string>com.doperpowers.sminos-manager.default</string>", text)
        self.assertIn("<key>RunAtLoad</key><true/>", text)
        self.assertIn("<key>KeepAlive</key><true/>", text)
        self.assertIn("<key>ThrottleInterval</key><integer>60</integer>", text)
        self.assertIn(os.path.join(os.environ["SMINOS_HOME"], "managers", "default.serve.log"), text)
        self.assertNotIn("{{", text)
        settings = os.path.join(os.environ["SMINOS_HOME"], "managers", "default.serve.json")
        self.assertEqual(stat.S_IMODE(os.stat(settings).st_mode), 0o600)
        self.assertEqual(json.loads(Path(settings).read_text()), {"port": 47555, "https_port": 47555, "owner": OWNER})
        self.assertIn("launchctl bootstrap gui/$(id -u) %s" % plist, r.stdout)
        self.assertIn("tailscale serve --bg --https=47555 http://127.0.0.1:47555", r.stdout)
        self.assertIn("https://%s:47555/" % DNS, r.stdout)
        self.assertEqual(stub_calls(), [["tailscale", "status", "--json"]])     # nothing loaded, nothing exposed

    def test_a_reinstall_keeps_the_ports_it_had(self):
        self.env["STUB_DIR"] = stub_dir({"tailscale status --json": ts_status()})
        self.assertEqual(manager("serve", "--install", "--name", "keep", "--port", "47600", env=self.env,
                                 as_mac=True).returncode, 0)
        r = manager("serve", "--install", "--name", "keep", env=self.env, as_mac=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        settings = os.path.join(os.environ["SMINOS_HOME"], "managers", "keep.serve.json")
        self.assertEqual(json.loads(Path(settings).read_text())["port"], 47600)

    def test_from_the_plugin_cache_it_runs_the_marketplace_clone(self):
        home = os.environ["HOME"]
        cached = mirror_tree(os.path.join(home, ".claude", "plugins", "cache", "doperpowers", "sminos", "9.9.9"))
        clone = os.path.join(BASE, "clone")
        stable = mirror_tree(os.path.join(clone, "sminos"))
        known = os.path.join(home, ".claude", "plugins", "known_marketplaces.json")
        with open(known, "w") as f:
            json.dump({"doperpowers": {"installLocation": clone}}, f)
        try:
            self.env["STUB_DIR"] = stub_dir({"tailscale status --json": ts_status()})
            r = manager("serve", "--install", "--name", "cached", env=self.env, script=cached, as_mac=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("<string>%s</string>" % stable, Path(self.plist("cached")).read_text())
            os.remove(stable)
            r = manager("serve", "--install", "--name", "cached2", env=self.env, script=cached, as_mac=True)
            self.assertEqual(r.returncode, 1)                             # never a path the next update deletes
            self.assertIn("marketplace clone", r.stderr)
            self.assertFalse(os.path.exists(self.plist("cached2")))
        finally:
            os.remove(known)

    def test_install_refuses_without_tailscale_or_on_a_tagged_node(self):
        for answers, word in (({}, "tailscale"),
                              ({"tailscale status --json": ts_status(state="Stopped")}, "not running"),
                              ({"tailscale status --json": ts_status(tags=["tag:devcloud"])}, "tagged")):
            self.env["STUB_DIR"] = stub_dir(answers)
            r = manager("serve", "--install", "--name", "refused", env=self.env, as_mac=True)
            self.assertEqual(r.returncode, 1, word)
            self.assertIn(word, r.stderr)
            self.assertFalse(os.path.exists(self.plist("refused")))
            self.assertFalse(os.path.exists(os.path.join(os.environ["SMINOS_HOME"], "managers",
                                                         "refused.serve.json")))

    def test_install_refuses_off_macos(self):
        if sys.platform == "darwin":
            self.skipTest("this is macOS")
        r = manager("serve", "--install", "--name", "linux")
        self.assertEqual(r.returncode, 1)
        self.assertIn("launchd", r.stderr)


class Status(unittest.TestCase):
    def setUp(self):
        open(os.environ["STUB_LOG"], "w").close()
        self.env = os.environ.copy()
        write_settings("st", 47700)

    def serve_status(self, port):
        return json.dumps({"TCP": {str(port): {"HTTPS": True}},
                           "Web": {"%s:%d" % (DNS, port): {"Handlers": {"/": {"Proxy": "http://127.0.0.1:%d" % port}}}}})

    def test_status_when_loaded_and_exposed(self):
        self.env["STUB_DIR"] = stub_dir({
            "tailscale status --json": ts_status(),
            "tailscale serve status --json": self.serve_status(47700),
            "launchctl print": "com.doperpowers.sminos-manager.st = {\n\tstate = running\n\tpid = 4242\n}\n"})
        r = manager("serve", "--status", "--name", "st", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("https://%s:47700/" % DNS, r.stdout)
        self.assertIn("running", r.stdout)
        self.assertIn("4242", r.stdout)
        j = json.loads(manager("serve", "--status", "--name", "st", "--json", env=self.env).stdout)
        self.assertEqual(j["address"], "https://%s:47700/" % DNS)
        self.assertTrue(j["launchd"]["loaded"])
        self.assertEqual(j["launchd"]["pid"], 4242)
        self.assertTrue(j["tailscale"]["mapped"])
        self.assertTrue(j["up"])
        self.assertIn(["launchctl", "print", "gui/%d/com.doperpowers.sminos-manager.st" % os.getuid()], stub_calls())

    def test_a_loaded_agent_that_is_not_running_is_not_up(self):
        self.env["STUB_DIR"] = stub_dir({
            "tailscale status --json": ts_status(),
            "tailscale serve status --json": self.serve_status(47700),
            "launchctl print": "com.doperpowers.sminos-manager.st = {\n\tstate = waiting\n\tlast exit code = 1\n}\n"})
        j = json.loads(manager("serve", "--status", "--name", "st", "--json", env=self.env).stdout)
        self.assertTrue(j["launchd"]["loaded"])
        self.assertFalse(j["launchd"]["running"])
        self.assertTrue(j["tailscale"]["mapped"])
        self.assertFalse(j["up"])
        text = manager("serve", "--status", "--name", "st", env=self.env).stdout
        self.assertIn("not running", text)
        self.assertIn("waiting", text)

    def test_status_when_neither(self):
        self.env["STUB_DIR"] = stub_dir({"tailscale status --json": ts_status(),
                                         "tailscale serve status --json": self.serve_status(47999)})
        r = manager("serve", "--status", "--name", "st", "--json", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        j = json.loads(r.stdout)
        self.assertFalse(j["launchd"]["loaded"])
        self.assertFalse(j["tailscale"]["mapped"])
        self.assertFalse(j["up"])
        text = manager("serve", "--status", "--name", "st", env=self.env).stdout
        self.assertIn("launchctl bootstrap", text)
        self.assertIn("tailscale serve --bg --https=47700 http://127.0.0.1:47700", text)

    def test_status_without_an_install(self):
        r = manager("serve", "--status", "--name", "never", "--json", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        j = json.loads(r.stdout)
        self.assertFalse(j["installed"])
        self.assertIsNone(j["address"])
        self.assertIn("--install", manager("serve", "--status", "--name", "never", env=self.env).stdout)

    def test_flags_that_do_not_go_together(self):
        self.assertEqual(manager("serve", "--status", "--install").returncode, 2)


class Page(unittest.TestCase):
    """The page's script in a Node VM over a stand-in DOM (page_check.mjs)."""

    def check(self, scenario):
        node = shutil.which("node")
        if not node:
            self.skipTest("no node on PATH")
        r = subprocess.run([node, str(HERE / "page_check.mjs"), str(SKILL / "assets" / "page.html"), scenario],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_an_update_during_a_fetch_is_fetched_after_it(self):
        got = self.check("refresh")
        self.assertEqual(got["errors"], [])
        self.assertEqual(got["fetches"], 2)          # the held fetch, then one for the update that landed meanwhile
        self.assertEqual(got["shown"], "new")


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(BASE, ignore_errors=True)
