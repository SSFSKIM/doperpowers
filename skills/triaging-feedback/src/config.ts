export interface Config {
  supabaseUrl: string; supabaseServiceKey: string; openaiApiKey: string;
  repoPath: string; baseBranch: string; boardScriptsDir: string;
  k: number; timeoutMs: number; reclaimMs: number;
  enabled: boolean; fixEnabled: boolean;
}

function req(env: Record<string, string | undefined>, key: string): string {
  const v = env[key];
  if (!v) throw new Error(`missing required env: ${key}`);
  return v;
}

export function loadConfig(env: Record<string, string | undefined>): Config {
  return {
    supabaseUrl: req(env, 'SUPABASE_URL'),
    supabaseServiceKey: req(env, 'SUPABASE_SERVICE_ROLE_KEY'),
    openaiApiKey: req(env, 'OPENAI_API_KEY'),
    repoPath: req(env, 'TRIAGE_REPO_PATH'),
    baseBranch: req(env, 'TRIAGE_BASE_BRANCH'),
    boardScriptsDir: req(env, 'TRIAGE_BOARD_SCRIPTS_DIR'),
    k: env.TRIAGE_K ? Number(env.TRIAGE_K) : 3,
    timeoutMs: env.TRIAGE_TIMEOUT_MS ? Number(env.TRIAGE_TIMEOUT_MS) : 20 * 60_000,
    // 최악 디스패치 시간(턴 2회 × 20분 + 빌드 15분)보다 커야 한다(F3) — 그렇지 않으면 아직 살아있는
    // 잡을 다른 폴러 인스턴스(다른 머신/수동 실행)가 리클레임해 이중 처리할 수 있다.
    reclaimMs: env.TRIAGE_RECLAIM_MS ? Number(env.TRIAGE_RECLAIM_MS) : 90 * 60_000,
    enabled: env.TRIAGE_ENABLED !== 'false',
    // 안전 기본값 = false(F5). 리터럴 'true'를 명시했을 때만 fix PR 자동 생성 경로가 켜진다 —
    // 새로 붙는 레포는 항상 섀도 모드(티켓만)로 시작해야 하므로 unset/오타는 전부 off로 취급.
    fixEnabled: env.TRIAGE_FIX_ENABLED === 'true',
  };
}
