#!/usr/bin/env python3
"""Live check of the rows a plugin-run /reload-plugins leaves, in a real session.

The reload mod runs `/reload-plugins` itself when installed_plugins.json
shows a new install of a plugin the session runs. Its `session.append` hook
(door `command`) keeps that command's three rows (the caveat, the command
line, the `local_command` output) empty, and appends the output's text as a
system notice of the plugin's. What only a running engine shows, pinned so a
release that breaks it fails loudly:
- the transcript rows such a reload leaves (A): the three kept empty, the
  notice a system row, in that order;
- that this holds both when another plugin is updated and when doperpowers
  itself is, whose reload replaces the module whose hook sees the rows (B);
- what the screen draws for them (C): no `(no content)` line, the notice;
  the main screen is read with tmux frames around the reload, and the
  transcript view (ctrl+o) once it has settled;
- what the model is sent (D): the request after the reloads, read off a
  logging proxy between the session and the gateway, carries none of the
  reload's text; and haiku, asked to repeat what precedes the question in
  its message, repeats none of it.
The same run is made first with the plugin as the worktree has it, then (E)
with a copy whose reload mod has no `session.append` hook, for contrast: the
three rows keep their text, the screen draws the command and its output,
the request carries all of it. `--variant after|before` runs one of the two.

Unlike the other live checks the plugin is installed, not loaded with
--plugin-dir (the reload mod watches only the plugin cache): a git
marketplace, as doperpowers' own is, carries a copy of the worktree's plugin
and a skill-only probe plugin, both installed at user scope. (A directory
marketplace will not do: a reload re-reads its plugins from the folder,
outside the cache, and the mod stops watching doperpowers.) The marketplace
is a local repository reached through an https URL the temporary HOME's
gitconfig rewrites, since the engine takes no file:// source and clones
shallow, which a dumb HTTP server cannot serve. An update is what a real one
is: a version bump committed and pushed, `claude plugin marketplace update`,
`claude plugin update`. The mod looks at installed_plugins.json every 15 s
and acts once it has been quiet one period, so each reload lands 15 to 30 s
after its update.

It spends model calls (haiku, three short prompts per variant), so no suite
runs it: run it by hand with the model gateway's keys in the environment.
Isolation is live-bridge-check.py's (whose class it extends): a temporary
HOME whose .claude is the session's config dir, a temporary SMINOS_HOME, a
tmux server of its own, the gateway keys in a 0600 env file removed at the
end. With --keep the temporary directory stays, holding each reload's rows
and screen frames, the requests the proxy saw (their bodies, never their
headers) and the session's debug log.

    tests/mods/live-reload-rows-check.py [--variant after|before] [--keep]
"""

import collections
import glob
import gzip
import http.client
import http.server
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
wait_for = LB.wait_for

MARKET = "rlmp"
MARKET_URL = "https://rlcheck.invalid/rlmp.git"
PROBE = "rlprobe"
QUESTION = "RLCHECK-ECHO"
# Text that is the reload's own, in any of its rows.
RELOAD_TEXT = ("<local-command-caveat>", "<command-name>/reload-plugins", "<local-command-stdout>", "Reloaded:")
NOTICE = "/reload-plugins, run by doperpowers: "
DEBUG_WORDS = ("loaded (worker", "unloaded", "session.append", "command.run", "reload:", "refreshActivePlugins",
               "$.ui.", "re-entry")
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "trailers",
       "transfer-encoding", "upgrade", "host"}


def claude_bin():
    """The engine itself, not a terminal app's wrapper of it earlier on PATH."""
    for d in os.environ.get("PATH", "").split(":"):
        path = os.path.join(d, "claude")
        if "cmux" not in d and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    sys.exit("live-reload-rows-check: no claude on PATH")


CLAUDE = claude_bin()


class Proxy:
    """Relays every request to the gateway as it is, and keeps the bodies of the model requests."""

    def __init__(self, upstream, log):
        u = urllib.parse.urlsplit(upstream)
        if u.scheme not in ("http", "https"):
            sys.exit("live-reload-rows-check: the gateway's URL is not http(s): %s" % upstream)
        self.log, self.lock = log, threading.Lock()
        conn_class = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        base = u.path.rstrip("/")
        proxy = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def body(self):
                if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                    out = b""
                    while True:
                        size = int(self.rfile.readline().split(b";")[0], 16)
                        if size == 0:
                            self.rfile.readline()
                            return out
                        out += self.rfile.read(size)
                        self.rfile.readline()
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def relay(self):
                body = self.body()
                if self.command == "POST" and "/messages" in self.path:
                    proxy.record(self.path, body, self.headers.get("Content-Encoding", ""))
                conn = conn_class(u.hostname, u.port, timeout=600)
                headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
                headers["Host"] = u.netloc
                conn.request(self.command, base + self.path, body=body or None, headers=headers)
                r = conn.getresponse()
                self.send_response_only(r.status, r.reason)
                for k, v in r.getheaders():
                    if k.lower() not in HOP:
                        self.send_header(k, v)
                self.send_header("Connection", "close")
                self.end_headers()
                while True:
                    chunk = r.read1(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                conn.close()

            do_GET = do_POST = do_HEAD = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = relay

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]

    def record(self, path, raw, encoding):
        try:
            data = json.loads(gzip.decompress(raw) if "gzip" in encoding.lower() else raw)
        except ValueError:
            data = {"undecoded": len(raw), "encoding": encoding}
        with self.lock, open(self.log, "a") as f:
            f.write(json.dumps({"t": time.time(), "path": path, "body": data}) + "\n")

    def requests(self):
        try:
            with open(self.log) as f:
                return [json.loads(line) for line in f]
        except OSError:
            return []

    def close(self):
        self.server.shutdown()


def blocks_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else "" for b in content)
    return ""


def row_text(row):
    if row.get("type") == "system":
        return blocks_text(row.get("content"))
    return blocks_text((row.get("message") or {}).get("content"))


def row_line(row):
    """A row as the report quotes it: its type, subtype, isMeta, origin and content."""
    content = row.get("content") if row.get("type") == "system" else (row.get("message") or {}).get("content")
    keep = {k: row[k] for k in ("type", "subtype", "isMeta", "origin", "level") if k in row}
    keep["content"] = content if not isinstance(content, str) or len(content) < 240 else content[:240] + "…"
    if row.get("type") == "attachment":
        keep["attachment"] = str(row.get("attachment"))[:160]
    return json.dumps(keep, ensure_ascii=False)


def lines_of(pane):
    return [l.rstrip() for l in pane.splitlines() if l.strip()]


def added(before, after):
    """The lines of `after` beyond those of `before`, counted: a reload's lines can repeat an earlier reload's."""
    left = collections.Counter(before)
    out = []
    for line in after:
        if left[line] > 0:
            left[line] -= 1
        else:
            out.append(line)
    return out


def is_output(row):
    return row.get("type") == "system" and row.get("subtype") == "local_command"


def bump(version):
    head, _, last = version.rpartition(".")
    return "%s.%d" % (head, int(last) + 1)


def strip_rows_hook(path):
    """The reload mod without its session.append hook: what the session ran before the change."""
    with open(path) as f:
        src = f.read()
    start = src.index("  let isOutputDue = false\n")
    end = src.index("  on('session.start'", start)
    out = src[:start] + src[end:]
    assert "on('session.append'" not in out, "the hook is still in the copy"
    with open(path, "w") as f:
        f.write(out)


class ReloadRows(LB.Live):
    def __init__(self, keep, variant):
        super().__init__(keep)
        self.variant = variant
        self.root = os.path.realpath(self.root)  # /tmp is a link on macOS: one spelling of the paths the mod compares
        self.home = os.path.join(self.root, "home")
        self.cfg = os.path.join(self.home, ".claude")
        self.smh = os.path.join(self.root, "s")
        self.work = os.path.join(self.root, "work")
        self.envfile = os.path.join(self.root, "env")
        self.market = os.path.join(self.root, "market")
        self.plugin = os.path.join(self.market, "doperpowers")
        self.debug = os.path.join(self.root, "debug.log")
        self.proxy = None
        self.versions = {}
        self.label = variant

    def local_env(self):
        env = super().local_env()
        env["PATH"] = ":".join(d for d in env.get("PATH", "").split(":") if "cmux" not in d)
        return env

    def check(self, name, ok, detail):
        super().check("[%s] %s" % (self.label, name), ok, detail)

    # -- the marketplace and the installs

    def setup(self):
        for k in LB.GATEWAY_KEYS:
            if k not in os.environ:
                sys.exit("live-reload-rows-check: the gateway keys are not in the environment: %s" % k)
        self.proxy = Proxy(os.environ["ANTHROPIC_BASE_URL"], os.path.join(self.root, "requests.jsonl"))
        super().setup()  # copies the worktree's plugin into the marketplace, as self.plugin
        shutil.copytree(os.path.join(LB.REPO, "types"), os.path.join(self.plugin, "types"))
        os.unlink(os.path.join(self.plugin, ".claude-plugin", "marketplace.json"))
        if self.variant == "before":
            strip_rows_hook(os.path.join(self.plugin, "hooks", "mods", "reload.tsx"))
        with open(os.path.join(self.plugin, ".claude-plugin", "plugin.json")) as f:
            self.versions["doperpowers"] = json.load(f)["version"]
        probe = os.path.join(self.market, PROBE)
        os.makedirs(os.path.join(probe, ".claude-plugin"))
        os.makedirs(os.path.join(probe, "skills", PROBE))
        self.versions[PROBE] = "1.0.0"
        with open(os.path.join(probe, ".claude-plugin", "plugin.json"), "w") as f:
            json.dump({"name": PROBE, "version": "1.0.0", "description": "A probe the live check updates."}, f)
        with open(os.path.join(probe, "skills", PROBE, "SKILL.md"), "w") as f:
            f.write("---\nname: %s\ndescription: A probe skill; never use it.\n---\nNothing.\n" % PROBE)
        self.write_market()
        with open(self.envfile, "a") as f:
            f.write("export ANTHROPIC_BASE_URL=%s\n" % shlex.quote(self.proxy.url))
        # A git marketplace, as doperpowers' own is: its plugins load from the
        # cache at the clone's version. (A directory marketplace's are re-read
        # from the folder on a reload, which the mod does not watch.) The
        # engine clones shallow, which file:// serves and a dumb HTTP server
        # does not; an https URL is what it accepts, rewritten by the HOME's
        # gitconfig.
        gitconfig = os.path.join(self.home, ".gitconfig")
        for key, value in (("user.name", "live-reload-rows-check"), ("user.email", "check@rlcheck.invalid"),
                           ("url.file://%s.git.insteadOf" % self.market, MARKET_URL)):
            subprocess.run(["git", "config", "--file", gitconfig, key, value], check=True)
        self.git("-c", "init.defaultBranch=main", "init", "-q", self.market)
        self.git("-C", self.market, "add", "-A")
        self.git("-C", self.market, "commit", "-qm", "the marketplace")
        self.git("clone", "-q", "--bare", self.market, self.market + ".git")
        self.cli("plugin", "marketplace", "add", MARKET_URL)
        for name in ("doperpowers", PROBE):
            self.cli("plugin", "install", "%s@%s" % (name, MARKET), "--scope", "user")
        records = self.installed()
        with open(os.path.join(self.cfg, "settings.json")) as f:
            enabled = json.load(f).get("enabledPlugins", {})
        for name in ("doperpowers", PROBE):
            key = "%s@%s" % (name, MARKET)
            if not records.get(key) or enabled.get(key) is not True:
                raise RuntimeError("%s is not installed and enabled: %s, %s" % (key, records.get(key), enabled))

    def write_market(self):
        os.makedirs(os.path.join(self.market, ".claude-plugin"), exist_ok=True)
        with open(os.path.join(self.market, ".claude-plugin", "marketplace.json"), "w") as f:
            json.dump({"name": MARKET, "owner": {"name": "live-reload-rows-check"},
                       "plugins": [{"name": n, "version": v, "source": "./" + n} for n, v in sorted(self.versions.items())]},
                      f, indent=2)

    def git(self, *args):
        subprocess.run(["git"] + list(args), env=self.local_env(), check=True, capture_output=True)

    def cli(self, *args):
        r = subprocess.run([CLAUDE] + list(args), cwd=self.root, env=self.local_env(), capture_output=True, text=True,
                           timeout=180)
        if r.returncode != 0:
            raise RuntimeError("claude %s: exit %d: %s" % (" ".join(args), r.returncode, (r.stderr or r.stdout).strip()[-400:]))
        return r.stdout

    def installed(self):
        with open(os.path.join(self.cfg, "plugins", "installed_plugins.json")) as f:
            return json.load(f)["plugins"]

    def update(self, name):
        """A new version of `name`, the way a real update lands: the marketplace carries it, `claude plugin update` installs it."""
        new = bump(self.versions[name])
        manifest = os.path.join(self.market, name, ".claude-plugin", "plugin.json")
        with open(manifest) as f:
            data = json.load(f)
        data["version"] = new
        with open(manifest, "w") as f:
            json.dump(data, f, indent=2)
        self.versions[name] = new
        self.write_market()
        self.git("-C", self.market, "commit", "-qam", "%s %s" % (name, new))
        self.git("-C", self.market, "push", "-q", self.market + ".git", "main")
        self.cli("plugin", "marketplace", "update", MARKET)
        out = self.cli("plugin", "update", "%s@%s" % (name, MARKET), "--scope", "user")
        path = self.installed()["%s@%s" % (name, MARKET)][0]["installPath"]
        if not path.endswith("/" + new):
            raise RuntimeError("the update did not install %s %s: %s / %s" % (name, new, path, out.strip()[-200:]))
        return new

    # -- the session

    def start_session(self):
        inner = ("set -e; . %s; cd %s; exec %s --model haiku --permission-mode default -n %s --debug-file %s") % (
            shlex.quote(self.envfile), shlex.quote(self.work), shlex.quote(CLAUDE), LB.NAME, shlex.quote(self.debug))
        cmd = "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)
        subprocess.run(self.tmux + ["new-session", "-d", "-s", "brl", "-x", "200", "-y", "50", cmd], check=True)

    def rows(self):
        out = []
        for path in glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl")):
            with open(path) as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        return out

    def reply_after(self, n, marker=None):
        """The first assistant text after row n (and after the user row holding `marker`, if given)."""
        rows = self.rows()[n:]
        if marker is not None:
            at = [i for i, r in enumerate(rows) if r.get("type") == "user" and marker in row_text(r)]
            if not at:
                return None
            rows = rows[at[0] + 1:]
        texts = [row_text(r) for r in rows if r.get("type") == "assistant" and row_text(r).strip()]
        return texts[0] if texts else None

    def debug_lines(self, offset, words=DEBUG_WORDS):
        try:
            with open(self.debug, errors="replace") as f:
                f.seek(offset)
                text = f.read()
        except OSError:
            return []
        return [l.rstrip()[:220] for l in text.splitlines() if any(w in l for w in words)]

    def debug_size(self):
        try:
            return os.path.getsize(self.debug)
        except OSError:
            return 0

    def save(self, name, data):
        with open(os.path.join(self.root, name), "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data, indent=1, ensure_ascii=False))

    # -- one reload

    def observe_reload(self, name, label):
        """Updates `name` and watches the transcript and the screen until the reload's rows have landed."""
        n0 = len(self.rows())
        base = lines_of(self.pane())
        new_lines, frames = [], []
        dbg0 = self.debug_size()
        t0 = time.time()
        version = self.update(name)

        def look():
            pane = self.pane()
            if not frames or frames[-1][1] != pane:
                frames.append((round(time.time() - t0, 2), pane))
            for line in added(base, lines_of(pane)):
                if line not in new_lines:
                    new_lines.append(line)
            rows = self.rows()[n0:]
            return rows if any(is_output(r) for r in rows) else None

        wait_for("the reload's output row after the %s update (%s)" % (name, label), 120, look, every=0.25)
        landed = time.time() - t0
        settle = time.time() + 6
        while time.time() < settle:
            look()
            time.sleep(0.25)
        rows = self.rows()[n0:]
        final = self.pane()
        # The transcript view (ctrl+o) draws verbose: what the main screen leaves out.
        self.keys("C-o")
        time.sleep(2)
        tview = self.pane()
        self.keys("C-o")
        try:
            wait_for("the main screen again", 10, lambda: "for shortcuts" in self.pane())
        except TimeoutError:
            self.keys("Escape")
            wait_for("the main screen again", 10, lambda: "for shortcuts" in self.pane())
        self.save("rows-%s.json" % label, rows)
        self.save("frames-%s.txt" % label, "\n".join("=== +%ss\n%s" % (t, p) for t, p in frames))
        self.save("transcript-view-%s.txt" % label, tview)
        print("  -- %s: %s updated to %s; the reload's output row landed %.1f s later; the rows since the update:" % (
            label, name, version, landed), flush=True)
        for r in rows:
            print("       " + row_line(r), flush=True)
        print("     screen lines drawn since the update (any frame, %d frames):" % len(frames), flush=True)
        for l in new_lines:
            print("       | " + l, flush=True)
        final_new = added(base, lines_of(final))
        print("     of those, on the screen once settled:", flush=True)
        for l in final_new:
            print("       | " + l, flush=True)
        print("     the transcript view (ctrl+o), from the first reply on:", flush=True)
        tlines = lines_of(tview)
        start = max([i for i, l in enumerate(tlines) if "ready" in l] or [0])
        for l in tlines[start:start + 30]:
            print("       : " + l[:190], flush=True)
        dbg = self.debug_lines(dbg0)
        print("     the debug log since the update, on the module, the command and the appends:", flush=True)
        for l in dbg:
            print("       ~ " + l, flush=True)
        self.judge_reload(label, rows, new_lines, final_new, tlines)

    def judge_reload(self, label, rows, drawn, settled, tview):
        users = [i for i, r in enumerate(rows) if r.get("type") == "user"]
        caveat = [i for i in users if rows[i].get("isMeta")]
        command = [i for i in users if not rows[i].get("isMeta")]
        output = [i for i, r in enumerate(rows) if is_output(r)]
        notice = [i for i, r in enumerate(rows) if r.get("type") == "system" and row_text(r).startswith(NOTICE)]
        held = sorted({t for r in rows if not row_text(r).startswith(NOTICE) for t in RELOAD_TEXT if t in row_text(r)})
        texts = {"caveat": [row_text(rows[i]) for i in caveat], "command": [row_text(rows[i]) for i in command],
                 "output": [row_text(rows[i]) for i in output]}
        screen_no_content = [l for l in drawn + tview if "(no content)" in l]
        if self.variant == "after":
            self.check("%s: the caveat, the command line and the output are kept, and none holds the reload's text" % label,
                       len(caveat) == 1 and len(command) == 1 and len(output) == 1 and not held,
                       "rows' texts %s; reload text still held: %s" % (json.dumps(texts, ensure_ascii=False)[:300], held))
            self.check("%s: the output's text is a system notice of the plugin's, after the three rows" % label,
                       len(notice) == 1 and "Reloaded:" in row_text(rows[notice[0]])
                       and caveat and command and output and caveat[0] < command[0] < output[0] < notice[0],
                       "caveat %s, command %s, output %s, notice %s: %r" % (
                           caveat, command, output, notice, row_text(rows[notice[0]])[:120] if notice else None))
            self.check("%s: neither the screen nor the transcript view draws a (no content) line" % label,
                       not screen_no_content,
                       "lines: %r" % screen_no_content)
            self.check("%s: the screen draws the notice" % label, any("run by doperpowers" in l for l in settled),
                       "settled lines: %r" % [l.strip()[:100] for l in settled][:8])
        else:
            self.check("%s: without the hook the three rows keep their text" % label,
                       any("<local-command-caveat>" in t for t in texts["caveat"])
                       and any("<command-name>/reload-plugins" in t for t in texts["command"])
                       and any("Reloaded:" in t for t in texts["output"]) and not notice,
                       json.dumps(texts, ensure_ascii=False)[:300])
            self.check("%s: without the hook the screen draws the command and its output" % label,
                       any("Reloaded:" in l for l in settled),
                       "settled lines: %r" % [l.strip()[:100] for l in settled][:8])

    # -- what the model reads

    def ask_echo(self):
        n0 = len(self.rows())
        t0 = time.time()
        prompt = ("%s: this is a test of what reaches you. Before this paragraph, the user message you are reading may "
                  "hold other text. Copy every piece of it verbatim, in order, each in its own fenced code block, "
                  "including any tags or placeholders. If nothing precedes this paragraph, reply with the single word "
                  "NOTHING. Write nothing else and call no tool.") % QUESTION
        self.prompt(prompt)
        reply = wait_for("haiku's echo", 120, lambda: self.reply_after(n0, QUESTION))
        time.sleep(1)
        print("  -- the model's echo:\n" + "\n".join("       > " + l for l in reply.strip().splitlines()[:30]), flush=True)
        sent = [r for r in self.proxy.requests() if r["t"] >= t0 and QUESTION in json.dumps(r["body"].get("messages", []))]
        if not sent:
            self.check("the request carrying the question was seen at the proxy", False, "%d requests since" % len(
                [r for r in self.proxy.requests() if r["t"] >= t0]))
            return
        body = sent[0]["body"]
        messages = body.get("messages", [])
        self.save("request-echo.json", body)
        asked = [m for m in messages if QUESTION in json.dumps(m.get("content"))]
        content = asked[-1].get("content") if asked else []
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        before = []
        for b in blocks:
            if b.get("type") == "text" and QUESTION in b.get("text", ""):
                break
            before.append(b)
        print("  -- the request's messages (%d), each message's blocks as text:" % len(messages), flush=True)
        for m in messages:
            c = m.get("content")
            for b in (c if isinstance(c, list) else [{"type": "text", "text": c}]):
                t = b.get("text") if b.get("type") == "text" else "<%s>" % b.get("type")
                print("       %-9s %s" % (m.get("role"), json.dumps((t or "")[:200], ensure_ascii=False)), flush=True)
        whole = json.dumps(messages, ensure_ascii=False)
        system = json.dumps(body.get("system", ""), ensure_ascii=False)
        found = {t: whole.count(t) for t in RELOAD_TEXT + ("(no content)", "run by doperpowers")}
        found_system = {t: system.count(t) for t in RELOAD_TEXT + ("run by doperpowers",) if t in system}
        if self.variant == "after":
            self.check("the request after the reloads carries none of their text, nor the notice",
                       not any(found[t] for t in RELOAD_TEXT + ("run by doperpowers",)) and not found_system,
                       "counts in the messages %s, in the system prompt %s; blocks before the question %s" % (
                           found, found_system, json.dumps(before, ensure_ascii=False)[:300]))
            self.check("the model repeats none of the reload's text",
                       not any(t in reply for t in RELOAD_TEXT + ("run by doperpowers",)), reply.strip()[:200])
        else:
            self.check("without the hook the request carries the reloads' caveat, command line and output",
                       all(found[t] for t in RELOAD_TEXT), "counts in the messages %s" % found)

    # -- the whole run

    def run(self):
        print("live reload-rows check, %s (%s):" % (self.variant, self.root), flush=True)
        self.setup()
        self.start_session()
        sock_dir = os.path.join(self.smh, "bridge")
        found = wait_for("the bridge's socket", 90, lambda: [n for n in os.listdir(sock_dir)
                                                             if n.endswith(".sock") and not n.startswith(".")]
                         if os.path.isdir(sock_dir) else None)
        self.session = found[0][:-5]
        n0 = len(self.rows())
        self.prompt("Reply with the single word ready and nothing else.")
        wait_for("the first reply", 120, lambda: self.reply_after(n0))
        time.sleep(2)
        self.observe_reload(PROBE, "probe-only")
        self.observe_reload("doperpowers", "doperpowers-itself")
        self.ask_echo()

    def cleanup(self):
        super().cleanup()
        if self.proxy is not None:
            self.proxy.close()


def main():
    args = sys.argv[1:]
    keep = "--keep" in args
    variants = ["after", "before"]
    if "--variant" in args:
        v = args[args.index("--variant") + 1]
        if v not in variants:
            sys.exit("--variant: after or before")
        variants = [v]
    results = []
    for variant in variants:
        live = ReloadRows(keep, variant)
        try:
            live.run()
        except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
            live.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
            print("  pane at the failure:\n" + "\n".join("    " + l for l in live.pane().rstrip().splitlines()[-25:]))
            dbg = live.debug_lines(0)
            print("  the debug log's last lines on the module, the command and the appends:\n" + "\n".join("    " + l for l in dbg[-20:]))
        finally:
            live.cleanup()
        results += live.results
    failed = [r for r in results if not r[1]]
    print("%s: %d of %d checks passed" % ("FAILED" if failed else "passed", len(results) - len(failed), len(results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
