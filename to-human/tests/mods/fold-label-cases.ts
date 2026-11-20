// The table of which run a fold line reads (fold-label-cases.json), run
// through the mod's own rule (labelOf, which reads labelFor) case by case,
// and its digest pinned: a client that draws the same lines from the
// session's folds file keeps a byte-for-byte copy under this digest, so a
// change of the rule is a change of the file first, and of this digest with
// it. Run with bun (to-human/tests/mods/run.sh); not a kit test, since the
// kit loads no file but code.
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import type { FoldRun, Folds, OpenFold } from '../../types/to-human'
import { labelOf } from '../../hooks/mods/folds'
import type { RowKind } from '../../hooks/mods/to-human'
import { anchorOf, keyOf, newView, runEnd, runStart } from '../../hooks/mods/to-human'

/** The digest of fold-label-cases.json every copy of it is pinned to. */
const FOLD_LABEL_CASES_SHA256 = 'c65988f084c0978b3f79eab220ae02f3ef7175f2717ea225ff421557f9c0fa94'

type CaseRow = { id: string; class: RowKind; placed: boolean; call?: { line: string; done: boolean } }
type Case = {
  name: string
  rows: CaseRow[]
  closed: { first: string; last: string; summary: string }[]
  open: { first: string; summary?: string; covered?: string } | null
  running: boolean
  labels: Record<string, string | null>
}

const bytes = readFileSync(join(import.meta.dir, 'fold-label-cases.json'))
const failures: string[] = []
const digest = createHash('sha256').update(bytes).digest('hex')
if (digest !== FOLD_LABEL_CASES_SHA256) failures.push(`the file's sha256 is ${digest}, pinned ${FOLD_LABEL_CASES_SHA256}`)
const { cases } = JSON.parse(bytes.toString('utf8')) as { cases: Case[] }

/**
 * The open run as the tracker publishes it: its live line is its newest
 * call's after the last row its summary covered (from its first row while it
 * has none), and it is live while rows joined since that summary.
 */
function openOf(rows: readonly CaseRow[], open: NonNullable<Case['open']>): FoldRun {
  const from = rows.findIndex((row) => row.id === open.first)
  const after = open.summary === undefined ? from : rows.findIndex((row) => row.id === open.covered) + 1
  const since = from < 0 ? [] : rows.slice(Math.max(after, from))
  const line = since.filter((row) => row.call !== undefined).at(-1)?.call?.line
  const isLive = open.summary === undefined || since.length > 0
  return { first: open.first, ...(open.summary !== undefined && { summary: open.summary }), ...(line !== undefined && { line }), ...(isLive && { isLive: true as const }) }
}

for (const c of cases) {
  const view = newView(() => true)
  c.rows.forEach((row, i) => {
    view.order.push(row.id)
    view.rowOf.set(row.id, row.class)
    // An anchored ask's place is its anchor's (placeAt); a kept row's blocks share their row's.
    if (row.placed && anchorOf(row.id) === undefined && !view.place.has(keyOf(row.id))) view.place.set(keyOf(row.id), i)
  })
  const folds: Folds = { shape: 1, runs: c.closed.map((run) => ({ ...run })) }
  const open: OpenFold = c.open === null ? null : openOf(c.rows, c.open)
  const firsts = view.order.filter((id) => {
    const kind = view.rowOf.get(id)
    return (kind === 'record' || kind === 'mixed') && runStart(view.order, view.rowOf, id) === id
  })
  const expected = Object.keys(c.labels)
  if (JSON.stringify(firsts) !== JSON.stringify(expected)) failures.push(`${c.name}: the stretches begin at ${JSON.stringify(firsts)}, the case labels ${JSON.stringify(expected)}`)
  for (const first of firsts) {
    const label = labelOf(folds, open, view, first, runEnd(view.order, view.rowOf, first)) ?? null
    if (label !== (c.labels[first] ?? null)) failures.push(`${c.name}: ${first} reads ${JSON.stringify(label)}, expected ${JSON.stringify(c.labels[first])}`)
  }
}

if (failures.length > 0) {
  for (const failure of failures) console.error(`fold-label-cases: ${failure}`)
  process.exit(1)
}
console.log(`fold-label-cases: ${cases.length} cases as expected`)
