// One `fetch`: the cache, then fetch → route → extract → render → images →
// measure → publish, all within one deadline. Once the page itself is in
// hand, it is always published; a failure is remembered for a few minutes.
import { execFile } from 'node:child_process'
import { statSync } from 'node:fs'
import { readFile, rm, stat, writeFile } from 'node:fs/promises'
import { delimiter, join } from 'node:path'
import { beginBuild, FAILURE_MEMORY_MS, publish, readFailure, readFresh, rememberFailure, REUSE_MAX_AGE_MS } from './cache.ts'
import { CLIP_DEADLINE_MS, Deadline } from './deadline.ts'
import { countWords, estimateTokens } from './estimate.ts'
import { extractHtml, htmlFrontmatter, markdownWithFrontmatter } from './extract.ts'
import type { Extracted, PageMeta } from './extract.ts'
import { guardedFetch, HttpError, request } from './http.ts'
import type { HttpResponse } from './http.ts'
import { DRAW_LIMITS, drawSvgs } from './draw.ts'
import { downloadImages } from './images.ts'
import type { DrawSvgs, ImageEntry } from './images.ts'
import { entryDir } from './key.ts'
import { buildOutline, splitLines } from './measure.ts'
import type { OutlineEntry, OutlineMode } from './measure.ts'
import { boundaryOf, deniedError, isDenied, RefusedError } from './netguard.ts'
import { findChrome, renderDom, RENDER_LIMITS } from './render.ts'
import type { ServedDocument } from './render.ts'
import { decodeText, route } from './route.ts'
import type { Kind } from './route.ts'

export type { ImageEntry, OutlineEntry }

export type ClipOk = {
  ok: true
  dir: string
  file: string
  text?: string
  kind: Kind
  url: string
  finalUrl: string
  status: number
  contentType: string
  fetchedAt: string
  cached: boolean
  rendered: boolean
  title?: string; site?: string; author?: string; published?: string; description?: string
  words?: number
  bytes: number
  lines?: number
  tokens?: number
  outline?: OutlineEntry[]
  /** Headings left out of `outline` to keep it within 80 entries. */
  outlineOmitted?: number
  images: ImageEntry[]
  /** An SVG fetched by its own URL, drawn: the PNG beside it; or, not drawn, why. */
  png?: string
  notDrawn?: string
  notes: string[]
}
export type ClipError = {
  ok: false
  url: string
  status?: number
  error: string
  bodySnippet?: string
  /** A second fetch will fail the same way: an HTTP 4xx other than 408 and 429, or a refusal. */
  permanent?: true
  /** When the failure happened, on an answer from the failure memory rather than a request. */
  failedAt?: string
}
export type ClipResult = ClipOk | ClipError

export type ClipOptions = { cacheDir: string; refresh?: boolean; env?: NodeJS.ProcessEnv; deadlineMs?: number }

/**
 * A page's fetch: its response's headers within `headersMs`, then its body for
 * as long as bytes keep arriving (no gap of `stallMs`), up to the deadline.
 */
export const FETCH_LIMITS = { headersMs: 30_000, stallMs: 20_000, maxBytes: 50 * 1048576 }
export const PDFTOTEXT_TIMEOUT_MS = 60_000
export const RENDER_MIN_WORDS = 50

const ACCEPT = 'text/markdown;q=1.0, text/html;q=0.9, */*;q=0.8'
const BROWSER_ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'

export async function clip(rawUrl: string, opts: ClipOptions): Promise<ClipResult> {
  const env = opts.env ?? process.env
  const deadline = new Deadline(opts.deadlineMs ?? CLIP_DEADLINE_MS)
  const boundary = boundaryOf(env)
  const fail = (error: string, extra: Partial<ClipError> = {}): ClipError => ({ ok: false, url: rawUrl, ...extra, error })

  let url: URL
  try { url = new URL(rawUrl.trim()) } catch { return fail(`invalid URL: ${rawUrl}`) }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return fail(`unsupported scheme: ${url.protocol} (http and https only)`)
  // Before the cache too: a denied host's saved copy is not handed out either.
  if (isDenied(url.hostname, boundary.deny)) return fail(deniedError(url.hostname).message, { permanent: true })
  const entry = entryDir(opts.cacheDir, url)

  if (!opts.refresh) {
    const meta = await readFresh<ClipOk>(entry, REUSE_MAX_AGE_MS)
    if (meta) {
      // Nor a copy whose page was served from a host denied since it was saved.
      const served = new URL(meta.finalUrl).hostname
      if (isDenied(served, boundary.deny)) return fail(deniedError(served).message, { permanent: true })
      return { ...meta, url: rawUrl, cached: true }
    }
    const failure = await readFailure<ClipError & { failedAt: string }>(entry, FAILURE_MEMORY_MS)
    if (failure) return { ...failure, url: rawUrl }
  }
  // What the site or the network failed is remembered; a refusal is decided again each time, at no cost.
  const failed = async (error: string, extra: Partial<ClipError> = {}): Promise<ClipError> => {
    const result = fail(error, extra)
    await rememberFailure(entry, { ...result, failedAt: new Date().toISOString() })
    return result
  }

  // 1. Fetch.
  const get = (target: URL, accept: string) => request(target, {
    headers: { accept, 'accept-language': 'en-US,en;q=0.9' }, boundary,
    timeoutMs: deadline.remaining(), headersMs: FETCH_LIMITS.headersMs, stallMs: FETCH_LIMITS.stallMs, maxBytes: FETCH_LIMITS.maxBytes,
  })
  let res: HttpResponse
  let httpsFailed: string | undefined
  let fetched = url // the URL the response was asked of: its https form when https first worked
  let accept = ACCEPT
  try {
    ;({ res, target: fetched, httpsFailed } = await fetchHttpsFirst(url, async target => {
      accept = ACCEPT
      const first = await get(target, accept)
      return first.status === 406 ? get(target, accept = BROWSER_ACCEPT) : first
    }, () => deadline.remaining()))
  } catch (e) {
    if (e instanceof RefusedError) return fail(e.message, { permanent: true })
    if (e instanceof HttpError) return failed(e.message)
    throw e
  }
  const siteFetch = guardedFetch(boundary, () => deadline.remaining())
  // 3. Extract, and 4. render when the plain fetch found no content: the result with more words.
  const extractPage = async (html: string, at: string): Promise<HtmlPage> => {
    const notes: string[] = []
    const ex = await extractHtml(html, at, siteFetch)
    if (ex.words < RENDER_MIN_WORDS) {
      const chrome = findChrome(env)
      if ('note' in chrome) notes.push(chrome.note)
      else {
        const out = await renderDom(at, chrome, deadline.limit(RENDER_LIMITS.timeoutMs), boundary)
        const served = 'note' in out ? out : servedPage(out)
        if ('note' in served) notes.push(served.note)
        else {
          // Extracted, and later its images resolved, against the document the browser ended on.
          const again = await extractHtml(served.html, served.url, siteFetch)
          const used = again.words > ex.words
          // Either way the agent is told when what it gets may not be the whole page.
          if (used && served.unsettled) notes.push(served.unsettled)
          else if (Math.max(again.words, ex.words) < RENDER_MIN_WORDS) notes.push(`even rendered, the page holds only ${Math.max(again.words, ex.words)} words; its content may load later than the render waits, or come from an API the page calls`)
          if (used) return { ex: again, url: served.url, rendered: true, notes }
        }
      }
    }
    return { ex, url: at, rendered: false, notes }
  }
  // A 403 is often a bot wall that turns away a client that is not a browser and lets
  // one through (techblog.woowahan.com: 403 to this client, the article to Chromium).
  // The page is the browser's only when the browser was served it with a 2xx, by its
  // own NetLog: a denial page renders to a DOM like any other. Otherwise the 403 stands.
  let walled: { ex: Extracted; url: string; unsettled?: string } | undefined
  if (res.status === 403) {
    const chrome = findChrome(env)
    if (!('note' in chrome)) {
      const out = await renderDom(res.url.href, chrome, deadline.limit(RENDER_LIMITS.timeoutMs), boundary)
      const served = 'note' in out ? undefined : servedPage(out)
      if (served && 'url' in served) {
        const ex = await extractHtml(served.html, served.url, siteFetch)
        if (ex.words >= RENDER_MIN_WORDS) walled = { ex, url: served.url, unsettled: served.unsettled }
      }
    }
  }
  if (res.status >= 400 && !walled) {
    const snippet = snippetOf(res.body, res.headers['content-type'])
    const permanent = res.status < 500 && res.status !== 408 && res.status !== 429
    return failed(statusLine(res), { status: res.status, ...(snippet ? { bodySnippet: snippet } : {}), ...(permanent ? { permanent: true } : {}) })
  }
  const fetchedAt = new Date().toISOString()
  // Where the page saved was served from; a render the browser navigated elsewhere moves it.
  let finalUrl = walled?.url ?? res.url.href
  let contentType = walled ? 'text/html' : String(res.headers['content-type'] ?? '')
  let status = res.status

  // 2. Route. The page is in hand: from here on it is published.
  let r = walled ? route('text/html', Buffer.alloc(0)) : route(contentType, res.body)
  const tmp = await beginBuild(entry)
  try {
    const notes: string[] = []
    let meta: PageMeta = {}
    let words: number | undefined
    let rendered = false
    let images: ImageEntry[] = []
    let textFile: string | undefined // the file lines and the outline are measured over
    let mode: OutlineMode = 'plain'
    const main = join(tmp, r.file)
    let drawnSvg: { png: string } | { notDrawn: string } | undefined
    const draw: DrawSvgs = files => {
      const chrome = findChrome(env)
      if ('note' in chrome) {
        const why = chrome.note.replace(/^rendering unavailable on this machine: /, '')
        return Promise.resolve(new Map(files.map(f => [f, { error: why }])))
      }
      return drawSvgs(files, chrome, deadline.limit(DRAW_LIMITS.timeoutMs), boundary)
    }

    if (r.kind === 'html' || r.kind === 'markdown') {
      let head = ''
      let body = ''
      let page: HtmlPage | undefined
      if (walled) {
        const notes = [`the site refused a plain fetch (HTTP ${res.status}); this is the page as headless Chromium rendered it`]
        page = { ex: walled.ex, url: walled.url, rendered: true, notes: walled.unsettled ? [...notes, walled.unsettled] : notes }
      }
      else if (r.kind === 'html') page = await extractPage(decodeText(res.body, contentType, true), finalUrl)
      else {
        const md = markdownWithFrontmatter(decodeText(res.body, contentType, false), finalUrl, fetchedAt)
        if (md.title) meta.title = md.title
        body = md.text
        // Markdown with no content can be a stub of a page a script draws (bundlephobia
        // answers the markdown Accept with seven words). The HTML page then takes the
        // HTML path, and replaces the stub when it finds over twice the words: one page
        // in two formats counts about the same, a stub a fraction (Defuddle accepts its
        // own retries by the same margin). A page short either way stays the markdown.
        const mdWords = bodyWords(body)
        if (accept === ACCEPT && mdWords < RENDER_MIN_WORDS) {
          const html = await get(fetched, BROWSER_ACCEPT).catch(e => { if (e instanceof RefusedError || e instanceof HttpError) return undefined; throw e })
          const type = String(html?.headers['content-type'] ?? '')
          if (html && html.status < 400 && route(type, html.body).kind === 'html') {
            const alt = await extractPage(decodeText(html.body, type, true), html.url.href)
            if (alt.ex.words > 2 * mdWords) { page = alt; r = route(type, html.body); status = html.status; contentType = type }
            else notes.push(...alt.notes)
          }
        }
      }
      if (page) {
        // Extracted, and its images resolved, against where the page was served from.
        finalUrl = page.url
        rendered = page.rendered
        notes.push(...page.notes)
        meta = page.ex.meta
        words = page.ex.words
        head = htmlFrontmatter(meta, words, finalUrl, fetchedAt)
        body = page.ex.body
      }
      // 5. Images. Their lines are counted in the text as written, frontmatter included.
      const text = head + body
      const withImages = await downloadImages(text, finalUrl, tmp, deadline, boundary, draw)
      images = withImages.images
      await writeFile(main, withImages.markdown)
      textFile = main
      mode = 'markdown'
    } else if (r.kind === 'text') {
      await writeFile(main, decodeText(res.body, contentType, false))
      textFile = main
    } else if (r.kind === 'json') {
      const raw = decodeText(res.body, contentType, false)
      let pretty: string
      try { pretty = JSON.stringify(JSON.parse(raw), null, 2) + '\n' } catch {
        pretty = raw
        notes.push('not valid JSON; saved as served')
      }
      await writeFile(main, pretty)
      textFile = main
    } else if (r.kind === 'pdf') {
      await writeFile(main, res.body)
      const txt = join(tmp, 'page.txt')
      const extracted = await pdfToText(main, txt, env, deadline.limit(PDFTOTEXT_TIMEOUT_MS))
      if (extracted === true) { textFile = txt; mode = 'pdf' } else notes.push(extracted)
    } else {
      await writeFile(main, res.body)
      if (r.kind === 'image' && r.file.endsWith('.svg')) {
        const d = (await draw([main])).get(main)!
        drawnSvg = 'png' in d ? { png: d.png.slice(tmp.length + 1) } : { notDrawn: d.error }
      }
    }

    // Said only when the page did come over plain http, not when http redirected back to https.
    if (httpsFailed !== undefined && finalUrl.startsWith('http:')) notes.unshift(`fetched over plain http: https failed (${httpsFailed.slice(0, 160)})`)

    // 6. Measure, write meta.json, publish.
    const result = {
      ok: true as const, kind: r.kind, url: rawUrl, finalUrl, status, contentType, fetchedAt, cached: false, rendered,
      ...pick(meta), bytes: (await stat(main)).size,
    }
    let measured = {}
    if (textFile) {
      const text = await readFile(textFile, 'utf8')
      if (r.kind === 'markdown') words = bodyWords(text)
      else if (words === undefined) words = countWords(text)
      const { outline, omitted } = buildOutline(text, mode, images.map(i => i.line))
      measured = { words, lines: splitLines(text).length, tokens: estimateTokens(text), outline, ...(omitted ? { outlineOmitted: omitted } : {}) }
    }
    let written: ClipOk | undefined
    await publish(tmp, entry, async dir => {
      written = {
        ...result, dir, file: join(dir, r.file), ...(textFile && textFile !== main ? { text: join(dir, 'page.txt') } : {}),
        ...measured, images,
        ...(drawnSvg ? ('png' in drawnSvg ? { png: join(dir, drawnSvg.png) } : drawnSvg) : {}),
        notes,
      }
      const { cached: _, ...onDisk } = written
      await writeFile(join(tmp, 'meta.json'), JSON.stringify(onDisk, null, 2) + '\n')
    })
    return written!
  } catch (e) {
    await rm(tmp, { recursive: true, force: true }).catch(() => {})
    throw e
  }
}

type HtmlPage = { ex: Extracted; url: string; rendered: boolean; notes: string[] }

/** The words of a markdown file under its frontmatter. */
const bodyWords = (text: string) => countWords(text.replace(/^---\n[\s\S]*?\n---\n/, ''))

/**
 * A render counts as the page only when Chromium's NetLog shows the browser was
 * served its document with a 2xx (`renderDom` gives a document only when the
 * last main-frame response could have become it). A DOM alone cannot tell a
 * page from a denial, an error page, or a navigation that failed.
 */
function servedPage(out: { html: string; document?: ServedDocument; unsettled?: string }): { html: string; url: string; unsettled?: string } | { note: string } {
  const doc = out.document
  if (!doc) return { note: 'rendering not used: the browser was served no page it could show (a failed navigation, or no 2xx document); the plain fetch is kept' }
  if (doc.status < 200 || doc.status >= 300) return { note: `rendering not used: the browser was served HTTP ${doc.status}; the plain fetch is kept` }
  return { html: out.html, url: doc.url, unsettled: out.unsettled }
}

/** The https: form of an http: URL on the default port; none for any other URL. */
export function httpsFirst(url: URL): URL | undefined {
  if (url.protocol !== 'http:' || url.port !== '') return undefined
  const secure = new URL(url.href)
  secure.protocol = 'https:'
  return secure
}

/**
 * The response to `url`, an http: URL on the default port tried over https
 * first, and the URL it was asked of. When https brings no page (an error
 * status, a connection or TLS failure, a timeout, a refusal), the URL is
 * fetched as given, and `httpsFailed` says why. A refusal falls back too: https
 * follows redirects, so it may concern where https led rather than the URL's
 * host, and the http attempt passes the same guard, so a host refused for
 * itself is refused again, at the cost of a lookup. An https download that
 * ran out the time left leaves none for http: its failure stands.
 */
export async function fetchHttpsFirst(url: URL, get: (target: URL) => Promise<HttpResponse>, timeLeft: () => number = () => Infinity): Promise<{ res: HttpResponse; target: URL; httpsFailed?: string }> {
  const secure = httpsFirst(url)
  if (!secure) return { res: await get(url), target: url }
  let httpsFailed: string
  try {
    const res = await get(secure)
    if (res.status < 400) return { res, target: secure }
    httpsFailed = statusLine(res)
  } catch (e) {
    if (!(e instanceof HttpError) && !(e instanceof RefusedError)) throw e
    if (timeLeft() <= 0) throw e
    httpsFailed = e.message
  }
  return { res: await get(url), target: url, httpsFailed }
}

const statusLine = (res: HttpResponse) => `HTTP ${res.status}${res.statusText ? ' ' + res.statusText : ''}`

function pick(meta: PageMeta) {
  const { title, site, author, published, description } = meta
  return Object.fromEntries(Object.entries({ title, site, author, published, description }).filter(([, v]) => v)) as Partial<ClipOk>
}

function snippetOf(body: Buffer, contentType: string | undefined): string | undefined {
  const text = decodeText(body.subarray(0, 2 * 1048576), contentType, true)
    .replace(/<(script|style|noscript|template)\b[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<(script|style)\b[\s\S]*$/i, ' ') // one left open where the cap cut it
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim()
  return text ? text.slice(0, 300) : undefined
}

/** page.txt from `pdftotext -layout`, or the note saying why there is none. */
function pdfToText(pdf: string, txt: string, env: NodeJS.ProcessEnv, timeoutMs: number): Promise<true | string> {
  const bin = (env.PATH ?? '').split(delimiter).filter(Boolean).map(d => join(d, 'pdftotext')).find(p => {
    try { return statSync(p).isFile() } catch { return false }
  })
  if (!bin) return Promise.resolve('no text extracted: pdftotext is not on PATH (install poppler)')
  if (timeoutMs <= 0) return Promise.resolve('no text extracted: the time budget was spent')
  return new Promise(resolve => {
    execFile(bin, ['-layout', '-enc', 'UTF-8', pdf, txt], { timeout: timeoutMs }, async err => {
      // A download that took most of the deadline leaves pdftotext only the rest.
      if (err?.killed) { resolve(`no text extracted: pdftotext did not finish within ${Math.round(timeoutMs / 1000)} s`); return }
      if (err) { resolve(`no text extracted: pdftotext failed (${(err.message.split('\n')[0] ?? '').slice(0, 200)})`); return }
      const text = await readFile(txt, 'utf8').catch(() => '')
      if (text.replace(/\f/g, '').trim()) { resolve(true); return }
      await rm(txt, { force: true })
      resolve('no text extracted: the PDF has no text layer')
    })
  })
}
