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
    expect(c.enabled).toBe(true);      // TRIAGE_ENABLED unset ⇒ default on
    expect(c.fixEnabled).toBe(true);   // TRIAGE_FIX_ENABLED unset ⇒ default on
  });
  it('honors kill switches and overrides', () => {
    const c = loadConfig({ ...base, TRIAGE_ENABLED: 'false', TRIAGE_FIX_ENABLED: 'false', TRIAGE_K: '1' });
    expect(c.enabled).toBe(false);
    expect(c.fixEnabled).toBe(false);
    expect(c.k).toBe(1);
  });
  it('throws when a required secret is missing', () => {
    expect(() => loadConfig({ ...base, SUPABASE_SERVICE_ROLE_KEY: '' })).toThrow(/SUPABASE_SERVICE_ROLE_KEY/);
  });
});
