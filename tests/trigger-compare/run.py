#!/usr/bin/env python3
"""Skill trigger comparison: two checkouts of this repo's plugins, same prompts, same models.

  run.py run    --baseline TREE --variant TREE --out DIR [--models opus] [--reps 1]
                [--prompts DIR] [--only 01,02] [--max-turns 5] [--jobs 4] [--claude BIN]
  run.py report --out DIR

TREE is a checkout of this repository (a worktree at the revision to test). DIR
is where results go; keep it outside the repository. Needs python3, git (2.32+)
and an authenticated `claude` CLI.

WHAT IT MEASURES
Whether a change to skill descriptions moves which skills a session invokes.
Each prompt in prompts/ is a user request with the skill it should (or should
not) trigger. A cell = (arm, model, prompt, rep): one headless `claude -p`
session in a fresh copy of fixture/ (a small Python repo, made a git repo with
a feature branch at run time by make_template), the arm's plugins loaded with
--plugin-dir. Per prompt, model and arm the report counts the sessions that
loaded each skill (a Skill call the engine answered with success; refused
calls are kept as `skill_attempts` in cell.json), loaded none, started work
before any skill, answered without tools, or changed the project (uncommitted
changes, untracked files or new commits). Only verified cells enter those
rates; cells that errored, whose isolation could not be checked (no init
event), or whose isolation check failed are counted on rows of their own.

WHAT IT CANNOT
- A session is cut at --max-turns: a skill invoked later is not counted, and
  what the session does with a skill once loaded is not observed.
- It gives no noise estimate. Passing the same tree as both arms measures one
  (the report calls it a noise-floor run) at the price of a full run. Without
  it, at 5 reps a side only large differences show: a 4/5 against 2/5 result
  has come back 6/10 against 6/10 on a rerun.
- Each cell is a paid model session. 240 cells (Fable and Opus) cost $80.71;
  a Fable cell averaged $0.51, an Opus cell $0.19.
- The caller's user-tier setup (~/.claude/CLAUDE.md, user settings, hooks,
  other installed plugins) stays in force, the same in both arms, so results
  are of the caller's environment, not a bare one.
- It is not a sandbox. The session runs with the caller's HOME, credentials
  and network, with permissions bypassed; its filesystem writes and its egress
  are not confined. What ISOLATION lists is all it does.

`run` is resumable and bound to its inputs: config.json records a fingerprint
of each arm's plugin files and of each prompt's text, and the cell budget. A
rerun with the same --out skips cells verified with the same inputs, reruns
the others, may add models, prompts or reps, and refuses (naming what
differs) when an input already run has changed. `report` is also printed at
the end of `run`, and reads only the cells of the configured matrix. Layout:
  config.json                      trees, revs, fingerprints, models, prompts, flags
  cells/<cell key>/{stream.jsonl,stderr.txt,cell.json}
  report.md                        the tables

Prompt files (prompts/*.md): header lines `key: value`, a line `---`, then the
prompt text. Keys: `expect` (a skill name, `none`, or `any` = record only),
`note`. Add a prompt by adding a file.

ISOLATION
- Plugins: every plugin dir of the tree (root + immediate subdirs with
  .claude-plugin/plugin.json) is passed with --plugin-dir, which shadows the
  same-named installed plugin; `--settings` also sets enabledPlugins false for
  `<name>@<marketplace>` of every such plugin in either tree. Each cell's init
  event is checked, and each loaded skill of those plugins must have been read
  from the arm's checkout (cell.json `isolation`).
- Kept from the caller's state: a throwaway project copy per cell; git runs
  for the fixture with no inherited GIT_* variables, no system or global
  config, no templates and no hooks, and the fixture's own config sets
  core.hooksPath to /dev/null so the session's commits run no hooks either;
  --no-session-persistence (no transcript in ~/.claude/projects); telemetry
  off; SMNS_INTERNAL=1 and SMINOS_HOME=<out>/scratch/sminos (sminos hooks skip
  or write to scratch); WEB_CACHE_DIR=<out>/scratch/web-cache (the web
  plugin's session-start prune works on scratch); the parent session's
  Claude/cmux/sminos/git variables scrubbed; the real claude binary rather
  than a cmux shim; --strict-mcp-config (no user MCP servers); outward tools
  denied (DENY); PATH shims for gh, ssh, sminos...
- Not kept: the to-human plugin's session start prunes fold files older than
  30 days under ${CLAUDE_CONFIG_DIR:-~/.claude}/to-human/folds, which only a
  different config dir would move (and that would drop the caller's login);
  hooks of the caller's other plugins run as in any session of theirs.
"""
import argparse, concurrent.futures as cf, hashlib, json, os, random, re, shutil, signal
import subprocess, sys, threading, time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS_FORMAT = 2  # config.json layout; a results dir of another format is not resumed
SHIM_CMDS = ["gh", "ssh", "scp", "rsync", "sminos", "osascript", "claude", "devcloud", "cmux"]
DENY = ["Agent", "Task", "SendMessage", "Workflow", "CronCreate", "CronDelete", "DesignSync",
        "mcp__sminos__AskUserQuestion", "mcp__to-human__message",
        "Bash(git push:*)", "Bash(gh:*)", "Bash(sminos:*)"]
# skill-neutral tools: do not count as "started the task"
NEUTRAL_TOOLS = {"Skill", "ToolSearch", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}
# what the engine loads from a plugin dir; their content is the arm's fingerprint
PLUGIN_INPUTS = (".claude-plugin", "skills", "agents", "hooks", "output-styles", "commands", "bin",
                 ".mcp.json", ".lsp.json", "settings.json")
BASE_DIR = "Base directory for this skill: "
ARMS = ("baseline", "variant")
CLASSES = ("ok", "errored", "unverified", "isolation")


def sha(*parts):
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:16]


def slug(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s)


def cell_key(arm, model, pid, rep):
    """Path-safe and collision-free: the hash is of the raw tuple."""
    return f"{arm}__{slug(model)}__{slug(pid)}__r{rep}__{sha(arm, model, pid, rep)[:8]}"


# ---------------------------------------------------------------- git
def scrubbed_git_env(base=None):
    """The environment without inherited GIT_* overrides (GIT_DIR and the like)."""
    return {k: v for k, v in (base or os.environ).items() if not k.startswith("GIT_")}


FIXTURE_GIT_ENV = {**scrubbed_git_env(), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                   "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def fixture_git(repo: Path, *a, check=True):
    return subprocess.run(["git", "-c", f"core.hooksPath={os.devnull}", "-C", str(repo), *a],
                          check=check, capture_output=True, text=True, env=FIXTURE_GIT_ENV).stdout


# ---------------------------------------------------------------- trees / plugins
def plugin_dirs(tree: Path):
    """[(name, path)] of the plugins a tree holds: the root and immediate subdirs."""
    out = []
    for d in [tree] + sorted(p for p in tree.iterdir() if p.is_dir() and not p.name.startswith(".")):
        pj = d / ".claude-plugin" / "plugin.json"
        if pj.is_file():
            out.append((json.loads(pj.read_text())["name"], d))
    return out


def plugin_fingerprint(plugins):
    """Hash of every file the engine loads from the plugins (PLUGIN_INPUTS), names included."""
    h = hashlib.sha256()
    for name, d in plugins:
        h.update(f"plugin {name}\0".encode())
        for top in PLUGIN_INPUTS:
            p = d / top
            files = [p] if p.is_file() else sorted(p.rglob("*")) if p.is_dir() else []
            for f in files:
                rel = f.relative_to(d)
                if f.is_file() and not {"node_modules", "__pycache__", ".git"} & set(rel.parts):
                    h.update(str(rel).encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()[:16]


def marketplace_name(tree: Path):
    mj = tree / ".claude-plugin" / "marketplace.json"
    return json.loads(mj.read_text()).get("name", "doperpowers") if mj.is_file() else "doperpowers"


def frontmatter_description(skill_md: Path):
    lines = skill_md.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    out, grab = [], False
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        if ln.startswith("description:"):
            grab = True
            out.append(ln.split(":", 1)[1].strip())
        elif grab and (ln.startswith(" ") or ln.startswith("\t")):
            out.append(ln.strip())
        elif grab:
            grab = False
    return " ".join(x for x in out if x not in (">", "|", ">-", "|-")) if out else None


def skill_descriptions(plugins):
    """{ 'plugin:skill': description } for every skill of the given plugins."""
    d = {}
    for name, pdir in plugins:
        for md in sorted((pdir / "skills").glob("*/SKILL.md")):
            d[f"{name}:{md.parent.name}"] = frontmatter_description(md)
    return d


def git_rev(tree: Path):
    env = scrubbed_git_env()
    try:
        rev = subprocess.run(["git", "-C", str(tree), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, env=env).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(tree), "status", "--porcelain"],
                               capture_output=True, text=True, env=env).stdout.strip() != ""
        return rev + ("+dirty" if dirty else "") if rev else "?"
    except Exception:
        return "?"


# ---------------------------------------------------------------- prompts / fixture
def load_prompts(pdir: Path, only):
    prompts = []
    for f in sorted(pdir.glob("*.md")):
        head, _, body = f.read_text().partition("\n---\n")
        meta = {}
        for ln in head.splitlines():
            if ":" in ln:
                k, v = ln.split(":", 1)
                meta[k.strip()] = v.strip()
        pid = f.stem
        if only and not any(pid.startswith(o) or pid == o for o in only):
            continue
        text = body.strip()
        prompts.append({"id": pid, "expect": meta.get("expect", "any"), "note": meta.get("note", ""),
                        "text": text, "sha": sha(text)})
    return prompts


def make_template(out: Path):
    """fixture/ as a git repo on main, plus branch feature/restock-report (not checked out).
    Returns (template dir, the commit ids its refs start at)."""
    tpl = out / "template"
    if tpl.exists():
        shutil.rmtree(tpl)
    shutil.copytree(HERE / "fixture", tpl)
    git = lambda *a: fixture_git(tpl, *a)
    git("init", "-q", "--template=", "-b", "main")
    git("config", "user.name", "t"); git("config", "user.email", "t@t")
    git("config", "core.hooksPath", os.devnull)  # the session's own commits run no hooks
    git("add", "-A"); git("commit", "-qm", "shop scripts: inventory and report")
    git("checkout", "-qb", "feature/restock-report")
    (tpl / "src" / "restock.py").write_text(
        '"""Restock report."""\nfrom .inventory import Inventory\n\n\n'
        'def restock_report(inv: Inventory, target: int = 10) -> str:\n'
        '    lines = []\n'
        '    for item in inv.low_stock(target):\n'
        '        lines.append(f"{item.sku}: order {target - item.qty} x {item.name}")\n'
        '    return "\\n".join(lines) or "nothing to restock"\n')
    (tpl / "tests" / "test_restock.py").write_text(
        'from src.inventory import Inventory, Item\nfrom src.restock import restock_report\n\n\n'
        'def test_restock_report():\n    inv = Inventory()\n    inv.add(Item("A1", "bolt", 2, 10))\n'
        '    assert restock_report(inv, 10) == "A1: order 8 x bolt"\n')
    git("add", "-A"); git("commit", "-qm", "Add restock report")
    git("checkout", "-q", "main")
    start = sorted(set(git("for-each-ref", "--format=%(objectname)").split()))
    return tpl, start


def project_changes(work: Path, start):
    """What the session changed: porcelain status (untracked included) and files of new commits."""
    status = fixture_git(work, "status", "--porcelain", "--untracked-files=all", check=False).splitlines()
    committed = fixture_git(work, "log", "--all", "--format=", "--name-only", "--not", *start,
                            check=False).split()
    return sorted(set(status)) + [f"committed {f}" for f in sorted(set(committed))]


def make_shims(out: Path):
    d = out / "shims"
    d.mkdir(exist_ok=True)
    for c in SHIM_CMDS:
        p = d / c
        p.write_text(f'#!/bin/sh\necho "{c}: disabled in the trigger-test harness" >&2\nexit 1\n')
        p.chmod(0o755)
    return d


def real_claude(explicit=None):
    if explicit:  # absolute: the session runs in the fixture copy
        return str(Path(shutil.which(explicit) or explicit).resolve())
    for d in os.environ.get("PATH", "").split(":"):
        if "cmux" in d.lower() or not d:
            continue
        c = Path(d) / "claude"
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    sys.exit("no claude binary found outside cmux shims; pass --claude")


# ---------------------------------------------------------------- one cell
def scrubbed_env(out: Path, shims: Path):
    env = {}
    for k, v in scrubbed_git_env().items():
        if k in ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_PROJECT_DIR", "KAIROS"):
            continue
        if k.startswith(("CMUX_", "SMNS_", "SMINOS_", "MAWS_", "KAIROS_", "WEB_CACHE_")):
            continue
        if k in ("CLAUDE_CODE_CHILD_NOTES_DIR", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_ENTRYPOINT",
                 "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
                 "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_SESSION_ID"):
            continue
        env[k] = v
    env["PATH"] = ":".join([str(shims)] + [p for p in env.get("PATH", "").split(":") if "cmux" not in p.lower()])
    scratch = out / "scratch"
    env.update({"SMNS_INTERNAL": "1", "SMINOS_HOME": str(scratch / "sminos"),
                "WEB_CACHE_DIR": str(scratch / "web-cache"),
                # a notification hook keyed on a cmux surface stays quiet
                "CMUX_SURFACE_ID": "trigger-test", "CLAUDE_CODE_ENABLE_TELEMETRY": "0"})
    return env


def build_cmd(a, model, prompt_text, tree_plugins, disabled):
    settings = {"enabledPlugins": {n: False for n in disabled},
                "env": {"CLAUDE_CODE_ENABLE_TELEMETRY": "0"}}
    cmd = [a.claude_bin, "-p", prompt_text, "--model", model, "--max-turns", str(a.max_turns),
           "--output-format", "stream-json", "--verbose", "--no-session-persistence",
           "--permission-mode", "bypassPermissions", "--strict-mcp-config",
           "--max-budget-usd", str(a.max_budget), "--disallowedTools", ",".join(DENY),
           "--settings", json.dumps(settings)]
    for _, d in tree_plugins:
        cmd += ["--plugin-dir", str(d)]
    return cmd


def events(stream_path: Path):
    for ln in stream_path.read_text().splitlines():
        try:
            yield json.loads(ln)
        except Exception:
            continue


def analyze(stream_path: Path, tree_plugins, tree_skills, disabled):
    """Summarize one stream-json file."""
    init, result, seq, texts = None, None, [], []
    pending, loaded_ids, attempts, loads, awaiting, dirs = {}, set(), [], [], [], []
    for d in events(stream_path):
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            init = d
        elif t == "result":
            result = d
        elif t == "assistant":
            for b in d.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    inp = b.get("input", {})
                    skill = inp.get("skill") if b["name"] == "Skill" else None
                    seq.append({"id": b.get("id"), "tool": b["name"], "skill": skill,
                                "arg": (inp.get("command") or inp.get("file_path") or inp.get("pattern") or "")[:120]})
                    if b["name"] == "Skill":
                        attempts.append(skill)
                        pending[b.get("id")] = skill
                elif b.get("type") == "text":
                    texts.append(b["text"])
        elif t == "user":
            content = d.get("message", {}).get("content")
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
            results = [b for b in blocks if b.get("type") == "tool_result"]
            for b in results:
                if b.get("tool_use_id") not in pending:
                    continue
                skill = pending.pop(b["tool_use_id"])
                meta = d.get("tool_use_result") if len(results) == 1 else None
                if not b.get("is_error") and not (isinstance(meta, dict) and meta.get("success") is False):
                    loads.append(skill)
                    loaded_ids.add(b["tool_use_id"])
                    awaiting.append(skill)
            for b in blocks:
                if b.get("type") == "text" and b.get("text", "").startswith(BASE_DIR):
                    # the engine sends the skill body right after the Skill result
                    dirs.append((awaiting.pop(0) if awaiting else None,
                                 b["text"][len(BASE_DIR):].split("\n", 1)[0]))
    first_skill_i = next((i for i, s in enumerate(seq) if s["id"] in loaded_ids), None)
    work_i = next((i for i, s in enumerate(seq) if s["tool"] not in NEUTRAL_TOOLS), None)
    iso = {"ok": None, "problems": []}
    if init:
        probs = []
        by_src = {p["source"]: p["path"] for p in init.get("plugins", [])}
        for name, d in tree_plugins:
            if by_src.get(f"{name}@inline") != str(d):
                probs.append(f"{name}: loaded from {by_src.get(name + '@inline')} not {d}")
        for p in init.get("plugins", []):
            if p["source"] in disabled or (p["name"] in {n for n, _ in tree_plugins} and not p["source"].endswith("@inline")):
                probs.append(f"installed copy loaded: {p['source']} {p['path']}")
        sk = init.get("skills", [])
        dup = sorted({s for s in sk if sk.count(s) > 1})
        if dup:
            probs.append(f"duplicate skills: {dup}")
        ns = {n for n, _ in tree_plugins}
        have = {s for s in sk if s.split(":")[0] in ns and ":" in s}
        want = set(tree_skills)
        for name, d in tree_plugins:  # a manifest's `workflows` register as skills too
            pj = Path(d) / ".claude-plugin" / "plugin.json"
            want |= {f"{name}:{Path(w).stem}" for w in (json.loads(pj.read_text()) if pj.is_file() else {}).get("workflows", [])}
        if have != want:
            probs.append(f"skill set differs: missing {sorted(want - have)} extra {sorted(have - want)}")
        # where each loaded skill of the compared plugins was read from
        roots = {n: Path(d) for n, d in tree_plugins}
        seen = defaultdict(int)
        for skill, sd in dirs:
            plug, _, sname = (skill or "").partition(":")
            if plug in roots:
                seen[skill] += 1
                exact = roots[plug] / "skills" / sname
                ok = Path(sd) == exact if (exact / "SKILL.md").is_file() else Path(sd).is_relative_to(roots[plug])
                if not ok:
                    probs.append(f"{skill} read from {sd}, not from {roots[plug]}")
        for skill in loads:
            if (skill or "").partition(":")[0] in roots and seen[skill] == 0:
                probs.append(f"{skill}: loaded, but no skill directory seen")
        iso = {"ok": not probs, "problems": probs, "skill_dirs": [sd for _, sd in dirs]}
    u = (result or {}).get("usage", {}) or {}
    return {
        "skills": loads,
        "skill_attempts": attempts,
        "first_skill_turn": first_skill_i,
        "tool_seq": [s["tool"] + (":" + s["skill"] if s["skill"] else "") for s in seq],
        "first_work_tool": seq[work_i]["tool"] if work_i is not None else None,
        "direct_before_skill": work_i is not None and (first_skill_i is None or work_i < first_skill_i),
        "direct_start": work_i is not None,
        "no_tools": len(seq) == 0,
        "text_head": (texts[-1] if texts else "")[:300],
        "isolation": iso,
        "result_subtype": (result or {}).get("subtype"),
        "is_error": (result or {}).get("is_error"),
        "num_turns": (result or {}).get("num_turns"),
        "cost_usd": (result or {}).get("total_cost_usd"),
        "tokens": {"input": u.get("input_tokens"), "cache_creation": u.get("cache_creation_input_tokens"),
                   "cache_read": u.get("cache_read_input_tokens"), "output": u.get("output_tokens")},
        "model_seen": (init or {}).get("model"),
        "engine_version": (init or {}).get("claude_code_version"),
        "session_id": (init or {}).get("session_id"),
    }


def cell_class(c):
    """ok (enters the rates), errored, unverified (no init event) or isolation (check failed)."""
    if c.get("status") == "errored" or c.get("status") == "error" or c.get("timed_out"):
        return "errored"
    ok = c.get("isolation", {}).get("ok")
    return "unverified" if ok is None else "isolation" if ok is False else "ok"


def cell_inputs(cfg, arm, model, prompt_sha):
    return sha(cfg[arm]["fingerprint"], prompt_sha, model, cfg["max_turns"], cfg["max_budget"], cfg["timeout"])


class Runner:
    def __init__(self, a, out, cfg, trees, prompts, tpl, start, shims):
        self.a, self.out, self.cfg, self.trees, self.prompts = a, out, cfg, trees, prompts
        self.tpl, self.start, self.shims = tpl, start, shims
        self.env = scrubbed_env(out, shims)
        self.lock = threading.Lock()  # guards procs, launch and stopping together
        self.stopping = False
        self.done = 0
        self.procs = set()

    def run_cell(self, arm, model, p, rep, total):
        cd = self.out / "cells" / cell_key(arm, model, p["id"], rep)
        work = self.out / "work" / cd.name
        if self.stopping:
            return "cancelled"
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(self.tpl, work)
        tp = self.trees[arm]["plugins"]
        cmd = build_cmd(self.a, model, p["text"], tp, self.trees["_disabled"])
        cd.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        timed_out = False
        with open(cd / "stream.jsonl", "w") as so, open(cd / "stderr.txt", "w") as se:
            with self.lock:  # no launch after an interrupt, and every child is registered before it can be missed
                if self.stopping:
                    shutil.rmtree(work, ignore_errors=True)
                    return "cancelled"
                proc = subprocess.Popen(cmd, cwd=work, env=self.env, stdin=subprocess.DEVNULL,
                                        stdout=so, stderr=se, start_new_session=True)
                self.procs.add(proc)
            try:
                proc.wait(timeout=self.a.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            finally:
                with self.lock:
                    self.procs.discard(proc)
        dur = time.time() - t0
        changes = project_changes(work, self.start)
        shutil.rmtree(work, ignore_errors=True)
        info = analyze(cd / "stream.jsonl", tp, self.trees[arm]["skills"], self.trees["_disabled"])
        ran = (info["result_subtype"] in ("success", "error_max_turns") and not
               (info["is_error"] and info["result_subtype"] == "success") and not timed_out and not self.stopping)
        if info["session_id"]:  # the engine leaves an empty ~/.claude/session-env/<id>; remove it
            try:
                (Path.home() / ".claude" / "session-env" / info["session_id"]).rmdir()
            except OSError:
                pass
        cell = {"arm": arm, "model": model, "prompt": p["id"], "rep": rep, "expect": p["expect"],
                "inputs": cell_inputs(self.cfg, arm, model, p["sha"]),
                "duration_s": round(dur, 1), "timed_out": timed_out,
                "files_changed": changes, "cmd_exit": proc.returncode, **info}
        cell["status"] = cell_class({**cell, "status": "ok" if ran else "errored"})
        (cd / "cell.json").write_text(json.dumps(cell, indent=1))
        with self.lock:
            self.done += 1
            print(f"[{self.done}/{total}] {cd.name}  {cell['status']}  skills={info['skills']} "
                  f"first={info['tool_seq'][:2]} ${info['cost_usd'] or 0:.2f} {dur:.0f}s"
                  + (f"  {info['isolation']['problems']}" if cell["status"] == "isolation" else ""), flush=True)
        return cell["status"]

    def run_all(self, cells):
        total = len(cells)
        ex = cf.ThreadPoolExecutor(max_workers=self.a.jobs)
        futs = [ex.submit(self.run_cell, *c, total) for c in cells]
        try:
            for f in cf.as_completed(futs):
                f.result()
        except BaseException as e:  # an interrupt, or a cell that raised: stop every session
            print(f"stopping ({type(e).__name__}); killing sessions (unfinished cells rerun on resume)", flush=True)
            with self.lock:
                self.stopping = True
                for pr in list(self.procs):
                    try:
                        os.killpg(pr.pid, signal.SIGKILL)
                    except Exception:
                        pass
            ex.shutdown(wait=True, cancel_futures=True)  # each worker reaps its killed child
            raise
        ex.shutdown(wait=True)


# ---------------------------------------------------------------- report
def report(out: Path):
    cfg = json.loads((out / "config.json").read_text())
    models = cfg["models"]
    prompts = {p["id"]: p for p in cfg["prompts"]}
    reps = range(1, cfg["reps"] + 1)
    cells = []
    for cj in sorted((out / "cells").glob("*/cell.json")):
        c = json.loads(cj.read_text())
        if (c.get("arm") in ARMS and c.get("model") in models and c.get("prompt") in prompts
                and c.get("rep") in reps
                and ("fingerprint" not in cfg["baseline"]  # an older harness's results: no inputs recorded
                     or c.get("inputs") == cell_inputs(cfg, c["arm"], c["model"], prompts[c["prompt"]]["sha"]))):
            c["class"] = cell_class(c)
            cells.append(c)
    lines = [f"# Skill trigger comparison  ({out.name})", "",
             f"baseline: {cfg['baseline']['path']} @ {cfg['baseline']['rev']}",
             f"variant:  {cfg['variant']['path']} @ {cfg['variant']['rev']}",
             f"models: {', '.join(models)}   reps: {cfg['reps']}   max-turns: {cfg['max_turns']}", ""]
    changed = cfg.get("changed_descriptions", [])
    same_inputs = "fingerprint" in cfg["baseline"] and cfg["baseline"]["fingerprint"] == cfg["variant"]["fingerprint"]
    lines.append(f"skills whose description differs between the trees: {len(changed)}"
                 + (f" ({', '.join(changed)})" if changed else
                    "  (plugin files identical: this is a noise-floor run)" if same_inputs else
                    "  (no description differences)"))
    n = {k: sum(1 for c in cells if c["class"] == k) for k in CLASSES}
    lines.append(f"cells: {len(cells)} finished: {n['ok']} verified, {n['errored']} errored, "
                 f"{n['unverified']} unverified, {n['isolation']} failed the isolation check "
                 "(only verified cells enter the rates)")
    versions = sorted({c.get("engine_version") for c in cells if c.get("engine_version")})
    if len(versions) > 1:
        lines.append(f"engine versions differ across cells: {', '.join(versions)}")
    tot = sum((c.get("cost_usd") or 0) for c in cells)
    lines += [f"total cost reported: ${tot:.2f}", ""]
    by_prompt = defaultdict(list)
    for c in cells:
        by_prompt[c["prompt"]].append(c)
    colw = 11
    for pid in sorted(by_prompt):
        pr = prompts[pid]
        expect = pr["expect"]
        lines += [f"## {pid}   expect: {expect}", f"   {pr['note']}", ""]
        cs = by_prompt[pid]
        skills = sorted({s for c in cs if c["class"] == "ok" for s in c["skills"]})
        if expect not in ("none", "any") and expect not in skills:
            skills.insert(0, expect)
        hdr1 = f"{'':36}" + "".join(f"{m:^{colw*2}}" for m in models)
        hdr2 = f"{'':36}" + "".join(f"{'base':>{colw}}{'variant':>{colw}}" for _ in models)
        def row(label, pred, among=lambda c: c["class"] == "ok"):
            r = f"{label:36}"
            for m in models:
                for arm in ARMS:
                    sel = [c for c in cs if c["model"] == m and c["arm"] == arm and among(c)]
                    k = sum(1 for c in sel if pred(c))
                    r += f"{(str(k) + '/' + str(len(sel))) if sel else '-':>{colw}}"
            return r
        rows = []
        for s in skills:
            mark = "*" if s == expect else ""
            rows.append(row((s + mark)[:35], lambda c, s=s: s in c["skills"]))
        rows.append(row("(any skill)", lambda c: bool(c["skills"])))
        rows.append(row("(no skill)", lambda c: not c["skills"]))
        rows.append(row("started work before any skill", lambda c: c["direct_before_skill"]))
        rows.append(row("answered without tools", lambda c: c["no_tools"]))
        rows.append(row("files changed in project", lambda c: bool(c["files_changed"])))
        for k, label in (("errored", "excluded: errored"), ("unverified", "excluded: unverified"),
                         ("isolation", "excluded: isolation failed")):
            rows.append(row(label, lambda c, k=k: c["class"] == k, among=lambda c: True))
        lines += [hdr1, hdr2] + rows + [""]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    return "\n".join(lines)


# ---------------------------------------------------------------- main
def merge_config(old, new):
    """The config a rerun continues under, or exit naming what changed."""
    if old.get("format") != HARNESS_FORMAT:
        sys.exit("this --out was made by another version of the harness; use a new --out")
    diffs = [k for k in ("max_turns", "max_budget", "timeout") if old[k] != new[k]]
    for arm in ARMS:
        for k in ("path", "fingerprint", "plugins"):
            if old[arm][k] != new[arm][k]:
                diffs.append(f"{arm} {k}")
    old_p = {p["id"]: p for p in old["prompts"]}
    diffs += [f"prompt {p['id']} text" for p in new["prompts"] if p["id"] in old_p and old_p[p["id"]]["sha"] != p["sha"]]
    if diffs:
        sys.exit(f"inputs differ from the run already in this --out: {', '.join(diffs)}; use a new --out")
    merged = dict(old)
    merged["models"] = old["models"] + [m for m in new["models"] if m not in old["models"]]
    merged["reps"] = max(old["reps"], new["reps"])
    new_p = {p["id"]: p for p in new["prompts"]}
    merged["prompts"] = sorted([new_p.get(i, p) for i, p in old_p.items()] +
                               [p for i, p in new_p.items() if i not in old_p], key=lambda p: p["id"])
    added = [x for x in ("models", "reps", "prompts") if merged[x] != old[x]]
    if added:
        print(f"extending the run in this --out: {', '.join(added)}", flush=True)
    return merged


def cmd_run(a):
    out = Path(a.out).resolve()
    a.claude_bin = real_claude(a.claude)
    trees, descs = {}, {}
    for arm, path in (("baseline", a.baseline), ("variant", a.variant)):
        t = Path(path).resolve()
        plugins = plugin_dirs(t) if t.is_dir() else []
        if not plugins:
            sys.exit(f"{arm} {t} holds no plugin")
        descs[arm] = skill_descriptions(plugins)
        trees[arm] = {"path": str(t), "plugins": plugins, "rev": git_rev(t),
                      "fingerprint": plugin_fingerprint(plugins), "skills": list(descs[arm])}
    mk = marketplace_name(Path(a.baseline).resolve())
    names = {n for arm in ARMS for n, _ in trees[arm]["plugins"]}
    trees["_disabled"] = {f"{n}@{mk}" for n in names}
    prompts = load_prompts(Path(a.prompts), [x for x in (a.only or "").split(",") if x])
    models = [m for m in a.models.split(",") if m]
    changed = sorted(k for k in set(descs["baseline"]) | set(descs["variant"])
                     if descs["baseline"].get(k) != descs["variant"].get(k))
    cfg = {"format": HARNESS_FORMAT,
           **{arm: {"path": trees[arm]["path"], "rev": trees[arm]["rev"], "fingerprint": trees[arm]["fingerprint"],
                    "plugins": [[n, str(d)] for n, d in trees[arm]["plugins"]]} for arm in ARMS},
           "models": models, "reps": a.reps, "max_turns": a.max_turns, "max_budget": a.max_budget,
           "timeout": a.timeout,
           "prompts": [{k: p[k] for k in ("id", "expect", "note", "sha")} for p in prompts],
           "changed_descriptions": changed}
    out.mkdir(parents=True, exist_ok=True)
    cfgp = out / "config.json"
    if cfgp.exists():
        cfg = merge_config(json.loads(cfgp.read_text()), cfg)
    cfgp.write_text(json.dumps(cfg, indent=1))
    (out / "scratch" / "sminos").mkdir(parents=True, exist_ok=True)
    tpl, start = make_template(out)
    shims = make_shims(out)
    cells = [(arm, m, p, r) for arm in ARMS for m in models for p in prompts for r in range(1, a.reps + 1)]
    random.Random(a.seed).shuffle(cells)  # interleave arms so drift in load/time does not line up with one arm

    def done(c):
        cj = out / "cells" / cell_key(c[0], c[1], c[2]["id"], c[3]) / "cell.json"
        if not cj.exists():
            return False
        old = json.loads(cj.read_text())
        return old.get("status") == "ok" and old.get("inputs") == cell_inputs(cfg, c[0], c[1], c[2]["sha"])
    todo = [c for c in cells if not done(c)]
    print(f"{len(cells)} cells, {len(cells) - len(todo)} already done, running {len(todo)} with {a.jobs} jobs -> {out}", flush=True)
    if todo:
        Runner(a, out, cfg, trees, prompts, tpl, start, shims).run_all(todo)
    print()
    print(report(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the cells of a comparison (paid sessions), then report")
    r.add_argument("--baseline", required=True); r.add_argument("--variant", required=True)
    r.add_argument("--models", default="opus"); r.add_argument("--reps", type=int, default=1)
    r.add_argument("--prompts", default=str(HERE / "prompts")); r.add_argument("--only")
    r.add_argument("--max-turns", type=int, default=5); r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--timeout", type=int, default=600); r.add_argument("--max-budget", type=float, default=2.0)
    r.add_argument("--seed", type=int, default=1); r.add_argument("--out", required=True); r.add_argument("--claude")
    p = sub.add_parser("report", help="rebuild report.md from a results directory")
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "run":
        cmd_run(a)
    else:
        print(report(Path(a.out).resolve()))


if __name__ == "__main__":
    main()
