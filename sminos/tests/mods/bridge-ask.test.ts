import { describe, expect, test, tier } from 'claude-code/testing'
import type { SessionMessage } from 'claude-code'

import {
  ASK_BUSY,
  ASK_DESCRIPTION,
  ASK_FRAME,
  ASK_GRACE_POLLS,
  FORK_GUARD_PRESENT,
  FORK_GUARD_PROBE,
  NO_GUARD,
  TAIL_MAX,
  TAIL_RESULT_MAX,
  askEnd,
  ASK_AFTER_QUESTION,
  askPrompt,
  renderTail,
} from '../../hooks/mods/bridge-ask'
import { BTW_TEXT_MAX, NOTHING_TO_FORK } from '../../hooks/mods/bridge-btw'
import { SID, SOCK, harness, hello } from './bridge-harness'

tier('user')

const USAGE = { input_tokens: 4, output_tokens: 300, cache_read_input_tokens: 27_169, cache_creation_input_tokens: 710, model: 'claude-haiku' }
/** UTF-8 bytes, counted another way than the module counts them: each escaped byte one. */
const utf8 = (s: string) => encodeURIComponent(s).replace(/%[0-9A-F]{2}/g, 'x').length

/** A row of the conversation as `$.session.messages()` gives it. */
const said = (text: string): SessionMessage => ({ role: 'assistant', text, toolUses: [] })
const asked = (text: string): SessionMessage => ({ role: 'user', text, toolUses: [] })
const called = (id: string, tool: string, input: Record<string, unknown>, text?: string, isError = false): SessionMessage => ({
  role: 'assistant',
  text: '',
  toolUses: [{ tool_use_id: id, tool, input, ...(text !== undefined && { text }), ...(isError && { isError: true as const }) }],
})
const results = (id: string, text: string): SessionMessage => ({ role: 'user', text: '', toolUses: [], toolResults: [{ tool_use_id: id, text, isError: false }] })

describe('the fork agent: its words', () => {
  test("the frame is fixed, word for word (copied as FORK_FRAME in sminos_fork.py)", () => {
    expect(ASK_FRAME).toBe(
      "You are a read-only fork of this session, started by the owner's manager session to answer one question. The session itself never sees this exchange, and nothing you do here reaches it. Do not continue the session's task. You may use read-only tools (reading and searching files, read-only shell commands such as git log, git status or gh pr view) to check facts; anything that would change a file or any state is refused. Answer the question directly, then stop.",
    )
    expect(ASK_DESCRIPTION).toBe('manager query')
  })

  test("the guard's presence is asked by its probe path and known by its answer, word for word (doperpowers' hooks/mods/fork-guard.tsx)", () => {
    expect(FORK_GUARD_PROBE).toBe('/dev/null/sminos-fork-guard-probe')
    expect(FORK_GUARD_PRESENT).toBe('The read-only fork guard (doperpowers) is loaded.')
  })

  test("the prompt: the frame, the tail as a delimited record to read, not to act on, then the question, then the rule against the session's calls", () => {
    expect(ASK_AFTER_QUESTION).toBe("Answer it from what you can see; do not perform any of the session's pending or planned calls.")
    expect(askPrompt('', 'What are you waiting on?')).toBe(
      `${ASK_FRAME}\n\nThe question:\n\nWhat are you waiting on?\n\n${ASK_AFTER_QUESTION}`,
    )
    expect(askPrompt('the session wrote: running the tests', 'Which tests?')).toBe(
      `${ASK_FRAME}\n\nWhat the session has done since the request this fork continues from, for reference only: a record of the session's own work, to read, not to act on (oldest first).\n\n<session-record>\nthe session wrote: running the tests\n</session-record>\n\nThe question:\n\nWhich tests?\n\n${ASK_AFTER_QUESTION}`,
    )
  })
})

describe('the fork agent: the tail', () => {
  test("rendered from the last completed response on: its text, each tool call with its input and its result, the user rows left out", () => {
    const rows = [
      said('Earlier, before the last request.'),
      results('toolu_0', 'old'),
      said('Now I will sleep.'),
      called('toolu_s', 'Bash', { command: 'sleep 20' }),
      results('toolu_s', 'ignored: the call carries its result'),
    ]
    expect(renderTail(rows, { toolUseIds: ['toolu_s'], texts: [] })).toBe('the session wrote: Now I will sleep.\nthe session called: Bash({"command":"sleep 20"})\n  (still running in the session — not yours to run)')
  })

  test("a call's result follows it, cut to 2,000 characters; an error is said to be one", () => {
    expect(TAIL_RESULT_MAX).toBe(2_000)
    const long = 'x'.repeat(5_000)
    const tail = renderTail([called('toolu_r', 'Read', { file_path: '/a' }, long), called('toolu_b', 'Bash', { command: 'false' }, 'exit 1', true)], { toolUseIds: ['toolu_r'], texts: [] })
    const [first, result, second, error] = tail.split('\n')
    expect(first).toBe('the session called: Read({"file_path":"/a"})')
    expect(result).toBe(`  result: ${'x'.repeat(2_000)} [… 3000 more characters]`)
    expect(second).toBe('the session called: Bash({"command":"false"})')
    expect(error).toBe('  error: exit 1')
  })

  test("a call's input is cut to 2,000 characters too: one Write never fills the tail", () => {
    const tail = renderTail([called('toolu_w', 'Write', { file_path: '/a', content: 'y'.repeat(10_000) })], { toolUseIds: ['toolu_w'], texts: [] })
    expect(tail.length).toBeLessThan(2_200)
    expect(tail).toContain('[… ')
  })

  test('the newest 32 KiB of UTF-8 are kept, the cut said at the top', () => {
    expect(TAIL_MAX).toBe(32 * 1024)
    const rows = [called('toolu_a', 'Bash', { command: 'a' })]
    for (let i = 0; i < 40; i++) {
      rows.push(said(`${i}: ${'가'.repeat(400)}`))
    }
    rows.push(said('the newest line'))
    const tail = renderTail(rows, { toolUseIds: ['toolu_a'], texts: [] })
    expect(utf8(tail)).toBeLessThanOrEqual(TAIL_MAX)
    expect(utf8(tail)).toBeGreaterThan(TAIL_MAX - 1_300)
    expect(tail.startsWith('[earlier messages cut]\n')).toBe(true)
    expect(tail.endsWith('the session wrote: the newest line')).toBe(true)
    expect(tail).not.toContain('the session called: Bash')
  })

  test("a response with no tool call is found by its text: its prose reaches the fork while the turn goes on past it", () => {
    const rows = [said('Let me look.'), asked('older prompt'), said('Let me look.'), asked('A Stop hook said: keep going.')]
    expect(renderTail(rows, { toolUseIds: [], texts: ['Let me look.'] })).toBe('the session wrote: Let me look.')
    // A row holding several of the response's text blocks, joined.
    expect(renderTail([asked('go'), said('First part.\nSecond part.')], { toolUseIds: [], texts: ['First part.', 'Second part.'] })).toBe(
      'the session wrote: First part.\nSecond part.',
    )
    // A response the transcript split across rows: its text row, then its call row.
    expect(renderTail([asked('go'), said('Checking.'), called('toolu_c', 'Read', { file_path: '/a' })], { toolUseIds: [], texts: ['Checking.'] })).toBe(
      'the session wrote: Checking.\nthe session called: Read({"file_path":"/a"})\n  (still running in the session — not yours to run)',
    )
  })

  test('nothing when no row holds the response the tail starts from', () => {
    expect(renderTail([said('a'), asked('b')], { toolUseIds: [], texts: [] })).toBe('')
    expect(renderTail([said('a'), called('toolu_x', 'Bash', { command: 'x' })], { toolUseIds: ['toolu_gone'], texts: [] })).toBe('')
    expect(renderTail([said('a')], { toolUseIds: [], texts: ['  '] })).toBe('')
  })
})

describe("the fork agent: the end, from the fork's turn.complete", () => {
  const ended = (fields: Record<string, unknown>) => askEnd({ turnId: 't', answer: '', durationMs: 1, isAborted: false, reason: 'answer', ...fields } as never)

  test('the answer, cut to 64 KiB and marked so, with the whole fork’s cost', () => {
    expect(ended({ answer: 'Waiting on your merge of #452.', usage: USAGE })).toEqual({
      text: 'Waiting on your merge of #452.',
      usage: { input: 4, output: 300, cacheRead: 27_169, cacheWrite: 710 },
    })
    const long = ended({ answer: '가'.repeat(30_000), usage: USAGE })
    expect(long).toMatchObject({ truncated: true, usage: { output: 300 } })
    expect(utf8(long.text as string)).toBeLessThanOrEqual(BTW_TEXT_MAX)
  })

  test('why there is no answer: empty, aborted, or failed with the reason the turn ended; the cost wherever there was one', () => {
    expect(ended({ answer: '  ', usage: USAGE })).toEqual({ reason: 'empty-reply', usage: { input: 4, output: 300, cacheRead: 27_169, cacheWrite: 710 } })
    expect(ended({ reason: 'aborted', isAborted: true })).toEqual({ reason: 'aborted' })
    expect(ended({ reason: 'error', usage: USAGE })).toMatchObject({ reason: 'failed', error: "the fork's turn ended: error", usage: { input: 4 } })
    expect(ended({ reason: 'refusal' })).toEqual({ reason: 'failed', error: "the fork's turn ended: refusal" })
  })
})

describe('the fork agent: the op', () => {
  /** The fork's own turn.complete, as every hook hears an agent's end. */
  const forkEnds = async (h: ReturnType<typeof harness>, agentId: string, fields: Record<string, unknown> = {}) => {
    await h.hook('turn.complete', { turnId: 'tf' })(h.engine, { turnId: 'tf', answer: 'It waits on you.', durationMs: 9, isAborted: false, reason: 'answer', agentId, usage: USAGE, ...fields }, async () => ({ text: '' }))
    await h.settle()
  }
  const live = async (options: Parameters<typeof harness>[0] = {}) => {
    const h = harness({ guard: true, messages: [asked('hi'), said('PELICAN-42.')], ...options })
    await h.ready()
    return h
  }

  test("answered at once, started, with the fork's agent id; the fork spawned under the frame, its start and end after the answer", async () => {
    const h = await live()
    const r = await h.command({ op: 'ask', prompt: 'Quote your last message.' })
    expect(r).toMatchObject({ ok: true, result: { started: true, id: r.id, agentId: 'afork1' } })
    expect(h.spawns).toEqual([{ subagentType: 'fork', description: 'manager query', prompt: askPrompt('', 'Quote your last message.') }])
    expect(h.queries).toEqual([{ tool: 'Read', input: { file_path: FORK_GUARD_PROBE } }])
    const at = (e: Record<string, unknown>) => h.events().indexOf(e)
    expect(h.ofType('ask')).toMatchObject([{ phase: 'start', id: r.id, agentId: 'afork1' }])
    expect(at(h.ofType('ask')[0]!)).toBeGreaterThan(at(r))
    await forkEnds(h, 'afork1')
    expect(h.ofType('ask')[1]).toMatchObject({ type: 'ask', phase: 'end', id: r.id, agentId: 'afork1', text: 'It waits on you.', usage: { input: 4, output: 300, cacheRead: 27_169, cacheWrite: 710 } })
    // Nothing is written into the conversation.
    expect(h.calls.filter((c) => c.op === 'append' || c.op === 'submit' || c.op === 'command.run' || c.op === 'send')).toEqual([])
  })

  test('a question that is no text is refused bad-prompt before anything is asked', async () => {
    const h = await live()
    expect(await h.command({ op: 'ask', prompt: ' ' })).toMatchObject({ ok: false, code: 'bad-prompt' })
    expect(await h.command({ op: 'ask' })).toMatchObject({ ok: false, code: 'bad-prompt' })
    expect(h.spawns).toEqual([])
    expect(h.queries).toEqual([])
  })

  test('a second ask while one runs is refused busy; once its fork ended, another is taken', async () => {
    const h = await live()
    const first = await h.command({ op: 'ask', prompt: 'one' })
    expect(await h.command({ op: 'ask', prompt: 'two' })).toMatchObject({ ok: false, code: 'busy', error: ASK_BUSY })
    expect(h.spawns).toHaveLength(1)
    await forkEnds(h, first.result ? (first.result as { agentId: string }).agentId : '')
    expect(await h.command({ op: 'ask', prompt: 'three' })).toMatchObject({ ok: true, result: { started: true, agentId: 'afork2' } })
  })

  test('two asks that arrive together: one is taken, the other busy', async () => {
    const h = await live()
    const [a, b] = await Promise.all([h.command({ op: 'ask', prompt: 'a' }), h.command({ op: 'ask', prompt: 'b' })])
    expect([a.ok, b.ok].sort()).toEqual([false, true])
    expect([a, b].find((r) => r.ok === false)).toMatchObject({ code: 'busy' })
    expect(h.spawns).toHaveLength(1)
  })

  test('with no guard loaded, refused no-guard and nothing spawned; a guard unloaded later turns ask off the same way', async () => {
    const none = await live({ guard: false })
    expect(await none.command({ op: 'ask', prompt: 'q' })).toMatchObject({ ok: false, code: 'no-guard', error: NO_GUARD })
    expect(none.spawns).toEqual([])
    const h = await live()
    const r = await h.command({ op: 'ask', prompt: 'q' })
    await forkEnds(h, (r.result as { agentId: string }).agentId)
    h.setGuard(false)
    expect(await h.command({ op: 'ask', prompt: 'again' })).toMatchObject({ ok: false, code: 'no-guard' })
    expect(h.spawns).toHaveLength(1)
  })

  test('a session that has made no request yet is refused nothing-to-fork', async () => {
    const h = await live({ messages: [] })
    expect(await h.command({ op: 'ask', prompt: 'q' })).toMatchObject({ ok: false, code: 'nothing-to-fork', error: NOTHING_TO_FORK })
    expect(h.spawns).toEqual([])
  })

  test("the engine's refusal of the spawn is the op's, coded spawn-refused (manager query takes the headless fork), and nothing stays open", async () => {
    const h = await live({ spawnDeny: 'past a Stop nothing is spawned' })
    expect(await h.command({ op: 'ask', prompt: 'q' })).toMatchObject({ ok: false, code: 'spawn-refused', error: 'the fork was not spawned: past a Stop nothing is spawned' })
    expect(h.sessionState.get('bridgeAsk') ?? []).toEqual([])
    expect(h.ofType('ask')).toEqual([])
  })

  test('an end is matched to its own agent only: another agent ending, or the main turn, ends nothing', async () => {
    const h = await live()
    const r = await h.command({ op: 'ask', prompt: 'q' })
    await forkEnds(h, 'asomeoneelse')
    await h.turn('tmain')
    await h.complete('tmain')
    expect(h.ofType('ask').map((e) => e.phase)).toEqual(['start'])
    await forkEnds(h, 'afork1', { reason: 'aborted', isAborted: true, usage: undefined, answer: '' })
    expect(h.ofType('ask')[1]).toEqual(expect.objectContaining({ phase: 'end', id: r.id, agentId: 'afork1', reason: 'aborted' }))
  })

  test('idle, the fork gets no tail: it sees the whole conversation', async () => {
    const h = await live()
    await h.turn('t1')
    await h.step({ turnId: 't1', index: 0, messageCount: 3, model: 'm' }, [{ kind: 'tool', index: 0, id: 'toolu_s', name: 'Bash' }, { kind: 'stop', stopReason: 'tool_use', usage: USAGE }])
    await h.complete('t1')
    h.setRows([asked('go'), called('toolu_s', 'Bash', { command: 'sleep 20' }, 'slept'), said('SLEEP-DONE')])
    await h.command({ op: 'ask', prompt: 'q' })
    expect(h.spawns[0]!.prompt).toBe(askPrompt('', 'q'))
  })

  test('mid-turn, the tail carries what followed the last completed request: the latest tool call is named', async () => {
    const h = await live()
    await h.turn('t1')
    await h.step({ turnId: 't1', index: 0, messageCount: 3, model: 'm' }, [{ kind: 'text', index: 0, text: 'Sleeping.' }, { kind: 'tool', index: 1, id: 'toolu_s', name: 'Bash' }, { kind: 'stop', stopReason: 'tool_use', usage: USAGE }])
    h.setRows([asked('go'), said('Sleeping.'), called('toolu_s', 'Bash', { command: 'sleep 20' })])
    await h.command({ op: 'ask', prompt: 'What are you running?' })
    expect(h.spawns[0]!.prompt).toBe(askPrompt('the session wrote: Sleeping.\nthe session called: Bash({"command":"sleep 20"})\n  (still running in the session — not yours to run)', 'What are you running?'))
  })

  test("a continued turn: a response with no tool call (a Stop hook kept the turn going) is the tail's start, its prose in the fork's prompt", async () => {
    const h = await live()
    await h.turn('t1')
    await h.step({ turnId: 't1', index: 0, messageCount: 3, model: 'm' }, [
      { kind: 'text', index: 0, text: 'The tests pass; ' },
      { kind: 'text', index: 0, text: 'I will stop here.' },
      { kind: 'stop', stopReason: 'end_turn', usage: USAGE },
    ])
    // The turn goes on (a Stop hook's continuation): its next request is in flight.
    h.setRows([asked('go'), said('The tests pass; I will stop here.'), asked('Stop hook feedback: also run the linter.')])
    await h.command({ op: 'ask', prompt: 'Where are you?' })
    expect(h.spawns[0]!.prompt).toBe(askPrompt('the session wrote: The tests pass; I will stop here.', 'Where are you?'))
  })

  test('a response that never completed (no stop with usage) moves nothing: the tail starts at the last one that did', async () => {
    const h = await live()
    await h.turn('t1')
    await h.step({ turnId: 't1', index: 0, messageCount: 3, model: 'm' }, [{ kind: 'tool', index: 0, id: 'toolu_1', name: 'Read' }, { kind: 'stop', stopReason: 'tool_use', usage: USAGE }])
    await h.step({ turnId: 't1', index: 1, messageCount: 5, model: 'm' }, [{ kind: 'tool', index: 0, id: 'toolu_2', name: 'Bash' }, { kind: 'stop', stopReason: null, usage: null }])
    h.setRows([asked('go'), called('toolu_1', 'Read', { file_path: '/a' }, 'A'), called('toolu_2', 'Bash', { command: 'ls' })])
    await h.command({ op: 'ask', prompt: 'q' })
    expect(h.spawns[0]!.prompt).toContain('the session called: Read({"file_path":"/a"})\n  result: A\nthe session called: Bash({"command":"ls"})')
  })

  test("a subagent's response is no anchor: the tail follows the main loop's", async () => {
    const h = await live()
    await h.turn('t1')
    await h.step({ turnId: 't1', index: 0, messageCount: 3, model: 'm' }, [{ kind: 'tool', index: 0, id: 'toolu_m', name: 'Agent' }, { kind: 'stop', stopReason: 'tool_use', usage: USAGE }])
    await h.step({ turnId: 'ts', index: 0, messageCount: 1, model: 'm', agentId: 'asub' }, [{ kind: 'tool', index: 0, id: 'toolu_sub', name: 'Read' }, { kind: 'stop', stopReason: 'tool_use', usage: USAGE }])
    h.setRows([asked('go'), called('toolu_m', 'Agent', { description: 'look' })])
    await h.command({ op: 'ask', prompt: 'q' })
    expect(h.spawns[0]!.prompt).toContain('the session called: Agent({"description":"look"})')
  })

  test('an ask started in a module then reloaded ends once in its successor, aborted, under its own id and agent', async () => {
    const kept = new Map<string, unknown>()
    const before = await live({ sessionState: kept })
    const r = await before.command({ op: 'ask', prompt: 'still there?' })
    expect(kept.get('bridgeAsk')).toEqual([{ id: r.id, agentId: 'afork1' }])
    const after = await live({ sessionState: kept })
    expect(after.ofType('ask')).toEqual([expect.objectContaining({ phase: 'end', id: r.id, agentId: 'afork1', reason: 'aborted' })])
    expect(kept.get('bridgeAsk')).toEqual([])
    const next = await live({ sessionState: kept })
    expect(next.ofType('ask')).toEqual([])
  })

  const managed = (id: string, status: string) => ({ id, description: 'manager query', type: 'fork', status, spawnedBy: 'sminos' })

  test("busy is read from the agent list: a sminos fork still live after two reloads keeps the next ask busy; once it stopped, ask is taken", async () => {
    const kept = new Map<string, unknown>()
    const first = await live({ sessionState: kept })
    const r = await first.command({ op: 'ask', prompt: 'q' })
    const agentId = (r.result as { agentId: string }).agentId
    // Reload one: the ask ends aborted and leaves bridgeAsk; the fork runs on.
    const second = await live({ sessionState: kept, agents: [managed(agentId, 'running')] })
    expect(second.ofType('ask')).toEqual([expect.objectContaining({ phase: 'end', id: r.id, agentId, reason: 'aborted' })])
    expect(kept.get('bridgeAsk')).toEqual([])
    // Reload two: nothing of the ask is kept anywhere, and the fork still runs.
    const third = await live({ sessionState: kept, agents: [managed(agentId, 'running')] })
    for (const status of ['running', 'pending', 'waiting']) {
      third.setAgents([managed(agentId, status)])
      expect(await third.command({ op: 'ask', prompt: 'q' })).toMatchObject({ ok: false, code: 'busy', error: ASK_BUSY })
    }
    expect(third.spawns).toEqual([])
    third.setAgents([managed(agentId, 'completed')])
    expect(await third.command({ op: 'ask', prompt: 'q' })).toMatchObject({ ok: true, result: { started: true } })
  })

  test("another plugin's fork, the model's own fork, and a sminos subagent that is no fork leave ask free", async () => {
    const h = await live({
      agents: [
        { id: 'aprobe', description: 'fork probe', type: 'fork', status: 'running', spawnedBy: 'forkprobe' },
        { id: 'amodel', description: 'x', type: 'fork', status: 'running' },
        { id: 'asub', description: 'y', type: 'general-purpose', status: 'running', spawnedBy: 'sminos' },
      ],
    })
    expect(await h.command({ op: 'ask', prompt: 'q' })).toMatchObject({ ok: true, result: { started: true } })
  })

  /** A live harness whose last ask's fork has ended (its turn.complete heard), the agent list answering `listing(n)` at its n-th read from here. */
  const afterHeardEnd = async (listing: (agentId: string, n: number) => Record<string, unknown>[]) => {
    const h = await live()
    const r = await h.command({ op: 'ask', prompt: 'q' })
    const agentId = (r.result as { agentId: string }).agentId
    await forkEnds(h, agentId)
    let reads = 0
    ;(h.engine as unknown as { agent: { list: () => Promise<unknown> } }).agent.list = async () => listing(agentId, ++reads)
    return { h, reads: () => reads }
  }

  test("a fork whose end this module heard, still listed running a moment, is read again within a short grace: once it is listed completed, the next ask is taken", async () => {
    const { h, reads } = await afterHeardEnd((id, n) => [managed(id, n < 3 ? 'running' : 'completed')])
    expect(await h.command({ op: 'ask', prompt: 'again' })).toMatchObject({ ok: true, result: { started: true } })
    expect(reads()).toBe(3)
  })

  test("a heard end whose fork stays waiting (background work of its own) is busy at once: waiting gets no grace", async () => {
    const { h, reads } = await afterHeardEnd((id) => [managed(id, 'waiting')])
    expect(await h.command({ op: 'ask', prompt: 'again' })).toMatchObject({ ok: false, code: 'busy' })
    expect(reads()).toBe(1)
    expect(h.spawns).toHaveLength(1)
  })

  test("a heard end whose listing stays running past the grace is busy: the list is authoritative", async () => {
    const { h, reads } = await afterHeardEnd((id) => [managed(id, 'running')])
    expect(await h.command({ op: 'ask', prompt: 'again' })).toMatchObject({ ok: false, code: 'busy' })
    expect(reads()).toBe(ASK_GRACE_POLLS + 1)
    expect(h.spawns).toHaveLength(1)
  })

  test("a heard end gives no grace to another live sminos fork beside it", async () => {
    const { h, reads } = await afterHeardEnd((id) => [managed(id, 'running'), managed('aother', 'running')])
    expect(await h.command({ op: 'ask', prompt: 'again' })).toMatchObject({ ok: false, code: 'busy' })
    expect(reads()).toBe(1)
  })

  test('while the agent list cannot be read, ask is busy', async () => {
    const h = await live()
    ;(h.engine as unknown as { agent: { list: () => Promise<unknown> } }).agent.list = async () => {
      throw new Error('$.agent.list: the host did not answer')
    }
    expect(await h.command({ op: 'ask', prompt: 'q' })).toMatchObject({ ok: false, code: 'busy' })
    expect(h.spawns).toEqual([])
  })

  test("open asks are kept under bridgeAsk, beside the async question tool's snapshot under ask: neither overwrites the other across a reload", async () => {
    const kept = new Map<string, unknown>()
    const snapshot = { shape: 2, asks: [{ id: 'toolu_q', questions: [], status: 'open' }], undelivered: [{ id: 'toolu_q', text: 'yes' }], isTurnRunning: false, isDialogUp: false, answered: 1 }
    kept.set('ask', snapshot)
    const before = await live({ sessionState: kept })
    const r = await before.command({ op: 'ask', prompt: 'q' })
    expect(kept.get('ask')).toEqual(snapshot)
    expect(kept.get('bridgeAsk')).toEqual([{ id: r.id, agentId: 'afork1' }])
    await live({ sessionState: kept })
    expect(kept.get('ask')).toEqual(snapshot)
    expect(kept.get('bridgeAsk')).toEqual([])
  })

  test("an end that came while no child was there reaches the next child after its resync, once", async () => {
    const h = await live()
    const r = await h.command({ op: 'ask', prompt: 'across a crash' })
    const timers = h.timers.length
    h.children[0]!.end()
    await h.settle()
    await forkEnds(h, 'afork1')
    h.timers[timers]!.fn()
    await h.settle()
    h.children[1]!.write(hello(SID, SOCK, undefined, 'n1'))
    await h.settle()
    const toNext = h.posts.filter((p) => p.nonce === 'n1').flatMap((p) => p.events)
    expect(toNext.map((e) => e.type)).toEqual(['session', 'resync', 'ask'])
    expect(toNext[2]).toMatchObject({ phase: 'end', id: r.id, text: 'It waits on you.' })
  })

  test('the capabilities name ask among the ops and the controls', async () => {
    const h = await live()
    expect(h.ofType('resync')[0]!.capabilities).toMatchObject({ ops: expect.arrayContaining(['ask']), controls: { ask: { available: true } } })
  })
})
