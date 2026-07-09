import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { symlinkSync, existsSync } from 'node:fs';

const run = promisify(execFile);

/** repoPath = 대상 레포(ida-solution)의 로컬 베이스 체크아웃 경로. baseBranch = PR의 base(예: feat/m4.5-polish). */
export function makeGit(repoPath: string, baseBranch: string) {
  return {
    /** feedback id별 격리 워크트리 생성 + 전용 fix 브랜치 체크아웃. 반환: 워크트리 절대경로. */
    async addWorktree(id: string): Promise<string> {
      const wt = `${repoPath}/.triage-worktrees/${id.slice(0, 8)}`;
      const branch = `fix/feedback-${id.slice(0, 8)}`;
      await run('git', ['-C', repoPath, 'fetch', 'origin', baseBranch]);
      await run('git', ['-C', repoPath, 'worktree', 'add', '-b', branch, wt, `origin/${baseBranch}`]);
      // 새 워크트리는 node_modules가 없다(gitignored, per-worktree) — buildAndTest가 의존성을
      // 해석하려면 베이스 체크아웃의 node_modules를 심볼릭 링크로 공유한다(느린 재설치 회피).
      const nm = `${repoPath}/node_modules`;
      if (existsSync(nm) && !existsSync(`${wt}/node_modules`)) symlinkSync(nm, `${wt}/node_modules`, 'dir');
      return wt;
    },

    /** 워크트리 정리. 실패해도(이미 삭제됨 등) 무시 — 호출부(finally)에서 항상 호출된다. */
    async removeWorktree(wt: string): Promise<void> {
      await run('git', ['-C', repoPath, 'worktree', 'remove', '--force', wt]).catch(() => {});
    },

    /** 워크트리 내 변경분 통계. gate.ts의 G3(diff 규모)·G4(리스크 표면 파일 목록) 판단 입력. */
    async diffStat(wt: string): Promise<{ files: string[]; lines: number }> {
      const { stdout } = await run('git', ['-C', wt, 'diff', '--numstat']);
      const rows = stdout.trim().split('\n').filter(Boolean);
      const files = rows.map((r) => r.split('\t')[2]);
      const lines = rows.reduce((n, r) => {
        const [a, d] = r.split('\t');
        return n + (Number(a) || 0) + (Number(d) || 0);
      }, 0);
      return { files, lines };
    },

    /** 워크트리에서 프로덕션 빌드 실행(G5). 15분 타임아웃 — Next.js 풀빌드를 고려한 여유치.
     * maxBuffer 64MiB — execFile 기본값(1MiB)로는 실 Next.js 빌드의 combined stdout/stderr가
     * 넘쳐 성공한 빌드도 buffer overflow로 오탐(false) 처리된다. */
    async buildAndTest(wt: string): Promise<boolean> {
      try {
        await run('npm', ['run', 'build'], { cwd: wt, timeout: 15 * 60_000, maxBuffer: 64 * 1024 * 1024 });
        return true;
      } catch {
        return false;
      }
    },
  };
}
