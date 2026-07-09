import { describe, it, expect } from 'vitest';
import { parseVerdict } from '../src/verdict';

const good = 'blah\n```json\n{"feedback_id":"f1","resolved_category":"bug","route":"fix","root_cause":"foo.ts:12 널 참조","confidence":"high"}\n```\nend';

describe('parseVerdict', () => {
  it('extracts a well-formed fenced verdict', () => {
    const v = parseVerdict(good);
    expect(v?.route).toBe('fix');
    expect(v?.resolved_category).toBe('bug');
    expect(v?.feedback_id).toBe('f1');
  });
  it('returns null when no fenced json present', () => {
    expect(parseVerdict('no json here')).toBeNull();
  });
  it('returns null on invalid JSON', () => {
    expect(parseVerdict('```json\n{not json}\n```')).toBeNull();
  });
  it('returns null when a required field is missing', () => {
    expect(parseVerdict('```json\n{"route":"fix"}\n```')).toBeNull();
  });
  it('returns null on an out-of-enum route', () => {
    expect(parseVerdict('```json\n{"feedback_id":"f","resolved_category":"bug","route":"merge","root_cause":"x","confidence":"high"}\n```')).toBeNull();
  });
  it('returns null when the fenced json is an array, not an object', () => {
    expect(parseVerdict('```json\n["bug","fix"]\n```')).toBeNull();
  });
});
