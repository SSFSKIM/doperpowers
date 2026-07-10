import type { FeedbackCategory } from './types';
import type { Verdict } from './verdict';

export type ResolvedCategory = 'bug' | 'idea' | 'question' | 'other';
export type BirthState = 'ready-for-agent' | 'needs-human' | 'needs-info';

// spec R3 — ida-solution 골든룰에서 그대로 옮긴 리스크 표면. 인용된 경로가 하나라도 닿으면
// ready-for-agent 불가(needs-human 강등) — 사람 판단 없이 에이전트가 만지면 안 되는 영역.
export const RISK_SURFACES: RegExp[] = [
  /^lib\/auth\.ts$/, /^middleware\.ts$/,                    // auth/RLS
  /^lib\/schema\.sql$/, /^sql\/.*\.sql$/, /^types\/index\.ts$/, // migrations/schema/mirror
  /^app\/api\/ai\/generate-plan\/route\.ts$/,               // generate-plan 타임테이블 레이아웃
  /^lib\/exam-bank\.ts$/,                                    // exam-bank 저작권
  /^lib\/exam-calendar\.ts$/, /^lib\/grade-system\.ts$/,    // D-day/등급 진실
  /^lib\/anthropic\.ts$/,                                    // 서버 전용 LLM/시크릿
  /^app\/api\/cron\//, /^vercel\.json$/,                    // cron
];

export function touchesRiskSurface(paths: string[]): string | null {
  for (const p of paths) if (RISK_SURFACES.some((re) => re.test(p))) return p;
  return null;
}

/** 자유 텍스트(root_cause·티켓 본문)에서 경로 후보 토큰을 추출한다.
 * 워커의 자기 보고 목록을 믿는 대신 디스패처가 텍스트를 직접 스캔한다(R3) —
 * `file.ts:12` 꼴 인용은 :line 꼬리를 벗겨 경로만 남긴다. 과잉 추출(산문 속 경로 언급)은
 * needs-human 강등이라는 안전한 방향의 오탐이므로 허용한다. */
export function extractCandidatePaths(text: string): string[] {
  const tokens = text.match(/[\w@./-]+/g) ?? [];
  return tokens
    .map((t) => t.replace(/:\d+(?:[-:]\d+)?$/, ''))
    .filter((t) => t.includes('/') || /\.\w+$/.test(t));
}

const PARK_NOTE_FALLBACK = '워커가 park 사유를 남기지 않음 — verdict 확인 필요';

/** 등록 게이트(R1–R5): 워커의 추천 상태는 참고용, 최종 birth state는 디스패처가 결정한다.
 * idea/question(제출 분류든 재분류든)은 무조건 needs-human — 제품/스코프/답변은 사람 몫(R4).
 * ready-for-agent는 bug(R1) + file:line 인용(R2) + 리스크 표면 무접촉(R3)일 때만 존중되고,
 * 하나라도 어긋나면 사유를 담아 needs-human으로 강등된다. park 상태는 노트 필수(R5). */
export function routeTicket(rowCategory: FeedbackCategory, v: Verdict): { state: BirthState; note: string | undefined } {
  if (rowCategory === 'idea' || v.resolved_category === 'idea')
    return { state: 'needs-human', note: v.ticket.note ?? '아이디어 — 제품/스코프 판단은 사람 몫' };
  if (rowCategory === 'question' || v.resolved_category === 'question')
    return { state: 'needs-human', note: v.ticket.note ?? '사용자 질문 — 사람이 답변' };

  if (v.ticket.state !== 'ready-for-agent')
    return { state: v.ticket.state, note: v.ticket.note ?? PARK_NOTE_FALLBACK };

  if (v.resolved_category !== 'bug')
    return { state: 'needs-human', note: `ready-for-agent 강등: 분류가 bug 아님(${v.resolved_category})` };
  if (!/\S+:\d+/.test(v.root_cause))
    return { state: 'needs-human', note: 'ready-for-agent 강등: 근본원인에 file:line 인용 없음' };
  const cited = extractCandidatePaths(`${v.root_cause}\n${v.ticket.title}\n${v.ticket.body}`);
  const hit = touchesRiskSurface(cited);
  if (hit)
    return { state: 'needs-human', note: `ready-for-agent 강등: 리스크 표면 접촉(${hit})` };

  return { state: 'ready-for-agent', note: undefined };
}
