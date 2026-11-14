#!/usr/bin/env python3
"""The panel server: one process per machine that serves every session's panel and the base they share, and the
only writer of a panel's records. Its command line is the mod's whole interface to it.

    server.py serve                                   run in the foreground (tests, debugging)
    server.py ensure                                  make sure a server answers, when a panel exists; print
                                                      {"address": "<origin>/", "reach": ...}, or {} when none does
    server.py open-panel --session <id> [--locale en|ko]
                                                      make the panel's draft from its page (or the starter);
                                                      print OpenPanel
    server.py publish --session <id>                  put the draft over the page in one rename; print Published

Panels live in <configuration directory>/to-human/panels/<short id>/ (panel.html, draft.html, meta.json,
state.json); server.json (0600) beside them holds the running server's port, pid, version and the token every
control request carries. The server listens on 127.0.0.1:$PANEL_PORT (4777) alone; with PANEL_REACH=tailnet it has
`tailscale serve` pass an HTTPS port of the machine's tailnet name to it. Design and contracts:
docs/doperpowers/specs/2026-11-13-present-panel-design.md. Python's standard library only.
"""

import hmac
import html
import http.client
import json
import os
import re
import secrets
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.realpath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
BASE_DIR = os.path.join(HERE, "base")
STARTER = os.path.join(BASE_DIR, "starter.html")
GUIDE = os.path.join(BASE_DIR, "GUIDE.md")

DEFAULT_PORT = 4777
SERVER_NAME = "to-human-panel"
TOOL_TIMEOUT = 5          # each tailscale command
REFRESH_EVERY = 30        # the tailnet identity and mapping are looked at no more often than this
REACH_WAIT = 2            # open-panel waits this long for a refresh it needs (the first, or one it asked for)
START_WAIT = 2            # a server started by the command line answers within this
MAX_AGE = 30 * 86400      # a panel whose page and draft are both older is removed when a server starts
MAX_BODY = 64 * 1024

SHORT_ID = re.compile(r"[0-9a-f]{8}")
NOTE_ID = re.compile(r"u\d+-\d+")
NOTE_ID_ATTR = re.compile(r"""\bid\s*=\s*["']?(u\d+-\d+)(?=["'\s>/])""")
# A mark of a note's change: one note may mark several places (`<mark data-note="u2-1">`).
NOTE_MARK_ATTR = re.compile(r"""\bdata-note\s*=\s*["']?(u\d+-\d+)(?=["'\s>/])""")
PAGE_PATH = re.compile(r"/([0-9a-f]{8})/(written|seen|check)?")
BASE_FILE = re.compile(r"/base/([A-Za-z0-9][A-Za-z0-9._-]*)")
TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".html": "text/html; charset=utf-8", ".md": "text/markdown; charset=utf-8"}

WAITING = {
    "en": ("The panel is being written", "The panel is being written. This page shows it as soon as it is."),
    "ko": ("패널을 작성하는 중", "패널을 작성하는 중입니다. 다 쓰이면 이 페이지에 바로 나타납니다."),
}


class Refused(Exception):
    """The command cannot do what it was asked: one line for the session."""


# ------------------------------------------------------------------ settings

def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def panels_root():
    return os.path.join(config_dir(), "to-human", "panels")


def panel_port():
    raw = os.environ.get("PANEL_PORT") or str(DEFAULT_PORT)
    if not raw.isdigit() or not 0 < int(raw) < 65536:
        raise Refused("PANEL_PORT is %r, not a port number" % raw)
    return int(raw)


def locale_of(value):
    v = (value or "").strip().lower()
    return "ko" if v in ("ko", "korean") else "en"


def wants_tailnet(value):
    return (value or "").strip().lower() == "tailnet"


def plugin_version():
    try:
        with open(os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json")) as f:
            return str(json.load(f).get("version") or "0")
    except (OSError, ValueError, AttributeError):
        return "0"


def version_key(v):
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.+-]", str(v))[:3])


def now_ms():
    return int(time.time() * 1000)


# ------------------------------------------------------------------ files

def read_json(path, default):
    try:
        with open(path) as f:
            value = json.load(f)
    except (OSError, ValueError):
        return default
    return value if isinstance(value, dict) else default


def write_atomic(path, data, mode=None):
    """`data` (bytes) at `path`, whole: a temporary file beside it, then one rename."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            if mode is not None:
                os.fchmod(f.fileno(), mode)
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path, value, mode=None):
    write_atomic(path, (json.dumps(value, ensure_ascii=False) + "\n").encode(), mode)


def read_text(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8", "surrogateescape")


def copy_text(src, dst):
    write_atomic(dst, read_text(src).encode("utf-8", "surrogateescape"))


def starter_text(locale):
    text = read_text(STARTER)
    return text.replace('<html lang="en">', '<html lang="%s">' % locale, 1) if locale != "en" else text


# ------------------------------------------------------------------ what a page may hold

TAG_START = re.compile(r"<(meta|link|base)(?=[\t\n\f\r />])", re.I | re.A)
SPACE = "\t\n\f\r "


def _tag_end(text, i):
    """Where the start tag whose name ends at `i` ends, its attributes, and whether it is closed, as a browser's
    tokenizer reads them: quotes count only around a value, the first `>` outside one ends it; a tag left open
    runs to the end, its open attribute counted with what it holds so far."""
    n, attrs = len(text), {}
    while True:
        while i < n and text[i] in SPACE + "/":
            i += 1
        if i >= n:
            return n, attrs, False
        if text[i] == ">":
            return i + 1, attrs, True
        j = i + 1                                   # a name may start with `=`, and holds quotes as letters
        while j < n and text[j] not in SPACE + "/>=":
            j += 1
        name, i = text[i:j].lower(), j
        while i < n and text[i] in SPACE:
            i += 1
        value = ""
        if i < n and text[i] == "=":
            i += 1
            while i < n and text[i] in SPACE:
                i += 1
            if i < n and text[i] in "\"'":
                k = text.find(text[i], i + 1)
                if k < 0:
                    attrs.setdefault(name, html.unescape(text[i + 1:]))
                    return n, attrs, False
                value, i = text[i + 1:k], k + 1
            else:
                j = i
                while j < n and text[j] not in SPACE + ">":
                    j += 1
                value, i = text[i:j], j
        attrs.setdefault(name, html.unescape(value))


def _kept(kind, attrs):
    if kind == "meta":
        return "http-equiv" not in attrs
    if kind == "link":
        return attrs.get("rel", "").lower().split() == ["stylesheet"] and attrs.get("href", "").startswith("/base/")
    return False


def cut(text):
    """`text` without every <meta http-equiv>, every <link> but a stylesheet under /base/ and every <base>; and
    what was cut ("meta http-equiv", "link", "base", each once, in the order first met).

    A tag is found wherever a browser could find one: every `<meta`, `<link` or `<base` in the source is read as a
    start tag, inside a comment or a script as much as in the body, since a reading that skips what it takes for
    a comment (html.parser takes `<!-->` for an open one; a browser closes it at once) would leave a live tag in
    place. A tag the draft leaves open is cut whatever it holds so far: what follows the draft when it is served
    (the server's script) would close it, and give it attributes of its own. Cutting repeats until nothing is
    left to cut, so the pieces around a cut cannot join into a new tag."""
    removed = []
    while True:
        out, pos, changed = [], 0, False
        for m in TAG_START.finditer(text):
            if m.start() < pos:
                continue
            kind = m.group(1).lower()
            end, attrs, closed = _tag_end(text, m.end())
            if closed and _kept(kind, attrs):
                continue
            out.append(text[pos:m.start()])
            pos, changed = end, True
            label = "meta http-equiv" if kind == "meta" else kind
            if label not in removed:
                removed.append(label)
        if not changed:
            return text, removed
        out.append(text[pos:])
        text = "".join(out)


def insert_script(text, written, checked, nonce):
    """The page with the server's own script appended at the very end of its source: its publish time and the
    notes checked off, as JSON with `<` escaped. The end of a well-formed page stands outside every comment, tag
    and raw-text element, where a textual `</head>` may not (a head comment can name it); panel.js is linked
    `defer`, so it runs after this script, and a `</html>` before it only moves it into the body. No guard
    precedes it: a draft tag left open that swallows it cannot carry its nonce, since CSP3 denies a nonce to an
    element with `<script` in an attribute."""
    data = json.dumps({"written": written, "checked": checked}, separators=(",", ":")).replace("<", "\\u003c")
    return text + '<script nonce="%s">window.PANEL=%s</script>' % (nonce, data)


def waiting_page(locale):
    title, said = WAITING.get(locale, WAITING["en"])
    return ('<!doctype html>\n<html lang="%s">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>%s</title>\n'
            '<link rel="stylesheet" href="/base/panel.css">\n<script src="/base/panel.js" defer></script>\n'
            '</head>\n<body>\n<p class="panel-waiting">%s</p>\n</body>\n</html>\n' % (locale, title, said))


# ------------------------------------------------------------------ the panels

def short_of(session):
    if not isinstance(session, str) or not SHORT_ID.fullmatch(session[:8]):
        raise Refused("%r is not a session id: a panel's place is its first 8 characters, lowercase hex" % session)
    return session[:8]


class Panels:
    """Every panel's records, read and written under one lock."""

    def __init__(self, root):
        self.root = root
        self.lock = threading.Lock()

    def dir(self, short):
        return os.path.join(self.root, short)

    def paths(self, short):
        d = self.dir(short)
        return {k: os.path.join(d, v) for k, v in (("page", "panel.html"), ("draft", "draft.html"),
                                                   ("meta", "meta.json"), ("state", "state.json"))}

    def exists(self, short):
        return os.path.isdir(self.dir(short))

    def state(self, short):
        s = read_json(self.paths(short)["state"], {})
        checked = [c for c in s.get("checked") or [] if isinstance(c, str)]
        seen, written = s.get("seen"), s.get("written")
        return {"seen": seen if isinstance(seen, int) else None,
                "written": written if isinstance(written, int) else None, "checked": checked}

    def meta(self, short):
        return read_json(self.paths(short)["meta"], None)

    def _owned(self, short, session):
        meta = self.meta(short)
        if meta and meta.get("session") != session:
            raise Refused("the panel %s belongs to another session (%s), whose id begins alike: this session "
                          "cannot have a panel" % (short, meta.get("session")))
        return meta

    def open_panel(self, session, locale):
        short = short_of(session)
        with self.lock:
            meta = self._owned(short, session) or {}
            p = self.paths(short)
            os.makedirs(self.dir(short), mode=0o700, exist_ok=True)
            state = self.state(short)
            is_new = not os.path.exists(p["page"])
            if is_new:
                write_atomic(p["draft"], starter_text(locale).encode("utf-8", "surrogateescape"))
                held = set()
            else:
                copy_text(p["page"], p["draft"])
                # A note is held while its aside or any of its marks remains: the fork deletes them all.
                page = read_text(p["page"])
                held = set(NOTE_ID_ATTR.findall(page)) | set(NOTE_MARK_ATTR.findall(page))
            state["checked"] = [c for c in state["checked"] if c in held]
            update = (meta.get("updates") if isinstance(meta.get("updates"), int) else 0) + 1
            write_json(p["meta"], {"session": session, "updates": update, "locale": locale,
                                   "seenAtOpen": state["seen"]})
            write_json(p["state"], state)
        written, seen = state["written"], state["seen"]
        look = "never" if written is None or seen is None else "current" if seen >= written else "stale"
        return {"dir": self.dir(short), "draft": p["draft"], "guide": GUIDE, "update": update, "isNew": is_new,
                "locale": locale, "seen": look, "checked": state["checked"]}

    def publish(self, session):
        short = short_of(session)
        with self.lock:
            meta = self._owned(short, session)
            p = self.paths(short)
            if meta is None or not os.path.exists(p["draft"]):
                raise Refused("there is no draft of the panel %s to publish: run open-panel first" % short)
            text, removed = cut(read_text(p["draft"]))
            data = text.encode("utf-8", "surrogateescape")
            if os.path.exists(p["page"]):
                with open(p["page"], "rb") as f:
                    current = f.read()
            else:
                current = starter_text(meta.get("locale") or "en").encode("utf-8", "surrogateescape")
            state = self.state(short)
            replaced = state["written"]
            published = data != current
            if published:
                write_atomic(p["page"], data)
                state["written"] = max(now_ms(), (replaced or 0) + 1)
                write_json(p["state"], state)
            at_open, seen = meta.get("seenAtOpen"), state["seen"]
            meanwhile = (published and replaced is not None and seen is not None and seen >= replaced
                         and not (isinstance(at_open, int) and at_open >= replaced))
        return {"published": published, "written": state["written"], "removed": removed,
                "lookedMeanwhile": meanwhile}

    def check(self, short, note):
        with self.lock:
            if not self.exists(short):
                return False
            state = self.state(short)
            if note not in state["checked"]:
                state["checked"].append(note)
                write_json(self.paths(short)["state"], state)
        return True

    def saw(self, short, written):
        """A look at the publication of time `written`: recorded when no newer one is, and it is not past the
        current one."""
        with self.lock:
            if not self.exists(short):
                return False
            state = self.state(short)
            current = state["written"]
            if current is not None and written <= current and (state["seen"] is None or written > state["seen"]):
                state["seen"] = written
                write_json(self.paths(short)["state"], state)
        return True

    def page(self, short):
        """(the page's text or None before its first publish, its publish time, the checked notes, the locale)."""
        with self.lock:
            state = self.state(short)
            meta = self.meta(short) or {}
            try:
                text = read_text(self.paths(short)["page"])
            except FileNotFoundError:
                text = None
        return text, state["written"], state["checked"], meta.get("locale") or "en"

    def any(self):
        try:
            return any(SHORT_ID.fullmatch(n) and os.path.isdir(os.path.join(self.root, n))
                       for n in os.listdir(self.root))
        except OSError:
            return False

    def remove_old(self):
        cutoff = time.time() - MAX_AGE
        try:
            names = os.listdir(self.root)
        except OSError:
            return
        for n in names:
            d = os.path.join(self.root, n)
            if not SHORT_ID.fullmatch(n) or not os.path.isdir(d):
                continue
            times = []
            for f in ("panel.html", "draft.html"):
                try:
                    times.append(os.stat(os.path.join(d, f)).st_mtime)
                except OSError:
                    pass
            if not times:
                times = [os.stat(d).st_mtime]
            if max(times) < cutoff:
                shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ reach

def run_tool(argv):
    """(exit code, output) of a tailscale command, in TOOL_TIMEOUT; (None, why) when it cannot run."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=TOOL_TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    return r.returncode, r.stdout if r.returncode == 0 else (r.stderr.strip() or r.stdout.strip())


class Reach:
    """The machine's tailnet identity and whether `tailscale serve` maps the port here, held for the requests
    (which never run tailscale) and refreshed by a background thread, at most every REFRESH_EVERY seconds."""

    def __init__(self, port, want):
        self.port, self.want = port, want
        self.lock = threading.Lock()
        self.identity = None        # {"dns", "owner", "tagged"} once tailscale has answered
        self.mapped = False
        self.thread = None
        self.last = None
        self.settled = False

    def ask(self, want):
        """Start a refresh when one is due, or when tailnet is asked for the first time; the thread to wait on
        when the caller should (the first refresh, or one this ask forced), else None."""
        with self.lock:
            forced = want and not self.want
            self.want = self.want or want
            running = self.thread is not None and self.thread.is_alive()
            if not running and (forced or self.last is None or time.monotonic() - self.last >= REFRESH_EVERY):
                self.last = time.monotonic()
                self.thread = threading.Thread(target=self._refresh, daemon=True)
                self.thread.start()
                running = True
            return self.thread if running and (forced or not self.settled) else None

    def _refresh(self):
        try:
            identity, running = self._status()
            mapped = "unknown"
            if running:
                mapped = self._mapping()
                if mapped == "no" and self.want:
                    tool = shutil.which("tailscale") or "tailscale"
                    argv = [tool, "serve", "--bg", "--https=%d" % self.port, "http://127.0.0.1:%d" % self.port]
                    code, out = run_tool(argv)
                    if code != 0:
                        code, out = run_tool(["sudo", "-n"] + argv)
                    if code != 0:
                        sys.stderr.write("panel server: tailscale serve refused (%s)\n" % out)
                    mapped = self._mapping()
            with self.lock:
                if identity is not None:
                    self.identity = identity
                self.mapped = mapped == "yes" and bool(identity and identity["dns"])
        finally:
            with self.lock:
                self.settled = True

    def _status(self):
        code, out = run_tool(["tailscale", "status", "--json"])
        if code != 0:
            return None, False
        try:
            st = json.loads(out)
            me = st["Self"]
            users = st.get("User") or {}
        except (ValueError, KeyError, TypeError):
            return None, False
        tags = me.get("Tags") or []
        owner = "" if tags else ((users.get(str(me.get("UserID"))) or {}).get("LoginName") or "")
        identity = {"dns": (me.get("DNSName") or "").rstrip("."), "owner": owner, "tagged": bool(tags)}
        return identity, st.get("BackendState") == "Running"

    def _mapping(self):
        """What the daemon's serve config holds for the port: "yes", its HTTPS goes to this server; "other", the
        port is someone else's (left alone); "no", the lookup answered and shows nothing on the port; "unknown",
        the lookup failed, timed out or answered something that is not a serve config. Only "no" lets the server
        configure: not knowing whether the port is taken is not knowing it is free."""
        code, out = run_tool(["tailscale", "serve", "status", "--json"])
        if code != 0:
            return "unknown"
        try:
            status = json.loads(out)
        except ValueError:
            return "unknown"
        if not isinstance(status, dict):
            return "unknown"
        web, tcp = status.get("Web"), status.get("TCP")      # absent (or null) when nothing is served
        web, tcp = {} if web is None else web, {} if tcp is None else tcp
        if not isinstance(web, dict) or not isinstance(tcp, dict):
            return "unknown"
        for host, conf in web.items():
            if host.rsplit(":", 1)[-1] == str(self.port):
                handlers = conf.get("Handlers") if isinstance(conf, dict) else None
                handler = handlers.get("/") if isinstance(handlers, dict) else None
                proxy = handler.get("Proxy") if isinstance(handler, dict) else None
                return "yes" if proxy == "http://127.0.0.1:%d" % self.port else "other"
        return "other" if str(self.port) in tcp else "no"

    def view(self):
        """(origin, reach): the tailnet origin when the server is exposed there, else the local one."""
        with self.lock:
            if self.mapped:
                return "https://%s:%d" % (self.identity["dns"], self.port), "tailnet"
        return "http://127.0.0.1:%d" % self.port, "local"

    def tailnet_origin(self):
        with self.lock:
            return "https://%s:%d" % (self.identity["dns"], self.port) if self.identity and self.identity["dns"] else None

    def who(self):
        with self.lock:
            return dict(self.identity) if self.identity else None


# ------------------------------------------------------------------ the server

class Handler(BaseHTTPRequestHandler):
    server_version = SERVER_NAME
    sys_version = ""

    def __getattr__(self, attr):
        # Every method lands in one place, so who may ask is checked before anything else, for every method.
        if attr.startswith("do_"):
            return self.dispatch
        raise AttributeError(attr)

    def log_message(self, fmt, *args):
        pass

    # who may ask

    def admit(self):
        """(origin, "local" | "tailnet") of an admitted request, or None."""
        port, h = self.server.port, self.headers
        if "X-Forwarded-For" in h or "X-Forwarded-Host" in h:
            logins = h.get_all("Tailscale-User-Login") or []
            me = self.server.reach.who()
            if len(logins) != 1 or not logins[0].strip() or me is None or not me["dns"]:
                return None
            if not me["tagged"] and (not me["owner"] or logins[0] != me["owner"]):
                return None
            return "https://%s:%d" % (me["dns"], port), "tailnet"
        hosts = h.get_all("Host") or []
        if len(hosts) != 1 or hosts[0] not in ("127.0.0.1:%d" % port, "localhost:%d" % port):
            return None
        return "http://" + hosts[0], "local"

    def post_allowed(self):
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            return False
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        port = self.server.port
        own = {"http://127.0.0.1:%d" % port, "http://localhost:%d" % port}
        tailnet = self.server.reach.tailnet_origin()
        if tailnet:
            own.add(tailnet)
        return origin in own

    def dispatch(self):
        self.nonce = secrets.token_urlsafe(16)
        admitted = self.admit()
        if admitted is None:
            return self.reply(403)
        self.origin, self.via = admitted
        if self.command == "POST" and not self.post_allowed():
            return self.reply(403)
        path = self.path.split("?", 1)[0]
        if path.startswith("/control/"):
            token = self.headers.get("X-Panel-Token") or ""
            if self.via != "local" or not hmac.compare_digest(token.encode(), self.server.token.encode()):
                return self.reply(403)
            return self.control(path[len("/control/"):])
        if self.command == "GET":
            m = BASE_FILE.fullmatch(path)
            if m:
                return self.base_file(m.group(1))
        m = PAGE_PATH.fullmatch(path)
        if m:
            short, what = m.groups()
            if not self.server.panels.exists(short):
                return self.reply(404)
            if self.command == "GET" and what is None:
                return self.page(short)
            if self.command == "GET" and what == "written":
                return self.json(200, {"written": self.server.panels.page(short)[1]})
            if self.command == "POST" and what in ("seen", "check"):
                return self.panel_post(short, what)
        if self.command == "GET" and SHORT_ID.fullmatch(path[1:]) and self.server.panels.exists(path[1:]):
            return self.reply(301, headers={"Location": path + "/"})
        return self.reply(404)

    # answers

    def common_headers(self):
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src %s/base/ 'nonce-%s'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
                         "frame-ancestors 'none'" % (getattr(self, "origin", "http://127.0.0.1:%d" % self.server.port),
                                                     self.nonce))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def reply(self, code, body=b"", kind=None, headers=None):
        self.send_response(code)
        if kind:
            self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.common_headers()
        self.end_headers()
        if body:
            self.wfile.write(body)

    def json(self, code, value):
        self.reply(code, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def body(self):
        """The request's JSON, or None when it is not JSON or too long."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if not 0 <= n <= MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(n).decode() or "null")
        except (ValueError, UnicodeDecodeError):
            return None

    def base_file(self, name):
        path = os.path.join(BASE_DIR, name)
        ext = os.path.splitext(name)[1]
        if ext not in TYPES or not os.path.isfile(path):
            return self.reply(404)
        with open(path, "rb") as f:
            self.reply(200, f.read(), TYPES[ext])

    def page(self, short):
        text, written, checked, locale = self.server.panels.page(short)
        if text is None:
            text = waiting_page(locale)
        out = insert_script(text, written, checked, self.nonce)
        self.reply(200, out.encode("utf-8", "surrogateescape"), "text/html; charset=utf-8")

    def panel_post(self, short, what):
        body = self.body()
        if what == "check":
            note = body.get("note") if isinstance(body, dict) else None
            if not isinstance(note, str) or not NOTE_ID.fullmatch(note):
                return self.reply(400)
            self.server.panels.check(short, note)
        else:
            written = body.get("written") if isinstance(body, dict) else None
            if not isinstance(written, int) or isinstance(written, bool):
                return self.reply(400)
            self.server.panels.saw(short, written)
        self.reply(204)

    def control(self, verb):
        srv = self.server
        if self.command == "GET" and verb == "health":
            return self.json(200, {"server": SERVER_NAME, "version": srv.version, "root": srv.panels.root})
        if self.command != "POST" or verb not in ("open-panel", "publish", "reach", "shutdown"):
            return self.reply(404)
        body = self.body()
        if not isinstance(body, dict):
            return self.reply(400)
        if verb == "shutdown":
            self.reply(204)
            threading.Thread(target=srv.shutdown, daemon=True).start()
            return None
        try:
            if verb == "reach":
                self.await_reach(body.get("reach"))
                origin, reach = srv.reach.view()
                return self.json(200, {"address": origin + "/", "reach": reach})
            if verb == "open-panel":
                self.await_reach(body.get("reach"))
                out = srv.panels.open_panel(body.get("session"), locale_of(body.get("locale")))
            else:
                out = srv.panels.publish(body.get("session"))
        except Refused as e:
            return self.json(409, {"error": str(e)})
        except OSError as e:
            return self.json(500, {"error": "the panels directory %s cannot be written (%s)" % (srv.panels.root, e)})
        origin, reach = srv.reach.view()
        address = "%s/%s/" % (origin, short_of(body.get("session")))
        if verb == "open-panel":
            out = dict({"address": address, "reach": reach}, **out)
        else:
            out = {"published": out["published"], "address": address, "reach": reach, "written": out["written"],
                   "removed": out["removed"], "lookedMeanwhile": out["lookedMeanwhile"]}
        return self.json(200, out)

    def await_reach(self, reach):
        t = self.server.reach.ask(wants_tailnet(reach))
        if t is not None:
            t.join(REACH_WAIT)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    allow_reuse_port = False    # a second server on the port must fail to bind (later Pythons set it for HTTPServer)

    def __init__(self, port, root):
        self.port = port
        self.version = plugin_version()
        self.token = secrets.token_urlsafe(32)
        self.panels = Panels(root)
        self.reach = Reach(port, wants_tailnet(os.environ.get("PANEL_REACH")))
        super().__init__(("127.0.0.1", port), Handler)

    def server_bind(self):
        # HTTPServer.server_bind looks up the host's fully qualified name, a resolver query the server needs not.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def serve():
    port, root = panel_port(), panels_root()
    os.makedirs(root, mode=0o700, exist_ok=True)
    try:
        httpd = Server(port, root)
    except OSError as e:
        raise Refused("the panel server cannot listen on 127.0.0.1:%d (%s)" % (port, e))
    record = os.path.join(root, "server.json")
    write_json(record, {"pid": os.getpid(), "port": port, "version": httpd.version, "token": httpd.token}, 0o600)
    httpd.panels.remove_old()
    httpd.reach.ask(httpd.reach.want)
    sys.stderr.write("panel server %s: %s on http://127.0.0.1:%d/\n" % (httpd.version, root, port))
    sys.stderr.flush()
    try:
        httpd.serve_forever(poll_interval=0.25)
    finally:
        httpd.server_close()
        if read_json(record, {}).get("token") == httpd.token:
            try:
                os.unlink(record)
            except OSError:
                pass


# ------------------------------------------------------------------ the command line, a client of the server

def call(port, method, path, token=None, body=None, timeout=10):
    """(status, parsed JSON or None) of a control request; (None, None) when nothing listens."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    headers = {"Host": "127.0.0.1:%d" % port}
    if token:
        headers["X-Panel-Token"] = token
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    try:
        c.request(method, path, body=data, headers=headers)
        r = c.getresponse()
        raw = r.read()
    except ConnectionRefusedError:
        return None, None
    except (OSError, http.client.HTTPException) as e:
        return 0, {"error": str(e)}
    finally:
        c.close()
    try:
        return r.status, json.loads(raw) if raw else None
    except ValueError:
        return r.status, None


def token_of(root):
    return read_json(os.path.join(root, "server.json"), {}).get("token")


def start_detached():
    """A server of this plugin started in its own process session, through a double fork, so it outlives the
    command, the session that ran it and a hangup of its terminal; its output to server.log."""
    root = panels_root()
    os.makedirs(root, mode=0o700, exist_ok=True)
    log = os.open(os.path.join(root, "server.log"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    null = os.open(os.devnull, os.O_RDONLY)
    pid = os.fork()
    if pid == 0:
        try:
            os.setsid()
            if os.fork() != 0:
                os._exit(0)
            os.dup2(null, 0)
            os.dup2(log, 1)
            os.dup2(log, 2)
            os.execv(sys.executable, [sys.executable, os.path.realpath(__file__), "serve"])
        finally:
            os._exit(1)
    os.close(log)
    os.close(null)
    os.waitpid(pid, 0)


def wait_up(port, root, timeout=START_WAIT):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        status, info = call(port, "GET", "/control/health", token_of(root), timeout=1)
        if status == 200 and isinstance(info, dict) and info.get("server") == SERVER_NAME:
            return info
        time.sleep(0.05)
    return None


def wait_free(port, timeout=START_WAIT):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        except OSError:
            return
        time.sleep(0.05)


def ensure_server():
    """The port and token of a server of this configuration directory at this version or newer, started or
    replaced as needed."""
    port, root = panel_port(), panels_root()
    own = plugin_version()
    for attempt in range(2):
        status, info = call(port, "GET", "/control/health", token_of(root), timeout=2)
        if status is None:
            start_detached()
            if wait_up(port, root):
                return port, token_of(root)
            continue                    # another command may have started one in the same moment: ask again
        same_dir = isinstance(info, dict) and info.get("server") == SERVER_NAME and \
            os.path.realpath(str(info.get("root"))) == os.path.realpath(root)
        if status != 200 or not same_dir:
            raise Refused("port %d on this machine answers, but not as this configuration directory's panel server "
                          "(another program, or the panel server of another CLAUDE_CONFIG_DIR): PANEL_PORT names "
                          "another" % port)
        if version_key(info.get("version")) >= version_key(own):
            return port, token_of(root)
        call(port, "POST", "/control/shutdown", token_of(root), {})
        wait_free(port)
        start_detached()
        if wait_up(port, root):
            return port, token_of(root)
    raise Refused("the panel server did not start on port %d; its output is in %s"
                  % (port, os.path.join(root, "server.log")))


def control(verb, body):
    port, token = ensure_server()
    status, out = call(port, "POST", "/control/" + verb, token, body)
    if status != 200 or not isinstance(out, dict):
        raise Refused((out or {}).get("error") if isinstance(out, dict) and out.get("error")
                      else "the panel server answered %s to %s" % (status, verb))
    return out


def main(argv):
    args = list(argv)
    if not args or args[0] not in ("serve", "ensure", "open-panel", "publish"):
        sys.stderr.write("usage: server.py serve | ensure | open-panel --session <id> [--locale en|ko] | "
                         "publish --session <id>\n")
        return 2
    verb, rest = args[0], args[1:]
    opts = {}
    while rest:
        flag = rest.pop(0)
        if flag not in ("--session", "--locale") or not rest:
            sys.stderr.write("server.py %s: unexpected %s\n" % (verb, flag))
            return 2
        opts[flag[2:]] = rest.pop(0)
    try:
        if verb == "serve":
            serve()
            return 0
        if verb == "ensure":
            if not Panels(panels_root()).any():
                print("{}")
                return 0
            out = control("reach", {"reach": os.environ.get("PANEL_REACH")})
        else:
            if "session" not in opts:
                raise Refused("%s needs --session <id>" % verb)
            short_of(opts["session"])
            if verb == "open-panel":
                locale = locale_of(opts.get("locale") or os.environ.get("PANEL_LOCALE"))
                out = control("open-panel", {"session": opts["session"], "locale": locale,
                                             "reach": os.environ.get("PANEL_REACH")})
            else:
                out = control("publish", {"session": opts["session"]})
    except Refused as e:
        sys.stderr.write("server.py %s: %s\n" % (verb, e))
        return 1
    except OSError as e:             # the panels directory (or its log) cannot be made or written
        sys.stderr.write("server.py %s: the panels directory %s cannot be written (%s)\n" % (verb, panels_root(), e))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
