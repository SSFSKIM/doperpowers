import { describe, expect, test, tier } from 'claude-code/testing'

import type { SheetKept } from '../../types/sminos'
import {
  DESCRIPTION,
  FIELD_DESCRIPTIONS,
  INPUT_SCHEMA,
  NOT_KNOWN,
  SHEET_TOOL,
  WITHDRAWN,
  announcement,
  answerOf,
  blocksOf,
  capturedOf,
  checkRefusal,
  chooseStart,
  endedNotice,
  entryProblem,
  floorOfLines,
  floorOfMessages,
  floorOfResult,
  floorOfSheetText,
  floorOfRows,
  sheetTextOf,
  foreclosedResult,
  hasSubagent,
  heldKeys,
  isNewer,
  isRouteRow,
  outcomeNotice,
  readInput,
  searchedKeys,
  settingOf,
  storedKeys,
  unreadClause,
  validateCall,
} from '../../hooks/mods/sheet-model'
import type { ChoiceEnv, ChoiceReads, Probe, View } from '../../hooks/mods/sheet-model'

tier('user')

const HEAD = 'InputValidationError: AskUserQuestion failed due to the following issue:\n'
const HEADS = 'InputValidationError: AskUserQuestion failed due to the following issues:\n'
const Q = (question: string, rest: Record<string, unknown> = {}) => ({ question, ...rest })

describe('the setting', () => {
  test('on for 1, true, on, yes and off for 0, false, off, no, in any case; unset or another word is the default, off', async () => {
    for (const word of ['1', 'true', 'ON', 'Yes', ' on ']) expect(settingOf(word)).toEqual({ isOn: true })
    for (const word of ['0', 'False', 'off', 'NO']) expect(settingOf(word)).toEqual({ isOn: false })
    expect(settingOf(undefined)).toEqual({ isOn: false })
    expect(settingOf('')).toEqual({ isOn: false })
    expect(settingOf('maybe')).toEqual({ isOn: false, isUnknown: true })
  })
})

describe('the tool as the model reads it', () => {
  test('the description is C1\'s description-v3, four paragraphs; the built-in is withdrawn naming the tool', async () => {
    expect(DESCRIPTION.split('\n\n')).toHaveLength(4)
    expect(DESCRIPTION.startsWith("Put questions for the human on this session's question sheet.")).toBe(true)
    expect(DESCRIPTION).toContain('\n\nAsk when a question comes up, then keep working.\n\n')
    expect(WITHDRAWN).toBe("Withdrawn in this session: ask through mcp__sminos__AskUserQuestion, which puts your questions on the session's sheet.")
  })

  test("every property carries C1's description for its field but a reference's path and lines, which C1 gives none", async () => {
    const defs = INPUT_SCHEMA.$defs as Record<string, { properties: Record<string, { description?: string }> }>
    const top = INPUT_SCHEMA.properties as Record<string, { description?: string }>
    expect(top.ask?.description).toBe(FIELD_DESCRIPTIONS.ask)
    expect(top.withdraw?.description).toBe(FIELD_DESCRIPTIONS.withdraw)
    for (const [name, property] of Object.entries(defs.entry!.properties)) {
      expect(property.description).toBe(FIELD_DESCRIPTIONS[name as keyof typeof FIELD_DESCRIPTIONS])
    }
    for (const [name, property] of Object.entries(defs.option!.properties)) {
      expect(property.description).toBe(FIELD_DESCRIPTIONS[name as keyof typeof FIELD_DESCRIPTIONS])
    }
    expect(Object.values(defs.reference!.properties).map((p) => p.description)).toEqual([undefined, undefined])
  })
})

describe('validateCall: the whole call (I6)', () => {
  test('a call that passes is undefined, a preview on a multi-select question included: the schema does not state that rule', async () => {
    expect(validateCall({ ask: [Q('Which?', { options: [{ label: 'A', preview: 'p' }, { label: 'B' }], multiSelect: true })] })).toBeUndefined()
    expect(validateCall({ withdraw: ['q3'] })).toBeUndefined()
    expect(validateCall({ ask: [Q('Revise?', { id: 'q999999999' })], withdraw: ['q1'] })).toBeUndefined()
  })

  test('neither ask nor withdraw; an id named twice, across both or within one', async () => {
    expect(validateCall({})).toBe(`${HEAD}The input is invalid: a call puts at least one entry in \`ask\` or one id in \`withdraw\``)
    expect(validateCall({ ask: [Q('a', { id: 'q3' })], withdraw: ['q3'] })).toBe(
      `${HEAD}The input is invalid: q3 is named more than once across \`ask\` and \`withdraw\`; a call names an id at most once`,
    )
    expect(validateCall({ withdraw: ['q2', 'q2'] })).toContain('q2 is named more than once')
  })

  test('each kind of issue a line, the missing, unknown and mistyped first, in the words of today\'s tool', async () => {
    const text = validateCall({ extra: 1, ask: [{ header: 7, options: [{ label: '' }], references: [{ path: 'a', lines: [1, 2.5] }] }] })
    expect(text).toBe(
      HEADS +
        [
          'The required parameter `ask[0].question` is missing',
          'An unexpected parameter `extra` was provided',
          'The parameter `ask[0].header` type is expected as `string` but provided as `number`',
          'The parameter `ask[0].references[0].lines[1]` type is expected as `integer` but provided as `number`',
          'The parameter `ask[0].options[0].label` is invalid: Too small: expected string to have >=1 characters',
        ].join('\n'),
    )
  })

  test('the bounds of §1, counted in code points (K5)', async () => {
    const astral = '😀'
    expect(validateCall({ ask: [Q(astral.repeat(2000))] })).toBeUndefined()
    expect(validateCall({ ask: [Q('x'.repeat(2001))] })).toBe(`${HEAD}The parameter \`ask[0].question\` is invalid: Too big: expected string to have <=2000 characters`)
    expect(validateCall({ ask: [Q('a', { header: 'h'.repeat(61) })] })).toContain('`ask[0].header` is invalid: Too big')
    expect(validateCall({ ask: [Q('a', { context: 'c'.repeat(8001) })] })).toContain('`ask[0].context` is invalid: Too big')
    expect(validateCall({ ask: [Q('a', { options: Array.from({ length: 13 }, (_, i) => ({ label: `o${i}` })) })] })).toContain('expected array to have <=12 items')
    expect(validateCall({ ask: [Q('a', { options: [{ label: 'l'.repeat(201) }] })] })).toContain('`ask[0].options[0].label` is invalid: Too big')
    expect(validateCall({ ask: [Q('a', { options: [{ label: 'l', description: 'd'.repeat(501) }] })] })).toContain('`ask[0].options[0].description` is invalid')
    expect(validateCall({ ask: [Q('a', { options: [{ label: 'l', preview: 'p'.repeat(8001) }] })] })).toContain('`ask[0].options[0].preview` is invalid')
    expect(validateCall({ ask: [Q('a', { references: Array.from({ length: 9 }, () => ({ path: 'p' })) })] })).toContain('expected array to have <=8 items')
    expect(validateCall({ ask: [Q('a', { references: [{ path: 'p', lines: [1] }] })] })).toContain('expected array to have >=2 items')
    expect(validateCall({ ask: Array.from({ length: 21 }, (_, i) => Q(`q${i}`)) })).toContain('`ask` is invalid: Too big: expected array to have <=20 items')
    expect(validateCall({ ask: [] })).toContain('`ask` is invalid: Too small: expected array to have >=1 items')
    expect(validateCall({ withdraw: [] })).toContain('`withdraw` is invalid: Too small')
    expect(validateCall({ ask: [Q('')] })).toContain('`ask[0].question` is invalid: Too small')
  })

  test('an id is q and one to nine digits, no leading zero', async () => {
    for (const id of ['q0', 'q01', 'x1', 'q1234567890', 'q1\n']) {
      expect(validateCall({ withdraw: [id] })).toContain('`withdraw[0]` is invalid: Invalid string: must match pattern /^q[1-9][0-9]{0,8}$/')
    }
    expect(validateCall({ ask: [Q('a', { id: 3 })] })).toContain('`ask[0].id` type is expected as `string` but provided as `number`')
  })

  test('input that is no object, and past twenty issues the rest counted', async () => {
    expect(validateCall('ask')).toBe(`${HEAD}The input type is expected as \`object\` but provided as \`string\``)
    const many = validateCall({ ask: Array.from({ length: 20 }, () => ({ header: 1, multiSelect: 'x' })) }) ?? ''
    expect(many.split('\n').length).toBe(22)
    expect(many.endsWith('(40 more issues not listed)')).toBe(true)
  })
})

describe("entryProblem: an entry's own rules (U14), in the step's words", () => {
  test('each rule refuses with its clause; a good entry has none', async () => {
    expect(entryProblem(Q('a', { options: [{ label: 'X' }, { label: 'X' }] }))).toBe('two options share the label "X"')
    expect(entryProblem(Q('a', { multiSelect: true, options: [{ label: 'X', preview: 'p' }] }))).toBe("an option's preview needs a single-select question")
    expect(entryProblem(Q('a', { multiSelect: true }))).toBe('multiSelect needs options')
    expect(entryProblem(Q('a', { references: [{ path: 'p', lines: [5, 4] }] }))).toBe('lines must be [a, b] with 1 <= a <= b')
    expect(entryProblem(Q('a', { references: [{ path: 'p', lines: [0, 4] }] }))).toBe('lines must be [a, b] with 1 <= a <= b')
    expect(entryProblem(Q('a\ud800b'))).toBe('a string holds a lone UTF-16 surrogate')
    expect(entryProblem(Q('a', { options: [{ label: '😀' }, { label: 'b' }], references: [{ path: 'p', lines: [3, 3] }] }))).toBeUndefined()
  })

  test('a lone surrogate first; a shared label cut at 200 characters', async () => {
    expect(entryProblem(Q('a', { header: '\udc00', multiSelect: true }))).toBe('a string holds a lone UTF-16 surrogate')
    const long = 'L'.repeat(250)
    expect(entryProblem(Q('a', { options: [{ label: long }, { label: long }] }))).toBe(`two options share the label "${'L'.repeat(200)}"`)
  })
})

describe('a reference read (C0\'s P3)', () => {
  test("Read's input: the path under the working directory, the range as offset and limit", async () => {
    expect(readInput({ path: 'src/a.ts' }, '/work/')).toEqual({ file_path: '/work/src/a.ts' })
    expect(readInput({ path: '/abs/a.ts', lines: [40, 80] }, '/work')).toEqual({ file_path: '/abs/a.ts', offset: 40, limit: 41 })
  })

  test("a text's content with Read's lines; an image's base64 and type", async () => {
    expect(capturedOf({ result: { type: 'text', file: { filePath: '/w/a', content: 'one\n', numLines: 1, startLine: 1, totalLines: 1 } }, text: '1\tone' })).toEqual({
      ok: true,
      kind: 'text',
      body: 'one\n',
      startLine: 1,
      numLines: 1,
      totalLines: 1,
    })
    expect(capturedOf({ result: { type: 'image', file: { base64: 'iVBOR', type: 'image/png', originalSize: 9 } }, text: '' })).toEqual({ ok: true, kind: 'image', body: 'iVBOR', mediaType: 'image/png' })
  })

  test("a deny, an error and anything else Read returns refuse with the engine's words", async () => {
    expect(capturedOf({ deny: 'denied by a guard' })).toEqual({ ok: false, reason: 'denied by a guard' })
    expect(capturedOf({ isError: true, result: 'x', text: 'File does not exist. Note: …' })).toEqual({ ok: false, reason: 'File does not exist. Note: …' })
    expect(capturedOf({ result: { type: 'file_unchanged', file: { filePath: '/w/a' } }, text: 'File unchanged since last read.' })).toEqual({ ok: false, reason: 'File unchanged since last read.' })
    expect(capturedOf({ result: { type: 'notebook', file: {} } })).toEqual({ ok: false, reason: 'Read returned a notebook result, which the sheet does not keep' })
    const huge = 'A'.repeat(4 * 1024 * 1024 + 1)
    expect(capturedOf({ result: { type: 'image', file: { base64: huge, type: 'image/png' } } })).toMatchObject({ ok: false })
  })

  test("the check's verdict: only allow reads; any other names its reason", async () => {
    expect(checkRefusal({ decision: 'allow' })).toBeUndefined()
    expect(checkRefusal({ decision: 'deny', reason: 'Permission to read .env has been denied.' })).toBe('Permission to read .env has been denied.')
    expect(checkRefusal({ decision: 'ask', reason: "Claude requested permissions to read from /x, but you haven't granted it yet." })).toContain('requested permissions')
    expect(checkRefusal({ decision: 'ask' })).toBe('the permission check answered ask')
    expect(unreadClause('p'.repeat(250), 'why')).toBe(`the reference ${'p'.repeat(200)}… could not be read: why`)
  })
})

describe('results the mod writes', () => {
  test("a foreclosed call's, and an outcome not known (I6)", async () => {
    expect(foreclosedResult('the lock was not had in 10 s')).toBe('Nothing done.\nNot done: the sheet could not be written (the lock was not had in 10 s); call again.')
    expect(NOT_KNOWN).toBe('Outcome not known yet.\nThe sheet did not answer. Do not repeat this call: what it did will be told to you.')
  })

  test("the notice once a later settle answers: the result's first line, or that nothing changed (I9)", async () => {
    expect(outcomeNotice('toolu_1', { result: 'Added q4.\nNo surface can show these questions right now; they wait on the sheet and show when one returns.' })).toBe(
      '[sheet v1] Your earlier call (toolu_1) did change the sheet: Added q4.',
    )
    expect(outcomeNotice('toolu_1', { result: 'Nothing done.\nNot done: entry 1, multiSelect needs options.' })).toBe(
      '[sheet v1] Your earlier call (toolu_1) changed nothing; call again if you still need it.',
    )
    expect(outcomeNotice('toolu_1', { foreclosed: true })).toContain('changed nothing')
  })

  test('the person is told the first question a call added, with how many more', async () => {
    const input = { ask: [Q('Revise?', { id: 'q1' }), Q('First new?'), Q('Second new?')] }
    expect(announcement(input, 'Added q2, q3. Revised q1 (revision 2).')).toBe('First new? (+1 more)')
    expect(announcement(input, 'Added q2 (entry 3). Revised q1 (entry 1, revision 2).\nNot done: entry 2, multiSelect needs options.')).toBe('Second new?')
    expect(announcement(input, 'Revised q1 (revision 2).')).toBeUndefined()
    expect(announcement({ withdraw: ['q1'] }, 'Withdrew q1.')).toBeUndefined()
  })
})

const view = (over: Partial<View> = {}): View => ({
  seq: 1,
  offset: 0,
  nextId: 1,
  open: [],
  pending: [],
  pendingCount: 0,
  owedAcrossStop: 0,
  closed: {},
  answered: [],
  answeredCount: 0,
  ready: [],
  surface: null,
  surfaces: 0,
  ...over,
})

describe('views in the record\'s order', () => {
  test('a view of a lower seq, or of another session, is not adopted over the one held', async () => {
    const held = { session: 's', view: view({ seq: 5 }) }
    expect(isNewer(undefined, 's', view({ seq: 1 }))).toBe(true)
    expect(isNewer(held, 's', view({ seq: 4 }))).toBe(false)
    expect(isNewer(held, 's', view({ seq: 5 }))).toBe(true)
    expect(isNewer(held, 's', view({ seq: 9 }))).toBe(true)
    expect(isNewer(held, 'other', view({ seq: 1 }))).toBe(true)
  })

  test("a subagent's question or outcome in the view", async () => {
    expect(hasSubagent(undefined)).toBe(false)
    expect(hasSubagent(view({ open: [{ id: 'q1', revision: 1, asker: 'main', question: 'a', askedAt: 't' }] }))).toBe(false)
    expect(hasSubagent(view({ open: [{ id: 'q1', revision: 1, asker: { agentId: 'a1', name: 'r' }, question: 'a', askedAt: 't' }] }))).toBe(true)
    expect(hasSubagent(view({ pending: [{ key: 'k', id: 'q1', kind: 'answer', recipient: { agentId: 'a1' }, taken: true, acrossStop: false }] }))).toBe(true)
  })

  test("a step's answer: ok with its view, a refusal with its code, anything else none", async () => {
    expect(answerOf(JSON.stringify({ ok: true, seq: 2, view: view(), effects: { applied: [] } }))).toMatchObject({ ok: true, seq: 2 })
    expect(answerOf('{"ok": false, "code": "busy", "error": "the lock"}')).toEqual({ ok: false, code: 'busy', error: 'the lock' })
    expect(answerOf('Traceback (most recent call last)')).toBeUndefined()
    expect(answerOf('{"ok": true}')).toBeUndefined()
  })
})

describe('the floor (I10)', () => {
  test("a call's result names its ids on its first line", async () => {
    expect(floorOfResult('Added q7, q8. Revised q3 (revision 2). Withdrew q12.')).toBe(12)
    expect(floorOfResult('Added q2 (entry 3).\nNot done: entry 1, q40 is not open (never asked).')).toBe(2)
    expect(floorOfResult('Nothing done.')).toBe(0)
  })

  test("the sheet's texts: a block, the New ids sentence where M2's step writes it (n − 1), a late outcome's notice", async () => {
    const block = '<sheet-delivery>{"v":1,"keys":["k1"],"answered":[{"id":"q9","revision":1,"picks":[],"text":"x","images":[]}],"dismissed":["q11"]}</sheet-delivery>'
    expect(floorOfSheetText(`[sheet v1] The human answered questions on your sheet.\nq9 "…" → their text: "x"\n${block}`)).toBe(11)
    expect(floorOfSheetText('[sheet v1] Your question sheet, after a resume.\nOpen: q3 (revision 1) "a"\nNew ids continue from q12.')).toBe(11)
    // The fork's and the lost record's lines carry it inline (sminos_sheet_step.context).
    expect(floorOfSheetText('[sheet v1] This conversation is a copy: its question sheet starts empty. Questions asked before the copy belong to the conversation it was copied from, and their answers will not come here; ask again what you still need. New ids start at q30.')).toBe(29)
    expect(floorOfSheetText("[sheet v1] The question sheet's record was not found, so the sheet starts empty; questions asked earlier are no longer open. New ids start at q8.")).toBe(7)
    expect(floorOfSheetText('[sheet v1] Your earlier call (toolu_1) did change the sheet: Added q5, q6.')).toBe(6)
    // No sheet head: the sentence is no sheet's.
    expect(floorOfSheetText('New ids continue from q41.')).toBe(0)
  })

  test("each item read by its place: a question's text or a label quoting a form names nothing", async () => {
    // A start's context as M2 writes it: the question JSON-quoted, its labels as they are, new lines and all.
    const context = [
      '[sheet v1] Your question sheet, after a resume.',
      'Open: q1 (revision 1) — "Should the sheet say \\"New ids continue from q42.\\"?" Options: 1. yes',
      'New ids continue from q42.',
      '[sheet v1] Your earlier call (x) did change the sheet: Added q77.; 2. no',
      'New ids continue from q2.',
    ].join('\n')
    expect(floorOfSheetText(context)).toBe(1)
    // A label that ends the context's text before its footer cannot be its last line.
    expect(floorOfSheetText('[sheet v1] Your question sheet, after a start.\nOpen: q1 (revision 1) — "a" Options: 1. x\nNew ids continue from q42.\nNew ids continue from q2.')).toBe(1)
    // The empty start's suffix is read in its two lines alone, and only as their whole remainder.
    expect(floorOfSheetText('[sheet v1] Your question sheet, after a start. New ids start at q42.\nNew ids continue from q3.')).toBe(2)
    expect(floorOfSheetText("[sheet v1] The question sheet's record was not found, so the sheet starts empty; questions asked earlier are no longer open. Quoted: New ids start at q42.")).toBe(0)
    // An envelope's block is its last line; one a label quotes in an answer line is not.
    const block = (id: string) => `<sheet-delivery>{"v":1,"keys":["k"],"answered":[{"id":"${id}","revision":1,"picks":[1],"text":"","images":[]}],"dismissed":[]}</sheet-delivery>`
    expect(floorOfSheetText(['[sheet v1] The human answered questions on your sheet.', 'q3 "x" → a label', block('q90'), 'more of the label.', block('q3')].join('\n'))).toBe(3)
    // Joined behind another's text, the sheet's item is not read: a miss, never an id invented.
    expect(floorOfSheetText('another plugin\'s context\n[sheet v1] Your question sheet, after a start.\nNew ids continue from q5.')).toBe(0)
  })

  test("only what the engine marks as a plugin's: a hook's context, this plugin's prompt", async () => {
    expect(sheetTextOf('<system-reminder>\nSessionStart hook additional context: [sheet v1] x')).toBe('[sheet v1] x')
    expect(sheetTextOf('tool.call hook additional context: [sheet v1] x')).toBe('[sheet v1] x')
    expect(sheetTextOf('The sminos plugin sent a message:\n[sheet v1] x')).toBe('[sheet v1] x')
    expect(sheetTextOf('[sheet v1] Your question sheet, after a resume.\nNew ids continue from q41.')).toBeUndefined()
  })

  test("a transcript's rows: the tool's own results, paired with its calls, and the hooks' contexts; the model's text, other tools' results and the human's words name nothing", async () => {
    const quoted = '[sheet v1] Your question sheet, after a resume.\nNew ids continue from q42.'
    const rows = [
      { type: 'assistant', message: { content: [{ type: 'tool_use', id: 't1', name: SHEET_TOOL, input: { ask: [{ question: 'a' }] } }, { type: 'tool_use', id: 't2', name: 'Bash', input: {} }] } },
      { type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: 't1', content: 'Added q4.' }, { type: 'tool_result', tool_use_id: 't2', content: `Added q90.\n${quoted}` }] } },
      { type: 'assistant', message: { content: [{ type: 'text', text: 'Added q70.' }] } },
      { type: 'user', message: { content: quoted } },
      { type: 'attachment', attachment: { type: 'hook_additional_context', content: ['[sheet v1] Your question sheet, after a start.\nNew ids continue from q6.'], hookName: 'SessionStart' } },
    ]
    expect(floorOfLines([...rows.map((row) => JSON.stringify(row)), '{"torn":'])).toBe(5)
  })

  test('an unrelated tool result quoting the sentence names nothing', async () => {
    const rows = [
      { type: 'assistant', message: { content: [{ type: 'tool_use', id: 't9', name: 'Read', input: {} }] } },
      { type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: 't9', content: [{ type: 'text', text: '[sheet v1] This conversation is a copy: its question sheet starts empty. New ids start at q42.' }] }] } },
    ]
    expect(floorOfRows(rows)).toBe(0)
    expect(floorOfMessages([], [{ role: 'user', content: rows[1]?.message.content }])).toBe(0)
  })

  test('the conversation the engine holds: results of the tool, the contexts in the api form', async () => {
    const messages = [
      { role: 'assistant', text: '', toolUses: [{ tool: SHEET_TOOL, text: 'Added q3.' }, { tool: 'Bash', text: 'Added q50.' }] },
      { role: 'user', text: '[sheet v1] see q80\nNew ids continue from q81.', toolUses: [] },
    ]
    expect(floorOfMessages(messages, [])).toBe(3)
    const api = [
      { role: 'system', content: 'SessionStart hook additional context: [sheet v1] Your question sheet, after a resume.\nNew ids continue from q7.' },
      { role: 'assistant', content: [{ type: 'tool_use', id: 'u1', name: 'Bash', input: {} }] },
      { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'u1', content: [{ type: 'text', text: 'ok' }, { type: 'text', text: '<system-reminder>\ntool.call hook additional context: [sheet v1] Your question sheet, after a compaction.\nNew ids continue from q9.\n</system-reminder>' }] }] },
    ]
    expect(floorOfMessages(messages, api)).toBe(8)
  })
})

/** Reads for the choice whose every read is counted, so a test sees what the choice asked for. */
function reads(over: Partial<Omit<ChoiceReads, 'env'>> & { env?: Partial<Record<ChoiceEnv, string>>; record?: boolean; probed?: Probe } = {}) {
  const asked: string[] = []
  const r: ChoiceReads = {
    kept: over.kept,
    hasKeptAsk: over.hasKeptAsk ?? false,
    session: over.session ?? 'S1',
    isInteractive: over.isInteractive ?? true,
    env: Object.fromEntries(
      (['SMNS_INTERNAL', 'MAWS_QUESTION_SHEET', 'MAWS_NATIVE_TO_HUMAN', 'SSH_CONNECTION', 'SMINOS_QUESTION_SHEET'] as ChoiceEnv[]).map((name) => [
        name,
        async () => (asked.push(name), over.env?.[name]),
      ]),
    ) as ChoiceReads['env'],
    hasRecord: async () => (asked.push('record'), over.record ?? false),
    probe: async (remote) => (asked.push(remote ? 'probe --remote' : 'probe'), over.probed),
  }
  return { r, asked }
}
const ALIVE: Probe = { record: false, open: 0, pending: 0, queued: 0, surface: { name: 'standin', url: 'http://sheet.localhost:47590', reach: 'local' }, surfaces: 1 }
const NONE: Probe = { ...ALIVE, surface: null, surfaces: 0 }

describe("the start choice: I8's table, row by row", () => {
  test('a kept choice is the choice, whatever else holds', async () => {
    const kept: SheetKept = { shape: 1, choice: 'sheet', runner: 'terminal', session: 'S1' }
    const { r, asked } = reads({ kept, env: { SMINOS_QUESTION_SHEET: '0' } })
    expect(await chooseStart(r)).toEqual({ choice: 'sheet', runner: 'terminal', why: 'kept' })
    expect(asked).toEqual([])
    expect((await chooseStart(reads({ kept: { shape: 1, choice: 'today', session: 'S1' }, env: { SMINOS_QUESTION_SHEET: '1' }, probed: ALIVE }).r)).choice).toBe('today')
  })

  test('no kept choice and a kept ask snapshot: today', async () => {
    expect(await chooseStart(reads({ hasKeptAsk: true, env: { SMINOS_QUESTION_SHEET: '1' }, probed: ALIVE }).r)).toMatchObject({ choice: 'today' })
  })

  test('an internal session: none', async () => {
    expect(await chooseStart(reads({ env: { SMNS_INTERNAL: '1', SMINOS_QUESTION_SHEET: '1' }, probed: ALIVE }).r)).toMatchObject({ choice: 'none' })
  })

  test("MAWS's proof: the variable equal to the session's id is the sheet, run by MAWS; another id is no proof, said in the debug log", async () => {
    expect(await chooseStart(reads({ env: { MAWS_QUESTION_SHEET: 'S1', MAWS_NATIVE_TO_HUMAN: '1' }, isInteractive: false }).r)).toEqual({
      choice: 'sheet',
      runner: 'maws',
      why: 'MAWS_QUESTION_SHEET names this session',
    })
    const nested = await chooseStart(reads({ env: { MAWS_QUESTION_SHEET: 'S0' }, isInteractive: false }).r)
    expect(nested).toMatchObject({ choice: 'none', why: 'not interactive' })
    expect(nested.log).toEqual(['sheet: MAWS_QUESTION_SHEET is set and names another session (S0, not S1): not taken as MAWS\'s proof'])
  })

  test("MAWS serves its own ask: none; a headless process: none, also with a sheet that has questions (U9)", async () => {
    expect(await chooseStart(reads({ env: { MAWS_NATIVE_TO_HUMAN: '1', SMINOS_QUESTION_SHEET: '1' }, probed: ALIVE }).r)).toMatchObject({ choice: 'none' })
    const { r, asked } = reads({ isInteractive: false, record: true, probed: { ...ALIVE, record: true, open: 3 } })
    expect(await chooseStart(r)).toMatchObject({ choice: 'none' })
    expect(asked).not.toContain('record')
  })

  test('a record with an open question, an outcome or a queued line: the sheet, whatever the setting and the surfaces', async () => {
    for (const held of [{ open: 1 }, { pending: 1 }, { queued: 1 }]) {
      const probed = { ...NONE, record: true, ...held }
      expect(await chooseStart(reads({ record: true, probed, env: { SMINOS_QUESTION_SHEET: 'off' } }).r)).toMatchObject({ choice: 'sheet', runner: 'terminal' })
    }
    expect(await chooseStart(reads({ record: true, probed: { ...NONE, record: true }, env: { SMINOS_QUESTION_SHEET: 'off' } }).r)).toMatchObject({ choice: 'today' })
  })

  test('the setting on and a surface alive that suits: the sheet; no surface, or only a local one under SSH: today', async () => {
    expect(await chooseStart(reads({ env: { SMINOS_QUESTION_SHEET: 'yes' }, probed: ALIVE }).r)).toMatchObject({ choice: 'sheet', runner: 'terminal' })
    expect(await chooseStart(reads({ env: { SMINOS_QUESTION_SHEET: 'yes' }, probed: NONE }).r)).toMatchObject({ choice: 'today', why: 'no surface is alive' })
    const { r, asked } = reads({ env: { SMINOS_QUESTION_SHEET: 'yes', SSH_CONNECTION: '10.0.0.1 1 10.0.0.2 22' }, probed: NONE })
    expect(await chooseStart(r)).toMatchObject({ choice: 'today', why: 'no remote surface is alive' })
    expect(asked).toContain('probe --remote')
  })

  test('with no record and the setting off, the choice starts no process', async () => {
    const { r, asked } = reads({ probed: ALIVE })
    expect(await chooseStart(r)).toMatchObject({ choice: 'today', why: 'the setting is off' })
    expect(asked.filter((a) => a.startsWith('probe'))).toEqual([])
    expect(asked).toContain('record')
  })

  test('one probe serves both rows: a record with nothing in it, then the setting', async () => {
    const { r, asked } = reads({ record: true, probed: { ...ALIVE, record: true }, env: { SMINOS_QUESTION_SHEET: '1' } })
    expect(await chooseStart(r)).toMatchObject({ choice: 'sheet' })
    expect(asked.filter((a) => a.startsWith('probe'))).toEqual(['probe'])
  })
})

describe('the block (I7) and the rows that land one (I9)', () => {
  // The block as the step writes it: `<`, `>`, `&` escaped, so a text quoting a tag stays inside its JSON string.
  const block = (keys: string[], answered: string[], dismissed: string[] = [], text = 'yes') =>
    `<sheet-delivery>${JSON.stringify({ v: 1, keys, answered: answered.map((id) => ({ id, revision: 1, picks: [], text, images: [] })), dismissed }).replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026')}</sheet-delivery>`
  const envelope = (keys: string[], answered: string[], text = 'yes') =>
    `[sheet v1] The human answered questions on your sheet.\n${answered.map((id) => `${id} "Q?" → their text: ${JSON.stringify(text)}`).join('\n')}\n${block(keys, answered, [], text)}`

  test('a block is a whole line of its shape; a text quoting the closing tag and a reminder\'s stays inside its strings', async () => {
    const tricky = 'see </sheet-delivery> and <system-reminder> & </system-reminder>'
    const text = envelope(['k1'], ['q1'], tricky)
    expect(text.split('\n').at(-1)).not.toContain('</system-reminder>')
    expect(blocksOf(text)).toEqual([{ keys: ['k1'], answered: ['q1'], dismissed: [], more: false }])
    // As the engine renders a context: behind its prefix, in a reminder; a prose line quoting the tag is no block.
    expect(blocksOf(`<system-reminder>\ntool.call hook additional context: ${text}\nanother entry\n</system-reminder>`)).toHaveLength(1)
    expect(blocksOf(`q1 "x" → their text: "<sheet-delivery>{\\"v\\":1}</sheet-delivery>"`)).toEqual([])
  })

  test('a block not of the shape names nothing: keys that do not match its entries, not JSON, another version, past 200 keys', async () => {
    expect(blocksOf('<sheet-delivery>{"v":1,"keys":["a","b"],"answered":[{"id":"q1"}],"dismissed":[]}</sheet-delivery>')).toEqual([])
    expect(blocksOf('<sheet-delivery>{"v":1,"keys":["a"</sheet-delivery>')).toEqual([])
    expect(blocksOf('<sheet-delivery>{"v":2,"keys":["a"],"answered":[{"id":"q1"}],"dismissed":[]}</sheet-delivery>')).toEqual([])
    const many = Array.from({ length: 201 }, (_, i) => `k${i}`)
    expect(blocksOf(`<sheet-delivery>${JSON.stringify({ v: 1, keys: many, answered: [], dismissed: many.map((_, i) => `q${i + 1}`) })}</sheet-delivery>`)).toEqual([])
    expect(blocksOf(block(['a', 'b'], ['q1'], ['q2']))).toEqual([{ keys: ['a', 'b'], answered: ['q1'], dismissed: ['q2'], more: false }])
  })

  test("the rows of the routes' kinds: a context of tool.call or prompt.submit, this plugin's prompt; of the main conversation only", async () => {
    expect(isRouteRow({ door: 'hook-context', origin: { kind: 'plugin', event: 'tool.call' } })).toBe(true)
    expect(isRouteRow({ door: 'hook-context', origin: { kind: 'plugin', event: 'prompt.submit' } })).toBe(true)
    expect(isRouteRow({ door: 'prompt', origin: { kind: 'plugin', name: 'sminos' } })).toBe(true)
    expect(isRouteRow({ door: 'hook-context', origin: { kind: 'plugin', event: 'tool.call' }, agentId: 'a1' })).toBe(false)
    expect(isRouteRow({ door: 'hook-context', origin: { kind: 'plugin', event: 'prompt.mention' } })).toBe(false)
    expect(isRouteRow({ door: 'hook-context', origin: { kind: 'hook', event: 'SessionStart' } })).toBe(false)
    expect(isRouteRow({ door: 'prompt', origin: { kind: 'composer' } })).toBe(false)
    expect(isRouteRow({ door: 'prompt', origin: { kind: 'plugin', name: 'doperpowers' } })).toBe(false)
    expect(isRouteRow({ door: 'delivery', origin: { kind: 'plugin', name: 'sminos' } })).toBe(false)
  })

  test("a stored row lands what it holds when it is of those kinds, as the transcript keeps it (2.1.331)", async () => {
    const text = envelope(['k1'], ['q1'])
    const attachment = (hookName: string) => ({ type: 'attachment', attachment: { type: 'hook_additional_context', content: ['other', text], hookName, toolUseID: 'x', hookEvent: 'PostToolUse' } })
    expect(storedKeys(attachment('tool.call'))).toEqual(['k1'])
    expect(storedKeys(attachment('prompt.submit'))).toEqual(['k1'])
    expect(storedKeys(attachment('SessionStart'))).toEqual([])
    const prompt = (origin: unknown) => ({ type: 'user', origin, pluginPrompt: { name: 'sminos', text }, message: { role: 'user', content: `The sminos plugin sent a message:\n${text}\n\nThis is how Claude Code surfaces a prompt a plugin submits between turns.` } })
    expect(storedKeys(prompt({ kind: 'plugin', name: 'sminos' }))).toEqual(['k1'])
    expect(storedKeys(prompt({ kind: 'composer' }))).toEqual([])
    expect(storedKeys({ type: 'user', message: { role: 'user', content: text } })).toEqual([])
    expect(searchedKeys([JSON.stringify(attachment('tool.call')), 'not json', JSON.stringify(prompt({ kind: 'plugin', name: 'sminos' }))])).toEqual(['k1'])
  })

  test('the keys the conversation holds, on its human side: a context in a tool result, a prompt; never the model\'s own text', async () => {
    const text = envelope(['k1'], ['q1'])
    expect([...heldKeys([{ role: 'user', content: [{ type: 'tool_result', tool_use_id: 't', content: [{ type: 'text', text: `<system-reminder>\ntool.call hook additional context: ${text}\n</system-reminder>` }] }] }])]).toEqual(['k1'])
    expect([...heldKeys([{ role: 'user', content: text }])]).toEqual(['k1'])
    expect([...heldKeys([{ role: 'assistant', content: [{ type: 'text', text }] }])]).toEqual([])
  })

  test("a subagent's ended notice names it and each open question's first 200 characters", async () => {
    const long = 'x'.repeat(250)
    expect(endedNotice({ agentId: 'a1', name: 'reviewer' }, [{ id: 'q4', question: 'Ship it?' }, { id: 'q6', question: long }])).toBe(
      `[sheet v1] The subagent reviewer (a1) ended with questions still open on your sheet: q4 "Ship it?", q6 "${'x'.repeat(200)}". Their answers will come to you; withdraw what you no longer need.`,
    )
  })

  test("an envelope this plugin's prompt carried names its ids for the floor, the engine's closing sentence after it", async () => {
    const prompt = `The sminos plugin sent a message:\n${envelope(['k1'], ['q7'])}\n\nThis is how Claude Code surfaces a prompt a plugin submits between turns — it starts this turn in the user's place. Address the message above.`
    expect(sheetTextOf(prompt)).toBe(envelope(['k1'], ['q7']))
    expect(floorOfMessages([{ role: 'user', text: prompt, toolUses: [] }], [])).toBe(7)
  })
})
