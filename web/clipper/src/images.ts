// The page's images: every image link in the markdown is downloaded into
// assets/ (named by first appearance, extension from the content type) and
// its link rewritten to the file. An image that fails, or is under 1 KiB,
// keeps its remote link, and the image list records why.
import { writeFileSync } from 'node:fs'
import { mkdir, rename, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { request, HttpError, USER_AGENT } from './http.ts'
import { RefusedError } from './netguard.ts'
import type { Boundary } from './netguard.ts'
import { imageExtension, mediaTypeOf, sniff } from './route.ts'
import { Deadline } from './deadline.ts'
import type { Drawn } from './draw.ts'

/**
 * A saved SVG drawn as a PNG has the PNG as its `file` and the SVG as `svg`; one
 * not drawn keeps the SVG as its `file`, and `notDrawn` says why.
 */
export type ImageEntry = { file?: string; url: string; alt: string; line: number; bytes?: number; error?: string; svg?: string; notDrawn?: string }

/** Draws SVG files (absolute paths) as PNGs beside them: `drawSvgs` in the clipper. */
export type DrawSvgs = (files: string[]) => Promise<Map<string, Drawn>>

/**
 * Each image's time is `timeoutMs`; a page's images together have `totalMs`
 * from the first download (and never past the fetch's deadline).
 */
export const IMAGE_LIMITS = { concurrency: 6, timeoutMs: 20_000, totalMs: 30_000, maxBytes: 15 * 1048576, maxImages: 40, minBytes: 1024 }

// Avif is left out: Read cannot show it, and image CDNs pick a format by Accept.
const IMAGE_ACCEPT = 'image/webp,image/png,image/jpeg,image/gif,image/svg+xml,image/*;q=0.8,*/*;q=0.5'

// An image as written: [start, end) is the span a rewrite replaces, and
// `rewrite` gives that span's new text for a new target. An inline image
// replaces only its target (its title stays); a reference image becomes an
// inline one in place, leaving its definition to any links that share it.
type Link = { start: number; end: number; alt: string; target: string; line: number; rewrite: (target: string) => string }

const FENCE = /^ {0,3}(`{3,}|~{3,})/
const PUNCTUATION = '[!-/:-@[-`{-~]'
// V8 keeps a backtrack entry for each repetition of a group in a pattern (a character
// class under `*` or `+` keeps none), and some 8.4 million exhaust its stack: the match
// throws RangeError and the fetch fails, as an inline image's data: URI over about 6 MB
// did. So nothing here repeats a group per character: a label (or alt) runs to the
// first `]` not escaped, its group repeated per backslash, and a destination is read
// by a loop.
const LABEL = String.raw`[^\]\\]*(?:\\.[^\]\\]*)*`
// ![alt], then an inline image's `(`, its destination read on by `inlineDestination`;
// else ![alt][label], ![label][] or ![label], through a definition.
const IMAGE = new RegExp(String.raw`!\[(${LABEL})\](?:(\(\s*)|\[(${LABEL})\])?`, 'g')
const DEFINITION = new RegExp(String.raw`^ {0,3}\[((?!\])${LABEL})\]:[ \t]*(<[^>\n]*>|\S+)(?:[ \t]+(?:"[^"\n]*"|'[^'\n]*'|\([^)\n]*\)))?[ \t]*$`)
// A destination's characters, a step at a time and one way only: a run of characters
// but a space, a parenthesis or a backslash; a backslash and the punctuation it
// escapes; a backslash before anything else. Readings that overlapped gave a
// destination that cannot close 2^n ways to fail (28 escape pairs: 9 s).
const STEP = new RegExp(String.raw`[^\s()\\]+|\\${PUNCTUATION}?`, 'y')
const ANGLED = /<[^>\n]*>/y
// What follows a destination: a title, if any, and the `)` that closes the link.
const CLOSE = /(?:\s+(?:"[^"\n]*"|'[^'\n]*'))?\s*\)/y

const normalizeLabel = (label: string) => label.trim().replace(/\s+/g, ' ').toLowerCase()
const unbracket = (t: string) => (t.startsWith('<') && t.endsWith('>') ? t.slice(1, -1) : t)

/**
 * A destination as markdown reads it: a backslash before punctuation is that
 * character, and `&amp;` is `&` (Defuddle writes `chart_\(1\).png`, and `&amp;`
 * before an `&` that would read as an entity). Resolved as written, `\(` is a
 * path separator to the URL parser.
 */
const ESCAPE = new RegExp(String.raw`\\(${PUNCTUATION})|&amp;`, 'g')
const literal = (t: string) => t.replace(ESCAPE, (_, c?: string) => c ?? '&')

/** A target written as a destination that reads back as the same target: the inverse of `literal`. */
function destination(t: string): string {
  const escaped = t.replace(/[\\<>]/g, '\\$&').replace(/&(?=#\d+;|#x[\da-f]+;|[a-z][\da-z]*;)/gi, '&amp;')
  return /[\s()]/.test(t) ? `<${escaped}>` : escaped
}

/** The lines outside fenced code, each with its offset in the markdown. */
function proseLines(markdown: string): { text: string; offset: number; line: number }[] {
  const out: { text: string; offset: number; line: number }[] = []
  let offset = 0
  let fence: string | null = null
  markdown.split('\n').forEach((text, i) => {
    const f = FENCE.exec(text)
    if (fence) {
      if (f && f[1][0] === fence[0] && f[1].length >= fence.length && text.trim() === f[1]) fence = null
    } else if (f) fence = f[1]
    else out.push({ text, offset, line: i + 1 })
    offset += text.length + 1
  })
  return out
}

/** The spans of a line's inline code: a backtick run up to the next run of the same length. */
function codeSpans(line: string): [number, number][] {
  const spans: [number, number][] = []
  const runs = [...line.matchAll(/`+/g)].filter(r => !escaped(line, r.index))
  for (let i = 0; i < runs.length; i++) {
    const close = runs.findIndex((r, j) => j > i && r[0].length === runs[i][0].length)
    if (close < 0) continue
    spans.push([runs[i].index, runs[close].index + runs[close][0].length])
    i = close
  }
  return spans
}

/** Whether the character at `at` is escaped by an odd run of backslashes before it. */
function escaped(line: string, at: number): boolean {
  let n = 0
  while (at - n - 1 >= 0 && line[at - n - 1] === '\\') n++
  return n % 2 === 1
}

/** Where the destination characters from `at` end. */
function characters(line: string, at: number): number {
  for (STEP.lastIndex = at; STEP.test(line); ) at = STEP.lastIndex
  return at
}

/**
 * The inline destination from `at` and the end of its link, or none when it does not
 * close: `<…>`, else characters and at most one level of balanced parentheses, then a
 * title, if any, and `)`.
 */
function inlineDestination(line: string, at: number): { end: number; close: number } | undefined {
  const closes = (end: number) => {
    CLOSE.lastIndex = end
    return CLOSE.test(line) ? { end, close: CLOSE.lastIndex } : undefined
  }
  ANGLED.lastIndex = at
  const angled = ANGLED.test(line) ? closes(ANGLED.lastIndex) : undefined
  if (angled) return angled
  let end = characters(line, at)
  while (line[end] === '(') {
    const inner = characters(line, end + 1)
    if (line[inner] !== ')') break
    end = characters(line, inner + 1)
  }
  return end > at ? closes(end) : undefined
}

/** Image links where they render: not in fenced or inline code, not escaped. */
export function findImageLinks(markdown: string): Link[] {
  const lines = proseLines(markdown)
  const definitions = new Map<string, string>()
  for (const { text } of lines) {
    const d = DEFINITION.exec(text)
    if (d && !definitions.has(normalizeLabel(d[1]))) definitions.set(normalizeLabel(d[1]), literal(unbracket(d[2])))
  }
  const links: Link[] = []
  for (const { text, offset, line } of lines) {
    if (DEFINITION.test(text)) continue
    const code = codeSpans(text)
    IMAGE.lastIndex = 0
    for (let m = IMAGE.exec(text); m; m = IMAGE.exec(text)) {
      // An inline image: the link ends past its `)`, and one that does not close is text.
      const start = IMAGE.lastIndex
      let inline: { end: number; close: number } | undefined
      if (m[2] !== undefined) {
        inline = inlineDestination(text, start)
        if (!inline) continue
        IMAGE.lastIndex = inline.close
      }
      if (escaped(text, m.index) || code.some(([s, e]) => m.index >= s && m.index < e)) continue
      const rawAlt = m[1]
      const alt = rawAlt.replace(/\\(.)/g, '$1')
      if (inline) {
        links.push({ start: offset + start, end: offset + inline.end, alt, target: literal(unbracket(text.slice(start, inline.end))), line, rewrite: destination })
        continue
      }
      // A reference: ![alt][label], or ![label][] and ![label], whose label is the alt.
      const target = definitions.get(normalizeLabel(m[3] || rawAlt))
      if (target === undefined) continue
      links.push({ start: offset + m.index, end: offset + m.index + m[0].length, alt, target, line, rewrite: t => `![${rawAlt}](${destination(t)})` })
    }
  }
  return links
}

/** A download's outcome. `silent`: the origin that gave no response (the image's own, or a redirect's target). */
type Download = { file?: string; part?: string; ext?: string; bytes?: number; error?: string; svg?: string; notDrawn?: string; silent?: string }

/** The breaker's key: a URL's origin (scheme, host and port, the scheme's default port left out), none for a data: URI. */
function originOf(url: string | URL): string {
  try {
    const origin = new URL(url).origin
    return origin === 'null' ? '' : origin
  } catch {
    return ''
  }
}

/** Each image link's target made absolute against `base`, in order; one that will not parse stays as written. */
function absoluteTargets(links: Link[], base: string): string[] {
  return links.map(l => {
    try { return new URL(l.target, base).href } catch { return l.target }
  })
}

/**
 * The markdown with every image link's target made absolute, nothing
 * downloaded, and the distinct targets in order of first appearance: the
 * whole page's links (full.md), which an agent fetches one by one.
 */
export function absoluteImageLinks(markdown: string, base: string): { markdown: string; urls: string[] } {
  const links = findImageLinks(markdown)
  const absolute = absoluteTargets(links, base)
  let out = ''
  let at = 0
  links.forEach((l, i) => {
    // A data: URI stays as it was written, as a page.md image not saved does.
    const keep = absolute[i].startsWith('data:')
    out += markdown.slice(at, l.start) + (keep ? markdown.slice(l.start, l.end) : l.rewrite(absolute[i]))
    at = l.end
  })
  out += markdown.slice(at)
  return { markdown: out, urls: [...new Set(absolute)] }
}

export async function downloadImages(
  markdown: string, base: string, dir: string, deadline: Deadline, boundary: Boundary, draw?: DrawSvgs,
): Promise<{ markdown: string; images: ImageEntry[] }> {
  const links = findImageLinks(markdown)
  const absolute = absoluteTargets(links, base)
  const unique = [...new Set(absolute)]
  const results = new Map<string, Download>()
  const queue = unique.slice(0, IMAGE_LIMITS.maxImages)
  for (const url of unique.slice(IMAGE_LIMITS.maxImages)) results.set(url, { error: `not downloaded: over the ${IMAGE_LIMITS.maxImages}-image limit` })
  const assets = join(dir, 'assets')
  if (queue.length) await mkdir(assets, { recursive: true })

  // The page's images share one budget from here, within the fetch's deadline:
  // most pages' images take half a second, and the time went to hosts that never answered.
  const budget = new Deadline(Math.min(IMAGE_LIMITS.totalMs, deadline.remaining()))
  // An origin that did not answer one image is not asked for the rest, at any hop: each would wait its full time.
  const silent = new Set<string>()
  const beforeHop = (hop: URL) => {
    const origin = originOf(hop)
    if (origin && silent.has(origin)) throw new HttpError(`not downloaded: ${origin} did not answer an earlier image`)
  }

  // Downloads land in part files. Once the budget closes nothing more is
  // written (each write is synchronous after the check), so a download the
  // budget abandoned cannot leave a file in a published generation.
  const gate = { closed: false }
  const closed = new Promise<void>(resolve => { setTimeout(resolve, budget.remaining()).unref() })
  let next = 0
  const worker = async () => {
    while (next < queue.length && !budget.expired()) {
      const k = next++
      const url = queue[k]
      const got = await downloadOne(url, join(assets, `.part-${k}`), base, budget, boundary, gate, beforeHop)
      if (got.silent) silent.add(got.silent)
      results.set(url, got)
    }
  }
  await Promise.race([Promise.all(Array.from({ length: IMAGE_LIMITS.concurrency }, worker)), closed])
  gate.closed = true
  for (const url of queue) if (!results.has(url)) results.set(url, { error: 'not downloaded: time budget' })

  // Saved images are numbered by first appearance: assets/01.<ext>, 02, …
  let n = 0
  for (const url of queue) {
    const r = results.get(url)!
    if (!r.part) continue
    const file = `assets/${String(++n).padStart(2, '0')}.${r.ext}`
    await rename(r.part, join(dir, file))
    results.set(url, { file, bytes: r.bytes })
  }
  if (queue.length && n === 0) await rm(assets, { recursive: true, force: true })

  // Read cannot show an SVG: each saved one is drawn as a PNG beside it, which the link then names.
  const svgs = queue.filter(url => results.get(url)!.file?.endsWith('.svg'))
  if (draw && svgs.length) {
    const drawn = await draw(svgs.map(url => join(dir, results.get(url)!.file!)))
    for (const url of svgs) {
      const svg = results.get(url)!
      const d = drawn.get(join(dir, svg.file!)) ?? { error: 'not drawn' }
      results.set(url, 'png' in d
        ? { file: svg.file!.replace(/\.svg$/, '.png'), bytes: d.bytes, svg: svg.file }
        : { ...svg, notDrawn: d.error })
    }
  }

  let out = ''
  let at = 0
  const images: ImageEntry[] = links.map((l, i) => {
    const url = absolute[i]
    const r = results.get(url)!
    // A saved image links to its file; one that was not keeps a remote link,
    // made absolute. A data: URI that was not saved stays as it was written.
    const keep = !r.file && url.startsWith('data:')
    out += markdown.slice(at, l.start) + (keep ? markdown.slice(l.start, l.end) : l.rewrite(r.file ?? url))
    at = l.end
    const shown = url.startsWith('data:') ? url.slice(0, 40) + '…' : url
    return {
      ...(r.file ? { file: r.file, bytes: r.bytes } : {}), url: shown, alt: l.alt, line: l.line,
      ...(r.error ? { error: r.error } : {}), ...(r.svg ? { svg: r.svg } : {}), ...(r.notDrawn ? { notDrawn: r.notDrawn } : {}),
    }
  })
  out += markdown.slice(at)
  return { markdown: out, images }
}

async function downloadOne(
  url: string, part: string, page: string, budget: Deadline, boundary: Boundary, gate: { closed: boolean }, beforeHop: (hop: URL) => void,
): Promise<Download> {
  let body: Buffer
  let mediaType: string
  // The image's own time, or what is left of the page's budget when that is less.
  const timeoutMs = budget.limit(IMAGE_LIMITS.timeoutMs)
  try {
    if (url.startsWith('data:')) {
      ;({ body, mediaType } = decodeDataUri(url))
    } else {
      const parsed = new URL(url)
      if (timeoutMs <= 0) return { error: 'not downloaded: time budget' }
      const res = await request(parsed, {
        headers: { accept: IMAGE_ACCEPT, 'user-agent': USER_AGENT }, referrer: page, timeoutMs, maxBytes: IMAGE_LIMITS.maxBytes, boundary, beforeHop,
      })
      if (res.status >= 400) return { error: `HTTP ${res.status}` }
      mediaType = mediaTypeOf(res.headers['content-type'])
      body = res.body
      if (!imageExtension(mediaType)) mediaType = sniff(body)
    }
  } catch (e) {
    if (e instanceof RefusedError) return { error: `refused: ${e.brief}` }
    // A request whose time was the budget's remainder ran out of budget, though its timer may fire a
    // millisecond before the budget's clock reads zero; it says nothing of its host.
    if (e instanceof HttpError && e.timedOut && (budget.expired() || timeoutMs < IMAGE_LIMITS.timeoutMs)) return { error: 'not downloaded: time budget' }
    // Keyed by where it went unanswered: a host that redirected did answer.
    if (e instanceof HttpError && e.unanswered) return { error: e.message, silent: originOf(e.at ?? url) }
    return { error: e instanceof Error ? e.message : String(e) }
  }
  const ext = imageExtension(mediaType)
  if (!ext) return { error: `not an image (${mediaType || 'no content type'})` }
  if (body.length < IMAGE_LIMITS.minBytes) return { error: `under 1 KiB (${body.length} bytes)` }
  if (gate.closed) return { error: 'not downloaded: time budget' }
  writeFileSync(part, body)
  return { part, ext, bytes: body.length }
}


function decodeDataUri(uri: string): { body: Buffer; mediaType: string } {
  const comma = uri.indexOf(',')
  if (comma < 0) throw new Error('malformed data: URI')
  const head = uri.slice(5, comma)
  const data = uri.slice(comma + 1)
  const base64 = /;base64$/i.test(head)
  return {
    mediaType: mediaTypeOf(head.replace(/;base64$/i, '')) || 'text/plain',
    body: base64 ? Buffer.from(data, 'base64') : Buffer.from(decodeURIComponent(data), 'utf8'),
  }
}
