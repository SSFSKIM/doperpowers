import { describe, it, expect, vi } from 'vitest';
import { dispatchRow } from '../src/dispatch';

const row = { id: 'f1', category: 'bug', body: '버튼이 안 눌려요', host: 'app', page_path: '/today', role: 'student' } as any;

function deps(over: any = {}) {
  return {
    cfg: { fixEnabled: true, baseBranch: 'feat/m4.5-polish' } as any,
    git: { addWorktree: vi.fn().mockResolvedValue('/wt'), removeWorktree: vi.fn(), diffStat: vi.fn().mockResolvedValue({ files: ['components/x.tsx'], lines: 10 }), buildAndTest: vi.fn().mockResolvedValue(true) },
    runTurn: vi.fn()
      .mockResolvedValueOnce({ text: '```json\n{"feedback_id":"f1","resolved_category":"bug","route":"fix","root_cause":"x.tsx:3 핸들러 누락","confidence":"high"}\n```' })
      .mockResolvedValueOnce({ text: 'applied' }),
    se: { findExisting: vi.fn().mockResolvedValue({}), openFixPr: vi.fn().mockResolvedValue('https://gh/pull/9'), registerTicket: vi.fn().mockResolvedValue('https://gh/issues/9') },
    db: { writeback: vi.fn() },
    ...over,
  };
}

describe('dispatchRow', () => {
  it('bug that passes the gate → fix PR, writeback fixed', async () => {
    const d = deps();
    const st = await dispatchRow(row, d);
    expect(st).toBe('fixed');
    expect(d.se.openFixPr).toHaveBeenCalled();
    expect(d.db.writeback).toHaveBeenCalledWith('f1', expect.objectContaining({ triage_state: 'fixed', triage_pr_url: 'https://gh/pull/9' }));
    expect(d.git.removeWorktree).toHaveBeenCalled();
  });

  it('idea → ticket without ever raising the sandbox', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: '```json\n{"feedback_id":"f1","resolved_category":"idea","route":"ticket","root_cause":"기능 요청","confidence":"low"}\n```' }) });
    const st = await dispatchRow({ ...row, category: 'idea' }, d);
    expect(st).toBe('ticketed');
    // only the read_only diagnosis turn ran; no workspace_write
    expect(d.runTurn).toHaveBeenCalledTimes(1);
    expect(d.runTurn).toHaveBeenCalledWith(expect.objectContaining({ sandbox: 'read_only' }));
    expect(d.se.registerTicket).toHaveBeenCalled();
    const call = d.se.registerTicket.mock.calls[0][0];
    expect(call.descriptiveLabels).toEqual(expect.arrayContaining(['source:user-feedback']));
    expect(call.descriptiveLabels).not.toEqual(expect.arrayContaining(['type:question']));
  });

  it('bug whose fix touches a risk surface → ticket, not PR', async () => {
    const d = deps({ git: { addWorktree: vi.fn().mockResolvedValue('/wt'), removeWorktree: vi.fn(), diffStat: vi.fn().mockResolvedValue({ files: ['lib/auth.ts'], lines: 5 }), buildAndTest: vi.fn().mockResolvedValue(true) } });
    const st = await dispatchRow(row, d);
    expect(st).toBe('ticketed');
    expect(d.se.openFixPr).not.toHaveBeenCalled();
    expect(d.se.registerTicket).toHaveBeenCalledWith(expect.objectContaining({ reason: expect.stringContaining('lib/auth.ts') }));
  });

  it('TRIAGE_FIX_ENABLED=false → bug becomes a ticket', async () => {
    const d = deps({ cfg: { fixEnabled: false, baseBranch: 'b' } });
    const st = await dispatchRow(row, d);
    expect(st).toBe('ticketed');
    expect(d.se.openFixPr).not.toHaveBeenCalled();
  });

  it('already-handled row (idempotency) → skips acting, writes back existing url', async () => {
    const d = deps({ se: { findExisting: vi.fn().mockResolvedValue({ pr: 'https://gh/pull/1' }), openFixPr: vi.fn(), registerTicket: vi.fn() }, db: { writeback: vi.fn() } });
    const st = await dispatchRow(row, d);
    expect(st).toBe('fixed');
    expect(d.se.openFixPr).not.toHaveBeenCalled();
    expect(d.db.writeback).toHaveBeenCalledWith('f1', expect.objectContaining({ triage_pr_url: 'https://gh/pull/1' }));
  });

  it('verdict.feedback_id가 요청한 행과 다르면 실패 처리(모델의 행 id 참칭/혼동 방어)', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: '```json\n{"feedback_id":"other-row","resolved_category":"bug","route":"fix","root_cause":"x.tsx:3","confidence":"high"}\n```' }) });
    const st = await dispatchRow(row, d);
    expect(st).toBe('failed');
    expect(d.db.writeback).toHaveBeenCalledWith('f1', expect.objectContaining({ triage_state: 'failed' }));
    expect(d.runTurn).toHaveBeenCalledTimes(1); // write 턴은 절대 열리지 않는다
    expect(d.se.openFixPr).not.toHaveBeenCalled();
    expect(d.se.registerTicket).not.toHaveBeenCalled();
    expect(d.git.removeWorktree).toHaveBeenCalled();
  });

  it('question → ticket with descriptiveLabels carrying both source and type markers', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: '```json\n{"feedback_id":"f1","resolved_category":"question","route":"ticket","root_cause":"사용법 문의","confidence":"low"}\n```' }) });
    const st = await dispatchRow({ ...row, category: 'question' }, d);
    expect(st).toBe('ticketed');
    expect(d.se.registerTicket).toHaveBeenCalledWith(expect.objectContaining({
      descriptiveLabels: expect.arrayContaining(['source:user-feedback', 'type:question']),
    }));
  });
});
