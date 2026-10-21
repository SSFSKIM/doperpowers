import type { EngineInterface, On } from 'claude-code'

/**
 * A session is renamed after what it is in charge of: `sminos derive` asks
 * the session's fork for its in-charge line and a charge name with it, and,
 * when the engine name it would replace is still the session's, hands the
 * name over as a pending file, `<sminos home>/names/<session>.json`
 * (docs/doperpowers/specs/2026-10-20-sminos-charge-names-design.md §3).
 *
 * The mod applies it with the engine's own `/rename`, between turns: a timer
 * reads the file, and at the first tick that finds the session idle the CLI
 * checks the name is still due (`sminos name-due`: the engine name is still
 * the one the file replaces, the session is still one sminos may name, the
 * name is still free), then `$.command.run` renames. The engine registers it
 * as any `/rename` (`user`), writes the transcript's `custom-title` and
 * `agent-name`, and tells the model itself, so the mod adds nothing of its
 * own. Measured on 2.1.306: interactive sessions, `--bg` jobs and SDK
 * sessions (`sdk-ts`, streaming input) alike take the command while idle,
 * and it starts no model turn; so the timer runs in every session.
 *
 * The check runs once per pending file's text, not once per tick; a tick
 * with nothing new pays one failed read.
 */

/** How often the pending file is looked at. */
export const POLL_MS = 15_000

/**
 * How long the check may take, as the address bounds `who`: `name-due`
 * reconciles the session's project before it answers, a read comparable to
 * `who`'s.
 */
export const NAME_DUE_TIMEOUT_MS = 10_000

/** The sminos ask's snapshot (types/sminos.d.ts), whose `isDialogUp` holds the rename. */
const ASK = { plugin: 'sminos', key: 'ask' } as const

/** What the namer reaches the engine and the CLI through; the session start makes it from `$`. */
export type NameIo = {
  /** The session the process is in now (a /clear or a resume moves it). */
  session: () => Promise<string>
  /** That session's pending file; rejects when there is none. */
  read: (session: string) => Promise<string>
  /** `sminos name-due` for that session, bounded. */
  due: (session: string) => Promise<{ exitCode: number; stdout: string }>
  /** The engine's `/rename`, which acts on the session the process is in when it runs. */
  rename: (name: string) => Promise<unknown>
  /** An ask's dialog is up: the module that raised it takes its answer, not a command run meanwhile. */
  isAskDialogUp: () => Promise<boolean>
  log: (text: string) => void
}

/** The main turn, as the turn hooks below see it: whether one runs, and how many have started. */
const turn = { isRunning: false, started: 0 }

/** How many sessions ended in this process: a /clear or a resume goes on under another id, with no session.start. */
const sessions = { ended: 0 }

/** A turn starts; a subagent's run raises its own, with its agentId, and is not the main turn. */
export function turnStarted(e: { agentId?: string }) {
  if (e.agentId === undefined) {
    turn.isRunning = true
    turn.started += 1
  }
}

export function turnEnded(e: { agentId?: string }) {
  if (e.agentId === undefined) {
    turn.isRunning = false
  }
}

export function sessionEnded() {
  sessions.ended += 1
}

/** Forgets the turn and the sessions (tests, which share this module). */
export function resetName() {
  turn.isRunning = false
  turn.started = 0
  sessions.ended = 0
}

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

export function createNamer(io: NameIo) {
  /** The text of the pending file last checked: checked once. */
  let handled: string | undefined
  let isBusy = false

  async function step() {
    // What the attempt rests on, taken before anything is awaited: no main
    // turn starts and no session ends from here until the command, or the
    // answer is stale or meant for another session. Every await below is a
    // window for either, so the tick judges them all again, synchronously,
    // right before it renames.
    const at = { started: turn.started, ended: sessions.ended }
    const hasMoved = () => turn.isRunning || turn.started !== at.started || sessions.ended !== at.ended
    const session = await io.session()
    const pending = await io.read(session).catch(() => undefined)
    if (pending === undefined || pending === handled) {
      return
    }
    // A slash command run during a turn waits for its end, by which time the
    // check's answer may be stale; and a dialog's answer is its own.
    if (turn.isRunning || (await io.isAskDialogUp())) {
      return
    }
    // One attempt per pending file, whatever comes of it: a CLI that keeps
    // hanging would otherwise cost a check on every tick. A missed rename is
    // retried when the next derive rewrites the file. The exception is an
    // attempt that something above overtook: the file is left for a later
    // idle tick (the same text, or, after a /clear, the new session's own).
    const before = handled
    handled = pending
    const answer = await io.due(session).then(
      (value) => ({ value }),
      (error: unknown) => ({ error }),
    )
    if (hasMoved()) {
      handled = before
      return
    }
    if ('error' in answer) {
      io.log(`name: sminos name-due did not answer (${message(answer.error)}); this pending name is not tried again`)
      return
    }
    const { exitCode, stdout } = answer.value
    const name = exitCode === 0 ? (stdout.trim().split('\n')[0] ?? '').trim() : ''
    if (name === '') {
      return
    }
    // The person may have opened an ask's dialog while the check ran (a press
    // starts no turn), and the session id is read again in case it moved with
    // no session.end seen. Nothing is awaited between this judgment and the
    // command, which acts on the session the process is in.
    const [isDialogUp, now] = await Promise.all([io.isAskDialogUp(), io.session()])
    if (isDialogUp || hasMoved() || now !== session) {
      handled = before
      return
    }
    try {
      await io.rename(name)
    } catch (error) {
      io.log(`name: /rename ${name} was refused (${message(error)})`)
    }
  }

  return {
    async tick() {
      if (isBusy) {
        return
      }
      isBusy = true
      try {
        await step()
      } finally {
        isBusy = false
      }
    },
  }
}

/** The sminos home as the CLI's root() resolves it: SMINOS_HOME, else DAEMON_HOME, else ~/.claude/sminos. */
async function sminosHome($: EngineInterface): Promise<string> {
  const own = (await $.env.get('SMINOS_HOME')) || (await $.env.get('DAEMON_HOME'))
  return own || `${(await $.env.get('HOME')) ?? ''}/.claude/sminos`
}

/** Starts the timer, in every session but an internal fork. The session id is read at each tick, so a /clear's new session is the one checked. */
export async function startNaming($: EngineInterface) {
  if ((await $.env.get('SMNS_INTERNAL')) !== undefined) {
    return
  }
  const home = await sminosHome($)
  const namer = createNamer({
    session: () => $.session.id(),
    read: (session) => $.fs.read(`${home}/names/${session}.json`),
    due: (session) => $.process.run([`${$.plugin.root}/skills/sminos/scripts/sminos`, 'name-due', '--session', session], { timeoutMs: NAME_DUE_TIMEOUT_MS }),
    rename: (name) => $.command.run({ command: 'rename', args: name }),
    isAskDialogUp: async () => {
      const { value } = await $.state.get(ASK)
      return typeof value === 'object' && value !== null && (value as { isDialogUp?: unknown }).isDialogUp === true
    },
    log: (line) => $.ui.log(line, { to: 'debug' }),
  })
  $.clock.every(POLL_MS, () => void namer.tick())
}

export function registerName(on: On) {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    try {
      await startNaming($)
    } catch (error) {
      $.ui.log(`name: not watching for a pending name: ${message(error)}`, { to: 'debug' })
    }
    return result
  })
  on('turn.start', (_, e, next) => {
    turnStarted(e)
    return next(e)
  })
  on('turn.complete', async (_, e, next) => {
    try {
      return await next(e)
    } finally {
      turnEnded(e)
    }
  })
  // Any end: a /clear or a resume goes on under another session id (matched,
  // as the bridge holds the module's unmatched registration; an id is never
  // empty).
  on('session.end', { sessionId: /./ }, (_, e, next) => {
    sessionEnded()
    return next(e)
  })
}
