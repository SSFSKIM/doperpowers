import { test } from 'node:test'
import assert from 'node:assert/strict'
import { numbered } from '../src/numbered.ts'
import { estimateTokens } from '../src/estimate.ts'

test('every line is prefixed with its number when the whole file fits', () => {
  const { header, body } = numbered('alpha\nbeta\n', 1000, 0)
  assert.deepEqual(header, { firstLine: 1, lastLine: 2, totalLines: 2 })
  assert.equal(body, '1| alpha\n2| beta\n')
})

test('numbering stops before the line that would pass the cap, reserve included, and reports the last line it included', () => {
  const lines = Array.from({ length: 100 }, (_, i) => `line ${i + 1} ${'x'.repeat(30)}`)
  const text = lines.join('\n') + '\n'
  const { header, body } = numbered(text, 200, 40)
  assert.equal(header.totalLines, 100)
  assert.ok(header.lastLine > 0 && header.lastLine < 100)
  assert.equal(body.split('\n').filter(Boolean).length, header.lastLine)
  assert.ok(estimateTokens(body) + 40 <= 200)
  const oneMore = body + `${header.lastLine + 1}| ${lines[header.lastLine]}\n`
  assert.ok(estimateTokens(oneMore) + 40 > 200)
  assert.ok(body.endsWith(`${header.lastLine}| ${lines[header.lastLine - 1]}\n`))
})

test('a first line that alone passes the cap is printed cut to fit, and the header says so', () => {
  const huge = 'x'.repeat(4000) + '한'.repeat(10)
  const { header, body } = numbered(huge + '\nsecond\n', 300, 20)
  assert.deepEqual(header, { firstLine: 1, lastLine: 1, totalLines: 2, cut: true })
  assert.ok(body.startsWith('1| xxxx') && body.endsWith('\n'))
  assert.equal(body.split('\n').length, 2) // one line, then the final newline
  assert.ok(estimateTokens(body) + 20 <= 300)
  assert.ok(estimateTokens(body) + 20 > 296, 'cut as late as fits')
  // Cut by characters, never inside one: a multi-byte character is whole or absent.
  const korean = numbered('가'.repeat(500) + '\n', 100, 0)
  assert.equal(korean.header.cut, true)
  assert.match(korean.body, /^1\| 가+\n$/)
  assert.ok(estimateTokens(korean.body) <= 100)
  // A first line that fits leaves no flag.
  assert.equal('cut' in numbered('short\n', 100, 0).header, false)
})

test('a carriage return at a line end is dropped; an empty file numbers nothing', () => {
  assert.equal(numbered('a\r\nb\r\n', 100, 0).body, '1| a\n2| b\n')
  assert.deepEqual(numbered('', 100, 0).header, { firstLine: 1, lastLine: 0, totalLines: 0 })
})
