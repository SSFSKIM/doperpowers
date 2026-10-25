// The page's images: every image link in the markdown is downloaded into
// assets/ (named by first appearance, extension from the content type) and
// its link rewritten to the file. An image that fails, or is under 1 KiB,
// keeps its remote link, and the image list records why.
import { writeFileSync } from 'node:fs'
import { mkdir, rename, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { request, HttpError, USER_AGENT } from './http.ts'
import { RefusedError } from './netguard.ts'
import { imageExtension, mediaTypeOf, sniff } from './route.ts'
import type { Deadline } from './deadline.ts'

export type ImageEntry = { file?: string; url: string; alt: string; line: number; bytes?: number; error?: string }

export const IMAGE_LIMITS = { concurrency: 6, timeoutMs: 20_000, maxBytes: 15 * 1048576, maxImages: 40, minBytes: 1024 }

// Avif is left out: Read cannot show it, and image CDNs pick a format by Accept.
const IMAGE_ACCEPT = 'image/webp,image/png,image/jpeg,image/gif,image/svg+xml,image/*;q=0.8,*/*;q=0.5'

// [targetStart, targetEnd) is the link target's span in the markdown, angle brackets included.
type Link = { targetStart: number; targetEnd: number; alt: string; target: string; line: number }

const FENCE = /^ {0,3}(`{3,}|~{3,})/
// ![alt](target "title"): the target may hold one level of balanced parentheses.
const IMAGE = /!\[((?:\\.|[^\]\\])*)\]\(\s*(<[^>\n]*>|(?:[^\s()]|\([^\s()]*\))+)(\s+(?:"[^"\n]*"|'[^'\n]*'))?\s*\)/dg

/** Image links outside fenced code, with the line each sits on. */
export function findImageLinks(markdown: string): Link[] {
  const links: Link[] = []
  let offset = 0
  let fence: string | null = null
  const lines = markdown.split('\n')
  lines.forEach((line, i) => {
    const f = FENCE.exec(line)
    if (fence) {
      if (f && f[1][0] === fence[0] && f[1].length >= fence.length && line.trim() === f[1]) fence = null
    } else if (f) fence = f[1]
    else {
      for (const m of line.matchAll(IMAGE)) {
        const target = m[2].startsWith('<') ? m[2].slice(1, -1) : m[2]
        const [targetStart, targetEnd] = m.indices![2]
        links.push({ targetStart: offset + targetStart, targetEnd: offset + targetEnd, alt: m[1].replace(/\\(.)/g, '$1'), target, line: i + 1 })
      }
    }
    offset += line.length + 1
  })
  return links
}

type Download = { file?: string; part?: string; ext?: string; bytes?: number; error?: string }

export async function downloadImages(
  markdown: string, base: string, dir: string, deadline: Deadline, allow: Set<string>,
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
      results.set(url, await downloadOne(url, join(assets, `.part-${k}`), base, deadline, allow, gate))
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

  let out = ''
  let at = 0
  const images: ImageEntry[] = links.map((l, i) => {
    const url = absolute[i]
    const r = results.get(url)!
    // A saved image links to its file; one that was not keeps a remote link, made absolute.
    const target = r.file ?? (url.startsWith('data:') ? markdown.slice(l.targetStart, l.targetEnd) : url)
    out += markdown.slice(at, l.targetStart) + target
    at = l.targetEnd
    const shown = url.startsWith('data:') ? url.slice(0, 40) + '…' : url
    return { ...(r.file ? { file: r.file, bytes: r.bytes } : {}), url: shown, alt: l.alt, line: l.line, ...(r.error ? { error: r.error } : {}) }
  })
  out += markdown.slice(at)
  return { markdown: out, images }
}

async function downloadOne(url: string, part: string, referer: string, deadline: Deadline, allow: Set<string>, gate: { closed: boolean }): Promise<Download> {
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
        headers: { accept: IMAGE_ACCEPT, referer, 'user-agent': USER_AGENT }, timeoutMs, maxBytes: IMAGE_LIMITS.maxBytes, allow,
      })
      if (res.status >= 400) return { error: `HTTP ${res.status}` }
      mediaType = mediaTypeOf(res.headers['content-type'])
      body = res.body
      if (!imageExtension(mediaType)) mediaType = sniff(body)
    }
  } catch (e) {
    if (e instanceof RefusedError) return { error: 'refused: non-public address' }
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
