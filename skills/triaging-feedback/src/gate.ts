export type ResolvedCategory = 'bug' | 'idea' | 'question' | 'other';

// spec G4 — ida-solution 골든룰에서 그대로 옮긴 리스크 표면. 하나라도 닿으면 자동수정 불가.
export const RISK_SURFACES: RegExp[] = [
  /^lib\/auth\.ts$/, /^middleware\.ts$/,                    // auth/RLS
  /^lib\/schema\.sql$/, /^sql\/.*\.sql$/, /^types\/index\.ts$/, // migrations/schema/mirror
  /^app\/api\/ai\/generate-plan\/route\.ts$/,               // generate-plan 타임테이블 레이아웃
  /^lib\/exam-bank\.ts$/,                                    // exam-bank 저작권
  /^lib\/exam-calendar\.ts$/, /^lib\/grade-system\.ts$/,    // D-day/등급 진실
  /^lib\/anthropic\.ts$/,                                    // 서버 전용 LLM/시크릿
  /^app\/api\/cron\//, /^vercel\.json$/,                    // cron
];

export function touchesRiskSurface(paths: string[]): string | null {
  for (const p of paths) if (RISK_SURFACES.some((re) => re.test(p))) return p;
  return null;
}

export interface GateInput {
  resolvedCategory: ResolvedCategory;
  changedFiles: string[];
  diffLines: number;
  testsPassed: boolean;
  rootCauseCited: boolean;
}

export function enforceGate(i: GateInput): { pass: boolean; reason?: string } {
  if (i.resolvedCategory !== 'bug') return { pass: false, reason: `category=${i.resolvedCategory} (버그 아님)` };
  if (!i.rootCauseCited) return { pass: false, reason: '근본원인 인용 없음' };
  if (i.diffLines > 150) return { pass: false, reason: `diff ${i.diffLines}줄 > 150` };
  if (i.changedFiles.length > 5) return { pass: false, reason: `파일 ${i.changedFiles.length}개 > 5` };
  const hit = touchesRiskSurface(i.changedFiles);
  if (hit) return { pass: false, reason: `리스크 표면 접촉: ${hit}` };
  if (!i.testsPassed) return { pass: false, reason: '빌드/테스트 실패' };
  return { pass: true };
}
