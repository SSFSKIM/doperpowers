// The Bash restoration rule, proved by execution: each value × command shape
// is restored, run under /bin/bash and /bin/zsh, and must either print exactly
// the expected bytes or have been left unrestored (the handle in place, named).
// Nothing a value holds may run: its payloads print a marker that appears only
// when executed. Run with bun (devcloud/tests/mods/run.sh); not a kit test, as
// it starts processes.
import { spawnSync } from 'node:child_process'
import { closeSync, mkdtempSync, openSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { Handles } from '../../hooks/mods/secrets-handles'

// Executed, these print the marker; as data they never spell it.
const RUN = '$(printf "%s%s" INJ ECTED)'
const TICK = '`printf "%s%s" INJ ECTED`'
const MARKER = 'INJECTED'

const VALUES: [string, string][] = [
  ['inert', 'sk-live-AbC012_./+:@=%x'],
  ['base64', 'YWJjZGVm+/0123=='],
  ['dollar', `a${RUN}b`],
  ['backtick', `a${TICK}b`],
  ['quotes', `a'b"c${RUN}`],
  ['backslash', `a\\${RUN}\\\\b`],
  ['newline', `line1\n${RUN}\nline3`],
  ['semicolon', `a; printf ${MARKER}; b`],
  ['delimiter', `x\nEOF\nprintf ${MARKER}\ny`],
  ['leading =', '=printf'],
  ['tilde', '~root'],
  ['glob', 'a*b?c[d]'],
  ['bang', `a!b!!c${RUN}`],
  ['brace', 'a{b,c}d'],
  ['hash', 'a #b'],
]

// [name, command with {H} for the handle, the bytes it prints given the value]
const SHAPES: [string, string, (v: string) => string][] = [
  ['single', "printf %s '{H}'", (v) => v],
  ['double', 'printf %s "{H}"', (v) => v],
  ['unquoted', 'printf %s {H}', (v) => v],
  ['in a word', 'printf %s x{H}y', (v) => `x${v}y`],
  ['assignment', 'x={H}; printf %s "$x"', (v) => v],
  ['heredoc', 'cat <<EOF\n{H}\nEOF', (v) => `${v}\n`],
  ['quoted heredoc', "cat <<'EOF'\n{H}\nEOF", (v) => `${v}\n`],
  ['backslash heredoc', 'cat <<\\EOF\n{H}\nEOF', (v) => `${v}\n`],
  ['part-quoted heredoc', 'cat <<E"OF"\n{H}\nEOF', (v) => `${v}\n`],
  ['substitution in heredoc', 'cat <<EOF\n$(printf %s {H})\nEOF', (v) => `${v}\n`],
  ['here-string', 'cat <<< {H}', (v) => `${v}\n`],
  ['here-string then word', 'cat <<< x; printf %s {H}', (v) => `x\n${v}`],
  ['command substitution', 'printf %s "$(printf %s {H})"', (v) => v],
  ['backticks', 'printf %s "`printf %s {H}`"', (v) => v],
  ['comment', ': # {H}\nprintf %s ok', () => 'ok'],
  ['parameter default', 'printf %s "${X:-{H}}"', (v) => v],
  ['ansi-c', "printf %s $'{H}'", (v) => v],
  ['continuation', 'printf %s \\\n{H}', (v) => v],
  ['after $', 'X=1; printf %s ${H}', (v) => v],
]

const SHELLS = ['/bin/bash', '/bin/zsh']
const dir = mkdtempSync(join(tmpdir(), 'devcloud-shell-'))
let failures = 0
let restored = 0
let left = 0

function check(name: string, value: string, shape: string, template: string, expected: (v: string) => string) {
  const h = new Handles('test')
  h.setKnown([{ label: 'V', value }])
  const command = template.replace('{H}', '[secret:V]')
  const r = h.restoreShell(command)
  const unquotable = (r as { unquotable?: string[] }).unquotable ?? []
  if (unquotable.length > 0) {
    left++
    if (r.text !== command || unquotable[0] !== '[secret:V]') fail('left unrestored, but the command changed')
    return
  }
  restored++
  for (const shell of SHELLS) {
    // Into a file, not a pipe: a pipe's output from a quick child was now and
    // then lost under bun (exit 0, nothing read).
    const sink = join(dir, 'out')
    const fd = openSync(sink, 'w')
    spawnSync(shell, ['-c', r.text], { cwd: dir, stdio: ['ignore', fd, 'ignore'], timeout: 10_000 })
    closeSync(fd)
    const out = readFileSync(sink, 'utf8')
    if (out.includes(MARKER) && !expected(value).includes(MARKER)) fail(`${shell}: the value ran`)
    else if (out !== expected(value)) fail(`${shell}: printed ${JSON.stringify(out)}, not ${JSON.stringify(expected(value))}`)
  }
  function fail(why: string) {
    failures++
    console.log(`FAIL ${name} × ${shape}: ${why}`)
  }
}

for (const [name, value] of VALUES) for (const [shape, template, expected] of SHAPES) check(name, value, shape, template, expected)

// A small fuzz over the same shapes: values drawn from the characters that matter.
const ALPHABET = ['a', 'Z', '0', '_', '-', '.', '/', '+', ':', '@', '=', '%', ' ', '\n', "'", '"', '\\', '$', '`', ';', '&', '|', '<', '>', '(', ')', '*', '?', '[', ']', '{', '}', ',', '~', '!', '#', '^', 'EOF', RUN]
let seed = 20261017
const next = () => (seed = (seed * 1103515245 + 12345) >>> 0) >>> 16
for (let i = 0; i < 40; i++) {
  const length = 1 + (next() % 8)
  const value = Array.from({ length }, () => ALPHABET[next() % ALPHABET.length]).join('')
  for (const [shape, template, expected] of SHAPES) check(`fuzz ${JSON.stringify(value)}`, value, shape, template, expected)
}

rmSync(dir, { recursive: true, force: true })
console.log(`shell-exec: ${restored} restored and run under ${SHELLS.length} shells, ${left} left unrestored, ${failures} failed`)
process.exit(failures === 0 ? 0 : 1)
