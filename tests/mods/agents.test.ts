import { describe, expect, test, tier } from 'claude-code/testing'

import type { AgentRow } from '../../hooks/mods/agents'
import { buildTree, buttonLabel, elapsed, summarize, toolLine } from '../../hooks/mods/agents'

tier('user')

const row = (id: string, parentId?: string): AgentRow => ({
  id,
  description: id,
  type: 'general-purpose',
  status: 'running',
  parentId,
})

describe('buildTree', () => {
  test('nests each agent under the one that spawned it, in spawn order', async () => {
    const tree = buildTree([row('c1'), row('s1', 'c1'), row('s2', 'c1'), row('s2s1', 's2'), row('c2'), row('c3')])

    expect(tree.map((r) => [r.id, r.depth])).toEqual([
      ['c1', 0],
      ['s1', 1],
      ['s2', 1],
      ['s2s1', 2],
      ['c2', 0],
      ['c3', 0],
    ])
  })

  test('an agent whose parent is not listed sits at the top level', async () => {
    const tree = buildTree([row('orphan', 'gone'), row('c1')])

    expect(tree.map((r) => [r.id, r.depth])).toEqual([
      ['orphan', 0],
      ['c1', 0],
    ])
  })

  test('a child listed before its parent still draws under it', async () => {
    const tree = buildTree([row('s1', 'c1'), row('c1')])

    expect(tree.map((r) => [r.id, r.depth])).toEqual([
      ['c1', 0],
      ['s1', 1],
    ])
  })
})

describe('summarize', () => {
  const line = (o: unknown) => JSON.stringify(o)
  const transcript = [
    line({ type: 'user', message: { role: 'user', content: 'Fix the parser.\nIt breaks on nesting.\nThird line.\nFourth line.' } }),
    line({ type: 'attachment', attachment: { type: 'hook_success' } }),
    line({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'thinking', thinking: 'hmm' }] } }),
    line({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'text', text: 'Reading the file first.' }] } }),
    line({
      type: 'assistant',
      message: { role: 'assistant', content: [{ type: 'tool_use', id: 't1', name: 'Read', input: { file_path: 'hooks/mods/to-human.tsx' } }] },
    }),
    line({
      type: 'user',
      message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 't1', content: '     1\timport x\n     2\timport y' }] },
    }),
    line({
      type: 'assistant',
      message: { role: 'assistant', content: [{ type: 'tool_use', id: 't2', name: 'Bash', input: { command: 'ls  -la\n  /tmp' } }] },
    }),
    line({
      type: 'user',
      message: {
        role: 'user',
        content: [{ type: 'tool_result', tool_use_id: 't2', is_error: true, content: [{ type: 'text', text: 'ls: cannot access' }] }],
      },
    }),
    line({ type: 'user', message: { role: 'user', content: [{ type: 'text', text: '<task-notification>done</task-notification>' }] } }),
    line({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'text', text: '' }] } }),
    line({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'text', text: 'Done.' }] } }),
    'not json',
  ].join('\n')

  test('keeps the prompt, the text, one line per tool call and the first line of each result', async () => {
    const { entries, skipped } = summarize(transcript, 400)

    expect(skipped).toBe(0)
    expect(entries).toEqual([
      { kind: 'prompt', text: 'Fix the parser.\nIt breaks on nesting.\nThird line. …' },
      { kind: 'text', text: 'Reading the file first.' },
      { kind: 'tool', text: 'Read(hooks/mods/to-human.tsx)' },
      { kind: 'result', text: '1\timport x', isError: false },
      { kind: 'tool', text: 'Bash(ls -la /tmp)' },
      { kind: 'result', text: 'ls: cannot access', isError: true },
      { kind: 'note', text: '<task-notification>done</task-notification>' },
      { kind: 'text', text: 'Done.' },
    ])
  })

  test('keeps only the newest entries past the cap and counts the rest', async () => {
    const { entries, skipped } = summarize(transcript, 3)

    expect(skipped).toBe(5)
    expect(entries.map((e) => e.kind)).toEqual(['result', 'note', 'text'])
  })

  test('an empty or unwritten transcript is no entries', async () => {
    expect(summarize('', 400)).toEqual({ entries: [], skipped: 0 })
  })
})

describe('toolLine', () => {
  test('names the tool and the one argument that identifies the call', async () => {
    expect(toolLine('Bash', { command: 'git status', description: 'Show status' })).toBe('Bash(git status)')
    expect(toolLine('Edit', { file_path: 'a.ts', old_string: 'x', new_string: 'y' })).toBe('Edit(a.ts)')
    expect(toolLine('Agent', { prompt: 'long…', description: 'review the diff', subagent_type: 'x' })).toBe(
      'Agent(review the diff)',
    )
    expect(toolLine('Grep', { pattern: 'foo', path: '.' })).toBe('Grep(foo)')
  })

  test('falls back to the first string argument, and to the bare name', async () => {
    expect(toolLine('mcp__ptc__exec', { code: 'print(1)', session: 'x' })).toBe('mcp__ptc__exec(print(1))')
    expect(toolLine('TaskOutput', { timeout: 30 })).toBe('TaskOutput')
    expect(toolLine('Skill', null)).toBe('Skill')
  })
})

describe('labels', () => {
  test('the button reads how many still run and how many are done', async () => {
    expect(buttonLabel(2, 0)).toBe('2 running')
    expect(buttonLabel(0, 3)).toBe('3 done')
    expect(buttonLabel(2, 3)).toBe('2 running · 3 done')
  })

  test('elapsed time reads at the grain a person glances at', async () => {
    expect(elapsed(12_000)).toBe('12s')
    expect(elapsed(62_000)).toBe('1m02s')
    expect(elapsed(3_780_000)).toBe('1h03m')
  })
})
