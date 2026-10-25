/**
 * The fetch tool's replies (R1–R4 of the design,
 * docs/doperpowers/specs/2026-10-25-web-fetch-design.md): a pure function of
 * the clipper's result (I1) and the summary's outcome, with no `$`, so every
 * shape is tested without an engine.
 */

export type OutlineEntry = { level: number; title: string; line: number; endLine: number; tokens: number; images: number }
export type ImageEntry = { file?: string; url: string; alt: string; line: number; bytes?: number; error?: string }

export type ClipOk = {
  ok: true
  dir: string
  file: string
  text?: string
  kind: 'html' | 'markdown' | 'text' | 'json' | 'pdf' | 'image' | 'binary'
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
  outlineOmitted?: number
  images: ImageEntry[]
  notes: string[]
}
export type ClipError = { ok: false; url: string; status?: number; error: string; bodySnippet?: string }
export type ClipResult = ClipOk | ClipError

/** `clip.mjs numbered`'s header line. */
export type NumberedHeader = { firstLine: number; lastLine: number; totalLines: number; cut?: true }

/** A page whose estimate is at most this comes back whole (R1); a longer one as its outline (R2). */
export const INLINE_MAX_TOKENS = 5000

/** What the summary came to: the model's answer over the lines it read, or why there is none. */
export type Summary =
  | { isAnswered: true; text: string; model: string; header: NumberedHeader }
  | { isAnswered: false; why: string }

export type ReplyContext = {
  /** Milliseconds since the epoch, for the copy's age. */
  now: number
  /** Whether the call asked a question (`prompt`). */
  isAsked: boolean
  /** The summary's outcome, when one was attempted. */
  summary?: Summary
  /** The text file's content, for R1. */
  page?: string
}

/** The file R1–R3 work on: the main file, or `page.txt` beside a PDF; none for a PDF without text, an image or a binary. */
export function textFileOf(r: ClipOk): string | undefined {
  if (r.lines === undefined) return undefined
  if (r.kind === 'pdf') return r.text
  if (r.kind === 'image' || r.kind === 'binary') return undefined
  return r.file
}

/** Whether a reply without an answer gives the page whole (R1) rather than its outline (R2). */
export function isWhole(r: ClipOk): boolean {
  return textFileOf(r) !== undefined && (r.tokens ?? Infinity) <= INLINE_MAX_TOKENS
}

/** The reply to a fetch that succeeded: R1, R2 or R3, or a non-text kind's. */
export function replyFor(r: ClipOk, context: ReplyContext): string {
  const textFile = textFileOf(r)
  if (textFile === undefined) return notAPage(r, context)
  const { summary } = context
  if (summary?.isAnswered) return answered(r, textFile, summary, context.now)
  const lead = summary === undefined ? [] : [`The answer could not be made (${summary.why}), so here is the page itself.`, '']
  const body = isWhole(r) && context.page !== undefined ? whole(r, textFile, context.page, context.now) : outlined(r, textFile, context.now)
  return [...lead, body].join('\n')
}

/** R4: what the model reads as the call's error. */
export function failureReply(r: ClipError): string {
  const lines = [`fetch failed: ${r.url}: ${r.error}`]
  if (r.bodySnippet) lines.push(`The site's response began: "${r.bodySnippet}"`)
  return lines.join('\n')
}

// R1: the header, then the page with its image links absolute, so Read takes them as they stand.
function whole(r: ClipOk, textFile: string, page: string, now: number): string {
  return [...header(r, textFile, now), '', '---', absoluteImages(r, page)].join('\n')
}

// R2: the header, the outline, the images, and how to read a section.
function outlined(r: ClipOk, textFile: string, now: number): string {
  const lines = [...header(r, textFile, now), '', 'Outline (lines · ~tokens · images):', ...outlineLines(r.outline ?? [])]
  if (r.outlineOmitted) {
    lines.push(
      r.kind === 'pdf'
        ? `  (${count(r.outlineOmitted, 'more page')} not listed)`
        : `  (${count(r.outlineOmitted, 'deeper heading')} left out to keep the outline short; Grep the file for "^#" to list them all)`,
    )
  }
  if (hasImages(r)) lines.push(...imageLines(r))
  lines.push('', 'Read the sections you need: Read(file_path, offset=<first line>, limit=<line count>).')
  return lines.join('\n')
}

// R3: the answer, then where it came from.
function answered(r: ClipOk, textFile: string, summary: Extract<Summary, { isAnswered: true }>, now: number): string {
  const { lastLine, totalLines, cut } = summary.header
  const span = cut
    ? `line 1 cut short, of ${number(totalLines)}: the rest was not read`
    : lastLine < totalLines
      ? `lines 1–${number(lastLine)} of ${number(totalLines)}: the rest was not read`
      : `lines 1–${number(lastLine)} of ${number(totalLines)}`
  const facts = [quotedTitle(r), siteOf(r), r.lines !== undefined && count(r.lines, 'line'), hasImages(r) && count(savedImages(r).length, 'image'), `fetched ${age(r, now)}`]
  return [
    summary.text.trim(),
    '',
    `— Answered by ${summary.model} from ${textFile} (${span}). Read cited lines to check them.`,
    joinFacts(facts) + (r.rendered ? ' · rendered in headless Chromium' : ''),
    ...r.notes,
  ].join('\n')
}

// The kinds with no text file: never sent to the model or to the summary.
function notAPage(r: ClipOk, context: ReplyContext): string {
  const lines: string[] = []
  const note = r.notes.find((n) => n.startsWith('no text extracted'))
  if (r.kind === 'pdf') {
    if (context.isAsked) lines.push('Cannot answer from a PDF without its text.')
    lines.push(...header(r, undefined, context.now, note), `Saved ${r.file}`)
    const why = note?.replace(/^no text extracted:\s*/, '') ?? 'none came out'
    lines.push(`No text extracted here (${why}); Read the PDF by page: Read(file_path, pages: "1-5").`)
  } else if (r.kind === 'image') {
    if (context.isAsked) lines.push('A small model cannot read images.')
    lines.push(...header(r, undefined, context.now), `Image saved: ${r.file}. Read it to see it.`)
  } else {
    const type = mediaType(r.contentType)
    if (context.isAsked) lines.push(`Cannot answer from ${/^[aeiou]/i.test(type) ? 'an' : 'a'} ${type} file.`)
    lines.push(...header(r, undefined, context.now), `Saved ${r.file} (${type}, ${size(r.bytes)}); not a page.`)
  }
  return lines.join('\n')
}

/**
 * The header: where the file is (left out for the kinds whose body names it),
 * what the page is, how fresh the copy is, then each clipper note on a line.
 */
function header(r: ClipOk, textFile: string | undefined, now: number, omitNote?: string): string[] {
  const lines: string[] = []
  if (textFile !== undefined) {
    lines.push(`Saved ${textFile}`)
    if (r.kind === 'pdf') lines.push(`The PDF: ${r.file}; Read(file_path, pages: "N-M") shows its pages as rendered.`)
  }
  const pages = r.kind === 'pdf' && r.outline !== undefined ? r.outline.filter((e) => e.level > 0).length + (r.outlineOmitted ?? 0) : undefined
  lines.push(
    joinFacts([
      quotedTitle(r),
      siteOf(r),
      r.kind === 'pdf' && 'PDF',
      pages !== undefined && pages > 0 && count(pages, 'page'),
      r.words !== undefined && count(r.words, 'word'),
      r.lines !== undefined && count(r.lines, 'line'),
      r.tokens !== undefined && `~${tokens(r.tokens)} tokens`,
      hasImages(r) && count(savedImages(r).length, 'image'),
    ]),
  )
  lines.push((r.cached ? `Cached, fetched ${age(r, now)} (refresh: true fetches again)` : 'Fetched now') + (r.rendered ? ' · rendered in headless Chromium' : ''))
  lines.push(...r.notes.filter((n) => n !== omitNote))
  return lines
}

/** The outline, one entry a line: its range, indented by heading level, its size and images. */
function outlineLines(outline: OutlineEntry[]): string[] {
  const headed = outline.filter((e) => e.level > 0)
  const top = headed.length > 0 ? Math.min(...headed.map((e) => e.level)) : 1
  const rows = outline.map((e) => {
    const indent = e.level > 0 ? '  '.repeat(e.level - top) : ''
    const label = e.level > 0 && !/^page \d+$/.test(e.title) ? `${'#'.repeat(e.level)} ${e.title}` : e.title
    return { range: `L${e.line}–${e.endLine}`, label: cut(indent + label, 64), e }
  })
  const rangeWidth = Math.max(0, ...rows.map((row) => row.range.length)) + 2
  const labelWidth = Math.max(0, ...rows.map((row) => row.label.length)) + 2
  return rows.map(({ range, label, e }) => {
    if (e.title === '(frontmatter)') return `  ${range.padEnd(rangeWidth)}${label}`.trimEnd()
    const figure = `${kilo(e.tokens)}${e.images > 0 ? ` · ${count(e.images, 'image')}` : ''}`
    return `  ${range.padEnd(rangeWidth)}${label.padEnd(labelWidth)}${figure}`
  })
}

/** Each image, saved ones by absolute path, unsaved ones by URL with why. */
function imageLines(r: ClipOk): string[] {
  if (r.images.length === 0) return ['Images (Read one to see it): none']
  return [
    'Images (Read one to see it):',
    ...r.images.map((image) => {
      const alt = image.alt.trim() === '' ? '' : `  "${cut(image.alt.trim().replace(/\s+/g, ' '), 100)}"`
      return image.file !== undefined
        ? `  ${absolute(r, image.file)}  L${image.line}${alt}`
        : `  ${image.url}  L${image.line}${alt}  not saved: ${image.error ?? 'unknown'}`
    }),
  ]
}

/** The page with each saved image's link, on the line the clipper recorded, made absolute. */
function absoluteImages(r: ClipOk, page: string): string {
  const saved = savedImages(r)
  if (saved.length === 0) return page
  const lines = page.split('\n')
  for (const image of saved) {
    const at = image.line - 1
    const line = lines[at]
    if (line === undefined) continue
    const target = absolute(r, image.file!)
    const shown = /[\s()<>]/.test(target) ? `<${target}>` : target
    lines[at] = line.split(`](${image.file})`).join(`](${shown})`)
  }
  return lines.join('\n')
}

const savedImages = (r: ClipOk) => r.images.filter((image) => image.file !== undefined)
const hasImages = (r: ClipOk) => r.kind === 'html' || r.kind === 'markdown'
const absolute = (r: ClipOk, file: string) => (file.startsWith('/') ? file : `${r.dir}/${file}`)

function quotedTitle(r: ClipOk): string | false {
  return r.title !== undefined && r.title.trim() !== '' && `"${cut(r.title.trim(), 100)}"`
}

function siteOf(r: ClipOk): string {
  if (r.site !== undefined && r.site.trim() !== '') return r.site.trim()
  try {
    return new URL(r.finalUrl).hostname
  } catch {
    return r.finalUrl
  }
}

const joinFacts = (facts: (string | false | undefined)[]) => facts.filter((f): f is string => typeof f === 'string' && f !== '').join(' · ')

/** How long ago the copy was fetched, for a header: `now` for a fresh fetch. */
function age(r: ClipOk, now: number): string {
  if (!r.cached) return 'now'
  const s = Math.max(0, Math.round((now - Date.parse(r.fetchedAt)) / 1000))
  if (s < 60) return `${s} s ago`
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

const number = (n: number) => n.toLocaleString('en-US')
const count = (n: number, noun: string) => `${number(n)} ${noun}${n === 1 ? '' : 's'}`

/** A header's token figure: `850`, `1.8k`, `13k`. */
function tokens(n: number): string {
  if (n < 1000) return String(n)
  if (n < 10_000) return `${(n / 1000).toFixed(1)}k`
  return `${Math.round(n / 1000)}k`
}

/** An outline's token figure, always in thousands: `0.6k`, `3.1k`, `13k`. */
function kilo(n: number): string {
  if (n < 100) return '<0.1k'
  if (n < 10_000) return `${(n / 1000).toFixed(1)}k`
  return `${Math.round(n / 1000)}k`
}

function size(bytes: number): string {
  if (bytes < 1024) return count(bytes, 'byte')
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const mediaType = (contentType: string) => contentType.split(';')[0]!.trim() || 'unknown'

function cut(text: string, max: number): string {
  const chars = [...text]
  return chars.length <= max ? text : `${chars.slice(0, max - 1).join('')}…`
}
