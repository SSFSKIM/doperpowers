# Feedback Triage Skill (doperpowers) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `skills/triaging-feedback/` skill — a self-hosted Mac cron that polls ida-solution's `feedback` table, drives one Codex-SDK thread per new row to diagnose it, and either opens a fix PR or files a `needs-info` human ticket, writing the outcome back to the row.

**Architecture:** A Node/TypeScript program (the plugin's first non-shell subsystem, self-contained with its own `package.json`). A thin `feedback-poll.sh` launchd wrapper invokes the Node poller, which atomically claims `pending` rows and hands each to the dispatcher. The dispatcher follows **model-proposes / dispatcher-disposes**: a Codex thread only reads/edits code in an ephemeral git worktree; the dispatcher enforces the fix-gate on the *real diff*, then performs every privileged side effect (Supabase writeback, `gh pr create`, `board-register.sh`) itself. The Codex-SDK surface is pinned by a spike task before any code depends on it.

**Tech Stack:** Node 20+, TypeScript, `@openai/codex-sdk`, `@supabase/supabase-js`, Vitest (unit), `tsx` (run). Shells out to `git`, `gh`, and the issue-tracker `board-*.sh` scripts.

## Global Constraints

- **Runs on the self-hosted Mac only** — needs the ida-solution repo checked out, `gh` auth, `OPENAI_API_KEY`, and the Supabase **service-role** key (the `feedback` table is deny-all RLS). All secrets live in a git-ignored env file, never committed.
- **Depends on Plan A being live** — the `triage_*` columns must exist and the `p86` migration be applied before the poller can claim/writeback. The skill can be *built and unit-tested* without Plan A; it cannot *run* against real data until Phase 0 ships.
- **Model-proposes / dispatcher-disposes** — the Codex thread never holds DB creds or the `gh` token and is instructed not to read `.env`/secret files. Every irreversible side effect is dispatcher code.
- **Fix gate enforced on the real git diff**, not the model's self-reported verdict. The verdict is advisory.
- **Kill switches (env):** `TRIAGE_ENABLED` (master), `TRIAGE_FIX_ENABLED` (false ⇒ every bug becomes a ticket).
- **Sequential, bounded:** at most `K` rows per tick (default 3), one at a time; per-worker timeout (default 20 min); worktree removed in a `finally` on every path.
- **doperpowers commits** land on `main` (no integration-branch gate in this repo).
- **Risk-surface list is copied verbatim from the spec** (§ "Triage Worker Protocol", gate G4) — see Task 3.
- **Korean** for the worker-protocol prompt, SKILL.md prose, ticket/PR bodies, and commit messages.

---

### Task 1 (SPIKE): Pin the Codex-SDK surface

**Deliverable is knowledge, not shipped code.** The dispatcher depends on three `@openai/codex-sdk` behaviors the spec flagged as unverified. This spike answers them before Task 6 codes the adapter against them.

**Question the spike answers:** In the **TypeScript** SDK, (a) can `sandbox` be set per turn (`read_only` for diagnosis, `workspace_write` for the fix) on one thread? (b) does `resumeThread(id)` / repeated `thread.run()` carry context? (c) how is the model's final assistant text recovered from a `run()` result so the dispatcher can extract the fenced-JSON verdict? (d) does it run headless with only `OPENAI_API_KEY` and operate inside a specified `cwd`/worktree?

**Files:**
- Create (throwaway): `skills/triaging-feedback/spike/codex-probe.mjs`

- [ ] **Step 1: Install the SDK in a scratch dir**

```bash
mkdir -p skills/triaging-feedback/spike && cd skills/triaging-feedback/spike
npm init -y >/dev/null && npm install @openai/codex-sdk
```

- [ ] **Step 2: Probe per-turn sandbox, resume, and text recovery**

Write `codex-probe.mjs` that: creates a temp git worktree with one known file; starts a thread; runs turn 1 with `read_only` asking "print the value of X in file Y and output a fenced ```json block {\"seen\":true}```"; runs turn 2 with `workspace_write` asking to append a line to a file; logs the full `result` object shape of each `run()` (so we learn where the assistant text lives) and whether the turn-2 write actually landed on disk.

```js
import { Codex } from "@openai/codex-sdk";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { execSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";

const wt = mkdtempSync(join(tmpdir(), "codex-probe-"));
execSync("git init -q && git commit -q --allow-empty -m init", { cwd: wt });
writeFileSync(join(wt, "known.txt"), "X = 42\n");

const codex = new Codex();               // reads OPENAI_API_KEY from env
const thread = codex.startThread({ workingDirectory: wt }); // <- confirm option name in the spike
const r1 = await thread.run("Read known.txt and reply with a fenced ```json {\"x\": <value>}``` block.", { sandbox: "read_only" });
console.log("R1 KEYS:", Object.keys(r1));
console.log("R1 RAW:", JSON.stringify(r1, null, 2).slice(0, 2000));
const r2 = await thread.run("Append a line 'touched' to known.txt.", { sandbox: "workspace_write" });
console.log("WROTE?", readFileSync(join(wt, "known.txt"), "utf8").includes("touched"));
console.log("THREAD ID:", thread.id ?? "(none exposed)");
```

- [ ] **Step 3: Run it and record the shape**

Run: `OPENAI_API_KEY=… node skills/triaging-feedback/spike/codex-probe.mjs`
Observe and write down: the exact option name for the working directory; the exact per-turn sandbox option name/values; the property path to the assistant's final text on the `run()` result; whether `WROTE? true`; whether a thread id is exposed for resume.

- [ ] **Step 4: Apply the promote-or-discard criteria**

Record findings in the spec's `## Surprises & Discoveries` (append a dated bullet). Then:
- **Promote** if per-turn sandbox + text recovery both work in TS → Task 6 codes `codexAdapter.ts` against the confirmed shape; delete `spike/`.
- **Discard-and-pivot** if TS lacks per-turn sandbox → fall back to the **Python** SDK (`openai-codex`, which the docs show *does* expose `Sandbox` presets per turn) and note the language pivot in the spec's `## Decision Log`; the rest of this plan's pure-TS units are unaffected only if the dispatcher stays Node — if pivoting to Python, Tasks 3–5's pure logic port to Python with the same shapes.

```bash
rm -rf skills/triaging-feedback/spike   # knowledge captured in the spec; code is throwaway
```

---

### Task 2: Skill scaffold + config

**Files:**
- Create: `skills/triaging-feedback/package.json`
- Create: `skills/triaging-feedback/tsconfig.json`
- Create: `skills/triaging-feedback/src/config.ts`
- Create: `skills/triaging-feedback/.gitignore`
- Test: `skills/triaging-feedback/test/config.test.ts`

**Interfaces:**
- Produces: `loadConfig(env): Config` where `Config = { supabaseUrl, supabaseServiceKey, openaiApiKey, repoPath, baseBranch, boardScriptsDir, k, timeoutMs, enabled, fixEnabled, reclaimMs }`. All later tasks read `Config`.

- [ ] **Step 1: Write the failing test**

Create `skills/triaging-feedback/test/config.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { loadConfig } from '../src/config';

const base = {
  SUPABASE_URL: 'https://x.supabase.co', SUPABASE_SERVICE_ROLE_KEY: 'k',
  OPENAI_API_KEY: 'o', TRIAGE_REPO_PATH: '/repo', TRIAGE_BASE_BRANCH: 'feat/m4.5-polish',
  TRIAGE_BOARD_SCRIPTS_DIR: '/board',
};

describe('loadConfig', () => {
  it('parses required fields and applies defaults', () => {
    const c = loadConfig(base);
    expect(c.supabaseUrl).toBe('https://x.supabase.co');
    expect(c.k).toBe(3);
    expect(c.timeoutMs).toBe(20 * 60_000);
    expect(c.enabled).toBe(true);      // TRIAGE_ENABLED unset ⇒ default on
    expect(c.fixEnabled).toBe(true);   // TRIAGE_FIX_ENABLED unset ⇒ default on
  });
  it('honors kill switches and overrides', () => {
    const c = loadConfig({ ...base, TRIAGE_ENABLED: 'false', TRIAGE_FIX_ENABLED: 'false', TRIAGE_K: '1' });
    expect(c.enabled).toBe(false);
    expect(c.fixEnabled).toBe(false);
    expect(c.k).toBe(1);
  });
  it('throws when a required secret is missing', () => {
    expect(() => loadConfig({ ...base, SUPABASE_SERVICE_ROLE_KEY: '' })).toThrow(/SUPABASE_SERVICE_ROLE_KEY/);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd skills/triaging-feedback && npm install && npx vitest run test/config.test.ts`
Expected: FAIL — cannot resolve `../src/config`.

- [ ] **Step 3: Write `package.json`, `tsconfig.json`, `.gitignore`, `config.ts`**

`skills/triaging-feedback/package.json`:
```json
{
  "name": "triaging-feedback",
  "private": true,
  "type": "module",
  "scripts": { "test": "vitest run", "poll": "tsx src/poll.ts" },
  "dependencies": { "@openai/codex-sdk": "*", "@supabase/supabase-js": "^2" },
  "devDependencies": { "typescript": "^5", "tsx": "^4", "vitest": "^2" }
}
```

`skills/triaging-feedback/tsconfig.json`:
```json
{ "compilerOptions": { "target": "ES2022", "module": "ES2022", "moduleResolution": "bundler", "strict": true, "esModuleInterop": true, "skipLibCheck": true } }
```

`skills/triaging-feedback/.gitignore`:
```
node_modules/
.env
spike/
```

`skills/triaging-feedback/src/config.ts`:
```ts
export interface Config {
  supabaseUrl: string; supabaseServiceKey: string; openaiApiKey: string;
  repoPath: string; baseBranch: string; boardScriptsDir: string;
  k: number; timeoutMs: number; reclaimMs: number;
  enabled: boolean; fixEnabled: boolean;
}

function req(env: Record<string, string | undefined>, key: string): string {
  const v = env[key];
  if (!v) throw new Error(`missing required env: ${key}`);
  return v;
}

export function loadConfig(env: Record<string, string | undefined>): Config {
  return {
    supabaseUrl: req(env, 'SUPABASE_URL'),
    supabaseServiceKey: req(env, 'SUPABASE_SERVICE_ROLE_KEY'),
    openaiApiKey: req(env, 'OPENAI_API_KEY'),
    repoPath: req(env, 'TRIAGE_REPO_PATH'),
    baseBranch: req(env, 'TRIAGE_BASE_BRANCH'),
    boardScriptsDir: req(env, 'TRIAGE_BOARD_SCRIPTS_DIR'),
    k: env.TRIAGE_K ? Number(env.TRIAGE_K) : 3,
    timeoutMs: env.TRIAGE_TIMEOUT_MS ? Number(env.TRIAGE_TIMEOUT_MS) : 20 * 60_000,
    reclaimMs: env.TRIAGE_RECLAIM_MS ? Number(env.TRIAGE_RECLAIM_MS) : 30 * 60_000,
    enabled: env.TRIAGE_ENABLED !== 'false',
    fixEnabled: env.TRIAGE_FIX_ENABLED !== 'false',
  };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run test/config.test.ts`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add skills/triaging-feedback/package.json skills/triaging-feedback/tsconfig.json skills/triaging-feedback/.gitignore skills/triaging-feedback/src/config.ts skills/triaging-feedback/test/config.test.ts
git commit -m "feat(triaging-feedback): 스킬 스캐폴드 + config 로더(kill switch·기본값)"
```

---

### Task 3: The fix gate (pure, TDD) — the safety-critical unit

**Files:**
- Create: `skills/triaging-feedback/src/gate.ts`
- Test: `skills/triaging-feedback/test/gate.test.ts`

**Interfaces:**
- Produces: `RISK_SURFACES: RegExp[]`; `touchesRiskSurface(paths: string[]): string | null` (returns the first offending path or null); `enforceGate(input): { pass: boolean; reason?: string }` where `input = { resolvedCategory, changedFiles: string[], diffLines: number, testsPassed: boolean, rootCauseCited: boolean }`.

- [ ] **Step 1: Write the failing test**

Create `skills/triaging-feedback/test/gate.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { touchesRiskSurface, enforceGate } from '../src/gate';

const ok = {
  resolvedCategory: 'bug' as const, changedFiles: ['components/today/Card.tsx'],
  diffLines: 20, testsPassed: true, rootCauseCited: true,
};

describe('touchesRiskSurface', () => {
  it.each([
    'lib/auth.ts', 'middleware.ts', 'sql/p87_new.sql', 'lib/schema.sql',
    'types/index.ts', 'lib/anthropic.ts', 'lib/exam-calendar.ts', 'lib/grade-system.ts',
    'lib/exam-bank.ts', 'app/api/cron/x/route.ts', 'vercel.json',
    'app/api/ai/generate-plan/route.ts',
  ])('flags %s', (p) => { expect(touchesRiskSurface([p])).toBe(p); });

  it('allows benign paths', () => {
    expect(touchesRiskSurface(['components/today/Card.tsx', 'app/hq/feedback/FeedbackListClient.tsx'])).toBeNull();
  });
});

describe('enforceGate', () => {
  it('passes a clean, small, cited bug fix', () => {
    expect(enforceGate(ok)).toEqual({ pass: true });
  });
  it('fails on non-bug category', () => {
    expect(enforceGate({ ...ok, resolvedCategory: 'idea' }).pass).toBe(false);
  });
  it('fails on oversized diff (lines)', () => {
    expect(enforceGate({ ...ok, diffLines: 151 }).pass).toBe(false);
  });
  it('fails on too many files', () => {
    expect(enforceGate({ ...ok, changedFiles: ['a','b','c','d','e','f'] }).pass).toBe(false);
  });
  it('fails on risk-surface touch even when everything else is fine', () => {
    const r = enforceGate({ ...ok, changedFiles: ['lib/auth.ts'] });
    expect(r.pass).toBe(false);
    expect(r.reason).toContain('lib/auth.ts');
  });
  it('fails when tests did not pass', () => {
    expect(enforceGate({ ...ok, testsPassed: false }).pass).toBe(false);
  });
  it('fails when root cause is not cited', () => {
    expect(enforceGate({ ...ok, rootCauseCited: false }).pass).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run test/gate.test.ts`
Expected: FAIL — cannot resolve `../src/gate`.

- [ ] **Step 3: Write `gate.ts`** (risk-surface list copied verbatim from spec G4)

```ts
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run test/gate.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/triaging-feedback/src/gate.ts skills/triaging-feedback/test/gate.test.ts
git commit -m "feat(triaging-feedback): 픽스 게이트(리스크표면·크기·테스트·인용) — 안전 핵심 유닛 TDD"
```

---

### Task 4: Verdict parser (pure, TDD)

**Files:**
- Create: `skills/triaging-feedback/src/verdict.ts`
- Test: `skills/triaging-feedback/test/verdict.test.ts`

**Interfaces:**
- Produces: `Verdict = { feedback_id: string; resolved_category: ResolvedCategory; route: 'fix'|'ticket'; root_cause: string; reason_if_ticket?: string; confidence: 'high'|'medium'|'low' }`; `parseVerdict(modelText: string): Verdict | null` (extracts the last fenced ```json block, validates required fields; returns null on malformed).

- [ ] **Step 1: Write the failing test**

Create `skills/triaging-feedback/test/verdict.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { parseVerdict } from '../src/verdict';

const good = 'blah\n```json\n{"feedback_id":"f1","resolved_category":"bug","route":"fix","root_cause":"foo.ts:12 널 참조","confidence":"high"}\n```\nend';

describe('parseVerdict', () => {
  it('extracts a well-formed fenced verdict', () => {
    const v = parseVerdict(good);
    expect(v?.route).toBe('fix');
    expect(v?.resolved_category).toBe('bug');
    expect(v?.feedback_id).toBe('f1');
  });
  it('returns null when no fenced json present', () => {
    expect(parseVerdict('no json here')).toBeNull();
  });
  it('returns null on invalid JSON', () => {
    expect(parseVerdict('```json\n{not json}\n```')).toBeNull();
  });
  it('returns null when a required field is missing', () => {
    expect(parseVerdict('```json\n{"route":"fix"}\n```')).toBeNull();
  });
  it('returns null on an out-of-enum route', () => {
    expect(parseVerdict('```json\n{"feedback_id":"f","resolved_category":"bug","route":"merge","root_cause":"x","confidence":"high"}\n```')).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run test/verdict.test.ts`
Expected: FAIL — cannot resolve `../src/verdict`.

- [ ] **Step 3: Write `verdict.ts`**

```ts
import type { ResolvedCategory } from './gate';

export interface Verdict {
  feedback_id: string;
  resolved_category: ResolvedCategory;
  route: 'fix' | 'ticket';
  root_cause: string;
  reason_if_ticket?: string;
  confidence: 'high' | 'medium' | 'low';
}

const CATS = ['bug', 'idea', 'question', 'other'];

export function parseVerdict(text: string): Verdict | null {
  const blocks = [...text.matchAll(/```json\s*([\s\S]*?)```/g)];
  if (blocks.length === 0) return null;
  let raw: unknown;
  try { raw = JSON.parse(blocks[blocks.length - 1][1].trim()); } catch { return null; }
  if (typeof raw !== 'object' || raw === null) return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.feedback_id !== 'string') return null;
  if (typeof o.root_cause !== 'string') return null;
  if (typeof o.resolved_category !== 'string' || !CATS.includes(o.resolved_category)) return null;
  if (o.route !== 'fix' && o.route !== 'ticket') return null;
  if (o.confidence !== 'high' && o.confidence !== 'medium' && o.confidence !== 'low') return null;
  return {
    feedback_id: o.feedback_id,
    resolved_category: o.resolved_category as ResolvedCategory,
    route: o.route,
    root_cause: o.root_cause,
    reason_if_ticket: typeof o.reason_if_ticket === 'string' ? o.reason_if_ticket : undefined,
    confidence: o.confidence,
  };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run test/verdict.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/triaging-feedback/src/verdict.ts skills/triaging-feedback/test/verdict.test.ts
git commit -m "feat(triaging-feedback): 펜스드-JSON verdict 파서(스키마 검증·malformed→null)"
```

---

### Task 5: Category pre-router (pure, TDD)

**Files:**
- Create: `skills/triaging-feedback/src/route.ts`
- Test: `skills/triaging-feedback/test/route.test.ts`

**Interfaces:**
- Produces: `preRoute(category: 'bug'|'idea'|'question'|'other'): 'diagnose' | 'ticket'` — `idea`/`question` → `ticket` (never reach diagnosis/`workspace_write`); `bug` → `diagnose`; `other` → `diagnose` (the worker infers and may still emit `route:ticket`).

- [ ] **Step 1: Write the failing test**

Create `skills/triaging-feedback/test/route.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { preRoute } from '../src/route';

describe('preRoute', () => {
  it('idea → ticket', () => expect(preRoute('idea')).toBe('ticket'));
  it('question → ticket', () => expect(preRoute('question')).toBe('ticket'));
  it('bug → diagnose', () => expect(preRoute('bug')).toBe('diagnose'));
  it('other → diagnose (worker infers)', () => expect(preRoute('other')).toBe('diagnose'));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run test/route.test.ts`
Expected: FAIL — cannot resolve `../src/route`.

- [ ] **Step 3: Write `route.ts`**

```ts
import type { FeedbackCategory } from './types';

/** 카테고리 우선 라우팅. idea/question은 절대 workspace_write로 가지 않는다. */
export function preRoute(category: FeedbackCategory): 'diagnose' | 'ticket' {
  if (category === 'idea' || category === 'question') return 'ticket';
  return 'diagnose'; // bug, other
}
```

Create `skills/triaging-feedback/src/types.ts` (shared row shape mirroring ida `Feedback`):
```ts
export type FeedbackCategory = 'bug' | 'idea' | 'question' | 'other';
export type TriageState = 'pending' | 'claimed' | 'fixed' | 'ticketed' | 'skipped' | 'failed';

export interface FeedbackRow {
  id: string; user_id: string; role: string | null; academy_id: string | null;
  category: FeedbackCategory; body: string; page_path: string | null;
  host: string | null; created_at: string; triage_state: TriageState;
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run test/route.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/triaging-feedback/src/route.ts skills/triaging-feedback/src/types.ts skills/triaging-feedback/test/route.test.ts
git commit -m "feat(triaging-feedback): 카테고리 프리라우터(idea/question→ticket) + 공유 FeedbackRow 타입"
```

---

### Task 6: Codex adapter (from spike findings)

**Files:**
- Create: `skills/triaging-feedback/src/codexAdapter.ts`

**Interfaces:**
- Produces: `runTurn(opts: { worktree: string; prompt: string; sandbox: 'read_only'|'workspace_write'; thread?: CodexThread }): Promise<{ text: string; thread: CodexThread }>` — a thin seam over `@openai/codex-sdk`, coded against the **property paths confirmed in Task 1's spike**. Later tasks depend only on this signature, never on the SDK directly, so the dispatcher stays unit-testable with a mocked `runTurn`.

- [ ] **Step 1: Implement the seam using the spike's confirmed shape**

Write `codexAdapter.ts`. The bracketed spots marked `/* SPIKE */` are filled with the exact option names / result path the spike recorded (Task 1 Step 3):

```ts
import { Codex } from '@openai/codex-sdk';

export type CodexThread = ReturnType<Codex['startThread']>;

const codex = new Codex(); // OPENAI_API_KEY from env

export async function runTurn(opts: {
  worktree: string; prompt: string; sandbox: 'read_only' | 'workspace_write'; thread?: CodexThread;
}): Promise<{ text: string; thread: CodexThread }> {
  const thread = opts.thread ?? codex.startThread({ workingDirectory: opts.worktree } /* SPIKE: option name */);
  const result = await thread.run(opts.prompt, { sandbox: opts.sandbox } /* SPIKE: per-turn sandbox */);
  const text = extractText(result); /* SPIKE: result → assistant text path */
  return { text, thread };
}

function extractText(result: unknown): string {
  // Filled per spike Step 3. Placeholder shape until then:
  const r = result as { finalResponse?: string; output?: string };
  return r.finalResponse ?? r.output ?? String(result);
}
```

- [ ] **Step 2: Smoke-check it compiles**

Run: `npx tsc --noEmit`
Expected: exit 0. (No unit test here — this is the thin, SDK-bound seam; it is exercised end-to-end in Task 12's shadow run. All logic that *can* be tested without the SDK lives in Tasks 3–5 and 9.)

- [ ] **Step 3: Commit**

```bash
git add skills/triaging-feedback/src/codexAdapter.ts
git commit -m "feat(triaging-feedback): Codex-SDK 어댑터 seam(runTurn) — 스파이크 확정 형태 반영"
```

---

### Task 7: Supabase adapter (claim / writeback / actionable)

**Files:**
- Create: `skills/triaging-feedback/src/db.ts`
- Test: `skills/triaging-feedback/test/db.test.ts`

**Interfaces:**
- Produces: `makeDb(cfg)` → `{ findActionable(k, reclaimMs): Promise<FeedbackRow[]>, claim(id): Promise<boolean>, writeback(id, patch): Promise<void> }` where `patch = { triage_state, triage_pr_url?, triage_issue_url? }`. `claim` returns true only if it transitioned `pending → claimed` (atomic).

- [ ] **Step 1: Write the failing test (claim atomicity via a fake client)**

Create `skills/triaging-feedback/test/db.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { claimQuery } from '../src/db';

describe('claimQuery', () => {
  it('claims only when triage_state is pending (row returned)', async () => {
    const chain = { update: vi.fn().mockReturnThis(), eq: vi.fn().mockReturnThis(),
      select: vi.fn().mockResolvedValue({ data: [{ id: 'a' }], error: null }) };
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    expect(await claimQuery(client, 'a')).toBe(true);
    expect(chain.update).toHaveBeenCalledWith(expect.objectContaining({ triage_state: 'claimed' }));
    // guarded on id AND pending
    expect(chain.eq).toHaveBeenCalledWith('id', 'a');
    expect(chain.eq).toHaveBeenCalledWith('triage_state', 'pending');
  });
  it('returns false when nothing was claimable (0 rows)', async () => {
    const chain = { update: vi.fn().mockReturnThis(), eq: vi.fn().mockReturnThis(),
      select: vi.fn().mockResolvedValue({ data: [], error: null }) };
    const client = { from: vi.fn().mockReturnValue(chain) } as any;
    expect(await claimQuery(client, 'a')).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run test/db.test.ts`
Expected: FAIL — cannot resolve `../src/db`.

- [ ] **Step 3: Write `db.ts`**

```ts
import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type { Config } from './config';
import type { FeedbackRow, TriageState } from './types';

/** 원자적 클레임: pending인 경우에만 claimed로. 반환행이 있으면 이 폴러가 소유. */
export async function claimQuery(client: SupabaseClient, id: string): Promise<boolean> {
  const { data, error } = await client
    .from('feedback')
    .update({ triage_state: 'claimed', triaged_at: new Date().toISOString() })
    .eq('id', id)
    .eq('triage_state', 'pending')
    .select('id');
  if (error) throw error;
  return (data?.length ?? 0) > 0;
}

export function makeDb(cfg: Config) {
  const client = createClient(cfg.supabaseUrl, cfg.supabaseServiceKey, { auth: { persistSession: false } });
  return {
    async findActionable(k: number, reclaimMs: number): Promise<FeedbackRow[]> {
      const staleBefore = new Date(Date.now() - reclaimMs).toISOString();
      const { data, error } = await client
        .from('feedback')
        .select('id,user_id,role,academy_id,category,body,page_path,host,created_at,triage_state')
        .or(`triage_state.eq.pending,and(triage_state.eq.claimed,triaged_at.lt.${staleBefore})`)
        .order('created_at', { ascending: true })
        .limit(k);
      if (error) throw error;
      return (data ?? []) as FeedbackRow[];
    },
    claim: (id: string) => claimQuery(client, id),
    async writeback(id: string, patch: { triage_state: TriageState; triage_pr_url?: string; triage_issue_url?: string }) {
      const { error } = await client.from('feedback')
        .update({ ...patch, triaged_at: new Date().toISOString() }).eq('id', id);
      if (error) throw error;
    },
  };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run test/db.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/triaging-feedback/src/db.ts skills/triaging-feedback/test/db.test.ts
git commit -m "feat(triaging-feedback): Supabase 어댑터(원자적 claim·findActionable·writeback)"
```

---

### Task 8: GitHub + board side-effects (PR / ticket / idempotency)

**Files:**
- Create: `skills/triaging-feedback/src/sideEffects.ts`
- Test: `skills/triaging-feedback/test/sideEffects.test.ts`

**Interfaces:**
- Produces: `makeSideEffects(cfg, sh)` → `{ findExisting(feedbackId): Promise<{pr?:string;issue?:string}>, openFixPr(args): Promise<string>, registerTicket(args): Promise<string> }`, where `sh(cmd, args): Promise<string>` runs a command (injected so it can be mocked). Every artifact carries the marker `feedback:<id>` in its body → idempotency.

- [ ] **Step 1: Write the failing test (idempotency marker + board invocation)**

Create `skills/triaging-feedback/test/sideEffects.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { makeSideEffects, MARKER } from '../src/sideEffects';

const cfg: any = { repoPath: '/repo', baseBranch: 'feat/m4.5-polish', boardScriptsDir: '/board' };

describe('sideEffects', () => {
  it('registerTicket calls board-register.sh with needs-info + note and embeds the marker', async () => {
    const sh = vi.fn().mockResolvedValue('142 https://github.com/o/r/issues/142');
    const se = makeSideEffects(cfg, sh);
    const url = await se.registerTicket({ feedbackId: 'f9', title: '제목', category: 'enhancement', priority: 'P2', body: '본문', reason: '사람 판단 필요' });
    expect(url).toContain('/issues/142');
    const [cmd, args] = sh.mock.calls[0];
    expect(cmd).toBe('/board/board-register.sh');
    expect(args).toEqual(expect.arrayContaining(['제목', 'enhancement', 'P2', '--state', 'needs-info', '--note', '사람 판단 필요']));
    // marker embedded so findExisting can dedup later
    expect(args.join(' ')).toContain(`${MARKER}f9`);
  });

  it('findExisting parses a prior PR by marker search', async () => {
    const sh = vi.fn().mockResolvedValue(JSON.stringify([{ url: 'https://github.com/o/r/pull/50' }]));
    const se = makeSideEffects(cfg, sh);
    const found = await se.findExisting('f9');
    expect(found.pr).toBe('https://github.com/o/r/pull/50');
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run test/sideEffects.test.ts`
Expected: FAIL — cannot resolve `../src/sideEffects`.

- [ ] **Step 3: Write `sideEffects.ts`**

```ts
import type { Config } from './config';

export const MARKER = 'feedback:'; // 아티팩트 본문에 심는 멱등 마커 (feedback:<id>)
export type Sh = (cmd: string, args: string[], cwd?: string) => Promise<string>;

export function makeSideEffects(cfg: Config, sh: Sh) {
  return {
    /** 이 feedback_id로 이미 열린 PR/이슈가 있으면 반환(멱등 가드). */
    async findExisting(feedbackId: string): Promise<{ pr?: string; issue?: string }> {
      const q = `${MARKER}${feedbackId} in:body`;
      const prOut = await sh('gh', ['pr', 'list', '--repo', cfg.repoPath, '--search', q, '--state', 'all', '--json', 'url'], cfg.repoPath).catch(() => '[]');
      const issOut = await sh('gh', ['issue', 'list', '--repo', cfg.repoPath, '--search', q, '--state', 'all', '--json', 'url'], cfg.repoPath).catch(() => '[]');
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
      const out = await sh('gh', ['pr', 'create', '--repo', cfg.repoPath, '--base', cfg.baseBranch, '--head', a.branch, '--title', a.title, '--body', body], a.worktree);
      return out.trim().split('\n').pop() ?? out.trim();
    },

    /** needs-info 사람 티켓 등록. 본문에 마커 삽입. 반환: 이슈 URL. */
    async registerTicket(a: { feedbackId: string; title: string; category: 'bug' | 'enhancement'; priority: 'P0'|'P1'|'P2'|'P3'; body: string; reason: string }): Promise<string> {
      const body = `${a.body}\n\n<!-- ${MARKER}${a.feedbackId} -->`;
      const out = await sh(`${cfg.boardScriptsDir}/board-register.sh`, [a.title, a.category, a.priority, '--state', 'needs-info', '--note', a.reason, '--body', body]);
      // board-register.sh prints "<number> <url>"
      const url = out.trim().split(/\s+/).find((t) => t.startsWith('http'));
      return url ?? out.trim();
    },
  };
}
```

> **Plan-time note (board labels):** `board-register.sh` manages `status:`/`priority:`/`category` labels but not arbitrary `source:user-feedback` / `type:question` labels. After `registerTicket`, add those descriptive labels with `gh issue edit <n> --add-label source:user-feedback[,type:question]` — these are **not** `status:*` labels, so they don't violate the board's status-label Hard Gate. Confirm the labels exist (create once with `gh label create`) during Task 10 setup. If `board-register.sh` lacks a `--body` flag, seed the body via `gh issue edit <n> --body` immediately after registration instead.

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run test/sideEffects.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/triaging-feedback/src/sideEffects.ts skills/triaging-feedback/test/sideEffects.test.ts
git commit -m "feat(triaging-feedback): GitHub/board 사이드이펙트(PR·needs-info 티켓·마커 멱등)"
```

---

### Task 9: The dispatcher (orchestration, TDD with mocked adapters)

**Files:**
- Create: `skills/triaging-feedback/src/dispatch.ts`
- Test: `skills/triaging-feedback/test/dispatch.test.ts`

**Interfaces:**
- Consumes: `runTurn` (Task 6), `makeDb` (7), `makeSideEffects` (8), `enforceGate`/`touchesRiskSurface` (3), `parseVerdict` (4), `preRoute` (5).
- Produces: `dispatchRow(row, deps): Promise<TriageState>` where `deps` bundles the adapters + `cfg` + a `git` helper. Pure orchestration; every external effect is an injected dep, so this is fully unit-testable.

- [ ] **Step 1: Write the failing test (three routes with mocks)**

Create `skills/triaging-feedback/test/dispatch.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { dispatchRow } from '../src/dispatch';

const row = { id: 'f1', category: 'bug', body: '버튼이 안 눌려요', host: 'app', page_path: '/today', role: 'student' } as any;

function deps(over: any = {}) {
  return {
    cfg: { fixEnabled: true, baseBranch: 'feat/m4.5-polish' } as any,
    git: { addWorktree: vi.fn().mockResolvedValue('/wt'), removeWorktree: vi.fn(), diffStat: vi.fn().mockResolvedValue({ files: ['components/x.tsx'], lines: 10 }), buildAndTest: vi.fn().mockResolvedValue(true) },
    runTurn: vi.fn()
      .mockResolvedValueOnce({ text: '```json\n{"feedback_id":"f1","resolved_category":"bug","route":"fix","root_cause":"x.tsx:3 핸들러 누락","confidence":"high"}\n```', thread: {} })
      .mockResolvedValueOnce({ text: 'applied', thread: {} }),
    se: { findExisting: vi.fn().mockResolvedValue({}), openFixPr: vi.fn().mockResolvedValue('https://gh/pull/9'), registerTicket: vi.fn().mockResolvedValue('https://gh/issues/9') },
    db: { writeback: vi.fn() },
    ...over,
  };
}

describe('dispatchRow', () => {
  it('bug that passes the gate → fix PR, writeback fixed', async () => {
    const d = deps();
    const st = await dispatchRow(row, d);
    expect(st).toBe('fixed');
    expect(d.se.openFixPr).toHaveBeenCalled();
    expect(d.db.writeback).toHaveBeenCalledWith('f1', expect.objectContaining({ triage_state: 'fixed', triage_pr_url: 'https://gh/pull/9' }));
    expect(d.git.removeWorktree).toHaveBeenCalled();
  });

  it('idea → ticket without ever raising the sandbox', async () => {
    const d = deps({ runTurn: vi.fn().mockResolvedValue({ text: '```json\n{"feedback_id":"f1","resolved_category":"idea","route":"ticket","root_cause":"기능 요청","confidence":"low"}\n```', thread: {} }) });
    const st = await dispatchRow({ ...row, category: 'idea' }, d);
    expect(st).toBe('ticketed');
    // only the read_only diagnosis turn ran; no workspace_write
    expect(d.runTurn).toHaveBeenCalledTimes(1);
    expect(d.runTurn).toHaveBeenCalledWith(expect.objectContaining({ sandbox: 'read_only' }));
    expect(d.se.registerTicket).toHaveBeenCalled();
  });

  it('bug whose fix touches a risk surface → ticket, not PR', async () => {
    const d = deps({ git: { addWorktree: vi.fn().mockResolvedValue('/wt'), removeWorktree: vi.fn(), diffStat: vi.fn().mockResolvedValue({ files: ['lib/auth.ts'], lines: 5 }), buildAndTest: vi.fn().mockResolvedValue(true) } });
    const st = await dispatchRow(row, d);
    expect(st).toBe('ticketed');
    expect(d.se.openFixPr).not.toHaveBeenCalled();
    expect(d.se.registerTicket).toHaveBeenCalledWith(expect.objectContaining({ reason: expect.stringContaining('lib/auth.ts') }));
  });

  it('TRIAGE_FIX_ENABLED=false → bug becomes a ticket', async () => {
    const d = deps({ cfg: { fixEnabled: false, baseBranch: 'b' } });
    const st = await dispatchRow(row, d);
    expect(st).toBe('ticketed');
    expect(d.se.openFixPr).not.toHaveBeenCalled();
  });

  it('already-handled row (idempotency) → skips acting, writes back existing url', async () => {
    const d = deps({ se: { findExisting: vi.fn().mockResolvedValue({ pr: 'https://gh/pull/1' }), openFixPr: vi.fn(), registerTicket: vi.fn() }, db: { writeback: vi.fn() } });
    const st = await dispatchRow(row, d);
    expect(st).toBe('fixed');
    expect(d.se.openFixPr).not.toHaveBeenCalled();
    expect(d.db.writeback).toHaveBeenCalledWith('f1', expect.objectContaining({ triage_pr_url: 'https://gh/pull/1' }));
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run test/dispatch.test.ts`
Expected: FAIL — cannot resolve `../src/dispatch`.

- [ ] **Step 3: Write `dispatch.ts`**

```ts
import type { FeedbackRow, TriageState } from './types';
import { preRoute } from './route';
import { parseVerdict } from './verdict';
import { enforceGate } from './gate';
import { renderTriagePrompt, renderFixPrompt } from './prompt';

export interface Deps {
  cfg: { fixEnabled: boolean; baseBranch: string };
  git: {
    addWorktree(feedbackId: string): Promise<string>;
    removeWorktree(wt: string): Promise<void>;
    diffStat(wt: string): Promise<{ files: string[]; lines: number }>;
    buildAndTest(wt: string): Promise<boolean>;
  };
  runTurn(o: { worktree: string; prompt: string; sandbox: 'read_only' | 'workspace_write'; thread?: unknown }): Promise<{ text: string; thread: unknown }>;
  se: {
    findExisting(id: string): Promise<{ pr?: string; issue?: string }>;
    openFixPr(a: { feedbackId: string; worktree: string; branch: string; title: string; body: string }): Promise<string>;
    registerTicket(a: { feedbackId: string; title: string; category: 'bug' | 'enhancement'; priority: 'P0'|'P1'|'P2'|'P3'; body: string; reason: string }): Promise<string>;
  };
  db: { writeback(id: string, patch: { triage_state: TriageState; triage_pr_url?: string; triage_issue_url?: string }): Promise<void> };
}

export async function dispatchRow(row: FeedbackRow, d: Deps): Promise<TriageState> {
  // 멱등 가드: 이미 이 피드백으로 만든 아티팩트가 있으면 재실행하지 않는다.
  const existing = await d.se.findExisting(row.id);
  if (existing.pr) { await d.db.writeback(row.id, { triage_state: 'fixed', triage_pr_url: existing.pr }); return 'fixed'; }
  if (existing.issue) { await d.db.writeback(row.id, { triage_state: 'ticketed', triage_issue_url: existing.issue }); return 'ticketed'; }

  const wt = await d.git.addWorktree(row.id);
  try {
    // turn 1: read_only 진단 (body = untrusted data)
    const { text, thread } = await d.runTurn({ worktree: wt, prompt: renderTriagePrompt(row), sandbox: 'read_only' });
    const verdict = parseVerdict(text);
    if (!verdict) { await d.db.writeback(row.id, { triage_state: 'failed' }); return 'failed'; }

    const wantsFix = d.cfg.fixEnabled && preRoute(row.category) === 'diagnose' && verdict.route === 'fix';
    if (!wantsFix) {
      const url = await d.se.registerTicket({ feedbackId: row.id, title: ticketTitle(row), category: row.category === 'bug' ? 'bug' : 'enhancement', priority: 'P2', body: ticketBody(row, verdict.root_cause), reason: verdict.reason_if_ticket ?? '자동 수정 대상 아님' });
      await d.db.writeback(row.id, { triage_state: 'ticketed', triage_issue_url: url });
      return 'ticketed';
    }

    // turn 2: workspace_write 수정
    await d.runTurn({ worktree: wt, prompt: renderFixPrompt(row, verdict), sandbox: 'workspace_write', thread });
    const stat = await d.git.diffStat(wt);
    const testsPassed = await d.git.buildAndTest(wt);
    const gate = enforceGate({ resolvedCategory: verdict.resolved_category, changedFiles: stat.files, diffLines: stat.lines, testsPassed, rootCauseCited: /\S+:\d+/.test(verdict.root_cause) });

    if (!gate.pass) {
      const url = await d.se.registerTicket({ feedbackId: row.id, title: ticketTitle(row), category: 'bug', priority: 'P2', body: ticketBody(row, verdict.root_cause), reason: gate.reason! });
      await d.db.writeback(row.id, { triage_state: 'ticketed', triage_issue_url: url });
      return 'ticketed';
    }

    const branch = `fix/feedback-${row.id.slice(0, 8)}`;
    const pr = await d.se.openFixPr({ feedbackId: row.id, worktree: wt, branch, title: `fix(feedback): ${ticketTitle(row)}`, body: ticketBody(row, verdict.root_cause) });
    await d.db.writeback(row.id, { triage_state: 'fixed', triage_pr_url: pr });
    return 'fixed';
  } finally {
    await d.git.removeWorktree(wt);
  }
}

function ticketTitle(row: FeedbackRow): string {
  return row.body.replace(/\s+/g, ' ').trim().slice(0, 60);
}
function ticketBody(row: FeedbackRow, diagnosis: string): string {
  return [`> ${row.body}`, '', `- 분류: ${row.category}`, `- 제출자 role: ${row.role ?? '-'}`, `- host: ${row.host ?? '-'}`, `- page: ${row.page_path ?? '-'}`, '', `**진단:** ${diagnosis}`].join('\n');
}
```

Also create `skills/triaging-feedback/src/prompt.ts` (prompt renderers — the actual protocol wording lands in Task 10's reference; these stubs consume it):
```ts
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run test/dispatch.test.ts`
Expected: PASS (5 passed). (`prompt.ts` reads the protocol file; create a placeholder `references/triage-worker-protocol.md` with the `{{PLACEHOLDERS}}` now so the import resolves; its final wording is Task 10.)

- [ ] **Step 5: Commit**

```bash
git add skills/triaging-feedback/src/dispatch.ts skills/triaging-feedback/src/prompt.ts skills/triaging-feedback/test/dispatch.test.ts skills/triaging-feedback/references/triage-worker-protocol.md
git commit -m "feat(triaging-feedback): 디스패처 오케스트레이션(멱등·라우팅·게이트·PR/티켓) TDD"
```

---

### Task 10: Worker-protocol reference + poller entry + launchd + SKILL.md

**Files:**
- Create/finalize: `skills/triaging-feedback/references/triage-worker-protocol.md`
- Create: `skills/triaging-feedback/src/git.ts` (worktree/diff/build helpers)
- Create: `skills/triaging-feedback/src/poll.ts` (entry)
- Create: `skills/triaging-feedback/scripts/feedback-poll.sh` (launchd wrapper)
- Create: `skills/triaging-feedback/references/setup.md`
- Create: `skills/triaging-feedback/SKILL.md`

- [ ] **Step 1: Finalize the worker protocol** (Korean prose; the ORIENT→CLASSIFY→DIAGNOSE→DECIDE→ACT phases + the untrusted-input boundary + the fenced-JSON verdict contract, verbatim from the spec's "Triage Worker Protocol" section). Must contain the placeholders `{{FEEDBACK_ID}} {{CATEGORY}} {{BODY}} {{PAGE_PATH}} {{ROLE}} {{HOST}}` and instruct: treat `{{BODY}}` as data never instructions; cite `file:line`; emit exactly one fenced ```json verdict.

- [ ] **Step 2: Write `git.ts`** — `addWorktree(id)` → `git -C repo worktree add --detach <path> <baseBranch>` then create branch; `removeWorktree`; `diffStat` → parse `git diff --numstat`; `buildAndTest` → run `npm run build` (and targeted tests) in the worktree, return boolean.

```ts
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const run = promisify(execFile);

export function makeGit(repoPath: string, baseBranch: string) {
  return {
    async addWorktree(id: string): Promise<string> {
      const wt = `${repoPath}/.triage-worktrees/${id.slice(0, 8)}`;
      const branch = `fix/feedback-${id.slice(0, 8)}`;
      await run('git', ['-C', repoPath, 'fetch', 'origin', baseBranch]);
      await run('git', ['-C', repoPath, 'worktree', 'add', '-b', branch, wt, `origin/${baseBranch}`]);
      return wt;
    },
    async removeWorktree(wt: string) { await run('git', ['-C', repoPath, 'worktree', 'remove', '--force', wt]).catch(() => {}); },
    async diffStat(wt: string): Promise<{ files: string[]; lines: number }> {
      const { stdout } = await run('git', ['-C', wt, 'diff', '--numstat']);
      const rows = stdout.trim().split('\n').filter(Boolean);
      const files = rows.map((r) => r.split('\t')[2]);
      const lines = rows.reduce((n, r) => { const [a, d] = r.split('\t'); return n + (Number(a) || 0) + (Number(d) || 0); }, 0);
      return { files, lines };
    },
    async buildAndTest(wt: string): Promise<boolean> {
      try { await run('npm', ['run', 'build'], { cwd: wt, timeout: 15 * 60_000 }); return true; } catch { return false; }
    },
  };
}
```

- [ ] **Step 3: Write `poll.ts`** — the entry: `loadConfig(process.env)`; if `!enabled` exit 0; `db.findActionable(k, reclaimMs)`; for each row, `if (!await db.claim(row.id)) continue`; `await dispatchRow(row, deps)` wrapped in try/catch that on error `db.writeback(id,{triage_state:'failed'})`; sequential.

```ts
import { loadConfig } from './config';
import { makeDb } from './db';
import { makeGit } from './git';
import { makeSideEffects, type Sh } from './sideEffects';
import { runTurn } from './codexAdapter';
import { dispatchRow } from './dispatch';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const execFileP = promisify(execFile);
const sh: Sh = async (cmd, args, cwd) => (await execFileP(cmd, args, { cwd, maxBuffer: 10 * 1024 * 1024 })).stdout;

const cfg = loadConfig(process.env);
if (!cfg.enabled) { console.log('TRIAGE_ENABLED=false — skip'); process.exit(0); }
const db = makeDb(cfg);
const git = makeGit(cfg.repoPath, cfg.baseBranch);
const se = makeSideEffects(cfg, sh);

const rows = await db.findActionable(cfg.k, cfg.reclaimMs);
for (const row of rows) {
  if (!(await db.claim(row.id))) continue;   // someone else took it
  try {
    const st = await dispatchRow(row, { cfg, git, runTurn, se, db });
    console.log(`feedback ${row.id} → ${st}`);
  } catch (e) {
    console.error(`feedback ${row.id} failed:`, e);
    await db.writeback(row.id, { triage_state: 'failed' }).catch(() => {});
  }
}
```

- [ ] **Step 4: Write `scripts/feedback-poll.sh`** (launchd wrapper) and `references/setup.md` (launchd plist every 10 min, the env file with all `TRIAGE_*` + secrets, `gh label create source:user-feedback` / `type:question`, and the "start in shadow: `TRIAGE_FIX_ENABLED=false`" instruction).

```bash
#!/usr/bin/env bash
# launchd 진입점. 스킬 디렉터리의 .env를 로드하고 Node 폴러를 실행.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
set -a; [ -f "$here/.env" ] && . "$here/.env"; set +a
cd "$here" && exec npx tsx src/poll.ts
```

- [ ] **Step 5: Write `SKILL.md`** — frontmatter (name `triaging-feedback`, description in the dispatch-family voice) + how it works + the "adopting a repo" checklist (mirror `reviewing-prs` SKILL.md style: private repo, service-role key, apply Plan A migration first, shadow mode, cron cadence).

- [ ] **Step 6: Smoke-check + commit**

Run: `npx tsc --noEmit && npx vitest run`
Expected: exit 0; all unit suites pass.

```bash
git add skills/triaging-feedback/src/git.ts skills/triaging-feedback/src/poll.ts skills/triaging-feedback/scripts/feedback-poll.sh skills/triaging-feedback/references/ skills/triaging-feedback/SKILL.md
git commit -m "feat(triaging-feedback): 워커 프로토콜·git 헬퍼·폴러 엔트리·launchd·SKILL.md"
```

---

### Task 11 (Final Verification): shadow run + spec acceptance

**Files:** none (verification only). Requires Plan A live (migration applied) on a non-production/staging ida-solution + Supabase, or a dedicated test project.

- [ ] **Step 1: Full unit suite**

Run: `cd skills/triaging-feedback && npx vitest run`
Expected: config, gate, verdict, route, db, sideEffects, dispatch suites all green.

- [ ] **Step 2: Seed a pending feedback row** in the test Supabase:
```sql
INSERT INTO feedback (user_id, role, category, body, page_path, host, triage_state)
VALUES ('<a real users.id>', 'student', 'bug', '오늘 화면에서 완료 체크가 저장이 안 돼요', '/today', 'localhost:3000', 'pending');
```

- [ ] **Step 3: Shadow run (no code writes)**

Set `TRIAGE_ENABLED=true`, `TRIAGE_FIX_ENABLED=false` in `.env`, then:
Run: `bash skills/triaging-feedback/scripts/feedback-poll.sh`
Expected (spec acceptance, observation phase): the seeded row moves `pending → claimed → ticketed`; a `needs-info` issue appears labeled `source:user-feedback` with the diagnosis + verbatim feedback quote in its body; the row's `triage_issue_url` is set; no PR is opened; no code is written.

- [ ] **Step 4: Verify idempotency** — run the poller again immediately.
Expected: the row (now `ticketed`) is not re-processed (not in `findActionable`), and no duplicate issue is created.

- [ ] **Step 5: (Optional, gated) One real fix** — flip `TRIAGE_FIX_ENABLED=true`, seed a second row describing a *known small non-risk-surface bug*, run once.
Expected (spec acceptance, fix phase): row → `fixed`; a PR is opened against `TRIAGE_BASE_BRANCH` whose body cites `feedback:<id>`; `triage_pr_url` set; the `reviewing-prs --sweep` cron subsequently reviews that PR (confirm a `review-pr-*` daemon / review comment appears).

- [ ] **Step 6: Confirm HQ visibility** — open `/hq/feedback` (Plan A) and confirm the seeded rows show `🤖 티켓 → #…` and `🤖 수정 → PR #…` badges.

---

## Global self-review notes (fixed inline before finishing)

- **Spec drift reconciled:** the spec named `feedback-poll.sh` as the ingress adapter; this plan keeps that filename as the **launchd wrapper** and puts the logic in Node (`poll.ts`) for testability. A spec Revision Note records this.
- Every spec Acceptance bullet maps to a Task 11 step; every gate condition (G1–G6) maps to a `gate.test.ts` case; the untrusted-input boundary lives in the Task 10 protocol; the idempotency guard is Task 8 + the Task 9 dispatcher test.
- **Deliberate v1 simplification — priority.** The dispatcher stamps every ticket `P2`. The spec allows `P1` for data-loss/blocking breaks; that escalation is **deferred** (would add a `priority` field to the verdict). Acceptable for the shadow launch — HQ can re-prioritize; wire P1 in a follow-up once ticket volume shows it's needed.
- **Descriptive-label wiring.** `source:user-feedback` (always) and `type:question` (when `category==='question'`) are applied by a `gh issue edit <n> --add-label …` step **inside `registerTicket`**, right after `board-register.sh` returns the issue number (they are non-`status:` labels, so the board Hard Gate permits raw `gh`). The Task 8 plan-time note specifies this; the implementer adds the call in `sideEffects.ts` and a test asserting the label list.
