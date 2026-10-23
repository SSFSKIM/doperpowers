import { message, state } from './bridge-state'
import type { ListedAgent } from './bridge-state'
import { emit } from './bridge-stream'

/**
 * The agents the module did not see spawn (DX5 "For DC8"): those that ran
 * before it loaded (a reload, a resume) and those no `agent.spawn` hook
 * reports (a forked skill), learned from the engine's own list
 * (`$.agent.list()`) and said as `agent` spawn and stop events, so the agent
 * state every resync carries holds them too.
 *
 * The list is read at the module's load (before the first hello, so the
 * child's first snapshot has them), at each heartbeat, when a loop the
 * bridge does not know starts a turn, and every AGENTS_REFRESH_MS while any
 * agent runs.
 *
 * A seeded spawn carries what the list gives and nothing else: its id, its
 * parent, its type, its description, and its name when it has one. An agent
 * an `agent.spawn` hook reports is that hook's to report, with the spawn's
 * whole record; the list only ends it, when the list says it is over or it
 * has left the list (only a finished agent leaves it), and the engine's
 * SubagentStop after that says nothing more.
 */

/**
 * How often the list is read while an agent runs: an agent's end reaches the
 * plane within DC8.G3's second (this, the post, and the plane's own pass).
 */
export const AGENTS_REFRESH_MS = 500
/** The list's words for an agent whose loop is over (AgentStatus); `idle` and `waiting` are a loop alive. */
const ENDED = new Set(['completed', 'failed', 'killed'])

const isRunning = (agent: Record<string, unknown> | undefined) => agent?.running === true

/** What the list says now, folded into the agent state as events. */
export function learnAgents(listed: readonly ListedAgent[]) {
  const present = new Set<string>()
  for (const a of listed) {
    present.add(a.id)
    if (state.cleared.has(a.id)) {
      continue
    }
    const known = state.agents.get(a.id)
    const isOver = ENDED.has(a.status)
    if (known === undefined) {
      // A spawn hook still running reports it, with the spawn's whole record.
      if (state.spawning > 0) {
        continue
      }
      state.listed.add(a.id)
      emit({
        type: 'agent',
        phase: 'spawn',
        agentId: a.id,
        parentAgentId: a.parentId ?? null,
        subagentType: a.type,
        description: a.description,
        ...(a.name !== undefined && { name: a.name }),
      })
      if (isOver) {
        emit({ type: 'agent', phase: 'stop', agentId: a.id, agentType: a.type })
      }
      continue
    }
    state.listed.add(a.id)
    if (isRunning(known) && isOver) {
      emit({ type: 'agent', phase: 'stop', agentId: a.id, agentType: a.type })
    }
  }
  for (const id of state.listed) {
    const known = state.agents.get(id)
    if (!present.has(id) && isRunning(known)) {
      emit({ type: 'agent', phase: 'stop', agentId: id, agentType: known?.subagentType ?? null })
    }
  }
}

/**
 * Reads the list and learns from it; then, while an agent runs, the next read
 * is due. Reads overlap (the heartbeat, a turn's start, the timer): a read is
 * applied only if no read begun after it has been applied already, so an
 * older list never ends an agent a newer one showed running. One begun before
 * a /clear is not this conversation's: what it names that nobody knew is set
 * aside with the rest of the old conversation's agents.
 */
export async function refreshAgents() {
  const list = state.listAgents
  if (list === undefined || state.post === undefined) {
    return
  }
  const asked = ++state.agentReads.asked
  const conversation = state.conversation
  const reading = list()
  state.agentListsInFlight.add(reading)
  try {
    const listed = await reading.finally(() => state.agentListsInFlight.delete(reading))
    await state.clearing
    if (conversation !== state.conversation) {
      setAside(listed)
    } else if (asked > state.agentReads.applied) {
      state.agentReads.applied = asked
      learnAgents(listed)
    }
  } catch (error) {
    state.log?.(`bridge: the agent list was not read: ${message(error)}`)
  }
  watchAgents()
}

/** The agents a list names that this conversation does not know: the conversation before a /clear's. */
function setAside(listed: readonly ListedAgent[]) {
  for (const a of listed) {
    if (!state.agents.has(a.id) && !state.claimed.has(a.id)) {
      state.cleared.add(a.id)
    }
  }
}

/**
 * An agent this conversation's own hooks named (its spawn, its loop's first
 * turn): this conversation's, whatever a list answered at the /clear said. A
 * /clear's retried read is answered after the new conversation may have
 * started agents of its own, which it names alongside the old ones.
 */
export function claimAgent(id: string) {
  state.claimed.add(id)
  state.cleared.delete(id)
}

/**
 * A /clear (before forgetLive): the old conversation's agents are set aside,
 * those it knew and those the engine's list names, since the list goes on
 * naming them for a while: every answer to a read outstanding at the /clear,
 * and a read made now, before the new conversation has any of its own (tried
 * twice; if both fail, the outstanding answers and the agents it knew are all
 * that is set aside). Every read of the list after this waits until each of
 * those answers is in, so none of them can seed an agent they name. The
 * retry may be answered once the new conversation has agents of its own:
 * those its hooks claim (claimAgent) are never set aside, or stop being.
 */
export function forgetAgents() {
  for (const id of [...state.agents.keys(), ...state.listed]) {
    state.cleared.add(id)
  }
  state.listed.clear()
  state.claimed.clear()
  state.conversation++
  const list = state.listAgents
  if (list === undefined) {
    return
  }
  const now = list().catch(() => list())
  const clearing: Promise<void> = Promise.allSettled([now, state.clearing, ...state.agentListsInFlight]).then(([read, ...rest]) => {
    if (read?.status === 'rejected') {
      state.log?.(`bridge: the agent list was not read at the /clear: ${message(read.reason)}`)
    }
    for (const a of [read, ...rest]) {
      if (a?.status === 'fulfilled' && Array.isArray(a.value)) {
        setAside(a.value)
      }
    }
  })
  state.clearing = clearing
  void clearing.then(() => {
    if (state.clearing === clearing) {
      state.clearing = undefined
    }
  })
}

/** The list read again in AGENTS_REFRESH_MS, while any agent runs. */
export function watchAgents() {
  if (state.isAgentsWatched || state.after === undefined || ![...state.agents.values()].some(isRunning)) {
    return
  }
  state.isAgentsWatched = true
  state.after(AGENTS_REFRESH_MS, () => {
    state.isAgentsWatched = false
    void refreshAgents()
  })
}
