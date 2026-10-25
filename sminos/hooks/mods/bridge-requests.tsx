import type { PermissionRequestDecision } from 'claude-code'

import { ASK_TOOL, answerAsync } from './ask'
import type { AskNote } from './ask'
import { capped, isRecord, parsed, state } from './bridge-state'
import type { Answer, Capped, Check, Command, Decision, Outcome, Request } from './bridge-state'
import { emit, raisedFields } from './bridge-stream'

/**
 * Requests from outside (DC2 M3): a permission prompt or a question the
 * engine puts to its dialog is `raised`, and its `classic.PermissionRequest`
 * hook long-polls the child for a decision while the terminal's dialog stays
 * up; an async question of the ask mod is raised as it opens and answered
 * through it. Each ends with one `settled` naming the side whose answer the
 * engine used, read from what the engine did: its mark of a hook's decision
 * beside the call's result, the result itself, the dialog closing in the
 * terminal (the child watches the session record), the turn ending.
 *
 * The wait for a client's decision takes `$`, and is in bridge.tsx
 * (`awaitDecision`).
 */

/**
 * The engine records each permission decision as it is made (its
 * `tool_decision` collector record, raised to plugins through `telemetry.log`
 * whether or not a collector is configured; live, 2.1.300, also with
 * DISABLE_TELEMETRY and CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC). A call
 * whose result arrives with no record within this long is settled from the
 * transcript instead.
 */
export const RECORD_WAIT_MS = 1_000
/** The transcript holds a result row once it is written: read again this often, so many times. */
export const TRANSCRIPT_RETRY_MS = 300
const TRANSCRIPT_TRIES = 6
/** The record's sources that are the person at the dialog (`user_abort` is an interrupt: nobody answered). */
const PERSON_SOURCES = new Set(['user_temporary', 'user_permanent', 'user_reject'])
/** Tool checks put to the dialog, kept for their PermissionRequest (and those decided, for a late one); recent settlements, for a late subscriber. */
export const CHECKS_KEPT = 50
/** Decision records kept for a request raised, or a dialog attributed, after its record came. */
const RECORDS_KEPT = 200
const SETTLED_KEPT = 100
/** A deny that carries no words of its own. */
const DENIED = 'The human denied this request.'
/** The engine's result for a call the terminal's dialog refused. */
const REFUSAL = "The user doesn't want to proceed with this tool use."

/** DX4's winner for who answered: the terminal; the CLI or the bridge itself (other); anyone else, a member on the web. */
const winnerOf = (by: string) => (by === 'terminal' ? 'terminal' : by === 'cli' || by === 'bridge' ? 'other' : 'web')

export function raise(r: Request) {
  state.requests.set(r.id, r)
  emit({ type: 'raised', ...raisedFields(r) })
}

/** The one settlement of a request: the side whose answer the engine used, what it was, and who answered. */
export function settle(r: Request, outcome: Outcome, by: string) {
  if (state.requests.get(r.id) !== r) {
    return
  }
  state.requests.delete(r.id)
  const settled = { request: r.id, winner: winnerOf(by), outcome, by }
  state.settled.push({ ...settled, t: Date.now() })
  if (state.settled.length > SETTLED_KEPT) {
    state.settled.shift()
  }
  emit({ type: 'settled', ...settled })
  // An async question answered through this dialog settles with it.
  const asked = state.askDialogs.get(r.id)
  if (asked !== undefined) {
    state.askDialogs.delete(r.id)
    answeredThrough(asked, settled)
  }
}

/** Whether a subagent runs in the background, itself or under an ancestor; one the bridge does not know of is taken to (its window is bounded). */
export function isBackground(agentId: string): boolean {
  let at: string | null = agentId
  for (let depth = 0; at !== null && depth < 16; depth++) {
    const agent: Record<string, unknown> | undefined = state.agents.get(at)
    if (agent === undefined || agent.background === true) {
      return true
    }
    at = typeof agent.parentAgentId === 'string' ? agent.parentAgentId : null
  }
  return false
}

/**
 * A running call's input as the bridge's `tool.call` hook was handed it (the
 * latest call of that id); none for a call it did not see.
 */
export function shownCall(toolUseId: string): Capped | undefined {
  return [...state.calls.values()].findLast((c) => c.toolUseId === toolUseId)?.shown
}

/**
 * The call a PermissionRequest is for: the hook's input names no call, so the
 * engine's check that put a call of that tool, in that loop, to the dialog
 * names it (the one with the same input first). Every PermissionRequest takes
 * its check, raised or not, so none is left for a later identical call. A
 * check whose decision the engine already recorded is taken as decided.
 */
export function claimCheck(tool: string, agentId: string | null, input: unknown): { toolUseId: string; shown?: Capped; isDecided: boolean } | undefined {
  const same = (c: Check) => c.tool === tool && c.agentId === agentId
  const text = JSON.stringify(input)
  const exact = (c: Check) => same(c) && JSON.stringify(c.input) === text
  const take = (list: Check[], at: number, isDecided: boolean) => {
    const c = list.splice(at, 1)[0] as Check
    return { toolUseId: c.toolUseId, ...(c.shown !== undefined && { shown: c.shown }), isDecided }
  }
  let at = state.checks.findIndex(exact)
  if (at >= 0) {
    return take(state.checks, at, false)
  }
  at = state.decidedChecks.findIndex(exact)
  if (at >= 0) {
    return take(state.decidedChecks, at, true)
  }
  at = state.checks.findIndex(same)
  return at < 0 ? undefined : take(state.checks, at, false)
}

/**
 * The one tool besides a question whose allow must carry an input (2.1.307):
 * the engine drops a hook's bare allow of a tool that requires the person,
 * and the plan's dialog stays; of those tools, it takes an allow carrying
 * one only for this and a question. Every other allow goes bare: an input,
 * even the call's own, has the engine check the call again before taking
 * the allow, and a call an ask rule or a safety check put to the dialog is
 * then asked again, the allow unused.
 */
const PLAN_TOOL = 'ExitPlanMode'

/**
 * The decision as the engine takes it: a question's allow carries the
 * dialog's own questions with the answers; a plan's, the call's own input,
 * whole. That is `rawInput`, the hook's input as the engine handed it, which
 * the engine finds unchanged and runs as it is. The raised `input` is the
 * call before the hooks beneath, capped: in its place a long plan would
 * reach the tool cut, and be approved and saved as the plan.
 */
export function engineDecision(r: Request, d: Decision): PermissionRequestDecision {
  if (d.behavior === 'deny') {
    return { behavior: 'deny', message: d.message ?? DENIED }
  }
  if (r.isQuestion) {
    return { behavior: 'allow', updatedInput: { ...(isRecord(r.rawInput) ? r.rawInput : {}), answers: d.updatedInput?.answers ?? {} } }
  }
  if (r.tool === PLAN_TOOL && isRecord(r.rawInput)) {
    return { behavior: 'allow', updatedInput: r.rawInput }
  }
  return { behavior: 'allow' }
}

/**
 * The engine recorded the decision on a call (DX4's evidence of who won,
 * tied to the call's id): a PermissionRequest hook's, the person's at the
 * dialog (`user_*`), or neither (its rules or mode, an interrupt). The
 * record is kept: a call whose PermissionRequest has not raised it yet is
 * never raised, and an async question answered through a dialog that was
 * never raised is attributed by it.
 */
export function decisionRecorded(id: string, source: string, isAccepted: boolean) {
  const at = state.checks.findIndex((c) => c.toolUseId === id)
  if (at >= 0) {
    state.decidedChecks.push(...state.checks.splice(at, 1))
    if (state.decidedChecks.length > CHECKS_KEPT) {
      state.decidedChecks.shift()
    }
  }
  state.records.set(id, { source, isAccepted })
  if (state.records.size > RECORDS_KEPT) {
    state.records.delete(state.records.keys().next().value as string)
  }
  const r = state.requests.get(id)
  if (r !== undefined && !r.isAsync) {
    settleDecided(r, source, isAccepted)
  }
}

/**
 * Settles a request from who decided it: the bridge's decider when a hook's
 * decision was used and it is the one the bridge handed out; the terminal
 * when the person decided at the dialog; else nobody (withdrawn).
 */
function settleDecided(r: Request, source: string, isAccepted: boolean) {
  const outcome: Outcome = !isAccepted ? 'deny' : r.isQuestion ? 'answered' : 'allow'
  if (r.isAborted) {
    settle(r, 'withdrawn', 'bridge')
  } else if (source === 'hook' && r.decided !== undefined && (r.decided.decision.behavior === 'allow') === isAccepted) {
    settle(r, outcome, r.decided.by)
  } else if (PERSON_SOURCES.has(source)) {
    settle(r, outcome, 'terminal')
  } else {
    if (source === 'hook') {
      state.log?.(`bridge: request ${r.id} was decided by a PermissionRequest hook with an answer the bridge did not hand out; withdrawn`)
    }
    settle(r, 'withdrawn', 'bridge')
  }
}

/**
 * A request's call ended with no record of its decision yet: one that comes
 * within RECORD_WAIT_MS settles it; else the transcript does. The engine
 * writes its mark of a used hook decision (`hook_permission_decision`, with
 * the call's id) just before the call's result, so once the result row is in
 * the file, a mark with this call's id says the hook's answer was used, and
 * none says the person's was.
 */
export function callEnded(toolUseId: string, result: { text: string; uuid: string }) {
  const r = state.requests.get(toolUseId)
  if (r === undefined || r.isAsync) {
    return
  }
  state.after?.(RECORD_WAIT_MS, () => void settleFromTranscript(r, result, 0))
}

async function settleFromTranscript(r: Request, result: { text: string; uuid: string }, tries: number) {
  if (state.requests.get(r.id) !== r) {
    return
  }
  const path = transcriptOf(r)
  let lines: string[] | undefined
  try {
    lines = path === undefined || state.read === undefined ? undefined : (await state.read(path)).split('\n').filter((l) => l.includes(r.id) || l.includes(result.uuid))
  } catch {
    lines = undefined
  }
  if (state.requests.get(r.id) !== r) {
    return
  }
  const rows = (lines ?? []).map(parsed).filter((row) => row !== undefined)
  if (!rows.some((row) => row.uuid === result.uuid)) {
    if (lines !== undefined && tries < TRANSCRIPT_TRIES) {
      state.after?.(TRANSCRIPT_RETRY_MS, () => void settleFromTranscript(r, result, tries + 1))
      return
    }
    state.log?.(`bridge: request ${r.id}: no record of its decision, and its result is not in ${path ?? 'a transcript'}; withdrawn`)
    settle(r, 'withdrawn', 'bridge')
    return
  }
  const mark = rows.map((row) => row.attachment).find((a) => isRecord(a) && a.type === 'hook_permission_decision' && a.toolUseID === r.id)
  if (isRecord(mark)) {
    settleDecided(r, 'hook', mark.decision === 'allow')
  } else {
    settleDecided(r, 'user_temporary', !result.text.includes(REFUSAL))
  }
}

/** The file a request's loop keeps its rows in: the session's transcript, or its subagent's beside it. */
function transcriptOf(r: Request): string | undefined {
  const main = r.transcript
  if (main === undefined || r.agentId === null || main.includes('/subagents/')) {
    return main
  }
  return `${main.replace(/\.jsonl$/, '')}/subagents/agent-${r.agentId}.jsonl`
}

/**
 * An async question answered through a dialog a press opened: settled as
 * that dialog's request settled (its winner answered the question), or
 * withdrawn when the dialog's own settlement names nobody.
 */
function answeredThrough(id: string, dialog: { outcome: string; by: string }) {
  const r = state.requests.get(id)
  if (r?.isAsync) {
    settle(r, dialog.outcome === 'withdrawn' ? 'withdrawn' : 'answered', dialog.by)
  }
}

/**
 * What the ask mod's asks do (its observer): an async question is raised as
 * it opens and settled as it is answered, dismissed or forgotten; a dialog it raised
 * that ended with no record of who decided it is withdrawn.
 */
export function onAskNote(note: AskNote) {
  // No bridge, or none yet: bridgeStart raises the asks still open as it starts.
  if (state.post === undefined) {
    return
  }
  if (note.kind === 'open') {
    if (!state.requests.has(note.id)) {
      const input = capped({ questions: note.questions })
      raise({ id: note.id, tool: ASK_TOOL, input: input.value, rawInput: { questions: note.questions }, isTruncated: input.cut, agentId: null, isAsync: true, isQuestion: true, t: Date.now(), isAborted: false })
    }
  } else if (note.kind === 'answered') {
    if (!state.requests.get(note.id)?.isAsync) {
      return
    }
    if ('by' in note) {
      answeredThrough(note.id, { outcome: 'answered', by: note.by })
      return
    }
    const done = state.settled.find((s) => s.request === note.dialog)
    const record = state.records.get(note.dialog)
    if (done !== undefined) {
      answeredThrough(note.id, { outcome: String(done.outcome), by: String(done.by) })
    } else if (state.requests.has(note.dialog)) {
      state.askDialogs.set(note.dialog, note.id)
    } else if (record !== undefined && PERSON_SOURCES.has(record.source)) {
      // Its dialog was answered before it was raised: only the person could have.
      answeredThrough(note.id, { outcome: 'answered', by: 'terminal' })
    } else {
      answeredThrough(note.id, { outcome: 'withdrawn', by: 'bridge' })
    }
  } else if (note.kind === 'dismissed') {
    // The person closed it at the terminal unanswered: no answer will settle it.
    const r = state.requests.get(note.id)
    if (r?.isAsync) {
      settle(r, 'withdrawn', 'terminal')
    }
  } else if (note.kind === 'forgotten') {
    for (const id of note.ids) {
      const r = state.requests.get(id)
      if (r?.isAsync) {
        settle(r, 'withdrawn', 'bridge')
      }
    }
  } else {
    // The dialog keeps no rows to read: with no record by now, nobody is known to have answered it.
    const r = state.requests.get(note.toolUseId)
    if (r !== undefined && !r.isAsync) {
      state.after?.(RECORD_WAIT_MS, () => settle(r, 'withdrawn', 'bridge'))
    }
  }
}

/** An async question's answer from outside (the child relays a client's), handed to the ask mod, which delivers it. */
export function answerFromOutside(command: Command): Answer {
  const { request, answers, by } = command
  if (typeof request !== 'string' || typeof by !== 'string' || !isRecord(answers) || !Object.values(answers).every((a) => typeof a === 'string')) {
    return { ok: false, error: 'answer needs request, answers (by question) and by' }
  }
  if (state.requests.get(request)?.isAsync !== true) {
    return { ok: false, error: `no async question ${request} is pending` }
  }
  const done = answerAsync(request, answers as Record<string, string>, by)
  return done.ok ? { ok: true, result: { answered: true } } : { ok: false, error: done.error }
}

/** The session ended: what it left pending is withdrawn. */
export function withdrawAll() {
  for (const r of [...state.requests.values()]) {
    settle(r, 'withdrawn', 'bridge')
  }
}

/** A call's first question text, from its `questions`; undefined when it has none. */
export function firstQuestion(questions: unknown): string | undefined {
  const q = Array.isArray(questions) ? questions[0] : undefined
  return isRecord(q) && typeof q.question === 'string' ? q.question : undefined
}

/**
 * The ask call a dialog of the ask mod was opened inside: the one running
 * call of the ask tool whose first question is the dialog's (the dialog
 * carries it, under its own header) and that no other dialog was paired
 * with. None for a dialog the human opened from an async ask's button, and
 * none when two such calls run: the pairing would be a guess.
 */
export function askCallFor(question: string | undefined): string | undefined {
  if (question === undefined) {
    return undefined
  }
  const paired = new Set(state.dialogCalls.values())
  const calls = [...state.calls.values()].filter((c) => c.tool === ASK_TOOL && c.question === question && c.toolUseId !== undefined && !paired.has(c.toolUseId))
  return calls.length === 1 ? calls[0]?.toolUseId : undefined
}
