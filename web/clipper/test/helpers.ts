// Local servers, traps and fixtures for the clipper's tests: everything is
// served from 127.0.0.1 so the tests run offline and deterministically.
import { createServer } from 'node:http'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { createServer as createTcpServer } from 'node:net'
import { createSocket } from 'node:dgram'
import { mkdtemp, readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { findChrome } from '../src/render.ts'

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

export const send = (type: string, body: string | Buffer, status = 200, extra: Record<string, string> = {}): Handler =>
  (_req, res) => { res.writeHead(status, { 'content-type': type, ...extra }); res.end(body) }

/** Bytes that open like a PNG, `size` long: the clipper keeps what it is sent. */
export function pngBytes(size: number, seed = 1): Buffer {
  const b = Buffer.alloc(size)
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(b)
  for (let i = 8; i < size; i++) b[i] = (i * 31 + seed) & 0xff
  return b
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
