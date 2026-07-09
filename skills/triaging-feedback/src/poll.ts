import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { loadConfig } from './config';
import { makeDb } from './db';
import { makeGit } from './git';
import { makeSideEffects, type Sh } from './sideEffects';
import { makeCodexRunner } from './codexAdapter';
import { dispatchRow } from './dispatch';

const execFileP = promisify(execFile);
const sh: Sh = async (cmd, args, cwd) => (await execFileP(cmd, args, { cwd, maxBuffer: 10 * 1024 * 1024 })).stdout;

const cfg = loadConfig(process.env);
if (!cfg.enabled) {
  console.log('TRIAGE_ENABLED=false — skip');
  process.exit(0);
}

const db = makeDb(cfg);
const git = makeGit(cfg.repoPath, cfg.baseBranch);
const se = makeSideEffects(cfg, sh);
const runTurn = makeCodexRunner(cfg.openaiApiKey, cfg.timeoutMs);

const rows = await db.findActionable(cfg.k, cfg.reclaimMs);
for (const row of rows) {
  // 원자적 claim: 다른 폴러 인스턴스가 먼저 가져갔으면 건너뛴다(동시 실행 안전).
  if (!(await db.claim(row.id))) continue;
  try {
    const st = await dispatchRow(row, { cfg, git, runTurn, se, db });
    console.log(`feedback ${row.id} → ${st}`);
  } catch (e) {
    console.error(`feedback ${row.id} failed:`, e);
    await db.writeback(row.id, { triage_state: 'failed' }).catch(() => {});
  }
}
