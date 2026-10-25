import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { join } from 'node:path'
import { normalizeUrl, entryDir } from '../src/key.ts'

test('normalization lowercases scheme and host, drops the default port and fragment, keeps the query', () => {
  assert.equal(normalizeUrl(new URL('HTTPS://Example.COM:443/A/B?x=1&Y=2#frag')), 'https://example.com/A/B?x=1&Y=2')
  assert.equal(normalizeUrl(new URL('http://example.com:8080/')), 'http://example.com:8080/')
  assert.equal(normalizeUrl(new URL('http://example.com')), 'http://example.com/')
})

test('the entry folder is <host>/<slug>-<hash8> of the normalized URL', () => {
  const url = new URL('https://Docs.Example.com/en/Docs/Build_With.Claude/prompt-caching?v=2#x')
  const hash = createHash('sha256').update('https://docs.example.com/en/Docs/Build_With.Claude/prompt-caching?v=2').digest('hex').slice(0, 8)
  assert.equal(entryDir('/c', url), join('/c', 'docs.example.com', `en-docs-build-with-claude-prompt-caching-${hash}`))
})

test('an empty path is "index"; a long path is cut to 60 characters without a trailing dash', () => {
  assert.match(entryDir('/c', new URL('https://example.com/')), /\/example\.com\/index-[0-9a-f]{8}$/)
  const long = new URL('https://example.com/' + 'abcdefghi/'.repeat(10))
  const slug = entryDir('/c', long).split('/').pop()!.replace(/-[0-9a-f]{8}$/, '')
  assert.ok(slug.length <= 60, slug)
  assert.ok(!slug.endsWith('-'))
})

test('a non-default port is kept in the host folder', () => {
  assert.match(entryDir('/c', new URL('http://127.0.0.1:8080/x')), /\/127\.0\.0\.1_8080\/x-[0-9a-f]{8}$/)
})
