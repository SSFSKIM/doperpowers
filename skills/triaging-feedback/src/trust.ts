import type { FeedbackRow } from './types';

export type TrustLevel = 'developer' | 'user';

/** 피드백 행의 신뢰 수준을 판별한다(2026-07-11, 2단계 신뢰 설계).
 * 1차 신호 = role: POST /api/feedback이 제출자 role을 서버에서 직접 조회해 저장하므로
 * (클라이언트 불신) 위조 불가 — trustedRoles(기본 'admin')에 속하면 developer.
 * 2차 신호 = devCode: .env의 시크릿 코드로, 본문이 `#<code>`로 시작하면 developer.
 * 코드는 본문에서 제거해 반환한다 — 그대로 두면 티켓 provenance 인용을 타고 공개
 * 이슈에 노출되어 다음 제출자부터 위조 가능해진다(코드 누출 = 즉시 로테이트 대상). */
export function resolveTrust(
  row: FeedbackRow,
  cfg: { trustedRoles: string[]; devCode?: string },
): { level: TrustLevel; body: string } {
  if (row.role && cfg.trustedRoles.includes(row.role)) return { level: 'developer', body: row.body };
  if (cfg.devCode) {
    const trimmed = row.body.trimStart();
    const prefix = `#${cfg.devCode}`;
    if (trimmed.startsWith(prefix)) return { level: 'developer', body: trimmed.slice(prefix.length).trimStart() };
  }
  return { level: 'user', body: row.body };
}
