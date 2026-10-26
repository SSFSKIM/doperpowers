import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { createServer as createTcpServer } from 'node:net'
import type { Socket } from 'node:net'
import { join } from 'node:path'
import { absoluteImageLinks, findImageLinks, downloadImages, IMAGE_LIMITS } from '../src/images.ts'
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
  assert.equal(byAlt.d2.error, `not downloaded: http://${dead} did not answer an earlier image`)
  assert.equal(byAlt.d3.error, `not downloaded: http://${dead} did not answer an earlier image`)
  assert.equal(byAlt.r2.error, `not downloaded: http://${refused} did not answer an earlier image`)
  assert.equal(byAlt.e2.error, 'HTTP 404')
  assert.equal(silent.connections(), 1)
  assert.deepEqual(errors.hits, ['/1.png', '/2.png'])
  // The images not asked for keep their remote links.
  assert.equal(byAlt.d2.url, `http://${dead}/2.png`)
  assert.equal(byAlt.d2.file, undefined)
  assert.ok(Date.now() - started < 2000, `took ${Date.now() - started} ms`)
})

test('a host that redirected an image to one that did not answer answered: only the redirect\'s target is not asked again', async t => {
  limits(t, { concurrency: 1, timeoutMs: 400 })
  const silent = await startSilent()
  t.after(() => silent.close())
  const dead = `http://127.0.0.1:${silent.port}`
  const site = await startServer({
    '/hop.png': (_req, res) => { res.writeHead(302, { location: `${dead}/moved.png` }); res.end() },
    '/ok.png': send('image/png', pngBytes(2000, 7)),
  })
  t.after(() => site.close())
  const md = `![hop](/hop.png)\n\n![ok](/ok.png)\n\n![direct](${dead}/direct.png)\n`
  const dir = await mkdtemp(join(tmpdir(), 'clip-images-'))
  const { images } = await downloadImages(md, `${site.origin}/page`, dir, new Deadline(10_000), boundaryOf({ WEB_ALLOW_HOSTS: `127.0.0.1:${site.port},127.0.0.1:${silent.port}` }))
  const byAlt = Object.fromEntries(images.map(i => [i.alt, i]))
  assert.equal(byAlt.hop.error, 'timed out after 0 s')
  assert.equal(byAlt.ok.file, 'assets/01.png', JSON.stringify(byAlt.ok))
  assert.equal(byAlt.direct.error, `not downloaded: ${dead} did not answer an earlier image`)
  assert.equal(silent.connections(), 1)
})

test('a host is its origin: an http image that did not answer leaves the same host\'s https images asked', async t => {
  // .invalid never resolves: each request fails before any response, unanswered.
  limits(t, { concurrency: 1, timeoutMs: 3000 })
  const md = '![a](http://cdn.invalid/1.png)\n\n![b](https://cdn.invalid/2.png)\n\n![c](http://cdn.invalid:80/3.png)\n'
  const dir = await mkdtemp(join(tmpdir(), 'clip-images-'))
  const { images } = await downloadImages(md, 'https://site.invalid/page', dir, new Deadline(10_000), boundaryOf({}))
  const [a, b, c] = images
  assert.match(a.error!, /^network error: /)
  assert.match(b.error!, /^network error: /)
  // The default port is the origin's own: http://cdn.invalid:80 is http://cdn.invalid.
  assert.equal(c.error, 'not downloaded: http://cdn.invalid did not answer an earlier image')
})

test('an image destination is read as markdown writes it: escapes undone before it is resolved, and written back valid', async t => {
  const site = await startServer({
    '/img/chart_(1).png': send('image/png', pngBytes(2000, 8)),
    '/img/a&b.png': send('image/png', pngBytes(2000, 9)),
  })
  t.after(() => site.close())
  // As Defuddle writes them: parentheses escaped with a backslash, and an entity-like & as &amp;.
  const md = '![chart](/img/chart_\\(1\\).png)\n\n![amp](/img/a&amp;b.png)\n\n![gone](/img/gone_\\(2\\).png "A title")\n\n![spaced](</img/my chart.png>)\n\n![odd](/img/odd\\(3.png)\n'
  assert.deepEqual(findImageLinks(md).map(l => l.target), ['/img/chart_(1).png', '/img/a&b.png', '/img/gone_(2).png', '/img/my chart.png', '/img/odd(3.png'])
  const dir = await mkdtemp(join(tmpdir(), 'clip-images-'))
  const { markdown, images } = await downloadImages(md, `${site.origin}/page`, dir, new Deadline(10_000), boundaryOf({ WEB_ALLOW_HOSTS: `127.0.0.1:${site.port}` }))
  assert.deepEqual(images.map(i => i.file ?? i.error), ['assets/01.png', 'assets/02.png', 'HTTP 404', 'HTTP 404', 'HTTP 404'])
  assert.equal(images[2].url, `${site.origin}/img/gone_(2).png`)
  // A remote link kept is a valid destination, which reads back as the same URL.
  const lines = markdown.split('\n')
  assert.equal(lines[0], '![chart](assets/01.png)')
  assert.equal(lines[4], `![gone](<${site.origin}/img/gone_(2).png> "A title")`)
  assert.equal(lines[6], `![spaced](${site.origin}/img/my%20chart.png)`)
  assert.equal(lines[8], `![odd](<${site.origin}/img/odd(3.png>)`)
  assert.deepEqual(findImageLinks(markdown).slice(2).map(l => l.target), [`${site.origin}/img/gone_(2).png`, `${site.origin}/img/my%20chart.png`, `${site.origin}/img/odd(3.png`])

  // The whole page's links, never downloaded, are made absolute the same way.
  const whole = absoluteImageLinks(md, 'https://img.example/page')
  assert.equal(whole.markdown.split('\n')[0], '![chart](<https://img.example/img/chart_(1).png>)')
  assert.deepEqual(whole.urls, ['https://img.example/img/chart_(1).png', 'https://img.example/img/a&b.png', 'https://img.example/img/gone_(2).png', 'https://img.example/img/my%20chart.png', 'https://img.example/img/odd(3.png'])
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
