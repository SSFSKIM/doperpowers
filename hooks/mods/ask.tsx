import type { EngineInterface, On, ToolDescribeResult } from 'claude-code'

/**
 * The tool as the model names it, `mcp__<plugin>__<name>`; written out so the
 * engine's scan reads the matchers (the hooks below name it as a literal).
 */
export const ASK_TOOL = 'mcp__doperpowers__AskUserQuestion'

/** The plugin's name as a dispatch's origin carries it. */
const PLUGIN = 'doperpowers'

export type AskOption = { label: string; description: string; preview?: string }
export type AskQuestion = { question: string; header: string; options: AskOption[]; multiSelect: boolean }
export type AskInput = { questions: AskQuestion[]; async?: boolean; metadata?: { source?: string } }

export const ASYNC_PARAGRAPH =
  "`async`: set it to true when you can go on with other work while the human decides. The call then returns at once; the questions wait in the human's view until they answer, and their answer reaches you in a later message that quotes each question. Leave it false when nothing useful can proceed without the answer."

/** What the built-in answers while this tool stands in for it, as its description and as its refusal. */
export const WITHDRAWN = "Withdrawn in this session: ask through mcp__doperpowers__AskUserQuestion, which takes this tool's input plus async."

export const SUBAGENT_REFUSAL = 'AskUserQuestion is for the main conversation: report what you need to the agent that dispatched you.'

/** The answer to a model call made later in a turn whose ask the human declined. */
export const LATCHED = 'Not run: the human declined the question asked in this turn.'

/**
 * The built-in's model-facing input schema on 2.1.296, less `answers` and
 * `annotations` (the permission component's channel, never the model's),
 * plus `async`.
 */
export const INPUT_SCHEMA: Record<string, unknown> = {
  type: 'object',
  additionalProperties: false,
  required: ['questions'],
  properties: {
    questions: {
      type: 'array',
      minItems: 1,
      maxItems: 4,
      description: 'Questions to ask the user (1-4 questions)',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['question', 'header', 'options', 'multiSelect'],
        properties: {
          question: {
            type: 'string',
            description:
              'The complete question to ask the user. Should be clear, specific, and end with a question mark. Example: "Which library should we use for date formatting?" If multiSelect is true, phrase it accordingly, e.g. "Which features do you want to enable?"',
          },
          header: { type: 'string', description: 'Very short label displayed as a chip/tag (max 12 chars). Examples: "Auth method", "Library", "Approach".' },
          options: {
            type: 'array',
            minItems: 2,
            maxItems: 4,
            description:
              "The available choices for this question. Must have 2-4 options. Each option should be a distinct, mutually exclusive choice (unless multiSelect is enabled). There should be no 'Other' option, that will be provided automatically.",
            items: {
              type: 'object',
              additionalProperties: false,
              required: ['label', 'description'],
              properties: {
                label: {
                  type: 'string',
                  description: 'The display text for this option that the user will see and select. Should be concise (1-5 words) and clearly describe the choice.',
                },
                description: {
                  type: 'string',
                  description: 'Explanation of what this option means or what will happen if chosen. Useful for providing context about trade-offs or implications.',
                },
                preview: {
                  type: 'string',
                  description:
                    'Optional preview content rendered when this option is focused. Use for mockups, code snippets, or visual comparisons that help users compare options. See the tool description for the expected content format.',
                },
              },
            },
          },
          multiSelect: {
            type: 'boolean',
            default: false,
            description: 'Set to true to allow the user to select multiple options instead of just one. Use when choices are not mutually exclusive.',
          },
        },
      },
    },
    metadata: {
      type: 'object',
      additionalProperties: false,
      description: 'Optional metadata for tracking and analytics purposes. Not displayed to user.',
      properties: {
        source: {
          type: 'string',
          description: 'Optional identifier for the source of this question (e.g., "remember" for /remember command). Used for analytics tracking.',
        },
      },
    },
    async: { type: 'boolean', default: false, description: ASYNC_PARAGRAPH },
  },
}

/** The model-facing description: the built-in's, then the async paragraph. */
export function describeAsk(builtin: string): string {
  return `${builtin}\n\n${ASYNC_PARAGRAPH}`
}

// Validation, as the built-in's zod schema and the engine's error formatter
// (`vV`) answer it: issues in zod's order, the missing, unknown and mistyped
// ones listed first; a call whose issues are all of the other kinds (sizes,
// the uniqueness rule) gets zod's own JSON of them, as the engine prints it.

type Path = (string | number)[]
type Issue =
  | { code: 'invalid_type'; path: Path; expected: string; received: string }
  | { code: 'unrecognized_keys'; path: Path; keys: string[] }
  | { origin: 'array'; code: 'too_small' | 'too_big'; minimum?: number; maximum?: number; inclusive: true; path: Path; message: string }
  | { code: 'custom'; path: Path; message: string }

const UNIQUE = 'Question texts must be unique, option labels must be unique within each question'
const STEER =
  'This call included a question with fewer than 2 options, so it was rejected and the person never saw it. A question with a single option has no decision in it. Do not retry this call and do not invent a filler second option. Instead, state the one path you were going to offer as the approach you are taking, then continue with the task. If this call also contained questions with 2 to 4 options (each with distinct labels), you may re-ask those questions alone in a new call. Ask a question only when the person has at least two genuinely distinct choices.'
const LISTED = 20

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

/** zod's name for what it received. */
function kindOf(value: unknown): string {
  if (value === undefined) return 'undefined'
  if (value === null) return 'null'
  if (Array.isArray(value)) return 'array'
  if (typeof value === 'number' && Number.isNaN(value)) return 'nan'
  return typeof value
}

/** Collects the issues of one value against its expected kind; false when the kind is wrong (zod aborts there). */
function expectKind(issues: Issue[], path: Path, value: unknown, expected: 'string' | 'boolean' | 'array' | 'object'): boolean {
  const received = kindOf(value)
  if (received === expected) {
    return true
  }
  issues.push({ code: 'invalid_type', path, expected, received })
  return false
}

function sized(issues: Issue[], path: Path, length: number, min: number, max: number) {
  if (length < min) {
    issues.push({ origin: 'array', code: 'too_small', minimum: min, inclusive: true, path, message: `Too small: expected array to have >=${min} items` })
  }
  if (length > max) {
    issues.push({ origin: 'array', code: 'too_big', maximum: max, inclusive: true, path, message: `Too big: expected array to have <=${max} items` })
  }
}

function optionIssues(issues: Issue[], path: Path, value: unknown) {
  if (!expectKind(issues, path, value, 'object')) return
  const option = value as Record<string, unknown>
  expectKind(issues, [...path, 'label'], option.label, 'string')
  expectKind(issues, [...path, 'description'], option.description, 'string')
  if (option.preview !== undefined) expectKind(issues, [...path, 'preview'], option.preview, 'string')
}

function questionIssues(issues: Issue[], path: Path, value: unknown) {
  if (!expectKind(issues, path, value, 'object')) return
  const q = value as Record<string, unknown>
  expectKind(issues, [...path, 'question'], q.question, 'string')
  expectKind(issues, [...path, 'header'], q.header, 'string')
  if (expectKind(issues, [...path, 'options'], q.options, 'array')) {
    const options = q.options as unknown[]
    options.forEach((option, i) => optionIssues(issues, [...path, 'options', i], option))
    sized(issues, [...path, 'options'], options.length, 2, 4)
  }
  if (q.multiSelect !== undefined) expectKind(issues, [...path, 'multiSelect'], q.multiSelect, 'boolean')
}

function isUnique(questions: AskQuestion[]): boolean {
  const texts = questions.map((q) => q.question)
  return new Set(texts).size === texts.length && questions.every((q) => new Set(q.options.map((o) => o.label)).size === q.options.length)
}

/** The issues zod finds in `input`, in its order. */
function issuesOf(input: Record<string, unknown>): Issue[] {
  const issues: Issue[] = []
  if (expectKind(issues, ['questions'], input.questions, 'array')) {
    const questions = input.questions as unknown[]
    questions.forEach((q, i) => questionIssues(issues, ['questions', i], q))
    sized(issues, ['questions'], questions.length, 1, 4)
  }
  if (input.metadata !== undefined && expectKind(issues, ['metadata'], input.metadata, 'object')) {
    const source = (input.metadata as Record<string, unknown>).source
    if (source !== undefined) expectKind(issues, ['metadata', 'source'], source, 'string')
  }
  if (input.async !== undefined) expectKind(issues, ['async'], input.async, 'boolean')
  const unknown = Object.keys(input).filter((key) => !['questions', 'metadata', 'async'].includes(key))
  if (unknown.length > 0) issues.push({ code: 'unrecognized_keys', path: [], keys: unknown })
  // A mistyped or missing field aborts the parse before the refinement runs.
  if (!issues.some((issue) => issue.code === 'invalid_type') && !isUnique(input.questions as AskQuestion[])) {
    issues.push({ code: 'custom', path: [], message: UNIQUE })
  }
  return issues
}

/** `questions[0].options` from `['questions', 0, 'options']`. */
const pathText = (path: Path) => path.reduce<string>((text, part, i) => (typeof part === 'number' ? `${text}[${part}]` : i === 0 ? part : `${text}.${part}`), '')

/** zod's JSON of its issues, the form the engine prints when it lists none. */
function issuesJson(issues: Issue[]): string {
  return JSON.stringify(issues, null, 2)
}

function formatted(issues: Issue[]): string {
  const missing: string[] = []
  const unknown: string[] = []
  const mistyped: string[] = []
  const other: string[] = []
  for (const issue of issues) {
    if (issue.code === 'invalid_type') {
      if (issue.received === 'undefined') missing.push(`The required parameter \`${pathText(issue.path)}\` is missing`)
      else mistyped.push(`The parameter \`${pathText(issue.path)}\` type is expected as \`${issue.expected}\` but provided as \`${issue.received}\``)
    } else if (issue.code === 'unrecognized_keys') {
      unknown.push(...issue.keys.map((key) => `An unexpected parameter \`${pathText([...issue.path, key])}\` was provided`))
    } else {
      const subject = issue.path.length === 0 ? 'The input' : `The parameter \`${pathText(issue.path)}\``
      other.push(`${subject} is invalid: ${issue.message}`)
    }
  }
  const lines = [...missing, ...unknown, ...mistyped]
  if (lines.length === 0) {
    return issuesJson(issues)
  }
  lines.push(...other.slice(0, LISTED))
  const unlisted = other.length - LISTED
  if (unlisted > 0) lines.push(`(${unlisted} more ${unlisted === 1 ? 'issue' : 'issues'} not listed)`)
  return `AskUserQuestion failed due to the following ${lines.length > 1 ? 'issues' : 'issue'}:\n${lines.join('\n')}`
}

/** Whether some question has fewer than two options: the built-in's steer then leads the error. */
function hasLoneOption(input: Record<string, unknown>): boolean {
  return Array.isArray(input.questions) && input.questions.some((q) => isRecord(q) && Array.isArray(q.options) && q.options.length < 2)
}

/**
 * The built-in's error text for what `input` breaks (every issue, as the
 * engine lists them), else undefined: the text a deny carries, which the
 * engine wraps in `<tool_use_error>` as it wraps the built-in's own.
 */
export function validateQuestions(input: unknown): string | undefined {
  const record = isRecord(input) ? input : {}
  const issues = issuesOf(record)
  if (issues.length === 0) {
    return undefined
  }
  const body = formatted(issues)
  return `InputValidationError: ${hasLoneOption(record) ? `${STEER}\n\n${body}` : body}`
}

// Pictures pasted into the dialog. The widened call's answer reads `(Image
// attached)` and carries no bytes, but at paste time the engine writes each
// picture into the session's pasted-image store, as it does a prompt's
// (`<temp root>/<project slug>/<session id>/images/<n>.png`). The files that
// appear there while a dialog is open are that dialog's pastes.

const MEDIA_TYPES: Record<string, string> = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp' }
const STORED = /^(\d+)\.(png|jpe?g|gif|webp)$/

/** The media type of a stored picture, by its extension. */
export function mediaTypeOf(name: string): string | undefined {
  return MEDIA_TYPES[name.slice(name.lastIndexOf('.') + 1).toLowerCase()]
}

/**
 * The stored pictures in `after` that were not in `before` nor taken by an
 * earlier dialog, in the store's number order: one dialog's pastes.
 */
export function newImages(before: readonly string[], after: readonly string[], taken: ReadonlySet<string> = new Set()): string[] {
  const seen = new Set(before)
  return after
    .filter((name) => STORED.test(name) && !seen.has(name) && !taken.has(name))
    .sort((a, b) => Number(STORED.exec(a)?.[1]) - Number(STORED.exec(b)?.[1]))
}

/** One picture as an API content block. */
export function imageBlock(name: string, base64: string) {
  return { type: 'image' as const, source: { type: 'base64' as const, media_type: mediaTypeOf(name) ?? 'image/png', data: base64 } }
}

/** The engine's mark on an answer whose "Type something" kept a picture. */
const IMAGE_MARK = '(Image attached)'

/**
 * How many answers the engine marked as carrying a picture. The store keeps
 * every paste, also one the human removed in the dialog; the marks are what
 * says pictures were kept, at least one per marked answer.
 */
export function imageMarks(answers: readonly string[]): number {
  return answers.filter((answer) => answer.endsWith(IMAGE_MARK)).length
}

/**
 * The answers a settled dialog recorded: the answered record's `answers`, or
 * the `  Answer: …` lines "Chat about this" lists in its refusal.
 */
function answersOf(outcome: { kind: 'answered'; record: unknown } | { kind: 'refused'; text: string }): string[] {
  if (outcome.kind === 'refused') {
    return [...outcome.text.matchAll(/^ {2}Answer: (.*)$/gm)].map((match) => match[1] ?? '')
  }
  const answers = isRecord(outcome.record) && isRecord(outcome.record.answers) ? outcome.record.answers : {}
  return Object.values(answers).filter((answer): answer is string => typeof answer === 'string')
}

/** Where this session's pasted pictures are kept: the per-user temp root, the project slug and the session id. */
type Store = { slug: string; sessionId: string; root?: string | null }
let store: Store | undefined
/** Store paths a settled dialog took, so a dialog queued behind it does not take them again. */
let taken = new Set<string>()

/** The project's slug as the engine spells it: the transcript's folder under `projects/`. */
export function slugOf(transcriptPath: string): string {
  const parts = transcriptPath.split(/[\\/]/)
  return parts[parts.length - 2] ?? ''
}

/**
 * The engine's per-user temp root, `<CLAUDE_CODE_TMPDIR or /tmp>/claude-<uid>`:
 * the one such folder this process can read (each is private to its user),
 * or, should several be readable, the one holding this project's folder.
 */
async function findTempRoot($: EngineInterface, slug: string): Promise<string | null> {
  const base = ((await $.env.get('CLAUDE_CODE_TMPDIR')) || '/tmp').replace(/[\\/]+$/, '')
  const entries = await $.fs.list(base).catch(() => [])
  const roots = entries.filter((entry) => /^claude-\d+$/.test(entry.name)).map((entry) => `${base}/${entry.name}`)
  const readable = (await Promise.all(roots.map(async (root) => ((await $.fs.list(root).then(() => true, () => false)) ? root : undefined)))).filter(
    (root): root is string => root !== undefined,
  )
  if (readable.length === 1) {
    return readable[0] as string
  }
  const holding = (await Promise.all(readable.map(async (root) => ((await $.fs.exists(`${root}/${slug}`)) ? root : undefined)))).filter(
    (root): root is string => root !== undefined,
  )
  return holding.length === 1 ? (holding[0] as string) : null
}

/** This session's pasted-image folder, or undefined (with a debug line) when it cannot be placed. */
async function imageFolder($: EngineInterface): Promise<string | undefined> {
  if (store === undefined) {
    $.ui.log('ask: no SessionStart payload yet; pasted pictures cannot be found', { to: 'debug' })
    return undefined
  }
  if (store.root === undefined) {
    store.root = await findTempRoot($, store.slug)
  }
  if (store.root === null) {
    $.ui.log("ask: the engine's temp root was not found; pasted pictures reach the model as text only", { to: 'debug' })
    return undefined
  }
  return `${store.root}/${store.slug}/${store.sessionId}/images`
}

/** The names in the image folder; none when it does not exist yet. */
async function storedImages($: EngineInterface, folder: string | undefined): Promise<string[]> {
  if (folder === undefined || !(await $.fs.exists(folder))) {
    return []
  }
  return (await $.fs.list(folder).catch(() => [])).filter((entry) => entry.kind === 'file').map((entry) => entry.name)
}

/** The pictures at `paths` as content blocks; one that cannot be read is left out, with a debug line. */
async function imageBlocks($: EngineInterface, paths: readonly string[]) {
  const blocks: ReturnType<typeof imageBlock>[] = []
  for (const path of paths) {
    try {
      const { base64 } = await $.fs.read(path, { as: 'bytes' })
      blocks.push(imageBlock(path, base64))
    } catch (error) {
      $.ui.log(`ask: the pasted picture ${path} could not be read: ${message(error)}`, { to: 'debug' })
    }
  }
  return blocks
}

/**
 * The engine's own line for an image known only by its file (no
 * dimensions): what the model reads to open a picture with Read.
 */
export function imageSourceLine(path: string): string {
  return `[Image source: ${path}]`
}

/** One `[Image source: <path>]` line per picture, the path as it resolves on disk. */
async function imageLines($: EngineInterface, paths: readonly string[]): Promise<string[]> {
  return Promise.all(
    paths.map(async (path) => {
      const real = await $.fs
        .stat(path, { resolve: true })
        .then((stat) => stat.realPath)
        .catch(() => undefined)
      return imageSourceLine(real ?? path)
    }),
  )
}

// The dialog.

export type DialogOutcome =
  | { kind: 'answered'; text: string; record: unknown; images: string[] } // text: the engine's result text; images: paths pasted in this dialog
  | { kind: 'refused'; text: string; hasFeedback: boolean; images: string[] } // text: the refusal; hasFeedback: "Chat about this"; images: kept with it

/** "Chat about this" refuses with the human's words after this. */
const FEEDBACK = 'To tell you how to proceed, the user said:'

/** One raised dialog: its question set, the token its one-question raise carries as the header, and what it settled with. */
type Entry = { token: string; questions: AskQuestion[]; isClaimed: boolean; outcome?: DialogOutcome }

let entries: Entry[] = []
let raised = 0
/**
 * The tool stands in for the built-in in this session, so the built-in is
 * withdrawn: set as an interactive session starts (the engine describes the
 * built-in while it does), cleared should the tool not be registered.
 */
let isServing = false
/** What the built-in's tool.describe last answered: withdrawn or not; undefined before it was described. */
let wasWithdrawn: boolean | undefined
/** A blocking ask was declined without feedback in the running turn: its later model calls are refused. */
let isLatched = false
/**
 * The built-in's description as the engine computes it (its tool.describe),
 * and whether this tool has been described, from which of them (undefined:
 * from the shortened text the session started with).
 */
let builtinDescription: string | undefined
let isDescribed = false
let describedFrom: string | undefined

/** Forgets every ask and the session's state; for tests, which share this module. */
export function resetAsk() {
  entries = []
  raised = 0
  isServing = false
  wasWithdrawn = undefined
  isLatched = false
  builtinDescription = undefined
  isDescribed = false
  describedFrom = undefined
  store = undefined
  taken = new Set()
}

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

/** What the widened call's `next` resolved, as the tool reads it (no pictures yet). */
function outcomeOf(result: { deny?: string; text?: string; result?: unknown; isError?: true }): DialogOutcome {
  if (result.deny !== undefined) {
    return { kind: 'refused', text: result.deny, hasFeedback: false, images: [] }
  }
  const text = result.text ?? (typeof result.result === 'string' ? result.result : '')
  if (result.isError === true) {
    return { kind: 'refused', text, hasFeedback: text.includes(FEEDBACK), images: [] }
  }
  return { kind: 'answered', text, record: result.result, images: [] }
}

/**
 * Opens the engine dialog for `questions` (a pending entry, `$.ui.ask` with
 * the first question) and settles with what the widening hook's `next`
 * resolved for that entry, with the pictures pasted into it. Must be
 * awaited inside a hook dispatch of this file (`$` never crosses an
 * import). The engine queues it behind any dialog already open.
 */
export async function openDialog($: EngineInterface, questions: AskQuestion[]): Promise<DialogOutcome> {
  const entry: Entry = { token: `ask-${++raised}`, questions, isClaimed: false }
  entries.push(entry)
  try {
    const folder = await imageFolder($)
    const before = await storedImages($, folder)
    const first = questions[0] as AskQuestion
    try {
      await $.ui.ask(first.question, {
        options: first.options.map((o) => o.label),
        header: entry.token,
        ...(first.multiSelect && { multiSelect: true as const }),
      })
    } catch (error) {
      // A refusal at the dialog rejects too; the widened call's outcome is the answer.
      if (entry.outcome === undefined) {
        throw error
      }
    }
    const outcome = entry.outcome as DialogOutcome | undefined
    if (outcome === undefined) {
      throw new Error(`the dialog for "${first.question}" settled without being widened (${entry.token})`)
    }
    const pasted = newImages(before, await storedImages($, folder), taken)
    pasted.forEach((name) => taken.add(name))
    // Only an answer or "Chat about this" carries pictures; Esc carries none.
    if (pasted.length === 0 || (outcome.kind === 'refused' && !outcome.hasFeedback)) {
      return outcome
    }
    // The marks say at least one picture per marked answer was kept. When
    // they account for every paste, all were kept; otherwise which ones the
    // human removed is unknown, and none is sent rather than a removed one.
    const marks = imageMarks(answersOf(outcome))
    if (marks !== pasted.length) {
      $.ui.log(`ask: ${pasted.length} ${pasted.length === 1 ? 'picture was' : 'pictures were'} pasted and ${marks} ${marks === 1 ? 'answer carries' : 'answers carry'} one; which were kept is unknown, so none is sent`, {
        to: 'debug',
      })
      return outcome
    }
    return { ...outcome, images: pasted.map((name) => `${folder}/${name}`) }
  } finally {
    entries = entries.filter((e) => e !== entry)
  }
}

/**
 * The pending entry an AskUserQuestion call claims: only this plugin's own
 * raise (an origin the host sets and no plugin can write), with one question
 * whose header is an unclaimed entry's token.
 */
function claim(origin: { plugin: string }, e: { questions?: unknown }): Entry | undefined {
  if (origin.plugin !== PLUGIN || !Array.isArray(e.questions) || e.questions.length !== 1) {
    return undefined
  }
  const header = isRecord(e.questions[0]) ? e.questions[0].header : undefined
  const entry = entries.find((candidate) => !candidate.isClaimed && candidate.token === header)
  if (entry !== undefined) {
    entry.isClaimed = true
  }
  return entry
}

/** A call the model made in the main conversation: the engine's dispatch, no subagent. */
const isModelMainCall = (origin: { plugin: string }, e: { agentId?: string }) => origin.plugin === 'engine' && e.agentId === undefined

/** A call's own arguments: its envelope less the keys the engine reserves. */
const argumentsOf = (e: object) => Object.fromEntries(Object.entries(e).filter(([key]) => !['tool', 'tool_use_id', 'agentId', 'consent'].includes(key)))

/**
 * Session start: registers the tool under the built-in's description. The
 * whole text comes from the built-in's tool.describe, which the engine
 * raises while the session starts; should it not have come yet,
 * `$.tool.list()`'s, which keeps the first 300 characters, stands in until
 * it does. A session without the built-in gets nothing, and the built-in
 * is put back should the tool not register: the dialog's tool is not
 * there to be reached.
 */
async function askStart($: EngineInterface) {
  const builtin = (await $.tool.list()).find((tool) => tool.name === 'AskUserQuestion')
  try {
    if (builtin === undefined) {
      throw new Error('no AskUserQuestion in this session')
    }
    await $.tool.register({ name: 'AskUserQuestion', description: describeAsk(builtinDescription ?? builtin.description), inputSchema: INPUT_SCHEMA })
  } catch (error) {
    isServing = false
    $.ui.log(`ask: the tool is not registered: ${message(error)}`, { to: 'debug' })
  }
  // The built-in was described before this settled the other way: again.
  if (wasWithdrawn !== undefined && wasWithdrawn !== isServing) {
    $.ui.invalidate('tool.describe')
  }
}

/**
 * Registers the tool and serves it: a blocking ask opens the engine dialog
 * through `$.ui.ask` and returns the engine's own result text; the built-in
 * is withdrawn from the model, and a declined ask ends the model's turn as
 * the built-in's does.
 */
export function registerAsk(on: On) {
  on('session.start', { isInteractive: true }, async ($, e, next) => {
    isServing = true
    const result = await next(e)
    await askStart($)
    return result
  })

  // Every SessionStart (agents.tsx holds the one registration a module may
  // make without a matcher): where this session's pasted pictures are kept.
  on('classic.SessionStart', { hook_event_name: 'SessionStart' }, async (_, e, next) => {
    store = { slug: slugOf(e.transcript_path), sessionId: e.session_id }
    return next(e)
  }).catch((_, e, next) => next(e))

  // Every turn (compact holds the unmatched registration; a turn's id is
  // never empty): a new turn starts unlatched.
  on('turn.start', { turnId: /./ }, (_, e, next) => {
    isLatched = false
    return next(e)
  })

  // A turn latched by a declined ask ends at its next model request, unsent,
  // as the built-in's abort ends it: no stop line, no interruption marker.
  on('turn.step', async function* ($, e, next) {
    if (!isLatched || e.agentId !== undefined) {
      return yield* next(e)
    }
    try {
      await $.turn.abort({ turnId: e.turnId })
    } catch (error) {
      $.ui.log(`ask: the declined turn could not be aborted: ${message(error)}`, { to: 'debug' })
    }
    return { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: 'end_turn' as const, usage: null }
  })

  // The tool ships inline, so the model reads its schema and guidance in every
  // request, under the built-in's whole description once the engine has
  // described the built-in; the built-in waits behind tool search, its name
  // alone in view.
  on('tool.describe', { tool: 'mcp__doperpowers__AskUserQuestion' }, async (_, e, next) => {
    const described = await next(e)
    isDescribed = true
    describedFrom = builtinDescription
    const description = builtinDescription === undefined ? described.description : describeAsk(builtinDescription)
    return { ...described, description, isDeferred: false } as ToolDescribeResult
  })
  on('tool.describe', { tool: 'AskUserQuestion' }, async ($, e, next) => {
    const described = await next(e)
    if (builtinDescription !== described.description) {
      $.ui.log(`ask: the built-in's description read (${described.description.length} characters)`, { to: 'debug' })
    }
    builtinDescription = described.description
    wasWithdrawn = isServing
    if (!isServing) {
      return described
    }
    // This tool was described first, from the shortened text: once more.
    if (isDescribed && describedFrom !== builtinDescription) {
      $.ui.invalidate('tool.describe')
    }
    return { description: WITHDRAWN, isDeferred: true } as ToolDescribeResult
  })

  // Outermost on every call: after a declined ask, the turn's later model
  // calls are refused before they run, where the built-in's abort would have
  // cancelled them.
  on('tool.call', (_, e, next) => {
    if (isLatched && isModelMainCall(next.origin, e)) {
      return { deny: LATCHED }
    }
    return next(e)
  }).catch((_, e, next) => next(e))

  // The mod's own raise is widened to its entry's whole set; every other call
  // from the model, or a stray one from this plugin, is refused. Another
  // plugin's $.ui.ask is its own business and passes.
  on('tool.call', { tool: 'AskUserQuestion' }, async ($, e, next) => {
    if (!isServing || (next.origin.plugin !== PLUGIN && next.origin.plugin !== 'engine')) {
      return next(e)
    }
    const entry = claim(next.origin, e)
    if (entry === undefined) {
      return { deny: WITHDRAWN }
    }
    const result = await next({ ...e, questions: entry.questions } as typeof e)
    entry.outcome = outcomeOf(result as Parameters<typeof outcomeOf>[0])
    return result
  }).catch((_, e, next) =>
    // Failed before passing the call on, the withdrawal still holds for the model.
    !next.called && next.error.kind !== 're-entry' && isServing && next.origin.plugin === 'engine' ? { deny: WITHDRAWN } : next(e),
  )

  on('tool.call', { tool: 'mcp__doperpowers__AskUserQuestion' }, async ($, e) => {
    if (e.agentId !== undefined) {
      return { deny: SUBAGENT_REFUSAL }
    }
    const input = argumentsOf(e)
    const invalid = validateQuestions(input)
    if (invalid !== undefined) {
      return { deny: invalid }
    }
    let outcome: DialogOutcome
    try {
      outcome = await openDialog($, (input as AskInput).questions)
    } catch (error) {
      $.ui.log(`ask: ${message(error)}`, { to: 'debug' })
      return { deny: `The question could not be asked: ${message(error)}` }
    }
    if (outcome.kind === 'refused') {
      if (!outcome.hasFeedback) {
        isLatched = true
      }
      // A refusal is text: the pictures kept with "Chat about this" go as
      // their files, one line each, for the model to Read.
      const lines = await imageLines($, outcome.images)
      return { deny: [outcome.text, ...lines].join('\n') }
    }
    // The built-in puts pasted pictures beside its result; here they sit in
    // it, after the engine's text, which reads the same to the model.
    const blocks = await imageBlocks($, outcome.images)
    return { result: blocks.length === 0 ? outcome.text : [{ type: 'text', text: outcome.text }, ...blocks] }
  }).catch((_, e, next) =>
    // Asked in place of this hook for its own dialog's call (re-entry): pass it on.
    next.error.kind === 're-entry' ? next(e) : { deny: `The question could not be asked: the hook ${next.error.kind === 'timeout' ? 'ran out of time' : 'failed'}.` },
  )
}
