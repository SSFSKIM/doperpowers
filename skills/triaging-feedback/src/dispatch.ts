import type { FeedbackRow, TriageState } from './types';
import { preRoute } from './route';
import { parseVerdict } from './verdict';
import { enforceGate } from './gate';
import { renderTriagePrompt, renderFixPrompt } from './prompt';

export interface Deps {
  cfg: { fixEnabled: boolean; baseBranch: string };
  git: {
    addWorktree(feedbackId: string): Promise<string>;
    removeWorktree(wt: string): Promise<void>;
    diffStat(wt: string): Promise<{ files: string[]; lines: number }>;
    buildAndTest(wt: string): Promise<boolean>;
  };
  runTurn(o: { worktree: string; prompt: string; sandbox: 'read_only' | 'workspace_write'; thread?: unknown }): Promise<{ text: string; thread: unknown }>;
  se: {
    findExisting(id: string): Promise<{ pr?: string; issue?: string }>;
    openFixPr(a: { feedbackId: string; worktree: string; branch: string; title: string; body: string }): Promise<string>;
    registerTicket(a: { feedbackId: string; title: string; category: 'bug' | 'enhancement'; priority: 'P0'|'P1'|'P2'|'P3'; body: string; reason: string; descriptiveLabels?: string[] }): Promise<string>;
  };
  db: { writeback(id: string, patch: { triage_state: TriageState; triage_pr_url?: string; triage_issue_url?: string }): Promise<void> };
}

export async function dispatchRow(row: FeedbackRow, d: Deps): Promise<TriageState> {
  // 멱등 가드: 이미 이 피드백으로 만든 아티팩트가 있으면 재실행하지 않는다.
  const existing = await d.se.findExisting(row.id);
  if (existing.pr) { await d.db.writeback(row.id, { triage_state: 'fixed', triage_pr_url: existing.pr }); return 'fixed'; }
  if (existing.issue) { await d.db.writeback(row.id, { triage_state: 'ticketed', triage_issue_url: existing.issue }); return 'ticketed'; }

  const wt = await d.git.addWorktree(row.id);
  try {
    // turn 1: read_only 진단 (body = untrusted data)
    const { text, thread } = await d.runTurn({ worktree: wt, prompt: renderTriagePrompt(row), sandbox: 'read_only' });
    const verdict = parseVerdict(text);
    if (!verdict) { await d.db.writeback(row.id, { triage_state: 'failed' }); return 'failed'; }

    const wantsFix = d.cfg.fixEnabled && preRoute(row.category) === 'diagnose' && verdict.route === 'fix';
    if (!wantsFix) {
      const url = await d.se.registerTicket({ feedbackId: row.id, title: ticketTitle(row), category: row.category === 'bug' ? 'bug' : 'enhancement', priority: 'P2', body: ticketBody(row, verdict.root_cause), reason: verdict.reason_if_ticket ?? '자동 수정 대상 아님', descriptiveLabels: descriptiveLabels(row) });
      await d.db.writeback(row.id, { triage_state: 'ticketed', triage_issue_url: url });
      return 'ticketed';
    }

    // turn 2: workspace_write 수정
    await d.runTurn({ worktree: wt, prompt: renderFixPrompt(row, verdict), sandbox: 'workspace_write', thread });
    const stat = await d.git.diffStat(wt);
    const testsPassed = await d.git.buildAndTest(wt);
    const gate = enforceGate({ resolvedCategory: verdict.resolved_category, changedFiles: stat.files, diffLines: stat.lines, testsPassed, rootCauseCited: /\S+:\d+/.test(verdict.root_cause) });

    if (!gate.pass) {
      const url = await d.se.registerTicket({ feedbackId: row.id, title: ticketTitle(row), category: 'bug', priority: 'P2', body: ticketBody(row, verdict.root_cause), reason: gate.reason!, descriptiveLabels: descriptiveLabels(row) });
      await d.db.writeback(row.id, { triage_state: 'ticketed', triage_issue_url: url });
      return 'ticketed';
    }

    const branch = `fix/feedback-${row.id.slice(0, 8)}`;
    const pr = await d.se.openFixPr({ feedbackId: row.id, worktree: wt, branch, title: `fix(feedback): ${ticketTitle(row)}`, body: ticketBody(row, verdict.root_cause) });
    await d.db.writeback(row.id, { triage_state: 'fixed', triage_pr_url: pr });
    return 'fixed';
  } finally {
    await d.git.removeWorktree(wt);
  }
}

function descriptiveLabels(row: FeedbackRow): string[] {
  return ['source:user-feedback', ...(row.category === 'question' ? ['type:question'] : [])];
}

function ticketTitle(row: FeedbackRow): string {
  return row.body.replace(/\s+/g, ' ').trim().slice(0, 60);
}
function ticketBody(row: FeedbackRow, diagnosis: string): string {
  return [`> ${row.body}`, '', `- 분류: ${row.category}`, `- 제출자 role: ${row.role ?? '-'}`, `- host: ${row.host ?? '-'}`, `- page: ${row.page_path ?? '-'}`, '', `**진단:** ${diagnosis}`].join('\n');
}
