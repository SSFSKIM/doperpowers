// The search a module that starts mid-session runs for its transcript's order
// (sessionPlaceArgs), proved by execution: it finds the session's file by its
// id under CLAUDE_CONFIG_DIR, else ~/.claude, lists its rows as the resumed
// session's search does, and lists none, as grep's "none", while the session
// has no file yet. Run with bun (to-human/tests/mods/run.sh); not a kit test,
// as it starts processes.
import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { placesIn, sessionPlaceArgs } from '../../hooks/mods/to-human'

const root = mkdtempSync(join(tmpdir(), 'to-human-places-'))
const failures: string[] = []
try {
  const transcript = (dir: string, rows: string) => {
    mkdirSync(join(root, dir, 'projects', '-work'), { recursive: true })
    writeFileSync(join(root, dir, 'projects', '-work', '0b6f.jsonl'), rows)
  }
  transcript('home/.claude', '{"uuid":"a","message":{"content":[{"type":"tool_use","id":"t1"}]}}\n{"uuid":"b"}\n')
  transcript('config', '{"uuid":"c"}\n')
  mkdirSync(join(root, 'empty'))
  const [shell, ...args] = sessionPlaceArgs('0b6f')
  const run = (env: Record<string, string>) => spawnSync(shell!, args, { env: { PATH: '/usr/bin:/bin', ...env }, encoding: 'utf8' })
  const check = (name: string, env: Record<string, string>, ids: string[], code: number) => {
    const found = run(env)
    const got = placesIn(found.stdout)
    if (found.status !== code || JSON.stringify(got) !== JSON.stringify(ids)) {
      failures.push(`${name}: exit ${found.status} ${JSON.stringify(got)}, wanted exit ${code} ${JSON.stringify(ids)}`)
    }
  }
  check('~/.claude', { HOME: join(root, 'home') }, ['a', 't1', 'b'], 0)
  check('CLAUDE_CONFIG_DIR', { HOME: join(root, 'home'), CLAUDE_CONFIG_DIR: join(root, 'config') }, ['c'], 0)
  check('no transcript yet', { HOME: join(root, 'empty') }, [], 1)
} finally {
  rmSync(root, { recursive: true, force: true })
}
if (failures.length > 0) {
  console.error(failures.join('\n'))
  process.exit(1)
}
console.log('session-places: 3 searches as expected')
