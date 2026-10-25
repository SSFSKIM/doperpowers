import unittest

import grade
import harness

TASK = {
    'id': 'exact-detail-1', 'question': 'What default applies to max_udp_payload_size?',
    'facts': [{'id': 'f1', 'claim': 'The default is 65527.', 'evidence': 'source line 7613'},
              {'id': 'f2', 'claim': 'Values below 1200 are invalid.', 'evidence': 'source line 7614'}],
}


class Mask(unittest.TestCase):
    def test_paths_tools_and_line_citations_are_masked(self):
        answer = ('Per /var/folders/c1/T/m3home-x/.cache/claude-web/www.rfc-editor.org/rfc-rfc9000-html-1a2b3c4d/20261025T101010123Z-ab12/page.md '
                  'the default is 65527 [L7613] and values below 1200 are invalid [L7614–7615]. '
                  'I used mcp__web__fetch, then WebFetch, then Read on page.md and assets/01.png (lines 7600-7620). '
                  'See ~/.cache/claude-web/x and /Users/new/foo.')
        masked = grade.mask(answer)
        for leak in ('/var/folders', 'claude-web', 'page.md', 'mcp__web__fetch', 'WebFetch', '[L7613]', 'L7614', 'assets/01.png', '7600-7620', '/Users/new'):
            self.assertNotIn(leak, masked, leak)
        self.assertIn('65527', masked)
        self.assertIn('1200', masked)

    def test_file_links_are_masked_whole(self):
        answer = ('The default is 65527 ([page.md#L12](file:///var/folders/c1/T/web-evals-x/home-k4qz/.cache/claude-web/www.rfc-editor.org/rfc-rfc9000-html-46f5fb09/20261025T100131859Z-378b/page.md#L12)), '
                  'see also <file:///private/var/folders/c1/T/home-ab/.cache/claude-web/x/page.md#L7-L9> and '
                  '[the figure](file:///Users/new/.cache/claude-web/a/b/assets/01.png). Values below 1200 are invalid (page.md#L5).')
        masked = grade.mask(answer)
        for leak in ('file:', 'home-k4qz', 'claude-web', 'rfc-rfc9000-html-46f5fb09', '20261025T100131859Z', '#L12', '#L7', '#L5', 'assets/01.png', '/Users/new'):
            self.assertNotIn(leak, masked, leak)
        self.assertIn('65527', masked)
        self.assertIn('1200', masked)

    def test_code_that_says_file_colon_is_not_a_file_uri(self):
        import json
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, 'tasks-reserve.json')) as f:
            key = next(t for t in json.load(f) if t['id'] == 'code-r2')['facts'][0]['claim']
        code = key.split('\n', 1)[1]  # the key's code, as a perfect answer would quote it
        self.assertIn('Line from file: ${line}', code)
        self.assertEqual(grade.mask(code), code)
        cited = code + '\n\nSource: [readline.md#L1337](file:///private/var/folders/c1/T/home-ab/.cache/claude-web/nodejs.org/x/page.md#L1337)'
        masked = grade.mask(cited)
        self.assertIn('Line from file: ${line}', masked)
        for leak in ('file:///', 'home-ab', 'claude-web', '#L1337'):
            self.assertNotIn(leak, masked, leak)

    def test_ordinary_text_is_untouched(self):
        answer = 'The crate lists 11K SLoC (10,663 lines of Rust code) and 75.8 KiB; use `a/b` paths like src/lib.rs.'
        self.assertEqual(grade.mask(answer), answer)


class Prompt(unittest.TestCase):
    def test_the_prompt_holds_question_facts_and_masked_answer(self):
        p = grade.grader_prompt(TASK, 'It is 65527 [L7613].')
        self.assertIn(TASK['question'], p)
        self.assertIn('f1: The default is 65527.', p)
        self.assertIn('f2: Values below 1200 are invalid.', p)
        self.assertIn('It is 65527 [ref].', p)
        self.assertNotIn('source line', p)  # the evidence stays out


class ParseGrade(unittest.TestCase):
    def test_verdict_follows_the_facts(self):
        g = grade.parse_grade('```json\n{"verdict": "correct", "facts": {"f1": true, "f2": false}, "note": "missing f2"}\n```', ['f1', 'f2'])
        self.assertEqual(g, {'verdict': 'partial', 'facts': {'f1': True, 'f2': False}, 'note': 'missing f2'})

    def test_all_and_none(self):
        self.assertEqual(grade.parse_grade('{"verdict":"correct","facts":{"f1":true,"f2":true},"note":""}', ['f1', 'f2'])['verdict'], 'correct')
        self.assertEqual(grade.parse_grade('{"verdict":"partial","facts":{"f1":false,"f2":false},"note":"x"}', ['f1', 'f2'])['verdict'], 'wrong')

    def test_a_fact_left_out_counts_false(self):
        g = grade.parse_grade('Here: {"verdict":"correct","facts":{"f1":true},"note":"ok"}', ['f1', 'f2'])
        self.assertEqual(g['facts'], {'f1': True, 'f2': False})
        self.assertEqual(g['verdict'], 'partial')

    def test_unparseable_is_none(self):
        self.assertIsNone(grade.parse_grade('I think it is correct.', ['f1']))
        self.assertIsNone(grade.parse_grade('{"verdict": "correct", "facts": [true]}', ['f1']))


class Grader(unittest.TestCase):
    def setUp(self):
        import json
        import tempfile
        self.calls, self.work = [], tempfile.mkdtemp()
        reply = json.dumps({'result': '{"verdict":"correct","facts":{"f1":true,"f2":true},"note":""}',
                            'modelUsage': {'sol': {'inputTokens': 9, 'costUSD': 0.01}}, 'total_cost_usd': 0.01})
        self.saved = harness.run_claude, harness.make_home
        harness.run_claude = lambda args, *rest: (self.calls.append(args) or (reply, '', 0, False, 5))
        harness.make_home = lambda parent: tempfile.mkdtemp(dir=parent)

    def tearDown(self):
        harness.run_claude, harness.make_home = self.saved

    def test_sol_at_xhigh_grades_by_default(self):
        g, usage = grade.grade(TASK, 'It is 65527, below 1200 invalid.', self.work)
        args = self.calls[0]
        self.assertEqual(args[args.index('--model') + 1], 'sol')
        self.assertEqual(args[args.index('--effort') + 1], 'xhigh')
        self.assertEqual((usage['model'], usage['effort'], g['verdict']), ('sol', 'xhigh', 'correct'))

    def test_another_grader_runs_at_its_default_effort(self):
        _, usage = grade.grade(TASK, 'It is 65527.', self.work, 'opus')
        self.assertEqual(self.calls[0][self.calls[0].index('--model') + 1], 'opus')
        self.assertNotIn('--effort', self.calls[0])
        self.assertNotIn('effort', usage)


if __name__ == '__main__':
    unittest.main()
