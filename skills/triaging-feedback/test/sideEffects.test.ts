import { describe, it, expect, vi } from 'vitest';
import { makeSideEffects, MARKER } from '../src/sideEffects';

const cfg: any = { repoPath: '/repo', baseBranch: 'feat/m4.5-polish', boardScriptsDir: '/board' };

describe('sideEffects', () => {
  it('registerTicket calls board-register.sh with the routed park state + note + --body-file, marker in the body, cwd=repoPath', async () => {
    const sh = vi.fn().mockResolvedValue('142 https://github.com/o/r/issues/142');
    const writeTmp = vi.fn().mockReturnValue('/tmp/triage-f9.md');
    const se = makeSideEffects(cfg, sh, writeTmp);
    const url = await se.registerTicket({ feedbackId: 'f9', title: '제목', category: 'enhancement', priority: 'P2', body: '본문', state: 'needs-human', note: '사람 판단 필요' });
    expect(url).toContain('/issues/142');
    const [cmd, args, cwd] = sh.mock.calls[0];
    expect(cmd).toBe('/board/board-register.sh');
    expect(args).toEqual(expect.arrayContaining(['제목', 'enhancement', 'P2', '--state', 'needs-human', '--note', '사람 판단 필요', '--body-file', '/tmp/triage-f9.md']));
    expect(cwd).toBe('/repo');
    // 마커는 임시파일에 쓴 본문에 들어가야 findExisting이 나중에 dedup 가능
    const [, content] = writeTmp.mock.calls[0];
    expect(content).toContain(`${MARKER}f9`);
  });

  it('registerTicket registers ready-for-agent without a --note flag', async () => {
    const sh = vi.fn().mockResolvedValue('9 https://github.com/o/r/issues/9');
    const writeTmp = vi.fn().mockReturnValue('/tmp/triage-f2.md');
    const se = makeSideEffects(cfg, sh, writeTmp);
    await se.registerTicket({ feedbackId: 'f2', title: 't', category: 'bug', priority: 'P2', body: 'b', state: 'ready-for-agent' });
    const [, args] = sh.mock.calls[0];
    expect(args).toEqual(expect.arrayContaining(['--state', 'ready-for-agent']));
    expect(args).not.toContain('--note');
  });

  it('registerTicket adds descriptive labels via gh issue edit (non-status labels)', async () => {
    const sh = vi.fn().mockResolvedValue('7 https://github.com/o/r/issues/7');
    const writeTmp = vi.fn().mockReturnValue('/tmp/triage-q.md');
    const se = makeSideEffects(cfg, sh, writeTmp);
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
});
