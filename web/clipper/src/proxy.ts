// The filtering proxy headless Chromium renders through: it runs in-process
// on 127.0.0.1 for the render's lifetime and applies the network boundary to
// every plain HTTP request and every CONNECT (HTTPS and WebSocket tunnels),
// connecting to the address it checked.
import http from 'node:http'
import { connect } from 'node:net'
import type { Socket } from 'node:net'
import { pinnedLookup, resolveChecked } from './netguard.ts'

export type EgressProxy = { port: number; close: () => Promise<void> }

const HOP_HEADERS = ['proxy-connection', 'proxy-authorization', 'connection', 'keep-alive', 'transfer-encoding', 'te', 'trailer', 'upgrade']

export async function startEgressProxy(allow: Set<string>): Promise<EgressProxy> {
  const sockets = new Set<Socket>()
  const track = (s: Socket) => { sockets.add(s); s.on('close', () => sockets.delete(s)) }

  const server = http.createServer(async (req, res) => {
    let url: URL
    try {
      url = new URL(req.url ?? '')
      if (url.protocol !== 'http:') throw new Error('not http')
    } catch {
      res.writeHead(400).end('absolute http URL expected')
      return
    }
    const port = Number(url.port) || 80
    let addresses
    try {
      addresses = await resolveChecked(url.hostname, port, { allow })
    } catch (e) {
      res.writeHead(403, { 'content-type': 'text/plain' }).end(e instanceof Error ? e.message : 'refused')
      return
    }
    const headers = { ...req.headers }
    for (const h of HOP_HEADERS) delete headers[h]
    const upstream = http.request({
      hostname: url.hostname.replace(/^\[|\]$/g, ''), port, path: url.pathname + url.search, method: req.method, headers,
      lookup: pinnedLookup(addresses), agent: false,
    }, up => {
      res.writeHead(up.statusCode ?? 502, up.headers)
      up.pipe(res)
    })
    upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end() })
    req.pipe(upstream)
  })

  server.on('connect', async (req: http.IncomingMessage, client: Socket, head: Buffer) => {
    track(client)
    client.on('error', () => {})
    const m = /^\[?([^\]]+?)\]?:(\d+)$/.exec(req.url ?? '')
    if (!m) { client.end('HTTP/1.1 400 Bad Request\r\n\r\n'); return }
    const [, host, portText] = m
    let addresses
    try {
      addresses = await resolveChecked(host, Number(portText), { allow })
    } catch {
      client.end('HTTP/1.1 403 Forbidden\r\n\r\n')
      return
    }
    const upstream = connect({ host: addresses[0].address, port: Number(portText) })
    track(upstream)
    upstream.on('connect', () => {
      client.write('HTTP/1.1 200 Connection Established\r\n\r\n')
      if (head.length) upstream.write(head)
      upstream.pipe(client)
      client.pipe(upstream)
    })
    upstream.on('error', () => client.end('HTTP/1.1 502 Bad Gateway\r\n\r\n'))
    client.on('close', () => upstream.destroy())
  })

  // A WebSocket through a proxy is a CONNECT tunnel; a bare upgrade request is not served.
  server.on('upgrade', (_req, socket: Socket) => socket.end('HTTP/1.1 501 Not Implemented\r\n\r\n'))
  server.on('connection', track)

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => resolve())
  })
  return {
    port: (server.address() as { port: number }).port,
    close: () => new Promise<void>(resolve => {
      for (const s of sockets) s.destroy()
      server.close(() => resolve())
    }),
  }
}
