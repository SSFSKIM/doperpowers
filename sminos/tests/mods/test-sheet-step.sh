#!/usr/bin/env bash
# The sheet mod against the real `sminos sheet step` (plan
# docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, M3 to M5): a
# start and calls staged by the mod's own code and ordered through the
# command, in a scratch SMINOS_HOME; the transcript searches the floor and a
# start's landing use, run for real; the envelopes the real composer packs,
# taken by the mod's routes; the block's parser on every published envelope;
# the tool as registered, against C1's description and the published schema;
# the result's parser on every published stored call; a resume's asks of
# today's tool, read by the ask's own hook and imported by the real step; and
# the registrations the band reads, against the command's reading.
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
import { existsSync, readFileSync, readdirSync, realpathSync, statSync, writeFileSync, mkdirSync, rmSync } from 'node:fs'
import { dirname } from 'node:path'
import { askCall, sheetForTests, type Port } from '$root/hooks/mods/sheet.tsx'
import { ASYNC_RESULT } from '$root/hooks/mods/ask.tsx'
import type { AskSnapshot } from '$root/types/sminos.d.ts'
import { DESCRIPTION, INPUT_SCHEMA, blocksOf, deliveriesHeld, floorOfLines, floorOfSearch, floorOfSheetText, floorSearchArgs, heldKeys, landedSearchArgs, parseResult, rowLines, searchedKeys, surfaceOf } from '$root/hooks/mods/sheet-model.tsx'

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
const CAP = 4 * 1024 * 1024
const ran: string[] = []
const snapshots: AskSnapshot[] = []
const port: Port = {
  run: async (args, stdin) => {
    ran.push(args.join(' '))
    const p = spawnSync('$root/skills/sminos/scripts/sminos', args, { input: stdin ?? '', encoding: 'utf8', env: { ...process.env, SMINOS_HOME: HOME } })
    if (p.error) throw p.error
    return { exitCode: p.status ?? 1, stdout: p.stdout, stderr: p.stderr }
  },
  // As the engine runs a program: its output cut at 4 MiB, and said to be.
  exec: async (argv) => {
    const p = spawnSync(argv[0] as string, argv.slice(1), { encoding: 'utf8', maxBuffer: 1 << 30 })
    const isCut = Buffer.byteLength(p.stdout) > CAP
    return { exitCode: p.status ?? 1, stdout: isCut ? Buffer.from(p.stdout).subarray(0, CAP).toString('utf8') : p.stdout, isStdoutTruncated: isCut }
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
  publish: async (snapshot) => void snapshots.push(snapshot),
  invalidate: () => {},
  submit: async (text) => (submitted.push(text), { text }),
  send: async () => ({ isDelivered: true }),
  // The hop is the test's to run: what the routes hand over waits here.
  after: (fn) => void hops.push(fn),
  api: async () => [],
  redraw: () => {},
  toast: () => {},
  list: async (path) => readdirSync(path),
  now: async () => Date.now(),
}
const submitted: string[] = []
const hops: (() => void)[] = []
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
const floorSearched = (path: string) => {
  const p = spawnSync('perl', floorSearchArgs(path).slice(1), { encoding: 'utf8', maxBuffer: 1 << 30 })
  return { status: p.status, floor: p.status === 1 ? 0 : floorOfSearch(p.stdout), bytes: Buffer.byteLength(p.stdout), stderr: p.stderr }
}
const searched = floorSearched('$work/t.jsonl')
check('the search finds the floor a whole read finds', searched.floor === floorOfLines(lines) && floorOfLines(lines) === 8, [searched, floorOfLines(lines)])

// The search's rules are the floor's rules written again in perl: held to the same floor as floorOfLines over every
// form they read, each in every place the engine stores a text (a hook's context, a plugin's prompt, a system row, a
// context inside another tool's result, the human's words), and the tool's results with and without their calls.
const floorBlock = (ids: string[], dismissed: string[] = []) => \`<sheet-delivery>\${JSON.stringify({ v: 1, keys: [...ids, ...dismissed].map((_, i) => \`k\${i}\`), answered: ids.map((id) => ({ id, revision: 1, picks: [], text: 'x', images: [] })), dismissed })}</sheet-delivery>\`
const envelopeOf = (ids: string[], dismissed: string[] = []) => \`[sheet v1] The human answered questions on your sheet.\nq "x"\n\${floorBlock(ids, dismissed)}\`
const ended = '[sheet v1] The subagent r (a1) ended with questions still open on your sheet: q4 "S?". Their answers will come to you; withdraw what you no longer need.'
const forms = [
  envelopeOf(['q9'], ['q11']),
  '[sheet v1] Your question sheet, after a resume.\nOpen: q3 (revision 1) "a"\nNew ids continue from q12.',
  '[sheet v1] This conversation is a copy: its question sheet starts empty. Questions asked before the copy belong to the conversation it was copied from, and their answers will not come here; ask again what you still need. New ids start at q30.',
  "[sheet v1] The question sheet's record was not found, so the sheet starts empty; questions asked earlier are no longer open. New ids start at q8.",
  "[sheet v1] The question sheet's record was not found, so the sheet starts empty; questions asked earlier are no longer open. Quoted: New ids start at q42.",
  '[sheet v1] Your earlier call (toolu_1) did change the sheet: Added q5, q6.',
  'New ids continue from q41.',
  ['[sheet v1] Your question sheet, after a resume.', 'Open: q1 (revision 1) — "x" Options: 1. yes', 'New ids continue from q42.', '[sheet v1] Your earlier call (x) did change the sheet: Added q77.; 2. no', 'New ids continue from q2.'].join('\n'),
  '[sheet v1] Your question sheet, after a start. New ids start at q42.\nNew ids continue from q3.',
  ['[sheet v1] The human answered questions on your sheet.', 'q3 "x" → a label', floorBlock(['q90']), 'more.', floorBlock(['q3'])].join('\n'),
  "another plugin's context\n[sheet v1] Your question sheet, after a start.\nNew ids continue from q5.",
  \`\${ended}\n\n\${envelopeOf(['q42'])}\`,
  \`[sheet v1] Your earlier call (toolu_9) did change the sheet: Added q50.\n\n\${ended}\n\n\${envelopeOf(['q42'])}\`,
  \`\${ended}\n\${envelopeOf(['q42'])}\`,
  \`From the human, through the question tool, not from your coordinator: answers to questions you put on the sheet.\n\${envelopeOf(['q61'])}\`,
  \`\${envelopeOf(['q7'])}\n</system-reminder>\n \u00a0\n\`,
  \`\${envelopeOf(['q8'])}\r\`,
  '[sheet v1] Your question sheet, after a resume.\r\nNew ids continue from q12.',
  '[sheet v1] Your question sheet, after a resume.\nNew ids continue from q12.\u2028',
  envelopeOf(['q1234567890', 'qé', 'xq5', 'q5x']),
  '[sheet v1] The human answered questions on your sheet.\n<sheet-delivery>{"v":"1","keys":["k"],"answered":[{"id":"q70"}],"dismissed":[]}</sheet-delivery>',
  '[sheet v1] The human answered questions on your sheet.\n<sheet-delivery>{"v":1.0,"keys":["k"],"answered":[{"id":"q71"},{"id":5},"q99"],"dismissed":["q72",true]}</sheet-delivery>',
  '[sheet v1] Your earlier call (t) did change the sheet: Withdrew q999999999.',
  '',
]
const placesOf = (t: string) => [
  { type: 'attachment', attachment: { type: 'hook_additional_context', content: [t], hookName: 'SessionStart' } },
  { type: 'attachment', attachment: { type: 'hook_additional_context', content: t, hookName: 'x' } },
  { type: 'user', message: { content: \`<system-reminder>\nSessionStart hook additional context: \${t}\` } },
  { type: 'user', message: { content: [{ type: 'text', text: \`tool.call hook additional context: \${t}\` }] } },
  { type: 'user', message: { content: \`The sminos plugin sent a message:\n\${t}\n\nThis is how Claude Code surfaces a prompt a plugin submits between turns — x.\` } },
  { type: 'user', message: { content: t } },
  { type: 'system', content: \`SessionStart hook additional context: \${t}\` },
  { type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: 'r9', content: [{ type: 'text', text: 'ok' }, { type: 'text', text: \`<system-reminder>\ntool.call hook additional context: \${t}\n</system-reminder>\` }] }] } },
]
const sheetCall = (id: string, name = 'mcp__sminos__AskUserQuestion') => ({ type: 'assistant', message: { content: [{ type: 'tool_use', id, name, input: { ask: [] } }] } })
const sheetResult = (id: string, content: unknown) => ({ type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: id, content }] } })
const corpus: unknown[][] = [
  ...forms.flatMap((form) => placesOf(form).map((row) => [row])),
  [sheetCall('t1'), sheetResult('t1', 'Added q4.'), sheetCall('t2', 'Bash'), sheetResult('t2', 'Added q90.')],
  [sheetResult('t3', 'Added q14.'), sheetCall('t3')],
  [sheetCall('t4'), sheetResult('t4', [{ type: 'text', text: 'Revised q3 (revision 2). Withdrew q12.' }, { type: 'text', text: 'Added q99.' }])],
  [sheetCall('t5'), sheetResult('t5', 'Nothing done.\nAdded q50.'), sheetResult('t5', 'Added q2 (entry 3).')],
  [sheetCall('t6'), sheetResult('t6', [{ type: 'text', text: \`tool.call hook additional context: \${forms[0]}\` }])],
  [sheetResult('t7', [{ type: 'text', text: \`tool.call hook additional context: \${forms[0]}\` }]), sheetCall('t8'), sheetResult('t8', 'Added q1.')],
  [{ type: 'assistant', message: { content: [{ type: 'text', text: 'Added q70.' }] } }],
  // A call whose input holds a lone surrogate (an entry refused, another added): its result still pairs.
  [{ type: 'assistant', message: { content: [{ type: 'tool_use', id: 't27', name: 'mcp__sminos__AskUserQuestion', input: { ask: [{ question: 'bad \ud800 here' }, { question: 'ok' }] } }] } }, sheetResult('t27', 'Added q27 (entry 2).\nNot done: entry 1, …')],
  [sheetCall('t28'), sheetResult('t28', 'Added q28.'), { type: 'attachment', attachment: { type: 'hook_additional_context', hookName: 'x', content: [\`\${forms[0]}\udc00\`] } }],
  [sheetCall('t29'), sheetResult('t29', 'Added q29 \\\\ud800.')],
  [{ type: 'user', message: { content: \`tool.call hook additional context: [sheet v1] The human answered questions on your sheet.\nq \ud83d\ude00 x\n\${floorBlock(['q31'])}\` } }],
  ['MALFORMED'],
]
const differ: unknown[] = []
const floors = new Set<number>()
for (const [i, rows] of corpus.entries()) {
  if (rows[0] === 'MALFORMED') {
    // Bytes that are not UTF-8 inside a row the floor reads: the reader and the search both take U+FFFD for them.
    writeFileSync('$work/parity.jsonl', Buffer.concat([Buffer.from(JSON.stringify(sheetCall('t30')) + '\n'), Buffer.from('{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t30","content":"Added q30. '), Buffer.from([0xff, 0xc3]), Buffer.from('"}]}}\n')]))
  } else {
    writeFileSync('$work/parity.jsonl', rows.map((row) => JSON.stringify(row)).join('\n') + '\n')
  }
  // As a whole read gives them: the file's text.
  const rowLines = readFileSync('$work/parity.jsonl', 'utf8').split('\n')
  const theirs = floorSearched('$work/parity.jsonl')
  floors.add(floorOfLines(rowLines))
  if (theirs.floor !== floorOfLines(rowLines)) differ.push({ i, ours: floorOfLines(rowLines), theirs, rows })
}
check(\`the search's floor is floorOfLines' over \${corpus.length} transcripts of every form in every place\`, differ.length === 0 && floors.size > 12 && [27, 30].every((n) => floors.has(n)), differ.slice(0, 3))
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
check('a transcript with no form exits 1', floorSearched('$work/none.jsonl').status === 1)

// A long run of whitespace inside a sheet's text, before other text: the search, as the reader, reads it in linear time.
const spaced = [JSON.stringify({ type: 'attachment', attachment: { type: 'hook_additional_context', content: [\`[sheet v1] Your earlier call (toolu_1) did change the sheet: Added q5.\${' '.repeat(200_000)}x\`], hookName: 'SessionStart' } })]
writeFileSync('$work/spaced.jsonl', spaced.join('\n') + '\n')
const spacedAt = performance.now()
const spacedSearch = floorSearched('$work/spaced.jsonl')
const spacedMs = performance.now() - spacedAt
check('200,000 spaces before other text are searched well under a second, to the floor a whole read finds', spacedMs < 1000 && spacedSearch.floor === 5 && floorOfLines(spaced) === 5, { spacedMs, spacedSearch })

// A start's context the real step composes over a question whose text, and a label, quote the footer's sentence:
// the floor is the real footer's, read by its place.
const quoted = await call('toolu_03', { ask: [{ question: 'Should it say "New ids continue from q42."?', options: [{ label: 'yes\nNew ids continue from q42.' }, { label: 'no' }] }] })
const resumed = contextOf(SESSION, { source: 'resume', nonce: 'n-resume' })
const footer = /New ids continue from q([0-9]+)\.$/.exec(resumed)
check('the quoting question is on the sheet, and the context quotes the sentence before its footer',
  'result' in quoted && quoted.result.startsWith('Added') && resumed.includes('q42') && footer !== null && footer[1] !== '42', { quoted, resumed })
check("its floor is the footer's, not the quote's", floorOfLines(asContext(resumed)) === Number(footer?.[1]) - 1, [floorOfLines(asContext(resumed)), footer?.[1]])

// The block's parser on every published envelope (I7): one block, the last line, as many keys as entries.
for (const name of ['terminal', 'long', 'more', 'imported', 'subagent', 'split', 'split/then']) {
  for (const file of ['envelope.txt', 'steer.txt']) {
    const path = \`$root/types/sheet/examples/\${name}/\${file}\`
    if (!existsSync(path)) continue
    const text = readFileSync(path, 'utf8')
    const blocks = blocksOf(text)
    const last = text.replace(/\n$/, '').split('\n').at(-1) ?? ''
    check(\`the published \${name}/\${file} holds one block, its last line\`, blocks.length === 1 && last.startsWith('<sheet-delivery>') && blocks[0]!.keys.length === blocks[0]!.answered.length + blocks[0]!.dismissed.length, blocks)
  }
}

// A start's search, for real (I9): the transcript holds a context row that delivered one of two answers, and a
// human's prompt quoting the other's envelope; the first lands, the other stays owed across the stop, and the context
// the SessionStart returns lists only it.
const sminos = (args: string[], input = '') => spawnSync('$root/skills/sminos/scripts/sminos', args, { input, encoding: 'utf8', env: { ...process.env, SMINOS_HOME: HOME } })
const S2 = '5eed0000-0000-4000-8000-00000000c3b2'
await sheetForTests.sessionStarted(port, 'startup', S2, '$work/none.jsonl')
const two = await call('toolu_b1', { ask: [{ question: 'First?' }, { question: 'Second?' }] })
check('two questions on the second sheet', 'result' in two && two.result.startsWith('Added q1, q2.'), two)
sminos(['sheet', 'put', '--session', S2, '--no-wait'], ['ka000001', 'kb000002'].map((key, i) => JSON.stringify({ v: 1, key, kind: 'answer', id: \`q\${i + 1}\`, revision: 1, text: \`answer \${i + 1}\`, by: 'cli' })).join('\n') + '\n')
await sheetForTests.drain(port, sheetForTests.sheet().gen!)
hops.splice(0)
const ready = sheetForTests.sheet().gen?.held?.ready[0]
check('the drain holds both in one envelope', ready?.keys.join() === 'ka000001,kb000002', ready)
const delivered = '<sheet-delivery>{"v":1,"keys":["ka000001"],"answered":[{"id":"q1","revision":1,"picks":[],"text":"answer 1","images":[]}],"dismissed":[]}</sheet-delivery>'
const quoted2 = '<sheet-delivery>{"v":1,"keys":["kb000002"],"answered":[{"id":"q2","revision":1,"picks":[],"text":"answer 2","images":[]}],"dismissed":[]}</sheet-delivery>'
writeFileSync('$work/s2.jsonl', [
  JSON.stringify({ type: 'attachment', attachment: { type: 'hook_additional_context', content: [\`[sheet v1] The human answered questions on your sheet.\nq1 "First?" → their text: "answer 1"\n\${delivered}\`], hookName: 'tool.call', hookEvent: 'PostToolUse' } }),
  JSON.stringify({ type: 'user', origin: { kind: 'composer' }, message: { role: 'user', content: \`[sheet v1] The human answered questions on your sheet.\n\${quoted2}\` } }),
].join('\n') + '\n')
const context = await sheetForTests.sessionStarted(port, 'resume', S2, '$work/s2.jsonl')
const s2 = JSON.parse(readFileSync(\`\${HOME}/sheet/\${S2}/state.json\`, 'utf8'))
check('the delivered answer landed; the quoted one is still owed, across the stop', s2.pending.map((o: { key: string }) => o.key).join() === 'kb000002' && s2.pending[0].acrossStop === true && s2.closed.q1?.deliveredAt !== undefined, s2.pending)
check("the start's context lists only what is still owed", typeof context === 'string' && context.includes('q2 (revision 1)') && !context.includes('q1 (revision 1)'), context)
check('nothing went by a route while the start searched', submitted.length === 0 && hops.length === 0, { submitted, hops: hops.length })

// The search prints compact evidence, a row's kind and keys, newest first and each key once: a recent row behind more
// than 4 MiB of older matches is its first line, and an output cut at 4 MiB still holds it. A human's prompt quoting a
// block, another hook's context and an invalid block name nothing.
const blockOf = (key: string, id: string) => \`<sheet-delivery>{"v":1,"keys":[\${key.split(',').map((k) => JSON.stringify(k)).join(',')}],"answered":[{"id":"\${id}","revision":1,"picks":[],"text":"\${'x'.repeat(300)}","images":[]}],"dismissed":[]}</sheet-delivery>\`
const head = '[sheet v1] The human answered questions on your sheet.'
const contextRow = (hookName: string, key: string) => JSON.stringify({ type: 'attachment', attachment: { type: 'hook_additional_context', content: ['another hook', \`\${head}\\n\${blockOf(key, 'q1')}\`], hookName } })
const olds = Array.from({ length: 12_000 }, (_, i) => contextRow(i % 2 === 0 ? 'tool.call' : 'prompt.submit', \`old-\${i}\`))
const envelopeText = \`\${head}\\n\${blockOf('recent-1', 'q2')}\`
const newer = [
  contextRow('tool.call', 'old-0'),
  JSON.stringify({ type: 'user', origin: { kind: 'composer' }, message: { role: 'user', content: \`\${head}\\n\${blockOf('quoted-1', 'q3')}\` } }),
  contextRow('SessionStart', 'session-1'),
  // Two keys for one answered entry: no block.
  contextRow('tool.call', 'bad,worse'),
  // This plugin's row whose stored content a hook beneath stripped of the block: its submission's record still holds
  // it, which the model never read.
  JSON.stringify({ type: 'user', origin: { kind: 'plugin', name: 'sminos' }, pluginPrompt: { name: 'sminos', text: \`\${head}\\n\${blockOf('stripped-1', 'q4')}\` }, message: { role: 'user', content: 'The sminos plugin sent a message:\\n[sheet v1] (rewritten)' } }),
  JSON.stringify({ type: 'user', origin: { kind: 'plugin', name: 'sminos' }, pluginPrompt: { name: 'sminos', text: envelopeText }, message: { role: 'user', content: \`The sminos plugin sent a message:\\n\${envelopeText}\\n\\nThis is how Claude Code surfaces a prompt a plugin submits between turns.\` } }),
]
writeFileSync('$work/big.jsonl', [...olds, ...newer].join('\n') + '\n')
const bigSize = statSync('$work/big.jsonl').size
const evidence = execFileSync(landedSearchArgs('$work/big.jsonl')[0] as string, landedSearchArgs('$work/big.jsonl').slice(1), { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
const evidenceLines = evidence.split('\n')
const allFound = searchedKeys(evidenceLines)
check('the transcript searched is past 4 MiB of older matches', bigSize > 4 * 1024 * 1024, bigSize)
check('the newest row is the first line, its kind and keys', evidenceLines[0] === '{"keys":["recent-1"],"kind":"plugin"}', evidenceLines.slice(0, 3))
check('a key is printed once, at its newest row', evidenceLines[1] === '{"keys":["old-0"],"kind":"tool.call"}' && allFound.filter((k) => k === 'old-0').length === 1 && allFound.length === 12_001, [evidenceLines[1], allFound.length])
check("a human's quote, another hook's context, an invalid block and a submission's record the stored content lost name nothing", !['quoted-1', 'session-1', 'bad', 'worse', 'stripped-1'].some((k) => allFound.includes(k)), allFound.slice(0, 5))
const onlyArgs = landedSearchArgs('$work/big.jsonl', ['old-7', 'recent-1', 'never-1'])
const onlyLines = execFileSync(onlyArgs[0] as string, onlyArgs.slice(1), { encoding: 'utf8' }).split('\n').filter((l) => l !== '')
check("given the start's complete \`before\`, the search prints those keys alone", JSON.stringify(searchedKeys(onlyLines)) === '["recent-1","old-7"]' && onlyLines.length === 2, onlyLines)
const cut = evidence.slice(0, 4096)
check('an output cut short still holds the newest rows', searchedKeys(cut.split('\n').slice(0, -1)).slice(0, 2).join() === 'recent-1,old-0', cut.slice(0, 120))
check('the evidence is compact: a small part of what it searched', evidence.length < bigSize / 10, [evidence.length, bigSize])
check('a transcript with no envelope exits 1', spawnSync('perl', landedSearchArgs('$work/none.jsonl').slice(1)).status === 1)

// A fresh answer after two hundred owed across a stop that fill an envelope: the composer packs it first, so the
// envelope the mod takes wakes and goes by the idle route, from the hop.
const S3 = '5eed0000-0000-4000-8000-00000000c3b3'
await sheetForTests.sessionStarted(port, 'startup', S3, '$work/none.jsonl')
for (let c = 0; c < 11; c++) {
  const n = c < 10 ? 20 : 1
  await call(\`toolu_c\${c}\`, { ask: Array.from({ length: n }, (_, i) => ({ question: \`Old \${c * 20 + i + 1}?\` })) })
}
for (let b = 0; b < 4; b++) {
  sminos(['sheet', 'put', '--session', S3, '--no-wait'], Array.from({ length: 50 }, (_, i) => JSON.stringify({ v: 1, key: \`old-\${String(b * 50 + i + 1).padStart(4, '0')}\`, kind: 'answer', id: \`q\${b * 50 + i + 1}\`, revision: 1, text: 'old', by: 'cli' })).join('\n') + '\n')
}
await sheetForTests.sessionStarted(port, 'resume', S3, '$work/none.jsonl')
hops.splice(0)
const owed = sheetForTests.sheet().gen?.held
check('two hundred owed across the stop, none of them waking', owed?.owedAcrossStop === 200 && owed.ready[0]?.wakes === false, owed && { owed: owed.owedAcrossStop, ready: owed.ready.map((r) => [r.keys.length, r.wakes]) })
sminos(['sheet', 'put', '--session', S3, '--no-wait'], JSON.stringify({ v: 1, key: 'fresh-0201', kind: 'answer', id: 'q201', revision: 1, text: 'fresh', by: 'cli' }) + '\n')
await sheetForTests.drain(port, sheetForTests.sheet().gen!)
const fresh = sheetForTests.sheet().gen?.held?.ready[0]
// Its keys stand in the order of the ids (I7): the fresh answer's, q201's, last.
check('the first envelope holds the fresh answer and wakes; more follows', fresh !== undefined && fresh.keys.includes('fresh-0201') && fresh.wakes && fresh.more && fresh.keys.length < 201, fresh && { last: fresh.keys.at(-1), n: fresh.keys.length, wakes: fresh.wakes, more: fresh.more })
check('the idle route waits for the hop', submitted.length === 0 && hops.length === 1, hops.length)
hops.splice(0).forEach((fn) => fn())
await new Promise((resolve) => setTimeout(resolve, 10))
check('from the hop, the idle route submits that envelope', submitted.length === 1 && submitted[0] === fresh?.text, submitted.map((t) => t.slice(0, 80)))

// M5: the result's parser on every published stored call (grammar/result.examples.json), and each draws a row.
const examples = JSON.parse(readFileSync('$root/types/sheet/grammar/result.examples.json', 'utf8')) as { input: Record<string, unknown>; result: string; parsed: unknown }[]
for (const [i, example] of examples.entries()) {
  const parsed = parseResult(example.result)
  check(\`the published stored call \${i + 1} parses as published\`, JSON.stringify(canonical(parsed)) === JSON.stringify(canonical(example.parsed)), [parsed, example.parsed])
  check(\`the published stored call \${i + 1} draws its row\`, parsed !== undefined && rowLines(example.input, parsed, { delivered: new Map() }).length > 0)
}

// M5: a resume's open asks of today's tool. The sheet's start reads the transcript itself, as the ask reads it
// (readTodayAsks), stages what it read, and the real step imports it once: an ask only today's tool accepts, kept as
// it was asked. A read that was not definite imports nothing, and the next start does. A copy never imports.
// Not definite: the transcript past what one read takes, so it is searched, and the asks' search fails (the floor's,
// which names the path alone, runs).
const searchFailing: Port = {
  ...port,
  size: async (path) => (path.endsWith('/today.jsonl') ? 5 * 1024 * 1024 : port.size(path)),
  exec: async (argv) => (argv[0] === 'grep' || argv.length > 5 ? { exitCode: 2, stdout: '', isStdoutTruncated: false } : port.exec(argv)),
}
const resumeWith = (session: string, path: string, isSearchFailing = false) => sheetForTests.sessionStarted(isSearchFailing ? searchFailing : port, 'resume', session, path)
const wide = { question: \`\${'Which port should the dev server use, given everything above? '.repeat(40)}Which?\`, header: 'Port', multiSelect: false, options: [{ label: 'L'.repeat(201), description: 'a' }, { label: 'B', description: 'b' }] }
writeFileSync('$work/today.jsonl', [
  { type: 'assistant', timestamp: '2026-11-20T08:00:00.000Z', uuid: 'a1', message: { role: 'assistant', content: [{ type: 'tool_use', id: 'toolu_today1', name: 'mcp__sminos__AskUserQuestion', input: { questions: [wide], async: true } }] } },
  { type: 'user', uuid: 'a2', parentUuid: 'a1', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'toolu_today1', content: ASYNC_RESULT }] } },
].map((row) => JSON.stringify(row)).join('\n') + '\n')
const stateOf = (session: string) => JSON.parse(readFileSync(\`\${HOME}/sheet/\${session}/state.json\`, 'utf8'))
const S4 = '5eed0000-0000-4000-8000-00000000c3b4'
const told = await resumeWith(S4, '$work/today.jsonl')
const s4 = stateOf(S4)
const imported = s4.questions[0]
check("a resume imports today's open ask, kept as it was asked", s4.questions.length === 1 && imported?.id === 'q1' && imported.question === wide.question && imported.options[0]?.label === wide.options[0]!.label && imported.askedAt === '2026-11-20T08:00:00.000Z' && JSON.stringify(imported.importedFrom) === '{"callId":"toolu_today1","index":0}' && JSON.stringify(s4.import.calls) === '{"toolu_today1":["q1"]}', s4.questions)
check('and the start tells the agent', typeof told === 'string' && told.includes('Moved onto the sheet from the earlier question tool: q1'), told)
for (const n of [2, 3]) {
  await resumeWith(S4, '$work/today.jsonl')
  const again = stateOf(S4)
  check(\`once: after resume \${n} it is still the one question\`, again.questions.length === 1 && again.nextId === 2, again.questions.map((q: { id: string }) => q.id))
}
const S5 = '5eed0000-0000-4000-8000-00000000c3b5'
await resumeWith(S5, '$work/today.jsonl', true)
check('a read that was not definite imports nothing and records nothing', stateOf(S5).questions.length === 0 && JSON.stringify(stateOf(S5).import.calls) === '{}', stateOf(S5).import)
await resumeWith(S5, '$work/today.jsonl')
check('the next start reads again, and imports', stateOf(S5).questions.length === 1 && stateOf(S5).import.calls.toolu_today1?.[0] === 'q1', stateOf(S5).import)
const S6 = '5eed0000-0000-4000-8000-00000000c3b6'
await sheetForTests.sessionStarted(port, 'fork', S6, '$work/today.jsonl')
await resumeWith(S6, '$work/today.jsonl')
await resumeWith(S6, '$work/today.jsonl')
check("a copy's sheet starts empty and stays empty", stateOf(S6).questions.length === 0 && stateOf(S6).import.never === true, stateOf(S6).import)

// The floor's search failing outright (exit 2) while the asks' read is whole: the asks go marked floorUnknown, and the
// real step imports them into a record that has assigned an id, and defers them, recording nothing, in one that
// has not; the next start, its floor known, imports.
const floorFailing: Port = {
  ...port,
  size: async (path) => (path.endsWith('/today.jsonl') ? 5 * 1024 * 1024 : port.size(path)),
  exec: async (argv) => (argv[0] === 'perl' && argv[1] === '-e' ? port.exec(argv) : { exitCode: 2, stdout: '', isStdoutTruncated: false }),
}
const S8 = '5eed0000-0000-4000-8000-00000000c3b8'
await sheetForTests.sessionStarted(port, 'startup', S8, '$work/none.jsonl')
await call('toolu_s8a', { ask: [{ question: 'Asked here first?' }] })
await sheetForTests.sessionStarted(floorFailing, 'resume', S8, '$work/today.jsonl')
check('floor unknown, a record that assigned an id imports past it', stateOf(S8).questions.map((q: { id: string }) => q.id).join() === 'q1,q2' && stateOf(S8).import.calls.toolu_today1?.[0] === 'q2', { questions: stateOf(S8).questions.map((q: { id: string }) => q.id), import: stateOf(S8).import })
const S9 = '5eed0000-0000-4000-8000-00000000c3b9'
await sheetForTests.sessionStarted(floorFailing, 'resume', S9, '$work/today.jsonl')
check('floor unknown, a record that assigned none imports nothing and records nothing', stateOf(S9).questions.length === 0 && JSON.stringify(stateOf(S9).import.calls) === '{}' && stateOf(S9).nextId === 1, stateOf(S9))
await resumeWith(S9, '$work/today.jsonl')
check('and the next start, its floor known, imports', stateOf(S9).import.calls.toolu_today1?.[0] === 'q1', stateOf(S9).import)

// A history whose rows the floor reads run past 4 MiB (what one read takes, and what a program's output is cut at):
// the search prints its floor in a few bytes, so the floor is found, and the open ask of today's tool is imported
// past it. Its envelopes are what grow it; the asks' search (the tool's calls, today's results) stays small.
const longAnswer = 'a long answer '.repeat(400)
const history: string[] = []
for (let n = 1; n <= 700; n++) {
  history.push(JSON.stringify(sheetCall(\`toolu_h\${n}\`)), JSON.stringify(sheetResult(\`toolu_h\${n}\`, \`Added q\${n}.\`)))
  history.push(JSON.stringify({ type: 'attachment', attachment: { type: 'hook_additional_context', hookName: 'tool.call', content: [\`[sheet v1] The human answered questions on your sheet.\nq\${n} → their text: "\${longAnswer}"\n<sheet-delivery>\${JSON.stringify({ v: 1, keys: [\`h\${n}\`], answered: [{ id: \`q\${n}\`, revision: 1, picks: [], text: longAnswer, images: [] }], dismissed: [] })}</sheet-delivery>\`] } }))
}
writeFileSync('$work/long.jsonl', [...history, ...readFileSync('$work/today.jsonl', 'utf8').trimEnd().split('\n')].join('\n') + '\n')
const matching = readFileSync('$work/long.jsonl', 'utf8').split('\n').filter((line) => /(?:Added|Revised|Withdrew) q[1-9]|<sheet-delivery>|\[sheet v1\]|"name":"mcp__sminos__AskUserQuestion"/.test(line))
const longSearch = floorSearched('$work/long.jsonl')
check('the rows the floor reads run past 4 MiB; the search prints a few bytes and the floor a whole read gives', Buffer.byteLength(matching.join('\n')) > CAP && longSearch.bytes < 64 && longSearch.floor === 700, { bytes: Buffer.byteLength(matching.join('\n')), longSearch })
const S7 = '5eed0000-0000-4000-8000-00000000c3b7'
await resumeWith(S7, '$work/long.jsonl')
const s7 = stateOf(S7)
check('so a resume of it imports the open ask, its id past the floor', s7.questions.length === 1 && s7.questions[0]?.id === 'q701' && s7.import.calls.toolu_today1?.[0] === 'q701', { questions: s7.questions.map((q: { id: string }) => q.id), import: s7.import, logs: logs.filter((line) => line.includes('floor') || line.includes('today')).slice(-4) })

// M5: the published steer (X3: a user row whose text is an envelope) draws its receipts, read for drawing alone;
// landing reads routes' blocks only.
const steer = readFileSync('$root/types/sheet/examples/terminal/steer.txt', 'utf8')
const steerRow = [{ role: 'user', content: [{ type: 'text', text: steer }] }]
check("the published steer's block draws receipts: q7, q8, q12 answered, q9, q11 dismissed", JSON.stringify([...deliveriesHeld(steerRow)]) === JSON.stringify([
  ['q7', { how: 'answered', revision: 2, picks: [1, 2], text: 'passkeys only on mobile' }],
  ['q8', { how: 'answered', revision: 1, picks: [], text: 'Nothing waiting for you.' }],
  ['q12', { how: 'answered', revision: 1, picks: [1], text: '' }],
  ['q9', { how: 'dismissed' }],
  ['q11', { how: 'dismissed' }],
]), [...deliveriesHeld(steerRow)])
check('and settles nothing: no key of it is held as landed', heldKeys(steerRow).size === 0, [...heldKeys(steerRow)])

// M5: the registrations the band reads between steps, against the command's own reading of them (I8): the same
// surface, mawsd first, then by name; a temporary file, a half-written one and a stale one passed over.
const surfaces = \`\${HOME}/sheet/surfaces\`
mkdirSync(surfaces, { recursive: true })
const beat = (ageMs: number) => new Date(Date.now() - ageMs).toISOString()
const register = (file: string, name: string, ageMs: number, reach = 'local') =>
  writeFileSync(\`\${surfaces}/\${file}\`, JSON.stringify({ v: 1, name, pid: process.pid, url: \`http://\${name}.localhost:47590/\`, reach, heartbeatAt: beat(ageMs) }))
register('zeta.json', 'zeta', 1000)
register('alpha.json', 'alpha', 1000)
register('mawsd.json', 'mawsd', 1000)
register('old.json', 'aaa', 60_000)
register('.mawsd.tmp', 'aa', 1000)
writeFileSync(\`\${surfaces}/half.json\`, '{"v":1,"na')
const theirs = () => {
  const listed = JSON.parse(sminos(['sheet', 'surfaces', '--json']).stdout).surfaces as { name: string; url: string; reach: string; alive: boolean }[]
  const first = listed.find((r) => r.alive && r.reach === 'local')
  return first === undefined ? null : { name: first.name, url: first.url, reach: first.reach }
}
const ours = () => surfaceOf(readdirSync(surfaces).map((file) => ({ file, text: readFileSync(\`\${surfaces}/\${file}\`, 'utf8') })), Date.now(), false)
check("the band's reading is the command's: mawsd first", JSON.stringify(ours()) === JSON.stringify(theirs()) && ours()?.name === 'mawsd' && ours()?.url === 'http://mawsd.localhost:47590', [ours(), theirs()])
rmSync(\`\${surfaces}/mawsd.json\`)
check("the band's reading is the command's: then by name", JSON.stringify(ours()) === JSON.stringify(theirs()) && ours()?.name === 'alpha', [ours(), theirs()])

// M6: the ask snapshot a session under the sheet writes (I13), from the real step's views: an answer raises its count
// and lists the question with the human's answer as the envelope words it; a dismissal does neither. The steps that
// owe the project log order its projection, run for real: in no project here, it writes nothing, and the record keeps
// all it owes.
const SR = '5eed0000-0000-4000-8000-00000000c3c0'
await sheetForTests.sessionStarted(port, 'startup', SR, '$work/none.jsonl')
const logRuns = () => ran.filter((r) => r === \`sheet log --session \${SR}\`).length
await call('toolu_r1', { ask: [{ question: 'Ship today?', header: 'Ship', options: [{ label: 'Yes' }, { label: 'No' }] }, { question: 'Rename it?' }] })
const last = () => snapshots.at(-1)
check('the snapshot lists the two open, nothing answered', last()?.answered === 0 && last()?.sheet?.open.map((q) => q.id).join() === 'q1,q2' && last()?.asks.length === 0, last())
const putR = (line: Record<string, unknown>) => sminos(['sheet', 'put', '--session', SR, '--no-wait'], JSON.stringify({ v: 1, by: 'cli', ...line }) + '\n')
putR({ key: 'kr000001', kind: 'answer', id: 'q1', revision: 1, picks: ['Yes'], text: 'after the review' })
await sheetForTests.drain(port, sheetForTests.sheet().gen!)
hops.splice(0)
check('an answer: counted, and listed as an answered ask with the real answer', JSON.stringify(last()?.asks) === JSON.stringify([
  { id: 'sheet:q1', questions: [{ question: 'Ship today?', header: 'Ship', options: [], multiSelect: false }], status: 'answered', answer: '"Ship today?" → Yes. Their text: "after the review"' },
]) && last()?.answered === 1 && last()?.sheet?.owed === 1 && last()?.sheet?.open.map((q) => q.id).join() === 'q2', last())
putR({ key: 'kr000002', kind: 'dismiss', id: 'q2' })
await sheetForTests.drain(port, sheetForTests.sheet().gen!)
hops.splice(0)
check('a dismissal: no answer, not counted', last()?.answered === 1 && last()?.asks.length === 1 && last()?.sheet?.open.length === 0 && last()?.sheet?.owed === 2, last())
await new Promise((resolve) => setTimeout(resolve, 50))
const sr = JSON.parse(readFileSync(\`\${HOME}/sheet/\${SR}/state.json\`, 'utf8'))
check('each step that owed the log ordered its projection; in no project it wrote nothing, and all four are owed', logRuns() >= 2 && sr.log.owed.map((e: { kind: string }) => e.kind).join() === 'question,question,answered,answered', { runs: logRuns(), owed: sr.log.owed })

process.exit(failed === 0 ? 0 : 1)
TS

cd "$work" && bun run check.ts
echo "sheet step: all checks passed"
