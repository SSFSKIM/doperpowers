import { Codex, type CodexOptions, type ThreadOptions } from '@openai/codex-sdk';

// 디스패처의 언더스코어 어휘 → SDK의 하이픈 sandboxMode (스파이크 2026-07-10 확정).
const SANDBOX_MODE = {
  read_only: 'read-only',
  workspace_write: 'workspace-write',
} as const;

/** Codex CLI 자식 프로세스에 넘길 옵션을 순수하게 구성한다(F1 — Critical).
 * `new Codex()`(옵션 없음)는 SDK가 process.env를 통째로 상속시켜 자식에 넘긴다 — 서비스롤 키
 * 등 시크릿이 샌드박스 안 모델에 노출되고, 모델이 printenv로 읽어 root_cause에 실으면 그 문자열이
 * 티켓/PR 본문으로 그대로 공개 게시될 수 있다("워커는 크리덴셜을 안 가진다" 안전모델 위반).
 * `env`를 명시하면 SDK가 process.env를 상속하지 않으므로, codex CLI가 바이너리 탐색·
 * `~/.codex` 세션 디렉터리 접근에 필요로 하는 PATH/HOME만 통과시키고 그 외는 넣지 않는다. */
export function buildCodexOptions(
  openaiApiKey: string,
  processEnv: Record<string, string | undefined>,
): CodexOptions {
  const env: Record<string, string> = {};
  if (processEnv.PATH) env.PATH = processEnv.PATH;
  if (processEnv.HOME) env.HOME = processEnv.HOME;
  return { apiKey: openaiApiKey, env };
}

/** openaiApiKey(+timeoutMs)를 클로징한 runTurn 팩토리. Codex 인스턴스는 팩토리 호출 시 1회 생성.
 * 매 턴은 항상 fresh thread다(F2 — turn 1의 신뢰불가 피드백 본문이 turn 2의 workspace_write
 * 컨텍스트에 남지 않도록 resumeThread 설계를 폐기; 자세한 배경은 스펙 Decision Log 참고).
 * 턴마다 AbortController + timeoutMs로 취소 배선(F3 — 죽은 설정이던 timeoutMs를 실제로 사용). */
export function makeCodexRunner(openaiApiKey: string, timeoutMs: number) {
  const codex = new Codex(buildCodexOptions(openaiApiKey, process.env));

  return async function runTurn(opts: {
    worktree: string;
    prompt: string;
    sandbox: 'read_only' | 'workspace_write';
  }): Promise<{ text: string }> {
    const threadOptions: ThreadOptions = {
      workingDirectory: opts.worktree,
      skipGitRepoCheck: true,
      sandboxMode: SANDBOX_MODE[opts.sandbox],
      // 워커는 크리덴셜/네트워크가 없다 — 빌드·테스트·PR/티켓 게시는 전부 디스패처(git.ts/sideEffects.ts)가
      // 워크트리 밖에서 수행하므로 워커 자신의 승인·네트워크 접근은 불필요.
      approvalPolicy: 'never',
      networkAccessEnabled: false,
    };
    const thread = codex.startThread(threadOptions);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const result = await thread.run(opts.prompt, { signal: controller.signal });
      return { text: result.finalResponse };
    } finally {
      clearTimeout(timer);
    }
  };
}
