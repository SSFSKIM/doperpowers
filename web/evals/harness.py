"""What every eval process shares: the temporary HOME with the gateway's keys,
the clean environment, the `claude -p` invocation of each configuration, and
the measures read out of a run's stream-json.

The gateway's token is copied from the person's settings file into the
temporary one, file to file. Nothing here prints it or any other key's value.
"""

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

RUNNER_MODEL = 'sol'
RUNNER_EFFORT = 'xhigh'
# Runs per configuration and task: a development round, and the final run.
REPS = {'dev': 2, 'final': 4}

# The keys the gateway needs, copied from the env of ~/.claude/settings.json and nothing else.
GATEWAY_KEYS = (
    'ANTHROPIC_BASE_URL',
    'ANTHROPIC_AUTH_TOKEN',
    'ANTHROPIC_DEFAULT_FABLE_MODEL',
    'ANTHROPIC_DEFAULT_HAIKU_MODEL',
    'ANTHROPIC_DEFAULT_OPUS_MODEL',
    'ANTHROPIC_DEFAULT_SONNET_MODEL',
    'CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY',
    'CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING',
    'ENABLE_TOOL_SEARCH',
    'CLAUDE_STREAM_IDLE_TIMEOUT_MS',
    'CLAUDE_BYTE_STREAM_IDLE_TIMEOUT_MS',
)

PERSON_SETTINGS = os.path.expanduser('~/.claude/settings.json')
WEB_PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FETCH_TOOL = {'A': 'WebFetch', 'B': 'mcp__web__fetch'}
# Both configurations get the file tools and ToolSearch (WebFetch is a deferred
# tool in these sessions, as in the person's); Bash, WebSearch and Agent are
# left out of both, so neither can route around its fetch tool.
BASE_TOOLS = ('Read', 'Grep', 'Glob', 'ToolSearch')
# A task that names no URL (`"search": true`) gives both configurations the same
# search tool: search_mcp.py, since the built-in WebSearch fails on sol through the gateway.
SEARCH_SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'search_mcp.py')
SEARCH_TOOL = 'mcp__search__web_search'
SEARCH_USAGE = os.path.join('.cache', 'web-evals-search', 'usage.jsonl')


def playwright_cache():
    if os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
        return os.environ['PLAYWRIGHT_BROWSERS_PATH']
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Caches/ms-playwright')
    return os.path.expanduser('~/.cache/ms-playwright')


def make_home(parent, settings_path=PERSON_SETTINGS):
    """A new temporary HOME under `parent` whose settings hold only the gateway's keys."""
    with open(settings_path) as f:
        source = json.load(f).get('env', {})
    home = tempfile.mkdtemp(prefix='home-', dir=parent)
    os.makedirs(os.path.join(home, '.claude'))
    path = os.path.join(home, '.claude', 'settings.json')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump({'env': {k: source[k] for k in GATEWAY_KEYS if k in source}}, f)
    return home


def run_env(home, parent=None):
    """The environment of a run, built from nothing, so the parent session's variables do not bleed in."""
    parent = os.environ if parent is None else parent
    env = {k: parent[k] for k in ('PATH', 'USER', 'LOGNAME', 'TMPDIR') if k in parent}
    env.update({
        'HOME': home,
        'SHELL': '/bin/sh',
        'LANG': 'en_US.UTF-8',
        'CLAUDE_CODE_ENABLE_FUNCTION_HOOKS': '1',
        'PLAYWRIGHT_BROWSERS_PATH': playwright_cache(),
    })
    return env


def runner_args(arm, plugin_dir, question, search=False):
    """`claude -p` for one configuration: A has WebFetch only, B has mcp__web__fetch only;
    with `search`, both also have the search tool."""
    fetch, other = FETCH_TOOL[arm], FETCH_TOOL['B' if arm == 'A' else 'A']
    tools = list(BASE_TOOLS) + ([fetch] if arm == 'A' else [])
    allowed = list(BASE_TOOLS) + [fetch] + ([SEARCH_TOOL] if search else [])
    mcp = ['--mcp-config', json.dumps({'mcpServers': {'search': {'type': 'stdio', 'command': sys.executable,
                                                                 'args': ['-I', SEARCH_SERVER]}}})] if search else []
    return [
        'claude', '-p',
        '--model', RUNNER_MODEL, '--effort', RUNNER_EFFORT,
        '--output-format', 'stream-json', '--verbose',
        '--plugin-dir', plugin_dir,
        *mcp,
        '--tools', ','.join(tools),
        '--allowedTools', ','.join(allowed),
        '--disallowedTools', other,
        '--permission-prompts', 'none',
        '--', question,
    ]


def run_claude(args, cwd, env, timeout_s, grace_s=30):
    """Runs `claude` in a process group of its own. At the limit the group gets SIGINT, on which
    `claude -p` writes its result line (usage included) and exits; whatever has not exited
    `grace_s` later is killed. Returns (stdout, stderr, returncode, timed_out, wall_ms)."""
    started = time.monotonic()
    p = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         stdin=subprocess.DEVNULL, text=True, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout_s)
        return out, err, p.returncode, False, round((time.monotonic() - started) * 1000)
    except subprocess.TimeoutExpired:
        pass
    wall_ms = round((time.monotonic() - started) * 1000)
    _signal_group(p.pid, signal.SIGINT)
    try:
        out, err = p.communicate(timeout=grace_s)
    except subprocess.TimeoutExpired:
        _signal_group(p.pid, signal.SIGKILL)
        out, err = p.communicate()
    return out, err, p.returncode, True, wall_ms


def _signal_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


# A failed fetch's reason, after `fetch failed: <url>: `, when the site or the URL caused it.
_SITE_REASON = re.compile(r'(HTTP \d{3}|network error|refused:|too many redirects|redirected to an invalid'
                          r'|too large|invalid URL|unsupported scheme|no url given)')


def is_tool_caused(arm, text):
    """Whether a fetch error is the tool's own (criterion 3) rather than the site's."""
    if arm == 'B':
        m = re.match(r'fetch failed: (?:\S+: )?(.*)', text, re.S)
        return not (m and _SITE_REASON.match(m.group(1)))
    return not re.search(r'status code \d{3}', text)


_RUN_FILE = re.compile(r'^[\w-]+\.[AB]\.[\w-]+\.\d+\.json$')


def run_files(folder):
    """The I4 run files of a run folder, sorted (not the manifest, the projection, streams or failed runs)."""
    return sorted(n for n in os.listdir(folder) if _RUN_FILE.match(n))


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text')
    return ''


def _strip_error_tags(t):
    return re.sub(r'</?tool_use_error>', '', t).strip()


def _tokens(u):
    return {
        'input': u.get('inputTokens', 0),
        'output': u.get('outputTokens', 0),
        'cacheRead': u.get('cacheReadInputTokens', 0),
        'cacheCreation': u.get('cacheCreationInputTokens', 0),
    }


def parse_stream(text, arm, timed_out=False, wall_ms=None):
    """The I4 measures of one run, from its stream-json.

    Usage comes only from the result line's per-model usage. A stream without
    one (a run killed at its limit) has no reliable usage: the assistant
    messages' own usage fields are partial (output 0, cache reads folded into
    input in the pilot's streams), so tokens and cost are None, unavailable.
    A run cut off at its limit takes its wall time as its duration."""
    fetch = FETCH_TOOL[arm]
    fetch_ids, answered, errors, message_ids, searches = [], set(), [], set(), 0
    last_text, result, init_model = '', None, None
    for line in text.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        kind = o.get('type')
        if kind == 'system' and o.get('subtype') == 'init':
            init_model = o.get('model')
        elif kind == 'assistant':
            message = o.get('message', {})
            message_ids.add(message.get('id'))
            for b in message.get('content', []) or []:
                if b.get('type') == 'tool_use' and b.get('name') == fetch:
                    fetch_ids.append(b.get('id'))
                elif b.get('type') == 'tool_use' and b.get('name') == SEARCH_TOOL:
                    searches += 1
                elif b.get('type') == 'text' and b.get('text', '').strip():
                    last_text = b['text']
        elif kind == 'user':
            content = o.get('message', {}).get('content')
            for b in content if isinstance(content, list) else []:
                if b.get('type') != 'tool_result' or b.get('tool_use_id') not in fetch_ids:
                    continue
                answered.add(b['tool_use_id'])
                if b.get('is_error'):
                    t = _strip_error_tags(_text_of(b.get('content')))
                    errors.append({'text': t, 'toolCaused': is_tool_caused(arm, t)})
        elif kind == 'result':
            result = o
    if timed_out and any(i not in answered for i in fetch_ids):
        errors.append({'text': 'the run hit its time limit with a fetch call unanswered', 'toolCaused': True})
    if result is not None:
        usage = result.get('modelUsage') or {}
        main = _tokens(usage[RUNNER_MODEL]) if RUNNER_MODEL in usage else None
        cost, turns = result.get('total_cost_usd'), result.get('num_turns', len(message_ids))
        duration = wall_ms if timed_out and wall_ms is not None else result.get('duration_ms', wall_ms)
    else:
        usage, main, cost, turns, duration = None, None, None, len(message_ids), wall_ms
    return {
        'finalText': (result or {}).get('result') or last_text,
        'mainTokens': main,
        'usageByModel': usage,
        'fetchCalls': len(fetch_ids),
        'fetchErrors': errors,
        'searchCalls': searches,
        'turns': turns,
        'durationMs': duration,
        'costUsd': cost,
        'initModel': init_model,
        'isError': bool(result.get('is_error')) if result else True,
    }
