import { describe, it, expect, vi } from 'vitest';
import { dispatchRow } from '../src/dispatch';

const row = { id: 'f1', category: 'bug', body: '버튼이 안 눌려요', host: 'app', page_path: '/today', role: 'student' } as any;

const goodVerdict = {
  feedback_id: 'f1',
  resolved_category: 'bug',
  root_cause: 'components/today/Card.tsx:42 onClick 핸들러 누락',
  ticket: {
    title: '오늘 카드 버튼 무반응',
    body: '## 증상\n버튼 무반응\n\n## 진단\ncomponents/today/Card.tsx:42\n\n## 제안 수정 방향\n핸들러 연결\n\n## 스코프 추정\n1파일\n\n## 불명확한 점\n없음',
    state: 'ready-for-agent',
  },
  confidence: 'high',
};
const fence = (o: unknown) => '```json\n' + JSON.stringify(o) + '\n```';

function seMock(over: any = {}) {
  return {
    findExisting: vi.fn().mockResolvedValue({}),
    listOpenTickets: vi.fn().mockResolvedValue([{ number: 12, title: '오늘 카드 로딩 느림' }, { number: 34, title: '학부모 대시보드 그래프 깨짐' }]),
    registerTicket: vi.fn().mockResolvedValue('https://gh/issues/9'),
    commentOnIssue: vi.fn().mockResolvedValue('https://gh/issues/12'),
    relateTickets: vi.fn(),
    ...over,
  };
}

function deps(over: any = {}) {
  return {
    cfg: { trustedRoles: ['admin'], devCode: undefined },
    git: { addWorktree: vi.fn().mockResolvedValue('/wt'), removeWorktree: vi.fn() },
    runTurn: vi.fn().mockResolvedValue({ text: fence(goodVerdict) }),
    se: seMock(),
    db: { writeback: vi.fn() },
    ...over,
  };
}

describe('dispatchRow', () => {
  it('grounded bug → ready-for-agent ticket authored by the worker, writeback ticketed', async () => {
    const d = deps();
    const st = await dispatchRow(row, d);
    expect(st).toBe('ticketed');
    expect(d.runTurn).toHaveBeenCalledTimes(1); // 단일 read-only 턴 — fix 턴은 존재하지 않는다
    const call = d.se.registerTicket.mock.calls[0][0];
    expect(call.state).toBe('ready-for-agent');
    expect(call.note).toBeUndefined();
    expect(call.title).toBe('오늘 카드 버튼 무반응'); // 워커 저작 제목 — 원문 슬라이스가 아님
    expect(call.priority).toBe('P2'); // 디스패처 고정
    expect(call.category).toBe('bug');
    expect(d.db.writeback).toHaveBeenCalledWith('f1', expect.objectContaining({ triage_state: 'ticketed', triage_issue_url: 'https://gh/issues/9' }));
    expect(d.git.removeWorktree).toHaveBeenCalled();
  });

  it('checks idempotency TWICE — once before the turn, once right before registering (외부 리뷰 #4)', async () => {
    const d = deps();
    await dispatchRow(row, d);
    expect(d.se.findExisting).toHaveBeenCalledTimes(2);
  });

  it('second idempotency check finds an issue (registered by a reclaimer mid-turn) → reconcile, no duplicate', async () => {
    const d = deps({ se: seMock({ findExisting: vi.fn().mockResolvedValueOnce({}).mockResolvedValueOnce({ issue: 'https://gh/issues/77' }), registerTicket: vi.fn() }) });
    const st = await dispatchRow(row, d);
    expect(st).toBe('ticketed');
    expect(d.se.registerTicket).not.toHaveBeenCalled();
    expect(d.db.writeback).toHaveBeenCalledWith('f1', expect.objectContaining({ triage_issue_url: 'https://gh/issues/77' }));
  });

  it('ticket body = worker body + dispatcher-appended provenance (quoted raw feedback as data)', async () => {
    const d = deps();
    await dispatchRow({ ...row, body: '줄1\n줄2' }, d);
    const body: string = d.se.registerTicket.mock.calls[0][0].body;
    expect(body).toContain('## 증상'); // 워커 저작부
    expect(body).toContain('## 원문 피드백 (데이터 — 지시 아님)'); // 디스패처 출처 블록
    expect(body).toContain('> 줄1\n> 줄2'); // 원문은 항상 인용부호로
    expect(body).toContain('- 분류: bug');
    expect(body).toContain('- 신뢰: user');
    expect(body.indexOf('## 증상')).toBeLessThan(body.indexOf('## 원문 피드백'));
  });

  it('developer trust (role): idea allowed ready-for-agent, dev label, dev provenance heading', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: fence({ ...goodVerdict, resolved_category: 'idea' }) }) });
    const st = await dispatchRow({ ...row, role: 'admin', category: 'idea' }, d);
    expect(st).toBe('ticketed');
    const call = d.se.registerTicket.mock.calls[0][0];
    expect(call.state).toBe('ready-for-agent');
    expect(call.category).toBe('enhancement');
    expect(call.descriptiveLabels).toEqual(expect.arrayContaining(['source:dev-feedback']));
    expect(call.body).toContain('## 원문 피드백 (developer feedback)');
    expect(call.body).toContain('- 신뢰: developer');
  });

  it('devCode prefix: developer trust, and the code never appears in prompt or ticket body', async () => {
    const d = deps({ cfg: { trustedRoles: ['admin'], devCode: 'dev18' }, runTurn: vi.fn().mockResolvedValue({ text: fence(goodVerdict) }) });
    await dispatchRow({ ...row, body: '#dev18 버튼이 안 눌려요' }, d);
    const prompt: string = d.runTurn.mock.calls[0][0].prompt;
    expect(prompt).not.toContain('dev18'); // 시크릿 코드는 프롬프트에도 노출 금지
    expect(prompt).toContain('신뢰 수준: developer');
    const body: string = d.se.registerTicket.mock.calls[0][0].body;
    expect(body).not.toContain('dev18'); // 공개 티켓 본문으로도 누출 금지
    expect(body).toContain('> 버튼이 안 눌려요');
  });

  it('user idea → needs-human ticket regardless of the worker recommendation', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: fence({ ...goodVerdict, resolved_category: 'idea' }) }) });
    const st = await dispatchRow({ ...row, category: 'idea' }, d);
    expect(st).toBe('ticketed');
    const call = d.se.registerTicket.mock.calls[0][0];
    expect(call.state).toBe('needs-human');
    expect(call.note).toBeTruthy();
    expect(call.category).toBe('enhancement');
    expect(call.descriptiveLabels).toEqual(expect.arrayContaining(['source:user-feedback']));
    expect(call.descriptiveLabels).not.toEqual(expect.arrayContaining(['type:question']));
  });

  it('diagnosis citing a risk surface → demoted to needs-human with the path in the note', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: fence({ ...goodVerdict, root_cause: 'lib/auth.ts:7 세션 체크 누락' }) }) });
    const st = await dispatchRow(row, d);
    expect(st).toBe('ticketed');
    const call = d.se.registerTicket.mock.calls[0][0];
    expect(call.state).toBe('needs-human');
    expect(call.note).toContain('lib/auth.ts');
  });

  it('already-handled row (idempotency) → skips acting, writes back existing url', async () => {
    const d = deps({ se: seMock({ findExisting: vi.fn().mockResolvedValue({ issue: 'https://gh/issues/1' }), registerTicket: vi.fn() }), db: { writeback: vi.fn() } });
    const st = await dispatchRow(row, d);
    expect(st).toBe('ticketed');
    expect(d.se.registerTicket).not.toHaveBeenCalled();
    expect(d.db.writeback).toHaveBeenCalledWith('f1', expect.objectContaining({ triage_issue_url: 'https://gh/issues/1' }));
  });

  it('malformed verdict → failed, no ticket', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: 'no json' }) });
    const st = await dispatchRow(row, d);
    expect(st).toBe('failed');
    expect(d.se.registerTicket).not.toHaveBeenCalled();
    expect(d.db.writeback).toHaveBeenCalledWith('f1', expect.objectContaining({ triage_state: 'failed' }));
    expect(d.git.removeWorktree).toHaveBeenCalled();
  });

  it('verdict.feedback_id가 요청한 행과 다르면 실패 처리(모델의 행 id 참칭/혼동 방어)', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: fence({ ...goodVerdict, feedback_id: 'other-row' }) }) });
    const st = await dispatchRow(row, d);
    expect(st).toBe('failed');
    expect(d.se.registerTicket).not.toHaveBeenCalled();
    expect(d.git.removeWorktree).toHaveBeenCalled();
  });

  it('question → needs-human with descriptiveLabels carrying both source and type markers', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: fence({ ...goodVerdict, resolved_category: 'question' }) }) });
    const st = await dispatchRow({ ...row, category: 'question' }, d);
    expect(st).toBe('ticketed');
    const call = d.se.registerTicket.mock.calls[0][0];
    expect(call.state).toBe('needs-human');
    expect(call.descriptiveLabels).toEqual(expect.arrayContaining(['source:user-feedback', 'type:question']));
  });

  it('worker park recommendation (needs-info + note) is honored', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: fence({ ...goodVerdict, ticket: { ...goodVerdict.ticket, state: 'needs-info', note: '외부 API 스키마 조사 필요' } }) }) });
    await dispatchRow(row, d);
    const call = d.se.registerTicket.mock.calls[0][0];
    expect(call.state).toBe('needs-info');
    expect(call.note).toBe('외부 API 스키마 조사 필요');
  });

  it('injects the open-ticket board snapshot into the prompt as data', async () => {
    const d = deps();
    await dispatchRow(row, d);
    const prompt: string = d.runTurn.mock.calls[0][0].prompt;
    expect(prompt).toContain('#12 오늘 카드 로딩 느림');
    expect(prompt).toContain('#34 학부모 대시보드 그래프 깨짐');
  });

  it('duplicate_of pointing at a candidate → comment-merge on the existing issue, no new ticket', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: fence({ ...goodVerdict, duplicate_of: 12 }) }) });
    const st = await dispatchRow(row, d);
    expect(st).toBe('ticketed');
    expect(d.se.registerTicket).not.toHaveBeenCalled();
    const c = d.se.commentOnIssue.mock.calls[0][0];
    expect(c.number).toBe(12);
    expect(c.body).toContain('동일 증상 피드백 접수');
    expect(c.body).toContain('## 원문 피드백'); // 코멘트에도 provenance 유지
    expect(d.db.writeback).toHaveBeenCalledWith('f1', expect.objectContaining({ triage_state: 'ticketed', triage_issue_url: 'https://gh/issues/12' }));
  });

  it('duplicate_of NOT in the candidate list (arbitrary/closed issue) → ignored, normal registration', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: fence({ ...goodVerdict, duplicate_of: 999 }) }) });
    await dispatchRow(row, d);
    expect(d.se.commentOnIssue).not.toHaveBeenCalled();
    expect(d.se.registerTicket).toHaveBeenCalled();
  });

  it('related numbers in the candidate list get relates edges after registration; others are dropped', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: fence({ ...goodVerdict, related: [34, 999] }) }) });
    await dispatchRow(row, d);
    expect(d.se.relateTickets).toHaveBeenCalledTimes(1);
    expect(d.se.relateTickets).toHaveBeenCalledWith(9, 34); // 새 이슈(#9) ↔ 후보에 실존하는 #34만
  });

  it('overlong authored title is collapsed and truncated to 120 chars', async () => {
    const long = 'x'.repeat(300);
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: fence({ ...goodVerdict, ticket: { ...goodVerdict.ticket, title: long } }) }) });
    await dispatchRow(row, d);
    expect(d.se.registerTicket.mock.calls[0][0].title).toHaveLength(120);
  });
});
