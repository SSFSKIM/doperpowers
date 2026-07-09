import { describe, it, expect } from 'vitest';
import { touchesRiskSurface, enforceGate } from '../src/gate';

const ok = {
  resolvedCategory: 'bug' as const, changedFiles: ['components/today/Card.tsx'],
  diffLines: 20, testsPassed: true, rootCauseCited: true,
};

describe('touchesRiskSurface', () => {
  it.each([
    'lib/auth.ts', 'middleware.ts', 'sql/p87_new.sql', 'lib/schema.sql',
    'types/index.ts', 'lib/anthropic.ts', 'lib/exam-calendar.ts', 'lib/grade-system.ts',
    'lib/exam-bank.ts', 'app/api/cron/x/route.ts', 'vercel.json',
    'app/api/ai/generate-plan/route.ts',
  ])('flags %s', (p) => { expect(touchesRiskSurface([p])).toBe(p); });

  it('allows benign paths', () => {
    expect(touchesRiskSurface(['components/today/Card.tsx', 'app/hq/feedback/FeedbackListClient.tsx'])).toBeNull();
  });
});

describe('enforceGate', () => {
  it('passes a clean, small, cited bug fix', () => {
    expect(enforceGate(ok)).toEqual({ pass: true });
  });
  it('fails on non-bug category', () => {
    expect(enforceGate({ ...ok, resolvedCategory: 'idea' }).pass).toBe(false);
  });
  it('fails on oversized diff (lines)', () => {
    expect(enforceGate({ ...ok, diffLines: 151 }).pass).toBe(false);
  });
  it('fails on too many files', () => {
    expect(enforceGate({ ...ok, changedFiles: ['a','b','c','d','e','f'] }).pass).toBe(false);
  });
  it('fails on risk-surface touch even when everything else is fine', () => {
    const r = enforceGate({ ...ok, changedFiles: ['lib/auth.ts'] });
    expect(r.pass).toBe(false);
    expect(r.reason).toContain('lib/auth.ts');
  });
  it('fails when tests did not pass', () => {
    expect(enforceGate({ ...ok, testsPassed: false }).pass).toBe(false);
  });
  it('fails when root cause is not cited', () => {
    expect(enforceGate({ ...ok, rootCauseCited: false }).pass).toBe(false);
  });
});
