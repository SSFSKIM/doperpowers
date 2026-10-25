import json
import subprocess
import sys
import unittest

import deny_readers
import harness


def hook(event):
    p = subprocess.run([sys.executable, '-I', deny_readers.__file__], input=json.dumps(event), capture_output=True, text=True, timeout=30)
    return p.returncode, p.stderr


class Refused(unittest.TestCase):
    def test_the_readers_and_proxies_the_screening_met(self):
        for url, reader in (
            ('https://r.jina.ai/https://hothardware.com/reviews/x?page=2', 'r.jina.ai'),
            ('https://wsrv.nl/?url=https%3A%2F%2Fwww.nasa.gov%2Fa.pdf&page=750&output=png', 'wsrv.nl'),
            ('https://images.weserv.nl/?url=x', 'images.weserv.nl'),
            ('https://docs.google.com/gview?embedded=1&url=https%3A%2F%2Fx%2Fa.pdf', 'docs.google.com/gview'),
            ('https://docs.google.com/viewerng/thumb?ds=x', 'docs.google.com/viewerng'),
            ('https://www-nasa-gov.translate.goog/a.pdf?_x_tr_sl=en', 'translate.goog'),
            ('https://web.archive.org/web/2024/https://x/', 'archive.org'),
            ('http://archive.org/details/x', 'archive.org'),
        ):
            self.assertEqual(deny_readers.refused(url), reader, url)

    def test_the_pages_themselves_pass(self):
        for url in ('https://www.nasa.gov/wp-content/uploads/2024/04/a.pdf', 'https://docs.google.com/document/d/x/edit',
                    'https://notarchive.org/', 'https://jina.ai/reader', 'https://example.com/r.jina.ai', '', None):
            self.assertIsNone(deny_readers.refused(url), url)


class Hook(unittest.TestCase):
    def test_either_fetch_tool_is_refused_with_the_reason(self):
        for tool in ('WebFetch', 'mcp__web__fetch'):
            rc, err = hook({'hook_event_name': 'PreToolUse', 'tool_name': tool,
                            'tool_input': {'url': 'https://r.jina.ai/https://x.example/', 'prompt': 'p'}})
            self.assertEqual(rc, 2, tool)
            self.assertIn('Refused: r.jina.ai is a third-party reader or proxy', err)

    def test_other_tools_and_other_urls_pass(self):
        self.assertEqual(hook({'tool_name': 'WebFetch', 'tool_input': {'url': 'https://x.example/'}})[0], 0)
        self.assertEqual(hook({'tool_name': 'Read', 'tool_input': {'file_path': '/tmp/r.jina.ai'}})[0], 0)
        self.assertEqual(hook({'tool_name': 'mcp__search__web_search', 'tool_input': {'query': 'r.jina.ai'}})[0], 0)

    def test_both_configurations_load_the_plugin_ahead_of_the_web_plugin(self):
        for arm in ('A', 'B'):
            args = harness.runner_args(arm, '/w/web', 'Q?')
            dirs = [args[i + 1] for i, a in enumerate(args) if a == '--plugin-dir']
            self.assertEqual(dirs, [harness.DENY_PLUGIN, '/w/web'])

    def test_the_mod_asks_this_script(self):
        import os
        with open(os.path.join(harness.DENY_PLUGIN, 'hooks', 'mods', 'register.tsx')) as f:
            mod = f.read()
        self.assertIn('/../deny_readers.py', mod)
        self.assertEqual(os.path.realpath(os.path.join(harness.DENY_PLUGIN, '..', 'deny_readers.py')), os.path.realpath(harness.DENY_READERS))

    def test_a_refusal_is_not_a_tool_error(self):
        _, err = hook({'tool_name': 'mcp__web__fetch', 'tool_input': {'url': 'https://wsrv.nl/?url=x'}})
        for arm in ('A', 'B'):
            self.assertFalse(harness.is_tool_caused(arm, err.strip()), arm)


if __name__ == '__main__':
    unittest.main()
