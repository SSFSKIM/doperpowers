import type { FeedbackRow } from './types';
import type { Verdict } from './verdict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const dir = dirname(fileURLToPath(import.meta.url));
const PROTOCOL = readFileSync(join(dir, '../references/triage-worker-protocol.md'), 'utf8');

export function renderTriagePrompt(row: FeedbackRow): string {
  return PROTOCOL
    .replaceAll('{{CATEGORY}}', row.category)
    .replaceAll('{{BODY}}', row.body)
    .replaceAll('{{PAGE_PATH}}', row.page_path ?? '-')
    .replaceAll('{{ROLE}}', row.role ?? '-')
    .replaceAll('{{HOST}}', row.host ?? '-')
    .replaceAll('{{FEEDBACK_ID}}', row.id);
}
export function renderFixPrompt(row: FeedbackRow, v: Verdict): string {
  return `앞선 진단(${v.root_cause})을 근거로, 보고된 증상만 최소 변경으로 수정하라. 관련 없는 리팩터·범위 확장 금지. 수정 후 빌드/테스트가 통과해야 한다.`;
}
