// clip.mjs: fetch | numbered | prune. stdout carries only the result; a
// non-zero exit means a bug in the clipper, with its stack on stderr.
import { readFile } from 'node:fs/promises'
import { parseArgs } from 'node:util'
import { cacheRoot, prune } from './cache.ts'
import { clip } from './clip.ts'
import { numbered } from './numbered.ts'

const USAGE = `usage:
  clip.mjs fetch <url> [--refresh] [--cache-dir <dir>]
  clip.mjs numbered <text file> [--max-tokens <n>] [--reserve <n>]
  clip.mjs prune [--older-than-days 7] [--cache-dir <dir>]`

const SUMMARY_MAX_TOKENS = 150_000

async function main(argv: string[]): Promise<number> {
  // Libraries that log (Defuddle does) must not write into the result on stdout.
  const toStderr = (...args: unknown[]) => console.error(...args)
  console.log = console.info = console.warn = console.debug = toStderr

  const [command, ...rest] = argv
  const { values, positionals } = parseArgs({
    args: rest,
    allowPositionals: true,
    options: {
      refresh: { type: 'boolean' },
      'cache-dir': { type: 'string' },
      'max-tokens': { type: 'string' },
      reserve: { type: 'string' },
      'older-than-days': { type: 'string' },
    },
  })
  const out = (s: string) => new Promise<void>(resolve => process.stdout.write(s, () => resolve()))

  if (command === 'fetch' && positionals.length === 1) {
    const result = await clip(positionals[0], { cacheDir: cacheRoot(values['cache-dir']), refresh: values.refresh })
    await out(JSON.stringify(result) + '\n')
    return 0
  }
  if (command === 'numbered' && positionals.length === 1) {
    const text = await readFile(positionals[0], 'utf8')
    const { header, body } = numbered(text, number(values['max-tokens'], SUMMARY_MAX_TOKENS), number(values.reserve, 0))
    await out(JSON.stringify(header) + '\n' + body)
    return 0
  }
  if (command === 'prune' && positionals.length === 0) {
    const result = await prune(cacheRoot(values['cache-dir']), { olderThanDays: number(values['older-than-days'], 7) })
    await out(JSON.stringify(result) + '\n')
    return 0
  }
  console.error(USAGE)
  return 2
}

function number(value: string | undefined, fallback: number): number {
  if (value === undefined) return fallback
  const n = Number(value)
  if (!Number.isFinite(n) || n < 0) throw new Error(`not a non-negative number: ${value}\n${USAGE}`)
  return n
}

main(process.argv.slice(2)).then(
  code => process.exit(code),
  e => { process.stderr.write((e instanceof Error ? e.stack ?? e.message : String(e)) + '\n', () => process.exit(1)) },
)
