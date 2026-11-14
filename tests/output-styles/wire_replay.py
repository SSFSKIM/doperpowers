"""The exact API request a Claude Code session sent, rebuilt from its transcript.

Since about 2.1.31x the engine records each request it sends in the session's
transcript, delta-encoded:

  api-request        {id, params, shapeHash, base, keep, tail, cacheControl}:
                     the request's messages are the first `keep` messages of
                     request `base`, then the messages whose hashes `tail`
                     lists; `params` holds model, effort, thinking, betas
  api-request-shape  {shapeHash, shape: {system, tools}}
  api-request-blob   {hash, message}: a message the engine could not derive
                     from the transcript's own rows

A message's hash is the SHA-256 of its JSON with sorted keys and no spaces.
The messages without a blob are the transcript's own rows: an assistant
response is its rows' content blocks merged (one row per block, in
`apiBlockIndex` order), with tool inputs as `wireToolInputs` holds them; a
user message is a row's content (a string prompt as one text block); a
rendered attachment is its own message. Where no row matches a hash byte for
byte, an assistant response is taken from the rows of the request that
produced it, and a tool-result message from the result rows of the calls
before it, in their order; `approx` counts those (a few per long session).

Transcripts run to hundreds of megabytes, so this reads one line at a time
and keeps only what the one request it rebuilds needs: a first pass reads the
request records, a second the blobs and rows that request's chain names.
"""
import hashlib, json, re

PREFIX_REQ = '{"type":"api-request",'
PREFIX_BLOB = '{"type":"api-request-blob",'
PREFIX_SHAPE = '{"type":"api-request-shape",'
HASH_AT = re.compile(r'"hash":"([0-9a-f]{64})"')
SHAPE_AT = re.compile(r'"shapeHash":"([0-9a-f]{64})"')
REF_AT = re.compile(r'"requestRef":"([0-9a-f-]{36})"')


def digest(message):
    return hashlib.sha256(json.dumps(message, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def requests(path, whole=()):
    """Every request record of a transcript, by id: its base, keep and tail
    alone (a long session holds tens of thousands, each with its params),
    except the ids in `whole`, kept as recorded."""
    out = {}
    with open(path) as f:
        for line in f:
            if line.startswith(PREFIX_REQ):
                r = json.loads(line)
                out[r['id']] = r if r['id'] in whole else {k: r.get(k) for k in ('base', 'keep', 'tail')}
    return out


def rebuild(path, rid, reqs=None):
    """The request `rid` as it was sent: params, system, tools and messages,
    with its cache marks. Returns (request, approx)."""
    reqs = reqs or requests(path, whole={rid})
    # Where each of the request's messages was introduced: position p of a
    # request is its base's position p below `keep`, else its own tail's
    # entry p - keep; only the prefix a later request keeps is needed.
    final = reqs[rid]
    n = final['keep'] + len(final['tail'])
    origin = [None] * n
    x, upto = rid, n
    while x and upto:
        r = reqs[x]
        for p in range(r['keep'], upto):
            if origin[p] is None:
                origin[p] = (x, p - r['keep'])
        upto = min(upto, r['keep'])
        x = r.get('base')
    if any(o is None for o in origin):
        raise KeyError('request %s has positions no record introduces' % rid)
    need = {reqs[x]['tail'][i] for x, i in origin}
    resp_needed = {reqs[x].get('base') for x, _ in origin} - {None}
    shape_hash = final['shapeHash']
    blobs, shape, responses, results = {}, None, {}, {}

    def offer(message):
        h = digest(message)
        if h in need:
            blobs.setdefault(h, message)

    def merge(parts):
        """A response's rows as one message, and its tool inputs as sent."""
        wire, content = {}, []
        for _, c, w in sorted(parts, key=lambda p: p[0]):
            wire.update(w)
            content += c
        return {'role': 'assistant', 'content': content}, wire

    def as_sent(message, wire):
        return {'role': 'assistant', 'content': [dict(b, input=wire[b['id']]) if b.get('type') == 'tool_use' and b.get('id') in wire else b for b in message['content']]}

    def offer_response(parts):
        message, wire = merge(parts)
        offer(message)
        if wire:
            offer(as_sent(message, wire))

    open_groups = {}

    with open(path) as f:
        for line in f:
            if line.startswith(PREFIX_BLOB):
                m = HASH_AT.search(line, 0, 300)
                if m and m.group(1) in need:
                    blobs[m.group(1)] = json.loads(line)['message']
            elif line.startswith(PREFIX_SHAPE):
                m = SHAPE_AT.search(line, 0, 300)
                if m and m.group(1) == shape_hash:
                    shape = json.loads(line)['shape']
            elif line.startswith('{"type":"api-request"'):
                continue
            elif '"type":"assistant"' in line:
                r = json.loads(line)
                if r.get('type') != 'assistant':
                    continue
                if r.get('answeredWithoutRequest'):
                    # A reply a plugin made up with no request (the message
                    # tool's after a final message): a message of its own.
                    offer({'role': 'assistant', 'content': r['message']['content']})
                    continue
                key = r.get('requestRef') or r['message'].get('id')
                part = (r.get('apiBlockIndex', 0), r['message']['content'], r.get('wireToolInputs') or {})
                (responses if key in resp_needed else open_groups).setdefault(key, []).append(part)
                while len(open_groups) > 4:  # a response's rows lie together
                    offer_response(open_groups.pop(next(iter(open_groups))))
            elif '"type":"user"' in line:
                r = json.loads(line)
                if r.get('type') != 'user':
                    continue
                c = r['message']['content']
                for content in ([c, [{'type': 'text', 'text': c}]] if isinstance(c, str) else [c]):
                    offer({'role': 'user', 'content': content})
            elif '"type":"attachment"' in line and '"rendered"' in line:
                r = json.loads(line)
                content = [{'type': 'text', 'text': b['content']} for b in r.get('rendered') or [] if isinstance(b, dict) and 'content' in b]
                for role in ('user', 'system'):
                    offer({'role': role, 'content': content})

    for parts in list(open_groups.values()) + list(responses.values()):
        offer_response(parts)

    def response(req_id):
        """The response a request produced, from its rows, its tool inputs as sent."""
        if req_id not in responses:
            return None
        return as_sent(*merge(responses[req_id]))

    approx, messages, pending = 0, [], {}
    for p, (x, i) in enumerate(origin):
        h = reqs[x]['tail'][i]
        if h in blobs:
            messages.append(blobs[h])
        elif messages and messages[-1] is not None and messages[-1]['role'] == 'assistant':
            ids = [b['id'] for b in messages[-1]['content'] if b.get('type') == 'tool_use']
            if not ids:
                raise KeyError('no rows for message %s of request %s' % (h, x))
            pending[p] = (h, ids)
            messages.append(None)  # the results' rows, read below
        else:
            got = response(reqs[x].get('base'))
            if got is None:
                raise KeyError('no rows for message %s of request %s' % (h, x))
            messages.append(got)
            approx += 1
    if pending:
        # A tool-result message no single row matches: the result rows of the
        # calls before it, merged in the calls' order.
        ids = {i for _, want in pending.values() for i in want}
        with open(path) as f:
            for line in f:
                if '"type":"user"' in line and '"tool_result"' in line and any(i in line for i in ids):
                    r = json.loads(line)
                    c = r['message']['content']
                    if r.get('type') == 'user' and isinstance(c, list):
                        for b in c:
                            if b.get('type') == 'tool_result' and b.get('tool_use_id') in ids:
                                results[b['tool_use_id']] = c
        for p, (h, want) in pending.items():
            if any(i not in results for i in want):
                raise KeyError('no result rows for message %s' % h)
            merged = []
            for i in want:
                if results[i] not in merged:
                    merged.append(results[i])
            messages[p] = {'role': 'user', 'content': [b for part in merged for b in part]}
            approx += digest(messages[p]) != h
    if shape is None:
        raise KeyError('no shape %s' % shape_hash)
    req = dict(final['params'])
    req['system'] = shape['system']
    req['tools'] = shape['tools']
    req['messages'] = json.loads(json.dumps(messages))  # blobs can be shared between positions
    for cc in final.get('cacheControl') or []:
        node = req
        for p in cc['path']:
            node = node[p]
        if isinstance(node, dict):
            node['cache_control'] = cc['value']
    return req, approx


def response_of(path, rid):
    """What the request produced in the session: its response's content blocks."""
    parts = []
    with open(path) as f:
        for line in f:
            if '"type":"assistant"' in line and rid in line:
                r = json.loads(line)
                if r.get('type') == 'assistant' and r.get('requestRef') == rid:
                    parts.append((r.get('apiBlockIndex', 0), r['message']['content']))
    return [b for _, c in sorted(parts, key=lambda p: p[0]) for b in c]
