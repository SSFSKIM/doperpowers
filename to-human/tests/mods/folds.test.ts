import type { EngineInterface, On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { describe, expect, mock, test, tier } from 'claude-code/testing'

import type { Folds, OpenFold } from '../../types/to-human'
import type { Ask, KeptRow, Step } from '../../hooks/mods/folds'
import { LABEL_SYSTEM, follow, labelOf, lineOf, newTracker, published, registerFolds, stepsOf, summaryOf, takeUp } from '../../hooks/mods/folds'
import { FINAL_ANSWER, MESSAGE_TOOL } from '../../hooks/mods/message'
import { newView } from '../../hooks/mods/to-human'

tier('user')

// Rows as the main conversation keeps them, in the shapes the diagnosis's
// probe logged (~/.local/share/fold-runs/evidence/: door, origin, role,
// blocks), the text each carries from the engine's own formats.

const MODEL = { kind: 'model' as const, model: 'claude-haiku-5-5' }
const text = (value: string) => ({ type: 'text', text: value })
const use = (id: string, name: string, input: unknown = {}) => ({ type: 'tool_use', id, name, input })
const response = (uuid: string, ...content: Record<string, unknown>[]): KeptRow =>
  ({ door: 'response', uuid, origin: MODEL, message: { type: 'assistant', role: 'assistant', content } }) as KeptRow
const result = (uuid: string, call: string, tool = 'Bash', output = 'ok'): KeptRow =>
  ({
    door: 'tool-result', uuid, origin: { kind: 'tool', tool },
    message: { type: 'user', role: 'user', content: [{ type: 'tool_result', tool_use_id: call, content: output }] },
  }) as KeptRow
const userRow = (uuid: string, door: 'prompt' | 'delivery', origin: Record<string, unknown>, body: string, isMeta = false): KeptRow =>
  ({ door, uuid, origin, message: { type: 'user', role: 'user', ...(isMeta && { isMeta: true }), content: [text(body)] } }) as unknown as KeptRow
const row = (door: string, uuid: string, origin: Record<string, unknown> = { kind: 'engine' }, content: Record<string, unknown>[] = [text('x')], extra: Record<string, unknown> = {}): KeptRow =>
  ({ door, uuid, origin, message: { type: 'user', role: 'user', content }, ...extra }) as KeptRow

/** A task's notification as the engine writes it (a background command's, an agent's). */
const notification = (toolUseId: string, status: string) =>
  `<task-notification>\n<task-id>b6vqvwqvj</task-id>\n<tool-use-id>${toolUseId}</tool-use-id>\n<output-file>/tmp/b6vqvwqvj.output</output-file>\n<status>${status}</status>\n<summary>Agent "probe agent" ${status}</summary>\n</task-notification>`

const DOORS = ['prompt', 'delivery'] as const

describe('stepsOf: what each kept row does', () => {
  test('an unmarked text is a note; a marked one is a read row; a mixed one also opens the next run with its note', () => {
    expect(stepsOf(response('a1', text('Reading the logs.')), new Set())).toEqual([{ kind: 'note', id: 'a1', text: 'Reading the logs.' }])
    expect(stepsOf(response('a2', text('<message>Done.</message>')), new Set())).toEqual([{ kind: 'read', id: 'a2' }])
    expect(stepsOf(response('a3', text('<message>Done.</message>\nNow the tests.')), new Set())).toEqual([
      { kind: 'read', id: 'a3' },
      { kind: 'note', id: 'a3', text: '<message>Done.</message>\nNow the tests.' },
    ])
    expect(stepsOf(response('a4', text('  \n')), new Set())).toEqual([])
  })

  test('a read tool is a read row, a spawn remembered; any other call joins the run', () => {
    const spawns = new Set<string>()
    for (const tool of [MESSAGE_TOOL, 'AskUserQuestion', 'mcp__sminos__AskUserQuestion', 'Agent', 'Workflow']) {
      expect(stepsOf(response('a1', use(`toolu_${tool}`, tool)), spawns)).toEqual([{ kind: 'read', id: `toolu_${tool}` }])
    }
    expect([...spawns]).toEqual(['toolu_Agent', 'toolu_Workflow'])
    expect(stepsOf(response('a2', use('toolu_b', 'Bash', { command: 'ls' })), spawns)).toEqual([
      { kind: 'call', id: 'toolu_b', tool: 'Bash', input: { command: 'ls' } },
    ])
  })

  test("a response's blocks are taken in order, thinking left out", () => {
    const steps = stepsOf(
      response('a1', { type: 'thinking', thinking: 'hm' }, text('Checking.'), use('toolu_b', 'Bash', { command: 'ls' }), use('toolu_m', MESSAGE_TOOL, { text: 'Hi' })),
      new Set(),
    )
    expect(steps.map((step) => step.kind)).toEqual(['note', 'call', 'read'])
  })

  test("a tool result is its call's; a read tool's result is the read row's and changes nothing", () => {
    expect(stepsOf(result('u1', 'toolu_b'), new Set())).toEqual([{ kind: 'result', call: 'toolu_b', text: 'ok', isError: false }])
    // The tracker holds no run for a read call, so its result finds none (see `follow`).
    expect(stepsOf(result('u2', 'toolu_m', MESSAGE_TOOL, 'sent'), new Set())).toEqual([{ kind: 'result', call: 'toolu_m', text: 'sent', isError: false }])
    // A result's blocks: its texts, one line each, anything else by its type; an error says so.
    const blocks = row('tool-result', 'u3', { kind: 'tool', tool: 'Read' }, [
      { type: 'tool_result', tool_use_id: 'toolu_r', is_error: true, content: [text('first'), { type: 'image', source: {} }, text('last')] },
    ])
    expect(stepsOf(blocks, new Set())).toEqual([{ kind: 'result', call: 'toolu_r', text: 'first\n[image]\nlast', isError: true }])
  })

  test("the person's prompt is a read row, typed between turns or into a running one", () => {
    expect(stepsOf(userRow('p1', 'prompt', { kind: 'composer' }, 'Fix the build.'), new Set())).toEqual([{ kind: 'read', id: 'p1' }])
    // The probe's `ghost` scenario: a prompt typed into a running turn is kept through `delivery`, origin `composer`.
    expect(stepsOf(userRow('p2', 'delivery', { kind: 'composer' }, 'Also the docs.'), new Set())).toEqual([{ kind: 'read', id: 'p2' }])
  })

  test("a delivery joins the open run, kept between turns or folded into a running one", () => {
    for (const door of DOORS) {
      // A background command's finish, and a subagent's hand-back (`peer`, kept isMeta).
      expect(stepsOf(userRow('d1', door, { kind: 'task-notification' }, notification('toolu_bg', 'completed')), new Set())).toEqual([
        { kind: 'delivery', id: 'd1', text: notification('toolu_bg', 'completed') },
      ])
      expect(stepsOf(userRow('d2', door, { kind: 'peer' }, 'Another Claude session sent a message: done', true), new Set())).toEqual([
        { kind: 'delivery', id: 'd2', text: 'Another Claude session sent a message: done' },
      ])
      // Another session's sminos message is record by its frame; the person's, sent from elsewhere, is theirs.
      expect(stepsOf(userRow('d3', door, { kind: 'plugin', name: 'sminos', asUser: true }, '[sminos message from mini-doperpowers id=0a1b2c3d] hi'), new Set())).toEqual([
        { kind: 'delivery', id: 'd3', text: '[sminos message from mini-doperpowers id=0a1b2c3d] hi' },
      ])
      expect(stepsOf(userRow('d4', door, { kind: 'plugin', name: 'sminos', asUser: true }, '[sminos message from human id=0a1b2c3d] hi'), new Set())).toEqual([{ kind: 'read', id: 'd4' }])
    }
  })

  test("a channel's message is a delivery: the engine gives its drawing a sender, which the kept row lacks", () => {
    for (const door of DOORS) {
      expect(stepsOf(userRow('c1', door, { kind: 'channel', server: 'slack' }, 'Deploy is green.'), new Set())).toEqual([
        { kind: 'delivery', id: 'c1', text: 'Deploy is green.' },
      ])
    }
  })

  test("the failure of a spawn the report shows is a read row; another task's failure, and a spawn's finish, are deliveries", () => {
    for (const door of DOORS) {
      const spawns = new Set<string>()
      stepsOf(response('a1', use('toolu_agent', 'Agent', { prompt: 'go' })), spawns)
      expect(stepsOf(userRow('f1', door, { kind: 'task-notification' }, notification('toolu_agent', 'failed')), spawns)).toEqual([{ kind: 'read', id: 'f1' }])
      expect(stepsOf(userRow('f2', door, { kind: 'task-notification' }, notification('toolu_agent', 'completed')), spawns)[0]?.kind).toBe('delivery')
      expect(stepsOf(userRow('f3', door, { kind: 'task-notification' }, notification('toolu_bg', 'failed')), spawns)[0]?.kind).toBe('delivery')
    }
  })

  test('an API error and a compaction are read rows', () => {
    const error = { ...response('e1', text('API Error: Connection refused')), origin: { kind: 'model', model: '<synthetic>' } } as KeptRow
    expect(stepsOf(error, new Set())).toEqual([{ kind: 'read', id: 'e1' }])
    // The stand-in for no response is no error: an unmarked text, as the view reads it.
    const none = { ...response('e2', text('No response requested.')), origin: { kind: 'model', model: '<synthetic>' } } as KeptRow
    expect(stepsOf(none, new Set())[0]?.kind).toBe('note')
    expect(stepsOf(row('compaction', 'k1', { kind: 'engine' }), new Set())).toEqual([{ kind: 'read', id: 'k1' }])
  })

  test("everything else is ignored: hook context, notices, commands, attachments, a tool's own row, a queue record, a plugin's note, a subagent's rows", () => {
    const ignored = [
      row('hook-context', 'h1', { kind: 'hook', event: 'SessionStart' }, []),
      row('notice', 'n1', { kind: 'engine' }, []),
      row('command', 'c1', { kind: 'composer' }, [text('<command-name>/model</command-name>')]),
      row('attachment', 't1', { kind: 'engine' }),
      row('tool-message', 'm1', { kind: 'tool', tool: 'Read' }),
      row('queue', 'q1', { kind: 'engine' }, [text('Also the docs.')]),
      row('note', 'o1', { kind: 'plugin', name: 'sminos' }),
      response('r1', { type: 'thinking', thinking: 'hm' }),
      { ...response('s1', use('toolu_s', 'Bash', { command: 'ls' })), agentId: 'a7' } as KeptRow,
      { ...userRow('s2', 'prompt', { kind: 'composer' }, 'go'), agentId: 'a7' } as KeptRow,
      { ...result('s3', 'toolu_b'), agentId: 'a7' } as KeptRow,
    ]
    for (const kept of ignored) {
      expect(stepsOf(kept, new Set())).toEqual([])
    }
  })
})

describe('lineOf: one call as one line', () => {
  test('each tool of the table', () => {
    expect(lineOf('Bash', { command: 'npm test', description: 'Run the tests' })).toBe('Run the tests')
    expect(lineOf('Bash', { command: 'cd x &&\n  make all' })).toBe('cd x &&')
    expect(lineOf('Read', { file_path: '/repo/src/fold.ts' })).toBe('Read fold.ts')
    expect(lineOf('Edit', { file_path: '/repo/src/fold.ts', old_string: 'a', new_string: 'b' })).toBe('Edit fold.ts')
    expect(lineOf('Write', { file_path: '/repo/notes.md', content: '' })).toBe('Write notes.md')
    expect(lineOf('NotebookEdit', { notebook_path: '/repo/lab.ipynb', new_source: '' })).toBe('Edit lab.ipynb')
    expect(lineOf('Grep', { pattern: 'labelOf' })).toBe('Search "labelOf"')
    expect(lineOf('Glob', { pattern: '**/*.tsx' })).toBe('Search "**/*.tsx"')
    expect(lineOf('SendMessage', { to: 'main', summary: 'the review is in', message: 'Done.' })).toBe('Message to main: the review is in')
    expect(lineOf('SendMessage', { to: 'a1b2', message: 'Done.' })).toBe('Message to a1b2')
    expect(lineOf('Skill', { skill: 'doperpowers:execspec' })).toBe('Skill doperpowers:execspec')
    expect(lineOf('ToolSearch', { query: 'select:Monitor', max_results: 1 })).toBe('Tool search "select:Monitor"')
    expect(lineOf('mcp__web__fetch', { url: 'https://example.com' })).toBe('web: fetch')
    expect(lineOf('mcp__plugin_cua_cua_repl__js', { code: '1' })).toBe('plugin_cua_cua_repl: js')
    expect(lineOf('WebSearch', { query: 'x' })).toBe('WebSearch')
  })

  test('a field missing or of another type leaves the tool by name', () => {
    expect(lineOf('Bash', {})).toBe('Bash')
    expect(lineOf('Bash', { description: '  ', command: 'ls' })).toBe('ls')
    expect(lineOf('Read', { file_path: 7 })).toBe('Read')
    expect(lineOf('Read', undefined)).toBe('Read')
    expect(lineOf('Grep', {})).toBe('Grep')
    expect(lineOf('Skill', {})).toBe('Skill')
    expect(lineOf('SendMessage', {})).toBe('SendMessage')
  })

  test('a line is one line, cut at 120 characters', () => {
    expect(lineOf('Bash', { description: 'Run the tests\n  and the linter' })).toBe('Run the tests and the linter')
    const long = lineOf('Bash', { description: 'x'.repeat(200) })
    expect(Array.from(long).length).toBe(120)
    expect(long.endsWith('…')).toBe(true)
    expect(lineOf('Bash', { description: 'y'.repeat(120) })).toBe('y'.repeat(120))
    // Cut between code points, never inside one.
    expect(Array.from(lineOf('Bash', { description: '😀'.repeat(130) }))).toEqual([...Array(119).fill('😀'), '…'])
  })
})

/** Follows the rows in order, as the hooks do. */
const tracked = (...rows: KeptRow[]) => {
  const tracker = newTracker()
  for (const kept of rows) follow(tracker, stepsOf(kept, tracker.spawns))
  return tracker
}
const call = (uuid: string, id: string, description: string) => response(uuid, use(id, 'Bash', { command: 'true', description }))
const sent = (uuid: string, id: string) => response(uuid, use(id, MESSAGE_TOOL, { text: 'Update.' }))

describe('follow: the runs the rows make', () => {
  test("a call opens a run and sets its live line; the newest call's line wins", () => {
    const tracker = tracked(sent('a0', 'toolu_m0'), call('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1'), call('a2', 'toolu_2', 'Run the tests'))
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [] }, fold: { first: 'toolu_1', line: 'Run the tests', isLive: true }, foldLast: 'toolu_2' })
  })

  test('several calls in one response: the last one\'s line', () => {
    const tracker = tracked(response('a1', use('toolu_1', 'Read', { file_path: '/a/one.ts' }), use('toolu_2', 'Read', { file_path: '/a/two.ts' })))
    expect(published(tracker).fold?.line).toBe('Read two.ts')
  })

  test('a live run with no call yet carries no line', () => {
    const tracker = tracked(response('a1', text('Reading the logs.')))
    expect(published(tracker).fold).toEqual({ first: 'a1', isLive: true })
  })

  test('a read row closes the open run with its last row; the next row opens another', () => {
    const tracker = tracked(
      call('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1'),
      response('a2', text('Now the tests.')),
      sent('a3', 'toolu_m'), result('u3', 'toolu_m', MESSAGE_TOOL, 'sent'),
      call('a4', 'toolu_4', 'Run the tests'),
    )
    expect(published(tracker)).toEqual({
      // Closed with every result kept, and no summary made (M1): no longer live.
      folds: { shape: 1, runs: [{ first: 'toolu_1', last: 'a2' }] },
      fold: { first: 'toolu_4', line: 'Run the tests', isLive: true },
      foldLast: 'toolu_4',
    })
  })

  test("a run closed while one of its calls runs stays live on that call's line until its result is kept, which joins it", () => {
    // One response, a call beside a message: the message is kept, and closes the run, before the call has run.
    const tracker = tracked(response('a1', use('toolu_b', 'Bash', { command: 'make', description: 'Build it' }), use('toolu_m', MESSAGE_TOOL, { text: 'Building.' })))
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [{ first: 'toolu_b', last: 'toolu_b', line: 'Build it', isLive: true }] }, fold: null, foldLast: null })
    follow(tracker, stepsOf(result('u2', 'toolu_m', MESSAGE_TOOL, 'sent'), tracker.spawns))
    expect(published(tracker).folds.runs[0]?.isLive).toBe(true)
    follow(tracker, stepsOf(result('u3', 'toolu_b'), tracker.spawns))
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [{ first: 'toolu_b', last: 'toolu_b' }] }, fold: null, foldLast: null })
  })

  test('a mixed message closes the run before it and opens the next with its own record', () => {
    const tracker = tracked(call('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1'), response('a2', text('<message>Found it.</message>\nChecking the rest.')))
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [{ first: 'toolu_1', last: 'toolu_1' }] }, fold: { first: 'a2', isLive: true }, foldLast: 'a2' })
  })

  test('prompts taken in mid-turn stand in the run they fall in: one run', () => {
    const tracker = tracked(
      sent('a0', 'toolu_m0'),
      call('a1', 'toolu_1', 'Wait for the build'),
      row('queue', 'q1', { kind: 'engine' }, [text(notification('toolu_bg', 'completed'))]),
      result('u1', 'toolu_1'),
      userRow('d1', 'delivery', { kind: 'task-notification' }, notification('toolu_bg', 'completed')),
      userRow('d2', 'delivery', { kind: 'peer' }, 'Another Claude session sent a message: done', true),
      call('a2', 'toolu_2', 'Read the output'),
    )
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [] }, fold: { first: 'toolu_1', line: 'Read the output', isLive: true }, foldLast: 'toolu_2' })
  })

  test('a subagent\'s rows change nothing', () => {
    const before = published(tracked(call('a1', 'toolu_1', 'List the files')))
    const after = published(tracked(
      call('a1', 'toolu_1', 'List the files'),
      { ...sent('s1', 'toolu_sm'), agentId: 'a7' } as KeptRow,
      { ...call('s2', 'toolu_s', 'The agent\'s call'), agentId: 'a7' } as KeptRow,
      { ...userRow('s3', 'prompt', { kind: 'composer' }, 'go'), agentId: 'a7' } as KeptRow,
    ))
    expect(after).toEqual(before)
  })

  test('a read row with no open run, and a result of a call no run holds, change nothing', () => {
    const tracker = tracked(sent('a1', 'toolu_m'), result('u1', 'toolu_m', MESSAGE_TOOL, 'sent'), result('u2', 'toolu_unknown'))
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [] }, fold: null, foldLast: null })
  })
})

describe('takeUp: a module that starts over the runs another left', () => {
  test('the open run goes on with its live line, held not whole; a closed run left live loses the mark', () => {
    const tracker = newTracker()
    takeUp(
      tracker,
      { shape: 1, runs: [{ first: 'toolu_1', last: 'a2', summary: 'Listed the files' }, { first: 'toolu_3', last: 'toolu_3', line: 'Build it', isLive: true }] },
      { first: 'toolu_5', line: 'Run the tests', isLive: true },
      'toolu_5',
    )
    expect(tracker.open?.isWhole).toBe(false)
    expect(published(tracker).folds.runs).toEqual([{ first: 'toolu_1', last: 'a2', summary: 'Listed the files' }, { first: 'toolu_3', last: 'toolu_3' }])
    follow(tracker, stepsOf(call('a6', 'toolu_6', 'Lint it'), tracker.spawns))
    expect(published(tracker)).toMatchObject({ fold: { first: 'toolu_5', line: 'Lint it', isLive: true }, foldLast: 'toolu_6' })
    follow(tracker, stepsOf(result('u6', 'toolu_6'), tracker.spawns))
    follow(tracker, stepsOf(sent('a7', 'toolu_m'), tracker.spawns))
    expect(published(tracker).folds.runs.at(-1)).toEqual({ first: 'toolu_5', last: 'toolu_6' })
  })

  test('a taken-up open run that no row joins after closes with the last bound it was published with', () => {
    const tracker = newTracker()
    takeUp(tracker, { shape: 1, runs: [] }, { first: 'toolu_5', line: 'Run the tests', isLive: true }, 'a9')
    follow(tracker, stepsOf(sent('a10', 'toolu_m'), tracker.spawns))
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [{ first: 'toolu_5', last: 'a9' }] }, fold: null, foldLast: null })
  })

  test('nothing kept, or a value of another shape, starts empty', () => {
    const tracker = newTracker()
    takeUp(tracker, undefined, undefined, undefined)
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [] }, fold: null, foldLast: null })
    takeUp(tracker, { shape: 2, runs: 'no' } as unknown as Folds, 'x' as unknown as OpenFold, 7 as unknown as string)
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [] }, fold: null, foldLast: null })
  })
})

describe('labelOf: the run a row stands in, by place', () => {
  const placed = (ids: string[]) => {
    const view = newView(() => true)
    ids.forEach((id, i) => view.place.set(id, i))
    return view
  }
  // m0 | toolu_1 a2 | m3 | toolu_4 a5 | m6 | toolu_7 toolu_8 (open)
  const view = placed(['m0', 'toolu_1', 'a2', 'm3', 'toolu_4', 'a5', 'm6', 'toolu_7', 'toolu_8'])
  const folds: Folds = { shape: 1, runs: [{ first: 'toolu_1', last: 'a2', summary: 'Listed the files' }, { first: 'toolu_4', last: 'a5', line: 'Build it', isLive: true }] }
  const open: OpenFold = { first: 'toolu_7', last: 'toolu_8', line: 'Run the tests', isLive: true }

  test('any row of a closed run reads its label, live or settled', () => {
    expect(labelOf(folds, open, view, 'toolu_1')).toBe('Listed the files')
    expect(labelOf(folds, open, view, 'a2')).toBe('Listed the files')
    expect(labelOf(folds, open, view, 'a5')).toBe('Build it')
  })

  test('any row at or after the open run\'s first reads the open run\'s; a group by its first call', () => {
    expect(labelOf(folds, open, view, 'toolu_7')).toBe('Run the tests')
    expect(labelOf(folds, open, view, 'toolu_8')).toBe('Run the tests')
    expect(labelOf(folds, open, view, 'group:toolu_7')).toBe('Run the tests')
    expect(labelOf(folds, open, view, 'group:toolu_1')).toBe('Listed the files')
  })

  test('a row outside every run, or without a known place, reads nothing', () => {
    expect(labelOf(folds, open, view, 'm0')).toBeUndefined()
    expect(labelOf(folds, open, view, 'm3')).toBeUndefined()
    expect(labelOf(folds, open, view, 'unplaced')).toBeUndefined()
    // A place the view only guessed (a row drawn before it was kept) is not one.
    view.guess.set('guessed', 7.5)
    expect(labelOf(folds, open, view, 'guessed')).toBeUndefined()
    expect(labelOf(undefined, undefined, view, 'toolu_1')).toBeUndefined()
  })

  test('a run whose bound has no known place holds no row', () => {
    const lost: Folds = { shape: 1, runs: [{ first: 'toolu_1', last: 'gone', summary: 'Listed the files' }] }
    expect(labelOf(lost, null, view, 'toolu_1')).toBeUndefined()
    expect(labelOf(folds, { first: 'gone', isLive: true, line: 'x' }, view, 'toolu_8')).toBeUndefined()
  })

  test('a live run with no call reads its summary, or nothing; a run not live reads only its summary', () => {
    expect(labelOf(folds, { first: 'toolu_7', isLive: true, summary: 'Ran the tests' }, view, 'toolu_8')).toBe('Ran the tests')
    expect(labelOf(folds, { first: 'toolu_7', isLive: true }, view, 'toolu_8')).toBeUndefined()
    expect(labelOf(folds, { first: 'toolu_7', line: 'stale' }, view, 'toolu_8')).toBeUndefined()
    expect(labelOf(folds, { first: 'toolu_7', line: 'stale', summary: 'Ran the tests' }, view, 'toolu_8')).toBe('Ran the tests')
  })
})

/** A model call the hand-made engine holds until the test answers it. */
type Held = { request: Record<string, unknown>; answer: (reply: unknown) => void; fail: (error: Error) => void }
const answered = (text: string) => ({ isAnswered: true, text, usage: { input_tokens: 1, output_tokens: 1 } })

type HookOptions = {
  failWrites?: boolean
  writes?: string[]
  /** The variables `$.env.get` answers; HOME by default, so the session's file is kept. */
  env?: Record<string, string>
  /** The files `$.fs` holds, by path. */
  files?: Map<string, string>
  failFile?: boolean
  /** Each write of a file waits until the test lets it land (`landWrites`). */
  holdFile?: boolean
  isOn?: () => boolean
  sessionId?: string
}

/** The tracker's hooks over a hand-made engine whose `$.state` is a map, as the host keeps it across a reload. */
function trackerHooks(kept = new Map<string, unknown>(), options: HookOptions = {}) {
  const { failWrites = false, writes = [], env = { HOME: '/home/u' }, files = new Map<string, string>(), failFile = false, holdFile = false, isOn = () => true, sessionId = 's1' } = options
  const landing: (() => void)[] = []
  /** Lets every held write of a file land. */
  const landWrites = () => landing.splice(0).forEach((land) => land())
  type Hook = (engine: EngineInterface, e: Record<string, unknown>, next: (e: unknown) => Promise<unknown>) => Promise<unknown>
  const hooks: { event: string; handler: Hook }[] = []
  const on = ((event: string, ...rest: unknown[]) => hooks.push({ event, handler: rest[rest.length - 1] as Hook })) as unknown as On
  registerFolds(on, newView(() => true), isOn)
  const logs: string[] = []
  const held: Held[] = []
  const runs: (readonly string[])[] = []
  const engine = {
    state: {
      get: async (ref: { key: string }) => ({ value: kept.get(ref.key), version: 0 }),
      set: async (ref: { key: string }, value: unknown) => {
        if (failWrites) throw new Error('refused')
        writes.push(ref.key)
        kept.set(ref.key, value)
        return { isSet: true, version: 1 }
      },
    },
    ui: { log: (line: string) => logs.push(line) },
    env: { get: async (name: string) => env[name] },
    session: { id: async () => sessionId },
    fs: {
      exists: async (path: string) => files.has(path) || [...files.keys()].some((file) => file.startsWith(`${path}/`)),
      read: async (path: string) => {
        const file = files.get(path)
        if (file === undefined) throw new Error(`ENOENT: ${path}`)
        return file
      },
      write: async (path: string, value: string) => {
        if (failFile) throw new Error('disk full')
        if (holdFile) await new Promise<void>((land) => landing.push(land))
        files.set(path, value)
      },
    },
    process: {
      run: async (argv: readonly string[]) => {
        runs.push(argv)
        return { exitCode: 0, stdout: '', stderr: '' }
      },
    },
    model: {
      complete: (request: Record<string, unknown>) =>
        new Promise((resolve, reject) => held.push({ request, answer: resolve, fail: reject })),
    },
  } as unknown as EngineInterface
  const hook = (event: string) => hooks.find((h) => h.event === event)!.handler
  const append = async (kept: KeptRow) => {
    const stored = { message: kept.message, uuid: kept.uuid }
    const answer = await hook('session.append')(engine, kept as unknown as Record<string, unknown>, async () => stored)
    expect(answer).toBe(stored)
  }
  const start = (isInteractive = true) => hook('session.start')(engine, { cwd: '/w', surface: 'terminal', isInteractive }, async (e) => e)
  const sessionStart = (source: string, session_id = sessionId) => hook('classic.SessionStart')(engine, { source, session_id }, async () => ({}))
  const turnEnd = (agentId?: string) =>
    hook('turn.complete')(engine, { turnId: 't1', answer: '', durationMs: 1, isAborted: false, reason: 'answer', ...(agentId !== undefined && { agentId }) }, async () => ({ text: '' }))
  /** Lets the chained writes land. */
  const settle = () => Promise.resolve().then(() => undefined)
  return { kept, logs, held, files, runs, append, start, sessionStart, turnEnd, settle, landWrites }
}

const drain = async (settle: () => Promise<void>) => {
  for (let i = 0; i < 10; i++) await settle()
}

describe('registerFolds: the hooks', () => {
  test('publishes the runs in $.state as rows are kept, and hands every row on as it was stored', async () => {
    const h = trackerHooks()
    await h.start()
    await h.append(sent('a0', 'toolu_m0'))
    await h.append(call('a1', 'toolu_1', 'List the files'))
    await drain(h.settle)
    expect(h.kept.get('fold')).toEqual({ first: 'toolu_1', line: 'List the files', isLive: true })
    expect(h.kept.get('foldLast')).toBe('toolu_1')
    await h.append(sent('a2', 'toolu_m'))
    await drain(h.settle)
    expect(h.kept.get('fold')).toBeNull()
    expect(h.kept.get('foldLast')).toBeNull()
    expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [{ first: 'toolu_1', last: 'toolu_1', line: 'List the files', isLive: true }] })
  })

  test('a module that starts over an open run in $.state goes on with its live line', async () => {
    const first = trackerHooks()
    await first.start()
    await first.append(call('a1', 'toolu_1', 'List the files'))
    await drain(first.settle)
    // A reload: the module's variables start over, the host's state stays.
    const second = trackerHooks(first.kept)
    await second.start()
    await second.append(call('a2', 'toolu_2', 'Run the tests'))
    await drain(second.settle)
    expect(second.kept.get('fold')).toEqual({ first: 'toolu_1', line: 'Run the tests', isLive: true })
    expect(second.kept.get('foldLast')).toBe('toolu_2')
  })

  test('a taken-up open run still closes with its last bound', async () => {
    const first = trackerHooks()
    await first.start()
    await first.append(call('a1', 'toolu_1', 'List the files'))
    await first.append(response('a2', text('Now the tests.')))
    await drain(first.settle)
    const second = trackerHooks(first.kept)
    await second.start()
    await second.append(sent('a3', 'toolu_m'))
    await drain(second.settle)
    expect(second.kept.get('folds')).toEqual({ shape: 1, runs: [{ first: 'toolu_1', last: 'a2' }] })
  })

  test('a note, a delivery or a result joining the open run writes foldLast, never fold, which the buttons read', async () => {
    const writes: string[] = []
    const kept = new Map<string, unknown>()
    const h = trackerHooks(kept, { writes })
    await h.start()
    await h.append(sent('a0', 'toolu_m0'))
    await h.append(call('a1', 'toolu_1', 'Wait for the build'))
    await drain(h.settle)
    writes.length = 0
    await h.append(result('u1', 'toolu_1'))
    await h.append(response('a2', text('Reading the output.')))
    await h.append(userRow('d1', 'delivery', { kind: 'task-notification' }, notification('toolu_bg', 'completed')))
    await drain(h.settle)
    expect(writes).toEqual(['foldLast', 'foldLast'])
    expect(kept.get('foldLast')).toBe('d1')
    expect(kept.get('fold')).toEqual({ first: 'toolu_1', line: 'Wait for the build', isLive: true })
  })

  test('rows kept before the start-up read lands wait for it, in order', async () => {
    const kept = new Map<string, unknown>([['fold', { first: 'toolu_1', line: 'List the files', isLive: true }], ['foldLast', 'toolu_1']])
    const h = trackerHooks(kept)
    // No session.start first: the first row begins the read.
    await h.append(call('a2', 'toolu_2', 'Run the tests'))
    await h.append(call('a3', 'toolu_3', 'Lint it'))
    await drain(h.settle)
    expect(h.kept.get('fold')).toEqual({ first: 'toolu_1', line: 'Lint it', isLive: true })
    expect(h.kept.get('foldLast')).toBe('toolu_3')
  })

  test('a subagent\'s rows write nothing', async () => {
    const h = trackerHooks()
    await h.start()
    await h.append({ ...call('s1', 'toolu_s', 'The agent\'s call'), agentId: 'a7' } as KeptRow)
    await drain(h.settle)
    expect(h.kept.has('fold')).toBe(false)
    expect(h.kept.has('folds')).toBe(false)
  })

  test('a write that fails is logged, and the row is kept as ever', async () => {
    const h = trackerHooks(new Map(), { failWrites: true })
    await h.start()
    await h.append(call('a1', 'toolu_1', 'List the files'))
    await drain(h.settle)
    expect(h.logs.some((line) => line.includes('to-human: the folds could not be published'))).toBe(true)
  })

  test('a clear, a resume and a fork drop the runs of the conversation before', async () => {
    for (const source of ['clear', 'resume', 'fork']) {
      const h = trackerHooks()
      await h.start()
      await h.append(call('a1', 'toolu_1', 'List the files'))
      await h.append(sent('a2', 'toolu_m'))
      await h.append(call('a3', 'toolu_3', 'Run the tests'))
      await h.sessionStart(source)
      await drain(h.settle)
      expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [] })
      expect(h.kept.get('fold')).toBeNull()
      expect(h.kept.get('foldLast')).toBeNull()
    }
  })
})

// Summaries: which closes ask, with which digest, and what a reply does.

const END: Step[] = [{ kind: 'end' }]
/** Follows the rows in order as a session that asks for summaries does; the asks they made. */
const asked = (tracker: ReturnType<typeof newTracker>, ...rows: (KeptRow | 'end')[]): Ask[] =>
  rows.flatMap((kept) => follow(tracker, kept === 'end' ? END : stepsOf(kept, tracker.spawns), true))
const bash = (uuid: string, id: string, description: string, command = 'true') => response(uuid, use(id, 'Bash', { command, description }))

describe('follow: when a run is asked for its summary', () => {
  const RUN = 'NOTE Checking the build.\n\nCALL Bash — Build it\n$ make\n\nRESULT built'
  const before = (): KeptRow[] => [sent('a0', 'toolu_m0'), response('a1', text('Checking the build.')), bash('a2', 'toolu_2', 'Build it', 'make'), result('u2', 'toolu_2', 'Bash', 'built')]
  const closers: [string, KeptRow][] = [
    ['a message call', sent('c1', 'toolu_c')],
    ['a marked text', response('c1', text('<message>Built.</message>'))],
    ['a spawn', response('c1', use('toolu_c', 'Agent', { prompt: 'go' }))],
    ['a question', response('c1', use('toolu_c', 'AskUserQuestion', { questions: [] }))],
    ["the person's prompt", userRow('c1', 'prompt', { kind: 'composer' }, 'Next.')],
    ["the person's prompt typed into the turn", userRow('c1', 'delivery', { kind: 'composer' }, 'Next.')],
    ['an API error', { ...response('c1', text('API Error: 500')), origin: { kind: 'model', model: '<synthetic>' } } as KeptRow],
    ['a compaction', row('compaction', 'c1')],
  ]

  for (const [name, closer] of closers) {
    test(`a close at ${name} asks once, with the digest of exactly that run`, () => {
      const tracker = newTracker()
      expect(asked(tracker, ...before())).toEqual([])
      expect(asked(tracker, closer).map((ask) => ask.digest)).toEqual([RUN])
      // Asked, the run stays live on its last call's line until the reply settles.
      expect(published(tracker).folds.runs).toEqual([{ first: 'a1', last: 'toolu_2', line: 'Build it', isLive: true }])
      // Another read row, and a turn's end, ask nothing more.
      expect(asked(tracker, sent('c2', 'toolu_c2'), 'end')).toEqual([])
    })
  }

  test("the failure of a shown spawn closes the run after the spawn, its digest that run's alone", () => {
    const tracker = newTracker()
    const spawn = asked(tracker, ...before(), response('s1', use('toolu_agent', 'Agent', { prompt: 'go' })))
    expect(spawn.map((ask) => ask.digest)).toEqual([RUN])
    const failed = asked(tracker, bash('a3', 'toolu_3', 'Wait'), result('u3', 'toolu_3'), userRow('f1', 'delivery', { kind: 'task-notification' }, notification('toolu_agent', 'failed')))
    expect(failed.map((ask) => ask.digest)).toEqual(['CALL Bash — Wait\n$ true\n\nRESULT ok'])
  })

  test("a mixed message's own record opens the next run's digest", () => {
    const tracker = newTracker()
    asked(tracker, ...before(), response('m1', text('<message>Built.</message>\nNow the tests.')), bash('a3', 'toolu_3', 'Test it'), result('u3', 'toolu_3'))
    expect(asked(tracker, sent('c1', 'toolu_c')).map((ask) => ask.digest)).toEqual([
      'NOTE <message>Built.</message>\nNow the tests.\n\nCALL Bash — Test it\n$ true\n\nRESULT ok',
    ])
  })

  test('a run closed while one of its calls runs is asked for when that result is kept, with the result in its digest', () => {
    const tracker = newTracker()
    const closing = response('a1', use('toolu_b', 'Bash', { command: 'make', description: 'Build it' }), use('toolu_m', MESSAGE_TOOL, { text: 'Building.' }))
    expect(asked(tracker, closing, result('u1', 'toolu_m', MESSAGE_TOOL, 'sent'))).toEqual([])
    expect(asked(tracker, result('u2', 'toolu_b', 'Bash', 'built')).map((ask) => ask.digest)).toEqual(['CALL Bash — Build it\n$ make\n\nRESULT built'])
  })

  test("a run whose call's result never comes is asked for at the turn's end, and again if the result comes after all", () => {
    const tracker = newTracker()
    asked(tracker, response('a1', use('toolu_b', 'Bash', { command: 'make', description: 'Build it' }), use('toolu_m', MESSAGE_TOOL, { text: 'Building.' })))
    const atEnd = asked(tracker, 'end')
    expect(atEnd.map((ask) => ask.digest)).toEqual(['CALL Bash — Build it\n$ make'])
    const late = asked(tracker, result('u2', 'toolu_b', 'Bash', 'built'))
    expect(late.map((ask) => ask.digest)).toEqual(['CALL Bash — Build it\n$ make\n\nRESULT built'])
    expect(late[0]!.generation).not.toBe(atEnd[0]!.generation)
  })

  test("a turn's end asks for the open run; a later row makes it live again, and the next close asks for the whole run", () => {
    const tracker = newTracker()
    asked(tracker, sent('a0', 'toolu_m0'), bash('a1', 'toolu_1', 'List the files', 'ls'), result('u1', 'toolu_1'))
    const atEnd = asked(tracker, 'end')
    expect(atEnd.map((ask) => ask.digest)).toEqual(['CALL Bash — List the files\n$ ls\n\nRESULT ok'])
    expect(atEnd[0]!.run).toBe(tracker.open!)
    expect(asked(tracker, bash('a2', 'toolu_2', 'Run the tests', 'npm test'), result('u2', 'toolu_2'))).toEqual([])
    expect(published(tracker).fold).toEqual({ first: 'toolu_1', line: 'Run the tests', isLive: true })
    const closed = asked(tracker, sent('a3', 'toolu_m'))
    expect(closed.map((ask) => ask.digest)).toEqual(['CALL Bash — List the files\n$ ls\n\nRESULT ok\n\nCALL Bash — Run the tests\n$ npm test\n\nRESULT ok'])
    expect(closed[0]!.generation).toBeGreaterThan(atEnd[0]!.generation)
  })

  test("an open run asked for at a turn's end and closed with nothing new is not asked again", () => {
    const tracker = newTracker()
    asked(tracker, bash('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1'))
    expect(asked(tracker, 'end')).toHaveLength(1)
    expect(asked(tracker, userRow('p1', 'prompt', { kind: 'composer' }, 'Thanks.'))).toEqual([])
  })

  test("a turn's end with nothing new asks nothing", () => {
    const tracker = newTracker()
    expect(asked(tracker, 'end')).toEqual([])
    asked(tracker, bash('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1'), sent('a2', 'toolu_m'))
    expect(asked(tracker, 'end')).toEqual([])
    asked(tracker, bash('a3', 'toolu_3', 'Lint it'), result('u3', 'toolu_3'))
    expect(asked(tracker, 'end')).toHaveLength(1)
    expect(asked(tracker, 'end')).toEqual([])
  })

  test('a run not held whole is never asked for: it settles on what it had', () => {
    const tracker = newTracker()
    takeUp(tracker, { shape: 1, runs: [] }, { first: 'toolu_5', line: 'Run the tests', isLive: true, summary: 'Ran the tests' }, 'toolu_5')
    expect(asked(tracker, bash('a6', 'toolu_6', 'Lint it'), result('u6', 'toolu_6'), 'end')).toEqual([])
    expect(published(tracker).fold).toEqual({ first: 'toolu_5', summary: 'Ran the tests' })
    expect(asked(tracker, bash('a7', 'toolu_7', 'Build it'), result('u7', 'toolu_7'), sent('a8', 'toolu_m'))).toEqual([])
    expect(published(tracker).folds.runs).toEqual([{ first: 'toolu_5', last: 'toolu_7', summary: 'Ran the tests' }])
  })

  test("a session that does not ask settles each run at once, the open one at its turn's end", () => {
    const tracker = newTracker()
    for (const kept of [bash('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1')]) expect(follow(tracker, stepsOf(kept, tracker.spawns), false)).toEqual([])
    expect(follow(tracker, END, false)).toEqual([])
    expect(published(tracker).fold).toEqual({ first: 'toolu_1' })
  })
})

describe('the digest: what the model reads of a run', () => {
  const digestOf = (...rows: KeptRow[]) => {
    const tracker = newTracker()
    asked(tracker, ...rows)
    return asked(tracker, sent('z', 'toolu_z'), 'end')[0]!.digest
  }

  test("each part's shape", () => {
    expect(digestOf(
      response('a1', text('  Reading the logs.  ')),
      response('a2', use('toolu_1', 'Bash', { command: 'ls -la' })),
      result('u1', 'toolu_1', 'Bash', 'total 0'),
      response('a3', use('toolu_2', 'Read', { file_path: '/repo/src/fold.ts' })),
      result('u2', 'toolu_2', 'Read', 'export {}'),
      response('a4', use('toolu_3', 'Grep', { path: '/repo', pattern: 'labelOf', output_mode: 'content' })),
      response('a5', use('toolu_4', 'NotebookEdit', { notebook_path: '/repo/lab.ipynb', new_source: 'x' })),
      response('a6', use('toolu_5', 'WebSearch', { query: 'fold summaries' })),
      row('tool-result', 'u3', { kind: 'tool', tool: 'Grep' }, [{ type: 'tool_result', tool_use_id: 'toolu_3', is_error: true, content: 'bad regex' }]),
      userRow('d1', 'delivery', { kind: 'task-notification' }, notification('toolu_bg', 'completed')),
    )).toBe([
      'NOTE Reading the logs.',
      'CALL Bash\n$ ls -la',
      'RESULT total 0',
      'CALL Read /repo/src/fold.ts',
      'RESULT export {}',
      'CALL Grep /repo pattern="labelOf"',
      'CALL NotebookEdit /repo/lab.ipynb',
      'CALL WebSearch {"query":"fold summaries"}',
      'RESULT (error) bad regex',
      `DELIVERED ${notification('toolu_bg', 'completed')}`,
    ].join('\n\n'))
  })

  test('each part is cut as it is added', () => {
    const [note, command, query, delivery] = ['n'.repeat(1600), 'c'.repeat(700), 'q'.repeat(500), 'd'.repeat(650)]
    const output = `${'h'.repeat(600)}${'m'.repeat(500)}${'t'.repeat(400)}`
    const input = JSON.stringify({ query })
    expect(digestOf(
      response('a1', text(note)),
      response('a2', use('toolu_1', 'Bash', { command, description: 'Run it' })),
      result('u1', 'toolu_1', 'Bash', output),
      response('a3', use('toolu_2', 'WebSearch', { query })),
      userRow('d1', 'delivery', { kind: 'peer' }, delivery, true),
    )).toBe([
      `NOTE ${'n'.repeat(1500)} …[100 more chars]`,
      `CALL Bash — Run it\n$ ${'c'.repeat(600)} …[100 more chars]`,
      `RESULT ${'h'.repeat(600)}\n…[500 chars cut]…\n${'t'.repeat(400)}`,
      `CALL WebSearch ${input.slice(0, 400)} …[${input.length - 400} more chars]`,
      `DELIVERED ${'d'.repeat(600)} …[50 more chars]`,
    ].join('\n\n'))
  })

  test('a digest over 60,000 characters keeps its start to 40% and its end to 60%, saying how many rows were left out', () => {
    // Each note is 1,505 characters: 15 fit in 24,000, 23 in 36,000.
    const notes = Array.from({ length: 100 }, (_, i) => response(`a${i}`, text(`${String(i).padStart(3, '0')}${'x'.repeat(1497)}`)))
    const parts = digestOf(...notes).split('\n\n')
    expect(parts).toHaveLength(15 + 1 + 23)
    expect(parts.slice(0, 15).map((part) => part.slice(5, 8))).toEqual(Array.from({ length: 15 }, (_, i) => String(i).padStart(3, '0')))
    expect(parts[15]).toBe('…[62 rows of the run omitted here]…')
    expect(parts.slice(16).map((part) => part.slice(5, 8))).toEqual(Array.from({ length: 23 }, (_, i) => String(77 + i).padStart(3, '0')))
  })

  test('the cap counts the digest as joined, its separators and the omission line with it', () => {
    // 39 parts of 1,505 characters and one of 1,227, joined by 39 blank lines: exactly 60,000.
    const notes = (last: number) => [
      ...Array.from({ length: 39 }, (_, i) => response(`a${i}`, text('y'.repeat(1500)))),
      response('a39', text('z'.repeat(last))),
    ]
    const whole = digestOf(...notes(1222))
    expect(whole.length).toBe(60_000)
    expect(whole.split('\n\n')).toHaveLength(40)
    const capped = digestOf(...notes(1223))
    expect(capped.length).toBeLessThanOrEqual(60_000)
    expect(capped.split('\n\n')).toContain('…[1 rows of the run omitted here]…')
    // A last part of 1,330 leaves an end of 35,991 characters, within 60% of the cap but not with the omission line beside it.
    const tight = digestOf(...notes(1325))
    expect(tight.length).toBeLessThanOrEqual(60_000)
    expect(tight.split('\n\n')).toContain('…[2 rows of the run omitted here]…')
    // 40 notes of 1,495 characters: their parts alone are 60,000, their joined text 60,078.
    const close = digestOf(...Array.from({ length: 40 }, (_, i) => response(`b${i}`, text('x'.repeat(1495)))))
    expect(close.length).toBeLessThanOrEqual(60_000)
    expect(close).toContain('rows of the run omitted here')
  })
})

describe('summaryOf: the reply as a summary', () => {
  test("the reply's first non-empty line, trimmed, cut at 120 characters", () => {
    expect(summaryOf('\n\n  Fixed the build: 3 tests pass  \nA second line.')).toBe('Fixed the build: 3 tests pass')
    expect(Array.from(summaryOf('z'.repeat(130))!)).toEqual([...Array(119).fill('z'), '…'])
    expect(summaryOf('w'.repeat(120))).toBe('w'.repeat(120))
  })

  test('an empty reply is none', () => {
    expect(summaryOf('')).toBeUndefined()
    expect(summaryOf('  \n \n')).toBeUndefined()
  })
})

const FILE = '/home/u/.claude/to-human/folds/s1.json'
const stored = (files: Map<string, string>, path = FILE) => (files.has(path) ? JSON.parse(files.get(path)!) : undefined)

/** A session that asks: started interactive, its first message sent. */
const asking = async (h: ReturnType<typeof trackerHooks>) => {
  await h.start()
  await h.append(sent('a0', 'toolu_m0'))
}

describe('registerFolds: summaries', () => {
  test("a close asks the session's model once, and its reply settles the run's summary in $.state and in the session's file", async () => {
    const h = trackerHooks()
    await asking(h)
    await h.append(bash('a1', 'toolu_1', 'List the files', 'ls'))
    await h.append(result('u1', 'toolu_1'))
    await h.append(sent('a2', 'toolu_m'))
    await drain(h.settle)
    expect(h.held.map((ask) => ask.request)).toEqual([{
      model: 'haiku',
      system: LABEL_SYSTEM,
      prompt: '<stretch>\nCALL Bash — List the files\n$ ls\n\nRESULT ok\n</stretch>',
      effort: 'high',
      maxTokens: 4000,
      timeoutMs: 30_000,
    }])
    expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [{ first: 'toolu_1', last: 'toolu_1', line: 'List the files', isLive: true }] })
    h.held[0]!.answer(answered('Listed the files'))
    await drain(h.settle)
    expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [{ first: 'toolu_1', last: 'toolu_1', summary: 'Listed the files' }] })
    expect(stored(h.files)).toEqual({ shape: 1, runs: [['toolu_1', 'toolu_1', 'Listed the files']] })
  })

  test('TO_HUMAN_FOLD_MODEL names the model, and CLAUDE_CONFIG_DIR the folder of the file', async () => {
    const h = trackerHooks(new Map(), { env: { HOME: '/home/u', CLAUDE_CONFIG_DIR: '/cfg', TO_HUMAN_FOLD_MODEL: 'claude-nope-0' } })
    await asking(h)
    await h.append(bash('a1', 'toolu_1', 'List the files'))
    await h.append(result('u1', 'toolu_1'))
    await h.append(sent('a2', 'toolu_m'))
    await drain(h.settle)
    expect(h.held[0]!.request.model).toBe('claude-nope-0')
    h.held[0]!.answer(answered('Listed the files'))
    await drain(h.settle)
    expect(stored(h.files, '/cfg/to-human/folds/s1.json')).toEqual({ shape: 1, runs: [['toolu_1', 'toolu_1', 'Listed the files']] })
  })

  test("two runs' replies settling in the reverse order leave both summaries in $.state and in the session's file", async () => {
    const h = trackerHooks()
    await asking(h)
    await h.append(bash('a1', 'toolu_1', 'List the files'))
    await h.append(result('u1', 'toolu_1'))
    await h.append(sent('a2', 'toolu_m2'))
    await h.append(bash('a3', 'toolu_3', 'Run the tests'))
    await h.append(result('u3', 'toolu_3'))
    await h.append(sent('a4', 'toolu_m4'))
    await drain(h.settle)
    expect(h.held).toHaveLength(2)
    h.held[1]!.answer(answered('Ran the tests: 12 pass'))
    await drain(h.settle)
    h.held[0]!.answer(answered('Listed the files'))
    await drain(h.settle)
    expect(h.kept.get('folds')).toEqual({
      shape: 1,
      runs: [{ first: 'toolu_1', last: 'toolu_1', summary: 'Listed the files' }, { first: 'toolu_3', last: 'toolu_3', summary: 'Ran the tests: 12 pass' }],
    })
    expect(stored(h.files)).toEqual({ shape: 1, runs: [['toolu_1', 'toolu_1', 'Listed the files'], ['toolu_3', 'toolu_3', 'Ran the tests: 12 pass']] })
  })

  test("a turn's end summarizes the open run, which the file keeps with the last row its summary covered; a late reply for an earlier generation changes nothing", async () => {
    const h = trackerHooks()
    await asking(h)
    await h.append(bash('a1', 'toolu_1', 'List the files'))
    await h.append(result('u1', 'toolu_1'))
    await h.turnEnd()
    await drain(h.settle)
    h.held[0]!.answer(answered('Listed the files'))
    await drain(h.settle)
    expect(h.kept.get('fold')).toEqual({ first: 'toolu_1', summary: 'Listed the files' })
    expect(stored(h.files)).toEqual({ shape: 1, runs: [['toolu_1', 'toolu_1', 'Listed the files']] })

    // The session works on: live again, the summary kept under the new call's line.
    await h.append(bash('a2', 'toolu_2', 'Run the tests'))
    await h.turnEnd()
    await h.append(bash('a3', 'toolu_3', 'Lint it'))
    await drain(h.settle)
    expect(h.held).toHaveLength(2)
    h.held[1]!.answer(answered('Ran the tests'))
    await drain(h.settle)
    expect(h.kept.get('fold')).toEqual({ first: 'toolu_1', line: 'Lint it', summary: 'Listed the files', isLive: true })
    expect(stored(h.files)).toEqual({ shape: 1, runs: [['toolu_1', 'toolu_1', 'Listed the files']] })

    // The close asks for the whole run.
    await h.append(result('u2', 'toolu_2'))
    await h.append(result('u3', 'toolu_3'))
    await h.append(sent('a4', 'toolu_m'))
    await drain(h.settle)
    expect(h.held).toHaveLength(3)
    expect(h.held[2]!.request.prompt).toBe('<stretch>\nCALL Bash — List the files\n$ true\n\nRESULT ok\n\nCALL Bash — Run the tests\n$ true\n\nCALL Bash — Lint it\n$ true\n\nRESULT ok\n\nRESULT ok\n</stretch>')
    h.held[2]!.answer(answered('Listed the files, ran the tests and linted'))
    await drain(h.settle)
    expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [{ first: 'toolu_1', last: 'toolu_3', summary: 'Listed the files, ran the tests and linted' }] })
    expect(stored(h.files)).toEqual({ shape: 1, runs: [['toolu_1', 'toolu_3', 'Listed the files, ran the tests and linted']] })
  })

  test("the file bounds the open run by the last row its summary covered, not the rows that joined after", async () => {
    const h = trackerHooks()
    await asking(h)
    await h.append(bash('a1', 'toolu_1', 'List the files'))
    await h.append(result('u1', 'toolu_1'))
    await h.append(sent('a2', 'toolu_m'))
    await h.append(bash('a3', 'toolu_3', 'Run the tests'))
    await h.append(result('u3', 'toolu_3'))
    await h.append(response('a4', text('The tests pass.')))
    await h.turnEnd()
    await drain(h.settle)
    h.held[1]!.answer(answered('Ran the tests'))
    await drain(h.settle)
    // The open run grows; the closed run's reply then writes the file whole.
    await h.append(bash('a5', 'toolu_5', 'Lint it'))
    h.held[0]!.answer(answered('Listed the files'))
    await drain(h.settle)
    expect(stored(h.files)).toEqual({ shape: 1, runs: [['toolu_1', 'toolu_1', 'Listed the files'], ['toolu_3', 'a4', 'Ran the tests']] })
  })

  test("a result kept after the open run's turn-end summary makes it live again, and the next turn's end asks with it", async () => {
    const h = trackerHooks()
    await asking(h)
    // An interrupted call: the turn ends before its result is kept.
    await h.append(bash('a1', 'toolu_1', 'Wait for the build'))
    await h.turnEnd()
    await drain(h.settle)
    h.held[0]!.answer(answered('Waited for the build'))
    await drain(h.settle)
    expect(h.kept.get('fold')).toEqual({ first: 'toolu_1', summary: 'Waited for the build' })
    await h.append(result('u1', 'toolu_1', 'Bash', 'interrupted'))
    await h.turnEnd()
    await drain(h.settle)
    expect(h.kept.get('fold')).toEqual({ first: 'toolu_1', summary: 'Waited for the build', isLive: true })
    expect(h.held[1]!.request.prompt).toBe('<stretch>\nCALL Bash — Wait for the build\n$ true\n\nRESULT interrupted\n</stretch>')
  })

  test("a subagent's turn end asks nothing", async () => {
    const h = trackerHooks()
    await asking(h)
    await h.append(bash('a1', 'toolu_1', 'List the files'))
    await h.append(result('u1', 'toolu_1'))
    await h.turnEnd('a7')
    await drain(h.settle)
    expect(h.held).toEqual([])
  })

  for (const [name, reply] of [
    ['unanswered', () => ({ isAnswered: false, reason: 'api-error', status: 404, error: 'invalid_request', usage: {} })],
    ['empty', () => answered('  \n')],
    ['thrown', () => new Error('the model is blocked')],
  ] as const) {
    test(`a call ${name} leaves the run's summary as it was, and the run no longer live`, async () => {
      const h = trackerHooks()
      await asking(h)
      await h.append(bash('a1', 'toolu_1', 'List the files'))
      await h.append(result('u1', 'toolu_1'))
      await h.turnEnd()
      await drain(h.settle)
      h.held[0]!.answer(answered('Listed the files'))
      await drain(h.settle)
      await h.append(bash('a2', 'toolu_2', 'Run the tests'))
      await h.append(result('u2', 'toolu_2'))
      await h.append(sent('a3', 'toolu_m'))
      await drain(h.settle)
      const outcome = reply()
      if (outcome instanceof Error) h.held[1]!.fail(outcome)
      else h.held[1]!.answer(outcome)
      await drain(h.settle)
      expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [{ first: 'toolu_1', last: 'toolu_2', summary: 'Listed the files' }] })
      expect(stored(h.files)).toEqual({ shape: 1, runs: [['toolu_1', 'toolu_1', 'Listed the files']] })
      expect(h.logs.some((line) => line.startsWith("to-human: a fold's summary"))).toBe(true)
    })
  }

  const gates: [string, HookOptions, boolean?][] = [
    ['before a mark', { isOn: () => false }],
    ['when not interactive', {}, false],
    ['under MAWS', { env: { HOME: '/home/u', MAWS_NATIVE_TO_HUMAN: '8' } }],
    ['under SMNS_INTERNAL', { env: { HOME: '/home/u', SMNS_INTERNAL: '1' } }],
  ]
  for (const [name, options, isInteractive = true] of gates) {
    test(`no call ${name}: each run settles on what it had`, async () => {
      const h = trackerHooks(new Map(), options)
      await h.start(isInteractive)
      // The person's prompts close the runs: no row of this session is a mark.
      await h.append(userRow('p0', 'prompt', { kind: 'composer' }, 'List them.'))
      await h.append(bash('a1', 'toolu_1', 'List the files'))
      await h.append(result('u1', 'toolu_1'))
      await h.append(userRow('p1', 'prompt', { kind: 'composer' }, 'Now the tests.'))
      await h.append(bash('a3', 'toolu_3', 'Run the tests'))
      await h.append(result('u3', 'toolu_3'))
      await h.turnEnd()
      await drain(h.settle)
      expect(h.held).toEqual([])
      expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [{ first: 'toolu_1', last: 'toolu_1' }] })
      expect(h.kept.get('fold')).toEqual({ first: 'toolu_3' })
    })
  }

  for (const [name, mark] of [
    ['a message call', sent('a2', 'toolu_m')],
    ['a marked text', response('a2', text('<message>Listed.</message>'))],
  ] as const) {
    test(`the first run's close at ${name} kept before any mark drew is summarized: the tracker counts the mark it follows`, async () => {
      const h = trackerHooks(new Map(), { isOn: () => false })
      await h.start()
      await h.append(bash('a1', 'toolu_1', 'List the files'))
      await h.append(result('u1', 'toolu_1'))
      await h.append(mark)
      await drain(h.settle)
      expect(h.held.map((ask) => ask.request.prompt)).toEqual(['<stretch>\nCALL Bash — List the files\n$ true\n\nRESULT ok\n</stretch>'])
    })
  }

  test("a subagent's message is no mark", async () => {
    const h = trackerHooks(new Map(), { isOn: () => false })
    await h.start()
    await h.append({ ...sent('s1', 'toolu_sm'), agentId: 'a7' } as KeptRow)
    await h.append(bash('a1', 'toolu_1', 'List the files'))
    await h.append(result('u1', 'toolu_1'))
    await h.turnEnd()
    await drain(h.settle)
    expect(h.held).toEqual([])
  })

  test('MAWS_NATIVE_TO_HUMAN set empty is no MAWS', async () => {
    const h = trackerHooks(new Map(), { env: { HOME: '/home/u', MAWS_NATIVE_TO_HUMAN: '' } })
    await asking(h)
    await h.append(bash('a1', 'toolu_1', 'List the files'))
    await h.append(result('u1', 'toolu_1'))
    await h.turnEnd()
    await drain(h.settle)
    expect(h.held).toHaveLength(1)
  })

  for (const source of ['clear', 'resume', 'fork']) {
    test(`a reply held across a ${source} and then released changes neither $.state nor either session's file`, async () => {
      const files = new Map<string, string>()
      const h = trackerHooks(new Map(), { files })
      await asking(h)
      await h.append(bash('a1', 'toolu_1', 'List the files'))
      await h.append(result('u1', 'toolu_1'))
      await h.append(sent('a2', 'toolu_m'))
      await drain(h.settle)
      await h.sessionStart(source, 's2')
      await drain(h.settle)
      const after = new Map(h.kept)
      h.held[0]!.answer(answered('Listed the files'))
      await drain(h.settle)
      expect(h.kept).toEqual(after)
      expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [] })
      expect([...files.keys()]).toEqual([])
    })
  }

  test("a write of the file that fails is logged, and the summary stays in $.state", async () => {
    const h = trackerHooks(new Map(), { failFile: true })
    await asking(h)
    await h.append(bash('a1', 'toolu_1', 'List the files'))
    await h.append(result('u1', 'toolu_1'))
    await h.append(sent('a2', 'toolu_m'))
    await drain(h.settle)
    h.held[0]!.answer(answered('Listed the files'))
    await drain(h.settle)
    expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [{ first: 'toolu_1', last: 'toolu_1', summary: 'Listed the files' }] })
    expect(h.logs.some((line) => line.startsWith('to-human: the folds could not be kept'))).toBe(true)
  })
})

describe("registerFolds: the session's file", () => {
  const FOLDS_DIR = '/home/u/.claude/to-human/folds'
  const file = (...runs: [string, string, string][]) => JSON.stringify({ shape: 1, runs })

  test('a new process publishes its session\'s file as closed runs, and removes files older than 30 days', async () => {
    const files = new Map([[FILE, file(['toolu_1', 'a2', 'Listed the files'], ['toolu_3', 'toolu_4', 'Ran the tests'])]])
    const h = trackerHooks(new Map(), { files })
    await h.start()
    await drain(h.settle)
    expect(h.kept.get('folds')).toEqual({
      shape: 1,
      runs: [{ first: 'toolu_1', last: 'a2', summary: 'Listed the files' }, { first: 'toolu_3', last: 'toolu_4', summary: 'Ran the tests' }],
    })
    expect(h.runs).toEqual([['find', FOLDS_DIR, '-type', 'f', '-name', '*.json', '-mtime', '+30', '-delete']])
    // Rows after it start a run of their own, which the next write keeps beside them.
    await h.append(bash('a5', 'toolu_5', 'Lint it'))
    await h.append(result('u5', 'toolu_5'))
    await h.turnEnd()
    await drain(h.settle)
    h.held[0]!.answer(answered('Linted'))
    await drain(h.settle)
    expect(stored(files)).toEqual({ shape: 1, runs: [['toolu_1', 'a2', 'Listed the files'], ['toolu_3', 'toolu_4', 'Ran the tests'], ['toolu_5', 'toolu_5', 'Linted']] })
  })

  test("a switch away and back to a session whose summary is still being written reads its file once the write has landed", async () => {
    const files = new Map<string, string>()
    const h = trackerHooks(new Map(), { files, holdFile: true })
    await asking(h)
    await h.append(bash('a1', 'toolu_1', 'List the files'))
    await h.append(result('u1', 'toolu_1'))
    await h.turnEnd()
    await drain(h.settle)
    h.held[0]!.answer(answered('First summary'))
    await drain(h.settle)
    // The write of s1's file is held: the session goes to s2 and back before it lands.
    await h.sessionStart('resume', 's2')
    await h.sessionStart('resume', 's1')
    await drain(h.settle)
    h.landWrites()
    await drain(h.settle)
    expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [{ first: 'toolu_1', last: 'toolu_1', summary: 'First summary' }] })
    await h.append(bash('a2', 'toolu_2', 'Run the tests'))
    await h.append(result('u2', 'toolu_2'))
    await h.turnEnd()
    await drain(h.settle)
    h.held.at(-1)!.answer(answered('Second summary'))
    await drain(h.settle)
    h.landWrites()
    await drain(h.settle)
    expect(stored(files)?.runs.map((run: string[]) => run[2])).toEqual(['First summary', 'Second summary'])
  })

  test('a reload, whose $.state holds the runs, reads no file and prunes nothing', async () => {
    const files = new Map([[FILE, file(['toolu_9', 'a9', 'From the file'])]])
    const kept = new Map<string, unknown>([['folds', { shape: 1, runs: [{ first: 'toolu_1', last: 'a2', summary: 'Listed the files' }] }]])
    const h = trackerHooks(kept, { files })
    await h.start()
    await drain(h.settle)
    expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [{ first: 'toolu_1', last: 'a2', summary: 'Listed the files' }] })
    expect(h.runs).toEqual([])
  })

  test('a file of another shape, or none, publishes no runs', async () => {
    for (const files of [new Map([[FILE, '{"shape":2}']]), new Map([[FILE, 'not json']]), new Map<string, string>()]) {
      const h = trackerHooks(new Map(), { files })
      await h.start()
      await drain(h.settle)
      expect(h.kept.has('folds')).toBe(false)
    }
  })

  test('no HOME and no CLAUDE_CONFIG_DIR: summaries are made, and kept nowhere', async () => {
    const h = trackerHooks(new Map(), { env: {} })
    await asking(h)
    await h.append(bash('a1', 'toolu_1', 'List the files'))
    await h.append(result('u1', 'toolu_1'))
    await h.turnEnd()
    await drain(h.settle)
    h.held[0]!.answer(answered('Listed the files'))
    await drain(h.settle)
    expect(h.kept.get('fold')).toEqual({ first: 'toolu_1', summary: 'Listed the files' })
    expect(h.files.size).toBe(0)
    expect(h.runs).toEqual([])
  })

  for (const source of ['clear', 'resume', 'fork']) {
    test(`a ${source} publishes the file of the session it now is`, async () => {
      const files = new Map([[`${FOLDS_DIR}/s2.json`, file(['toolu_7', 'a8', 'Resumed work'])]])
      const h = trackerHooks(new Map(), { files })
      await asking(h)
      await h.append(bash('a1', 'toolu_1', 'List the files'))
      await h.sessionStart(source, 's2')
      await drain(h.settle)
      expect(h.kept.get('folds')).toEqual({ shape: 1, runs: [{ first: 'toolu_7', last: 'a8', summary: 'Resumed work' }] })
      expect(h.kept.get('fold')).toBeNull()
      // What it summarizes from here on is kept in that session's file.
      await h.append(bash('a9', 'toolu_9', 'Lint it'))
      await h.append(result('u9', 'toolu_9'))
      await h.turnEnd()
      await drain(h.settle)
      h.held.at(-1)!.answer(answered('Linted'))
      await drain(h.settle)
      expect(stored(files, `${FOLDS_DIR}/s2.json`)).toEqual({ shape: 1, runs: [['toolu_7', 'a8', 'Resumed work'], ['toolu_9', 'toolu_9', 'Linted']] })
      expect(files.has(FILE)).toBe(false)
    })
  }
})

// The view and the tracker together, through the engine's kit: the button a
// fold draws reads its run's label.

const PLUGIN = 'to-human'
const engineDrawing = (on: On) =>
  on('ui.render', (_, e) => ({ type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }))
const messageRow = ($: Engine, requestId: string, value: string) =>
  $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId, props: { text: value, isFirstOfReply: true } })
const bashRow = ($: Engine, id: string, description: string, output: unknown = 'ok') =>
  $.ui.mount({
    plugin: PLUGIN, surface: 'terminal', component: 'ToolUse', requestId: id,
    props: { tool_use_id: id, tool: 'Bash', input: { command: 'true', description }, isRunning: output === undefined, isErrored: false, isInterrupted: false, output },
  } as never)
const sentRow = ($: Engine, id: string) =>
  $.ui.mount({
    plugin: PLUGIN, surface: 'terminal', component: 'ToolUse', requestId: id,
    props: { tool_use_id: id, tool: MESSAGE_TOOL, input: { text: 'Update.' }, isRunning: false, isErrored: false, isInterrupted: false, output: 'sent' },
  } as never)
const keep = ($: Engine, ...rows: KeptRow[]) => rows.reduce((at, kept) => at.then(() => $.session.append(kept as never).then(() => {})), Promise.resolve())
/** The text of the one button a mounted row draws, if it draws one. */
const button = async (mounted: { find: (query: { type: string }) => Promise<{ text: string } | undefined> }) => (await mounted.find({ type: 'Button' }))?.text

/** The values the plugin writes under its two keys, oldest first, as another plugin observes them. */
const writes = (on: On) => {
  const seen = { fold: [] as unknown[], folds: [] as unknown[] }
  on('state.set', { plugin: 'to-human', key: 'fold' }, async (_, e, next) => (seen.fold.push(e.value), next(e)))
  on('state.set', { plugin: 'to-human', key: 'folds' }, async (_, e, next) => (seen.folds.push(e.value), next(e)))
  return seen
}

describe('the fold\'s button', () => {
  test("a live fold reads its newest call's line; a closed one with no summary reads working record (acceptance 1)", async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    await keep($, sent('a0', 'toolu_m0'), result('u0', 'toolu_m0', MESSAGE_TOOL, 'sent'))
    await sentRow($, 'toolu_m0')
    await keep($, call('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1'))
    const first = await bashRow($, 'toolu_1', 'List the files')
    expect(await button(first)).toBe('› List the files')

    await keep($, call('a2', 'toolu_2', 'Run the tests'))
    await bashRow($, 'toolu_2', 'Run the tests', undefined)
    // The button stands on the run's first row, and reads the newest call.
    expect(await button(first)).toBe('› Run the tests')

    await keep($, result('u2', 'toolu_2'), sent('a3', 'toolu_m'), result('u3', 'toolu_m', MESSAGE_TOOL, 'sent'))
    await sentRow($, 'toolu_m')
    expect(await button(first)).toBe('› working record')
  })

  test('a press unfolds the run by its label, and the fold back reads it again', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    await keep($, sent('a0', 'toolu_m0'))
    await sentRow($, 'toolu_m0')
    await keep($, call('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1'))
    const first = await bashRow($, 'toolu_1', 'List the files')
    const output = await $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'ToolResult', requestId: 'toolu_1',
      props: { tool_use_id: 'toolu_1', tool: 'Bash', output: 'ok', isErrored: false },
    } as never)
    expect(await button(first)).toBe('› List the files')
    await first.press({ key: 'to-human-toggle' })
    expect(await first.find({ type: 'Text', text: 'ToolUse' })).toBeDefined()
    expect(await button(output)).toBe('‹ fold to report')
    await output.press({ key: 'to-human-toggle' })
    expect(await button(first)).toBe('› List the files')
  })

  test('a mixed message\'s button reads the run it opens', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    await keep($, response('a1', text('<message>Found it.</message>\nChecking the rest.')))
    const mixed = await messageRow($, 'a1', '<message>Found it.</message>\nChecking the rest.')
    expect(await button(mixed)).toBe('› working record')
    await keep($, call('a2', 'toolu_2', 'Check the rest'))
    await bashRow($, 'toolu_2', 'Check the rest', undefined)
    expect(await button(mixed)).toBe('› Check the rest')
  })

  test('a group\'s row reads its run\'s label by its first call', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    await keep($, sent('a0', 'toolu_m0'))
    await sentRow($, 'toolu_m0')
    await keep($, response('a1', use('toolu_1', 'Read', { file_path: '/a/one.ts' })), result('u1', 'toolu_1', 'Read'), response('a2', use('toolu_2', 'Read', { file_path: '/a/two.ts' })))
    const group = await $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'ToolGroup', requestId: 'g1',
      props: { calls: [{ tool_use_id: 'toolu_1', tool: 'Read' }, { tool_use_id: 'toolu_2', tool: 'Read' }], isExpanded: false, isActive: true },
    } as never)
    expect(await button(group)).toBe('› Read two.ts')
  })

  test('a run that took prompts in mid-turn draws one fold (acceptance 7)', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    const seen = writes(on)
    await keep($, sent('a0', 'toolu_m0'))
    await sentRow($, 'toolu_m0')
    await keep($, call('a1', 'toolu_1', 'Wait for the build'))
    const first = await bashRow($, 'toolu_1', 'Wait for the build', undefined)
    await keep($, row('queue', 'q1', { kind: 'engine' }, [text(notification('toolu_bg', 'completed'))]), result('u1', 'toolu_1'))
    await keep($, userRow('d1', 'delivery', { kind: 'task-notification' }, notification('toolu_bg', 'completed')))
    const delivery = await $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'UserMessage', requestId: 'd1',
      props: { origin: { kind: 'task-notification' }, text: notification('toolu_bg', 'completed'), task: { toolUseId: 'toolu_bg', status: 'completed' } },
    } as never)
    await keep($, call('a2', 'toolu_2', 'Read the output'))
    const second = await bashRow($, 'toolu_2', 'Read the output')
    expect(await button(first)).toBe('› Read the output')
    expect(await button(delivery)).toBeUndefined()
    expect(await button(second)).toBeUndefined()
    expect(seen.fold.at(-1)).toEqual({ first: 'toolu_1', line: 'Read the output', isLive: true })
    expect(seen.folds).toEqual([])
  })

  test('the response made up after a final message joins no run', async ($, on) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    const seen = writes(on)
    await keep($, response('a2', use('toolu_m', MESSAGE_TOOL, { text: 'Done.', final: true })), result('u2', 'toolu_m', MESSAGE_TOOL, 'sent'))
    const step = $.turn.step({ turnId: 't1', index: 1, model: 'haiku', messageCount: 3 })
    for (let read = await step.next(); read.done !== true; read = await step.next()) {
      // The made-up response streams; the engine keeps its row after the step.
    }
    await keep($, response('x1', text(FINAL_ANSWER)))
    expect(seen.fold).toEqual([])
    // The next turn's record opens a run of its own.
    await keep($, call('a3', 'toolu_3', 'List the files'))
    expect(seen.fold).toEqual([{ first: 'toolu_3', line: 'List the files', isLive: true }])
  })
})

describe("the fold's button and its summary", () => {
  /** An interactive session whose model answers each summary call with `reply`; the calls it was asked. */
  const interactive = async ($: Engine, on: On, reply: () => unknown) => {
    mock.env(on, {})
    mock.store(on)
    engineDrawing(on)
    on('session.start', (_, e) => ({ cwd: e.cwd }))
    on('turn.complete', () => ({ text: '' }))
    on('session.id', () => ({ value: 's1' }))
    on('process.run', () => ({ value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
    const asks: unknown[] = []
    on('model.complete', (_, e) => {
      asks.push(e)
      return { value: reply() as never }
    })
    await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
    return asks
  }
  /** Waits for the unawaited summary call and its writes to land. */
  const until = async (isDone: () => Promise<boolean>) => {
    for (let i = 0; i < 200 && !(await isDone()); i++) await Promise.resolve()
  }

  test('a closed fold reads its summary once the reply settles (acceptance 2)', async ($, on) => {
    const asks = await interactive($, on, () => answered('Listed the files'))
    await keep($, sent('a0', 'toolu_m0'), result('u0', 'toolu_m0', MESSAGE_TOOL, 'sent'))
    await sentRow($, 'toolu_m0')
    await keep($, call('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1'))
    const first = await bashRow($, 'toolu_1', 'List the files')
    expect(await button(first)).toBe('› List the files')
    await keep($, sent('a2', 'toolu_m'), result('u2', 'toolu_m', MESSAGE_TOOL, 'sent'))
    await sentRow($, 'toolu_m')
    await until(async () => (await button(first)) === '› Listed the files')
    expect(await button(first)).toBe('› Listed the files')
    expect(asks).toHaveLength(1)
  })

  test("a turn that ends without a message leaves a fold that reads its summary (acceptance 3)", async ($, on) => {
    await interactive($, on, () => answered('Listed the files'))
    await keep($, sent('a0', 'toolu_m0'), result('u0', 'toolu_m0', MESSAGE_TOOL, 'sent'))
    await sentRow($, 'toolu_m0')
    await keep($, call('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1'))
    const first = await bashRow($, 'toolu_1', 'List the files')
    await $.turn.complete({ turnId: 't1', answer: '', durationMs: 1, isAborted: false, reason: 'answer' })
    await until(async () => (await button(first)) === '› Listed the files')
    expect(await button(first)).toBe('› Listed the files')
  })

  test('a call that fails leaves a closed fold reading working record, and it still unfolds (acceptance 5)', async ($, on) => {
    const asks = await interactive($, on, () => ({ isAnswered: false, reason: 'api-error', status: 404, error: 'invalid_request', usage: {} }))
    await keep($, sent('a0', 'toolu_m0'), result('u0', 'toolu_m0', MESSAGE_TOOL, 'sent'))
    await sentRow($, 'toolu_m0')
    await keep($, call('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1'))
    const first = await bashRow($, 'toolu_1', 'List the files')
    await keep($, sent('a2', 'toolu_m'), result('u2', 'toolu_m', MESSAGE_TOOL, 'sent'))
    await sentRow($, 'toolu_m')
    await until(async () => (await button(first)) === '› working record')
    expect(asks).toHaveLength(1)
    expect(await button(first)).toBe('› working record')
    await first.press({ key: 'to-human-toggle' })
    expect(await first.find({ type: 'Text', text: 'ToolUse' })).toBeDefined()
  })

  test('a run that took prompts in mid-turn draws one fold with one summary (acceptance 7)', async ($, on) => {
    const asks = await interactive($, on, () => answered('Waited for the build and read its output'))
    await keep($, sent('a0', 'toolu_m0'))
    await sentRow($, 'toolu_m0')
    await keep($, call('a1', 'toolu_1', 'Wait for the build'))
    const first = await bashRow($, 'toolu_1', 'Wait for the build', undefined)
    await keep($, row('queue', 'q1', { kind: 'engine' }, [text(notification('toolu_bg', 'completed'))]), result('u1', 'toolu_1'))
    await keep($, userRow('d1', 'delivery', { kind: 'task-notification' }, notification('toolu_bg', 'completed')))
    await keep($, userRow('d2', 'delivery', { kind: 'peer' }, 'Another Claude session sent a message: done', true))
    await keep($, call('a2', 'toolu_2', 'Read the output'), result('u2', 'toolu_2'))
    const second = await bashRow($, 'toolu_2', 'Read the output')
    await keep($, sent('a3', 'toolu_m'), result('u3', 'toolu_m', MESSAGE_TOOL, 'sent'))
    await sentRow($, 'toolu_m')
    await until(async () => (await button(first)) === '› Waited for the build and read its output')
    expect(await button(first)).toBe('› Waited for the build and read its output')
    expect(await button(second)).toBeUndefined()
    expect(asks).toHaveLength(1)
  })
})
