import type { On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { describe, expect, mock, test, tier } from 'claude-code/testing'

import type { FileChange } from '../../hooks/mods/edits'
import { changeOf, lineCount, runOf, summaryParts } from '../../hooks/mods/edits'

tier('user')

const line = (changes: FileChange[]) => summaryParts(changes).map((part) => part.text).join('')
const change = (path: string, added: number, removed: number, more: Partial<FileChange> = {}): FileChange => ({ path, isCreate: false, added, removed, isDone: true, ...more })
const call = { isErrored: false, isInterrupted: false }

describe('changes', () => {
  test("an edit counts its result's patch, a new file what was written", async () => {
    const patch = [{ oldStart: 1, oldLines: 2, newStart: 1, newLines: 3, lines: [' a', '-b', '+c', '+d'] }]
    expect(changeOf({ ...call, tool: 'Edit', input: { file_path: '/r/a.py' }, output: { filePath: '/r/a.py', structuredPatch: patch } }))
      .toEqual({ path: '/r/a.py', isCreate: false, added: 2, removed: 1, isDone: true })
    expect(changeOf({ ...call, tool: 'Write', input: { file_path: '/r/n.md', content: 'x\ny\n' }, output: { type: 'create', content: 'x\ny\n', structuredPatch: [] } }))
      .toEqual({ path: '/r/n.md', isCreate: true, added: 2, removed: 0, isDone: true })
    expect(lineCount('one')).toBe(1)
  })

  test('a call still running has no counts, and an errored or other call is no change', async () => {
    expect(changeOf({ ...call, tool: 'Edit', input: { file_path: '/r/a.py' } })?.isDone).toBe(false)
    expect(changeOf({ ...call, isErrored: true, tool: 'Edit', input: { file_path: '/r/a.py' }, output: 'String not found' })).toBeUndefined()
    expect(changeOf({ ...call, tool: 'Bash', input: { command: 'ls' }, output: {} })).toBeUndefined()
  })

  test('a change staged for review, not applied, is no change', async () => {
    const patch = [{ oldStart: 1, oldLines: 1, newStart: 1, newLines: 1, lines: ['-a', '+b'] }]
    expect(changeOf({ ...call, tool: 'Edit', input: { file_path: '/r/a.py' }, output: { filePath: '/r/a.py', structuredPatch: patch, staged: true } })).toBeUndefined()
  })

  test("a notebook cell counts by its edit's mode, a replace only the lines that differ", async () => {
    const cell = (mode: string, old_source: string | undefined, new_source: string) =>
      changeOf({ ...call, tool: 'NotebookEdit', input: { notebook_path: '/r/n.ipynb', new_source }, output: { notebook_path: '/r/n.ipynb', edit_mode: mode, old_source, new_source } })
    const body = Array.from({ length: 100 }, (_, i) => `line ${i}`)
    const changed = body.map((text, i) => (i === 50 ? 'new' : text))
    expect(cell('replace', body.join('\n'), changed.join('\n'))).toMatchObject({ added: 1, removed: 1 })
    expect(cell('insert', undefined, 'a\nb\n')).toMatchObject({ added: 2, removed: 0 })
    expect(cell('delete', 'a\nb\nc', 'ignored')).toMatchObject({ added: 0, removed: 3 })
  })

  test('the line names each file with its own counts, one entry per file', async () => {
    expect(line([change('/r/build.py', 3, 0), change('/r/x/to-human.tsx', 40, 12), change('/r/build.py', 1, 1)]))
      .toBe('Edited build.py +4 -1, to-human.tsx +40 -12')
    expect(line([change('/r/a.ts', 1, 0), change('/r/n.md', 9, 0, { isCreate: true })])).toBe('Edited a.ts +1, created n.md +9')
  })

  test('two files of one name are told apart by their folder, and many files are counted', async () => {
    expect(line([change('/r/a/index.ts', 1, 0), change('/r/b/index.ts', 0, 2)])).toBe('Edited a/index.ts +1, b/index.ts -2')
    expect(line(['/a', '/b', '/c', '/d'].map((path) => change(path, 1, 1)))).toBe('Edited 4 files +4 -4')
  })

  test('a running call is named in progress', async () => {
    expect(line([change('/r/a.ts', 1, 0), change('/r/b.ts', 0, 0, { isDone: false })])).toBe('Editing a.ts +1, b.ts…')
  })

  test('a run is the file changes beside each other, up to the next other row', async () => {
    const changes = new Map([['e1', change('/a', 1, 0)], ['e2', change('/b', 1, 0)], ['e3', change('/c', 1, 0)]])
    expect(runOf(['m', 'e1', 'e2', 'b', 'e3'], changes, 'e2')).toEqual(['e1', 'e2'])
    expect(runOf(['m', 'e1', 'e2', 'b', 'e3'], changes, 'e3')).toEqual(['e3'])
  })
})

describe('the summary line', () => {
  const PLUGIN = 'to-human'
  const patch = (added: number) => [{ oldStart: 1, oldLines: 0, newStart: 1, newLines: added, lines: Array.from({ length: added }, () => '+x') }]
  const edit = (id: string, path: string, added: number) => ({
    tool_use_id: id, tool: 'Edit', input: { file_path: path, old_string: '', new_string: 'x' }, isRunning: false, isErrored: false, isInterrupted: false,
    output: { filePath: path, structuredPatch: patch(added) },
  })
  const setUp = async ($: Engine, on: On) => {
    mock.env(on, {})
    mock.store(on)
    on('ui.render', (_, e) => ({ type: 'Text', children: [String((e.props as { text?: string }).text ?? e.component)] }))
    await $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId: 'm1', props: { text: '<message>Editing.</message>', isFirstOfReply: true } })
  }
  const rows = async ($: Engine, props: ReturnType<typeof edit>, isExpanded = false) => {
    const use = await $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'ToolUse', requestId: props.tool_use_id, props: { ...props, isExpanded } } as never)
    const result = await $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'ToolResult', requestId: props.tool_use_id,
      props: { tool_use_id: props.tool_use_id, tool: props.tool, output: props.output, isErrored: false, isExpanded },
    } as never)
    return { use, result }
  }

  test('a run of edits draws one line in its first row, and a press unfolds their diffs', async ($, on) => {
    await setUp($, on)
    const first = await rows($, edit('e1', '/r/a.py', 3))
    const second = await rows($, edit('e2', '/r/b.py', 2))
    await first.use.press({ key: 'to-human-toggle' })

    expect((await first.use.find({ type: 'Button', key: 'to-human-edits' }))?.text).toBe('Edited a.py +3, b.py +2 ›')
    for (const row of [first.use, first.result, second.use, second.result]) {
      expect(await row.find({ type: 'Text', text: /^Tool(Use|Result)$/ })).toBeUndefined()
    }
    expect(await second.use.find({ type: 'Button', key: 'to-human-edits' })).toBeUndefined()

    await first.use.press({ key: 'to-human-edits' })
    expect((await first.use.find({ type: 'Button', key: 'to-human-edits' }))?.text).toBe('Edited a.py +3, b.py +2')
    expect(await first.use.find({ type: 'Text', text: 'ToolUse' })).toBeDefined()
    expect(await second.result.find({ type: 'Text', text: 'ToolResult' })).toBeDefined()

    await first.use.press({ key: 'to-human-edits' })
    expect(await second.result.find({ type: 'Text', text: 'ToolResult' })).toBeUndefined()
  })

  test('a result drawn before its call is hidden once the call is summarized', async ($, on) => {
    await setUp($, on)
    const props = edit('e1', '/r/a.py', 3)
    const result = await $.ui.mount({
      plugin: PLUGIN, surface: 'terminal', component: 'ToolResult', requestId: 'e1',
      props: { tool_use_id: 'e1', tool: 'Edit', output: props.output, isErrored: false, isExpanded: false },
    } as never)
    const use = await $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'ToolUse', requestId: 'e1', props: { ...props, isExpanded: false } } as never)
    await use.press({ key: 'to-human-toggle' })

    expect((await use.find({ type: 'Button', key: 'to-human-edits' }))?.text).toBe('Edited a.py +3 ›')
    expect(await result.find({ type: 'Text', text: 'ToolResult' })).toBeUndefined()
  })

  test('a staged edit keeps both its rows as the engine draws them', async ($, on) => {
    await setUp($, on)
    const props = edit('e1', '/r/a.py', 3)
    const { use, result } = await rows($, { ...props, output: { ...props.output, staged: true } } as never)
    await use.press({ key: 'to-human-toggle' })

    expect(await use.find({ type: 'Button', key: 'to-human-edits' })).toBeUndefined()
    expect(await use.find({ type: 'Text', text: 'ToolUse' })).toBeDefined()
    expect(await result.find({ type: 'Text', text: 'ToolResult' })).toBeDefined()
  })

  test('the ctrl+o transcript keeps every diff', async ($, on) => {
    await setUp($, on)
    const { use, result } = await rows($, edit('e1', '/r/a.py', 3), true)
    await $.ui.mount({ plugin: PLUGIN, surface: 'terminal', component: 'AssistantMessage', requestId: 'm2', props: { text: '<message>Done.</message>', isFirstOfReply: true } })
    await use.press({ key: 'to-human-toggle' })

    expect(await use.find({ type: 'Text', text: 'ToolUse' })).toBeDefined()
    expect(await result.find({ type: 'Text', text: 'ToolResult' })).toBeDefined()
  })
})
