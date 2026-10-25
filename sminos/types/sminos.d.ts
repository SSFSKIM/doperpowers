/**
 * sminos's contract: the one value it publishes in `$.state`, held by the
 * host for the session.
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

declare module 'claude-code' {
  interface PluginState {
    sminos: { ask: AskSnapshot }
  }
}
