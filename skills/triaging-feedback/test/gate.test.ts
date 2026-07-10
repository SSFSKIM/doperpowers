import { describe, it, expect } from 'vitest';
import { touchesRiskSurface, extractCandidatePaths, routeTicket } from '../src/gate';
import type { Verdict } from '../src/verdict';

type Over = Omit<Partial<Verdict>, 'ticket'> & { ticket?: Partial<Verdict['ticket']> };
function verdict(over: Over = {}): Verdict {
  return {
    feedback_id: 'f1',
    resolved_category: 'bug',
    root_cause: 'components/today/Card.tsx:42 onClick 핸들러 누락',
    confidence: 'high',
    ...over,
    ticket: {
      title: '오늘 카드 버튼 무반응',
      body: '## 증상\n버튼이 안 눌림\n\n## 진단\ncomponents/today/Card.tsx:42',
      state: 'ready-for-agent',
      ...(over.ticket ?? {}),
    },
  } as Verdict;
}

describe('touchesRiskSurface', () => {
  it.each([
    'lib/auth.ts', 'middleware.ts', 'sql/p87_new.sql', 'lib/schema.sql',
    'types/index.ts', 'lib/anthropic.ts', 'lib/exam-calendar.ts', 'lib/grade-system.ts',
    'lib/exam-bank.ts', 'app/api/cron/x/route.ts', 'vercel.json',
    'app/api/ai/generate-plan/route.ts',
  ])('flags %s', (p: string) => { expect(touchesRiskSurface([p])).toBe(p); });

  it('allows benign paths', () => {
    expect(touchesRiskSurface(['components/today/Card.tsx', 'app/hq/feedback/FeedbackListClient.tsx'])).toBeNull();
  });
});

describe('extractCandidatePaths', () => {
  it('extracts file:line citations with the line tail stripped', () => {
    expect(extractCandidatePaths('원인은 lib/auth.ts:12 그리고 components/x.tsx:3-9')).toEqual(
      expect.arrayContaining(['lib/auth.ts', 'components/x.tsx']),
    );
  });
  it('extracts bare paths mentioned in prose (no :line)', () => {
    expect(extractCandidatePaths('vercel.json 설정과 app/api/cron/daily 잡')).toEqual(
      expect.arrayContaining(['vercel.json', 'app/api/cron/daily']),
    );
  });
  it('ignores plain words', () => {
    expect(extractCandidatePaths('버튼이 안 눌려요 정말로')).toEqual([]);
  });
});

describe('routeTicket', () => {
  it('honors ready-for-agent for a cited, benign bug', () => {
    expect(routeTicket('bug', verdict())).toEqual({ state: 'ready-for-agent', note: undefined });
  });

  it('row category idea → forced needs-human even if the worker recommends ready-for-agent', () => {
    const r = routeTicket('idea', verdict());
    expect(r.state).toBe('needs-human');
  });

  it('resolved category question → forced needs-human (row category was other)', () => {
    const r = routeTicket('other', verdict({ resolved_category: 'question' }));
    expect(r.state).toBe('needs-human');
    expect(r.note).toBeTruthy();
  });

  it('worker-recommended park state is honored with its note', () => {
    const r = routeTicket('bug', verdict({ ticket: { state: 'needs-info', note: '레거시 API 응답 스키마 조사 필요' } }));
    expect(r).toEqual({ state: 'needs-info', note: '레거시 API 응답 스키마 조사 필요' });
  });

  it('park state without a note gets a fallback note (board requires one)', () => {
    const r = routeTicket('bug', verdict({ ticket: { state: 'needs-human', note: undefined } }));
    expect(r.state).toBe('needs-human');
    expect(r.note).toBeTruthy();
  });

  it('demotes ready-for-agent when resolved category is not bug', () => {
    const r = routeTicket('other', verdict({ resolved_category: 'other' }));
    expect(r.state).toBe('needs-human');
    expect(r.note).toContain('bug');
  });

  it('demotes ready-for-agent when root_cause has no file:line citation', () => {
    const r = routeTicket('bug', verdict({ root_cause: '어딘가 잘못됨' }));
    expect(r.state).toBe('needs-human');
    expect(r.note).toContain('인용');
  });

  it('demotes ready-for-agent when a cited path touches a risk surface (root_cause)', () => {
    const r = routeTicket('bug', verdict({ root_cause: 'lib/auth.ts:7 세션 체크 누락' }));
    expect(r.state).toBe('needs-human');
    expect(r.note).toContain('lib/auth.ts');
  });

  it('demotes ready-for-agent when the authored ticket body mentions a risk surface', () => {
    const r = routeTicket('bug', verdict({ ticket: { body: '## 제안 수정 방향\nsql/p90_fix.sql 마이그레이션 추가' } }));
    expect(r.state).toBe('needs-human');
    expect(r.note).toContain('sql/p90_fix.sql');
  });
});
