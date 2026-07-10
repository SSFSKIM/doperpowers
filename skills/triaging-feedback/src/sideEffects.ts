import type { Config } from './config';
import type { BirthState } from './gate';
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
    /** 이 feedback_id로 이미 등록된 이슈가 있으면 반환(멱등 가드). gh는 cwd의 git remote로 repo 추론. */
    async findExisting(feedbackId: string): Promise<{ issue?: string }> {
      const q = `${MARKER}${feedbackId} in:body`;
      const issOut = await sh('gh', ['issue', 'list', '--search', q, '--state', 'all', '--json', 'url'], cfg.repoPath).catch(() => '[]');
      const issue = (JSON.parse(issOut || '[]')[0]?.url) as string | undefined;
      return { issue };
    },

    /** 워커가 저작한 티켓을 게이트가 정한 birth state로 등록. 본문에 마커 삽입(임시파일 → --body-file).
     * note는 park 상태에서만 전달된다(routeTicket이 보장) — board-register가 park에 note를 요구한다.
     * 반환: 이슈 URL. */
    async registerTicket(a: { feedbackId: string; title: string; category: 'bug' | 'enhancement'; priority: 'P0' | 'P1' | 'P2' | 'P3'; body: string; state: BirthState; note?: string; descriptiveLabels?: string[] }): Promise<string> {
      const body = `${a.body}\n\n<!-- ${MARKER}${a.feedbackId} -->`;
      const bodyFile = writeTmp(`triage-${a.feedbackId}.md`, body);
      const args = [a.title, a.category, a.priority, '--state', a.state, '--body-file', bodyFile];
      if (a.note) args.push('--note', a.note);
      const out = await sh(`${cfg.boardScriptsDir}/board-register.sh`, args, cfg.repoPath);
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
