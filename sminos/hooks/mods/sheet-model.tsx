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
/**
 * The texts M2's step writes (sminos_sheet_step.py), which the floor reads
 * by their place, never by a scan: a question's text and its labels sit
 * inside them, and a label is written as it is, new lines and all.
 */
const START_HEAD = '[sheet v1] Your question sheet, after '
const FOOTER = /^New ids continue from q([1-9][0-9]{0,8})\.$/
const FORK_LINE =
  '[sheet v1] This conversation is a copy: its question sheet starts empty. Questions asked before the copy belong to the conversation it was copied from, and their answers will not come here; ask again what you still need.'
const LOST_LINE = "[sheet v1] The question sheet's record was not found, so the sheet starts empty; questions asked earlier are no longer open."
const EMPTY_START = / New ids start at q([1-9][0-9]{0,8})\.$/
const ENVELOPE_HEADS = ['[sheet v1] The human answered questions on your sheet.', '[sheet v1] The human dismissed questions on your sheet; no answer will come for them.']
const BLOCK_LINE = /^<sheet-delivery>(.*)<\/sheet-delivery>$/
const NOTICE = /^\[sheet v1\] Your earlier call \([^)\n]*\) did change the sheet: (.*)$/
/** The other notices, each one line (a question's text is a JSON string there): what the idle prompt may hold above its envelope. */
const OTHER_NOTICES = [
  /^\[sheet v1\] Your earlier call \([^)\n]*\) changed nothing; call again if you still need it\.$/,
  /^\[sheet v1\] The subagent .* \([^)\n]*\) ended with questions still open on your sheet: .*\. Their answers will come to you; withdraw what you no longer need\.$/,
]
/** A subagent's envelope opens with this line, before its head (M2's step). */
const SUBAGENT_OPENING = 'From the human, through the question tool, not from your coordinator: answers to questions you put on the sheet.'
/** A hook's context as a conversation holds it: the engine's own prefix (C0's P5), in a reminder or bare. */
const CONTEXT = /^(?:<system-reminder>\n)?[A-Za-z][A-Za-z.]* hook additional context: /
/** This plugin's prompt, as the engine prefixes it (an idle session's route). */
const PLUGIN_PROMPT = 'The sminos plugin sent a message:\n'
/** What the engine puts after a plugin's prompt, as the conversation keeps it (2.1.331; M4's rendering case). */
const PLUGIN_PROMPT_END = '\n\nThis is how Claude Code surfaces a prompt a plugin submits between turns'
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
 * one), read as one item by its place, never by a scan: a start's context
 * by its last line (`New ids continue from q<n>.`); the fork's and the lost
 * record's line by its own suffix (`New ids start at q<n>.`), those two
 * lines alone; an envelope's block, its last line; a late outcome's notice,
 * its first. The New ids sentence names the next id, so the floor it gives
 * is n − 1. A question's text or a label quoting any of these, new lines
 * and all, names nothing. A text that joins the sheet's item behind
 * another's is not read: a miss, never an id invented. 0 for none.
 */
export function floorOfSheetText(text: string): number {
  const all = text.replace(/\n<\/system-reminder>\s*$/, '').replace(/\s+$/, '').split('\n')
  // This plugin's idle prompt puts the notices waiting above its envelope, each a line and a blank one after it
  // (I9): each is read as the item it is, and the envelope below them as its own.
  let floor = 0
  let at = 0
  while (at < all.length - 2 && all[at + 1] === '' && (NOTICE.test(all[at] ?? '') || OTHER_NOTICES.some((re) => re.test(all[at] ?? '')))) {
    floor = Math.max(floor, floorOfItemText(all[at] as string))
    at += 2
  }
  return Math.max(floor, floorOfItemText(all.slice(at).join('\n')))
}

/** The floor of one item the sheet put there, read by its place (`floorOfSheetText`). */
function floorOfItemText(text: string): number {
  const lines = text.split('\n')
  const first = lines[0] ?? ''
  const last = lines[lines.length - 1] ?? ''
  if (first.startsWith(START_HEAD)) {
    const footer = FOOTER.exec(last)
    return lines.length > 1 && footer !== null ? highest([Number(footer[1]) - 1]) : 0
  }
  for (const line of [FORK_LINE, LOST_LINE]) {
    if (lines.length === 1 && first.startsWith(line)) {
      const suffix = EMPTY_START.exec(first)
      return suffix !== null && first.slice(line.length) === suffix[0] ? highest([Number(suffix[1]) - 1]) : 0
    }
  }
  const head = first === SUBAGENT_OPENING ? (lines[1] ?? '') : first
  if (ENVELOPE_HEADS.some((envelope) => head.startsWith(envelope))) {
    const block = BLOCK_LINE.exec(last)
    return lines.length > 1 && block !== null ? highest(blockIds(block[1] as string)) : 0
  }
  const notice = NOTICE.exec(first)
  return notice !== null ? floorOfResult(notice[1] as string) : 0
}

/** The ids an envelope's block names: answered and dismissed. */
function blockIds(body: string): number[] {
  try {
    const block: unknown = JSON.parse(body)
    if (isRecord(block) && block.v === 1 && Array.isArray(block.answered) && Array.isArray(block.dismissed)) {
      return [...block.answered.map((a) => (isRecord(a) ? a.id : undefined)), ...block.dismissed].flatMap((id) => (typeof id === 'string' ? idsIn(id) : []))
    }
  } catch {
    // A block that is not JSON names nothing.
  }
  return []
}

/**
 * The text a conversation's item carries when the engine marks it as one a
 * plugin put there: a hook's context (behind the engine's prefix), or this
 * plugin's prompt. Anything else (the human's words, a tool's output, the
 * model's) is no sheet's text: undefined.
 */
export function sheetTextOf(text: string): string | undefined {
  if (CONTEXT.test(text)) return text.replace(CONTEXT, '')
  if (text.startsWith(PLUGIN_PROMPT)) {
    const own = text.slice(PLUGIN_PROMPT.length)
    const end = own.lastIndexOf(PLUGIN_PROMPT_END)
    return end === -1 ? own : own.slice(0, end)
  }
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
 * The search for a transcript too large to read whole (I10), printing
 * compact evidence, never the rows: one line `{"floor":<n>}`, the floor
 * `floorOfLines` gives over the same rows. The pass reads the lines that can
 * hold an id the tool wrote (and the tool's calls, which pair a result with
 * its call), decodes them, and applies the floor's rules as `floorOfRows`
 * does: the tool's results by their first line, the sheet's texts by their
 * place (`floorOfSheetText`, `sheetTextOf`), a block's ids by its JSON. The
 * output is a few bytes whatever the history holds, so no cut can make the
 * floor unknown. Perl (JSON::PP and B are core; JSON::XS where the host has
 * it, for speed), one pass; its exit code is grep's: 0 found, 1 none, 2
 * unreadable. Its rules are the TypeScript ones written again: a test holds
 * the two to the same floor over every form they read. A row is decoded as
 * the TypeScript reader decodes it: its bytes as UTF-8 (a malformed sequence
 * U+FFFD), and a lone surrogate's escape, which JSON.parse keeps and perl's
 * decoders refuse, read as U+FFFD (no rule of the floor tells the two apart),
 * so no row that carries evidence is passed over and no floor reads low.
 */
export function floorSearchArgs(path: string): string[] {
  return ['perl', '-MJSON::PP', '-MB', '-MEncode', '-e', FLOOR_SEARCH, '--', path]
}

const FLOOR_SEARCH = [
  "binmode STDOUT; my $path = pop @ARGV; open(my $fh, \"<:raw\", $path) or exit 2;",
  "my $text = eval { require JSON::XS; JSON::XS->new } || JSON::PP->new;",
  "my $TOOL = \"mcp__sminos__AskUserQuestion\"; my $MAX = 999999999;",
  "my $WS = qr/[\\t\\n\\x0B\\f\\r \\x{A0}\\x{1680}\\x{2000}-\\x{200A}\\x{2028}\\x{2029}\\x{202F}\\x{205F}\\x{3000}\\x{FEFF}]/;",
  "my $DOT = qr/[^\\n\\r\\x{2028}\\x{2029}]/;",
  "my $START = \"[sheet v1] Your question sheet, after \";",
  "my $FORK = \"[sheet v1] This conversation is a copy: its question sheet starts empty. Questions asked before the copy belong to the conversation it was copied from, and their answers will not come here; ask again what you still need.\";",
  "my $LOST = \"[sheet v1] The question sheet's record was not found, so the sheet starts empty; questions asked earlier are no longer open.\";",
  "my @HEADS = (\"[sheet v1] The human answered questions on your sheet.\", \"[sheet v1] The human dismissed questions on your sheet; no answer will come for them.\");",
  "my $SUB = \"From the human, through the question tool, not from your coordinator: answers to questions you put on the sheet.\";",
  "my $PROMPT = \"The sminos plugin sent a message:\\n\"; my $PROMPT_END = \"\\n\\nThis is how Claude Code surfaces a prompt a plugin submits between turns\";",
  "my $NOTICE = qr/^\\[sheet v1\\] Your earlier call \\([^)\\n]*\\) did change the sheet: ($DOT*)\\z/;",
  "my @OTHER = (qr/^\\[sheet v1\\] Your earlier call \\([^)\\n]*\\) changed nothing; call again if you still need it\\.\\z/,",
  "  qr/^\\[sheet v1\\] The subagent $DOT* \\([^)\\n]*\\) ended with questions still open on your sheet: $DOT*\\. Their answers will come to you; withdraw what you no longer need\\.\\z/);",
  "sub starts { my ($s, $p) = @_; return substr($s, 0, length $p) eq $p }",
  "sub hi { my $m = 0; for (@_) { $m = $_ if $_ > $m } return $m < $MAX - 1 ? $m : $MAX - 1 }",
  "sub ids { my ($t) = @_; my @n; push @n, $1 while $t =~ /(?<![A-Za-z0-9_])q([1-9][0-9]{0,8})(?![A-Za-z0-9_])/g; return @n }",
  "sub of_result { my ($t) = @_; my ($first) = split /\\n/, $t, 2; $first //= \"\"; return $first =~ /^(?:Added|Revised|Withdrew) q[1-9]/ ? hi(ids($first)) : 0 }",
  "sub is_num1 { my ($v) = @_; return 0 if !defined $v || ref $v; my $f = B::svref_2object(\\$v)->FLAGS; return ($f & (B::SVf_IOK() | B::SVf_NOK())) && !($f & B::SVf_POK()) && $v == 1 }",
  "sub block_ids { my ($body) = @_; my $b = eval { $text->decode($body) }; return () unless ref $b eq \"HASH\" && is_num1($b->{v}) && ref $b->{answered} eq \"ARRAY\" && ref $b->{dismissed} eq \"ARRAY\";",
  "  return map { defined $_ && !ref $_ && !JSON::PP::is_bool($_) && B::svref_2object(\\$_)->FLAGS & B::SVf_POK() ? ids($_) : () } ((map { ref $_ eq \"HASH\" ? $_->{id} : undef } @{$b->{answered}}), @{$b->{dismissed}}) }",
  "sub of_item_text { my ($t) = @_; my @l = split /\\n/, $t, -1; @l = (\"\") unless @l; my ($first, $last) = ($l[0], $l[-1]);",
  "  if (starts($first, $START)) { return @l > 1 && $last =~ /^New ids continue from q([1-9][0-9]{0,8})\\.\\z/ ? hi($1 - 1) : 0 }",
  "  for my $line ($FORK, $LOST) { if (@l == 1 && starts($first, $line)) { return $first =~ / New ids start at q([1-9][0-9]{0,8})\\.\\z/ && substr($first, length $line) eq \" New ids start at q$1.\" ? hi($1 - 1) : 0 } }",
  "  my $head = $first eq $SUB ? ($l[1] // \"\") : $first;",
  "  if (grep { starts($head, $_) } @HEADS) { return @l > 1 && $last =~ /^<sheet-delivery>($DOT*)<\\/sheet-delivery>\\z/ ? hi(block_ids($1)) : 0 }",
  "  return $first =~ $NOTICE ? of_result($1) : 0 }",
  "sub of_sheet_text { my ($t) = @_; $t =~ s/\\n<\\/system-reminder>$WS*\\z//; $t =~ s/$WS+\\z//; my @a = split /\\n/, $t, -1; @a = (\"\") unless @a; my ($f, $at) = (0, 0);",
  "  while ($at < @a - 2 && $a[$at + 1] eq \"\" && ($a[$at] =~ $NOTICE || grep { $a[$at] =~ $_ } @OTHER)) { my $n = of_item_text($a[$at]); $f = $n if $n > $f; $at += 2 }",
  "  my $n = of_item_text(join \"\\n\", @a[$at .. $#a]); return $n > $f ? $n : $f }",
  "sub own_text { my ($t) = @_; return $t if $t =~ s/^(?:<system-reminder>\\n)?[A-Za-z][A-Za-z.]* hook additional context: //;",
  "  if (starts($t, $PROMPT)) { my $o = substr($t, length $PROMPT); my $e = rindex($o, $PROMPT_END); return $e < 0 ? $o : substr($o, 0, $e) } return undef }",
  "sub of_item { my ($t) = @_; my $o = own_text($t); return defined $o ? of_sheet_text($o) : 0 }",
  "sub texts { my ($c) = @_; return ($c) if defined $c && !ref $c && B::svref_2object(\\$c)->FLAGS & B::SVf_POK(); return () unless ref $c eq \"ARRAY\"; return map { ref $_ eq \"HASH\" && ($_->{type} // \"\") eq \"text\" && defined $_->{text} && !ref $_->{text} && B::svref_2object(\\$_->{text})->FLAGS & B::SVf_POK() ? ($_->{text}) : () } @$c }",
  "sub str { my ($v) = @_; return \"undefined\" unless defined $v; return $v ? \"true\" : \"false\" if JSON::PP::is_bool($v); return ref $v ? \"[object]\" : \"$v\" }",
  "my (%calls, %as_call, %as_other, $floor, $found); $floor = 0;",
  "sub up { $floor = $_[0] if $_[0] > $floor }",
  "sub chars { my $c = Encode::decode(\"UTF-8\", $_[0]); $c =~ s{(\\\\\\\\)|(\\\\u[dD][89abAB][0-9a-fA-F]{2}\\\\u[dD][c-fC-F][0-9a-fA-F]{2})|\\\\u[dD][89a-fA-F][0-9a-fA-F]{2}}{$1 // $2 // \"\\\\ufffd\"}ge if $c =~ /\\\\u[dD][89a-fA-F]/; return $c }",
  "while (my $line = <$fh>) { next unless $line =~ /(?:Added|Revised|Withdrew) q[1-9]|<sheet-delivery>|\\[sheet v1\\]|\"name\":\"mcp__sminos__AskUserQuestion\"/;",
  "  my $row = eval { $text->decode(chars($line)) }; next unless ref $row eq \"HASH\"; $found = 1; my $type = $row->{type} // \"\";",
  "  my $content = ref $row->{message} eq \"HASH\" ? $row->{message}{content} : undef;",
  "  if ($type eq \"assistant\") { if (ref $content eq \"ARRAY\") { for my $b (@$content) { $calls{str($b->{id})} = 1 if ref $b eq \"HASH\" && ($b->{type} // \"\") eq \"tool_use\" && defined $b->{name} && !ref $b->{name} && $b->{name} eq $TOOL } } }",
  "  elsif ($type eq \"user\") { up(of_item($_)) for texts($content);",
  "    if (ref $content eq \"ARRAY\") { for my $b (@$content) { next unless ref $b eq \"HASH\" && ($b->{type} // \"\") eq \"tool_result\"; my $id = str($b->{tool_use_id});",
  "      my $r = of_result(join \"\\n\", texts($b->{content})); $as_call{$id} = $r if $r > ($as_call{$id} // 0);",
  "      my $o = 0; if (ref $b->{content} eq \"ARRAY\") { for my $i (@{$b->{content}}) { next unless ref $i eq \"HASH\" && ($i->{type} // \"\") eq \"text\"; my $n = of_item(str($i->{text})); $o = $n if $n > $o } }",
  "      $as_other{$id} = $o if $o > ($as_other{$id} // 0) } } }",
  "  elsif ($type eq \"attachment\" && ref $row->{attachment} eq \"HASH\" && ($row->{attachment}{type} // \"\") eq \"hook_additional_context\") { my $c = $row->{attachment}{content};",
  "    my @t = ref $c eq \"ARRAY\" ? (grep { defined $_ && !ref $_ && B::svref_2object(\\$_)->FLAGS & B::SVf_POK() } @$c) : (defined $c && !ref $c && B::svref_2object(\\$c)->FLAGS & B::SVf_POK()) ? ($c) : (); up(of_sheet_text($_)) for @t }",
  "  elsif ($type eq \"system\" && defined $row->{content} && !ref $row->{content} && B::svref_2object(\\$row->{content})->FLAGS & B::SVf_POK()) { up(of_item($row->{content})) } }",
  "up($calls{$_} ? ($as_call{$_} // 0) : ($as_other{$_} // 0)) for keys %as_call, keys %as_other;",
  "print JSON::PP->new->canonical->encode({ floor => $floor + 0 }), \"\\n\"; exit($found ? 0 : 1);",
].join('\n')

/** The floor a search printed (`floorSearchArgs`): undefined for anything but its one line. */
export function floorOfSearch(stdout: string): number | undefined {
  try {
    const found: unknown = JSON.parse(stdout)
    return isRecord(found) && Number.isInteger(found.floor) && (found.floor as number) >= 0 && (found.floor as number) < ID_MAX ? (found.floor as number) : undefined
  } catch {
    return undefined
  }
}

// ------------------------------------------------------------------ delivery (I7's block, I9)

/** What a reader takes of a `<sheet-delivery>` block (I7): the keys it delivers and the ids it names. */
export type Block = { keys: string[]; answered: string[]; dismissed: string[]; more: boolean }

/** At most this many keys in one block: what one `delivered` line names (I7). */
const BLOCK_KEYS = 200

/**
 * The blocks a text holds: each line that is a whole `<sheet-delivery>…</sheet-delivery>`
 * of I7's shape (`v` 1, as many keys as answered and dismissed entries
 * together, at most 200). The block escapes `<`, `>` and `&`, so neither its
 * own closing tag nor a reminder's tag occurs inside it, and it is one line;
 * a prose line above it that quotes a tag is no block. A line that is not
 * one names nothing.
 */
export function blocksOf(text: string): Block[] {
  return blockLines(text).map(({ block }) => block)
}

/** Each block line of `text`, read, with its answered entries as they stand. */
function blockLines(text: string): { block: Block; entries: Record<string, unknown>[] }[] {
  const out: { block: Block; entries: Record<string, unknown>[] }[] = []
  for (const line of text.split('\n')) {
    const match = BLOCK_LINE.exec(line.replace(/\r$/, ''))
    if (match === null) continue
    try {
      const block: unknown = JSON.parse(match[1] as string)
      if (!isRecord(block) || block.v !== 1 || !Array.isArray(block.keys) || !Array.isArray(block.answered) || !Array.isArray(block.dismissed)) continue
      const keys = block.keys.filter((key): key is string => typeof key === 'string')
      const entries = block.answered.filter((a): a is Record<string, unknown> => isRecord(a) && typeof a.id === 'string')
      const answered = entries.map((a) => a.id as string)
      const dismissed = block.dismissed.filter((id): id is string => typeof id === 'string')
      if (keys.length !== block.keys.length || keys.length === 0 || keys.length > BLOCK_KEYS || keys.length !== answered.length + dismissed.length) continue
      out.push({ block: { keys, answered, dismissed, more: block.more === true }, entries })
    } catch {
      // A block that is not JSON names nothing.
    }
  }
  return out
}

/** Every key the blocks of `texts` name, each once, in order. */
export function keysIn(texts: readonly string[]): string[] {
  return [...new Set(texts.flatMap((text) => blocksOf(text).flatMap((block) => block.keys)))]
}

/** The plugin whose prompt and contexts the sheet sends: its rows are told by it. */
export const PLUGIN = 'sminos'

/**
 * Whether a row `session.append` hands is one the sheet's routes could have
 * put there (I9): of the main conversation, and either a context a plugin's
 * `tool.call` or `prompt.submit` hook attached, or this plugin's prompt. A
 * human's prompt that quotes an envelope, a steer, another tool's output: no.
 */
export function isRouteRow(e: { door: string; origin: unknown; agentId?: string }): boolean {
  if (e.agentId !== undefined || !isRecord(e.origin) || e.origin.kind !== 'plugin') return false
  if (e.door === 'hook-context') return e.origin.event === 'tool.call' || e.origin.event === 'prompt.submit'
  return e.door === 'prompt' && e.origin.name === PLUGIN
}

/** The texts of a content as a request carries it: a string, its text blocks, and the text inside its tool results. */
export function contentTexts(content: unknown): string[] {
  if (typeof content === 'string') return [content]
  if (!Array.isArray(content)) return []
  return content.flatMap((block) => {
    if (!isRecord(block)) return []
    if (block.type === 'text' && typeof block.text === 'string') return [block.text]
    if (block.type === 'tool_result') return contentTexts(block.content)
    return []
  })
}

/**
 * A start's search (I9) of the transcript at `path` for the envelopes the
 * routes delivered, printing compact evidence, never the rows: for each
 * stored row of a route's kind that holds a valid block (I7's shape, as
 * `blocksOf` reads it), a line `{"kind":…,"keys":[…]}`, newest row first,
 * each key once (at its newest row). A row of a route's kind: an attachment
 * of type `hook_additional_context` whose `hookName` is `tool.call` or
 * `prompt.submit`, or a user row whose origin is this plugin's prompt, its
 * keys read from the content the model was given only (never the
 * submission's `pluginPrompt` record, which a hook beneath does not
 * rewrite); told by what the stored row holds, which says less of authorship than the live
 * event did (U13). Only lines holding the block's tag are decoded. Perl
 * (JSON::PP is core), one pass; its exit code is grep's: 0 found, 1 none,
 * 2 unreadable. Given `only` (the keys a start's `before` lists, when it
 * lists every key pending), it prints those keys alone, at most 200: no cut
 * can drop one. Otherwise newest first, so an output cut at its bound keeps
 * the rows most likely still pending and loses only the oldest.
 */
export function landedSearchArgs(path: string, only: readonly string[] = []): string[] {
  return ['perl', '-MJSON::PP', '-e', LANDED_SEARCH, '--', path, ...only]
}

const LANDED_SEARCH = [
  'binmode STDOUT; my $path = shift @ARGV; my %only = map { $_ => 1 } @ARGV; open(my $fh, "<:raw", $path) or exit 2;',
  'my $json = JSON::PP->new->utf8; my $text = JSON::PP->new->utf8(0); my @rows;',
  'sub strs { my ($c) = @_; return ref $c eq "ARRAY" ? (grep { defined $_ && !ref $_ } @$c) : (defined $c && !ref $c) ? ($c) : () }',
  'sub texts { my ($c) = @_; return ($c) if defined $c && !ref $c; return () unless ref $c eq "ARRAY";',
  '  return map { ref $_ ne "HASH" ? () : ($_->{type} // "") eq "text" && defined $_->{text} && !ref $_->{text} ? ($_->{text}) : ($_->{type} // "") eq "tool_result" ? texts($_->{content}) : () } @$c }',
  'sub keys_of { my @keys; for my $t (@_) { for my $l (split /\\n/, $t) { $l =~ s/\\r$//; next unless $l =~ /^<sheet-delivery>(.*)<\\/sheet-delivery>$/;',
  '  my $b = eval { $text->decode($1) }; next unless ref $b eq "HASH" && defined $b->{v} && !ref $b->{v} && $b->{v} eq "1" && ref $b->{keys} eq "ARRAY" && ref $b->{answered} eq "ARRAY" && ref $b->{dismissed} eq "ARRAY";',
  '  my @k = grep { defined $_ && !ref $_ } @{$b->{keys}}; my $n = (grep { ref $_ eq "HASH" && defined $_->{id} && !ref $_->{id} } @{$b->{answered}}) + (grep { defined $_ && !ref $_ } @{$b->{dismissed}});',
  '  next unless @k == @{$b->{keys}} && @k >= 1 && @k <= 200 && @k == $n; push @keys, @k } } return @keys }',
  'while (my $line = <$fh>) { next if index($line, "<sheet-delivery>") < 0; my $row = eval { $json->decode($line) }; next unless ref $row eq "HASH"; my ($kind, @t); my $type = $row->{type} // "";',
  '  if ($type eq "attachment" && ref $row->{attachment} eq "HASH") { my $a = $row->{attachment}; next unless ($a->{type} // "") eq "hook_additional_context"; $kind = $a->{hookName} // ""; next unless $kind eq "tool.call" || $kind eq "prompt.submit"; @t = strs($a->{content}) }',
  '  elsif ($type eq "user" && ref $row->{origin} eq "HASH" && ($row->{origin}{kind} // "") eq "plugin" && ($row->{origin}{name} // "") eq "sminos") { $kind = "plugin"; @t = ref $row->{message} eq "HASH" ? texts($row->{message}{content}) : () }',
  '  else { next } my @k = grep { !%only || $only{$_} } keys_of(@t); push @rows, [$kind, [@k]] if @k }',
  'my $out = JSON::PP->new->utf8->canonical; my %seen; for my $r (reverse @rows) { my @k = grep { !$seen{$_}++ } @{$r->[1]}; print $out->encode({ kind => $r->[0], keys => [@k] }), "\\n" if @k } exit(@rows ? 0 : 1);',
].join('\n')

/**
 * The keys a start's search found: each line of its compact evidence that
 * is a row's kind and its keys (anything else, a line the cut ended inside
 * included, names none).
 */
export function searchedKeys(lines: readonly string[]): string[] {
  const kinds = new Set(['tool.call', 'prompt.submit', 'plugin'])
  return [
    ...new Set(
      lines.flatMap((line) => {
        try {
          const found: unknown = JSON.parse(line)
          if (!isRecord(found) || typeof found.kind !== 'string' || !kinds.has(found.kind) || !Array.isArray(found.keys)) return []
          const keys = found.keys.filter((key): key is string => typeof key === 'string' && key !== '')
          return keys.length === found.keys.length ? keys : []
        } catch {
          return []
        }
      }),
    ),
  ]
}

/**
 * A route's texts as the conversation the model holds renders it (the api
 * form, which keeps no origin; 2.1.331, M4's probe of each route): a hook's
 * context of `tool.call` or `prompt.submit` in the engine's reminder,
 * `<system-reminder>\n<hook> hook additional context: <entries>\n</system-reminder>`
 * (the result route's appended to the tool result's own text after its
 * output, the prompt route's a text block of its own), the same prefix bare
 * at an item's start (a stored system row), or this plugin's prompt behind
 * its frame, a text block of its own. A human's prompt or a tool's output
 * that quotes a block bare is no route's.
 */
const ROUTE_CONTEXT = /^(?:tool\.call|prompt\.submit) hook additional context: /
const ROUTE_REMINDER = /<system-reminder>\n(?:tool\.call|prompt\.submit) hook additional context: ([\s\S]*?)\n<\/system-reminder>/g
function routeTexts(text: string): string[] {
  if (text.startsWith(PLUGIN_PROMPT)) return [sheetTextOf(text) as string]
  if (ROUTE_CONTEXT.test(text)) return [text.replace(ROUTE_CONTEXT, '')]
  return [...text.matchAll(ROUTE_REMINDER)].map((match) => match[1] as string)
}

/** The texts routes put in the conversation the model holds (`$.session.messages({ as: 'api' })`), on its human's side. */
function routeItems(api: readonly { role: string; content: unknown }[]): string[] {
  return api
    .filter((message) => message.role !== 'assistant')
    .flatMap((message) => [...textsOf(message.content), ...blocksIn(message.content, 'tool_result').flatMap((block) => textsOf(block.content))])
    .flatMap(routeTexts)
}

/** The keys the conversation the model holds names in a block a route put there. */
export function heldKeys(api: readonly { role: string; content: unknown }[]): Set<string> {
  return new Set(keysIn(routeItems(api)))
}

/**
 * The notice of a subagent that stopped with questions open on the sheet
 * (I9, E14): its name and id, each question's first 200 characters as a
 * JSON string.
 */
export function endedNotice(agent: { agentId: string; name: string }, questions: readonly { id: string; question: string }[]): string {
  const listed = questions.map((q) => `${q.id} ${JSON.stringify([...q.question].slice(0, 200).join(''))}`).join(', ')
  return `[sheet v1] The subagent ${[...agent.name].slice(0, 200).join('')} (${agent.agentId}) ended with questions still open on your sheet: ${listed}. Their answers will come to you; withdraw what you no longer need.`
}

// ------------------------------------------------------------------ the terminal's drawing (M5; §8.3, §8.1)

/** A stored call's first line read (I6's grammar, `grammar/result.md`), as `result.examples.json` holds it parsed. */
export type Parsed =
  | { form: 'sentences'; added: { id: string; entry?: number }[]; revised: { id: string; entry?: number; revision: number }[]; withdrew: string[] }
  | { form: 'nothing' }
  | { form: 'unknown' }

const ITEM = 'q[0-9]+(?: \\(entry [0-9]+\\))?'
const RITEM = 'q[0-9]+ \\((?:entry [0-9]+, )?revision [0-9]+\\)'
const WITHDREW = 'Withdrew q[0-9]+(?:, q[0-9]+)*\\.'
/** The first line, whole: the published pattern, in parts. */
const FIRST_LINE = new RegExp(
  `^(?:Nothing done\\.|Outcome not known yet\\.|Added ${ITEM}(?:, ${ITEM})*\\.(?: Revised ${RITEM}(?:, ${RITEM})*\\.)?(?: ${WITHDREW})?|Revised ${RITEM}(?:, ${RITEM})*\\.(?: ${WITHDREW})?|${WITHDREW})$`,
)

/** A stored call's result read by its first line; undefined for a text that is none of I6's three (a denial, today's form). */
export function parseResult(text: string): Parsed | undefined {
  const first = text.split('\n', 1)[0] ?? ''
  if (!FIRST_LINE.test(first)) return undefined
  if (first === 'Nothing done.') return { form: 'nothing' }
  if (first === 'Outcome not known yet.') return { form: 'unknown' }
  const sentence = (verb: string) => /^(?:[^.]|\.(?! ))*/.exec(first.slice(first.indexOf(`${verb} `) + verb.length + 1))?.[0] ?? ''
  const added = first.includes('Added ')
    ? [...sentence('Added').matchAll(/(q[0-9]+)(?: \(entry ([0-9]+)\))?/g)].map((m) => ({ id: m[1] as string, ...(m[2] !== undefined && { entry: Number(m[2]) }) }))
    : []
  const revised = first.includes('Revised ')
    ? [...sentence('Revised').matchAll(/(q[0-9]+) \((?:entry ([0-9]+), )?revision ([0-9]+)\)/g)].map((m) => ({
        id: m[1] as string,
        ...(m[2] !== undefined && { entry: Number(m[2]) }),
        revision: Number(m[3]),
      }))
    : []
  const withdrew = first.includes('Withdrew ') ? [...sentence('Withdrew').matchAll(/q[0-9]+/g)].map((m) => m[0]) : []
  return { form: 'sentences', added, revised, withdrew }
}

/**
 * A sentence's end (the composite's writer's ruling of 2026-11-24, which C3
 * holds too): a run of `.`, `?`, `!` with its closing quotes or brackets,
 * where whitespace or the end follows (so `v1.2` ends none); or a run of the
 * full-width `。？！` with theirs, whatever follows.
 */
const SENTENCE_END = /(?:[.?!]+["'”’)\]]*(?=\s|$)|[。？！]+["'”’)\]」』）]*)/g

/**
 * A question's line (§8.1, which the app draws alike): its first sentence that
 * asks (its ending run holds `?` or `？`), else its first sentence, so a
 * question that opens with a statement is not shown as its preamble. A line
 * break ends a sentence too; a line's rest after its last end is a sentence
 * that does not ask.
 */
export function questionSentence(question: string): string {
  const sentences: { text: string; asks: boolean }[] = []
  for (const line of question.split(/\r?\n/)) {
    let from = 0
    for (const end of line.matchAll(SENTENCE_END)) {
      const to = (end.index ?? 0) + end[0].length
      sentences.push({ text: line.slice(from, to).trim(), asks: /[?？]/.test(end[0]) })
      from = to
    }
    sentences.push({ text: line.slice(from).trim(), asks: false })
  }
  const kept = sentences.filter((sentence) => sentence.text !== '')
  return (kept.find((sentence) => sentence.asks) ?? kept[0])?.text ?? ''
}

/** A stored result's text as a row hook is given it: a string, its text blocks joined, or an MCP result's content. */
export function resultTextOf(output: unknown): string {
  if (typeof output === 'string') return output
  if (Array.isArray(output)) return textsOf(output).join('\n')
  if (isRecord(output) && Array.isArray(output.content)) return textsOf(output.content).join('\n')
  return ''
}

/** A stored call's form, by its input (I11): `ask` or `withdraw` is the sheet's; `questions` today's. */
export function isSheetCall(input: unknown): input is SheetInput {
  return isRecord(input) && !('questions' in input) && ('ask' in input || 'withdraw' in input)
}

/** A surface, as the view carries it and the registrations read between steps give it. */
export type Surface = { name: string; url: string; reach: string }

/**
 * The line above the prompt (§8.3): how many questions are open and the
 * surface's link to this session's sheet, or how to read them when no
 * surface can show them; how many answers owed across a stop leave with the
 * next message. None when neither.
 */
export function bandLine(counts: { open: number; owed: number }, surface: Surface | null, session: string): string | undefined {
  const parts: string[] = []
  if (counts.open > 0) {
    parts.push(`${counts.open} open ${counts.open === 1 ? 'question' : 'questions'}`)
    parts.push(surface !== null ? `${surface.url}/s/${session}` : `the page is unreachable: sminos sheet show ${session.slice(0, 8)}`)
  }
  if (counts.owed > 0) {
    parts.push(`${counts.owed} ${counts.owed === 1 ? 'answer goes' : 'answers go'} with your next message`)
  }
  return parts.length === 0 ? undefined : parts.join(' · ')
}

/** A surface is alive this long after its heartbeat (I8). */
const HEARTBEAT_MS = 30_000
const SURFACE_NAME = /^[A-Za-z0-9._-]{1,64}$/
const HEARTBEAT_AT = /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$/

/**
 * The surface the band links between steps (M5): of the registrations read
 * from `surfaces/`, the first alive by age alone whose reach suits, read as
 * the step reads them (I8, "Reading the registrations"): only names ending
 * in `.json`; a file half-written, unparsable or of another shape not alive;
 * `mawsd` first, then the others by name; one trailing slash off the url. A
 * step's view is the full rule (a running pid too).
 */
export function surfaceOf(files: readonly { file: string; text: string }[], now: number, remote: boolean): Surface | null {
  const alive: { name: string; file: string; surface: Surface }[] = []
  for (const { file, text } of files) {
    if (!file.endsWith('.json')) continue
    let r: unknown
    try {
      r = JSON.parse(text)
    } catch {
      continue
    }
    if (
      !isRecord(r) ||
      r.v !== 1 ||
      typeof r.name !== 'string' ||
      !SURFACE_NAME.test(r.name) ||
      typeof r.pid !== 'number' ||
      !Number.isInteger(r.pid) ||
      r.pid < 1 ||
      typeof r.url !== 'string' ||
      codePoints(r.url) < 1 ||
      codePoints(r.url) > 2000 ||
      (r.reach !== 'local' && r.reach !== 'remote') ||
      typeof r.heartbeatAt !== 'string' ||
      !HEARTBEAT_AT.test(r.heartbeatAt)
    ) {
      continue
    }
    const at = Date.parse(r.heartbeatAt)
    // A well-shaped date that is no date (the 30th of February) reads back as another: not alive.
    if (Number.isNaN(at) || new Date(at).toISOString() !== r.heartbeatAt || now - at > HEARTBEAT_MS) continue
    const url = r.url.endsWith('/') && r.url.length > 1 ? r.url.slice(0, -1) : r.url
    alive.push({ name: r.name, file, surface: { name: r.name, url, reach: r.reach } })
  }
  const order = (a: { name: string; file: string }) => [a.name !== 'mawsd' ? 1 : 0, a.name, a.file] as const
  alive.sort((a, b) => {
    const [x, y] = [order(a), order(b)]
    return x[0] - y[0] || (x[1] < y[1] ? -1 : x[1] > y[1] ? 1 : 0) || (x[2] < y[2] ? -1 : x[2] > y[2] ? 1 : 0)
  })
  return alive.find((a) => a.surface.reach === 'remote' || !remote)?.surface ?? null
}

/** What a delivery's block says of a question: answered at a revision with places and a text, or dismissed. */
export type Delivered = { how: 'answered'; revision: number; picks: number[]; text: string } | { how: 'dismissed' }

/** The outcomes the blocks of `texts` deliver, by question id (a later block's over an earlier one's). */
export function deliveredIn(texts: readonly string[]): Map<string, Delivered> {
  const out = new Map<string, Delivered>()
  for (const text of texts) {
    for (const { block, entries } of blockLines(text)) {
      for (const entry of entries) {
        const picks = Array.isArray(entry.picks) ? entry.picks.filter((p): p is number => typeof p === 'number' && Number.isInteger(p)) : []
        out.set(entry.id as string, {
          how: 'answered',
          revision: typeof entry.revision === 'number' ? entry.revision : 1,
          picks,
          text: typeof entry.text === 'string' ? entry.text : '',
        })
      }
      block.dismissed.forEach((id) => out.set(id, { how: 'dismissed' }))
    }
  }
  return out
}

/**
 * The outcomes the conversation the model holds was delivered, for drawing
 * only (M5): in blocks a route put there, and in a steer, a user row whose
 * text is an envelope (X3's steer form, `examples/terminal/steer.txt`).
 * Landing reads routes' blocks alone (`heldKeys`): a steer settles nothing.
 */
export function deliveriesHeld(api: readonly { role: string; content: unknown }[]): Map<string, Delivered> {
  return deliveredIn(api.flatMap(drawnTexts))
}

/** A message's texts that carry blocks for drawing, in its content's order, so a question's newest block wins. */
function drawnTexts(message: { role: string; content: unknown }): string[] {
  if (message.role === 'assistant') return []
  const items: unknown[] = typeof message.content === 'string' ? [message.content] : Array.isArray(message.content) ? message.content : []
  return items.flatMap((item) => {
    const text = typeof item === 'string' ? item : isRecord(item) && item.type === 'text' && typeof item.text === 'string' ? item.text : undefined
    if (text !== undefined) {
      const isSteer = message.role === 'user' && ENVELOPE_HEADS.some((head) => text.startsWith(head))
      return [...routeTexts(text), ...(isSteer ? [text] : [])]
    }
    return isRecord(item) && item.type === 'tool_result' ? textsOf(item.content).flatMap(routeTexts) : []
  })
}

/** What a row reads of the sheet beyond its own call: the view while the record lives, and the deliveries' blocks. */
export type RowFacts = {
  view?: { open: readonly { id: string; revision: number }[]; closed: Readonly<Record<string, { how: string; revision: number; receipt?: string }>> }
  delivered: ReadonlyMap<string, Delivered>
}

/** The receipt's text of an answer: one line, its first 200 characters at most. */
const receiptText = (text: string) => [...text.replace(/\s+/g, ' ').trim()].slice(0, 200).join('')

/**
 * A call's row (§8.3, §8.1; I11): from its input and its result's first line
 * alone, one line a question it added or revised, in its entries' order
 * (`q7 Auth method — <its line>`), then one for each withdrawal it made. A
 * question that has left the sheet reads its receipt in the line's place
 * (`→ OAuth`, `· Dismissed`, `· Withdrawn`), and one a later call revised
 * `· Revised below`: from the view while the record holds it, else from the
 * blocks the conversation holds, the labels read by place from this call's
 * own input. A question neither knows is its line bare.
 */
export function rowLines(input: SheetInput, parsed: Parsed, facts: RowFacts): string[] {
  if (parsed.form === 'nothing') return ['Nothing done.']
  if (parsed.form === 'unknown') return ['outcome not known']
  const entries = input.ask ?? []
  // Each id to its entry: by the entry's place where the result names it, else in the entries' order (nothing refused).
  const placed: { id: string; entry?: Entry; revision: number }[] = []
  const isNamed = [...parsed.added, ...parsed.revised].some((item) => item.entry !== undefined)
  if (isNamed) {
    const items = [...parsed.added.map((a) => ({ ...a, revision: 1 })), ...parsed.revised].sort((a, b) => (a.entry ?? 0) - (b.entry ?? 0))
    items.forEach((item) => placed.push({ id: item.id, entry: item.entry === undefined ? undefined : entries[item.entry - 1], revision: item.revision }))
  } else {
    // Nothing refused: an entry without an id is the next added, one with an id is that id revised.
    const added = parsed.added.map((a) => ({ id: a.id, revision: 1 }))
    const revised = [...parsed.revised]
    for (const entry of entries) {
      const at = entry.id === undefined ? -1 : revised.findIndex((r) => r.id === entry.id)
      const item = entry.id === undefined ? added.shift() : at === -1 ? undefined : revised.splice(at, 1)[0]
      if (item !== undefined) placed.push({ id: item.id, entry, revision: item.revision })
    }
    // What no entry accounts for (an input that does not match its result) is its id alone.
    ;[...added, ...revised].forEach((item) => placed.push({ id: item.id, revision: item.revision }))
  }
  const lines = placed.map(({ id, entry, revision }) => {
    const name = entry?.header === undefined ? id : `${id} ${entry.header}`
    const open = entry === undefined ? name : `${name} — ${questionSentence(entry.question)}`
    const view = facts.view
    const isOpen = view?.open.find((q) => q.id === id)
    const closed = view?.closed[id]
    if (isOpen !== undefined) return isOpen.revision > revision ? `${name} · Revised below` : open
    if (closed !== undefined) {
      if (closed.revision > revision) return `${name} · Revised below`
      if (closed.how === 'answered') return `${name} → ${receiptText(closed.receipt ?? '')}`
      return `${name} · ${closed.how === 'dismissed' ? 'Dismissed' : 'Withdrawn'}`
    }
    const delivered = facts.delivered.get(id)
    if (delivered === undefined) return open
    if (delivered.how === 'dismissed') return `${name} · Dismissed`
    if (delivered.revision > revision) return `${name} · Revised below`
    if (delivered.revision < revision) return open
    const labels = delivered.picks.map((place) => entry?.options?.[place - 1]?.label ?? `option ${place}`)
    return `${name} → ${labels.length > 0 ? receiptText(labels.join(', ')) : receiptText([...delivered.text].slice(0, 80).join(''))}`
  })
  return [...lines, ...parsed.withdrew.map((id) => `${id} · Withdrawn`)]
}
