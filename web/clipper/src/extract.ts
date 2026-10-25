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
  const r = await Defuddle(doc as unknown as Document, url, { markdown: true, fetch: siteFetch })
  const meta: PageMeta = {}
  for (const k of ['title', 'author', 'site', 'published', 'description', 'domain', 'language'] as const) {
    const v = typeof r[k] === 'string' ? r[k].trim() : ''
    if (v) meta[k] = v
  }
  return { body: tidyMarkdown(r.content ?? ''), meta, words: r.wordCount ?? 0 }
}

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

// The images a <noscript> stands in for: a lazy image sits beside it, under the same
// parent. Only there, so the same picture elsewhere (a nav thumbnail) leaves it be.
function lazyTwinSources(ns: Element): Set<string> {
  const sources = new Set<string>()
  for (const img of Array.from(ns.parentElement?.querySelectorAll('img') ?? [])) {
    if (img.closest('noscript')) continue
    for (const a of ['src', 'data-src', 'data-lazy-src', 'data-original']) {
      const v = img.getAttribute(a)
      if (v) sources.add(v.trim())
    }
  }
  return sources
}

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
