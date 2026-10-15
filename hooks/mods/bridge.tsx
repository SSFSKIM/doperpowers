import type { EngineInterface, HookStream, HttpResponse, On, ProcessSpawnChunk, ProcessSpawnResult, SessionStartInput, Timer } from 'claude-code'

/**
 * The bridge (DC2): this session's live events go out, and commands come in,
 * through the session's endpoint, which a child process serves for the
 * session's life (`sminos bridge --session <id>`,
 * skills/sminos/scripts/sminos_bridge.py; the protocol is DX5).
 *
 * The child's stdout is the command channel: its first line is `hello`, naming
 * the socket it serves, and each line after it is one command, which the mod
 * answers with a `result` event. Events go to the socket as `POST /events`,
 * one request in flight at a time, so they arrive in the order they happened
 * and batch themselves under load. A module reload kills the child and runs
 * `session.start` again, which spawns the next.
 *
 * The mod keeps the session's live state itself (open turns, every message
 * still streaming with its text and last chunk index, the subagents), so
 * whenever the child's copy may be wrong (a post was lost, a new child said
 * hello) the next post opens with a `resync` that replaces it.
 */

export const HEARTBEAT_MS = 5_000
/** The longest string an event carries; the rest is in the transcript. */
export const TEXT_CAP = 65_536
const BATCH_MAX = 500
const QUEUE_MAX = 10_000
const RESPAWN_FIRST_MS = 1_000
const RESPAWN_MAX_MS = 60_000
/** A child that lived this long ended for a reason of its own: start again quickly. */
const STABLE_MS = 30_000
/** After a /clear: how often, and how many times, the new session's id is looked for. */
export const CLEAR_POLL_MS = 100
const CLEAR_POLL_TRIES = 50
/** How many polls the old session's last events may take to reach its child before it is stopped. */
const DRAIN_TRIES = 10
/** After a post that failed, the next waits this long. */
const RETRY_MS = 500

type BridgeEvent = Record<string, unknown> & { type: string }
type Command = Record<string, unknown> & { id: string; op: string }
/** A message still streaming, as the child's snapshot carries it (DX4). */
type Streaming = { turnId: string; agentId: string | null; step: number; model: string; text: string; thinking: string; upTo: number }

type BridgeState = {
  /**
   * The calls that outlive a hook, made in session.start: its `$` lives as
   * long as the child's loop does, so posts, timers and restarts run on it.
   */
  post?: (socketPath: string, body: string) => Promise<HttpResponse>
  log?: (text: string) => void
  after?: (ms: number, fn: () => void) => void
  readId?: () => Promise<string>
  /** Stops the child and starts one for this session. */
  restart?: (session: string) => void
  /** What the session start said, sent to each child once it says hello. */
  info?: Record<string, unknown>
  /** The session the child serves, the socket it named, and the child itself. */
  session?: string
  socket?: string
  child?: HookStream<ProcessSpawnChunk, ProcessSpawnResult>
  /** Bumped whenever a child is started or stopped on purpose; a loop of an older one does nothing more. */
  generation: number
  respawnMs: number
  heartbeat?: Timer
  queue: BridgeEvent[]
  isPosting: boolean
  /** A post failed: the next waits for RETRY_MS. */
  isWaiting: boolean
  /**
   * Between a /clear's session.end and the new session's child: nothing is
   * sent (the old child must not get the new session's events), and the live
   * state they build reaches the new child as its first resync.
   */
  isEnding: boolean
  /** The session's live state, the source of every resync. */
  turns: Map<string, Record<string, unknown>>
  messages: Map<string, Streaming>
  agents: Map<string, Record<string, unknown>>
  mainTurn?: string
  /** Main-loop model requests streaming now. */
  steps: number
  /** Tool calls running now, by call. */
  tools: Map<string, string>
  toolCalls: number
}

const fresh = (): BridgeState => ({
  generation: 0,
  respawnMs: RESPAWN_FIRST_MS,
  queue: [],
  isPosting: false,
  isWaiting: false,
  isEnding: false,
  turns: new Map(),
  messages: new Map(),
  agents: new Map(),
  steps: 0,
  tools: new Map(),
  toolCalls: 0,
})

let state = fresh()

/** Forgets everything; for tests, which share this module. */
export function resetBridge() {
  state = fresh()
}

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

/** Cuts `pending + text` into whole lines, keeping the unfinished rest. */
export function splitLines(pending: string, text: string): { lines: string[]; rest: string } {
  const parts = (pending + text).split('\n')
  const rest = parts.pop() ?? ''
  return { lines: parts.filter((l) => l.trim() !== ''), rest }
}

/** Where the session stands, for a command's answer and the heartbeat. */
function turnState() {
  return { mainTurn: state.mainTurn ?? null, isStreaming: state.steps > 0, tools: [...state.tools.values()] }
}

/**
 * A value with every string in it, at any depth, held to TEXT_CAP; `cut`
 * says whether any was.
 */
export function capped(value: unknown): { value: unknown; cut: boolean } {
  if (typeof value === 'string') {
    return value.length > TEXT_CAP ? { value: value.slice(0, TEXT_CAP), cut: true } : { value, cut: false }
  }
  if (Array.isArray(value)) {
    const items = value.map(capped)
    return { value: items.map((i) => i.value), cut: items.some((i) => i.cut) }
  }
  if (typeof value === 'object' && value !== null) {
    const entries = Object.entries(value).map(([k, v]) => [k, capped(v)] as const)
    return { value: Object.fromEntries(entries.map(([k, c]) => [k, c.value])), cut: entries.some(([, c]) => c.cut) }
  }
  return { value, cut: false }
}

const messageKey = (turnId: unknown, agentId: unknown, step: unknown) => `${String(turnId)}|${String(agentId)}|${String(step)}`

/** Folds an event into the session's live state. */
function track(e: BridgeEvent) {
  if (e.type === 'chunk') {
    const m = state.messages.get(messageKey(e.turnId, e.agentId, e.step))
    const chunk = e.chunk as { kind?: string; text?: string }
    if (m !== undefined) {
      if (chunk.kind === 'text') {
        m.text += chunk.text ?? ''
      } else if (chunk.kind === 'thinking') {
        m.thinking += chunk.text ?? ''
      }
      m.upTo = Number(e.chunkIndex)
    }
  } else if (e.type === 'step' && e.phase === 'start') {
    const m: Streaming = { turnId: String(e.turnId), agentId: (e.agentId as string | null) ?? null, step: Number(e.step), model: String(e.model), text: '', thinking: '', upTo: -1 }
    state.messages.set(messageKey(m.turnId, m.agentId, m.step), m)
  } else if (e.type === 'step' && e.phase === 'end') {
    state.messages.delete(messageKey(e.turnId, e.agentId, e.step))
  } else if (e.type === 'turn' && e.phase === 'start') {
    state.turns.set(String(e.turnId), { turnId: e.turnId, agentId: e.agentId, t: e.t })
  } else if (e.type === 'turn' && e.phase === 'complete') {
    state.turns.delete(String(e.turnId))
    for (const [k, m] of state.messages) {
      if (m.turnId === e.turnId) {
        state.messages.delete(k)
      }
    }
  } else if (e.type === 'agent') {
    const { type: _type, phase, t: _t, ...fields } = e
    state.agents.set(String(e.agentId), { ...state.agents.get(String(e.agentId)), ...fields, running: phase !== 'stop' })
  }
}

/** The live state whole: what the child replaces its own with. */
function resyncEvent(): BridgeEvent {
  return {
    type: 'resync',
    turns: [...state.turns.values()],
    streaming: [...state.messages.values()].map((m) => ({ ...m })),
    agents: [...state.agents.values()],
    t: Date.now(),
  }
}

/** Forgets the live state: the session after a /clear starts with none. */
function forgetLive() {
  state.turns.clear()
  state.messages.clear()
  state.agents.clear()
}

/**
 * Events that reached no child: counted in a gap, and the queue replaced by
 * that gap and a resync of the state as it stands now, which covers every
 * event lost and every one queued behind them.
 */
function lose(events: BridgeEvent[]) {
  const dropped = events.reduce((n, e) => n + (e.type === 'gap' ? Number(e.dropped) : e.type === 'resync' ? 0 : 1), 0)
  state.queue = [{ type: 'gap', dropped, t: Date.now() }, resyncEvent()]
}

function emit(event: BridgeEvent) {
  // Nothing is kept for a session with no bridge (an internal fork, a start that failed).
  if (state.post === undefined) {
    return
  }
  const stamped = { ...event, t: Date.now() }
  track(stamped)
  if (state.isEnding) {
    return
  }
  state.queue.push(stamped)
  if (state.queue.length > QUEUE_MAX) {
    lose(state.queue)
  }
  pump()
}

/** Posts what is queued, one request at a time, once a child has said where. */
function pump() {
  const { post, socket: socketPath } = state
  if (post === undefined || socketPath === undefined || state.isPosting || state.isWaiting || state.queue.length === 0) {
    return
  }
  const batch = state.queue.splice(0, BATCH_MAX)
  const generation = state.generation
  let failed = false
  state.isPosting = true
  const lost = (why: string) => {
    failed = true
    state.log?.(`bridge: ${batch.length} events not delivered: ${why}`)
    // A child replaced meanwhile gets its resync at its hello; one being
    // retired after a /clear gets nothing more.
    if (generation === state.generation && !state.isEnding) {
      lose([...batch, ...state.queue])
    }
  }
  post(socketPath, JSON.stringify(batch))
    .then(
      (res) => {
        if (!res.ok) {
          lost(`status ${res.status}`)
        }
      },
      (error: unknown) => lost(message(error)),
    )
    .finally(() => {
      state.isPosting = false
      if (failed && state.after !== undefined) {
        state.isWaiting = true
        state.after(RETRY_MS, () => {
          state.isWaiting = false
          pump()
        })
      } else {
        pump()
      }
    })
}

/** Answers one command line. M2 and M3 add their ops here. */
function runCommand(command: Command) {
  const answer = (fields: Record<string, unknown>) => emit({ type: 'result', id: command.id, op: command.op, ...fields })
  switch (command.op) {
    case 'ping':
      answer({ ok: true, result: { pong: true, state: turnState() } })
      return
    default:
      answer({ ok: false, error: `unknown op: ${command.op}` })
  }
}

function onLine($: EngineInterface, generation: number, line: string) {
  let parsed: unknown
  try {
    parsed = JSON.parse(line)
  } catch {
    $.ui.log(`bridge: a line from the child that is not JSON: ${line.slice(0, 200)}`, { to: 'debug' })
    return
  }
  if (generation !== state.generation || typeof parsed !== 'object' || parsed === null) {
    return
  }
  const msg = parsed as Record<string, unknown>
  if (msg.op === 'hello' && typeof msg.socket === 'string') {
    state.socket = msg.socket
    // A new child knows nothing of the session: what it started as, then
    // where it stands. What was queued for no child is in that state.
    state.queue = [{ type: 'session', phase: 'start', session: state.session, ...state.info, t: Date.now() }, resyncEvent()]
    pump()
    return
  }
  if (typeof msg.id === 'string' && typeof msg.op === 'string') {
    runCommand(msg as Command)
  }
}

/**
 * Starts the session's child and reads its lines until it ends; one that
 * ended on its own is started again, after a second, doubling while it keeps
 * ending at once, up to a minute.
 */
function startChild($: EngineInterface, session: string) {
  const generation = ++state.generation
  state.session = session
  state.socket = undefined
  const startedAt = Date.now()
  void (async () => {
    let pending = ''
    try {
      const child = $.process.spawn({ argv: [`${$.plugin.root}/skills/sminos/scripts/sminos`, 'bridge', '--session', session] })
      state.child = child
      for await (const piece of child) {
        if (piece.stream === 'stderr') {
          $.ui.log(`bridge: ${piece.text.trimEnd()}`, { to: 'debug' })
          continue
        }
        const { lines, rest } = splitLines(pending, piece.text)
        pending = rest
        for (const line of lines) {
          onLine($, generation, line)
        }
      }
      const ended = await child.result
      $.ui.log(`bridge: the child ended (${ended.signal ?? ended.code})`, { to: 'debug' })
    } catch (error) {
      $.ui.log(`bridge: the child failed: ${message(error)}`, { to: 'debug' })
    }
    if (generation !== state.generation) {
      return
    }
    state.socket = undefined
    state.child = undefined
    if (Date.now() - startedAt >= STABLE_MS) {
      state.respawnMs = RESPAWN_FIRST_MS
    }
    const delay = state.respawnMs
    state.respawnMs = Math.min(delay * 2, RESPAWN_MAX_MS)
    $.clock.after(delay, () => {
      if (generation === state.generation) {
        startChild($, session)
      }
    })
  })()
}

function stopChild() {
  state.generation++
  const child = state.child
  state.child = undefined
  state.socket = undefined
  // Leaving the stream kills the child.
  void child?.return({ code: null, signal: null })
}

/**
 * Moves the bridge to the session that took this one's place: once the old
 * child has its last events (or after DRAIN_TRIES polls), it is stopped and a
 * child for the new session started, whose hello resyncs what happened since.
 */
function switchSession(session: string, tries = 0) {
  if ((state.queue.length > 0 || state.isPosting) && tries < DRAIN_TRIES && state.after !== undefined) {
    state.after(CLEAR_POLL_MS, () => switchSession(session, tries + 1))
    return
  }
  if (session === state.session) {
    return
  }
  if (!state.isEnding) {
    // Found by the heartbeat, with no session.end before it.
    forgetLive()
  }
  state.isEnding = false
  state.queue = []
  state.restart?.(session)
}

/**
 * After a /clear's session.end: the new session's id, looked for every
 * CLEAR_POLL_MS (the heartbeat is the fallback). If the id never changes, this
 * session goes on, resynced.
 */
function awaitNextSession(tries = 0) {
  if (!state.isEnding || state.readId === undefined) {
    return
  }
  const old = state.session
  void state.readId().then(
    (session) => {
      if (!state.isEnding) {
        return
      }
      if (session !== old) {
        switchSession(session)
      } else if (tries < CLEAR_POLL_TRIES) {
        state.after?.(CLEAR_POLL_MS, () => awaitNextSession(tries + 1))
      } else {
        state.isEnding = false
        state.queue.push(resyncEvent())
        pump()
      }
    },
    (error: unknown) => state.log?.(`bridge: the session id could not be read: ${message(error)}`),
  )
}

/** The heartbeat; and the session's id read again, the fallback for a change of session missed. */
async function beat($: EngineInterface) {
  try {
    const session = await $.session.id()
    if (session !== state.session) {
      switchSession(session)
    }
  } catch (error) {
    $.ui.log(`bridge: the session id could not be read: ${message(error)}`, { to: 'debug' })
  }
  emit({ type: 'heartbeat', state: turnState() })
}

export async function bridgeStart($: EngineInterface, e: SessionStartInput) {
  // derive's headless fork of a session is never a member, and needs no bridge.
  if ((await $.env.get('SMNS_INTERNAL')) !== undefined) {
    return
  }
  state.post = (socketPath, body) =>
    $.http.fetch('http://bridge/events', { method: 'POST', socketPath, headers: { 'content-type': 'application/json' }, body })
  state.log = (text) => $.ui.log(text, { to: 'debug' })
  state.after = (ms, fn) => void $.clock.after(ms, fn)
  state.readId = () => $.session.id()
  state.restart = (session) => {
    stopChild()
    startChild($, session)
  }
  state.info = {
    cwd: e.cwd,
    surface: e.surface,
    isInteractive: e.isInteractive,
    model: await $.session.model(),
    version: (await $.session.version()).version,
  }
  stopChild()
  startChild($, await $.session.id())
  state.heartbeat?.cancel()
  state.heartbeat = $.clock.every(HEARTBEAT_MS, () => void beat($))
}

const RESERVED = new Set(['tool', 'tool_use_id', 'consent', 'agentId', 'requestMeta'])

/** A tool call's own arguments, every string in them held to TEXT_CAP. */
function toolInput(e: Record<string, unknown>): { value: unknown; cut: boolean } {
  return capped(Object.fromEntries(Object.entries(e).filter(([k]) => !RESERVED.has(k))))
}

/**
 * Registered first in register.tsx, so its hooks are the outermost of the
 * plugin's: what they report is what the session showed and recorded. Each
 * event is taken with a matcher that matches every input, since the other
 * mods hold the unmatched registrations and the engine admits one per event
 * per module.
 */
export function registerBridge(on: On) {
  on('session.start', { cwd: /^/ }, async ($, e, next) => {
    const started = await next(e)
    try {
      await bridgeStart($, e)
    } catch (error) {
      $.ui.log(`bridge: not started: ${message(error)}`, { to: 'debug' })
    }
    return started
  })

  // A /clear ends the conversation and goes on under a new id with no
  // session.start: the old child gets this end and nothing after it.
  on('session.end', async (_, e, next) => {
    emit({ type: 'session', phase: 'end', reason: e.reason })
    if (e.reason === 'clear' && state.post !== undefined) {
      state.isEnding = true
      forgetLive()
      awaitNextSession()
    }
    return next(e)
  })

  on('turn.start', { turnId: /^/ }, (_, e, next) => {
    if (e.agentId === undefined) {
      state.mainTurn = e.turnId
    }
    const text = capped(e.text)
    emit({ type: 'turn', phase: 'start', turnId: e.turnId, agentId: e.agentId ?? null, text: text.value, ...(text.cut && { truncated: true }) })
    return next(e)
  })

  on('turn.complete', { turnId: /^/ }, async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && state.mainTurn === e.turnId) {
      state.mainTurn = undefined
    }
    emit({ type: 'turn', phase: 'complete', turnId: e.turnId, agentId: e.agentId ?? null, reason: e.reason, usage: e.usage ?? null })
    if (e.agentId === undefined) {
      try {
        const usage = await $.session.usage()
        emit({ type: 'usage', context: usage.context, cost: usage.cost ?? null })
      } catch (error) {
        $.ui.log(`bridge: usage not read: ${message(error)}`, { to: 'debug' })
      }
    }
    return result
  })

  // Every model request of the main loop and of every subagent: each chunk
  // as the engine streamed it, tagged with its message (turn, agent, step) and
  // its index there; the engine's own opaque items are left out.
  on('turn.step', { turnId: /^/ }, async function* (_, e, next) {
    const tag = { turnId: e.turnId, agentId: e.agentId ?? null, step: e.index }
    const isMain = e.agentId === undefined
    emit({ type: 'step', phase: 'start', ...tag, model: e.model, effort: e.effort ?? null, messageCount: e.messageCount })
    if (isMain) {
      state.steps++
    }
    let chunkIndex = 0
    let stopReason: unknown = null
    let usage: unknown = null
    try {
      const stream = next(e)
      for await (const chunk of stream) {
        if (chunk.kind !== 'engine') {
          emit({ type: 'chunk', ...tag, chunkIndex: chunkIndex++, chunk })
        }
        yield chunk
      }
      const result = await stream.result
      stopReason = result.stopReason
      usage = result.usage
      return result
    } finally {
      if (isMain) {
        state.steps--
      }
      emit({ type: 'step', phase: 'end', ...tag, stopReason, usage })
    }
  })

  on('tool.call', { tool: /^/ }, async (_, e, next) => {
    const call = `${e.tool_use_id ?? ''}#${++state.toolCalls}`
    const base = { toolUseId: e.tool_use_id || null, tool: e.tool, agentId: e.agentId ?? null }
    const input = toolInput(e as Record<string, unknown>)
    emit({ type: 'tool', phase: 'call', ...base, input: input.value, ...(input.cut && { truncated: true }) })
    state.tools.set(call, String(e.tool))
    try {
      const result = await next(e)
      const text = capped(result.text)
      const denied = capped(result.deny)
      emit({
        type: 'tool',
        phase: 'result',
        ...base,
        isError: result.isError === true,
        ...(result.deny !== undefined && { denied: denied.value }),
        ...(typeof result.text === 'string' && { text: text.value }),
        ...((text.cut || denied.cut) && { truncated: true }),
      })
      return result
    } finally {
      state.tools.delete(call)
    }
  }).catch((_, e, next) => next(e))

  on('agent.spawn', { tool_use_id: /^/ }, async (_, e, next) => {
    const result = await next(e)
    if (result.agentId !== undefined) {
      emit({
        type: 'agent',
        phase: 'spawn',
        agentId: result.agentId,
        parentAgentId: e.parentAgentId ?? null,
        subagentType: e.subagentType,
        description: e.description,
        name: e.name ?? null,
        background: e.background,
        model: result.model,
        toolUseId: e.tool_use_id || null,
      })
    }
    return result
  })

  on('classic.SubagentStop', { hook_event_name: 'SubagentStop' }, async (_, e, next) => {
    emit({ type: 'agent', phase: 'stop', agentId: e.agent_id, agentType: e.agent_type })
    return next(e)
  })
}
