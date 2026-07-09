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
    reclaimMs: env.TRIAGE_RECLAIM_MS ? Number(env.TRIAGE_RECLAIM_MS) : 30 * 60_000,
    enabled: env.TRIAGE_ENABLED !== 'false',
    fixEnabled: env.TRIAGE_FIX_ENABLED !== 'false',
  };
}
