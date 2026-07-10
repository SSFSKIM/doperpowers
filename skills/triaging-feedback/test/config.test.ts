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
    expect(c.reclaimMs).toBe(90 * 60_000); // 최악 디스패치 시간(진단 턴 1회)보다 커야 함(F3)
    expect(c.enabled).toBe(true);          // TRIAGE_ENABLED unset ⇒ default on
    expect(c.model).toBe('gpt-5.6-terra'); // 무인 루프의 모델은 명시 고정 — ~/.codex 기본값 비의존; 워크호스면 충분
    expect(c.effort).toBe('high');
  });
  it('honors the kill switch and overrides', () => {
    const c = loadConfig({ ...base, TRIAGE_ENABLED: 'false', TRIAGE_K: '1', TRIAGE_MODEL: 'gpt-5.5', TRIAGE_EFFORT: 'medium' });
    expect(c.enabled).toBe(false);
    expect(c.k).toBe(1);
    expect(c.model).toBe('gpt-5.5');
    expect(c.effort).toBe('medium');
  });
  it('rejects an out-of-enum TRIAGE_EFFORT', () => {
    expect(() => loadConfig({ ...base, TRIAGE_EFFORT: 'max' })).toThrow(/TRIAGE_EFFORT/);
  });
  it('throws when a required secret is missing', () => {
    expect(() => loadConfig({ ...base, SUPABASE_SERVICE_ROLE_KEY: '' })).toThrow(/SUPABASE_SERVICE_ROLE_KEY/);
  });
});
