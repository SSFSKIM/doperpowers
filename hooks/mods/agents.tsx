import type { EngineInterface, On, RenderElement, RenderInput, Timer } from 'claude-code'

/**
 * One agent of the session as the pane draws it: what `$.agent.list()` says
 * of it, plus what the mod learned from the spawn (its model, when it
 * started and ended) or from the meta file the engine leaves beside its
 * transcript.
 */
export type AgentRow = {
  id: string
  description: string
  type: string
  /** `running`, `pending`, `completed`, `failed`, `killed`: the engine's own. */
  status: string
  /** The agent whose loop spawned it; absent when the main loop did. */
  parentId?: string
  model?: string
  startedAt?: number
  endedAt?: number
}

export type TreeRow = AgentRow & { depth: number }

/**
 * Orders the agents as a tree: each under the one that spawned it, siblings
 * in the order given. An agent whose parent is not in the list sits at the
 * top level.
 */
export function buildTree(rows: readonly AgentRow[]): TreeRow[] {
  const ids = new Set(rows.map((row) => row.id))
  const children = new Map<string | undefined, AgentRow[]>()
  for (const row of rows) {
    const parent = row.parentId !== undefined && ids.has(row.parentId) ? row.parentId : undefined
    const list = children.get(parent) ?? []
    list.push(row)
    children.set(parent, list)
  }

  const out: TreeRow[] = []
  const walk = (parent: string | undefined, depth: number) => {
    for (const row of children.get(parent) ?? []) {
      out.push({ ...row, depth })
      walk(row.id, depth + 1)
    }
  }
  walk(undefined, 0)
  return out
}

/**
 * One line of an agent's transcript as the pane shows it: the task it was
 * given, what it said, a tool call in one line, the first line of a tool's
 * result, or a message the engine slipped it (a task notification).
 */
export type Entry =
  | { kind: 'prompt'; text: string }
  | { kind: 'text'; text: string }
  | { kind: 'tool'; text: string }
  | { kind: 'result'; text: string; isError: boolean }
  | { kind: 'note'; text: string }

const KEY_ARG: Record<string, string> = {
  Bash: 'command',
  Read: 'file_path',
  Edit: 'file_path',
  Write: 'file_path',
  NotebookEdit: 'notebook_path',
  Agent: 'description',
  Grep: 'pattern',
  Glob: 'pattern',
  Skill: 'skill',
  WebFetch: 'url',
  WebSearch: 'query',
  SendMessage: 'to',
}

/**
 * A tool call in one line, `Name(arg)`: the one argument that tells calls
 * of that tool apart (the command, the path, the pattern), else the first
 * string argument, else the bare name. Whitespace runs collapse.
 */
export function toolLine(name: string, input: unknown): string {
  const args = input !== null && typeof input === 'object' ? (input as Record<string, unknown>) : {}
  const key = KEY_ARG[name]
  let arg = key !== undefined ? args[key] : undefined
  if (typeof arg !== 'string') {
    arg = Object.values(args).find((value) => typeof value === 'string')
  }
  if (typeof arg !== 'string' || arg.trim() === '') {
    return name
  }
  return `${name}(${arg.trim().replace(/\s+/g, ' ')})`
}

const PROMPT_LINES = 3

function firstLine(text: string): string {
  return text.split('\n').find((line) => line.trim() !== '')?.trim() ?? ''
}

function blockText(content: unknown): string {
  if (typeof content === 'string') {
    return content
  }
  if (!Array.isArray(content)) {
    return ''
  }
  return content
    .filter((block) => block !== null && typeof block === 'object' && (block as { type?: unknown }).type === 'text')
    .map((block) => String((block as { text?: unknown }).text ?? ''))
    .join('\n')
}

/**
 * Reads an agent's transcript file (JSON lines as the engine writes them)
 * into the entries the pane draws. Thinking, attachments and lines that are
 * not JSON are left out. Past `cap` entries the oldest are dropped and
 * counted in `skipped`.
 */
export function summarize(jsonl: string, cap: number): { entries: Entry[]; skipped: number } {
  const entries: Entry[] = []
  let sawPrompt = false

  for (const line of jsonl.split('\n')) {
    if (line.trim() === '') {
      continue
    }
    let row: { type?: unknown; message?: { content?: unknown } }
    try {
      row = JSON.parse(line)
    } catch {
      continue
    }
    const content = row.message?.content

    if (row.type === 'user') {
      if (Array.isArray(content)) {
        for (const block of content) {
          if (block === null || typeof block !== 'object') {
            continue
          }
          const { type, is_error: isError } = block as { type?: unknown; is_error?: unknown }
          if (type === 'tool_result') {
            const text = firstLine(blockText((block as { content?: unknown }).content))
            entries.push({ kind: 'result', text, isError: isError === true })
          }
        }
      }
      const text = blockText(content)
      if (text.trim() === '') {
        continue
      }
      if (!sawPrompt) {
        sawPrompt = true
        const lines = text.trim().split('\n')
        const head = lines.slice(0, PROMPT_LINES).join('\n')
        entries.push({ kind: 'prompt', text: lines.length > PROMPT_LINES ? `${head} …` : head })
      } else {
        entries.push({ kind: 'note', text: firstLine(text) })
      }
    } else if (row.type === 'assistant' && Array.isArray(content)) {
      for (const block of content) {
        if (block === null || typeof block !== 'object') {
          continue
        }
        const { type } = block as { type?: unknown }
        if (type === 'text') {
          const text = String((block as { text?: unknown }).text ?? '').trim()
          if (text !== '') {
            entries.push({ kind: 'text', text })
          }
        } else if (type === 'tool_use') {
          const { name, input } = block as { name?: unknown; input?: unknown }
          entries.push({ kind: 'tool', text: toolLine(String(name ?? '?'), input) })
        }
      }
    }
  }

  const skipped = Math.max(0, entries.length - cap)
  return { entries: entries.slice(skipped), skipped }
}

/**
 * The footer button's label: how many subagents still run and how many are
 * done, never a total that drowns the running count in a long session's
 * accumulated finished agents.
 */
export function buttonLabel(running: number, done: number): string {
  if (done === 0) {
    return `${running} running`
  }
  if (running === 0) {
    return `${done} done`
  }
  return `${running} running · ${done} done`
}

/**
 * A duration as a person glances at it: seconds under a minute, then
 * minutes and seconds, then hours and minutes.
 */
export function elapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s < 60) {
    return `${s}s`
  }
  const m = Math.floor(s / 60)
  if (m < 60) {
    return `${m}m${String(s % 60).padStart(2, '0')}s`
  }
  return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}m`
}

/**
 * Where the engine keeps the transcripts of a session's subagents: beside
 * the session's own transcript, in a directory named by its id.
 */
export function subagentsDir(transcriptPath: string): string {
  return `${transcriptPath.replace(/\.jsonl$/, '')}/subagents`
}

/**
 * A disk-seeded agent's start time: its transcript's first line, which is
 * timestamped when the agent starts, so siblings order by when they were
 * spawned. `metaMtimeMs` (the meta file's own time) is the fallback for a
 * transcript that is missing or does not parse — the meta file is rewritten
 * as the agent ends, so on its own it would order siblings by when they
 * finished instead.
 */
export function startTimeOf(transcriptHead: string, metaMtimeMs: number): number {
  const first = transcriptHead.split('\n', 1)[0]
  if (first !== undefined && first.trim() !== '') {
    try {
      const row = JSON.parse(first) as { timestamp?: unknown }
      if (typeof row.timestamp === 'string') {
        const t = Date.parse(row.timestamp)
        if (!Number.isNaN(t)) {
          return t
        }
      }
    } catch {
      // not JSON: fall through to the meta file's time
    }
  }
  return metaMtimeMs
}

const PANE = 'agents'
const BUTTON = 'agents-button'
const ROW = /^agent:/
/** Entries drawn of one transcript; older ones are counted, not drawn. */
const CAP = 300
/** Characters drawn of one text entry; `$.fs.read` itself stops at 4 MiB. */
const TEXT_CAP = 2000
const MAX_READ = 4 * 1024 * 1024
const POLL_MS = 1000
const TICK_MS = 30_000

const isRunning = (status: string) => status === 'running' || status === 'pending'
const isDone = (status: string) => status === 'completed' || status === 'failed' || status === 'killed'

const GLYPH: Record<string, { char: string; color?: string; dim: boolean }> = {
  running: { char: '●', color: 'cyan', dim: false },
  pending: { char: '◌', dim: true },
  completed: { char: '✓', dim: true },
  failed: { char: '✗', color: 'red', dim: false },
  killed: { char: '○', dim: true },
}

type Shown = {
  id: string
  size: number
  entries: Entry[]
  skipped: number
  tooLarge: boolean
  missing: boolean
}

type State = {
  /**
   * Every agent the list has named this session, by id, in the order first
   * seen: the engine drops a finished agent from its list after a while,
   * and the tree keeps it.
   */
  seen: Map<string, AgentRow>
  /** What the mod learned of each agent from events, by id. */
  known: Map<string, { model?: string; startedAt?: number; endedAt?: number }>
  /** Agents read from the meta files on disk, by id: the session's past. */
  disk: Map<string, AgentRow>
  /** The session's `subagents/` directory, once known. */
  dir?: string
  isOpen: boolean
  isFocused: boolean
  selected?: string
  shown?: Shown
  poll?: Timer
  tick?: Timer
  /** True while a period's reads are still running: the next period skips. */
  isPolling: boolean
  signature: string
}

function rows(state: State): AgentRow[] {
  const older = [...state.disk.values()]
    .filter((row) => !state.seen.has(row.id))
    .sort((a, b) => (a.startedAt ?? 0) - (b.startedAt ?? 0))
  const live = [...state.seen.values()].map((row): AgentRow => {
    const known = state.known.get(row.id)
    const meta = state.disk.get(row.id)
    return {
      ...row,
      model: known?.model ?? meta?.model,
      startedAt: known?.startedAt ?? meta?.startedAt,
      endedAt: known?.endedAt,
    }
  })
  return [...older, ...live]
}

const running = (state: State) => [...state.seen.values()].filter((row) => isRunning(row.status)).length
const done = (state: State) => [...state.seen.values()].filter((row) => isDone(row.status)).length

/**
 * Re-reads the engine's list, stamps what it learns, and asks for a redraw
 * when an agent appeared or changed status.
 */
async function refresh($: EngineInterface, state: State) {
  let listed
  try {
    listed = await $.agent.list()
  } catch {
    return
  }
  const now = Date.now()
  const present = new Set<string>()
  for (const agent of listed) {
    present.add(agent.id)
    state.seen.set(agent.id, {
      id: agent.id,
      description: agent.description || agent.type,
      type: agent.type,
      status: agent.status,
      parentId: agent.parentId,
    })
    const known = state.known.get(agent.id) ?? {}
    known.startedAt ??= now
    if (isDone(agent.status)) {
      known.endedAt ??= now
    } else {
      // A background agent's loop runs a turn per wake (its child's report
      // wakes it again), so a turn's end is not its end until the engine says.
      known.endedAt = undefined
    }
    state.known.set(agent.id, known)
  }
  for (const row of state.seen.values()) {
    if (!present.has(row.id) && isRunning(row.status)) {
      // Only a finished agent leaves the list.
      row.status = 'completed'
      const known = state.known.get(row.id) ?? {}
      known.endedAt ??= now
      state.known.set(row.id, known)
    }
  }
  const signature = [...state.seen.values()].map((row) => `${row.id}:${row.status}`).join(',')
  if (signature !== state.signature) {
    state.signature = signature
    $.ui.invalidate('ui.render')
  }
}

/**
 * Reads the meta file the engine leaves beside each transcript on disk, so
 * a resumed session's earlier agents are in the tree too.
 */
async function seed($: EngineInterface, state: State) {
  if (state.dir === undefined || !(await $.fs.exists(state.dir))) {
    return
  }
  let entries
  try {
    entries = await $.fs.list(state.dir)
  } catch {
    return
  }
  for (const entry of entries) {
    if (!entry.name.startsWith('agent-') || !entry.name.endsWith('.meta.json')) {
      continue
    }
    const id = entry.name.slice('agent-'.length, -'.meta.json'.length)
    if (state.disk.has(id)) {
      continue
    }
    try {
      const path = `${state.dir}/${entry.name}`
      const meta = JSON.parse(await $.fs.read(path)) as Record<string, unknown>
      const metaMtimeMs = (await $.fs.stat(path)).mtimeMs
      let transcriptHead = ''
      try {
        transcriptHead = await $.fs.read(`${state.dir}/agent-${id}.jsonl`)
      } catch {
        // no transcript on disk: the meta file's own time is what's left
      }
      const startedAt = startTimeOf(transcriptHead, metaMtimeMs)
      const type = typeof meta.agentType === 'string' ? meta.agentType : 'agent'
      state.disk.set(id, {
        id,
        description: typeof meta.description === 'string' && meta.description !== '' ? meta.description : type,
        type,
        status: 'completed',
        parentId: typeof meta.parentAgentId === 'string' ? meta.parentAgentId : undefined,
        model: typeof meta.model === 'string' ? meta.model : undefined,
        startedAt,
      })
    } catch {
      continue
    }
  }
}

/**
 * Reads the selected agent's transcript when it grew since the last read.
 * Resolves true when the pane has something new to draw.
 */
async function load($: EngineInterface, state: State, id: string): Promise<boolean> {
  const empty = { id, size: 0, entries: [], skipped: 0, tooLarge: false, missing: false }
  if (state.dir === undefined) {
    state.shown = { ...empty, missing: true }
    return true
  }
  const path = `${state.dir}/agent-${id}.jsonl`
  let size: number
  try {
    size = (await $.fs.stat(path)).size
  } catch {
    const changed = state.shown?.id !== id || !state.shown.missing
    state.shown = { ...empty, missing: true }
    return changed
  }
  if (state.shown?.id === id && state.shown.size === size) {
    return false
  }
  if (size > MAX_READ) {
    state.shown = { ...empty, size, tooLarge: true }
    return true
  }
  let text: string
  try {
    text = await $.fs.read(path)
  } catch {
    return false // gone or refused between the stat and the read: next period
  }
  const { entries, skipped } = summarize(text, CAP)
  state.shown = { ...empty, size, entries, skipped }
  return true
}

function follow($: EngineInterface, state: State) {
  if (!state.isFocused) {
    void $.ui.scroll({ in: PANE, to: 'end' })
  }
}

function startPolling($: EngineInterface, state: State) {
  stopPolling(state)
  state.poll = $.clock.every(POLL_MS, async () => {
    if (state.isPolling) {
      return
    }
    state.isPolling = true
    try {
      await refresh($, state)
      if (state.selected !== undefined && (await load($, state, state.selected))) {
        $.ui.invalidate('ui.render')
        follow($, state)
      }
    } catch {
      // A period that failed is a period skipped; the next one reads again.
    } finally {
      state.isPolling = false
    }
  })
  state.tick = $.clock.every(TICK_MS, () => {
    if (running(state) > 0) {
      $.ui.invalidate('ui.render')
    }
  })
}

function stopPolling(state: State) {
  state.poll?.cancel()
  state.tick?.cancel()
  state.poll = undefined
  state.tick = undefined
  state.isPolling = false
}

function timeOf(row: AgentRow): string {
  if (row.startedAt === undefined) {
    return ''
  }
  if (isRunning(row.status)) {
    return elapsed(Date.now() - row.startedAt)
  }
  return row.endedAt === undefined ? '' : elapsed(row.endedAt - row.startedAt)
}

function drawPane($: EngineInterface, state: State, e: RenderInput<'Pane'>): RenderElement {
  const { Box, Text, Button } = $.ui.resolve(e)
  state.isFocused = e.props.isFocused
  const width = e.props.bodyColumns
  const inView = e.props.view.agentId
  const tree = buildTree(rows(state))
  const shown = state.shown
  const current = state.selected === undefined ? undefined : tree.find((row) => row.id === state.selected)

  return (
    <Box flexDirection="column">
      {tree.length === 0 ? <Text dimColor>no agents yet</Text> : null}
      {tree.map((row) => {
        const glyph = GLYPH[row.status] ?? { char: '·', dim: true }
        const isSelected = row.id === state.selected
        const detail = [row.type, row.model].filter((part) => part !== undefined).join(' · ')
        return (
          <Box key={`row:${row.id}`} paddingLeft={row.depth * 2}>
            <Text color={isSelected ? undefined : glyph.color} dimColor={!isSelected && glyph.dim}>
              {isSelected ? '▸ ' : `${glyph.char} `}
            </Text>
            <Button
              key={`agent:${row.id}`}
              label={row.description}
              dimColor={!isRunning(row.status) && !isSelected}
              onPress={() => {
                state.selected = isSelected ? undefined : row.id
                state.shown = undefined
              }}
            />
            <Text dimColor wrap="truncate-end">
              {`  ${detail}  ${timeOf(row)}`}
              {row.id === inView ? '  ◀ in view' : ''}
            </Text>
          </Box>
        )
      })}
      {current !== undefined ? (
        <Box flexDirection="column" marginTop={1}>
          <Text dimColor>{'─'.repeat(Math.max(1, width))}</Text>
          <Box>
            <Text bold>{current.description}</Text>
            <Text dimColor wrap="truncate-end">
              {`  ${[current.type, current.model, current.status].filter((part) => part !== undefined).join(' · ')}`}
            </Text>
          </Box>
          {shown === undefined || shown.id !== current.id ? (
            <Text dimColor>reading…</Text>
          ) : shown.missing ? (
            <Text dimColor>no transcript on disk</Text>
          ) : shown.tooLarge ? (
            <Text dimColor>{`transcript too large to read (${Math.round(shown.size / 1048576)} MiB)`}</Text>
          ) : (
            <Box flexDirection="column">
              {shown.skipped > 0 ? <Text dimColor>{`… ${shown.skipped} earlier entries`}</Text> : null}
              {shown.entries.map((entry, i) => {
                const text = entry.text.length > TEXT_CAP ? `${entry.text.slice(0, TEXT_CAP)} …` : entry.text
                switch (entry.kind) {
                  case 'prompt':
                    return (
                      <Text key={`e:${i}`} dimColor wrap="wrap">
                        {`> ${text}`}
                      </Text>
                    )
                  case 'text':
                    return (
                      <Text key={`e:${i}`} wrap="wrap">
                        {text}
                      </Text>
                    )
                  case 'tool':
                    return (
                      <Text key={`e:${i}`} wrap="truncate-end">
                        {text}
                      </Text>
                    )
                  case 'result':
                    return (
                      <Text key={`e:${i}`} color={entry.isError ? 'red' : undefined} dimColor={!entry.isError} wrap="truncate-end">
                        {`  ⎿ ${text}`}
                      </Text>
                    )
                  case 'note':
                    return (
                      <Text key={`e:${i}`} dimColor wrap="truncate-end">
                        {`> ${text}`}
                      </Text>
                    )
                }
              })}
            </Box>
          )}
        </Box>
      ) : null}
    </Box>
  )
}

/**
 * Registers the agents pane: a button among the footer's mode labels,
 * from the session's first subagent on, that opens a pane
 * drawing the session's agents as the tree they spawned in; a press on one
 * draws its transcript beneath the tree, following the tail while it runs.
 */
export function registerAgents(on: On) {
  const state: State = {
    seen: new Map(),
    known: new Map(),
    disk: new Map(),
    isOpen: false,
    isFocused: false,
    isPolling: false,
    signature: '',
  }

  // The engine keeps each agent's transcript beside the session's own, under
  // `<transcript>/subagents/`; every classic payload names that transcript.
  // On a resumed session the directory already holds the earlier agents.
  on('classic.SessionStart', async ($, e, next) => {
    if (state.dir === undefined) {
      state.dir = subagentsDir(e.transcript_path)
      await seed($, state)
      if (state.disk.size > 0) {
        $.ui.invalidate('ui.render')
      }
    }
    return next(e)
  })

  on('classic.SubagentStart', async ($, e, next) => {
    state.dir ??= subagentsDir(e.transcript_path)
    const known = state.known.get(e.agent_id) ?? {}
    known.startedAt ??= Date.now()
    state.known.set(e.agent_id, known)
    await refresh($, state)
    return next(e)
  })

  on('classic.SubagentStop', async ($, e, next) => {
    const known = state.known.get(e.agent_id) ?? {}
    known.endedAt = Date.now()
    state.known.set(e.agent_id, known)
    await refresh($, state)
    return next(e)
  })

  on('agent.spawn', async ($, e, next) => {
    const result = await next(e)
    if (result.agentId !== undefined) {
      const known = state.known.get(result.agentId) ?? {}
      known.model = result.model
      known.startedAt ??= Date.now()
      state.known.set(result.agentId, known)
    }
    return result
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId !== undefined) {
      const known = state.known.get(e.agentId) ?? {}
      known.endedAt = Date.now()
      state.known.set(e.agentId, known)
    }
    await refresh($, state)
    return next(e)
  })

  // The button rides the footer's mode labels, which the engine draws at the
  // right end of the status line, after what the mods before this one drew
  // there (the kairos switch): this hook is registered ahead of theirs.
  on('ui.render', { component: 'SessionMode' }, async ($, e, next) => {
    const inner = await next(e)
    if (rows(state).length === 0) {
      return inner
    }
    const active = running(state)
    const { Box, Text, Button } = $.ui.resolve(e)
    return (
      <Box>
        {inner}
        <Text> </Text>
        <Button key={BUTTON} label={buttonLabel(active, done(state))} dimColor={active === 0} onPress={() => {}} />
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, ($, e) => drawPane($, state, e))

  on('ui.press', { element: BUTTON }, async ($, e, next) => {
    const result = await next(e)
    if (state.isOpen) {
      // Cleared here and not only at `ui.close`: a pane the engine dropped
      // (its drawing threw) closes without running its opener's hooks.
      state.isOpen = false
      stopPolling(state)
      await $.ui.close({ id: PANE })
      return result
    }
    await seed($, state)
    await refresh($, state)
    await $.ui.open({ id: PANE, title: 'subagents' })
    state.isOpen = true
    startPolling($, state)
    $.ui.invalidate('ui.render')
    return result
  })

  // A row's own closure picks the agent; the transcript is read and the
  // pane redrawn once it ran.
  on('ui.press', { requestId: PANE, element: ROW }, async ($, e, next) => {
    const result = await next(e)
    if (state.selected !== undefined) {
      await load($, state, state.selected)
    }
    $.ui.invalidate('ui.render')
    if (state.selected !== undefined) {
      follow($, state)
    }
    return result
  })

  on('ui.close', { id: PANE }, ($, e, next) => {
    state.isOpen = false
    stopPolling(state)
    return next(e)
  })
}
