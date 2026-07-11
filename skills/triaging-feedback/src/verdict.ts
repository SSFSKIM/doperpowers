import type { BirthState, ResolvedCategory } from './gate';

export interface TicketDraft {
  title: string;
  body: string;
  state: BirthState;
  note?: string;
}

export interface Verdict {
  feedback_id: string;
  resolved_category: ResolvedCategory;
  root_cause: string;
  ticket: TicketDraft;
  confidence: 'high' | 'medium' | 'low';
  /** 보드 스냅샷(디스패처 제공) 안에서 같은 문제를 다루는 기존 이슈 번호 — 있으면 새 티켓 대신
   * 그 이슈에 진단 코멘트를 남긴다. 디스패처가 후보 목록과 대조 검증한다. */
  duplicate_of?: number;
  /** 중복은 아니지만 관련 있는 기존 이슈 번호들 — 등록 후 relates 엣지(주석용)를 건다. */
  related?: number[];
}

const CATS = ['bug', 'idea', 'question', 'other'] satisfies ResolvedCategory[];
const STATES = ['ready-for-agent', 'needs-human', 'needs-info'] satisfies BirthState[];

const asIssueNumber = (v: unknown): number | undefined =>
  typeof v === 'number' && Number.isInteger(v) && v > 0 ? v : undefined;

export function parseVerdict(text: string): Verdict | null {
  const blocks = [...text.matchAll(/```json\s*([\s\S]*?)```/g)];
  if (blocks.length === 0) return null;
  let raw: unknown;
  try { raw = JSON.parse(blocks[blocks.length - 1][1].trim()); } catch { return null; }
  if (typeof raw !== 'object' || raw === null) return null;
  if (Array.isArray(raw)) return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.feedback_id !== 'string') return null;
  if (typeof o.root_cause !== 'string') return null;
  if (typeof o.resolved_category !== 'string' || !(CATS as readonly string[]).includes(o.resolved_category)) return null;
  if (o.confidence !== 'high' && o.confidence !== 'medium' && o.confidence !== 'low') return null;
  if (typeof o.ticket !== 'object' || o.ticket === null || Array.isArray(o.ticket)) return null;
  const t = o.ticket as Record<string, unknown>;
  if (typeof t.title !== 'string' || t.title.trim() === '') return null;
  if (typeof t.body !== 'string' || t.body.trim() === '') return null;
  if (typeof t.state !== 'string' || !(STATES as readonly string[]).includes(t.state)) return null;
  return {
    feedback_id: o.feedback_id,
    resolved_category: o.resolved_category as ResolvedCategory,
    root_cause: o.root_cause,
    ticket: {
      title: t.title.trim(),
      body: t.body,
      state: t.state as BirthState,
      note: typeof t.note === 'string' && t.note.trim() !== '' ? t.note : undefined,
    },
    confidence: o.confidence,
    // dup/related는 자문(advisory) 라우팅 힌트 — 필수 필드처럼 fail시키지 않고, 형식이
    // 어긋난 값만 조용히 버린다(좋은 티켓이 힌트 오형식 때문에 죽으면 안 된다). 실제 존재
    // 여부 검증은 디스패처가 후보 목록과 대조해서 한다.
    duplicate_of: asIssueNumber(o.duplicate_of),
    related: Array.isArray(o.related)
      ? (o.related.map(asIssueNumber).filter((n): n is number => n !== undefined))
      : undefined,
  };
}
