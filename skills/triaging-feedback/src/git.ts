import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const run = promisify(execFile);

/** repoPath = 대상 레포(ida-solution)의 로컬 베이스 체크아웃 경로. baseBranch = 통합 브랜치.
 * 티켓-온리 재설계(2026-07-11) 이후 워크트리는 쓰기 격리가 아니라 **인용 무결성**을 위한 것이다:
 * 베이스 체크아웃은 다른 브랜치에 있거나 dirty할 수 있어 file:line 인용이 어긋난다 — 워커는
 * origin/<baseBranch>에 고정된 깨끗한 detached 스냅샷에서 읽는다(브랜치 생성·빌드 없음). */
export function makeGit(repoPath: string, baseBranch: string) {
  return {
    /** feedback id별 read-only 진단용 detached 워크트리 생성. 반환: 워크트리 절대경로.
     * 재실행(reclaim) 안전: 동일 id의 잔여 워크트리가 있어도 정리 후 재생성한다. */
    async addWorktree(id: string): Promise<string> {
      const id8 = id.slice(0, 8);
      const wt = `${repoPath}/.triage-worktrees/${id8}`;
      await run('git', ['-C', repoPath, 'fetch', 'origin', baseBranch]);
      await run('git', ['-C', repoPath, 'worktree', 'remove', '--force', wt]).catch(() => {}); // 재실행 시 잔여 정리
      await run('git', ['-C', repoPath, 'worktree', 'prune']).catch(() => {});
      await run('git', ['-C', repoPath, 'worktree', 'add', '--detach', wt, `origin/${baseBranch}`]);
      return wt;
    },

    /** 워크트리 정리. 실패해도(이미 삭제됨 등) 무시 — 호출부(finally)에서 항상 호출된다. */
    async removeWorktree(wt: string): Promise<void> {
      await run('git', ['-C', repoPath, 'worktree', 'remove', '--force', wt]).catch(() => {});
    },
  };
}
