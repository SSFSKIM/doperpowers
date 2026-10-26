import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { createServer as createTcpServer } from 'node:net'
import type { Socket } from 'node:net'
import { join } from 'node:path'
import { findImageLinks, downloadImages, IMAGE_LIMITS } from '../src/images.ts'
import { Deadline } from '../src/deadline.ts'
import { boundaryOf } from '../src/netguard.ts'
import { startServer, startTrap, send, pngBytes } from './helpers.ts'

let server: Awaited<ReturnType<typeof startServer>>
before(async () => {
  server = await startServer({
    '/img/a.png': send('image/png', pngBytes(2000, 1)),
    '/img/b.png': send('image/png', pngBytes(3000, 2)),
    '/img/c.png': send('image/png', pngBytes(4000, 3)),
  })
})
after(() => server.close())

const page = [
  'Intro `![code](/img/c.png)` and \\![escaped](/img/c.png) and !\\[also](/img/c.png) end.', // 1: none of these is an image
  '![ref one][diag]', //                                                                       2: full reference
  '![diag][]', //                                                                              3: collapsed reference
  'Shortcut ![Diag] in text.', //                                                              4: shortcut, label case-insensitive
  '![inline](/img/a.png "A title")', //                                                        5: inline
  '``![double `tick` code](/img/c.png)``', //                                                  6: a code span of two backticks
  '![nothing][undefined-label]', //                                                            7: no definition: not an image
  '```', //                                                                                    8
  '![fenced](/img/c.png)', //                                                                  9: fenced code
  '```', //                                                                                   10
  '[diag]: /img/b.png "Diagram"', //                                                          11
  '[A link to the diagram][diag], not an image.', //                                          12
].join('\n') + '\n'

test('reference-style images are found through their definitions; code, escapes and missing definitions are not images', () => {
  const links = findImageLinks(page)
  assert.deepEqual(links.map(l => [l.line, l.alt, l.target]), [
    [2, 'ref one', '/img/b.png'],
    [3, 'diag', '/img/b.png'],
    [4, 'Diag', '/img/b.png'],
    [5, 'inline', '/img/a.png'],
  ])
})

test('images are rewritten where they render, and code, escapes, definitions and links are left as written', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'clip-images-'))
  const { markdown, images } = await downloadImages(page, `${server.origin}/page`, dir, new Deadline(10_000), boundaryOf({ WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }))
  const lines = markdown.split('\n')
  assert.equal(lines[0], page.split('\n')[0])
  assert.equal(lines[1], '![ref one](assets/01.png)')
  assert.equal(lines[2], '![diag](assets/01.png)')
  assert.equal(lines[3], 'Shortcut ![Diag](assets/01.png) in text.')
  assert.equal(lines[4], '![inline](assets/02.png "A title")')
  assert.deepEqual(lines.slice(5), page.split('\n').slice(5))
  assert.deepEqual(images.map(i => i.file), ['assets/01.png', 'assets/01.png', 'assets/01.png', 'assets/02.png'])
  assert.deepEqual((await readdir(join(dir, 'assets'))).sort(), ['01.png', '02.png'])
  assert.ok(!server.hits.includes('/img/c.png'), 'an image in code or escaped was fetched')
})

test("an image host on another origin sees neither the page's query nor its fragment", async t => {
  const referers: Record<string, string | undefined> = {}
  const host = await startServer({
    '/x.png': (req, res) => { referers.cross = req.headers.referer; send('image/png', pngBytes(2000, 4))(req, res) },
  })
  t.after(() => host.close())
  const site = await startServer({
    '/own.png': (req, res) => { referers.same = req.headers.referer; send('image/png', pngBytes(2000, 5))(req, res) },
  })
  t.after(() => site.close())
  const pageUrl = `${site.origin}/signed/page?token=s3cret&sig=abc#section-2`
  const dir = await mkdtemp(join(tmpdir(), 'clip-images-'))
  const md = `![cross](${host.origin}/x.png)\n\n![same](/own.png)\n`
  const { images } = await downloadImages(md, pageUrl, dir, new Deadline(10_000), boundaryOf({ WEB_ALLOW_HOSTS: `127.0.0.1:${site.port},127.0.0.1:${host.port}` }))
  assert.deepEqual(images.map(i => i.file), ['assets/01.png', 'assets/02.png'])
  assert.equal(referers.cross, `${site.origin}/`)
  assert.equal(referers.same, `${site.origin}/signed/page?token=s3cret&sig=abc`)
})

/** A TCP port that accepts each connection and never answers it, as a dead image host does. */
async function startSilent() {
  const sockets: Socket[] = []
  const server = createTcpServer(sock => { sockets.push(sock) })
  await new Promise<void>(r => server.listen(0, '127.0.0.1', r))
  return {
    port: (server.address() as { port: number }).port,
    connections: () => sockets.length,
    close: () => { for (const s of sockets) s.destroy(); return new Promise<void>(r => server.close(() => r())) },
  }
}

/** Sets IMAGE_LIMITS fields for one test. */
function limits(t: { after: (fn: () => void) => void }, over: Partial<typeof IMAGE_LIMITS>) {
  const before = { ...IMAGE_LIMITS }
  Object.assign(IMAGE_LIMITS, over)
  t.after(() => { Object.assign(IMAGE_LIMITS, before) })
}

test('a host that did not answer one image is not asked for the page\'s others; a host that answered with an error status is', async t => {
  // One at a time, so the first failure is known before the next image is taken.
  limits(t, { concurrency: 1, timeoutMs: 400 })
  const silent = await startSilent()
  t.after(() => silent.close())
  const closed = await startTrap()
  await closed.close() // nothing listens: each connection is refused
  const errors = await startServer({ '*': send('text/plain', 'gone', 404) })
  t.after(() => errors.close())
  const dead = `127.0.0.1:${silent.port}`
  const refused = `127.0.0.1:${closed.port}`
  const md = [
    `![d1](http://${dead}/1.png)`, `![r1](http://${refused}/1.png)`, `![e1](${errors.origin}/1.png)`, '![ok](/img/a.png)',
    `![d2](http://${dead}/2.png)`, `![r2](http://${refused}/2.png)`, `![e2](${errors.origin}/2.png)`, `![d3](http://${dead}/3.png)`,
  ].join('\n\n') + '\n'
  const allow = [`127.0.0.1:${server.port}`, dead, refused, `127.0.0.1:${errors.port}`].join(',')
  const dir = await mkdtemp(join(tmpdir(), 'clip-images-'))
  const started = Date.now()
  const { images } = await downloadImages(md, `${server.origin}/page`, dir, new Deadline(10_000), boundaryOf({ WEB_ALLOW_HOSTS: allow }))
  const byAlt = Object.fromEntries(images.map(i => [i.alt, i]))
  assert.equal(byAlt.d1.error, 'timed out after 0 s')
  assert.match(byAlt.r1.error!, /^network error: /)
  assert.equal(byAlt.e1.error, 'HTTP 404')
  assert.equal(byAlt.ok.file, 'assets/01.png')
  assert.equal(byAlt.d2.error, `not downloaded: ${dead} did not answer an earlier image`)
  assert.equal(byAlt.d3.error, `not downloaded: ${dead} did not answer an earlier image`)
  assert.equal(byAlt.r2.error, `not downloaded: ${refused} did not answer an earlier image`)
  assert.equal(byAlt.e2.error, 'HTTP 404')
  assert.equal(silent.connections(), 1)
  assert.deepEqual(errors.hits, ['/1.png', '/2.png'])
  // The images not asked for keep their remote links.
  assert.equal(byAlt.d2.url, `http://${dead}/2.png`)
  assert.equal(byAlt.d2.file, undefined)
  assert.ok(Date.now() - started < 2000, `took ${Date.now() - started} ms`)
})

test('a page\'s images share IMAGE_LIMITS.totalMs from the first download, well within the fetch\'s deadline', async t => {
  limits(t, { totalMs: 1200 })
  const timers: NodeJS.Timeout[] = []
  const slow = await startServer({ '*': (req, res) => { timers.push(setTimeout(() => send('image/png', pngBytes(2000, req.url?.length ?? 0))(req, res), 500)) } })
  t.after(async () => { for (const x of timers) clearTimeout(x); await slow.close() })
  // Three rounds of six at 500 ms each: the third is still arriving when the 1.2 s are up.
  const md = Array.from({ length: 18 }, (_, i) => `![i${i}](/img/${i}.png)`).join('\n\n') + '\n'
  const dir = await mkdtemp(join(tmpdir(), 'clip-images-'))
  const started = Date.now()
  const { images } = await downloadImages(md, `${slow.origin}/page`, dir, new Deadline(60_000), boundaryOf({ WEB_ALLOW_HOSTS: `127.0.0.1:${slow.port}` }))
  const took = Date.now() - started
  assert.ok(took >= 1100 && took < 1600, `took ${took} ms`)
  assert.equal(images.filter(i => i.file).length, 12)
  assert.deepEqual(images.slice(12).map(i => i.error), Array(6).fill('not downloaded: time budget'))
  assert.equal((await readdir(join(dir, 'assets'))).length, 12)
})
