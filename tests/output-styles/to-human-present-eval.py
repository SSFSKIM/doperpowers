"""Hand-run replay for the present rule, the sentence of the to-human style
and the owner's CLAUDE.md that says when a session puts something on its
panel (`mcp__to-human__present`) instead of only in a message: it spends
model calls, so nothing runs it automatically.

Each turn is a real point in the owner's transcripts where a session wrote
to its human (a response that called the message tool). The request that
produced that response is rebuilt as it was sent (`wire_replay.py`, exact
where `approx` is 0:
system, tools, messages, model, effort, thinking), then changed in three
places: the output style in it is replaced by the arm's style; the arm's
CLAUDE.md line is put at the end of the Reporting section of every copy of
the owner's `~/.claude/CLAUDE.md` it holds; and the present tool is offered
beside the message tool, defined as `to-human/hooks/mods/present.tsx` ships
it. The model writes that response again, and goes on until it reaches the
human: a run ends at the first response that calls the message tool, the
present tool or an ask tool (`REPORT_TOOLS`), or that calls nothing, and
calls the tool when any of its responses holds a `present` call. A call of
the present tool is not answered, so no fork is spawned. Any other call is
answered as not run (`NOT_RUN`), as an error, for at most --max-steps
responses (4). The models mostly check something before a report: in the
first round, with one response per run, 28 of 30 runs over the warranted
turns and 12 of 30 over the routine ones made such a call and stopped there,
never coming to the choice the rule is about; the original requests, sent
again unchanged, did the same in 3 of 5 runs, so it is the models' habit, not
the replay's. Offered only the tools that reach the human, they called the
command tool anyway (3 of 3 runs, the name taken from the conversation), so
the replay keeps every tool and answers such a call instead. A run still
checking at its last step reached no one and is counted apart (`undecided`).

The turns are in three classes; `TURNS` gives each with why it is in its
class. Seven warrant a panel by the rule's own terms (a decision the ask
dialog cannot carry, a design presented for approval, a third or later
revision of the same findings in one session); twelve stay text (ten
routine: a merge, a green run, a problem met and resolved, a short answer;
and two decisions the dialog carries); one, w2, is borderline, run and
counted in neither. The classes follow the human's ruling after the first
round (a decision gets a panel only when the dialog cannot carry it), which
moved w1 and w4 from warranted to the text side. The bar (the design's
acceptance 15): of the 36 runs over the text side at most 3 call the tool,
and of the 21 over the warranted turns at least 15.

  python3 tests/output-styles/to-human-present-eval.py NAME=STYLE.md[:CLAUDE_LINE.md] [...] \\
      [--reps 3] [--turns w1,r1,...] [--workers 3] [--max-steps 4] [--out results.json] [--dry-run]

An arm without a CLAUDE.md line leaves the copies as they were. e.g.
control=<(git show HEAD~1:output-styles/to-human.md) rule=output-styles/to-human.md:rule-claude.md.
--dry-run rebuilds every turn's request, checks each change landed, and
prints its size, calling nothing.

Each request is rebuilt for its run and released after it, a few at a time
(--workers), since a session's transcript runs to hundreds of megabytes and
a rebuilt context to a few. The three reps of a turn run one after another
so the second and third read the first's cache. It calls the local gateway
(`mid_turn.gateway_client`), in the request's own Claude Code shape.

Design: docs/doperpowers/specs/2026-11-13-present-panel-design.md (M3).
Results: docs/doperpowers/specs/2026-11-13-present-panel-eval.md.
"""
import argparse, json, os, re, sys, threading, time, concurrent.futures as cf
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import wire_replay  # noqa: E402
from mid_turn import MESSAGE_TOOL, gateway_client  # noqa: E402

PROJECTS = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude') / 'projects'
PRESENT_TSX = REPO / 'to-human' / 'hooks' / 'mods' / 'present.tsx'
PRESENT_TOOL = 'mcp__to-human__present'
STYLE_HEAD = '# Output Style: doperpowers:to-human\n'
STYLE_END = 'remain focused and relevant.'  # the style's last sentence, in every version
CLAUDE_HEAD = 'Contents of %s/.claude/CLAUDE.md' % Path.home()
REPORT_TOOLS = (MESSAGE_TOOL, PRESENT_TOOL, 'mcp__sminos__AskUserQuestion', 'AskUserQuestion')
OUT_OF_PLAN = 'out of plan usage'
SPENT = threading.Event()  # a plan ran out: no further request from this process


class PlanSpent(Exception):
    """The account's plan ran out, in this run or another worker's."""
NOT_RUN = 'Not run: this step is a replay of the session, and its commands are not executed here. Go on from what the conversation already shows.'

# (id, class, kind, transcript under the projects directory, request id, model and effort as sent, why it is in its class)
TURNS = [
    ('w1', 'text', 'decision the dialog carries',
     '-Users-new/72609148-ea13-4521-8605-3804943c1a3d.jsonl',
     '30a8aea2-d2c7-45de-ade0-8082fc105cbf', 'claude-opus-5-5 xhigh',
     'asks what to do with the 49 unmerged worktrees left (35 GB), in two kinds with counts and sizes, after a cleanup that went wider than approved (Korean)'),
    ('w2', 'borderline', 'decision',
     '-Users-new-Developer-GitHub-manim-master/4d4a4036-3e9d-46d6-8f80-9360dd736074.jsonl',
     'e58256f5-0435-423b-bdff-0b9a67d0be4d', 'claude-fable-5-2 xhigh',
     "recommends a full-length test over its own earlier default of a front part, with a table of the two options' cost, time and viewing; the choice goes to the ask dialog (Korean)"),
    ('w3', 'warranted', 'decision the dialog cannot carry',
     '-Users-new-Developer-GitHub-manim-master/c27e9d9d-4bfe-417e-8d10-3ca911d7e917.jsonl',
     '9870653f-abe3-499b-bac7-5fc85c3d19fb', 'claude-opus-5-5 xhigh',
     'all three memory designs fail the leak gate (a table of three measures by three designs); recommends a redesign and asks which way to go'),
    ('w4', 'text', 'decision the dialog carries',
     '-Users-new/639ca648-158e-4536-9007-59a2047aad20.jsonl',
     '658c5d05-fc61-4bf1-88ff-e658d24c2092', 'claude-opus-5-5 xhigh',
     'explains ticket #124 (redaction inside installed code) and puts build or defer to the human, with a recommendation'),
    ('w5', 'warranted', 'design',
     '-Users-new-Developer-GitHub-doperpowers/f89d7fb0-c79f-4284-8525-87eefc908975.jsonl',
     '8ae8e410-a29f-4bc6-87c2-c8d8c1fe2819', 'claude-opus-5-5 xhigh',
     'presents the session-manager design (skill, subscriptions, briefing, two new sminos commands) and asks for approval before writing the spec'),
    ('w6', 'warranted', 'design',
     '-Users-new-Developer-GitHub-claude-usage-menubar/95341a27-3caa-4a1c-8710-d6bcd72bbb56.jsonl',
     '3a514f67-4efd-4baf-8319-4e9174f07a2d', 'claude-opus-5-5 xhigh',
     'presents the full design of an OpenRouter models window with one open question, asking for approval or changes'),
    ('w7', 'warranted', 'design',
     '-Users-new-Developer-GitHub-doperpowers--claude-worktrees-web-fetch/700c5e84-d0f5-49f1-887d-85f3fbfd1f81.jsonl',
     '19acdc29-e00f-4404-8404-90c6ae3670ef', 'claude-opus-5-5 xhigh',
     "presents ticket #137's design (checking a saved page with the server before reuse) with the measurements behind it, for a ruling"),
    ('w8', 'warranted', 'revision',
     '-Users-new-Developer-GitHub-MAWS/10d85d03-71e5-4bbb-a515-872248b21ba3.jsonl',
     '2f9c7242-5770-4654-8387-11fc89704fef', 'claude-fable-5-2 xhigh',
     'the fourth correction in a session assembling a large UX spec: a card and a drawn frame the human answered rest on a wrong fact, so a rule changes and a question goes out'),
    ('w9', 'warranted', 'revision',
     '-Users-new-Developer-GitHub-manim-master/8e7e77ec-0479-4a46-b23c-c0ac94d79ee7.jsonl',
     '97291923-902e-4b16-adb0-ad8b96b4a3ef', 'claude-opus-5-5 xhigh',
     "the third version of the list of what the human's note reorganization lost (18 places, then four kinds, now five more); asks again (Korean)"),
    ('w10', 'warranted', 'revision',
     '-Users-new-Developer-GitHub-manim-master/49104986-bac9-48df-85c0-177eaf04e318.jsonl',
     '1f9e95ee-d7ff-4fdb-9e00-9bfac1f422eb', 'claude-opus-5-5 xhigh',
     "the third message on the whole-video judge's scene limit: the limit it reported, and had a fix designed around, was wrong"),
    ('r1', 'text', 'merge',
     '-Users-new-Developer-GitHub-doperpowers/7a79acf5-d9c4-4341-9b0b-d40e3a1cb541.jsonl',
     'ef1d507e-ab04-4bdb-90dd-4cfb9b9e7b5e', 'claude-opus-5-5 high',
     "a PR merged after two CI fixes; installing the update is the human's"),
    ('r2', 'text', 'merge',
     '-Users-new-Developer-GitHub-doperpowers/1cdcc7bc-7406-453e-8f01-f2ef6cfa3ccf.jsonl',
     '0fd66995-dea5-4dcf-ba1b-499d794fd9fc', 'claude-opus-5-5 xhigh',
     'both PRs of the work are merged and installed; the open items are listed'),
    ('r3', 'text', 'merge',
     '-Users-new-Developer-GitHub-MAWS/10d85d03-71e5-4bbb-a515-872248b21ba3.jsonl',
     'd645693c-0b43-4c75-86a2-81645dc38a8f', 'claude-fable-5-2 high',
     'one landing of a wave is on master; what is next in line'),
    ('r4', 'text', 'green run',
     '-Users-new-Developer-GitHub-doperpowers/b4948247-1ac3-46d2-8dcf-80894fd939d9.jsonl',
     '7b11205d-888e-44d2-a658-23c8298d730e', 'claude-fable-5-2 xhigh',
     'test rows passed on the final build and the VM is staged; nothing is needed'),
    ('r5', 'text', 'merge',
     '-Users-new-Developer-GitHub-manim-master/49104986-bac9-48df-85c0-177eaf04e318.jsonl',
     'f34918d7-9a2d-4923-890e-b95c6e361580', 'claude-opus-5-5 xhigh',
     'the first part of a milestone is merged; what comes next'),
    ('r6', 'text', 'problem resolved',
     '-Users-new-Developer-GitHub-doperpowers/9ea1d75c-a885-452a-91d6-086a7f246d29.jsonl',
     'f7a0f0cc-c3b7-4044-b24e-f9ca429c4a1b', 'claude-fable-5-2 xhigh',
     'two stale entries in the view were one leftover wait loop; stopped, nothing lost'),
    ('r7', 'text', 'problem resolved',
     '-Users-new-Developer-GitHub-manim-master/904e094e-a4c3-4f49-856c-9ddebc2b51e3.jsonl',
     '12b8e0dd-3f0e-4fe2-811f-a4bac7b35e7c', 'claude-opus-5-5 high',
     'a video is unlisted as asked, the live site checked, and how it comes back'),
    ('r8', 'text', 'short answer',
     '-Users-new-Developer-GitHub-doperpowers/aad801e3-82e6-4324-baab-b9fed08f42e7.jsonl',
     '578e1b6e-8e64-4813-a068-0e97b228d714', 'claude-fable-5-2 high',
     'two models removed from the routing guide as asked; one value left to the human (Korean)'),
    ('r9', 'text', 'short answer',
     '-Users-new-Developer-GitHub-doperpowers/d1d2d6b0-e450-4f43-83a8-203f21f682be.jsonl',
     'abfe84a7-0fe4-4fdd-9ede-58ee2f04510e', 'claude-opus-5-5 xhigh',
     'one sentence: the names stay as chosen and nothing changed'),
    ('r10', 'text', 'short answer',
     '-Users-new-Developer-GitHub-doperpowers/40776d16-8e78-44a7-b361-b27546a885f6.jsonl',
     '85e43254-a837-4b17-91e7-0df9fb990b37', 'claude-opus-5-5 xhigh',
     'confirms that nothing behavioral changed; one documentation commit'),
]


def present_tool_def(path=PRESENT_TSX):
    """The tool as the module registers it: its name, description and schema."""
    src = Path(path).read_text()
    desc = re.search(r'export const DESCRIPTION = "((?:[^"\\]|\\.)*)"', src).group(1)
    m = re.search(r"export const INPUT_SCHEMA = (\{.*?\n\})", src, re.S)
    js = re.sub(r"([{,]\s*)(\w+)\s*:", r'\1"\2":', m.group(1))
    js = re.sub(r"'((?:[^'\\]|\\.)*)'", lambda q: json.dumps(q.group(1)), js)
    js = re.sub(r",(\s*[}\]])", r"\1", js)
    return {'name': PRESENT_TOOL, 'description': desc, 'input_schema': json.loads(js)}


def style_body(path):
    return re.sub(r"^---\n.*?\n---\n", "", Path(path).read_text(), flags=re.S).strip()


def texts(req):
    """Every text block of the request's messages, to edit in place."""
    for m in req['messages']:
        if isinstance(m['content'], str):
            m['content'] = [{'type': 'text', 'text': m['content']}]
        for b in m['content']:
            if b.get('type') == 'text':
                yield b


def apply_arm(req, style, claude_line):
    """The request with the arm's style, its CLAUDE.md line and the present
    tool; returns how many copies of the style and of CLAUDE.md it changed."""
    styles = claudes = 0
    for b in texts(req):
        t = b['text']
        k = t.find(STYLE_HEAD)
        if k >= 0:
            # The engine adds more after the style in the same block (hook
            # context, the deferred tools, the date); every version of the
            # style the transcripts hold ends on the same sentence.
            end = t.find(STYLE_END, k)
            if end < 0:
                raise ValueError('a copy of the style without its last sentence')
            t = t[:k] + STYLE_HEAD + style + t[end + len(STYLE_END):]
            styles += 1
        if claude_line:
            start = 0
            while True:
                k = t.find(CLAUDE_HEAD, start)
                if k < 0:
                    break
                r = t.find('\n### Reporting\n', k)
                nxt = t.find('\n### ', r + 1) if r >= 0 else -1
                nxt_file = t.find('\nContents of ', k + 1)
                if r < 0 or nxt < 0 or (0 <= nxt_file < r):
                    raise ValueError('no Reporting section in a copy of CLAUDE.md')
                t = t[:nxt] + '\n' + claude_line.strip() + '\n' + t[nxt:]
                claudes += 1
                start = nxt + len(claude_line) + 2
        b['text'] = t
    names = [x['name'] for x in req['tools']]
    if PRESENT_TOOL not in names:
        at = names.index(MESSAGE_TOOL) + 1 if MESSAGE_TOOL in names else len(names)
        req['tools'].insert(at, present_tool_def())
    return styles, claudes


def send(client, req):
    """One response, streamed: its blocks in order (and as sent back, `raw`) and its usage."""
    params = dict(req)
    betas = params.pop('betas', [])
    named = {k: params.pop(k) for k in ('model', 'max_tokens', 'messages', 'system', 'tools', 'thinking') if k in params}
    for attempt in range(4):
        try:
            with client.beta.messages.stream(betas=betas, extra_body=params, **named) as s:
                msg = s.get_final_message()
            break
        except Exception as e:
            # A server error or a dropped connection is tried again; a 429 is
            # not (a spent plan stays spent, and its retries reach the account).
            status = getattr(e, 'status_code', None)
            if attempt == 3 or status == 429 or (status is not None and status < 500):
                raise
            time.sleep(10 * (attempt + 1))
    raw = [b.model_dump(exclude_none=True) for b in msg.content]
    blocks = []
    for b in msg.content:
        if b.type == 'text':
            blocks.append({'type': 'text', 'text': b.text})
        elif b.type == 'thinking' and getattr(b, 'thinking', ''):
            blocks.append({'type': 'progress', 'text': b.thinking})
        elif b.type == 'tool_use':
            blocks.append({'type': 'tool_use', 'name': b.name, 'input': b.input, 'id': b.id})
    u = msg.usage
    return {'stop': msg.stop_reason, 'blocks': blocks, 'raw': raw,
            'usage': {k: getattr(u, k, None) for k in ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens', 'output_tokens')}}


def run_once(client, req, max_steps):
    """One run: responses until one reaches the human or calls nothing,
    any other call answered as not run."""
    steps, messages = [], list(req['messages'])
    for _ in range(max_steps):
        if SPENT.is_set():
            raise PlanSpent('a plan ran out in this process before this request')
        got = send(client, dict(req, messages=messages))
        raw = got.pop('raw')
        steps.append(got)
        calls = [b for b in got['blocks'] if b['type'] == 'tool_use']
        if not calls or any(b['name'] in REPORT_TOOLS for b in calls):
            break
        messages = messages + [{'role': 'assistant', 'content': raw},
                               {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': b['id'], 'content': NOT_RUN, 'is_error': True} for b in calls]}]
    calls = [b for st in steps for b in st['blocks'] if b['type'] == 'tool_use']
    last = [b['name'] for b in steps[-1]['blocks'] if b['type'] == 'tool_use']
    undecided = bool(last) and not any(n in REPORT_TOOLS for n in last)
    return {'steps': steps,
            'reached_at': None if undecided else len(steps),
            'present': any(b['name'] == PRESENT_TOOL for b in calls),
            'message': any(b['name'] == MESSAGE_TOOL for b in calls),
            'undecided': undecided,
            'others': [b['name'] for b in calls if b['name'] not in REPORT_TOOLS]}


def run_turn(client, turn, arm, style, claude_line, reps, dry, max_steps=4):
    """The turn's runs for the repetition numbers in `reps`. A plan that runs
    out stops them: the repetition it reached is recorded as skipped, with
    no `rep`, so it counts as no run and a resume runs it again."""
    tid, cls, _kind, rel, rid, _sent, _why = turn
    path = PROJECTS / rel
    req, approx = wire_replay.rebuild(path, rid)
    styles, claudes = apply_arm(req, style, claude_line)
    if styles == 0 or (claude_line and claudes == 0):
        raise ValueError('%s: style copies %d, CLAUDE.md copies %d' % (tid, styles, claudes))
    size = len(json.dumps(req))
    head = {'turn': tid, 'class': cls, 'arm': arm, 'model': req['model'],
            'effort': (req.get('output_config') or {}).get('effort'), 'approx': approx,
            'styles': styles, 'claudes': claudes, 'bytes': size, 'tools': [x['name'] for x in req['tools']]}
    if dry:
        return [head]
    out = []
    for rep in reps:
        t0 = time.time()
        try:
            got = run_once(client, req, max_steps)
        except Exception as e:
            if isinstance(e, PlanSpent) or OUT_OF_PLAN in str(e):
                # The account's plan is spent: not a run, and no further
                # request from this process; it exits 3.
                SPENT.set()
                out.append(dict(head, skipped=repr(e), at_rep=rep))
                break
            got = {'error': repr(e)}
        out.append(dict(head, rep=rep, secs=round(time.time() - t0, 1), **got))
    del req
    return out


def pending(results, turns, arms, reps):
    """The repetitions still to run, by turn and arm: those with no
    completed run in `results` (a skipped or failed one is run again)."""
    done = {(x['turn'], x['arm'], x['rep']) for x in results if 'rep' in x and 'error' not in x}
    todo = {}
    for a in arms:
        for t in turns:
            left = [r for r in range(reps) if (t[0], a, r) not in done]
            if left:
                todo[(t[0], a)] = left
    return todo


def tally(results):
    """Per arm and class: runs, runs that call present, the step each run
    reached the human at (`never` for none), errors."""
    t = {}
    for x in results:
        if 'rep' not in x:
            continue
        c = t.setdefault((x['arm'], x['class']), {'runs': 0, 'present': 0, 'undecided': 0, 'errors': 0, 'reached_at': {}, 'by_turn': {}})
        if 'error' in x:
            c['errors'] += 1
            continue
        c['runs'] += 1
        c['present'] += x['present']
        c['undecided'] += x['undecided']
        # Runs from before the field existed: a decided run reached the human
        # at its last step.
        at = x['reached_at'] if 'reached_at' in x else None if x['undecided'] else len(x['steps'])
        at = at or 'never'
        c['reached_at'][at] = c['reached_at'].get(at, 0) + 1
        c['by_turn'][x['turn']] = c['by_turn'].get(x['turn'], 0) + x['present']
    return t


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('arms', nargs='+', help='NAME=STYLE.md[:CLAUDE_LINE.md]')
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--turns', default=','.join(t[0] for t in TURNS))
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--out', default='to-human-present-results.json')
    ap.add_argument('--max-steps', type=int, default=4)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    arms = {}
    for a in args.arms:
        name, spec = a.split('=', 1)
        style, _, line = spec.partition(':')
        arms[name] = (style_body(style), Path(line).read_text() if line else '')
    want = args.turns.split(',')
    turns = [t for t in TURNS if t[0] in want]
    client = None if args.dry_run else gateway_client().with_options(max_retries=0)
    # An existing --out is kept and added to: only the repetitions with no
    # completed run in it are run (one skipped for a spent plan is).
    results = json.loads(Path(args.out).read_text()) if Path(args.out).exists() and not args.dry_run else []
    results = [x for x in results if 'rep' in x and 'error' not in x]
    todo = pending(results, turns, arms, args.reps)
    by_id = {t[0]: t for t in turns}
    lock = threading.Lock()
    with cf.ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(run_turn, client, by_id[tid], a, arms[a][0], arms[a][1], reps, args.dry_run, args.max_steps): (tid, a)
                for (tid, a), reps in todo.items()}
        for f in cf.as_completed(futs):
            tid, a = futs[f]
            try:
                got = f.result()
            except Exception as e:
                got = [{'turn': tid, 'arm': a, 'error': repr(e)}]
            with lock:
                results += got
                Path(args.out).write_text(json.dumps(results, indent=1, ensure_ascii=False))
            for x in got:
                print(x['turn'], x['arm'], x.get('rep', '-'), 'PRESENT' if x.get('present') else '', x.get('error', ''), 'SKIPPED' if 'skipped' in x else '',
                      x.get('bytes', ''), x.get('model', ''), x.get('effort', ''), flush=True)
    for (a, cls), c in sorted(tally(results).items()):
        print(a, cls, '%d of %d call present; reached the human at step %s' % (c['present'], c['runs'], c['reached_at']), ('%d errors' % c['errors']) if c['errors'] else '', c['by_turn'])
    if SPENT.is_set():
        print('stopped: a plan ran out (out of plan usage); the turns marked SKIPPED were not run')
        sys.exit(3)
