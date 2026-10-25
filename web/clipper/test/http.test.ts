import { test } from 'node:test'
import assert from 'node:assert/strict'
import http from 'node:http'
import { CONNECT_ATTEMPT_MS, networkErrorMessage, request } from '../src/http.ts'
import { startServer, send } from './helpers.ts'

function connectError(code: string, address: string): Error {
  return Object.assign(new Error(`connect ${code} ${address}:443`), { code, address })
}

test("a failed connection to every address names each address and why, not an empty message", () => {
  // What Node throws when its address-by-address connect gives up: an AggregateError whose message is empty.
  const e = Object.assign(new AggregateError([connectError('ETIMEDOUT', '65.108.204.189'), connectError('EHOSTUNREACH', '2a01:4f9:1a:a084::2')], ''), { code: 'ETIMEDOUT' })
  assert.equal(networkErrorMessage(e), 'could not connect: 65.108.204.189 ETIMEDOUT, 2a01:4f9:1a:a084::2 EHOSTUNREACH')
})

test('an ordinary error keeps its message, and an error without one gives its code', () => {
  assert.equal(networkErrorMessage(new Error('socket hang up')), 'socket hang up')
  assert.equal(networkErrorMessage(Object.assign(new Error(''), { code: 'ECONNRESET' })), 'ECONNRESET')
  assert.equal(networkErrorMessage('boom'), 'boom')
})

test('each connection attempt may take far longer than Node’s 250 ms default before the next address is tried', async t => {
  // archive.apache.org from Seoul: a 250 ms attempt dropped the IPv4 connection while it was still
  // being made, and the IPv6 address was unreachable, so 4 of 12 image downloads failed (2026-10-25).
  assert.ok(CONNECT_ATTEMPT_MS >= 2000)
  const server = await startServer({ '/': send('text/plain', 'ok') })
  t.after(() => server.close())
  const seen: unknown[] = []
  const real = http.request
  t.mock.method(http, 'request', (...args: Parameters<typeof http.request>) => { seen.push(args[0]); return real(...args) })
  const res = await request(new URL(`${server.origin}/`), { headers: {}, timeoutMs: 5000, maxBytes: 1024, allow: new Set([`127.0.0.1:${server.port}`]) })
  assert.equal(res.status, 200)
  assert.equal(seen.length, 1)
  assert.equal((seen[0] as { autoSelectFamilyAttemptTimeout?: number }).autoSelectFamilyAttemptTimeout, CONNECT_ATTEMPT_MS)
})
