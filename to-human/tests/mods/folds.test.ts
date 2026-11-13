import type { EngineInterface, On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { describe, expect, mock, test, tier } from 'claude-code/testing'

import type { Folds, OpenFold } from '../../types/to-human'
import type { KeptRow } from '../../hooks/mods/folds'
import { follow, labelOf, lineOf, newTracker, published, registerFolds, stepsOf, takeUp } from '../../hooks/mods/folds'
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
    expect(stepsOf(result('u1', 'toolu_b'), new Set())).toEqual([{ kind: 'result', call: 'toolu_b' }])
    // The tracker holds no run for a read call, so its result finds none (see `follow`).
    expect(stepsOf(result('u2', 'toolu_m', MESSAGE_TOOL, 'sent'), new Set())).toEqual([{ kind: 'result', call: 'toolu_m' }])
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
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [] }, fold: { first: 'toolu_1', last: 'toolu_2', line: 'Run the tests', isLive: true } })
  })

  test('several calls in one response: the last one\'s line', () => {
    const tracker = tracked(response('a1', use('toolu_1', 'Read', { file_path: '/a/one.ts' }), use('toolu_2', 'Read', { file_path: '/a/two.ts' })))
    expect(published(tracker).fold?.line).toBe('Read two.ts')
  })

  test('a live run with no call yet carries no line', () => {
    const tracker = tracked(response('a1', text('Reading the logs.')))
    expect(published(tracker).fold).toEqual({ first: 'a1', last: 'a1', isLive: true })
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
      fold: { first: 'toolu_4', last: 'toolu_4', line: 'Run the tests', isLive: true },
    })
  })

  test("a run closed while one of its calls runs stays live on that call's line until its result is kept, which joins it", () => {
    // One response, a call beside a message: the message is kept, and closes the run, before the call has run.
    const tracker = tracked(response('a1', use('toolu_b', 'Bash', { command: 'make', description: 'Build it' }), use('toolu_m', MESSAGE_TOOL, { text: 'Building.' })))
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [{ first: 'toolu_b', last: 'toolu_b', line: 'Build it', isLive: true }] }, fold: null })
    follow(tracker, stepsOf(result('u2', 'toolu_m', MESSAGE_TOOL, 'sent'), tracker.spawns))
    expect(published(tracker).folds.runs[0]?.isLive).toBe(true)
    follow(tracker, stepsOf(result('u3', 'toolu_b'), tracker.spawns))
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [{ first: 'toolu_b', last: 'toolu_b' }] }, fold: null })
  })

  test('a mixed message closes the run before it and opens the next with its own record', () => {
    const tracker = tracked(call('a1', 'toolu_1', 'List the files'), result('u1', 'toolu_1'), response('a2', text('<message>Found it.</message>\nChecking the rest.')))
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [{ first: 'toolu_1', last: 'toolu_1' }] }, fold: { first: 'a2', last: 'a2', isLive: true } })
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
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [] }, fold: { first: 'toolu_1', last: 'toolu_2', line: 'Read the output', isLive: true } })
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
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [] }, fold: null })
  })
})

describe('takeUp: a module that starts over the runs another left', () => {
  test('the open run goes on with its live line, held not whole; a closed run left live loses the mark', () => {
    const tracker = newTracker()
    takeUp(
      tracker,
      { shape: 1, runs: [{ first: 'toolu_1', last: 'a2', summary: 'Listed the files' }, { first: 'toolu_3', last: 'toolu_3', line: 'Build it', isLive: true }] },
      { first: 'toolu_5', last: 'toolu_5', line: 'Run the tests', isLive: true },
    )
    expect(tracker.open?.isWhole).toBe(false)
    expect(published(tracker).folds.runs).toEqual([{ first: 'toolu_1', last: 'a2', summary: 'Listed the files' }, { first: 'toolu_3', last: 'toolu_3' }])
    follow(tracker, stepsOf(call('a6', 'toolu_6', 'Lint it'), tracker.spawns))
    expect(published(tracker).fold).toEqual({ first: 'toolu_5', last: 'toolu_6', line: 'Lint it', isLive: true })
    follow(tracker, stepsOf(result('u6', 'toolu_6'), tracker.spawns))
    follow(tracker, stepsOf(sent('a7', 'toolu_m'), tracker.spawns))
    expect(published(tracker).folds.runs.at(-1)).toEqual({ first: 'toolu_5', last: 'toolu_6' })
  })

  test('nothing kept, or a value of another shape, starts empty', () => {
    const tracker = newTracker()
    takeUp(tracker, undefined, undefined)
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [] }, fold: null })
    takeUp(tracker, { shape: 2, runs: 'no' } as unknown as Folds, 'x' as unknown as OpenFold)
    expect(published(tracker)).toEqual({ folds: { shape: 1, runs: [] }, fold: null })
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

/** The tracker's hooks over a hand-made engine whose `$.state` is a map, as the host keeps it across a reload. */
function trackerHooks(kept = new Map<string, unknown>(), { failWrites = false } = {}) {
  type Hook = (engine: EngineInterface, e: Record<string, unknown>, next: (e: unknown) => Promise<unknown>) => Promise<unknown>
  const hooks: { event: string; handler: Hook }[] = []
  const on = ((event: string, ...rest: unknown[]) => hooks.push({ event, handler: rest[rest.length - 1] as Hook })) as unknown as On
  registerFolds(on, newView(() => true), () => true)
  const logs: string[] = []
  const engine = {
    state: {
      get: async (ref: { key: string }) => ({ value: kept.get(ref.key), version: 0 }),
      set: async (ref: { key: string }, value: unknown) => {
        if (failWrites) throw new Error('refused')
        kept.set(ref.key, value)
        return { isSet: true, version: 1 }
      },
    },
    ui: { log: (line: string) => logs.push(line) },
  } as unknown as EngineInterface
  const hook = (event: string) => hooks.find((h) => h.event === event)!.handler
  const append = async (kept: KeptRow) => {
    const stored = { message: kept.message, uuid: kept.uuid }
    const answer = await hook('session.append')(engine, kept as unknown as Record<string, unknown>, async () => stored)
    expect(answer).toBe(stored)
  }
  const start = () => hook('session.start')(engine, { cwd: '/w', surface: 'terminal', isInteractive: true }, async (e) => e)
  const sessionStart = (source: string) => hook('classic.SessionStart')(engine, { source }, async () => ({}))
  /** Lets the chained writes land. */
  const settle = () => Promise.resolve().then(() => undefined)
  return { kept, logs, append, start, sessionStart, settle }
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
    expect(h.kept.get('fold')).toEqual({ first: 'toolu_1', last: 'toolu_1', line: 'List the files', isLive: true })
    await h.append(sent('a2', 'toolu_m'))
    await drain(h.settle)
    expect(h.kept.get('fold')).toBeNull()
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
    expect(second.kept.get('fold')).toEqual({ first: 'toolu_1', last: 'toolu_2', line: 'Run the tests', isLive: true })
  })

  test('rows kept before the start-up read lands wait for it, in order', async () => {
    const kept = new Map<string, unknown>([['fold', { first: 'toolu_1', last: 'toolu_1', line: 'List the files', isLive: true }]])
    const h = trackerHooks(kept)
    // No session.start first: the first row begins the read.
    await h.append(call('a2', 'toolu_2', 'Run the tests'))
    await h.append(call('a3', 'toolu_3', 'Lint it'))
    await drain(h.settle)
    expect(h.kept.get('fold')).toEqual({ first: 'toolu_1', last: 'toolu_3', line: 'Lint it', isLive: true })
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
    }
  })
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
    expect(seen.fold.at(-1)).toEqual({ first: 'toolu_1', last: 'toolu_2', line: 'Read the output', isLive: true })
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
    expect(seen.fold).toEqual([{ first: 'toolu_3', last: 'toolu_3', line: 'List the files', isLive: true }])
  })
})
