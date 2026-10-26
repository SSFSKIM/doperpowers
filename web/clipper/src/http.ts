// HTTP requests inside the network boundary. Node's own `http`/`https` take a
// connection `lookup`, which pins each connection to the addresses the guard
// checked; the global `fetch` takes one only through the undici package.
import http from 'node:http'
import https from 'node:https'
import type { IncomingHttpHeaders, IncomingMessage } from 'node:http'
import { createBrotliDecompress, createGunzip, createInflate } from 'node:zlib'
import type { Readable } from 'node:stream'
import { pinnedLookup, RefusedError, resolveChecked } from './netguard.ts'
import type { Address, Boundary } from './netguard.ts'

export const USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36'
export const MAX_REDIRECTS = 10
/**
 * How long one connection attempt may take before Node tries the host's next
 * address. Node's default, 250 ms, drops a connection to a far host while it is
 * still being made; with the other address family unreachable, every attempt
 * then fails (archive.apache.org from Seoul: 4 of 12 downloads, 2026-10-25).
 */
export const CONNECT_ATTEMPT_MS = 2500

/**
 * A failure's text: an AggregateError (every address failed) names each address
 * and its code, and an OpenSSL error only its reason.
 */
export function networkErrorMessage(e: unknown): string {
  if (e instanceof AggregateError && e.errors.length > 0) {
    const each = e.errors.map(x => {
      const { address, code } = x as { address?: string; code?: string }
      return [address, code].filter(Boolean).join(' ') || String((x as Error)?.message ?? x)
    })
    return `could not connect: ${each.join(', ')}`
  }
  if (e instanceof Error) {
    // `write EPROTO 80A1…:error:0A000410:SSL routines:ssl3_read_bytes:ssl/tls alert handshake failure:../deps/…`
    const tls = /error:[0-9A-F]+:[^:]*:[^:]*:([^:]+):/.exec(e.message)
    if (tls) return `TLS failed: ${tls[1]}`
    return e.message || String((e as { code?: string }).code ?? e.name)
  }
  return String(e)
}

/** A request that failed on the way: the network, a timeout, a size limit. */
export class HttpError extends Error {
  readonly timedOut: boolean
  /**
   * No response came at all: the name did not resolve, no connection was made
   * or it closed unanswered, or no headers came within the time. A host that
   * answered with any status, or began a body, did answer.
   */
  readonly unanswered: boolean
  /** The URL whose request failed: a redirect's target when the request had followed one. */
  at?: URL

  constructor(message: string, timedOut = false, unanswered = false) {
    super(message)
    this.timedOut = timedOut
    this.unanswered = unanswered
    this.name = 'HttpError'
  }
}

export type HttpResponse = { status: number; statusText: string; headers: IncomingHttpHeaders; body: Buffer; url: URL }

export type RequestOptions = {
  method?: string
  headers?: Record<string, string>
  body?: Buffer | string
  /** The whole request's time: every hop, the headers and the body. */
  timeoutMs: number
  /** The time to the final response's headers (every hop's lookup, connection and headers), when less. */
  headersMs?: number
  /** The longest the body may go with no bytes arriving. A body still arriving runs on to `timeoutMs`. */
  stallMs?: number
  maxBytes: number
  boundary: Boundary
  /** The page the request is made for; each hop gets the Referer `referrerFor` allows. */
  referrer?: string
}

/**
 * The Referer a browser's default policy (strict-origin-when-cross-origin)
 * sends from `page` to `target`: the page's URL to its own origin, the bare
 * origin to another, nothing from HTTPS to HTTP. Never a fragment or
 * credentials. A page URL can carry a token, and image hosts are third parties.
 */
export function referrerFor(page: string, target: URL): string | undefined {
  let from: URL
  try { from = new URL(page) } catch { return undefined }
  if (from.protocol !== 'http:' && from.protocol !== 'https:') return undefined
  if (from.protocol === 'https:' && target.protocol !== 'https:') return undefined
  from.hash = ''
  from.username = ''
  from.password = ''
  return from.origin === target.origin ? from.href : from.origin + '/'
}

/**
 * One request, following redirects (each hop checked), within its time limits:
 * `headersMs` to the final response's headers, then the body for as long as
 * bytes keep arriving (no gap of `stallMs`), the whole within `timeoutMs`.
 */
export async function request(start: URL, o: RequestOptions): Promise<HttpResponse> {
  const started = Date.now()
  const headersMs = o.headersMs !== undefined && o.headersMs < o.timeoutMs ? o.headersMs : undefined
  const limits: Limits = {
    timeLeft: () => Math.max(0, started + o.timeoutMs - Date.now()),
    headersLeft: () => Math.max(0, started + (headersMs ?? o.timeoutMs) - Date.now()),
    noHeaders: () => new HttpError(headersMs === undefined ? `timed out after ${seconds(o.timeoutMs)} s` : `no response within ${seconds(headersMs)} s`, true, true),
    timeoutMs: o.timeoutMs,
    stallMs: o.stallMs,
  }
  let url = start
  let method = o.method ?? 'GET'
  let body = o.body
  // A Referer given as a header is held to the same policy as `referrer`, hop by hop.
  const headers = { ...o.headers }
  let referrer = o.referrer
  for (const name of Object.keys(headers)) {
    if (name.toLowerCase() === 'referer') { referrer ??= headers[name]; delete headers[name] }
  }
  for (let hop = 0; ; hop++) {
    if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new HttpError(`unsupported scheme: ${url.protocol}`)
    const port = Number(url.port) || (url.protocol === 'https:' ? 443 : 80)
    const at = url
    const failedAt = (e: unknown) => {
      if (e instanceof HttpError) e.at ??= at
      return e
    }
    const addresses = await withTimeout(resolveChecked(url.hostname, port, { boundary: o.boundary }), limits.headersLeft(), limits.noHeaders)
      .catch(e => { throw failedAt(asTransportError(e)) })
    const referer = referrer === undefined ? undefined : referrerFor(referrer, url)
    const res = await once(url, addresses, { ...o, headers: referer ? { ...headers, referer } : headers, method, body }, limits)
      .catch(e => { throw failedAt(e) })
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

/** One request's clock: what is left of its whole time and of its time to the headers. */
type Limits = {
  timeLeft: () => number
  headersLeft: () => number
  noHeaders: () => HttpError
  timeoutMs: number
  stallMs?: number
}

const seconds = (ms: number) => Math.round(ms / 1000)
const amount = (bytes: number) =>
  bytes < 1024 ? `${bytes} bytes` : bytes < 1048576 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1048576).toFixed(1)} MB`

/**
 * The transport boundary: a refusal and an HttpError pass as they are, and any
 * other failure on the way to a connection (a name that does not resolve, a
 * resolver error) becomes a network error, which a fetch reports as a result.
 */
function asTransportError(e: unknown): Error {
  if (e instanceof RefusedError || e instanceof HttpError) return e
  return new HttpError(`network error: ${networkErrorMessage(e)}`, false, true)
}

function withTimeout<T>(p: Promise<T>, ms: number, error: () => Error): Promise<T> {
  let timer: NodeJS.Timeout
  return Promise.race([p, new Promise<never>((_, reject) => { timer = setTimeout(() => reject(error()), ms) })]).finally(() => clearTimeout(timer))
}

function once(url: URL, addresses: Address[], o: RequestOptions & { method: string }, limits: Limits): Promise<HttpResponse> {
  return new Promise((resolve, reject) => {
    const headersMs = limits.headersLeft()
    if (headersMs <= 0) { reject(limits.noHeaders()); return }
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
    const timers: NodeJS.Timeout[] = []
    let over = false
    let answered = false
    const end = () => { over = true; for (const t of timers) clearTimeout(t) }
    const fail = (e: Error) => { end(); reject(e instanceof HttpError ? e : new HttpError(`network error: ${networkErrorMessage(e)}`, false, !answered)) }
    // A limit that runs out fails the request with its own reason, before the teardown raises another.
    const abort = (e: HttpError) => { fail(e); req.destroy() }
    timers.push(setTimeout(() => abort(limits.noHeaders()), headersMs))
    req.on('error', fail)
    req.on('response', res => {
      answered = true
      clearTimeout(timers[0])
      const done = (body: Buffer) => {
        end()
        resolve({ status: res.statusCode ?? 0, statusText: res.statusMessage ?? '', headers: res.headers, body, url })
      }
      if ([301, 302, 303, 307, 308].includes(res.statusCode ?? 0) && res.headers.location) { res.resume(); done(Buffer.alloc(0)); return }
      // The body runs on to the request's whole time, unless no bytes arrive for `stallMs`.
      const length = Number(res.headers['content-length']) || 0
      let got = 0
      const progress = () => (length ? `${amount(got)} of ${amount(length)}` : amount(got))
      timers.push(setTimeout(() => abort(new HttpError(`timed out after ${seconds(limits.timeoutMs)} s with ${progress()} received`, true)), limits.timeLeft()))
      const stallMs = limits.stallMs
      const stall = stallMs ? setTimeout(() => abort(new HttpError(`stalled: no data for ${seconds(stallMs)} s after ${progress()}`, true)), stallMs) : undefined
      if (stall) timers.push(stall)
      res.on('data', (chunk: Buffer) => {
        got += chunk.length
        if (!over) stall?.refresh()
      })
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
export function guardedFetch(boundary: Boundary, timeLeft: () => number): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url)
    const headers: Record<string, string> = {}
    new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined)).forEach((v, k) => { headers[k] = v })
    const body = typeof init?.body === 'string' ? init.body : undefined
    const res = await request(url, { method: init?.method ?? 'GET', headers, body, timeoutMs: Math.min(15_000, timeLeft()), maxBytes: 10 * 1048576, boundary })
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
