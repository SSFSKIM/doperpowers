import unittest

import grade

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


if __name__ == '__main__':
    unittest.main()
