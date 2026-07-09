import type { ResolvedCategory } from './gate';

export interface Verdict {
  feedback_id: string;
  resolved_category: ResolvedCategory;
  route: 'fix' | 'ticket';
  root_cause: string;
  reason_if_ticket?: string;
  confidence: 'high' | 'medium' | 'low';
}

const CATS = ['bug', 'idea', 'question', 'other'] satisfies ResolvedCategory[];

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
  if (o.route !== 'fix' && o.route !== 'ticket') return null;
  if (o.confidence !== 'high' && o.confidence !== 'medium' && o.confidence !== 'low') return null;
  return {
    feedback_id: o.feedback_id,
    resolved_category: o.resolved_category as ResolvedCategory,
    route: o.route,
    root_cause: o.root_cause,
    reason_if_ticket: typeof o.reason_if_ticket === 'string' ? o.reason_if_ticket : undefined,
    confidence: o.confidence,
  };
}
