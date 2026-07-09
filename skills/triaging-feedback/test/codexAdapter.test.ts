import { describe, it, expect } from 'vitest';
import { buildCodexOptions } from '../src/codexAdapter';

// F1(Critical): Codex 자식 프로세스가 process.env 전체(서비스롤 키 포함)를 상속하던 문제.
// buildCodexOptions는 순수 함수라 Codex 인스턴스 생성/실호출 없이 env 구성만 검증한다.
describe('buildCodexOptions', () => {
  it('PATH/HOME만 통과시키고, processEnv에 시크릿이 섞여 있어도 결과에 부재한다', () => {
    const opts = buildCodexOptions('sk-test', {
      PATH: '/usr/bin:/bin',
      HOME: '/Users/demo',
      SUPABASE_SERVICE_ROLE_KEY: 'super-secret-key',
      GITHUB_TOKEN: 'gh-secret',
      GH_TOKEN: 'gh-secret-2',
      OPENAI_API_KEY: 'oai-secret',
      ANTHROPIC_API_KEY: 'anthropic-secret',
    });
    expect(opts.env).toEqual({ PATH: '/usr/bin:/bin', HOME: '/Users/demo' });
    expect(opts.env).not.toHaveProperty('SUPABASE_SERVICE_ROLE_KEY');
    expect(opts.env).not.toHaveProperty('GITHUB_TOKEN');
    expect(opts.env).not.toHaveProperty('GH_TOKEN');
    expect(opts.env).not.toHaveProperty('OPENAI_API_KEY');
    expect(opts.env).not.toHaveProperty('ANTHROPIC_API_KEY');
  });

  it('openaiApiKey를 apiKey로 그대로 전달한다', () => {
    const opts = buildCodexOptions('sk-abc123', { PATH: '/bin' });
    expect(opts.apiKey).toBe('sk-abc123');
  });

  it('processEnv에 PATH/HOME이 없으면 env에 그 키 자체가 없다(빈 문자열이 아니라 부재)', () => {
    const opts = buildCodexOptions('sk-test', { SOME_OTHER_VAR: 'x' });
    expect(opts.env).toEqual({});
    expect(opts.env).not.toHaveProperty('PATH');
    expect(opts.env).not.toHaveProperty('HOME');
  });
});
