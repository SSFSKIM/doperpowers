import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdir, writeFile, chmod, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { request } from 'node:http'
import { connect } from 'node:net'
import { clip } from '../src/clip.ts'
import type { ClipOk } from '../src/clip.ts'
import { findChrome, renderDom, servedDocument } from '../src/render.ts'
import { startEgressProxy } from '../src/proxy.ts'
import { boundaryOf } from '../src/netguard.ts'
import { startServer, startTrap, startUdpTrap, tmpCache, send, fixture, noChrome, pngBytes, FIXTURES } from './helpers.ts'

const WALLED_ARTICLE = '<html><head><title>Behind the wall</title></head><body><article><h1>Behind the wall</h1><p>'
  + 'This article is served only to clients that look like a browser, as a bot wall would serve it. '.repeat(8) + '</p></article></body></html>'

// A denial long enough to pass for a page, served with 403 to every client, browser or not.
const LONG_DENIAL = '<html><head><title>Access denied</title></head><body><main><h1>Access denied</h1><p>'
  + 'Your request was blocked by the security policy of this site, and the reference below identifies it to support. '.repeat(10) + '</p></main></body></html>'

// A walled article reached through a redirect, with a relative image and a relative link.
const MOVED_ARTICLE = '<html><head><title>Moved behind the wall</title></head><body><article><h1>Moved behind the wall</h1><p>'
  + 'This article moved, and is served only to clients that look like a browser. '.repeat(8)
  + '</p><p><img src="chart.png" alt="the chart"></p><p>Read the <a href="details">details</a>.</p></article></body></html>'

// A short shell (too few words) whose script moves the browser on to the article.
const MOVING_SHELL = '<html><head><title>Moving</title></head><body><p>Loading…</p><script>location.href = "/nested/article"</script></body></html>'
const NESTED_ARTICLE = MOVED_ARTICLE.replaceAll('Moved behind the wall', 'The nested article').replace('This article moved, and is served only to clients that look like a browser. ', 'This article sits one folder down, where the shell sent the browser. ')
// A short 200 shell to a plain client; a long page with a failure status to a browser.
const SHORT_SHELL = '<html><head><title>Shell</title></head><body><div id="app"></div></body></html>'
// A shell whose script writes the article and opens an event stream the server never ends:
// the open request stops the page's virtual time for good.
const HELD_OPEN = '<html><head><title>Live</title></head><body><div id="app"></div><script>'
  + 'const words = "This article was written by a script while the page kept an event stream open, as a live dashboard does. A browser that waits for every request to finish before reading the page waits forever. ";'
  + 'document.getElementById("app").innerHTML = "<article><h1>Live</h1><p>" + words.repeat(3) + "</p></article>";'
  + 'new EventSource("/events");</script></body></html>'
// A shell whose words come from a worker's request and are written by a timer once they arrive:
// virtual time waits for neither, so the budget is spent before they are on the page.
const WORKER_WORDS = 'These words reached the page from a worker, which fetched them after the page loaded, and a timer wrote them in. '.repeat(4)
const WORKER_PAGE = '<html><head><title>From a worker</title></head><body><div id="app">Loading</div><script>'
  + 'new Worker("/worker.js").onmessage = e => setTimeout(() => { document.getElementById("app").innerHTML = "<article><h1>From a worker</h1><p>" + e.data + "</p></article>" }, 50)'
  + '</script></body></html>'
const browserOnly = (status: number, body: string) => (req: import('node:http').IncomingMessage, res: import('node:http').ServerResponse) =>
  req.headers['sec-fetch-mode'] ? send('text/html', body, status)(req, res) : send('text/html', SHORT_SHELL)(req, res)

let server: Awaited<ReturnType<typeof startServer>>
let trap: Awaited<ReturnType<typeof startTrap>>
let udp: Awaited<ReturnType<typeof startUdpTrap>>

before(async () => {
  trap = await startTrap()
  udp = await startUdpTrap()
  const egress = (await fixture('egress.html')).replaceAll('{{TRAP}}', String(trap.port)).replaceAll('{{UDP}}', String(udp.port))
  server = await startServer({
    '/shell': send('text/html', await fixture('js-shell.html')),
    // The same shell with no Content-Type at all, as package.elm-lang.org serves its pages.
    '/untyped-shell': async (_req, res) => { res.writeHead(200); res.end(await fixture('js-shell.html')) },
    // The shell again, with a markdown stub for a client that asks for markdown, as bundlephobia serves its package pages.
    '/stub-shell': async (req, res) => (req.headers.accept ?? '').startsWith('text/markdown')
      ? send('text/markdown; charset=utf-8', '# Rendered Notes\n\nA notebook application.\n')(req, res)
      : send('text/html', await fixture('js-shell.html'))(req, res),
    '/egress': send('text/html', egress),
    '/hello': send('text/plain', 'hello through the proxy'),
    '/held-open': send('text/html', HELD_OPEN),
    '/worker-page': send('text/html', WORKER_PAGE),
    '/worker.js': send('text/javascript', 'fetch("/worker-data").then(r => r.text()).then(t => postMessage(t))'),
    '/worker-data': (req, res) => { setTimeout(() => send('text/plain', WORKER_WORDS)(req, res), 100) },
    '/thin-shell': send('text/html', '<html><head><title>Thin</title></head><body><div id="app"></div><script>document.getElementById("app").textContent = "Only a handful of words appear here, even in a browser."</script></body></html>'),
    // The shell, reaching for the same server under a name the test puts on the deny list.
    '/deny-probe': async (req, res) => send('text/html', (await fixture('js-shell.html')).replace('</body>',
      `<img src="http://localhost:${server.port}/denied.png"><script>fetch("http://localhost:${server.port}/denied-fetch").catch(() => {})</script></body>`))(req, res),
    '/events': (_req, res) => { res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' }); res.write('data: open\n\n') },
    '/slow': (_req, res) => { setTimeout(() => send('text/plain', 'ok')(_req, res), 2000) },
    // A bot wall: 403 to a client that is not a browser (Node sends no Sec-Fetch-* headers), the article to one that is.
    '/walled': (req, res) => req.headers['sec-fetch-mode']
      ? send('text/html', WALLED_ARTICLE)(req, res)
      : send('text/html', '<html><body><h1>Access denied</h1></body></html>', 403)(req, res),
    '/denied': send('text/html', LONG_DENIAL, 403),
    // The denial navigates on to a 204, which leaves the denial on screen: Chromium keeps the document.
    '/denied-then-empty': send('text/html', LONG_DENIAL.replace('</body>', '<script>setTimeout(() => { location.href = "/empty" }, 50)</script></body>'), 403),
    '/empty': send('text/html', '', 204),
    '/old': send('text/html', '', 301, { location: '/articles/post' }),
    '/articles/post': (req, res) => req.headers['sec-fetch-mode']
      ? send('text/html', MOVED_ARTICLE)(req, res)
      : send('text/html', '<html><body><h1>Access denied</h1></body></html>', 403)(req, res),
    '/articles/chart.png': send('image/png', pngBytes(2048, 7)),
    '/forbidden': send('text/html', '<html><body><h1>Forbidden</h1><p>No.</p></body></html>', 403),
    '/move': send('text/html', MOVING_SHELL),
    '/nested/article': send('text/html', NESTED_ARTICLE),
    '/nested/chart.png': send('image/png', pngBytes(2048, 8)),
    '/browser-403': browserOnly(403, LONG_DENIAL),
    '/browser-404': browserOnly(404, LONG_DENIAL.replaceAll('Access denied', 'Not found')),
    '/browser-503': browserOnly(503, LONG_DENIAL.replaceAll('Access denied', 'Service unavailable')),
    // The shell sends the browser to an address the boundary refuses: the navigation fails.
    '/nav-refused': (req, res) => send('text/html', `<html><body><p>Loading…</p><script>location.href = "http://127.0.0.1:${trap.port}/elsewhere"</script></body></html>`)(req, res),
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
  const proxy = await startEgressProxy(boundaryOf({ WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }))
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

test('a last main-frame response that cannot replace the document gives no document: 204, 205, an attachment, not HTML', () => {
  const denialThen = (status: string, ...more: string[]) => servedDocument(netLog([
    [11, 'URL_REQUEST_START_JOB', start('https://x.test/a')],
    [11, 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', headers('HTTP/1.1 403')],
    [20, 'URL_REQUEST_START_JOB', start('https://x.test/next')],
    [20, 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', { headers: [status, ...more] }],
  ]))
  assert.equal(denialThen('HTTP/1.1 204 No Content'), undefined)
  assert.equal(denialThen('HTTP/1.1 205 Reset Content'), undefined)
  assert.equal(denialThen('HTTP/1.1 200 OK', 'content-type: text/html', 'Content-Disposition: attachment; filename="a.html"'), undefined)
  assert.equal(denialThen('HTTP/1.1 200 OK', 'content-type: application/pdf'), undefined)
  assert.equal(denialThen('HTTP/1.1 200 OK', 'Content-Type: text/plain'), undefined)
  // No Content-Type at all: Chromium sniffs the body and renders it, so it becomes the document
  // (package.elm-lang.org serves its pages this way).
  assert.deepEqual(denialThen('HTTP/1.1 200 OK', 'Server: nginx', 'Transfer-Encoding: chunked'), { url: 'https://x.test/next', status: 200 })
  assert.deepEqual(denialThen('HTTP/1.1 200 OK', 'Content-Type: application/xhtml+xml; charset=utf-8'), { url: 'https://x.test/next', status: 200 })
  // A redirect the log never saw answered leaves nothing committed after it.
  assert.equal(servedDocument(netLog([
    [11, 'URL_REQUEST_START_JOB', start('https://x.test/a')],
    [11, 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', headers('HTTP/1.1 302 Found')],
  ])), undefined)
})

test('a NetLog that names no answered main-frame request, or does not parse, gives no document', () => {
  assert.equal(servedDocument(netLog([[11, 'URL_REQUEST_START_JOB', start('https://x.test/a')]])), undefined)
  assert.equal(servedDocument(netLog([[20, 'URL_REQUEST_START_JOB', start('https://x.test/a.js', 'other')], [20, 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS', headers('HTTP/1.1 200')]])), undefined)
  assert.equal(servedDocument('{"constants": {"logEventTypes": {}}, "events": [{"type"'), undefined)
  assert.equal(servedDocument(''), undefined)
})

test('a page served with no Content-Type, which Chromium sniffs as HTML, is rendered', { skip: noChrome }, async () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }
  delete env.WEB_CHROME
  const r = await clip(`${server.origin}/untyped-shell`, { cacheDir: await tmpCache(), env }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.equal(r.rendered, true, r.notes.join('|'))
  assert.ok(r.words! > 50)
  assert.match(await readFile(r.file, 'utf8'), /written by a script after the page loaded/)
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

test('a markdown stub of a page a script draws gives way to the page, rendered', { skip: noChrome }, async () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }
  delete env.WEB_CHROME
  const r = await clip(`${server.origin}/stub-shell`, { cacheDir: await tmpCache(), env }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.equal(r.kind, 'html')
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

test('a denial whose script navigates on to a 204 stays the 403 failure: the 204 replaced nothing', { skip: noChrome }, async () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }
  delete env.WEB_CHROME
  const r = await clip(`${server.origin}/denied-then-empty`, { cacheDir: await tmpCache(), env })
  assert.equal(r.ok, false, JSON.stringify(r))
  assert.equal((r as { status?: number }).status, 403)
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

const renderEnv = () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }
  delete env.WEB_CHROME
  return env
}

test('a shell the browser leaves for another page is extracted, and its images and links resolved, where the browser ended up', { skip: noChrome }, async () => {
  const r = await clip(`${server.origin}/move`, { cacheDir: await tmpCache(), env: renderEnv() }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.equal(r.rendered, true, r.notes.join('|'))
  assert.equal(r.finalUrl, `${server.origin}/nested/article`)
  assert.equal(r.images.length, 1, JSON.stringify(r.images))
  assert.equal(r.images[0].url, `${server.origin}/nested/chart.png`)
  assert.equal(r.images[0].file, 'assets/01.png')
  const page = await readFile(r.file, 'utf8')
  assert.ok(page.includes(`(${server.origin}/nested/details)`), page)
  assert.ok(page.includes(`source: "${server.origin}/nested/article"`), page)
})

for (const status of [403, 404, 503]) {
  test(`a long page the browser was served with ${status} does not replace a short 200 page`, { skip: noChrome }, async () => {
    const cacheDir = await tmpCache()
    const r = await clip(`${server.origin}/browser-${status}`, { cacheDir, env: renderEnv() }) as ClipOk
    assert.equal(r.ok, true, JSON.stringify(r))
    assert.equal(r.status, 200)
    assert.equal(r.rendered, false)
    assert.equal(r.finalUrl, `${server.origin}/browser-${status}`)
    assert.ok(r.notes.some(n => n.includes(`HTTP ${status}`) && n.includes('plain fetch is kept')), r.notes.join('|'))
    assert.doesNotMatch(await readFile(r.file, 'utf8'), /security policy of this site/)
  })
}

test('a render whose navigation fails is not taken for the page', { skip: noChrome }, async () => {
  const r = await clip(`${server.origin}/nav-refused`, { cacheDir: await tmpCache(), env: renderEnv() }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.equal(r.rendered, false)
  assert.equal(r.finalUrl, `${server.origin}/nav-refused`)
  assert.ok(r.notes.some(n => n.includes('plain fetch is kept')), r.notes.join('|'))
  assert.equal(trap.connections, 0)
})

test('a page that keeps a request open for good is taken as it stands at the cap, with a note saying so', { skip: noChrome }, async () => {
  const r = await clip(`${server.origin}/held-open`, { cacheDir: await tmpCache(), env: renderEnv(), deadlineMs: 12_000 }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.equal(r.rendered, true, r.notes.join('|'))
  assert.ok(r.notes.some(n => /^the page was still loading after \d+ s; this is how headless Chromium had rendered it by then$/.test(n)), r.notes.join('|'))
  assert.match(await readFile(r.file, 'utf8'), /kept an event stream open/)
})

test('content a worker fetches and a timer writes after the budget is spent is waited for', { skip: noChrome }, async () => {
  const r = await clip(`${server.origin}/worker-page`, { cacheDir: await tmpCache(), env: renderEnv() }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.equal(r.rendered, true, r.notes.join('|'))
  assert.match(await readFile(r.file, 'utf8'), /reached the page from a worker/)
  assert.deepEqual(r.notes, [])
})

test('a rendered page reaches no host on WEB_DENY_HOSTS, even one WEB_ALLOW_HOSTS exempts', { skip: noChrome }, async () => {
  const env = { ...renderEnv(), WEB_ALLOW_HOSTS: `127.0.0.1:${server.port},localhost:${server.port}`, WEB_DENY_HOSTS: 'localhost' }
  const hits = server.hits.length
  const r = await clip(`${server.origin}/deny-probe`, { cacheDir: await tmpCache(), env }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  // The probe only means something if the page's scripts ran.
  assert.equal(r.rendered, true, r.notes.join('|'))
  const seen = server.hits.slice(hits)
  assert.ok(!seen.includes('/denied.png') && !seen.includes('/denied-fetch'), seen.join(' '))
})

test('a page still thin once rendered says so', { skip: noChrome }, async () => {
  const r = await clip(`${server.origin}/thin-shell`, { cacheDir: await tmpCache(), env: renderEnv() }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.equal(r.rendered, true, r.notes.join('|'))
  assert.deepEqual(r.notes, [`even rendered, the page holds only ${r.words} words; its content may load later than the render waits, or come from an API the page calls`])
})

// The driver against a stand-in browser (test/fixtures/fake-chrome.mjs), so it runs where Chromium does not.
const fakeChrome = { path: join(FIXTURES, 'fake-chrome.mjs'), headless: '--headless' }

test('the driver takes the DOM once the page spent its budget, though each event arrives in one read with the reply before it', async () => {
  const started = Date.now()
  const out = await renderDom('http://fake.test/settles', fakeChrome, 20_000, boundaryOf({}))
  assert.deepEqual(out, { html: '<html><body><p>settles page</p></body></html>' })
  // A missed event would leave the driver waiting for the cap, 17 s away.
  assert.ok(Date.now() - started < 5000, `took ${Date.now() - started} ms`)
})

test('the driver takes the DOM of a page that never spends its budget at the cap, a few seconds inside the limit', async () => {
  const started = Date.now()
  const out = await renderDom('http://fake.test/stalls', fakeChrome, 4000, boundaryOf({}))
  assert.deepEqual(out, { html: '<html><body><p>stalls page</p></body></html>', unsettled: 'the page was still loading after 3 s; this is how headless Chromium had rendered it by then' })
  assert.ok(Date.now() - started < 4000, `took ${Date.now() - started} ms`)
})

test('a NetLog the browser is slow to close is waited for, not taken half-written', async () => {
  const out = await renderDom('http://fake.test/slowlog', fakeChrome, 20_000, boundaryOf({}))
  assert.deepEqual(out, { html: '<html><body><p>slowlog page</p></body></html>', document: { url: 'http://fake.test/slowlog', status: 200 } })
})

test('a navigation the browser could not make is a failed render', async () => {
  assert.deepEqual(await renderDom('http://fake.test/fails', fakeChrome, 10_000, boundaryOf({})),
    { note: 'rendering failed: the browser could not load the page (net::ERR_TUNNEL_CONNECTION_FAILED); the plain fetch is kept' })
})

test('a browser that cannot start is a failed render', async () => {
  const out = await renderDom('http://fake.test/settles', { path: join(FIXTURES, 'no-such-chrome'), headless: '--headless' }, 10_000, boundaryOf({}))
  assert.ok('note' in out && /^rendering failed: spawn .*no-such-chrome ENOENT; the plain fetch is kept$/.test(out.note), JSON.stringify(out))
})

test('a CONNECT tunnel falls back from an unreachable first address to the next checked one', async () => {
  // Only 127.0.0.1 listens: the first address, ::1 on this port, refuses the connection.
  const resolve = async () => [{ address: '::1', family: 6 }, { address: '127.0.0.1', family: 4 }]
  const proxy = await startEgressProxy(boundaryOf({ WEB_ALLOW_HOSTS: `fallback.test:${server.port}` }), { resolve })
  try {
    const reply = await new Promise<string>((done, fail) => {
      const sock = connect(proxy.port, '127.0.0.1', () => sock.write(`CONNECT fallback.test:${server.port} HTTP/1.1\r\nHost: fallback.test\r\n\r\n`))
      let got = ''
      let sent = false
      sock.on('data', d => {
        got += d
        if (!sent && got.includes('\r\n\r\n')) {
          sent = true
          if (!/ 200 /.test(got.split('\r\n')[0])) { sock.destroy(); done(got.split('\r\n')[0]); return }
          got = ''
          sock.write('GET /hello HTTP/1.1\r\nHost: fallback.test\r\nConnection: close\r\n\r\n')
        }
      })
      sock.on('end', () => done(got))
      sock.on('error', fail)
    })
    assert.match(reply, /hello through the proxy/)
  } finally {
    await proxy.close()
  }
})

test('a CONNECT tunnel connects to no address the guard did not check', async () => {
  const resolve = async () => [{ address: '::1', family: 6 }, { address: '127.0.0.1', family: 4 }]
  // Not allowed, so the check refuses both loopback addresses: nothing is connected to.
  const proxy = await startEgressProxy(boundaryOf({}), { resolve })
  try {
    const line = await new Promise<string>((done, fail) => {
      const sock = connect(proxy.port, '127.0.0.1', () => sock.write(`CONNECT fallback.test:${trap.port} HTTP/1.1\r\n\r\n`))
      let got = ''
      sock.on('data', d => { got += d; if (got.includes('\r\n\r\n')) { sock.destroy(); done(got.split('\r\n')[0]) } })
      sock.on('error', fail)
    })
    assert.match(line, / 403 /)
    assert.equal(trap.connections, 0)
  } finally {
    await proxy.close()
  }
})

test('with rendering off, a 403 is the failure it was', async () => {
  const env: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}`, WEB_CHROME: 'none' }
  const r = await clip(`${server.origin}/walled`, { cacheDir: await tmpCache(), env })
  assert.equal(r.ok, false)
  assert.equal((r as { status?: number }).status, 403)
})
