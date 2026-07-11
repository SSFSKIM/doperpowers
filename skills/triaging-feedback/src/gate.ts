import type { FeedbackCategory } from './types';
import type { TrustLevel } from './trust';
import type { Verdict } from './verdict';

export type ResolvedCategory = 'bug' | 'idea' | 'question' | 'other';
export type BirthState = 'ready-for-agent' | 'needs-human' | 'needs-info';

// spec R3 — ida-solution 골든룰에서 그대로 옮긴 리스크 표면(경로). 인용된 경로가 하나라도 닿으면
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

// spec R3 보강(외부 리뷰 #3) — 경로가 아니라 심볼/개념으로 리스크 표면을 지목하는 verdict도
// 잡는다: 무해한 래퍼 파일만 인용하고 본문에서 assertStudentAccess/supabaseAdmin 수정을
// 설명하는 우회를 막는다. 산문 속 언급의 오탐은 needs-human 강등이라 안전한 방향.
export const RISK_SYMBOLS: RegExp[] = [
  /\bassertStudentAccess\b/, /\bsupabaseAdmin\b/, /\bRLS\b/,
  /\bbuildMealBreakRows\b/, /\bsplitStudyAroundBlocks\b/, /\bresolveOverlaps\b/,
  /\bpast_exam_problems\b/, /\bSUPABASE_SERVICE_ROLE_KEY\b/,
];

export function touchesRiskSurface(paths: string[]): string | null {
  for (const p of paths) if (RISK_SURFACES.some((re) => re.test(p))) return p;
  return null;
}

export function touchesRiskSymbol(text: string): string | null {
  for (const re of RISK_SYMBOLS) {
    const m = text.match(re);
    if (m) return m[0];
  }
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

/** root_cause에서 "실제 파일 인용"만 추출한다(외부 리뷰 #2) — `unknown:12` 같은
 * 임의토큰:숫자가 아니라, :line을 벗긴 앞부분이 경로 꼴(슬래시 또는 확장자)인 것만 인정. */
export function extractFileCitations(text: string): string[] {
  const tokens = text.match(/[\w@./-]+:\d+(?:[-:]\d+)?/g) ?? [];
  return tokens
    .map((t) => t.replace(/:\d+(?:[-:]\d+)?$/, ''))
    .filter((t) => t.includes('/') || /\.\w+$/.test(t));
}

const PARK_NOTE_FALLBACK = '워커가 park 사유를 남기지 않음 — verdict 확인 필요';

// 내용 린트(결정론적) — ready-for-agent로 태어나는 티켓만 대상. 프로토콜의 본문 템플릿
// 5개 섹션이 전부 있어야 구현 게이트(well-defined 심사)가 읽을 수 있는 형태가 된다.
export const REQUIRED_SECTIONS = ['## 증상', '## 진단', '## 제안 수정 방향', '## 스코프 추정', '## 불명확한 점'] as const;
const BODY_MAX_CHARS = 10_000;

/** ready-for-agent 후보 티켓의 형식 검사. 실패 사유를 돌려주면 routeTicket이 needs-human으로
 * 강등한다(진단을 버리는 failed가 아니라 — 내용은 살리고 형식 미달만 사람에게 알린다). */
export function lintTicket(t: { title: string; body: string }, rawBody: string): string | null {
  const missing = REQUIRED_SECTIONS.filter((s) => !t.body.includes(s));
  if (missing.length) return `필수 섹션 누락: ${missing.join(', ')}`;
  if (t.body.length > BODY_MAX_CHARS) return `본문 과대(${t.body.length}자 > ${BODY_MAX_CHARS})`;
  // 제목 원문-복붙 방지: 요약이 아니라 사용자 문장을 그대로 옮긴 제목은 보드 가독성을 해친다.
  // 15자 이상이 원문에 그대로 나타나면 복붙으로 간주(짧은 제목의 우연 일치는 허용).
  const title = t.title.trim();
  if (title.length >= 15 && rawBody.includes(title)) return '제목이 원문 복사 — 요약 제목 필요';
  return null;
}

/** 등록 게이트(R1–R5): 워커의 추천 상태는 참고용, 최종 birth state는 디스패처가 결정한다.
 * 신뢰 2단계(2026-07-11): user 피드백은 보수적으로 — idea/question 무조건 needs-human(R4),
 * ready-for-agent는 bug만(R1). developer 피드백(role/코드로 판별)은 지시로 취급 —
 * R1/R4를 적용하지 않아 아이디어·개선도 ready-for-agent로 태어날 수 있다.
 * 두 수준 공통: 실제 file:line 인용(R2)과 리스크 표면 무접촉(R3, 경로+심볼)은 항상 요구 —
 * 리스크 표면을 에이전트가 무인으로 만지는 위험은 요청자가 누구든 동일하다.
 * rawBody(코드 제거 후 원문)는 내용 린트의 제목-복붙 검사에 쓰인다. */
export function routeTicket(trust: TrustLevel, rowCategory: FeedbackCategory, v: Verdict, rawBody: string): { state: BirthState; note: string | undefined } {
  if (trust === 'user') {
    if (rowCategory === 'idea' || v.resolved_category === 'idea')
      return { state: 'needs-human', note: v.ticket.note ?? '아이디어 — 제품/스코프 판단은 사람 몫' };
    if (rowCategory === 'question' || v.resolved_category === 'question')
      return { state: 'needs-human', note: v.ticket.note ?? '사용자 질문 — 사람이 답변' };
  }

  if (v.ticket.state !== 'ready-for-agent')
    return { state: v.ticket.state, note: v.ticket.note ?? PARK_NOTE_FALLBACK };

  if (trust === 'user' && v.resolved_category !== 'bug')
    return { state: 'needs-human', note: `ready-for-agent 강등: 분류가 bug 아님(${v.resolved_category})` };
  if (extractFileCitations(v.root_cause).length === 0)
    return { state: 'needs-human', note: 'ready-for-agent 강등: 근본원인에 실제 file:line 인용 없음' };
  const text = `${v.root_cause}\n${v.ticket.title}\n${v.ticket.body}`;
  const hit = touchesRiskSurface(extractCandidatePaths(text));
  if (hit)
    return { state: 'needs-human', note: `ready-for-agent 강등: 리스크 표면 접촉(${hit})` };
  const sym = touchesRiskSymbol(text);
  if (sym)
    return { state: 'needs-human', note: `ready-for-agent 강등: 리스크 심볼 언급(${sym})` };
  const lint = lintTicket(v.ticket, rawBody);
  if (lint)
    return { state: 'needs-human', note: `ready-for-agent 강등: ${lint}` };

  return { state: 'ready-for-agent', note: undefined };
}
