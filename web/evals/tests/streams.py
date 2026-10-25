"""Builders for stream-json lines in the shape `claude -p --output-format
stream-json --verbose` writes (2.1.310), for the tests."""

import json


def init(model='sol', tools=('Read', 'mcp__web__fetch')):
    return {'type': 'system', 'subtype': 'init', 'model': model, 'tools': list(tools)}


def tool_use(tool_id, name, inp):
    return {'type': 'assistant', 'message': {'id': 'msg-' + tool_id, 'model': 'sol', 'role': 'assistant',
            'content': [{'type': 'tool_use', 'id': tool_id, 'name': name, 'input': inp}]}}


def text(t):
    return {'type': 'assistant', 'message': {'id': 'msg-text', 'model': 'sol', 'role': 'assistant',
            'content': [{'type': 'text', 'text': t}]}}


def tool_result(tool_id, content, is_error=False):
    block = {'type': 'tool_result', 'tool_use_id': tool_id, 'content': content}
    if is_error:
        block['is_error'] = True
    return {'type': 'user', 'message': {'role': 'user', 'content': [block]}}


def model_usage(inp, out, cache_read=0, cache_creation=0, cost=0.0):
    return {'inputTokens': inp, 'outputTokens': out, 'cacheReadInputTokens': cache_read,
            'cacheCreationInputTokens': cache_creation, 'costUSD': cost, 'contextWindow': 200000}


def result(final, model_usages, turns=3, duration=12000, cost=0.5, is_error=False):
    return {'type': 'result', 'subtype': 'success', 'is_error': is_error, 'result': final,
            'num_turns': turns, 'duration_ms': duration, 'total_cost_usd': cost, 'modelUsage': model_usages}


def stream(*objs):
    return ''.join(json.dumps(o) + '\n' for o in objs)
