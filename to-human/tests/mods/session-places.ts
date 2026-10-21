// The searches for a transcript's order and its API errors, proved by
// execution, by rg where the machine has it and by grep where it has not: the
// resumed session's
// (placeArgs) lists the rows of the file it is given; the one a module that
// starts mid-session runs (sessionPlaceArgs) finds the session's file by its
// id under CLAUDE_CONFIG_DIR, else ~/.claude, lists its rows the same way, and
// lists none, as a search that finds none, while the session has no file yet.
// Run with bun (to-human/tests/mods/run.sh); not a kit test, as it starts
// processes.
import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { errorsIn, placeArgs, placesIn, sessionPlaceArgs } from '../../hooks/mods/to-human'

const root = mkdtempSync(join(tmpdir(), 'to-human-places-'))
const failures: string[] = []
let checks = 0
try {
  const transcript = (dir: string, rows: string) => {
    mkdirSync(join(root, dir, 'projects', '-work'), { recursive: true })
    writeFileSync(join(root, dir, 'projects', '-work', '0b6f.jsonl'), rows)
  }
  transcript('home/.claude', '{"uuid":"a","message":{"content":[{"type":"tool_use","id":"t1"}]}}\n{"uuid":"b"}\n{"uuid":"e","message":{"model":"<synthetic>"},"error":"server_error","isApiErrorMessage":true}\n')
  transcript('config', '{"uuid":"c"}\n')
  mkdirSync(join(root, 'empty'))
  // The search takes rg wherever PATH finds it, so with rg's directory first
  // it runs rg; with the system's directories alone, grep (where they hold no
  // rg, as on macOS).
  const rg = spawnSync('sh', ['-c', 'command -v rg'], { encoding: 'utf8' }).stdout.trim()
  const paths: [string, string][] = [['grep', '/usr/bin:/bin']]
  if (rg !== '') {
    paths.push(['rg', `${rg.slice(0, rg.lastIndexOf('/'))}:/bin`])
  } else {
    console.log('session-places: no rg on this machine; the grep searches alone')
  }
  for (const [tool, PATH] of paths) {
    const check = (name: string, argv: string[], env: Record<string, string>, ids: string[], code: number, errors: string[] = []) => {
      const [shell, ...args] = argv
      const found = spawnSync(shell!, args, { env: { PATH, ...env }, encoding: 'utf8' })
      const got = [placesIn(found.stdout), errorsIn(found.stdout)]
      if (found.status !== code || JSON.stringify(got) !== JSON.stringify([ids, errors])) {
        failures.push(`${tool}, ${name}: exit ${found.status} ${JSON.stringify(got)} ${found.stderr.trim()}, wanted exit ${code} ${JSON.stringify([ids, errors])}`)
      }
    }
    const session = sessionPlaceArgs('0b6f')
    check('~/.claude', session, { HOME: join(root, 'home') }, ['a', 't1', 'b', 'e'], 0, ['e'])
    check('CLAUDE_CONFIG_DIR', session, { HOME: join(root, 'home'), CLAUDE_CONFIG_DIR: join(root, 'config') }, ['c'], 0)
    check('no transcript yet', session, { HOME: join(root, 'empty') }, [], 1)
    check('a resumed transcript', placeArgs(join(root, 'home/.claude/projects/-work/0b6f.jsonl')), {}, ['a', 't1', 'b', 'e'], 0, ['e'])
    checks += 4
  }
} finally {
  rmSync(root, { recursive: true, force: true })
}
if (failures.length > 0) {
  console.error(failures.join('\n'))
  process.exit(1)
}
console.log(`session-places: ${checks} searches as expected`)
