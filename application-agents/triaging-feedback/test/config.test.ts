import { describe, it, expect } from 'vitest';
import { loadConfig } from '../src/config';

const base = {
  SUPABASE_URL: 'https://x.supabase.co', SUPABASE_SERVICE_ROLE_KEY: 'k',
  OPENAI_API_KEY: 'o', TRIAGE_REPO_PATH: '/repo', TRIAGE_BASE_BRANCH: 'feat/m4.5-polish',
  TRIAGE_BOARD_SCRIPTS_DIR: '/board',
};

describe('loadConfig', () => {
  it('parses required fields and applies defaults', () => {
    const c = loadConfig(base);
    expect(c.supabaseUrl).toBe('https://x.supabase.co');
    expect(c.k).toBe(3);
    expect(c.timeoutMs).toBe(20 * 60_000);
    expect(c.reclaimMs).toBe(90 * 60_000);
    expect(c.model).toBe('gpt-5.6-terra'); // 무인 루프의 모델은 명시 고정 — ~/.codex 기본값 비의존; 워크호스면 충분
    expect(c.effort).toBe('high');
    expect(c.trustedRoles).toEqual(['admin']); // 신뢰 2단계 기본: 서버 조회 role 스냅샷 기반
    expect(c.devCode).toBeUndefined();
  });
  it('honors overrides', () => {
    const c = loadConfig({ ...base, TRIAGE_K: '1', TRIAGE_MODEL: 'gpt-5.5', TRIAGE_EFFORT: 'medium', TRIAGE_TRUSTED_ROLES: 'admin, teacher', TRIAGE_DEV_CODE: 'dev18' });
    expect(c.k).toBe(1);
    expect(c.model).toBe('gpt-5.5');
    expect(c.effort).toBe('medium');
    expect(c.trustedRoles).toEqual(['admin', 'teacher']);
    expect(c.devCode).toBe('dev18');
  });
  it('rejects an out-of-enum TRIAGE_EFFORT', () => {
    expect(() => loadConfig({ ...base, TRIAGE_EFFORT: 'max' })).toThrow(/TRIAGE_EFFORT/);
  });
  it('enforces reclaim window > timeout + registration budget (외부 리뷰 #4)', () => {
    expect(() => loadConfig({ ...base, TRIAGE_RECLAIM_MS: String(25 * 60_000) })).toThrow(/TRIAGE_RECLAIM_MS/);
    expect(loadConfig({ ...base, TRIAGE_RECLAIM_MS: String(31 * 60_000) }).reclaimMs).toBe(31 * 60_000);
  });
  it('throws when a required secret is missing', () => {
    expect(() => loadConfig({ ...base, SUPABASE_SERVICE_ROLE_KEY: '' })).toThrow(/SUPABASE_SERVICE_ROLE_KEY/);
  });
});
