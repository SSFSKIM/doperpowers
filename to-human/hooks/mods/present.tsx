import type { EngineInterface, On, TurnCompleteInput } from 'claude-code'

import type { PresentRun, Presented, PresentedRow } from '../../types/to-human'
import { isMessageToolOn, readField } from './message'
import { isNotifying } from './notify'

/**
 * The present tool: a session's panel, one HTML page per session that its
 * human reads in a browser, served by the panel server (panel/server.py), for
 * what they must read closely and plain text carries poorly. The call returns
 * at once; a fork of the session, which holds the whole conversation, edits
 * the panel's draft in the background, and the server publishes it when the
 * fork has ended well. The human is shown the address by the call's row in
 * the report and a notification; the session learns the outcome as hook
 * context at its next tool call or prompt, without being woken (design and
 * contracts: docs/doperpowers/specs/2026-11-13-present-panel-design.md).
 *
 * The fork is held to reading and to writing its draft by the guard here: a
 * fork goes on with the session's task when nothing stops it, and an
 * unguarded write under the configuration directory raises a permission
 * dialog in the session's pane. The plugin's hooks run on the calls of a
 * fork it spawned, all but the one registration whose frame made the spawn,
 * so the guard is registered apart from the handler (trial 2).
 */
export const PRESENT_TOOL = 'mcp__to-human__present'

// When to use it is the rule's business (the style), as for the message tool.
export const DESCRIPTION = "Put something on this session's panel for the human; a fork of you writes it in the background."

export const INPUT_SCHEMA = {
  type: 'object',
  properties: {
    brief: {
      type: 'string',
      description: 'What to put on the panel or change on it. The fork has the conversation up to this call.',
    },
  },
  required: ['brief'],
}

export const STARTED = (address: string) =>
  `Writing the panel in the background: ${address} The human is shown the address in their report when it is written. You are not woken for it: you learn the outcome at your next step or prompt, so if a decision is due, ask now and point at the panel.`
/** Appended to STARTED and FINISHED when the panel opens only on this machine. */
export const LOCAL_ONLY = ' This address opens only on the machine this session runs on: its panel server is not exposed on the tailnet.'
export const FINISHED = (address: string, said: string) => `The panel is written and the human has been shown its address: ${address}\n${said}`
/** Appended to FINISHED when publishing cut something. */
export const REMOVED = (what: string[]) => ` Publishing cut from the page what a panel may not hold: ${what.join(', ')}.`
/** Appended to FINISHED when the human first looked at the page this update replaced while it was rewritten. */
export const LOOKED_MEANWHILE =
  ' The human first opened the page while it was being rewritten, so this update carries no notes for what it changed: tell them what changed if it matters.'
export const FAILED = (address: string, why: string) =>
  `The panel was not written (${why}); ${address} holds what it held before, and the human has been told. Call present again to retry.`
export const BUSY = (address: string) =>
  `The panel is being written now: ${address} Go on with your work: you are told at your next step once it is written, and can call present again then with what to change.`
export const PLAN_REFUSAL = 'present writes a file, which plan mode does not allow: call it once the plan is approved.'
export const SUBAGENT_REFUSAL =
  'present is for the main conversation; a subagent reaches the human through the session that dispatched it: put this in your report.'
export const EMPTY_REFUSAL = 'present needs its brief: what to put on the panel or change on it.'
export const GUARD_REFUSAL =
  "Refused: this fork writes the panel and nothing else; that step is the session's, and the session takes it. Go on editing the draft, and end with your two-line reply once it holds the panel."
/** A call refused while the run's record cannot be read back: whether a fork still writes the panel is unknown. */
export const RECORD_UNREAD = "present could not read back the panel's record, so it cannot tell whether a fork still writes it: call it again shortly."
/** Why a run is closed whose fork ended while no module of this plugin listened (a reload between). */
export const NOT_HEARD = 'its end was not heard'

/** What the fork is described as in the agent strip, `/tasks` and `$.agent.list()`. */
export const FORK_DESCRIPTION = 'panel'

/** What `server.py open-panel` prints. */
export type OpenPanel = {
  address: string
  reach: 'tailnet' | 'local'
  dir: string
  draft: string
  guide: string
  update: number
  isNew: boolean
  locale: 'en' | 'ko'
  seen: 'never' | 'current' | 'stale'
  checked: string[]
}

/** What `server.py publish` prints. */
type Published = { published: boolean; address: string; reach: 'tailnet' | 'local'; written: number | null; removed: string[]; lookedMeanwhile: boolean }

const SEEN = {
  never: 'The human has not looked at the panel: it owes them no notes.',
  current: 'The human has looked at the panel since its last update: they have seen what it holds.',
  stale: 'The human has not looked at the panel since its last update: what that update wrote, they have not seen.',
} as const

/**
 * The fork's prompt: the standing text with its slots filled from the
 * OpenPanel, then the brief. Its wording is authored agent behaviour, tested
 * by the live check's pages (tests/mods/live-present-check.py).
 */
export const STANDING_PROMPT = (open: OpenPanel, brief: string) => {
  const isKorean = open.locale === 'ko'
  const checked = open.checked.length === 0 ? '' : ` Delete these notes, which they checked off, with every mark of their ids: ${open.checked.join(', ')}.`
  return [
    "You are a fork of this session, started by its `present` call to write the session's panel for the human: one HTML page, the richer form of a message, which they read closely in a browser. You are not the session: do not continue its task, answer its human, or call `present`. The session goes on with its own work; yours is the panel, and it ends when the panel is written.",
    `Edit ${open.draft}: it is the panel as it stands${open.isNew ? ', a starter with nothing on it yet' : ''}, and it is published when you end. This is update ${open.update}. Write it in ${isKorean ? 'Korean' : 'English'}.`,
    `Compose it for what this content needs; no section or order is required. Write content only, on the base the page links: ${open.guide} lists its blocks and the markup of a note. Add your own inline styles or SVG where the base lacks something; nothing loads from another site. Plain and legible is the care expected. No credential goes on the page.`,
    `Keep it to about three screens: ${isKorean ? '1,800 to 2,700 characters' : '600 to 900 words'} of running text, not counting notes, labels inside figures, or what is folded at the bottom. Select and show (a diagram, a comparison, a table) instead of transcribing the conversation.`,
    'The body states what holds now; edit it in place. What is new or awaits the human goes at the top. What is older and settled is cut once it no longer serves, or moved to the bottom and folded behind a one-line summary. An explanation keeps its own order.',
    `${SEEN[open.seen]}\nWhere an edit changes what they have seen, write one note for that change, saying what changed and why, at the first place it shows, and mark each other place it changed with the same id; ids u${open.update}-1, u${open.update}-2, and so on, one per change. A note still on the page whose statement you change again is replaced by one note carrying both steps.${checked}`,
    `You can read anything and write only ${open.draft}. Reply with two lines: what the panel now holds, and what changed.`,
    `Brief: ${brief}`,
  ].join('\n\n')
}

/** The first line of a call's brief that says something, as its row reads it, whole or streaming; '' before any. */
export function briefLine(input: unknown): string {
  const brief = readField(input, 'brief')?.text ?? ''
  const line = brief.split('\n').find((l) => l.trim() !== '')?.trim() ?? ''
  return line.length > 120 ? `${line.slice(0, 119)}…` : line
}

const ADDRESS = /https?:\/\/\S+?\/[0-9a-f]{8}\//

/**
 * What a call's row shows: the run's state by the call's id, or, with none
 * (a resumed session: `$.state` ends with the process), the address its
 * result carries (`unknown`); undefined when neither says anything.
 */
export function rowOf(presented: Presented | undefined, id: string, output: unknown): (PresentedRow | { state: 'unknown'; address: string }) | undefined {
  const row = presented?.[id]
  if (row !== undefined) return row
  const text = typeof output === 'string' ? output : Array.isArray(output) ? output.map((b) => (typeof b?.text === 'string' ? b.text : '')).join('') : ''
  const address = ADDRESS.exec(text)?.[0]
  return address === undefined ? undefined : { state: 'unknown', address }
}

/** The tools the fork may call at all; any other is refused at `tool.call`, by name. */
const FORK_TOOLS: ReadonlySet<string> = new Set(['Read', 'Grep', 'Glob', 'Bash', 'Write', 'Edit'])
const READ_TOOLS: ReadonlySet<string> = new Set(['Read', 'Grep', 'Glob'])
/** A secret's handle, as devcloud's secrets guard writes one in place of its bytes. */
const HANDLE = /\[(?:secret|redacted):/
/** An agent's status in `$.agent.list()` while its loop may still act. */
const LIVE_STATUSES: ReadonlySet<string> = new Set(['pending', 'running', 'waiting'])
/** The grace an own fork gets when the list no longer calls it live but its end is not heard yet (about 3 s). */
const GRACE_POLL_MS = 250
const GRACE_POLLS = 12
const COMMAND_TIMEOUT_MS = 15_000
const SAID_MAX = 2_000

const RECORD = { plugin: 'to-human', key: 'present' } as const
const PRESENTED = { plugin: 'to-human', key: 'presented' } as const
const NOTICE = { plugin: 'to-human', key: 'presentNotice' } as const
const FORKS = { plugin: 'to-human', key: 'presentForks' } as const

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

// The module's memory, the authority while it runs; `$.state` holds a copy
// for a module that starts over (`restore`).
let run: PresentRun | null = null
let presented: Presented = {}
let notices: string[] = []
/**
 * The forks this module spawned, took up from `$.state` or found listed as
 * its panel forks: the guard's, for every call they make, whether or not
 * their run is still open.
 */
const forks = new Set<string>()
/** Each agent the list named and was found to be no panel fork of this plugin's (a description does not change). */
const others = new Set<string>()
/**
 * Which `$.state` keys were read back: a key is written only once it was, so
 * a write never replaces what a module before this one left there with less.
 */
const loaded = { record: false, rows: false, notices: false, forks: false }
/** Forks whose turn.complete this module heard (their run is being closed). */
const ended = new Set<string>()
/** Each draft's real path, as `$.fs.stat` resolves it. */
const drafts = new Map<string, string>()
/**
 * The main loop's permission mode as the engine last reported it (a prompt's,
 * or a switch's); undefined until one is reported. The engine has no getter
 * for it, and a tool call's input does not carry it.
 */
let mode: string | undefined
/** The reservation: set before the handler's first await, cleared once its call is answered. */
let starting: Promise<void> | undefined
let restoring: Promise<void> | undefined
let writes: Promise<unknown> = Promise.resolve()

/** Forgets the module's memory, as a module that starts over does; for tests, which share this module. */
export function forgetPresent() {
  mode = undefined
  run = null
  presented = {}
  notices = []
  forks.clear()
  others.clear()
  for (const key of Object.keys(loaded) as (keyof typeof loaded)[]) loaded[key] = false
  ended.clear()
  drafts.clear()
  starting = undefined
  restoring = undefined
  writes = Promise.resolve()
}

/**
 * Takes up what a module before this one left in `$.state`, each key on its
 * own: a key that cannot be read is read again at the next call, and until
 * then is neither taken up nor written.
 */
function restore($: EngineInterface): Promise<void> {
  restoring ??= (async () => {
    const read = async <T,>(key: keyof typeof loaded, get: () => Promise<{ value: T | undefined }>, take: (value: T | undefined) => void) => {
      if (loaded[key]) return true
      try {
        take((await get()).value)
        loaded[key] = true
        return true
      } catch (error) {
        $.ui.log(`to-human: the panel's ${key} could not be read back (${message(error)})`, { to: 'debug' })
        return false
      }
    }
    const done = await Promise.all([
      read('forks', () => $.state.get(FORKS), (kept) => kept?.forEach((id) => forks.add(id))),
      read('record', () => $.state.get(RECORD), (kept) => {
        if (run === null && kept) {
          run = kept
          forks.add(kept.agentId)
        }
      }),
      read('rows', () => $.state.get(PRESENTED), (rows) => (presented = { ...(rows ?? {}), ...presented })),
      read('notices', () => $.state.get(NOTICE), (told) => (notices = [...(told ?? []), ...notices])),
    ])
    if (done.includes(false)) restoring = undefined
  })()
  return restoring
}

/**
 * Writes the module's memory to `$.state` after any write before it: each
 * key as it stood at the call, and only if it had been read back by then (a
 * snapshot taken before a key was read back holds less than the store).
 * Resolves whether the record was written.
 */
function keep($: EngineInterface): Promise<boolean> {
  const ready = { ...loaded }
  const record = run
  const rows = { ...presented }
  const told = [...notices]
  const ids = [...forks]
  const set = async (isReady: boolean, key: keyof typeof loaded, write: () => Promise<{ isSet: boolean }>) => {
    if (!isReady) return false
    try {
      return (await write()).isSet
    } catch (error) {
      $.ui.log(`to-human: the panel's ${key} is not kept for a reload (${message(error)})`, { to: 'debug' })
      return false
    }
  }
  const kept = writes.then(async () => {
    const [isRecordKept] = await Promise.all([
      set(ready.record, 'record', () => $.state.set(RECORD, record)),
      set(ready.rows, 'rows', () => $.state.set(PRESENTED, rows)),
      set(ready.notices, 'notices', () => $.state.set(NOTICE, told)),
      set(ready.forks, 'forks', () => $.state.set(FORKS, ids)),
    ])
    return isRecordKept
  })
  writes = kept
  return kept
}

/** The panel server's command line, `server.py <verb> ...`. */
const serverArgs = (root: string, rest: readonly string[]) => ['python3', `${root}/panel/server.py`, ...rest]

/** One server command's JSON answer, or the one line it said why not. */
async function command<T>($: EngineInterface, rest: readonly string[]): Promise<{ value: T } | { error: string }> {
  try {
    const r = await $.process.run(serverArgs($.plugin.root, rest), { timeoutMs: COMMAND_TIMEOUT_MS })
    if (r.exitCode !== 0) {
      return { error: r.stderr.trim().split('\n').at(-1) || `server.py ${rest[0]} exited ${r.exitCode}` }
    }
    return { value: JSON.parse(r.stdout.trim().split('\n').at(-1) ?? '') as T }
  } catch (error) {
    return { error: `server.py ${rest[0]} did not run: ${message(error)}` }
  }
}

/** Raised when who an agent is cannot be told: the guard's `.catch` refuses its call. */
class Unresolved extends Error {
  override name = 'Unresolved'
}

/**
 * Whether a loop is a panel fork's: the guard holds its every call. The ids
 * this module spawned or read back say so, every one it ever spawned; past
 * them, the list names a fork this plugin spawned as the panel's, and an
 * agent it names otherwise is none. An agent it does not name is none once
 * the ids are read back (a workflow's agent, the engine's own forks), but
 * may be a panel fork whose run closed while they are not, so then, as when
 * the list cannot be read either, it throws Unresolved and is refused.
 */
async function isPanelFork($: EngineInterface, agentId: string | undefined): Promise<boolean> {
  if (agentId === undefined) return false
  if (forks.has(agentId)) return true
  await restore($)
  if (forks.has(agentId)) return true
  if (others.has(agentId)) return false
  let agents: Awaited<ReturnType<EngineInterface['agent']['list']>>
  try {
    agents = await $.agent.list()
  } catch (error) {
    if (loaded.forks) return false
    throw new Unresolved(`neither the panel's forks nor the agent list could be read (${message(error)})`)
  }
  const listed = agents.find((a) => a.id === agentId)
  if (listed === undefined) {
    if (loaded.forks) return false
    throw new Unresolved(`the panel's forks could not be read, and the agent list does not name ${agentId}`)
  }
  if (listed.type === 'fork' && listed.spawnedBy === $.plugin.name && listed.description === FORK_DESCRIPTION) {
    forks.add(agentId)
    return true
  }
  others.add(agentId)
  return false
}

/** Where a path lands, links and `..` resolved; undefined where it leads nowhere. */
async function realOf($: EngineInterface, path: unknown): Promise<string | undefined> {
  if (typeof path !== 'string' || path === '') return undefined
  return (await $.fs.stat(path, { resolve: true }).catch(() => undefined))?.realPath
}

/** Whether `path` is the draft of the run whose fork makes the call. */
async function isDraft($: EngineInterface, path: unknown): Promise<boolean> {
  const draft = run?.draft
  if (draft === undefined) return false
  let real = drafts.get(draft)
  if (real === undefined) {
    real = await realOf($, draft)
    if (real === undefined) return false
    drafts.set(draft, real)
  }
  return (await realOf($, path)) === real
}

/** Whether a call is the Agent call the engine makes of this module's spawn of a panel fork. */
function isOwnSpawn($: EngineInterface, origin: { plugin: string }, e: { tool: string; input: unknown; agentId?: string }): boolean {
  const input = e.input as { description?: unknown; subagent_type?: unknown } | null
  return origin.plugin === $.plugin.name && e.tool === 'Agent' && e.agentId === undefined && input?.subagent_type === 'fork' && input.description === FORK_DESCRIPTION
}

const refusedCheck = () => ({ decision: 'deny', reason: GUARD_REFUSAL }) as const

/**
 * Whether the open run's fork may still act. The list is read only here: a
 * live status keeps it open; otherwise, for a fork whose end this module may
 * yet hear, the list is read again for about 3 s (it calls an agent completed
 * about a second after its turn.complete); then the run is closed as not
 * written, without publishing, since a draft whose fork's ending is unknown
 * may be half edited. A list that cannot be read keeps it open. A record a
 * module before this one left publishing is published again and closed.
 */
async function isRunOpen($: EngineInterface, open: PresentRun): Promise<boolean> {
  if (ended.has(open.agentId)) return true
  if (open.phase === 'publishing') {
    // The fork ended well and a module before this one was publishing its draft when it stopped: publish it.
    ended.add(open.agentId)
    await publishRun($, open, { said: '', isAgain: true })
    return false
  }
  for (let poll = 0; ; poll++) {
    if (ended.has(open.agentId)) return true
    let status: string | undefined
    try {
      status = (await $.agent.list()).find((a) => a.id === open.agentId)?.status
    } catch {
      return true
    }
    if (status !== undefined && LIVE_STATUSES.has(status)) return true
    if (poll >= GRACE_POLLS) break
    await $.clock.sleep(GRACE_POLL_MS)
  }
  await close($, open, { state: 'failed', address: open.address, why: NOT_HEARD }, FAILED(open.address, NOT_HEARD))
  return false
}

/**
 * A run's end: the call's row, the person's notification, the session's
 * notice, then the record cleared, in that order.
 */
async function close($: EngineInterface, open: PresentRun, row: PresentedRow, notice: string) {
  if (run?.agentId !== open.agentId) return
  presented = { ...presented, [open.toolUseId]: row }
  notices = [...notices, notice]
  run = null
  ended.delete(open.agentId)
  const text = row.state === 'written' ? `The panel is written: ${row.address}` : `The panel was not written (${row.why})`
  try {
    if (isNotifying(await $.env.get('MAWS_NATIVE_TO_HUMAN'), await $.env.get('SMNS_INTERNAL'))) {
      $.ui.notify(text).catch((error) => $.ui.log(`to-human: the panel's notification failed (${message(error)})`, { to: 'debug' }))
    }
  } catch (error) {
    $.ui.log(`to-human: the panel's notification was not raised (${message(error)})`, { to: 'debug' })
  }
  await keep($)
}

/** Why a run is closed whose fork ended well but whose publishing phase could not be kept. */
const UNKEPT = 'its record could not be kept'

const WHY: Record<Exclude<TurnCompleteInput['reason'], 'answer'>, string> = {
  aborted: 'its fork was interrupted',
  error: 'an API error ended its fork',
  refusal: 'the model refused to write it',
}

/**
 * The fork's turn.complete: published when it answered, else not written.
 * The record says `publishing`, kept, before publish is called, so a module
 * that starts over in between publishes again rather than reading the run as
 * unheard.
 */
async function finish($: EngineInterface, open: PresentRun, e: TurnCompleteInput) {
  if (e.reason !== 'answer') {
    const why = WHY[e.reason]
    return close($, open, { state: 'failed', address: open.address, why }, FAILED(open.address, why))
  }
  const publishing: PresentRun = { ...open, phase: 'publishing' }
  if (run?.agentId === open.agentId) run = publishing
  // Never publish without the phase kept: a module that started over would read the run as unheard.
  if (!(await keep($))) {
    return close($, publishing, { state: 'failed', address: open.address, why: UNKEPT }, FAILED(open.address, UNKEPT))
  }
  return publishRun($, publishing, { said: e.answer.trim().slice(0, SAID_MAX), isAgain: false })
}

/**
 * Publishes the run's draft and closes the run by what that says: written
 * when publish says so, and, when it is published again (`isAgain`) by a
 * module that found the record publishing, also when the panel's last
 * publication is at or after the run's start, since a first publish that
 * committed before the reload leaves the second with nothing to change.
 * `said` is the fork's answer, '' when no module that heard it is left.
 */
async function publishRun($: EngineInterface, open: PresentRun, { said, isAgain }: { said: string; isAgain: boolean }) {
  const out = await command<Published>($, ['publish', '--session', open.session])
  if ('error' in out) {
    return close($, open, { state: 'failed', address: open.address, why: out.error }, FAILED(open.address, out.error))
  }
  const p = out.value
  const isWrittenBefore = isAgain && p.written !== null && open.startedAt !== undefined && p.written >= open.startedAt
  if (!p.published && !isWrittenBefore) {
    const why = 'the fork changed nothing on it'
    return close($, open, { state: 'failed', address: p.address, why }, FAILED(p.address, why))
  }
  const extra = (p.removed.length > 0 ? REMOVED(p.removed) : '') + (p.lookedMeanwhile ? LOOKED_MEANWHILE : '') + (p.reach === 'local' ? LOCAL_ONLY : '')
  const notice = FINISHED(p.address, said).trimEnd() + (extra === '' ? '' : `\n${extra.trim()}`)
  return close($, open, { state: 'written', address: p.address }, notice)
}

/** Takes the notices waiting for the session, for one delivery. */
function takeNotices($: EngineInterface): string[] {
  const taken = notices
  if (taken.length > 0) {
    notices = []
    void keep($)
  }
  return taken
}

/** The call: refusals first, then the reservation, open-panel, the spawn and the record (the spec's order). */
async function startRun($: EngineInterface, toolUseId: string, brief: string): Promise<{ result: string } | { deny: string }> {
  await restore($)
  if (!loaded.record || !loaded.forks) return { deny: RECORD_UNREAD }
  // The run as it stood: its fork may end, and the run close, while the list is read.
  const open = run
  if (open !== null && (await isRunOpen($, open)) && run?.agentId === open.agentId) {
    return { deny: BUSY(open.address) }
  }
  const startedAt = await $.clock.now()
  const session = await $.session.id()
  const locale = await $.env.get('PANEL_LOCALE')
  const opened = await command<OpenPanel>($, ['open-panel', '--session', session, ...(locale ? ['--locale', locale] : [])])
  if ('error' in opened) {
    return { deny: opened.error }
  }
  const panel = opened.value
  const spawned = await $.agent.spawn({ subagentType: 'fork', description: FORK_DESCRIPTION, prompt: STANDING_PROMPT(panel, brief) })
  const agentId = 'agentId' in spawned ? spawned.agentId : undefined
  if (agentId === undefined) {
    const deny = 'deny' in spawned && typeof spawned.deny === 'string' ? spawned.deny : 'the engine started no agent'
    // Past an interrupt the engine spawns nothing until the session takes input (bridge-ask.tsx).
    return { deny: `The panel's fork was not started: ${deny}` }
  }
  // Set before any await: the fork's first call finds its guard.
  forks.add(agentId)
  run = { agentId, toolUseId, session, dir: panel.dir, draft: panel.draft, address: panel.address, update: panel.update, startedAt, phase: 'writing' }
  presented = { ...presented, [toolUseId]: { state: 'writing', address: panel.address } }
  await keep($)
  return { result: STARTED(panel.address) + (panel.reach === 'local' ? LOCAL_ONLY : '') }
}

/**
 * Where it is offered (`session.start`): beside the message tool, in an
 * interactive session, outside MAWS (its own artifact viewer) and a sminos
 * internal fork. The main conversation only: a subagent's call is refused.
 */
export function registerPresent(on: On): void {
  // The guard, registered first so it is outer to the handler: a fork's own
  // present call is refused here. Every deny is GUARD_REFUSAL; none of the
  // fork's calls reaches a permission prompt. A `.catch` refuses a
  // subagent's call it had not passed on (who the agent is was not
  // settled), and passes the main loop's, whose failure is never the guard's.
  on('tool.call', { tool: /^/ }, async ($, e, next) => {
    if (!(await isPanelFork($, e.agentId))) return next(e)
    if (!FORK_TOOLS.has(e.tool)) return { deny: GUARD_REFUSAL }
    // The input as the fork wrote it: a hook beneath (devcloud's secrets guard) restores a handle before the check.
    const text = e.tool === 'Write' ? (e as { content?: unknown }).content : e.tool === 'Edit' ? (e as { new_string?: unknown }).new_string : undefined
    if (typeof text === 'string' && HANDLE.test(text)) return { deny: GUARD_REFUSAL }
    return next(e)
  }).catch((_, e, next) => (next.called || e.agentId === undefined ? next(e) : { deny: GUARD_REFUSAL }))

  on('tool.check', { tool: /^/ }, async ($, e, next) => {
    // The engine runs this module's spawn as an Agent call and checks it as it
    // checks any call, so a mode that asks (default, auto) put it to a
    // permission dialog the present call waited on. This plugin raised it.
    if (isOwnSpawn($, next.origin, e)) {
      $.ui.log("to-human: the panel fork's spawn is allowed at its check", { to: 'debug' })
      return { decision: 'allow' }
    }
    if (!(await isPanelFork($, e.agentId))) return next(e)
    if (READ_TOOLS.has(e.tool) || (e.tool === 'Bash' && e.isReadOnly === true)) return { decision: 'allow' }
    if ((e.tool === 'Write' || e.tool === 'Edit') && (await isDraft($, (e.input as { file_path?: unknown } | null)?.file_path))) {
      return { decision: 'allow' }
    }
    return refusedCheck()
  }).catch((_, e, next) => (next.called || e.agentId === undefined ? next(e) : refusedCheck()))

  // The main loop's mode, as the engine reports it: the mode each prompt is
  // submitted under, and each switch as it happens (sminos' bridge reads the
  // same two). Observed only.
  on('classic.UserPromptSubmit', { hook_event_name: 'UserPromptSubmit' }, (_, e, next) => {
    if (e.agent_id === undefined && typeof e.permission_mode === 'string') {
      mode = e.permission_mode
    }
    return next(e)
  }).catch((_, e, next) => next(e))

  on('telemetry.log', { to: 'collector' }, (_, e, next) => {
    if (e.to === 'collector' && e.event === 'permission_mode_changed' && e.attributes.agent_id === undefined && typeof e.attributes.to_mode === 'string') {
      mode = e.attributes.to_mode
    }
    return next(e)
  }).catch((_, e, next) => next(e))

  // After the hooks beneath: the message tool's registration is known by then.
  on('session.start', { cwd: /^/ }, async ($, e, next) => {
    const started = await next(e)
    if (!e.isInteractive) return started
    // The panels served again after a restart of the machine, and an older server replaced; never awaited.
    void $.process.run(serverArgs($.plugin.root, ['ensure']), { timeoutMs: COMMAND_TIMEOUT_MS }).then(
      (r) => r.exitCode !== 0 && $.ui.log(`to-human: the panel server was not ensured: ${r.stderr.trim()}`, { to: 'debug' }),
      (error: unknown) => $.ui.log(`to-human: the panel server was not ensured (${message(error)})`, { to: 'debug' }),
    )
    void restore($)
      .then(() => (run !== null && !ended.has(run.agentId) ? isRunOpen($, run) : undefined))
      .catch((error: unknown) => $.ui.log(`to-human: the panel's run was not reconciled (${message(error)})`, { to: 'debug' }))
    const maws = await $.env.get('MAWS_NATIVE_TO_HUMAN')
    if (!isMessageToolOn() || (maws !== undefined && maws !== '') || (await $.env.get('SMNS_INTERNAL')) !== undefined) {
      return started
    }
    try {
      await $.tool.register({ name: 'present', description: DESCRIPTION, inputSchema: INPUT_SCHEMA })
    } catch (error) {
      $.ui.log(`to-human: the present tool is not registered: ${message(error)}`, { to: 'debug' })
    }
    return started
  })

  on('tool.describe', { tool: PRESENT_TOOL }, async (_, e, next) => ({ ...(await next(e)), isDeferred: false }))

  // The session's notice of a run's end, beside the main loop's next tool
  // result: added to what `next` returned, outer to the tools this plugin
  // serves (the message tool's handler among them). Only the model's call
  // in the main loop: a plugin's own `$.tool.call` has no agentId either, and
  // its result's context enters no conversation.
  on('tool.call', { tool: /^/ }, async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined || next.origin.plugin !== 'engine' || result.deny !== undefined) return result
    await restore($)
    const taken = takeNotices($)
    return taken.length === 0 ? result : { ...result, context: [...(result.context ?? []), ...taken] }
  })

  on('tool.call', { tool: PRESENT_TOOL }, async ($, e) => {
    if (e.agentId !== undefined) return { deny: SUBAGENT_REFUSAL }
    const brief = (e as { brief?: unknown }).brief
    if (typeof brief !== 'string' || brief.trim() === '') return { deny: EMPTY_REFUSAL }
    // In plan mode the engine puts the spawn's Agent call to a permission dialog, on which the call would wait;
    // and a fork inherits the mode, where no hook can open its write.
    if (mode === 'plan') return { deny: PLAN_REFUSAL }
    // One fork at a time: a call that comes while another is starting waits for it, then is answered as it left things.
    while (starting !== undefined) await starting
    let release = () => {}
    starting = new Promise<void>((resolve) => (release = resolve))
    try {
      return await startRun($, e.tool_use_id, brief)
    } finally {
      starting = undefined
      release()
    }
  })

  // The fork's end, which the engine tells the session nothing of (trial 1).
  on('turn.complete', { reason: /./ }, async ($, e, next) => {
    if (e.agentId !== undefined) {
      await restore($)
      const open = run
      if (open !== null && open.agentId === e.agentId && !ended.has(e.agentId)) {
        ended.add(e.agentId)
        void finish($, open, e).catch((error: unknown) => $.ui.log(`to-human: the panel's end was not closed (${message(error)})`, { to: 'debug' }))
      }
    }
    return next(e)
  })

  // The notice beside the next prompt when no turn ran to carry it: added to
  // the input passed to `next`, since a prompt has entered the conversation by
  // the time `next` resolves. A prompt dropped beneath gives it back.
  on('prompt.submit', { text: /^/ }, async ($, e, next) => {
    if (e.command !== undefined) return next(e)
    await restore($)
    const taken = takeNotices($)
    if (taken.length === 0) return next(e)
    const result = await next({ ...e, context: [...(e.context ?? []), ...taken] })
    if (result.drop !== undefined) {
      notices = [...taken, ...notices]
      void keep($)
    }
    return result
  }).catch((_, e, next) => next(e))
}
