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
}

const CATS = ['bug', 'idea', 'question', 'other'] satisfies ResolvedCategory[];
const STATES = ['ready-for-agent', 'needs-human', 'needs-info'] satisfies BirthState[];

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
  };
}
