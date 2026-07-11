import { describe, it, expect, vi } from 'vitest';
import { makeSideEffects, MARKER } from '../src/sideEffects';

const cfg: any = { repoPath: '/repo', baseBranch: 'feat/m4.5-polish', boardScriptsDir: '/board' };

describe('sideEffects', () => {
  it('registerTicket calls board-register.sh with the routed park state + note + --body-file, marker in the body, cwd=repoPath', async () => {
    const sh = vi.fn().mockResolvedValue('142 https://github.com/o/r/issues/142');
    const writeTmp = vi.fn().mockReturnValue('/tmp/xyz/triage-f9.md');
    const removeTmp = vi.fn();
    const se = makeSideEffects(cfg, sh, writeTmp, removeTmp);
    const url = await se.registerTicket({ feedbackId: 'f9', title: '제목', category: 'enhancement', priority: 'P2', body: '본문', state: 'needs-human', note: '사람 판단 필요' });
    expect(url).toContain('/issues/142');
    const [cmd, args, cwd] = sh.mock.calls[0];
    expect(cmd).toBe('/board/board-register.sh');
    expect(args).toEqual(expect.arrayContaining(['제목', 'enhancement', 'P2', '--state', 'needs-human', '--note', '사람 판단 필요', '--body-file', '/tmp/xyz/triage-f9.md']));
    expect(cwd).toBe('/repo');
    // 마커는 임시파일에 쓴 본문에 들어가야 findExisting이 나중에 dedup 가능
    const [, content] = writeTmp.mock.calls[0];
    expect(content).toContain(`${MARKER}f9`);
  });

  it('registerTicket registers ready-for-agent without a --note flag', async () => {
    const sh = vi.fn().mockResolvedValue('9 https://github.com/o/r/issues/9');
    const se = makeSideEffects(cfg, sh, vi.fn().mockReturnValue('/tmp/x/t.md'), vi.fn());
    await se.registerTicket({ feedbackId: 'f2', title: 't', category: 'bug', priority: 'P2', body: 'b', state: 'ready-for-agent' });
    const [, args] = sh.mock.calls[0];
    expect(args).toEqual(expect.arrayContaining(['--state', 'ready-for-agent']));
    expect(args).not.toContain('--note');
  });

  it('registerTicket removes the temp body file even when registration throws (민감 원문 잔존 방지)', async () => {
    const sh = vi.fn().mockRejectedValue(new Error('gh down'));
    const removeTmp = vi.fn();
    const se = makeSideEffects(cfg, sh, vi.fn().mockReturnValue('/tmp/x/t.md'), removeTmp);
    await expect(se.registerTicket({ feedbackId: 'f3', title: 't', category: 'bug', priority: 'P2', body: 'b', state: 'ready-for-agent' })).rejects.toThrow('gh down');
    expect(removeTmp).toHaveBeenCalledWith('/tmp/x/t.md');
  });

  it('registerTicket adds descriptive labels via gh issue edit (non-status labels)', async () => {
    const sh = vi.fn().mockResolvedValue('7 https://github.com/o/r/issues/7');
    const se = makeSideEffects(cfg, sh, vi.fn().mockReturnValue('/tmp/x/q.md'), vi.fn());
    await se.registerTicket({ feedbackId: 'q', title: 't', category: 'enhancement', priority: 'P2', body: 'b', state: 'needs-human', note: 'r', descriptiveLabels: ['source:user-feedback', 'type:question'] });
    const editCall = sh.mock.calls.find((c: any[]) => c[1]?.[0] === 'issue' && c[1]?.[1] === 'edit');
    expect(editCall).toBeTruthy();
    expect(editCall![1]).toEqual(expect.arrayContaining(['issue', 'edit', '7', '--add-label', 'source:user-feedback,type:question']));
    expect(editCall![2]).toBe('/repo');
  });

  it('findExisting parses a prior issue by marker search', async () => {
    const sh = vi.fn().mockResolvedValue(JSON.stringify([{ url: 'https://github.com/o/r/issues/50' }]));
    const se = makeSideEffects(cfg, sh);
    const found = await se.findExisting('f9');
    expect(found.issue).toBe('https://github.com/o/r/issues/50');
    // 티켓-온리: PR 검색은 존재하지 않는다 — gh issue list 한 번만 호출
    expect(sh).toHaveBeenCalledTimes(1);
    expect(sh.mock.calls[0][1].slice(0, 2)).toEqual(['issue', 'list']);
  });

  it('findExisting fails CLOSED on gh search errors — a transient outage must not create duplicates (외부 리뷰 #5)', async () => {
    const sh = vi.fn().mockRejectedValue(new Error('gh: API rate limit'));
    const se = makeSideEffects(cfg, sh);
    await expect(se.findExisting('f9')).rejects.toThrow('rate limit');
  });

  it('findExisting searches comments too — dup-merge leaves its marker in a comment, not an issue body', async () => {
    const sh = vi.fn().mockResolvedValue('[]');
    const se = makeSideEffects(cfg, sh);
    await se.findExisting('f9');
    const q = sh.mock.calls[0][1][sh.mock.calls[0][1].indexOf('--search') + 1];
    expect(q).toContain('in:body,comments');
  });

  it('listOpenTickets returns number+title candidates, fails OPEN to [] (advisory feature)', async () => {
    const ok = makeSideEffects(cfg, vi.fn().mockResolvedValue(JSON.stringify([{ number: 12, title: 't' }])));
    expect(await ok.listOpenTickets()).toEqual([{ number: 12, title: 't' }]);
    const down = makeSideEffects(cfg, vi.fn().mockRejectedValue(new Error('gh down')));
    expect(await down.listOpenTickets()).toEqual([]);
  });

  it('commentOnIssue embeds the marker, strips the comment fragment from the returned URL, cleans up tmp', async () => {
    const sh = vi.fn().mockResolvedValue('https://github.com/o/r/issues/12#issuecomment-555\n');
    const writeTmp = vi.fn().mockReturnValue('/tmp/x/c.md');
    const removeTmp = vi.fn();
    const se = makeSideEffects(cfg, sh, writeTmp, removeTmp);
    const url = await se.commentOnIssue({ feedbackId: 'f9', number: 12, body: '진단' });
    expect(url).toBe('https://github.com/o/r/issues/12');
    expect(writeTmp.mock.calls[0][1]).toContain(`${MARKER}f9`);
    expect(sh.mock.calls[0][1].slice(0, 3)).toEqual(['issue', 'comment', '12']);
    expect(removeTmp).toHaveBeenCalledWith('/tmp/x/c.md');
  });

  it('relateTickets calls board-relate.sh best-effort (failure swallowed)', async () => {
    const sh = vi.fn().mockRejectedValue(new Error('meta lock'));
    const se = makeSideEffects(cfg, sh);
    await expect(se.relateTickets(9, 34)).resolves.toBeUndefined();
    expect(sh).toHaveBeenCalledWith('/board/board-relate.sh', ['9', '34'], '/repo');
  });
});
