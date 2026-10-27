/**
 * sminos's contract: the values it keeps in `$.state`, held by the host for
 * the session.
 *
 * `btw`: the ids of the session's side questions answered `started` whose
 * end the bridge's child has not taken yet (hooks/mods/bridge-btw.tsx), so
 * that the module that loads after a reload ends those whose fork the reload
 * aborted. Only sminos writes or reads it.
 *
 * `ask`: the ask mod's async asks and the answers on their way to the model
 * (hooks/mods/ask.tsx), kept so that a reload of the module takes them up,
 * and written on every change of any field it carries. Another plugin reads
 * it and observes its writes; only sminos writes it. doperpowers' appeal ends
 * its passes when `answered` grows, and its reload waits while `isDialogUp`:
 *
 *   const ASK = { plugin: 'sminos', key: 'ask' } as const
 *   const { value } = await $.state.get(ASK)          // undefined at version 0 where sminos is not loaded
 *   on('state.set', { plugin: 'sminos', key: 'ask' }, ($, e, next) => { ...e.value...; return next(e) })
 *
 * The matcher is written out where it is used: `claude plugin validate`
 * refuses a `$.state.get` reference const that is also handed to `on`.
 */
export type AskSnapshot = {
  shape: 2
  /** The session's async asks, oldest first: the call's id, its questions, and the engine's text once answered. */
  asks: {
    id: string
    questions: { question: string; header: string; options: { label: string; description: string; preview?: string }[]; multiSelect: boolean }[]
    status: 'open' | 'answered'
    answer?: string
  }[]
  /** The answers that have not reached the model, in the order given: the call's id, the delivery text, and whether it waits for a route rather than waking the session (a dismissal). */
  undelivered: { id: string; text: string; isQuiet?: boolean }[]
  isTurnRunning: boolean
  /** An ask's dialog is up: open, or queued behind another. A reload waits for it. */
  isDialogUp: boolean
  /** How many times the human answered this session — an async ask's delivery, a blocking dialog's outcome — so a reader ends what must end when the human speaks (the appeal's passes). */
  answered: number
  /** Where the session's pasted pictures are kept, once the session start named it. */
  store?: { slug: string; sessionId: string; root?: string | null }
}

/**
 * `media`: the desk's uploads this session holds (hooks/mods/bridge-media.tsx,
 * the desk control surface spec's MW5), each attachment where its intake
 * stands, so that the module that loads after a reload claims nothing twice
 * and ends what it cannot know. Only sminos writes or reads it.
 */
export type MediaState = 'pending' | 'claimed' | 'read' | 'forwarded' | 'aborted' | 'failed'
export type MediaAttachment = {
  /** The upload: the desk RPC's nonce. Attachment `index` of it is `<upload>.<index>`. */
  upload: string
  index: number
  /** The name the person gave it, for display: the prelude and the events. */
  name: string
  mediaType: string
  /** Where the daemon saved it, absolute and resolved, inside `root`. */
  path: string
  /** The upload directory the daemon resolved from the live working directory, pinned. */
  root: string
  state: MediaState
  /** The Read's tool-use id, generated when the attachment is claimed. */
  toolUseId?: string
  reason?: string
  /** The last state whose event the bridge's child took. */
  told?: MediaState
}
export type MediaSnapshot = { shape: 1; attachments: MediaAttachment[] }

/**
 * `lane`: the bridge child's resolved verdict on whether this process is a
 * MAWS lane B session (hooks/mods/bridge.tsx, O12 M3): `match`, the bridge
 * only observes; `mismatch`, it controls. Kept so that the module that
 * loads after a reload holds the verdict this process already has. Only
 * sminos writes or reads it.
 */
export type LaneVerdictKept = 'match' | 'mismatch'

declare module 'claude-code' {
  interface PluginState {
    sminos: { ask: AskSnapshot; btw: string[]; media: MediaSnapshot; lane: LaneVerdictKept }
  }
}
