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

RUNNER_MODEL = 'sol'
RUNNER_EFFORT = 'xhigh'

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


def runner_args(arm, plugin_dir, question):
    """`claude -p` for one configuration: A has WebFetch only, B has mcp__web__fetch only."""
    fetch, other = FETCH_TOOL[arm], FETCH_TOOL['B' if arm == 'A' else 'A']
    tools = list(BASE_TOOLS) + ([fetch] if arm == 'A' else [])
    return [
        'claude', '-p',
        '--model', RUNNER_MODEL, '--effort', RUNNER_EFFORT,
        '--output-format', 'stream-json', '--verbose',
        '--plugin-dir', plugin_dir,
        '--tools', ','.join(tools),
        '--allowedTools', ','.join(list(BASE_TOOLS) + [fetch]),
        '--disallowedTools', other,
        '--permission-prompts', 'none',
        '--', question,
    ]


def run_claude(args, cwd, env, timeout_s):
    """Runs `claude`, killing its whole process group at the limit. Returns (stdout, stderr, returncode, timed_out)."""
    p = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         stdin=subprocess.DEVNULL, text=True, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout_s)
        return out, err, p.returncode, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, err = p.communicate()
        return out, err, p.returncode, True


# A failed fetch's reason, after `fetch failed: <url>: `, when the site or the URL caused it.
_SITE_REASON = re.compile(r'(HTTP \d{3}|network error|refused:|too many redirects|redirected to an invalid'
                          r'|too large|invalid URL|unsupported scheme|no url given)')


def is_tool_caused(arm, text):
    """Whether a fetch error is the tool's own (criterion 3) rather than the site's."""
    if arm == 'B':
        m = re.match(r'fetch failed: (?:\S+: )?(.*)', text, re.S)
        return not (m and _SITE_REASON.match(m.group(1)))
    return not re.search(r'status code \d{3}', text)


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


def parse_stream(text, arm, timed_out=False):
    """The I4 measures of one run, from its stream-json."""
    fetch = FETCH_TOOL[arm]
    fetch_ids, answered, errors = [], set(), []
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
            for b in o.get('message', {}).get('content', []) or []:
                if b.get('type') == 'tool_use' and b.get('name') == fetch:
                    fetch_ids.append(b.get('id'))
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
    usage = (result or {}).get('modelUsage') or {}
    return {
        'finalText': (result.get('result') or '') if result else last_text,
        'mainTokens': _tokens(usage.get(RUNNER_MODEL, {})),
        'usageByModel': usage,
        'fetchCalls': len(fetch_ids),
        'fetchErrors': errors,
        'turns': (result or {}).get('num_turns', 0),
        'durationMs': (result or {}).get('duration_ms', 0),
        'costUsd': (result or {}).get('total_cost_usd', 0.0),
        'initModel': init_model,
        'isError': bool((result or {}).get('is_error')) if result else True,
    }
