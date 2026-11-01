"""The manager's page: `manager serve`, a read-only HTTP server of the ledger for the owner's tailnet, and its
launchd install.

    manager serve [--name N] [--port P]             the server, in the foreground
    manager serve --install [--name N] [--port P]   write the launchd agent and serve.json; print the load and
                                                    expose commands, running neither
    manager serve --status [--name N]               the address, launchd's hold, tailscale's mapping

The server binds 127.0.0.1 and `tailscale serve` proxies an HTTPS port of the Mac's tailnet name to it. Every
request must carry a `Tailscale-User-Login` equal to the owner's login recorded at install (serve.json); Serve
replaces a client-sent copy with the requesting node's user and sends none for a tagged node (checked live, M6),
so over the tailnet only the owner's own devices get in. A local process running as the owner could forge the
header on the local port, and could as well read the state file itself (0600): the trust boundary is the tailnet
ingress plus this Mac's own user.

    GET /             the page (assets/page.html, read per request)
    GET /ledger.json  `manager ledger --json` of the state file (manager_ledger.view), built per request
    GET /events       text/event-stream: `event: changed` with the state's `updated` when the state file moves
                      (stat once a second), a comment every 25 s to keep proxies open
    anything else     404; a method other than GET, 405; without the owner's identity, 403 before either

While serving it starts no process, opens no outbound connection and reads one file (and the page). When its own
scripts change (a plugin update), it executes itself again in place, as the sminos daemon does.
"""

import hashlib
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

import sminos as S
import manager_ledger as L

HERE = os.path.dirname(os.path.realpath(__file__))
SKILL_DIR = os.path.dirname(HERE)
PAGE = os.path.join(SKILL_DIR, "assets", "page.html")
PLIST_TEMPLATE = os.path.join(SKILL_DIR, "references", "sminos-manager.plist")
# Every script the server runs: its own directory and sminos's, whose modules manager_ledger imports.
CODE_DIRS = (HERE, S.SCRIPT_DIR)
LABEL_PREFIX = "com.doperpowers.sminos-manager."
DEFAULT_PORT = 47390        # the local port and, unless serve.json says otherwise, the tailnet's HTTPS port
TICK = 1.0                  # how often the state file (and the server's own code) is looked at
KEEPALIVE = 25.0            # a comment line on /events this often, so a proxy does not close it
CODE_SETTLE = 1.0           # new code is acted on once it has held still this long (an update in progress ends)
TOOL_TIMEOUT = 15           # tailscale and launchctl, run by --install and --status only
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; "
       "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class Refused(Exception):
    """`--install` cannot go on: one line for the owner."""


def settings_path(name):
    return os.path.join(S.root(), "managers", name + ".serve.json")


def log_path(name):
    return os.path.join(S.root(), "managers", name + ".serve.log")


def label(name):
    return LABEL_PREFIX + name


def plist_path(name):
    return os.path.join(S.home_dir(), "Library", "LaunchAgents", label(name) + ".plist")


def load_settings(name):
    """serve.json as {port, https_port, owner}, or None when there is none; ValueError when it does not hold."""
    try:
        with open(settings_path(name)) as f:
            raw = json.load(f)
    except FileNotFoundError:
        return None
    ok = (isinstance(raw, dict) and all(isinstance(raw.get(k), int) and 0 < raw[k] < 65536
                                        for k in ("port", "https_port"))
          and isinstance(raw.get("owner"), str) and raw["owner"])
    if not ok:
        raise ValueError("%s needs port, https_port and owner; rerun manager serve --install" % settings_path(name))
    return raw


# ------------------------------------------------------------------ the server

def state_signature(name):
    """What moves when the state file is replaced: (inode, mtime, size), None while there is none."""
    try:
        st = os.stat(L.path(name))
    except OSError:
        return None
    return st.st_ino, st.st_mtime_ns, st.st_size


class Handler(BaseHTTPRequestHandler):
    server_version = "sminos-manager"
    sys_version = ""

    def __getattr__(self, attr):
        # Every method the request line names (BaseHTTPRequestHandler looks up `do_<METHOD>`) lands in one
        # place, so identity is checked before anything else, for GET and every other method alike.
        if attr.startswith("do_"):
            return self.dispatch
        raise AttributeError(attr)

    def dispatch(self):
        logins = self.headers.get_all("Tailscale-User-Login") or []
        if len(logins) != 1 or logins[0] != self.server.owner:
            return self.reply(403, b"403: this page is its owner's alone (no matching Tailscale identity)\n")
        if self.command != "GET":
            return self.reply(405, b"405: the page is read-only; only GET is served\n", {"Allow": "GET"})
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self.page()
        if path == "/ledger.json":
            return self.ledger()
        if path == "/events":
            return self.events()
        return self.reply(404, b"404: not here\n")

    def reply(self, code, body, headers=None, kind="text/plain; charset=utf-8"):
        self.send_response(code)
        for k, v in {"Content-Type": kind, "Content-Length": str(len(body)), **(headers or {})}.items():
            self.send_header(k, v)
        self.common_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def common_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)

    def page(self):
        try:
            with open(PAGE, "rb") as f:
                body = f.read()
        except OSError as e:
            return self.reply(500, ("500: the page is missing (%s)\n" % e).encode())
        self.reply(200, body, kind="text/html; charset=utf-8")

    def ledger(self):
        name = self.server.name
        try:
            v = L.view(L.load(name), time.time())
        except (OSError, ValueError) as e:
            return self.reply(500, ("500: %s is unreadable (%s)\n" % (L.path(name), e)).encode())
        except L.Invalid as e:
            return self.reply(500, ("500: %s does not hold: %s\n" % (L.path(name), "; ".join(e.problems))).encode())
        self.reply(200, json.dumps(v, ensure_ascii=False).encode(), kind="application/json; charset=utf-8")

    def events(self):
        """The stream: `changed` each time the state file's signature moves, a comment every KEEPALIVE seconds;
        it ends when the client goes or the server stops."""
        name = self.server.name
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("X-Accel-Buffering", "no")
        self.common_headers()
        self.end_headers()
        seen, quiet = state_signature(name), time.monotonic()
        try:
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            while not self.server.stopping.wait(TICK):
                now = state_signature(name)
                if now != seen:
                    seen = now
                    try:
                        updated = L.load(name).get("updated") or ""
                    except Exception:
                        updated = ""
                    self.wfile.write(("event: changed\ndata: %s\n\n" % updated).encode())
                elif time.monotonic() - quiet >= KEEPALIVE:
                    self.wfile.write(b": still here\n\n")
                else:
                    continue
                self.wfile.flush()
                quiet = time.monotonic()
        except OSError:
            return              # the client went away

    def log_message(self, fmt, *args):
        pass                    # the page is read every few seconds from a phone; a request log would only grow


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, name, owner):
        self.name, self.owner, self.stopping = name, owner, threading.Event()
        super().__init__(("127.0.0.1", port), Handler)

    def server_bind(self):
        # HTTPServer.server_bind looks up the host's fully qualified name, a resolver query; the server needs none.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


_digests = {}   # path -> ((mtime_ns, size), sha-256 of its bytes)


def own_code():
    """Every script the server runs, by content: a marketplace update re-clones the whole marketplace, so every
    file gets a new mtime whether or not it changed. The stat is the cheap test; a file is read again only when its
    mtime or size moved."""
    out = {}
    for d in CODE_DIRS:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            if not n.endswith(".py"):
                continue
            p = os.path.join(d, n)
            try:
                st = os.stat(p)
                sig = (st.st_mtime_ns, st.st_size)
                kept = _digests.get(p)
                if kept is None or kept[0] != sig:
                    with open(p, "rb") as f:
                        kept = (sig, hashlib.sha256(f.read()).hexdigest())
                    _digests[p] = kept
            except OSError:
                continue
            out[p] = kept[1]
    return out


def serve(name, port=None):
    """The server, until SIGTERM; returns only to execute itself again when its code changed."""
    try:
        cfg = load_settings(name)
    except ValueError as e:
        raise Refused(str(e))
    if cfg is None:
        raise Refused("no settings for the page (%s): run manager serve --install%s first; it records the owner's "
                      "Tailscale login, which every request must carry" % (settings_path(name),
                                                                           "" if name == "default" else " --name " + name))
    httpd = Server(port or cfg["port"], name, cfg["owner"])
    sys.stderr.write("manager serve: the ledger %s on http://127.0.0.1:%d/ for %s\n"
                     % (L.path(name), httpd.server_port, cfg["owner"]))
    sys.stderr.flush()
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True).start()
    code = own_code()
    while True:
        time.sleep(TICK)
        now = own_code()
        if now == code:
            continue
        while True:     # wait for the update to finish writing
            time.sleep(CODE_SETTLE)
            later = own_code()
            if later == now:
                break
            now = later
        break
    sys.stderr.write("manager serve: its scripts changed; restarting in place\n")
    sys.stderr.flush()
    httpd.stopping.set()
    httpd.shutdown()
    httpd.server_close()
    os.execv(sys.executable, [sys.executable] + sys.orig_argv[1:])


# ------------------------------------------------------------------ install and status

def run_tool(argv):
    """(exit code, stdout) of tailscale or launchctl; (None, why) when it cannot run."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=TOOL_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    return r.returncode, r.stdout if r.returncode == 0 else (r.stderr.strip() or r.stdout.strip())


def tailnet_self():
    """(this node's tailnet name, its user's login, its tags) from `tailscale status --json`; Refused when
    tailscale cannot say."""
    code, out = run_tool(["tailscale", "status", "--json"])
    if code is None:
        raise Refused("tailscale cannot be run (%s); the page is reached through tailscale serve" % out)
    if code != 0:
        raise Refused("tailscale status failed (%s); is tailscale running?" % out)
    try:
        st = json.loads(out)
        me = st["Self"]
    except (ValueError, KeyError, TypeError):
        raise Refused("tailscale status --json did not answer as expected")
    if st.get("BackendState") not in (None, "Running"):
        raise Refused("tailscale is not running here (%s)" % st.get("BackendState"))
    user = (st.get("User") or {}).get(str(me.get("UserID"))) or {}
    return (me.get("DNSName") or "").rstrip("."), user.get("LoginName") or "", me.get("Tags") or []


def installed_script():
    """The manager.py the agent runs: a path that outlives plugin updates. One running from the versioned plugin
    cache is replaced by the marketplace clone's (as `sminos daemon install` does); a checkout runs itself."""
    here = os.path.join(HERE, "manager.py")
    plugins = os.path.join(S.home_dir(), ".claude", "plugins")
    if not here.startswith(os.path.realpath(os.path.join(plugins, "cache")) + os.sep):
        return here
    known = os.path.join(plugins, "known_marketplaces.json")
    try:
        with open(known) as f:
            location = str(((json.load(f) or {}).get("doperpowers") or {}).get("installLocation") or "")
    except (OSError, ValueError, AttributeError):
        location = ""
    stable = os.path.join(location, "sminos", "skills", "manager", "scripts", "manager.py") if location else ""
    if stable and os.path.isfile(stable):
        return stable
    raise Refused("this manager runs from the versioned plugin cache (%s), which a plugin update deletes, and the "
                  "doperpowers marketplace clone it would run instead is missing (%s); update the doperpowers "
                  "marketplace, or install from a checkout" % (here, stable or "no doperpowers entry in " + known))


def write_private(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(text)


def install(name, port=None):
    """Writes the launchd agent and serve.json; returns the lines to print (the load and expose commands, the
    address). Runs neither launchctl nor tailscale serve: loading and exposing are the owner's steps."""
    if sys.platform != "darwin":
        raise Refused("serve --install writes a launchd agent (macOS); this is %s" % sys.platform)
    if not (sys.executable and os.path.isabs(sys.executable)):
        raise Refused("this Python does not say where it is (sys.executable is %r)" % sys.executable)
    script = installed_script()
    dns, owner, tags = tailnet_self()
    if tags:
        raise Refused("this node is tagged (%s): a tagged node has no user, so tailscale serve would carry no "
                      "owner's identity to check" % ", ".join(tags))
    if not owner:
        raise Refused("tailscale status names no login for this node's user")
    try:
        old = load_settings(name) or {}
    except ValueError:
        old = {}
    local = port or old.get("port") or DEFAULT_PORT
    https = old.get("https_port") if (old and not port) else local
    with open(PLIST_TEMPLATE) as f:
        text = f.read()
    for key, value in (("LABEL", label(name)), ("PYTHON", sys.executable), ("MANAGER", script), ("NAME", name),
                       ("SMINOS_HOME", S.root()), ("LOG", log_path(name))):
        text = text.replace("{{%s}}" % key, escape(value))
    os.makedirs(os.path.join(S.root(), "managers"), mode=0o700, exist_ok=True)
    plist = plist_path(name)
    write_private(plist, text)
    S.write_json(settings_path(name), {"port": local, "https_port": https, "owner": owner}, mode=0o600)
    return ["wrote %s: it runs %s serve --name %s on %s" % (plist, script, name, sys.executable),
            "wrote %s: port %d, https port %d, owner %s" % (settings_path(name), local, https, owner),
            "load it:    launchctl bootstrap gui/$(id -u) %s" % plist,
            "expose it:  tailscale serve --bg --https=%d http://127.0.0.1:%d" % (https, local),
            "address:    https://%s:%d/" % (dns or "<this Mac's tailnet name>", https),
            "unload it:  launchctl bootout gui/$(id -u)/%s" % label(name)]


def status(name):
    """{installed, address, port, https_port, owner, launchd: {loaded, state, pid}, tailscale: {mapped, proxy}, up}."""
    try:
        cfg = load_settings(name)
    except ValueError as e:
        raise Refused(str(e))
    out = {"name": name, "installed": cfg is not None, "address": None, "port": None, "https_port": None,
           "owner": None, "launchd": {"loaded": False, "state": None, "pid": None},
           "tailscale": {"mapped": False, "proxy": None}, "up": False}
    if cfg is None:
        return out
    out.update(port=cfg["port"], https_port=cfg["https_port"], owner=cfg["owner"])
    try:
        dns = tailnet_self()[0]
    except Refused:
        dns = ""
    out["address"] = "https://%s:%d/" % (dns or "<this Mac's tailnet name>", cfg["https_port"])
    code, text = run_tool(["launchctl", "print", "gui/%d/%s" % (os.getuid(), label(name))])
    if code == 0:
        fields = {}
        for line in text.splitlines():
            k, sep, v = line.strip().partition(" = ")
            if sep and k in ("state", "pid") and k not in fields:
                fields[k] = v.strip()
        out["launchd"] = {"loaded": True, "state": fields.get("state"),
                          "pid": int(fields["pid"]) if fields.get("pid", "").isdigit() else None}
    code, text = run_tool(["tailscale", "serve", "status", "--json"])
    if code == 0:
        try:
            web = (json.loads(text) or {}).get("Web") or {}
        except ValueError:
            web = {}
        for host, conf in web.items():
            if host.rsplit(":", 1)[-1] == str(cfg["https_port"]):
                proxy = (((conf or {}).get("Handlers") or {}).get("/") or {}).get("Proxy")
                out["tailscale"] = {"mapped": proxy == "http://127.0.0.1:%d" % cfg["port"], "proxy": proxy}
    out["up"] = out["launchd"]["loaded"] and out["tailscale"]["mapped"]
    return out


def render_status(s):
    if not s["installed"]:
        return "the page is not installed (no %s): manager serve --install%s" % (
            settings_path(s["name"]), "" if s["name"] == "default" else " --name " + s["name"])
    ld, ts = s["launchd"], s["tailscale"]
    lines = ["address:   %s%s" % (s["address"], "" if s["up"] else "  (not reachable yet)")]
    if ld["loaded"]:
        lines.append("launchd:   holds %s (%s%s)" % (label(s["name"]), ld["state"] or "loaded",
                                                     ", pid %d" % ld["pid"] if ld["pid"] else ""))
    else:
        lines.append("launchd:   not loaded; load it: launchctl bootstrap gui/$(id -u) %s" % plist_path(s["name"]))
    if ts["mapped"]:
        lines.append("tailscale: serves https %d → http://127.0.0.1:%d" % (s["https_port"], s["port"]))
    else:
        lines.append("tailscale: %s; expose it: tailscale serve --bg --https=%d http://127.0.0.1:%d" % (
            "https %d goes to %s" % (s["https_port"], ts["proxy"]) if ts["proxy"] else "not exposed",
            s["https_port"], s["port"]))
    return "\n".join(lines)
