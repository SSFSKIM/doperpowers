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

import { writeFileSync } from 'node:fs'

import { Handles, spellings } from '../../hooks/mods/secrets-handles'
import { ENCODE, readCommand } from '../../hooks/mods/secrets-reads'
import { credentialFields } from '../../hooks/mods/secrets-sources'
import type { Format } from '../../hooks/mods/secrets-sources'

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
  ['delimiter word', 'END_SECRET'],
  ['==', 'foo==printf'],
  ['trailing ==', 'YWJjZA=='],
  [':=', 'a:=printf'],
  ['command name', 'printf'],
  ['arithmetic', '1+1'],
  // Values whose first letter a zsh `$name:` modifier would eat (h, t, a, s, g, A).
  ['h…', 'habcdef12'],
  ['t…', 'tok12345'],
  ['a…', 'abcdef12'],
  ['s…', 'sabc123'],
  ['g…', 'gh1234ab'],
  ['A…', 'A1b2c3d4'],
  ['digits', '12345678'],
  ['slash', 'abc/defg'],
  ['= first', '=printf'],
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
  ['delimiter equal', `cat <<'END_SECRET'\n{H}\nprintf "%s%s" INJ ECTED\nEND_SECRET`, (v) => `${v}\nprintf "%s%s" INJ ECTED\n`],
  ['after =', 'printf %s x={H}', (v) => `x=${v}`],
  ['after ==', 'printf %s x=={H}', (v) => `x==${v}`],
  ['after :=', 'printf %s x=a:={H}', (v) => `x=a:=${v}`],
  ['braced', 'printf %s ${{H}}', (v) => v],
  ['backslash', 'printf %s \\{H}', (v) => v],
  ['backslash in double', 'printf %s "\\{H}"', (v) => `\\${v}`],
  ['(( ))', '(( x = {H} )); printf %s ok', () => 'ok'],
  ['$(( ))', 'printf %s $(( {H} ))', (v) => v],
  ['$[ ]', 'printf %s $[ {H} ]', (v) => v],
  ['let', 'let x={H}; printf %s ok', () => 'ok'],
  ['[[ ]]', '[[ {H} == {H} ]] && printf %s ok', () => 'ok'],
  ['brace list', 'printf %s {a,{H}}', (v) => `a${v}`],
  // Fix wave 4: zsh modifiers, word-initial =, float and subscript arithmetic,
  // pattern replacement, redirection targets, braceccl, glob qualifiers.
  ['$USER: modifier', 'printf %s $USER:{H}', (v) => `alice:${v}`],
  ['"$USER:" modifier', 'printf %s "$USER:{H}"', (v) => `alice:${v}`],
  ['url with $USER', 'printf %s https://$USER:{H}@github.com/o/r.git', (v) => `https://alice:${v}@github.com/o/r.git`],
  ['$1: modifier', 'set -- p; printf %s $1:{H}', (v) => `p:${v}`],
  ['$X:t: modifier', 'printf %s $X:t:{H}', (v) => `c.txt:${v}`],
  ['${USER}:', 'printf %s ${USER}:{H}', (v) => `alice:${v}`],
  ['word-initial =', 'printf %s ={H}', (v) => `=${v}`],
  ["''=", "printf %s ''={H}", (v) => `=${v}`],
  ['array =', 'a=( ={H} ); printf %s "${a[@]}"', (v) => `=${v}`],
  ['brace =', 'printf %s {a,={H},b}', (v) => `a=${v}b`],
  ['typeset -F', 'typeset -F x={H}; printf %s "$x"', (v) => v],
  ['float', 'float x={H}; printf %s "$x"', (v) => v],
  ['local -F', 'f() { local -F x={H}; printf %s "$x"; }; f', (v) => v],
  ['subscript', 'a=(p q r); printf %s ${a[ {H} ]}', (v) => v],
  ['offset', 'printf %s ${X: {H} }', (v) => v],
  ['${X/pat/rep}', 'X=zabcdefgz; printf %s "${X/a{H}/Q}"', (v) => v],
  ['${X//pat/rep}', 'X=zabcdefgz; printf %s "${X//{H}/Q}"', (v) => v],
  ['>& target', 'printf %s ok >& {H}', () => 'ok'],
  ['> target', 'printf %s ok > {H}', () => ''],
  ['braceccl', 'printf %s {x{H}y}', (v) => `{x${v}y}`],
  ['glob qualifier', 'printf %s *(.{H})', (v) => `*(.${v})`],
  ['comma word', 'printf %s a,{H}', (v) => `a,${v}`],
  ['$ in double', 'b=1; printf %s "a$b{H}"', (v) => `a1${v}`],
  // The common shapes, which must still restore (MUST_RESTORE).
  ['bearer', 'printf %s "Authorization: Bearer {H}"', (v) => `Authorization: Bearer ${v}`],
  ['single words', "printf %s 'a {H} b'", (v) => `a ${v} b`],
  ['--token=', 'printf %s --token={H}', (v) => `--token=${v}`],
  ['X= cmd', 'X={H} sh -c \'printf %s "$X"\'', (v) => v],
  ['user:token@host', 'printf %s https://user:{H}@host/p', (v) => `https://user:${v}@host/p`],
]
// Shapes an inert value of these must restore in, or the rule is too narrow to use.
const MUST_RESTORE = ['bearer', 'single words', '--token=', 'X= cmd', 'user:token@host']
const COMMON_VALUES = ['inert', 'base64', 'h…', 't…', 'a…', 's…', 'g…', 'A…', 'digits', 'slash']

// Each shell, and the options that change how words are read.
const SHELLS: string[][] = [
  ['/bin/bash'],
  ['/bin/bash', '--posix'],
  ['/bin/bash', '-f'],
  ['/bin/zsh'],
  ['/bin/zsh', '-o', 'magic_equal_subst'],
  ['/bin/zsh', '-o', 'extendedglob'],
  ['/bin/zsh', '-o', 'noglob'],
  ['/bin/zsh', '-o', 'braceccl'],
  ['/bin/zsh', '-o', 'kshglob'],
]
// What the shapes read: a user, a path for `:t`.
const ENV = { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: '', USER: 'alice', X: '/a/b/c.txt' }
const dir = mkdtempSync(join(tmpdir(), 'devcloud-shell-'))
let failures = 0
let restored = 0
let left = 0

function check(name: string, value: string, shape: string, template: string, expected: (v: string) => string) {
  const h = new Handles('test')
  h.setKnown([{ label: 'V', value }])
  const command = template.split('{H}').join('[secret:V]')
  const r = h.restoreShell(command)
  const unquotable = (r as { unquotable?: string[] }).unquotable ?? []
  if (unquotable.length > 0) {
    left++
    // (A padded base64 value in a URL is the one exception: `==@` is not a trailing run.)
    const mustRestore = MUST_RESTORE.includes(shape) && COMMON_VALUES.includes(name) && !(name === 'base64' && shape === 'user:token@host')
    if (mustRestore) fail('left unrestored, but this common shape must restore')
    if (r.text !== command || unquotable[0] !== '[secret:V]') fail('left unrestored, but the command changed')
    return
  }
  restored++
  for (const [shell, ...options] of SHELLS) {
    // Into a file, not a pipe: a pipe's output from a quick child was now and
    // then lost under bun (exit 0, nothing read).
    const sink = join(dir, 'out')
    const fd = openSync(sink, 'w')
    spawnSync(shell!, [...options, '-c', r.text], { cwd: dir, env: { ...ENV, HOME: dir }, stdio: ['ignore', fd, 'ignore'], timeout: 10_000 })
    rmSync(join(dir, '[secret:V]'), { force: true })
    closeSync(fd)
    const out = readFileSync(sink, 'utf8')
    const name = [shell, ...options].join(' ')
    if (out.includes(MARKER) && !expected(value).includes(MARKER)) fail(`${name}: the value ran`)
    else if (out !== expected(value)) fail(`${name}: printed ${JSON.stringify(out)}, not ${JSON.stringify(expected(value))}`)
  }
  function fail(why: string) {
    failures++
    console.log(`FAIL ${name} × ${shape}: ${why}`)
  }
}

for (const [name, value] of VALUES) for (const [shape, template, expected] of SHAPES) check(name, value, shape, template, expected)

// A small fuzz over the same shapes: values drawn from the characters that matter.
const ALPHABET = ['a', 'Z', '0', '_', '-', '.', '/', '+', ':', '@', '=', '==', ':=', '%', 'printf', 'END_SECRET', ' ', '\n', "'", '"', '\\', '$', '`', ';', '&', '|', '<', '>', '(', ')', '*', '?', '[', ']', '{', '}', ',', '~', '!', '#', '^', 'EOF', RUN]
let seed = 20261017
const next = () => (seed = (seed * 1103515245 + 12345) >>> 0) >>> 16
for (let i = 0; i < 40; i++) {
  const length = 1 + (next() % 8)
  const value = Array.from({ length }, () => ALPHABET[next() % ALPHABET.length]).join('')
  for (const [shape, template, expected] of SHAPES) check(`fuzz ${JSON.stringify(value)}`, value, shape, template, expected)
}

// The reads a notice names, run against real files: each prints exactly the
// value its parser read, its escaping undone; through its encoding, exactly
// the handle's spelling.
const tricky = 'pa:ss\\w"o rd#é'
const FILES: [Format, string, string][] = [
  ['json', '.codex/auth.json', JSON.stringify({ tokens: { access_token: tricky, 'odd key': { token: `${tricky}2` }, refresh_token: 'ab?>c~d?>~', id_token: 'ab?>c~d?>~x' } })],
  ['gcloud', '.config/gcloud/key.json', JSON.stringify({ type: 'service_account', private_key: '-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n' })],
  ['toml', '.config/hcloud/cli.toml', `[[contexts]]\nname = "one"\ntoken = "t\\"q\\u00e9x1234567" # rotated\n[[contexts]]\nname = "one"\ntoken = 'lit#eral12345'\n`],
  ['pgpass', '.pgpass', `db:5432:*:app:pa\\:ss\\\\x1\ndb:5432:*:app:second123\n`],
  ['netrc', '.netrc', `machine m login me password "q uo\\"ted12"\nmachine m password "ctl\\n\\t\\qx99"\ndefault login d password un\\quoted"7\n`],
  ['git-credentials', '.git-credentials', `https://me:p%40ss%20w1@github.com/o/one.git\nhttps://me:other12345@github.com/o/one.git\n`],
  ['npmrc', '.npmrc', `registry=https://r/\n//r/:_authToken="npm_tok12345"\n`],
]
let reads = 0
for (const [format, path, text] of FILES) {
  const full = join(dir, path)
  spawnSync('mkdir', ['-p', join(full, '..')])
  writeFileSync(full, text)
  for (const field of credentialFields(format, text, path)) {
    if (!field.read) continue
    for (const { enc, text: spelling } of spellings(field.value)) {
      const command = enc ? `${readCommand(field.read)} | ${ENCODE[enc]}` : readCommand(field.read)
      for (const shell of ['/bin/bash', '/bin/zsh']) {
        const sink = join(dir, 'out')
        const fd = openSync(sink, 'w')
        spawnSync(shell, ['-c', command], { cwd: dir, env: { ...ENV, HOME: dir }, stdio: ['ignore', fd, 'ignore'], timeout: 10_000 })
        closeSync(fd)
        reads++
        const out = readFileSync(sink, 'utf8')
        if (out !== spelling) {
          failures++
          console.log(`FAIL read ${format} ${field.field}${enc ? `~${enc}` : ''} under ${shell}: printed ${JSON.stringify(out)}, not ${JSON.stringify(spelling)}`)
        }
      }
    }
  }
}
// A store value: the file holds it and one newline; the read drops just that.
for (const value of ['plain1234', 'ends\nin newline\n']) {
  writeFileSync(join(dir, 'store-key'), `${value}\n`)
  for (const shell of ['/bin/bash', '/bin/zsh']) {
    const out = spawnSync(shell, ['-c', readCommand({ kind: 'store', path: 'store-key' })], { cwd: dir, env: { ...ENV, HOME: dir }, encoding: 'utf8' }).stdout
    reads++
    if (out !== value) {
      failures++
      console.log(`FAIL read store under ${shell}: printed ${JSON.stringify(out)}, not ${JSON.stringify(value)}`)
    }
  }
}

rmSync(dir, { recursive: true, force: true })
console.log(`shell-exec: ${restored} restored and run under ${SHELLS.length} shells, ${left} left unrestored, ${reads} reads run, ${failures} failed`)
process.exit(failures === 0 ? 0 : 1)
