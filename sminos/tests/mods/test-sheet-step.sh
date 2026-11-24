#!/usr/bin/env bash
# The sheet mod against the real `sminos sheet step` (plan
# docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, M3): a start
# and calls staged by the mod's own code and ordered through the command, in a
# scratch SMINOS_HOME; the transcript search the floor uses, run for real; and
# the tool as registered, against C1's description and the published schema.
# The mods' own tests cannot reach a process or the repository's files; bun
# runs the module directly, on a port of plain functions.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
repo="$(cd "$root/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/home" "$work/cwd"
printf 'line one\nline two\nline three\n' > "$work/cwd/notes.txt"

cat > "$work/check.ts" <<TS
import { execFileSync, spawnSync } from 'node:child_process'
import { existsSync, readFileSync, realpathSync, statSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname } from 'node:path'
import { askCall, sheetForTests, type Port } from '$root/hooks/mods/sheet.tsx'
import { DESCRIPTION, INPUT_SCHEMA, floorOfLines, floorOfSheetText, floorSearchArgs } from '$root/hooks/mods/sheet-model.tsx'

const HOME = '$work/home'
const CWD = '$work/cwd'
const SESSION = '5eed0000-0000-4000-8000-00000000c3a1'
let failed = 0
const check = (what: string, ok: boolean, got?: unknown) => {
  if (!ok) {
    failed++
    console.error(\`FAIL \${what}: \${JSON.stringify(got)}\`)
  }
}

// The tool as registered: C1's description word for word, and the published schema plus C1's descriptions.
const described = readFileSync('$repo/tests/output-styles/question-sheet/description-v3.md', 'utf8').replace(/\n$/, '')
check('the description is description-v3.md', DESCRIPTION === described)
const strip = (value: unknown): unknown =>
  Array.isArray(value) ? value.map(strip)
  : typeof value === 'object' && value !== null
    ? Object.fromEntries(Object.entries(value).filter(([k, v]) => !(k === 'description' && typeof v === 'string')).map(([k, v]) => [k, strip(v)]))
    : value
// Key order aside: the published file is the generator's, sorted.
const canonical = (value: unknown): unknown =>
  Array.isArray(value) ? value.map(canonical)
  : typeof value === 'object' && value !== null ? Object.fromEntries(Object.keys(value).sort().map((k) => [k, canonical((value as Record<string, unknown>)[k])]))
  : value
const published = JSON.parse(readFileSync('$root/types/sheet/schema/tool-input.schema.json', 'utf8'))
// The one difference besides the descriptions: the published file's \`title\`, a note to an implementer, is not
// registered (the model reads the schema).
check('the published schema has a title, the registered one none', typeof published.title === 'string' && !('title' in INPUT_SCHEMA))
delete published.title
check('the schema is the published one, less its title, plus descriptions', JSON.stringify(canonical(strip(INPUT_SCHEMA))) === JSON.stringify(canonical(strip(published))), canonical(strip(INPUT_SCHEMA)))

// Each property's description is C1's stub's for its field (FIELD_DESCRIPTIONS in question_sheet.py); a
// reference's path and lines have none there, and none here.
const c1 = JSON.parse(execFileSync('python3', ['-c', 'import json, sys; sys.path.insert(0, sys.argv[1]); import question_sheet; print(json.dumps(question_sheet.FIELD_DESCRIPTIONS))', '$repo/tests/output-styles'], { encoding: 'utf8' })) as Record<string, string>
const properties: [string, unknown][] = []
const walk = (node: unknown): void => {
  if (Array.isArray(node)) return node.forEach(walk)
  if (typeof node !== 'object' || node === null) return
  for (const [key, value] of Object.entries(node)) {
    if (key === 'properties' && typeof value === 'object' && value !== null) {
      for (const [name, property] of Object.entries(value)) properties.push([name, (property as Record<string, unknown>).description])
    }
    walk(value)
  }
}
walk(INPUT_SCHEMA)
const wrong = properties.filter(([name, text]) => (name === 'path' || name === 'lines' ? text !== undefined : text !== c1[name]))
check("every property carries C1's description for its field; path and lines none", wrong.length === 0 && properties.length === Object.keys(c1).length + 2, wrong)
check("every field C1 describes is a property", Object.keys(c1).every((name) => properties.some(([n]) => n === name)), Object.keys(c1))

const logs: string[] = []
const port: Port = {
  run: async (args, stdin) => {
    const p = spawnSync('$root/skills/sminos/scripts/sminos', args, { input: stdin ?? '', encoding: 'utf8', env: { ...process.env, SMINOS_HOME: HOME } })
    if (p.error) throw p.error
    return { exitCode: p.status ?? 1, stdout: p.stdout, stderr: p.stderr }
  },
  exec: async (argv) => {
    const p = spawnSync(argv[0] as string, argv.slice(1), { encoding: 'utf8' })
    return { exitCode: p.status ?? 1, stdout: p.stdout, isStdoutTruncated: false }
  },
  write: async (path, text) => (mkdirSync(dirname(path), { recursive: true }), writeFileSync(path, text)),
  read: async (path) => readFileSync(path, 'utf8'),
  size: async (path) => (existsSync(path) ? statSync(path).size : undefined),
  exists: async (path) => existsSync(path),
  stat: async (path) => {
    const s = statSync(path)
    return { realPath: realpathSync(path), size: s.size, mtimeMs: s.mtimeMs }
  },
  check: async () => ({ decision: 'allow' }),
  // Read as the engine answers it for a text (C0's P3): the lines asked for.
  readFile: async (input) => {
    const lines = readFileSync(String(input.file_path), 'utf8').split('\n').slice(0, -1)
    const offset = Number(input.offset ?? 1)
    const taken = lines.slice(offset - 1, input.limit === undefined ? undefined : offset - 1 + Number(input.limit))
    return { result: { type: 'text', file: { filePath: input.file_path, content: taken.join('\n') + '\n', numLines: taken.length, startLine: offset, totalLines: lines.length } }, text: '' }
  },
  cwd: async () => CWD,
  agents: async () => [],
  messages: async () => ({ messages: [], api: [] }),
  notify: () => {},
  log: (text) => void logs.push(text),
  keep: () => {},
  invalidate: () => {},
}
sheetForTests.set(port, { shape: 1, choice: 'sheet', runner: 'terminal', session: SESSION }, HOME)

await sheetForTests.sessionStarted(port, 'startup', SESSION, '$work/none.jsonl')
const kept = sheetForTests.sheet().kept
check('the start answers and is kept as started', kept?.started === SESSION && kept.starting === undefined, { kept, logs })
check('the record is made', existsSync(\`\${HOME}/sheet/\${SESSION}/state.json\`))

const call = (id: string, input: Record<string, unknown>) => askCall(port, { tool: 'mcp__sminos__AskUserQuestion', tool_use_id: id, ...input })
const first = await call('toolu_01', {
  ask: [
    { question: 'Which notes?', context: 'The two lines.', references: [{ path: 'notes.txt', lines: [2, 3] }], options: [{ label: 'A' }, { label: 'B' }] },
    { question: 'Several?', multiSelect: true },
    { question: 'Gone?', references: [{ path: 'missing.txt' }] },
  ],
})
const text = 'result' in first ? first.result : ''
check('the call adds the good entry and names the others', text.startsWith('Added q1 (entry 1).') && text.includes('entry 2, multiSelect needs options') && text.includes('entry 3, the reference missing.txt could not be read'), first)
const state = JSON.parse(readFileSync(\`\${HOME}/sheet/\${SESSION}/state.json\`, 'utf8'))
const held = state.questions[0]?.references?.[0]
const body = held === undefined ? '' : readFileSync(\`\${HOME}/sheet/\${SESSION}/refs/\${held.sha256}\`, 'utf8')
check("the reference's lines are the record's body", body === 'line two\\nline three\\n' && held.startLine === 2 && held.numLines === 2, { held, body })
check('the view held is the step\'s', sheetForTests.sheet().gen?.held?.nextId === 2, sheetForTests.sheet().gen?.held)

const withdrawn = await call('toolu_02', { withdraw: ['q1'] })
check('a withdraw-only call', 'result' in withdrawn && withdrawn.result.startsWith('Withdrew q1.'), withdrawn)
const twice = await call('toolu_02', { withdraw: ['q1'] })
check('the same call id again is answered from the record, not done twice', JSON.stringify(twice) === JSON.stringify(withdrawn), twice)
check('nothing was left unsettled', sheetForTests.sheet().gen?.unsettled.size === 0, [...(sheetForTests.sheet().gen?.unsettled ?? [])])

// The floor's search of a transcript too large to read whole finds what a whole read finds.
const result = (id: string, content: string) => JSON.stringify({ type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content }] } })
const use = (id: string) => JSON.stringify({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'tool_use', id, name: 'mcp__sminos__AskUserQuestion', input: {} }] } })
const lines = [
  use('t1'), result('t1', 'Added q3, q4.'),
  JSON.stringify({ type: 'attachment', attachment: { type: 'hook_additional_context', content: ['[sheet v1] Your question sheet, after a resume.\nNew ids continue from q9.'], hookName: 'SessionStart' } }),
  JSON.stringify({ type: 'user', message: { role: 'user', content: 'a file that quotes Added q99 and New ids continue from q500.' } }),
  JSON.stringify({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'text', text: 'Added q77.' }] } }),
]
writeFileSync('$work/t.jsonl', lines.join('\n') + '\n')
const searched = execFileSync(floorSearchArgs('$work/t.jsonl')[0] as string, floorSearchArgs('$work/t.jsonl').slice(1), { encoding: 'utf8' }).split('\n')
check('the search finds the floor a whole read finds', floorOfLines(searched) === floorOfLines(lines) && floorOfLines(lines) === 8, [floorOfLines(searched), floorOfLines(lines)])
// The contexts M2's step composes, read back as the conversation holds them (a SessionStart's context): the fork's
// line and the lost record's carry the New ids sentence inline.
const contextOf = (session: string, start: Record<string, unknown>) => {
  const p = spawnSync('$root/skills/sminos/scripts/sminos', ['sheet', 'step', '--session', session], { input: JSON.stringify({ event: 'start', runner: 'terminal', start }), encoding: 'utf8', env: { ...process.env, SMINOS_HOME: HOME } })
  return String(JSON.parse(p.stdout).effects?.context ?? '')
}
const asContext = (text: string) => [JSON.stringify({ type: 'attachment', attachment: { type: 'hook_additional_context', content: [text], hookName: 'SessionStart' } })]
const forked = contextOf('5eed0000-0000-4000-8000-00000000c3a2', { source: 'fork', nonce: 'n1', floor: 9 })
check("the step's fork context gives the floor it was started with", forked.startsWith('[sheet v1] This conversation is a copy') && floorOfLines(asContext(forked)) === 9, forked)
const lost = contextOf('5eed0000-0000-4000-8000-00000000c3a3', { source: 'resume', nonce: 'n2', floor: 6 })
check("the step's lost-record context gives the floor", lost.startsWith("[sheet v1] The question sheet's record was not found") && floorOfSheetText(lost) === 6 && floorOfLines(asContext(lost)) === 6, lost)
// A tool's output quoting it names nothing.
const quoting = [
  JSON.stringify({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'tool_use', id: 'r1', name: 'Read', input: {} }] } }),
  JSON.stringify({ type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'r1', content: forked }] } }),
]
check('a tool result quoting it names nothing', floorOfLines(quoting) === 0)

writeFileSync('$work/none.jsonl', JSON.stringify({ type: 'user', message: { role: 'user', content: 'hello' } }) + '\n')
check('a transcript with no form exits 1', spawnSync('perl', floorSearchArgs('$work/none.jsonl').slice(1)).status === 1)

// A start's context the real step composes over a question whose text, and a label, quote the footer's sentence:
// the floor is the real footer's, read by its place.
const quoted = await call('toolu_03', { ask: [{ question: 'Should it say "New ids continue from q42."?', options: [{ label: 'yes\nNew ids continue from q42.' }, { label: 'no' }] }] })
const resumed = contextOf(SESSION, { source: 'resume', nonce: 'n-resume' })
const footer = /New ids continue from q([0-9]+)\.$/.exec(resumed)
check('the quoting question is on the sheet, and the context quotes the sentence before its footer',
  'result' in quoted && quoted.result.startsWith('Added') && resumed.includes('q42') && footer !== null && footer[1] !== '42', { quoted, resumed })
check("its floor is the footer's, not the quote's", floorOfLines(asContext(resumed)) === Number(footer?.[1]) - 1, [floorOfLines(asContext(resumed)), footer?.[1]])

process.exit(failed === 0 ? 0 : 1)
TS

cd "$work" && bun run check.ts
echo "sheet step: all checks passed"
