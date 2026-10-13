import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import type { AskQuestion } from '../../hooks/mods/ask'
import {
  ASK_TOOL,
  ASYNC_PARAGRAPH,
  INPUT_SCHEMA,
  LATCHED,
  SUBAGENT_REFUSAL,
  WITHDRAWN,
  describeAsk,
  imageBlock,
  imageMarks,
  mediaTypeOf,
  newImages,
  registerAsk,
  resetAsk,
  slugOf,
  validateQuestions,
} from '../../hooks/mods/ask'

tier('user')

const STEER =
  'This call included a question with fewer than 2 options, so it was rejected and the person never saw it. A question with a single option has no decision in it. Do not retry this call and do not invent a filler second option. Instead, state the one path you were going to offer as the approach you are taking, then continue with the task. If this call also contained questions with 2 to 4 options (each with distinct labels), you may re-ask those questions alone in a new call. Ask a question only when the person has at least two genuinely distinct choices.'

const option = (label: string, description = 'd') => ({ label, description })
const question = (text: string, header: string, labels: string[], multiSelect = false) => ({ question: text, header, multiSelect, options: labels.map((l) => option(l)) })

/**
 * The built-in's results for four invalid calls, recorded from a live session
 * on Claude Code 2.1.296 (2026-10-13); the engine wraps each in
 * `<tool_use_error>…</tool_use_error>`, as it wraps a hook's deny.
 */
describe('validateQuestions', () => {
  test('one option: the steer, then the issue as the engine prints a lone size issue', async () => {
    expect(validateQuestions({ questions: [question('Pick one?', 'One', ['Only'])] })).toBe(
      `InputValidationError: ${STEER}\n\n[\n  {\n    "origin": "array",\n    "code": "too_small",\n    "minimum": 2,\n    "inclusive": true,\n    "path": [\n      "questions",\n      0,\n      "options"\n    ],\n    "message": "Too small: expected array to have >=2 items"\n  }\n]`,
    )
  })

  test('duplicate question texts: the uniqueness message verbatim', async () => {
    expect(validateQuestions({ questions: [question('Same?', 'A', ['x', 'y']), question('Same?', 'B', ['x', 'y'])] })).toBe(
      'InputValidationError: [\n  {\n    "code": "custom",\n    "path": [],\n    "message": "Question texts must be unique, option labels must be unique within each question"\n  }\n]',
    )
  })

  test('a missing field: the head naming AskUserQuestion and one line', async () => {
    const { header: _, ...headless } = question('No header?', 'H', ['x', 'y'])
    expect(validateQuestions({ questions: [headless] })).toBe(
      'InputValidationError: AskUserQuestion failed due to the following issue:\nThe required parameter `questions[0].header` is missing',
    )
  })

  test('several rules broken: the steer, then one line per issue', async () => {
    expect(validateQuestions({ foo: '1', questions: [question('Single?', 'S', ['x']), question('Dup labels?', 'D', ['x', 'x'])] })).toBe(
      `InputValidationError: ${STEER}\n\nAskUserQuestion failed due to the following issues:\nAn unexpected parameter \`foo\` was provided\nThe parameter \`questions[0].options\` is invalid: Too small: expected array to have >=2 items\nThe input is invalid: Question texts must be unique, option labels must be unique within each question`,
    )
  })

  test('a valid set passes, previews and metadata included, and the header length is never checked', async () => {
    const preview = { ...option('Postgres'), preview: '+--+' }
    expect(validateQuestions({ questions: [{ ...question('Which backend?', 'A header far past twelve characters', ['SQLite']), options: [preview, option('SQLite')] }], metadata: { source: 'x' } })).toBeUndefined()
    expect(validateQuestions({ questions: [question('Which?', 'H', ['a', 'b', 'c', 'd'], true)], async: true })).toBeUndefined()
  })

  test('multiSelect may be left out: the built-in defaults it', async () => {
    const { multiSelect: _, ...bare } = question('Which?', 'H', ['a', 'b'])
    expect(validateQuestions({ questions: [bare] })).toBeUndefined()
  })

  test('too many questions or options: the size issue', async () => {
    const five = ['1?', '2?', '3?', '4?', '5?'].map((q) => question(q, 'H', ['a', 'b']))
    expect(validateQuestions({ questions: five })).toContain('"code": "too_big",\n    "maximum": 4')
    expect(validateQuestions({ questions: five })).toContain('"message": "Too big: expected array to have <=4 items"')
    expect(validateQuestions({ questions: [question('Q?', 'H', ['a', 'b', 'c', 'd', 'e'])] })).toContain('"path": [\n      "questions",\n      0,\n      "options"\n    ]')
    expect(validateQuestions({ questions: [] })).toContain('"message": "Too small: expected array to have >=1 items"')
  })

  test('duplicate option labels within one question break the uniqueness rule; across questions they do not', async () => {
    expect(validateQuestions({ questions: [question('Q?', 'H', ['a', 'a'])] })).toContain('"message": "Question texts must be unique, option labels must be unique within each question"')
    expect(validateQuestions({ questions: [question('Q1?', 'H', ['a', 'b']), question('Q2?', 'H', ['a', 'b'])] })).toBeUndefined()
  })

  test('wrong types, missing fields and keys the tool does not take, each a line', async () => {
    const text = validateQuestions({ answers: {}, async: 'yes', questions: [{ question: 'Q?', header: 7, multiSelect: 'no', options: [{ label: 'a' }, option('b')] }] })
    expect(text).toBe(
      [
        'InputValidationError: AskUserQuestion failed due to the following issues:',
        'The required parameter `questions[0].options[0].description` is missing',
        'An unexpected parameter `answers` was provided',
        'The parameter `questions[0].header` type is expected as `string` but provided as `number`',
        'The parameter `questions[0].multiSelect` type is expected as `boolean` but provided as `string`',
        'The parameter `async` type is expected as `boolean` but provided as `string`',
      ].join('\n'),
    )
  })

  test('the uniqueness rule is not checked once a field is missing or mistyped', async () => {
    const { header: _, ...headless } = question('Same?', 'H', ['x', 'y'])
    expect(validateQuestions({ questions: [headless, headless] })).not.toContain('must be unique')
  })

  test('questions that are not a list, and a missing list', async () => {
    expect(validateQuestions({ questions: 'Q?' })).toBe(
      'InputValidationError: AskUserQuestion failed due to the following issue:\nThe parameter `questions` type is expected as `array` but provided as `string`',
    )
    expect(validateQuestions({})).toBe('InputValidationError: AskUserQuestion failed due to the following issue:\nThe required parameter `questions` is missing')
  })

  test('past twenty listed issues the rest are counted', async () => {
    const many = Array.from({ length: 22 }, (_, i) => question(`Q${i}?`, 'H', ['a']))
    const text = validateQuestions({ extra: 1, questions: many }) ?? ''
    expect(text).toContain('(3 more issues not listed)')
    expect(text.split('\n').filter((line) => line.startsWith('The parameter')).length).toBe(20)
  })
})

describe('the tool as the model reads it', () => {
  test('the description is the built-in one, then the async paragraph', async () => {
    expect(describeAsk('Use this tool only when blocked.')).toBe(`Use this tool only when blocked.\n\n${ASYNC_PARAGRAPH}`)
    expect(ASYNC_PARAGRAPH).toBe(
      '`async`: set it to true when you can go on with other work while the human decides. The call then returns at once; the questions wait in the human\'s view until they answer, and their answer reaches you in a later message that quotes each question. Leave it false when nothing useful can proceed without the answer.',
    )
  })

  test('the schema is the built-in input without answers or annotations, plus async', async () => {
    const properties = INPUT_SCHEMA.properties as Record<string, Record<string, unknown>>
    expect(Object.keys(properties)).toEqual(['questions', 'metadata', 'async'])
    expect(properties.async).toEqual({ type: 'boolean', default: false, description: ASYNC_PARAGRAPH })
    expect(INPUT_SCHEMA.additionalProperties).toBe(false)
    expect(INPUT_SCHEMA.required).toEqual(['questions'])
  })
})

type Handler = (...args: unknown[]) => unknown
type Matcher = Record<string, unknown> | undefined
type Origin = { plugin: string; tier: string }
type Answer = { ref?: number; result: unknown; text?: string; isError?: true } | { deny: string }

const MOD: Origin = { plugin: 'doperpowers', tier: 'user' }
const MODEL: Origin = { plugin: 'engine', tier: 'core' }
const OTHER: Origin = { plugin: 'cua', tier: 'user' }

const ESC =
  "The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). STOP what you are doing and wait for the user to tell you how to proceed."
const CHAT =
  "The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). To tell you how to proceed, the user said:\nThe user wants to clarify these questions."
const answered = (text: string, answers: Record<string, string> = {}): Answer => ({ ref: 1, result: { questions: [], answers, annotations: {} }, text })
const refused = (text: string): Answer => ({ isError: true, result: `Error: ${text}`, text })

const BACKEND: AskQuestion = { question: 'Which backend?', header: 'Backend', multiSelect: false, options: [{ label: 'Postgres', description: 'd', preview: '+--+' }, option('SQLite')] }
const FEATURES: AskQuestion = { question: 'Which features?', header: 'Features', multiSelect: true, options: [option('Auth'), option('Export')] }

/**
 * A registrar that keeps the hooks, and an engine of plain records. `$.ui.ask`
 * is held until the test raises it: `raise(i, answer)` runs the AskUserQuestion
 * call it makes through the mod's own hook, as the engine does (the calling hook
 * left out, the origin this plugin), the dialog answering `answer`.
 */
function harness(
  options: { builtin?: string | undefined; tmpdir?: string; dirs?: Record<string, string[]>; unreadable?: string[]; whileStarting?: () => Promise<unknown>; register?: () => Promise<void> } = {},
) {
  const hooks: { event: string; matcher: Matcher; handler: Handler; onFailure?: Handler }[] = []
  const on = ((event: string, ...rest: unknown[]) => {
    const handler = rest[rest.length - 1] as Handler
    const matcher = rest.length > 1 ? (rest[0] as Matcher) : undefined
    const hook: (typeof hooks)[number] = { event, matcher, handler }
    hooks.push(hook)
    return { catch: (onFailure: Handler) => void (hook.onFailure = onFailure) }
  }) as unknown as On
  const calls: { op: string; args: unknown }[] = []
  const raises: { question: string; options: { options?: readonly string[]; header?: string; multiSelect?: true }; resolve: (v: string) => void; reject: (e: Error) => void }[] = []
  const builtin = 'builtin' in options ? options.builtin : 'Use this tool only when you are blocked.'
  // A file system of folders and their file names; a file's bytes are its path.
  const dirs = new Map(Object.entries(options.dirs ?? { '/tmp': ['claude-0', 'claude-501', 'other'], '/tmp/claude-501': [], '/tmp/claude-0': [] }))
  const unreadable = new Set(options.unreadable ?? ['/tmp/claude-0'])
  const $ = {
    env: { get: async (name: string) => (name === 'CLAUDE_CODE_TMPDIR' ? options.tmpdir : undefined) },
    fs: {
      list: async (path: string) => {
        const names = dirs.get(path)
        if (names === undefined || unreadable.has(path)) {
          throw new Error(`ENOENT or EACCES: ${path}`)
        }
        return names.map((name) => ({ name, kind: dirs.has(`${path}/${name}`) ? 'dir' : 'file', size: 1, mtimeMs: 0, isLink: false }))
      },
      exists: async (path: string) => dirs.has(path),
      // /tmp is a link to /private/tmp, as on macOS.
      stat: async (path: string, opts?: { resolve?: boolean }) => ({ kind: 'file', size: 1, mtimeMs: 0, isLink: false, ...(opts?.resolve === true && { realPath: `/private${path}` }) }),
      read: async (path: string, opts?: { as?: string }) => {
        calls.push({ op: 'fs.read', args: { path, ...opts } })
        return { base64: `bytes:${path}` }
      },
    },
    tool: {
      list: async () => {
        await options.whileStarting?.()
        return [{ name: 'Read', description: 'Reads.', mcp: false }, ...(builtin === undefined ? [] : [{ name: 'AskUserQuestion', description: builtin, mcp: false }])]
      },
      register: async (spec: { name: string }) => {
        calls.push({ op: 'tool.register', args: spec })
        await options.register?.()
        return { tool: `mcp__doperpowers__${spec.name}` }
      },
    },
    ui: {
      ask: (question: string, opts: (typeof raises)[number]['options']) =>
        new Promise<string>((resolve, reject) => {
          calls.push({ op: 'ui.ask', args: { question, ...opts } })
          raises.push({ question, options: opts, resolve, reject })
        }),
      log: (text: string) => calls.push({ op: 'ui.log', args: text }),
      toast: (text: string) => calls.push({ op: 'ui.toast', args: text }),
      invalidate: (event: string) => calls.push({ op: 'ui.invalidate', args: event }),
    },
    turn: { abort: async (args: unknown) => void calls.push({ op: 'turn.abort', args }) },
  }
  resetAsk()
  registerAsk(on)
  const engine = $ as unknown as EngineInterface

  const matching = (event: string, e: Record<string, unknown>) =>
    hooks.filter((h) => h.event === event && Object.entries(h.matcher ?? {}).every(([k, v]) => (v instanceof RegExp ? v.test(String(e[k])) : e[k] === v)))

  /** Runs `e` down the chain of `event`, outermost first; `bottom` answers beneath. */
  const dispatch = (event: string, e: Record<string, unknown>, origin: Origin, bottom: (e: Record<string, unknown>) => unknown) => {
    const chain = matching(event, e)
    const at = (i: number, input: Record<string, unknown>): unknown => {
      const hook = chain[i]
      if (hook === undefined) {
        return bottom(input)
      }
      const next = Object.assign(async (inner: Record<string, unknown>) => at(i + 1, inner), { origin })
      return hook.handler($, input, next)
    }
    return at(0, e)
  }

  /** The engine pasting pictures: files appear in a folder. */
  const paste = (folder: string, ...names: string[]) => {
    for (const parent of [folder.slice(0, folder.lastIndexOf('/'))]) {
      if (!dirs.has(parent)) dirs.set(parent, [])
    }
    dirs.set(folder, [...(dirs.get(folder) ?? []), ...names])
  }

  const classicStart = (transcript_path: string, session_id: string) =>
    dispatch('classic.SessionStart', { hook_event_name: 'SessionStart', source: 'startup', transcript_path, session_id, cwd: '/' }, MODEL, async () => ({}))

  const turnStart = () => dispatch('turn.start', { text: '', turnId: 'turn-2' }, MODEL, async (e) => ({ turnId: e.turnId }))

  /** One model request through the turn.step hooks; `sent` says whether it reached the engine. */
  const step = async (index: number, agentId?: string) => {
    const hook = matching('turn.step', {})[0]
    let sent = false
    const next = Object.assign(
      (async function* () {
        sent = true
        yield { kind: 'text', index: 0, text: 'hi', ref: 1 }
        return { turnId: 'turn-1', index, answer: 'hi', toolUses: [], stopReason: 'end_turn', usage: null }
      }) as unknown as (e: unknown) => AsyncGenerator<unknown, unknown>,
      { origin: MODEL },
    )
    const e = { turnId: 'turn-1', index, model: 'm', messageCount: 3, ...(agentId !== undefined && { agentId }) }
    const generator = (hook?.handler($, e, (inner: unknown) => next(inner)) ?? next(e)) as AsyncGenerator<unknown, unknown>
    const chunks: unknown[] = []
    for (;;) {
      const item = await generator.next()
      if (item.done === true) {
        return { sent, chunks, result: item.value }
      }
      chunks.push(item.value)
    }
  }

  const start = () => dispatch('session.start', { cwd: '/', surface: 'terminal', isInteractive: true }, { plugin: 'engine', tier: 'core' }, async () => ({ cwd: '/' }))

  /** A call of `tool` from `origin`; `ran` records whether the tool itself was reached. */
  const call = async (tool: string, args: Record<string, unknown>, origin: Origin = MODEL, agentId?: string) => {
    const ran: Record<string, unknown>[] = []
    const result = await dispatch('tool.call', { tool, tool_use_id: `toolu_${calls.length}`, ...args, ...(agentId !== undefined && { agentId }) }, origin, async (e) => {
      ran.push(e)
      return { ref: 9, result: 'ran', text: 'ran' }
    })
    return { result: result as Answer, ran }
  }

  let nested = 0
  /** Lets the engine raise the i-th held `$.ui.ask`: the AskUserQuestion call through the hooks, then the dialog's answer. */
  const raise = async (i: number, answer: Answer, origin: Origin = MOD) => {
    const r = raises[i]
    if (r === undefined) {
      throw new Error(`no raise ${i}`)
    }
    const shown: Record<string, unknown>[] = []
    const e = {
      tool: 'AskUserQuestion',
      tool_use_id: `nested_${nested++}`,
      questions: [{ question: r.question, header: r.options.header, multiSelect: r.options.multiSelect === true, options: (r.options.options ?? []).map((label) => ({ label, description: '' })) }],
    }
    const result = (await dispatch('tool.call', e, origin, async (input) => (shown.push(input), answer))) as Answer
    if ('deny' in result || result.isError === true) {
      r.reject(new Error(`$.ui.ask: no answer (${'deny' in result ? result.deny : result.text})`))
    } else {
      r.resolve('label')
    }
    return { result, shown }
  }

  // Microtask turns, so a hook working through its $ calls reaches the held raise.
  const settle = async () => {
    for (let i = 0; i < 100; i++) {
      await Promise.resolve()
    }
  }

  const describe = (tool: string, description: string) =>
    dispatch('tool.describe', { tool, description, isDeferred: true, provider: MODEL }, MODEL, async (e) => ({ description: e.description, isDeferred: e.isDeferred }))

  const registered = () => calls.filter((c) => c.op === 'tool.register').map((c) => c.args as { name: string; description: string; inputSchema: unknown })
  /** Runs the `.catch` of the hook on `event` matching `e`, as the engine does when the hook failed. */
  const fail = (event: string, e: Record<string, unknown>, failure: { kind: string; called?: boolean; origin?: Origin }) => {
    const hook = matching(event, e).find((h) => h.matcher !== undefined) ?? matching(event, e)[0]
    const ran: Record<string, unknown>[] = []
    const next = Object.assign(async (inner: Record<string, unknown>) => (ran.push(inner), { ref: 9, result: 'ran', text: 'ran' }), {
      origin: failure.origin ?? MODEL,
      called: failure.called === true,
      error: { kind: failure.kind },
    })
    return { answer: hook?.onFailure?.($, e, next), ran }
  }

  return { calls, raises, start, call, raise, settle, describe, registered, engine, dispatch, paste, classicStart, turnStart, step, fail }
}

describe('registerAsk: the tool and the built-in', () => {
  test('registers the tool at session start with the built-in description and the schema', async () => {
    const h = harness()
    await h.start()
    expect(h.registered()).toEqual([{ name: 'AskUserQuestion', description: describeAsk('Use this tool only when you are blocked.'), inputSchema: INPUT_SCHEMA }])
    expect(ASK_TOOL).toBe('mcp__doperpowers__AskUserQuestion')
  })

  test('the built-in described while the session starts: withdrawn, its whole text registered', async () => {
    let first: unknown
    const h = harness({ whileStarting: async () => (first = await h.describe('AskUserQuestion', 'The whole text.')) })
    await h.start()
    expect(first).toEqual({ description: WITHDRAWN, isDeferred: true })
    expect(h.registered()[0]?.description).toBe(describeAsk('The whole text.'))
    expect(h.calls.some((c) => c.op === 'ui.invalidate')).toBe(false)
  })

  test('the built-in described before the session started: described again once the tool is registered', async () => {
    const h = harness()
    expect(await h.describe('AskUserQuestion', 'The whole text.')).toEqual({ description: 'The whole text.', isDeferred: true })
    await h.start()
    expect(h.registered()[0]?.description).toBe(describeAsk('The whole text.'))
    expect(h.calls.filter((c) => c.op === 'ui.invalidate')).toEqual([{ op: 'ui.invalidate', args: 'tool.describe' }])
    expect(await h.describe('AskUserQuestion', 'The whole text.')).toEqual({ description: WITHDRAWN, isDeferred: true })
  })

  test('a tool that does not register puts the built-in back', async () => {
    const h = harness({
      whileStarting: async () => h.describe('AskUserQuestion', 'The whole text.'),
      register: async () => {
        throw new Error('no registrar')
      },
    })
    await h.start()
    expect(h.calls.filter((c) => c.op === 'ui.invalidate')).toEqual([{ op: 'ui.invalidate', args: 'tool.describe' }])
    expect(await h.describe('AskUserQuestion', 'The whole text.')).toEqual({ description: 'The whole text.', isDeferred: true })
    expect((await h.call('AskUserQuestion', { questions: [BACKEND] })).ran.length).toBe(1)
  })

  test('keeps the tool inline and withdraws the built-in to the deferred list', async () => {
    const h = harness()
    await h.start()
    expect(await h.describe('AskUserQuestion', 'The whole text.')).toEqual({ description: WITHDRAWN, isDeferred: true })
    expect(await h.describe(ASK_TOOL, 'Shortened.')).toEqual({ description: describeAsk('The whole text.'), isDeferred: false })
    expect(h.calls.some((c) => c.op === 'ui.invalidate')).toBe(false)
  })

  test('described before the built-in, the tool is described again once the whole text is known', async () => {
    const h = harness()
    await h.start()
    expect(await h.describe(ASK_TOOL, 'Shortened.')).toEqual({ description: 'Shortened.', isDeferred: false })
    await h.describe('AskUserQuestion', 'The whole text.')
    expect(h.calls.filter((c) => c.op === 'ui.invalidate').length).toBe(1)
    // The second round, in either order, settles without another.
    expect(await h.describe(ASK_TOOL, 'Shortened.')).toEqual({ description: describeAsk('The whole text.'), isDeferred: false })
    await h.describe('AskUserQuestion', 'The whole text.')
    expect(h.calls.filter((c) => c.op === 'ui.invalidate').length).toBe(1)
  })

  test('a session without the built-in registers nothing and withdraws nothing', async () => {
    const h = harness({ builtin: undefined })
    await h.start()
    expect(h.registered()).toEqual([])
    expect(await h.describe('AskUserQuestion', 'x')).toEqual({ description: 'x', isDeferred: true })
    const { result, ran } = await h.call('AskUserQuestion', { questions: [BACKEND] })
    expect(result).toEqual({ ref: 9, result: 'ran', text: 'ran' })
    expect(ran.length).toBe(1)
  })

  test("the model's own call of the built-in is refused", async () => {
    const h = harness()
    await h.start()
    const { result, ran } = await h.call('AskUserQuestion', { questions: [BACKEND] })
    expect(result).toEqual({ deny: WITHDRAWN })
    expect(ran).toEqual([])
  })

  test("another plugin's $.ui.ask is left alone", async () => {
    const h = harness()
    await h.start()
    const { result, ran } = await h.call('AskUserQuestion', { questions: [question('How careful?', 'Mood', ['Bold', 'Careful'])] }, OTHER)
    expect(result).toEqual({ ref: 9, result: 'ran', text: 'ran' })
    expect(ran.length).toBe(1)
  })

  test("a subagent's call is refused before any dialog", async () => {
    const h = harness()
    await h.start()
    const { result } = await h.call(ASK_TOOL, { questions: [BACKEND] }, MODEL, 'agent-1')
    expect(result).toEqual({ deny: SUBAGENT_REFUSAL })
    expect(h.raises).toEqual([])
  })

  test('an invalid ask is refused with the built-in error before any dialog', async () => {
    const h = harness()
    await h.start()
    const input = { questions: [question('Pick one?', 'One', ['Only'])] }
    const { result } = await h.call(ASK_TOOL, input)
    expect(result).toEqual({ deny: validateQuestions(input) })
    expect(h.raises).toEqual([])
  })
})

describe('registerAsk: a blocking ask', () => {
  test('raises the first question under a token header, widens to the whole set, and returns the engine text', async () => {
    const h = harness()
    await h.start()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND, FEATURES] })
    await h.settle()
    expect(h.calls.find((c) => c.op === 'ui.ask')?.args).toEqual({ question: 'Which backend?', options: ['Postgres', 'SQLite'], header: 'ask-1' })
    const { shown } = await h.raise(0, answered('The user answered: "Which backend?"="SQLite".'))
    expect(shown.length).toBe(1)
    expect(shown[0]?.questions).toEqual([BACKEND, FEATURES])
    expect((await pending).result).toEqual({ result: 'The user answered: "Which backend?"="SQLite".' })
  })

  test('async true runs as a blocking ask until async asks exist', async () => {
    const h = harness()
    await h.start()
    const pending = h.call(ASK_TOOL, { questions: [FEATURES], async: true })
    await h.settle()
    expect(h.calls.find((c) => c.op === 'ui.ask')?.args).toEqual({ question: 'Which features?', options: ['Auth', 'Export'], header: 'ask-1', multiSelect: true })
    await h.raise(0, answered('Your questions have been answered: x.'))
    expect((await pending).result).toEqual({ result: 'Your questions have been answered: x.' })
  })

  test('two asks with the same first question each claim their own entry, the second raised first', async () => {
    const h = harness()
    await h.start()
    const first = h.call(ASK_TOOL, { questions: [BACKEND] })
    const second = h.call(ASK_TOOL, { questions: [BACKEND, FEATURES] })
    await h.settle()
    expect(h.raises.map((r) => r.options.header)).toEqual(['ask-1', 'ask-2'])
    const late = await h.raise(1, answered('second answer'))
    expect(late.shown[0]?.questions).toEqual([BACKEND, FEATURES])
    const early = await h.raise(0, answered('first answer'))
    expect(early.shown[0]?.questions).toEqual([BACKEND])
    expect((await first).result).toEqual({ result: 'first answer' })
    expect((await second).result).toEqual({ result: 'second answer' })
  })

  test("a model's call carrying a pending token claims nothing; the ask's own raise still does", async () => {
    const h = harness()
    await h.start()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND, FEATURES] })
    await h.settle()
    const forged = await h.call('AskUserQuestion', { questions: [{ ...BACKEND, header: 'ask-1' }] })
    expect(forged.result).toEqual({ deny: WITHDRAWN })
    expect(forged.ran).toEqual([])
    const { shown } = await h.raise(0, answered('answer'))
    expect(shown[0]?.questions).toEqual([BACKEND, FEATURES])
    expect((await pending).result).toEqual({ result: 'answer' })
  })

  test('a raise from this plugin with no pending token is refused, and a token claims once', async () => {
    const h = harness()
    await h.start()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    const stray = await h.call('AskUserQuestion', { questions: [{ ...BACKEND, header: 'ask-9' }] }, MOD)
    expect(stray.result).toEqual({ deny: WITHDRAWN })
    await h.raise(0, answered('answer'))
    await pending
    const replay = await h.call('AskUserQuestion', { questions: [{ ...BACKEND, header: 'ask-1' }] }, MOD)
    expect(replay.result).toEqual({ deny: WITHDRAWN })
  })

  test('"Chat about this" returns its text as the error result and the turn goes on', async () => {
    const h = harness()
    await h.start()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    await h.raise(0, refused(CHAT))
    expect((await pending).result).toEqual({ deny: CHAT })
    const after = await h.call('Bash', { command: 'ls' })
    expect(after.ran.length).toBe(1)
  })

  test('Esc returns its text as the error result and latches the turn: later model calls are refused before they run', async () => {
    const h = harness()
    await h.start()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    await h.raise(0, refused(ESC))
    expect((await pending).result).toEqual({ deny: ESC })

    const write = await h.call('Write', { file_path: 'x.txt', content: 'hi' })
    expect(write.result).toEqual({ deny: LATCHED })
    expect(write.ran).toEqual([])
    const again = await h.call(ASK_TOOL, { questions: [FEATURES] })
    expect(again.result).toEqual({ deny: LATCHED })
    expect(h.raises.length).toBe(1)

    // Not the model's main loop: a subagent's call and a plugin's own run.
    expect((await h.call('Read', { file_path: 'a' }, MODEL, 'agent-1')).ran.length).toBe(1)
    expect((await h.call('Read', { file_path: 'a' }, OTHER)).ran.length).toBe(1)
  })
})

describe('the turn a declined ask ends', () => {
  const declined = async (text: string) => {
    const h = harness()
    await h.start()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    await h.raise(0, refused(text))
    await pending
    return h
  }

  test('after Esc the next main request is not sent: the turn is aborted there', async () => {
    const h = await declined(ESC)
    const latched = await h.step(1)
    expect(latched.sent).toBe(false)
    expect(latched.chunks).toEqual([])
    expect(h.calls.filter((c) => c.op === 'turn.abort')).toEqual([{ op: 'turn.abort', args: { turnId: 'turn-1' } }])
  })

  test("a subagent's request in that turn is sent", async () => {
    const h = await declined(ESC)
    expect((await h.step(0, 'agent-1')).sent).toBe(true)
    expect(h.calls.some((c) => c.op === 'turn.abort')).toBe(false)
  })

  test('after "Chat about this" the turn goes on', async () => {
    const h = await declined(CHAT)
    expect((await h.step(1)).sent).toBe(true)
    expect(h.calls.some((c) => c.op === 'turn.abort')).toBe(false)
  })

  test('the next turn starts unlatched', async () => {
    const h = await declined(ESC)
    await h.turnStart()
    expect((await h.step(0)).sent).toBe(true)
    expect((await h.call('Write', { file_path: 'x.txt' })).ran.length).toBe(1)
  })
})

describe('pictures pasted into the dialog', () => {
  const FOLDER = '/tmp/claude-501/-work-repo/sess-1/images'

  test('newImages takes what appeared, in the store number order, less what an earlier dialog took', async () => {
    expect(newImages(['1.png'], ['1.png', '10.png', '2.jpg', 'notes.txt', '3.png'], new Set(['3.png']))).toEqual(['2.jpg', '10.png'])
    expect(newImages([], [])).toEqual([])
  })

  test('the media type follows the extension', async () => {
    expect(['1.png', '2.jpg', '3.jpeg', '4.gif', '5.webp'].map(mediaTypeOf)).toEqual(['image/png', 'image/jpeg', 'image/jpeg', 'image/gif', 'image/webp'])
    expect(imageBlock('/x/2.jpg', 'QUJD')).toEqual({ type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data: 'QUJD' } })
  })

  test("the slug is the transcript's folder", async () => {
    expect(slugOf('/Users/me/.claude/projects/-work-repo/sess-1.jsonl')).toBe('-work-repo')
  })

  test('pastes become image blocks after the engine text, in number order', async () => {
    const h = harness()
    await h.start()
    await h.classicStart('/Users/me/.claude/projects/-work-repo/sess-1.jsonl', 'sess-1')
    h.paste(FOLDER, '1.png') // a prompt's paste, before the ask
    const pending = h.call(ASK_TOOL, { questions: [BACKEND, FEATURES] })
    await h.settle()
    h.paste(FOLDER, '3.jpg', '2.png')
    const text = 'The user answered: "Which backend?"="(Image attached)", "Which features?"="Auth, mine (Image attached)".'
    await h.raise(0, answered(text, { 'Which backend?': '(Image attached)', 'Which features?': 'mine (Image attached)' }))
    expect((await pending).result).toEqual({
      result: [
        { type: 'text', text },
        { type: 'image', source: { type: 'base64', media_type: 'image/png', data: `bytes:${FOLDER}/2.png` } },
        { type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data: `bytes:${FOLDER}/3.jpg` } },
      ],
    })
  })

  test('no pastes leave the plain text', async () => {
    const h = harness()
    await h.start()
    await h.classicStart('/Users/me/.claude/projects/-work-repo/sess-1.jsonl', 'sess-1')
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    await h.raise(0, answered('answer'))
    expect((await pending).result).toEqual({ result: 'answer' })
  })

  test('two dialogs queued together: each takes only its own pastes', async () => {
    const h = harness()
    await h.start()
    await h.classicStart('/Users/me/.claude/projects/-work-repo/sess-1.jsonl', 'sess-1')
    const first = h.call(ASK_TOOL, { questions: [BACKEND] })
    const second = h.call(ASK_TOOL, { questions: [FEATURES] })
    await h.settle()
    h.paste(FOLDER, '1.png')
    await h.raise(0, answered('first', { 'Which backend?': 'x (Image attached)' }))
    await first
    h.paste(FOLDER, '2.png')
    await h.raise(1, answered('second', { 'Which features?': '(Image attached)' }))
    const blocks = (await second).result as { result: { type: string; source?: { data: string } }[] }
    expect(blocks.result.map((b) => b.source?.data ?? b.type)).toEqual(['text', `bytes:${FOLDER}/2.png`])
  })

  test('the temp root follows CLAUDE_CODE_TMPDIR', async () => {
    const h = harness({ tmpdir: '/scratch/', dirs: { '/scratch': ['claude-77'], '/scratch/claude-77': [] }, unreadable: [] })
    await h.start()
    await h.classicStart('/p/-repo/s.jsonl', 's')
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    h.paste('/scratch/claude-77/-repo/s/images', '1.png')
    await h.raise(0, answered('answer', { 'Which backend?': '(Image attached)' }))
    expect(((await pending).result as { result: unknown[] }).result.length).toBe(2)
  })

  test('a store that cannot be placed leaves the text, with a debug line', async () => {
    const h = harness({ dirs: { '/tmp': ['other'] }, unreadable: [] })
    await h.start()
    await h.classicStart('/p/-repo/s.jsonl', 's')
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    await h.raise(0, answered('answer'))
    expect((await pending).result).toEqual({ result: 'answer' })
    expect(h.calls.some((c) => c.op === 'ui.log' && String(c.args).includes('temp root was not found'))).toBe(true)
  })
})

describe('pictures the human kept', () => {
  const FOLDER = '/tmp/claude-501/-work-repo/sess-1/images'
  const ready = async () => {
    const h = harness()
    await h.start()
    await h.classicStart('/Users/me/.claude/projects/-work-repo/sess-1.jsonl', 'sess-1')
    return h
  }

  test('imageMarks counts the answers the engine marked as carrying a picture', async () => {
    expect(imageMarks(['(Image attached)', 'mine (Image attached)', 'SQLite', 'Auth, Export'])).toBe(2)
    expect(imageMarks([])).toBe(0)
  })

  test('a picture pasted and then removed is not sent', async () => {
    const h = await ready()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    h.paste(FOLDER, '1.png') // the store keeps it; the dialog dropped it
    await h.raise(0, answered('The user answered: "Which backend?"="like this".', { 'Which backend?': 'like this' }))
    expect((await pending).result).toEqual({ result: 'The user answered: "Which backend?"="like this".' })
    expect(h.calls.some((c) => c.op === 'fs.read')).toBe(false)
  })

  test('more pastes than marked answers: which were kept is unknown, so none is sent and the debug log says so', async () => {
    const h = await ready()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    h.paste(FOLDER, '1.png', '2.png') // one removed, or both kept in one answer: the mod cannot tell
    await h.raise(0, answered('The user answered: "Which backend?"="x (Image attached)".', { 'Which backend?': 'x (Image attached)' }))
    expect((await pending).result).toEqual({ result: 'The user answered: "Which backend?"="x (Image attached)".' })
    expect(h.calls.some((c) => c.op === 'ui.log' && String(c.args).includes('2 pictures were pasted and 1 answer carries one'))).toBe(true)
  })

  test('"Chat about this" keeps the refusal and names each kept picture by its real path, one line each', async () => {
    const h = await ready()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    h.paste(FOLDER, '1.png')
    const chat = `${CHAT}\n    Questions asked:\n- "Which backend?"\n  Answer: like this (Image attached)`
    await h.raise(0, refused(chat))
    expect((await pending).result).toEqual({ deny: `${chat}\n[Image: source: /private${FOLDER}/1.png]` })
  })

  test('"Chat about this" with a removed picture is the plain refusal', async () => {
    const h = await ready()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    h.paste(FOLDER, '1.png')
    const chat = `${CHAT}\n    Questions asked:\n- "Which backend?"\n  Answer: like this`
    await h.raise(0, refused(chat))
    expect((await pending).result).toEqual({ deny: chat })
  })

  test('Esc sends no pictures', async () => {
    const h = await ready()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    h.paste(FOLDER, '1.png')
    await h.raise(0, refused(ESC))
    expect((await pending).result).toEqual({ deny: ESC })
  })
})

describe('when a hook fails', () => {
  test('the withdrawal holds for the model; another call, or a raise already passed on, goes on', async () => {
    const h = harness()
    await h.start()
    const e = { tool: 'AskUserQuestion', tool_use_id: 't', questions: [BACKEND] }
    expect(await h.fail('tool.call', e, { kind: 'throw' }).answer).toEqual({ deny: WITHDRAWN })
    expect((await h.fail('tool.call', e, { kind: 'throw', origin: MOD }).answer)).toEqual({ ref: 9, result: 'ran', text: 'ran' })
    expect((await h.fail('tool.call', e, { kind: 'throw', called: true }).answer)).toEqual({ ref: 9, result: 'ran', text: 'ran' })
  })

  test("the tool's own failure is a refusal naming it; asked in its place for its dialog's call, it passes the call on", async () => {
    const h = harness()
    await h.start()
    const ask = { tool: ASK_TOOL, tool_use_id: 't', questions: [BACKEND] }
    expect(await h.fail('tool.call', ask, { kind: 'timeout' }).answer).toEqual({ deny: 'The question could not be asked: the hook ran out of time.' })
    expect(await h.fail('tool.call', ask, { kind: 're-entry', origin: MOD }).answer).toEqual({ ref: 9, result: 'ran', text: 'ran' })
  })
})
