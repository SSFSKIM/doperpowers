import type { Config } from './config';
import type { BirthState } from './gate';
import { writeFileSync, mkdtempSync, unlinkSync, rmdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';

export const MARKER = 'feedback:'; // 아티팩트 본문에 심는 멱등 마커 (feedback:<id>)
export type Sh = (cmd: string, args: string[], cwd?: string) => Promise<string>;
export type WriteTmp = (name: string, content: string) => string; // 파일을 쓰고 그 경로를 반환
export type RemoveTmp = (path: string) => void;

/** 예측 불가능한 전용 디렉터리(mkdtemp) + 0600 — 원문 피드백엔 민감한 사용자 텍스트가
 * 담길 수 있다(외부 리뷰 #6). 공유 머신에서의 로컬 노출·경로 충돌을 함께 막는다. */
const defaultWriteTmp: WriteTmp = (name, content) => {
  const dir = mkdtempSync(join(tmpdir(), 'triage-'));
  const p = join(dir, name);
  writeFileSync(p, content, { mode: 0o600 });
  return p;
};

// rmdirSync는 빈 디렉터리만 지운다 — 주입된 경로가 공유 디렉터리(/tmp 등)여도 안전.
const defaultRemoveTmp: RemoveTmp = (p) => {
  try { unlinkSync(p); rmdirSync(dirname(p)); } catch { /* 이미 정리됨 등 — 무시 */ }
};

export function makeSideEffects(cfg: Config, sh: Sh, writeTmp: WriteTmp = defaultWriteTmp, removeTmp: RemoveTmp = defaultRemoveTmp) {
  return {
    /** 이 feedback_id로 이미 등록된 이슈가 있으면 반환(멱등 가드). gh는 cwd의 git remote로 repo 추론.
     * fail-closed(외부 리뷰 #5): gh 검색 실패를 "없음"으로 치환하지 않는다 — 에러는 그대로
     * 던져 이 행을 failed로 남긴다. 일시적 GitHub 장애가 중복 티켓을 만들면 안 된다. */
    async findExisting(feedbackId: string): Promise<{ issue?: string }> {
      const q = `${MARKER}${feedbackId} in:body`;
      const issOut = await sh('gh', ['issue', 'list', '--search', q, '--state', 'all', '--json', 'url'], cfg.repoPath);
      const issue = (JSON.parse(issOut || '[]')[0]?.url) as string | undefined;
      return { issue };
    },

    /** 워커가 저작한 티켓을 게이트가 정한 birth state로 등록. 본문에 마커 삽입(임시파일 → --body-file).
     * note는 park 상태에서만 전달된다(routeTicket이 보장) — board-register가 park에 note를 요구한다.
     * 임시파일은 등록 성공/실패와 무관하게 finally에서 정리한다. 반환: 이슈 URL. */
    async registerTicket(a: { feedbackId: string; title: string; category: 'bug' | 'enhancement'; priority: 'P0' | 'P1' | 'P2' | 'P3'; body: string; state: BirthState; note?: string; descriptiveLabels?: string[] }): Promise<string> {
      const body = `${a.body}\n\n<!-- ${MARKER}${a.feedbackId} -->`;
      const bodyFile = writeTmp(`triage-${a.feedbackId}.md`, body);
      try {
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
      } finally {
        removeTmp(bodyFile);
      }
    },
  };
}
