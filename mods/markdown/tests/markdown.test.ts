import { describe, expect, test, tier } from 'claude-code/testing'

import { parse, parseInline, widthOf, wrapRuns } from '../hooks/markdown'

tier('user')

describe('markdown', () => {
  test('blocks: heading, paragraph, fence, rule, quote', async () => {
    const blocks = parse('# Title\n\nSome *text*.\n\n```ts\nlet x = 1\n```\n\n---\n\n> quoted\n> more')

    expect(blocks.map(b => b.kind)).toEqual(['heading', 'paragraph', 'code', 'rule', 'quote'])
    expect(blocks[2]).toEqual({ kind: 'code', language: 'ts', source: 'let x = 1' })
    expect(blocks[4]).toEqual({
      kind: 'quote',
      blocks: [{ kind: 'paragraph', inline: [{ text: 'quoted more' }] }],
    })
  })

  test('an unclosed fence runs to the end while streaming', async () => {
    const blocks = parse('Before\n\n```py\nprint(1)\nprint(2)')

    expect(blocks[1]).toEqual({ kind: 'code', language: 'py', source: 'print(1)\nprint(2)' })
  })

  test('lists nest, number, and carry task boxes', async () => {
    const blocks = parse('1. one\n2. two\n   - inner\n   - [x] done\n\nAfter')
    const list = blocks[0]

    expect(list?.kind).toBe('list')
    if (list?.kind !== 'list') {
      return
    }
    expect(list.ordered).toBe(true)
    expect(list.loose).toBe(false)
    expect(list.items.length).toBe(2)
    const nested = list.items[1]?.blocks[1]
    expect(nested?.kind).toBe('list')
    if (nested?.kind !== 'list') {
      return
    }
    expect(nested.items[1]?.checked).toBe(true)
    expect(nested.items[1]?.blocks[0]).toEqual({ kind: 'paragraph', inline: [{ text: 'done' }] })
    expect(blocks[1]?.kind).toBe('paragraph')
  })

  test('a blank line between items makes a loose list', async () => {
    const blocks = parse('- a\n\n- b')

    expect(blocks.length).toBe(1)
    expect(blocks[0]?.kind === 'list' && blocks[0].loose).toBe(true)
  })

  test('tables split cells, read alignment and pad short rows', async () => {
    const blocks = parse('| a | b |\n|:--|--:|\n| 1 |\n| `x|y` | 2 |')
    const table = blocks[0]

    expect(table?.kind).toBe('table')
    if (table?.kind !== 'table') {
      return
    }
    expect(table.align).toEqual(['left', 'right'])
    expect(table.rows[0]).toEqual([[{ text: '1' }], []])
    expect(table.rows[1]?.[0]).toEqual([{ text: 'x|y', code: true }])
  })

  test('inline: emphasis, code, strike, links, escapes, snake_case', async () => {
    expect(parseInline('**bold** and *it* and `co*de` ~~no~~')).toEqual([
      { text: 'bold', bold: true },
      { text: ' and ' },
      { text: 'it', italic: true },
      { text: ' and ' },
      { text: 'co*de', code: true },
      { text: ' ' },
      { text: 'no', strike: true },
    ])
    expect(parseInline('[**AP** exam](https://example.com/a) see https://x.io/p.')).toEqual([
      { text: 'AP', bold: true, href: 'https://example.com/a' },
      { text: ' exam', href: 'https://example.com/a' },
      { text: ' see ' },
      { text: 'https://x.io/p', href: 'https://x.io/p' },
      { text: '.' },
    ])
    expect(parseInline('a \\*literal\\* snake_case_name *open')).toEqual([{ text: 'a *literal* snake_case_name *open' }])
    expect(parseInline('***both***')).toEqual([{ text: 'both', bold: true, italic: true }])
  })

  test('width counts Hangul and CJK as two cells', async () => {
    expect(widthOf('티베트 (Tibet)')).toBe(6 + 8)
    expect(widthOf('abc')).toBe(3)
  })

  test('wrap breaks at spaces, keeps styles, splits a long word', async () => {
    const lines = wrapRuns([{ text: 'one two ', bold: true }, { text: 'three four' }], 9)

    expect(lines).toEqual([
      [{ text: 'one two', bold: true }],
      [{ text: 'three' }],
      [{ text: 'four' }],
    ])
    expect(wrapRuns([{ text: 'abcdefghij' }], 4)).toEqual([[{ text: 'abcd' }], [{ text: 'efgh' }], [{ text: 'ij' }]])
  })
})
