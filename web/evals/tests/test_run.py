import json
import os
import tempfile
import unittest

import run


def task(cat, n, set_):
    return {'id': f'{cat}-{n}', 'set': set_, 'category': cat, 'lang': 'en', 'url': 'https://x/', 'question': 'q https://x/', 'facts': []}


CATS = ['exact-detail', 'table', 'code', 'image', 'js', 'pdf', 'gist', 'synthesis']
TASKS = [task(c, n, 'dev' if n <= 2 else 'final') for c in CATS for n in range(1, 6)]


class Plan(unittest.TestCase):
    def test_a_development_round_is_64_runs(self):
        plan = run.plan_runs(TASKS, set_='dev', reps=2)
        self.assertEqual(len(plan), 64)
        self.assertEqual({t['set'] for t, _, _ in plan}, {'dev'})
        self.assertEqual({arm for _, arm, _ in plan}, {'A', 'B'})

    def test_the_final_run_is_192_runs(self):
        self.assertEqual(len(run.plan_runs(TASKS, set_='final', reps=4)), 192)

    def test_ids_narrow_the_plan(self):
        plan = run.plan_runs(TASKS, set_='dev', reps=1, ids=['exact-detail-1', 'gist-2'])
        self.assertEqual(sorted((t['id'], arm) for t, arm, _ in plan),
                         [('exact-detail-1', 'A'), ('exact-detail-1', 'B'), ('gist-2', 'A'), ('gist-2', 'B')])

    def test_an_unknown_or_wrong_set_id_is_refused(self):
        with self.assertRaises(SystemExit):
            run.plan_runs(TASKS, set_='dev', reps=1, ids=['exact-detail-3'])
        with self.assertRaises(SystemExit):
            run.plan_runs(TASKS, set_='dev', reps=1, ids=['nope'])

    def test_run_names_follow_i4(self):
        self.assertEqual(run.run_name('gist-2', 'B', 3), 'gist-2.B.sol.3')

    def test_a_screening_round_runs_one_configuration(self):
        plan = run.plan_runs(TASKS, set_='final', reps=2, arms=['A'])
        self.assertEqual(len(plan), 24 * 2)
        self.assertEqual({arm for _, arm, _ in plan}, {'A'})

    def test_round_sizes_come_from_the_tasks_file(self):
        self.assertEqual(run.round_runs(TASKS), run.ROUND_RUNS)
        hard = [task(c, n, 'dev' if n <= 2 else 'final') for c in ('verbatim', 'long-pdf') for n in range(1, 5)]
        self.assertEqual(run.round_runs(hard), {'dev': 4 * 2, 'final': 4 * 4})

    def test_the_pilot_takes_its_tasks_from_the_file(self):
        self.assertEqual(run.pilot_ids(TASKS), list(run.PILOT_TASKS))
        hard = [task(c, n, 'dev' if n <= 2 else 'final') for c in ('verbatim', 'long-pdf', 'image', 'search') for n in range(1, 5)]
        self.assertEqual(run.pilot_ids(hard), ['verbatim-1', 'long-pdf-1', 'image-1'])


class Resume(unittest.TestCase):
    def test_runs_with_a_graded_result_file_are_skipped(self):
        out = tempfile.mkdtemp()
        plan = run.plan_runs(TASKS, set_='dev', reps=1, ids=['code-1'])
        with open(os.path.join(out, 'code-1.A.sol.1.json'), 'w') as f:
            json.dump({'task': 'code-1', 'verdict': 'correct'}, f)
        with open(os.path.join(out, 'code-1.B.sol.1.json'), 'w') as f:
            json.dump({'task': 'code-1'}, f)  # ran, not yet graded
        todo = run.pending(plan, out)
        self.assertEqual([(t['id'], arm, need) for t, arm, _, need in todo], [('code-1', 'B', 'grade')])

    def test_runs_without_a_file_are_run(self):
        out = tempfile.mkdtemp()
        plan = run.plan_runs(TASKS, set_='dev', reps=1, ids=['code-1'])
        self.assertEqual([need for *_, need in run.pending(plan, out)], ['run', 'run'])


def usage(i, o, cr=0, cc=0, cost=0.0):
    return {'inputTokens': i, 'outputTokens': o, 'cacheReadInputTokens': cr, 'cacheCreationInputTokens': cc, 'costUSD': cost}


class Projection(unittest.TestCase):
    def test_per_model_tokens_and_usd_scale_to_a_round_and_the_final(self):
        runs = [
            {'arm': 'A', 'costUsd': 1.0, 'usageByModel': {'sol': usage(100, 10, 1000), 'claude-haiku-5-5[1m]': usage(50, 5, cost=0.2)},
             'grade': {'costUsd': 0.1, 'usageByModel': {'claude-opus-5-5[1m]': usage(20, 2)}}},
            {'arm': 'A', 'costUsd': 3.0, 'usageByModel': {'sol': usage(300, 30, 3000)}, 'grade': {'costUsd': 0.3, 'usageByModel': {'claude-opus-5-5[1m]': usage(40, 4)}}},
            {'arm': 'B', 'costUsd': 2.0, 'usageByModel': {'sol': usage(200, 20)},
             'haikuUsage': [{'usage': {'input_tokens': 70, 'output_tokens': 7, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}}],
             'grade': {'costUsd': 0.2, 'usageByModel': {'claude-opus-5-5[1m]': usage(30, 3)}}},
        ]
        p = run.projection(runs)
        # Per run, by arm: means.
        self.assertEqual(p['perRun']['A']['sol'], {'input': 200, 'output': 20, 'cacheRead': 2000, 'cacheCreation': 0})
        self.assertEqual(p['perRun']['A']['haiku'], {'input': 25, 'output': 2.5, 'cacheRead': 0, 'cacheCreation': 0})
        self.assertEqual(p['perRun']['B']['haiku'], {'input': 70, 'output': 7, 'cacheRead': 0, 'cacheCreation': 0})
        self.assertEqual(p['perRun']['A']['grader'], {'input': 30, 'output': 3, 'cacheRead': 0, 'cacheCreation': 0})
        self.assertEqual(p['perRun']['A']['usdRunner'], 2.0)
        self.assertEqual(p['perRun']['A']['usdByModel'], {'sol': 0.0, 'haiku': 0.1, 'grader': 0.0})
        self.assertEqual(p['perRun']['B']['usdGrader'], 0.2)
        # A round: 32 runs per arm; the final: 96 per arm.
        self.assertEqual(p['dev']['sol']['input'], 200 * 32 + 200 * 32)
        self.assertEqual(p['final']['haiku']['input'], 25 * 96 + 70 * 96)
        self.assertAlmostEqual(p['dev']['usdRunner'], 2.0 * 32 + 2.0 * 32)
        self.assertAlmostEqual(p['final']['usdGrader'], 0.2 * 96 + 0.2 * 96)
        self.assertEqual(p['runs'], {'A': 2, 'B': 1})

    def test_an_unpiloted_configuration_costs_what_the_piloted_one_did(self):
        runs = [{'arm': 'A', 'costUsd': 1.0, 'usageByModel': {'sol': usage(100, 10)},
                 'searchUsage': [{'usage': {'input_tokens': 12000, 'output_tokens': 300, 'server_tool_use': {'web_search_requests': 2}}}],
                 'grade': {'costUsd': 0.1, 'usageByModel': {}}}]
        p = run.projection(runs, {'dev': 10, 'final': 30})
        self.assertEqual(p['assumed'], {'B': 'A'})
        self.assertAlmostEqual(p['final']['usdRunner'], 1.0 * 30 * 2)
        self.assertEqual(p['final']['search']['input'], 12000 * 30 * 2)
        self.assertEqual(p['final']['searchRequests'], 2 * 30 * 2)
        self.assertIn('Configuration B was not piloted', run.format_projection(p))

    def test_runs_with_unavailable_usage_are_left_out_of_the_means_and_counted(self):
        runs = [
            {'arm': 'B', 'costUsd': 2.0, 'usageByModel': {'sol': usage(200, 20)}, 'grade': {'costUsd': 0.2, 'usageByModel': {}}},
            {'arm': 'B', 'costUsd': None, 'usageByModel': None, 'mainTokens': None, 'grade': {'costUsd': 0.4, 'usageByModel': {}}},
        ]
        p = run.projection(runs)
        self.assertEqual(p['perRun']['B']['sol']['input'], 200)
        self.assertEqual(p['perRun']['B']['usdRunner'], 2.0)
        self.assertAlmostEqual(p['perRun']['B']['usdGrader'], 0.3)
        self.assertEqual(p['unavailable'], {'B': 1})


if __name__ == '__main__':
    unittest.main()
