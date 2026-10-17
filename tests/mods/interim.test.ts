import { describe, expect, test, tier } from 'claude-code/testing'
import type { On } from 'claude-code'

import { INTERIM_NOTE, WAITING, handsBack, readInterim, registerInterim, searchArgs } from '../../hooks/mods/interim'

tier('user')

// The two notes the engine writes into an agent's completion notification
// (2.1.292 to 2.1.302), the interim one first.
const TASK = 'a6f9399af416f127b'
const output = (task: string) => `/tmp/claude-501/p/s/tasks/${task}.output`
const notification = (note: string, result = WAITING, status = 'completed', task = TASK) => `<task-notification>
<task-id>${task}</task-id>
<output-file>${output(task)}</output-file>
<status>${status}</status>
<summary>Agent "Execute C10 sessions plan" finished</summary>
<note>${note}</note>
<result>${result}
</result>
</task-notification>`
const INTERIM_TEXT = 'This agent stopped with background work of its own still running. It may resume on its own when that work completes or reports, and the same task-id notifies again if it does; the result below may be interim.'
const INTERIM = notification(INTERIM_TEXT)
const FINAL_NOTE = 'A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.'
const FINAL = notification(FINAL_NOTE)
const POINTER = 'This agent\'s report was delivered to you as a message from "a1" (its SubagentHandback call). Read it there; it is not repeated here.'
const WORKTREE = '<worktree><worktreePath>/repo/.claude/worktrees/agent-a6f9399af416f127b</worktreePath><worktreeBranch>worktree-agent-a6f9399af416f127b</worktreeBranch></worktree>'
const withWorktree = (text: string, worktree = WORKTREE) => text.replace('</result>', `</result>\n${worktree}`)

// Transcript records as the engine writes them, one JSON line each.
const meta = (content: string) => JSON.stringify({ type: 'user', isMeta: true, message: { role: 'user', content } })
const REMINDER = meta('<system-reminder>\nYour final report is delivered through SubagentHandback: when your work is complete, call SubagentHandback({message: <your full report>}).\n</system-reminder>')
const COUNTERMAND = meta('<system-reminder>\nSubagentHandback is not available in this run: an earlier instruction to report through it no longer applies. Write your final report as plain text; it will be delivered.\n</system-reminder>')
const BOUNDARY = JSON.stringify({ type: 'system', subtype: 'compact_boundary', content: 'Conversation compacted' })
const lines = (...records: string[]) => `${records.join('\n')}\n`

describe('readInterim', () => {
  test('reads the interim note and nothing else', async () => {
    expect(readInterim(INTERIM)).toEqual({ taskId: TASK, outputFile: output(TASK) })
    expect(readInterim(FINAL)).toBeUndefined()
    expect(readInterim(INTERIM.replace(/\n<output-file>.*<\/output-file>/, ''))).toEqual({ taskId: TASK })
  })

  test('passes a pointer to a delivered report: it does not prove the report reached this session', async () => {
    expect(readInterim(notification(INTERIM_TEXT, POINTER))).toBeUndefined()
    expect(readInterim(notification(INTERIM_TEXT, 'This agent\'s report was delivered to you as a message from "a1" (its SubagentHandback call), under a SECURITY WARNING from auto mode — the warning above the report says why. Read it there; it is not repeated here.'))).toBeUndefined()
  })

  test('passes an interim notification whose result is the agent\'s own text', async () => {
    expect(readInterim(notification(INTERIM_TEXT, '{"verdict":"incorrect","findings":[]}'))).toBeUndefined()
    expect(readInterim(notification(INTERIM_TEXT, ''))).toBeUndefined()
  })

  test('passes a result that carries anything beyond the placeholder', async () => {
    expect(readInterim(notification(INTERIM_TEXT, `${WAITING} Turn limit reached.`))).toBeUndefined()
    expect(readInterim(notification(INTERIM_TEXT, `${WAITING}\nAlso: the build is red.`))).toBeUndefined()
    expect(readInterim(notification(INTERIM_TEXT, 'The agent says: ' + WAITING))).toBeUndefined()
  })

  test('passes a final note whose result or summary quotes the interim sentence', async () => {
    expect(readInterim(notification(FINAL_NOTE, `${INTERIM_TEXT}\n${WAITING}`))).toBeUndefined()
    expect(readInterim(notification(FINAL_NOTE).replace('finished</summary>', `finished: ${INTERIM_NOTE}</summary>`))).toBeUndefined()
  })

  test('passes a notification whose status is not completed', async () => {
    expect(readInterim(notification(INTERIM_TEXT, WAITING, 'failed'))).toBeUndefined()
    expect(readInterim(notification(INTERIM_TEXT, WAITING, 'killed'))).toBeUndefined()
  })

  test('reads only a notification, not a prompt quoting one', async () => {
    expect(readInterim(`why did this come in?\n${INTERIM}`)).toBeUndefined()
  })

  test('reads a notification as the engine wrote it, with every line it can carry', async () => {
    // Verbatim from a MAWS session, 2026-10-17 (engine 2.1.289).
    expect(readInterim(`<task-notification>
<task-id>a3e145df620ee3bfc</task-id>
<tool-use-id>toolu_013azJXtexpYGKttP32rN9rk</tool-use-id>
<output-file>/private/tmp/claude-501/-Users-new-Developer-GitHub-MAWS/e3ce7feb-2e31-42ee-b836-829ecb01458b/tasks/a3e145df620ee3bfc.output</output-file>
<status>completed</status>
<summary>Agent "E2 plan child: file-backed dashboards" finished</summary>
<note>${INTERIM_TEXT}</note>
<result>${WAITING}
</result>
<usage><subagent_tokens>414449</subagent_tokens><tool_uses>5</tool_uses><duration_ms>47388</duration_ms></usage>
<worktree><worktreePath>/Users/new/Developer/GitHub/MAWS/.claude/worktrees/agent-a3e145df620ee3bfc</worktreePath><worktreeBranch>worktree-agent-a3e145df620ee3bfc</worktreeBranch></worktree>
</task-notification>`)).toEqual({
      taskId: 'a3e145df620ee3bfc',
      outputFile: '/private/tmp/claude-501/-Users-new-Developer-GitHub-MAWS/e3ce7feb-2e31-42ee-b836-829ecb01458b/tasks/a3e145df620ee3bfc.output',
      worktree: '<worktree><worktreePath>/Users/new/Developer/GitHub/MAWS/.claude/worktrees/agent-a3e145df620ee3bfc</worktreePath><worktreeBranch>worktree-agent-a3e145df620ee3bfc</worktreeBranch></worktree>',
    })
  })

  test('passes anything riding along with the envelope', async () => {
    expect(readInterim(`${INTERIM}\n${FINAL}`)).toBeUndefined()
    expect(readInterim(`${INTERIM}\nThe build is red.`)).toBeUndefined()
    expect(readInterim(INTERIM.replace('<result>', '<artifact-content-authored-by-others/>\nThe result below may relay Artifact content written by people other than you.\n<result>'))).toBeUndefined()
    expect(readInterim(INTERIM.replace('</note>', '</note>\n<report>done</report>'))).toBeUndefined()
    expect(readInterim(INTERIM.replace('</result>', '</result>\n<result>the real report</result>'))).toBeUndefined()
  })

  test('passes an interim note with a clause appended', async () => {
    expect(readInterim(INTERIM.replace('may be interim.</note>', 'may be interim. One or more messages sent to this agent arrived after this run\'s last step, too late for the result below.</note>'))).toBeUndefined()
    expect(readInterim(INTERIM.replace('may be interim.</note>', 'may be interim. This agent\'s work so far is saved.</note>'))).toBeUndefined()
  })
})

describe('handsBack', () => {
  test('the reminder, latest of the two, says the run hands back', async () => {
    expect(handsBack(lines(REMINDER))).toBe(true)
    expect(handsBack(lines(COUNTERMAND, REMINDER))).toBe(true)
  })

  test('no reminder at all: the placeholder could be the agent\'s own words', async () => {
    expect(handsBack('')).toBe(false)
  })

  test('a countermand after the reminder says it does not', async () => {
    expect(handsBack(lines(REMINDER, COUNTERMAND))).toBe(false)
  })

  test('a compaction after the reminder leaves it unknown; a reminder after one counts', async () => {
    expect(handsBack(lines(REMINDER, BOUNDARY))).toBe(false)
    expect(handsBack(lines(REMINDER, BOUNDARY, REMINDER))).toBe(true)
  })

  test('a line after the reminder that does not parse leaves it unknown', async () => {
    expect(handsBack(lines(REMINDER, '{"type":"user","isMeta":tr'))).toBe(false)
  })

  test('reads only meta user records whose content opens with the text', async () => {
    const quoted = JSON.stringify({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'text', text: 'Your final report is delivered through SubagentHandback' }] } })
    const typed = JSON.stringify({ type: 'user', message: { role: 'user', content: '<system-reminder>\nYour final report is delivered through SubagentHandback' } })
    const blocks = JSON.stringify({ type: 'user', isMeta: true, message: { role: 'user', content: [{ type: 'text', text: '<system-reminder>\nYour final report is delivered through SubagentHandback' }] } })
    expect(handsBack(lines(quoted, typed, blocks))).toBe(false)
    // A record that is not the countermand does not hide the reminder before it.
    expect(handsBack(lines(REMINDER, quoted, typed, blocks))).toBe(true)
  })
})

type Hook = { event: string; matcher: unknown; handler: (...args: unknown[]) => Promise<unknown> }
type Run = { exitCode: number; stdout: string; stderr: string; isStdoutTruncated: boolean; isStderrTruncated: boolean }
type Submitted = { text?: string; drop?: string }
type Stat = { kind: 'file' | 'dir' | 'other'; size: number; mtimeMs: number; isLink: boolean; realPath?: string }

/** Where an agent's `.output` link lands: its transcript, as the engine lays them out. */
const transcriptOf = (task: string) => `/Users/u/.claude/projects/p/s/subagents/agent-${task}.jsonl`
const linked = (realPath: string | undefined) => async (): Promise<Stat> => ({ kind: realPath === undefined ? 'other' : 'file', size: 0, mtimeMs: 0, isLink: true, ...(realPath !== undefined && { realPath }) })

/**
 * The mod's hooks over a fake engine: the agents `$.agent.list()` names,
 * where each `.output` link lands, and what the transcript search answers.
 */
function harness({
  agents = [{ id: TASK }] as { id: string; parentId?: string }[] | (() => never),
  stat = (async (path: string): Promise<Stat> => linked(transcriptOf(/\/tasks\/([^/]+)\.output$/.exec(path)![1]!))()) as (path: string) => Promise<Stat>,
  search = (async () => ({ exitCode: 0, stdout: lines(REMINDER), stderr: '', isStdoutTruncated: false, isStderrTruncated: false })) as (argv: string[]) => Promise<Run>,
  beneath = async (e: { text: string }): Promise<Submitted> => ({ text: e.text }),
} = {}) {
  const hooks: Hook[] = []
  registerInterim(((event: string, matcher: unknown, handler: Hook['handler']) => {
    hooks.push({ event, matcher, handler })
  }) as unknown as On)
  const searched: string[][] = []
  const $ = {
    agent: { list: async () => (typeof agents === 'function' ? agents() : agents) },
    fs: { stat: async (path: string, options: { resolve: boolean }) => (expect(options).toEqual({ resolve: true }), stat(path)) },
    process: { run: async (argv: string[]) => (searched.push(argv), search(argv)) },
    ui: { log: () => {} },
  }
  const promptSubmit = hooks.find((hook) => hook.event === 'prompt.submit')!
  let entered = 0
  const submit = async (text: string) => {
    return promptSubmit.handler($, { text, origin: { kind: 'task-notification' } }, async (e: { text: string }) => (entered++, beneath(e))) as Promise<Submitted>
  }
  return { hooks, submit, searched, entered: () => entered }
}

const failing = (stdout: string, exitCode = 0, isStdoutTruncated = false) => async (): Promise<Run> => ({ exitCode, stdout, stderr: '', isStdoutTruncated, isStderrTruncated: false })

describe('registerInterim', () => {
  test('hooks task notifications alone: no session state, so a module loaded mid-session filters from its first notice', async () => {
    const { hooks } = harness()
    expect(hooks.map((hook) => [hook.event, hook.matcher])).toEqual([['prompt.submit', { origin: { kind: 'task-notification' } }]])
  })

  test('drops the main loop\'s parked agent whose transcript shows the reminder, searching where its .output lands', async () => {
    const h = harness()
    const dropped = await h.submit(INTERIM)
    expect(typeof dropped.drop).toBe('string')
    expect(h.entered()).toBe(0)
    expect(h.searched).toEqual([searchArgs(transcriptOf(TASK))])
  })

  test('passes a notification without an output file, or whose link does not land on the agent\'s transcript', async () => {
    const bare = INTERIM.replace(/\n<output-file>.*<\/output-file>/, '')
    const h = harness()
    expect(await h.submit(bare)).toEqual({ text: bare })
    expect(h.searched).toEqual([])
    for (const stat of [
      linked(undefined), // dangling
      linked(output(TASK)), // a plain output file, no link
      linked(transcriptOf('b1')), // another agent's transcript
      async (): Promise<Stat> => { throw new Error('ENOENT') },
    ]) {
      const other = harness({ stat })
      expect(await other.submit(INTERIM)).toEqual({ text: INTERIM })
      expect(other.searched).toEqual([])
    }
  })

  test('passes the final notification without a lookup', async () => {
    const h = harness()
    expect(await h.submit(FINAL)).toEqual({ text: FINAL })
    expect(h.searched).toEqual([])
  })

  test('passes the placeholder when the agent wrote it itself: no reminder in its transcript', async () => {
    const h = harness({ search: failing('', 1) })
    expect(await h.submit(INTERIM)).toEqual({ text: INTERIM })
  })

  test('passes when a countermand follows the reminder', async () => {
    const h = harness({ search: failing(lines(REMINDER, COUNTERMAND)) })
    expect(await h.submit(INTERIM)).toEqual({ text: INTERIM })
  })

  test('the first notice of a worktree passes, a repeat drops, a new branch or task passes again', async () => {
    const h = harness({ agents: [{ id: TASK }, { id: 'b1' }] })
    const first = withWorktree(INTERIM)
    expect(await h.submit(first)).toEqual({ text: first })
    expect(typeof (await h.submit(first)).drop).toBe('string')
    const moved = withWorktree(INTERIM, WORKTREE.replace('worktree-agent-a6f9399af416f127b</worktreeBranch>', 'other</worktreeBranch>'))
    expect(await h.submit(moved)).toEqual({ text: moved })
    const other = withWorktree(notification(INTERIM_TEXT, WAITING, 'completed', 'b1'))
    expect(await h.submit(other)).toEqual({ text: other })
  })

  test('a worktree notice that did not enter is not counted as seen', async () => {
    let refuse = true
    const h = harness({ beneath: async (e) => (refuse ? { drop: 'a settings hook said no' } : { text: e.text }) })
    const first = withWorktree(INTERIM)
    expect((await h.submit(first)).drop).toBe('a settings hook said no')
    refuse = false
    expect(await h.submit(first)).toEqual({ text: first })
  })

  test('passes a pointer to a delivered report', async () => {
    const h = harness()
    const pointer = notification(INTERIM_TEXT, POINTER)
    expect(await h.submit(pointer)).toEqual({ text: pointer })
  })

  test('an orphan\'s first notice passes, the session\'s first sign of it; its repeats drop', async () => {
    const h = harness({ agents: [{ id: TASK, parentId: 'a0parent' }] })
    expect(await h.submit(INTERIM)).toEqual({ text: INTERIM })
    expect(h.searched).toEqual([])
    expect(typeof (await h.submit(INTERIM)).drop).toBe('string')
  })

  test('an orphan\'s notice that did not enter leaves the next one to pass', async () => {
    let refuse = true
    const h = harness({ agents: [{ id: TASK, parentId: 'a0parent' }], beneath: async (e) => (refuse ? { drop: 'a settings hook said no' } : { text: e.text }) })
    expect((await h.submit(INTERIM)).drop).toBe('a settings hook said no')
    refuse = false
    expect(await h.submit(INTERIM)).toEqual({ text: INTERIM })
  })

  test('a known agent\'s repeat still needs the reminder', async () => {
    let stdout = ''
    const h = harness({ agents: [{ id: TASK, parentId: 'a0parent' }], search: async () => ({ exitCode: stdout === '' ? 1 : 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false }) })
    expect(await h.submit(INTERIM)).toEqual({ text: INTERIM })
    expect(await h.submit(INTERIM)).toEqual({ text: INTERIM })
    stdout = lines(REMINDER, COUNTERMAND)
    expect(await h.submit(INTERIM)).toEqual({ text: INTERIM })
    stdout = lines(REMINDER)
    expect(typeof (await h.submit(INTERIM)).drop).toBe('string')
  })

  test('every lookup that fails or cannot tell lets the notification through', async () => {
    const cases = [
      harness({ agents: [] }),
      harness({ agents: () => { throw new Error('list refused') } }),
      harness({ search: async () => { throw new Error('grep did not start') } }),
      harness({ search: failing('', 2) }),
      harness({ search: failing(lines(REMINDER), 0, true) }),
      harness({ search: failing(lines(REMINDER, BOUNDARY)) }),
      harness({ search: failing(lines(REMINDER, 'not json')) }),
    ]
    for (const h of cases) {
      expect(await h.submit(INTERIM)).toEqual({ text: INTERIM })
    }
  })
})
