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
        run = harness.parse_stream(text, 'B', timed_out=True)
        self.assertEqual(run['finalText'], '')
        self.assertEqual(run['mainTokens'], {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheCreation': 0})
        self.assertEqual(run['fetchErrors'], [{'text': 'the run hit its time limit with a fetch call unanswered', 'toolCaused': True}])

    def test_a_cut_off_run_without_a_pending_fetch_adds_no_tool_error(self):
        text = s.stream(s.init(), s.tool_use('t1', 'mcp__web__fetch', {}), s.tool_result('t1', 'Saved'), s.text('thinking aloud'))
        run = harness.parse_stream(text, 'B', timed_out=True)
        self.assertEqual(run['fetchErrors'], [])
        self.assertEqual(run['finalText'], 'thinking aloud')

    def test_garbage_lines_are_skipped(self):
        text = 'not json\n' + s.stream(s.result('ok', {'sol': s.model_usage(1, 2)}))
        self.assertEqual(harness.parse_stream(text, 'B')['finalText'], 'ok')


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
