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
 */

export const HEARTBEAT_MS = 5_000
/** The longest text an event carries in one field; the rest is in the transcript. */
export const TEXT_CAP = 65_536
const BATCH_MAX = 500
const QUEUE_MAX = 10_000
const RESPAWN_FIRST_MS = 1_000
const RESPAWN_MAX_MS = 60_000
/** A child that lived this long ended for a reason of its own: start again quickly. */
const STABLE_MS = 30_000

type BridgeEvent = Record<string, unknown> & { type: string }
type Command = Record<string, unknown> & { id: string; op: string }

type BridgeState = {
  /**
   * Posting a batch and logging a line, made in session.start: its `$`
   * outlives every hook, as the child's loop does, so the posts run on it.
   */
  post?: (socketPath: string, body: string) => Promise<HttpResponse>
  log?: (text: string) => void
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
  /** Events lost to failed posts, said in the next. */
  dropped: number
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
  dropped: 0,
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

/** A string held to TEXT_CAP, and whether it was cut. */
function capped(text: string): [string, boolean] {
  return text.length > TEXT_CAP ? [text.slice(0, TEXT_CAP), true] : [text, false]
}

function emit(event: BridgeEvent) {
  // Nothing is kept for a session with no bridge (an internal fork, a start that failed).
  if (state.post === undefined) {
    return
  }
  state.queue.push({ ...event, t: Date.now() })
  if (state.queue.length > QUEUE_MAX) {
    state.dropped += state.queue.length - QUEUE_MAX
    state.queue.splice(0, state.queue.length - QUEUE_MAX)
  }
  pump()
}

/** Posts what is queued, one request at a time, once a child has said where. */
function pump() {
  const { post, socket: socketPath } = state
  if (post === undefined || socketPath === undefined || state.isPosting || state.queue.length === 0) {
    return
  }
  const batch = state.queue.splice(0, BATCH_MAX)
  if (state.dropped > 0) {
    batch.unshift({ type: 'gap', dropped: state.dropped, t: Date.now() })
    state.dropped = 0
  }
  state.isPosting = true
  const lost = (why: string) => {
    state.dropped += batch.reduce((n, e) => n + (e.type === 'gap' ? Number(e.dropped) : 1), 0)
    state.log?.(`bridge: ${batch.length} events not delivered: ${why}`)
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
      pump()
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
    // The child knows nothing of the session yet: what it started as comes first.
    state.queue.unshift({ type: 'session', phase: 'start', session: state.session, ...state.info, t: Date.now() })
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

/** The heartbeat; and the session's id read again, since a /clear changes it with no session.start. */
async function beat($: EngineInterface) {
  try {
    const session = await $.session.id()
    if (session !== state.session) {
      stopChild()
      startChild($, session)
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

/** A tool call's own arguments, each string held to TEXT_CAP. */
function toolInput(e: Record<string, unknown>): { input: Record<string, unknown>; truncated: boolean } {
  let truncated = false
  const input: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(e)) {
    if (RESERVED.has(key)) {
      continue
    }
    if (typeof value === 'string') {
      const [text, cut] = capped(value)
      truncated ||= cut
      input[key] = text
    } else {
      input[key] = value
    }
  }
  return { input, truncated }
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

  on('session.end', async (_, e, next) => {
    emit({ type: 'session', phase: 'end', reason: e.reason })
    return next(e)
  })

  on('turn.start', { turnId: /^/ }, (_, e, next) => {
    if (e.agentId === undefined) {
      state.mainTurn = e.turnId
    }
    emit({ type: 'turn', phase: 'start', turnId: e.turnId, agentId: e.agentId ?? null, text: capped(e.text)[0] })
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
    const { input, truncated } = toolInput(e as Record<string, unknown>)
    emit({ type: 'tool', phase: 'call', ...base, input, ...(truncated && { truncated }) })
    state.tools.set(call, String(e.tool))
    try {
      const result = await next(e)
      const [text, cut] = typeof result.text === 'string' ? capped(result.text) : [undefined, false]
      emit({
        type: 'tool',
        phase: 'result',
        ...base,
        isError: result.isError === true,
        ...(result.deny !== undefined && { denied: capped(result.deny)[0] }),
        ...(text !== undefined && { text }),
        ...(cut && { truncated: true }),
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
