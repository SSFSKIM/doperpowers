/**
 * A markdown parser for what a model writes: paragraphs, ATX headings,
 * fenced code, block quotes, nested bullet and numbered lists with task
 * boxes, pipe tables, rules, and inline emphasis, code, strikethrough and
 * links. Pure: no environment, so it runs in a hooks module and in a test.
 *
 * Text may be mid-stream: an unclosed fence runs to the end, an unmatched
 * emphasis marker draws as itself.
 */

export type Run = {
  text: string
  bold?: true
  italic?: true
  code?: true
  strike?: true
  href?: string
}

export type Inline = Run[]

export type Align = 'left' | 'center' | 'right'

export type ListItem = {
  blocks: Block[]
  /** Present on a task item: `- [ ]` false, `- [x]` true. */
  checked?: boolean
}

export type Block =
  | { kind: 'paragraph'; inline: Inline }
  | { kind: 'heading'; level: number; inline: Inline }
  | { kind: 'code'; language: string; source: string }
  | { kind: 'quote'; blocks: Block[] }
  | { kind: 'list'; ordered: boolean; start: number; loose: boolean; items: ListItem[] }
  | { kind: 'table'; align: Align[]; header: Inline[]; rows: Inline[][] }
  | { kind: 'rule' }

const FENCE = /^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)/
const HEADING = /^ {0,3}(#{1,6})(?:\s+(.*?))?\s*#*\s*$/
const RULE = /^ {0,3}([-*_])(?:\s*\1){2,}\s*$/
const QUOTE = /^ {0,3}>\s?(.*)$/
const LIST = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/
const LIST_BARE = /^(\s*)([-*+]|\d{1,9}[.)])\s*$/
const TABLE_DELIM = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/
const TASK = /^\[([ xX])\]\s+(.*)$/s

export function parse(text: string): Block[] {
  return parseBlocks(text.replace(/\r\n?/g, '\n').split('\n'))
}

function isBlank(line: string): boolean {
  return line.trim() === ''
}

/** True when the line opens a block that interrupts a paragraph. */
function startsBlock(line: string): boolean {
  return (
    FENCE.test(line) ||
    HEADING.test(line) ||
    RULE.test(line) ||
    QUOTE.test(line) ||
    LIST.test(line) ||
    LIST_BARE.test(line)
  )
}

function parseBlocks(lines: string[]): Block[] {
  const blocks: Block[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i] ?? ''

    if (isBlank(line)) {
      i += 1
      continue
    }

    const fence = FENCE.exec(line)
    if (fence) {
      const mark = fence[1] ?? '```'
      const language = fence[2] ?? ''
      const body: string[] = []
      i += 1
      while (i < lines.length) {
        const l = lines[i] ?? ''
        if (l.trim().startsWith(mark[0] ?? '`') && new RegExp(`^ {0,3}\\${mark[0]}{${mark.length},}\\s*$`).test(l)) {
          i += 1
          break
        }
        body.push(l)
        i += 1
      }
      blocks.push({ kind: 'code', language, source: body.join('\n') })
      continue
    }

    const heading = HEADING.exec(line)
    if (heading) {
      blocks.push({
        kind: 'heading',
        level: (heading[1] ?? '#').length,
        inline: parseInline(heading[2] ?? ''),
      })
      i += 1
      continue
    }

    if (RULE.test(line)) {
      blocks.push({ kind: 'rule' })
      i += 1
      continue
    }

    if (QUOTE.test(line)) {
      const inner: string[] = []
      while (i < lines.length) {
        const l = lines[i] ?? ''
        const q = QUOTE.exec(l)
        if (q) {
          inner.push(q[1] ?? '')
        } else if (!isBlank(l) && !startsBlock(l) && inner.length > 0 && !isBlank(inner[inner.length - 1] ?? '')) {
          inner.push(l)
        } else {
          break
        }
        i += 1
      }
      blocks.push({ kind: 'quote', blocks: parseBlocks(inner) })
      continue
    }

    const list = LIST.exec(line) ?? LIST_BARE.exec(line)
    if (list) {
      const [block, next] = parseList(lines, i)
      blocks.push(block)
      i = next
      continue
    }

    if (line.includes('|') && i + 1 < lines.length && TABLE_DELIM.test(lines[i + 1] ?? '')) {
      const header = splitRow(line)
      const align = splitRow(lines[i + 1] ?? '').map(alignOf)
      if (header.length === align.length) {
        const rows: Inline[][] = []
        i += 2
        while (i < lines.length) {
          const l = lines[i] ?? ''
          if (isBlank(l) || !l.includes('|')) {
            break
          }
          const cells = splitRow(l)
          while (cells.length < header.length) {
            cells.push('')
          }
          rows.push(cells.slice(0, header.length).map(parseInline))
          i += 1
        }
        blocks.push({ kind: 'table', align, header: header.map(parseInline), rows })
        continue
      }
    }

    const para: string[] = [line]
    i += 1
    while (i < lines.length) {
      const l = lines[i] ?? ''
      if (isBlank(l) || startsBlock(l)) {
        break
      }
      if (l.includes('|') && i + 1 < lines.length && TABLE_DELIM.test(lines[i + 1] ?? '')) {
        break
      }
      para.push(l)
      i += 1
    }
    blocks.push({ kind: 'paragraph', inline: parseInline(para.map(l => l.trim()).join(' ')) })
  }

  return blocks
}

function markerOf(marker: string): { ordered: boolean; start: number } {
  const n = Number.parseInt(marker, 10)
  return Number.isNaN(n) ? { ordered: false, start: 1 } : { ordered: true, start: n }
}

/**
 * Reads one list starting at `from`: every item at the first item's indent
 * with the same kind of marker, each item's continuation lines (indented at
 * least to its content) parsed as blocks of their own.
 */
function parseList(lines: string[], from: number): [Block, number] {
  const first = LIST.exec(lines[from] ?? '') ?? LIST_BARE.exec(lines[from] ?? '')
  const indent = (first?.[1] ?? '').length
  const { ordered, start } = markerOf(first?.[2] ?? '-')
  const items: ListItem[] = []
  let loose = false
  let i = from

  while (i < lines.length) {
    const line = lines[i] ?? ''
    const m = LIST.exec(line) ?? LIST_BARE.exec(line)
    if (!m || (m[1] ?? '').length !== indent || markerOf(m[2] ?? '-').ordered !== ordered) {
      break
    }

    const marker = m[2] ?? '-'
    const contentIndent = indent + marker.length + 1
    let firstLine = m[3] ?? ''
    let checked: boolean | undefined
    const task = TASK.exec(firstLine)
    if (task) {
      checked = task[1] !== ' '
      firstLine = task[2] ?? ''
    }

    const inner: string[] = [firstLine]
    i += 1
    let sawBlank = false

    while (i < lines.length) {
      const l = lines[i] ?? ''
      if (isBlank(l)) {
        // A blank line ends the item unless what follows is still indented
        // under it.
        const after = lines[i + 1] ?? ''
        if (i + 1 < lines.length && !isBlank(after) && leading(after) >= contentIndent) {
          inner.push('')
          sawBlank = true
          i += 1
          continue
        }
        break
      }
      if (leading(l) >= contentIndent) {
        inner.push(l.slice(contentIndent))
        i += 1
        continue
      }
      // A lazy continuation: unindented text after a one-line item.
      const asItem = LIST.exec(l) ?? LIST_BARE.exec(l)
      if (!asItem && !startsBlock(l) && inner.length === 1) {
        inner.push(l.trim())
        i += 1
        continue
      }
      break
    }

    const item: ListItem = { blocks: parseBlocks(inner) }
    if (checked !== undefined) {
      item.checked = checked
    }
    if (item.blocks.length === 0) {
      item.blocks.push({ kind: 'paragraph', inline: [] })
    }
    items.push(item)
    if (sawBlank) {
      loose = true
    }

    // A blank line between two items makes the list loose.
    if (i < lines.length && isBlank(lines[i] ?? '')) {
      let j = i
      while (j < lines.length && isBlank(lines[j] ?? '')) {
        j += 1
      }
      const nextItem = j < lines.length ? (LIST.exec(lines[j] ?? '') ?? LIST_BARE.exec(lines[j] ?? '')) : null
      if (nextItem && (nextItem[1] ?? '').length === indent && markerOf(nextItem[2] ?? '-').ordered === ordered) {
        loose = true
        i = j
      }
    }
  }

  return [{ kind: 'list', ordered, start, loose, items }, i]
}

function leading(line: string): number {
  return line.length - line.trimStart().length
}

function splitRow(line: string): string[] {
  let s = line.trim()
  if (s.startsWith('|')) {
    s = s.slice(1)
  }
  if (s.endsWith('|') && !s.endsWith('\\|')) {
    s = s.slice(0, -1)
  }
  const cells: string[] = []
  let cell = ''
  let inCode = false
  for (let i = 0; i < s.length; i += 1) {
    const c = s[i]
    if (c === '\\' && s[i + 1] === '|') {
      cell += '|'
      i += 1
    } else if (c === '`') {
      inCode = !inCode
      cell += c
    } else if (c === '|' && !inCode) {
      cells.push(cell.trim())
      cell = ''
    } else {
      cell += c
    }
  }
  cells.push(cell.trim())
  return cells
}

function alignOf(cell: string): Align {
  const left = cell.startsWith(':')
  const right = cell.endsWith(':')
  return left && right ? 'center' : right ? 'right' : 'left'
}

// ---------------------------------------------------------------- inline

type Style = { bold?: true; italic?: true; strike?: true; href?: string }

const URL = /^https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"]/

export function parseInline(text: string): Inline {
  return merge(inlineOf(text, {}))
}

function inlineOf(s: string, style: Style): Run[] {
  const runs: Run[] = []
  let buf = ''
  const flush = () => {
    if (buf !== '') {
      runs.push({ text: buf, ...style })
      buf = ''
    }
  }
  let i = 0

  while (i < s.length) {
    const c = s[i] ?? ''

    if (c === '\\' && i + 1 < s.length && /[\\`*_~[\]()<>#+\-.!|]/.test(s[i + 1] ?? '')) {
      buf += s[i + 1]
      i += 2
      continue
    }

    if (c === '`') {
      const ticks = countRun(s, i, '`')
      const close = findTicks(s, i + ticks, ticks)
      if (close >= 0) {
        flush()
        let code = s.slice(i + ticks, close)
        if (code.length > 2 && code.startsWith(' ') && code.endsWith(' ') && code.trim() !== '') {
          code = code.slice(1, -1)
        }
        runs.push({ text: code, code: true, ...style })
        i = close + ticks
        continue
      }
      buf += s.slice(i, i + ticks)
      i += ticks
      continue
    }

    if (c === '[') {
      const link = readLink(s, i)
      if (link) {
        flush()
        runs.push(...inlineOf(link.text, { ...style, href: link.href }))
        i = link.end
        continue
      }
    }

    if (c === '<') {
      const m = /^<(https?:\/\/[^\s<>]+)>/.exec(s.slice(i))
      if (m) {
        flush()
        const href = m[1] ?? ''
        runs.push({ text: href, ...style, href })
        i += m[0].length
        continue
      }
    }

    if (c === 'h' && (s.startsWith('http://', i) || s.startsWith('https://', i)) && !style.href) {
      const m = URL.exec(s.slice(i))
      if (m && (i === 0 || /[\s(]/.test(s[i - 1] ?? ''))) {
        flush()
        runs.push({ text: m[0], ...style, href: m[0] })
        i += m[0].length
        continue
      }
    }

    if (c === '*' || c === '_' || c === '~') {
      const n = countRun(s, i, c)
      const mark = c === '~' ? (n >= 2 ? '~~' : '') : n >= 2 ? c + c : c
      if (mark !== '' && canOpen(s, i, mark.length)) {
        const close = findClose(s, i + mark.length, mark)
        if (close >= 0) {
          flush()
          const inner = s.slice(i + mark.length, close)
          const next: Style = { ...style }
          if (mark === '~~') {
            next.strike = true
          } else if (mark.length === 2) {
            next.bold = true
          } else {
            next.italic = true
          }
          runs.push(...inlineOf(inner, next))
          i = close + mark.length
          continue
        }
      }
      buf += s.slice(i, i + n)
      i += n
      continue
    }

    buf += c
    i += 1
  }

  flush()
  return runs
}

function countRun(s: string, i: number, c: string): number {
  let n = 0
  while (s[i + n] === c) {
    n += 1
  }
  return n
}

function findTicks(s: string, from: number, ticks: number): number {
  let i = from
  while (i < s.length) {
    if (s[i] === '`') {
      const n = countRun(s, i, '`')
      if (n === ticks) {
        return i
      }
      i += n
    } else {
      i += 1
    }
  }
  return -1
}

function isWordChar(c: string | undefined): boolean {
  return c !== undefined && /[\p{L}\p{N}]/u.test(c)
}

function canOpen(s: string, i: number, len: number): boolean {
  const after = s[i + len]
  if (after === undefined || /\s/.test(after)) {
    return false
  }
  // An underscore inside a word (snake_case) is not emphasis.
  if (s[i] === '_' && isWordChar(s[i - 1])) {
    return false
  }
  return true
}

function canClose(s: string, i: number, len: number): boolean {
  const before = s[i - 1]
  if (before === undefined || /\s/.test(before)) {
    return false
  }
  if (s[i] === '_' && isWordChar(s[i + len])) {
    return false
  }
  return true
}

/** The index of the closing `mark` after `from`, skipping code spans; -1 if none. */
function findClose(s: string, from: number, mark: string): number {
  const c = mark[0] ?? '*'
  let i = from
  while (i < s.length) {
    const ch = s[i]
    if (ch === '\\') {
      i += 2
      continue
    }
    if (ch === '`') {
      const n = countRun(s, i, '`')
      const end = findTicks(s, i + n, n)
      i = end >= 0 ? end + n : i + n
      continue
    }
    if (ch === c) {
      const n = countRun(s, i, c)
      if (n === mark.length && canClose(s, i, n)) {
        return i
      }
      if (n > mark.length && canClose(s, i, n)) {
        // `***x***` style closers: take the last `mark.length` of the run.
        return i + n - mark.length
      }
      i += n
      continue
    }
    i += 1
  }
  return -1
}

function readLink(s: string, from: number): { text: string; href: string; end: number } | null {
  let depth = 0
  let i = from
  while (i < s.length) {
    const ch = s[i]
    if (ch === '\\') {
      i += 2
      continue
    }
    if (ch === '[') {
      depth += 1
    } else if (ch === ']') {
      depth -= 1
      if (depth === 0) {
        break
      }
    }
    i += 1
  }
  if (depth !== 0 || s[i + 1] !== '(') {
    return null
  }
  const text = s.slice(from + 1, i)
  let j = i + 2
  let parens = 0
  while (j < s.length) {
    const ch = s[j]
    if (ch === '(') {
      parens += 1
    } else if (ch === ')') {
      if (parens === 0) {
        break
      }
      parens -= 1
    }
    j += 1
  }
  if (j >= s.length) {
    return null
  }
  let href = s.slice(i + 2, j).trim()
  const title = /^(\S+)\s+["'(].*["')]$/.exec(href)
  if (title) {
    href = title[1] ?? href
  }
  if (href.startsWith('<') && href.endsWith('>')) {
    href = href.slice(1, -1)
  }
  return { text, href, end: j + 1 }
}

/** Joins adjacent runs of one style, so a wrap sees whole words. */
function merge(runs: Run[]): Run[] {
  const out: Run[] = []
  for (const run of runs) {
    const last = out[out.length - 1]
    if (last && sameStyle(last, run)) {
      last.text += run.text
    } else {
      out.push({ ...run })
    }
  }
  return out.filter(r => r.text !== '')
}

function sameStyle(a: Run, b: Run): boolean {
  return a.bold === b.bold && a.italic === b.italic && a.code === b.code && a.strike === b.strike && a.href === b.href
}

// ----------------------------------------------------------------- width

/**
 * The cells a string takes on the terminal: two for an East Asian wide or
 * fullwidth character (Hangul, CJK, most emoji), none for a combining mark
 * or a zero-width joiner, one for the rest.
 */
export function widthOf(s: string): number {
  let w = 0
  for (const ch of s) {
    w += cellsOf(ch.codePointAt(0) ?? 0)
  }
  return w
}

function cellsOf(cp: number): number {
  if (cp === 0 || cp === 0x200b || cp === 0x200d || (cp >= 0x300 && cp <= 0x36f) || (cp >= 0xfe00 && cp <= 0xfe0f)) {
    return 0
  }
  if (
    (cp >= 0x1100 && cp <= 0x115f) ||
    (cp >= 0x2e80 && cp <= 0xa4cf && cp !== 0x303f) ||
    (cp >= 0xac00 && cp <= 0xd7a3) ||
    (cp >= 0xf900 && cp <= 0xfaff) ||
    (cp >= 0xfe30 && cp <= 0xfe4f) ||
    (cp >= 0xff00 && cp <= 0xff60) ||
    (cp >= 0xffe0 && cp <= 0xffe6) ||
    (cp >= 0x1f300 && cp <= 0x1f64f) ||
    (cp >= 0x1f900 && cp <= 0x1f9ff) ||
    (cp >= 0x20000 && cp <= 0x3fffd)
  ) {
    return 2
  }
  return 1
}

/**
 * Breaks runs into lines no wider than `width` cells, at spaces where it
 * can and inside a word where it must; each line keeps its runs' styles.
 */
export function wrapRuns(runs: Run[], width: number): Run[][] {
  const lines: Run[][] = []
  let line: Run[] = []
  let used = 0

  const push = (run: Run) => {
    const last = line[line.length - 1]
    if (last && sameStyle(last, run)) {
      last.text += run.text
    } else {
      line.push({ ...run })
    }
    used += widthOf(run.text)
  }
  const newline = () => {
    lines.push(line)
    line = []
    used = 0
  }

  for (const run of runs) {
    const words = run.text.split(/(\s+)/).filter(w => w !== '')
    for (const word of words) {
      const isSpace = /^\s+$/.test(word)
      const w = widthOf(word)
      if (isSpace) {
        if (used > 0 && used + w <= width) {
          push({ ...run, text: ' ' })
        }
        continue
      }
      if (used + w <= width) {
        push({ ...run, text: word })
        continue
      }
      if (used > 0) {
        trimEnd(line)
        newline()
      }
      if (w <= width) {
        push({ ...run, text: word })
        continue
      }
      // A word wider than the line: break it by cells.
      let piece = ''
      let pw = 0
      for (const ch of word) {
        const cw = widthOf(ch)
        if (pw + cw > width) {
          push({ ...run, text: piece })
          newline()
          piece = ''
          pw = 0
        }
        piece += ch
        pw += cw
      }
      push({ ...run, text: piece })
    }
  }

  trimEnd(line)
  if (line.length > 0 || lines.length === 0) {
    lines.push(line)
  }
  return lines
}

function trimEnd(line: Run[]): void {
  const last = line[line.length - 1]
  if (last) {
    last.text = last.text.replace(/\s+$/, '')
    if (last.text === '') {
      line.pop()
    }
  }
}

/** The plain text of runs. */
export function plainOf(runs: Run[]): string {
  return runs.map(r => r.text).join('')
}
