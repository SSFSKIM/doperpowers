export const EFFORTS = ['minimal', 'low', 'medium', 'high', 'xhigh'] as const;
export type Effort = (typeof EFFORTS)[number];

export interface Config {
  supabaseUrl: string; supabaseServiceKey: string; openaiApiKey: string;
  repoPath: string; baseBranch: string; boardScriptsDir: string;
  model: string; effort: Effort;
  k: number; timeoutMs: number; reclaimMs: number;
  enabled: boolean;
}

function req(env: Record<string, string | undefined>, key: string): string {
  const v = env[key];
  if (!v) throw new Error(`missing required env: ${key}`);
  return v;
}

export function loadConfig(env: Record<string, string | undefined>): Config {
  const effort = env.TRIAGE_EFFORT ?? 'medium';
  if (!(EFFORTS as readonly string[]).includes(effort))
    throw new Error(`TRIAGE_EFFORT must be one of: ${EFFORTS.join(', ')}`);
  return {
    supabaseUrl: req(env, 'SUPABASE_URL'),
    supabaseServiceKey: req(env, 'SUPABASE_SERVICE_ROLE_KEY'),
    openaiApiKey: req(env, 'OPENAI_API_KEY'),
    repoPath: req(env, 'TRIAGE_REPO_PATH'),
    baseBranch: req(env, 'TRIAGE_BASE_BRANCH'),
    boardScriptsDir: req(env, 'TRIAGE_BOARD_SCRIPTS_DIR'),
    // 워커 모델/노력을 명시 고정 — 미지정 시 ~/.codex/config.toml의 대화용 기본값이
    // 무인 루프에 조용히 새어드는 결합을 끊는다(2026-07-11 티켓-온리 재설계).
    model: env.TRIAGE_MODEL || 'gpt-5.6-sol',
    effort: effort as Effort,
    k: env.TRIAGE_K ? Number(env.TRIAGE_K) : 3,
    timeoutMs: env.TRIAGE_TIMEOUT_MS ? Number(env.TRIAGE_TIMEOUT_MS) : 20 * 60_000,
    // 최악 디스패치 시간(진단 턴 1회 = timeoutMs + 티켓 등록 지연)보다 커야 한다(F3) —
    // 그렇지 않으면 아직 살아있는 잡을 다른 폴러 인스턴스가 리클레임해 이중 처리할 수 있다.
    reclaimMs: env.TRIAGE_RECLAIM_MS ? Number(env.TRIAGE_RECLAIM_MS) : 90 * 60_000,
    enabled: env.TRIAGE_ENABLED !== 'false',
  };
}
