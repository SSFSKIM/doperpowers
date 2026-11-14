#!/usr/bin/env python3
"""The present replay's logic on a made-up transcript: no model call.

    python3 tests/output-styles/test-present-eval.py

It checks that `wire_replay.rebuild` puts a request back together from the
transcript's request records, blobs and rows (a string prompt sent as one
text block, a response's rows merged with its tool inputs as sent, a
tool-result message no single row matches, a reply made up without a
request, a later request's keep), and how far it falls back when a hash
matches nothing; and that the eval's `apply_arm` replaces the style without
the text the engine adds after it, puts the CLAUDE.md line in each copy's
Reporting section, and offers the present tool beside the message tool.
"""
import importlib.util, json, os, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wire_replay  # noqa: E402
from wire_replay import digest  # noqa: E402

spec = importlib.util.spec_from_file_location('present_eval', HERE / 'to-human-present-eval.py')
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

SHAPE = {'system': [{'type': 'text', 'text': "You are Claude Code, Anthropic's official CLI for Claude."}],
         'tools': [{'name': 'Bash'}, {'name': 'mcp__to-human__message'}, {'name': 'Read'}]}
PARAMS = {'model': 'claude-opus-5-5', 'max_tokens': 1000, 'output_config': {'effort': 'xhigh'}}


def line(obj):
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)


def transcript(rows):
    f = tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False)
    for r in rows:
        f.write(line(r) + '\n')
    f.close()
    return f.name


def request(rid, base, keep, tail):
    return {'type': 'api-request', 'id': rid, 'params': PARAMS, 'shapeHash': '5' * 64, 'base': base, 'keep': keep,
            'tail': [digest(m) for m in tail], 'cacheControl': [{'path': ['messages', 0, 'content', 0], 'value': {'type': 'ephemeral'}}]}


def assistant(ref, mid, index, block, wire=None):
    r = {'parentUuid': None, 'type': 'assistant', 'requestRef': ref, 'apiBlockIndex': index,
         'message': {'id': mid, 'role': 'assistant', 'content': [block]}}
    if wire:
        r['wireToolInputs'] = wire
    return r


def user(content):
    return {'parentUuid': None, 'type': 'user', 'message': {'role': 'user', 'content': content}}


class Rebuild(unittest.TestCase):
    def setUp(self):
        prompt = {'role': 'user', 'content': [{'type': 'text', 'text': 'Clean up the repo.'}]}
        thinking = {'type': 'thinking', 'thinking': '', 'signature': 'sig'}
        t1 = {'type': 'tool_use', 'id': 'toolu_1', 'name': 'Bash', 'input': {'command': 'ls'}}
        t2 = {'type': 'tool_use', 'id': 'toolu_2', 'name': 'Read', 'input': {'file_path': '/x'}}
        sent_t1 = dict(t1, input={'command': 'cd /repo && ls'})  # the wire form a hook rewrote
        response = {'role': 'assistant', 'content': [thinking, sent_t1, t2]}
        r1 = [{'type': 'tool_result', 'tool_use_id': 'toolu_1', 'content': 'a b'}]
        r2 = [{'type': 'tool_result', 'tool_use_id': 'toolu_2', 'content': 'x'}]
        results = {'role': 'user', 'content': r1 + r2}  # one message, two rows
        style = {'role': 'system', 'content': [{'type': 'text', 'text': 'the style is active'}]}
        made_up = {'role': 'assistant', 'content': [{'type': 'text', 'text': 'Message sent to the human.'}]}
        later = {'role': 'user', 'content': [{'type': 'text', 'text': 'And the tests?'}]}
        self.expected = [prompt, response, results, style, made_up, later]
        self.rows = [
            {'type': 'api-request-shape', 'shapeHash': '5' * 64, 'shape': SHAPE},
            user('Clean up the repo.'),
            request('A', None, 0, [prompt]),
            assistant('A', 'msg_1', 0, thinking),
            assistant('A', 'msg_1', 1, t1, {'toolu_1': sent_t1['input']}),
            assistant('A', 'msg_1', 2, t2),
            user(r1), user(r2),
            {'type': 'api-request-blob', 'hash': digest(style), 'message': style},
            request('B', 'A', 1, [response, results, style]),
            {'parentUuid': None, 'type': 'assistant', 'answeredWithoutRequest': True, 'message': {'id': 'msg_hook_1', 'role': 'assistant', 'content': made_up['content']}},
            user('And the tests?'),
            request('C', 'B', 4, [made_up, later]),
        ]

    def test_the_request_as_it_was_sent(self):
        req, approx = wire_replay.rebuild(transcript(self.rows), 'C')
        self.assertEqual(approx, 0)
        got = json.loads(json.dumps(req['messages']))
        got[0]['content'][0].pop('cache_control')
        self.assertEqual(got, self.expected)
        self.assertEqual(req['messages'][0]['content'][0]['cache_control'], {'type': 'ephemeral'})
        self.assertEqual((req['model'], req['output_config'], req['tools']), (PARAMS['model'], PARAMS['output_config'], SHAPE['tools']))

    def test_a_response_no_row_matches_is_taken_from_the_rows_of_the_request_that_made_it(self):
        rows = [dict(r, wireToolInputs={}) if r.get('wireToolInputs') else r for r in self.rows]  # the wire form is lost
        req, approx = wire_replay.rebuild(transcript(rows), 'C')
        self.assertEqual(approx, 1)
        self.assertEqual(req['messages'][1]['content'][1]['input'], {'command': 'ls'})
        self.assertEqual(req['messages'][2], self.expected[2])

    def test_results_sent_in_another_order_than_the_calls_are_matched(self):
        # Parallel calls' results go on the wire as they arrived, not in the
        # calls' order.
        flipped = {'role': 'user', 'content': self.expected[2]['content'][::-1]}
        rows = [request('B', 'A', 1, [self.expected[1], flipped, self.expected[3]]) if r.get('id') == 'B' else r for r in self.rows]
        rows = [request('C', 'B', 4, [self.expected[4], self.expected[5]]) if r.get('id') == 'C' else r for r in rows]
        req, approx = wire_replay.rebuild(transcript(rows), 'C')
        self.assertEqual((approx, req['messages'][2]), (0, flipped))

    def test_a_skill_result_carries_the_skill_body_that_follows_it(self):
        # The engine sends a Skill call's result and the skill's body (a meta
        # row of its own in the transcript) as one message.
        prompt = {'role': 'user', 'content': [{'type': 'text', 'text': 'Design it.'}]}
        call = {'type': 'tool_use', 'id': 'toolu_9', 'name': 'Skill', 'input': {'skill': 'brainstorming'}}
        result = [{'type': 'tool_result', 'tool_use_id': 'toolu_9', 'content': 'Launching skill: brainstorming'}]
        body = [{'type': 'text', 'text': 'Base directory for this skill: /s\n\n# Brainstorming'}]
        sent = {'role': 'user', 'content': result + body}
        rows = [
            {'type': 'api-request-shape', 'shapeHash': '5' * 64, 'shape': SHAPE},
            user('Design it.'),
            request('A', None, 0, [prompt]),
            assistant('A', 'msg_1', 0, call),
            user(result),
            dict(user(body), isMeta=True),
            request('B', 'A', 1, [{'role': 'assistant', 'content': [call]}, sent]),
        ]
        req, approx = wire_replay.rebuild(transcript(rows), 'B')
        self.assertEqual((approx, req['messages'][2]), (0, sent))

    def test_a_kept_prefix_needs_nothing_past_it(self):
        # D keeps C's first message only (as after a rewind): the style's blob,
        # past that prefix, is not needed, so its absence is no error.
        rows = [r for r in self.rows if r.get('type') != 'api-request-blob']
        rows.append(request('D', 'C', 1, [self.expected[5]]))
        req, approx = wire_replay.rebuild(transcript(rows), 'D')
        req['messages'][0]['content'][0].pop('cache_control')
        self.assertEqual((req['messages'], approx), ([self.expected[0], self.expected[5]], 0))


class ApplyArm(unittest.TestCase):
    def request(self):
        old_style = ev.STYLE_HEAD + 'An old style.\n\n## Insights\nbut ' + ev.STYLE_END
        claude = ('Contents of %s (user\'s private global instructions for all projects):\n\n# CLAUDE.md\n\n'
                  '### Reporting\n\nWorking updates may be terse.\n\n### Delegation and context\n\nDelegate.\n' % ev.CLAUDE_HEAD[len('Contents of '):])
        return {'tools': [{'name': 'Bash'}, {'name': 'mcp__to-human__message'}, {'name': 'Read'}],
                'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': claude}]},
                             {'role': 'system', 'content': [{'type': 'text', 'text': 'Env.\n\n' + old_style + "\n\nToday's date is 2026-11-01."}]},
                             {'role': 'user', 'content': 'Re-read:\n' + claude}]}

    def test_the_arm_lands_in_each_place(self):
        req = self.request()
        styles, claudes = ev.apply_arm(req, 'The new style.\nIt ends: ' + ev.STYLE_END, 'THE RULE LINE\n')
        self.assertEqual((styles, claudes), (1, 2))
        self.assertEqual(req['messages'][1]['content'][0]['text'],
                         'Env.\n\n' + ev.STYLE_HEAD + 'The new style.\nIt ends: ' + ev.STYLE_END + "\n\nToday's date is 2026-11-01.")
        for m in (req['messages'][0], req['messages'][2]):
            self.assertIn('Working updates may be terse.\n\nTHE RULE LINE\n\n### Delegation and context', m['content'][0]['text'])
        self.assertEqual([t['name'] for t in req['tools']], ['Bash', 'mcp__to-human__message', 'mcp__to-human__present', 'Read'])
        self.assertEqual(req['tools'][2]['input_schema']['required'], ['brief'])

    def test_a_control_arm_leaves_claude_md_as_it_was(self):
        req = self.request()
        before = req['messages'][0]['content'][0]['text']
        self.assertEqual(ev.apply_arm(req, 'S ' + ev.STYLE_END, ''), (1, 0))
        self.assertEqual(req['messages'][0]['content'][0]['text'], before)

    def test_a_style_cut_short_is_an_error(self):
        req = self.request()
        req['messages'][1]['content'][0]['text'] = ev.STYLE_HEAD + 'no last sentence'
        with self.assertRaises(ValueError):
            ev.apply_arm(req, 'S', '')


class RunOnce(unittest.TestCase):
    def run_with(self, responses, max_steps=4):
        sent = []

        def fake_send(client, req):
            sent.append(req['messages'])
            blocks = responses[len(sent) - 1]
            raw = [dict(b, type='tool_use') for b in blocks]
            return {'stop': 'tool_use', 'blocks': [dict(b, type='tool_use') for b in blocks], 'raw': raw, 'usage': {}}

        real, ev.send = ev.send, fake_send
        try:
            return ev.run_once(None, {'messages': [{'role': 'user', 'content': 'go'}]}, max_steps), sent
        finally:
            ev.send = real

    def test_a_check_is_answered_as_not_run_and_the_run_goes_on_to_the_report(self):
        got, sent = self.run_with([[{'id': 't1', 'name': 'Bash', 'input': {}}],
                                   [{'id': 't2', 'name': ev.PRESENT_TOOL, 'input': {'brief': 'b'}}]])
        self.assertEqual((got['present'], got['message'], got['undecided'], got['others']), (True, False, False, ['Bash']))
        self.assertEqual(len(sent), 2)
        answer = sent[1][-1]['content'][0]
        self.assertEqual((answer['tool_use_id'], answer['is_error'], answer['content']), ('t1', True, ev.NOT_RUN))

    def test_a_run_still_checking_at_its_last_step_is_undecided(self):
        got, sent = self.run_with([[{'id': 't%d' % i, 'name': 'Read', 'input': {}}] for i in range(2)], max_steps=2)
        self.assertEqual((got['present'], got['undecided'], len(sent)), (False, True, 2))

    def test_a_plan_spent_by_another_worker_stops_the_run_before_its_next_request(self):
        sent = []

        def fake_send(client, req):
            sent.append(1)
            ev.SPENT.set()  # another worker's request was refused meanwhile
            b = {'type': 'tool_use', 'id': 't1', 'name': 'Bash', 'input': {}}
            return {'stop': 'tool_use', 'blocks': [b], 'raw': [b], 'usage': {}}

        real, ev.send = ev.send, fake_send
        try:
            with self.assertRaises(ev.PlanSpent):
                ev.run_once(None, {'messages': []}, 4)
        finally:
            ev.send = real
            ev.SPENT.clear()
        self.assertEqual(len(sent), 1)

    def test_a_message_ends_the_run(self):
        got, sent = self.run_with([[{'id': 't1', 'name': ev.MESSAGE_TOOL, 'input': {'text': 'x'}}], []])
        self.assertEqual((got['message'], got['present'], got['undecided'], len(sent)), (True, False, False, 1))


class Turn(unittest.TestCase):
    def test_a_spent_plan_skips_the_turn_and_is_no_run(self):
        calls = []

        def spent(client, req, max_steps):
            calls.append(1)
            raise RuntimeError("Error code: 429 - This account is out of plan usage until 2026-11-14T15:00:00Z.")

        saved = ev.run_once, ev.wire_replay.rebuild, ev.apply_arm
        ev.run_once, ev.wire_replay.rebuild, ev.apply_arm = spent, (lambda path, rid: ({'model': 'm', 'tools': []}, 0)), (lambda *a: (1, 1))
        try:
            out = ev.run_turn(None, ev.TURNS[0], 'rule', 's', 'l', [0, 1, 2], False)
        finally:
            ev.run_once, ev.wire_replay.rebuild, ev.apply_arm = saved
        self.assertTrue(ev.SPENT.is_set())
        ev.SPENT.clear()
        self.assertEqual((len(calls), len(out), 'skipped' in out[0], 'rep' in out[0]), (1, 1, True, False))
        self.assertEqual(ev.tally(out), {})

    def test_after_a_spent_plan_a_resume_runs_only_the_repetitions_not_yet_run(self):
        ran = []

        def once(client, req, max_steps):
            ran.append(1)
            if len(ran) == 2:
                raise RuntimeError('Error code: 429 - This account is out of plan usage until 2026-11-14T15:00:00Z.')
            return {'steps': [{}], 'reached_at': 1, 'present': False, 'message': True, 'undecided': False, 'others': []}

        turn = ev.TURNS[0]
        saved = ev.run_once, ev.wire_replay.rebuild, ev.apply_arm
        ev.run_once, ev.wire_replay.rebuild, ev.apply_arm = once, (lambda path, rid: ({'model': 'm', 'tools': []}, 0)), (lambda *a: (1, 1))
        try:
            first = ev.run_turn(None, turn, 'rule', 's', 'l', [0, 1, 2], False)
            self.assertTrue(ev.SPENT.is_set())
            ev.SPENT.clear()  # the plan is renewed; a new process resumes
            todo = ev.pending(first, [turn], ['rule'], 3)
            self.assertEqual(todo, {(turn[0], 'rule'): [1, 2]})
            second = ev.run_turn(None, turn, 'rule', 's', 'l', todo[(turn[0], 'rule')], False)
        finally:
            ev.run_once, ev.wire_replay.rebuild, ev.apply_arm = saved
            ev.SPENT.clear()
        self.assertEqual([x['rep'] for x in first + second if 'rep' in x], [0, 1, 2])
        self.assertEqual(ev.pending(first + second, [turn], ['rule'], 3), {})

    def test_the_tally_counts_where_each_run_reached_the_human(self):
        runs = [dict(turn='w1', arm='a', **{'class': 'warranted'}, rep=i, present=p, undecided=u, reached_at=at)
                for i, (p, u, at) in enumerate([(True, False, 1), (False, False, 2), (False, True, None)])]
        c = ev.tally(runs)[('a', 'warranted')]
        self.assertEqual((c['runs'], c['present'], c['reached_at']), (3, 1, {1: 1, 2: 1, 'never': 1}))

    def test_a_run_from_before_reached_at_counts_at_its_last_step(self):
        runs = [dict(turn='w1', arm='a', **{'class': 'warranted'}, rep=i, present=False, undecided=u, steps=[{}] * n)
                for i, (u, n) in enumerate([(False, 2), (True, 4)])]
        self.assertEqual(ev.tally(runs)[('a', 'warranted')]['reached_at'], {2: 1, 'never': 1})


if __name__ == '__main__':
    unittest.main()
