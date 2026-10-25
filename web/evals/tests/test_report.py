import unittest

import report

CATS = ['exact-detail', 'table', 'code', 'image', 'js', 'pdf', 'gist', 'synthesis']


def tasks(n_per_cat=3):
    return [{'id': f'{c}-{i}', 'category': c, 'set': 'final', 'facts': [{'id': 'f1'}]} for c in CATS for i in range(1, n_per_cat + 1)]


def runs_for(ts, a_correct, b_correct, reps=4, tokens=1000):
    """a_correct / b_correct: task id -> correct runs out of `reps`."""
    out = []
    for t in ts:
        for arm, table in (('A', a_correct), ('B', b_correct)):
            for rep in range(1, reps + 1):
                ok = rep <= table.get(t['id'], reps)
                out.append({'task': t['id'], 'arm': arm, 'rep': rep, 'verdict': 'correct' if ok else 'wrong', 'facts': {'f1': ok},
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


class Completeness(unittest.TestCase):
    def setUp(self):
        self.ts = tasks()
        self.expected = report.expected_runs(self.ts, 'final', 4)

    def test_the_expected_matrix_is_task_by_arm_by_rep(self):
        self.assertEqual(len(self.expected), 24 * 2 * 4)
        self.assertIn(('code-1', 'B', 4), self.expected)
        dev = [dict(t, set='dev') for t in tasks(2)]
        self.assertEqual(len(report.expected_runs(dev + self.ts, 'dev', 2)), 16 * 2 * 2)

    def test_a_full_graded_matrix_is_complete(self):
        a = report.audit(self.ts, runs_for(self.ts, {}, {}), self.expected)
        self.assertTrue(a['complete'])

    def test_missing_runs_are_named(self):
        pilot = [r for r in runs_for(self.ts, {}, {}, reps=1) if r['task'] in ('code-1', 'gist-1', 'pdf-1')]
        a = report.audit(self.ts, pilot, self.expected)
        self.assertFalse(a['complete'])
        self.assertEqual(len(a['missing']), 192 - 6)

    def test_ungraded_and_invalid_grades_are_named(self):
        rs = runs_for(self.ts, {}, {})
        for r in rs:
            if r['arm'] == 'A':
                r.pop('verdict')
        rs[4]['facts'] = {}  # a B run (the first task's rep 1) whose grade does not cover the key
        a = report.audit(self.ts, rs, self.expected)
        self.assertFalse(a['complete'])
        self.assertEqual(len(a['ungraded']), 96 + 1)

    def test_duplicates_and_strays_are_named(self):
        rs = runs_for(self.ts, {}, {})
        rs.append(dict(rs[0]))
        rs.append({**rs[0], 'task': 'nope-1'})
        a = report.audit(self.ts, rs, self.expected)
        self.assertFalse(a['complete'])
        self.assertEqual(a['duplicates'], [(rs[0]['task'], rs[0]['arm'], rs[0]['rep'])])
        self.assertEqual(a['unexpected'], [('nope-1', rs[0]['arm'], rs[0]['rep'])])


class Unavailable(unittest.TestCase):
    def test_criterion_4_does_not_pass_on_unavailable_tokens(self):
        ts = tasks()
        rs = runs_for(ts, {}, {})
        b_gist = [r for r in rs if r['task'].startswith('gist') and r['arm'] == 'B']
        b_gist[0]['mainTokens'] = None
        c4 = report.criteria(ts, rs)[3]
        self.assertEqual(c4['verdict'], 'UNAVAILABLE')
        self.assertEqual(c4['excluded'], 1)
        self.assertEqual(c4['medianB'], 1000)  # over the runs that have usage

    def test_tables_leave_unavailable_values_out_and_say_so(self):
        ts = tasks()
        rs = runs_for(ts, {}, {})
        for r in rs:
            if r['task'] == 'pdf-1' and r['arm'] == 'B' and r['rep'] == 1:
                r['mainTokens'], r['costUsd'] = None, None
        md = report.render(ts, rs, 'x', report.expected_runs(ts, 'final', 4))
        self.assertIn('| pdf | B | 12 | 0 | 0 | 1,000 (1 n/a) | 0.100 (1 n/a) |', md)


class Render(unittest.TestCase):
    def test_a_complete_report_names_each_criterion_and_category(self):
        ts = tasks()
        dev_ts = [dict(t, set='dev') for t in ts]
        md = report.render(ts, runs_for(ts, {}, {}), 'Final run', report.expected_runs(ts, 'final', 4),
                           dev_rounds=[('round 1', dev_ts, runs_for(dev_ts, {}, {}, reps=2), report.expected_runs(dev_ts, 'dev', 2))])
        for needle in ('Overall: **PASS**', 'PASS 1', 'PASS 2', 'PASS 3', 'PASS 4', '| gist |', 'round 1', 'mean d'):
            self.assertIn(needle, md)
        self.assertNotIn('provisional', md)

    def test_an_incomplete_folder_gets_no_gate_verdict(self):
        ts = tasks()
        pilot = [r for r in runs_for(ts, {}, {}, reps=1) if r['task'] in ('code-1', 'gist-1', 'pdf-1')]
        md = report.render(ts, pilot, 'pilot', report.expected_runs(ts, 'final', 4))
        self.assertIn('Overall: **INCOMPLETE**', md)
        self.assertIn('provisional', md)
        self.assertNotIn('**PASS', md)
        self.assertIn('186 missing', md)

    def test_removing_every_a_verdict_withholds_the_gate(self):
        ts = tasks()
        rs = runs_for(ts, {}, {})
        for r in rs:
            if r['arm'] == 'A':
                r.pop('verdict')
        md = report.render(ts, rs, 'x', report.expected_runs(ts, 'final', 4))
        self.assertIn('Overall: **INCOMPLETE**', md)
        self.assertIn('96 not validly graded', md)


HARD = ['verbatim', 'long-page', 'long-pdf', 'image', 'search']


def hard_tasks():
    return [{'id': f'{c}-{i}', 'category': c, 'set': 'final', 'facts': [{'id': 'f1'}]} for c in HARD for i in range(1, 4)]


class HardSet(unittest.TestCase):
    def test_without_gist_tasks_criterion_4_does_not_apply(self):
        ts = hard_tasks()
        c = report.criteria(ts, runs_for(ts, {}, {}))
        self.assertEqual(c[3]['verdict'], 'N/A')
        md = report.render(ts, runs_for(ts, {}, {}), 'hard', report.expected_runs(ts, 'final', 4))
        self.assertIn('Overall: **PASS**', md)
        self.assertIn('the set has no gist tasks', md)
        self.assertIn('| long-pdf | A |', md)

    def test_b_better_with_confidence_is_read_off_the_lower_bound(self):
        ts = hard_tasks()
        a = {t['id']: 1 for t in ts}  # A 1/4 everywhere, B 4/4
        c1 = report.criteria(ts, runs_for(ts, a, {}))[0]
        self.assertTrue(c1['better'])
        self.assertAlmostEqual(c1['mean'], 0.75)
        a = {t['id']: 3 for t in ts[:2]}  # B ahead on two tasks of fifteen only
        a.update({t['id']: 4 for t in ts[2:]})
        b = {ts[2]['id']: 3}
        self.assertFalse(report.criteria(ts, runs_for(ts, a, b))[0]['better'])
        md = report.render(ts, runs_for(ts, {t['id']: 1 for t in ts}, {}), 'hard', report.expected_runs(ts, 'final', 4))
        self.assertIn('B better with confidence (lower bound above 0): yes', md)
        self.assertIn('| verbatim-1 | verbatim | 1/0/3 | 4/0/0 | +0.75 |', md)

    def test_a_screening_folder_reports_each_tasks_verdicts(self):
        ts = hard_tasks()
        expected = report.expected_runs(ts, 'final', 2, arms=['A'])
        self.assertEqual(len(expected), 15 * 2)
        rs = [r for r in runs_for(ts, {'search-2': 1}, {}, reps=2) if r['arm'] == 'A']
        md = report.render(ts, rs, 'screen', expected)
        self.assertIn('# Web fetch screening', md)
        self.assertNotIn('Pass criteria', md)
        self.assertIn('| search-2 | search | 1/0/1 |', md)
        self.assertIn('- search-2 A rep 2: wrong', md)

    def test_one_configurations_folders_taken_together_are_judged_over_the_whole_matrix(self):
        ts = hard_tasks()
        a_only = report.expected_runs(ts, 'final', 1, arms=['A'])
        b_only = report.expected_runs(ts, 'final', 1, arms=['B'])
        self.assertEqual(report.gate_matrix(ts, a_only), a_only)  # one configuration stays a screening round
        both = report.gate_matrix(ts, a_only | b_only)
        self.assertEqual(len(both), 15 * 2 * 4)
        md = report.render(ts, runs_for(ts, {}, {}, reps=1), 'x', both)
        self.assertIn('Overall: **INCOMPLETE**', md)

    def test_a_set_with_mechanisms_is_summarized_by_them(self):
        ts = [dict(t, mechanism='over-10mb' if t['category'] == 'long-pdf' else 'quote-limit') for t in hard_tasks()]
        rows = report._by_mechanism(ts, runs_for(ts, {'long-pdf-1': 0, 'long-pdf-2': 2}, {}))
        self.assertIn('| over-10mb | 3 | 6/12 | 12/12 | +0.50 |', rows)
        self.assertIn('| quote-limit | 12 | 48/48 | 48/48 | +0.00 |', rows)
        md = report.render(ts, runs_for(ts, {}, {}), 'x', report.expected_runs(ts, 'final', 4))
        self.assertIn('## By mechanism', md)
        self.assertEqual(report._by_mechanism(hard_tasks(), runs_for(hard_tasks(), {}, {})), [])

    def test_a_tasks_mechanism_gets_a_column(self):
        ts = [dict(t, mechanism='over-10mb' if t['category'] == 'long-pdf' else 'quote-limit') for t in hard_tasks()]
        rows = report._by_task(ts, runs_for(ts, {'long-pdf-1': 0}, {}), ['A', 'B'])
        self.assertEqual(rows[0], '| Task | Category | Mechanism | A correct/partial/wrong | B correct/partial/wrong | d (B − A) |')
        self.assertIn('| long-pdf-1 | long-pdf | over-10mb | 0/0/4 | 4/0/0 | +1.00 |', rows)


if __name__ == '__main__':
    unittest.main()
