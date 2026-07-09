import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { symlinkSync, existsSync } from 'node:fs';

const run = promisify(execFile);

/** repoPath = 대상 레포(ida-solution)의 로컬 베이스 체크아웃 경로. baseBranch = PR의 base(예: feat/m4.5-polish). */
export function makeGit(repoPath: string, baseBranch: string) {
  return {
    /** feedback id별 격리 워크트리 생성 + 전용 fix 브랜치 체크아웃. 반환: 워크트리 절대경로.
     * 재실행(reclaim) 안전: 동일 id의 잔여 워크트리/브랜치가 있어도 정리 후 재생성한다. */
    async addWorktree(id: string): Promise<string> {
      const id8 = id.slice(0, 8);
      const wt = `${repoPath}/.triage-worktrees/${id8}`;
      const branch = `fix/feedback-${id8}`;
      await run('git', ['-C', repoPath, 'fetch', 'origin', baseBranch]);
      await run('git', ['-C', repoPath, 'worktree', 'remove', '--force', wt]).catch(() => {}); // 재실행 시 잔여 정리
      await run('git', ['-C', repoPath, 'worktree', 'prune']).catch(() => {});
      await run('git', ['-C', repoPath, 'worktree', 'add', '-B', branch, wt, `origin/${baseBranch}`]); // -B: 있으면 리셋
      // 새 워크트리는 node_modules가 없다(gitignored, per-worktree) — buildAndTest가 의존성을
      // 해석하려면 베이스 체크아웃의 node_modules를 심볼릭 링크로 공유한다(느린 재설치 회피).
      const nm = `${repoPath}/node_modules`;
      if (existsSync(nm) && !existsSync(`${wt}/node_modules`)) symlinkSync(nm, `${wt}/node_modules`, 'dir');
      return wt;
    },

    /** 워크트리 정리 + 미사용 로컬 fix 브랜치 삭제. 실패해도(이미 삭제됨 등) 무시 — 호출부(finally)에서 항상 호출된다.
     * openFixPr을 탄 경로는 이미 origin에 푸시·PR이 열려 있으므로 로컬 브랜치 삭제는 안전(원격/PR은 유지). */
    async removeWorktree(wt: string): Promise<void> {
      const id8 = wt.split('/').pop() ?? '';
      await run('git', ['-C', repoPath, 'worktree', 'remove', '--force', wt]).catch(() => {});
      if (id8) await run('git', ['-C', repoPath, 'branch', '-D', `fix/feedback-${id8}`]).catch(() => {});
    },

    /** 워크트리 내 변경분 통계. gate.ts의 G3(diff 규모)·G4(리스크 표면 파일 목록) 판단 입력.
     * 커밋될 형태 그대로 측정: 먼저 스테이징(git add -A)한 뒤 staged diff를 본다 — 그래야
     * Codex가 새로 추가한(untracked) 파일도 게이트에 보인다(`git diff --numstat`은 tracked 파일만 잡는다). */
    async diffStat(wt: string): Promise<{ files: string[]; lines: number }> {
      await run('git', ['-C', wt, 'add', '-A']); // 새 파일(untracked)도 게이트에 보이게 스테이징
      const { stdout } = await run('git', ['-C', wt, 'diff', '--cached', '--numstat'], { maxBuffer: 64 * 1024 * 1024 });
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
