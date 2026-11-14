#!/usr/bin/env python3
"""The panel server (to-human/panel/server.py): its command line, its requests, who may ask, what a page may do,
publishing, and its reach over the tailnet.

Each test has its own configuration directory, its own free port, and a stub `tailscale` and `sudo` first on PATH
(they log their calls and answer from files the test writes), so nothing here runs the real ones or reaches the
owner's ~/.claude or port 4777. A server the command line starts runs detached, as it does for a session; every
test stops its own.

Run: python3 -m unittest discover -s to-human/tests/panel
"""
import http.client
import importlib.util
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.dont_write_bytecode = True      # loading server.py must leave no __pycache__ in the plugin
HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[1]
PANEL = PLUGIN / "panel"
SERVER_PY = PANEL / "server.py"
BASE = PANEL / "base"
VERSION = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]

SID = "b4d10f41-4268-45ce-ad05-309f05c3ee48"
SHORT = SID[:8]
OTHER_SID = "b4d10f41-0000-0000-0000-000000000000"     # the same short id, another session
OWNER = "owner@github"
DNS = "mac.tail0000.ts.net"

ROOT = tempfile.mkdtemp(prefix="panel-tests.", dir="/tmp")
FAKE_BIN = os.path.join(ROOT, "bin")
os.makedirs(FAKE_BIN)

TAILSCALE = r'''#!/usr/bin/env python3
import json, os, sys, time
d = os.environ["STUB_DIR"]
args = sys.argv[1:]
with open(os.path.join(d, "calls.log"), "a") as f:
    f.write(json.dumps({"argv": args, "sudo": os.environ.get("STUB_SUDO") == "1"}) + "\n")
if os.path.exists(os.path.join(d, "stall")):
    time.sleep(30)
def answer(name, default=None):
    p = os.path.join(d, name)
    if os.path.exists(p):
        sys.stdout.write(open(p).read()); sys.exit(0)
    if default is None:
        sys.stderr.write("stub: no answer\n"); sys.exit(1)
    sys.stdout.write(default); sys.exit(0)
if args == ["status", "--json"]:
    answer("status.json")
if args == ["serve", "status", "--json"]:
    if os.path.exists(os.path.join(d, "serve-status-fails")):
        sys.stderr.write("stub: serve status failed\n"); sys.exit(1)
    if os.path.exists(os.path.join(d, "serve-status-stalls")):
        time.sleep(30)
    answer("serve.json", "{}")
if args[:2] == ["serve", "--bg"]:
    if os.path.exists(os.path.join(d, "needs-sudo")) and os.environ.get("STUB_SUDO") != "1":
        sys.stderr.write("Access denied: serve config denied\n"); sys.exit(1)
    port = args[2].split("=", 1)[1]
    with open(os.path.join(d, "serve.json"), "w") as f:
        json.dump({"TCP": {port: {"HTTPS": True}},
                   "Web": {"%s:%s" % (os.environ["STUB_DNS"], port): {"Handlers": {"/": {"Proxy": args[3]}}}}}, f)
    print("Available within your tailnet"); sys.exit(0)
sys.stderr.write("stub: unknown %r\n" % args); sys.exit(1)
'''
SUDO = '''#!/bin/sh
[ "$1" = -n ] || { echo "stub sudo: only -n" >&2; exit 1; }
shift
[ -e "$STUB_DIR/sudo-refused" ] && { echo "sudo: a password is required" >&2; exit 1; }
STUB_SUDO=1 exec "$@"
'''
for name, text in (("tailscale", TAILSCALE), ("sudo", SUDO)):
    with open(os.path.join(FAKE_BIN, name), "w") as f:
        f.write(text)
    os.chmod(os.path.join(FAKE_BIN, name), 0o755)


def ts_status(tagged=False, state="Running"):
    me = {"ID": "n1", "UserID": 42, "DNSName": DNS + ".", "HostName": "mac"}
    users = {"42": {"ID": 42, "LoginName": OWNER}, "7": {"ID": 7, "LoginName": "other@github"}}
    if tagged:
        me["Tags"] = ["tag:devcloud"]
        me["UserID"] = 99
        users["99"] = {"ID": 99, "LoginName": "tagged-devices"}
    return json.dumps({"BackendState": state, "Self": me, "User": users})


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def load_server():
    spec = importlib.util.spec_from_file_location("panel_server", SERVER_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Env:
    """One configuration directory, port and stub directory; the command line run against them."""

    def __init__(self, reach=None, tagged=False, needs_sudo=False, stall=False, tailscale="Running", script=SERVER_PY):
        self.dir = tempfile.mkdtemp(dir=ROOT)
        self.config = os.path.join(self.dir, "config")
        self.stub = os.path.join(self.dir, "stub")
        os.makedirs(self.config)
        os.makedirs(self.stub)
        self.port = free_port()
        self.script = script
        if tailscale:
            self.stub_file("status.json", ts_status(tagged=tagged, state=tailscale))
        if needs_sudo:
            self.stub_file("needs-sudo", "")
        if stall:
            self.stub_file("stall", "")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("PANEL_")}
        self.env.update(CLAUDE_CONFIG_DIR=self.config, PANEL_PORT=str(self.port), STUB_DIR=self.stub, STUB_DNS=DNS,
                        PATH=FAKE_BIN + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"))
        if reach:
            self.env["PANEL_REACH"] = reach

    @property
    def panels(self):
        return os.path.join(self.config, "to-human", "panels")

    def panel(self, *parts, short=SHORT):
        return os.path.join(self.panels, short, *parts)

    def stub_file(self, name, text):
        with open(os.path.join(self.stub, name), "w") as f:
            f.write(text)

    def calls(self):
        try:
            with open(os.path.join(self.stub, "calls.log")) as f:
                return [json.loads(line) for line in f]
        except FileNotFoundError:
            return []

    def cli(self, *args, script=None, env=None, timeout=30):
        return subprocess.run([sys.executable, str(script or self.script)] + list(args), capture_output=True,
                              text=True, env=env or self.env, timeout=timeout)

    def ok(self, *args, **kw):
        r = self.cli(*args, **kw)
        if r.returncode != 0:
            raise AssertionError("%s exited %d: %s" % (args, r.returncode, r.stderr))
        lines = r.stdout.strip().splitlines()
        assert len(lines) == 1, r.stdout
        return json.loads(lines[0])

    def open(self, session=SID, *extra, **kw):
        return self.ok("open-panel", "--session", session, *extra, **kw)

    def publish(self, session=SID, **kw):
        return self.ok("publish", "--session", session, **kw)

    def write_draft(self, body, short=SHORT, lang="en"):
        with open(self.panel("draft.html", short=short), "w") as f:
            f.write(page(body, lang))

    def server_json(self):
        with open(os.path.join(self.panels, "server.json")) as f:
            return json.load(f)

    def request(self, method, path, body=None, headers=None, host=None, ctype="application/json"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        h = {"Host": host or "127.0.0.1:%d" % self.port}
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            h["Content-Type"] = ctype
            h["Content-Length"] = str(len(data))
        h.update(headers or {})
        for k, v in h.items():
            for one in (v if isinstance(v, list) else [v]):
                c.putheader(k, one)
        c.endheaders(data)
        r = c.getresponse()
        out = r.read()
        c.close()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, out

    def control(self, method, path, body=None):
        return self.request(method, path, body, headers={"X-Panel-Token": self.server_json()["token"]})

    def stop(self):
        """Stop whatever server this directory started, and wait for the port to be free."""
        try:
            pid = self.server_json()["pid"]
        except (OSError, ValueError, KeyError):
            pid = None
        if pid:
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass
        wait_free(self.port)

    def close(self):
        self.stop()
        shutil.rmtree(self.dir, ignore_errors=True)


def wait_free(port, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        except OSError:
            return
        time.sleep(0.05)
    raise AssertionError("port %d still answers" % port)


def page(body, lang="en"):
    return ('<!doctype html>\n<html lang="%s">\n<head>\n<meta charset="utf-8">\n<title>T</title>\n'
            '<link rel="stylesheet" href="/base/panel.css">\n<script src="/base/panel.js" defer></script>\n'
            '</head>\n<body>\n%s\n</body>\n</html>\n' % (lang, body))


NOTE = '<p>The plan <mark data-note="u2-1">is B now</mark>.</p>\n<aside class="note" id="u2-1">Was A.</aside>'


class Case(unittest.TestCase):
    """A test with its own Env, closed at its end."""

    env_args = {}

    def setUp(self):
        self.e = Env(**self.env_args)
        self.addCleanup(self.e.close)


# ------------------------------------------------------------------ the command line

class CommandLine(Case):
    def test_open_panel_makes_a_panel_and_answers_open_panel(self):
        t0 = time.time()
        o = self.e.open()
        self.assertLess(time.time() - t0, 4.0)                                      # a cold start, in budget
        self.assertEqual(o["address"], "http://127.0.0.1:%d/%s/" % (self.e.port, SHORT))
        self.assertEqual(o["reach"], "local")
        self.assertEqual(os.path.realpath(o["dir"]), os.path.realpath(self.e.panel()))
        self.assertEqual(os.path.realpath(o["draft"]), os.path.realpath(self.e.panel("draft.html")))
        self.assertEqual(os.path.realpath(o["guide"]), os.path.realpath(BASE / "GUIDE.md"))
        self.assertEqual((o["update"], o["isNew"], o["locale"], o["seen"], o["checked"]), (1, True, "en", "never", []))
        self.assertEqual(Path(o["draft"]).read_text(), (BASE / "starter.html").read_text())
        meta = json.loads(Path(self.e.panel("meta.json")).read_text())
        self.assertEqual((meta["session"], meta["updates"], meta["locale"]), (SID, 1, "en"))
        state = json.loads(Path(self.e.panel("state.json")).read_text())
        self.assertEqual(state, {"seen": None, "written": None, "checked": []})

    def test_publish_of_the_starter_is_not_a_publish(self):
        self.e.open()
        p = self.e.publish()
        self.assertEqual(p["published"], False)
        self.assertEqual(p["written"], None)
        self.assertFalse(os.path.exists(self.e.panel("panel.html")))

    def test_publish_then_the_next_update_starts_from_the_page(self):
        self.e.open()
        self.e.write_draft("<h1>First</h1>")
        p = self.e.publish()
        self.assertTrue(p["published"])
        self.assertIsInstance(p["written"], int)
        self.assertEqual((p["removed"], p["lookedMeanwhile"]), ([], False))
        self.assertEqual(Path(self.e.panel("panel.html")).read_text(), page("<h1>First</h1>"))
        again = self.e.publish()                                                 # the draft is the page now
        self.assertEqual((again["published"], again["written"]), (False, p["written"]))
        o = self.e.open()
        self.assertEqual((o["update"], o["isNew"], o["seen"]), (2, False, "never"))
        self.assertEqual(Path(o["draft"]).read_text(), page("<h1>First</h1>"))

    def test_a_short_id_another_session_holds_is_refused(self):
        self.e.open()
        r = self.e.cli("open-panel", "--session", OTHER_SID)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
        self.assertIn(SHORT, r.stderr)
        self.assertEqual(json.loads(Path(self.e.panel("meta.json")).read_text())["session"], SID)

    def test_a_session_id_that_is_no_id_is_refused(self):
        for bad in ("short", "ZZZZZZZZ-1", "../../etc"):
            r = self.e.cli("open-panel", "--session", bad)
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_korean(self):
        o = self.e.open(SID, "--locale", "ko")
        self.assertEqual(o["locale"], "ko")
        self.assertIn('<html lang="ko">', Path(o["draft"]).read_text())
        # unpublished, the address says the panel is being written, in Korean
        status, _, body = self.e.request("GET", "/%s/" % SHORT)
        self.assertEqual(status, 200)
        self.assertIn('lang="ko"', body.decode())
        self.assertEqual(self.e.publish()["published"], False)                    # the Korean starter is unchanged

    def test_locale_from_the_environment(self):
        for value, want in (("korean", "ko"), ("KO", "ko"), ("English", "en"), ("fr", "en")):
            env = dict(self.e.env, PANEL_LOCALE=value)
            self.assertEqual(self.e.open(env=env)["locale"], want, value)

    def test_open_panel_drops_checks_of_notes_the_page_no_longer_holds(self):
        self.e.open()
        self.e.write_draft(NOTE + '\n<aside class="note" id="u2-2">Two.</aside>')
        self.e.publish()
        for note in ("u2-1", "u2-2"):
            self.assertEqual(self.e.request("POST", "/%s/check" % SHORT, {"note": note})[0], 204)
        self.assertEqual(self.e.open()["checked"], ["u2-1", "u2-2"])
        self.e.write_draft(NOTE)                                                  # u2-2 deleted by the fork
        self.e.publish()
        self.assertEqual(self.e.open()["checked"], ["u2-1"])
        state = json.loads(Path(self.e.panel("state.json")).read_text())
        self.assertEqual(state["checked"], ["u2-1"])

    @unittest.skipIf(os.geteuid() == 0, "root writes through any mode")
    def test_an_unwritable_configuration_directory_is_one_line(self):
        os.chmod(self.e.config, 0o500)
        self.addCleanup(os.chmod, self.e.config, 0o700)
        for args in (("open-panel", "--session", SID), ("serve",)):
            r = self.e.cli(*args)
            self.assertEqual(r.returncode, 1, args)
            self.assertEqual(r.stdout, "")
            self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn(self.e.config, r.stderr)

    def test_server_json_is_private(self):
        self.e.open()
        mode = stat.S_IMODE(os.stat(os.path.join(self.e.panels, "server.json")).st_mode)
        self.assertEqual(mode, 0o600)

    def test_ensure_starts_nothing_without_a_panel(self):
        r = self.e.cli("ensure")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "{}"))
        self.assertFalse(os.path.exists(os.path.join(self.e.panels, "server.json")))
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", self.e.port), timeout=0.5).close()

    def test_after_shutdown_ensure_brings_the_address_back(self):
        self.e.open()
        self.e.write_draft("<h1>Kept</h1>")
        self.e.publish()
        status, _, _ = self.e.control("POST", "/control/shutdown", {})
        self.assertEqual(status, 204)
        wait_free(self.e.port)
        self.assertEqual(self.e.ok("ensure"), {"address": "http://127.0.0.1:%d/" % self.e.port, "reach": "local"})
        status, _, body = self.e.request("GET", "/%s/" % SHORT)
        self.assertEqual(status, 200)
        self.assertIn(b"<h1>Kept</h1>", body)

    def test_the_server_outlives_the_command_and_its_process_group(self):
        self.e.open()
        pid = self.e.server_json()["pid"]
        self.assertNotEqual(os.getpgid(pid), os.getpgid(0))
        self.assertEqual(os.getsid(pid), os.getpgid(pid))                        # a session of its own

    def test_two_open_panels_on_a_cold_port(self):
        procs = [subprocess.Popen([sys.executable, str(SERVER_PY), "open-panel", "--session", sid],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.e.env)
                 for sid in (SID, "c0ffee00-1111-2222-3333-444444444444")]
        outs = [p.communicate(timeout=30) for p in procs]
        for p, (out, err) in zip(procs, outs):
            self.assertEqual(p.returncode, 0, err)
            self.assertEqual(json.loads(out)["update"], 1)
        pid = self.e.server_json()["pid"]
        status, _, body = self.e.control("GET", "/control/health")
        self.assertEqual(status, 200)
        time.sleep(0.5)
        self.assertEqual(self.e.server_json()["pid"], pid)                        # one server stands
        os.kill(pid, 0)

    def test_another_programs_port_is_an_error(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", self.e.port))
        sock.listen(5)
        stop = threading.Event()

        def answer():
            sock.settimeout(0.2)
            while not stop.is_set():
                try:
                    c, _ = sock.accept()
                except OSError:
                    continue
                c.recv(65536)
                c.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n<p>static</p>")
                c.close()

        t = threading.Thread(target=answer, daemon=True)
        t.start()
        try:
            r = self.e.cli("open-panel", "--session", SID)
        finally:
            stop.set()
            t.join()
            sock.close()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
        self.assertIn(str(self.e.port), r.stderr)

    def test_another_configuration_directorys_server_is_an_error(self):
        self.e.open()
        other = dict(self.e.env, CLAUDE_CONFIG_DIR=os.path.join(self.e.dir, "other-config"))
        r = self.e.cli("open-panel", "--session", SID, env=other)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.e.dir, "other-config", "to-human", "panels", SHORT)))

    def test_old_panels_are_removed_when_a_server_starts(self):
        old_sid = "0d0d0d0d-0000-0000-0000-000000000000"
        self.e.open()
        self.e.open(old_sid)
        self.e.stop()
        stale = time.time() - 31 * 86400
        old = self.e.panel(short=old_sid[:8])
        os.utime(os.path.join(old, "draft.html"), (stale, stale))
        half = self.e.panel()                                   # an old draft but a recent page: kept
        with open(self.e.panel("panel.html"), "w") as f:
            f.write("<p>x</p>")
        os.utime(os.path.join(half, "draft.html"), (stale, stale))
        self.e.ok("ensure")
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(half))


class Versions(unittest.TestCase):
    """The version rule: a server of a lower version is replaced, a higher one left alone."""

    def plugin_copy(self, version):
        root = tempfile.mkdtemp(dir=ROOT)
        shutil.copytree(PANEL, os.path.join(root, "panel"), ignore=shutil.ignore_patterns("__pycache__"))
        os.makedirs(os.path.join(root, ".claude-plugin"))
        with open(os.path.join(root, ".claude-plugin", "plugin.json"), "w") as f:
            json.dump({"name": "to-human", "version": version}, f)
        return os.path.join(root, "panel", "server.py")

    def setUp(self):
        self.e = Env()
        self.addCleanup(self.e.close)

    def health(self):
        status, _, body = self.e.control("GET", "/control/health")
        self.assertEqual(status, 200)
        return json.loads(body)

    def test_an_older_server_is_replaced(self):
        self.e.open(script=self.plugin_copy("0.0.1"))
        self.assertEqual(self.health()["version"], "0.0.1")
        old_pid = self.e.server_json()["pid"]
        self.e.open()
        h = self.health()
        self.assertEqual((h["server"], h["version"]), ("to-human-panel", VERSION))
        self.assertNotEqual(self.e.server_json()["pid"], old_pid)

    def test_a_newer_server_is_left_alone(self):
        self.e.open(script=self.plugin_copy("999.0.0"))
        pid = self.e.server_json()["pid"]
        self.e.open()
        self.assertEqual(self.health()["version"], "999.0.0")
        self.assertEqual(self.e.server_json()["pid"], pid)


# ------------------------------------------------------------------ the requests

class Requests(Case):
    def setUp(self):
        super().setUp()
        self.e.open()

    def get_page(self, **kw):
        return self.e.request("GET", "/%s/" % SHORT, **kw)

    def test_before_the_first_publish_the_page_says_it_is_being_written(self):
        status, h, body = self.get_page()
        self.assertEqual(status, 200)
        text = body.decode()
        self.assertIn("/base/panel.js", text)
        self.assertIn('window.PANEL={"written":null,"checked":[]}', text)
        self.assertEqual(json.loads(self.e.request("GET", "/%s/written" % SHORT)[2]), {"written": None})

    def test_the_page_carries_the_inserted_script_under_the_response_nonce(self):
        self.e.write_draft(NOTE)
        written = self.e.publish()["written"]
        self.e.request("POST", "/%s/check" % SHORT, {"note": "u2-1"})
        status, h, body = self.get_page()
        self.assertEqual(status, 200)
        self.assertTrue(h["content-type"].startswith("text/html"))
        nonce = re.search(r"'nonce-([^']+)'", h["content-security-policy"]).group(1)
        inserted = '<script nonce="%s">window.PANEL={"written":%d,"checked":["u2-1"]}</script>' % (nonce, written)
        self.assertEqual(body.decode(), page(NOTE).replace("</head>", inserted + "</head>"))
        self.assertNotEqual(nonce, re.search(r"'nonce-([^']+)'",
                                             self.get_page()[1]["content-security-policy"]).group(1))

    def test_a_page_without_a_head_gets_the_script_appended(self):
        with open(self.e.panel("draft.html"), "w") as f:
            f.write("<p>bare</p>")
        self.e.publish()
        body = self.get_page()[2].decode()
        self.assertTrue(body.startswith("<p>bare</p><script nonce="))
        self.assertTrue(body.endswith("</script>"))

    def test_the_inserted_json_escapes_lt(self):
        S = load_server()
        out = S.insert_script("<head></head>", 5, ["</script><script>alert(1)//"], "n")
        self.assertEqual(out, '<head><script nonce="n">window.PANEL={"written":5,"checked":'
                              '["\\u003c/script>\\u003cscript>alert(1)//"]}</script></head>')

    def test_every_response_holds_the_policy(self):
        self.e.write_draft("<p>x</p>")
        self.e.publish()
        for method, path in (("GET", "/%s/" % SHORT), ("GET", "/%s/written" % SHORT), ("GET", "/base/panel.css"),
                             ("GET", "/nowhere")):
            _, h, _ = self.e.request(method, path)
            csp = h["content-security-policy"]
            self.assertRegex(csp, r"^default-src 'none'; script-src http://127\.0\.0\.1:%d/base/ 'nonce-[A-Za-z0-9_-]+'; "
                                  r"style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
                                  r"base-uri 'none'; form-action 'none'; frame-ancestors 'none'$" % self.e.port, path)
            self.assertEqual(h["x-content-type-options"], "nosniff")
            self.assertEqual(h["referrer-policy"], "no-referrer")
            self.assertEqual(h["cache-control"], "no-store")
        _, h, _ = self.e.request("GET", "/%s/" % SHORT, host="localhost:%d" % self.e.port)
        self.assertIn("script-src http://localhost:%d/base/ " % self.e.port, h["content-security-policy"])

    def test_base_files(self):
        for name, kind in (("panel.css", "text/css"), ("panel.js", "text/javascript")):
            status, h, body = self.e.request("GET", "/base/" + name)
            self.assertEqual(status, 200)
            self.assertTrue(h["content-type"].startswith(kind), h["content-type"])
            self.assertEqual(body, (BASE / name).read_bytes())
        for bad in ("/base/", "/base/../server.py", "/base/%2e%2e/server.py", "/base/nope.css", "/base/.hidden"):
            self.assertEqual(self.e.request("GET", bad)[0], 404, bad)

    def test_nothing_of_a_panels_directory_but_the_page(self):
        self.e.write_draft("<p>x</p>")
        self.e.publish()
        for name in ("draft.html", "meta.json", "state.json", "panel.html", "../server.json"):
            self.assertEqual(self.e.request("GET", "/%s/%s" % (SHORT, name))[0], 404, name)
        self.assertEqual(self.e.request("GET", "/deadbeef/")[0], 404)              # no such panel
        self.assertEqual(self.e.request("POST", "/deadbeef/check", {"note": "u1-1"})[0], 404)

    def test_check(self):
        for note in ("u2-1", "u2-1", "u10-3"):
            self.assertEqual(self.e.request("POST", "/%s/check" % SHORT, {"note": note})[0], 204)
        state = json.loads(Path(self.e.panel("state.json")).read_text())
        self.assertEqual(state["checked"], ["u2-1", "u10-3"])
        for bad in ({"note": "r1-scope"}, {"note": "u2-1\n"}, {"note": "u2-"}, {"note": 3}, {}, [], "u2-1"):
            self.assertEqual(self.e.request("POST", "/%s/check" % SHORT, bad)[0], 400, bad)
        self.assertEqual(self.e.request("POST", "/%s/check" % SHORT, b"{not json")[0], 400)

    def test_a_look_names_the_publication_it_saw(self):
        self.e.write_draft("<p>one</p>")
        first = self.e.publish()["written"]
        self.e.open()
        self.e.write_draft("<p>two</p>")
        second = self.e.publish()["written"]
        self.assertGreater(second, first)
        # a late report from the page since replaced: the newer one stays unseen
        self.assertEqual(self.e.request("POST", "/%s/seen" % SHORT, {"written": first})[0], 204)
        self.assertEqual(self.e.open()["seen"], "stale")
        self.e.publish()
        self.assertEqual(self.e.request("POST", "/%s/seen" % SHORT, {"written": second})[0], 204)
        self.assertEqual(self.e.open()["seen"], "current")
        self.e.publish()
        # an older report after a newer one moves nothing back; a time no publication had is not recorded
        self.e.request("POST", "/%s/seen" % SHORT, {"written": first})
        self.e.request("POST", "/%s/seen" % SHORT, {"written": second + 10 ** 9})
        self.assertEqual(json.loads(Path(self.e.panel("state.json")).read_text())["seen"], second)
        self.assertEqual(self.e.request("POST", "/%s/seen" % SHORT, {"written": "x"})[0], 400)

    def test_a_first_look_while_the_page_is_rewritten(self):
        self.e.write_draft("<p>one</p>")
        first = self.e.publish()["written"]
        o = self.e.open()
        self.assertEqual(o["seen"], "never")
        self.e.request("POST", "/%s/seen" % SHORT, {"written": first})            # opened mid-rewrite
        self.e.write_draft("<p>two</p>")
        p = self.e.publish()
        self.assertEqual((p["published"], p["lookedMeanwhile"]), (True, True))
        self.e.request("POST", "/%s/seen" % SHORT, {"written": p["written"]})
        self.e.open()
        self.e.write_draft("<p>three</p>")
        self.assertEqual(self.e.publish()["lookedMeanwhile"], False)              # seen before the open

    def test_publish_cuts_what_a_page_may_not_hold(self):
        body = ('<meta http-equiv="refresh" content="0;url=https://example.com/">\n'
                '<link rel="dns-prefetch" href="//evil.example">\n<base href="https://evil.example/">\n<p>kept</p>')
        self.e.write_draft(body)
        p = self.e.publish()
        self.assertEqual(p["removed"], ["meta http-equiv", "link", "base"])
        self.assertEqual(Path(self.e.panel("panel.html")).read_text(), page("\n\n\n<p>kept</p>"))
        self.assertIn(b"<p>kept</p>", self.get_page()[2])

    def served_after_publishing(self, source):
        with open(self.e.panel("draft.html"), "w") as f:
            f.write(source)
        self.e.publish()
        status, h, body = self.get_page()
        self.assertEqual(status, 200)
        return body.decode(), re.search(r"'nonce-([^']+)'", h["content-security-policy"]).group(1)

    def test_a_draft_ending_inside_a_meta_serves_no_meta(self):
        # Left open at the end, the meta would take the inserted script's quotes and `>` as its own.
        served, _ = self.served_after_publishing(
            '<p>x</p><meta content="0;url=https://invalid.example/" http-equiv="refresh')
        self.assertNotIn("http-equiv", served.lower())
        self.assertNotIn("<meta", served.lower())

    def test_a_head_comment_naming_head_stays_a_comment(self):
        # The script goes before the first textual </head>, here inside a comment, where it is only comment
        # text: the comment, the title and the body are as they were, and nothing new reaches the body.
        source = ('<!doctype html><head><!-- Keep </head> as an example; not body text. --><title>Plan</title>'
                  '</head><body><h1>Plan</h1><p>Expected body.</p></body>')
        served, nonce = self.served_after_publishing(source)
        tag = '<script nonce="%s">' % nonce
        self.assertEqual(re.sub(re.escape(tag) + r".*?</script>", "", served), source)
        comment = served[served.index("<!--"):served.index("-->") + 3]
        self.assertIn(tag, comment)
        self.assertTrue(comment.endswith("not body text. -->"))
        self.assertTrue(served.endswith("</head><body><h1>Plan</h1><p>Expected body.</p></body>"))

    def test_unknown_paths_and_methods(self):
        for method, path in (("GET", "/"), ("GET", "/nope"), ("PUT", "/%s/" % SHORT), ("GET", "/%s/check" % SHORT),
                             ("POST", "/%s/" % SHORT), ("DELETE", "/%s/" % SHORT), ("GET", "/%s/x" % SHORT)):
            self.assertEqual(self.e.request(method, path, {} if method != "GET" else None)[0], 404, (method, path))


class WhoMayAsk(Case):
    env_args = {"reach": "tailnet"}

    def setUp(self):
        super().setUp()
        self.o = self.e.open()
        self.e.write_draft("<p>secret</p>")
        self.e.publish()
        self.path = "/%s/" % SHORT

    def proxied(self, path=None, login=OWNER, host=None, method="GET", body=None, headers=None):
        h = {"X-Forwarded-For": "100.64.0.9", "X-Forwarded-Host": host or "%s:%d" % (DNS, self.e.port)}
        if login is not None:
            h["Tailscale-User-Login"] = login
        h.update(headers or {})
        return self.e.request(method, path or self.path, body, headers=h, host=host or "%s:%d" % (DNS, self.e.port))

    def test_acceptance_11_local_refusals(self):
        status, h, body = self.e.request("GET", self.path, host="evil.example")
        self.assertEqual((status, body), (403, b""))
        self.assertEqual(self.e.request("GET", self.path, host="127.0.0.1:1")[0], 403)
        self.assertEqual(self.e.request("POST", "/%s/check" % SHORT, b'{"note": "u1-1"}', ctype="text/plain")[0], 403)
        self.assertEqual(self.e.request("GET", "/control/health")[0], 403)
        self.assertEqual(self.e.request("GET", "/control/health", headers={"X-Panel-Token": "made-up"})[0], 403)
        self.assertEqual(self.e.request("POST", "/%s/check" % SHORT, {"note": "nope"})[0], 400)
        self.assertEqual(self.e.request("GET", self.path)[0], 200)
        self.assertEqual(self.e.request("GET", self.path, host="localhost:%d" % self.e.port)[0], 200)

    def test_a_post_from_another_origin_is_refused(self):
        check = "/%s/check" % SHORT
        self.assertEqual(self.e.request("POST", check, {"note": "u1-1"}, headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.e.request("POST", check, {"note": "u1-1"}, headers={"Origin": "null"})[0], 403)
        for own in ("http://127.0.0.1:%d" % self.e.port, "http://localhost:%d" % self.e.port,
                    "https://%s:%d" % (DNS, self.e.port)):
            self.assertEqual(self.e.request("POST", check, {"note": "u1-1"}, headers={"Origin": own})[0], 204, own)
        self.assertEqual(self.e.request("POST", check, {"note": "u1-1"},
                                        ctype="application/json; charset=utf-8")[0], 204)

    def test_through_tailscale_serve_the_owners_login_alone(self):
        status, h, body = self.proxied()
        self.assertEqual(status, 200)
        self.assertIn(b"secret", body)
        self.assertIn("script-src https://%s:%d/base/ " % (DNS, self.e.port), h["content-security-policy"])
        self.assertEqual(self.proxied(login="other@github")[0], 403)
        self.assertEqual(self.proxied(login="")[0], 403)
        self.assertEqual(self.proxied(login=None)[0], 403)                        # a tagged device: no login
        self.assertEqual(self.proxied(login=[OWNER, OWNER])[0], 403)
        self.assertEqual(self.proxied(login=OWNER.upper())[0], 403)

    def test_the_forwarding_headers_decide_not_the_host(self):
        # acceptance 13's two forms: the honest Host and a forged local one
        local = "127.0.0.1:%d" % self.e.port
        self.assertEqual(self.proxied(login=None, host=local)[0], 403)
        self.assertEqual(self.proxied(login="other@github", host=local)[0], 403)
        only_for = {"X-Forwarded-For": "100.64.0.9"}
        self.assertEqual(self.e.request("GET", self.path, headers=only_for)[0], 403)
        self.assertEqual(self.e.request("GET", self.path, headers={"X-Forwarded-Host": local})[0], 403)

    def test_control_is_local_only(self):
        token = self.e.server_json()["token"]
        self.assertEqual(self.proxied("/control/health", headers={"X-Panel-Token": token})[0], 403)
        self.assertEqual(self.proxied("/control/health", headers={"X-Panel-Token": "made-up"})[0], 403)
        self.assertEqual(self.e.control("GET", "/control/health")[0], 200)

    def test_a_check_through_the_tailnet(self):
        status = self.proxied("/%s/check" % SHORT, method="POST", body={"note": "u1-1"},
                              headers={"Origin": "https://%s:%d" % (DNS, self.e.port)})[0]
        self.assertEqual(status, 204)
        self.assertEqual(json.loads(Path(self.e.panel("state.json")).read_text())["checked"], ["u1-1"])


class TaggedMachine(Case):
    """A devcloud host: tagged, no user, so any login passes and none is refused."""
    env_args = {"reach": "tailnet", "tagged": True}

    def test_any_login_passes_and_none_does_not(self):
        self.e.open()
        h = {"X-Forwarded-For": "100.64.0.9", "X-Forwarded-Host": "%s:%d" % (DNS, self.e.port)}
        for login, want in (("someone@github", 200), (OWNER, 200), (None, 403), ("", 403)):
            hh = dict(h, **({"Tailscale-User-Login": login} if login is not None else {}))
            self.assertEqual(self.e.request("GET", "/%s/" % SHORT, headers=hh)[0], want, login)


# ------------------------------------------------------------------ reach

class Reach(unittest.TestCase):
    def env(self, **kw):
        e = Env(**kw)
        self.addCleanup(e.close)
        return e

    def serve_calls(self, e):
        return [c for c in e.calls() if c["argv"][:2] == ["serve", "--bg"]]

    def test_local_unless_asked(self):
        e = self.env()
        o = e.open()
        self.assertEqual((o["reach"], o["address"]), ("local", "http://127.0.0.1:%d/%s/" % (e.port, SHORT)))
        self.assertEqual(self.serve_calls(e), [])

    def test_tailnet_maps_the_port_and_answers_the_tailnet_address(self):
        e = self.env(reach="tailnet")
        o = e.open()
        self.assertEqual((o["reach"], o["address"]), ("tailnet", "https://%s:%d/%s/" % (DNS, e.port, SHORT)))
        self.assertEqual([c["argv"] for c in self.serve_calls(e)],
                         [["serve", "--bg", "--https=%d" % e.port, "http://127.0.0.1:%d" % e.port]])
        e.write_draft("<p>x</p>")
        p = e.publish()
        self.assertEqual((p["reach"], p["address"]), ("tailnet", o["address"]))
        self.assertEqual(e.ok("ensure"), {"address": "https://%s:%d/" % (DNS, e.port), "reach": "tailnet"})
        self.assertEqual(len(self.serve_calls(e)), 1)                             # mapped once

    def test_a_standing_mapping_is_not_made_again(self):
        e = self.env(reach="tailnet")
        e.stub_file("serve.json", json.dumps({"Web": {"%s:%d" % (DNS, e.port): {
            "Handlers": {"/": {"Proxy": "http://127.0.0.1:%d" % e.port}}}}}))
        self.assertEqual(e.open()["reach"], "tailnet")
        self.assertEqual(self.serve_calls(e), [])

    def test_a_port_mapped_elsewhere_is_left_alone(self):
        e = self.env(reach="tailnet")
        e.stub_file("serve.json", json.dumps({"Web": {"%s:%d" % (DNS, e.port): {
            "Handlers": {"/": {"Proxy": "http://127.0.0.1:9"}}}}}))
        self.assertEqual(e.open()["reach"], "local")
        self.assertEqual(self.serve_calls(e), [])

    def test_a_port_forwarded_as_tcp_is_left_alone(self):
        e = self.env(reach="tailnet")
        e.stub_file("serve.json", json.dumps({"TCP": {str(e.port): {"TCPForward": "127.0.0.1:22"}}}))
        self.assertEqual(e.open()["reach"], "local")
        self.assertEqual(self.serve_calls(e), [])

    def test_a_failed_mapping_lookup_configures_nothing(self):
        # Not knowing whether the port is mapped is not knowing it is free: someone else's mapping may stand.
        e = self.env(reach="tailnet")
        e.stub_file("serve-status-fails", "")
        self.assertEqual(e.open()["reach"], "local")
        self.assertEqual(self.serve_calls(e), [])

    def test_a_malformed_mapping_lookup_configures_nothing(self):
        e = self.env(reach="tailnet")
        for garbled in ("not json{", "[]", '{"Web": []}'):
            e.stub_file("serve.json", garbled)
            self.assertEqual(e.open(env=dict(e.env, PANEL_REACH="tailnet"))["reach"], "local", garbled)
            e.stop()
        self.assertEqual(self.serve_calls(e), [])

    def test_a_mapping_lookup_that_times_out_configures_nothing(self):
        e = self.env(reach="tailnet")
        e.stub_file("serve-status-stalls", "")
        self.assertEqual(e.open()["reach"], "local")
        time.sleep(6)                                       # past the lookup's 5 s limit
        self.assertEqual(self.serve_calls(e), [])

    def test_refused_until_run_under_sudo_n(self):
        e = self.env(reach="tailnet", needs_sudo=True)
        o = e.open()
        self.assertEqual(o["reach"], "tailnet")
        self.assertEqual([c["sudo"] for c in self.serve_calls(e)], [False, True])

    def test_sudo_refused_too_is_local(self):
        e = self.env(reach="tailnet", needs_sudo=True)
        e.stub_file("sudo-refused", "")
        self.assertEqual(e.open()["reach"], "local")

    def test_tailscale_not_running_is_local(self):
        e = self.env(reach="tailnet", tailscale="Stopped")
        self.assertEqual(e.open()["reach"], "local")
        self.assertEqual(self.serve_calls(e), [])

    def test_no_tailscale_at_all_is_local(self):
        e = self.env(reach="tailnet", tailscale=None)
        self.assertEqual(e.open()["reach"], "local")

    def test_a_stalled_tailscale_keeps_the_budget(self):
        e = self.env(reach="tailnet", stall=True)
        t0 = time.time()
        o = e.open()
        self.assertLess(time.time() - t0, 4.0)
        self.assertEqual(o["reach"], "local")
        # served all the while: a request is never held by tailscale
        t0 = time.time()
        self.assertEqual(e.request("GET", "/%s/" % SHORT)[0], 200)
        self.assertLess(time.time() - t0, 1.0)

    def test_tailnet_asked_of_a_server_started_without_it(self):
        e = self.env()
        self.assertEqual(e.open()["reach"], "local")
        o = e.open(env=dict(e.env, PANEL_REACH="tailnet"))
        self.assertEqual(o["reach"], "tailnet")


# ------------------------------------------------------------------ the lock

class OneWriter(unittest.TestCase):
    """A check that lands while open-panel is between its read and its write survives: both run under one lock."""

    def test_a_check_during_open_panel_survives(self):
        e = Env()
        self.addCleanup(e.close)
        S = load_server()
        os.environ_backup = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(os.environ_backup)))
        os.environ.update(CLAUDE_CONFIG_DIR=e.config, PANEL_PORT=str(e.port), STUB_DIR=e.stub, STUB_DNS=DNS,
                          PATH=e.env["PATH"])
        panels = S.Panels(S.panels_root())
        panels.open_panel(SID, "en")
        e.write_draft('<p><mark data-note="u1-1">x</mark></p><aside class="note" id="u1-1">y</aside>')
        panels.publish(SID)                       # a page, so the next open-panel copies it to the draft
        reading = threading.Event()
        real_copy = S.copy_text

        def slow_copy(src, dst):
            reading.set()
            time.sleep(0.5)                       # open-panel has read the state and not yet written it
            real_copy(src, dst)

        S.copy_text = slow_copy
        try:
            t = threading.Thread(target=panels.open_panel, args=(SID, "en"))
            t.start()
            self.assertTrue(reading.wait(5))
            panels.check(SHORT, "u1-1")
            t.join()
        finally:
            S.copy_text = real_copy
        state = json.loads(Path(e.panel("state.json")).read_text())
        self.assertEqual(state["checked"], ["u1-1"])


def tearDownModule():
    shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
