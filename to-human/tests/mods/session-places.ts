// The searches for a transcript's order, its API errors and the responses a
// hook answered without a request, proved by execution, by rg where the
// machine has it and by grep where it has not: the resumed session's
// (placeArgs) lists the rows of the file it is given; the one a module that
// starts mid-session runs (sessionPlaceArgs) finds the session's file by its
// id under CLAUDE_CONFIG_DIR, else ~/.claude, lists its rows the same way, and
// lists none, as a search that finds none, while the session has no file yet.
// Each writes its list to a file of its own, read back whole a piece at a
// time (readList, pieceArgs), the file gone after: here in pieces far smaller
// than the engine's, so a list runs across many, and a piece ends mid-line.
// Run with bun (to-human/tests/mods/run.sh); not a kit test, as it starts
// processes.
import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { errorsIn, placeArgs, placesIn, readList, sessionPlaceArgs, unrequestedIn } from '../../hooks/mods/to-human'

const root = mkdtempSync(join(tmpdir(), 'to-human-places-'))
const failures: string[] = []
let checks = 0
try {
  const transcript = (dir: string, rows: string) => {
    mkdirSync(join(root, dir, 'projects', '-work'), { recursive: true })
    writeFileSync(join(root, dir, 'projects', '-work', '0b6f.jsonl'), rows)
  }
  transcript('home/.claude', '{"uuid":"a","message":{"content":[{"type":"tool_use","id":"t1"}]}}\n{"uuid":"b"}\n{"uuid":"e","message":{"model":"<synthetic>"},"error":"server_error","isApiErrorMessage":true}\n{"type":"assistant","uuid":"h","message":{"id":"msg_hook_1","content":[{"type":"text","text":"Message sent to the human.","citations":null}]},"isApiErrorMessage":false,"answeredWithoutRequest":true}\n')
  transcript('config', '{"uuid":"c"}\n')
  const many = Array.from({ length: 500 }, (_, i) => `r${i}`)
  transcript('many/.claude', many.map((id) => `{"uuid":"${id}"}\n`).join(''))
  mkdirSync(join(root, 'empty'))
  const temp = join(root, 'tmp')
  mkdirSync(temp)
  // The search takes rg wherever PATH finds it, so with rg's directory first
  // it runs rg; with the system's directories alone, grep (where they hold no
  // rg, as on macOS).
  const rg = spawnSync('sh', ['-c', 'command -v rg'], { encoding: 'utf8' }).stdout.trim()
  const paths: [string, string][] = [['grep', '/usr/bin:/bin']]
  if (rg !== '') {
    // mktemp, tail and head are in /usr/bin on macOS, beside its grep.
    paths.push(['rg', `${rg.slice(0, rg.lastIndexOf('/'))}:/usr/bin:/bin`])
  } else {
    console.log('session-places: no rg on this machine; the grep searches alone')
  }
  for (const [tool, PATH] of paths) {
    const check = async (name: string, argv: string[], env: Record<string, string>, ids: string[], code: number, errors: string[] = [], unrequested: string[] = [], bytes = 37) => {
      const run = async (command: string[]) => {
        const [shell, ...args] = command
        const done = spawnSync(shell!, args, { env: { PATH, TMPDIR: temp, ...env }, encoding: 'utf8' })
        return { exitCode: done.status ?? 2, stdout: done.stdout }
      }
      const found = await readList(run, argv, bytes)
      const got = [placesIn(found.stdout), errorsIn(found.stdout), unrequestedIn(found.stdout)]
      if (found.exitCode !== code || JSON.stringify(got) !== JSON.stringify([ids, errors, unrequested])) {
        failures.push(`${tool}, ${name}: exit ${found.exitCode} ${JSON.stringify(got).slice(0, 300)}, wanted exit ${code} ${JSON.stringify([ids, errors, unrequested]).slice(0, 300)}`)
      }
      checks += 1
    }
    const session = sessionPlaceArgs('0b6f')
    await check('~/.claude', session, { HOME: join(root, 'home') }, ['a', 't1', 'b', 'e', 'h'], 0, ['e'], ['h'])
    await check('CLAUDE_CONFIG_DIR', session, { HOME: join(root, 'home'), CLAUDE_CONFIG_DIR: join(root, 'config') }, ['c'], 0)
    await check('no transcript yet', session, { HOME: join(root, 'empty') }, [], 1)
    await check('a resumed transcript', placeArgs(join(root, 'home/.claude/projects/-work/0b6f.jsonl')), {}, ['a', 't1', 'b', 'e', 'h'], 0, ['e'], ['h'])
    await check('a list of many pieces', session, { HOME: join(root, 'many') }, many, 0)
    await check('a list in one piece', session, { HOME: join(root, 'many') }, many, 0, [], [], 1 << 20)
  }
  // Every list's file is gone once read.
  const left = spawnSync('ls', [temp], { encoding: 'utf8' }).stdout.trim()
  if (left !== '' || !existsSync(temp)) failures.push(`the lists' files were left: ${left}`)
} finally {
  rmSync(root, { recursive: true, force: true })
}
if (failures.length > 0) {
  console.error(failures.join('\n'))
  process.exit(1)
}
console.log(`session-places: ${checks} searches as expected`)
