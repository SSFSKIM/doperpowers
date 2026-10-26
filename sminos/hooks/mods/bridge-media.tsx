import type { EngineInterface, HookStream, TurnStepChunk, TurnStepInput, TurnStepResult } from 'claude-code'
import type { MediaAttachment, MediaSnapshot, MediaState } from '../../types/sminos'
import { WAKE_LINE, isRecord, message, state } from './bridge-state'
import type { Answer } from './bridge-state'
import { emitOwed } from './bridge-stream'

/**
 * The desk's image and PDF intake (DX5 op `media`, the desk control surface
 * spec's MW5): a file the daemon saved inside the session's working directory
 * reaches the model through a native Read the bridge streams itself, at a
 * main-loop step, so the next request carries it as an `image` or `document`
 * block (measured on 2.1.310: a `turn.step` hook that streams `tool` and
 * `input` chunks and a `tool_use` stop, without `next`, makes the engine run
 * that Read; a returned `toolUses` alone runs nothing).
 *
 * Each attachment is `pending` once accepted, `claimed` when a step takes it
 * (its tool-use id recorded before anything is yielded), then `read` (its
 * result holds the media), `forwarded` (the next main-loop step passed the
 * conversation on through `next`, which a hook beneath may still answer
 * without a model request), `aborted` (its step was cancelled: never streamed
 * again) or `failed` (a denied or error result, a file no longer inside its
 * root). It is kept in `$.state`, which the host holds for the session across
 * a reload, so the module after a reload claims nothing twice and ends what it
 * cannot know. Each change is a `media` event, owed until the child took it.
 */

/** The upload kept for the session (types/sminos.d.ts). */
const MEDIA = { plugin: 'sminos', key: 'media' } as const
/** The media types the daemon validated against the bytes; the stored name's extension came from it. */
export const MEDIA_TYPES: ReadonlySet<string> = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'application/pdf'])
/** Attachments in one upload, at most (DX6 `media`). */
export const MEDIA_FILES_MAX = 4
/** An idle session given this long for the person's own Send to start the turn before the bridge wakes it. */
export const MEDIA_WAKE_MS = 2_000
/** Uploads kept once ended and said, so that a repeated id is still answered `duplicate`. */
export const MEDIA_UPLOADS_KEPT = 64
/** Characters of a reason an event carries. */
const REASON_MAX = 1_000
/** A name, a display name: no control character, no line break. */
const NAME = /^[^\x00-\x1f\x7f\u2028\u2029]{1,128}$/
const UPLOAD = /^[A-Za-z0-9_-]{1,128}$/
export const MEDIA_MOVED_REASON = 'the file is no longer where it was saved, inside its upload directory'
export const MEDIA_CANCELLED_REASON = 'its step was cancelled before the Read ran'
export const MEDIA_TURN_ENDED_REASON = 'the turn ended before its Read ran'
export const MEDIA_RELOAD_REASON = 'indeterminate after reload'
export const MEDIA_EMPTY_REASON = 'the Read returned no image or document'
const ENDED: ReadonlySet<MediaState> = new Set(['forwarded', 'aborted', 'failed'])
/** The states an event says (`pending` and `claimed` are the bridge's own). */
const SAID: ReadonlySet<MediaState> = new Set(['read', 'forwarded', 'aborted', 'failed'])
const ORDER: Record<MediaState, number> = { pending: 0, claimed: 1, read: 2, forwarded: 3, aborted: 3, failed: 3 }

/** The disclosure the TUI shows and the model reads above the Read: the synthetic rows are model-shaped. */
export const mediaPrelude = (name: string) => `${WAKE_LINE} The person attached ${name} from the desk: this Read is the bridge's, not your choice.`

/** The one wake an intake sends: the bridge's line, then the attachments it names. */
export function mediaWakeText(names: readonly string[]): string {
  const listed = names.length <= 1 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`
  return `${WAKE_LINE}\nThe person attached ${listed} from the desk: the bridge reads ${names.length === 1 ? 'it' : 'them'} into the conversation now.`
}

const uploadOf = (upload: string) => state.media.filter((a) => a.upload === upload)
const cut = (text: string) => (text.length > REASON_MAX ? text.slice(0, REASON_MAX) : text)

/** Writes the uploads as they stand now, after any write before it: whether it was kept. */
function keep($: EngineInterface): Promise<boolean> {
  const snapshot: MediaSnapshot = { shape: 1, attachments: state.media.map((a) => ({ ...a })) }
  const written = state.mediaWrites.then(() => $.state.set(MEDIA, snapshot)).then(
    () => true,
    (error: unknown) => {
      state.log?.(`bridge: the desk's uploads were not kept for a reload: ${message(error)}`)
      return false
    },
  )
  state.mediaWrites = written.then(() => undefined)
  return written
}

/**
 * An attachment's state said on the stream (DX5 `media`), owed until the child
 * took it: `phase` is `end` once it leaves every attachment of its upload
 * ended, and `attachments` the whole upload as it stands, so the latest event
 * is the whole picture. The attachment's index is `index`: every line of the
 * child's stream carries its own `n`.
 */
function say($: EngineInterface, a: MediaAttachment) {
  const upload = uploadOf(a.upload)
  const said = a.state
  void emitOwed({
    type: 'media',
    id: a.upload,
    upload: a.upload,
    index: a.index,
    state: said,
    phase: upload.every((x) => ENDED.has(x.state)) ? 'end' : 'start',
    ...(a.toolUseId !== undefined && { toolUseId: a.toolUseId }),
    ...(a.reason !== undefined && { reason: a.reason }),
    attachments: upload.map((x) => ({ index: x.index, state: x.state, ...(x.toolUseId !== undefined && { toolUseId: x.toolUseId }), ...(x.reason !== undefined && { reason: x.reason }) })),
  }).then(() => {
    if (a.told === undefined || ORDER[said] >= ORDER[a.told]) {
      a.told = said
      void keep($)
    }
  })
}

/** An attachment moved on, kept and said. */
function move($: EngineInterface, a: MediaAttachment, to: MediaState, reason?: string) {
  a.state = to
  if (reason !== undefined) {
    a.reason = cut(reason)
  }
  void keep($)
  say($, a)
}

/** Uploads ended and said beyond MEDIA_UPLOADS_KEPT are let go, oldest first. */
function prune() {
  const done = [...new Set(state.media.map((a) => a.upload))].filter((u) => uploadOf(u).every((a) => ENDED.has(a.state) && a.told === a.state))
  const gone = new Set(done.slice(0, Math.max(0, done.length - MEDIA_UPLOADS_KEPT)))
  state.media = state.media.filter((a) => !gone.has(a.upload))
}

/**
 * What a module before this one held, read once and reconciled: a claim whose
 * result is in the conversation advances (read, or forwarded when a response
 * followed it), one with none is aborted (it is never streamed again: the
 * file could be read twice); pending waits, its wake armed again from now
 * (engine timers die with the module). Every state the child has not taken is
 * said again.
 */
export function mediaLoaded($: EngineInterface): Promise<void> {
  state.mediaLoad ??= (async () => {
    let kept: unknown
    try {
      kept = (await $.state.get(MEDIA)).value
    } catch (error) {
      state.log?.(`bridge: the desk's uploads could not be read: ${message(error)}`)
      return
    }
    const held = isRecord(kept) && kept.shape === 1 && Array.isArray(kept.attachments) ? (kept.attachments as MediaAttachment[]).filter(isAttachment) : []
    if (held.length === 0) {
      return
    }
    state.media = [...held.map((a) => ({ ...a })), ...state.media]
    const claimed = state.media.filter((a) => a.state === 'claimed')
    let conversation: unknown = []
    if (claimed.length > 0) {
      try {
        conversation = await $.session.messages({ as: 'api' })
      } catch (error) {
        state.log?.(`bridge: the conversation was not read to reconcile the desk's uploads: ${message(error)}`)
      }
    }
    const messages = Array.isArray(conversation) ? (conversation as { role?: unknown; content?: unknown }[]) : []
    for (const a of claimed) {
      const at = messages.findIndex((m) => m.role === 'user' && resultFor(m.content, a.toolUseId) !== undefined)
      if (at === -1) {
        a.state = 'aborted'
        a.reason = MEDIA_RELOAD_REASON
        continue
      }
      const outcome = judged(resultFor(messages[at]!.content, a.toolUseId)!)
      a.state = outcome.state === 'read' && messages.slice(at + 1).some((m) => m.role === 'assistant') ? 'forwarded' : outcome.state
      if (outcome.reason !== undefined) {
        a.reason = outcome.reason
      }
    }
    void keep($)
    for (const a of state.media) {
      if (SAID.has(a.state) && a.told !== a.state) {
        say($, a)
      }
    }
    if (state.media.some((a) => a.state === 'pending')) {
      armWake($)
    }
  })()
  return state.mediaLoad
}

function isAttachment(a: unknown): a is MediaAttachment {
  return (
    isRecord(a) &&
    typeof a.upload === 'string' &&
    Number.isInteger(a.index) &&
    typeof a.name === 'string' &&
    typeof a.path === 'string' &&
    typeof a.root === 'string' &&
    typeof a.state === 'string' &&
    a.state in ORDER
  )
}

/** Whether `path` lands exactly on itself, a file, inside `root` (itself a real directory): no link anywhere on the way. */
async function isInside($: EngineInterface, path: string, root: string): Promise<boolean> {
  const [dir, file] = await Promise.all([$.fs.stat(root, { resolve: true }).catch(() => undefined), $.fs.stat(path, { resolve: true }).catch(() => undefined)])
  return dir?.kind === 'dir' && !dir.isLink && dir.realPath === root && file?.kind === 'file' && !file.isLink && file.realPath === path && path.startsWith(`${root}/`)
}

/**
 * DX5 `media {upload, root, files: [{n, path, name, mediaType}]}`: the
 * daemon's saved upload, checked (each path a file that lands on itself
 * inside the root, the root its own real path), held in the session's state,
 * then answered `queued`; an upload already held is answered `duplicate`.
 * Idle, the bridge then waits MEDIA_WAKE_MS for a turn to start, and wakes
 * the session once if none did.
 */
export async function acceptMedia($: EngineInterface, command: Record<string, unknown>): Promise<Answer & { after?: () => void }> {
  const { upload, root, files } = command
  if (typeof upload !== 'string' || !UPLOAD.test(upload) || typeof root !== 'string' || !root.startsWith('/') || root.endsWith('/')) {
    return { ok: false, error: 'media needs its upload id and the absolute directory it was saved in' }
  }
  if (!Array.isArray(files) || files.length === 0 || files.length > MEDIA_FILES_MAX) {
    return { ok: false, error: `media holds 1 to ${MEDIA_FILES_MAX} files` }
  }
  const asked: MediaAttachment[] = []
  for (const f of files as unknown[]) {
    if (
      !isRecord(f) ||
      !Number.isInteger(f.n) ||
      (f.n as number) < 0 ||
      (f.n as number) >= MEDIA_FILES_MAX ||
      asked.some((a) => a.index === f.n) ||
      typeof f.path !== 'string' ||
      typeof f.name !== 'string' ||
      !NAME.test(f.name) ||
      typeof f.mediaType !== 'string' ||
      !MEDIA_TYPES.has(f.mediaType)
    ) {
      return { ok: false, error: 'each file is {n, path, name, mediaType}: n 0 to 3, once each; a name without a control character; an image or a PDF' }
    }
    asked.push({ upload, index: f.n as number, name: f.name, mediaType: f.mediaType, path: f.path, root, state: 'pending' })
  }
  await mediaLoaded($)
  if (uploadOf(upload).length > 0) {
    return { ok: true, result: { duplicate: true, upload } }
  }
  for (const a of asked) {
    const isThere = await $.fs.stat(a.path).then(
      () => true,
      () => false,
    )
    if (!isThere) {
      return { ok: false, error: `${a.name} is missing: nothing is at ${a.path}` }
    }
    if (!(await isInside($, a.path, root))) {
      return { ok: false, error: `${a.name} is not a file inside its upload directory ${root}` }
    }
  }
  // Another answer may have held it while this one checked.
  if (uploadOf(upload).length > 0) {
    return { ok: true, result: { duplicate: true, upload } }
  }
  state.media.push(...asked)
  prune()
  if (!(await keep($))) {
    state.media = state.media.filter((a) => a.upload !== upload)
    return { ok: false, error: 'the upload could not be kept in the session state, so a reload would lose it' }
  }
  return { ok: true, result: { queued: true, upload }, after: () => armWake($) }
}

/** A generated tool-use id, as the API spells one: never a model's. */
function toolUseId(): string {
  let hex = ''
  for (let i = 0; i < 24; i++) {
    hex += Math.floor(Math.random() * 16).toString(16)
  }
  return `toolu_sminos_${hex}`
}

/**
 * At a main-loop step: the first pending attachment claimed (its tool-use id
 * kept before anything is yielded), checked still inside its pinned root
 * (else failed, and the next is tried), and streamed as the prelude and one
 * native Read of its pinned path, with no `pages` (a PDF goes whole, as a
 * `document`). Undefined when nothing is pending: the step goes on through
 * `next`. A subagent's loop is never touched.
 */
export async function claimMedia($: EngineInterface, e: TurnStepInput): Promise<HookStream<TurnStepChunk, TurnStepResult> | undefined> {
  if (e.agentId !== undefined) {
    return undefined
  }
  await mediaLoaded($)
  for (;;) {
    const a = state.media.find((x) => x.state === 'pending')
    if (a === undefined) {
      return undefined
    }
    a.state = 'claimed'
    a.toolUseId = toolUseId()
    if (!(await keep($))) {
      // Unkept, a reload would not know it was claimed and could read it twice: it waits.
      a.state = 'pending'
      delete a.toolUseId
      return undefined
    }
    if (!(await isInside($, a.path, a.root))) {
      move($, a, 'failed', MEDIA_MOVED_REASON)
      continue
    }
    return syntheticRead($, a, e)
  }
}

/** The claimed attachment's step: the prelude, the Read, the stop; a step closed before its end leaves the claim aborted. */
function syntheticRead($: EngineInterface, a: MediaAttachment, e: TurnStepInput): HookStream<TurnStepChunk, TurnStepResult> {
  const prelude = mediaPrelude(a.name)
  const input = { file_path: a.path }
  const result: TurnStepResult = { turnId: e.turnId, index: e.index, answer: prelude, toolUses: [{ name: 'Read', input }], stopReason: 'tool_use', usage: null }
  let isComplete = false
  const stream = (async function* (): AsyncGenerator<TurnStepChunk, TurnStepResult> {
    try {
      yield { kind: 'text', index: 0, text: prelude }
      yield { kind: 'tool', index: 1, id: a.toolUseId!, name: 'Read' }
      yield { kind: 'input', index: 1, json: JSON.stringify(input) }
      yield { kind: 'stop', stopReason: 'tool_use', usage: null }
      isComplete = true
      return result
    } finally {
      if (!isComplete && a.state === 'claimed') {
        move($, a, 'aborted', MEDIA_CANCELLED_REASON)
      }
    }
  })()
  return Object.assign(stream, { result: Promise.resolve(result) })
}

/** The tool_result block for `id` in a message's content, if it holds one. */
function resultFor(content: unknown, id: string | undefined): Record<string, unknown> | undefined {
  if (id === undefined || !Array.isArray(content)) {
    return undefined
  }
  return (content as unknown[]).find((b): b is Record<string, unknown> => isRecord(b) && b.type === 'tool_result' && b.tool_use_id === id)
}

/** What a Read's result says of its attachment: read when it holds an image or a document, else failed with its text. */
function judged(block: Record<string, unknown>): { state: 'read' | 'failed'; reason?: string } {
  const blocks = Array.isArray(block.content) ? (block.content as unknown[]) : []
  const text = typeof block.content === 'string' ? block.content : blocks.flatMap((b) => (isRecord(b) && b.type === 'text' && typeof b.text === 'string' ? [b.text] : [])).join('\n')
  if (block.is_error === true) {
    return { state: 'failed', reason: cut(text === '' ? 'the Read failed' : text) }
  }
  if (blocks.some((b) => isRecord(b) && (b.type === 'image' || b.type === 'document'))) {
    return { state: 'read' }
  }
  return { state: 'failed', reason: cut(text === '' ? MEDIA_EMPTY_REASON : `${MEDIA_EMPTY_REASON}: ${text}`) }
}

/** A main-loop row the session keeps: the result of a claimed attachment's Read moves it on. */
export function observeMediaResult($: EngineInterface, door: string, message: unknown, agentId: string | null) {
  if (door !== 'tool-result' || agentId !== null || !isRecord(message)) {
    return
  }
  for (const a of state.media.filter((x) => x.state === 'claimed')) {
    const block = resultFor(message.content, a.toolUseId)
    if (block !== undefined) {
      const outcome = judged(block)
      move($, a, outcome.state, outcome.reason)
    }
  }
}

/** A main-loop step about to pass the conversation on through `next`: every attachment read goes with it. */
export function mediaPassedOn($: EngineInterface) {
  for (const a of state.media.filter((x) => x.state === 'read')) {
    move($, a, 'forwarded')
  }
}

/** A main turn started: an armed wake is not needed (its steps take what is pending). */
export function mediaTurnStarted() {
  state.mediaWake.armed = undefined
}

/**
 * A main turn ended: a claim it left without a result ended with it
 * (aborted), and one attachment still pending (its last request ended
 * `end_turn`, so no step took it) is woken for once.
 */
export function mediaTurnEnded($: EngineInterface) {
  for (const a of state.media.filter((x) => x.state === 'claimed')) {
    move($, a, 'aborted', MEDIA_TURN_ENDED_REASON)
  }
  if (state.media.some((a) => a.state === 'pending')) {
    state.mediaWake.armed = undefined
    submitWake($)
  }
}

/** Idle: one wake after MEDIA_WAKE_MS, unless a turn starts first or a wake is owed already. */
function armWake($: EngineInterface) {
  if (state.mainTurn !== undefined || state.mediaWake.armed !== undefined || state.mediaWake.isSubmitted || state.after === undefined) {
    return
  }
  const armed = {}
  state.mediaWake.armed = armed
  state.after(MEDIA_WAKE_MS, () => {
    if (state.mediaWake.armed !== armed) {
      return
    }
    state.mediaWake.armed = undefined
    void (async () => {
      if (state.mainTurn !== undefined || !state.media.some((a) => a.state === 'pending')) {
        return
      }
      // Loaded into a session whose turn it cannot see yet: wait until it can tell.
      if ((await state.isTurnStillUnknown?.()) === true) {
        armWake($)
        return
      }
      submitWake($)
    })()
  })
}

/**
 * The wake: the bridge's line and the attachments it names, as the
 * bridge's other wakes are submitted. After an Esc the engine refuses it
 * (`stopped`), and the attachment waits for the person's next turn: the
 * bridge never reaches past that through the calls an Esc leaves open.
 */
function submitWake($: EngineInterface) {
  if (state.mediaWake.isSubmitted) {
    return
  }
  const names = state.media.filter((a) => a.state === 'pending').map((a) => a.name)
  state.mediaWake.isSubmitted = true
  const settled = () => (state.mediaWake.isSubmitted = false)
  $.prompt.submit({ text: mediaWakeText(names), asUser: true }).then(
      (entered) => {
        settled()
        if (entered.drop !== undefined) {
          state.log?.(`bridge: the wake for the desk's upload was dropped: ${entered.drop}`)
        }
      },
      (error: unknown) => {
        settled()
        state.log?.(`bridge: the wake for the desk's upload was not submitted: ${message(error)}`)
      },
    )
}
