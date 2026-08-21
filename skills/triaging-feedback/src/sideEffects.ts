import type { Config } from './config';
import type { BirthState } from './gate';
import { writeFileSync, mkdtempSync, unlinkSync, rmdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';

export const MARKER = 'feedback:'; // 아티팩트 본문에 심는 멱등 마커 (feedback:<id>)

/** 보드가 본문 "뒤"에 붙이는 자기 meta 블록 (_board.py compose_body/META_RE).
 * 내부는 닫힘줄(`\n-->`)을 건너뛰지 못한다 — 인용된 가짜 블록은 자기 닫힘줄에서 끝나
 * 본문 끝까지 이어지지 못하므로, 여기 걸리는 건 언제나 "진짜" 트레일러 하나뿐이다.
 * (meta 값 안의 `-->`는 항상 `key: ` 뒤에 있어 줄머리에 오지 않는다 — clean_meta 참조.) */
const BOARD_META_TRAILER = /\n?<!-- board:meta\n(?:(?!\n-->)[\s\S])*\n-->\s*$/;
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
     * fail-closed(외부 리뷰 #5): gh 호출 실패를 "없음"으로 치환하지 않는다 — 에러는 그대로
     * 던져 이 행을 failed로 남긴다. 일시적 GitHub 장애가 중복 티켓을 만들면 안 된다.
     * in:body,comments — dup-병합 경로는 마커를 기존 이슈의 "코멘트"에 남기므로 둘 다 본다.
     *
     * 검색은 후보 수집일 뿐, 확정이 아니다(dp#59): GitHub 검색은 전문(full-text) 매치라
     * 다른 티켓에 인용된 원문 속 위조 마커도 — 펜스 안이든, 인젝션된 진단문 속이든 —
     * 그대로 매치된다. 진짜 마커는 registerTicket/commentOnIssue가 항상 아티팩트의
     * "마지막 줄"로 심으므로, 각 후보의 본문·코멘트 footer를 재조회해 확인한 것만 dup으로
     * 인정한다. 마커 뒤에는 어떤 사용자 유래 텍스트도 올 수 없어 footer는 위조 불가.
     *
     * 단 하나, 보드 자신은 마커 뒤에 온다: park note·spawned-by가 있는 티켓은 본문이
     * `<!-- board:meta … -->` 트레일러로 끝나므로(_board.py compose_body), footer를 보기 전에
     * 그 블록 하나를 벗겨낸다. 벗겨도 안전한 이유는 그 블록이 보드만 쓸 수 있는 자리이기
     * 때문이다: clean_meta가 meta 값 안의 `<!-- board:meta` 토큰을 거부하니 진짜 블록 안에
     * 또 다른 opener는 없고, 피드백 A의 티켓에서 트레일러를 떼면 남는 건 여전히 A의 마커다.
     * (트레이드오프: 사람이 이슈 본문을 footer 뒤로 덧편집하면 그 행은 dup 미탐지 —
     * 중복 티켓이라는 "보이는" 실패로 격하된다. 위조로 인한 조용한 피드백 드롭보다 낫다.) */
    async findExisting(feedbackId: string): Promise<{ issue?: string }> {
      const q = `${MARKER}${feedbackId} in:body,comments`;
      const issOut = await sh('gh', ['issue', 'list', '--search', q, '--state', 'all', '--json', 'url,number'], cfg.repoPath);
      const candidates: { url?: string; number?: number }[] = JSON.parse(issOut || '[]');
      const stamp = `<!-- ${MARKER}${feedbackId} -->`;
      const stamped = (text: unknown) =>
        typeof text === 'string' && text.replace(BOARD_META_TRAILER, '').trimEnd().endsWith(stamp);
      for (const c of candidates) {
        if (!c?.url || c?.number == null) continue;
        const viewOut = await sh('gh', ['issue', 'view', String(c.number), '--json', 'body,comments'], cfg.repoPath);
        const view = JSON.parse(viewOut || '{}');
        if (stamped(view.body) || ((view.comments ?? []) as { body?: string }[]).some((cm) => stamped(cm?.body))) {
          return { issue: c.url };
        }
      }
      return {};
    },

    /** 중복/관련 판단용 후보: 열린 이슈의 번호+제목(최대 40개). 실패는 빈 목록으로 —
     * 이 목록은 자문용 향상 기능이라, 스냅샷 장애가 행 전체를 죽일 이유가 없다
     * (멱등-critical한 findExisting과 달리 fail-open이 맞다: 최악이 "이번 행은 dup 미탐지"). */
    async listOpenTickets(): Promise<{ number: number; title: string }[]> {
      const out = await sh('gh', ['issue', 'list', '--state', 'open', '--json', 'number,title', '--limit', '40'], cfg.repoPath).catch(() => '[]');
      try { return JSON.parse(out || '[]'); } catch { return []; }
    },

    /** dup-병합: 새 티켓 대신 기존 이슈에 진단을 코멘트로 남긴다. 마커 포함(재실행 dedup은
     * findExisting의 in:comments가 잡는다). 기존 이슈의 상태는 절대 건드리지 않는다.
     * 반환: 이슈 URL(코멘트 fragment 제거). */
    async commentOnIssue(a: { feedbackId: string; number: number; body: string }): Promise<string> {
      const body = `${a.body}\n\n<!-- ${MARKER}${a.feedbackId} -->`;
      const bodyFile = writeTmp(`triage-${a.feedbackId}.md`, body);
      try {
        const out = await sh('gh', ['issue', 'comment', String(a.number), '--body-file', bodyFile], cfg.repoPath);
        return (out.trim().split(/\s+/).find((t) => t.startsWith('http')) ?? out.trim()).split('#')[0];
      } finally {
        removeTmp(bodyFile);
      }
    },

    /** relates 엣지(주석 전용, eligibility 무관) — 실패해도 티켓 등록 자체를 되돌릴 이유가
     * 없으므로 best-effort. */
    async relateTickets(a: number, b: number): Promise<void> {
      await sh(`${cfg.boardScriptsDir}/board-relate.sh`, [String(a), String(b)], cfg.repoPath).catch(() => '');
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
