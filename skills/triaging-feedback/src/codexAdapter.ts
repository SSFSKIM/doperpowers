import { Codex } from '@openai/codex-sdk';

export type CodexThread = ReturnType<Codex['startThread']>;

// 디스패처의 언더스코어 어휘 → SDK의 하이픈 sandboxMode (스파이크 2026-07-10 확정).
const SANDBOX_MODE = {
  read_only: 'read-only',
  workspace_write: 'workspace-write',
} as const;

const codex = new Codex(); // 인증: 상속된 process.env(CODEX_API_KEY/OPENAI_API_KEY) 또는 new Codex({ apiKey })

export async function runTurn(opts: {
  worktree: string;
  prompt: string;
  sandbox: 'read_only' | 'workspace_write';
  thread?: CodexThread;
}): Promise<{ text: string; thread: CodexThread }> {
  // TS SDK는 sandbox를 스레드 생성 시점에 고정한다(run()당 전환 불가). 같은 대화의 다음 턴에서
  // sandbox를 바꾸려면 앞선 스레드의 id로 resumeThread하며 새 ThreadOptions를 준다. thread.id는
  // 첫 run() 완료 후에만 채워지므로, resume 턴에는 항상 존재한다.
  const threadOptions = {
    workingDirectory: opts.worktree,
    skipGitRepoCheck: true,
    sandboxMode: SANDBOX_MODE[opts.sandbox],
  };
  let thread: CodexThread;
  if (opts.thread) {
    const id = opts.thread.id;
    if (!id) throw new Error('runTurn: 이전 스레드 id가 없어 resume 불가(첫 run() 미완료)');
    thread = codex.resumeThread(id, threadOptions);
  } else {
    thread = codex.startThread(threadOptions);
  }
  const result = await thread.run(opts.prompt);
  return { text: result.finalResponse, thread };
}
