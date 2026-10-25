import http.server
import json
import os
import tempfile
import threading
import unittest

import search_mcp


class FakeGateway(http.server.BaseHTTPRequestHandler):
    seen = []
    reply = {}
    status = 200

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['content-length'])))
        FakeGateway.seen.append({'path': self.path, 'headers': {k.lower(): v for k, v in self.headers.items()}, 'body': body})
        data = json.dumps(FakeGateway.reply).encode()
        self.send_response(FakeGateway.status)
        self.send_header('content-type', 'application/json')
        self.send_header('content-length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


def results(*pairs):
    return {'type': 'web_search_tool_result', 'tool_use_id': 's1',
            'content': [{'type': 'web_search_result', 'title': t, 'url': u, 'encrypted_content': 'x'} for t, u in pairs]}


class Reply(unittest.TestCase):
    def test_links_then_the_cited_text_as_one_passage(self):
        content = [{'type': 'server_tool_use', 'id': 's1', 'name': 'web_search', 'input': {'query': 'q'}},
                   results(('PostgreSQL 16.0 Release Notes', 'https://www.postgresql.org/docs/release/16.0/')),
                   {'type': 'text', 'text': 'The notes list '}, {'type': 'text', 'text': 'pg_stat_io', 'citations': [{}]},
                   {'type': 'text', 'text': ' under Monitoring.'}]
        text = search_mcp.format_reply('pg 16', content)
        self.assertTrue(text.startswith('Web search results for query: "pg 16"\n\nLinks: [{"title": "PostgreSQL 16.0 Release Notes"'))
        self.assertIn('\n\nThe notes list pg_stat_io under Monitoring.\n\n', text)
        self.assertTrue(text.endswith('using markdown hyperlinks.'))

    def test_a_search_error_and_no_results(self):
        content = [{'type': 'web_search_tool_result', 'content': {'type': 'web_search_tool_result_error', 'error_code': 'max_uses_exceeded'}},
                   results()]
        text = search_mcp.format_reply('x', content)
        self.assertIn('Web search error: max_uses_exceeded', text)
        self.assertIn('No links found.', text)

    def test_the_request_is_websearchs(self):
        body = search_mcp.request_body('claude-haiku-5-5', {'query': 'q', 'allowed_domains': ['bok.or.kr'], 'blocked_domains': []})
        self.assertEqual(body['tool_choice'], {'type': 'tool', 'name': 'web_search'})
        self.assertEqual(body['tools'], [{'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': 8, 'allowed_domains': ['bok.or.kr']}])
        self.assertEqual(body['system'][0]['text'], search_mcp.IDENTITY)
        self.assertEqual(body['messages'], [{'role': 'user', 'content': 'Perform a web search for the query: q'}])


class Search(unittest.TestCase):
    def setUp(self):
        self.server = http.server.HTTPServer(('127.0.0.1', 0), FakeGateway)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.home = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.home, '.claude'))
        with open(os.path.join(self.home, '.claude', 'settings.json'), 'w') as f:
            json.dump({'env': {'ANTHROPIC_BASE_URL': f'http://127.0.0.1:{self.server.server_port}/',
                               'ANTHROPIC_AUTH_TOKEN': 'tok', 'ANTHROPIC_DEFAULT_HAIKU_MODEL': 'claude-haiku-5-5[1m]'}}, f)
        FakeGateway.seen, FakeGateway.status = [], 200
        FakeGateway.reply = {'model': 'claude-haiku-5-5', 'usage': {'input_tokens': 12000, 'output_tokens': 300,
                                                                    'server_tool_use': {'web_search_requests': 1}},
                             'content': [results(('T', 'https://t.example/')), {'type': 'text', 'text': 'Summary.'}]}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def call(self, args):
        return search_mcp.handle({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': 'web_search', 'arguments': args}}, self.home)

    def test_a_search_goes_to_the_gateway_as_claude_code_and_is_logged(self):
        res = self.call({'query': 'rust survey 2023'})
        self.assertFalse(res['result']['isError'])
        self.assertIn('Links: [{"title": "T", "url": "https://t.example/"}]', res['result']['content'][0]['text'])
        sent = FakeGateway.seen[0]
        self.assertEqual(sent['path'], '/v1/messages')
        self.assertEqual(sent['headers']['authorization'], 'Bearer tok')
        self.assertEqual(sent['headers']['x-app'], 'cli')
        self.assertEqual(sent['body']['model'], 'claude-haiku-5-5')
        with open(os.path.join(self.home, search_mcp.USAGE_LOG)) as f:
            line = json.loads(f.read())
        self.assertEqual((line['query'], line['usage']['server_tool_use']['web_search_requests']), ('rust survey 2023', 1))

    def test_a_gateway_error_is_an_error_result(self):
        FakeGateway.status, FakeGateway.reply = 429, {'type': 'error', 'error': {'type': 'rate_limit_error'}}
        res = self.call({'query': 'x y'})
        self.assertTrue(res['result']['isError'])
        self.assertIn('HTTP 429', res['result']['content'][0]['text'])

    def test_a_query_too_short_never_reaches_the_gateway(self):
        self.assertTrue(self.call({'query': ' '})['result']['isError'])
        self.assertEqual(FakeGateway.seen, [])


class Protocol(unittest.TestCase):
    def test_initialize_list_and_unknowns(self):
        init = search_mcp.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}}, '/nowhere')
        self.assertEqual(init['result']['protocolVersion'], '2025-06-18')
        self.assertEqual(init['result']['capabilities'], {'tools': {}})
        tools = search_mcp.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}, '/nowhere')['result']['tools']
        self.assertEqual([t['name'] for t in tools], ['web_search'])
        self.assertIsNone(search_mcp.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, '/nowhere'))
        self.assertEqual(search_mcp.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'resources/list'}, '/nowhere')['error']['code'], -32601)
        bad = search_mcp.handle({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'fetch'}}, '/nowhere')
        self.assertEqual(bad['error']['code'], -32602)


if __name__ == '__main__':
    unittest.main()
