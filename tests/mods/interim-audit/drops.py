# Every dropped prompt since the merge, in every main transcript touched since: what was dropped, by which hook reason,
# and for interim drops whether the agent's report later reached that session.
import json, re, collections, os, subprocess
PROJECTS = os.path.expanduser('~/.claude/projects')
WAIT = 'This agent has not reported yet: it is waiting on its own background work and will deliver its report through SubagentHandback when that finishes.'
NOTE = 'This agent stopped with background work of its own still running.'
MERGE = os.environ['AUDIT_SINCE']
tid = lambda t: (re.search(r'<task-id>([^<]+)</task-id>', t) or [None, None])[1]
summ = lambda t: (re.search(r'<summary>Agent "([^"]*)"', t) or [None, ''])[1]
res = lambda t: (re.search(r'<result>([^<]*)</result>', t) or [None, None])[1]
def secs(ts): return int(ts[8:10])*86400 + int(ts[11:13])*3600 + int(ts[14:16])*60 + float(ts[17:23])
def textof(d):
    if d['type'] == 'user':
        c = d['message'].get('content'); return c if isinstance(c, str) else ' '.join(b.get('text', '') for b in (c or []) if isinstance(b, dict) and b.get('type') == 'text')
    p = (d.get('attachment') or {}).get('prompt'); return p if isinstance(p, str) else ''
def pure(t):  # independent of the hook's regex: one completed envelope, the full interim note, the bare placeholder
    t = t.strip()
    return (t.startswith('<task-notification>') and t.endswith('</task-notification>') and t.count('<task-notification>') == 1
            and '<status>completed</status>' in t and (res(t) or '').strip() == WAIT
            and re.search(r'<note>' + re.escape(NOTE) + r' It may resume on its own when that work completes or reports, and the same task-id notifies again if it does; the result below may be interim\.</note>', t) is not None)
allrows = {}; other_drops = []
for f in open(os.environ['AUDIT_OUT'] + '/sessions.txt').read().split():
    path = os.path.join(PROJECTS, f[2:])
    items, droprows = [], []
    hb = collections.defaultdict(list); finals = collections.defaultdict(list); killed = collections.defaultdict(list); entered = collections.Counter(); peers = collections.defaultdict(list)
    for line in open(path, errors='ignore'):
        if not any(k in line for k in ('queue-operation', 'dropped_by_hook', '"peer"', 'task-notification')): continue
        try: d = json.loads(line)
        except: continue
        ts = d.get('timestamp') or ''
        if d.get('isSidechain') or ts < MERGE: continue
        t = d['type']; x = d.get('content') if isinstance(d.get('content'), str) else ''
        if t == 'queue-operation':
            op, why = d.get('operation'), d.get('reason')
            if op == 'enqueue' and NOTE in x: items.append({'ts': ts, 'text': x, 'fate': None})
            elif op == 'remove' and NOTE in x:
                for it in items:
                    if it['fate'] is None and it['text'] == x: it['fate'] = why; it['fts'] = ts; break
        elif t == 'system' and (d.get('promptSubmitEnding') or {}).get('ending', {}).get('kind') == 'dropped_by_hook':
            droprows.append((ts, d['promptSubmitEnding']['ending'].get('reason', '')))
        elif t in ('user', 'attachment'):
            y = textof(d); o = (d.get('origin') if t == 'user' else (d.get('attachment') or {}).get('origin')) or {}
            if o.get('kind') == 'peer':
                (hb if o.get('handback') else peers)[o.get('from') or o.get('senderTaskId')].append(ts)
            if y.lstrip().startswith('<task-notification>'):
                if NOTE in y: entered[y.strip()] += 1
                elif '<status>completed</status>' in y: finals[tid(y)].append(ts)
                elif re.search(r'<status>(killed|failed|stopped)</status>', y): killed[tid(y)].append(ts)
    for it in items:
        if it['fate'] in (None, 'absorbed_mid_turn') and entered[it['text'].strip()] > 0:
            entered[it['text'].strip()] -= 1; it['fate'] = 'entered'
    explained = [secs(it['fts']) for it in items if it['fate'] == 'dropped_by_hook']
    for r, reason in droprows:
        if not reason.startswith('interim agent notification'):
            other_drops.append((f, r, reason)); continue
        if any(abs(secs(r) - e) < 2 for e in explained): continue
        cand = [it for it in items if it['fate'] is None and it['ts'] <= r]
        if cand: cand[-1]['fate'] = 'dropped_by_hook'; cand[-1]['fts'] = r
        else: other_drops.append((f, r, 'UNPAIRED interim drop row'))
    first_drop = min((it['ts'] for it in items if it['fate'] == 'dropped_by_hook'), default=None)
    rows = []
    for it in items:
        i = tid(it['text'])
        rows.append(dict(ts=it['ts'], task=i, agent=summ(it['text']), fate=it['fate'] or 'unresolved', pure=pure(it['text']),
                         waiting=(res(it['text']) or '').strip() == WAIT, wt='<worktree>' in it['text'], out=(re.search(r'<output-file>([^<]*)<', it['text']) or [None, None])[1],
                         hb=next((h for h in hb.get(i, []) if h > it['ts']), None), final=next((h for h in finals.get(i, []) if h > it['ts']), None),
                         killed=next((h for h in killed.get(i, []) if h > it['ts']), None), peer=len([p for p in peers.get(i, []) if p > it['ts']]),
                         after_first_drop=first_drop is not None and it['ts'] >= first_drop))
    if rows: allrows[f] = rows
json.dump({'rows': allrows, 'other': other_drops}, open(os.environ['AUDIT_OUT'] + '/drops.json', 'w'), indent=1)
drops = [(f, r) for f, rs in allrows.items() for r in rs if r['fate'] == 'dropped_by_hook']
print('interim drops:', len(drops), '| sessions:', len({f for f, _ in drops}), '| agents:', len({r['task'] for _, r in drops}), '| not pure:', sum(not r['pure'] for _, r in drops))
print('other dropped prompts:', len(other_drops)); [print('  ', o) for o in other_drops[:20]]
byagent = collections.OrderedDict()
for f, r in sorted(drops, key=lambda x: x[1]['ts']):
    k = (f, r['task']); byagent.setdefault(k, []).append(r)
print('\nper agent (session, agent, drops, first..last drop, hand-back after last drop, final, killed, peer msgs after first drop):')
for (f, i), rs in byagent.items():
    last = rs[-1]
    print(f'  {f.split("/")[-1][:8]} {i[:8]} {rs[0]["agent"][:44]:44} n={len(rs):2} {rs[0]["ts"][5:16]}..{last["ts"][11:16]} hb={str(last["hb"])[5:16]} final={str(last["final"])[5:16]} killed={str(last["killed"])[5:16]} peers={rs[0]["peer"]}')
print('\nwaiting placeholders that entered main after the session\'s first drop (missed drops):')
for f, rs in allrows.items():
    for r in rs:
        if r['after_first_drop'] and r['waiting'] and r['fate'] == 'entered':
            print(f'  {f.split("/")[-1][:8]} {r["ts"][5:19]} {r["task"][:8]} wt={r["wt"]} {r["agent"][:50]}')
