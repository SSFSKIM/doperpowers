import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import type { AskNote, AskQuestion } from '../../hooks/mods/ask'
import {
  ASK_TOOL,
  answerAsync,
  observeAsks,
  ASYNC_PARAGRAPH,
  ASYNC_RESULT,
  INPUT_SCHEMA,
  LATCHED,
  SUBAGENT_REFUSAL,
  WITHDRAWN,
  answerRows,
  askRow,
  deliveredIds,
  deliveryText,
  describeAsk,
  imageBlock,
  imageMarks,
  imageSourceLine,
  isAccepted,
  mediaTypeOf,
  newImages,
  asyncAsks,
  rebuildAsks,
  registerAsk,
  registerAskBand,
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
      '`async`: set it to true when you can go on with other work while the human decides. The call then returns at once; the questions wait in the human\'s view until they answer, and their answer reaches you in a later message that quotes each question. Leave it false when the work is blocked by the answer, nothing useful can proceed without the answer, or the answer is the last thing left in your turn.',
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
  options: {
    builtin?: string | undefined
    tmpdir?: string
    /** MAWS_NATIVE_TO_HUMAN's value; unset by default. */
    maws?: string
    dirs?: Record<string, string[]>
    unreadable?: string[]
    whileStarting?: () => Promise<unknown>
    register?: () => Promise<void>
    /** What `$.prompt.submit` answers; entered by default. */
    submit?: (text: string) => Promise<unknown>
    /** Text files `$.fs.read` reads; one missing rejects. */
    files?: Record<string, string>
    /** What `$.process.run` prints. */
    run?: (argv: readonly string[]) => Promise<{ exitCode: number; stdout: string; isStdoutTruncated: boolean }>
    /** Runs while `$.fs.stat` is awaited, before it answers. */
    whileStat?: (path: string) => void
  } = {},
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
    env: { get: async (name: string) => (name === 'CLAUDE_CODE_TMPDIR' ? options.tmpdir : name === 'MAWS_NATIVE_TO_HUMAN' ? options.maws : undefined) },
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
      stat: async (path: string, opts?: { resolve?: boolean }) => {
        options.whileStat?.(path)
        return { kind: 'file', size: 1, mtimeMs: 0, isLink: false, ...(opts?.resolve === true && { realPath: `/private${path}` }) }
      },
      read: async (path: string, opts?: { as?: string }) => {
        calls.push({ op: 'fs.read', args: { path, ...opts } })
        if (opts?.as !== 'bytes') {
          const text = options.files?.[path]
          if (text === undefined) {
            throw new Error(`ENOENT or too large: ${path}`)
          }
          return text
        }
        return { base64: `bytes:${path}` }
      },
    },
    process: {
      run: async (argv: readonly string[]) => {
        calls.push({ op: 'process.run', args: argv })
        if (options.run === undefined) {
          throw new Error('no such command')
        }
        return options.run(argv)
      },
    },
    prompt: {
      submit: async ({ text }: { text: string }) => {
        calls.push({ op: 'prompt.submit', args: text })
        return options.submit === undefined ? { text } : options.submit(text)
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
  registerAskBand(on)
  registerAsk(on)
  const engine = $ as unknown as EngineInterface

  const matching = (event: string, e: Record<string, unknown>) =>
    hooks.filter((h) => h.event === event && Object.entries(h.matcher ?? {}).every(([k, v]) => (v instanceof RegExp ? v.test(String(e[k])) : e[k] === v)))

  /** Runs `e` down the chain of `event`, outermost first; `bottom` answers beneath. */
  const dispatch = (event: string, e: Record<string, unknown>, origin: Origin, bottom: (e: Record<string, unknown>) => unknown, signal = new AbortController().signal) => {
    const chain = matching(event, e)
    const at = (i: number, input: Record<string, unknown>): unknown => {
      const hook = chain[i]
      if (hook === undefined) {
        return bottom(input)
      }
      const next = Object.assign(async (inner: Record<string, unknown>) => at(i + 1, inner), { origin, signal })
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

  const classicStart = (transcript_path: string, session_id: string, source = 'startup') =>
    dispatch('classic.SessionStart', { hook_event_name: 'SessionStart', source, transcript_path, session_id, cwd: '/' }, MODEL, async () => ({}))

  const turnStart = (agentId?: string) =>
    dispatch('turn.start', { text: '', turnId: 'turn-2', ...(agentId !== undefined && { agentId }) }, MODEL, async (e) => ({ turnId: e.turnId }))

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
  /** `interrupted`: the person's interrupt cuts the call while it runs, aborting the dispatch. */
  const call = async (tool: string, args: Record<string, unknown>, origin: Origin = MODEL, agentId?: string, interrupted = false) => {
    const ran: Record<string, unknown>[] = []
    const abort = new AbortController()
    const e = { tool, tool_use_id: `toolu_${calls.length}`, ...args, ...(agentId !== undefined && { agentId }) }
    const result = await dispatch(
      'tool.call',
      e,
      origin,
      async (inner) => {
        ran.push(inner)
        if (interrupted) {
          abort.abort()
          return { ref: 9, isError: true, result: undefined, text: 'interrupted' }
        }
        return { ref: 9, result: 'ran', text: 'ran' }
      },
      abort.signal,
    )
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

  const turnComplete = (reason: string, agentId?: string) =>
    dispatch('turn.complete', { turnId: 'turn-1', reason, answer: '', durationMs: 1, isAborted: reason === 'aborted', ...(agentId !== undefined && { agentId }) }, MODEL, async () => ({ text: '' }))

  /** The person's prompt through the prompt.submit hooks; `bottom` answers beneath (entered, by default). */
  const prompt = (text: string, bottom: (e: Record<string, unknown>) => unknown = (e) => ({ text: e.text, context: e.context })) =>
    dispatch('prompt.submit', { text, wait: false, origin: { kind: 'user' } }, MODEL, async (e) => bottom(e)) as Promise<{ text?: string; context?: string[]; drop?: string }>

  const press = (element: string) => dispatch('ui.press', { element, component: 'ToolUse', requestId: 'r' }, MODEL, async () => ({}))

  const submitted = () => calls.filter((c) => c.op === 'prompt.submit').map((c) => c.args as string)

  return { calls, raises, start, call, raise, settle, describe, registered, engine, dispatch, paste, classicStart, turnStart, step, fail, turnComplete, prompt, press, submitted }
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

  test('under MAWS the tool is not registered and the built-in is left as described', async () => {
    const h = harness({ maws: '4' })
    await h.start()
    expect(h.registered()).toEqual([])
    expect(await h.describe('AskUserQuestion', 'The whole text.')).toEqual({ description: 'The whole text.', isDeferred: true })
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

  test("a subagent's turn starting does not unlatch it", async () => {
    const h = await declined(ESC)
    await h.turnStart('agent-1')
    expect((await h.call('Write', { file_path: 'x.txt' })).result).toEqual({ deny: LATCHED })
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

  test("a picture's line is the engine's source-only form", async () => {
    expect(imageSourceLine('/private/tmp/x/1.png')).toBe('[Image source: /private/tmp/x/1.png]')
  })

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
    expect((await pending).result).toEqual({ deny: `${chat}\n[Image source: /private${FOLDER}/1.png]` })
  })

  test('"Chat about this" reads a whole answer, over several lines, for its mark', async () => {
    const h = await ready()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND, FEATURES] })
    await h.settle()
    h.paste(FOLDER, '1.png')
    const chat = `${CHAT}\n    Questions asked:\n- "Which backend?"\n  Answer: first line\nsecond line (Image attached)\n- "Which features?"\n  (No answer provided)`
    await h.raise(0, refused(chat))
    expect((await pending).result).toEqual({ deny: `${chat}\n[Image source: /private${FOLDER}/1.png]` })
  })

  test('"Chat about this" with notes after an answer: the answer ends where the notes begin', async () => {
    const h = await ready()
    const pending = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    h.paste(FOLDER, '1.png')
    const chat = `${CHAT}\n    Questions asked:\n- "Which backend?"\n  Answer: this (Image attached)\n  User notes: later (Image attached)`
    await h.raise(0, refused(chat))
    expect((await pending).result).toEqual({ deny: `${chat}\n[Image source: /private${FOLDER}/1.png]` })
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

const ANSWER = 'Your questions have been answered: "Which backend?"="SQLite". You can now continue with these answers in mind.'

describe('the delivery text', () => {
  test('the head names the call, then the engine text', async () => {
    expect(deliveryText('toolu_1', ANSWER)).toBe(`The human responded to your async AskUserQuestion (call toolu_1): ${ANSWER}`)
  })

  // The stored forms, as a live session on 2.1.296 recorded them (2026-10-13).
  test('the call ids round-trip through every form a delivery is stored in', async () => {
    const one = deliveryText('toolu_A', ANSWER)
    const two = deliveryText('toolu_B', 'The user answered: "Which features?"="Auth, Export". Read the answers carefully.')
    // A tool result's context: an attachment whose content is the list of entries.
    const result = { type: 'hook_additional_context', content: [one, two], hookName: 'tool.call', toolUseID: 'toolu_X-context', hookEvent: 'PostToolUse' }
    expect(result.content.flatMap(deliveredIds)).toEqual(['toolu_A', 'toolu_B'])
    // A prompt the plugin submitted: the engine's framing around the text.
    const framed = `The doperpowers plugin sent a message:\n${one}\n\n${two}\n\nThis is how Claude Code surfaces a prompt a plugin submits between turns — it starts this turn in the user's place. Address the message above.`
    expect(deliveredIds(framed)).toEqual(['toolu_A', 'toolu_B'])
    // A prompt.submit hook's context: the same attachment, under the prompt's hook.
    const prompt = { type: 'hook_additional_context', content: [one], hookName: 'prompt.submit', toolUseID: 'hook-1', hookEvent: 'UserPromptSubmit' }
    expect(prompt.content.flatMap(deliveredIds)).toEqual(['toolu_A'])
    expect(deliveredIds('The human answered something else (call toolu_C).')).toEqual([])
  })
})

describe('isAccepted', () => {
  const input = { questions: [BACKEND], async: true }
  test('a call whose result is the async result, not an error, with a valid input', async () => {
    expect(isAccepted(input, { content: ASYNC_RESULT })).toBe(true)
    expect(isAccepted(input, { content: [{ type: 'text', text: ASYNC_RESULT }] })).toBe(true)
  })
  test('not a validation refusal, a subagent refusal, a permission denial, or a call with no result', async () => {
    const single = { questions: [question('Pick one?', 'One', ['Only'])], async: true }
    expect(isAccepted(single, { content: `<tool_use_error>${validateQuestions(single)}</tool_use_error>`, is_error: true })).toBe(false)
    expect(isAccepted(single, { content: ASYNC_RESULT })).toBe(false)
    expect(isAccepted(input, { content: `<tool_use_error>${SUBAGENT_REFUSAL}</tool_use_error>`, is_error: true })).toBe(false)
    expect(isAccepted(input, { content: 'Permission to use mcp__doperpowers__AskUserQuestion has been denied.', is_error: true })).toBe(false)
    expect(isAccepted(input, { content: ASYNC_RESULT, is_error: true })).toBe(false)
    expect(isAccepted(input, undefined)).toBe(false)
  })
})

describe('an async ask', () => {
  const ready = async () => {
    const h = harness()
    await h.start()
    return h
  }
  /** An async ask accepted, then answered by a press; the human's Submit answers `answer`. */
  const answer = async (h: ReturnType<typeof harness>, id: string, result: Answer) => {
    const pressed = h.press(`ask-answer:${id}`)
    await h.settle()
    const i = h.raises.length - 1
    await h.raise(i, result)
    await pressed
    await h.settle()
  }
  test('returns at once with the async result, opens no dialog, and stands open', async () => {
    const h = await ready()
    const { result } = await h.call(ASK_TOOL, { questions: [BACKEND, FEATURES], async: true })
    expect(result).toEqual({ result: ASYNC_RESULT })
    expect(h.raises).toEqual([])
    expect(asyncAsks().map((a) => ({ status: a.status, questions: a.questions }))).toEqual([{ status: 'open', questions: [BACKEND, FEATURES] }])
    expect(ASYNC_RESULT).toBe(
      'Your questions are waiting for the human; this call does not wait for them. Their answer will reach you in a later message that quotes each question. Go on with work that does not depend on it.',
    )
  })

  test('an invalid async ask is refused like a blocking one, and is no ask', async () => {
    const h = await ready()
    const input = { questions: [question('Pick one?', 'One', ['Only'])], async: true }
    expect((await h.call(ASK_TOOL, input)).result).toEqual({ deny: validateQuestions(input) })
    expect(asyncAsks()).toEqual([])
  })

  test('a press opens the engine dialog with the whole set; answered while idle, the answer is submitted at once', async () => {
    const h = await ready()
    await h.call(ASK_TOOL, { questions: [BACKEND, FEATURES], async: true })
    const [open] = asyncAsks()
    const pressed = h.press(`ask-answer:${open?.id}`)
    await h.settle()
    const { shown } = await h.raise(0, answered(ANSWER))
    await pressed
    await h.settle()
    expect(shown[0]?.questions).toEqual([BACKEND, FEATURES])
    expect(h.submitted()).toEqual([deliveryText(open?.id ?? '', ANSWER)])
    expect(asyncAsks()[0]).toMatchObject({ status: 'answered', answer: ANSWER })
  })

  test('a press on an ask whose dialog is already raised, or that is answered, does nothing', async () => {
    const h = await ready()
    await h.call(ASK_TOOL, { questions: [BACKEND], async: true })
    const id = asyncAsks()[0]?.id ?? ''
    const first = h.press(`ask-answer:${id}`)
    await h.settle()
    await h.press(`ask-answer:${id}`)
    await h.settle()
    expect(h.raises.length).toBe(1)
    await h.raise(0, answered(ANSWER))
    await first
    await h.press(`ask-answer:${id}`)
    await h.settle()
    expect(h.raises.length).toBe(1)
  })

  test('Esc is "not now": nothing is delivered, the ask stays open, and a later press opens it again', async () => {
    const h = await ready()
    await h.call(ASK_TOOL, { questions: [BACKEND], async: true })
    const id = asyncAsks()[0]?.id ?? ''
    await answer(h, id, refused(ESC))
    expect(h.submitted()).toEqual([])
    expect(asyncAsks()[0]?.status).toBe('open')
    // Esc on the mod's own dialog does not latch the turn.
    expect((await h.call('Bash', { command: 'ls' })).ran.length).toBe(1)
    await answer(h, id, answered(ANSWER))
    expect(h.raises.length).toBe(2)
    expect(h.submitted()).toEqual([deliveryText(id, ANSWER)])
  })

  test('"Chat about this" is delivered as the blocking call would have returned it, and closes the ask', async () => {
    const h = await ready()
    await h.call(ASK_TOOL, { questions: [BACKEND], async: true })
    const id = asyncAsks()[0]?.id ?? ''
    await answer(h, id, refused(CHAT))
    expect(h.submitted()).toEqual([deliveryText(id, CHAT)])
    expect(asyncAsks()[0]).toMatchObject({ status: 'answered', answer: CHAT })
  })

  test('pasted pictures the human kept follow the engine text, one source line each', async () => {
    const FOLDER = '/tmp/claude-501/-work-repo/sess-1/images'
    const h = await ready()
    await h.classicStart('/Users/me/.claude/projects/-work-repo/sess-1.jsonl', 'sess-1')
    await h.call(ASK_TOOL, { questions: [BACKEND], async: true })
    const id = asyncAsks()[0]?.id ?? ''
    const pressed = h.press(`ask-answer:${id}`)
    await h.settle()
    h.paste(FOLDER, '1.png')
    const text = 'The user answered: "Which backend?"="like this (Image attached)". Read the answers carefully.'
    await h.raise(0, answered(text, { 'Which backend?': 'like this (Image attached)' }))
    await pressed
    await h.settle()
    expect(h.submitted()).toEqual([deliveryText(id, `${text}\n[Image source: /private${FOLDER}/1.png]`)])
    expect(h.calls.some((c) => c.op === 'fs.read')).toBe(false)
  })
})

describe('delivery while the model works', () => {
  /** A running turn with an async ask answered in it: the answer is held. */
  const held = async (text = ANSWER) => {
    const h = harness()
    await h.start()
    await h.turnStart()
    await h.call(ASK_TOOL, { questions: [BACKEND], async: true })
    const id = asyncAsks().at(-1)?.id ?? ''
    const pressed = h.press(`ask-answer:${id}`)
    await h.settle()
    await h.raise(h.raises.length - 1, answered(text))
    await pressed
    await h.settle()
    return { h, id }
  }

  test('held while a turn runs, then carried once on the next model-made result', async () => {
    const { h, id } = await held()
    expect(h.submitted()).toEqual([])
    const first = await h.call('Bash', { command: 'sleep 60' })
    expect(first.result).toEqual({ ref: 9, result: 'ran', text: 'ran', context: [deliveryText(id, ANSWER)] })
    const second = await h.call('Bash', { command: 'echo second' })
    expect(second.result).toEqual({ ref: 9, result: 'ran', text: 'ran' })
    await h.turnComplete('answer')
    await h.settle()
    expect(h.submitted()).toEqual([])
  })

  test("not on a call the human's interrupt cut: the engine keeps no context there", async () => {
    const { h, id } = await held()
    expect((await h.call('Bash', { command: 'sleep 60' }, MODEL, undefined, true)).result).toEqual({ ref: 9, isError: true, result: undefined, text: 'interrupted' })
    await h.turnComplete('aborted')
    expect((await h.prompt('go on')).context).toEqual([deliveryText(id, ANSWER)])
  })

  test("never on a plugin's call, a subagent's, or a deny", async () => {
    const { h, id } = await held()
    expect((await h.call('Read', { file_path: 'a' }, OTHER)).result).toEqual({ ref: 9, result: 'ran', text: 'ran' })
    expect((await h.call('Read', { file_path: 'a' }, MODEL, 'agent-1')).result).toEqual({ ref: 9, result: 'ran', text: 'ran' })
    expect((await h.call('AskUserQuestion', { questions: [BACKEND] })).result).toEqual({ deny: WITHDRAWN })
    expect((await h.call('Read', { file_path: 'a' })).result).toEqual({ ref: 9, result: 'ran', text: 'ran', context: [deliveryText(id, ANSWER)] })
  })

  test("two answers go out together, once each; ask A's answer held while ask B's dialog settles goes on the model's result, not B's nested call", async () => {
    const h = harness()
    await h.start()
    await h.turnStart()
    await h.call(ASK_TOOL, { questions: [BACKEND], async: true })
    await h.call(ASK_TOOL, { questions: [FEATURES], async: true })
    const [a, b] = asyncAsks()
    const pressA = h.press(`ask-answer:${a?.id}`)
    const pressB = h.press(`ask-answer:${b?.id}`)
    await h.settle()
    await h.raise(0, answered('answer A'))
    await pressA
    await h.settle()
    const nested = await h.raise(1, answered('answer B'))
    expect(nested.result).not.toHaveProperty('context')
    await pressB
    await h.settle()
    const { result } = await h.call('Bash', { command: 'sleep 40' })
    expect(result).toEqual({ ref: 9, result: 'ran', text: 'ran', context: [deliveryText(a?.id ?? '', 'answer A'), deliveryText(b?.id ?? '', 'answer B')] })
    expect((await h.call('Bash', { command: 'ls' })).result).not.toHaveProperty('context')
  })

  test("a blocking ask's own result carries an answer held while its dialog was up", async () => {
    const h = harness()
    await h.start()
    await h.turnStart()
    await h.call(ASK_TOOL, { questions: [FEATURES], async: true })
    const id = asyncAsks()[0]?.id ?? ''
    const pressed = h.press(`ask-answer:${id}`)
    await h.settle()
    const blocking = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    await h.raise(0, answered('answer A'))
    await pressed
    await h.settle()
    await h.raise(1, answered('blocking answer'))
    expect((await blocking).result).toEqual({ result: 'blocking answer', context: [deliveryText(id, 'answer A')] })
  })

  test('a turn the model answered submits what is held, in one prompt', async () => {
    const { h, id } = await held()
    await h.turnComplete('answer')
    await h.settle()
    expect(h.submitted()).toEqual([deliveryText(id, ANSWER)])
  })

  test("a subagent's turn starting after the main turn ended is not a main turn: an answer then is submitted at once", async () => {
    const h = harness()
    await h.start()
    await h.turnStart()
    await h.call(ASK_TOOL, { questions: [BACKEND], async: true })
    await h.turnComplete('answer')
    await h.turnStart('agent-1')
    const id = asyncAsks()[0]?.id ?? ''
    const pressed = h.press(`ask-answer:${id}`)
    await h.settle()
    await h.raise(0, answered(ANSWER))
    await pressed
    await h.settle()
    expect(h.submitted()).toEqual([deliveryText(id, ANSWER)])
  })

  test("a subagent's turn end is not the main turn's", async () => {
    const { h } = await held()
    await h.turnComplete('answer', 'agent-1')
    await h.settle()
    expect(h.submitted()).toEqual([])
  })

  test("a turn that ends otherwise keeps what is held, and the human's next prompt carries it as context", async () => {
    for (const reason of ['aborted', 'error', 'refusal']) {
      const { h, id } = await held()
      await h.turnComplete(reason)
      await h.settle()
      expect(h.submitted()).toEqual([])
      expect(await h.prompt('go on')).toEqual({ text: 'go on', context: [deliveryText(id, ANSWER)] })
      expect(await h.prompt('and again')).toEqual({ text: 'and again', context: undefined })
    }
  })

  test('a turn latched by a declined blocking ask keeps what is held, whatever its reason', async () => {
    const { h, id } = await held()
    const blocking = h.call(ASK_TOOL, { questions: [FEATURES] })
    await h.settle()
    await h.raise(h.raises.length - 1, refused(ESC))
    expect((await blocking).result).toEqual({ deny: ESC })
    await h.turnComplete('answer')
    await h.settle()
    expect(h.submitted()).toEqual([])
    expect((await h.prompt('go on')).context).toEqual([deliveryText(id, ANSWER)])
  })

  test('a submission that is dropped or rejected puts its answers back ahead of any answered meanwhile', async () => {
    for (const failure of [async () => ({ drop: 'a hook dropped it' }), async () => Promise.reject(new Error('refused'))]) {
      let release: (v: unknown) => void = () => {}
      const h = harness({ submit: () => new Promise((resolve) => (release = resolve)).then(failure) })
      await h.start()
      await h.turnStart()
      await h.call(ASK_TOOL, { questions: [BACKEND], async: true })
      await h.call(ASK_TOOL, { questions: [FEATURES], async: true })
      const [a, b] = asyncAsks()
      const pressA = h.press(`ask-answer:${a?.id}`)
      await h.settle()
      await h.raise(0, answered('answer A'))
      await pressA
      await h.turnComplete('answer')
      await h.settle()
      expect(h.submitted()).toEqual([deliveryText(a?.id ?? '', 'answer A')])
      // While the submission is pending, a result does not carry its answer a second time.
      await h.turnStart()
      expect((await h.call('Bash', { command: 'ls' })).result).not.toHaveProperty('context')
      const pressB = h.press(`ask-answer:${b?.id}`)
      await h.settle()
      await h.raise(1, answered('answer B'))
      await pressB
      release(undefined)
      await h.settle()
      expect(h.calls.some((c) => c.op === 'ui.toast')).toBe(true)
      expect((await h.call('Bash', { command: 'ls' })).result).toEqual({
        ref: 9,
        result: 'ran',
        text: 'ran',
        context: [deliveryText(a?.id ?? '', 'answer A'), deliveryText(b?.id ?? '', 'answer B')],
      })
    }
  })

  test("the human's prompt rejected beneath puts its answers back before the failure goes on", async () => {
    const { h, id } = await held()
    await h.turnComplete('aborted')
    await expect(
      h.prompt('go on', () => {
        throw new Error('a hook beneath broke')
      }),
    ).rejects.toThrow('a hook beneath broke')
    expect((await h.prompt('again')).context).toEqual([deliveryText(id, ANSWER)])
  })

  test("the human's prompt dropped beneath puts its answers back", async () => {
    const { h, id } = await held()
    await h.turnComplete('aborted')
    expect(await h.prompt('go on', () => ({ drop: 'blocked' }))).toEqual({ drop: 'blocked' })
    expect((await h.prompt('again')).context).toEqual([deliveryText(id, ANSWER)])
  })
})

describe('the rows', () => {
  test("answerRows reads each answered question from the engine's text, previews and notes aside", async () => {
    const text =
      'The user answered: "Which backend?"="SQLite" selected preview:\n+--------+\n| SQLite |\n+--------+ notes: board db only, "Which features?"="Auth, Export". Read the answers carefully — they may request clarification, changes, or that you not proceed — and follow what they actually say.'
    expect(answerRows([BACKEND, FEATURES], text)).toEqual([
      ['Which backend?', 'SQLite'],
      ['Which features?', 'Auth, Export'],
    ])
    expect(answerRows([BACKEND, FEATURES], ANSWER)).toEqual([['Which backend?', 'SQLite']])
    expect(answerRows([BACKEND], 'The user answered: "Which backend?"=(no option selected) notes: later. Read the answers carefully.')).toEqual([['Which backend?', '(notes only)']])
    expect(answerRows([BACKEND], 'The user answered: "Which backend?"="say "hi" (Image attached)". Read the answers carefully.\n[Image source: /x/1.png]')).toEqual([
      ['Which backend?', 'say "hi" (Image attached)'],
    ])
    expect(answerRows([BACKEND], 'The user did not answer the questions.')).toEqual([])
  })

  const props = (over: Record<string, unknown>) => ({ input: { questions: [BACKEND, FEATURES] }, output: undefined, isRunning: false, isErrored: false, isInterrupted: false, ...over })

  test('a blocking ask: nothing while its dialog is up, the answers once answered, declined once refused', async () => {
    expect(askRow(props({ isRunning: true }))).toEqual({ kind: 'none' })
    expect(askRow(props({ output: ANSWER }))).toEqual({ kind: 'answered', rows: [['Which backend?', 'SQLite']], isDelivered: true })
    expect(askRow(props({ output: [{ type: 'text', text: ANSWER }, { type: 'image' }] }))).toEqual({ kind: 'answered', rows: [['Which backend?', 'SQLite']], isDelivered: true })
    expect(askRow(props({ output: 'The user did not answer the questions.' }))).toEqual({ kind: 'none' })
    expect(askRow(props({ isErrored: true, output: `<tool_use_error>${ESC}</tool_use_error>` }))).toEqual({ kind: 'declined', questions: [BACKEND, FEATURES], isDelivered: true })
    expect(askRow(props({ isErrored: true, output: CHAT }))).toEqual({ kind: 'declined', questions: [BACKEND, FEATURES], isDelivered: true })
  })

  test("other errors, an interruption, and an async call the mod does not know draw as the engine's", async () => {
    expect(askRow(props({ isErrored: true, output: `<tool_use_error>${SUBAGENT_REFUSAL}</tool_use_error>` }))).toEqual({ kind: 'engine' })
    expect(askRow(props({ isInterrupted: true }))).toEqual({ kind: 'engine' })
    expect(askRow(props({ output: ASYNC_RESULT }))).toEqual({ kind: 'engine' })
  })

  test('an async ask: open with its questions, then its answers, saying so until they reached the model', async () => {
    const open = { id: 't', questions: [BACKEND], status: 'open' as const }
    expect(askRow(props({ output: ASYNC_RESULT }), open)).toEqual({ kind: 'open', questions: [BACKEND] })
    const done = { ...open, status: 'answered' as const, answer: ANSWER }
    expect(askRow(props({ output: ASYNC_RESULT }), done, false)).toEqual({ kind: 'answered', rows: [['Which backend?', 'SQLite']], isDelivered: false })
    expect(askRow(props({ output: ASYNC_RESULT }), done, true)).toEqual({ kind: 'answered', rows: [['Which backend?', 'SQLite']], isDelivered: true })
    expect(askRow(props({ output: ASYNC_RESULT }), { ...open, status: 'answered', answer: CHAT }, true)).toEqual({ kind: 'declined', questions: [BACKEND], isDelivered: true })
  })
})

describe('a resumed session', () => {
  const T = '/p/-repo/s.jsonl'
  // The conversation's rows, each the child of the one written before it, as
  // the engine stores them; `line` is a metadata row, which carries no uuid.
  let rowCount = 0
  let lastUuid: string | null = null
  const line = (row: unknown) => JSON.stringify(row)
  const row = (r: Record<string, unknown>) => {
    const uuid = `u${++rowCount}`
    const stored = JSON.stringify({ parentUuid: lastUuid, uuid, ...r })
    lastUuid = uuid
    return stored
  }
  const use = (id: string, input: unknown) => row({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'tool_use', id, name: ASK_TOOL, input }] } })
  const result = (id: string, content: unknown, is_error?: boolean) =>
    row({ type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content, ...(is_error && { is_error }) }] } })
  const single = { questions: [question('Pick one?', 'One', ['Only'])], async: true }
  const lines = [
    use('t-open', { questions: [BACKEND], async: true }),
    result('t-open', ASYNC_RESULT),
    // The engine's wire copy of a request's message repeats a call: not a second ask.
    line({ type: 'api-request-blob', sessionId: 's', hash: 'h1', message: { role: 'assistant', content: [{ type: 'tool_use', id: 't-open', name: ASK_TOOL, input: { questions: [BACKEND], async: true } }] } }),
    use('t-done', { questions: [FEATURES], async: true }),
    result('t-done', [{ type: 'text', text: ASYNC_RESULT }]),
    use('t-bad', single),
    result('t-bad', `<tool_use_error>${validateQuestions(single)}</tool_use_error>`, true),
    use('t-blocking', { questions: [BACKEND] }),
    result('t-blocking', ANSWER),
    use('t-cut', { questions: [BACKEND], async: true }),
    row({ type: 'attachment', attachment: { type: 'hook_additional_context', content: [deliveryText('t-done', 'Your questions have been answered: "Which features?"="Auth". You can now continue with these answers in mind.')] } }),
    // The model quoting a delivery is not one, nor the queue's record of a prompt that may never have entered.
    row({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'text', text: deliveryText('t-open', 'made up') }] } }),
    line({ type: 'queue-operation', operation: 'enqueue', content: `The doperpowers plugin sent a message:\n${deliveryText('t-open', 'dropped')}` }),
    line({ type: 'last-prompt', lastPrompt: `The doperpowers plugin sent a message: ${deliveryText('t-open', 'dropped')}` }),
    // A tool's output that prints a delivery (a read of this transcript) is not one either,
    // nor the human quoting one in a prompt of their own.
    result('t-cat', `{"content":["${deliveryText('t-open', 'printed')}"]}`),
    row({ type: 'user', message: { role: 'user', content: `what does this mean? ${deliveryText('t-open', 'quoted')}` } }),
    row({ type: 'user', message: { role: 'user', content: [{ type: 'text', text: deliveryText('t-open', 'quoted') }] } }),
  ]

  test('rebuildAsks keeps the accepted asks, open or answered by a later delivery', async () => {
    expect(rebuildAsks(lines)).toEqual([
      { id: 't-open', questions: [BACKEND], status: 'open' },
      { id: 't-done', questions: [FEATURES], status: 'answered', answer: 'Your questions have been answered: "Which features?"="Auth". You can now continue with these answers in mind.' },
    ])
    const submittedRow = row({ type: 'user', message: { role: 'user', content: `The doperpowers plugin sent a message:\n${deliveryText('t-open', ANSWER)}` } })
    expect(rebuildAsks([...lines, submittedRow])[0]).toEqual({ id: 't-open', questions: [BACKEND], status: 'answered', answer: ANSWER })
    expect(rebuildAsks(['not json', ''])).toEqual([])
  })

  test('at a resumed SessionStart the asks are read back from the transcript', async () => {
    const h = harness({ files: { [T]: lines.join('\n') } })
    await h.start()
    await h.classicStart(T, 's', 'resume')
    expect(asyncAsks().map((a) => [a.id, a.status])).toEqual([
      ['t-open', 'open'],
      ['t-done', 'answered'],
    ])
    expect(h.calls.some((c) => c.op === 'ui.invalidate' && c.args === 'ui.render')).toBe(true)
  })

  test('a transcript too large to read whole is searched for the lines that can matter', async () => {
    const h = harness({ run: async () => ({ exitCode: 0, stdout: lines.join('\n'), isStdoutTruncated: false }) })
    await h.start()
    await h.classicStart(T, 's', 'resume')
    expect(asyncAsks().length).toBe(2)
    const argv = h.calls.find((c) => c.op === 'process.run')?.args as string[]
    expect(argv[0]).toBe('grep')
    expect(argv.at(-1)).toBe(T)
  })

  test('the search patterns find exactly the stored forms resume reads', async () => {
    const h = harness({ run: async () => ({ exitCode: 1, stdout: '', isStdoutTruncated: false }) })
    await h.start()
    await h.classicStart(T, 's', 'resume')
    const argv = h.calls.find((c) => c.op === 'process.run')?.args as string[]
    const patterns = argv.filter((_, i) => argv[i - 1] === '-e')
    const plugin = line({ type: 'user', message: { role: 'user', content: `The doperpowers plugin sent a message:\n${deliveryText('t-open', ANSWER)}` } })
    const human = line({ type: 'user', message: { role: 'user', content: `see ${deliveryText('t-open', ANSWER)}` } })
    const snapshot = line({ type: 'attachment', attachment: { type: 'prompt_snapshot', tools: [{ name: ASK_TOOL, description: 'd' }] } })
    const found = (row: string) => patterns.some((pattern) => row.includes(pattern))
    expect([...lines.slice(0, 4), lines[9] as string, plugin].map(found)).toEqual([true, true, true, true, true, true])
    expect([human, snapshot].map(found)).toEqual([false, false])
  })

  test('no line found is no ask; a failed search or a cut one rebuilds nothing, with a debug line', async () => {
    for (const [run, logged] of [
      [{ exitCode: 1, stdout: '', isStdoutTruncated: false }, undefined],
      [{ exitCode: 2, stdout: '', isStdoutTruncated: false }, 'could not be searched'],
      [{ exitCode: 0, stdout: lines.slice(0, 4).join('\n'), isStdoutTruncated: true }, 'past what one search returns'],
    ] as const) {
      const h = harness({ run: async () => run })
      await h.start()
      await h.classicStart(T, 's', 'resume')
      expect(asyncAsks()).toEqual([])
      const logs = h.calls.filter((c) => c.op === 'ui.log').map((c) => String(c.args))
      expect(logs.some((text) => logged !== undefined && text.includes(logged))).toBe(logged !== undefined)
    }
  })

  /** A row of a conversation with its ancestry spelled out. */
  const at = (uuid: string, parentUuid: string | null, r: Record<string, unknown>) => JSON.stringify({ parentUuid, uuid, ...r })
  const call = (uuid: string, parent: string | null, id: string, q: AskQuestion) =>
    at(uuid, parent, { type: 'assistant', message: { role: 'assistant', content: [{ type: 'tool_use', id, name: ASK_TOOL, input: { questions: [q], async: true } }] } })
  const accepted = (uuid: string, parent: string, id: string) =>
    at(uuid, parent, { type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: ASYNC_RESULT }] } })
  const delivered = (uuid: string, parent: string, id: string) =>
    at(uuid, parent, { type: 'attachment', attachment: { type: 'hook_additional_context', content: [deliveryText(id, ANSWER)] } })
  const prompt = (uuid: string, parent: string | null) => at(uuid, parent, { type: 'user', message: { role: 'user', content: 'go on' } })
  /** The engine's record of a rewind: the row it went back to, or none past the first prompt. */
  const rewind = (leafUuid: string | null) => line({ type: 'last-prompt', leafUuid, explicit: true, rewound: true })
  /**
   * One model response with an async ask and a Bash call, as the engine writes
   * it: a row per call sharing the response's id, each result parented to the
   * row of its own call, so the chain goes on from the last result and the
   * ask's result sits beside it. `deliveredOnResult`: a context attachment on
   * the ask's result carries a delivery for `deliveredId`.
   */
  const twoCalls = (prefix: string, parent: string, id: string, q: AskQuestion, deliveredId?: string) => {
    const response = { id: `msg_${prefix}`, role: 'assistant' }
    return [
      at(`${prefix}1`, parent, { type: 'assistant', message: { ...response, content: [{ type: 'tool_use', id, name: ASK_TOOL, input: { questions: [q], async: true } }] } }),
      at(`${prefix}2`, `${prefix}1`, { type: 'assistant', message: { ...response, content: [{ type: 'tool_use', id: `${id}-bash`, name: 'Bash', input: { command: 'sleep 40' } }] } }),
      at(`${prefix}3`, `${prefix}1`, { type: 'user', sourceToolAssistantUUID: `${prefix}1`, message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: ASYNC_RESULT }] } }),
      ...(deliveredId === undefined ? [] : [delivered(`${prefix}3c`, `${prefix}3`, deliveredId)]),
      at(`${prefix}4`, `${prefix}2`, { type: 'user', sourceToolAssistantUUID: `${prefix}2`, message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: `${id}-bash`, content: 'done' }] } }),
      at(`${prefix}5`, `${prefix}4`, { type: 'attachment', attachment: { type: 'output_style', style: 'x' } }),
    ]
  }
  // A, asked and accepted; then a branch the human rewound past: B asked, and A answered there.
  const rewound = [
    prompt('p1', null),
    call('a1', 'p1', 't-A', BACKEND),
    accepted('a2', 'a1', 't-A'),
    prompt('p2', 'a2'),
    call('b1', 'p2', 't-B', FEATURES),
    accepted('b2', 'b1', 't-B'),
    delivered('b3', 'b2', 't-A'),
  ]

  test('a branch the human rewound past is not the conversation: its asks and deliveries are left out', async () => {
    // Rewound to A's acceptance and went on from there.
    const wentOn = [...rewound, rewind('a2'), prompt('p3', 'a2'), at('r1', 'p3', { type: 'assistant', message: { role: 'assistant', content: [{ type: 'text', text: 'ok' }] } })]
    expect(rebuildAsks(wentOn)).toEqual([{ id: 't-A', questions: [BACKEND], status: 'open' }])
    // Rewound and left at once: the engine's record of the rewind names the leaf.
    expect(rebuildAsks([...rewound, rewind('a2')])).toEqual([{ id: 't-A', questions: [BACKEND], status: 'open' }])
    // Rewound to before the first prompt (the engine writes no leaf) and left: no conversation, no ask.
    expect(rebuildAsks([...rewound, rewind(null)])).toEqual([])
    // Not rewound: the latest record of the prompt names the row before it, and rows after it are still the conversation.
    expect(rebuildAsks([...rewound.slice(0, 4), line({ type: 'last-prompt', leafUuid: 'p2' }), ...rewound.slice(4)]).map((a) => [a.id, a.status])).toEqual([
      ['t-A', 'answered'],
      ['t-B', 'open'],
    ])
  })

  test('an async ask beside another call in one response is an ask, rewound or not', async () => {
    const response = [prompt('p1', null), ...twoCalls('m', 'p1', 't-A', BACKEND), prompt('p2', 'm5')]
    expect(rebuildAsks(response)).toEqual([{ id: 't-A', questions: [BACKEND], status: 'open' }])
    // A later branch rewound past: the kept conversation still holds the ask, beside the chain as the engine restores it.
    const later = [...response, call('b1', 'p2', 't-B', FEATURES), accepted('b2', 'b1', 't-B'), rewind('p2')]
    expect(rebuildAsks(later)).toEqual([{ id: 't-A', questions: [BACKEND], status: 'open' }])
    // A result parented elsewhere (a hook's notice under its call) is known by the call it answers:
    // the engine's own source record, or the call's id alone.
    const reparented = (keep: (result: Record<string, unknown>) => Record<string, unknown>) =>
      later.flatMap((stored) => {
        const parsed = JSON.parse(stored) as Record<string, unknown>
        if (parsed.uuid !== 'm3') return [stored]
        return [at('m1h', 'm1', { type: 'attachment', attachment: { type: 'hook_success' } }), JSON.stringify(keep({ ...parsed, parentUuid: 'm1h' }))]
      })
    expect(rebuildAsks(reparented((result) => result))).toEqual([{ id: 't-A', questions: [BACKEND], status: 'open' }])
    expect(rebuildAsks(reparented(({ sourceToolAssistantUUID: _, ...result }) => result))).toEqual([{ id: 't-A', questions: [BACKEND], status: 'open' }])
  })

  test('with a rewind, a delivery on a result beside the chain still closes its ask, and the side rows of a response come with it', async () => {
    const kept = [
      prompt('p1', null),
      ...twoCalls('m', 'p1', 't-A', BACKEND),
      prompt('p2', 'm5'),
      ...twoCalls('n', 'p2', 't-C', FEATURES, 't-A'),
      prompt('p3', 'n5'),
    ]
    const abandoned = [call('b1', 'p3', 't-B', { ...BACKEND, question: 'Which port?' }), accepted('b2', 'b1', 't-B'), delivered('b3', 'b2', 't-C')]
    expect(rebuildAsks([...kept, ...abandoned, rewind('p3')]).map((a) => [a.id, a.status])).toEqual([
      ['t-A', 'answered'],
      ['t-C', 'open'],
    ])
  })

  test('a compaction does not cut the conversation: the boundary goes on through its logical parent', async () => {
    const compacted = [
      prompt('p1', null),
      call('a1', 'p1', 't-A', BACKEND),
      accepted('a2', 'a1', 't-A'),
      call('c1', 'a2', 't-C', FEATURES),
      accepted('c2', 'c1', 't-C'),
      at('k1', null, { type: 'system', subtype: 'compact_boundary', logicalParentUuid: 'c2', content: 'Conversation compacted' }),
      at('k2', 'k1', { type: 'user', isCompactSummary: true, message: { role: 'user', content: 'Summary.' } }),
      delivered('k3', 'k2', 't-C'),
    ]
    expect(rebuildAsks(compacted).map((a) => [a.id, a.status])).toEqual([
      ['t-A', 'open'],
      ['t-C', 'answered'],
    ])
    // With a rewind after the boundary, the walk back crosses it.
    const branch = [call('b1', 'k3', 't-B', { ...BACKEND, question: 'Which port?' }), accepted('b2', 'b1', 't-B')]
    expect(rebuildAsks([...compacted, ...branch, rewind('k3')]).map((a) => [a.id, a.status])).toEqual([
      ['t-A', 'open'],
      ['t-C', 'answered'],
    ])
  })

  test('the lines a search found carry no ancestry to follow: every one counts', async () => {
    const found = rewound.filter((_, i) => i !== 0 && i !== 3)
    expect(rebuildAsks(found, { isWholeFile: false }).map((a) => [a.id, a.status])).toEqual([
      ['t-A', 'answered'],
      ['t-B', 'open'],
    ])
  })

  test('/clear forgets the asks; a compaction keeps them', async () => {
    const h = harness()
    await h.start()
    await h.call(ASK_TOOL, { questions: [BACKEND], async: true })
    await h.classicStart(T, 's', 'compact')
    expect(asyncAsks().length).toBe(1)
    await h.classicStart(T, 's2', 'clear')
    expect(asyncAsks()).toEqual([])
  })
})

describe('answered from outside the terminal (the bridge)', () => {
  /** A started session watched by an observer, with an async ask of BACKEND and FEATURES open. */
  const opened = async () => {
    const notes: AskNote[] = []
    const h = harness()
    observeAsks((note) => notes.push(note))
    await h.start()
    await h.call(ASK_TOOL, { questions: [BACKEND, FEATURES], async: true })
    const id = asyncAsks()[0]?.id ?? ''
    return { h, notes, id }
  }

  test('the observer is told of an async ask as it opens', async () => {
    const { notes, id } = await opened()
    expect(notes).toEqual([{ kind: 'open', id, questions: [BACKEND, FEATURES] }])
  })

  test('answered while idle: delivered at once, in the words the dialog would have produced, and the observer told who answered', async () => {
    const { h, notes, id } = await opened()
    expect(answerAsync(id, { 'Which backend?': 'SQLite', 'Which features?': 'Auth, Export' }, 'cli')).toEqual({ ok: true })
    await h.settle()
    const text = 'Your questions have been answered: "Which backend?"="SQLite", "Which features?"="Auth, Export". You can now continue with these answers in mind.'
    expect(h.submitted()).toEqual([deliveryText(id, text)])
    expect(asyncAsks()[0]).toMatchObject({ status: 'answered', answer: text })
    expect(notes.at(-1)).toEqual({ kind: 'answered', id, by: 'cli' })
    expect(answerRows([BACKEND, FEATURES], text)).toEqual([
      ['Which backend?', 'SQLite'],
      ['Which features?', 'Auth, Export'],
    ])
  })

  test('an answer that names no option reads as the engine words free text', async () => {
    const { h, id } = await opened()
    answerAsync(id, { 'Which backend?': 'MySQL, if you can' }, 'm-1')
    await h.settle()
    expect(h.submitted()).toEqual([
      deliveryText(
        id,
        'The user answered: "Which backend?"="MySQL, if you can". Read the answers carefully — they may request clarification, changes, or that you not proceed — and follow what they actually say.',
      ),
    ])
  })

  test('answered once: a second answer, or one for an ask that is none, is refused', async () => {
    const { id } = await opened()
    answerAsync(id, { 'Which backend?': 'SQLite' }, 'cli')
    expect(answerAsync(id, { 'Which backend?': 'Postgres' }, 'cli')).toEqual({ ok: false, error: `the question ${id} was already answered` })
    expect(answerAsync('toolu_none', { 'Which backend?': 'Postgres' }, 'cli')).toEqual({ ok: false, error: 'no async question toolu_none is open in this session' })
  })

  test('while a turn runs the answer is held, then rides the next model-made result', async () => {
    const { h, id } = await opened()
    await h.turnStart()
    answerAsync(id, { 'Which backend?': 'SQLite' }, 'cli')
    await h.settle()
    expect(h.submitted()).toEqual([])
    const { result } = await h.call('Bash', { command: 'ls' })
    expect(result).toEqual({ ref: 9, result: 'ran', text: 'ran', context: [deliveryText(id, ANSWER)] })
  })

  test('refused while its dialog is open in the terminal: the terminal has it', async () => {
    const { h, id } = await opened()
    const pressed = h.press(`ask-answer:${id}`)
    await h.settle()
    expect(answerAsync(id, { 'Which backend?': 'SQLite' }, 'cli')).toEqual({ ok: false, error: `the question ${id} is open in the terminal's dialog` })
    await h.raise(0, answered(ANSWER))
    await pressed
  })

  test("an answer from outside while a press's answer is still being taken in (its pictures' paths read) is refused: the ask has one answer", async () => {
    const FOLDER = '/tmp/claude-501/-work-repo/sess-1/images'
    const notes: AskNote[] = []
    const meanwhile: unknown[] = []
    let id = ''
    const h = harness({ whileStat: () => void meanwhile.push(answerAsync(id, { 'Which backend?': 'Postgres' }, 'm-1')) })
    observeAsks((note) => notes.push(note))
    await h.start()
    await h.classicStart('/Users/me/.claude/projects/-work-repo/sess-1.jsonl', 'sess-1')
    await h.call(ASK_TOOL, { questions: [BACKEND], async: true })
    id = asyncAsks()[0]?.id ?? ''
    const pressed = h.press(`ask-answer:${id}`)
    await h.settle()
    h.paste(FOLDER, '1.png')
    const text = 'The user answered: "Which backend?"="like this (Image attached)". Read the answers carefully.'
    await h.raise(0, answered(text, { 'Which backend?': 'like this (Image attached)' }))
    await pressed
    await h.settle()
    expect(meanwhile).toEqual([{ ok: false, error: `the question ${id} is open in the terminal's dialog` }])
    expect(h.submitted()).toEqual([deliveryText(id, `${text}\n[Image source: /private${FOLDER}/1.png]`)])
    expect(notes.filter((n) => n.kind === 'answered')).toEqual([{ kind: 'answered', id, dialog: 'nested_0' }])
    expect(asyncAsks()[0]).toMatchObject({ status: 'answered', answer: `${text}\n[Image source: /private${FOLDER}/1.png]` })
  })

  test("a press's answer is told to the observer with the dialog it went through, whose answer may have come from outside", async () => {
    const { h, notes, id } = await opened()
    const pressed = h.press(`ask-answer:${id}`)
    await h.settle()
    await h.raise(0, answered(ANSWER))
    await pressed
    await h.settle()
    expect(notes.at(-1)).toEqual({ kind: 'answered', id, dialog: 'nested_0' })
  })

  test('a dialog the mod raised is told to the observer as it settles, by its call id, with what the engine returned', async () => {
    const { h, notes } = await opened()
    const blocking = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    await h.raise(0, answered(ANSWER))
    await blocking
    expect(notes.filter((n) => n.kind === 'dialog')).toEqual([{ kind: 'dialog', toolUseId: 'nested_0', isError: false, text: ANSWER }])
    const second = h.call(ASK_TOOL, { questions: [BACKEND] })
    await h.settle()
    await h.raise(1, refused(ESC))
    await second
    expect(notes.filter((n) => n.kind === 'dialog').at(-1)).toEqual({ kind: 'dialog', toolUseId: 'nested_1', isError: true, text: ESC })
  })

  test('/clear forgets the open asks, and tells the observer which', async () => {
    const { h, notes, id } = await opened()
    await h.classicStart('/Users/me/.claude/projects/-w/s.jsonl', 's2', 'clear')
    expect(notes.at(-1)).toEqual({ kind: 'forgotten', ids: [id] })
  })
})
