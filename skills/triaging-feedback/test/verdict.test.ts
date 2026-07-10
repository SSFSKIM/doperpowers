import { describe, it, expect } from 'vitest';
import { parseVerdict } from '../src/verdict';

const goodObj = {
  feedback_id: 'f1',
  resolved_category: 'bug',
  root_cause: 'foo.ts:12 널 참조',
  ticket: { title: '오늘 화면 카드 널 참조 크래시', body: '## 증상\n…\n## 진단\nfoo.ts:12', state: 'ready-for-agent' },
  confidence: 'high',
};
const fence = (o: unknown) => 'blah\n```json\n' + JSON.stringify(o) + '\n```\nend';

describe('parseVerdict', () => {
  it('extracts a well-formed fenced verdict with the authored ticket', () => {
    const v = parseVerdict(fence(goodObj));
    expect(v?.feedback_id).toBe('f1');
    expect(v?.resolved_category).toBe('bug');
    expect(v?.ticket.title).toBe('오늘 화면 카드 널 참조 크래시');
    expect(v?.ticket.state).toBe('ready-for-agent');
    expect(v?.ticket.note).toBeUndefined();
  });
  it('keeps a park note when present, drops a blank one', () => {
    expect(parseVerdict(fence({ ...goodObj, ticket: { ...goodObj.ticket, state: 'needs-human', note: '사람 판단 필요' } }))?.ticket.note).toBe('사람 판단 필요');
    expect(parseVerdict(fence({ ...goodObj, ticket: { ...goodObj.ticket, note: '  ' } }))?.ticket.note).toBeUndefined();
  });
  it('returns null when no fenced json present', () => {
    expect(parseVerdict('no json here')).toBeNull();
  });
  it('returns null on invalid JSON', () => {
    expect(parseVerdict('```json\n{not json}\n```')).toBeNull();
  });
  it('returns null when a required field is missing', () => {
    expect(parseVerdict('```json\n{"feedback_id":"f"}\n```')).toBeNull();
  });
  it('returns null when the ticket is missing or not an object', () => {
    expect(parseVerdict(fence({ ...goodObj, ticket: undefined }))).toBeNull();
    expect(parseVerdict(fence({ ...goodObj, ticket: 'x' }))).toBeNull();
  });
  it('returns null on an empty ticket title or body', () => {
    expect(parseVerdict(fence({ ...goodObj, ticket: { ...goodObj.ticket, title: '  ' } }))).toBeNull();
    expect(parseVerdict(fence({ ...goodObj, ticket: { ...goodObj.ticket, body: '' } }))).toBeNull();
  });
  it('returns null on an out-of-enum ticket state', () => {
    expect(parseVerdict(fence({ ...goodObj, ticket: { ...goodObj.ticket, state: 'in-progress' } }))).toBeNull();
  });
  it('returns null on an out-of-enum category', () => {
    expect(parseVerdict(fence({ ...goodObj, resolved_category: 'praise' }))).toBeNull();
  });
  it('returns null when the fenced json is an array, not an object', () => {
    expect(parseVerdict('```json\n["bug","fix"]\n```')).toBeNull();
  });
});
