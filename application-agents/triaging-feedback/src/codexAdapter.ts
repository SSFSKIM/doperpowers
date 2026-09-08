import { Codex, type CodexOptions, type ThreadOptions } from '@openai/codex-sdk';
import type { Effort } from './config';

/** Codex CLI 자식 프로세스에 넘길 옵션을 순수하게 구성한다(F1 — Critical).
 * `new Codex()`(옵션 없음)는 SDK가 process.env를 통째로 상속시켜 자식에 넘긴다 — 서비스롤 키
 * 등 시크릿이 샌드박스 안 모델에 노출되고, 모델이 printenv로 읽어 root_cause에 실으면 그 문자열이
 * 티켓 본문으로 그대로 공개 게시될 수 있다("워커는 크리덴셜을 안 가진다" 안전모델 위반).
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

/** 진단 턴 1회짜리 runTurn 팩토리. Codex 인스턴스는 팩토리 호출 시 1회 생성.
 * 티켓-온리 재설계(2026-07-11) 이후 워커는 항상 read-only 단일 턴이다 — 코드를 쓰지 않고,
 * 진단 + 티켓 저작만 한다. model/effort는 설정으로 고정(~/.codex 기본값 비의존).
 * 워커는 크리덴셜/네트워크가 없고 승인 에스컬레이션 대상 자체가 없다(approvalPolicy:never).
 * 턴마다 AbortController + timeoutMs로 취소 배선(F3). */
export function makeCodexRunner(cfg: { openaiApiKey: string; timeoutMs: number; model: string; effort: Effort }) {
  const codex = new Codex(buildCodexOptions(cfg.openaiApiKey, process.env));

  return async function runTurn(opts: { worktree: string; prompt: string }): Promise<{ text: string }> {
    const threadOptions: ThreadOptions = {
      workingDirectory: opts.worktree,
      skipGitRepoCheck: true,
      sandboxMode: 'read-only',
      model: cfg.model,
      modelReasoningEffort: cfg.effort,
      approvalPolicy: 'never',
      networkAccessEnabled: false,
    };
    const thread = codex.startThread(threadOptions);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), cfg.timeoutMs);
    try {
      const result = await thread.run(opts.prompt, { signal: controller.signal });
      return { text: result.finalResponse };
    } finally {
      clearTimeout(timer);
    }
  };
}
