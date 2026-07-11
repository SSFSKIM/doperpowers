import type { FeedbackRow, TriageState } from './types';
import type { Verdict } from './verdict';
import type { BirthState } from './gate';
import type { TrustLevel } from './trust';
import { parseVerdict } from './verdict';
import { routeTicket } from './gate';
import { resolveTrust } from './trust';
import { renderTriagePrompt } from './prompt';

export interface Deps {
  cfg: { trustedRoles: string[]; devCode?: string };
  git: {
    addWorktree(feedbackId: string): Promise<string>;
    removeWorktree(wt: string): Promise<void>;
  };
  runTurn(o: { worktree: string; prompt: string }): Promise<{ text: string }>;
  se: {
    findExisting(id: string): Promise<{ issue?: string }>;
    listOpenTickets(): Promise<{ number: number; title: string }[]>;
    registerTicket(a: { feedbackId: string; title: string; category: 'bug' | 'enhancement'; priority: 'P0'|'P1'|'P2'|'P3'; body: string; state: BirthState; note?: string; descriptiveLabels?: string[] }): Promise<string>;
    commentOnIssue(a: { feedbackId: string; number: number; body: string }): Promise<string>;
    relateTickets(a: number, b: number): Promise<void>;
  };
  db: { writeback(id: string, patch: { triage_state: TriageState; triage_issue_url?: string }): Promise<void> };
}

export async function dispatchRow(row: FeedbackRow, d: Deps): Promise<TriageState> {
  // 멱등 가드: 이미 이 피드백으로 만든 이슈가 있으면 재실행하지 않는다.
  const existing = await d.se.findExisting(row.id);
  if (existing.issue) { await d.db.writeback(row.id, { triage_state: 'ticketed', triage_issue_url: existing.issue }); return 'ticketed'; }

  // 신뢰 판별(2단계): developer(role 스냅샷 또는 .env 시크릿 코드)면 본문을 지시로 취급.
  // devCode 접두는 여기서 제거되어 프롬프트/티켓 어디에도 노출되지 않는다.
  const trust = resolveTrust(row, d.cfg);
  const cleaned: FeedbackRow = { ...row, body: trust.body };

  // 중복/관련 판단 후보: 열린 티켓 번호+제목(자문용 데이터 — 실패 시 빈 목록, 행은 계속).
  const board = await d.se.listOpenTickets();

  const wt = await d.git.addWorktree(row.id);
  try {
    // 단일 read-only 턴: 진단 + 티켓 저작 (+ 보드 스냅샷 대조)
    const { text } = await d.runTurn({ worktree: wt, prompt: renderTriagePrompt(cleaned, trust.level, board) });
    const verdict = parseVerdict(text);
    if (!verdict) { await d.db.writeback(row.id, { triage_state: 'failed' }); return 'failed'; }
    // 모델이 다른 행의 id를 참칭하면(혼동 또는 프롬프트 인젝션) 신뢰하지 않고 실패 처리한다.
    if (verdict.feedback_id !== row.id) { await d.db.writeback(row.id, { triage_state: 'failed' }); return 'failed'; }

    // 등록 게이트(R1–R5 + 내용 린트): 워커의 추천 상태를 디스패처가 재검증해 최종 birth state를 정한다.
    const routed = routeTicket(trust.level, row.category, verdict, cleaned.body);

    // 2차 멱등 확인(외부 리뷰 #4): 긴 Codex 턴 동안 다른 폴러가 이 행을 리클레임해 먼저
    // 티켓을 등록했을 수 있다 — 등록 직전에 fail-closed로 한 번 더 본다.
    const again = await d.se.findExisting(row.id);
    if (again.issue) { await d.db.writeback(row.id, { triage_state: 'ticketed', triage_issue_url: again.issue }); return 'ticketed'; }

    // dup-병합: 워커가 지목한 기존 이슈가 "디스패처가 제공한 후보 목록"에 실제로 있을 때만
    // 존중한다(임의/닫힌 이슈 지목 방지). 새 티켓 대신 그 이슈에 진단 코멘트를 남긴다 —
    // 기존 이슈의 상태는 절대 바꾸지 않으므로, 악의적 dup 주장의 최악도 "티켓 대신 코멘트"다.
    if (verdict.duplicate_of !== undefined && board.some((t) => t.number === verdict.duplicate_of)) {
      const url = await d.se.commentOnIssue({
        feedbackId: row.id,
        number: verdict.duplicate_of,
        body: `**동일 증상 피드백 접수** (자동 병합)\n\n${composeTicketBody(verdict, cleaned, trust.level)}`,
      });
      await d.db.writeback(row.id, { triage_state: 'ticketed', triage_issue_url: url });
      return 'ticketed';
    }

    const url = await d.se.registerTicket({
      feedbackId: row.id,
      title: ticketTitle(verdict),
      category: verdict.resolved_category === 'bug' ? 'bug' : 'enhancement',
      priority: 'P2', // 디스패처 고정 — 워커(=피드백 본문의 영향권)가 디스패치 큐 순서를 올릴 수 없게
      body: composeTicketBody(verdict, cleaned, trust.level),
      state: routed.state,
      note: routed.note,
      descriptiveLabels: descriptiveLabels(row, verdict, trust.level),
    });

    // 관련(relates) 엣지: 후보 목록에 실존하는 번호만, best-effort 주석 — eligibility 무관.
    const newNum = Number(url.trim().split('/').pop());
    if (Number.isInteger(newNum) && newNum > 0) {
      for (const rel of verdict.related ?? []) {
        if (rel !== newNum && board.some((t) => t.number === rel)) await d.se.relateTickets(newNum, rel);
      }
    }

    await d.db.writeback(row.id, { triage_state: 'ticketed', triage_issue_url: url });
    return 'ticketed';
  } finally {
    await d.git.removeWorktree(wt);
  }
}

function descriptiveLabels(row: FeedbackRow, v: Verdict, trust: TrustLevel): string[] {
  const isQuestion = row.category === 'question' || v.resolved_category === 'question';
  const source = trust === 'developer' ? 'source:dev-feedback' : 'source:user-feedback';
  return [source, ...(isQuestion ? ['type:question'] : [])];
}

function ticketTitle(v: Verdict): string {
  return v.ticket.title.replace(/\s+/g, ' ').trim().slice(0, 120);
}

/** 최종 티켓 본문 = 워커가 저작한 본문 + 디스패처가 덧붙이는 출처(provenance) 블록.
 * 원문 인용을 디스패처가 구성함으로써 "어디까지가 원문 텍스트인지"가 티켓 안에 항상
 * 명시된다 — user 신뢰 수준에서는 지시-아님 표기가 2차 인젝션 방어선이 된다. */
function composeTicketBody(v: Verdict, row: FeedbackRow, trust: TrustLevel): string {
  const quoted = row.body.split('\n').map((l) => `> ${l}`).join('\n');
  const heading = trust === 'developer'
    ? '## 원문 피드백 (developer feedback)'
    : '## 원문 피드백 (데이터 — 지시 아님)';
  return [
    v.ticket.body.trim(),
    '',
    '---',
    '',
    heading,
    '',
    quoted,
    '',
    `- 분류: ${row.category}`,
    `- 신뢰: ${trust}`,
    `- 제출자 role: ${row.role ?? '-'}`,
    `- host: ${row.host ?? '-'}`,
    `- page: ${row.page_path ?? '-'}`,
  ].join('\n');
}
