import type { SheetKept } from '../../types/sminos'

/**
 * The question sheet's model: everything of the sheet's mod that takes no `$`
 * (the plan docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md,
 * I6, I8, I10, I11). The tool's description and schema, the start choice's
 * table, the input's validation and an entry's own rules, what a reference's
 * Read is asked and answers, the result texts the mod writes itself, the
 * floor read from a conversation, and the views' order. `sheet.tsx` holds the
 * hooks and everything that takes `$`.
 */

/** The tool as the model names it: the same tool as today's, under the sheet's schema (composite §2.1). */
export const SHEET_TOOL = 'mcp__sminos__AskUserQuestion'

/**
 * `SMINOS_QUESTION_SHEET` unset: whether a terminal session with a surface
 * takes the sheet. Off until C7 turns the default on, so a session takes the
 * sheet only where someone opted in (composite §7).
 */
export const SHEET_DEFAULT = false

/**
 * The setting's word: on for `1`, `true`, `on`, `yes`, off for `0`, `false`,
 * `off`, `no`, in any case; unset, or a word that is neither, is the default
 * (the second with `isUnknown`, for a debug line).
 */
export function settingOf(value: string | undefined): { isOn: boolean; isUnknown?: true } {
  const word = (value ?? '').trim().toLowerCase()
  if (['1', 'true', 'on', 'yes'].includes(word)) return { isOn: true }
  if (['0', 'false', 'off', 'no'].includes(word)) return { isOn: false }
  return word === '' ? { isOn: SHEET_DEFAULT } : { isOn: SHEET_DEFAULT, isUnknown: true }
}

// ------------------------------------------------------------------ the tool as the model reads it

/**
 * The description the tool is registered under: C1's `description-v3.md`
 * (tests/output-styles/question-sheet/), word for word, the owner's ruling on
 * the baseline (composite §2.4). A mod loads no file, so it is held here;
 * `tests/mods/test-sheet-step.sh` holds it equal to the file.
 */
export const DESCRIPTION = [
  "Put questions for the human on this session's question sheet. The human reads the sheet apart from this conversation and answers any question, in any order, when they choose; the answers reach you later as a message. The call returns at once and nothing waits on it: keep working on whatever does not depend on the answers.",
  'Ask when a question comes up, then keep working.',
  'A question stays open until the human answers or dismisses it. When something changes an open question you asked (a fact it rests on, an option that no longer holds, what you would recommend), revise that question: an `ask` entry with its `id` replaces it in place, and the human sees it marked as updated. Do not ask a second question in its stead, since the human would have to work out which of the two stands. Put in `withdraw` a question that no longer needs an answer.',
  'The human sees each question as a card on its own: its header, question, options, `context` and `references`, and nothing of this conversation, your notes or your earlier messages. Write the card so that someone who has only the card can decide: in `context`, what the question turns on (what you found, with the facts and numbers and where they come from) and what each option would lead to; in `references`, the files it concerns. Mark the option you recommend `recommended`, and say why in `context`.',
].join('\n\n')

/**
 * Each property's description: the one C1's stub registers for that field
 * (`FIELD_DESCRIPTIONS` in tests/output-styles/question_sheet.py;
 * `description-v3.md` sets none of its own), so C1's evals measure the tool as
 * it ships. A reference's `path` and `lines` have none there, and none here.
 */
export const FIELD_DESCRIPTIONS = {
  ask: 'Questions to add, or to revise by id: 1 to 20 entries.',
  id: 'The id of an open question you asked ("q3"): this entry replaces that question. Leave it out to add a new question; the tool assigns ids.',
  question: 'The question.',
  header: 'Optional short label.',
  options: 'Zero to twelve choices; none for a question answered in words. The human can always add text.',
  label: 'The choice, short. Unique within the question.',
  description: 'Optional: what choosing it means.',
  preview: 'Optional Markdown shown beside the focused option (single-select only).',
  recommended: 'Optional: true on the option you recommend.',
  multiSelect: 'Optional: the human may pick several options.',
  context: 'Optional Markdown: what the human needs to judge the question.',
  references: 'Optional: up to eight files the question is about, captured as they are now; each a path and an optional [first, last] line range.',
  withdraw: 'Ids of open questions you asked that no longer need an answer.',
} as const

const F = FIELD_DESCRIPTIONS

/**
 * The schema the tool is registered under: the published
 * `sminos/types/sheet/schema/tool-input.schema.json` with a description on
 * each property. Its `title`, a note on the file for an implementer, is the
 * file's description and is not the model's to read. A mod loads no JSON
 * (`bridge-routes.tsx` is the precedent); `tests/mods/test-sheet-step.sh`
 * holds this equal to the file once the descriptions are taken out.
 */
export const INPUT_SCHEMA: Record<string, unknown> = {
  $schema: 'https://json-schema.org/draft/2020-12/schema',
  type: 'object',
  additionalProperties: false,
  required: [],
  properties: {
    ask: { type: 'array', minItems: 1, maxItems: 20, items: { $ref: '#/$defs/entry' }, description: F.ask },
    withdraw: { type: 'array', minItems: 1, items: { $ref: '#/$defs/id' }, description: F.withdraw },
  },
  $defs: {
    entry: {
      type: 'object',
      additionalProperties: false,
      required: ['question'],
      properties: {
        id: { $ref: '#/$defs/id', description: F.id },
        question: { type: 'string', minLength: 1, maxLength: 2000, description: F.question },
        header: { type: 'string', maxLength: 60, description: F.header },
        options: { type: 'array', maxItems: 12, items: { $ref: '#/$defs/option' }, description: F.options },
        multiSelect: { type: 'boolean', description: F.multiSelect },
        context: { type: 'string', maxLength: 8000, description: F.context },
        references: { type: 'array', maxItems: 8, items: { $ref: '#/$defs/reference' }, description: F.references },
      },
    },
    id: { type: 'string', pattern: '^q[1-9][0-9]{0,8}$' },
    option: {
      type: 'object',
      additionalProperties: false,
      required: ['label'],
      properties: {
        label: { type: 'string', minLength: 1, maxLength: 200, description: F.label },
        description: { type: 'string', maxLength: 500, description: F.description },
        preview: { type: 'string', maxLength: 8000, description: F.preview },
        recommended: { type: 'boolean', description: F.recommended },
      },
    },
    reference: {
      type: 'object',
      additionalProperties: false,
      required: ['path'],
      properties: {
        path: { type: 'string', minLength: 1 },
        lines: { type: 'array', minItems: 2, maxItems: 2, items: { type: 'integer' } },
      },
    },
  },
}

/** What the built-in answers while the sheet stands in for it, as its description and as its refusal (I8). */
export const WITHDRAWN = `Withdrawn in this session: ask through ${SHEET_TOOL}, which puts your questions on the session's sheet.`

// ------------------------------------------------------------------ the input (I6)

export type Reference = { path: string; lines?: [number, number] }
export type Option = { label: string; description?: string; preview?: string; recommended?: boolean }
export type Entry = {
  id?: string
  question: string
  header?: string
  options?: Option[]
  multiSelect?: boolean
  context?: string
  references?: Reference[]
}
export type SheetInput = { ask?: Entry[]; withdraw?: string[] }

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

/** Characters as the composite counts them: Unicode code points (K5). */
export const codePoints = (text: string) => [...text].length

type Path = (string | number)[]
type Issue =
  | { kind: 'missing'; path: Path }
  | { kind: 'unknown'; path: Path }
  | { kind: 'mistyped'; path: Path; expected: string; received: string }
  | { kind: 'other'; path: Path; message: string }

/** zod's name for what it received, as today's tool's errors say it. */
function kindOf(value: unknown): string {
  if (value === undefined) return 'undefined'
  if (value === null) return 'null'
  if (Array.isArray(value)) return 'array'
  if (typeof value === 'number' && Number.isNaN(value)) return 'nan'
  return typeof value
}

function isType(value: unknown, type: string): boolean {
  switch (type) {
    case 'object':
      return isRecord(value)
    case 'array':
      return Array.isArray(value)
    case 'integer':
      return typeof value === 'number' && Number.isInteger(value)
    default:
      return typeof value === type
  }
}

/** The issues of `value` against `schema`, a node of INPUT_SCHEMA: the published keywords only (I1). */
function check(issues: Issue[], schema: Record<string, unknown>, value: unknown, path: Path) {
  if (typeof schema.$ref === 'string') {
    const name = schema.$ref.replace('#/$defs/', '')
    check(issues, (INPUT_SCHEMA.$defs as Record<string, Record<string, unknown>>)[name] as Record<string, unknown>, value, path)
    return
  }
  const type = schema.type as string
  if (!isType(value, type)) {
    issues.push({ kind: 'mistyped', path, expected: type, received: kindOf(value) })
    return
  }
  if (type === 'object') {
    const record = value as Record<string, unknown>
    const properties = schema.properties as Record<string, Record<string, unknown>>
    for (const key of schema.required as string[]) {
      if (record[key] === undefined) issues.push({ kind: 'missing', path: [...path, key] })
    }
    for (const [key, inner] of Object.entries(record)) {
      const property = properties[key]
      if (property === undefined) {
        issues.push({ kind: 'unknown', path: [...path, key] })
      } else if (inner !== undefined) {
        check(issues, property, inner, [...path, key])
      }
    }
  } else if (type === 'array') {
    const items = value as unknown[]
    items.forEach((item, i) => check(issues, schema.items as Record<string, unknown>, item, [...path, i]))
    if (typeof schema.minItems === 'number' && items.length < schema.minItems) {
      issues.push({ kind: 'other', path, message: `Too small: expected array to have >=${schema.minItems} items` })
    }
    if (typeof schema.maxItems === 'number' && items.length > schema.maxItems) {
      issues.push({ kind: 'other', path, message: `Too big: expected array to have <=${schema.maxItems} items` })
    }
  } else if (type === 'string') {
    const length = codePoints(value as string)
    if (typeof schema.minLength === 'number' && length < schema.minLength) {
      issues.push({ kind: 'other', path, message: `Too small: expected string to have >=${schema.minLength} characters` })
    }
    if (typeof schema.maxLength === 'number' && length > schema.maxLength) {
      issues.push({ kind: 'other', path, message: `Too big: expected string to have <=${schema.maxLength} characters` })
    }
    if (typeof schema.pattern === 'string' && !new RegExp(schema.pattern).test(value as string)) {
      issues.push({ kind: 'other', path, message: `Invalid string: must match pattern /${schema.pattern}/` })
    }
  }
}

/** `ask[0].options` from `['ask', 0, 'options']`. */
const pathText = (path: Path) => path.reduce<string>((text, part, i) => (typeof part === 'number' ? `${text}[${part}]` : i === 0 ? part : `${text}.${part}`), '')

/** Past this many, the rest of the issues are counted, as today's tool counts them. */
const LISTED = 20

/**
 * The denial of a call that breaks the whole call's rules (I6's first kind):
 * the published schema, then the two rules of the call no schema of its
 * keywords states, at least one of `ask` and `withdraw` and an id at most once
 * across both. In the words today's tool's denial uses, one line an issue;
 * undefined for a call that passes. A denied call reaches no step.
 */
export function validateCall(input: unknown): string | undefined {
  const issues: Issue[] = []
  check(issues, INPUT_SCHEMA, input, [])
  if (issues.length === 0 && isRecord(input)) {
    const call = input as SheetInput
    if (call.ask === undefined && call.withdraw === undefined) {
      issues.push({ kind: 'other', path: [], message: 'a call puts at least one entry in `ask` or one id in `withdraw`' })
    }
    const ids = [...(call.ask ?? []).flatMap((entry) => (entry.id === undefined ? [] : [entry.id])), ...(call.withdraw ?? [])]
    const twice = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))]
    for (const id of twice) {
      issues.push({ kind: 'other', path: [], message: `${id} is named more than once across \`ask\` and \`withdraw\`; a call names an id at most once` })
    }
  }
  if (issues.length === 0) {
    return undefined
  }
  const order = { missing: 0, unknown: 1, mistyped: 2, other: 3 }
  const lines = [...issues]
    .sort((a, b) => order[a.kind] - order[b.kind])
    .map((issue) => {
      switch (issue.kind) {
        case 'missing':
          return `The required parameter \`${pathText(issue.path)}\` is missing`
        case 'unknown':
          return `An unexpected parameter \`${pathText(issue.path)}\` was provided`
        case 'mistyped':
          return `${issue.path.length === 0 ? 'The input' : `The parameter \`${pathText(issue.path)}\``} type is expected as \`${issue.expected}\` but provided as \`${issue.received}\``
        default:
          return `${issue.path.length === 0 ? 'The input' : `The parameter \`${pathText(issue.path)}\``} is invalid: ${issue.message}`
      }
    })
  const listed = lines.slice(0, LISTED)
  const unlisted = lines.length - listed.length
  if (unlisted > 0) listed.push(`(${unlisted} more ${unlisted === 1 ? 'issue' : 'issues'} not listed)`)
  return `InputValidationError: AskUserQuestion failed due to the following ${lines.length > 1 ? 'issues' : 'issue'}:\n${listed.join('\n')}`
}

/** Whether a string holds a UTF-16 surrogate that is not half of a pair. */
const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/

function holdsLoneSurrogate(value: unknown): boolean {
  if (typeof value === 'string') return LONE_SURROGATE.test(value)
  if (Array.isArray(value)) return value.some(holdsLoneSurrogate)
  if (isRecord(value)) return Object.entries(value).some(([key, inner]) => LONE_SURROGATE.test(key) || holdsLoneSurrogate(inner))
  return false
}

/** The first N characters of `text` and `…` when it was longer: the step's `mark`. */
export function cut(text: string, n: number): string {
  const chars = [...text]
  return chars.length <= n ? text : `${chars.slice(0, n).join('')}…`
}

/**
 * An entry's own refusal (U14), as its clause after `entry <n>, `, the step's
 * words (`entry_problem` in sminos_sheet_step.py, which checks them again):
 * a lone surrogate, two options with one label, a preview on a multi-select
 * question, `multiSelect` without options, a line range out of order. The
 * entry passed the schema.
 */
export function entryProblem(entry: Entry): string | undefined {
  if (holdsLoneSurrogate(entry)) {
    return 'a string holds a lone UTF-16 surrogate'
  }
  const seen = new Set<string>()
  for (const { label } of entry.options ?? []) {
    if (seen.has(label)) return `two options share the label "${[...label].slice(0, 200).join('')}"`
    seen.add(label)
  }
  if (entry.multiSelect === true && (entry.options ?? []).some((o) => o.preview !== undefined)) {
    return "an option's preview needs a single-select question"
  }
  if (entry.multiSelect === true && (entry.options ?? []).length === 0) {
    return 'multiSelect needs options'
  }
  for (const reference of entry.references ?? []) {
    if (reference.lines !== undefined && !(1 <= reference.lines[0] && reference.lines[0] <= reference.lines[1])) {
      return 'lines must be [a, b] with 1 <= a <= b'
    }
  }
  return undefined
}

// ------------------------------------------------------------------ references (I5 Capture, C0's P3)

/** The path a reference names, absolute: as given when it is, else under the session's working directory. */
export function absoluteOf(path: string, cwd: string): string {
  return path.startsWith('/') ? path : `${cwd.replace(/\/+$/, '')}/${path}`
}

/** Read's input for a reference: its range as Read's `offset` and `limit` (`lines: [a, b]` is offset a, limit b − a + 1). */
export function readInput(reference: Reference, cwd: string): { file_path: string; offset?: number; limit?: number } {
  const file_path = absoluteOf(reference.path, cwd)
  if (reference.lines === undefined) {
    return { file_path }
  }
  const [a, b] = reference.lines
  return { file_path, offset: a, limit: b - a + 1 }
}

/** What one write of the staging may hold: `$.fs.write` refuses past 4 MiB. */
export const STAGED_MAX = 4 * 1024 * 1024

/** A body Read gave, as the staging keeps it: a text's content, or an image's bytes in base64. */
export type Captured =
  | { ok: true; kind: 'text'; body: string; startLine: number; numLines: number; totalLines: number }
  | { ok: true; kind: 'image'; body: string; mediaType: string }
  | { ok: false; reason: string }

const nonNegative = (n: unknown): n is number => typeof n === 'number' && Number.isInteger(n) && n >= 0

/**
 * What a Read of a reference answered (`$.tool.call`'s result, C0's P3):
 * `file.content` for a text, the field a guard's `tool.call` hook rewrites,
 * with Read's own lines; `file.base64` and its `type` for an image. Any other
 * answer refuses the reference with the engine's reason: a deny, an error (a
 * missing file, one over 256 KB named without a range), and anything else
 * Read returns, its "unchanged since read" stub among them.
 */
export function capturedOf(result: unknown): Captured {
  const r = isRecord(result) ? result : {}
  const text = typeof r.text === 'string' ? r.text.trim() : ''
  if (typeof r.deny === 'string') {
    return { ok: false, reason: r.deny }
  }
  if (r.isError === true) {
    return { ok: false, reason: text || 'Read failed' }
  }
  const record = isRecord(r.result) ? r.result : {}
  const file = isRecord(record.file) ? record.file : {}
  if (record.type === 'text' && typeof file.content === 'string' && nonNegative(file.startLine) && nonNegative(file.numLines) && nonNegative(file.totalLines)) {
    return { ok: true, kind: 'text', body: file.content, startLine: file.startLine, numLines: file.numLines, totalLines: file.totalLines }
  }
  if (record.type === 'image' && typeof file.base64 === 'string' && typeof file.type === 'string') {
    if (file.base64.length > STAGED_MAX) {
      return { ok: false, reason: `the image is ${file.base64.length} bytes in base64, past the ${STAGED_MAX} the sheet keeps` }
    }
    return { ok: true, kind: 'image', body: file.base64, mediaType: file.type }
  }
  return { ok: false, reason: text || `Read returned ${typeof record.type === 'string' ? `a ${record.type} result` : 'no file'}, which the sheet does not keep` }
}

/** The check's verdict, as the reason an entry is refused for when it is not `allow`. */
export function checkRefusal(verdict: unknown): string | undefined {
  const v = isRecord(verdict) ? verdict : {}
  if (v.decision === 'allow') {
    return undefined
  }
  return typeof v.reason === 'string' && v.reason !== '' ? v.reason : `the permission check answered ${typeof v.decision === 'string' ? v.decision : 'nothing'}`
}

/** An entry refused for a reference it could not capture: its clause after `entry <n>, ` (I6). */
export function unreadClause(path: string, reason: string): string {
  return `the reference ${cut(path, 200)} could not be read: ${reason}`
}

// ------------------------------------------------------------------ results the mod writes (I6)

/** A foreclosed call's result: nothing done, and why, the one clause I6 gives it. */
export function foreclosedResult(why: string): string {
  return `Nothing done.\nNot done: the sheet could not be written (${cut(why, 500)}); call again.`
}

/** A call whose step and settling gave no answer: the outcome follows as a notice (I9). */
export const NOT_KNOWN = 'Outcome not known yet.\nThe sheet did not answer. Do not repeat this call: what it did will be told to you.'

/** Why a call made before the session's start step answered changed nothing (I8, Started). */
export const STARTING = 'the sheet is still starting'

/**
 * The notice for a call answered `Outcome not known yet.` once a later settle
 * answers it (I9): the result's first line, or that it changed nothing.
 */
export function outcomeNotice(callId: string, outcome: { result: string } | { foreclosed: true }): string {
  const first = 'result' in outcome ? (outcome.result.split('\n')[0] ?? '') : 'Nothing done.'
  return first === 'Nothing done.'
    ? `[sheet v1] Your earlier call (${callId}) changed nothing; call again if you still need it.`
    : `[sheet v1] Your earlier call (${callId}) did change the sheet: ${first}`
}

/**
 * What the person is told as the agent asks (today's tool's announcement):
 * the first question the call added, `(+N more)` beside it; nothing for a call
 * that added none. Read from the result's first line: its `Added` sentence
 * names the added ids, with their entries' places when anything was refused,
 * else they are the entries without an id, in order.
 */
export function announcement(input: SheetInput, result: string): string | undefined {
  const added = /^Added ([^.]*)\./.exec(result.split('\n')[0] ?? '')
  if (added === null) {
    return undefined
  }
  const items = (added[1] as string).split(', ')
  const place = /\(entry (\d+)\)/.exec(items[0] ?? '')
  const entries = input.ask ?? []
  const first = place !== null ? entries[Number(place[1]) - 1] : entries.find((entry) => entry.id === undefined)
  const question = first?.question.trim()
  if (question === undefined || question === '') {
    return undefined
  }
  return items.length > 1 ? `${question} (+${items.length - 1} more)` : question
}

// ------------------------------------------------------------------ the start choice (I8)

export type Choice = SheetKept['choice']
export type Runner = NonNullable<SheetKept['runner']>

/** What `sminos sheet probe` answers (I5): a few hundred bytes whatever the record holds. */
export type Probe = { record: boolean; open: number; pending: number; queued: number; surface: { name: string; url: string; reach: string } | null; surfaces: number }

/**
 * What the choice reads, each only where the table needs it: with no record
 * and the setting off it starts no process.
 */
/** The environment variables the choice reads, each read only when its row is reached. */
export type ChoiceEnv = 'SMNS_INTERNAL' | 'MAWS_QUESTION_SHEET' | 'MAWS_NATIVE_TO_HUMAN' | 'SSH_CONNECTION' | 'SMINOS_QUESTION_SHEET'

export type ChoiceReads = {
  kept: SheetKept | undefined
  hasKeptAsk: boolean
  session: string
  isInteractive: boolean
  env: Record<ChoiceEnv, () => Promise<string | undefined>>
  hasRecord: () => Promise<boolean>
  probe: (remote: boolean) => Promise<Probe | undefined>
}

export type Chosen = { choice: Choice; runner?: Runner; why: string; log?: string[] }

const isSet = (value: string | undefined): value is string => value !== undefined && value !== ''

/**
 * I8's table, top row first: the choice is made at a process's first
 * `session.start` and kept, so a reload and a /clear keep the process's.
 */
export async function chooseStart(reads: ChoiceReads): Promise<Chosen> {
  const log: string[] = []
  if (reads.kept !== undefined) {
    return { choice: reads.kept.choice, ...(reads.kept.runner !== undefined && { runner: reads.kept.runner }), why: 'kept' }
  }
  if (reads.hasKeptAsk) {
    return { choice: 'today', why: 'a module before this one served the ask here' }
  }
  if (isSet(await reads.env.SMNS_INTERNAL())) {
    return { choice: 'none', why: 'an internal session' }
  }
  const maws = await reads.env.MAWS_QUESTION_SHEET()
  if (isSet(maws)) {
    if (maws === reads.session) {
      return { choice: 'sheet', runner: 'maws', why: 'MAWS_QUESTION_SHEET names this session' }
    }
    log.push(`sheet: MAWS_QUESTION_SHEET is set and names another session (${cut(maws, 80)}, not ${reads.session}): not taken as MAWS's proof`)
  }
  const done = (chosen: Omit<Chosen, 'log'>): Chosen => (log.length > 0 ? { ...chosen, log } : chosen)
  if (isSet(await reads.env.MAWS_NATIVE_TO_HUMAN())) {
    return done({ choice: 'none', why: 'MAWS serves its own ask' })
  }
  if (!reads.isInteractive) {
    return done({ choice: 'none', why: 'not interactive' })
  }
  const remote = isSet(await reads.env.SSH_CONNECTION())
  let probe: Probe | undefined
  if (await reads.hasRecord()) {
    probe = await reads.probe(remote)
    if (probe !== undefined && probe.record && probe.open + probe.pending + probe.queued > 0) {
      return done({ choice: 'sheet', runner: 'terminal', why: 'the sheet holds questions, outcomes or queued lines' })
    }
  }
  const setting = settingOf(await reads.env.SMINOS_QUESTION_SHEET())
  if (setting.isUnknown === true) {
    log.push('sheet: SMINOS_QUESTION_SHEET is neither on nor off; its default holds')
  }
  if (!setting.isOn) {
    return done({ choice: 'today', why: 'the setting is off' })
  }
  probe ??= await reads.probe(remote)
  if (probe?.surface != null) {
    return done({ choice: 'sheet', runner: 'terminal', why: `the surface ${probe.surface.name} is alive and suits` })
  }
  return done({ choice: 'today', why: probe === undefined ? 'the surfaces could not be read' : remote ? 'no remote surface is alive' : 'no surface is alive' })
}

// ------------------------------------------------------------------ the view (I5), adopted in the record's order

export type Asker = 'main' | { agentId: string; name: string }
export type Recipient = 'main' | { agentId: string }
export type View = {
  seq: number
  offset: number
  nextId: number
  open: { id: string; revision: number; asker: Asker; header?: string; question: string; askedAt: string }[]
  pending: { key: string; id: string; kind: 'answer' | 'dismiss'; recipient: Recipient; taken: boolean; acrossStop: boolean }[]
  pendingCount: number
  owedAcrossStop: number
  closed: Record<string, { how: string; revision: number; header?: string; receipt?: string }>
  answered: { id: string; header?: string; question: string; answer: string }[]
  answeredCount: number
  ready: { recipient: Recipient; keys: string[]; text: string; wakes: boolean; more: boolean }[]
  surface: { name: string; url: string; reach: string } | null
  surfaces: number
}
export type Verdict = Record<string, unknown> & { verdict: string }
export type Effects = {
  applied: string[]
  skipped: number
  verdicts: Record<string, Verdict>
  result?: string
  foreclosed?: true
  context?: string
  owed: number
  start?: { empty: 'fork' | 'lost' | null; before: string[]; beforeCount: number; imported: { callId: string; ids: string[] }[] }
}
export type StepAnswer = { ok: true; seq: number; view: View; effects: Effects } | { ok: false; code: string; error: string }

/** A step's printed answer, read; undefined for what is no answer (I5: "A step never fails a session"). */
export function answerOf(stdout: string): StepAnswer | undefined {
  try {
    const answer: unknown = JSON.parse(stdout)
    if (isRecord(answer) && answer.ok === true && typeof answer.seq === 'number' && isRecord(answer.view) && isRecord(answer.effects)) {
      return answer as StepAnswer
    }
    if (isRecord(answer) && answer.ok === false && typeof answer.code === 'string') {
      return { ok: false, code: answer.code, error: typeof answer.error === 'string' ? answer.error : answer.code }
    }
  } catch {
    // Output that is not JSON is no answer.
  }
  return undefined
}

/**
 * Whether a view answered for `session` replaces the one held: the record's
 * order (its `seq`), so an answer that comes late changes nothing; a view of
 * another session (one a /clear left) is never adopted.
 */
export function isNewer(held: { session: string; view: View } | undefined, session: string, view: View): boolean {
  return held === undefined || held.session !== session || view.seq >= held.view.seq
}

/** Whether a view holds a subagent's question or outcome: then the running agents go with every step (I9). */
export function hasSubagent(view: View | undefined): boolean {
  return view !== undefined && (view.open.some((q) => q.asker !== 'main') || view.pending.some((o) => o.recipient !== 'main'))
}

// ------------------------------------------------------------------ the floor (I10)

/** The highest id a record may assign: `q999999999` (I2). */
const ID_MAX = 999_999_999

const ID = /\bq([1-9][0-9]{0,8})\b/g
const RESULT_IDS = /^(?:Added|Revised|Withdrew) q[1-9]/
const NEW_IDS = /New ids (?:continue from|start at) q([1-9][0-9]{0,8})\./g
const BLOCK = /<sheet-delivery>(.*?)<\/sheet-delivery>/gs
const NOTICE = /\[sheet v1\] Your earlier call \([^)\n]*\) did change the sheet: ([^\n]*)/g
/** What every text the sheet puts in a conversation carries: its heads, the fork's and the lost record's lines (M2's step). */
const SHEET_MARK = '[sheet v1]'
/** A hook's context as a conversation holds it: the engine's own prefix (C0's P5), in a reminder or bare. */
const CONTEXT = /^(?:<system-reminder>\n)?[A-Za-z][A-Za-z.]* hook additional context: /
/** This plugin's prompt, as the engine prefixes it (an idle session's route). */
const PLUGIN_PROMPT = 'The sminos plugin sent a message:\n'

const idsIn = (text: string) => [...text.matchAll(ID)].map((match) => Number(match[1]))
const highest = (ns: readonly number[]) => Math.min(ns.reduce((a, b) => Math.max(a, b), 0), ID_MAX - 1)

/**
 * The highest question number a call's result names: its first line's
 * `Added`, `Revised` and `Withdrew` sentences (I6). 0 for none.
 */
export function floorOfResult(text: string): number {
  const first = text.split('\n', 1)[0] ?? ''
  return RESULT_IDS.test(first) ? highest(idsIn(first)) : 0
}

/**
 * The highest question number a text the sheet put in the conversation
 * names (a hook's context, or this plugin's prompt; the caller knows it is
 * one): an envelope's block (its answered and dismissed ids); in a text of
 * the sheet's (`[sheet v1]`), the `New ids … q<n>.` sentence, at a line's
 * start after a start's context or inline after the fork's and the lost
 * record's lines (it names the next id, so the floor it gives is n − 1); and
 * a notice of a call's late outcome. 0 for none.
 */
export function floorOfSheetText(text: string): number {
  const found: number[] = []
  for (const [, body] of text.matchAll(BLOCK)) {
    try {
      const block: unknown = JSON.parse(body as string)
      if (isRecord(block) && block.v === 1 && Array.isArray(block.answered) && Array.isArray(block.dismissed)) {
        for (const id of [...block.answered.map((a) => (isRecord(a) ? a.id : undefined)), ...block.dismissed]) {
          if (typeof id === 'string') found.push(...idsIn(id))
        }
      }
    } catch {
      // A block that is not JSON names nothing.
    }
  }
  if (text.includes(SHEET_MARK)) {
    found.push(...[...text.matchAll(NEW_IDS)].map((match) => Number(match[1]) - 1))
    found.push(...[...text.matchAll(NOTICE)].map((match) => floorOfResult(match[1] as string)))
  }
  return highest(found)
}

/**
 * The text a conversation's item carries when the engine marks it as one a
 * plugin put there: a hook's context (behind the engine's prefix), or this
 * plugin's prompt. Anything else (the human's words, a tool's output, the
 * model's) is no sheet's text: undefined.
 */
export function sheetTextOf(text: string): string | undefined {
  if (CONTEXT.test(text)) return text.replace(CONTEXT, '')
  if (text.startsWith(PLUGIN_PROMPT)) return text.slice(PLUGIN_PROMPT.length)
  return undefined
}

const floorOfItem = (text: string) => {
  const own = sheetTextOf(text)
  return own === undefined ? 0 : floorOfSheetText(own)
}

/** The texts of a content: a string, or its text blocks. */
function textsOf(content: unknown): string[] {
  if (typeof content === 'string') return [content]
  return Array.isArray(content) ? content.flatMap((block) => (isRecord(block) && block.type === 'text' && typeof block.text === 'string' ? [block.text] : [])) : []
}

/** The blocks of a content of one type. */
function blocksIn(content: unknown, type: string): Record<string, unknown>[] {
  return Array.isArray(content) ? content.filter((block): block is Record<string, unknown> => isRecord(block) && block.type === type) : []
}

/** A tool result's text: a string, or its text blocks joined. */
function resultText(content: unknown): string {
  return textsOf(content).join('\n')
}

/**
 * The floor of one user-side content: the results of the tool's own calls
 * (paired by id), and the items the engine marks as a plugin's, a context
 * in a tool result's blocks included. Another tool's output, and the
 * human's words, name nothing whatever they quote.
 */
function floorOfContent(content: unknown, calls: ReadonlySet<string>): number {
  let floor = Math.max(0, ...textsOf(content).map(floorOfItem))
  for (const block of blocksIn(content, 'tool_result')) {
    if (calls.has(String(block.tool_use_id))) {
      floor = Math.max(floor, floorOfResult(resultText(block.content)))
    } else {
      floor = Math.max(floor, ...blocksIn(block.content, 'text').map((inner) => floorOfItem(String(inner.text))))
    }
  }
  return floor
}

/** The ids of the tool's calls in a list of assistant contents. */
const sheetCalls = (contents: readonly unknown[]) =>
  new Set(contents.flatMap((content) => blocksIn(content, 'tool_use').filter((b) => b.name === SHEET_TOOL).map((b) => String(b.id))))

/**
 * The floor of a transcript's rows, as the engine stores them: the results
 * of the tool's calls (paired with their calls by id), the hooks' contexts
 * (attachment rows) and a plugin's prompt; the model's rows, another tool's
 * output and the human's words name nothing.
 */
export function floorOfRows(rows: readonly Record<string, unknown>[]): number {
  const contentOf = (row: Record<string, unknown>) => (isRecord(row.message) ? row.message.content : undefined)
  const calls = sheetCalls(rows.filter((row) => row.type === 'assistant').map(contentOf))
  let floor = 0
  for (const row of rows) {
    if (row.type === 'user') {
      floor = Math.max(floor, floorOfContent(contentOf(row), calls))
    } else if (row.type === 'attachment' && isRecord(row.attachment) && row.attachment.type === 'hook_additional_context') {
      const content = row.attachment.content
      const texts = Array.isArray(content) ? content.filter((item): item is string => typeof item === 'string') : typeof content === 'string' ? [content] : []
      floor = Math.max(floor, ...texts.map(floorOfSheetText))
    } else if (row.type === 'system' && typeof row.content === 'string') {
      floor = Math.max(floor, floorOfItem(row.content))
    }
  }
  return floor
}

/** The floor of a transcript's lines, one stored row as JSON each; a line that is not JSON names nothing. */
export function floorOfLines(lines: readonly string[]): number {
  const rows = lines.flatMap((line) => {
    try {
      const row: unknown = JSON.parse(line)
      return isRecord(row) ? [row] : []
    } catch {
      return []
    }
  })
  return floorOfRows(rows)
}

/**
 * The floor of the conversation the engine holds (`$.session.messages()`,
 * then its `{ as: 'api' }` form): the tool's own calls' results, and the
 * items the engine marks as a plugin's (a hook's context, a plugin's
 * prompt), on the human's and the system's side.
 */
export function floorOfMessages(
  messages: readonly { role: string; text: string; toolUses: readonly { tool: string; text?: string }[] }[],
  api: readonly { role: string; content: unknown }[],
): number {
  let floor = 0
  for (const message of messages) {
    for (const use of message.toolUses) {
      if (use.tool === SHEET_TOOL && use.text !== undefined) floor = Math.max(floor, floorOfResult(use.text))
    }
    if (message.role !== 'assistant') floor = Math.max(floor, floorOfItem(message.text))
  }
  const calls = sheetCalls(api.filter((message) => message.role === 'assistant').map((message) => message.content))
  for (const message of api) {
    if (message.role !== 'assistant') floor = Math.max(floor, floorOfContent(message.content, calls))
  }
  return floor
}

/**
 * The search for a transcript too large to read whole: the lines that can
 * hold an id the tool wrote (perl, one pass, lines printed as bytes), with
 * the tool's calls, which pair a result with its call. Its exit code is
 * grep's: 0 found, 1 none, 2 unreadable.
 */
export function floorSearchArgs(path: string): string[] {
  return [
    'perl',
    '-e',
    'binmode STDOUT; my $path = pop @ARGV; open(my $fh, "<:raw", $path) or exit 2; my $found = 0; while (my $line = <$fh>) { if ($line =~ /(?:Added|Revised|Withdrew) q[1-9]|<sheet-delivery>|\\[sheet v1\\]|"name":"mcp__sminos__AskUserQuestion"/) { print $line; $found = 1 } } exit($found ? 0 : 1);',
    '--',
    path,
  ]
}
