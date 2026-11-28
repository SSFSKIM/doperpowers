import type { EngineInterface, On } from 'claude-code'

import { AGENT_ID, attribute, notification, statusOf, taskBandLine } from './tasks-model'
import type { Status } from './tasks-model'

/**
 * The Task Board's side in a session (child B1 of
 * docs/doperpowers/specs/2026-11-27-task-board-design.md; its execution
 * document's §6 and M4): a subagent's task names the subagent, the line above
 * the prompt counts the session's open tasks, and a new blocking task the
 * session assigned raises one notification on the machine. The store and its
 * rules are the command's (`sminos task`, sminos_tasks.py); this reads it only
 * through `sminos task status --session <id> --json` and writes nothing.
 *
 * **The attribution** (`registerTaskAttribution`, first in register.tsx, so
 * every other hook of sminos's and the plugins seated inside it receive the
 * command as it will run, and the person approves the command with the flag):
 * on a Bash call whose `e.agentId` is present and whole by D2's pattern, the
 * command goes on as `attribute` changed it (tasks-model.tsx), named from
 * `$.agent.list()` at the call (the agent's description, else its type; the
 * id alone where the list cannot be read). Any other call, and any failure of
 * the hook (its `.catch`), goes on unchanged: the attribution is a delivery
 * hint and never stops a command. A session marked `SMNS_INTERNAL` is left as
 * it is.
 *
 * **When the mod reads.** At the start; then at each tool call, prompt and
 * turn's end the mod sees, and on a 5 s timer, when one `$.fs.stat` of
 * `tasks/state.json` differs from the stat taken before the last read that
 * answered (or the session id differs: a `/clear`); and every twelfth tick
 * regardless, since a surface's registration changes without the store
 * changing. One read at a time; a look asked for while one runs makes one more
 * after it. A read that fails leaves the last answer standing and is tried
 * again at the next look, the stat it would have answered for not taken.
 *
 * **The notification.** A task in the answer's `mine` (open, blocking, this
 * session's own) whose `born` is above the `seq` of the first answer this
 * process adopted raises `$.ui.notify` once (tasks-model's `notification`):
 * tasks open when the process started raise none.
 *
 * **The line** (`registerTaskBand`, beneath the sheet's): `taskBandLine` of
 * the last answer, drawn above what the hooks beneath drew, not while a survey
 * holds the band.
 *
 * Where function hooks are off none of this runs: a subagent's task then names
 * no subagent, and the human's acts are told as any are (the start line, the
 * notice).
 */

/** The look's timer, and how many of its ticks pass before a read that asks no stat. */
export const TICK_MS = 5_000
export const FORCED_TICKS = 12
const RUN_TIMEOUT_MS = 10_000

/** What the mod reaches the engine through: closures made in its `session.start` hook (portOf); a test hands its own. */
export type TasksPort = {
  /** The sminos command; rejects when it does not start or runs out of time. */
  run: (args: string[]) => Promise<{ exitCode: number; stdout: string; stderr: string }>
  /** The store's stat as one string, `absent` where it is not there. */
  stat: () => Promise<string>
  session: () => Promise<string>
  notify: (text: string) => void
  redraw: () => void
  log: (text: string) => void
}

type TasksState = {
  port?: TasksPort
  status?: Status
  /** The seq of the first answer adopted: tasks born after it are new. */
  floor?: number
  notified: Set<string>
  /** What the last read that answered was taken against. */
  answered?: { stat: string; session: string }
  reading?: Promise<void>
  again?: { forced: boolean }
  ticks: number
}

const tasks: TasksState = { notified: new Set(), ticks: 0 }

/** Forgets everything (tests). */
export function resetTasks() {
  tasks.port = undefined
  tasks.status = undefined
  tasks.floor = undefined
  tasks.notified = new Set()
  tasks.answered = undefined
  tasks.reading = undefined
  tasks.again = undefined
  tasks.ticks = 0
}

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

/** The line above the prompt now, or undefined. */
export function bandNow(): string | undefined {
  return tasks.status === undefined ? undefined : taskBandLine(tasks.status.open, tasks.status.board)
}

/** An answer taken: the notification for each new blocking task, the line drawn again when it changed. */
function adopt(port: TasksPort, status: Status) {
  tasks.floor ??= status.seq
  for (const m of status.mine) {
    if (m.born > tasks.floor && !tasks.notified.has(m.id)) {
      tasks.notified.add(m.id)
      port.notify(notification(m.title))
    }
  }
  const before = bandNow()
  tasks.status = status
  if (bandNow() !== before) port.redraw()
}

/** One read, when the store or the session moved since the last that answered, or `forced`. */
async function read(port: TasksPort, forced: boolean) {
  try {
    const [session, stat] = await Promise.all([port.session(), port.stat()])
    const last = tasks.answered
    if (!forced && last !== undefined && last.stat === stat && last.session === session) return
    const out = await port.run(['task', 'status', '--session', session, '--json'])
    const status = out.exitCode === 0 ? statusOf(out.stdout) : undefined
    if (status === undefined) {
      port.log(`tasks: the board's status was not read (exit ${out.exitCode}): ${out.stderr.trim().slice(0, 200)}`)
      return
    }
    tasks.answered = { stat, session }
    adopt(port, status)
  } catch (error) {
    port.log(`tasks: the board's status was not read: ${message(error)}`)
  }
}

/** A look (above): one read at a time, one more after it for any asked meanwhile. Never awaited by a hook. */
export async function look(port: TasksPort, forced = false): Promise<void> {
  if (tasks.reading !== undefined) {
    tasks.again = { forced: forced || tasks.again?.forced === true }
    return tasks.reading
  }
  const reading = read(port, forced)
  tasks.reading = reading
  await reading
  tasks.reading = undefined
  const again = tasks.again
  tasks.again = undefined
  if (again !== undefined) await look(port, again.forced)
}

/** The timer's tick: a look, every twelfth a forced one. */
export function tick(port: TasksPort) {
  tasks.ticks += 1
  void look(port, tasks.ticks % FORCED_TICKS === 0)
}

const triggerLook = () => {
  if (tasks.port !== undefined) void look(tasks.port)
}

/** The sminos home as the command resolves it: SMINOS_HOME, else DAEMON_HOME, else ~/.claude/sminos. */
async function sminosHome($: EngineInterface): Promise<string> {
  const own = (await $.env.get('SMINOS_HOME')) || (await $.env.get('DAEMON_HOME'))
  return own || `${(await $.env.get('HOME')) ?? ''}/.claude/sminos`
}

/** The engine, as the tasks' mod reaches it: closures made here, in its own hook. */
function portOf($: EngineInterface, home: string): TasksPort {
  const command = `${$.plugin.root}/skills/sminos/scripts/sminos`
  const store = `${home}/tasks/state.json`
  return {
    run: (args) => $.process.run([command, ...args], { timeoutMs: RUN_TIMEOUT_MS }),
    stat: () =>
      $.fs.stat(store).then(
        (s) => `${s.kind}:${s.size}:${s.mtimeMs}`,
        () => 'absent',
      ),
    session: () => $.session.id(),
    notify: (text) => void $.ui.notify(text).catch((error: unknown) => $.ui.log(`tasks: the notification failed (${message(error)})`, { to: 'debug' })),
    redraw: () => $.ui.invalidate('ui.render'),
    log: (text) => $.ui.log(text, { to: 'debug' }),
  }
}

/** The name the board shows for a subagent: its description, else its type; undefined where the list cannot be read. */
async function agentName($: EngineInterface, agentId: string): Promise<string | undefined> {
  try {
    const agent = (await $.agent.list()).find((a) => a.id === agentId)
    return agent === undefined ? undefined : agent.description || agent.type || undefined
  } catch {
    return undefined
  }
}

/** The attribution (above): first in register.tsx. */
export function registerTaskAttribution(on: On) {
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const agentId = e.agentId
    if (typeof e.command !== 'string' || agentId === undefined || !AGENT_ID.test(agentId) || attribute(e.command, agentId, undefined) === undefined) {
      return next(e)
    }
    if ((await $.env.get('SMNS_INTERNAL')) !== undefined) {
      return next(e)
    }
    const command = attribute(e.command, agentId, await agentName($, agentId))
    return command === undefined ? next(e) : next({ ...e, command })
  }).catch((_$, e, next) => next(e))
}

/** The line above the prompt (D8): beneath the sheet's, above what the hooks beneath drew; not while a survey holds the band. */
export function registerTaskBand(on: On) {
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const line = bandNow()
    if (line === undefined || e.props.hasSurvey) {
      return next(e)
    }
    const inner = await next(e)
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        <Text dimColor>{line}</Text>
        {inner}
      </Box>
    )
  })
}

/** The reads (above): the start's, the hooks' looks and the timer. */
export function registerTasks(on: On) {
  on('session.start', { cwd: /^/ }, async ($, e, next) => {
    const result = await next(e)
    if ((await $.env.get('SMNS_INTERNAL')) !== undefined || tasks.port !== undefined) {
      return result
    }
    const port = portOf($, await sminosHome($))
    tasks.port = port
    $.clock.every(TICK_MS, () => tick(port))
    void look(port)
    return result
  }).catch((_$, e, next) => next(e))
  on('tool.call', { tool: /^/ }, (_$, e, next) => {
    triggerLook()
    return next(e)
  })
  on('prompt.submit', { text: /^/ }, (_$, e, next) => {
    triggerLook()
    return next(e)
  })
  on('turn.complete', { turnId: /./ }, (_$, e, next) => {
    triggerLook()
    return next(e)
  })
}
