import type { FeedbackRow } from './types';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const dir = dirname(fileURLToPath(import.meta.url));
const PROTOCOL = readFileSync(join(dir, '../references/triage-worker-protocol.md'), 'utf8');

// replaceAll의 두 번째 인자를 문자열로 주면 치환 문자열 안의 `$&`/`$'`/`$\`` 등이 특수 패턴으로
// 해석돼 프롬프트가 왜곡된다(F7). 함수 형태로 넘겨 리터럴 치환을 강제한다.
export function renderTriagePrompt(row: FeedbackRow): string {
  return PROTOCOL
    .replaceAll('{{CATEGORY}}', () => row.category)
    .replaceAll('{{BODY}}', () => row.body)
    .replaceAll('{{PAGE_PATH}}', () => row.page_path ?? '-')
    .replaceAll('{{ROLE}}', () => row.role ?? '-')
    .replaceAll('{{HOST}}', () => row.host ?? '-')
    .replaceAll('{{FEEDBACK_ID}}', () => row.id);
}
