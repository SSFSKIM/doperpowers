# For every interim drop since the merge: (a) pure placeholder, (b) engine provenance in the child transcript,
# (c) the conversation already held an earlier notice of that agent (with the same worktree), (d) report later or agent alive.
import json, re, os, subprocess, time
PROJECTS = os.path.expanduser('~/.claude/projects')
d = json.load(open(os.environ['AUDIT_OUT'] + '/drops.json'))
WT = lambda t: (re.search(r'(<worktree>.*?</worktree>)', t) or [None, None])[1]
def provenance(out):
    real = os.path.realpath(out)
    r = subprocess.run(['grep', '-a', '-E', 'Your final report is delivered through SubagentHandback|SubagentHandback is not available in this run|compact_boundary', '--', real], capture_output=True, text=True)
    for l in reversed(r.stdout.splitlines()):
        x = json.loads(l)
        if x.get('type') == 'system': return 'child compacted'
        c = (x.get('message') or {}).get('content')
        if x.get('type') == 'user' and x.get('isMeta') and isinstance(c, str):
            return 'reminder' if c.startswith('<system-reminder>\nYour final') else 'countermand' if c.startswith('<system-reminder>\nSubagentHandback is not') else 'other'
    return 'none'
def textof(r):
    if r['type'] == 'user':
        c = r['message'].get('content'); return c if isinstance(c, str) else ' '.join(b.get('text', '') for b in (c or []) if isinstance(b, dict) and b.get('type') == 'text')
    p = (r.get('attachment') or {}).get('prompt'); return p if isinstance(p, str) else ''
bad = []; n = 0; now = time.time()
for f, rows in d['rows'].items():
    drops = [r for r in rows if r['fate'] == 'dropped_by_hook']
    if not drops: continue
    path = os.path.join(PROJECTS, f[2:])
    conv = []; events = []
    for line in open(path, errors='ignore'):
        if 'compact_boundary' not in line and 'task-notification' not in line: continue
        try: r = json.loads(line)
        except: continue
        if r.get('isSidechain'): continue
        if r['type'] == 'system' and r.get('subtype') == 'compact_boundary': events.append((r['timestamp'], 'C', None, None)); continue
        if r['type'] in ('user', 'attachment'):
            x = textof(r)
            if x.lstrip().startswith('<task-notification>'):
                events.append((r.get('timestamp') or '', 'N', (re.search(r'<task-id>([^<]+)<', x) or [0, ''])[1], WT(x)))
    for dr in drops:
        n += 1
        text = None
        held = False
        for ts, k, task, wt in events:
            if ts >= dr['ts']: break
            if k == 'C': held = False; continue
            if task == dr['task'] and (not dr['wt'] or wt is not None): held = True
        prov = provenance(dr['out'])
        alive = None
        if not dr['hb']:
            try: alive = int(now - os.path.getmtime(os.path.realpath(dr['out'])))
            except: alive = -1
        problems = []
        if not dr['pure']: problems.append('not a pure placeholder')
        if prov != 'reminder': problems.append('provenance ' + prov)
        orphan = False
        try: orphan = 'parentAgentId' in json.load(open(path[:-6] + f"/subagents/agent-{dr['task']}.meta.json"))
        except Exception: pass
        if (dr['wt'] or orphan) and not held: problems.append('conversation did not hold an earlier notice')
        if not dr['hb'] and (alive is None or alive > 7200): problems.append(f'no report after and agent idle {alive}s')
        if problems: bad.append((f.split('/')[-1][:8], dr['ts'], dr['task'][:8], dr['agent'][:40], problems))
print('drops checked:', n, '| with a problem:', len(bad))
for b in bad: print(' ', b)
