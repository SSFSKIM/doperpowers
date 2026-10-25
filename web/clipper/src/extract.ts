// HTML to clipper-shaped markdown: Defuddle (the extraction Obsidian Web
// Clipper is built on) over a linkedom document, with the frontmatter
// Defuddle's --frontmatter mode writes, plus `fetched`.
import { Defuddle } from 'defuddle/node'
import { parseHTML } from 'linkedom'
import { findHeadings, splitLines } from './measure.ts'

export type PageMeta = { title?: string; author?: string; site?: string; published?: string; description?: string; domain?: string; language?: string }
export type Extracted = { body: string; meta: PageMeta; words: number }

export async function extractHtml(html: string, url: string, siteFetch: typeof fetch): Promise<Extracted> {
  const doc = parseHTML(html).document
  // The polyfills Defuddle applies to a linkedom document of its own.
  const loose = doc as unknown as { URL: string; styleSheets?: unknown; defaultView: { getComputedStyle?: unknown } | null }
  if (!loose.styleSheets) loose.styleSheets = []
  if (loose.defaultView && !loose.defaultView.getComputedStyle) loose.defaultView.getComputedStyle = () => ({ display: '' })
  loose.URL = url
  markWrapperLanguages(doc as unknown as Document)
  keepNoscriptImages(doc as unknown as Document)
  keepDatesAsData(doc as unknown as Document)
  const r = await Defuddle(doc as unknown as Document, url, { markdown: true, fetch: siteFetch })
  const meta: PageMeta = {}
  for (const k of ['title', 'author', 'site', 'published', 'description', 'domain', 'language'] as const) {
    const v = typeof r[k] === 'string' ? unshield(r[k]).trim() : ''
    if (v) meta[k] = v
  }
  return { body: tidyMarkdown(unshield(r.content ?? '')), meta, words: r.wordCount ?? 0 }
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
// unlabeled date on its own, the byline, is still Defuddle's to drop.
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
  for (const time of Array.from(doc.querySelectorAll('time'))) {
    let block = time.parentElement
    while (block && INLINE_TAGS.has(block.tagName)) block = block.parentElement
    if (block && textOf(block) !== textOf(time)) freeTime(time)
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
// Defuddle's `published` reads it.
function freeTime(time: Element): void {
  const text = textOf(time)
  if (!text) return
  if (!time.getAttribute('datetime')) time.setAttribute('datetime', text)
  time.after(...Array.from(time.childNodes))
}

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
