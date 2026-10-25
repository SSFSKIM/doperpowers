import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { findImageLinks, downloadImages } from '../src/images.ts'
import { Deadline } from '../src/deadline.ts'
import { boundaryOf } from '../src/netguard.ts'
import { startServer, send, pngBytes } from './helpers.ts'

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
