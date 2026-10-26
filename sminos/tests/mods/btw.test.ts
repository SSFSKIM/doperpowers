import { describe, expect, test, tier } from 'claude-code/testing'
import { BTW_FRAME, BTW_TEXT_MAX, boundedText, btwEnd, framed } from '../../hooks/mods/bridge-btw'

tier('user')

const USAGE = { input_tokens: 12, output_tokens: 34, cache_read_input_tokens: 5000, cache_creation_input_tokens: 7 }
/** UTF-8 bytes, counted another way than the module counts them: each escaped byte one. */
const utf8 = (s: string) => encodeURIComponent(s).replace(/%[0-9A-F]{2}/g, 'x').length

describe('the side question', () => {
  test("the person's question is sent under the frame, as asked", () => {
    expect(BTW_FRAME).toBe('Answer the following without using any tools and without continuing your current task; one reply, then stop.')
    expect(framed('what did we decide\nabout the cache?')).toBe(`${BTW_FRAME}\n\nwhat did we decide\nabout the cache?`)
  })

  test('an answer is held to 64 KiB of UTF-8, cut between code points and marked truncated', () => {
    expect(BTW_TEXT_MAX).toBe(65_536)
    expect(boundedText('short')).toEqual({ text: 'short', truncated: false })
    const ascii = 'a'.repeat(BTW_TEXT_MAX)
    expect(boundedText(ascii)).toEqual({ text: ascii, truncated: false })
    expect(boundedText(`${ascii}b`)).toEqual({ text: ascii, truncated: true })
    // Three bytes a character: 21,845 of them fit (65,535 bytes), the next would not.
    const hangul = boundedText('가'.repeat(30_000))
    expect(hangul).toEqual({ text: '가'.repeat(21_845), truncated: true })
    expect(utf8(hangul.text)).toBe(65_535)
    // A character outside the BMP (two UTF-16 units, four bytes) is never split.
    const astral = boundedText(`${'a'.repeat(BTW_TEXT_MAX - 2)}😀`)
    expect(astral).toEqual({ text: 'a'.repeat(BTW_TEXT_MAX - 2), truncated: true })
  })

  test("an end carries the answer and what it cost, or why there is none, the cost wherever a request was made", () => {
    expect(btwEnd({ isAnswered: true, text: 'It is testing the cache.', usage: USAGE })).toEqual({
      text: 'It is testing the cache.',
      usage: { input: 12, output: 34, cacheRead: 5000, cacheWrite: 7 },
    })
    const long = btwEnd({ isAnswered: true, text: 'x'.repeat(BTW_TEXT_MAX + 1), usage: USAGE })
    expect(long).toMatchObject({ truncated: true, usage: { output: 34 } })
    expect(utf8(long.text as string)).toBe(BTW_TEXT_MAX)
    expect(btwEnd({ isAnswered: false, reason: 'nothing-to-fork' })).toEqual({ reason: 'nothing-to-fork' })
    expect(btwEnd({ isAnswered: false, reason: 'api-error', status: 529, error: 'overloaded', usage: USAGE })).toEqual({
      reason: 'api-error', status: 529, error: 'overloaded', usage: { input: 12, output: 34, cacheRead: 5000, cacheWrite: 7 },
    })
    expect(btwEnd({ isAnswered: false, reason: 'empty-reply', usage: USAGE })).toMatchObject({ reason: 'empty-reply', usage: { input: 12 } })
    expect(btwEnd({ isAnswered: false, reason: 'aborted', usage: USAGE })).toMatchObject({ reason: 'aborted' })
  })
})
