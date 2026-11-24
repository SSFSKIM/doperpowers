import { describe, expect, test, tier } from 'claude-code/testing'

import { ASYNC_RESULT, asksReadWhileYielded, asyncAsks, observeAsks } from '../../hooks/mods/ask'
import type { AskNote } from '../../hooks/mods/ask'
import { DESCRIPTION, INPUT_SCHEMA, NOT_KNOWN, SHEET_TOOL, WITHDRAWN } from '../../hooks/mods/sheet-model'
import { TICK_MS, sheetNotices, sheetNudge, sheetView } from '../../hooks/mods/sheet'
import { ALIVE, HOME, MODEL, S1, S2, SHEET_ON, defaultStep, gated, harness, ok, sheetOn, view } from './sheet-harness'
import type { StepEvent, StepScript } from './sheet-harness'

tier('user')

describe('the start choice, at session.start (I8)', () => {
  test('the setting on and a surface alive: the tool under the sheet\'s description and schema, the ask registering nothing', async () => {
    const h = sheetOn()
    await h.start()
    expect(h.registered()).toEqual([{ name: 'AskUserQuestion', description: DESCRIPTION, inputSchema: INPUT_SCHEMA }])
    expect(h.kept.get('sminos.sheet')).toEqual({ shape: 1, choice: 'sheet', runner: 'terminal', session: S1 })
    expect(h.kept.get('sminos.ask')).toBeUndefined()
    expect(h.timers).toHaveLength(1)
  })

  test("the setting off, no surface, or SSH with a local one only: today's tool, as the ask registers it", async () => {
    for (const h of [harness({ probe: ALIVE }), sheetOn({ probe: { ...ALIVE, surface: null, surfaces: 0 } }), sheetOn({ env: { SSH_CONNECTION: '1 2 3 4' }, probe: { ...ALIVE, surface: null } })]) {
      await h.start()
      expect(h.registered().map((r) => (r.inputSchema as { required: string[] }).required)).toEqual([['questions']])
      expect((h.kept.get('sminos.sheet') as { choice: string }).choice).toBe('today')
      expect(h.timers).toHaveLength(0)
    }
    const remote = sheetOn({ env: { SSH_CONNECTION: '1 2 3 4' }, probe: { ...ALIVE, surface: null } })
    await remote.start()
    expect(remote.runs()).toEqual([`sheet probe --session ${S1} --remote`])
  })

  test('with the setting off and no record, the choice runs no process', async () => {
    const h = harness({ probe: ALIVE })
    await h.start()
    expect(h.runs()).toEqual([])
  })

  test('a sheet with a question open: the sheet, the setting off', async () => {
    const h = harness({ record: true, probe: { ...ALIVE, surface: null, surfaces: 0, record: true, open: 2 } })
    await h.start()
    expect(h.registered().map((r) => r.inputSchema)).toEqual([INPUT_SCHEMA])
  })

  test("not interactive, an internal session, MAWS serving its own ask: none, and the sheet's hooks pass on", async () => {
    for (const h of [sheetOn({ isInteractive: false }), sheetOn({ env: { SMNS_INTERNAL: '1' } }), sheetOn({ env: { MAWS_NATIVE_TO_HUMAN: '1' } })]) {
      await h.start()
      expect((h.kept.get('sminos.sheet') as { choice: string }).choice).toBe('none')
      expect(h.registered().filter((r) => r.inputSchema === INPUT_SCHEMA)).toEqual([])
    }
  })

  test("MAWS's proof: its variable naming this session is the sheet run by MAWS; a nested claude -p with another's id is not, said in the debug log", async () => {
    const maws = harness({ env: { MAWS_QUESTION_SHEET: S1, MAWS_NATIVE_TO_HUMAN: '1' }, isInteractive: false })
    await maws.start(false)
    expect(maws.kept.get('sminos.sheet')).toEqual({ shape: 1, choice: 'sheet', runner: 'maws', session: S1 })
    expect(maws.registered().map((r) => r.inputSchema)).toEqual([INPUT_SCHEMA])
    const nested = harness({ env: { MAWS_QUESTION_SHEET: S2, MAWS_NATIVE_TO_HUMAN: '1' }, isInteractive: false })
    await nested.start(false)
    expect(nested.registered()).toEqual([])
    expect(nested.logs()).toContain(`sheet: MAWS_QUESTION_SHEET is set and names another session (${S2}, not ${S1}): not taken as MAWS's proof`)
  })

  test('the choice is kept across a reload, whatever the setting says then; a kept ask snapshot with no choice kept is today', async () => {
    const first = sheetOn()
    await first.ready()
    const reloaded = harness({ kept: first.kept, probe: { ...ALIVE, surface: null } })
    await reloaded.start()
    expect(reloaded.registered().map((r) => r.inputSchema)).toEqual([INPUT_SCHEMA])
    // The reload drains for a view (E13), its start having answered before.
    await reloaded.settle()
    expect(reloaded.steps.map((s) => s.event)).toEqual(['drain'])
    const older = sheetOn({ kept: new Map([['sminos.ask', { shape: 2, asks: [], undelivered: [], isTurnRunning: false, isDialogUp: false, answered: 0 }]]) })
    await older.start()
    expect((older.kept.get('sminos.sheet') as { choice: string }).choice).toBe('today')
    expect(older.runs()).toEqual([])
  })

  test("a launch's SessionStart that comes while session.start still chooses (a terminal's, 2.1.331) is ordered once the choice is the sheet", async () => {
    const h = sheetOn()
    let release: () => void = () => {}
    const engine = h.engine as unknown as { process: { run: (argv: string[], init?: unknown) => Promise<unknown> } }
    const run = engine.process.run
    // The probe waits, as the choice's process call does, while the engine runs the SessionStart.
    engine.process.run = async (argv, init) => (argv[2] === 'probe' ? (await new Promise<void>((r) => (release = r)), run(argv, init)) : run(argv, init))
    const starting = h.start()
    await h.settle()
    // The ask's SessionStart waits for the choice, as the sheet's orders nothing yet.
    const classic = h.classicStart('startup')
    await h.settle()
    expect(h.steps).toEqual([])
    release()
    await starting
    await classic
    await h.settle()
    expect(h.steps).toHaveLength(1)
    expect(h.steps[0]).toMatchObject({ event: 'start', start: { source: 'startup', floor: 0 } })
    expect(h.kept.get('sminos.sheet')).toMatchObject({ choice: 'sheet', started: S1 })
  })

  test("a SessionStart that came early is dropped when the choice is not the sheet", async () => {
    const h = harness({ probe: ALIVE })
    await h.classicStart('startup')
    await h.start()
    await h.settle()
    expect(h.steps).toEqual([])
  })

  test('a reload before the start answered orders that start, under its nonce', async () => {
    const first = sheetOn({ step: () => Promise.reject(new Error('the command did not start')) })
    await first.start()
    await first.classicStart('resume')
    const nonce = (first.kept.get('sminos.sheet') as { starting: { nonce: string } }).starting.nonce
    const reloaded = harness({ kept: first.kept })
    await reloaded.start()
    await reloaded.settle()
    expect(reloaded.steps[0]).toMatchObject({ event: 'start', start: { source: 'resume', nonce } })
    expect((reloaded.kept.get('sminos.sheet') as { started?: string }).started).toBe(S1)
  })
})

describe('the ask yields (I11)', () => {
  test("yielded, it describes nothing and draws no band; the sheet's description stands and the built-in is withdrawn", async () => {
    const h = sheetOn()
    await h.start()
    expect(await h.describe(SHEET_TOOL, 'from the registration')).toEqual({ description: DESCRIPTION, isDeferred: false })
    expect(await h.describe('AskUserQuestion', 'The built-in.')).toEqual({ description: WITHDRAWN, isDeferred: true })
    expect(await h.render('AbovePrompt', { hasSurvey: false })).toBe('beneath')
  })

  test("yielded, a stored call of the sheet's form is the engine's to draw; one of today's form is still the ask's", async () => {
    const h = sheetOn()
    await h.start()
    expect(await h.render('ToolUse', { tool: SHEET_TOOL, tool_use_id: 't1', input: { ask: [{ question: 'a' }] }, output: 'Added q1.', isRunning: false, isErrored: false })).toBe('beneath')
    expect(await h.render('ToolResult', { tool: SHEET_TOOL, tool_use_id: 't1', output: 'Added q1.\nNot done: entry 2, multiSelect needs options.', isErrored: false })).toBe('beneath')
    expect(await h.render('ToolResult', { tool: SHEET_TOOL, tool_use_id: 't2', output: 'Outcome not known yet.\nThe sheet did not answer.', isErrored: false })).toBe('beneath')
    // Today's form, answered: the ask draws it (its row reaches for the renderer).
    const today = { questions: [{ question: 'Which?', header: 'H', multiSelect: false, options: [{ label: 'A', description: 'a' }, { label: 'B', description: 'b' }] }] }
    const drawn = h.render('ToolUse', { tool: SHEET_TOOL, tool_use_id: 't3', input: today, output: 'User has answered your questions: "Which?"="A". You can now continue with these answers in mind.', isRunning: false, isErrored: false })
    await expect(drawn).rejects.toThrow('drew')
  })

  test("not yielded (today), the sheet's hooks pass every call on: today's tool answers", async () => {
    const h = harness()
    await h.start()
    const { result } = await h.ask({ questions: [{ question: 'Which?', header: 'H', multiSelect: false, options: [{ label: 'A', description: 'a' }, { label: 'B', description: 'b' }] }] })
    expect(result).toEqual({ result: ASYNC_RESULT })
    expect(h.steps).toEqual([])
  })

  test("the built-in's call from the model is refused with the sheet's sentence; another plugin's passes", async () => {
    const h = sheetOn()
    await h.start()
    expect((await h.call('AskUserQuestion', { questions: [] })).result).toEqual({ deny: WITHDRAWN })
    expect((await h.call('AskUserQuestion', { questions: [] }, undefined, { plugin: 'cua', tier: 'user' })).ran).toHaveLength(1)
  })
})

describe('a call (I6)', () => {
  test("a whole-call refusal is a denial in today's words, reaching no step and staging nothing", async () => {
    const h = sheetOn()
    await h.ready()
    const before = h.steps.length
    for (const args of [{}, { ask: [{ question: 'a', id: 'q1' }], withdraw: ['q1'] }, { ask: [{ question: 'x'.repeat(2001) }] }, { ask: [{ question: 'a', extra: 1 }] }]) {
      const { result } = await h.ask(args)
      expect(result.deny?.startsWith('InputValidationError: AskUserQuestion failed due to the following issue')).toBe(true)
    }
    expect(h.steps.length).toBe(before)
    expect(h.writes()).toEqual([])
  })

  test("each entry's own refusal is staged as its clause, the others staged whole, and the step's result answered", async () => {
    const h = sheetOn({ step: (event, n) => (event.event === 'call' ? ok(n, { result: 'Added q1 (entry 2).\nNot done: entry 1, two options share the label "X".' }) : ok(n)) })
    await h.ready()
    const entries = [
      { question: 'Dup?', options: [{ label: 'X' }, { label: 'X' }] },
      { question: 'Fine?', options: [{ label: 'A' }] },
      { question: 'Multi preview?', multiSelect: true, options: [{ label: 'A', preview: 'p' }] },
      { question: 'Multi bare?', multiSelect: true },
      { question: 'Lines?', references: [{ path: 'a.ts', lines: [9, 2] }] },
    ]
    const { result, id } = await h.ask({ ask: entries })
    expect(result).toEqual({ result: 'Added q1 (entry 2).\nNot done: entry 1, two options share the label "X".' })
    const dir = `${HOME}/sheet/.staging/${S1}/${id}`
    expect(h.staged(`${dir}/call.json`)).toEqual({
      asker: 'main',
      entries: [
        { refused: 'two options share the label "X"' },
        { file: 'entry-2.json', captures: [] },
        { refused: "an option's preview needs a single-select question" },
        { refused: 'multiSelect needs options' },
        { refused: 'lines must be [a, b] with 1 <= a <= b' },
      ],
      withdraw: [],
    })
    expect(h.staged(`${dir}/entry-2.json`)).toEqual(entries[1] as Record<string, unknown>)
    expect(h.steps.at(-1)).toMatchObject({ event: 'call', call: { callId: id }, runner: 'terminal', remote: false })
    expect(h.calls.filter((c) => c.op === 'ui.notify').map((c) => c.args)).toEqual(['Fine?'])
  })

  test("a reference is captured through Read: checked, read, then where it lands; its body staged beside the entry", async () => {
    const h = sheetOn()
    await h.ready()
    const { id } = await h.ask({ ask: [{ question: 'Auth?', references: [{ path: 'src/auth.ts', lines: [40, 80] }, { path: '/abs/logo.png' }] }] })
    expect(h.calls.filter((c) => c.op === 'tool.check').map((c) => c.args)).toEqual([{ file_path: '/work/src/auth.ts', offset: 40, limit: 41 }, { file_path: '/abs/logo.png' }])
    expect(h.calls.filter((c) => c.op === 'tool.call').map((c) => c.args)).toEqual([
      { tool: 'Read', file_path: '/work/src/auth.ts', offset: 40, limit: 41 },
      { tool: 'Read', file_path: '/abs/logo.png' },
    ])
    const dir = `${HOME}/sheet/.staging/${S1}/${id}`
    expect(h.staged(`${dir}/call.json`).entries).toEqual([
      {
        file: 'entry-1.json',
        captures: [
          { ok: true, kind: 'text', startLine: 1, numLines: 1, totalLines: 1, abs: '/real/work/src/auth.ts', size: 5, mtimeMs: 1763900000000, file: 'ref-1-1' },
          { ok: true, kind: 'text', startLine: 1, numLines: 1, totalLines: 1, abs: '/real/abs/logo.png', size: 5, mtimeMs: 1763900000000, file: 'ref-1-2' },
        ],
      },
    ])
    expect(h.files.get(`${dir}/ref-1-1`)).toBe('content of /work/src/auth.ts\n')
  })

  test('an image is staged as its base64, with its media type', async () => {
    const h = sheetOn({ reads: { '/w/logo.png': { result: { type: 'image', file: { base64: 'iVBORw0KGgo=', type: 'image/png', originalSize: 9 } }, text: '' } } })
    await h.ready()
    const { id } = await h.ask({ ask: [{ question: 'Logo?', references: [{ path: '/w/logo.png' }] }] })
    const dir = `${HOME}/sheet/.staging/${S1}/${id}`
    expect((h.staged(`${dir}/call.json`).entries as { captures: unknown[] }[])[0]?.captures).toEqual([
      { ok: true, kind: 'image', mediaType: 'image/png', abs: '/real/w/logo.png', size: 5, mtimeMs: 1763900000000, file: 'ref-1-1' },
    ])
    expect(h.files.get(`${dir}/ref-1-1`)).toBe('iVBORw0KGgo=')
  })

  test("a capture refused by the check (a deny rule, a guard, the ask of a path outside the working directories), by a failing Read, and by the stub: the entry refused with the engine's reason, nothing of the file staged", async () => {
    const outside = "Claude requested permissions to read from /etc/hosts, but you haven't granted it yet."
    const h = sheetOn({
      checks: {
        '/work/.env': { decision: 'deny', reason: 'Permission to read /work/.env has been denied.', rule: 'Read(**/.env)' },
        '/work/secrets.txt': { decision: 'deny', reason: 'SECRETS GUARD: a secrets file' },
        '/etc/hosts': { decision: 'ask', reason: outside },
      },
      reads: {
        '/work/gone.ts': { isError: true, result: 'x', text: 'File does not exist. Note: your current working directory is /work.' },
        '/work/big.log': { isError: true, result: 'x', text: 'File content (1.4MB) exceeds maximum allowed size (256KB). Use offset and limit parameters to read specific portions.' },
        '/work/same.ts': { result: { type: 'file_unchanged', file: { filePath: '/work/same.ts' } }, text: 'File unchanged since last read.' },
      },
    })
    await h.ready()
    const paths = ['.env', 'secrets.txt', '/etc/hosts', 'gone.ts', 'big.log', 'same.ts']
    const { id } = await h.ask({ ask: paths.map((path) => ({ question: `About ${path}?`, references: [{ path: 'fine.ts' }, { path }] })) })
    const dir = `${HOME}/sheet/.staging/${S1}/${id}`
    expect(h.staged(`${dir}/call.json`).entries).toEqual([
      { refused: 'the reference .env could not be read: Permission to read /work/.env has been denied.' },
      { refused: 'the reference secrets.txt could not be read: SECRETS GUARD: a secrets file' },
      { refused: `the reference /etc/hosts could not be read: ${outside}` },
      { refused: 'the reference gone.ts could not be read: File does not exist. Note: your current working directory is /work.' },
      { refused: 'the reference big.log could not be read: File content (1.4MB) exceeds maximum allowed size (256KB). Use offset and limit parameters to read specific portions.' },
      { refused: 'the reference same.ts could not be read: File unchanged since last read.' },
    ])
    // Neither the refused file nor the entry's other reference, read before it, is staged.
    expect(h.writes().map((w) => w.path)).toEqual([`${dir}/call.json`])
    // A file the check refused is never read.
    expect(h.calls.filter((c) => c.op === 'tool.call').map((c) => (c.args as { file_path: string }).file_path)).not.toContain('/work/.env')
  })

  test('a call that only withdraws is staged and ordered', async () => {
    const h = sheetOn({ step: (event, n) => (event.event === 'call' ? ok(n, { result: 'Withdrew q2.' }) : ok(n)) })
    await h.ready()
    const { result, id } = await h.ask({ withdraw: ['q2'] })
    expect(result).toEqual({ result: 'Withdrew q2.' })
    expect(h.staged(`${HOME}/sheet/.staging/${S1}/${id}/call.json`)).toEqual({ asker: 'main', entries: [], withdraw: ['q2'] })
    expect(h.calls.filter((c) => c.op === 'ui.notify')).toEqual([])
  })

  test("a subagent's call: its asker by its agent's description, else its type; the running agents with the step", async () => {
    const agents = [
      { id: 'a1', description: 'reviewer', type: 'general-purpose', status: 'running' },
      { id: 'a2', description: '', type: 'Explore', status: 'running' },
      { id: 'a3', description: 'done', type: 'x', status: 'completed' },
    ]
    const h = sheetOn({ agents })
    await h.ready()
    const one = await h.ask({ ask: [{ question: 'Mine?' }] }, 'a1')
    expect(h.staged(`${HOME}/sheet/.staging/${S1}/${one.id}/call.json`).asker).toEqual({ agentId: 'a1', name: 'reviewer' })
    expect(h.steps.at(-1)).toMatchObject({ agents: { running: ['a1', 'a2'], direct: true } })
    const two = await h.ask({ ask: [{ question: 'Mine too?' }] }, 'a2')
    expect(h.staged(`${HOME}/sheet/.staging/${S1}/${two.id}/call.json`).asker).toEqual({ agentId: 'a2', name: 'Explore' })
  })

  test('a call before the session\'s start has answered changes nothing and says so', async () => {
    const h = sheetOn()
    await h.start()
    const { result } = await h.ask({ ask: [{ question: 'Early?' }] })
    expect(result).toEqual({ result: 'Nothing done.\nNot done: the sheet could not be written (the sheet is still starting); call again.' })
    expect(h.steps).toEqual([])
  })

  test('a call at every bound of the schema stages no file over 4 MiB', async () => {
    const big = (n: number) => '\u{10FFFF}'.repeat(n)
    const entry = (i: number) => ({
      question: big(2000),
      header: big(60),
      context: big(8000),
      options: Array.from({ length: 12 }, (_, k) => ({ label: `${String.fromCharCode(65 + k)}${big(199)}`, description: big(500), preview: big(8000) })),
      references: Array.from({ length: 8 }, (_, k) => ({ path: `f${i}-${k}.txt` })),
    })
    const huge = 'x'.repeat(256 * 1024)
    const reads = Object.fromEntries(
      Array.from({ length: 20 }, (_, i) => Array.from({ length: 8 }, (_, k) => [`/work/f${i}-${k}.txt`, { result: { type: 'text', file: { content: huge, numLines: 1, startLine: 1, totalLines: 1 } } }])).flat(),
    )
    const h = sheetOn({ reads })
    await h.ready()
    const { result } = await h.ask({ ask: Array.from({ length: 20 }, (_, i) => entry(i)) })
    expect(result).toEqual({ result: 'Added q1.' })
    const sizes = h.writes().map((w) => w.bytes)
    expect(sizes.length).toBe(20 * 8 + 20 + 1)
    expect(Math.max(...sizes)).toBeLessThan(4 * 1024 * 1024)
  })
})

describe('a call with no answer from its step (I5)', () => {
  test('a step that committed and whose answer was lost: settled, the recorded result answered once, then acknowledged', async () => {
    const h = sheetOn({
      step: (event, n) => {
        if (event.event === 'call') return 'Traceback: the answer was lost'
        if (event.event === 'settle') return ok(n, { result: 'Added q1.' })
        return ok(n)
      },
    })
    await h.ready()
    const { result, id } = await h.ask({ ask: [{ question: 'Lost?' }] })
    expect(result).toEqual({ result: 'Added q1.' })
    expect(h.steps.slice(-2).map((s) => s.event)).toEqual(['call', 'settle'])
    // The acknowledgement rides the next step, and only that one.
    await sheetNudge([])
    expect(h.steps.at(-1)).toMatchObject({ event: 'drain', acked: [id] })
    await sheetNudge([])
    expect(h.steps.at(-1)?.acked).toBeUndefined()
  })

  test("a step that never ran: the settle forecloses it, and the model reads Nothing done with the clause", async () => {
    const h = sheetOn({
      step: (event, n) => {
        if (event.event === 'call') throw new Error('the lock was not had in 10 s')
        if (event.event === 'settle') return ok(n, { foreclosed: true })
        return ok(n)
      },
    })
    await h.ready()
    const { result } = await h.ask({ ask: [{ question: 'Never?' }] })
    expect(result).toEqual({ result: 'Nothing done.\nNot done: the sheet could not be written (the lock was not had in 10 s); call again.' })
  })

  test('three settles unanswered: Outcome not known yet; a later settle that answers becomes one notice, and the call is acknowledged', async () => {
    let isDown = true
    const h = sheetOn({ step: (event, n) => (event.event === 'call' || (event.event === 'settle' && isDown) ? Promise.reject(new Error('timed out')) : event.event === 'settle' ? ok(n, { result: 'Added q1, q2.' }) : ok(n)) })
    await h.ready()
    const { result, id } = await h.ask({ ask: [{ question: 'A?' }, { question: 'B?' }] })
    expect(result).toEqual({ result: NOT_KNOWN })
    expect(h.steps.slice(-4).map((s) => s.event)).toEqual(['call', 'settle', 'settle', 'settle'])
    await h.tick()
    expect(sheetNotices()).toEqual([])
    isDown = false
    await h.tick()
    expect(sheetNotices()).toEqual([`[sheet v1] Your earlier call (${id}) did change the sheet: Added q1, q2.`])
    await h.tick()
    expect(sheetNotices()).toHaveLength(1)
    await sheetNudge([])
    await sheetNudge([])
    expect(h.steps.filter((s) => s.acked?.includes(id))).toHaveLength(1)
  })
})

describe('views and drains', () => {
  test("an answer of an older seq arriving after a newer one changes no view; its own result is still returned", async () => {
    let release: (stdout: string) => void = () => {}
    const h = sheetOn({ step: (event, n) => (event.event === 'call' ? new Promise<string>((r) => (release = r)) : ok(n + 10)) })
    await h.ready()
    const asking = h.ask({ ask: [{ question: 'Slow?' }] })
    await h.settle()
    // A drain the check orders answers a newer record while the call waits.
    await h.tick()
    const newer = sheetView()?.seq
    release(ok(2, { result: 'Added q1.' }, { nextId: 2 }))
    expect((await asking).result).toEqual({ result: 'Added q1.' })
    expect(sheetView()?.seq).toBe(newer as number)
  })

  test('a second drain asked for while one runs is one more step, not two; a hook that only triggers a drain returns before the step does', async () => {
    const pending: ((stdout: string) => void)[] = []
    const h = sheetOn({ step: (event, n) => (event.event === 'drain' ? new Promise<string>((r) => pending.push(() => r(ok(n)))) : ok(n)) })
    await h.ready()
    const before = h.steps.length
    const nudges = [sheetNudge(['k1']), sheetNudge(['k2']), sheetNudge(['k3'])]
    await h.settle()
    expect(h.steps.length - before).toBe(1)
    // The check's hooks return while the drain waits.
    const { ran } = await h.call('Bash', { command: 'ls' })
    expect(ran).toHaveLength(1)
    pending.shift()?.(ok(0))
    await h.settle()
    expect(h.steps.length - before).toBe(2)
    expect(h.steps.at(-1)).toMatchObject({ event: 'drain', keys: ['k2', 'k3'] })
    pending.shift()?.(ok(0))
    await Promise.all(nudges)
    expect(h.steps.length - before).toBe(2)
  })

  test("the bridge's nudge answers the verdicts of its keys from the drain's effects", async () => {
    const verdict = { verdict: 'stale', kind: 'answer', at: '2026-11-24T10:00:00.000Z', id: 'q2', current: 2 }
    const h = sheetOn({ step: (event, n) => (event.event === 'drain' ? ok(n, { verdicts: { 'page-1': verdict } }) : ok(n)) })
    await h.ready()
    expect(await sheetNudge(['page-1', 'page-2'])).toEqual({ ok: true, result: { verdicts: { 'page-1': verdict } } })
    expect(h.steps.at(-1)).toMatchObject({ event: 'drain', keys: ['page-1', 'page-2'] })
  })

  test('the check drains when the inbox is longer than the view says, once for a write that did not finish', async () => {
    const h = sheetOn({ files: { [`${HOME}/sheet/${S1}/inbox.jsonl`]: '' } })
    await h.ready()
    const drains = () => h.steps.filter((s) => s.event === 'drain').length
    await h.tick()
    expect(drains()).toBe(0)
    h.files.set(`${HOME}/sheet/${S1}/inbox.jsonl`, '{"v":1,"key":"page-0001"')
    await h.tick()
    await h.tick()
    expect(drains()).toBe(1)
  })

  test("a bridge hello and a tick before a fork's start order nothing; the fork's start carries the floor its conversation holds", async () => {
    const h = sheetOn({ messages: { rows: [{ role: 'assistant', text: '', toolUses: [{ tool: SHEET_TOOL, text: 'Added q7, q8.' }] }], api: [] } })
    await h.start()
    expect(await sheetNudge([])).toMatchObject({ ok: false, code: 'no-sheet' })
    await h.tick()
    expect(h.steps).toEqual([])
    await h.classicStart('fork', S2)
    expect(h.steps).toHaveLength(1)
    expect(h.steps[0]).toMatchObject({ event: 'start', start: { source: 'fork', floor: 8 } })
    expect(h.kept.get('sminos.sheet')).toMatchObject({ session: S2, started: S2 })
  })

  test("every call carries the floor while the view assigns q1 next; past it, none; a conversation not readable at the start is read at the call", async () => {
    const h = sheetOn({ step: (event, n) => (event.event === 'call' ? ok(n, { result: 'Added q5.' }, { nextId: 6 }) : ok(n)) })
    await h.start()
    await h.classicStart('fork', S2)
    expect(h.steps[0]?.start).not.toHaveProperty('floor')
    h.converse({ rows: [], api: [{ role: 'system', content: 'SessionStart hook additional context: [sheet v1] Your question sheet, after a resume.\nNew ids continue from q5.' }] })
    await h.ask({ ask: [{ question: 'First?' }] })
    expect(h.steps.at(-1)?.call).toMatchObject({ floor: 4 })
    await h.ask({ ask: [{ question: 'Second?' }] })
    expect(h.steps.at(-1)?.call).not.toHaveProperty('floor')
  })
})

describe('the other triggers (E12, E14)', () => {
  test("a compaction drains with the context named, and starts nothing; a subagent's stop drains", async () => {
    const h = sheetOn()
    await h.ready()
    await h.classicStart('compact')
    expect(h.steps.at(-1)).toMatchObject({ event: 'drain', context: 'compact' })
    expect(h.steps.filter((s) => s.event === 'start')).toHaveLength(1)
    await h.dispatch('classic.SubagentStop', { hook_event_name: 'SubagentStop', session_id: S1, agent_id: 'a1' })
    await h.settle()
    expect(h.steps.at(-1)).toMatchObject({ event: 'drain' })
    expect(h.steps.at(-1)).not.toHaveProperty('context')
    expect(h.steps).toHaveLength(3)
  })
})


describe("a resume's legacy asks wait for the choice (I11)", () => {
  /** A transcript holding one open async ask of today's tool, as the engine stores it. */
  const legacy = () => {
    const question = { question: 'Which port?', header: 'Port', multiSelect: false, options: [{ label: 'A', description: 'a' }, { label: 'B', description: 'b' }] }
    const rows = [
      { type: 'assistant', message: { role: 'assistant', content: [{ type: 'tool_use', id: 't-open', name: SHEET_TOOL, input: { questions: [question], async: true } }] } },
      { type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 't-open', content: ASYNC_RESULT }] } },
    ]
    return rows.map((row, i) => JSON.stringify({ parentUuid: i === 0 ? null : `u${i - 1}`, uuid: `u${i}`, ...row })).join('\n') + '\n'
  }

  /**
   * A resume's SessionStart that comes before the choice is made: while the
   * choice's probe waits (`order: 'during'`), or before session.start runs
   * at all (`'first'`). Timers fire meanwhile, as many as `ticks` (each a
   * clock tick past any wait a timer could bound). Then the choice is made.
   */
  async function earlyResume(over: Parameters<typeof harness>[0], order: 'during' | 'first' = 'during', ticks = 0) {
    const h = harness({ ...over, files: { [`/t/${S1}.jsonl`]: legacy() } })
    const notes: AskNote[] = []
    observeAsks((note) => notes.push(note))
    let release: () => void = () => {}
    const engine = h.engine as unknown as { process: { run: (argv: string[], init?: unknown) => Promise<unknown> } }
    const run = engine.process.run
    engine.process.run = async (argv, init) => (argv[2] === 'probe' ? (await new Promise<void>((r) => (release = r)), run(argv, init)) : run(argv, init))
    let starting: Promise<unknown> = Promise.resolve()
    if (order === 'during') {
      starting = h.start()
      await h.settle()
    }
    // The hook returns without waiting for the choice.
    await h.classicStart('resume')
    if (order === 'first') {
      starting = h.start()
      await h.settle()
    }
    for (let i = 0; i < ticks; i++) await h.tick()
    // Read, not taken up: nothing published while the choice is open.
    expect(notes).toEqual([])
    expect(asyncAsks()).toEqual([])
    release()
    await starting
    await h.settle()
    return { h, notes }
  }

  for (const order of ['during', 'first'] as const) {
    test(`a SessionStart ${order === 'first' ? 'before' : 'during'} the choice, which is the sheet: the ask takes up none and publishes nothing; what it read is kept for the import`, async () => {
      const { h, notes } = await earlyResume({ env: SHEET_ON, probe: ALIVE }, order)
      expect((h.kept.get('sminos.sheet') as { choice: string }).choice).toBe('sheet')
      expect(notes).toEqual([])
      expect(asyncAsks()).toEqual([])
      expect(asksReadWhileYielded().map((ask) => [ask.id, ask.status])).toEqual([['t-open', 'open']])
      expect(await h.render('AbovePrompt', { hasSurvey: false })).toBe('beneath')
    })

    test(`a SessionStart ${order === 'first' ? 'before' : 'during'} the choice, which is today: the ask takes them up as it does today, once the choice is made`, async () => {
      const { h, notes } = await earlyResume({ env: SHEET_ON, probe: { ...ALIVE, surface: null, surfaces: 0 } }, order)
      expect((h.kept.get('sminos.sheet') as { choice: string }).choice).toBe('today')
      expect(notes).toEqual([expect.objectContaining({ kind: 'open', id: 't-open' })])
      expect(asyncAsks().map((ask) => [ask.id, ask.status])).toEqual([['t-open', 'open']])
    })
  }

  test('a choice of the sheet that comes after every timer has fired (a slow probe) still takes up nothing', async () => {
    const { notes } = await earlyResume({ env: SHEET_ON, probe: ALIVE }, 'during', 5)
    expect(notes).toEqual([])
    expect(asyncAsks()).toEqual([])
  })

  for (const [choice, probe] of [['sheet', ALIVE], ['today', { ...ALIVE, surface: null, surfaces: 0 }]] as const) {
    test(`the choice made (${choice}) while the SessionStart's read of the transcript is still pending: ${choice === 'sheet' ? 'nothing is adopted, the read kept for the import' : 'the asks are adopted once read'}`, async () => {
      const h = harness({ env: SHEET_ON, probe, files: { [`/t/${S1}.jsonl`]: legacy() } })
      const notes: AskNote[] = []
      observeAsks((note) => notes.push(note))
      const engine = h.engine as unknown as { process: { run: (argv: string[], init?: unknown) => Promise<unknown> }; fs: { read: (path: string) => Promise<string> } }
      let releaseProbe: () => void = () => {}
      const run = engine.process.run
      engine.process.run = async (argv, init) => (argv[2] === 'probe' ? (await new Promise<void>((r) => (releaseProbe = r)), run(argv, init)) : run(argv, init))
      // The ask's first read of the transcript waits; any later read (the sheet's floor) does not.
      let releaseRead: () => void = () => {}
      let isHeld = false
      const read = engine.fs.read
      engine.fs.read = async (path) => {
        if (path === `/t/${S1}.jsonl` && !isHeld) {
          isHeld = true
          await new Promise<void>((r) => (releaseRead = r))
        }
        return read(path)
      }
      const starting = h.start()
      await h.settle()
      const classic = h.classicStart('resume')
      await h.settle()
      expect(isHeld).toBe(true)
      // The choice is made while the read is pending.
      releaseProbe()
      await starting
      await h.settle()
      expect((h.kept.get('sminos.sheet') as { choice: string }).choice).toBe(choice)
      releaseRead()
      await classic
      await h.settle()
      if (choice === 'sheet') {
        expect(notes).toEqual([])
        expect(asyncAsks()).toEqual([])
        expect(asksReadWhileYielded().map((ask) => [ask.id, ask.status])).toEqual([['t-open', 'open']])
      } else {
        expect(notes).toEqual([expect.objectContaining({ kind: 'open', id: 't-open' })])
        expect(asyncAsks().map((ask) => [ask.id, ask.status])).toEqual([['t-open', 'open']])
      }
    })
  }

  test('once the choice is made, a later SessionStart takes the asks up at once (today)', async () => {
    const h = harness({ probe: ALIVE, files: { [`/t/${S1}.jsonl`]: legacy() } })
    const notes: AskNote[] = []
    observeAsks((note) => notes.push(note))
    await h.start()
    await h.classicStart('resume')
    expect(notes).toEqual([expect.objectContaining({ kind: 'open', id: 't-open' })])
  })
})

describe('one start at a time (I5)', () => {
  test('a trigger while the start runs joins it: one start step, and nothing else ordered before it answers', async () => {
    const g = gated(['start'])
    const h = sheetOn({ step: g.script })
    await h.start()
    const starting = h.classicStart('startup')
    await h.settle()
    await h.tick()
    await h.tick()
    expect(sheetNudge([])).resolves.toMatchObject({ ok: false, code: 'no-sheet' })
    expect(h.steps.map((s) => s.event)).toEqual(['start'])
    g.waiting.shift()?.release()
    await starting
    await h.settle()
    expect(h.steps.filter((s) => s.event === 'start')).toHaveLength(1)
    expect(h.kept.get('sminos.sheet')).toMatchObject({ started: S1 })
  })

  test('a start that settled with no answer is ordered again at the next trigger, under the same nonce', async () => {
    const g = gated(['start'])
    const h = sheetOn({ step: g.script })
    await h.start()
    const starting = h.classicStart('startup')
    await h.settle()
    g.waiting.shift()?.release(new Error('timed out'))
    await starting
    await h.tick()
    expect(h.steps.map((s) => s.event)).toEqual(['start', 'start'])
    expect(h.steps[1]?.start).toEqual(h.steps[0]?.start)
    g.waiting.shift()?.release()
    await h.settle()
    expect(h.kept.get('sminos.sheet')).toMatchObject({ started: S1 })
  })
})

describe('a session change fences the work of the one before (I5)', () => {
  /** A session whose call got no answer from three settles: unsettled in S1. */
  async function unsettled(over: { settle?: () => string | Promise<string> } = {}) {
    let isDown = true
    const h = sheetOn({
      messages: { rows: [], api: [] },
      step: (event, n) => {
        if (event.event === 'call' && isDown) return Promise.reject(new Error('timed out'))
        if (event.event === 'settle') return isDown ? Promise.reject(new Error('timed out')) : (over.settle?.() ?? ok(n, { result: 'Added q1.' }))
        return defaultStep(event, n)
      },
    })
    await h.ready()
    const { id } = await h.ask({ ask: [{ question: 'Parent?' }] })
    return { h, id, up: () => (isDown = false) }
  }

  test("a /branch's session never settles the parent's call against its record, nor tells the copy of it", async () => {
    const { h, up } = await unsettled()
    await h.classicStart('fork', S2)
    up()
    await h.tick()
    await h.tick()
    const before = h.steps.findIndex((s) => s.session === S2)
    expect(h.steps.slice(before).filter((s) => s.event === 'settle')).toEqual([])
    expect(sheetNotices()).toEqual([])
  })

  test("a settle in flight when the session changes completes into the generation it began in", async () => {
    let release: (stdout: string) => void = () => {}
    const { h, id, up } = await unsettled({ settle: () => new Promise<string>((r) => (release = r)) })
    up()
    void h.tick()
    await h.settle()
    expect(h.steps.at(-1)).toMatchObject({ event: 'settle', session: S1, call: { callId: id } })
    await h.classicStart('fork', S2)
    release(ok(9, { result: 'Added q1.' }))
    await h.settle()
    expect(sheetNotices()).toEqual([])
    await sheetNudge([])
    expect(h.steps.at(-1)).toMatchObject({ event: 'drain', session: S2 })
    expect(h.steps.at(-1)).not.toHaveProperty('acked')
  })

  test("a call whose hook fails after the session changed is the parent's to settle: the copy never settles it, and its late answer tells no one", async () => {
    const g = gated(['call'])
    const h = sheetOn({ step: g.script })
    await h.ready()
    let giveUp: () => void = () => {}
    const asking = h.call(SHEET_TOOL, { ask: [{ question: 'Parent?' }] }, undefined, MODEL, new Promise<void>((r) => (giveUp = r)))
    await h.settle()
    await h.classicStart('fork', S2)
    giveUp()
    expect((await asking).result).toEqual({ result: NOT_KNOWN })
    await h.tick()
    await h.tick()
    expect(h.steps.filter((s) => s.session === S2 && s.event === 'settle')).toEqual([])
    g.waiting.shift()?.release(ok(5, { result: 'Added q1.' }))
    await h.settle()
    expect(h.calls.filter((c) => c.op === 'ui.notify')).toEqual([])
    expect(sheetNotices()).toEqual([])
  })

  test("a call whose hook fails in its own session is settled there at the next trigger", async () => {
    const g = gated(['call'])
    const h = sheetOn({ step: g.script })
    await h.ready()
    let giveUp: () => void = () => {}
    const asking = h.call(SHEET_TOOL, { ask: [{ question: 'Mine?' }] }, undefined, MODEL, new Promise<void>((r) => (giveUp = r)))
    await h.settle()
    giveUp()
    const { id } = await asking
    await h.tick()
    expect(h.steps.at(-1)).toMatchObject({ event: 'settle', session: S1, call: { callId: id } })
  })

  test("a fork's session starts with nothing of the parent's to acknowledge", async () => {
    const h = sheetOn({ step: (event, n) => (event.event === 'call' ? 'lost' : event.event === 'settle' ? ok(n, { result: 'Added q1.' }) : ok(n)) })
    await h.ready()
    await h.ask({ ask: [{ question: 'Parent?' }] })
    await h.classicStart('fork', S2)
    await sheetNudge([])
    expect(h.steps.filter((s) => s.session === S2).every((s) => s.acked === undefined)).toBe(true)
  })

  test("a /clear retires the session's start: no trigger orders it again, and the removal waits for one in flight", async () => {
    const g = gated(['start'])
    const h = sheetOn({ step: g.script })
    await h.start()
    void h.classicStart('startup')
    await h.settle()
    await h.sessionEnd('clear')
    await h.settle()
    expect(h.kept.get('sminos.sheet')).not.toHaveProperty('starting')
    expect(h.runs().filter((r) => r.startsWith('sheet remove'))).toEqual([])
    await h.tick()
    expect(h.steps.map((s) => s.event)).toEqual(['start'])
    g.waiting.shift()?.release()
    await h.settle()
    expect(h.runs().filter((r) => r.startsWith('sheet remove'))).toEqual([`sheet remove --session ${S1} --cleared`])
    expect(h.kept.get('sminos.sheet')).not.toHaveProperty('started')
  })
})

describe("the check of K4 where the sheet's own hooks answer", () => {
  test("the tool's own call and the built-in's refusal trigger it", async () => {
    const h = sheetOn({ files: { [`${HOME}/sheet/${S1}/inbox.jsonl`]: '' } })
    await h.ready()
    const drains = () => h.steps.filter((s) => s.event === 'drain').length
    h.files.set(`${HOME}/sheet/${S1}/inbox.jsonl`, '{"v":1}\n')
    await h.ask({})
    await h.settle()
    expect(drains()).toBe(1)
    h.files.set(`${HOME}/sheet/${S1}/inbox.jsonl`, '{"v":1}\n{"v":1}\n')
    await h.call('AskUserQuestion', { questions: [] })
    await h.settle()
    expect(drains()).toBe(2)
  })
})

describe('a /clear (E15)', () => {
  test("the new session's start never waits for the old record's removal, and is kept for a retry before anything is awaited", async () => {
    const g = gated(['start'])
    const h = sheetOn({ step: g.script })
    await h.start()
    void h.classicStart('startup')
    await h.settle()
    await h.sessionEnd('clear')
    // The old start is still in flight: the removal waits for it, the new session's start does not.
    const clearing = h.classicStart('clear', S2)
    await h.settle()
    expect(h.kept.get('sminos.sheet')).toMatchObject({ session: S2, starting: { source: 'clear', floor: 0 } })
    expect(h.steps.map((s) => [s.event, s.session])).toEqual([['start', S1], ['start', S2]])
    expect(h.runs().filter((r) => r.startsWith('sheet remove'))).toEqual([])
    // The new start gives no answer: it is ordered again under its nonce.
    g.waiting[1]?.release(new Error('timed out'))
    await clearing
    await h.tick()
    expect(h.steps.filter((s) => s.session === S2).map((s) => s.start)).toEqual([h.steps[1]?.start, h.steps[1]?.start])
    // The old start lands: only then is its record removed, once.
    g.waiting[0]?.release()
    await h.settle()
    expect(h.runs().filter((r) => r.startsWith('sheet remove'))).toEqual([`sheet remove --session ${S1} --cleared`])
    expect(h.kept.get('sminos.sheet')).not.toHaveProperty('started', S1)
  })

  test("the record it leaves is removed at the session's end; the new session's start, removing nothing more, then answers", async () => {
    const h = sheetOn()
    await h.ready()
    await h.sessionEnd('clear')
    await h.settle()
    expect(h.runs()).toContain(`sheet remove --session ${S1} --cleared`)
    await h.classicStart('clear', S2)
    expect(h.runs().filter((r) => r === `sheet remove --session ${S1} --cleared`)).toHaveLength(1)
    expect(h.steps.at(-1)).toMatchObject({ event: 'start', start: { source: 'clear', floor: 0 } })
    expect(h.kept.get('sminos.sheet')).toEqual({ shape: 1, choice: 'sheet', runner: 'terminal', session: S2, started: S2 })
  })

  test('a removal the end could not make is made at the start', async () => {
    let fails = true
    const h = sheetOn()
    await h.ready()
    const engine = h.engine as unknown as { process: { run: (argv: string[], init?: unknown) => Promise<unknown> } }
    const run = engine.process.run
    engine.process.run = async (argv, init) =>
      argv[2] === 'remove' && fails ? (h.calls.push({ op: 'process.run', args: argv }), { exitCode: 1, stdout: '', stderr: 'busy', isStdoutTruncated: false, isStderrTruncated: false }) : run(argv, init)
    await h.sessionEnd('clear')
    await h.settle()
    expect(h.kept.get('sminos.sheet')).toMatchObject({ left: S1 })
    fails = false
    await h.classicStart('clear', S2)
    expect(h.runs().filter((r) => r === `sheet remove --session ${S1} --cleared`)).toHaveLength(2)
    expect(h.kept.get('sminos.sheet')).not.toHaveProperty('left')
  })
})
