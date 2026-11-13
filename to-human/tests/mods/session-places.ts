// The searches for a transcript's order, its API errors and the responses a
// hook answered without a request, proved by
// execution, by rg where the machine has it and by grep where it has not: the
// resumed session's
// (placeArgs) lists the rows of the file it is given; the one a module that
// starts mid-session runs (sessionPlaceArgs) finds the session's file by its
// id under CLAUDE_CONFIG_DIR, else ~/.claude, lists its rows the same way, and
// lists none, as a search that finds none, while the session has no file yet;
// the subagents' transcripts beside it are listed (subagentsArgs,
// sessionSubagentsArgs), a session with none listing none, and a batch of
// them is searched as one (apartArgs), every row and call of each.
// Run with bun (to-human/tests/mods/run.sh); not a kit test, as it starts
// processes.
import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { apartArgs, errorsIn, placeArgs, placesIn, sessionPlaceArgs, sessionSubagentsArgs, subagentsArgs, unrequestedIn } from '../../hooks/mods/to-human'

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
  mkdirSync(join(root, 'home/.claude/projects/-work/0b6f/subagents'), { recursive: true })
  writeFileSync(join(root, 'home/.claude/projects/-work/0b6f/subagents/agent-1.jsonl'), '{"uuid":"s1","message":{"content":[{"type":"tool_use","id":"st1"}]}}\n')
  writeFileSync(join(root, 'home/.claude/projects/-work/0b6f/subagents/agent-2.jsonl'), '{"uuid":"s2"}\n')
  writeFileSync(join(root, 'empty-agent.jsonl'), '{"type":"summary"}\n')
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
    const check = (name: string, argv: string[], env: Record<string, string>, ids: string[], code: number, errors: string[] = [], unrequested: string[] = []) => {
      const [shell, ...args] = argv
      const found = spawnSync(shell!, args, { env: { PATH, ...env }, encoding: 'utf8' })
      const got = [placesIn(found.stdout), errorsIn(found.stdout), unrequestedIn(found.stdout)]
      if (found.status !== code || JSON.stringify(got) !== JSON.stringify([ids, errors, unrequested])) {
        failures.push(`${tool}, ${name}: exit ${found.status} ${JSON.stringify(got)} ${found.stderr.trim()}, wanted exit ${code} ${JSON.stringify([ids, errors, unrequested])}`)
      }
    }
    const session = sessionPlaceArgs('0b6f')
    check('~/.claude', session, { HOME: join(root, 'home') }, ['a', 't1', 'b', 'e', 'h'], 0, ['e'], ['h'])
    check('CLAUDE_CONFIG_DIR', session, { HOME: join(root, 'home'), CLAUDE_CONFIG_DIR: join(root, 'config') }, ['c'], 0)
    check('no transcript yet', session, { HOME: join(root, 'empty') }, [], 1)
    check('a resumed transcript', placeArgs(join(root, 'home/.claude/projects/-work/0b6f.jsonl')), {}, ['a', 't1', 'b', 'e', 'h'], 0, ['e'], ['h'])
    // The subagents' transcripts beside it, listed, then searched a batch at a
    // time: every row and call of each file in the batch.
    const run = (argv: string[], env: Record<string, string>) => {
      const [shell, ...args] = argv
      return spawnSync(shell!, args, { env: { PATH, ...env }, encoding: 'utf8' })
    }
    const listed = (name: string, argv: string[], env: Record<string, string>, files: string[], code: number) => {
      const found = run(argv, env)
      const got = `${found.status} ${JSON.stringify(found.stdout.split('\n').filter((line) => line !== '').sort())}`
      const wanted = `${code} ${JSON.stringify(files)}`
      if (got !== wanted) failures.push(`${tool}, ${name}: ${got} ${found.stderr.trim()}, wanted ${wanted}`)
      return found.stdout.split('\n').filter((line) => line !== '')
    }
    const apart = (name: string, files: string[], ids: string[], code: number) => {
      const found = run(apartArgs(files), {})
      const got = `${found.status} ${JSON.stringify(placesIn(found.stdout).sort())}`
      const wanted = `${code} ${JSON.stringify(ids)}`
      if (got !== wanted) failures.push(`${tool}, ${name}: ${got} ${found.stderr.trim()}, wanted ${wanted}`)
    }
    const agents = ['agent-1.jsonl', 'agent-2.jsonl'].map((file) => join(root, 'home/.claude/projects/-work/0b6f/subagents', file))
    const files = listed("a session's subagents", sessionSubagentsArgs('0b6f'), { HOME: join(root, 'home') }, agents, 0)
    listed('no subagents yet', sessionSubagentsArgs('0b6f'), { HOME: join(root, 'home'), CLAUDE_CONFIG_DIR: join(root, 'config') }, [], 1)
    listed("a resumed session's subagents", subagentsArgs(join(root, 'home/.claude/projects/-work/0b6f.jsonl')), {}, agents, 0)
    listed('a resumed session with none', subagentsArgs(join(root, 'config/projects/-work/0b6f.jsonl')), {}, [], 1)
    apart('a batch of two', files, ['s1', 's2', 'st1'], 0)
    apart('a batch of one', [agents[1]!], ['s2'], 0)
    apart('a batch with no rows', [join(root, 'empty-agent.jsonl')], [], 1)
    checks += 11
  }
} finally {
  rmSync(root, { recursive: true, force: true })
}
if (failures.length > 0) {
  console.error(failures.join('\n'))
  process.exit(1)
}
console.log(`session-places: ${checks} searches as expected`)
