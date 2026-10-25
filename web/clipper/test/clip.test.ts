import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFile, readdir, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { clip } from '../src/clip.ts'
import type { ClipResult, ClipOk } from '../src/clip.ts'
import { startServer, startTrap, tmpCache, send, fixture, pngBytes, pdfBytes, PIXEL_GIF, noPdftotext } from './helpers.ts'

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

test('a failure says what failed, carries the body, and leaves nothing in the cache', async () => {
  const cacheDir = await tmpCache()
  const r = await clip(`${server.origin}/gone`, { cacheDir, env })
  assert.equal(r.ok, false)
  if (r.ok) return
  assert.equal(r.status, 410)
  assert.match(r.bodySnippet!, /^Gone Gone This page was removed in 2019/)
  assert.ok(r.bodySnippet!.length <= 300)
  const notFound = await clip(`${server.origin}/nothing`, { cacheDir, env })
  assert.equal(notFound.ok, false)
  assert.equal(!notFound.ok && notFound.status, 404)
  assert.deepEqual(await readdir(cacheDir), [])
})

test('an agent URL at a non-public address is refused without a request', async () => {
  const cacheDir = await tmpCache()
  for (const url of [`http://127.0.0.1:${trap.port}/`, `http://localhost:${trap.port}/`, `http://[::1]:${trap.port}/`, `http://2130706433:${trap.port}/`]) {
    const r = await clip(url, { cacheDir, env })
    assert.equal(r.ok, false, url)
    assert.match(!r.ok ? r.error : '', /^refused: /, url)
  }
  assert.equal(trap.connections, 0)
  assert.deepEqual(await readdir(cacheDir), [])
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
