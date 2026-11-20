// The declaration a client reads without running the plugin
// (to-human/maws-surface.json) says from which contract version the view
// draws on the client's surface; the view's gate (to-human.tsx,
// MAWS_DRAWS_FROM) is what the view does. The two must agree, and the file
// holds that one fact. Run with bun (to-human/tests/mods/run.sh); not a kit
// test, since the kit loads no file but code.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { MAWS_DRAWS_FROM } from '../../hooks/mods/to-human'

const path = join(import.meta.dir, '../../maws-surface.json')
let failure: string | undefined
try {
  const declared: unknown = JSON.parse(readFileSync(path, 'utf8'))
  const expected = { toHumanView: { drawsFrom: MAWS_DRAWS_FROM } }
  if (JSON.stringify(declared) !== JSON.stringify(expected)) {
    failure = `maws-surface.json declares ${JSON.stringify(declared)}, the gate draws from ${MAWS_DRAWS_FROM}: expected ${JSON.stringify(expected)}`
  }
} catch (error) {
  failure = `maws-surface.json could not be read (${String(error)})`
}
if (failure !== undefined) {
  console.error(`maws-surface: ${failure}`)
  process.exit(1)
}
console.log(`maws-surface: the declaration and the gate agree (draws from ${MAWS_DRAWS_FROM})`)
