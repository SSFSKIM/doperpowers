// The review lane on the native Workflow tool. One script, one `level` argument,
// two shapes: low/medium/high dispatch a single reviewer agent (the same rungs
// the registered `doperpowers:reviewer-<level>` agents give a direct Agent-tool
// dispatch, for contexts without this tool); xhigh/max run the panel — one lens-free sweep, up to five diff-derived scalpel lenses,
// every finder a reviewer agent, one binding verifier over the merged pool.
// Every model judgment lives in an agent turn; everything else is deterministic.
//
// Invoke:  Workflow({ scriptPath: "<skill-base>/workflows/code-review.js",
//                     args: { level, base, baseCommit, headCommit } })
//
// args:
//   level       — low | medium | high | xhigh | max (default medium)
//   base        — the base ref the branch is reviewed against ("main")     REQUIRED
//   baseCommit  — `git merge-base <base> HEAD`, resolved by the caller     REQUIRED
//   headCommit  — `git rev-parse HEAD`, resolved by the caller             REQUIRED
//   repo        — absolute path of the checkout under review when it is not the
//                 session's cwd (a worktree, a scratch repo)
//   lens        — one scalpel mandate for a single-reviewer level (optional)
//   lenses      — an array replacing the panel's derived scalpel set (optional)
//   maxLenses   — cap on panel scalpels (default per level, at most 5)
//   finderAgent — agent type for every reviewer, default "doperpowers:reviewer-medium"
//                 (the registered reviewers share one body; the rung's model and
//                 effort above override the agent's own pin per call)
//   deriverModel / deriverEffort, finderModel / finderEffort,
//   verifierModel / verifierEffort — per-lane overrides of the level's ladder
//
// The script cannot run git (workflow scripts have no filesystem), so the caller
// resolves the pin and passes both commits. Every prompt names both, so every
// lane reviews one committed range even if a ref moves while it runs, and a
// different head is a different prompt — a different replay-cache identity. The
// caller re-resolves both commits when the run returns: if either moved, the
// verdict describes a diff that no longer exists and is read as `interrupted`.

export const meta = {
  name: 'code-review',
  description: 'Independent code review by effort level: a single reviewer (low/medium/high) or the multi-lens panel with one binding verifier (xhigh/max)',
  phases: [
    { title: 'Derive', detail: 'panel levels: read the diff, write the scalpel lenses' },
    { title: 'Find', detail: 'the reviewer, or the lens-free sweep + one reviewer per lens' },
    { title: 'Verify', detail: 'panel levels: one binding verifier over the merged candidate pool' },
  ],
}

// ---------------------------------------------------------------- Ladder
// Effort is the only routing input; the session never chooses models. Sol at
// xhigh is the rung the X1 baseline was scored on (17/17 seeded, FP 0 as the
// codex engine's production default). The verifier never runs below its finders:
// the panel's one recorded false positive came from a verifier at high under
// finders at xhigh, and it is the only stage between a plausible candidate and a
// published finding.
const LADDER = {
  low:    { shape: 'single', finder: { model: 'sol', effort: 'high' } },
  medium: { shape: 'single', finder: { model: 'sol', effort: 'xhigh' } },
  high:   { shape: 'single', finder: { model: 'astra', effort: 'high' } },
  xhigh:  { shape: 'panel', maxLenses: 5,
            deriver: { model: 'sol', effort: 'high' },
            finder: { model: 'sol', effort: 'xhigh' },
            verifier: { model: 'sol', effort: 'xhigh' } },
  max:    { shape: 'panel', maxLenses: 5,
            deriver: { model: 'sol', effort: 'xhigh' },
            finder: { model: 'astra', effort: 'high' },
            verifier: { model: 'astra', effort: 'high' } },
}

if (!args || !args.base || !args.baseCommit || !args.headCommit) {
  throw new Error('code-review requires args.base, args.baseCommit (git merge-base <base> HEAD), and args.headCommit (git rev-parse HEAD)')
}
const level = args.level ?? 'medium'
const rung = LADDER[level]
if (!rung) throw new Error(`code-review: unknown level '${level}' (low | medium | high | xhigh | max)`)
const base = args.base
const baseCommit = args.baseCommit
const headCommit = args.headCommit
const finderAgent = args.finderAgent ?? 'doperpowers:reviewer-medium'
const lane = (name) => ({ model: args[`${name}Model`] ?? rung[name]?.model, effort: args[`${name}Effort`] ?? rung[name]?.effort })
const finder = lane('finder')
const deriver = lane('deriver')
const verifier = lane('verifier')
const maxLenses = Math.min(5, args.maxLenses ?? rung.maxLenses ?? 0)

const rangeOf = () => `${baseCommit} (merge-base(HEAD, ${base}), resolved once at review start)`
// `repo` points every lane at a checkout other than the session's cwd (a
// worktree, a bench scratch repo); it is shell-quoted wherever it enters a command.
const repo = args.repo ?? null
const quotedRepo = repo ? `'${String(repo).replaceAll("'", "'\\''")}'` : null
const git = repo ? `git -C ${quotedRepo}` : 'git'
const DIFF = `${git} diff ${baseCommit} ${headCommit}`
const WHERE = repo ? `The repository under review is at ${repo}: run git with \`-C ${quotedRepo}\` and read files under that path. ` : ''
// Without repo, each lane gets a fresh worktree at HEAD: reviewers read committed
// content, and nothing they run can touch the session's working tree. With repo
// pointing elsewhere, that worktree would isolate the wrong checkout, so omit it.
const ISOLATION = repo ? {} : { isolation: 'worktree' }

// The one sentence codex's native review turn carried, with pinned commits in
// place of refs that could move.
const TARGET = `${WHERE}Review the code changes against the base branch '${base}'. The merge base commit for this comparison is ${baseCommit}; the reviewed head is ${headCommit}. Run \`${DIFF}\` to inspect the changes relative to ${base}. Provide prioritized, actionable findings.`
const withLens = (mandate) => mandate ? `${TARGET}\n\nLens for this review: ${mandate}` : TARGET

const FINDINGS_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['findings', 'explanation'],
  properties: {
    findings: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['priority', 'title', 'file', 'lines', 'comment'],
      properties: {
        priority: { type: 'string', enum: ['P0', 'P1', 'P2', 'P3'] },
        title: { type: 'string' },
        file: { type: 'string' },
        lines: { type: 'string' },
        comment: { type: 'string' },
      },
    } },
    explanation: { type: 'string' },
  },
}
// The reviewer's prose format tags the title; with a priority field beside it
// the tag is noise.
const untagged = (title) => String(title).replace(/^\[P[0-3]\]\s*/, '')
const stubsOf = (finderId, r) => r.findings.map((f, k) => ({ id: `${finderId}#${k + 1}`, ...f, title: untagged(f.title) }))

const target = { base, baseCommit, headCommit, repo }
const ORDER = { P0: 0, P1: 1, P2: 2, P3: 3 }

// One transport retry on a fresh agent, as the codex engine gave every leaf: a
// gateway stream that ends mid-turn is a dead lane the first time and usually a
// fine one the second. The retry carries a different label, so a resume never
// conflates the dead turn with its replacement. A second death is final.
const once = async (label, run) => {
  const first = await run(label).catch(() => null)
  if (first) return first
  log(`${label} died — one retry`)
  return run(`${label}-retry`).catch(() => null)
}

// ---------------------------------------------------------------- Single reviewer
// One reviewer at the level's model and effort; its findings are the result, its
// own explanation the verdict's. A lost reviewer is `interrupted`, never clean.

if (rung.shape === 'single') {
  log(`review (${level}: ${finder.model}/${finder.effort}) against ${base} @ ${baseCommit.slice(0, 10)} (HEAD ${headCommit.slice(0, 10)})`)
  phase('Find')
  const r = await once('reviewer', (label) => agent(withLens(args.lens ?? null),
    { ...finder, ...ISOLATION, agentType: finderAgent, schema: FINDINGS_SCHEMA, label, phase: 'Find' }))
  if (!r || !Array.isArray(r.findings)) {
    return { verdict: 'interrupted', findings: [], lenses: [], target, level,
      coverage: [{ finder: 'reviewer', lens: args.lens ?? null, status: 'dead', candidates: 0 }],
      explanation: 'the reviewer did not complete — no verdict can be asserted' }
  }
  const findings = stubsOf('reviewer', r)
    .map((s) => ({ ...s, sources: ['reviewer'] }))
    .sort((a, b) => ORDER[a.priority] - ORDER[b.priority])
  const verdict = findings.length > 0 ? 'incorrect' : 'correct'
  log(`review verdict: ${verdict} — ${r.explanation}`)
  return { verdict, findings, lenses: args.lens ? [args.lens] : [], target, level,
    coverage: [{ finder: 'reviewer', lens: args.lens ?? null, status: 'ok', candidates: findings.length }],
    explanation: r.explanation }
}

// ---------------------------------------------------------------- Derive

// A dead deriver is a lost review surface, not evidence that this diff warranted
// no scalpels. Finder rows join the same coverage account after the Find phase.
const coverage = []

const DERIVER_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['lenses'],
  properties: { lenses: { type: 'array', items: { type: 'string' } } },
}

const DERIVER_PROMPT = `${WHERE}You are preparing a multi-reviewer code-review panel for the diff between ${rangeOf()} and ${headCommit} (HEAD, resolved once at panel start) in this repository. Run \`${DIFF} --stat\` and skim the largest hunks with \`${DIFF}\`. Never modify the repository.

Write between 0 and ${maxLenses} scalpel lens mandates. Each mandate is AT MOST TWO SIMPLE SENTENCES naming one structural risk surface of THIS diff (example of the calibre required: "Pay attention to authorization and actor-identity assumptions in the changed API routes."). A separate lens-free reviewer already sweeps everything, so a mandate must earn its slot: fewer, sharper mandates beat coverage padding — a small single-concern diff deserves zero or one. Consider, only where this diff actually raises them: changed-logic accuracy, cross-file contract impact, behavior lost with removed or moved code, security surface, performance and resources.`

phase('Derive')
let lenses = args.lenses
if (!Array.isArray(lenses)) {
  const derived = await once('lens-deriver', (label) => agent(DERIVER_PROMPT, { ...deriver, ...ISOLATION, schema: DERIVER_SCHEMA, label, phase: 'Derive' }))
  lenses = derived ? derived.lenses : []
  if (!derived) {
    coverage.push({ finder: 'lens-deriver', lens: null, status: 'dead', candidates: 0 })
    log('lens-deriver died — coverage is incomplete; running the sweep alone')
  }
}
lenses = lenses.slice(0, maxLenses).map((l) => String(l).trim()).filter(Boolean)
log(`panel (${level}: finders ${finder.model}/${finder.effort}, verifier ${verifier.model}/${verifier.effort}): sweep + ${lenses.length} scalpel(s) against ${base} @ ${baseCommit.slice(0, 10)} (HEAD ${headCommit.slice(0, 10)})`)

// ---------------------------------------------------------------- Find

const finders = [
  { finderId: 'sweep', mandate: null },
  ...lenses.map((mandate, i) => ({ finderId: `scalpel-${i + 1}`, mandate })),
]

// All finders at once. The barrier is real: the verifier deduplicates across
// lanes, so it needs the whole pool. `parallel` turns a dead worker into null
// rather than losing the panel, and the array stays index-aligned with finders.
phase('Find')
const reviews = await parallel(finders.map(({ finderId, mandate }) => () =>
  once(finderId, (label) => agent(withLens(mandate),
    { ...finder, ...ISOLATION, agentType: finderAgent, schema: FINDINGS_SCHEMA, label, phase: 'Find' }))))

// Add the finder rows to the panel's coverage account. A lane that died is
// named as such: the verifier only ever sees the pool, so a lost finder with no
// coverage row would read downstream as a lane that found nothing.
const pool = []
reviews.forEach((r, i) => {
  const { finderId, mandate } = finders[i]
  if (!r || !Array.isArray(r.findings)) { coverage.push({ finder: finderId, lens: mandate, status: 'dead', candidates: 0 }); return }
  const stubs = stubsOf(finderId, r)
  coverage.push({ finder: finderId, lens: mandate, status: 'ok', candidates: stubs.length })
  pool.push(...stubs)
})
log(`pool: ${pool.length} candidate(s) from ${coverage.filter((c) => c.finder !== 'lens-deriver' && c.status === 'ok').length}/${finders.length} lanes`)

// ---------------------------------------------------------------- Verify

const VERIFIER_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['verdicts'],
  properties: { verdicts: { type: 'array', items: {
    type: 'object', additionalProperties: false,
    required: ['id', 'verdict', 'duplicateOf', 'priority', 'comment'],
    properties: {
      id: { type: 'string' },
      verdict: { type: 'string', enum: ['CONFIRMED', 'REFUTED'] },
      // null = not a duplicate / no priority (a refuted finding has none).
      duplicateOf: { type: ['string', 'null'] },
      priority: { type: ['string', 'null'], enum: ['P0', 'P1', 'P2', 'P3', null] },
      comment: { type: 'string' },
    },
  } } },
}

// The verifier's contract, checked in code rather than trusted: exactly one
// verdict per candidate, and a duplicateOf graph that resolves — no phantom
// target, no duplicate of something refuted, no cycle. A schema-valid verdict
// set can violate every one of these, and each silently loses or double-counts
// a finding downstream.
function checkPostconditions(verdicts, pool) {
  const errs = []
  const ids = new Set(pool.map((s) => s.id))
  const seen = new Map()
  for (const v of verdicts) {
    if (!ids.has(v.id)) errs.push(`phantom id ${v.id}`)
    seen.set(v.id, (seen.get(v.id) ?? 0) + 1)
  }
  for (const s of pool) if (!seen.has(s.id)) errs.push(`missing verdict for ${s.id}`)
  for (const [id, n] of seen) if (n > 1) errs.push(`duplicate verdict for ${id}`)
  const byId = new Map(verdicts.map((v) => [v.id, v]))
  for (const v of verdicts) {
    if (!v.duplicateOf) continue
    const target = byId.get(v.duplicateOf)
    if (!target) { errs.push(`duplicateOf ${v.duplicateOf} does not exist`); continue }
    if (target.verdict === 'REFUTED') errs.push(`duplicateOf targets refuted ${v.duplicateOf}`)
    let hops = 0, cur = target
    while (cur?.duplicateOf && hops++ < verdicts.length) cur = byId.get(cur.duplicateOf)
    if (cur?.duplicateOf) errs.push(`duplicateOf cycle at ${v.id}`)
  }
  return errs
}

// A candidate id is prefixed with the finder that raised it, so the roster
// tells the verifier what each reviewer was pointed at: a claim from a mandated
// lens reads differently from the same claim raised unprompted by the sweep.
const lensRoster = () => finders
  .map(({ finderId, mandate }) => `- ${finderId}: ${mandate ?? '(lens-free sweep)'}`)
  .join('\n')

const VERIFIER_PROMPT = () =>
  `${WHERE}You are the binding verifier of a multi-reviewer code-review panel. The candidate findings below came from independent reviewers of the diff against ${rangeOf()} at the reviewed head ${headCommit} — run \`${DIFF}\` and re-inspect the code yourself before judging; a candidate is confirmed only when you can name the concrete failure. Never modify the repository. For EVERY candidate id return exactly one verdict: CONFIRMED (name the concrete failure scenario) or REFUTED (state why it is wrong, intentional, pre-existing, or not a real defect — the code's own documentation and the change's stated intent count as evidence). Mark true duplicates with duplicateOf pointing at the strongest formulation (null when the finding is not a duplicate), assign priority P0–P3 to confirmed findings (null on a refuted one), and put your evidence in comment.

The reviewers, and the lens each was given (a candidate id carries its reviewer's label):
${lensRoster()}

Candidates (JSON):
${JSON.stringify(pool, null, 2)}`

// The repair is a FRESH agent — it knows nothing the prompt omits: not its role,
// not the range, not what CONFIRMED means — and its answer is binding when it
// passes, so it carries the whole contract with the violation on top.
const REPAIR_PROMPT = (errs) =>
  `A previous verifier's verdict set violated the contract: ${errs.join('; ')}. The full contract follows again, unchanged.

${VERIFIER_PROMPT()}

Return the FULL corrected verdicts array covering every candidate id exactly once.`

// `verified` is three-state: the verdicts, an empty array when there was nothing
// to judge, or null when the verifier could not be made to honour its contract —
// rendered below as an interrupted panel, never as a partially-trusted set.
phase('Verify')
let verified = []
if (pool.length > 0) {
  const opts = { ...verifier, ...ISOLATION, schema: VERIFIER_SCHEMA, phase: 'Verify' }
  const attempt = await agent(VERIFIER_PROMPT(), { ...opts, label: 'verifier' }).catch(() => null)
  const errs = attempt ? checkPostconditions(attempt.verdicts, pool) : ['verifier died']
  if (errs.length === 0) verified = attempt.verdicts
  else {
    log(`verifier postconditions failed: ${errs.join('; ')} — one repair round`)
    const retry = await agent(REPAIR_PROMPT(errs), { ...opts, label: 'verifier-repair' }).catch(() => null)
    const errs2 = retry ? checkPostconditions(retry.verdicts, pool) : ['verifier repair died']
    verified = errs2.length === 0 ? retry.verdicts : null
    if (verified === null) log(`verifier repair failed: ${errs2.join('; ')}`)
  }
}

// ---------------------------------------------------------------- Assemble
// Every judgement has been made — the finders raised, the verifier ruled,
// coverage recorded what the panel got. What is left is honesty: which losses
// a verdict is still allowed to stand on top of.

const sweepDead = coverage.some((c) => c.finder === 'sweep' && c.status !== 'ok')
const lostLenses = coverage.filter((c) => c.status !== 'ok')

// Unjudged candidates are not findings — nobody re-inspected them — but they are
// the only thing this run produced, so they ride along raw.
if (verified === null) {
  return { verdict: 'interrupted', findings: [], coverage, lenses, pool, target, level,
    explanation: 'verifier did not produce a contract-valid verdict set; raw candidate pool attached' }
}

const byId = new Map(verified.map((v) => [v.id, v]))
const stubById = new Map(pool.map((s) => [s.id, s]))
// A duplicate may point at another duplicate — the postconditions forbid a cycle
// and a refuted target, not a chain — so credit follows the chain to its root.
const rootOf = (v) => { let cur = v; while (cur.duplicateOf) cur = byId.get(cur.duplicateOf); return cur.id }
// `sources` is the finding's claim about who independently stands behind it,
// so only a verdict the verifier itself upheld is counted: a REFUTED duplicate
// is the verifier saying "the same claim, and it is wrong" in one breath.
const sourcesOf = (v) => [...new Set(
  [v, ...verified.filter((d) => d.duplicateOf && d.verdict === 'CONFIRMED' && rootOf(d) === v.id)]
    .map((d) => d.id.split('#')[0]))]

const findings = verified
  .filter((v) => v.verdict === 'CONFIRMED' && !v.duplicateOf)
  .map((v) => {
    const stub = stubById.get(v.id)
    return { id: v.id, priority: v.priority ?? stub.priority, title: stub.title,
      file: stub.file, lines: stub.lines, comment: v.comment, sources: sourcesOf(v) }
  })
  .sort((a, b) => ORDER[a.priority] - ORDER[b.priority])

let verdict = findings.length > 0 ? 'incorrect' : 'correct'
let explanation = findings.length > 0
  ? `confirmed: ${findings.slice(0, 3).map((f) => f.title).join('; ')}`
  : 'no confirmed findings'
// An empty verdict set means two different things — every lane reported and
// found nothing, or the lanes that would have found something never reported.
// Only coverage tells them apart, so a clean verdict is asserted only when
// nothing was lost. A lost lane beside a CONFIRMED finding costs the panel its
// claim to completeness, never a real defect.
if (verdict === 'correct' && lostLenses.length > 0) {
  verdict = 'interrupted'
  explanation = `coverage incomplete (${lostLenses.map((c) => c.finder).join(', ')}) — a clean verdict cannot be asserted`
}
if (verdict === 'incorrect' && lostLenses.length > 0) {
  explanation += `; coverage partial: ${lostLenses.map((c) => c.finder).join(', ')}`
}
// The sweep is the only lane that reads the whole diff, so without it the panel
// cannot say what it missed: losing it fails the ROUND, whatever the scalpels
// confirmed. Interrupted withholds the claim of completeness, not the evidence.
if (sweepDead) {
  verdict = 'interrupted'
  explanation = 'the lens-free sweep did not complete — round is interrupted' +
    (findings.length > 0 ? `; ${findings.length} confirmed finding(s) attached as partial evidence` : '')
}
// A whole panel that found nothing is the shape a mis-aimed diff also makes.
if (verdict === 'correct' && pool.length === 0) {
  explanation += ' (note: every finder returned zero findings — verify the diff target is what you intended)'
}
log(`panel verdict: ${verdict} — ${explanation}`)
return { verdict, findings, coverage, lenses, explanation, target, level }
