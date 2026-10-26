import { test } from 'node:test'
import assert from 'node:assert/strict'
import http from 'node:http'
import { CONNECT_ATTEMPT_MS, HttpError, networkErrorMessage, referrerFor, request } from '../src/http.ts'
import { boundaryOf } from '../src/netguard.ts'
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

test('an OpenSSL error gives its reason, not its record dump', () => {
  // httpforever.com over https, 2026-10-25.
  const e = new Error('write EPROTO 80A10DFA01000000:error:0A000410:SSL routines:ssl3_read_bytes:ssl/tls alert handshake failure:../deps/openssl/openssl/ssl/record/rec_layer_s3.c:916:SSL alert number 40\n')
  assert.equal(networkErrorMessage(e), 'TLS failed: ssl/tls alert handshake failure')
  assert.equal(networkErrorMessage(new Error('80B1:error:0A00010B:SSL routines::wrong version number:../deps/x.c:1:')), 'TLS failed: wrong version number')
  assert.equal(networkErrorMessage(new Error('certificate has expired')), 'certificate has expired')
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
  const res = await request(new URL(`${server.origin}/`), { headers: {}, timeoutMs: 5000, maxBytes: 1024, boundary: boundaryOf({ WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }) })
  assert.equal(res.status, 200)
  assert.equal(seen.length, 1)
  assert.equal((seen[0] as { autoSelectFamilyAttemptTimeout?: number }).autoSelectFamilyAttemptTimeout, CONNECT_ATTEMPT_MS)
})

test('the Referer follows strict-origin-when-cross-origin, and never carries a fragment or credentials', () => {
  const page = 'https://user:pw@site.test/a/page?token=secret#frag'
  // Same origin: the page's URL, without its fragment and credentials.
  assert.equal(referrerFor(page, new URL('https://site.test/img/x.png')), 'https://site.test/a/page?token=secret')
  // Another origin (host, port or scheme): the page's origin only.
  assert.equal(referrerFor(page, new URL('https://cdn.test/x.png')), 'https://site.test/')
  assert.equal(referrerFor(page, new URL('https://site.test:8443/x.png')), 'https://site.test/')
  // HTTPS to HTTP: nothing.
  assert.equal(referrerFor(page, new URL('http://site.test/x.png')), undefined)
  assert.equal(referrerFor('http://site.test/p?q=1', new URL('https://cdn.test/x.png')), 'http://site.test/')
  // A page that is not http(s) gives nothing.
  assert.equal(referrerFor('data:text/html,hi', new URL('https://cdn.test/x.png')), undefined)
})

test('a referrer is worked out again at every redirect hop, so a hop to another origin sees only the origin', async t => {
  const seen: Record<string, string | undefined> = {}
  const record = (name: string) => (req: http.IncomingMessage, res: http.ServerResponse) => { seen[name] = req.headers.referer; send('image/png', 'x'.repeat(2000))(req, res) }
  const other = await startServer({ '/img/y.png': record('other') })
  t.after(() => other.close())
  const site = await startServer({
    '/img/same.png': record('same'),
    '/hop': (req, res) => { seen.hop = req.headers.referer; res.writeHead(302, { location: `${other.origin}/img/y.png` }); res.end() },
  })
  t.after(() => site.close())
  const boundary = boundaryOf({ WEB_ALLOW_HOSTS: `127.0.0.1:${site.port},127.0.0.1:${other.port}` })
  const page = `${site.origin}/page?token=secret#frag`
  await request(new URL(`${site.origin}/img/same.png`), { referrer: page, timeoutMs: 5000, maxBytes: 1e6, boundary })
  await request(new URL(`${site.origin}/hop`), { referrer: page, timeoutMs: 5000, maxBytes: 1e6, boundary })
  assert.equal(seen.same, `${site.origin}/page?token=secret`)
  assert.equal(seen.hop, `${site.origin}/page?token=secret`)
  assert.equal(seen.other, `${site.origin}/`)
  // A Referer passed as a header is held to the same policy.
  delete seen.other
  await request(new URL(`${other.origin}/img/y.png`), { headers: { Referer: page }, timeoutMs: 5000, maxBytes: 1e6, boundary })
  assert.equal(seen.other, `${site.origin}/`)
})

/** A server whose `/` sends its headers, then `chunks` pieces of `size` bytes `everyMs` apart (forever when Infinity), then ends. */
async function trickle(t: { after: (fn: () => Promise<void>) => void }, o: { chunks: number; size: number; everyMs: number; length?: number }) {
  const timers: NodeJS.Timeout[] = []
  const server = await startServer({
    '/': (_req, res) => {
      res.writeHead(200, { 'content-type': 'application/octet-stream', ...(o.length ? { 'content-length': String(o.length) } : {}) })
      let sent = 0
      const next = () => {
        if (sent >= o.chunks) { if (!o.length) res.end(); return }
        res.write(Buffer.alloc(o.size, 120))
        sent++
        timers.push(setTimeout(next, o.everyMs))
      }
      next()
    },
    '/silent': () => {},
  })
  t.after(async () => { for (const x of timers) clearTimeout(x); await server.close() })
  return { server, boundary: boundaryOf({ WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }) }
}

const timedOut = (pattern: RegExp) => (e: unknown) => {
  assert.ok(e instanceof HttpError, String(e))
  assert.match(e.message, pattern)
  assert.equal(e.timedOut, true)
  return true
}

test('a body still arriving runs past the time to the headers, to the whole time', async t => {
  const { server, boundary } = await trickle(t, { chunks: 15, size: 1024, everyMs: 100 })
  const started = Date.now()
  const res = await request(new URL(`${server.origin}/`), { headersMs: 500, stallMs: 1000, timeoutMs: 10_000, maxBytes: 1e6, boundary })
  assert.equal(res.body.length, 15 * 1024)
  assert.ok(Date.now() - started > 1000, 'the body took past the headers limit')
})

test('headers that do not come in the time to the headers fail with no response, well before the whole time', async t => {
  const { server, boundary } = await trickle(t, { chunks: 0, size: 0, everyMs: 0 })
  const started = Date.now()
  await assert.rejects(request(new URL(`${server.origin}/silent`), { headersMs: 1000, stallMs: 500, timeoutMs: 10_000, maxBytes: 1e6, boundary }), timedOut(/^no response within 1 s$/))
  assert.ok(Date.now() - started < 5000)
})

test('a body that stops arriving fails at the stall limit, saying how much came', async t => {
  const { server, boundary } = await trickle(t, { chunks: 2, size: 64 * 1024, everyMs: 50, length: 2 * 1048576 })
  const started = Date.now()
  await assert.rejects(request(new URL(`${server.origin}/`), { headersMs: 1000, stallMs: 1000, timeoutMs: 10_000, maxBytes: 1e7, boundary }), timedOut(/^stalled: no data for 1 s after 128 KB of 2\.0 MB$/))
  assert.ok(Date.now() - started < 5000)
})

test('a body still arriving at the whole time fails with what it received', async t => {
  const { server, boundary } = await trickle(t, { chunks: Infinity, size: 1024, everyMs: 100 })
  await assert.rejects(request(new URL(`${server.origin}/`), { headersMs: 1000, stallMs: 1000, timeoutMs: 2000, maxBytes: 1e7, boundary }), timedOut(/^timed out after 2 s with \d+ KB received$/))
})

test('without a time to the headers, the whole time covers the headers as before', async t => {
  const { server, boundary } = await trickle(t, { chunks: 0, size: 0, everyMs: 0 })
  await assert.rejects(request(new URL(`${server.origin}/silent`), { timeoutMs: 1000, maxBytes: 1e6, boundary }), timedOut(/^timed out after 1 s$/))
})

test('a request that got no response is unanswered; one whose server answered, then failed, is not', async t => {
  const unanswered = (expected: boolean) => (e: unknown) => {
    assert.ok(e instanceof HttpError, String(e))
    assert.equal(e.unanswered, expected, e.message)
    return true
  }
  const { server, boundary } = await trickle(t, { chunks: 2, size: 1024, everyMs: 50, length: 1048576 })
  // No headers within the time.
  await assert.rejects(request(new URL(`${server.origin}/silent`), { timeoutMs: 500, maxBytes: 1e6, boundary }), unanswered(true))
  // No connection: nothing listens on the port.
  const closed = await startServer({})
  await closed.close()
  await assert.rejects(request(new URL(`${closed.origin}/`), { timeoutMs: 2000, maxBytes: 1e6, boundary: boundaryOf({ WEB_ALLOW_HOSTS: `127.0.0.1:${closed.port}` }) }), unanswered(true))
  // A name that does not resolve (.invalid never does; a resolver that hangs times out, unanswered too).
  await assert.rejects(request(new URL('http://no-such-host.invalid/x.png'), { timeoutMs: 3000, maxBytes: 1e6, boundary }), unanswered(true))
  // Headers came, then the body stopped, or ran past the size limit: the host answered.
  await assert.rejects(request(new URL(`${server.origin}/`), { timeoutMs: 10_000, stallMs: 500, maxBytes: 1e6, boundary }), unanswered(false))
  await assert.rejects(request(new URL(`${server.origin}/`), { timeoutMs: 10_000, maxBytes: 1500, boundary }), unanswered(false))
})

test('https to a server that does not speak TLS is an HttpError, the failure https first falls back from', async t => {
  const server = await startServer({ '/': send('text/plain', 'plain') })
  t.after(() => server.close())
  const boundary = boundaryOf({ WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` })
  await assert.rejects(request(new URL(`https://127.0.0.1:${server.port}/`), { timeoutMs: 5000, maxBytes: 1024, boundary }), (e: unknown) => {
    assert.ok(e instanceof HttpError, String(e))
    assert.match(e.message, /^network error: TLS failed: /)
    return true
  })
})
