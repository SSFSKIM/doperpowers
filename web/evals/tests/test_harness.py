import json
import os
import stat
import tempfile
import unittest

import harness
from tests import streams as s


class ParseStream(unittest.TestCase):
    def test_b_run_measures(self):
        text = s.stream(
            s.init(),
            s.tool_use('t1', 'mcp__web__fetch', {'url': 'https://example.com/'}),
            s.tool_result('t1', 'Saved /tmp/x/page.md\n...'),
            s.tool_use('t2', 'Read', {'file_path': '/tmp/x/page.md'}),
            s.tool_result('t2', '1\t---'),
            s.tool_use('t3', 'mcp__web__fetch', {'url': 'https://example.com/missing'}),
            s.tool_result('t3', '<tool_use_error>fetch failed: https://example.com/missing: HTTP 404 Not Found</tool_use_error>', True),
            s.text('The answer is 42.'),
            s.result('The answer is 42.', {'sol': s.model_usage(1000, 200, 5000, 300, 0.25)}, turns=4, duration=31000, cost=0.25),
        )
        run = harness.parse_stream(text, 'B')
        self.assertEqual(run['finalText'], 'The answer is 42.')
        self.assertEqual(run['mainTokens'], {'input': 1000, 'output': 200, 'cacheRead': 5000, 'cacheCreation': 300})
        self.assertEqual(run['fetchCalls'], 2)
        self.assertEqual(run['fetchErrors'], [{'text': 'fetch failed: https://example.com/missing: HTTP 404 Not Found', 'toolCaused': False}])
        self.assertEqual((run['turns'], run['durationMs'], run['costUsd']), (4, 31000, 0.25))
        self.assertEqual(run['initModel'], 'sol')

    def test_a_run_main_tokens_are_the_runner_models_only(self):
        text = s.stream(
            s.init(tools=('Read', 'WebFetch')),
            s.tool_use('t1', 'WebFetch', {'url': 'https://example.com/', 'prompt': 'what?'}),
            s.tool_result('t1', [{'type': 'text', 'text': 'It says 42.'}]),
            s.result('42', {'sol': s.model_usage(800, 100), 'claude-haiku-5-5[1m]': s.model_usage(9000, 300, cost=0.01)}),
        )
        run = harness.parse_stream(text, 'A')
        self.assertEqual(run['mainTokens'], {'input': 800, 'output': 100, 'cacheRead': 0, 'cacheCreation': 0})
        self.assertEqual(sorted(run['usageByModel']), ['claude-haiku-5-5[1m]', 'sol'])
        self.assertEqual(run['fetchCalls'], 1)
        self.assertEqual(run['fetchErrors'], [])

    def test_a_counts_webfetch_not_the_web_tool(self):
        text = s.stream(s.init(), s.tool_use('t1', 'mcp__web__fetch', {}), s.result('x', {}))
        self.assertEqual(harness.parse_stream(text, 'A')['fetchCalls'], 0)

    def test_a_run_cut_off_before_its_result(self):
        text = s.stream(
            s.init(),
            s.tool_use('t1', 'mcp__web__fetch', {'url': 'https://slow.example/'}),
        )
        run = harness.parse_stream(text, 'B', timed_out=True, wall_ms=600_412)
        self.assertEqual(run['finalText'], '')
        # Without a result line the usage cannot be known: unavailable, never zero.
        self.assertIsNone(run['mainTokens'])
        self.assertIsNone(run['usageByModel'])
        self.assertIsNone(run['costUsd'])
        self.assertEqual(run['durationMs'], 600_412)
        self.assertEqual(run['turns'], 1)  # one assistant message; equal to num_turns in every pilot run
        self.assertEqual(run['fetchErrors'], [{'text': 'the run hit its time limit with a fetch call unanswered', 'toolCaused': True}])

    def test_an_interrupted_run_keeps_the_usage_of_its_result_line(self):
        # SIGINT at the limit makes `claude -p` write a result line (subtype error_during_execution) with its usage.
        text = s.stream(
            s.init(),
            s.tool_use('t1', 'Read', {}),
            s.tool_result('t1', 'x'),
            s.text('partial notes'),
            {**s.result('', {'sol': s.model_usage(12058, 997, 28416)}, turns=8, duration=39549, cost=0.07), 'subtype': 'error_during_execution', 'is_error': True},
        )
        run = harness.parse_stream(text, 'B', timed_out=True, wall_ms=600_100)
        self.assertEqual(run['mainTokens'], {'input': 12058, 'output': 997, 'cacheRead': 28416, 'cacheCreation': 0})
        self.assertEqual(run['costUsd'], 0.07)
        self.assertEqual(run['durationMs'], 600_100)  # the wall time to the limit, not the engine's own figure
        self.assertEqual(run['finalText'], 'partial notes')

    def test_a_finished_run_keeps_the_engines_duration(self):
        text = s.stream(s.result('ok', {'sol': s.model_usage(1, 2)}, duration=31000))
        self.assertEqual(harness.parse_stream(text, 'B', wall_ms=33000)['durationMs'], 31000)

    def test_a_cut_off_run_without_a_pending_fetch_adds_no_tool_error(self):
        text = s.stream(s.init(), s.tool_use('t1', 'mcp__web__fetch', {}), s.tool_result('t1', 'Saved'), s.text('thinking aloud'))
        run = harness.parse_stream(text, 'B', timed_out=True)
        self.assertEqual(run['fetchErrors'], [])
        self.assertEqual(run['finalText'], 'thinking aloud')

    def test_garbage_lines_are_skipped(self):
        text = 'not json\n' + s.stream(s.result('ok', {'sol': s.model_usage(1, 2)}))
        self.assertEqual(harness.parse_stream(text, 'B')['finalText'], 'ok')


FAKE_CLAUDE = r'''
import json, signal, sys, time
def stop(*_):
    print(json.dumps({"type": "result", "subtype": "error_during_execution", "result": "", "modelUsage": {"sol": {"inputTokens": 5}}}), flush=True)
    sys.exit(0)
signal.signal(signal.SIGINT, stop)
print(json.dumps({"type": "system", "subtype": "init"}), flush=True)
time.sleep(60)
'''

DEAF_CLAUDE = r'''
import signal, time
signal.signal(signal.SIGINT, signal.SIG_IGN)
print("started", flush=True)
time.sleep(60)
'''


class RunClaude(unittest.TestCase):
    def test_the_limit_interrupts_so_the_result_line_is_written(self):
        import sys
        out, err, rc, timed_out, wall_ms = harness.run_claude([sys.executable, '-c', FAKE_CLAUDE], tempfile.gettempdir(), None, 1)
        self.assertTrue(timed_out)
        self.assertIn('"type": "result"', out)
        self.assertGreaterEqual(wall_ms, 1000)
        self.assertLess(wall_ms, 10_000)

    def test_a_process_deaf_to_the_interrupt_is_killed(self):
        import sys
        out, err, rc, timed_out, wall_ms = harness.run_claude([sys.executable, '-c', DEAF_CLAUDE], tempfile.gettempdir(), None, 1, grace_s=1)
        self.assertTrue(timed_out)
        self.assertEqual(out, 'started\n')
        self.assertLess(wall_ms, 10_000)

    def test_a_run_inside_its_limit(self):
        import sys
        out, err, rc, timed_out, wall_ms = harness.run_claude([sys.executable, '-c', 'print("hi")'], tempfile.gettempdir(), None, 30)
        self.assertEqual((out, rc, timed_out), ('hi\n', 0, False))


class ClassifyFetchError(unittest.TestCase):
    def test_b_site_errors(self):
        for reason in ('HTTP 403 Forbidden', 'network error: getaddrinfo ENOTFOUND x', 'refused: x resolves to a non-public address (10.0.0.1); for a local server use curl through Bash',
                       'too many redirects (more than 10)', 'too large: over 50 MB', 'invalid URL: x', 'unsupported scheme: ftp: (http and https only)'):
            self.assertFalse(harness.is_tool_caused('B', f'fetch failed: https://x.example/: {reason}'), reason)

    def test_b_tool_errors(self):
        for reason in ('the clipper failed (exit 1), a bug in the web plugin: TypeError', "the clipper's result could not be read: {",
                       'the clipper did not finish within 180 s and was stopped', 'the web plugin failed (throw: boom)',
                       'timed out after 30 s', 'the saved page could not be read: EACCES'):
            self.assertTrue(harness.is_tool_caused('B', f'fetch failed: https://x.example/: {reason}'), reason)

    def test_a_status_errors_are_the_sites(self):
        self.assertFalse(harness.is_tool_caused('A', 'Request failed with status code 404'))
        self.assertTrue(harness.is_tool_caused('A', 'Claude Code is unable to fetch from example.com'))


class Home(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.settings = os.path.join(self.dir, 'settings.json')
        env = {k: 'v-' + k for k in harness.GATEWAY_KEYS}
        env.update({'CLAUDE_CODE_PLUGIN_DIRS': '/somewhere', 'PLAYWRIGHT_MCP_EXTENSION_TOKEN': 'secret'})
        with open(self.settings, 'w') as f:
            json.dump({'env': env, 'hooks': {'x': 1}, 'enabledPlugins': {'a@b': True}}, f)

    def test_only_the_gateway_keys_are_copied(self):
        home = harness.make_home(self.dir, self.settings)
        path = os.path.join(home, '.claude', 'settings.json')
        with open(path) as f:
            written = json.load(f)
        self.assertEqual(written, {'env': {k: 'v-' + k for k in harness.GATEWAY_KEYS}})
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_the_run_env_is_built_clean(self):
        env = harness.run_env('/tmp/h', parent={'PATH': '/bin', 'ANTHROPIC_AUTH_TOKEN': 't', 'CLAUDECODE': '1', 'USER': 'me', 'TMPDIR': '/t/'})
        self.assertEqual(env['HOME'], '/tmp/h')
        self.assertEqual(env['PATH'], '/bin')
        self.assertEqual(env['CLAUDE_CODE_ENABLE_FUNCTION_HOOKS'], '1')
        self.assertIn('PLAYWRIGHT_BROWSERS_PATH', env)
        self.assertNotIn('ANTHROPIC_AUTH_TOKEN', env)
        self.assertNotIn('CLAUDECODE', env)


class Arguments(unittest.TestCase):
    def test_configurations(self):
        a = harness.runner_args('A', '/w/web', 'Q?')
        b = harness.runner_args('B', '/w/web', 'Q?')
        for args in (a, b):
            self.assertEqual(args[:2], ['claude', '-p'])
            self.assertIn('--plugin-dir', args)
            self.assertEqual(args[args.index('--model') + 1], 'sol')
            self.assertEqual(args[args.index('--effort') + 1], 'xhigh')
            self.assertEqual(args[-2:], ['--', 'Q?'])
        self.assertEqual(a[a.index('--tools') + 1], 'Read,Grep,Glob,ToolSearch,WebFetch')
        self.assertEqual(a[a.index('--disallowedTools') + 1], 'mcp__web__fetch')
        self.assertEqual(b[b.index('--tools') + 1], 'Read,Grep,Glob,ToolSearch')
        self.assertEqual(b[b.index('--disallowedTools') + 1], 'WebFetch')
        self.assertIn('mcp__web__fetch', b[b.index('--allowedTools') + 1])
        self.assertIn('WebFetch', a[a.index('--allowedTools') + 1])


if __name__ == '__main__':
    unittest.main()
