// HTTP requests inside the network boundary. Node's own `http`/`https` take a
// connection `lookup`, which pins each connection to the addresses the guard
// checked; the global `fetch` takes one only through the undici package.
import http from 'node:http'
import https from 'node:https'
import type { IncomingHttpHeaders, IncomingMessage } from 'node:http'
import { createBrotliDecompress, createGunzip, createInflate } from 'node:zlib'
import type { Readable } from 'node:stream'
import { pinnedLookup, RefusedError, resolveChecked } from './netguard.ts'
import type { Address } from './netguard.ts'

export const USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36'
export const MAX_REDIRECTS = 10
/**
 * How long one connection attempt may take before Node tries the host's next
 * address. Node's default, 250 ms, drops a connection to a far host while it is
 * still being made; with the other address family unreachable, every attempt
 * then fails (archive.apache.org from Seoul: 4 of 12 downloads, 2026-10-25).
 */
export const CONNECT_ATTEMPT_MS = 2500

/** A failure's text: an AggregateError (every address failed) names each address and its code. */
export function networkErrorMessage(e: unknown): string {
  if (e instanceof AggregateError && e.errors.length > 0) {
    const each = e.errors.map(x => {
      const { address, code } = x as { address?: string; code?: string }
      return [address, code].filter(Boolean).join(' ') || String((x as Error)?.message ?? x)
    })
    return `could not connect: ${each.join(', ')}`
  }
  if (e instanceof Error) return e.message || String((e as { code?: string }).code ?? e.name)
  return String(e)
}

/** A request that failed on the way: the network, a timeout, a size limit. */
export class HttpError extends Error {
  readonly timedOut: boolean

  constructor(message: string, timedOut = false) {
    super(message)
    this.timedOut = timedOut
    this.name = 'HttpError'
  }
}

export type HttpResponse = { status: number; statusText: string; headers: IncomingHttpHeaders; body: Buffer; url: URL }

export type RequestOptions = {
  method?: string
  headers?: Record<string, string>
  body?: Buffer | string
  timeoutMs: number
  maxBytes: number
  allow: Set<string>
}

/** One request, following redirects (each hop checked), within one time limit. */
export async function request(start: URL, o: RequestOptions): Promise<HttpResponse> {
  const until = Date.now() + o.timeoutMs
  const timeLeft = () => Math.max(0, until - Date.now())
  const timedOut = () => new HttpError(`timed out after ${Math.round(o.timeoutMs / 1000)} s`, true)
  let url = start
  let method = o.method ?? 'GET'
  let body = o.body
  for (let hop = 0; ; hop++) {
    if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new HttpError(`unsupported scheme: ${url.protocol}`)
    const port = Number(url.port) || (url.protocol === 'https:' ? 443 : 80)
    const addresses = await withTimeout(resolveChecked(url.hostname, port, { allow: o.allow }), timeLeft(), timedOut)
      .catch(e => { throw asTransportError(e) })
    const res = await once(url, addresses, { ...o, method, body }, timeLeft(), timedOut)
    const location = res.headers.location
    if ([301, 302, 303, 307, 308].includes(res.status) && location) {
      if (hop >= MAX_REDIRECTS) throw new HttpError(`too many redirects (more than ${MAX_REDIRECTS})`)
      try { url = new URL(location, url) } catch { throw new HttpError(`redirected to an invalid location: ${location.slice(0, 200)}`) }
      if (res.status === 303 || ((res.status === 301 || res.status === 302) && method === 'POST')) { method = 'GET'; body = undefined }
      continue
    }
    return res
  }
}

/**
 * The transport boundary: a refusal and an HttpError pass as they are, and any
 * other failure on the way to a connection (a name that does not resolve, a
 * resolver error) becomes a network error, which a fetch reports as a result.
 */
function asTransportError(e: unknown): Error {
  if (e instanceof RefusedError || e instanceof HttpError) return e
  return new HttpError(`network error: ${networkErrorMessage(e)}`)
}

function withTimeout<T>(p: Promise<T>, ms: number, error: () => Error): Promise<T> {
  let timer: NodeJS.Timeout
  return Promise.race([p, new Promise<never>((_, reject) => { timer = setTimeout(() => reject(error()), ms) })]).finally(() => clearTimeout(timer))
}

function once(url: URL, addresses: Address[], o: RequestOptions & { method: string }, ms: number, timedOut: () => Error): Promise<HttpResponse> {
  return new Promise((resolve, reject) => {
    if (ms <= 0) { reject(timedOut()); return }
    const mod = url.protocol === 'https:' ? https : http
    const req = mod.request({
      protocol: url.protocol,
      hostname: url.hostname.replace(/^\[|\]$/g, ''),
      port: url.port || undefined,
      path: url.pathname + url.search,
      method: o.method,
      headers: { 'user-agent': USER_AGENT, 'accept-encoding': 'gzip, deflate, br', ...o.headers },
      lookup: pinnedLookup(addresses),
      // Passed through to the socket's connect (Node 20+); @types/node does not list it on a request.
      ...({ autoSelectFamilyAttemptTimeout: CONNECT_ATTEMPT_MS } as object),
      agent: false,
    })
    const timer = setTimeout(() => req.destroy(timedOut()), ms)
    const fail = (e: Error) => { clearTimeout(timer); reject(e instanceof HttpError ? e : new HttpError(`network error: ${networkErrorMessage(e)}`)) }
    req.on('error', fail)
    req.on('response', res => {
      const done = (body: Buffer) => {
        clearTimeout(timer)
        resolve({ status: res.statusCode ?? 0, statusText: res.statusMessage ?? '', headers: res.headers, body, url })
      }
      if ([301, 302, 303, 307, 308].includes(res.statusCode ?? 0) && res.headers.location) { res.resume(); done(Buffer.alloc(0)); return }
      readBody(res, o.maxBytes).then(done, e => { req.destroy(); fail(e) })
    })
    req.end(o.body)
  })
}

function readBody(res: IncomingMessage, maxBytes: number): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const encoding = String(res.headers['content-encoding'] ?? '').trim().toLowerCase()
    let stream: Readable = res
    if (encoding === 'gzip' || encoding === 'x-gzip') stream = res.pipe(createGunzip())
    else if (encoding === 'deflate') stream = res.pipe(createInflate())
    else if (encoding === 'br') stream = res.pipe(createBrotliDecompress())
    const chunks: Buffer[] = []
    let size = 0
    stream.on('data', (chunk: Buffer) => {
      size += chunk.length
      if (size > maxBytes) {
        stream.destroy()
        res.destroy()
        reject(new HttpError(`too large: over ${Math.round(maxBytes / 1048576)} MB`))
        return
      }
      chunks.push(chunk)
    })
    stream.on('end', () => resolve(Buffer.concat(chunks)))
    stream.on('error', e => reject(new HttpError(`network error: ${networkErrorMessage(e)}`)))
    res.on('error', e => reject(new HttpError(`network error: ${networkErrorMessage(e)}`)))
    res.on('aborted', () => reject(new HttpError('network error: the response was cut off')))
  })
}

/**
 * A `fetch` for Defuddle's site extractors (YouTube transcripts, Reddit
 * comments, …), so their requests stay inside the boundary too.
 */
export function guardedFetch(allow: Set<string>, timeLeft: () => number): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url)
    const headers: Record<string, string> = {}
    new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined)).forEach((v, k) => { headers[k] = v })
    const body = typeof init?.body === 'string' ? init.body : undefined
    const res = await request(url, { method: init?.method ?? 'GET', headers, body, timeoutMs: Math.min(15_000, timeLeft()), maxBytes: 10 * 1048576, allow })
    const out = new Headers()
    for (const [k, v] of Object.entries(res.headers)) {
      if (v === undefined || k === 'content-encoding' || k === 'content-length') continue
      for (const one of Array.isArray(v) ? v : [v]) out.append(k, one)
    }
    const nullBody = [101, 204, 205, 304].includes(res.status)
    const response = new Response(nullBody ? null : new Uint8Array(res.body), { status: res.status < 200 || res.status > 599 ? 502 : res.status, headers: out })
    Object.defineProperty(response, 'url', { value: res.url.href })
    return response
  }) as typeof fetch
}
