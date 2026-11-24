"""sminos's internal fork code: a question put to a fork of a session, which
the session never sees. No CLI verb: `derive` and the session manager's
`manager query` call it (design
docs/doperpowers/specs/2026-10-31-session-manager-design.md, §Queries and
§`derive` on `btw`).

Three ways to fork a session, and what each costs:

- `btw` (ask_btw), the bridge's side question: one tool-less completion over
  the session's last request, reading the session's whole prompt cache,
  invisible in the session. A live session whose bridge offers it.
- the fork agent (ask_fork_agent), the bridge's `ask`: a forked subagent
  inside the session, with the session's tools held read-only by
  doperpowers' fork guard, reading the session's cache. A live session whose
  bridge offers it and has the guard loaded (else refused `no-guard`).
- the headless fork (headless_fork): `claude -p --resume <session>
  --fork-session`, a process of its own that never reads the session's cache
  (its system prompt and tools differ from the session's), for a session
  that is not running or whose bridge cannot do the above.

A bridge op subscribes to the session's stream first, posts the op, and waits
for its end by the op's id. A silence past the timeout leaves the fork to
finish on its own: stopping it through the bridge would leave a note in the
session's conversation.

Beside the forks, `find` asks a model afresh (ask_model: no session behind
it; docs/doperpowers/specs/2026-11-23-sminos-session-search-design.md, §3b).
It and the headless fork are both internal processes, started and cleaned
up by one helper (run_internal).
"""

import glob
import json
import os
import queue
import subprocess
import time
import uuid as uuidlib
from typing import NamedTuple

import sminos as S
import sminos_bridge as B
import sminos_control as C

# The frame the headless fork's question is put under: bridge-ask.tsx's
# ASK_FRAME, word for word (the bridge adds that one itself for the fork
# agent). A test pins the two the same.
FORK_FRAME = ("You are a read-only fork of this session, started by the owner's manager session to answer one question. "
              "The session itself never sees this exchange, and nothing you do here reaches it. Do not continue the "
              "session's task. You may use read-only tools (reading and searching files, read-only shell commands such "
              "as git log, git status or gh pr view) to check facts; anything that would change a file or any state is "
              "refused. Answer the question directly, then stop.")

# The tools a headless fork with tools may use; auto mode refuses what it
# judges risky, and the frame asks for reading only (the owner's call).
HEADLESS_TOOLS = "Read,Grep,Glob,Bash"


class ForkAnswer(NamedTuple):
    text: str
    via: str            # "btw" | "fork agent" | "headless fork"
    usage: dict         # {"input", "output", "cacheRead", "cacheWrite"}
    truncated: bool


class ForkFailed(Exception):
    """A fork that gave no answer. `reason` is one line (at most
    sminos.DERIVE_WHY_MAX characters), `stderr` a headless fork's, `code` the
    bridge's refusal code, or the end's reason (`api-error`, `aborted`,
    `empty-reply`, `failed`, `nothing-to-fork`), or `timeout`; "" otherwise."""

    def __init__(self, reason, stderr="", code=""):
        super().__init__(reason)
        self.reason, self.stderr, self.code = reason, stderr, code


def _usage(u):
    """An end's usage (`{input, output, cacheRead, cacheWrite}`), every count an int."""
    u = u if isinstance(u, dict) else {}
    return {k: int(u.get(k) or 0) for k in ("input", "output", "cacheRead", "cacheWrite")}


def _result_usage(u):
    """A `claude -p` result's usage in the end's shape."""
    u = u if isinstance(u, dict) else {}
    return {"input": int(u.get("input_tokens") or 0), "output": int(u.get("output_tokens") or 0),
            "cacheRead": int(u.get("cache_read_input_tokens") or 0),
            "cacheWrite": int(u.get("cache_creation_input_tokens") or 0)}


def _line(text):
    return " ".join(str(text).split())[:S.DERIVE_WHY_MAX]


# ------------------------------------------------------------------ through the bridge


def bridge_offers(session, op):
    """Whether the session's bridge answers and its capabilities list `op`
    among its ops (an observer's list none), and do not mark that control
    unavailable."""
    status = B.probe(B.endpoint(session))
    caps = (status or {}).get("capabilities")
    if not isinstance(caps, dict) or not isinstance(caps.get("ops"), list) or op not in caps["ops"]:
        return False
    control = caps.get("controls", {}).get(op) if isinstance(caps.get("controls"), dict) else None
    return not (isinstance(control, dict) and control.get("available") is False)


def _ended_without_answer(what, e):
    """Why an end carries no answer, as one line."""
    reason = str(e.get("reason") or "empty-reply")
    if reason == "api-error":
        why = "its request failed (HTTP %s%s)" % (e.get("status"), ": %s" % e["error"] if e.get("error") else "")
    elif reason == "aborted":
        why = "it was aborted"
    elif reason == "empty-reply":
        why = "it answered nothing"
    elif reason == "nothing-to-fork":
        why = "the session has made no model request to fork"
    else:
        why = "%s%s" % (reason, ": %s" % e["error"] if e.get("error") else "")
    return _line("the %s ended without an answer: %s" % (what, why))


# How often an ask whose end has not reached the stream looks for it where
# the bridge's child keeps it (_ask_bridge).
KEPT_POLL_S = 0.5
# How long an ask's bridge may answer nowhere before it is taken as gone (a
# reload's new child takes a moment to come up).
CHILDLESS_S = 10


def _ask_bridge(session, op, prompt, timeout, via, what, kept=False):
    """`op {prompt}` on the session's bridge, its end awaited on the stream
    subscribed before it went. The subscription is closed however this
    ends (derive --all asks one member after another in one process); the
    fork is not stopped by it.

    `kept`: the op goes with an `rpc` nonce of its own, so the bridge's child
    keeps its answer, and then its end, under that nonce in its kept file,
    as it does a desk RPC's, and a child that replaces it (a reload of the
    module) takes the nonce up from that file. A reload mid-op can post the
    end to the new child before any subscriber is back on its stream, so an
    end the stream has not brought is looked for there until the timeout."""
    path = B.endpoint(session)
    events = C.follow_stream(path)
    try:
        return _asked(events, session, path, op, prompt, timeout, via, what,
                      "manager-%s" % uuidlib.uuid4().hex if kept else None)
    finally:
        events.close()


def kept_end(session, nonce):
    """The end the session's bridge child kept beside the answer to the op
    sent with `nonce`, or None."""
    end = ((B.load_kept(session).get("rpcs") or {}).get(nonce) or {}).get("end")
    return end if isinstance(end, dict) else None


def _asked(events, session, path, op, prompt, timeout, via, what, nonce):
    try:
        first = events.get(timeout=C.FIRST_WAIT_S)
    except queue.Empty:
        first = None
    if not first or first.get("type") != "snapshot":
        raise ForkFailed("the session's bridge did not stream", code="no-stream")
    try:
        r = C.post_command(path, {"op": op, "prompt": prompt, **({"rpc": nonce} if nonce else {})})
    except C.Unanswered as e:
        raise ForkFailed(_line("the session's bridge gave no answer: %s" % e))
    if r is None:
        raise ForkFailed("no bridge answers for the session", code="no-bridge")
    status, out = r
    out = out if isinstance(out, dict) else {}
    if status != 200:
        raise ForkFailed(_line("the session's bridge answered %d: %s" % (status, out.get("error"))))
    if not out.get("ok"):
        raise ForkFailed(_line(out.get("error") or "the %s was refused" % what), code=str(out.get("code") or ""))
    oid = (out.get("result") or {}).get("id") or out.get("id")
    deadline = time.monotonic() + timeout
    streaming, e, childless = True, None, None
    while True:
        left = deadline - time.monotonic()
        if streaming:
            try:
                got = events.get(timeout=max(0.0, min(left, KEPT_POLL_S) if nonce else left))
            except queue.Empty:
                got = False
            if got is None:
                streaming = False   # the child went, or another replaced it
            elif got and got.get("type") == op and got.get("phase") == "end" and got.get("id") == oid:
                e = got
                break
        if nonce:
            e = kept_end(session, nonce)
            if e is not None:
                break
        if not streaming and not nonce:
            raise ForkFailed("the session's bridge ended before the %s did" % what, code="ended")
        if not streaming:
            # A reload leaves no child for a moment before its new one: only a bridge gone for longer is gone.
            if B.probe(path) is not None:
                childless = None
            elif childless is None:
                childless = time.monotonic()
            elif time.monotonic() - childless > CHILDLESS_S:
                raise ForkFailed("the session's bridge ended before the %s did" % what, code="ended")
        if left <= 0:
            raise ForkFailed("the %s gave no answer within %d s" % (what, timeout), code="timeout")
        if not streaming:
            time.sleep(max(0.0, min(left, KEPT_POLL_S)))
    text = e.get("text")
    if e.get("reason") or not isinstance(text, str) or not text.strip():
        raise ForkFailed(_ended_without_answer(what, e), code=str(e.get("reason") or "empty-reply"))
    return ForkAnswer(text, via, _usage(e.get("usage")), e.get("truncated") is True)


def ask_btw(session, prompt, timeout=120):
    """The session's side question (`btw`): the bridge puts `prompt` under its
    own frame (BTW_FRAME). It goes with no `rpc` nonce, unlike `ask`: the
    daemon relays a bridge's `btw` events to the desk as DX4 `op` only under
    a nonce, so one with none stays on the machine; a reload mid-question
    costs derive its timeout, then the headless fork."""
    return _ask_bridge(session, "btw", prompt, timeout, "btw", "side question")


def ask_fork_agent(session, prompt, timeout=300):
    """The session's fork agent (`ask`): the bridge puts `prompt` under
    ASK_FRAME, with the tail of a running turn."""
    return _ask_bridge(session, "ask", prompt, timeout, "fork agent", "fork agent", kept=True)


# ------------------------------------------------------------------ headless


def fork_failure(obj, err):
    """Why a headless fork ended without an answer, as one line of at most
    DERIVE_WHY_MAX characters: its result's error text when it reported an
    error, else the head of its stderr; "" when it said nothing."""
    said = []
    if obj and obj.get("is_error"):
        errors = obj.get("errors")
        said = [str(obj.get("result") or "")] + ([str(e) for e in errors] if isinstance(errors, list) else [])
    text = " ".join(" ".join(said).split()) or " ".join((err or "").split())
    return text[:S.DERIVE_WHY_MAX]


# The gate an internal process starts behind: the shell waits on fd N for the
# release line and execs the engine only after a successful read, so a parent
# that died or failed before marking it (end of file on the gate) starts nothing.
GATE = 'read -r _ <&%d || exit 1; exec %d<&-; exec "$@"'


def _stop(proc):
    """Kill and reap a child the gate still holds."""
    proc.kill()
    proc.communicate()


def run_internal(args, *, cwd, env, timeout, stdin_text=None, cleanup=None, what="fork"):
    """Run `args` (a `claude -p … --output-format json` call) as an internal
    process: started behind GATE, its pid marked internal under
    $SMINOS_HOME/internal/ before the release, so the record hook
    (SMNS_INTERNAL in `env`) and reconciliation never take it for a member;
    then run to its end or `timeout`, `stdin_text` on its standard input
    (none: /dev/null). Any failure between the start and the release kills
    and reaps the child before ForkFailed. Its JSON result, read from the
    last `{` line of its stdout, is returned when it exited 0, reported no
    error and answered something; ForkFailed otherwise, `what` naming it in
    the reason. Whatever the outcome, `cleanup(result or None)` removes
    what the engine wrote anyway (the caller knows where: a transcript under
    the id it minted), and the marker is removed after it, even when the
    cleanup raises."""
    gate_r, gate_w = os.pipe()
    marker = ""
    out = err = ""
    obj = None
    try:
        try:
            proc = subprocess.Popen(["/bin/sh", "-c", GATE % (gate_r, gate_r), "sh"] + list(args), cwd=cwd, env=env,
                                    stdin=subprocess.DEVNULL if stdin_text is None else subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, pass_fds=(gate_r,))
        except OSError as e:
            raise ForkFailed("the %s did not start: %s" % (what, e))
        finally:
            os.close(gate_r)
        try:
            os.makedirs(os.path.join(S.root(), "internal"), mode=0o700, exist_ok=True)
            marker = os.path.join(S.root(), "internal", str(proc.pid))
            open(marker, "w").close()
            os.write(gate_w, b"\n")
        except BaseException as e:
            _stop(proc)
            if isinstance(e, Exception):
                raise ForkFailed("its %s could not be marked internal: %s" % (what, e)) from e
            raise
        os.close(gate_w)
        gate_w = -1
        try:
            out, err = proc.communicate(input=stdin_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            why = fork_failure(None, err)
            raise ForkFailed("the %s timed out after %ds%s" % (what, timeout, ": " + why if why else ""), err,
                             code="timeout")
        except BaseException:
            # An interrupt (or anything) mid-wait: the engine is stopped and reaped before its transcript and
            # its marker are removed, never left running unmarked.
            proc.kill()
            proc.wait()
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()
            raise
        for raw in reversed((out or "").splitlines()):
            if raw.strip().startswith("{"):
                try:
                    d = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    obj = d
                    break
        if proc.returncode != 0 or obj is None or obj.get("is_error"):
            why = fork_failure(obj, err)
            raise ForkFailed("the %s failed (exit %d)%s" % (what, proc.returncode, ": " + why if why else ""), err)
        if not str(obj.get("result") or "").strip():
            raise ForkFailed("the %s answered nothing" % what, err, code="empty-reply")
        return obj
    finally:
        if gate_w != -1:
            os.close(gate_w)
        try:
            if cleanup is not None:
                cleanup(obj)
        finally:
            if marker:
                try:
                    os.unlink(marker)
                except FileNotFoundError:
                    pass


def headless_fork(project, m, prompt, *, tools, cache, timeout):
    """Fork member `m`'s session headless and ask it `prompt`, as an
    internal process (run_internal). It starts in safe mode and persists
    nothing; its session id is minted here (`--session-id`) all the same, so
    a transcript an engine wrote anyway is known and deleted whatever the
    outcome. `tools` False offers it none (`--tools ""`), True the read-only
    set under auto mode; `cache` False sends it uncached
    (DISABLE_PROMPT_CACHING). The prompt comes last: `--tools` takes several
    values and would swallow a prompt right after it."""
    fork = str(uuidlib.uuid4())
    env = {**os.environ, "SMNS_INTERNAL": "1"}
    if cache:
        env.pop("DISABLE_PROMPT_CACHING", None)
    else:
        env["DISABLE_PROMPT_CACHING"] = "1"
    args = ["claude", "-p", "--resume", m.session, "--fork-session", "--session-id", fork, "--safe-mode",
            "--no-session-persistence"]
    args += ["--permission-mode", "auto", "--tools", HEADLESS_TOOLS] if tools else ["--tools", ""]
    args += ["--output-format", "json", prompt]

    def cleanup(obj):
        # The minted id, and the one its result names (an engine that ignored --session-id), looked up as the
        # machine's transcripts are; never the session it resumed.
        for sid in {fork, str((obj or {}).get("session_id") or "")}:
            path = S.transcript_now(sid) if S.UUID_RE.fullmatch(sid) and sid != m.session else ""
            if path:
                os.unlink(path)
    obj = run_internal(args, cwd=S.member_cwd(project, m), env=env, timeout=timeout, cleanup=cleanup)
    return ForkAnswer(str(obj.get("result") or ""), "headless fork", _result_usage(obj.get("usage")), False)


# ------------------------------------------------------------------ a model, asked afresh

# What would carry a call, or the prompt, off the owner's first-party login
# (§3b of docs/doperpowers/specs/2026-11-23-sminos-session-search-design.md):
# the gateway's settings, a subagent model override, telemetry that can
# export the prompt; and by prefix (OFF_LOGIN_PREFIXES) every ANTHROPIC_*
# variable (base URL, auth token, API key, model aliases), every provider
# switch (CLAUDE_CODE_USE_*, those to come included) and every OpenTelemetry
# setting (OTEL_*); and every key the gateway settings file names.
OFF_LOGIN = ("CLAUDE_CODE_SUBAGENT_MODEL", "CLODEX_SETTINGS", "CLAUDE_CODE_ENABLE_TELEMETRY")
OFF_LOGIN_PREFIXES = ("ANTHROPIC_", "CLAUDE_CODE_USE_", "OTEL_")
# What stays whatever a gateway settings file names: how the engine is found, and the first-party login itself.
LOGIN_KEPT = ("PATH", "HOME", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN")


def model_env():
    """The environment of a fresh model call: the caller's, less what
    launch_env drops for a plain-route launch (the launch-only markers and
    the gateway settings' keys) and everything that routes off the
    first-party login or exports the prompt (OFF_LOGIN, OFF_LOGIN_PREFIXES),
    marked internal."""
    env = S.launch_env("")
    for k in list(env):
        if k not in LOGIN_KEPT and (k.startswith(OFF_LOGIN_PREFIXES) or k in OFF_LOGIN):
            del env[k]
    for k in LOGIN_KEPT:
        if k in os.environ:
            env[k] = os.environ[k]
    env["SMNS_INTERNAL"] = "1"
    return env


def ask_model(prompt, *, model="haiku", effort="medium", timeout=120):
    """One fresh, tool-less `claude -p` call of `model`, `prompt` on its
    standard input, as an internal process (run_internal) on the caller's
    own first-party login (model_env: no gateway, API key or provider
    inherited from the caller's environment); its working
    directory $SMINOS_HOME, never a protected folder or a project's. Safe
    mode: no plugins, hooks, MCP servers or CLAUDE.md, the machine's own
    login (bare mode would read an API key alone). Its session id is minted
    only so a transcript the engine wrote despite --no-session-persistence
    is found and deleted: that id alone, under the config dir the child ran
    under (its CLAUDE_CONFIG_DIR, else the default), never an id its result
    names, which could be any session's. ForkFailed as headless_fork raises
    it."""
    minted = str(uuidlib.uuid4())
    env = model_env()

    def cleanup(_obj):
        for path in glob.glob(os.path.join(glob.escape(S.config_dir(env)), "projects", "*", minted + ".jsonl")):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
    args = ["claude", "-p", "--safe-mode", "--no-session-persistence", "--session-id", minted, "--model", model,
            "--effort", effort, "--tools", "", "--output-format", "json"]
    os.makedirs(S.root(), exist_ok=True)
    obj = run_internal(args, cwd=S.root(), env=env, timeout=timeout, stdin_text=prompt, cleanup=cleanup,
                       what="model call")
    return ForkAnswer(str(obj.get("result") or ""), "model", _result_usage(obj.get("usage")), False)
