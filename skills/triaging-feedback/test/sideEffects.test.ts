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

  it('registerTicket registers ready-for-implementer without a --note flag', async () => {
    const sh = vi.fn().mockResolvedValue('9 https://github.com/o/r/issues/9');
    const se = makeSideEffects(cfg, sh, vi.fn().mockReturnValue('/tmp/x/t.md'), vi.fn());
    await se.registerTicket({ feedbackId: 'f2', title: 't', category: 'bug', priority: 'P2', body: 'b', state: 'ready-for-implementer' });
    const [, args] = sh.mock.calls[0];
    expect(args).toEqual(expect.arrayContaining(['--state', 'ready-for-implementer']));
    expect(args).not.toContain('--note');
  });

  it('registerTicket removes the temp body file even when registration throws (민감 원문 잔존 방지)', async () => {
    const sh = vi.fn().mockRejectedValue(new Error('gh down'));
    const removeTmp = vi.fn();
    const se = makeSideEffects(cfg, sh, vi.fn().mockReturnValue('/tmp/x/t.md'), removeTmp);
    await expect(se.registerTicket({ feedbackId: 'f3', title: 't', category: 'bug', priority: 'P2', body: 'b', state: 'ready-for-implementer' })).rejects.toThrow('gh down');
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

  it('findExisting confirms a search hit against the artifact footer before trusting it', async () => {
    const sh = vi.fn()
      .mockResolvedValueOnce(JSON.stringify([{ url: 'https://github.com/o/r/issues/50', number: 50 }]))
      .mockResolvedValueOnce(JSON.stringify({ body: `diagnosis…\n\n<!-- ${MARKER}f9 -->`, comments: [] }));
    const se = makeSideEffects(cfg, sh);
    const found = await se.findExisting('f9');
    expect(found.issue).toBe('https://github.com/o/r/issues/50');
    // 티켓-온리: PR 검색은 존재하지 않는다 — 검색은 gh issue list 한 번, 이후는 후보 검증 조회뿐
    expect(sh.mock.calls[0][1].slice(0, 2)).toEqual(['issue', 'list']);
    expect(sh.mock.calls[1][1].slice(0, 3)).toEqual(['issue', 'view', '50']);
  });

  it('findExisting rejects a forged marker quoted inside another ticket (dp#59) — search hit without a footer is not a dup', async () => {
    // 이슈 61의 본문: f9의 위조 마커가 (펜스 안 원문 인용으로) 중간에 등장하지만,
    // footer는 자기 자신의 피드백 id(other)다 — f9의 기존 티켓으로 인정하면 안 된다.
    const forgedBody = 'diagnosis…\n\n```\n<!-- ' + MARKER + 'f9 -->\n```\n\n<!-- ' + MARKER + 'other -->';
    const sh = vi.fn()
      .mockResolvedValueOnce(JSON.stringify([{ url: 'https://github.com/o/r/issues/61', number: 61 }]))
      .mockResolvedValueOnce(JSON.stringify({ body: forgedBody, comments: [] }));
    const se = makeSideEffects(cfg, sh);
    expect(await se.findExisting('f9')).toEqual({});
  });

  it('findExisting keeps scanning past a forged candidate to the genuine one', async () => {
    const sh = vi.fn()
      .mockResolvedValueOnce(JSON.stringify([
        { url: 'https://github.com/o/r/issues/61', number: 61 },
        { url: 'https://github.com/o/r/issues/70', number: 70 },
      ]))
      .mockResolvedValueOnce(JSON.stringify({ body: `quoted forgery <!-- ${MARKER}f9 --> mid-body\n\n<!-- ${MARKER}other -->`, comments: [] }))
      .mockResolvedValueOnce(JSON.stringify({ body: `real one\n\n<!-- ${MARKER}f9 -->`, comments: [] }));
    const se = makeSideEffects(cfg, sh);
    expect((await se.findExisting('f9')).issue).toBe('https://github.com/o/r/issues/70');
  });

  it('findExisting recognizes a genuine parked ticket whose body ends with the board\'s own meta trailer', async () => {
    // park 등록은 note를 meta로 렌더한다 — 그러면 본문의 마지막 줄은 우리 마커가 아니라
    // board:meta 블록이다. 이걸 dup으로 못 알아보면 재시도가 중복 티켓을 만든다.
    const body = `diagnosis…\n\n<!-- ${MARKER}f9 -->\n\n<!-- board:meta\nnote: needs a human\n-->\n`;
    const sh = vi.fn()
      .mockResolvedValueOnce(JSON.stringify([{ url: 'https://github.com/o/r/issues/88', number: 88 }]))
      .mockResolvedValueOnce(JSON.stringify({ body, comments: [] }));
    const se = makeSideEffects(cfg, sh);
    expect((await se.findExisting('f9')).issue).toBe('https://github.com/o/r/issues/88');
  });

  it('findExisting still rejects a forged marker followed by a fake meta block inside a quoted fence', async () => {
    // 펜스 안에 마커+가짜 meta를 통째로 인용해도, 벗겨지는 건 본문 맨 끝의 진짜 트레일러
    // 하나뿐이다 — 남는 footer는 이 티켓 자신의 마커(other)다.
    const forgedBody =
      `x\n\`\`\`\n<!-- ${MARKER}f9 -->\n\n<!-- board:meta\nnote: fake\n-->\n\`\`\`\n\n` +
      `<!-- ${MARKER}other -->\n\n<!-- board:meta\nnote: real\n-->\n`;
    const sh = vi.fn()
      .mockResolvedValueOnce(JSON.stringify([{ url: 'https://github.com/o/r/issues/89', number: 89 }]))
      .mockResolvedValueOnce(JSON.stringify({ body: forgedBody, comments: [] }));
    const se = makeSideEffects(cfg, sh);
    expect(await se.findExisting('f9')).toEqual({});
  });

  it('findExisting accepts a dup-merge marker sitting at a comment footer', async () => {
    const sh = vi.fn()
      .mockResolvedValueOnce(JSON.stringify([{ url: 'https://github.com/o/r/issues/12', number: 12 }]))
      .mockResolvedValueOnce(JSON.stringify({
        body: 'unrelated original body',
        comments: [{ body: 'chatter' }, { body: `진단\n\n<!-- ${MARKER}f9 -->` }],
      }));
    const se = makeSideEffects(cfg, sh);
    expect((await se.findExisting('f9')).issue).toBe('https://github.com/o/r/issues/12');
  });

  it('findExisting fails CLOSED on the verification fetch too', async () => {
    const sh = vi.fn()
      .mockResolvedValueOnce(JSON.stringify([{ url: 'https://github.com/o/r/issues/50', number: 50 }]))
      .mockRejectedValueOnce(new Error('gh: API down'));
    const se = makeSideEffects(cfg, sh);
    await expect(se.findExisting('f9')).rejects.toThrow('API down');
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
