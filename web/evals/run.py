"""Runs the web-fetch evals: each task in configuration A (WebFetch only) and
B (mcp__web__fetch only), `claude -p` on sol at xhigh in a temporary HOME,
then grades each run (grade.py).

    python3 -I web/evals/run.py --pilot              # 3 dev tasks x 2 configurations x 1 run, then the cost projection
    python3 -I web/evals/run.py --set dev            # one development round: 16 tasks x 2 x 2 = 64 runs
    python3 -I web/evals/run.py --set final          # the final run: 24 x 2 x 4 = 192 runs
    python3 -I web/evals/run.py --set dev --out web/evals/runs/<stamp>   # resume an interrupted suite

A run whose result file holds a verdict is skipped; one that ran but is not
graded is graded. Runs land in web/evals/runs/<UTC stamp>/ (gitignored):
<task>.<arm>.sol.<rep>.json (I4), with the run's stream beside it.
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grade  # noqa: E402
import harness  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PILOT_TASKS = ('exact-detail-1', 'image-1', 'gist-2')
REPS = {'dev': 2, 'final': 4}
JOBS = 6
RUN_TIMEOUT_S = 600
ARMS = ('A', 'B')
# Runs per configuration in a development round and in the final run.
ROUND_RUNS = {'dev': 16 * REPS['dev'], 'final': 24 * REPS['final']}
TOKEN_KINDS = ('input', 'output', 'cacheRead', 'cacheCreation')


def plan_runs(tasks, set_, reps, ids=None):
    chosen = [t for t in tasks if t['set'] == set_]
    if ids:
        known = {t['id']: t for t in tasks}
        for i in ids:
            if i not in known or known[i]['set'] != set_:
                sys.exit(f'run.py: {i} is not a {set_} task')
        chosen = [t for t in chosen if t['id'] in ids]
    # Rep-major, so the runs going at once are spread over tasks and sites.
    return [(t, arm, rep) for rep in range(1, reps + 1) for t in chosen for arm in ARMS]


def run_name(task_id, arm, rep):
    return f'{task_id}.{arm}.{harness.RUNNER_MODEL}.{rep}'


def pending(plan, out):
    todo = []
    for t, arm, rep in plan:
        path = os.path.join(out, run_name(t['id'], arm, rep) + '.json')
        if not os.path.exists(path):
            todo.append((t, arm, rep, 'run'))
            continue
        with open(path) as f:
            if 'verdict' not in json.load(f):
                todo.append((t, arm, rep, 'grade'))
    return todo


def _family(model):
    if model == harness.RUNNER_MODEL:
        return 'sol'
    for name in ('haiku', 'opus', 'sonnet'):
        if name in model:
            return name
    return model


def _zero():
    return {k: 0 for k in TOKEN_KINDS}


def _add(acc, u):
    acc['input'] += u.get('inputTokens', u.get('input_tokens', 0)) or 0
    acc['output'] += u.get('outputTokens', u.get('output_tokens', 0)) or 0
    acc['cacheRead'] += u.get('cacheReadInputTokens', u.get('cache_read_input_tokens', 0)) or 0
    acc['cacheCreation'] += u.get('cacheCreationInputTokens', u.get('cache_creation_input_tokens', 0)) or 0


def projection(runs):
    """Per-model tokens and reported USD per run (by configuration), scaled to a development round and the final run."""
    per_arm = {}
    for arm in ARMS:
        rs = [r for r in runs if r['arm'] == arm]
        if not rs:
            continue
        tok = {m: _zero() for m in ('sol', 'haiku', 'opus')}
        usd = {m: 0.0 for m in ('sol', 'haiku', 'opus')}
        runner_usd = grader_usd = 0.0
        for r in rs:
            for model, u in (r.get('usageByModel') or {}).items():
                fam = _family(model)
                _add(tok.setdefault(fam, _zero()), u)
                usd[fam] = usd.get(fam, 0.0) + (u.get('costUSD') or 0.0)
            for line in r.get('haikuUsage') or []:
                _add(tok['haiku'], line.get('usage') or {})
            g = r.get('grade') or {}
            for model, u in (g.get('usageByModel') or {}).items():
                fam = _family(model)
                _add(tok.setdefault(fam, _zero()), u)
                usd[fam] = usd.get(fam, 0.0) + (u.get('costUSD') or 0.0)
            runner_usd += r.get('costUsd') or 0.0
            grader_usd += g.get('costUsd') or 0.0
        n = len(rs)
        mean = {m: {k: v / n for k, v in t.items()} for m, t in tok.items()}
        mean = {m: {k: (int(v) if float(v).is_integer() else v) for k, v in t.items()} for m, t in mean.items()}
        mean['usdByModel'] = {m: v / n for m, v in usd.items()}
        mean['usdRunner'] = runner_usd / n
        mean['usdGrader'] = grader_usd / n
        per_arm[arm] = mean
    out = {'perRun': per_arm, 'runs': {arm: len([r for r in runs if r['arm'] == arm]) for arm in ARMS if any(r['arm'] == arm for r in runs)}}
    for name, n in ROUND_RUNS.items():
        total = {}
        for arm, mean in per_arm.items():
            for key, val in mean.items():
                if isinstance(val, dict):
                    acc = total.setdefault(key, {})
                    for k, v in val.items():
                        acc[k] = acc.get(k, 0) + v * n
                else:
                    total[key] = total.get(key, 0) + val * n
        out[name] = total
    return out


def format_projection(p):
    lines = [f"Pilot runs: {p['runs']}", '']
    for scope, label in (('dev', f"one development round ({2 * ROUND_RUNS['dev']} runs)"),
                         ('final', f"the final run ({2 * ROUND_RUNS['final']} runs)")):
        t = p[scope]
        lines.append(f'Projected for {label}:')
        for m, role in (('sol', 'runner'), ('opus', 'grader'), ('haiku', 'summaries')):
            u = t.get(m, {})
            lines.append(f"  {m:6} ({role:9}) input {u.get('input', 0):>13,.0f}  output {u.get('output', 0):>11,.0f}  "
                         f"cache read {u.get('cacheRead', 0):>13,.0f}  cache write {u.get('cacheCreation', 0):>11,.0f}  "
                         f"USD reported {t['usdByModel'].get(m, 0):>8.2f}")
        lines.append(f"  USD reported: runner sessions {t['usdRunner']:.2f} + grader {t['usdGrader']:.2f} = {t['usdRunner'] + t['usdGrader']:.2f}")
        lines.append('')
    return '\n'.join(lines)


def _git(*args):
    return subprocess.run(['git', '-C', HERE, *args], capture_output=True, text=True).stdout.strip()


def _manifest(out, set_, tasks_file, reps):
    path = os.path.join(out, 'manifest.json')
    now = {'commit': _git('rev-parse', 'HEAD'), 'dirty': bool(_git('status', '--porcelain', '--', os.path.dirname(HERE)))}
    if os.path.exists(path):
        with open(path) as f:
            m = json.load(f)
        if m['commit'] != now['commit'] or m['set'] != set_ or m['tasksFile'] != os.path.basename(tasks_file):
            sys.exit(f"run.py: {out} holds runs of {m['set']} at {m['commit'][:8]} ({m['tasksFile']}); "
                     f"this is {set_} at {now['commit'][:8]}: start a new folder")
        return m
    version = subprocess.run(['claude', '--version'], capture_output=True, text=True).stdout.strip()
    m = {**now, 'set': set_, 'tasksFile': os.path.basename(tasks_file), 'reps': reps, 'model': harness.RUNNER_MODEL,
         'effort': harness.RUNNER_EFFORT, 'claude': version, 'started': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    grade.write_json(path, m)
    return m


def run_one(t, arm, rep, out, work):
    """One run, written as its I4 file; None when the run failed for a reason outside it (no result, an API error), so a resume retries it."""
    name = run_name(t['id'], arm, rep)
    home = harness.make_home(work)
    cwd = tempfile.mkdtemp(prefix='cwd-', dir=work)
    try:
        args = harness.runner_args(arm, harness.WEB_PLUGIN, t['question'])
        stdout, stderr, rc, timed_out = harness.run_claude(args, cwd, harness.run_env(home), RUN_TIMEOUT_S)
        with open(os.path.join(out, name + '.stream.jsonl'), 'w') as f:
            f.write(stdout)
        if stderr.strip():
            with open(os.path.join(out, name + '.stderr.txt'), 'w') as f:
                f.write(stderr)
        m = harness.parse_stream(stdout, arm, timed_out=timed_out)
        haiku = []
        usage_log = os.path.join(home, '.cache', 'claude-web', 'usage.jsonl')
        if os.path.exists(usage_log):
            with open(usage_log) as f:
                haiku = [json.loads(line) for line in f if line.strip()]
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(cwd, ignore_errors=True)
    has_result = '"type":"result"' in stdout.replace(' ', '')
    if not timed_out and (not has_result or _api_error(stdout)):
        with open(os.path.join(out, name + '.failed.json'), 'w') as f:
            json.dump({'rc': rc, 'stderr': stderr[-2000:], 'apiError': _api_error(stdout)}, f, indent=1)
        return None
    r = {'task': t['id'], 'arm': arm, 'model': harness.RUNNER_MODEL, 'effort': harness.RUNNER_EFFORT, 'rep': rep,
         'finalText': m['finalText'], 'mainTokens': m['mainTokens'], 'usageByModel': m['usageByModel'],
         **({'haikuUsage': haiku} if arm == 'B' else {}),
         'fetchCalls': m['fetchCalls'], 'fetchErrors': m['fetchErrors'],
         'turns': m['turns'], 'durationMs': m['durationMs'], 'costUsd': m['costUsd'], 'initModel': m['initModel']}
    if timed_out:
        r['runError'] = f'timed out after {RUN_TIMEOUT_S} s'
    grade.write_json(os.path.join(out, name + '.json'), r)
    return r


def _api_error(stdout):
    for line in stdout.splitlines():
        if '"type":"result"' in line.replace(' ', ''):
            try:
                return json.loads(line).get('api_error_status')
            except ValueError:
                return None
    return None


def grade_one(t, arm, rep, out, work):
    path = os.path.join(out, run_name(t['id'], arm, rep) + '.json')
    with open(path) as f:
        r = json.load(f)
    g, usage = grade.grade(t, r.get('finalText', ''), work)
    r['grade'] = usage
    if g:
        r.update(g)
    grade.write_json(path, r)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument('--pilot', action='store_true')
    which.add_argument('--set', choices=('dev', 'final'))
    ap.add_argument('--tasks', default=os.path.join(HERE, 'tasks.json'))
    ap.add_argument('--ids', help='comma-separated task ids, to run part of the set')
    ap.add_argument('--reps', type=int)
    ap.add_argument('--out')
    ap.add_argument('--jobs', type=int, default=JOBS)
    a = ap.parse_args()

    with open(a.tasks) as f:
        tasks = json.load(f)
    set_ = 'dev' if a.pilot else a.set
    ids = list(PILOT_TASKS) if a.pilot else (a.ids.split(',') if a.ids else None)
    reps = a.reps or (1 if a.pilot else REPS[set_])
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = a.out or os.path.join(HERE, 'runs', stamp + ('-pilot' if a.pilot else f'-{set_}'))
    os.makedirs(out, exist_ok=True)
    m = _manifest(out, set_, a.tasks, reps)
    if m['dirty']:
        print(f'run.py: note: web/ has uncommitted changes at {m["commit"][:8]}', file=sys.stderr)

    plan = plan_runs(tasks, set_, reps, ids)
    todo = pending(plan, out)
    print(f'{out}: {len(plan)} runs, {len(todo)} to do', flush=True)
    work = tempfile.mkdtemp(prefix='web-evals-')
    lock = threading.Lock()

    def job(item):
        t, arm, rep, need = item
        r = run_one(t, arm, rep, out, work) if need == 'run' else None
        if need == 'run' and r is None:
            line = f'{run_name(t["id"], arm, rep)}: FAILED outside the run (see .failed.json); a resume retries it'
        else:
            r = grade_one(t, arm, rep, out, work)
            tok = r['mainTokens']
            line = (f"{run_name(t['id'], arm, rep)}: {r.get('verdict', 'UNGRADED')}  fetch {r['fetchCalls']}"
                    f"{' errors ' + str(len(r['fetchErrors'])) if r['fetchErrors'] else ''}  turns {r['turns']}  "
                    f"sol tokens {sum(tok.values()):,}  {r['durationMs'] / 1000:.0f} s  ${r['costUsd']:.2f}"
                    f"{'  ' + r['runError'] if r.get('runError') else ''}")
        with lock:
            print(line, flush=True)

    try:
        with concurrent.futures.ThreadPoolExecutor(a.jobs) as pool:
            list(pool.map(job, todo))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    runs = []
    for t, arm, rep in plan:
        path = os.path.join(out, run_name(t['id'], arm, rep) + '.json')
        if os.path.exists(path):
            with open(path) as f:
                runs.append(json.load(f))
    print(f'{len(runs)}/{len(plan)} runs recorded, {sum("verdict" in r for r in runs)} graded')
    if a.pilot:
        p = projection(runs)
        grade.write_json(os.path.join(out, 'projection.json'), p)
        print(format_projection(p))


if __name__ == '__main__':
    main()
