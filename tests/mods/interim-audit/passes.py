# Every interim notice that ENTERED a main session since the merge, with the reason the filter let it in.
import json, re, os, subprocess, collections
PROJECTS = os.path.expanduser('~/.claude/projects')
WAIT = 'This agent has not reported yet: it is waiting on its own background work and will deliver its report through SubagentHandback when that finishes.'
NOTE = 'This agent stopped with background work of its own still running.'
MERGE = os.environ['AUDIT_SINCE']
G = lambda p, t: (re.search(p, t) or [None, None])[1]
def textof(d):
    if d['type'] == 'user':
        c = d['message'].get('content'); return c if isinstance(c, str) else ' '.join(b.get('text', '') for b in (c or []) if isinstance(b, dict) and b.get('type') == 'text')
    p = (d.get('attachment') or {}).get('prompt'); return p if isinstance(p, str) else ''
def hands_back(out):
    try:
        real = os.path.realpath(out)
        if not real.endswith('.jsonl'): return 'link?'
        r = subprocess.run(['grep', '-a', '-E', 'Your final report is delivered through SubagentHandback|SubagentHandback is not available in this run|compact_boundary', '--', real], capture_output=True, text=True)
        for l in reversed(r.stdout.splitlines()):
            try: x = json.loads(l)
            except: return 'unparsed'
            if x.get('type') == 'system' and x.get('subtype') == 'compact_boundary': return 'child compacted after marker'
            c = (x.get('message') or {}).get('content')
            if x.get('type') == 'user' and x.get('isMeta') and isinstance(c, str):
                if c.startswith('<system-reminder>\nYour final report'): return 'yes'
                if c.startswith('<system-reminder>\nSubagentHandback is not'): return 'countermand'
        return 'no marker'
    except Exception as e: return 'err'
rows = []
for f in open(os.environ['AUDIT_OUT'] + '/sessions.txt').read().split():
    path = os.path.join(PROJECTS, f[2:])
    sub = path[:-6] + '/subagents'
    conv = []; drops = []
    for line in open(path, errors='ignore'):
        if not any(k in line for k in ('compact_boundary', 'task-notification', 'dropped_by_hook')): continue
        try: d = json.loads(line)
        except: continue
        if d.get('isSidechain'): continue
        ts = d.get('timestamp') or ''; t = d['type']
        if t == 'system' and d.get('subtype') == 'compact_boundary': conv = []; continue
        if t == 'system' and (d.get('promptSubmitEnding') or {}).get('ending', {}).get('kind') == 'dropped_by_hook': drops.append(ts); continue
        if t not in ('user', 'attachment'): continue
        if t == 'attachment' and (d.get('attachment') or {}).get('type') != 'queued_command': continue
        x = textof(d)
        if not x.lstrip().startswith('<task-notification>'): continue
        how = 'user-row' if t == 'user' else 'mid-turn'
        task = G(r'<task-id>([^<]+)<', x); wt = G(r'(<worktree>.*?</worktree>)', x)
        if ts >= MERGE and NOTE in x:
            result = (G(r'<result>([^<]*)</result>', x) or '').strip()
            if result != WAIT:
                why = 'pointer (by design)' if 'report was delivered' in result else 'agent text / warning (by design)'
            else:
                out = G(r'<output-file>([^<]*)<', x)
                meta = {}
                try: meta = json.load(open(f'{sub}/agent-{task}.meta.json'))
                except: pass
                orphan = 'parentAgentId' in meta
                prior = [c for c in conv if c[0] == task and (wt is None or (c[1] or '') == wt)]
                if out is None: why = 'no output-file'
                elif (wt or orphan) and not prior: why = ('worktree' if wt else 'orphan') + ': no earlier notice in conversation (by design)'
                elif (wt or orphan) and all(c[2] == 'mid-turn' for c in prior): why = ('worktree' if wt else 'orphan') + ': earlier notices only mid-turn (let in only by plugins before 7.171.1)'
                else:
                    hb = hands_back(out)
                    if hb != 'yes': why = f'provenance: {hb} (fail-open)'
                    else:
                        why = 'SHOULD HAVE DROPPED, unless the session ran a plugin without the filter (before 7.165.0)'
            rows.append((f.split('/')[-1][:8], f.split('/')[1][-24:], ts[5:19], task[:8], how, why, G(r'<summary>Agent "([^"]*)"', x)[:40] if G(r'<summary>Agent "([^"]*)"', x) else ''))
        conv.append((task, wt, how))
c = collections.Counter(r[5] for r in rows)
print('interim notices that entered a main session since', MERGE + ':', len(rows))
for k, v in c.most_common(): print(f'  {v:4}  {k}')
print()
for r in rows:
    if not r[5].endswith('(by design)'): print(' ', *r)
