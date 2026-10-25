// One `fetch`: the cache, then fetch → route → extract → render → images →
// measure → publish, all within one deadline. Once the page itself is in
// hand, it is always published.
import { execFile } from 'node:child_process'
import { statSync } from 'node:fs'
import { readFile, rm, stat, writeFile } from 'node:fs/promises'
import { delimiter, join } from 'node:path'
import { beginBuild, publish, readFresh, REUSE_MAX_AGE_MS } from './cache.ts'
import { CLIP_DEADLINE_MS, Deadline } from './deadline.ts'
import { countWords, estimateTokens } from './estimate.ts'
import { extractHtml, htmlFrontmatter, markdownWithFrontmatter } from './extract.ts'
import type { PageMeta } from './extract.ts'
import { guardedFetch, HttpError, request } from './http.ts'
import { downloadImages } from './images.ts'
import type { ImageEntry } from './images.ts'
import { entryDir } from './key.ts'
import { buildOutline, splitLines } from './measure.ts'
import type { OutlineEntry, OutlineMode } from './measure.ts'
import { allowedHosts, RefusedError } from './netguard.ts'
import { findChrome, renderDom, RENDER_LIMITS } from './render.ts'
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
  notes: string[]
}
export type ClipError = { ok: false; url: string; status?: number; error: string; bodySnippet?: string }
export type ClipResult = ClipOk | ClipError

export type ClipOptions = { cacheDir: string; refresh?: boolean; env?: NodeJS.ProcessEnv; deadlineMs?: number }

export const FETCH_LIMITS = { timeoutMs: 30_000, maxBytes: 50 * 1048576 }
export const PDFTOTEXT_TIMEOUT_MS = 60_000
export const RENDER_MIN_WORDS = 50

const ACCEPT = 'text/markdown;q=1.0, text/html;q=0.9, */*;q=0.8'
const BROWSER_ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'

export async function clip(rawUrl: string, opts: ClipOptions): Promise<ClipResult> {
  const env = opts.env ?? process.env
  const deadline = new Deadline(opts.deadlineMs ?? CLIP_DEADLINE_MS)
  const allow = allowedHosts(env)
  const fail = (error: string, extra: Partial<ClipError> = {}): ClipError => ({ ok: false, url: rawUrl, ...extra, error })

  let url: URL
  try { url = new URL(rawUrl.trim()) } catch { return fail(`invalid URL: ${rawUrl}`) }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return fail(`unsupported scheme: ${url.protocol} (http and https only)`)
  const entry = entryDir(opts.cacheDir, url)

  if (!opts.refresh) {
    const meta = await readFresh<ClipOk>(entry, REUSE_MAX_AGE_MS)
    if (meta) return { ...meta, url: rawUrl, cached: true }
  }

  // 1. Fetch.
  let res
  try {
    const get = (accept: string) => request(url, {
      headers: { accept, 'accept-language': 'en-US,en;q=0.9' }, timeoutMs: deadline.limit(FETCH_LIMITS.timeoutMs), maxBytes: FETCH_LIMITS.maxBytes, allow,
    })
    res = await get(ACCEPT)
    if (res.status === 406) res = await get(BROWSER_ACCEPT)
  } catch (e) {
    if (e instanceof RefusedError || e instanceof HttpError) return fail(e.message)
    throw e
  }
  if (res.status >= 400) {
    const snippet = snippetOf(res.body, res.headers['content-type'])
    return fail(`HTTP ${res.status}${res.statusText ? ' ' + res.statusText : ''}`, { status: res.status, ...(snippet ? { bodySnippet: snippet } : {}) })
  }
  const fetchedAt = new Date().toISOString()
  const finalUrl = res.url.href
  const contentType = String(res.headers['content-type'] ?? '')

  // 2. Route. The page is in hand: from here on it is published.
  const r = route(contentType, res.body)
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

    if (r.kind === 'html' || r.kind === 'markdown') {
      let head = ''
      let body: string
      if (r.kind === 'html') {
        // 3. Extract, and 4. render when the plain fetch found no content.
        const siteFetch = guardedFetch(allow, () => deadline.remaining())
        let ex = await extractHtml(decodeText(res.body, contentType, true), finalUrl, siteFetch)
        if (ex.words < RENDER_MIN_WORDS) {
          const chrome = findChrome(env)
          if ('note' in chrome) notes.push(chrome.note)
          else {
            const out = await renderDom(finalUrl, chrome, deadline.limit(RENDER_LIMITS.timeoutMs), allow)
            if ('note' in out) notes.push(out.note)
            else {
              const again = await extractHtml(out.html, finalUrl, siteFetch)
              if (again.words > ex.words) { ex = again; rendered = true }
            }
          }
        }
        meta = ex.meta
        words = ex.words
        head = htmlFrontmatter(meta, words, finalUrl, fetchedAt)
        body = ex.body
      } else {
        const md = markdownWithFrontmatter(decodeText(res.body, contentType, false), finalUrl, fetchedAt)
        if (md.title) meta.title = md.title
        body = md.text
      }
      // 5. Images. Their lines are counted in the text as written, frontmatter included.
      const text = head + body
      const withImages = await downloadImages(text, finalUrl, tmp, deadline, allow)
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
    }

    // 6. Measure, write meta.json, publish.
    const result = {
      ok: true as const, kind: r.kind, url: rawUrl, finalUrl, status: res.status, contentType, fetchedAt, cached: false, rendered,
      ...pick(meta), bytes: (await stat(main)).size,
    }
    let measured = {}
    if (textFile) {
      const text = await readFile(textFile, 'utf8')
      if (r.kind === 'markdown') words = countWords(text.replace(/^---\n[\s\S]*?\n---\n/, ''))
      else if (words === undefined) words = countWords(text)
      const { outline, omitted } = buildOutline(text, mode, images.map(i => i.line))
      measured = { words, lines: splitLines(text).length, tokens: estimateTokens(text), outline, ...(omitted ? { outlineOmitted: omitted } : {}) }
    }
    let written: ClipOk | undefined
    await publish(tmp, entry, async dir => {
      written = {
        ...result, dir, file: join(dir, r.file), ...(textFile && textFile !== main ? { text: join(dir, 'page.txt') } : {}),
        ...measured, images, notes,
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
      if (err) { resolve(`no text extracted: pdftotext failed (${(err.message.split('\n')[0] ?? '').slice(0, 200)})`); return }
      const text = await readFile(txt, 'utf8').catch(() => '')
      if (text.replace(/\f/g, '').trim()) { resolve(true); return }
      await rm(txt, { force: true })
      resolve('no text extracted: the PDF has no text layer')
    })
  })
}
