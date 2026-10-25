// Lines and the outline, computed over the text file as written, so an
// outline line number is the line Read shows.
import { estimateTokens } from './estimate.ts'

export const OUTLINE_MAX_ENTRIES = 80

export type OutlineEntry = { level: number; title: string; line: number; endLine: number; tokens: number; images: number }
export type OutlineMode = 'markdown' | 'plain' | 'pdf'

/** The file's lines as Read numbers them: a final newline does not start another line. */
export function splitLines(text: string): string[] {
  if (text === '') return []
  const lines = text.split('\n')
  if (lines[lines.length - 1] === '') lines.pop()
  return lines
}

/**
 * The outline of a text file. `imageLines` are the (1-based) lines image
 * links sit on. `omitted` counts the headings left out to fit the cap.
 */
export function buildOutline(text: string, mode: OutlineMode, imageLines: number[]): { outline: OutlineEntry[]; omitted: number } {
  const lines = splitLines(text)
  const ranges = mode === 'pdf' ? pdfRanges(text, lines.length) : mode === 'plain' ? bodyRange(1, lines.length) : markdownRanges(lines)
  const entries = ranges.map(r => ({
    ...r,
    tokens: estimateTokens(lines.slice(r.line - 1, r.endLine).join('\n')),
    images: imageLines.filter(l => l >= r.line && l <= r.endLine).length,
  }))
  return capOutline(entries, OUTLINE_MAX_ENTRIES)
}

type Range = { level: number; title: string; line: number; endLine: number }

function bodyRange(from: number, to: number): Range[] {
  return to >= from ? [{ level: 0, title: '(body)', line: from, endLine: to }] : []
}

const FENCE = /^ {0,3}(`{3,}|~{3,})/
const ATX = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$/

/** ATX headings from line `from` on; a heading inside a fenced code block is not one. */
export function findHeadings(lines: string[], from = 1): { level: number; title: string; line: number }[] {
  const headings: { level: number; title: string; line: number }[] = []
  let fence: string | null = null
  for (let i = from - 1; i < lines.length; i++) {
    const line = lines[i]
    const f = FENCE.exec(line)
    if (fence) {
      if (f && f[1][0] === fence[0] && f[1].length >= fence.length && line.trim() === f[1]) fence = null
      continue
    }
    if (f) { fence = f[1]; continue }
    const h = ATX.exec(line)
    if (h) headings.push({ level: h[1].length, title: (h[2] ?? '').trim(), line: i + 1 })
  }
  return headings
}

function markdownRanges(lines: string[]): Range[] {
  const out: Range[] = []
  let bodyStart = 1
  if (lines[0] === '---') {
    const close = lines.indexOf('---', 1)
    if (close > 0) {
      out.push({ level: 0, title: '(frontmatter)', line: 1, endLine: close + 1 })
      bodyStart = close + 2
    }
  }
  const headings = findHeadings(lines, bodyStart)
  const last = lines.length
  if (headings.length === 0) return [...out, ...bodyRange(bodyStart, last)]
  const firstHeading = headings[0].line
  if (lines.slice(bodyStart - 1, firstHeading - 1).some(l => l.trim() !== ''))
    out.push({ level: 0, title: '(top)', line: bodyStart, endLine: firstHeading - 1 })
  headings.forEach((h, i) => {
    const next = headings.slice(i + 1).find(n => n.level <= h.level)
    out.push({ ...h, endLine: next ? next.line - 1 : last })
  })
  return out
}

// pdftotext ends each page with a form feed; the next page starts after it.
function pdfRanges(text: string, lineCount: number): Range[] {
  const out: Range[] = []
  let line = 1 // the line the current page starts on
  let pageStart = 0 // its offset in text
  let lineAt = 1 // line number at offset i
  for (let i = 0; i <= text.length; i++) {
    const ch = text[i]
    if (ch === '\f' || i === text.length) {
      const pageText = text.slice(pageStart, i)
      if (ch === '\f' || pageText.trim() !== '') {
        // The page ends on the line before the form feed when the feed opens its line.
        const atLineStart = i === 0 || text[i - 1] === '\n'
        const end = Math.min(atLineStart ? lineAt - 1 : lineAt, lineCount)
        out.push({ level: 1, title: `page ${out.length + 1}`, line, endLine: Math.max(end, line) })
      }
      line = lineAt
      pageStart = i + 1
    } else if (ch === '\n') lineAt++
  }
  return out
}

function capOutline(entries: OutlineEntry[], max: number): { outline: OutlineEntry[]; omitted: number } {
  let outline = entries
  while (outline.length > max) {
    const levels = [...new Set(outline.filter(e => e.level > 0).map(e => e.level))]
    if (levels.length > 1) {
      const deepest = Math.max(...levels)
      outline = outline.filter(e => e.level !== deepest)
    } else outline = outline.slice(0, max)
  }
  return { outline, omitted: entries.length - outline.length }
}
