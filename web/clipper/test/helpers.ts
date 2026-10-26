// Local servers, traps and fixtures for the clipper's tests: everything is
// served from 127.0.0.1 so the tests run offline and deterministically.
import { createServer } from 'node:http'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { createServer as createTcpServer } from 'node:net'
import { createSocket } from 'node:dgram'
import { mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { findChrome } from '../src/render.ts'
import { CHECK_FLOOR_MS, FAILURE_MEMORY_MS, readCurrent, recordCheck } from '../src/cache.ts'
import { entryDir } from '../src/key.ts'

export const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), 'fixtures')
export const fixture = (name: string) => readFile(join(FIXTURES, name), 'utf8')

export type Handler = (req: IncomingMessage, res: ServerResponse) => void | Promise<void>

export async function startServer(routes: Record<string, Handler>) {
  const hits: string[] = []
  const server = createServer(async (req, res) => {
    hits.push(req.url ?? '')
    const route = routes[(req.url ?? '').split('?')[0]] ?? routes['*']
    if (!route) { res.writeHead(404, { 'content-type': 'text/html' }); res.end('<h1>Not here</h1><p>No such page on this test server.</p>'); return }
    await route(req, res)
  })
  await new Promise<void>(r => server.listen(0, '127.0.0.1', r))
  const port = (server.address() as { port: number }).port
  return {
    port,
    origin: `http://127.0.0.1:${port}`,
    hits,
    close: () => { server.closeAllConnections(); return new Promise<void>(r => server.close(() => r())) },
  }
}

/** A TCP port that counts every connection made to it. */
export async function startTrap() {
  const state = { port: 0, connections: 0, close: async () => {} }
  const server = createTcpServer(sock => { state.connections++; sock.destroy() })
  await new Promise<void>(r => server.listen(0, '127.0.0.1', r))
  state.port = (server.address() as { port: number }).port
  state.close = () => new Promise<void>(r => server.close(() => r()))
  return state
}

/** A UDP port that counts every packet sent to it. */
export async function startUdpTrap() {
  const sock = createSocket('udp4')
  const state = { port: 0, packets: 0, close: async () => {} }
  sock.on('message', () => { state.packets++ })
  await new Promise<void>(r => sock.bind(0, '127.0.0.1', r))
  state.port = sock.address().port
  state.close = () => new Promise<void>(r => sock.close(() => r()))
  return state
}

export const tmpCache = () => mkdtemp(join(tmpdir(), 'clip-test-'))

/** Moves the URL's saved copy, and its last check, past CHECK_FLOOR_MS: the next call asks the site. */
export async function pastFloor(cacheDir: string, url: string) {
  const entry = entryDir(cacheDir, new URL(url))
  const current = (await readCurrent<{ fetchedAt: string }>(entry))!
  const earlier = (at: string) => new Date(Date.parse(at) - CHECK_FLOOR_MS - 1000).toISOString()
  await writeFile(join(entry, current.generation, 'meta.json'), JSON.stringify({ ...current.meta, fetchedAt: earlier(current.meta.fetchedAt) }))
  if (current.checkedAt) await recordCheck(entry, current.generation, earlier(current.checkedAt))
}

/** Moves the URL's remembered failure past FAILURE_MEMORY_MS. */
export async function forgetFailure(cacheDir: string, url: string) {
  const file = join(entryDir(cacheDir, new URL(url)), '.failed.json')
  const failure = JSON.parse(await readFile(file, 'utf8'))
  await writeFile(file, JSON.stringify({ ...failure, failedAt: new Date(Date.parse(failure.failedAt) - FAILURE_MEMORY_MS - 1000).toISOString() }))
}

/** The cache's files and folders below its entries (host/entry/<name>), as `<entry>/<name>`: generations, .tmp- folders, failures. */
export async function entryContents(root: string): Promise<string[]> {
  const all = await readdir(root, { recursive: true })
  return all.map(p => p.split('/')).filter(p => p.length === 3).map(p => `${p[1]}/${p[2]}`).sort()
}

export const send = (type: string, body: string | Buffer, status = 200, extra: Record<string, string> = {}): Handler =>
  (_req, res) => { res.writeHead(status, { 'content-type': type, ...extra }); res.end(body) }

/** Bytes that open like a PNG, `size` long: the clipper keeps what it is sent. */
export function pngBytes(size: number, seed = 1): Buffer {
  const b = Buffer.alloc(size)
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(b)
  for (let i = 8; i < size; i++) b[i] = (i * 31 + seed) & 0xff
  return b
}

/**
 * A page whose images are inline base64 data: URIs, `bytes` each, in the forms
 * Defuddle reads: a <picture> (its <source srcset> and <img src>), an <img srcset>
 * with widths and one without, a link to one, and a gallery beside the article,
 * which only full.md keeps. `images` holds each image's bytes and URI by its alt.
 */
export function inlineImagesPage(bytes: number) {
  const image = (seed: number, type: string) => {
    const body = pngBytes(bytes, seed)
    return { body, uri: `data:image/${type};base64,${body.toString('base64')}` }
  }
  const images = { chart: image(1, 'webp'), wide: image(2, 'png'), narrow: image(3, 'png'), bare: image(4, 'png'), gallery: image(5, 'jpeg') }
  const words = '<p>' + 'Prose about the benchmark charts, long enough for the extractor to keep the article whole. '.repeat(6) + '</p>'
  const html = `<!doctype html><html><head><title>Benchmarks</title></head><body>
    <article><h1>Benchmarks</h1>${words}
    <picture><source srcset="${images.chart.uri}" media="(max-width: 30em)"><img src="${images.chart.uri}" alt="chart"></picture>${words}
    <figure><img srcset="${images.wide.uri} 800w, ${images.narrow.uri} 400w" src="${images.narrow.uri}" alt="wide"></figure>${words}
    <figure><img srcset="${images.bare.uri}" alt="bare"><figcaption>A srcset of one URI and no width</figcaption></figure>${words}
    <p>The <a href="${images.chart.uri}">chart itself</a>.</p></article>
    <aside><h2>Gallery</h2><img src="${images.gallery.uri}" alt="gallery"><p>${'Gallery notes the article leaves out. '.repeat(20)}</p></aside>
    </body></html>`
  return { html, images }
}

/** A 1×1 transparent GIF: 43 bytes. */
export const PIXEL_GIF = Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64')

/** A minimal PDF with one text line per page. */
export function pdfBytes(pages: string[]): Buffer {
  const objs: string[] = []
  const n = pages.length
  const pageIds = pages.map((_, i) => 3 + i * 2)
  objs[1] = '<< /Type /Catalog /Pages 2 0 R >>'
  objs[2] = `<< /Type /Pages /Kids [${pageIds.map(id => `${id} 0 R`).join(' ')}] /Count ${n} >>`
  const font = 3 + n * 2
  pages.forEach((text, i) => {
    const content = `BT /F1 18 Tf 72 720 Td (${text.replace(/[()\\]/g, '\\$&')}) Tj ET`
    objs[pageIds[i]] = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents ${pageIds[i] + 1} 0 R /Resources << /Font << /F1 ${font} 0 R >> >> >>`
    objs[pageIds[i] + 1] = `<< /Length ${content.length} >>\nstream\n${content}\nendstream`
  })
  objs[font] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'
  let out = '%PDF-1.4\n'
  const offsets: number[] = []
  for (let id = 1; id < objs.length; id++) {
    offsets[id] = out.length
    out += `${id} 0 obj\n${objs[id]}\nendobj\n`
  }
  const xref = out.length
  out += `xref\n0 ${objs.length}\n0000000000 65535 f \n`
  for (let id = 1; id < objs.length; id++) out += `${String(offsets[id]).padStart(10, '0')} 00000 n \n`
  out += `trailer\n<< /Size ${objs.length} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(out, 'latin1')
}

export function onPath(cmd: string): boolean {
  try { execFileSync('/bin/sh', ['-c', `command -v ${cmd}`], { stdio: 'ignore' }); return true } catch { return false }
}

const chrome = findChrome(process.env)
/** Why the rendering tests cannot run here, or false when they can. */
export const noChrome: string | false = 'note' in chrome ? `no Chromium on this machine (${chrome.note})` : false
export const noPdftotext: string | false = onPath('pdftotext') ? false : 'pdftotext is not on PATH'

export const exists = (p: string) => existsSync(p)
