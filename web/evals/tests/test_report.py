import unittest

import report

CATS = ['exact-detail', 'table', 'code', 'image', 'js', 'pdf', 'gist', 'synthesis']


def tasks(n_per_cat=3):
    return [{'id': f'{c}-{i}', 'category': c, 'set': 'final'} for c in CATS for i in range(1, n_per_cat + 1)]


def runs_for(ts, a_correct, b_correct, reps=4, tokens=1000):
    """a_correct / b_correct: task id -> correct runs out of `reps`."""
    out = []
    for t in ts:
        for arm, table in (('A', a_correct), ('B', b_correct)):
            for rep in range(1, reps + 1):
                ok = rep <= table.get(t['id'], reps)
                out.append({'task': t['id'], 'arm': arm, 'rep': rep, 'verdict': 'correct' if ok else 'wrong',
                            'mainTokens': {'input': tokens, 'output': 0, 'cacheRead': 0, 'cacheCreation': 0},
                            'fetchCalls': 1, 'fetchErrors': [], 'turns': 2, 'durationMs': 1000, 'costUsd': 0.1, 'finalText': '', 'note': ''})
    return out


class Bootstrap(unittest.TestCase):
    def test_no_difference_is_a_zero_interval(self):
        mean, lo, hi = report.bootstrap_mean([0.0] * 24)
        self.assertEqual((mean, lo, hi), (0.0, 0.0, 0.0))

    def test_it_is_seeded(self):
        ds = [0.25, -0.25, 0, 0.5, -0.5, 0, 0.25, 0] * 3
        self.assertEqual(report.bootstrap_mean(ds), report.bootstrap_mean(ds))
        mean, lo, hi = report.bootstrap_mean(ds)
        self.assertLess(lo, mean)
        self.assertGreater(hi, mean)


class Criteria(unittest.TestCase):
    def setUp(self):
        self.ts = tasks()

    def test_equal_arms_pass_everything(self):
        c = report.criteria(self.ts, runs_for(self.ts, {}, {}))
        self.assertEqual([x['verdict'] for x in c], ['PASS', 'PASS', 'PASS', 'PASS'])

    def test_criterion_1_fails_when_b_is_clearly_worse(self):
        b = {t['id']: 2 for t in self.ts}  # B 2/4 everywhere, A 4/4
        c1 = report.criteria(self.ts, runs_for(self.ts, {}, b))[0]
        self.assertEqual(c1['verdict'], 'FAIL')
        self.assertAlmostEqual(c1['mean'], -0.5)

    def test_criterion_1_inconclusive_on_a_positive_mean_with_a_low_bound(self):
        a = {t['id']: 2 for t in self.ts}
        b = dict(a)
        b['code-1'] = 0
        b['table-1'] = 0
        for tid in ('exact-detail-1', 'image-1', 'js-1', 'pdf-1', 'gist-1', 'synthesis-1'):
            b[tid] = 4  # +0.5 on six tasks, -0.5 on two: mean > 0, wide interval
        b['exact-detail-2'] = 0
        b['image-2'] = 0
        b['js-2'] = 0
        c1 = report.criteria(self.ts, runs_for(self.ts, a, b))[0]
        self.assertGreater(c1['mean'], 0)
        self.assertLess(c1['lo'], -0.05)
        self.assertEqual(c1['verdict'], 'INCONCLUSIVE')

    def test_criterion_2_trips_at_two_fewer_correct_in_a_category(self):
        c2 = report.criteria(self.ts, runs_for(self.ts, {}, {'pdf-1': 2}))[1]
        self.assertEqual(c2['verdict'], 'FAIL')
        self.assertEqual(c2['tripped'], ['pdf'])
        c2 = report.criteria(self.ts, runs_for(self.ts, {}, {'pdf-1': 3}))[1]
        self.assertEqual(c2['verdict'], 'PASS')

    def test_criterion_3_counts_only_b_errors_the_tool_caused(self):
        rs = runs_for(self.ts, {}, {})
        a_run = next(r for r in rs if r['arm'] == 'A')
        a_run['fetchErrors'] = [{'text': 'boom', 'toolCaused': True}]
        b_runs = [r for r in rs if r['arm'] == 'B']
        b_runs[0]['fetchErrors'] = [{'text': 'fetch failed: x: HTTP 404', 'toolCaused': False}]
        self.assertEqual(report.criteria(self.ts, rs)[2]['verdict'], 'PASS')
        b_runs[1]['fetchErrors'] = [{'text': 'fetch failed: x: the clipper failed', 'toolCaused': True}]
        c3 = report.criteria(self.ts, rs)[2]
        self.assertEqual(c3['verdict'], 'FAIL')
        self.assertEqual(len(c3['errors']), 1)

    def test_criterion_4_compares_gist_medians(self):
        rs = runs_for(self.ts, {}, {})
        for r in rs:
            if r['task'].startswith('gist') and r['arm'] == 'B':
                r['mainTokens']['cacheRead'] = 600  # 1600 vs 1000: 1.6x
        c4 = report.criteria(self.ts, rs)[3]
        self.assertEqual(c4['verdict'], 'FAIL')
        self.assertAlmostEqual(c4['ratio'], 1.6)
        for r in rs:
            if r['task'].startswith('gist') and r['arm'] == 'B':
                r['mainTokens']['cacheRead'] = 500
        self.assertEqual(report.criteria(self.ts, rs)[3]['verdict'], 'PASS')

    def test_an_ungraded_run_counts_as_not_correct(self):
        rs = runs_for(self.ts, {}, {})
        for r in rs:
            if r['task'] == 'code-1' and r['arm'] == 'B':
                r.pop('verdict')
        c = report.criteria(self.ts, rs)
        self.assertAlmostEqual(c[0]['mean'], -1 / 24)


class LoadRuns(unittest.TestCase):
    def test_only_run_files_are_loaded(self):
        import json
        import os
        import tempfile
        d = tempfile.mkdtemp()
        for name, obj in (('code-1.A.sol.1.json', {'task': 'code-1'}), ('code-1.B.sol.1.failed.json', {'rc': 1}),
                          ('manifest.json', {}), ('projection.json', {}), ('code-1.A.sol.1.stream.jsonl', {})):
            with open(os.path.join(d, name), 'w') as f:
                json.dump(obj, f)
        self.assertEqual(report.load_runs(d), [{'task': 'code-1'}])


class Render(unittest.TestCase):
    def test_the_report_names_each_criterion_and_category(self):
        ts = tasks()
        md = report.render(ts, runs_for(ts, {}, {}), title='Final run', dev_rounds=[('round 1', ts, runs_for(ts, {}, {}, reps=2))])
        for needle in ('PASS 1', 'PASS 2', 'PASS 3', 'PASS 4', '| gist |', 'round 1', 'mean d'):
            self.assertIn(needle, md)


if __name__ == '__main__':
    unittest.main()
