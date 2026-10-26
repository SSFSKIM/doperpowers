import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, readdir, stat, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { clip, fetchHttpsFirst, FETCH_LIMITS, FULL_LIMITS, httpsFirst } from '../src/clip.ts'
import type { ClipResult, ClipOk, ClipError } from '../src/clip.ts'
import { FAILURE_MEMORY_MS } from '../src/cache.ts'
import { HttpError } from '../src/http.ts'
import type { HttpResponse } from '../src/http.ts'
import { estimateTokens } from '../src/estimate.ts'
import { entryDir } from '../src/key.ts'
import { RefusedError } from '../src/netguard.ts'
import { startServer, startTrap, tmpCache, send, fixture, pngBytes, pdfBytes, PIXEL_GIF, noPdftotext, entryContents } from './helpers.ts'

let server: Awaited<ReturnType<typeof startServer>>
let trap: Awaited<ReturnType<typeof startTrap>>
let env: NodeJS.ProcessEnv
const stall: { res: import('node:http').ServerResponse }[] = []
let stallingHtml = ''

before(async () => {
  trap = await startTrap()
  const article = await fixture('article.html')
  const many = ['<!doctype html><html><head><title>Many Headings</title></head><body><article><h1>Many Headings</h1>']
  for (let i = 0; i < 12; i++) {
    many.push(`<h2>Part ${i}</h2><p>Part ${i} has a few words of its own so the section is not empty and the extractor keeps it in the article body.</p>`)
    for (let j = 0; j < 8; j++) many.push(`<h3>Detail ${i}.${j}</h3><p>Detail ${i}.${j} explains one small point about part ${i} in a sentence or two.</p>`)
  }
  many.push('</article></body></html>')
  const stalling = ['<!doctype html><html><head><title>Stalling Images</title></head><body><article><h1>Stalling Images</h1>',
    '<p>' + 'This page has forty images, and every one of them stalls forever on the server, so only the time budget can end the downloads. '.repeat(3) + '</p>']
  for (let i = 0; i < 40; i++) stalling.push(`<p><img src="/stall/${i}.png" alt="stalled ${i}"></p>`)
  stalling.push('</article></body></html>')
  stallingHtml = stalling.join('')

  server = await startServer({
    '/article': send('text/html; charset=utf-8', article),
    '/crates/tinycrate': send('text/html; charset=utf-8', await fixture('sidebar.html')),
    // The article, with one chart beside it and nothing more.
    '/gallery': send('text/html; charset=utf-8', article.replace('</main>', '</main><aside><img src="/charts/beside.png" alt="Beside the article"></aside>')),
    '/img/diagram.png': send('image/png', pngBytes(2048, 1)),
    '/img/lazy.png': send('image/png', pngBytes(3000, 2)),
    '/img/small.png': send('image/png', pngBytes(1500, 3)),
    '/img/large.png': send('image/png', pngBytes(5000, 4)),
    '/img/pixel.gif': send('image/gif', PIXEL_GIF),
    '/img/photo': send('image/webp', pngBytes(4000, 5)),
    '/notes.md': send('text/markdown; charset=utf-8', '# Field Notes\n\nSome notes in markdown.\n\n![chart](/img/diagram.png)\n\n## Later\n\nMore.\n'),
    '/pixel.md': send('text/markdown', '# Pixel\n\n![tracker](/img/pixel.gif)\n'),
    '/data.json': send('application/json', '{"a":1,"b":[1,2]}'),
    '/readme.txt': send('text/plain; charset=utf-8', 'Plain text.\n# not a heading\n'),
    '/paper.pdf': send('application/pdf', pdfBytes(['First page words', 'Second page words', 'Third page words'])),
    '/r1': (_q, res) => { res.writeHead(301, { location: '/r2' }); res.end() },
    '/r2': (_q, res) => { res.writeHead(302, { location: `${server.origin}/article` }); res.end() },
    '/to-trap': (_q, res) => { res.writeHead(302, { location: `http://127.0.0.1:${trap.port}/x` }); res.end() },
    '/to-metadata': (_q, res) => { res.writeHead(302, { location: 'http://169.254.169.254/latest/meta-data/' }); res.end() },
    '/to-localhost': (_q, res) => { res.writeHead(302, { location: `http://localhost:${server.port}/article` }); res.end() },
    '/localhost-image': (req, res) => send('text/html', article.replaceAll('/img/diagram.png', `http://localhost:${server.port}/img/diagram.png`))(req, res),
    '/busy': send('text/plain', 'Down for maintenance', 503),
    '/slow-down': send('text/plain', 'Too many requests', 429),
    '/picky': (req, res) => {
      if ((req.headers.accept ?? '').startsWith('text/markdown')) { res.writeHead(406, { 'content-type': 'text/plain' }); res.end('Not Acceptable'); return }
      res.writeHead(200, { 'content-type': 'text/html' }); res.end(article)
    },
    // A markdown stub to the markdown Accept, the article to a browser's.
    '/stub': (req, res) => (req.headers.accept ?? '').startsWith('text/markdown')
      ? send('text/markdown; charset=utf-8', '# react\n\n@18.2.0\n\n[View react on npm](https://npmjs.com/package/react)\n')(req, res)
      : send('text/html; charset=utf-8', article)(req, res),
    // A short page either way, its HTML a few words longer.
    '/short': (req, res) => (req.headers.accept ?? '').startsWith('text/markdown')
      ? send('text/markdown', '# Changelog\n\nVersion 1.0.1 fixes the date parser.\n')(req, res)
      : send('text/html', '<!doctype html><html><head><title>Changelog</title></head><body><article><h1>Changelog</h1><p>Version 1.0.1 fixes the date parser.</p><p>Older versions are listed on the releases page.</p></article></body></html>')(req, res),
    '/trap-image': send('text/html', article.replace('/img/diagram.png', `http://127.0.0.1:${trap.port}/diagram.png`)),
    '/many': send('text/html', many.join('')),
    '/rfc8439.html': send('text/html', await fixture('bare-pre.html')),
    '/thin': send('text/html', '<!doctype html><html><head><title>Thin</title></head><body><div id="root"></div></body></html>'),
    // A large inline script first, as Next.js error pages have: its text is not the body.
    '/gone': send('text/html', '<html><head><title>Gone</title><script>self.__next_f.push(' + '"x",'.repeat(40000) + ')</script></head><body><h1>Gone</h1><p>This page was removed in 2019 and will not be back.</p></body></html>', 410),
    '/korean': send('text/html; charset=euc-kr', Buffer.from([
      ...Buffer.from('<html><head><title>'), 0xc7, 0xd1, 0xb1, 0xdb, ...Buffer.from('</title></head><body><article><h1>'), 0xc7, 0xd1, 0xb1, 0xdb,
      ...Buffer.from('</h1><p>'), 0xc7, 0xd1, 0xb1, 0xdb, 0xbe, 0xee, ...Buffer.from(' text text text.</p></article></body></html>'),
    ])),
  })
  env = { ...process.env, WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}`, WEB_CHROME: 'none' }
})

after(async () => {
  for (const s of stall) s.res.destroy()
  await server.close()
  await trap.close()
})

const ok = (r: ClipResult): ClipOk => {
  assert.equal(r.ok, true, JSON.stringify(r))
  return r as ClipOk
}

test('an article becomes page.md with clipper frontmatter and its images downloaded beside it', async () => {
  const cacheDir = await tmpCache()
  const r = ok(await clip(`${server.origin}/article`, { cacheDir, env }))
  assert.equal(r.kind, 'html')
  assert.equal(r.cached, false)
  assert.equal(r.file, join(r.dir, 'page.md'))
  assert.equal(r.title, 'Gardens of the Test Server')
  const md = await readFile(r.file, 'utf8')
  assert.match(md, /^---\ntitle: "Gardens of the Test Server"\n/)
  assert.match(md, new RegExp(`\\nsource: "${server.origin}/article"\\n`))
  assert.match(md, /\nfetched: \d{4}-\d\d-\d\dT/)
  assert.match(md, /\nword_count: \d+\n/)

  const byAlt = Object.fromEntries(r.images.map(i => [i.alt, i]))
  // The diagram, saved once though linked twice.
  assert.equal(byAlt['A diagram of the beds'].file, 'assets/01.png')
  assert.equal(byAlt['The same diagram again'].file, 'assets/01.png')
  // Lazy data-src and srcset variants resolve to their real images.
  assert.ok(byAlt['The lazy bed']?.file, JSON.stringify(r.images))
  assert.ok(byAlt['Responsive beds']?.file, JSON.stringify(r.images))
  // The extension comes from the content type, not the URL.
  assert.match(byAlt['Photo with no extension'].file!, /^assets\/\d\d\.webp$/)
  // Every saved image link in page.md points at assets/…
  for (const img of r.images.filter(i => i.file)) {
    assert.ok(md.includes(`](${img.file})`), img.file)
    assert.equal((await stat(join(r.dir, img.file!))).size, img.bytes)
    assert.ok(md.split('\n')[img.line - 1].includes(img.file!), `image on line ${img.line}`)
  }
  const files = (await readdir(join(r.dir, 'assets'))).sort()
  assert.equal(files.length, new Set(r.images.filter(i => i.file).map(i => i.file)).size)

  // The fenced code keeps its language, and its comment is not a heading.
  assert.match(md, /```python\n# water the beans first/)
  assert.ok(!r.outline!.some(e => e.title.includes('water the beans')))
  assert.deepEqual(r.outline!.filter(e => e.level > 0).map(e => e.title), ['Lazy pictures', 'Code in the shed'])
  assert.equal(r.lines, md.split('\n').length - (md.endsWith('\n') ? 1 : 0))
  assert.ok(r.tokens! > 0 && r.words! > 50)

  const meta = JSON.parse(await readFile(join(r.dir, 'meta.json'), 'utf8'))
  assert.equal(meta.cached, undefined)
  assert.equal(meta.dir, r.dir)
})

test('the whole page is saved beside the article as full.md: what the article leaves out, its images as absolute links never fetched', async () => {
  const cacheDir = await tmpCache()
  const hits = server.hits.length
  const r = ok(await clip(`${server.origin}/crates/tinycrate`, { cacheDir, env }))
  const page = await readFile(r.file, 'utf8')
  assert.doesNotMatch(page, /77\.6 KiB/)

  assert.ok(r.full, JSON.stringify(r))
  assert.equal(r.full.file, join(r.dir, 'full.md'))
  const full = await readFile(r.full.file, 'utf8')
  // The sidebar's figures and the gallery's captions, in the page's order, around the article.
  for (const text of ['MSRV', 'v1.31.0', 'MIT OR Apache-2.0', '77.6 KiB', 'Spring yield: beans 41 kg', 'Every record has a schema']) assert.ok(full.includes(text), text)
  assert.ok(full.indexOf('Every record has a schema') < full.indexOf('Spring yield') && full.indexOf('Spring yield') < full.indexOf('77.6 KiB'))
  // Hidden elements are still removed.
  assert.doesNotMatch(full, /Choose a language/)
  // Its images are links, made absolute, and never downloaded.
  assert.ok(full.includes(`![Spring yield by bed](${server.origin}/charts/yield-spring.png)`), full)
  assert.ok(full.includes(`![Autumn yield by bed](${server.origin}/crates/charts/yield-autumn.png)`), full)
  assert.ok(!server.hits.slice(hits).some(h => h.includes('/charts/')), server.hits.slice(hits).join(' '))
  assert.deepEqual(r.images, [])
  assert.ok(!(await readdir(r.dir)).includes('assets'))

  // page.md's frontmatter, with the whole page's own word count; measured as page.md is.
  const front = (md: string) => md.slice(0, md.indexOf('\n---\n') + 5).replace(/\nword_count: \d+\n/, '\n')
  assert.equal(front(full), front(page))
  assert.match(front(page), /^---\ntitle: "tinycrate 1\.0\.200"\n/)
  assert.match(full, new RegExp(`\\nword_count: ${r.full.words}\\n`))
  assert.ok(r.full.words >= r.words! + FULL_LIMITS.minWords, `${r.full.words} against ${r.words}`)
  assert.equal(r.full.lines, full.split('\n').length - 1)
  assert.equal(r.full.tokens, estimateTokens(full))
  assert.equal(r.full.images, 2)

  // A cached copy carries it too.
  const again = ok(await clip(`${server.origin}/crates/tinycrate`, { cacheDir, env }))
  assert.equal(again.cached, true)
  assert.deepEqual(again.full, r.full)
})

test('full.md is saved for an image link the article lacks, and not made when the whole page adds nothing', async () => {
  const beside = ok(await clip(`${server.origin}/gallery`, { cacheDir: await tmpCache(), env }))
  assert.ok(beside.full, JSON.stringify(beside))
  assert.ok(beside.full.words < beside.words! + FULL_LIMITS.minWords, `${beside.full.words} against ${beside.words}`)
  assert.ok((await readFile(beside.full.file, 'utf8')).includes(`![Beside the article](${server.origin}/charts/beside.png)`))

  // The article fixture's page adds its menu and footer, a few words, and no image.
  const r = ok(await clip(`${server.origin}/article`, { cacheDir: await tmpCache(), env }))
  assert.equal(r.full, undefined)
  assert.ok(!(await readdir(r.dir)).includes('full.md'))
  assert.deepEqual(r.notes, [])
  // A markdown page has none: its site wrote it, and nothing was dropped.
  const md = ok(await clip(`${server.origin}/notes.md`, { cacheDir: await tmpCache(), env }))
  assert.equal(md.full, undefined)
})

test('an article whose extraction took over FULL_LIMITS.skipAfterMs gets no full.md, and a note says so', async t => {
  const before = FULL_LIMITS.skipAfterMs
  FULL_LIMITS.skipAfterMs = -1 // any extraction takes longer
  t.after(() => { FULL_LIMITS.skipAfterMs = before })
  const r = ok(await clip(`${server.origin}/crates/tinycrate`, { cacheDir: await tmpCache(), env }))
  assert.equal(r.full, undefined)
  assert.ok(!(await readdir(r.dir)).includes('full.md'))
  assert.equal(r.notes.length, 1, r.notes.join('|'))
  assert.match(r.notes[0], /^the whole page \(full\.md\) was not saved: extracting the article took \d+\.\d s$/)
})

test('an image under 1 KiB keeps its remote link, with the reason recorded', async () => {
  // Served markdown, so no extractor stands between the link and the image step.
  const r = ok(await clip(`${server.origin}/pixel.md`, { cacheDir: await tmpCache(), env }))
  assert.deepEqual(r.images, [{ url: `${server.origin}/img/pixel.gif`, alt: 'tracker', line: 9, error: 'under 1 KiB (42 bytes)' }])
  const md = await readFile(r.file, 'utf8')
  assert.equal(md.split('\n')[8], `![tracker](${server.origin}/img/pixel.gif)`)
})

test('the cache answers a repeat request without a request, and --refresh publishes a new generation', async () => {
  const cacheDir = await tmpCache()
  const first = ok(await clip(`${server.origin}/article`, { cacheDir, env }))
  const hits = server.hits.length
  const again = ok(await clip(`${server.origin}/article#section`, { cacheDir, env }))
  assert.equal(again.cached, true)
  assert.equal(again.dir, first.dir)
  assert.equal(again.url, `${server.origin}/article#section`)
  assert.equal(server.hits.length, hits)
  const fresh = ok(await clip(`${server.origin}/article`, { cacheDir, env, refresh: true }))
  assert.equal(fresh.cached, false)
  assert.notEqual(fresh.dir, first.dir)
  assert.ok((await stat(first.file)).isFile())
})

test('two concurrent fetches of one URL publish two complete generations', async () => {
  const cacheDir = await tmpCache()
  const [a, b] = (await Promise.all([1, 2].map(() => clip(`${server.origin}/article`, { cacheDir, env, refresh: true })))).map(ok)
  assert.notEqual(a.dir, b.dir)
  for (const r of [a, b]) assert.ok(JSON.parse(await readFile(join(r.dir, 'meta.json'), 'utf8')).ok)
  const again = ok(await clip(`${server.origin}/article`, { cacheDir, env }))
  assert.equal(again.dir, [a.dir, b.dir].sort()[1])
})

test('a served markdown file gets frontmatter and its images', async () => {
  const cacheDir = await tmpCache()
  const r = ok(await clip(`${server.origin}/notes.md`, { cacheDir, env }))
  assert.equal(r.kind, 'markdown')
  assert.equal(r.title, 'Field Notes')
  const md = await readFile(r.file, 'utf8')
  assert.match(md, new RegExp(`^---\\ntitle: "Field Notes"\\nsource: "${server.origin}/notes.md"\\nfetched: [^\\n]+\\n---\\n\\n# Field Notes\\n`))
  assert.ok(md.includes('![chart](assets/01.png)'))
  assert.deepEqual(r.outline!.map(e => e.title), ['(frontmatter)', 'Field Notes', 'Later'])
})

test('JSON is pretty-printed into page.json, plain text kept as served in page.txt', async () => {
  const cacheDir = await tmpCache()
  const j = ok(await clip(`${server.origin}/data.json`, { cacheDir, env }))
  assert.equal(j.kind, 'json')
  assert.equal(await readFile(j.file, 'utf8'), JSON.stringify({ a: 1, b: [1, 2] }, null, 2) + '\n')
  const t = ok(await clip(`${server.origin}/readme.txt`, { cacheDir, env }))
  assert.equal(t.kind, 'text')
  assert.equal(t.file, join(t.dir, 'page.txt'))
  assert.equal(await readFile(t.file, 'utf8'), 'Plain text.\n# not a heading\n')
  assert.deepEqual(t.outline!.map(e => e.title), ['(body)'])
})

test('a PDF is saved as page.pdf, with page.txt and one outline entry per page', { skip: noPdftotext }, async () => {
  const cacheDir = await tmpCache()
  const r = ok(await clip(`${server.origin}/paper.pdf`, { cacheDir, env }))
  assert.equal(r.kind, 'pdf')
  assert.equal(r.file, join(r.dir, 'page.pdf'))
  assert.equal(r.text, join(r.dir, 'page.txt'))
  assert.match(await readFile(r.text!, 'utf8'), /Second page words/)
  assert.deepEqual(r.outline!.map(e => e.title), ['page 1', 'page 2', 'page 3'])
})

test('a PDF without pdftotext is saved with a note and no text figures', async () => {
  const cacheDir = await tmpCache()
  const r = ok(await clip(`${server.origin}/paper.pdf`, { cacheDir, env: { ...env, PATH: '/nonexistent' } }))
  assert.equal(r.kind, 'pdf')
  assert.equal(r.text, undefined)
  assert.equal(r.lines, undefined)
  assert.equal(r.outline, undefined)
  assert.ok(r.notes.some(n => n.includes('pdftotext')), r.notes.join('|'))
})

test('pdftotext cut short by the time left says so, and the PDF is still saved', async () => {
  const bin = await mkdtemp(join(tmpdir(), 'slow-pdftotext-'))
  await writeFile(join(bin, 'pdftotext'), '#!/bin/sh\nexec sleep 30\n', { mode: 0o755 })
  const r = ok(await clip(`${server.origin}/paper.pdf`, { cacheDir: await tmpCache(), env: { ...env, PATH: `${bin}:${process.env.PATH}` }, deadlineMs: 3000 }))
  assert.equal(r.kind, 'pdf')
  assert.equal(r.text, undefined)
  assert.equal(r.notes.length, 1)
  assert.match(r.notes[0], /^no text extracted: pdftotext did not finish within \d s$/)
})

test('a page still arriving past the time to its headers is fetched; one that stops fails at the stall limit', async t => {
  // The hard eval's 17.6 MB IEA PDF timed out at a fixed 30 s while it was still arriving (board #143).
  const steadyMs = FETCH_LIMITS.headersMs + 3000
  const timers: NodeJS.Timeout[] = []
  const slow = await startServer({
    '/steady.txt': (_req, res) => {
      res.writeHead(200, { 'content-type': 'text/plain' })
      const until = Date.now() + steadyMs
      const next = () => {
        if (Date.now() >= until) { res.end('the last line\n'); return }
        res.write('a line still arriving\n')
        timers.push(setTimeout(next, 1000))
      }
      next()
    },
    '/stops.txt': (_req, res) => { res.writeHead(200, { 'content-type': 'text/plain', 'content-length': String(1048576) }); res.write('the first line, and no more\n') },
  })
  t.after(async () => { for (const x of timers) clearTimeout(x); await slow.close() })
  const slowEnv = { ...env, WEB_ALLOW_HOSTS: `127.0.0.1:${slow.port}` }
  const started = Date.now()
  const [steady, stops] = await Promise.all([
    clip(`${slow.origin}/steady.txt`, { cacheDir: await tmpCache(), env: slowEnv }).then(r => ({ r, ms: Date.now() - started })),
    clip(`${slow.origin}/stops.txt`, { cacheDir: await tmpCache(), env: slowEnv }).then(r => ({ r, ms: Date.now() - started })),
  ])
  const page = ok(steady.r)
  assert.ok(steady.ms >= steadyMs, `took ${steady.ms} ms`)
  assert.match(await readFile(page.file, 'utf8'), /^(a line still arriving\n)+the last line\n$/)
  assert.equal(stops.r.ok, false, JSON.stringify(stops.r))
  assert.equal((stops.r as ClipError).error, `stalled: no data for ${FETCH_LIMITS.stallMs / 1000} s after 28 bytes of 1.0 MB`)
  assert.ok(stops.ms >= FETCH_LIMITS.stallMs && stops.ms < FETCH_LIMITS.stallMs + 10_000, `failed after ${stops.ms} ms`)
})

test('redirects are followed and the final URL recorded', async () => {
  const cacheDir = await tmpCache()
  const r = ok(await clip(`${server.origin}/r1`, { cacheDir, env }))
  assert.equal(r.url, `${server.origin}/r1`)
  assert.equal(r.finalUrl, `${server.origin}/article`)
})

test('a markdown stub gives way to the HTML page, and a page short either way stays the markdown served', async () => {
  const hits = server.hits.length
  const r = ok(await clip(`${server.origin}/stub`, { cacheDir: await tmpCache(), env }))
  assert.equal(r.kind, 'html')
  assert.equal(r.contentType, 'text/html; charset=utf-8')
  assert.equal(r.title, 'Gardens of the Test Server')
  const md = await readFile(r.file, 'utf8')
  assert.ok(!md.includes('View react on npm'))
  assert.match(md, /water the beans first/)
  assert.deepEqual(server.hits.slice(hits).filter(h => h === '/stub'), ['/stub', '/stub'])

  const short = ok(await clip(`${server.origin}/short`, { cacheDir: await tmpCache(), env }))
  assert.equal(short.kind, 'markdown')
  assert.equal(short.title, 'Changelog')
  assert.match(await readFile(short.file, 'utf8'), /\n---\n\n# Changelog\n\nVersion 1\.0\.1 fixes the date parser\.\n$/)
  // The HTML page was thin too, and this machine (WEB_CHROME=none) would not render it.
  assert.deepEqual(short.notes, ['rendering unavailable on this machine: turned off by WEB_CHROME=none'])
})

test('a 406 is retried once with a browser Accept', async () => {
  const r = ok(await clip(`${server.origin}/picky`, { cacheDir: await tmpCache(), env }))
  assert.equal(r.kind, 'html')
})

const failure = (r: ClipResult): ClipError => {
  assert.equal(r.ok, false, JSON.stringify(r))
  return r as ClipError
}

test('a failure says what failed, carries the body, and publishes nothing', async () => {
  const cacheDir = await tmpCache()
  const r = failure(await clip(`${server.origin}/gone`, { cacheDir, env }))
  assert.equal(r.status, 410)
  assert.match(r.bodySnippet!, /^Gone Gone This page was removed in 2019/)
  assert.ok(r.bodySnippet!.length <= 300)
  const notFound = failure(await clip(`${server.origin}/nothing`, { cacheDir, env }))
  assert.equal(notFound.status, 404)
  // Each entry holds its failure, remembered, and no generation.
  assert.deepEqual((await entryContents(cacheDir)).map(p => p.split('/')[1]), ['.failed.json', '.failed.json'])
})

test('a failure is remembered: the next call answers from it without a request, until refresh or FAILURE_MEMORY_MS', async () => {
  const cacheDir = await tmpCache()
  const url = `${server.origin}/nothing`
  const first = failure(await clip(url, { cacheDir, env }))
  assert.equal(first.failedAt, undefined)
  const hits = server.hits.length
  const again = failure(await clip(`${url}#part`, { cacheDir, env }))
  assert.equal(server.hits.length, hits)
  assert.deepEqual({ ...again, failedAt: undefined }, { ...first, url: `${url}#part`, failedAt: undefined })
  assert.ok(Date.now() - Date.parse(again.failedAt!) < 5000, again.failedAt)

  // refresh asks the site again.
  failure(await clip(url, { cacheDir, env, refresh: true }))
  assert.equal(server.hits.length, hits + 1)

  // A memory older than FAILURE_MEMORY_MS is not used.
  const file = join(entryDir(cacheDir, new URL(url)), '.failed.json')
  const stale = { ...JSON.parse(await readFile(file, 'utf8')), failedAt: new Date(Date.now() - FAILURE_MEMORY_MS - 1000).toISOString() }
  await writeFile(file, JSON.stringify(stale))
  const later = failure(await clip(url, { cacheDir, env }))
  assert.equal(server.hits.length, hits + 2)
  assert.equal(later.failedAt, undefined)
})

test('a 4xx is permanent, except 408 and 429; a 5xx and a network error are not, and are remembered too', async () => {
  const cacheDir = await tmpCache()
  assert.equal(failure(await clip(`${server.origin}/nothing`, { cacheDir, env })).permanent, true)
  assert.equal(failure(await clip(`${server.origin}/gone`, { cacheDir, env })).permanent, true)
  assert.equal(failure(await clip(`${server.origin}/slow-down`, { cacheDir, env })).permanent, undefined)
  const busy = failure(await clip(`${server.origin}/busy`, { cacheDir, env }))
  assert.equal(busy.status, 503)
  assert.equal(busy.permanent, undefined)
  assert.ok(failure(await clip(`${server.origin}/busy`, { cacheDir, env })).failedAt)

  // A closed port: nothing listens once the trap is gone, so the connection is refused.
  const closed = await startTrap()
  await closed.close()
  const allowClosed = { ...env, WEB_ALLOW_HOSTS: `${env.WEB_ALLOW_HOSTS},127.0.0.1:${closed.port}` }
  const down = failure(await clip(`http://127.0.0.1:${closed.port}/`, { cacheDir, env: allowClosed }))
  assert.match(down.error, /^network error: /)
  assert.equal(down.permanent, undefined)
  assert.ok(failure(await clip(`http://127.0.0.1:${closed.port}/`, { cacheDir, env: allowClosed })).failedAt)
})

test('an agent URL at a non-public address is refused without a request, permanent, and not remembered', async () => {
  const cacheDir = await tmpCache()
  for (const url of [`http://127.0.0.1:${trap.port}/`, `http://localhost:${trap.port}/`, `http://[::1]:${trap.port}/`, `http://2130706433:${trap.port}/`]) {
    const r = failure(await clip(url, { cacheDir, env }))
    assert.match(r.error, /^refused: /, url)
    assert.equal(r.permanent, true, url)
  }
  assert.equal(trap.connections, 0)
  assert.deepEqual(await readdir(cacheDir), [])
})

test('a host on WEB_DENY_HOSTS is refused before any request and before its saved copy, as the agent URL or a redirect hop', async () => {
  const cacheDir = await tmpCache()
  const open = { ...env, WEB_ALLOW_HOSTS: `${env.WEB_ALLOW_HOSTS},localhost:${server.port}` }
  ok(await clip(`http://localhost:${server.port}/article`, { cacheDir, env: open }))
  const denied = { ...open, WEB_DENY_HOSTS: 'localhost' }
  const hits = server.hits.length
  const r = failure(await clip(`http://localhost:${server.port}/article`, { cacheDir, env: denied }))
  assert.equal(r.error, 'refused: localhost is on the deny list (WEB_DENY_HOSTS)')
  assert.equal(r.permanent, true)
  assert.equal(server.hits.length, hits)

  const hop = failure(await clip(`${server.origin}/to-localhost`, { cacheDir, env: denied }))
  assert.equal(hop.error, 'refused: localhost is on the deny list (WEB_DENY_HOSTS)')
  assert.deepEqual(server.hits.slice(hits), ['/to-localhost'])
})

test('a saved copy whose final URL is on a host denied since is refused, permanent, without a request', async () => {
  const cacheDir = await tmpCache()
  const open = { ...env, WEB_ALLOW_HOSTS: `${env.WEB_ALLOW_HOSTS},localhost:${server.port}` }
  const saved = ok(await clip(`${server.origin}/to-localhost`, { cacheDir, env: open }))
  assert.equal(saved.finalUrl, `http://localhost:${server.port}/article`)
  const hits = server.hits.length
  const r = failure(await clip(`${server.origin}/to-localhost`, { cacheDir, env: { ...open, WEB_DENY_HOSTS: 'localhost' } }))
  assert.equal(r.error, 'refused: localhost is on the deny list (WEB_DENY_HOSTS)')
  assert.equal(r.permanent, true)
  assert.equal(server.hits.length, hits)
})

test('an image on a denied host keeps its remote link, refused, and is never requested', async () => {
  const denied = { ...env, WEB_ALLOW_HOSTS: `${env.WEB_ALLOW_HOSTS},localhost:${server.port}`, WEB_DENY_HOSTS: 'localhost' }
  const hits = server.hits.length
  const r = ok(await clip(`${server.origin}/localhost-image`, { cacheDir: await tmpCache(), env: denied }))
  const img = r.images.find(i => i.url.startsWith(`http://localhost:${server.port}/`))
  assert.ok(img, JSON.stringify(r.images))
  assert.equal(img.file, undefined)
  assert.equal(img.error, 'refused: on the deny list')
  assert.ok(!server.hits.slice(hits).includes('/img/diagram.png'), server.hits.slice(hits).join(' '))
})

test('an http: URL on the default port is tried over https first; any other URL as given', () => {
  assert.equal(httpsFirst(new URL('http://example.com/a?b=1'))?.href, 'https://example.com/a?b=1')
  assert.equal(httpsFirst(new URL('http://example.com:80/'))?.href, 'https://example.com/')
  assert.equal(httpsFirst(new URL('http://example.com:8080/')), undefined)
  assert.equal(httpsFirst(new URL('https://example.com/')), undefined)
})

test('https first falls back to the URL as given when https brings no page or is refused, saying why', async () => {
  const response = (url: URL, status: number, statusText = ''): HttpResponse => ({ status, statusText, headers: {}, body: Buffer.alloc(0), url })
  const run = async (https: (u: URL) => HttpResponse, http: (u: URL) => HttpResponse = u => response(u, 200)) => {
    const asked: string[] = []
    const out = await fetchHttpsFirst(new URL('http://example.com/a'), async u => { asked.push(u.href); return u.protocol === 'https:' ? https(u) : http(u) })
    return { asked, final: out.res.url.href, httpsFailed: out.httpsFailed }
  }
  assert.deepEqual(await run(u => response(u, 200)), { asked: ['https://example.com/a'], final: 'https://example.com/a', httpsFailed: undefined })
  assert.deepEqual(await run(u => response(u, 404, 'Not Found')), { asked: ['https://example.com/a', 'http://example.com/a'], final: 'http://example.com/a', httpsFailed: 'HTTP 404 Not Found' })
  assert.deepEqual(await run(() => { throw new HttpError('network error: self-signed certificate') }), { asked: ['https://example.com/a', 'http://example.com/a'], final: 'http://example.com/a', httpsFailed: 'network error: self-signed certificate' })
  // https may be refused for where it redirected, not for the URL's host: http is still read.
  const hop = 'refused: tracker.test is on the deny list (WEB_DENY_HOSTS)'
  assert.deepEqual(await run(() => { throw new RefusedError(hop) }), { asked: ['https://example.com/a', 'http://example.com/a'], final: 'http://example.com/a', httpsFailed: hop })
  // A refusal of the http attempt too is the answer.
  const own = 'refused: example.com resolves to a non-public address (10.0.0.7); for a local server use curl through Bash'
  await assert.rejects(run(() => { throw new RefusedError(own) }, () => { throw new RefusedError(own) }), (e: unknown) => e instanceof RefusedError && e.message === own)
  // An https download that ran out the time left is the answer: http would have none.
  const asked: string[] = []
  const late = 'timed out after 150 s with 12.3 of 17.6 MB received'
  await assert.rejects(fetchHttpsFirst(new URL('http://example.com/a'), async u => { asked.push(u.href); throw new HttpError(late, true) }, () => 0), (e: unknown) => e instanceof HttpError && e.message === late)
  assert.deepEqual(asked, ['https://example.com/a'])
})

test('a redirect to a non-public address is refused, and the trap receives nothing', async () => {
  const cacheDir = await tmpCache()
  for (const path of ['/to-trap', '/to-metadata']) {
    const r = await clip(`${server.origin}${path}`, { cacheDir, env })
    assert.equal(r.ok, false)
    assert.match(!r.ok ? r.error : '', /^refused: /)
  }
  assert.equal(trap.connections, 0)
})

test('an image at a non-public address keeps its remote link, refused, and the trap receives nothing', async () => {
  const r = ok(await clip(`${server.origin}/trap-image`, { cacheDir: await tmpCache(), env }))
  const img = r.images.find(i => i.url.includes(`:${trap.port}/`))
  assert.ok(img, JSON.stringify(r.images))
  assert.equal(img.file, undefined)
  assert.equal(img.error, 'refused: non-public address')
  assert.equal(trap.connections, 0)
})

test('a page over 80 headings drops its deepest level and says how many headings were left out', async () => {
  const r = ok(await clip(`${server.origin}/many`, { cacheDir: await tmpCache(), env }))
  assert.ok(r.outline!.length <= 80)
  assert.ok(!r.outline!.some(e => e.level === 3))
  assert.equal(r.outlineOmitted, 96)
})

test('the deadline publishes the page with stalled images marked, before CLIP_DEADLINE_MS', async () => {
  const stallServer = await startServer({
    '/stalling': send('text/html', stallingHtml),
    '*': (_req, res) => { stall.push({ res }) },
  })
  try {
    const start = Date.now()
    const r = ok(await clip(`${stallServer.origin}/stalling`, { cacheDir: await tmpCache(), env: { ...env, WEB_ALLOW_HOSTS: `127.0.0.1:${stallServer.port}` }, deadlineMs: 2000 }))
    const took = Date.now() - start
    assert.ok(took < 3000, `took ${took} ms`)
    assert.equal(r.images.length, 40)
    assert.ok(r.images.every(i => i.error === 'not downloaded: time budget'), JSON.stringify(r.images.slice(0, 3)))
  } finally {
    for (const s of stall.splice(0)) s.res.destroy()
    await stallServer.close()
  }
})

test('WEB_CHROME=none turns rendering off, with the note, when the page needs it', async () => {
  const r = ok(await clip(`${server.origin}/thin`, { cacheDir: await tmpCache(), env: { ...env, WEB_CHROME: 'none' } }))
  assert.equal(r.rendered, false)
  assert.ok(r.notes.includes('rendering unavailable on this machine: turned off by WEB_CHROME=none'), r.notes.join('|'))
  const missing = ok(await clip(`${server.origin}/thin`, { cacheDir: await tmpCache(), env: { ...env, WEB_CHROME: '/nonexistent/chrome' } }))
  assert.ok(missing.notes.some(n => n.startsWith('rendering unavailable on this machine: ') && n.includes('WEB_CHROME')), missing.notes.join('|'))
  const full = ok(await clip(`${server.origin}/article`, { cacheDir: await tmpCache(), env: { ...env, WEB_CHROME: 'none' } }))
  assert.deepEqual(full.notes, [])
})

test('a page with no <html> or <body>, only <pre> blocks, is extracted with no browser', async () => {
  // rfc-editor's htmlized RFCs; this env has rendering off, so the plain extraction is all there is.
  const r = ok(await clip(`${server.origin}/rfc8439.html`, { cacheDir: await tmpCache(), env }))
  assert.equal(r.kind, 'html')
  assert.equal(r.rendered, false)
  assert.deepEqual(r.notes, [])
  assert.ok(r.words! > 150, String(r.words))
  const md = await readFile(r.file, 'utf8')
  assert.match(md, /This document defines the ChaCha20 stream cipher/)
  assert.match(md, /Copyright \(c\) 2018 IETF Trust/)
})

test('a page in a legacy charset is decoded by its declared charset', async () => {
  const r = ok(await clip(`${server.origin}/korean`, { cacheDir: await tmpCache(), env }))
  assert.equal(r.title, '한글')
  assert.match(await readFile(r.file, 'utf8'), /한글어 text/)
})

test('unsupported schemes and malformed URLs fail with a reason', async () => {
  const cacheDir = await tmpCache()
  const ftp = await clip('ftp://example.com/x', { cacheDir, env })
  assert.equal(ftp.ok, false)
  assert.match(!ftp.ok ? ftp.error : '', /^unsupported scheme/)
  const bad = await clip('not a url', { cacheDir, env })
  assert.equal(bad.ok, false)
  assert.match(!bad.ok ? bad.error : '', /^invalid URL/)
})
