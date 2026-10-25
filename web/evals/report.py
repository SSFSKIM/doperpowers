"""Writes the eval report from a run folder, with the development rounds summarized.

    python3 -I web/evals/report.py web/evals/runs/<final stamp> --dev web/evals/runs/<dev stamp>... \\
      > docs/doperpowers/specs/2026-10-25-web-fetch-eval-report.md

The first folder is judged against the four pass criteria (the design's
"The evals"); a development folder given there is judged the same way, which
is how a round is checked against the freeze rule.
"""

import argparse
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = ('exact-detail', 'table', 'code', 'image', 'js', 'pdf', 'gist', 'synthesis')
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261025
MARGIN = -0.05
GIST_TOKEN_RATIO = 1.5


def main_tokens(r):
    """The main model's tokens of a run: input, output, cache read and cache creation together."""
    return sum((r.get('mainTokens') or {}).values())


def bootstrap_mean(ds, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    """The mean of the per-task differences and its 90% percentile interval over resampled tasks."""
    rng = random.Random(seed)
    n = len(ds)
    means = sorted(sum(rng.choice(ds) for _ in range(n)) / n for _ in range(resamples))
    lo = means[int(0.05 * resamples)]
    hi = means[int(0.95 * resamples) - 1]
    return sum(ds) / n, lo, hi


def _correct_share(runs):
    return sum(r.get('verdict') == 'correct' for r in runs) / len(runs) if runs else 0.0


def criteria(tasks, runs):
    by = {}
    for r in runs:
        by.setdefault((r['task'], r['arm']), []).append(r)
    cat_of = {t['id']: t['category'] for t in tasks}
    task_ids = [t['id'] for t in tasks if (t['id'], 'A') in by or (t['id'], 'B') in by]

    # 1. B not worse overall, with confidence.
    ds = [_correct_share(by.get((tid, 'B'), [])) - _correct_share(by.get((tid, 'A'), [])) for tid in task_ids]
    mean, lo, hi = bootstrap_mean(ds) if ds else (0.0, 0.0, 0.0)
    v1 = 'PASS' if lo >= MARGIN else 'INCONCLUSIVE' if mean > 0 else 'FAIL'
    c1 = {'n': 1, 'verdict': v1, 'mean': mean, 'lo': lo, 'hi': hi, 'tasks': len(ds)}

    # 2. The per-category tripwire.
    counts = {}
    for r in runs:
        if r.get('verdict') == 'correct':
            key = (cat_of.get(r['task']), r['arm'])
            counts[key] = counts.get(key, 0) + 1
    cats = [c for c in CATEGORIES if any(cat_of.get(tid) == c for tid in task_ids)]
    tripped = [c for c in cats if counts.get((c, 'B'), 0) < counts.get((c, 'A'), 0) - 1]
    c2 = {'n': 2, 'verdict': 'FAIL' if tripped else 'PASS', 'tripped': tripped,
          'byCategory': {c: (counts.get((c, 'A'), 0), counts.get((c, 'B'), 0)) for c in cats}}

    # 3. No tool error the tool caused, in B.
    errors = [(r['task'], r['rep'], e['text']) for r in runs if r['arm'] == 'B' for e in r.get('fetchErrors', []) if e.get('toolCaused')]
    c3 = {'n': 3, 'verdict': 'FAIL' if errors else 'PASS', 'errors': errors}

    # 4. Gist: B's median main-model tokens at most 1.5x A's.
    gist = {arm: [main_tokens(r) for r in runs if r['arm'] == arm and cat_of.get(r['task']) == 'gist'] for arm in ('A', 'B')}
    if gist['A'] and gist['B']:
        ma, mb = statistics.median(gist['A']), statistics.median(gist['B'])
        ratio = mb / ma if ma else float('inf')
        c4 = {'n': 4, 'verdict': 'PASS' if ratio <= GIST_TOKEN_RATIO else 'FAIL', 'ratio': ratio, 'medianA': ma, 'medianB': mb}
    else:
        c4 = {'n': 4, 'verdict': 'N/A', 'ratio': None, 'medianA': None, 'medianB': None}
    return [c1, c2, c3, c4]


def _criteria_lines(cs):
    c1, c2, c3, c4 = cs
    lines = [
        f"- **{c1['verdict']} 1** — B not worse overall: mean d {c1['mean']:+.3f}, 90% interval "
        f"[{c1['lo']:+.3f}, {c1['hi']:+.3f}] over {c1['tasks']} tasks ({BOOTSTRAP_RESAMPLES:,} resamples, seed {BOOTSTRAP_SEED}); "
        f"passes at a lower bound of {MARGIN:+.2f} or above.",
        f"- **{c2['verdict']} 2** — category tripwire (B at most one correct run fewer than A): "
        + ', '.join(f"{c} {a}/{b}" for c, (a, b) in c2['byCategory'].items())
        + (f"; tripped: {', '.join(c2['tripped'])}" if c2['tripped'] else '') + ' (A/B correct runs).',
        f"- **{c3['verdict']} 3** — no B tool error the tool caused: {len(c3['errors'])} found"
        + ''.join(f"\n  - {tid} rep {rep}: {text[:200]}" for tid, rep, text in c3['errors']),
    ]
    if c4['ratio'] is None:
        lines.append(f"- **{c4['verdict']} 4** — gist tokens: no gist runs in both configurations.")
    else:
        lines.append(f"- **{c4['verdict']} 4** — gist median main-model tokens: B {c4['medianB']:,.0f} vs A {c4['medianA']:,.0f} "
                     f"= {c4['ratio']:.2f}x (at most {GIST_TOKEN_RATIO}x).")
    return lines


def _table(tasks, runs):
    cat_of = {t['id']: t['category'] for t in tasks}
    rows = ['| Category | Config | Correct | Partial | Wrong | Median tokens | Median cost (USD) | Median duration (s) | Fetch calls (mean) |',
            '|---|---|---|---|---|---|---|---|---|']
    for c in CATEGORIES:
        for arm in ('A', 'B'):
            rs = [r for r in runs if r['arm'] == arm and cat_of.get(r['task']) == c]
            if not rs:
                continue
            v = [r.get('verdict') for r in rs]
            rows.append(f"| {c} | {arm} | {v.count('correct')} | {v.count('partial')} | {len(rs) - v.count('correct') - v.count('partial')} | "
                        f"{statistics.median(main_tokens(r) for r in rs):,.0f} | {statistics.median(r.get('costUsd', 0) for r in rs):.3f} | "
                        f"{statistics.median(r.get('durationMs', 0) for r in rs) / 1000:.0f} | {statistics.mean(r.get('fetchCalls', 0) for r in rs):.1f} |")
    return rows


def _failures(runs):
    out = []
    for r in sorted(runs, key=lambda r: (r['task'], r['arm'], r['rep'])):
        if r.get('verdict') == 'correct' and not r.get('runError'):
            continue
        why = r.get('runError') or r.get('note') or ('not graded' if 'verdict' not in r else '')
        out.append(f"- {r['task']} {r['arm']} rep {r['rep']}: {r.get('verdict', 'ungraded')} — {why}".rstrip(' —'))
    return out or ['- none']


def render(tasks, runs, title, dev_rounds=()):
    cs = criteria(tasks, runs)
    passed = all(c['verdict'] == 'PASS' for c in cs)
    md = [f'# Web fetch eval report — {title}', '',
          f"Overall: **{'PASS' if passed else 'NOT PASSED'}** "
          f"({len(runs)} runs; A = WebFetch only, B = mcp__web__fetch only; sol at xhigh; graded by opus).", '',
          '## Pass criteria', '', *_criteria_lines(cs), '',
          '## By category', '', *_table(tasks, runs), '',
          'Tokens are the main model\'s input, output, cache read and cache creation together. '
          'Cost is what the run output reports (sol is priced by Claude Code as an unknown model, '
          'and B\'s summary calls are outside it; see the usage notes in the design).', '',
          '## Runs not fully correct', '', *_failures(runs), '']
    if dev_rounds:
        md += ['## Development rounds', '']
        for label, ts, rs in dev_rounds:
            dc = criteria(ts, rs)
            md.append(f"### {label}")
            md.append('')
            md += _criteria_lines(dc)
            md.append('')
    return '\n'.join(md)


def load_runs(folder):
    runs = []
    for name in sorted(os.listdir(folder)):
        if name.endswith('.json') and name not in ('manifest.json', 'projection.json') and not name.endswith('.failed.json'):
            with open(os.path.join(folder, name)) as f:
                runs.append(json.load(f))
    return runs


def _tasks_of(folder, default):
    path = default
    manifest = os.path.join(folder, 'manifest.json')
    if os.path.exists(manifest):
        with open(manifest) as f:
            path = os.path.join(HERE, json.load(f)['tasksFile'])
    with open(path) as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('runs', nargs='+', help='the run folder judged (more than one: their runs together, as when reserve tasks are added)')
    ap.add_argument('--dev', nargs='*', default=[])
    ap.add_argument('--tasks', default=os.path.join(HERE, 'tasks.json'))
    a = ap.parse_args()
    tasks, runs = [], []
    for folder in a.runs:
        for t in _tasks_of(folder, a.tasks):
            if t['id'] not in {x['id'] for x in tasks}:
                tasks.append(t)
        runs += load_runs(folder)
    dev = [(f'Round {i} ({os.path.basename(os.path.normpath(d))})', _tasks_of(d, a.tasks), load_runs(d)) for i, d in enumerate(a.dev, 1)]
    title = ', '.join(os.path.basename(os.path.normpath(f)) for f in a.runs)
    sys.stdout.write(render(tasks, runs, title, dev) + '\n')


if __name__ == '__main__':
    main()
