export const EFFORTS = ['minimal', 'low', 'medium', 'high', 'xhigh'] as const;
export type Effort = (typeof EFFORTS)[number];

export interface Config {
  supabaseUrl: string; supabaseServiceKey: string; openaiApiKey: string;
  repoPath: string; baseBranch: string; boardScriptsDir: string;
  model: string; effort: Effort;
  trustedRoles: string[]; devCode?: string;
  k: number; timeoutMs: number; reclaimMs: number;
}

function req(env: Record<string, string | undefined>, key: string): string {
  const v = env[key];
  if (!v) throw new Error(`missing required env: ${key}`);
  return v;
}

// 등록/DB 기록 지연 예산 — 리클레임 창 검증(외부 리뷰 #4)에 쓰인다.
const REGISTRATION_BUDGET_MS = 10 * 60_000;

export function loadConfig(env: Record<string, string | undefined>): Config {
  const effort = env.TRIAGE_EFFORT ?? 'high';
  if (!(EFFORTS as readonly string[]).includes(effort))
    throw new Error(`TRIAGE_EFFORT must be one of: ${EFFORTS.join(', ')}`);
  const timeoutMs = env.TRIAGE_TIMEOUT_MS ? Number(env.TRIAGE_TIMEOUT_MS) : 20 * 60_000;
  const reclaimMs = env.TRIAGE_RECLAIM_MS ? Number(env.TRIAGE_RECLAIM_MS) : 90 * 60_000;
  // 리클레임 창이 최악 실행 시간(진단 턴 + 등록/기록)보다 짧으면 살아있는 잡을 다른 폴러가
  // 리클레임해 이중 티켓이 난다 — 주석 권고였던 것을 로드 시점 강제로 승격(외부 리뷰 #4).
  if (reclaimMs <= timeoutMs + REGISTRATION_BUDGET_MS)
    throw new Error(`TRIAGE_RECLAIM_MS (${reclaimMs}) must exceed TRIAGE_TIMEOUT_MS + ${REGISTRATION_BUDGET_MS}ms registration budget (${timeoutMs + REGISTRATION_BUDGET_MS})`);
  return {
    supabaseUrl: req(env, 'SUPABASE_URL'),
    supabaseServiceKey: req(env, 'SUPABASE_SERVICE_ROLE_KEY'),
    openaiApiKey: req(env, 'OPENAI_API_KEY'),
    repoPath: req(env, 'TRIAGE_REPO_PATH'),
    baseBranch: req(env, 'TRIAGE_BASE_BRANCH'),
    boardScriptsDir: req(env, 'TRIAGE_BOARD_SCRIPTS_DIR'),
    // 워커 모델/노력을 명시 고정 — 미지정 시 ~/.codex/config.toml의 대화용 기본값이
    // 무인 루프에 조용히 새어드는 결합을 끊는다(2026-07-11 티켓-온리 재설계).
    // 워크호스 모델 + high effort: 진단·티켓 저작은 플래그십(sol)급 문제가 아니다.
    model: env.TRIAGE_MODEL || 'gpt-5.6-terra',
    effort: effort as Effort,
    // 신뢰 2단계(외부 리뷰 #1): role은 /api/feedback이 서버에서 조회한 스냅샷이라 위조 불가.
    // devCode는 .env 시크릿 — 본문 `#<code>` 접두로 developer 신뢰를 얻는 편의 경로(선택).
    trustedRoles: (env.TRIAGE_TRUSTED_ROLES ?? 'admin').split(',').map((s) => s.trim()).filter(Boolean),
    devCode: env.TRIAGE_DEV_CODE || undefined,
    k: env.TRIAGE_K ? Number(env.TRIAGE_K) : 3,
    timeoutMs,
    reclaimMs,
  };
}
