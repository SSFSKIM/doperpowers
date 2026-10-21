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
  /** The session's pending file; rejects when there is none. */
  read: () => Promise<string>
  /** `sminos name-due` for the session, bounded. */
  due: () => Promise<{ exitCode: number; stdout: string }>
  /** The engine's `/rename`. */
  rename: (name: string) => Promise<unknown>
  /** An ask's dialog is up: the module that raised it takes its answer, not a command run meanwhile. */
  isAskDialogUp: () => Promise<boolean>
  log: (text: string) => void
}

/** The main turn, as the turn hooks below see it: whether one runs, and how many have started. */
const turn = { isRunning: false, started: 0 }

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

/** Forgets the turn (tests, which share this module). */
export function resetName() {
  turn.isRunning = false
  turn.started = 0
}

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

export function createNamer(io: NameIo) {
  /** The text of the pending file last checked: checked once. */
  let handled: string | undefined
  let isBusy = false

  async function step() {
    const pending = await io.read().catch(() => undefined)
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
    // retried when the next derive rewrites the file.
    const before = { handled, started: turn.started }
    handled = pending
    const answer = await io.due().then(
      (value) => ({ value }),
      (error: unknown) => ({ error }),
    )
    // A turn started meanwhile, whatever the check answered: the answer may
    // be stale, and the session is not idle. The next idle tick asks again.
    if (turn.started !== before.started || turn.isRunning) {
      handled = before.handled
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
    // starts no turn): its answer is its own. And a turn may have started
    // while the dialog was read. Either way the next idle tick renames.
    const isDialogUp = await io.isAskDialogUp()
    if (isDialogUp || turn.isRunning || turn.started !== before.started) {
      handled = before.handled
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
  let session = ''
  const namer = createNamer({
    read: async () => {
      session = await $.session.id()
      return $.fs.read(`${home}/names/${session}.json`)
    },
    due: () => $.process.run([`${$.plugin.root}/skills/sminos/scripts/sminos`, 'name-due', '--session', session], { timeoutMs: NAME_DUE_TIMEOUT_MS }),
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
}
