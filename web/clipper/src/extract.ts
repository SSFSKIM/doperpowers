// HTML to clipper-shaped markdown: Defuddle (the extraction Obsidian Web
// Clipper is built on) over a linkedom document, with the frontmatter
// Defuddle's --frontmatter mode writes, plus `fetched`.
import { Defuddle, DefuddleClass } from 'defuddle/node'
// Not in Defuddle's package exports, so named by path; the same module defuddle/node converts with.
import { createMarkdownContent } from '../node_modules/defuddle/dist/markdown.js'
import { parseHTML } from 'linkedom'
import { randomBytes } from 'node:crypto'
import { findHeadings, splitLines } from './measure.ts'

export type PageMeta = { title?: string; author?: string; site?: string; published?: string; description?: string; domain?: string; language?: string }
export type Extracted = { body: string; meta: PageMeta; words: number }

export async function extractHtml(html: string, url: string, siteFetch: typeof fetch): Promise<Extracted> {
  const { doc, restore } = prepare(html, url)
  const r = await Defuddle(doc, url, { markdown: true, fetch: siteFetch })
  const meta: PageMeta = {}
  for (const k of ['title', 'author', 'site', 'published', 'description', 'domain', 'language'] as const) {
    const v = typeof r[k] === 'string' ? restore(unshield(r[k])).trim() : ''
    if (v) meta[k] = v
  }
  return { body: tidyMarkdown(restore(unshield(r.content ?? ''))), meta, words: r.wordCount ?? 0 }
}

/**
 * The whole page (full.md): the same document, parsed afresh since Defuddle
 * changes the one it reads, converted from its <body> with Defuddle's removal
 * passes off, so a sidebar or a gallery the article leaves out is kept, in the
 * page's order. Hidden elements still go: kept, they add only language pickers
 * and menus. It makes no request: the async extractors stay off (a YouTube
 * page's transcript is page.md's already).
 *
 * Defuddle reads `contentSelector` only after two ways of its own to the
 * article, and both are taken away here:
 * - a schema.org `articleBody` or `text` (JSON-LD) trades the body for the
 *   element holding that text, or for the text itself: the fresh document's
 *   JSON-LD goes (page.md's frontmatter has the metadata already);
 * - a site extractor (Wikipedia's `#mw-content-text`, GitHub's issues, …)
 *   answers before the selector is read: the flag Defuddle holds while an
 *   extractor's own selector runs keeps them out. It is a private field of
 *   defuddle 0.19.6, pinned; the absence check makes a version without it
 *   fail here (full.md not saved, with a note) and in the tests, not quietly
 *   give the article.
 */
export function extractFull(html: string, url: string): { body: string; words: number } {
  const { doc, restore } = prepare(html, url)
  for (const script of Array.from(doc.querySelectorAll('script'))) {
    if (/ld\+json/i.test(script.getAttribute('type') ?? '')) script.remove()
  }
  const defuddle = new DefuddleClass(doc, {
    url,
    useAsync: false,
    contentSelector: 'body',
    removeExactSelectors: false,
    removePartialSelectors: false,
    removeLowScoring: false,
    removeContentPatterns: false,
    removeHiddenElements: true,
  })
  const internals = defuddle as unknown as { _inExtractorPipelineRun?: boolean }
  if (internals._inExtractorPipelineRun !== false) throw new Error('this Defuddle has no flag to keep its site extractors out')
  internals._inExtractorPipelineRun = true
  const r = defuddle.parse()
  return { body: tidyMarkdown(restore(unshield(createMarkdownContent(r.content ?? '', url)))), words: r.wordCount ?? 0 }
}

/**
 * The document Defuddle reads: parsed, polyfilled as Defuddle polyfills its
 * own, and through the clipper's pre-passes; with what puts back, in text
 * made from it, the inline images' payloads it stands in for.
 */
function prepare(html: string, url: string): { doc: Document; restore: (text: string) => string } {
  const doc = parseDocument(html)
  // The polyfills Defuddle applies to a linkedom document of its own.
  const loose = doc as unknown as { URL: string; styleSheets?: unknown; defaultView: { getComputedStyle?: unknown } | null }
  if (!loose.styleSheets) loose.styleSheets = []
  if (loose.defaultView && !loose.defaultView.getComputedStyle) loose.defaultView.getComputedStyle = () => ({ display: '' })
  loose.URL = url
  markWrapperLanguages(doc as unknown as Document)
  keepNoscriptImages(doc as unknown as Document)
  keepDatesAsData(doc as unknown as Document)
  // Last, so the images a <noscript> gave way to are covered too.
  const restore = standInForPayloads(doc as unknown as Document, html)
  return { doc: doc as unknown as Document, restore }
}

// Defuddle reads a srcset with /(.+?)\s+(\d+(?:\.\d+)?[wx])/g, which tries each
// position of an entry without a width against all the rest of it: time in the
// square of the entry's length. A URL is short; an inline image's base64 payload is
// not, and hothardware's <picture>, one 49 KB data: URI in a <source srcset>, took
// 6 s of CPU a pass. So each long payload in an attribute stands in for a short one
// of its own while Defuddle reads the document, and is put back in the markdown it
// writes: the image links, and the files saved from them, are what they were. The
// stand-in keeps the URI's header (Defuddle tells data:, data:image/ and svg+xml
// apart by it), is STAND_IN_LENGTH long so Defuddle does not take it for a lazy
// image's placeholder (a payload under 133 characters), and, like the base64 it
// stands for, holds no character the URL parser or the markdown conversion changes.
// Every attribute, not only srcset: a payload anywhere is one Defuddle pass away
// from the same cost.
const MIN_PAYLOAD = 1024
const LONG_PAYLOAD = new RegExp(`(;base64,)([A-Za-z0-9+/=]{${MIN_PAYLOAD},})`, 'i')
const STAND_IN_LENGTH = 136

function standInForPayloads(doc: Document, html: string): (text: string) => string {
  if (!LONG_PAYLOAD.test(html)) return text => text
  // Unique to this extraction, so no text of the page's own is taken for one.
  const nonce = randomBytes(8).toString('hex')
  const standIns = new Map<string, string>() // payload → its stand-in: one payload, one stand-in
  const payloads = new Map<string, string>() // stand-in → payload
  const standInFor = (payload: string) => {
    let s = standIns.get(payload)
    if (!s) {
      s = nonce + String(standIns.size).padStart(STAND_IN_LENGTH - nonce.length, '0')
      standIns.set(payload, s)
      payloads.set(s, payload)
    }
    return s
  }
  const every = new RegExp(LONG_PAYLOAD.source, 'gi')
  for (const el of Array.from(doc.querySelectorAll('*'))) {
    for (const { name, value } of Array.from(el.attributes)) {
      if (value.length < MIN_PAYLOAD) continue
      const short = value.replace(every, (_, head: string, payload: string) => head + standInFor(payload))
      if (short !== value) el.setAttribute(name, short)
    }
  }
  if (!payloads.size) return text => text
  const standIn = new RegExp(`${nonce}\\d{${STAND_IN_LENGTH - nonce.length}}`, 'g')
  return text => text.replace(standIn, s => payloads.get(s) ?? s)
}

// linkedom builds only the structure a document's tags spell out. HTML lets a page
// leave out <html>, <head> and <body>: linkedom's root is then the page's first
// element, with the rest of the page beside it, or the content sits beside an empty
// body, where Defuddle can miss all of it (rfc-editor's RFCs, a run of bare <pre>
// blocks, gave 0 words). Such a document is rebuilt with the tags a browser
// supplies: its leading head elements in <head>, the rest in <body>. A document whose
// content is all in its <body> is left as parsed, whatever scripts or styles it has
// outside it.
const HEAD_TAGS = new Set(['TITLE', 'META', 'LINK', 'BASE', 'STYLE', 'SCRIPT', 'NOSCRIPT', 'TEMPLATE'])

function parseDocument(html: string) {
  const doc = parseHTML(html).document
  const root = doc.documentElement
  const quiet = (n: Node) => n.nodeType === 8 || n.nodeType === 10 || n.nodeType === 3 && !(n.nodeValue ?? '').trim()
  const inert = (n: Node) => quiet(n) || HEAD_TAGS.has(n.nodeName)
  const whole = root?.tagName === 'HTML'
    && Array.from(doc.childNodes).every(n => n === root || inert(n))
    && Array.from(root.childNodes).every(n => inert(n) || n.nodeName === 'HEAD' || n.nodeName === 'BODY')
  if (whole) return doc
  // The parsed nodes move into a fresh document as they are: written out and parsed
  // again, linkedom's serialization would turn a title's escaped "&lt;/title&gt;" into
  // markup and unescape attribute values.
  const fresh = parseHTML('<!doctype html><html><head></head><body></body></html>').document
  let inBody = false
  const place = (node: Node, inHead = false): void => {
    const el = node.nodeType === 1 ? node as Element : undefined
    if (el && (el.tagName === 'HTML' || el.tagName === 'HEAD' || el.tagName === 'BODY')) {
      const into = el.tagName === 'HTML' ? fresh.documentElement : el.tagName === 'BODY' ? fresh.body : undefined
      for (const a of into ? Array.from(el.attributes) : []) if (!into!.hasAttribute(a.name)) into!.setAttribute(a.name, a.value)
      if (el.tagName === 'BODY') inBody = true
      for (const child of Array.from(el.childNodes)) place(child, el.tagName === 'HEAD')
    } else if (node.nodeType !== 10) { // the doctype is the fresh one's
      const toHead = inHead || !inBody && (quiet(node) || !!el && HEAD_TAGS.has(el.tagName))
      if (!toHead) inBody = true
      ;(toHead ? fresh.head : fresh.body).appendChild(fresh.importNode(node, true))
    }
  }
  for (const node of Array.from(doc.childNodes)) place(node)
  return fresh
}

// Defuddle takes a short dated line near the top of the content for the article's
// byline, whose date the frontmatter's `published` carries, and drops it; near the
// content's edges it also cuts a <time> out of the line around it. On a reference
// or registry page those dates are the page's data: deps.dev's "Published / May 22,
// 2023", PostgreSQL's "Release date: 2023-09-14", an RFC's reference dates.
// Defuddle keeps a date it sees labeled, but only as "Published:" or one of a few
// other words and a colon. So a date with a label of its own (a heading, term or
// header cell just before it, or any short "Label:" opening its line) is hidden
// from Defuddle's date patterns, a SHIELD between its characters that the result
// loses again; and a <time> inside a longer line hands the line its text. An
// unlabeled date on its own, the byline, is still Defuddle's to drop, and so is
// any date beside the page's title (the first h1 and three elements either side):
// there Defuddle reads the page's own date, from text when no tag carries it, for
// `published` and the author.
const SHIELD = '\u2063' // INVISIBLE SEPARATOR: to a pattern, no letter, digit or space
const DATE = /(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}|\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*|\d{4}[-/]\d{1,2}[-/]\d{1,2}|\b\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago\b/i
const LABEL_TAGS = new Set(['H2', 'H3', 'H4', 'H5', 'H6', 'DT', 'TH'])
const INLINE_TAGS = new Set(['A', 'ABBR', 'B', 'BDI', 'BDO', 'CITE', 'CODE', 'DATA', 'DFN', 'EM', 'FONT', 'I', 'KBD', 'MARK', 'Q', 'S', 'SAMP', 'SMALL', 'SPAN', 'STRONG', 'SUB', 'SUP', 'TIME', 'U', 'VAR'])

const textOf = (el: Element) => (el.textContent ?? '').replace(/\s+/g, ' ').trim()
const wordsIn = (s: string) => s ? s.split(' ').length : 0
const isDate = (s: string) => wordsIn(s) <= 6 && DATE.test(s) && !s.includes('://')
const isLabel = (el: Element | null) => {
  const name = el && LABEL_TAGS.has(el.tagName) ? textOf(el) : ''
  return wordsIn(name) >= 1 && wordsIn(name) <= 4 && !/[.!?]/.test(name)
}
const isLabeledLine = (s: string) => {
  const m = /^(\p{L}[^:]*):(.+)$/u.exec(s)
  return !!m && wordsIn(m[1].trim()) <= 3 && isDate(m[2].trim())
}

function keepDatesAsData(doc: Document): void {
  const title = doc.querySelector('h1')
  const besideTitle: Element[] = title ? [title] : []
  for (const step of ['nextElementSibling', 'previousElementSibling'] as const) {
    for (let el = title?.[step], i = 0; el && i < 3; el = el[step], i++) besideTitle.push(el)
  }
  const isBesideTitle = (node: Node) => besideTitle.some(el => el.contains(node))
  for (const time of Array.from(doc.querySelectorAll('time'))) {
    if (isBesideTitle(time)) continue
    let line = time.parentElement
    while (line && INLINE_TAGS.has(line.tagName)) line = line.parentElement
    // A line: a block holding only text and inline elements, more of it than the date.
    if (line && textOf(line) !== textOf(time) && Array.from(line.querySelectorAll('*')).every(el => INLINE_TAGS.has(el.tagName) || el.tagName === 'BR' || el.tagName === 'IMG')) freeTime(time)
  }
  const dated: Node[] = []
  const collect = (node: Node) => {
    if (node.nodeType === 3) { if (DATE.test(node.nodeValue ?? '')) dated.push(node) }
    else if (node.nodeName !== 'SCRIPT' && node.nodeName !== 'STYLE') for (const child of Array.from(node.childNodes)) collect(child)
  }
  if (doc.body) collect(doc.body)
  // From each date up through the few-word elements around it, to the first that is
  // labeled: by the element before it, or by its own text.
  for (const node of dated) {
    if (isBesideTitle(node)) continue
    for (let el = node.parentElement; el; el = el.parentElement) {
      const text = textOf(el)
      if (wordsIn(text) > 10) break
      if (isLabeledLine(text) || isDate(text) && isLabel(el.previousElementSibling)) { shield(el); break }
    }
  }
}

function shield(el: Element): void {
  for (const time of Array.from(el.querySelectorAll('time'))) freeTime(time)
  const walk = (node: Node) => {
    if (node.nodeType === 3) { if (DATE.test(node.nodeValue ?? '')) node.nodeValue = Array.from(node.nodeValue!).join(SHIELD) }
    else for (const child of Array.from(node.childNodes)) walk(child)
  }
  walk(el)
}

// Its text moves out beside it, since Defuddle removes a <time> near the content's
// edges whatever it holds. The emptied element keeps the date in `datetime`, where
// Defuddle's `published` reads it. A hidden one keeps its text, for Defuddle to
// remove with it (a page's machine timestamp behind a visible "yesterday").
function freeTime(time: Element): void {
  const text = textOf(time)
  if (!text || mayBeHidden(time)) return
  if (!time.getAttribute('datetime')) time.setAttribute('datetime', text)
  time.after(...Array.from(time.childNodes))
}

// Wider than what Defuddle removes as hidden: a <time> wrongly taken for hidden only
// keeps the text it always had.
const mayBeHidden = (el: Element) => el.hasAttribute('hidden') || el.hasAttribute('aria-hidden')
  || /display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0/i.test(el.getAttribute('style') ?? '')
  || /(?:^|[\s:])(?:hidden|invisible)(?:\s|$)/.test(el.getAttribute('class') ?? '')

const unshield = (s: string) => s.split(SHIELD).join('')

// Highlighters that name the language on a wrapper around the <pre>: Sphinx
// (`highlight-python3`) and GitHub (`highlight-source-shell`). Defuddle reads
// these wrappers' language only when it is a name it knows, so it is copied
// down as data-lang, which it takes as it stands.
// GitHub's are linguist scopes: highlight-source-js, highlight-text-html-basic.
const WRAPPER_LANGUAGE = /^highlight-(?:source-|text-)?([a-z][\w+#]*)/
const NOT_A_LANGUAGE = new Set(['default', 'none', 'text', 'plain', 'plaintext', 'output'])

function markWrapperLanguages(doc: Document): void {
  for (const pre of Array.from(doc.querySelectorAll('pre'))) {
    const code = pre.querySelector('code')
    const own = [pre, code].some(el => el && (el.getAttribute('data-lang') || /(?:^|\s)(?:language|lang)-/.test(el.getAttribute('class') ?? '')))
    if (own) continue
    let el: Element | null = pre.parentElement
    for (let depth = 0; el && depth < 3; depth++, el = el.parentElement) {
      const name = Array.from(el.classList).map(c => WRAPPER_LANGUAGE.exec(c.toLowerCase())?.[1]).find(Boolean)
      if (!name) continue
      const lang = name.replace(/^(python|py)3$/, 'python')
      // On every element from the <pre> up to the wrapper: Defuddle takes whichever
      // of them its code-block selectors match as the block.
      if (!NOT_A_LANGUAGE.has(lang)) for (let at: Element | null = pre; at && at !== el.parentElement; at = at.parentElement) at.setAttribute('data-lang', lang)
      break
    }
  }
}

// A <noscript> image is the static fallback for something a script draws (a
// chart, a lazy image), and an extraction runs no script, so that fallback is
// the content: each <noscript> holding images gives way to them, in a <figure>. One without
// an image ("enable JavaScript") is left to Defuddle, which drops it.
function keepNoscriptImages(doc: Document): void {
  for (const ns of Array.from(doc.querySelectorAll('noscript'))) {
    let images = Array.from(ns.querySelectorAll('img'))
    if (images.length === 0 && /<img\b/i.test(ns.textContent ?? '')) {
      // A parser that keeps <noscript> as raw text: read its markup.
      const holder = doc.createElement('div')
      holder.innerHTML = ns.textContent ?? ''
      images = Array.from(holder.querySelectorAll('img'))
    }
    if (images.length === 0) continue
    const twins = lazyTwinSources(ns)
    images = images.filter(img => !twins.has((img.getAttribute('src') ?? '').trim()))
    // In a <figure>: beside the chart's own download links, a bare image sits in a
    // block that Defuddle drops as link-dense (the Rust survey's charts with three links).
    // One whose every image is already on the page goes, or Defuddle shows it twice.
    if (images.length === 0) ns.remove()
    else {
      const figure = doc.createElement('figure')
      figure.append(...images)
      ns.replaceWith(figure)
    }
  }
}

// The sources of the lazy image a <noscript> stands in for: its element sibling just
// before or after, that image or a wrapper holding it alone. Nothing else counts, so
// the same picture anywhere else (a nav thumbnail) leaves the <noscript> image be.
function lazyTwinSources(ns: Element): Set<string> {
  const sources = new Set<string>()
  for (const sibling of [ns.previousElementSibling, ns.nextElementSibling]) {
    if (!sibling) continue
    const imgs = sibling.tagName === 'IMG' ? [sibling] : Array.from(sibling.querySelectorAll('img'))
    const img = imgs.length === 1 ? imgs[0] : undefined
    if (!img || !LAZY_ATTRIBUTES.some(a => img.hasAttribute(a)) && img.getAttribute('loading') !== 'lazy') continue
    for (const a of ['src', ...LAZY_ATTRIBUTES]) {
      // A srcset's first candidate URL; any other attribute is one URL.
      const v = img.getAttribute(a)?.trim().split(/\s+/)[0]
      if (v) sources.add(v)
    }
  }
  return sources
}
const LAZY_ATTRIBUTES = ['data-src', 'data-srcset', 'data-lazy-src', 'data-original']

function tidyMarkdown(md: string): string {
  return md.replace(/\r\n?/g, '\n').replace(/\n{3,}/g, '\n\n').trim() + '\n'
}

const quote = (s: string) => '"' + s.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/[\r\n]+/g, ' ') + '"'

/** The frontmatter of an extracted page, in the field order Defuddle writes. */
export function htmlFrontmatter(meta: PageMeta, words: number, source: string, fetched: string): string {
  const lines = ['---']
  if (meta.title) lines.push(`title: ${quote(meta.title)}`)
  if (meta.author) lines.push(`author: ${quote(meta.author)}`)
  if (meta.site) lines.push(`site: ${quote(meta.site)}`)
  if (meta.published) lines.push(`published: ${meta.published}`)
  lines.push(`source: ${quote(source)}`)
  if (meta.domain) lines.push(`domain: ${quote(meta.domain)}`)
  if (meta.language) lines.push(`language: ${quote(meta.language)}`)
  if (meta.description) lines.push(`description: ${quote(meta.description)}`)
  if (words) lines.push(`word_count: ${words}`)
  lines.push(`fetched: ${fetched}`, '---', '', '')
  return lines.join('\n')
}

/**
 * A served markdown file with frontmatter: its title from the first `#`
 * heading. A file that has frontmatter already gets `source` and `fetched`
 * added to it rather than a second block.
 */
export function markdownWithFrontmatter(md: string, source: string, fetched: string): { text: string; title?: string } {
  const text = md.replace(/\r\n?/g, '\n')
  const own = /^---\n[\s\S]*?\n---\n/.exec(text)
  const ownTitle = own && /^title:[ \t]*(.+?)[ \t]*$/m.exec(own[0])?.[1]
  const title = ownTitle
    ? (/^"(.*)"$/.exec(ownTitle)?.[1].replace(/\\(.)/g, '$1') ?? ownTitle.replace(/^'(.*)'$/, '$1'))
    : findHeadings(splitLines(own ? text.slice(own[0].length) : text)).find(h => h.level === 1 && h.title)?.title
  if (own) {
    const block = own[0].slice(0, -4)
    const add = [/^source:/m.test(block) ? '' : `source: ${quote(source)}\n`, `fetched: ${fetched}\n`].join('')
    return { text: block + add + '---\n' + text.slice(own[0].length), title }
  }
  const head = ['---', ...(title ? [`title: ${quote(title)}`] : []), `source: ${quote(source)}`, `fetched: ${fetched}`, '---', '', ''].join('\n')
  return { text: head + text, title }
}
