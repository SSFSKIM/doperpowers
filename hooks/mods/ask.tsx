import type { EngineInterface, On, ToolDescribeResult } from 'claude-code'

import type { AskSnapshot } from '../../types/doperpowers'

/**
 * The tool as the model names it, `mcp__<plugin>__<name>`; written out so the
 * engine's scan reads the matchers (the hooks below name it as a literal).
 */
export const ASK_TOOL = 'mcp__doperpowers__AskUserQuestion'

/** The plugin's name as a dispatch's origin carries it. */
export const PLUGIN = 'doperpowers'

export type AskOption = { label: string; description: string; preview?: string }
export type AskQuestion = { question: string; header: string; options: AskOption[]; multiSelect: boolean }
export type AskInput = { questions: AskQuestion[]; async?: boolean; metadata?: { source?: string } }

export const ASYNC_PARAGRAPH =
  "`async`: set it to true when you can go on with other work while the human decides. The call then returns at once; the questions wait in the human's view until they answer, and their answer reaches you in a later message that quotes each question. Leave it false when the work is blocked by the answer, nothing useful can proceed without the answer, or the answer is the last thing left in your turn."

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
 * One answer of the list "Chat about this" writes in its refusal: the whole
 * answer after `  Answer: `, newlines included (the engine puts the human's
 * text in as typed), up to the question's notes, the next question, or the end.
 */
const CHAT_ANSWER = /^ {2}Answer: ([\s\S]*?)(?=\n {2}User notes: |\n- "|(?![\s\S]))/gm

/**
 * The answers a settled dialog recorded: the answered record's `answers`, or
 * the answers "Chat about this" lists in its refusal.
 */
function answersOf(outcome: { kind: 'answered'; record: unknown } | { kind: 'refused'; text: string }): string[] {
  if (outcome.kind === 'refused') {
    return [...outcome.text.matchAll(CHAT_ANSWER)].map((match) => match[1] ?? '')
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

export type DialogOutcome = (
  | { kind: 'answered'; text: string; record: unknown; images: string[] } // text: the engine's result text; images: paths pasted in this dialog
  | { kind: 'refused'; text: string; hasFeedback: boolean; images: string[] } // text: the refusal; hasFeedback: "Chat about this"; images: kept with it
) & { toolUseId?: string } // the dialog's own call: the bridge names who answered it

/** "Chat about this" refuses with the human's words after this. */
const FEEDBACK = 'To tell you how to proceed, the user said:'

/** One raised dialog: its question set, the token its one-question raise carries as the header, and what it settled with. */
type Entry = { token: string; questions: AskQuestion[]; isClaimed: boolean; outcome?: DialogOutcome; toolUseId?: string }

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

/**
 * What the session's asks do, as an observer (the bridge) is told: an async
 * ask opened, was answered (`by` whoever answered it from outside, or
 * through the `dialog` a press opened, whose answer the bridge attributes),
 * or was forgotten (a new conversation); a dialog this mod raised settled,
 * with what the engine returned for its call.
 */
export type AskNote =
  | { kind: 'open'; id: string; questions: AskQuestion[] }
  | { kind: 'answered'; id: string; by: string }
  | { kind: 'answered'; id: string; dialog: string }
  | { kind: 'forgotten'; ids: string[] }
  | { kind: 'dialog'; toolUseId: string; isError: boolean; text: string }

let observer: ((note: AskNote) => void) | undefined

/**
 * Sets the one observer of the session's asks and returns the one it
 * replaces, so a later mod chains to it rather than silencing it.
 */
export function observeAsks(fn: (note: AskNote) => void): ((note: AskNote) => void) | undefined {
  const previous = observer
  observer = fn
  return previous
}

function note(n: AskNote) {
  try {
    observer?.(n)
  } catch {
    // The observer's failure is its own; the ask goes on.
  }
}

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
  forgetAsyncAsks()
  isTurnRunning = false
  external = undefined
  keep = undefined
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
    const widened = entry.outcome as DialogOutcome | undefined
    if (widened === undefined) {
      throw new Error(`the dialog for "${first.question}" settled without being widened (${entry.token})`)
    }
    const outcome: DialogOutcome = { ...widened, ...(entry.toolUseId !== undefined && { toolUseId: entry.toolUseId }) }
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

// Asking without waiting. An async ask returns at once and stands open in
// the human's view; a press opens the same dialog, and the answer is handed
// to the model: as a prompt of its own while the session is idle, else held
// for the next result of the model's own calls, or the turn's end.

/** What an async call returns at once. */
export const ASYNC_RESULT =
  'Your questions are waiting for the human; this call does not wait for them. Their answer will reach you in a later message that quotes each question. Go on with work that does not depend on it.'

export const DELIVERY_HEAD = 'The human responded to your async AskUserQuestion'
/** How the engine frames a prompt this plugin submitted, in the user row it stores. */
const PLUGIN_PROMPT = 'The doperpowers plugin sent a message:\n'
const DELIVERY = /The human responded to your async AskUserQuestion \(call ([^)\s]+)\): /g

/** The text a delivery carries: which call it answers, then what the blocking call would have returned. */
export function deliveryText(toolUseId: string, engineText: string): string {
  return `${DELIVERY_HEAD} (call ${toolUseId}): ${engineText}`
}

/** The deliveries a stored row's text holds: each call id with the text after its head, up to the next. */
function deliveriesIn(text: string): { id: string; text: string }[] {
  const heads = [...text.matchAll(DELIVERY)]
  return heads.map((head, i) => ({
    id: head[1] as string,
    text: text.slice((head.index ?? 0) + head[0].length, heads[i + 1]?.index ?? text.length).trimEnd(),
  }))
}

/** The call ids a stored row's text answers (delivery heads found in it). */
export function deliveredIds(text: string): string[] {
  return deliveriesIn(text).map((delivery) => delivery.id)
}

export type OpenAsk = {
  id: string // the call's tool_use_id
  questions: AskQuestion[]
  status: 'open' | 'answered'
  answer?: string // the engine's result text, once answered
}

/** A stored result's text: a string, or its text blocks joined. */
function textOf(content: unknown): string {
  if (typeof content === 'string') {
    return content
  }
  if (Array.isArray(content)) {
    return content
      .filter((block): block is { text: string } => isRecord(block) && typeof block.text === 'string')
      .map((block) => block.text)
      .join('\n')
  }
  return ''
}

/**
 * Whether a stored async call was accepted: its paired tool_result is
 * ASYNC_RESULT and not an error, and its input passes validateQuestions.
 */
export function isAccepted(input: unknown, result: { content: unknown; is_error?: boolean } | undefined): boolean {
  return result !== undefined && result.is_error !== true && textOf(result.content) === ASYNC_RESULT && validateQuestions(input) === undefined
}

/** The record's mark for a question answered with notes alone, which the result text reads as no option selected. */
const NOTES_ONLY = '(notes only)'
const NO_OPTION = '(no option selected)'
/** The sentences that close the engine's summary of the answers. */
const SUMMARY_ENDS = ['. You can now continue with these answers in mind.', '. Read the answers carefully']

/**
 * Each answered question and its answer, as the built-in's row lists them,
 * read back from the engine's result text (`"<question>"="<answer>"`, a
 * preview and notes after it, the questions joined by `, `).
 */
export function answerRows(questions: readonly { question: string }[], text: string): [string, string][] {
  const ends = SUMMARY_ENDS.map((end) => text.lastIndexOf(end)).filter((at) => at >= 0)
  const end = ends.length > 0 ? Math.min(...ends) : text.length
  const found: { question: string; at: number; from: number }[] = []
  let cursor = 0
  for (const { question } of questions) {
    const key = `"${question}"=`
    const at = text.indexOf(key, cursor)
    if (at >= 0 && at < end) {
      found.push({ question, at, from: at + key.length })
      cursor = at + key.length
    }
  }
  return found.map(({ question, from }, i) => {
    const next = found[i + 1]
    const segment = text.slice(from, next === undefined ? end : next.at - ', '.length)
    if (segment.startsWith(NO_OPTION)) {
      return [question, NOTES_ONLY]
    }
    const close = [segment.indexOf('" selected preview:\n'), segment.indexOf('" notes: ')].find((at) => at > 0) ?? segment.lastIndexOf('"')
    return [question, segment.slice(1, close > 0 ? close : undefined)]
  })
}

/** The refusal's opening the engine writes when the human declines a dialog, Esc and "Chat about this" alike. */
const REFUSAL = "The user doesn't want to proceed with this tool use."

/** What an ask's transcript row draws. */
export type AskRow =
  | { kind: 'engine' } // the engine's own drawing of the call
  | { kind: 'none' } // nothing: a dialog still up, or nothing answered
  | { kind: 'open'; questions: AskQuestion[] } // an async ask waiting for the human
  | { kind: 'answered'; rows: [string, string][]; isDelivered: boolean }
  | { kind: 'declined'; questions: AskQuestion[]; isDelivered: boolean }

/**
 * The row of a call of the tool, as the engine draws the built-in's: nothing
 * while a blocking dialog is up, the answers once answered, declined once
 * refused; an open async ask, which the built-in never has, lists its
 * questions. `ask` is the async ask the call made, when the mod knows it;
 * `isDelivered` whether its answer has reached the model.
 */
export function askRow(
  props: { input: unknown; output?: unknown; isRunning: boolean; isErrored: boolean; isInterrupted?: boolean },
  ask?: OpenAsk,
  isDelivered = true,
): AskRow {
  const questions = isRecord(props.input) && Array.isArray(props.input.questions) ? (props.input.questions as AskQuestion[]) : []
  if (ask !== undefined) {
    if (ask.status === 'open') {
      return { kind: 'open', questions: ask.questions }
    }
    const answer = ask.answer ?? ''
    return answer.startsWith(REFUSAL)
      ? { kind: 'declined', questions: ask.questions, isDelivered }
      : { kind: 'answered', rows: answerRows(ask.questions, answer), isDelivered }
  }
  if (props.isInterrupted === true) {
    return { kind: 'engine' }
  }
  if (props.isRunning) {
    return { kind: 'none' }
  }
  const text = textOf(props.output)
  if (props.isErrored) {
    return text.includes(REFUSAL) ? { kind: 'declined', questions, isDelivered: true } : { kind: 'engine' }
  }
  if (text === ASYNC_RESULT) {
    return { kind: 'engine' }
  }
  const rows = answerRows(questions, text)
  return rows.length === 0 ? { kind: 'none' } : { kind: 'answered', rows, isDelivered: true }
}

type Row = Record<string, unknown>

/** A row that hangs beside the conversation's turns: an attachment, a notice, a meta prompt (the engine's `eL`). */
const isSideRow = (row: Row) =>
  row.type === 'attachment' ||
  (row.type === 'system' && row.subtype !== 'compact_boundary') ||
  (row.type === 'user' && row.isMeta === true && blocksOf(row, 'tool_result').length === 0)

/** The blocks of a row's message of one type. */
function blocksOf(row: Row, type: string): Record<string, unknown>[] {
  const content = isRecord(row.message) ? row.message.content : undefined
  return Array.isArray(content) ? content.filter((block): block is Record<string, unknown> => isRecord(block) && block.type === type) : []
}

/**
 * The rows of the conversation the engine resumes, in file order: back from
 * its leaf, parent by parent, across a compaction by the boundary's
 * `logicalParentUuid` (its `parentUuid` is null). A branch the human rewound
 * past stays in the file and is not on it. The leaf is the last row written,
 * unless the engine set the leaf explicitly after it: a rewind writes a
 * `last-prompt` record with `explicit: true` naming the row it went back to,
 * or no row when it went back past the first prompt (verified on two rewound
 * transcripts, 2.1.257 and 2.1.296; the writer is the bundle's `g_t`).
 *
 * The walk alone misses rows the engine restores beside it (its `i1r`): one
 * model response is a row per block, sharing the response's id, and each tool
 * result is parented to the row of its own call, so the results of all but
 * the last call sit beside the chain, with whatever hangs off them (a context
 * attachment carrying a delivery). As the engine does, each response on the
 * chain brings its rows, their results, and the side rows under them, a run
 * of attachments and notices that neither forks nor rejoins the chain.
 */
function conversationOf(rows: readonly Row[]): Row[] {
  const byUuid = new Map<string, Row>()
  let leaf: string | undefined
  for (const row of rows) {
    if (typeof row.uuid === 'string' && row.isSidechain !== true) {
      byUuid.set(row.uuid, row)
      leaf = row.uuid
    } else if (row.type === 'last-prompt' && row.explicit === true) {
      // A rewind's record; no leaf when it went back past the first prompt.
      leaf = typeof row.leafUuid === 'string' ? row.leafUuid : undefined
    }
  }
  const kept = new Set<string>()
  const chain: Row[] = []
  for (let at = leaf; at !== undefined && !kept.has(at); ) {
    const row = byUuid.get(at)
    if (row === undefined) {
      break
    }
    kept.add(at)
    chain.push(row)
    at = typeof row.parentUuid === 'string' ? row.parentUuid : typeof row.logicalParentUuid === 'string' ? row.logicalParentUuid : undefined
  }

  const responses = new Map<string, Row[]>() // a response's id: its rows
  const callRow = new Map<string, Row>() // a tool call's id: the row that made it
  const children = new Map<string, Row[]>() // a row's uuid: the rows parented to it
  const resultsOf = new Map<string, Set<Row>>() // a call row's uuid: the results of its calls
  const add = <K, V>(map: Map<K, V[]>, key: K, value: V) => map.set(key, [...(map.get(key) ?? []), value])
  for (const row of byUuid.values()) {
    if (typeof row.parentUuid === 'string') {
      add(children, row.parentUuid, row)
    }
    const id = row.type === 'assistant' && isRecord(row.message) ? row.message.id : undefined
    if (typeof id === 'string') {
      add(responses, id, row)
      blocksOf(row, 'tool_use').forEach((block) => callRow.set(String(block.id), row))
    }
  }
  for (const row of byUuid.values()) {
    const results = blocksOf(row, 'tool_result')
    if (row.type !== 'user' || results.length === 0) {
      continue
    }
    const owners = [row.parentUuid, row.sourceToolAssistantUUID, ...results.map((block) => callRow.get(String(block.tool_use_id))?.uuid)]
    for (const owner of owners) {
      if (typeof owner === 'string') {
        resultsOf.set(owner, (resultsOf.get(owner) ?? new Set()).add(row))
      }
    }
  }
  /** A run of side rows from `row` down, or none: one that forks, rejoins the conversation, or reaches a turn is not beside it (the engine's `Vae`). */
  const sideRun = (row: Row): Row[] => {
    const run: Row[] = []
    for (let at: Row | undefined = row; at !== undefined; ) {
      if (kept.has(at.uuid as string) || !isSideRow(at)) {
        return []
      }
      run.push(at)
      const next: Row[] = (children.get(at.uuid as string) ?? []).filter((child) => !kept.has(child.uuid as string))
      if (next.length > 1) {
        return []
      }
      at = next[0]
    }
    return run
  }
  for (const row of chain) {
    const id = row.type === 'assistant' && isRecord(row.message) ? row.message.id : undefined
    if (typeof id !== 'string') {
      continue
    }
    const response = responses.get(id) ?? [row]
    const results = response.flatMap((call) => [...(resultsOf.get(call.uuid as string) ?? [])])
    const restored = [...response, ...results]
    restored.forEach((restoredRow) => kept.add(restoredRow.uuid as string))
    for (const restoredRow of restored) {
      for (const child of children.get(restoredRow.uuid as string) ?? []) {
        sideRun(child).forEach((side) => kept.add(side.uuid as string))
      }
    }
  }
  return rows.filter((row) => typeof row.uuid === 'string' && kept.has(row.uuid))
}

/**
 * The async asks a transcript holds, in call order: each accepted call of the
 * tool, answered when a row the model read delivers it (an attachment of a
 * tool result's or a prompt's context, a user row the plugin submitted),
 * else open. Once the human rewound (the engine's `rewound` record), only the
 * conversation the engine resumes counts; without a rewind every row of the
 * file is on it. Lines a search found (`isWholeFile` false) carry no ancestry
 * to follow, and all count.
 */
export function rebuildAsks(lines: readonly string[], { isWholeFile = true }: { isWholeFile?: boolean } = {}): OpenAsk[] {
  const calls: { id: string; input: Record<string, unknown> }[] = []
  const results = new Map<string, { content: unknown; is_error?: boolean }>()
  const answers = new Map<string, string>()
  const parsed = lines.flatMap((line) => {
    try {
      const row: unknown = JSON.parse(line)
      return isRecord(row) ? [row] : []
    } catch {
      return []
    }
  })
  const isRewound = parsed.some((row) => row.type === 'last-prompt' && row.rewound === true)
  for (const row of isWholeFile && isRewound ? conversationOf(parsed) : parsed) {
    const message = isRecord(row.message) ? row.message : {}
    for (const block of Array.isArray(message.content) ? message.content : []) {
      // A call from the model's own row: the engine's wire copy of a request's message (`api-request-blob`) repeats it.
      if (row.type === 'assistant' && isRecord(block) && block.type === 'tool_use' && block.name === ASK_TOOL && isRecord(block.input) && block.input.async === true) {
        calls.push({ id: String(block.id), input: block.input })
      } else if (isRecord(block) && block.type === 'tool_result') {
        results.set(String(block.tool_use_id), block as { content: unknown; is_error?: boolean })
      }
    }
    for (const text of deliveryTexts(row)) {
      for (const delivery of deliveriesIn(text)) {
        answers.set(delivery.id, delivery.text)
      }
    }
  }
  return calls
    .filter((call) => isAccepted(call.input, results.get(call.id)))
    .map(({ id, input }) => {
      const questions = input.questions as AskQuestion[]
      const answer = answers.get(id)
      return answer === undefined ? { id, questions, status: 'open' } : { id, questions, status: 'answered', answer }
    })
}

/**
 * The texts of a stored row that can carry a delivery, as the engine stores
 * them: a context attachment's entries (a tool result's or a prompt's), and
 * the text of a user row the plugin submitted. Not the model's rows or the
 * human's own prompts, which may quote one, nor a tool's output, nor the
 * queue's record of a prompt that may never have entered.
 */
function deliveryTexts(row: Record<string, unknown>): string[] {
  if (row.type === 'attachment' && isRecord(row.attachment) && row.attachment.type === 'hook_additional_context') {
    const { content } = row.attachment
    return (Array.isArray(content) ? content : [content]).filter((entry): entry is string => typeof entry === 'string')
  }
  const message = isRecord(row.message) ? row.message : {}
  if (row.type !== 'user') {
    return []
  }
  const texts =
    typeof message.content === 'string'
      ? [message.content]
      : (Array.isArray(message.content) ? message.content : [])
          .filter((block): block is { type: 'text'; text: string } => isRecord(block) && block.type === 'text' && typeof block.text === 'string')
          .map((block) => block.text)
  // The plugin's own prompt, by the engine's framing; the human quoting a delivery is not one.
  return texts.filter((text) => text.startsWith(PLUGIN_PROMPT))
}

/** An answer on its way to the model: its ask and the delivery text. */
type Delivery = { id: string; text: string }

/** The session's async asks, oldest first. */
let asks: OpenAsk[] = []
/** Answers waiting for a route to the model, oldest first. */
let held: Delivery[] = []
/** Asks answered whose answer has not reached the model yet, held or on a route that may still fail, in the order answered. */
let undelivered = new Map<string, Delivery>()
/** Asks whose dialog is raised (open, or queued behind another), until its answer is the ask's. */
let raisedAsks = new Set<string>()
/** A main-conversation turn is running: an answer now is held, not submitted. */
let isTurnRunning = false

/**
 * What the module keeps across a reload of itself, in `$.state`, which the
 * host holds for the session: the engine loads the module afresh when its
 * plugin changed (an update the human's `/reload-plugins` or the autoreload
 * brings), and the module's own variables start over. An answer on its way
 * to the model when the module was reloaded is held again, so it may reach
 * the model twice, never not at all.
 */
const KEPT = { plugin: 'doperpowers', key: 'ask' } as const
/** Writes the snapshot; set as the session starts. */
let keep: ((snapshot: AskSnapshot) => void) | undefined

/** Keeps the session's asks as they stand now; called on each change of them. */
function save() {
  keep?.({ shape: 1, asks, undelivered: [...undelivered.values()], isTurnRunning, ...(store !== undefined && { store }) })
}

/** Takes up the asks a module before this one kept: every answer it had not delivered is held, for the next route. */
function restore(snapshot: AskSnapshot) {
  asks = snapshot.asks
  undelivered = new Map(snapshot.undelivered.map((item) => [item.id, item]))
  held = [...snapshot.undelivered]
  isTurnRunning = snapshot.isTurnRunning
  store = snapshot.store
}

function forgetAsyncAsks() {
  const open = asks.filter((ask) => ask.status === 'open').map((ask) => ask.id)
  asks = []
  held = []
  undelivered = new Map()
  raisedAsks = new Set()
  if (open.length > 0) {
    note({ kind: 'forgotten', ids: open })
  }
}

/** The session's async asks, open and answered, oldest first. */
export function asyncAsks(): readonly OpenAsk[] {
  return asks
}

/** Whether an ask's dialog is up: the module that raised it answers it, so a reload waits for it. */
export function isAskDialogUp(): boolean {
  return raisedAsks.size > 0
}

/** Whether a main-conversation turn is running: a slash command run now waits for its end. */
export function isMainTurnRunning(): boolean {
  return isTurnRunning
}

/** Takes every held answer, in one synchronous step, so no other route takes them too. */
const takeHeld = () => held.splice(0)

/**
 * What a delivery reaches the engine through: a hook's `$`, or the one the
 * session started with, which an answer from outside the terminal uses (it
 * arrives in no hook of this mod's).
 */
type Out = {
  submit: (text: string) => Promise<{ drop?: string }>
  invalidate: () => void
  toast: (text: string) => void
  log: (text: string) => void
}

const outOf = ($: EngineInterface): Out => ({
  submit: (text) => $.prompt.submit({ text }),
  invalidate: () => $.ui.invalidate('ui.render'),
  toast: (text) => $.ui.toast(text),
  log: (text) => $.ui.log(text, { to: 'debug' }),
})

/** The session's own `Out`, made as it started: undefined where the tool does not serve. */
let external: Out | undefined

/** A route delivered `items`: their asks read delivered. */
function delivered(out: Out, items: readonly Delivery[]) {
  items.forEach((item) => undelivered.delete(item.id))
  save()
  out.invalidate()
}

/** A route failed: `items` go back ahead of any answered meanwhile, for the next route to try. */
function putBack(out: Out, items: readonly Delivery[], why: string) {
  held.unshift(...items)
  out.toast(`An answer did not reach the model (${why}); it goes with the next message.`)
  out.log(`ask: a delivery failed, ${items.length} put back: ${why}`)
}

/** Submits `items` as one prompt of the plugin's, which runs once the session is idle. Never awaited inside a hook: the turn it waits for may be the hook's own. */
async function submitDeliveries(out: Out, items: Delivery[]) {
  try {
    const entered = await out.submit(items.map((item) => item.text).join('\n\n'))
    if (entered.drop !== undefined) {
      putBack(out, items, entered.drop)
      return
    }
    delivered(out, items)
  } catch (error) {
    putBack(out, items, message(error))
  }
}

/** An ask answered: held while a turn runs, else submitted at once with whatever was held before it. */
function deliver(out: Out, item: Delivery) {
  undelivered.set(item.id, item)
  save()
  if (isTurnRunning) {
    held.push(item)
    return
  }
  void submitDeliveries(out, [...takeHeld(), item])
}

/** The engine's closing sentences for answers that are all options, and for any other. */
const CHOSEN_END = 'You can now continue with these answers in mind.'
const TYPED_END = 'Read the answers carefully — they may request clarification, changes, or that you not proceed — and follow what they actually say.'

/**
 * The text the engine returns for `answers` to `questions` (its AskUserQuestion
 * result): each answered question as `"<question>"="<answer>"`, then the
 * sentence for answers that each name an option (a multi-select's labels
 * joined with ", "), or the one for any typed answer.
 */
export function answerText(questions: readonly AskQuestion[], answers: Readonly<Record<string, string>>): string {
  const given = questions.filter((q) => typeof answers[q.question] === 'string' && answers[q.question] !== '')
  if (given.length === 0) {
    return 'The user did not answer the questions.'
  }
  const pairs = given.map((q) => `"${q.question}"="${answers[q.question]}"`).join(', ')
  const isChosen = given.every((q) => {
    const labels = new Set(q.options.map((o) => o.label))
    const answer = answers[q.question] as string
    return labels.has(answer) || (q.multiSelect && answer.split(', ').every((part) => labels.has(part)))
  })
  return isChosen ? `Your questions have been answered: ${pairs}. ${CHOSEN_END}` : `The user answered: ${pairs}. ${TYPED_END}`
}

/**
 * An async ask answered from outside the terminal (the bridge, for a person
 * at the CLI or the web): delivered as a press's answer is, in the words the
 * dialog would have produced, and the observer told `by` whom. Refused for
 * an ask that is not open, or whose dialog the terminal has up.
 */
export function answerAsync(id: string, answers: Readonly<Record<string, string>>, by: string): { ok: true } | { ok: false; error: string } {
  const ask = asks.find((candidate) => candidate.id === id)
  if (ask === undefined) {
    return { ok: false, error: `no async question ${id} is open in this session` }
  }
  if (ask.status !== 'open') {
    return { ok: false, error: `the question ${id} was already answered` }
  }
  if (raisedAsks.has(id)) {
    return { ok: false, error: `the question ${id} is open in the terminal's dialog` }
  }
  if (external === undefined) {
    return { ok: false, error: 'the ask tool does not serve this session' }
  }
  const text = answerText(ask.questions, answers)
  ask.status = 'answered'
  ask.answer = text
  deliver(external, { id, text: deliveryText(id, text) })
  external.invalidate()
  note({ kind: 'answered', id, by })
  return { ok: true }
}

/** A press: opens the ask's dialog, and hands an answer, or "Chat about this", to the model. Esc leaves it open. */
async function answerAsk($: EngineInterface, id: string) {
  const ask = asks.find((candidate) => candidate.id === id)
  if (ask === undefined || ask.status !== 'open' || raisedAsks.has(id)) {
    return
  }
  // Held until the dialog's answer is the ask's, the waits after the dialog
  // included: an answer from outside meanwhile is refused, not a second one.
  raisedAsks.add(id)
  try {
    let outcome: DialogOutcome
    try {
      outcome = await openDialog($, ask.questions)
    } catch (error) {
      $.ui.log(`ask: ${message(error)}`, { to: 'debug' })
      $.ui.toast(`The question could not be asked: ${message(error)}`)
      return
    }
    if (outcome.kind === 'refused' && !outcome.hasFeedback) {
      return
    }
    // No route carries picture bytes: each kept paste goes as its file, for the model to Read.
    const answer = [outcome.text, ...(await imageLines($, outcome.images))].join('\n')
    ask.status = 'answered'
    ask.answer = answer
    deliver(outOf($), { id, text: deliveryText(id, answer) })
    $.ui.invalidate('ui.render')
    // The dialog goes through the PermissionRequest hooks like any other, so
    // its answer may have come from outside: the bridge names who gave it.
    note({ kind: 'answered', id, dialog: outcome.toolUseId ?? '' })
  } finally {
    raisedAsks.delete(id)
  }
}

/**
 * The stored forms resume reads, as the engine writes them into the
 * transcript (compact JSON, recorded live on 2.1.296): the tool's calls, its
 * async results, and the delivery forms. A search for these finds the
 * rows that can name an ask, and not the large rows that merely mention the
 * tool (the tool list a prompt snapshot carries).
 */
const STORED_FORMS = [
  `"name":"${ASK_TOOL}","input":`,
  ASYNC_RESULT,
  // A context attachment's entries: the first, or one behind another hook's
  // context (both routes append to what is there).
  `"type":"hook_additional_context","content":["${DELIVERY_HEAD}`,
  `","${DELIVERY_HEAD}`,
  `"content":${JSON.stringify(PLUGIN_PROMPT + DELIVERY_HEAD).slice(0, -1)}`,
]

/** The search for the stored forms in the transcript at `path`. */
export function searchArgs(path: string): string[] {
  return ['grep', '-F', ...STORED_FORMS.flatMap((form) => ['-e', form]), path]
}

/**
 * The async asks the transcript at `path` holds. One too large to read whole
 * (over 4 MiB) is searched for the lines that can name an ask, which carry no
 * ancestry: the asks of a branch the human rewound past count there too. A
 * search that fails, or whose output was cut at the same 4 MiB (it would drop
 * the newest asks), rebuilds nothing rather than a part, with a debug line.
 */
async function readAsks($: EngineInterface, path: string): Promise<OpenAsk[]> {
  let text: string
  try {
    text = await $.fs.read(path)
  } catch (error) {
    const failed = (why: string) => {
      $.ui.log(`ask: the transcript could not be read whole (${message(error)}) and ${why}; no async ask is rebuilt`, { to: 'debug' })
      return []
    }
    let search: Awaited<ReturnType<typeof $.process.run>>
    try {
      search = await $.process.run(searchArgs(path))
    } catch (searchError) {
      return failed(`could not be searched (${message(searchError)})`)
    }
    // grep: 0 lines found, 1 none, anything else a failure.
    if (search.exitCode === 1) {
      return []
    }
    if (search.exitCode !== 0) {
      return failed(`could not be searched (grep exited ${search.exitCode})`)
    }
    if (search.isStdoutTruncated === true) {
      return failed('its asks run past what one search returns')
    }
    return rebuildAsks(search.stdout.split('\n'), { isWholeFile: false })
  }
  return rebuildAsks(text.split('\n'))
}

const ANSWER_KEY = 'ask-answer:'
/** A button's own press does nothing: the `ui.press` hook answers it, where the engine can be reached. */
const noop = () => {}

/** `1 open question`, `2 open questions`: the questions of the asks still open. */
export function openCount(open: readonly OpenAsk[]): string {
  const count = open.reduce((sum, ask) => sum + ask.questions.length, 0)
  return `${count} open ${count === 1 ? 'question' : 'questions'}`
}

/**
 * The line above the prompt while an async ask is open: how many questions
 * wait, and `[ answer ]` for the oldest, since the ask's own row scrolls away
 * while the model works. The to-human view (its own plugin, outside this
 * one) draws its line under this.
 */
export function registerAskBand(on: On) {
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const inner = await next(e)
    const open = asks.filter((ask) => ask.status === 'open')
    const oldest = open[0]
    if (oldest === undefined || e.props.hasSurvey) {
      return inner
    }
    const { Box, Text, Button } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        <Box>
          <Text dimColor>{openCount(open)} · </Text>
          <Button key={`${ANSWER_KEY}${oldest.id}`} label="answer" onPress={noop} />
        </Box>
        {inner}
      </Box>
    )
  })
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
 * through `$.ui.ask` and returns the engine's own result text; an async ask
 * returns at once and is answered from its `[ answer ]`, the answer handed
 * to the model; the built-in is withdrawn from the model, and a declined ask
 * ends the model's turn as the built-in's does. The to-human view, a plugin
 * that depends on this one, sits outside its row hooks.
 */
export function registerAsk(on: On) {
  // Under MAWS (MAWS_NATIVE_TO_HUMAN set) the host offers its own ask tool,
  // so this one stays out and the built-in is left to MAWS's launch line,
  // whatever decides when the tool would otherwise register.
  on('session.start', { isInteractive: true }, async ($, e, next) => {
    const maws = await $.env.get('MAWS_NATIVE_TO_HUMAN')
    if (maws !== undefined && maws !== '') {
      return next(e)
    }
    isServing = true
    // An answer from outside the terminal comes in no hook of this mod's: it
    // is delivered through the session's own `$`.
    external = outOf($)
    // A module loaded into a running session (a reload) takes up the asks
    // the one before it kept; one starting with the process finds none.
    try {
      const { value } = await $.state.get(KEPT)
      if (isRecord(value) && value.shape === 1) {
        restore(value as AskSnapshot)
        $.ui.invalidate('ui.render')
      }
      keep = (snapshot) => void $.state.set(KEPT, snapshot).catch((error: unknown) => $.ui.log(`ask: the asks are not kept for a reload: ${message(error)}`, { to: 'debug' }))
      save()
    } catch (error) {
      $.ui.log(`ask: the asks are not kept for a reload: ${message(error)}`, { to: 'debug' })
    }
    const result = await next(e)
    await askStart($)
    return result
  })

  // Every SessionStart (agents.tsx holds the one registration a module may
  // make without a matcher): where this session's pasted pictures are kept.
  // A resumed session's async asks are read back from its transcript; a
  // cleared one has none, and a compaction keeps them.
  on('classic.SessionStart', { hook_event_name: 'SessionStart' }, async ($, e, next) => {
    store = { slug: slugOf(e.transcript_path), sessionId: e.session_id }
    if (e.source !== 'compact') {
      forgetAsyncAsks()
    }
    if (e.source === 'resume' || e.source === 'fork') {
      asks = await readAsks($, e.transcript_path)
      $.ui.invalidate('ui.render')
      for (const ask of asks.filter((candidate) => candidate.status === 'open')) {
        note({ kind: 'open', id: ask.id, questions: ask.questions })
      }
    }
    save()
    return next(e)
  }).catch((_, e, next) => next(e))

  // Every turn (compact holds the unmatched registration; a turn's id is
  // never empty): a new main turn starts unlatched, and an answer given while
  // it runs is held. A subagent's run raises its own, with its agentId, and
  // may start after the main turn ended; taken for the main turn's, it would
  // hold an answer given while the session idles until the next prompt.
  on('turn.start', { turnId: /./ }, (_, e, next) => {
    if (e.agentId === undefined) {
      isLatched = false
      isTurnRunning = true
      save()
    }
    return next(e)
  })

  // The main turn's end: what is held goes out as one prompt when the model
  // answered; a turn the human stopped (interrupted, or latched by a declined
  // ask, whatever its reason) or an error ended keeps it for their next
  // prompt. Not awaited: the prompt runs once the session is idle, after
  // this very turn.
  on('turn.complete', { turnId: /./ }, async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined) {
      isTurnRunning = false
      save()
      if (e.reason === 'answer' && !isLatched && held.length > 0) {
        void submitDeliveries(outOf($), takeHeld())
      } else if (held.length > 0 || isLatched) {
        $.ui.log(`ask: the turn ended (${e.reason}${isLatched ? ', latched' : ''}); ${held.length} held for the next prompt`, { to: 'debug' })
      }
    }
    return result
  })

  // The human's next prompt carries what is held, as context the model reads
  // beside it; a prompt dropped beneath puts it back.
  on('prompt.submit', { text: /^/ }, async ($, e, next) => {
    if (held.length === 0) {
      return next(e)
    }
    const items = takeHeld()
    let result: Awaited<ReturnType<typeof next>>
    try {
      result = await next({ ...e, context: [...(e.context ?? []), ...items.map((item) => item.text)] })
    } catch (error) {
      // The failure policy below lets the prompt through without them: they wait for the next route.
      putBack(outOf($), items, message(error))
      throw error
    }
    if (result.drop !== undefined) {
      putBack(outOf($), items, result.drop)
    } else {
      delivered(outOf($), items)
    }
    return result
  }).catch((_, e, next) => next(e))

  // A press on an ask's `[ answer ]`, in its row or above the prompt: the
  // dialog is raised from inside this dispatch, as the engine requires.
  on('ui.press', { element: /^ask-answer:/ }, async ($, e, next) => {
    const result = await next(e)
    await answerAsk($, e.element.slice(ANSWER_KEY.length))
    return result
  })

  // The tool's row draws what the engine draws for the built-in's, and an
  // open async ask with its `[ answer ]`; its result row draws nothing beside it.
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (e.props.tool !== ASK_TOOL) {
      return next(e)
    }
    const ask = asks.find((candidate) => candidate.id === e.props.tool_use_id)
    const row = askRow(e.props, ask, !undelivered.has(e.props.tool_use_id))
    if (row.kind === 'engine') {
      return next(e)
    }
    const { Box, Text, Button } = $.ui.resolve(e)
    if (row.kind === 'none') {
      return <Box />
    }
    const lines =
      row.kind === 'open'
        ? row.questions.map((q) => `· ${q.header} — ${q.question}`)
        : row.kind === 'answered'
          ? row.rows.map(([question, answer]) => `· ${question} → ${answer}`)
          : row.questions.map((q) => `· ${q.question} (${q.options.map((o) => o.label).join(' / ')})`)
    const title = row.kind === 'open' ? 'Claude asked (answer when ready):' : row.kind === 'answered' ? "User answered Claude's questions:" : 'User declined to answer questions'
    return (
      <Box flexDirection="column" marginTop={1}>
        <Text>⏺ {title}</Text>
        <Box flexDirection="row">
          <Text dimColor>{'  ⎿  '}</Text>
          <Box flexDirection="column">
            {lines.map((line) => (
              <Text key={line} color="inactive">
                {line}
              </Text>
            ))}
            {row.kind === 'open' ? <Button key={`${ANSWER_KEY}${e.props.tool_use_id}`} label="answer" onPress={noop} /> : null}
            {row.kind !== 'open' && !row.isDelivered ? <Text dimColor>not delivered yet</Text> : null}
          </Box>
        </Box>
      </Box>
    )
  })
  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    if (e.props.tool !== ASK_TOOL) {
      return next(e)
    }
    const ask = asks.find((candidate) => candidate.id === e.props.tool_use_id)
    const row = askRow({ input: undefined, output: e.props.output, isRunning: false, isErrored: e.props.isErrored }, ask)
    if (row.kind === 'engine') {
      return next(e)
    }
    const { Box } = $.ui.resolve(e)
    return <Box />
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
  //
  // Held answers ride the result of the model's next call in the main loop,
  // all together: never a plugin's own call (the mod's nested dialog, another
  // plugin's), whose context the model never reads, never a deny, and never a
  // call the human's interrupt cut (the engine stores no context for it). The
  // queue is taken in the same synchronous step that builds the context.
  on('tool.call', async ($, e, next) => {
    if (isLatched && isModelMainCall(next.origin, e)) {
      return { deny: LATCHED }
    }
    const result = await next(e)
    if (held.length === 0 || !isModelMainCall(next.origin, e) || result.deny !== undefined || next.signal.aborted) {
      return result
    }
    const items = takeHeld()
    delivered(outOf($), items)
    return { ...result, context: [...(result.context ?? []), ...items.map((item) => item.text)] }
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
    entry.toolUseId = e.tool_use_id
    // What the engine returned for this dialog's call, which the bridge's
    // own hooks do not see (the call is this plugin's): whose answer it used.
    note({ kind: 'dialog', toolUseId: e.tool_use_id ?? '', isError: entry.outcome.kind === 'refused', text: entry.outcome.text })
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
    const { questions } = input as AskInput
    if ((input as AskInput).async === true) {
      const ask: OpenAsk = { id: e.tool_use_id ?? `ask-${++raised}`, questions, status: 'open' }
      asks.push(ask)
      save()
      $.ui.invalidate('ui.render')
      note({ kind: 'open', id: ask.id, questions })
      return { result: ASYNC_RESULT }
    }
    let outcome: DialogOutcome
    try {
      outcome = await openDialog($, questions)
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
