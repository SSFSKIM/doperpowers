"""Writes the eval report from a run folder, with the development rounds summarized.

    python3 -I web/evals/report.py web/evals/runs/<final stamp> --dev web/evals/runs/<dev stamp>... \\
      > docs/doperpowers/specs/2026-10-25-web-fetch-eval-report.md

The first folder is judged against the four pass criteria (the design's
"The evals"); a development folder given there is judged the same way, which
is how a round is checked against the freeze rule.

A gate verdict is given only over the whole matrix its manifest's set calls
for (every task of the set x both configurations x the design's runs per
task), each run once and validly graded. Anything short of that is reported
INCOMPLETE, with what is missing, and its statistics are labelled provisional.
Criterion 4 applies to a set with gist tasks; criterion 1 also says whether B
is better with confidence (its interval's lower bound above 0), the reading
the hard set (tasks-hard.json) is built for. A folder of one configuration
(run.py --arms A) is a screening round: its report is each task's verdicts.
"""

import argparse
import json
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = ('exact-detail', 'table', 'code', 'image', 'js', 'pdf', 'gist', 'synthesis',
              'verbatim', 'long-page', 'long-pdf', 'search')
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261025
MARGIN = -0.05
GIST_TOKEN_RATIO = 1.5


VERDICTS = ('correct', 'partial', 'wrong')


def main_tokens(r):
    """The main model's tokens of a run: input, output, cache read and cache creation together; None when unavailable."""
    t = r.get('mainTokens')
    return None if t is None else sum(t.values())


def expected_runs(tasks, set_, reps, arms=('A', 'B')):
    """The (task, configuration, rep) matrix a set's gate (or a screening round) is judged over."""
    return {(t['id'], arm, rep) for t in tasks if t['set'] == set_ for arm in arms for rep in range(1, reps + 1)}


def _validly_graded(task, r):
    facts = r.get('facts')
    return (r.get('verdict') in VERDICTS and isinstance(facts, dict)
            and all(isinstance(facts.get(f['id']), bool) for f in task.get('facts', [])))


def audit(tasks, runs, expected):
    """What keeps a folder from a gate verdict: runs missing, not validly graded, duplicated, or not in the matrix."""
    by_id = {t['id']: t for t in tasks}
    seen = {}
    for r in runs:
        key = (r['task'], r['arm'], r['rep'])
        seen[key] = seen.get(key, 0) + 1
    out = {
        'missing': sorted(expected - set(seen)),
        'duplicates': sorted(k for k, n in seen.items() if n > 1),
        'unexpected': sorted(k for k in seen if k not in expected),
        'ungraded': sorted((r['task'], r['arm'], r['rep']) for r in runs
                           if (r['task'], r['arm'], r['rep']) in expected and not _validly_graded(by_id[r['task']], r)),
    }
    out['complete'] = not any(out.values())
    return out


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
    c1 = {'n': 1, 'verdict': v1, 'mean': mean, 'lo': lo, 'hi': hi, 'tasks': len(ds), 'better': lo > 0}

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

    # 4. Gist: B's median main-model tokens at most 1.5x A's. A run whose usage is
    # unavailable is left out of the median, and the criterion cannot pass while one is.
    # A set without gist tasks (the hard set) has nothing for it to judge.
    gist_runs = [r for r in runs if cat_of.get(r['task']) == 'gist']
    gist = {arm: [main_tokens(r) for r in gist_runs if r['arm'] == arm and main_tokens(r) is not None] for arm in ('A', 'B')}
    excluded = sum(main_tokens(r) is None for r in gist_runs)
    if not any(t['category'] == 'gist' for t in tasks):
        c4 = {'n': 4, 'verdict': 'N/A', 'ratio': None, 'medianA': None, 'medianB': None, 'excluded': 0}
    elif gist['A'] and gist['B']:
        ma, mb = statistics.median(gist['A']), statistics.median(gist['B'])
        ratio = mb / ma if ma else float('inf')
        verdict = 'UNAVAILABLE' if excluded else 'PASS' if ratio <= GIST_TOKEN_RATIO else 'FAIL'
        c4 = {'n': 4, 'verdict': verdict, 'ratio': ratio, 'medianA': ma, 'medianB': mb, 'excluded': excluded}
    else:
        c4 = {'n': 4, 'verdict': 'UNAVAILABLE', 'ratio': None, 'medianA': None, 'medianB': None, 'excluded': excluded}
    return [c1, c2, c3, c4]


def _criteria_lines(cs, final=True):
    c1, c2, c3, c4 = cs

    def label(c):
        return f"**{c['verdict']} {c['n']}**" if final else f"(provisional: {c['verdict'].lower()}) {c['n']}"

    lines = [
        f"- {label(c1)} — B not worse overall: mean d {c1['mean']:+.3f}, 90% interval "
        f"[{c1['lo']:+.3f}, {c1['hi']:+.3f}] over {c1['tasks']} tasks ({BOOTSTRAP_RESAMPLES:,} resamples, seed {BOOTSTRAP_SEED}); "
        f"passes at a lower bound of {MARGIN:+.2f} or above. B better with confidence (lower bound above 0): "
        f"{'yes' if c1['better'] else 'no'}.",
        f"- {label(c2)} — category tripwire (B at most one correct run fewer than A): "
        + ', '.join(f"{c} {a}/{b}" for c, (a, b) in c2['byCategory'].items())
        + (f"; tripped: {', '.join(c2['tripped'])}" if c2['tripped'] else '') + ' (A/B correct runs).',
        f"- {label(c3)} — no B tool error the tool caused: {len(c3['errors'])} found"
        + ''.join(f"\n  - {tid} rep {rep}: {text[:200]}" for tid, rep, text in c3['errors']),
    ]
    left_out = f"; {c4['excluded']} gist run(s) left out, their usage unavailable" if c4['excluded'] else ''
    if c4['verdict'] == 'N/A':
        lines.append(f"- {label(c4)} — gist tokens: the set has no gist tasks.")
    elif c4['ratio'] is None:
        lines.append(f"- {label(c4)} — gist tokens: no gist runs with usage in both configurations{left_out}.")
    else:
        lines.append(f"- {label(c4)} — gist median main-model tokens: B {c4['medianB']:,.0f} vs A {c4['medianA']:,.0f} "
                     f"= {c4['ratio']:.2f}x (at most {GIST_TOKEN_RATIO}x){left_out}.")
    return lines


def _median(values, fmt):
    """The median of the values that are available, with how many were not."""
    have = [v for v in values if v is not None]
    gone = len(values) - len(have)
    text = format(statistics.median(have), fmt) if have else 'n/a'
    return text + (f' ({gone} n/a)' if gone and have else '')


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
            durations = [None if r.get('durationMs') is None else r['durationMs'] / 1000 for r in rs]
            rows.append(f"| {c} | {arm} | {v.count('correct')} | {v.count('partial')} | {len(rs) - v.count('correct') - v.count('partial')} | "
                        f"{_median([main_tokens(r) for r in rs], ',.0f')} | {_median([r.get('costUsd') for r in rs], '.3f')} | "
                        f"{_median(durations, '.0f')} | {statistics.mean(r.get('fetchCalls', 0) for r in rs):.1f} |")
    return rows


def _by_task(tasks, runs, arms):
    """Each task's verdicts per configuration (correct/partial/wrong), and d when both ran."""
    both = len(arms) == 2
    mech = any('mechanism' in t for t in tasks)
    head = ('| Task | Category | ' + ('Mechanism | ' if mech else '') + ' | '.join(f'{arm} correct/partial/wrong' for arm in arms)
            + (' | d (B − A) |' if both else ' | Median tokens | Median duration (s) | Fetch calls (mean) |'))
    rows = [head, '|' + '---|' * (2 + mech + len(arms) + (1 if both else 3))]
    for t in tasks:
        cells, shares = [], {}
        rs_all = [r for r in runs if r['task'] == t['id']]
        if not rs_all:
            continue
        for arm in arms:
            rs = [r for r in rs_all if r['arm'] == arm]
            v = [r.get('verdict') for r in rs]
            cells.append(f"{v.count('correct')}/{v.count('partial')}/{len(rs) - v.count('correct') - v.count('partial')}")
            shares[arm] = _correct_share(rs)
        if both:
            cells.append(f"{shares['B'] - shares['A']:+.2f}")
        else:
            rs = [r for r in rs_all if r['arm'] == arms[0]]
            durations = [None if r.get('durationMs') is None else r['durationMs'] / 1000 for r in rs]
            cells += [_median([main_tokens(r) for r in rs], ',.0f'), _median(durations, '.0f'),
                      f"{statistics.mean(r.get('fetchCalls', 0) for r in rs):.1f}"]
        rows.append(f"| {t['id']} | {t['category']} | " + (f"{t.get('mechanism', '')} | " if mech else '') + ' | '.join(cells) + ' |')
    return rows


def _failures(runs):
    out = []
    for r in sorted(runs, key=lambda r: (r['task'], r['arm'], r['rep'])):
        if r.get('verdict') == 'correct' and not r.get('runError'):
            continue
        why = r.get('runError') or r.get('note') or ('not graded' if 'verdict' not in r else '')
        out.append(f"- {r['task']} {r['arm']} rep {r['rep']}: {r.get('verdict', 'ungraded')} — {why}".rstrip(' —'))
    return out or ['- none']


def _audit_lines(a):
    lines = [f"{len(a['missing'])} missing, {len(a['ungraded'])} not validly graded, "
             f"{len(a['duplicates'])} duplicated, {len(a['unexpected'])} not in the set's matrix."]
    for name, keys in (('Missing', a['missing']), ('Not validly graded', a['ungraded']),
                       ('Duplicated', a['duplicates']), ('Not in the matrix', a['unexpected'])):
        if keys:
            shown = ', '.join(f'{t} {arm} rep {rep}' for t, arm, rep in keys[:40])
            lines.append(f"- {name}: {shown}{f' … and {len(keys) - 40} more' if len(keys) > 40 else ''}")
    return lines


def _graders(runs):
    """Who graded the runs, read from their grade records: "opus", "sol at xhigh", or both."""
    seen = sorted({(g['model'] + (f" at {g['effort']}" if g.get('effort') else ''))
                   for g in ((r.get('grade') or {}) for r in runs) if g.get('model')})
    return ' and '.join(seen) or 'no grader yet'


def render_screening(tasks, runs, title, expected, arm):
    """A round of one configuration: no criteria, each task's verdicts."""
    a = audit(tasks, runs, expected)
    md = [f'# Web fetch screening — {title}', '',
          f"Configuration {arm} only ({'A = WebFetch' if arm == 'A' else 'B = mcp__web__fetch'}); "
          f"{len(runs)} runs of {len(expected)} expected; sol at xhigh; graded by {_graders(runs)}.", '']
    if not a['complete']:
        md += ['## Completeness', '', *_audit_lines(a), '']
    md += ['## By task', '', *_by_task(tasks, runs, [arm]), '',
           '## Runs not fully correct', '', *_failures(runs), '']
    return '\n'.join(md)


def render(tasks, runs, title, expected, dev_rounds=()):
    arms = sorted({arm for _, arm, _ in expected})
    if len(arms) == 1:
        return render_screening(tasks, runs, title, expected, arms[0])
    a = audit(tasks, runs, expected)
    cs = criteria(tasks, runs)
    if not a['complete']:
        overall = 'INCOMPLETE'
    else:
        overall = 'PASS' if all(c['verdict'] in ('PASS', 'N/A') for c in cs) else 'NOT PASSED'
    md = [f'# Web fetch eval report — {title}', '',
          f"Overall: **{overall}** "
          f"({len(runs)} runs of {len(expected)} expected; A = WebFetch only, B = mcp__web__fetch only; sol at xhigh; graded by {_graders(runs)}).", '']
    if not a['complete']:
        md += ['No gate verdict: the matrix is not complete and validly graded. '
               'The figures below are provisional, over the runs there are.', '', '## Completeness', '', *_audit_lines(a), '']
    md += ['## Pass criteria', '', *_criteria_lines(cs, a['complete']), '',
           '## By category', '', *_table(tasks, runs), '',
           'Tokens are the main model\'s input, output, cache read and cache creation together; '
           '"n/a" counts runs whose usage is unavailable (killed at the limit before a result line). '
           'Cost is what the run output reports (sol is priced by Claude Code as an unknown model, '
           'and B\'s summary calls are outside it; see the usage notes in the design).', '',
           '## By task', '', *_by_task(tasks, runs, ['A', 'B']), '',
           '## Runs not fully correct', '', *_failures(runs), '']
    if dev_rounds:
        md += ['## Development rounds', '']
        for label, ts, rs, exp in dev_rounds:
            da = audit(ts, rs, exp)
            md += [f"### {label}", '']
            if not da['complete']:
                md += [f"Incomplete: {_audit_lines(da)[0]}", '']
            md += [*_criteria_lines(criteria(ts, rs), da['complete']), '']
    return '\n'.join(md)


def load_runs(folder):
    runs = []
    for name in harness.run_files(folder):
        with open(os.path.join(folder, name)) as f:
            runs.append(json.load(f))
    return runs


def _folder(path):
    """A run folder's tasks, runs and expected matrix, from its manifest."""
    manifest = os.path.join(path, 'manifest.json')
    if not os.path.exists(manifest):
        sys.exit(f'report.py: {path} has no manifest.json (run.py writes one)')
    with open(manifest) as f:
        m = json.load(f)
    with open(os.path.join(HERE, m['tasksFile'])) as f:
        tasks = json.load(f)
    arms = m.get('arms', ['A', 'B'])
    # A task since dropped from its file leaves its runs behind; they are no part of the set now.
    ids = {t['id'] for t in tasks}
    runs = [r for r in load_runs(path) if r['task'] in ids]
    if len(arms) == 2:
        # A gate is judged over the design's runs per task.
        return tasks, runs, expected_runs(tasks, m['set'], harness.REPS[m['set']], arms)
    # A screening round: its runs per task, and the extra runs it gave some of the set's tasks.
    expected = expected_runs(tasks, m['set'], m['reps'], arms)
    in_set = {t['id'] for t in tasks if t['set'] == m['set']}
    expected |= {(r['task'], r['arm'], r['rep']) for r in runs if r['task'] in in_set and r['arm'] in arms}
    return tasks, runs, expected


def gate_matrix(tasks, expected):
    """Folders taken together that hold both configurations are judged as a gate, over the design's
    whole paired matrix of each set they cover; one configuration's folders stay a screening round."""
    if len({arm for _, arm, _ in expected}) < 2:
        return expected
    set_of = {t['id']: t['set'] for t in tasks}
    out = set(expected)
    for s in {set_of[tid] for tid, _, _ in expected}:
        out |= expected_runs(tasks, s, harness.REPS[s])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('runs', nargs='+', help='the run folder judged (more than one: their runs together, as when reserve tasks are added)')
    ap.add_argument('--dev', nargs='*', default=[])
    a = ap.parse_args()
    tasks, runs, expected = [], [], set()
    for path in a.runs:
        ts, rs, exp = _folder(path)
        tasks += [t for t in ts if t['id'] not in {x['id'] for x in tasks}]
        runs += rs
        expected |= exp
    expected = gate_matrix(tasks, expected)
    dev = [(f'Round {i} ({os.path.basename(os.path.normpath(d))})', *_folder(d)) for i, d in enumerate(a.dev, 1)]
    title = ', '.join(os.path.basename(os.path.normpath(f)) for f in a.runs)
    sys.stdout.write(render(tasks, runs, title, expected, dev) + '\n')


if __name__ == '__main__':
    main()
