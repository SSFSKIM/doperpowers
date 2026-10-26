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
// A link is read a step at a time, by loops over patterns that repeat only a character
// class (V8 keeps no backtrack entry for those). A pattern that repeats a group keeps an
// entry per repetition, and some millions exhaust V8's stack: the match throws RangeError
// and the fetch fails, as an inline image's data: URI over about 6 MB did (board #145).
//
// A label's (or alt's) characters: a run of characters but `]` and a backslash, or a
// backslash and the character after it. A label runs to the first `]` not escaped.
const LABEL_STEP = /[^\]\\]+|\\./y
// A destination's characters, one way only: a run of characters but a space, a
// parenthesis or a backslash; a backslash and the punctuation it escapes; a backslash
// before anything else. Readings that overlapped gave a destination that cannot close
// 2^n ways to fail (28 escape pairs: 9 s).
const DESTINATION_STEP = new RegExp(String.raw`[^\s()\\]+|\\${PUNCTUATION}?`, 'y')
const SPACES = /\s*/y
// What follows a destination: a title, if any, and the `)` that closes the link.
const CLOSE = /(?:\s+(?:"[^"\n]*"|'[^'\n]*'))?\s*\)/y
// A definition, `[label]: destination "title"`: its `[`, and what follows the label's `]`.
const DEFINITION_OPEN = /^ {0,3}\[/
const DEFINITION_REST = /:[ \t]*(<[^>\n]*>|\S+)(?:[ \t]+(?:"[^"\n]*"|'[^'\n]*'|\([^)\n]*\)))?[ \t]*$/y

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
  // Each run's next run of the same length, found in one pass from the end.
  const next: number[] = []
  const later = new Map<number, number>()
  for (let j = runs.length - 1; j >= 0; j--) {
    next[j] = later.get(runs[j][0].length) ?? -1
    later.set(runs[j][0].length, j)
  }
  for (let i = 0; i < runs.length; i++) {
    const close = next[i]
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

/** Where a run of `step`s from `at` stops. */
function steps(step: RegExp, line: string, at: number): number {
  for (step.lastIndex = at; step.test(line); ) at = step.lastIndex
  return at
}

/** A definition line's label and destination as written, or none for any other line. */
function definitionOf(line: string): { label: string; destination: string } | undefined {
  const open = DEFINITION_OPEN.exec(line)
  if (!open) return undefined
  const start = open[0].length
  const end = steps(LABEL_STEP, line, start)
  if (end === start || line[end] !== ']') return undefined
  DEFINITION_REST.lastIndex = end + 1
  const rest = DEFINITION_REST.exec(line)
  return rest ? { label: line.slice(start, end), destination: rest[1] } : undefined
}

/**
 * An image notation as written: `![alt]`, then an inline image's destination
 * ([start, end) in the line) and its `)`, or a `[label]`, or nothing. [index, end) is
 * the whole notation; an inline image that does not close is its `![alt]` alone.
 */
type Notation = { index: number; end: number; alt: string; destination?: [number, number]; label?: string }

/**
 * The image notations on a line, in order, as one pattern matched them before board
 * #145. Each `![` costs what it reads: a label that starts inside one already read ends
 * where that one did, and the next `>` is looked for once, so a line of `![` that never
 * close is read once, not again from each.
 */
function* notations(line: string): Generator<Notation> {
  let label = { from: 0, to: 0 } // the last label read: [from, to)
  const labelEnd = (open: number) => {
    // A `[` the last label read through is a run's character or an escape's second, and
    // what follows it is read the same way to the same stop.
    if (open < label.from || open >= label.to) label = { from: open + 1, to: steps(LABEL_STEP, line, open + 1) }
    return line[label.to] === ']' ? label.to : -1
  }
  let gt = { from: Infinity, at: -1 } // the first `>` at or past `from`, -1 for none
  const angledEnd = (at: number) => {
    if (line[at] !== '<') return -1
    if (at + 1 < gt.from || (gt.at >= 0 && gt.at <= at)) gt = { from: at + 1, at: line.indexOf('>', at + 1) }
    return gt.at < 0 ? -1 : gt.at + 1
  }
  // A destination closes with a title, if any, and `)`.
  const closes = (end: number) => {
    CLOSE.lastIndex = end
    return CLOSE.test(line) ? CLOSE.lastIndex : -1
  }
  // `<…>`, else characters and at most one level of balanced parentheses: [at, end) and the link's end.
  const inline = (at: number): { end: number; close: number } | undefined => {
    const angled = angledEnd(at)
    const angledClose = angled < 0 ? -1 : closes(angled)
    if (angledClose >= 0) return { end: angled, close: angledClose }
    let end = steps(DESTINATION_STEP, line, at)
    while (line[end] === '(') {
      const inner = steps(DESTINATION_STEP, line, end + 1)
      if (line[inner] !== ')') break
      end = steps(DESTINATION_STEP, line, inner + 1)
    }
    const close = end > at ? closes(end) : -1
    return close < 0 ? undefined : { end, close }
  }
  for (let index = line.indexOf('!['); index >= 0; ) {
    const altEnd = labelEnd(index + 1)
    if (altEnd < 0) {
      index = line.indexOf('![', index + 1)
      continue
    }
    const alt = line.slice(index + 2, altEnd)
    let found: Notation = { index, end: altEnd + 1, alt }
    if (line[altEnd + 1] === '(') {
      SPACES.lastIndex = altEnd + 2
      SPACES.test(line)
      const start = SPACES.lastIndex
      const d = inline(start)
      if (d) found = { index, end: d.close, alt, destination: [start, d.end] }
    } else if (line[altEnd + 1] === '[') {
      const end = labelEnd(altEnd + 1)
      if (end >= 0) found = { index, end: end + 1, alt, label: line.slice(altEnd + 2, end) }
    }
    yield found
    index = line.indexOf('![', found.end)
  }
}

/** Image links where they render: not in fenced or inline code, not escaped. */
export function findImageLinks(markdown: string): Link[] {
  const lines = proseLines(markdown)
  const definitions = new Map<string, string>()
  for (const { text } of lines) {
    const d = definitionOf(text)
    if (d && !definitions.has(normalizeLabel(d.label))) definitions.set(normalizeLabel(d.label), literal(unbracket(d.destination)))
  }
  const links: Link[] = []
  for (const { text, offset, line } of lines) {
    if (definitionOf(text)) continue
    const code = codeSpans(text)
    let span = 0 // the first code span not wholly before the notation
    for (const n of notations(text)) {
      while (span < code.length && code[span][1] <= n.index) span++
      if (escaped(text, n.index) || (span < code.length && code[span][0] <= n.index)) continue
      const alt = n.alt.replace(/\\(.)/g, '$1')
      if (n.destination) {
        const [s, e] = n.destination
        links.push({ start: offset + s, end: offset + e, alt, target: literal(unbracket(text.slice(s, e))), line, rewrite: destination })
        continue
      }
      // A reference: ![alt][label], or ![label][] and ![label], whose label is the alt;
      // not one a `(` follows, which is an inline image that does not close, or text.
      if (text[n.end] === '(') continue
      const target = definitions.get(normalizeLabel(n.label || n.alt))
      if (target === undefined) continue
      links.push({ start: offset + n.index, end: offset + n.end, alt, target, line, rewrite: t => `![${n.alt}](${destination(t)})` })
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
