import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { loadConfig } from './config';
import { makeDb } from './db';
import { makeGit } from './git';
import { makeSideEffects, type Sh } from './sideEffects';
import { makeCodexRunner } from './codexAdapter';
import { dispatchRow } from './dispatch';

// 킬 스위치는 설정 파싱보다 먼저 본다(외부 리뷰 #7) — 시크릿이 빠졌거나 로테이트 중인
// 환경에서도 TRIAGE_ENABLED=false는 항상 깨끗하게 멈출 수 있어야 한다.
if (process.env.TRIAGE_ENABLED === 'false') {
  console.log('TRIAGE_ENABLED=false — skip');
  process.exit(0);
}

const execFileP = promisify(execFile);
const sh: Sh = async (cmd, args, cwd) => (await execFileP(cmd, args, { cwd, maxBuffer: 10 * 1024 * 1024 })).stdout;

const cfg = loadConfig(process.env);
const db = makeDb(cfg);
const git = makeGit(cfg.repoPath, cfg.baseBranch);
const se = makeSideEffects(cfg, sh);
const runTurn = makeCodexRunner(cfg);

const rows = await db.findActionable(cfg.k, cfg.reclaimMs);
for (const row of rows) {
  // 원자적 claim: 다른 폴러 인스턴스가 먼저 가져갔으면 건너뛴다(동시 실행 안전).
  const lease = await db.claim(row.id);
  if (!lease) continue;
  // writeback을 이 클레임의 lease에 바인딩 — 리클레임당한 뒤의 늦은 기록은 던져지고(0행),
  // 행의 최종 상태는 리클레임한 쪽이 소유한다.
  const wb = { writeback: (id: string, patch: Parameters<typeof db.writeback>[2]) => db.writeback(id, lease, patch) };
  try {
    const st = await dispatchRow(row, { cfg, git, runTurn, se, db: wb });
    console.log(`feedback ${row.id} → ${st}`);
  } catch (e) {
    console.error(`feedback ${row.id} failed:`, e);
    await wb.writeback(row.id, { triage_state: 'failed' }).catch(() => {});
  }
}
