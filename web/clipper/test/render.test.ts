import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdir, writeFile, chmod, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { request } from 'node:http'
import { connect } from 'node:net'
import { clip } from '../src/clip.ts'
import type { ClipOk } from '../src/clip.ts'
import { findChrome, servedDocument } from '../src/render.ts'
import { startEgressProxy } from '../src/proxy.ts'
import { startServer, startTrap, startUdpTrap, tmpCache, send, fixture, noChrome, pngBytes } from './helpers.ts'

const WALLED_ARTICLE = '<html><head><title>Behind the wall</title></head><body><article><h1>Behind the wall</h1><p>'
  + 'This article is served only to clients that look like a browser, as a bot wall would serve it. '.repeat(8) + '</p></article></body></html>'

// A denial long enough to pass for a page, served with 403 to every client, browser or not.
const LONG_DENIAL = '<html><head><title>Access denied</title></head><body><main><h1>Access denied</h1><p>'
  + 'Your request was blocked by the security policy of this site, and the reference below identifies it to support. '.repeat(10) + '</p></main></body></html>'

// A walled article reached through a redirect, with a relative image and a relative link.
const MOVED_ARTICLE = '<html><head><title>Moved behind the wall</title></head><body><article><h1>Moved behind the wall</h1><p>'
  + 'This article moved, and is served only to clients that look like a browser. '.repeat(8)
  + '</p><p><img src="chart.png" alt="the chart"></p><p>Read the <a href="details">details</a>.</p></article></body></html>'

let server: Awaited<ReturnType<typeof startServer>>
let trap: Awaited<ReturnType<typeof startTrap>>
let udp: Awaited<ReturnType<typeof startUdpTrap>>

before(async () => {
  trap = await startTrap()
  udp = await startUdpTrap()
  const egress = (await fixture('egress.html')).replaceAll('{{TRAP}}', String(trap.port)).replaceAll('{{UDP}}', String(udp.port))
  server = await startServer({
    '/shell': send('text/html', await fixture('js-shell.html')),
    '/egress': send('text/html', egress),
    '/hello': send('text/plain', 'hello through the proxy'),
    '/slow': (_req, res) => { setTimeout(() => send('text/plain', 'ok')(_req, res), 2000) },
    // A bot wall: 403 to a client that is not a browser (Node sends no Sec-Fetch-* headers), the article to one that is.
    '/walled': (req, res) => req.headers['sec-fetch-mode']
      ? send('text/html', WALLED_ARTICLE)(req, res)
      : send('text/html', '<html><body><h1>Access denied</h1></body></html>', 403)(req, res),
    '/denied': send('text/html', LONG_DENIAL, 403),
    '/old': send('text/html', '', 301, { location: '/articles/post' }),
    '/articles/post': (req, res) => req.headers['sec-fetch-mode']
      ? send('text/html', MOVED_ARTICLE)(req, res)
      : send('text/html', '<html><body><h1>Access denied</h1></body></html>', 403)(req, res),
    '/articles/chart.png': send('image/png', pngBytes(2048, 7)),
    '/forbidden': send('text/html', '<html><body><h1>Forbidden</h1><p>No.</p></body></html>', 403),
  })
})

after(async () => {
  await server.close()
  await trap.close()
  await udp.close()
})

async function fakeBinary(path: string) {
  await mkdir(join(path, '..'), { recursive: true })
  await writeFile(path, '#!/bin/sh\n')
  await chmod(path, 0o755)
}

test('WEB_CHROME, when set, is the only candidate: a missing path or "none" turns rendering off and names it', () => {
  assert.deepEqual(findChrome({ WEB_CHROME: 'none' }), { note: 'rendering unavailable on this machine: turned off by WEB_CHROME=none' })
  assert.deepEqual(findChrome({ WEB_CHROME: '/nonexistent' }), { note: 'rendering unavailable on this machine: WEB_CHROME=/nonexistent does not exist' })
})

test('unset, the newest Playwright headless shell is found, then nothing when none is installed', async () => {
  const pw = await tmpCache()
  const older = join(pw, 'chromium_headless_shell-999', 'chrome-headless-shell-linux64', 'chrome-headless-shell')
  const newer = join(pw, 'chromium_headless_shell-1200', 'chrome-headless-shell-linux64', 'chrome-headless-shell')
  await fakeBinary(older)
  await fakeBinary(newer)
  const found = findChrome({ PLAYWRIGHT_BROWSERS_PATH: pw, PATH: '/nonexistent' }, 'linux')
  assert.deepEqual(found, { path: newer, headless: '--headless' })
  const empty = await tmpCache()
  assert.deepEqual(findChrome({ PLAYWRIGHT_BROWSERS_PATH: empty, PATH: '/nonexistent' }, 'linux'),
    { note: 'rendering unavailable on this machine: no Chromium found (set WEB_CHROME)' })
})

test('chromium on PATH is found after the Playwright cache, with --headless=new', async () => {
  const bin = await tmpCache()
  await fakeBinary(join(bin, 'chromium'))
  assert.deepEqual(findChrome({ PLAYWRIGHT_BROWSERS_PATH: await tmpCache(), PATH: bin }, 'linux'), { path: join(bin, 'chromium'), headless: '--headless=new' })
})

test('the egress proxy forwards to allowed hosts and refuses non-public ones, for plain requests and CONNECT', async () => {
  const proxy = await startEgressProxy(new Set([`127.0.0.1:${server.port}`]))
  try {
    const plain = (target: string) => new Promise<{ status: number; body: string }>((resolve, reject) => {
      const req = request({ host: '127.0.0.1', port: proxy.port, path: target, headers: { host: new URL(target).host } }, res => {
        let body = ''
        res.on('data', d => { body += d })
        res.on('end', () => resolve({ status: res.statusCode!, body }))
      })
      req.on('error', reject)
      req.end()
    })
    assert.deepEqual(await plain(`${server.origin}/hello`), { status: 200, body: 'hello through the proxy' })
    assert.equal((await plain(`http://127.0.0.1:${trap.port}/x`)).status, 403)
    assert.equal((await plain(`http://localhost:${trap.port}/x`)).status, 403)

    const tunnel = (target: string) => new Promise<string>((resolve, reject) => {
      const sock = connect(proxy.port, '127.0.0.1', () => sock.write(`CONNECT ${target} HTTP/1.1\r\nHost: ${target}\r\n\r\n`))
      let got = ''
      sock.on('data', d => { got += d; if (got.includes('\r\n\r\n')) { sock.destroy(); resolve(got.split('\r\n')[0]) } })
      sock.on('error', reject)
    })
    assert.match(await tunnel(`127.0.0.1:${trap.port}`), / 403 /)
    assert.match(await tunnel(`[::1]:${trap.port}`), / 403 /)
    assert.match(await tunnel(`127.0.0.1:${server.port}`), / 200 /)
    assert.equal(trap.connections, 0)
  } finally {
    await proxy.close()
  }
})

// A NetLog in Chromium's own shape: event types numbered in `constants`, each event on a source.
function netLog(events: [number, string, Record<string, unknown>?][]): string {
  const types = ['URL_REQUEST_START_JOB', 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', 'URL_REQUEST_REDIRECTED', 'SOCKET_BYTES_RECEIVED']
  return JSON.stringify({
    constants: { logEventTypes: Object.fromEntries(types.map((t, i) => [t, i + 1])) },
    events: events.map(([source, type, params]) => ({ source: { id: source, type: 1 }, type: types.indexOf(type) + 1, ...(params ? { params } : {}) })),
  })
}
const start = (url: string, request_type = 'main frame') => ({ url, method: 'GET', request_type })
const headers = (status: string) => ({ headers: [status, 'content-type: text/html'] })

test("the browser's served document is the last main-frame response, after its redirects", () => {
  assert.deepEqual(servedDocument(netLog([
    [11, 'URL_REQUEST_START_JOB', start('https://x.test/old')],
    [11, 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', headers('HTTP/1.1 301 Moved Permanently')],
    [11, 'URL_REQUEST_REDIRECTED', { location: 'https://x.test/articles/post' }],
    [11, 'URL_REQUEST_START_JOB', start('https://x.test/articles/post')],
    [11, 'URL_REQUEST_START_JOB'],
    [11, 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', headers('HTTP/1.1 200')],
    [20, 'URL_REQUEST_START_JOB', start('https://cdn.test/app.js', 'other')],
    [20, 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', headers('HTTP/1.1 404 Not Found')],
  ])), { url: 'https://x.test/articles/post', status: 200 })
  // A challenge that reloads the page: the second navigation is the document the DOM holds.
  assert.deepEqual(servedDocument(netLog([
    [11, 'URL_REQUEST_START_JOB', start('https://x.test/a')],
    [11, 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', headers('HTTP/2 403')],
    [30, 'URL_REQUEST_START_JOB', start('https://x.test/a')],
    [30, 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', headers('HTTP/2 200')],
  ])), { url: 'https://x.test/a', status: 200 })
  assert.deepEqual(servedDocument(netLog([
    [11, 'URL_REQUEST_START_JOB', start('https://x.test/a')],
    [11, 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', headers('HTTP/1.1 403')],
  ])), { url: 'https://x.test/a', status: 403 })
})

test('a NetLog that names no answered main-frame request, or does not parse, gives no document', () => {
  assert.equal(servedDocument(netLog([[11, 'URL_REQUEST_START_JOB', start('https://x.test/a')]])), undefined)
  assert.equal(servedDocument(netLog([[20, 'URL_REQUEST_START_JOB', start('https://x.test/a.js', 'other')], [20, 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', headers('HTTP/1.1 200')]])), undefined)
  assert.equal(servedDocument('{"constants": {"logEventTypes": {}}, "events": [{"type"'), undefined)
  assert.equal(servedDocument(''), undefined)
})

test('a page that needs JavaScript is rendered in headless Chromium', { skip: noChrome }, async () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }
  delete env.WEB_CHROME
  const r = await clip(`${server.origin}/shell`, { cacheDir: await tmpCache(), env }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.equal(r.rendered, true, r.notes.join('|'))
  assert.ok(r.words! > 50)
  assert.match(await readFile(r.file, 'utf8'), /written by a script after the page loaded/)
})

test('a rendered page reaches no trap through an image, a script fetch, a WebSocket or WebRTC', { skip: noChrome }, async () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }
  delete env.WEB_CHROME
  const r = await clip(`${server.origin}/egress`, { cacheDir: await tmpCache(), env }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  // The probe only means something if the page's scripts ran.
  assert.equal(r.rendered, true, r.notes.join('|'))
  assert.match(await readFile(r.file, 'utf8'), /tries every way a page can reach the network/)
  // Give a late UDP packet time to land.
  await new Promise(res => setTimeout(res, 1500))
  assert.equal(trap.connections, 0, 'TCP trap (img, fetch, WebSocket)')
  assert.equal(udp.packets, 0, 'UDP trap (RTCPeerConnection)')
})

test('a page a site refuses to a plain fetch (403) but serves a browser is rendered, with a note', { skip: noChrome }, async () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }
  delete env.WEB_CHROME
  const r = await clip(`${server.origin}/walled`, { cacheDir: await tmpCache(), env }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.equal(r.rendered, true)
  assert.equal(r.kind, 'html')
  assert.ok(r.notes.some(n => n.includes('HTTP 403')), r.notes.join('|'))
  assert.match(await readFile(r.file, 'utf8'), /served only to clients that look like a browser/)
})

test('a 403 that the browser gets too stays the failure it was', { skip: noChrome }, async () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }
  delete env.WEB_CHROME
  const r = await clip(`${server.origin}/forbidden`, { cacheDir: await tmpCache(), env })
  assert.equal(r.ok, false)
  assert.equal((r as { status?: number }).status, 403)
})

test('a long denial the browser is served with 403 too stays a failure, and is not cached', { skip: noChrome }, async () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }
  delete env.WEB_CHROME
  const cacheDir = await tmpCache()
  const r = await clip(`${server.origin}/denied`, { cacheDir, env })
  assert.equal(r.ok, false, JSON.stringify(r))
  assert.equal((r as { status?: number }).status, 403)
  const again = await clip(`${server.origin}/denied`, { cacheDir, env })
  assert.equal(again.ok, false)
  assert.equal((again as { cached?: boolean }).cached, undefined)
})

test('a walled page reached through a redirect resolves its images and links against where it was served', { skip: noChrome }, async () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }
  delete env.WEB_CHROME
  const r = await clip(`${server.origin}/old`, { cacheDir: await tmpCache(), env }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.equal(r.rendered, true)
  assert.equal(r.finalUrl, `${server.origin}/articles/post`)
  assert.equal(r.images.length, 1, JSON.stringify(r.images))
  assert.equal(r.images[0].file, 'assets/01.png')
  const page = await readFile(r.file, 'utf8')
  assert.ok(page.includes(`(${server.origin}/articles/details)`), page)
  assert.ok(page.includes(`source: "${server.origin}/articles/post"`), page)
})

test('with rendering off, a 403 is the failure it was', async () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}`, WEB_CHROME: 'none' }
  const r = await clip(`${server.origin}/walled`, { cacheDir: await tmpCache(), env })
  assert.equal(r.ok, false)
  assert.equal((r as { status?: number }).status, 403)
})
