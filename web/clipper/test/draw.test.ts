import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { clip } from '../src/clip.ts'
import type { ClipOk } from '../src/clip.ts'
import { viewBoxSize } from '../src/draw.ts'
import { findChrome, renderDom } from '../src/render.ts'
import { boundaryOf } from '../src/netguard.ts'
import { startServer, send, tmpCache, noChrome, pngBytes } from './helpers.ts'

// Over 1 KiB, or the image step would take it for a tracking pixel.
const PAD = '<!-- ' + 'Padding that carries the file over one kibibyte, as a real chart is. '.repeat(20) + '-->'
const chart = (attrs: string) => `<svg xmlns="http://www.w3.org/2000/svg" ${attrs}>${PAD}<rect width="100%" height="100%" fill="#eee"/>`
  + '<text x="10" y="40" font-size="24">Bare Metal Servers 18%</text></svg>'
const PROSE = '<p>' + 'The survey asked where teams deploy their programs, and the charts below give the answers by provider. '.repeat(8) + '</p>'
const SVG = 'image/svg+xml'

// Every way an SVG can name something to load, each aimed at the test server under the name
// localhost, which the test allows: only the way the SVG is drawn can keep them from being fetched.
const TRAP_PATHS = ['import.css', 'font.woff', 'paint.svg', 'image.png', 'xlink.png', 'sprite.svg', 'feimage.png', 'foreign.png', 'script', 'script.png']
const trapSvg = (port: number) => {
  const at = (path: string) => `http://localhost:${port}/trap/${path}`
  return '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="300" height="150">'
    + `<style>@import url(${at('import.css')}); @font-face { font-family: trap; src: url(${at('font.woff')}) }`
    + ` text { font-family: trap } rect { fill: url(${at('paint.svg#p')}) }</style>`
    + `<image href="${at('image.png')}" width="10" height="10"/><image xlink:href="${at('xlink.png')}" width="10" height="10"/>`
    + `<use href="${at('sprite.svg#a')}"/><filter id="f"><feImage href="${at('feimage.png')}"/></filter>`
    + `<foreignObject width="100" height="100"><img xmlns="http://www.w3.org/1999/xhtml" src="${at('foreign.png')}"/></foreignObject>`
    + `<script>fetch('${at('script')}'); new Image().src = '${at('script.png')}'</script>`
    + `<rect width="50" height="50" filter="url(#f)"/><text x="60" y="80">Trap</text>${PAD}</svg>`
}

let server: Awaited<ReturnType<typeof startServer>>
before(async () => {
  server = await startServer({
    '/charts': send('text/html', '<html><head><title>Survey charts</title></head><body><article><h1>Survey charts</h1>' + PROSE
      + '<p><img src="chart.svg" alt="Cloud platforms"></p><p><img src="wide.svg" alt="Wide"></p>'
      + '<p><img src="viewbox.svg" alt="Viewbox only"></p><p><img src="broken.svg" alt="Broken"></p>'
      + '<p><img src="photo.png" alt="A photo"></p></article></body></html>'),
    '/chart.svg': send(SVG, chart('width="400" height="200"')),
    '/wide.svg': send(SVG, chart('width="3000" height="1000"')),
    '/viewbox.svg': send(SVG, chart('viewBox="0 0 800 200"')),
    '/broken.svg': send(SVG, '<svg xmlns="http://www.w3.org/2000/svg"><rect ' + PAD),
    '/photo.png': send('image/png', pngBytes(3000, 9)),
    '/trap-page': (req, res) => send('text/html', '<html><head><title>A trap</title></head><body><article><h1>A trap</h1>' + PROSE
      + `<p><img src="http://localhost:${server.port}/trap.svg" alt="Trap"></p></article></body></html>`)(req, res),
    '/trap.svg': (req, res) => send(SVG, trapSvg(server.port))(req, res),
  })
})
after(() => server.close())

const env = (chrome = true): NodeJS.ProcessEnv => {
  const e: NodeJS.ProcessEnv = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port},localhost:${server.port}` }
  if (chrome) delete e.WEB_CHROME
  else e.WEB_CHROME = 'none'
  return e
}
const pngSize = (b: Buffer) => [b.readUInt32BE(16), b.readUInt32BE(20)]

test('an SVG with no width of its own is drawn at its viewBox size; one with a width, at its natural size', () => {
  assert.deepEqual(viewBoxSize('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 200">'), [800, 200])
  assert.deepEqual(viewBoxSize("<svg width='100%' viewBox='0,0,640.5,480'>"), [640.5, 480])
  assert.equal(viewBoxSize('<svg width="400" viewBox="0 0 800 200">'), undefined)
  assert.equal(viewBoxSize('<svg>'), undefined)
  assert.equal(viewBoxSize('<svg viewBox="0 0 0 10">'), undefined)
  assert.equal(viewBoxSize('<html><body></body></html>'), undefined)
})

test("a page's SVGs are drawn as PNGs beside them at twice their size, the long edge at most 2000 px, and its links name the PNGs", { skip: noChrome }, async () => {
  const r = await clip(`${server.origin}/charts`, { cacheDir: await tmpCache(), env: env() }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.deepEqual(r.images.map(i => [i.file, i.svg, i.notDrawn]), [
    ['assets/01.png', 'assets/01.svg', undefined],
    ['assets/02.png', 'assets/02.svg', undefined],
    ['assets/03.png', 'assets/03.svg', undefined],
    ['assets/04.svg', undefined, 'the SVG could not be decoded'],
    ['assets/05.png', undefined, undefined],
  ])
  const sizes = await Promise.all(['01', '02', '03'].map(async n => pngSize(await readFile(join(r.dir, `assets/${n}.png`)))))
  assert.deepEqual(sizes, [[800, 400], [2000, 667], [1600, 400]])
  // Each original stays beside its drawing, and the drawing's bytes are what the entry says.
  assert.match(await readFile(join(r.dir, 'assets/01.svg'), 'utf8'), /Bare Metal Servers 18%/)
  assert.equal(r.images[0].bytes, (await readFile(join(r.dir, 'assets/01.png'))).length)
  const page = await readFile(r.file, 'utf8')
  for (const link of ['(assets/01.png)', '(assets/02.png)', '(assets/03.png)', '(assets/04.svg)', '(assets/05.png)']) assert.ok(page.includes(link), link)
  assert.ok(!page.includes('(assets/01.svg)'))
  // A picture that is not an SVG is saved as before, with nothing added.
  assert.deepEqual(Object.keys(r.images[4]).sort(), ['alt', 'bytes', 'file', 'line', 'url'])
})

test('an SVG drawn as an image loads nothing it names: the same SVG opened as a document does reach the server', { skip: noChrome }, async () => {
  const hits = server.hits.length
  const r = await clip(`${server.origin}/trap-page`, { cacheDir: await tmpCache(), env: env() }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  // The clipper fetched the SVG from the allowed name, and Chromium drew it.
  assert.ok(server.hits.slice(hits).includes('/trap.svg'))
  assert.deepEqual(r.images.map(i => [i.file, i.svg]), [['assets/01.png', 'assets/01.svg']])
  await new Promise(resolve => setTimeout(resolve, 500))
  assert.deepEqual(server.hits.slice(hits).filter(h => h.startsWith('/trap/')), [])

  // The control: the same browser, proxy and boundary, the SVG as a document. Its requests get through.
  const chrome = findChrome(env())
  assert.ok(!('note' in chrome))
  const before = server.hits.length
  await renderDom(`http://localhost:${server.port}/trap.svg`, chrome, 20_000, boundaryOf(env()))
  // Every channel the SVG names is live: each one the drawing did not use, it could have.
  const reached = new Set(server.hits.slice(before).filter(h => h.startsWith('/trap/')))
  assert.deepEqual([...reached].sort(), TRAP_PATHS.map(p => `/trap/${p}`).sort())
})

test('an SVG fetched by its own URL is drawn as image.png beside image.svg', { skip: noChrome }, async () => {
  const r = await clip(`${server.origin}/chart.svg`, { cacheDir: await tmpCache(), env: env() }) as ClipOk
  assert.equal(r.kind, 'image')
  assert.equal(r.file, join(r.dir, 'image.svg'))
  assert.equal(r.png, join(r.dir, 'image.png'))
  assert.deepEqual(pngSize(await readFile(r.png!)), [800, 400])
})

test('without Chromium an SVG stays the file its link names, with why it was not drawn', async () => {
  const r = await clip(`${server.origin}/charts`, { cacheDir: await tmpCache(), env: env(false) }) as ClipOk
  assert.equal(r.ok, true, JSON.stringify(r))
  assert.deepEqual(r.images.map(i => [i.file, i.svg, i.notDrawn]), [
    ['assets/01.svg', undefined, 'turned off by WEB_CHROME=none'],
    ['assets/02.svg', undefined, 'turned off by WEB_CHROME=none'],
    ['assets/03.svg', undefined, 'turned off by WEB_CHROME=none'],
    ['assets/04.svg', undefined, 'turned off by WEB_CHROME=none'],
    ['assets/05.png', undefined, undefined],
  ])
  assert.ok((await readFile(r.file, 'utf8')).includes('(assets/01.svg)'))
  const direct = await clip(`${server.origin}/chart.svg`, { cacheDir: await tmpCache(), env: env(false) }) as ClipOk
  assert.equal(direct.png, undefined)
  assert.equal(direct.notDrawn, 'turned off by WEB_CHROME=none')
})
