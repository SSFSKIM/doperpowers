"""The evals' web search: an MCP server (stdio) with one tool, `web_search`,
given to both configurations of a task that names no URL.

Claude Code's own WebSearch asks the session's model to run the API's
server-side web_search tool, and through the gateway `sol` cannot run it
("API Error: 400 The request contains content this Codex gateway cannot
translate", 2.1.310). This server makes the request WebSearch makes, with the
same system text, the same forced tool and the same reply shape, on haiku,
which the gateway serves. It reads the gateway's address, token and haiku
mapping from $HOME/.claude/settings.json (the run's temporary HOME), and logs
each search's usage to $HOME/.cache/web-evals-search/usage.jsonl.

    python3 -I web/evals/search_mcp.py     # speaks MCP on stdin/stdout
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

# The gateway serves Claude models to Claude Code's requests only: their first system block
# names Claude Code, as every request Claude Code makes does (one without it gets a 429).
IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."
HEADERS = {'user-agent': 'claude-cli/2.1.310 (external, sdk-cli)', 'x-app': 'cli'}
SYSTEM = ('You run a web search for another Claude model, which is waiting on the result and can search again. '
          'Search once, then reply with a brief summary of the results.')
MAX_USES = 8
MAX_TOKENS = 4096
TIMEOUT_S = 120
USAGE_LOG = os.path.join('.cache', 'web-evals-search', 'usage.jsonl')

TOOL = {
    'name': 'web_search',
    'description': ('Searches the web and returns the results: their titles and URLs, and a short summary of what '
                    'they say. Use it to find pages; fetch a page to read it.'),
    'inputSchema': {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'minLength': 2, 'description': 'The search query.'},
            'allowed_domains': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Only include results from these domains.'},
            'blocked_domains': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Never include results from these domains.'},
        },
        'required': ['query'],
    },
}


def gateway(home):
    with open(os.path.join(home, '.claude', 'settings.json')) as f:
        env = json.load(f).get('env', {})
    model = env.get('ANTHROPIC_DEFAULT_HAIKU_MODEL', 'claude-haiku-4-5')
    # A `[1m]` suffix is Claude Code's notation for the 1M window, not part of the model id.
    return env['ANTHROPIC_BASE_URL'].rstrip('/'), env['ANTHROPIC_AUTH_TOKEN'], model.split('[')[0]


def request_body(model, args):
    tool = {'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': MAX_USES}
    for key in ('allowed_domains', 'blocked_domains'):
        if args.get(key):
            tool[key] = args[key]
    return {'model': model, 'max_tokens': MAX_TOKENS,
            'system': [{'type': 'text', 'text': IDENTITY}, {'type': 'text', 'text': SYSTEM}],
            'thinking': {'type': 'disabled'},
            'messages': [{'role': 'user', 'content': 'Perform a web search for the query: ' + args['query']}],
            'tools': [tool], 'tool_choice': {'type': 'tool', 'name': 'web_search'}}


def format_reply(query, content):
    """WebSearch's reply: each search's links as JSON, then the text, in order. The API splits
    cited text into many blocks; a run of text blocks is one passage."""
    parts = [f'Web search results for query: "{query}"', '']
    text = ''
    for block in content:
        kind = block.get('type')
        if kind == 'text':
            text += block.get('text', '')
            continue
        if kind != 'web_search_tool_result':
            continue
        if text.strip():
            parts += [text.strip(), '']
        text = ''
        results = block.get('content')
        if isinstance(results, list):
            links = [{'title': r.get('title', ''), 'url': r.get('url', '')} for r in results if r.get('type') == 'web_search_result']
            parts += [f'Links: {json.dumps(links, ensure_ascii=False)}' if links else 'No links found.', '']
        else:
            parts += [f"Web search error: {(results or {}).get('error_code', 'unknown')}", '']
    if text.strip():
        parts += [text.strip(), '']
    parts.append('REMINDER: You MUST include the sources above in your response to the user using markdown hyperlinks.')
    return '\n'.join(parts)


def search(args, home):
    """(reply text, is_error)."""
    base, token, model = gateway(home)
    body = json.dumps(request_body(model, args)).encode()
    req = urllib.request.Request(base + '/v1/messages', data=body, method='POST', headers={
        'content-type': 'application/json', 'anthropic-version': '2023-06-01', 'authorization': 'Bearer ' + token, **HEADERS})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
            out = json.load(res)
    except urllib.error.HTTPError as e:
        return f'Web search failed: HTTP {e.code}: {e.read()[:300].decode("utf-8", "replace")}', True
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return f'Web search failed: {e}', True
    log_usage(home, {'query': args['query'], 'model': out.get('model', model), 'usage': out.get('usage') or {},
                     'durationMs': round((time.monotonic() - started) * 1000)})
    return format_reply(args['query'], out.get('content') or []), False


_log_lock = threading.Lock()


def log_usage(home, line):
    path = os.path.join(home, USAGE_LOG)
    with _log_lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a') as f:
            f.write(json.dumps(line) + '\n')


def handle(msg, home):
    """The response to one JSON-RPC message, or None for a notification."""
    method, mid = msg.get('method'), msg.get('id')
    if mid is None:
        return None
    if method == 'initialize':
        version = (msg.get('params') or {}).get('protocolVersion', '2025-06-18')
        result = {'protocolVersion': version, 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'web-evals-search', 'version': '1'}}
    elif method == 'ping':
        result = {}
    elif method == 'tools/list':
        result = {'tools': [TOOL]}
    elif method == 'tools/call':
        params = msg.get('params') or {}
        args = params.get('arguments') or {}
        if params.get('name') != TOOL['name']:
            return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32602, 'message': f"unknown tool: {params.get('name')}"}}
        if not isinstance(args.get('query'), str) or len(args['query'].strip()) < 2:
            text, is_error = 'Web search failed: a query of at least 2 characters is required.', True
        else:
            text, is_error = search(args, home)
        result = {'content': [{'type': 'text', 'text': text}], 'isError': is_error}
    else:
        return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32601, 'message': f'method not found: {method}'}}
    return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def main():
    home = os.environ['HOME']
    out_lock = threading.Lock()

    def answer(msg):
        res = handle(msg, home)
        if res is not None:
            with out_lock:
                sys.stdout.write(json.dumps(res) + '\n')
                sys.stdout.flush()

    calls = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        # A search takes seconds; calls made together are answered as they finish.
        if msg.get('method') == 'tools/call':
            calls.append(threading.Thread(target=answer, args=(msg,)))
            calls[-1].start()
        else:
            answer(msg)
    for t in calls:
        t.join()


if __name__ == '__main__':
    main()
