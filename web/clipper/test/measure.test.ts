import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildOutline, splitLines, OUTLINE_MAX_ENTRIES } from '../src/measure.ts'
import { estimateTokens } from '../src/estimate.ts'

const page = [
  '---', //                     1
  'title: "T"', //              2
  '---', //                     3
  '', //                        4
  'Intro text.', //             5
  '', //                        6
  '# Top', //                   7
  'a', //                       8
  '## One', //                  9
  'b', //                      10
  '![x](assets/01.png)', //    11
  '### One.a', //              12
  'c', //                      13
  '## Two', //                 14
  'd', //                      15
  '# Next', //                 16
  'e', //                      17
].join('\n') + '\n'

test('lines are what Read shows: a final newline does not start another line', () => {
  assert.equal(splitLines('a\nb\n').length, 2)
  assert.equal(splitLines('a\nb').length, 2)
  assert.equal(splitLines('').length, 0)
})

test('outline ranges nest, count the frontmatter lines, and sum their children', () => {
  const { outline, omitted } = buildOutline(page, 'markdown', [11])
  assert.equal(omitted, 0)
  const brief = outline.map(e => [e.level, e.title, e.line, e.endLine, e.images])
  assert.deepEqual(brief, [
    [0, '(frontmatter)', 1, 3, 0],
    [0, '(top)', 4, 6, 0],
    [1, 'Top', 7, 15, 1],
    [2, 'One', 9, 13, 1],
    [3, 'One.a', 12, 13, 0],
    [2, 'Two', 14, 15, 0],
    [1, 'Next', 16, 17, 0],
  ])
  const lines = splitLines(page)
  const top = outline[2]
  assert.equal(top.tokens, estimateTokens(lines.slice(6, 15).join('\n')))
  const one = outline[3]
  assert.ok(top.tokens > one.tokens)
})

test('a heading inside a fenced code block is not a heading', () => {
  const text = ['# Real', '```bash', '# not a heading', '```', '~~~~', '## also not', '~~~', '## still fenced', '~~~~', '## Real two', 'x'].join('\n')
  const { outline } = buildOutline(text, 'markdown', [])
  assert.deepEqual(outline.map(e => e.title), ['Real', 'Real two'])
})

test('past 80 entries the deepest level is dropped first, and the count of left-out headings is reported', () => {
  const lines = ['---', 'title: "x"', '---']
  for (let i = 0; i < 10; i++) {
    lines.push(`## Section ${i}`, 'text')
    for (let j = 0; j < 10; j++) lines.push(`### Sub ${i}.${j}`, 'text')
  }
  const { outline, omitted } = buildOutline(lines.join('\n'), 'markdown', [])
  assert.equal(omitted, 100)
  assert.equal(outline.length, 11)
  assert.ok(outline.every(e => e.level === 0 || e.level === 2))
  assert.ok(outline.length <= OUTLINE_MAX_ENTRIES)
})

test('two levels over the cap drop the deepest first, then stop once it fits', () => {
  const lines: string[] = []
  for (let i = 0; i < 30; i++) {
    lines.push(`# H1 ${i}`, `## H2 ${i}`)
    for (let j = 0; j < 2; j++) lines.push(`### H3 ${i}.${j}`)
  }
  // 30 + 30 + 60 = 120 entries: dropping H3 leaves 60, which fits.
  const { outline, omitted } = buildOutline(lines.join('\n'), 'markdown', [])
  assert.equal(outline.length, 60)
  assert.equal(omitted, 60)
})

test('one heading level over the cap keeps the first 80 entries', () => {
  const lines: string[] = []
  for (let i = 0; i < 100; i++) lines.push(`## H ${i}`, 'x')
  const { outline, omitted } = buildOutline(lines.join('\n'), 'markdown', [])
  assert.equal(outline.length, OUTLINE_MAX_ENTRIES)
  assert.equal(omitted, 20)
  assert.equal(outline[79].title, 'H 79')
})

test('a page with no headings gets one entry for the whole body', () => {
  const text = '---\ntitle: "x"\n---\n\nJust text.\nMore.\n'
  const { outline } = buildOutline(text, 'markdown', [])
  assert.deepEqual(outline.map(e => [e.title, e.line, e.endLine]), [['(frontmatter)', 1, 3], ['(body)', 4, 6]])
})

test('plain text is never read for headings', () => {
  const text = '# a shell comment\necho hi\n'
  const { outline } = buildOutline(text, 'plain', [])
  assert.deepEqual(outline.map(e => [e.level, e.title, e.line, e.endLine]), [[0, '(body)', 1, 2]])
})

test('a PDF outline has one entry per page, split at form feeds', () => {
  const text = 'Page one line 1\nPage one line 2\n\fPage two\nmore two\n\fPage three\n\f'
  const { outline } = buildOutline(text, 'pdf', [])
  assert.deepEqual(outline.map(e => [e.level, e.title, e.line, e.endLine]), [
    [1, 'page 1', 1, 2],
    [1, 'page 2', 3, 4],
    [1, 'page 3', 5, 5],
  ])
})
