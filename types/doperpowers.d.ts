/**
 * doperpowers' values in `$.state`, held by the host for the session.
 *
 * `ask`: the ask mod's async asks and the answers on their way to the model
 * (hooks/mods/ask.tsx), kept so that a reload of the module takes them up.
 */
export type AskSnapshot = {
  shape: 1
  /** The session's async asks, oldest first: the call's id, its questions, and the engine's text once answered. */
  asks: {
    id: string
    questions: { question: string; header: string; options: { label: string; description: string; preview?: string }[]; multiSelect: boolean }[]
    status: 'open' | 'answered'
    answer?: string
  }[]
  /** The answers that have not reached the model, in the order given: the call's id and the delivery text. */
  undelivered: { id: string; text: string }[]
  isTurnRunning: boolean
  /** Where the session's pasted pictures are kept, once the session start named it. */
  store?: { slug: string; sessionId: string; root?: string | null }
}

declare module 'claude-code' {
  interface PluginState {
    doperpowers: { ask: AskSnapshot }
  }
}
