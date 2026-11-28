#!/usr/bin/env python3
"""Skill trigger comparison: two checkouts of this repo's plugins, same prompts, same models.

  run.py run    --baseline TREE --variant TREE --out DIR [--models opus] [--reps 1]
                [--prompts DIR] [--only 01,02] [--max-turns 5] [--jobs 4] [--claude BIN]
  run.py report --out DIR

TREE is a checkout of this repository (a worktree at the revision to test). DIR
is where results go; keep it outside the repository. Needs python3, git and an
authenticated `claude` CLI.

WHAT IT MEASURES
Whether a change to skill descriptions moves which skills a session invokes.
Each prompt in prompts/ is a user request with the skill it should (or should
not) trigger. A cell = (arm, model, prompt, rep): one headless `claude -p`
session in a fresh copy of fixture/ (a small Python repo, made a git repo with
a feature branch at run time by make_template), the arm's plugins loaded with
--plugin-dir. Per prompt, model and arm the report counts the sessions that
invoked each skill (through the Skill tool), invoked none, started work before
any skill, answered without tools, changed files, or errored.

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

`run` is resumable: the same command with the same --out skips finished cells
(cell.json status ok) and retries errored or interrupted ones. `report` is
also printed at the end of `run`. Layout of --out:
  config.json                      trees, git revs, models, flags
  cells/<arm>__<model>__<prompt>__r<k>/{stream.jsonl,stderr.txt,cell.json}
  report.md                        the tables

Prompt files (prompts/*.md): header lines `key: value`, a line `---`, then the
prompt text. Keys: `expect` (a skill name, `none`, or `any` = record only),
`note`. Add a prompt by adding a file.

ISOLATION
- Plugins: every plugin dir of the tree (root + immediate subdirs with
  .claude-plugin/plugin.json) is passed with --plugin-dir, which shadows the
  same-named installed plugin; `--settings` also sets enabledPlugins false for
  `<name>@<marketplace>` of every such plugin in either tree, so nothing of the
  cache can leak in. Each cell's init event is checked (cell.json `isolation`).
- Nothing reaches the outside: throwaway project copy per cell,
  --no-session-persistence (no transcript in ~/.claude/projects), telemetry off,
  SMNS_INTERNAL=1 and SMINOS_HOME=<out>/sminos-scratch (sminos hooks skip or
  write to scratch), the parent session's Claude/cmux/sminos variables scrubbed,
  the real claude binary rather than a cmux shim, --strict-mcp-config (no user
  MCP servers), outward tools denied (DENY), and PATH shims for gh, ssh, sminos...
"""
import argparse, concurrent.futures as cf, json, os, random, re, shutil, signal
import subprocess, sys, threading, time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHIM_CMDS = ["gh", "ssh", "scp", "rsync", "sminos", "osascript", "claude", "devcloud", "cmux"]
DENY = ["Agent", "Task", "SendMessage", "Workflow", "CronCreate", "CronDelete", "DesignSync",
        "mcp__sminos__AskUserQuestion", "mcp__to-human__message",
        "Bash(git push:*)", "Bash(gh:*)", "Bash(sminos:*)"]
WORK_TOOLS = {"Bash", "Read", "Edit", "Write", "Grep", "Glob", "NotebookEdit", "WebSearch"}
# skill-neutral tools: do not count as "started the task"
NEUTRAL_TOOLS = {"Skill", "ToolSearch", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}


# ---------------------------------------------------------------- trees / plugins
def plugin_dirs(tree: Path):
    """[(name, path)] of the plugins a tree holds: the root and immediate subdirs."""
    out = []
    for d in [tree] + sorted(p for p in tree.iterdir() if p.is_dir() and not p.name.startswith(".")):
        pj = d / ".claude-plugin" / "plugin.json"
        if pj.is_file():
            out.append((json.loads(pj.read_text())["name"], d))
    return out


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


def skill_descriptions(tree: Path):
    """{ 'plugin:skill': description } for every skill of every plugin of the tree."""
    d = {}
    for name, pdir in plugin_dirs(tree):
        for md in sorted((pdir / "skills").glob("*/SKILL.md")):
            d[f"{name}:{md.parent.name}"] = frontmatter_description(md)
    return d


def git_rev(tree: Path):
    try:
        rev = subprocess.run(["git", "-C", str(tree), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(tree), "status", "--porcelain"],
                               capture_output=True, text=True).stdout.strip() != ""
        return rev + ("+dirty" if dirty else "")
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
        prompts.append({"id": pid, "expect": meta.get("expect", "any"), "note": meta.get("note", ""),
                        "text": body.strip()})
    return prompts


def make_template(out: Path):
    """fixture/ as a git repo on main, plus branch feature/restock-report (not checked out)."""
    tpl = out / "template"
    if tpl.exists():
        shutil.rmtree(tpl)
    shutil.copytree(HERE / "fixture", tpl)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    def git(*a):
        subprocess.run(["git", "-C", str(tpl), *a], check=True, capture_output=True, env=env)
    git("init", "-q", "-b", "main"); git("config", "user.name", "t"); git("config", "user.email", "t@t")
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
    return tpl


def make_shims(out: Path):
    d = out / "shims"
    d.mkdir(exist_ok=True)
    for c in SHIM_CMDS:
        p = d / c
        p.write_text(f'#!/bin/sh\necho "{c}: disabled in the trigger-test harness" >&2\nexit 1\n')
        p.chmod(0o755)
    return d


def real_claude(explicit=None):
    if explicit:
        return explicit
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
    for k, v in os.environ.items():
        if k in ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_PROJECT_DIR", "KAIROS"):
            continue
        if k.startswith(("CMUX_", "SMNS_", "SMINOS_", "MAWS_")):
            continue
        if k in ("CLAUDE_CODE_CHILD_NOTES_DIR", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_ENTRYPOINT",
                 "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
                 "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_SESSION_ID"):
            continue
        env[k] = v
    env["PATH"] = ":".join([str(shims)] + [p for p in env.get("PATH", "").split(":") if "cmux" not in p.lower()])
    env.update({"SMNS_INTERNAL": "1", "SMINOS_HOME": str(out / "sminos-scratch"),
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


def analyze(stream_path: Path, tree_plugins, tree_skills, disabled):
    """Summarize one stream-json file."""
    init, result, seq, texts = None, None, [], []
    for ln in stream_path.read_text().splitlines():
        try:
            d = json.loads(ln)
        except Exception:
            continue
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            init = d
        elif t == "result":
            result = d
        elif t == "assistant":
            for b in d.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    inp = b.get("input", {})
                    seq.append({"tool": b["name"],
                                "skill": inp.get("skill") if b["name"] == "Skill" else None,
                                "arg": (inp.get("command") or inp.get("file_path") or inp.get("pattern") or "")[:120]})
                elif b.get("type") == "text":
                    texts.append(b["text"])
    skills = [s["skill"] for s in seq if s["tool"] == "Skill"]
    first_skill_i = next((i for i, s in enumerate(seq) if s["tool"] == "Skill"), None)
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
            pj = json.loads((d / ".claude-plugin" / "plugin.json").read_text())
            want |= {f"{name}:{Path(w).stem}" for w in pj.get("workflows", [])}
        if have != want:
            probs.append(f"skill set differs: missing {sorted(want - have)} extra {sorted(have - want)}")
        iso = {"ok": not probs, "problems": probs}
        # strongest check: where each invoked skill was actually read from
        dirs = sorted(set(re.findall(r"Base directory for this skill: (\S+)", stream_path.read_text().replace("\\n", "\n"))))
        iso["skill_dirs"] = dirs
        roots = [str(d) for _, d in tree_plugins]
        for sd in dirs:
            if not any(sd.startswith(r + "/") for r in roots):
                iso["problems"].append(f"skill read from outside the tree: {sd}")
        iso["ok"] = not iso["problems"]
    u = (result or {}).get("usage", {}) or {}
    return {
        "skills": skills,
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
        "session_id": (init or {}).get("session_id"),
    }


class Runner:
    def __init__(self, a, out, trees, prompts, tpl, shims):
        self.a, self.out, self.trees, self.prompts, self.tpl, self.shims = a, out, trees, prompts, tpl, shims
        self.disabled = trees["_disabled"]
        self.env = scrubbed_env(out, shims)
        self.lock = threading.Lock()
        self.done = 0
        self.procs = set()

    def cell_dir(self, arm, model, pid, rep):
        return self.out / "cells" / f"{arm}__{model}__{pid}__r{rep}"

    def run_cell(self, arm, model, p, rep, total):
        cd = self.cell_dir(arm, model, p["id"], rep)
        cj = cd / "cell.json"
        if cj.exists() and json.loads(cj.read_text()).get("status") == "ok":
            return "skip"
        cd.mkdir(parents=True, exist_ok=True)
        work = self.out / "work" / cd.name
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(self.tpl, work)
        tp = self.trees[arm]["plugins"]
        cmd = build_cmd(self.a, model, p["text"], tp, self.disabled)
        t0 = time.time()
        timed_out = False
        with open(cd / "stream.jsonl", "w") as so, open(cd / "stderr.txt", "w") as se:
            proc = subprocess.Popen(cmd, cwd=work, env=self.env, stdin=subprocess.DEVNULL,
                                    stdout=so, stderr=se, start_new_session=True)
            with self.lock:
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
        git_status = subprocess.run(["git", "-C", str(work), "status", "--porcelain"],
                                    capture_output=True, text=True).stdout.strip().splitlines()
        shutil.rmtree(work, ignore_errors=True)
        tree_skills = [k for k in self.trees[arm]["skills"]]
        info = analyze(cd / "stream.jsonl", tp, tree_skills, self.disabled)
        ok = (info["result_subtype"] in ("success", "error_max_turns") and not
              (info["is_error"] and info["result_subtype"] == "success") and not timed_out)
        if info["session_id"]:  # the engine leaves an empty ~/.claude/session-env/<id>; remove it
            try:
                (Path.home() / ".claude" / "session-env" / info["session_id"]).rmdir()
            except OSError:
                pass
        cell = {"status": "ok" if ok else "error", "arm": arm, "model": model, "prompt": p["id"],
                "rep": rep, "expect": p["expect"], "duration_s": round(dur, 1), "timed_out": timed_out,
                "files_changed": git_status, "cmd_exit": proc.returncode, **info}
        cj.write_text(json.dumps(cell, indent=1))
        with self.lock:
            self.done += 1
            print(f"[{self.done}/{total}] {cd.name}  {cell['status']}  skills={info['skills']} "
                  f"first={info['tool_seq'][:2]} ${info['cost_usd'] or 0:.2f} {dur:.0f}s"
                  + ("  ISOLATION PROBLEM" if info['isolation']['ok'] is False else ""), flush=True)
        return cell["status"]

    def run_all(self, cells):
        total = len(cells)
        ex = cf.ThreadPoolExecutor(max_workers=self.a.jobs)
        futs = [ex.submit(self.run_cell, *c, total) for c in cells]
        try:
            for f in cf.as_completed(futs):
                f.result()
        except KeyboardInterrupt:
            print("interrupted; killing sessions (unfinished cells rerun on resume)", flush=True)
            for f in futs:
                f.cancel()
            with self.lock:
                for pr in list(self.procs):
                    try:
                        os.killpg(pr.pid, signal.SIGKILL)
                    except Exception:
                        pass
            raise
        finally:
            ex.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------- report
def report(out: Path):
    cfg = json.loads((out / "config.json").read_text())
    cells = []
    for cj in sorted((out / "cells").glob("*/cell.json")):
        c = json.loads(cj.read_text())
        cells.append(c)
    models = cfg["models"]
    arms = ["baseline", "variant"]
    lines = [f"# Skill trigger comparison  ({out.name})", "",
             f"baseline: {cfg['baseline']['path']} @ {cfg['baseline']['rev']}",
             f"variant:  {cfg['variant']['path']} @ {cfg['variant']['rev']}",
             f"models: {', '.join(models)}   reps: {cfg['reps']}   max-turns: {cfg['max_turns']}", ""]
    changed = cfg.get("changed_descriptions", [])
    lines.append(f"skills whose description differs between the trees: {len(changed)}"
                 + (f" ({', '.join(changed)})" if changed else "  (trees identical: this is a noise-floor run)"))
    bad = [c for c in cells if c["isolation"]["ok"] is False]
    errs = [c for c in cells if c["status"] != "ok"]
    lines.append(f"cells: {len(cells)} finished, {len(errs)} errored, {len(bad)} with plugin-isolation problems")
    tot = sum((c.get("cost_usd") or 0) for c in cells)
    lines += [f"total cost reported: ${tot:.2f}", ""]
    by_prompt = defaultdict(list)
    for c in cells:
        by_prompt[c["prompt"]].append(c)
    prompts = {p["id"]: p for p in cfg["prompts"]}
    colw = 11
    for pid in sorted(by_prompt):
        pr = prompts.get(pid, {"expect": "?", "note": ""})
        expect = pr["expect"]
        lines += [f"## {pid}   expect: {expect}", f"   {pr['note']}", ""]
        cs = by_prompt[pid]
        skills = sorted({s for c in cs for s in c["skills"]})
        if expect not in ("none", "any") and expect not in skills:
            skills.insert(0, expect)
        hdr1 = f"{'':36}" + "".join(f"{m:^{colw*2}}" for m in models)
        hdr2 = f"{'':36}" + "".join(f"{'base':>{colw}}{'variant':>{colw}}" for _ in models)
        rows = []
        def n_of(m, arm):
            return sum(1 for c in cs if c["model"] == m and c["arm"] == arm)
        def row(label, pred):
            r = f"{label:36}"
            for m in models:
                for arm in arms:
                    sel = [c for c in cs if c["model"] == m and c["arm"] == arm]
                    k = sum(1 for c in sel if pred(c))
                    r += f"{(str(k) + '/' + str(len(sel))) if sel else '-':>{colw}}"
            return r
        for s in skills:
            mark = "*" if s == expect else ""
            rows.append(row((s + mark)[:35], lambda c, s=s: s in c["skills"]))
        rows.append(row("(any skill)", lambda c: bool(c["skills"])))
        rows.append(row("(no skill)", lambda c: not c["skills"]))
        rows.append(row("started work before any skill", lambda c: c["direct_before_skill"]))
        rows.append(row("answered without tools", lambda c: c["no_tools"]))
        rows.append(row("files changed in project", lambda c: bool(c["files_changed"])))
        rows.append(row("errored cell", lambda c: c["status"] != "ok"))
        lines += [hdr1, hdr2] + rows + [""]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    return "\n".join(lines)


# ---------------------------------------------------------------- main
def cmd_run(a):
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    a.claude_bin = real_claude(a.claude)
    trees, descs = {}, {}
    for arm, path in (("baseline", a.baseline), ("variant", a.variant)):
        t = Path(path).resolve()
        trees[arm] = {"path": str(t), "plugins": plugin_dirs(t), "rev": git_rev(t)}
        descs[arm] = skill_descriptions(t)
        trees[arm]["skills"] = list(descs[arm])
    if trees["baseline"]["plugins"] == []:
        sys.exit("baseline holds no plugin")
    mk = marketplace_name(Path(a.baseline))
    names = {n for arm in trees for n, _ in trees[arm]["plugins"]}
    trees["_disabled"] = {f"{n}@{mk}" for n in names}
    prompts = load_prompts(Path(a.prompts), [x for x in (a.only or "").split(",") if x])
    models = [m for m in a.models.split(",") if m]
    changed = sorted(k for k in set(descs["baseline"]) | set(descs["variant"])
                     if descs["baseline"].get(k) != descs["variant"].get(k))
    cfg = {"baseline": {"path": trees["baseline"]["path"], "rev": trees["baseline"]["rev"]},
           "variant": {"path": trees["variant"]["path"], "rev": trees["variant"]["rev"]},
           "models": models, "reps": a.reps, "max_turns": a.max_turns,
           "prompts": [{k: p[k] for k in ("id", "expect", "note")} for p in prompts],
           "changed_descriptions": changed}
    cfgp = out / "config.json"
    if cfgp.exists():
        old = json.loads(cfgp.read_text())
        if (old["baseline"], old["variant"], old["max_turns"]) != (cfg["baseline"], cfg["variant"], cfg["max_turns"]):
            sys.exit(f"{out} was started with different trees or max-turns; use a new --out")
    cfgp.write_text(json.dumps(cfg, indent=1))
    (out / "sminos-scratch").mkdir(exist_ok=True)
    tpl = make_template(out)
    shims = make_shims(out)
    cells = [(arm, m, p, r) for arm in ("baseline", "variant") for m in models for p in prompts
             for r in range(1, a.reps + 1)]
    random.Random(a.seed).shuffle(cells)  # interleave arms so drift in load/time does not line up with one arm
    todo = [c for c in cells if not ((out / "cells" / f"{c[0]}__{c[1]}__{c[2]['id']}__r{c[3]}" / "cell.json").exists()
            and json.loads((out / "cells" / f"{c[0]}__{c[1]}__{c[2]['id']}__r{c[3]}" / "cell.json").read_text()).get("status") == "ok")]
    print(f"{len(cells)} cells, {len(cells) - len(todo)} already done, running {len(todo)} with {a.jobs} jobs -> {out}", flush=True)
    if todo:
        Runner(a, out, trees, prompts, tpl, shims).run_all(todo)
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
