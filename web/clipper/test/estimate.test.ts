import { test } from 'node:test'
import assert from 'node:assert/strict'
import { estimateTokens, TokenCounter } from '../src/estimate.ts'

test('ASCII text counts one token per four characters, rounded up', () => {
  assert.equal(estimateTokens(''), 0)
  assert.equal(estimateTokens('abcd'), 1)
  assert.equal(estimateTokens('abcde'), 2)
  assert.equal(estimateTokens('a'.repeat(400)), 100)
})

test('a non-ASCII character counts as one token', () => {
  assert.equal(estimateTokens('한국어'), 3)
  assert.equal(estimateTokens('中文'), 2)
  // An astral character is one character, not two UTF-16 units.
  assert.equal(estimateTokens('😀'), 1)
  // Mixed: 8 ASCII (2 tokens) + 2 non-ASCII.
  assert.equal(estimateTokens('abcdefgh한글'), 4)
})

test('the counter gives the estimate of everything added, as one text', () => {
  const c = new TokenCounter()
  c.add('ab')
  c.add('cd')
  assert.equal(c.value, 1) // "abcd" is one token, not two half lines rounded up each
  c.add('é')
  assert.equal(c.value, 2)
  assert.equal(c.peek('efgh'), 3)
  assert.equal(c.value, 2)
})
