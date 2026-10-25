import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdir, writeFile, chmod, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { request } from 'node:http'
import { connect } from 'node:net'
import { clip } from '../src/clip.ts'
import type { ClipOk } from '../src/clip.ts'
import { findChrome } from '../src/render.ts'
import { startEgressProxy } from '../src/proxy.ts'
import { startServer, startTrap, startUdpTrap, tmpCache, send, fixture, noChrome } from './helpers.ts'

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
