import type { Config } from './config';
import { writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export const MARKER = 'feedback:'; // 아티팩트 본문에 심는 멱등 마커 (feedback:<id>)
export type Sh = (cmd: string, args: string[], cwd?: string) => Promise<string>;
export type WriteTmp = (name: string, content: string) => string; // 파일을 쓰고 그 경로를 반환

const defaultWriteTmp: WriteTmp = (name, content) => {
  const p = join(tmpdir(), name);
  writeFileSync(p, content);
  return p;
};

export function makeSideEffects(cfg: Config, sh: Sh, writeTmp: WriteTmp = defaultWriteTmp) {
  return {
    /** 이 feedback_id로 이미 열린 PR/이슈가 있으면 반환(멱등 가드). gh는 cwd의 git remote로 repo 추론. */
    async findExisting(feedbackId: string): Promise<{ pr?: string; issue?: string }> {
      const q = `${MARKER}${feedbackId} in:body`;
      const prOut = await sh('gh', ['pr', 'list', '--search', q, '--state', 'all', '--json', 'url'], cfg.repoPath).catch(() => '[]');
      const issOut = await sh('gh', ['issue', 'list', '--search', q, '--state', 'all', '--json', 'url'], cfg.repoPath).catch(() => '[]');
      const pr = (JSON.parse(prOut || '[]')[0]?.url) as string | undefined;
      const issue = (JSON.parse(issOut || '[]')[0]?.url) as string | undefined;
      return { pr, issue };
    },

    /** 워크트리에 이미 적용된 수정 → 커밋·푸시·PR. 본문에 마커 삽입. 반환: PR URL. */
    async openFixPr(a: { feedbackId: string; worktree: string; branch: string; title: string; body: string }): Promise<string> {
      await sh('git', ['add', '-A'], a.worktree);
      await sh('git', ['commit', '-m', a.title], a.worktree);
      await sh('git', ['push', '-u', 'origin', a.branch], a.worktree);
      const body = `${a.body}\n\n<!-- ${MARKER}${a.feedbackId} -->`;
      const out = await sh('gh', ['pr', 'create', '--base', cfg.baseBranch, '--head', a.branch, '--title', a.title, '--body', body], a.worktree);
      return out.trim().split('\n').pop() ?? out.trim();
    },

    /** needs-human 사람 티켓 등록. 본문에 마커 삽입(임시파일 → --body-file). 반환: 이슈 URL. */
    async registerTicket(a: { feedbackId: string; title: string; category: 'bug' | 'enhancement'; priority: 'P0' | 'P1' | 'P2' | 'P3'; body: string; reason: string; descriptiveLabels?: string[] }): Promise<string> {
      const body = `${a.body}\n\n<!-- ${MARKER}${a.feedbackId} -->`;
      const bodyFile = writeTmp(`triage-${a.feedbackId}.md`, body);
      const out = await sh(`${cfg.boardScriptsDir}/board-register.sh`, [a.title, a.category, a.priority, '--state', 'needs-human', '--note', a.reason, '--body-file', bodyFile], cfg.repoPath);
      const parts = out.trim().split(/\s+/);
      const num = parts[0];
      const url = parts.find((t) => t.startsWith('http')) ?? out.trim();
      const labels = a.descriptiveLabels ?? [];
      if (labels.length && num) {
        await sh('gh', ['issue', 'edit', num, '--add-label', labels.join(',')], cfg.repoPath).catch(() => '');
      }
      return url;
    },
  };
}
