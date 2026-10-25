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
import type { Deadline } from './deadline.ts'
import type { Drawn } from './draw.ts'

/**
 * A saved SVG drawn as a PNG has the PNG as its `file` and the SVG as `svg`; one
 * not drawn keeps the SVG as its `file`, and `notDrawn` says why.
 */
export type ImageEntry = { file?: string; url: string; alt: string; line: number; bytes?: number; error?: string; svg?: string; notDrawn?: string }

/** Draws SVG files (absolute paths) as PNGs beside them: `drawSvgs` in the clipper. */
export type DrawSvgs = (files: string[]) => Promise<Map<string, Drawn>>

export const IMAGE_LIMITS = { concurrency: 6, timeoutMs: 20_000, maxBytes: 15 * 1048576, maxImages: 40, minBytes: 1024 }

// Avif is left out: Read cannot show it, and image CDNs pick a format by Accept.
const IMAGE_ACCEPT = 'image/webp,image/png,image/jpeg,image/gif,image/svg+xml,image/*;q=0.8,*/*;q=0.5'

// An image as written: [start, end) is the span a rewrite replaces, and
// `rewrite` gives that span's new text for a new target. An inline image
// replaces only its target (its title stays); a reference image becomes an
// inline one in place, leaving its definition to any links that share it.
type Link = { start: number; end: number; alt: string; target: string; line: number; rewrite: (target: string) => string }

const FENCE = /^ {0,3}(`{3,}|~{3,})/
// ![alt](target "title"), the target holding at most one level of balanced
// parentheses; else ![alt][label], ![label][] or ![label], through a definition.
const IMAGE = /!\[((?:\\.|[^\]\\])*)\](?:\(\s*(<[^>\n]*>|(?:[^\s()]|\([^\s()]*\))+)(\s+(?:"[^"\n]*"|'[^'\n]*'))?\s*\)|\[((?:\\.|[^\]\\])*)\])?/dg
const DEFINITION = /^ {0,3}\[((?:\\.|[^\]\\])+)\]:[ \t]*(<[^>\n]*>|\S+)(?:[ \t]+(?:"[^"\n]*"|'[^'\n]*'|\([^)\n]*\)))?[ \t]*$/

const normalizeLabel = (label: string) => label.trim().replace(/\s+/g, ' ').toLowerCase()
const unbracket = (t: string) => (t.startsWith('<') && t.endsWith('>') ? t.slice(1, -1) : t)
const destination = (t: string) => (/[\s()<>]/.test(t) ? `<${t}>` : t)

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

/** Image links where they render: not in fenced or inline code, not escaped. */
export function findImageLinks(markdown: string): Link[] {
  const lines = proseLines(markdown)
  const definitions = new Map<string, string>()
  for (const { text } of lines) {
    const d = DEFINITION.exec(text)
    if (d && !definitions.has(normalizeLabel(d[1]))) definitions.set(normalizeLabel(d[1]), unbracket(d[2]))
  }
  const links: Link[] = []
  for (const { text, offset, line } of lines) {
    if (DEFINITION.test(text)) continue
    const code = codeSpans(text)
    for (const m of text.matchAll(IMAGE)) {
      if (escaped(text, m.index) || code.some(([s, e]) => m.index >= s && m.index < e)) continue
      const rawAlt = m[1]
      const alt = rawAlt.replace(/\\(.)/g, '$1')
      if (m[2] !== undefined) {
        const [s, e] = m.indices![2]
        links.push({ start: offset + s, end: offset + e, alt, target: unbracket(m[2]), line, rewrite: t => t })
        continue
      }
      // A reference: ![alt][label], or ![label][] and ![label], whose label is the alt.
      if (text[m.index + m[0].length] === '(') continue
      const target = definitions.get(normalizeLabel(m[4] || rawAlt))
      if (target === undefined) continue
      links.push({ start: offset + m.index, end: offset + m.index + m[0].length, alt, target, line, rewrite: t => `![${rawAlt}](${destination(t)})` })
    }
  }
  return links
}

type Download = { file?: string; part?: string; ext?: string; bytes?: number; error?: string; svg?: string; notDrawn?: string }

export async function downloadImages(
  markdown: string, base: string, dir: string, deadline: Deadline, boundary: Boundary, draw?: DrawSvgs,
): Promise<{ markdown: string; images: ImageEntry[] }> {
  const links = findImageLinks(markdown)
  const unique: string[] = []
  const absolute = links.map(l => {
    let url: string
    try { url = new URL(l.target, base).href } catch { url = l.target }
    if (!unique.includes(url)) unique.push(url)
    return url
  })
  const results = new Map<string, Download>()
  const queue = unique.slice(0, IMAGE_LIMITS.maxImages)
  for (const url of unique.slice(IMAGE_LIMITS.maxImages)) results.set(url, { error: `not downloaded: over the ${IMAGE_LIMITS.maxImages}-image limit` })
  const assets = join(dir, 'assets')
  if (queue.length) await mkdir(assets, { recursive: true })

  // Downloads land in part files. Once the budget closes nothing more is
  // written (each write is synchronous after the check), so a download the
  // deadline abandoned cannot leave a file in a published generation.
  const gate = { closed: false }
  const budget = new Promise<void>(resolve => { setTimeout(resolve, deadline.remaining()).unref() })
  let next = 0
  const worker = async () => {
    while (next < queue.length && !deadline.expired()) {
      const k = next++
      const url = queue[k]
      results.set(url, await downloadOne(url, join(assets, `.part-${k}`), base, deadline, boundary, gate))
    }
  }
  await Promise.race([Promise.all(Array.from({ length: IMAGE_LIMITS.concurrency }, worker)), budget])
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

async function downloadOne(url: string, part: string, page: string, deadline: Deadline, boundary: Boundary, gate: { closed: boolean }): Promise<Download> {
  let body: Buffer
  let mediaType: string
  try {
    if (url.startsWith('data:')) {
      ;({ body, mediaType } = decodeDataUri(url))
    } else {
      const parsed = new URL(url)
      const timeoutMs = deadline.limit(IMAGE_LIMITS.timeoutMs)
      if (timeoutMs <= 0) return { error: 'not downloaded: time budget' }
      const res = await request(parsed, {
        headers: { accept: IMAGE_ACCEPT, 'user-agent': USER_AGENT }, referrer: page, timeoutMs, maxBytes: IMAGE_LIMITS.maxBytes, boundary,
      })
      if (res.status >= 400) return { error: `HTTP ${res.status}` }
      mediaType = mediaTypeOf(res.headers['content-type'])
      body = res.body
      if (!imageExtension(mediaType)) mediaType = sniff(body)
    }
  } catch (e) {
    if (e instanceof RefusedError) return { error: `refused: ${e.brief}` }
    if (e instanceof HttpError && e.timedOut && deadline.expired()) return { error: 'not downloaded: time budget' }
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
