import type { Elements, On, PluginOptions, RenderElement, RenderNode } from 'claude-code'

import { parse, plainOf, widthOf, wrapRuns } from './markdown'
import type { Align, Block, ListItem, Run } from './markdown'

type T = Elements['terminal']

type Theme = {
  accent: string
  measure: number
}

const CODE_COLOR = 'cyan'
const MAX_CODE = 10000

/** `h` answers a node; every call here builds an element. */
function el(tag: unknown, props: Record<string, unknown> | null, ...children: unknown[]): RenderElement {
  return h(tag as (props: never) => RenderElement, props, ...children) as RenderElement
}

/**
 * The link's href as the engine bounds it, or null when it would refuse the
 * tree: https (or http on localhost), printable ASCII, no user part.
 */
function safeHref(href: string): string | null {
  try {
    const url = new URL(href)
    const isHttps = url.protocol === 'https:'
    const isLocal = url.protocol === 'http:' && url.hostname === 'localhost'
    if ((!isHttps && !isLocal) || url.username !== '' || url.password !== '') {
      return null
    }
    const spelled = url.href
    if (spelled.length > 2048 || !/^[\x21-\x7e]+$/.test(spelled) || spelled.includes('@')) {
      return null
    }
    return spelled
  } catch {
    return null
  }
}

function inline(t: T, theme: Theme, runs: Run[]): RenderNode[] {
  return runs.map(run => {
    const props: Record<string, string | boolean> = {}
    if (run.code) {
      props.color = CODE_COLOR
    }
    if (run.bold) {
      props.bold = true
    }
    if (run.italic) {
      props.italic = true
    }
    if (run.strike) {
      props.strikethrough = true
    }
    if (run.href) {
      const href = safeHref(run.href)
      props.underline = true
      props.color = theme.accent
      const text = el(t.Text, props, run.text)
      return href ? el(t.Link, { href }, text) : text
    }
    return Object.keys(props).length > 0 ? el(t.Text, props, run.text) : run.text
  })
}

/** One wrapped line of runs, padded to `width` per `align`. */
function line(t: T, theme: Theme, runs: Run[], width: number, align: Align, bold: boolean): RenderElement {
  const slack = Math.max(0, width - widthOf(plainOf(runs)))
  const left = align === 'right' ? slack : align === 'center' ? Math.floor(slack / 2) : 0
  const props: Record<string, boolean> = {}
  if (bold) {
    props.bold = true
  }
  return el(t.Text, props, left > 0 ? ' '.repeat(left) : '', ...inline(t, theme, runs))
}

function paragraph(t: T, theme: Theme, runs: Run[]): RenderElement {
  return el(t.Text, { wrap: 'wrap' }, ...inline(t, theme, runs))
}

function heading(t: T, theme: Theme, level: number, runs: Run[], width: number): RenderElement[] {
  const props: Record<string, string | boolean> = { bold: true }
  if (level <= 2) {
    props.color = theme.accent
  } else if (level >= 4) {
    props.dimColor = true
  }
  const title = el(t.Text, props, ...inline(t, theme, runs))
  if (level === 1) {
    return [title, el(t.Text, { color: theme.accent, dimColor: true }, '─'.repeat(width))]
  }
  return [title]
}

function code(t: T, language: string, source: string): RenderElement {
  if (source.trim() === '') {
    return el(t.Text, { dimColor: true }, '')
  }
  const props: Record<string, string> = { source: source.slice(0, MAX_CODE), wrap: 'wrap' }
  if (language !== '') {
    props.language = language
  }
  return el(t.Code, props)
}

function quote(t: T, theme: Theme, inner: Block[], width: number): RenderElement[] {
  const bar = () => el(t.Box, { width: 2 }, el(t.Text, { color: theme.accent }, '▎'))
  const rows: RenderElement[] = []
  inner.forEach((block, i) => {
    if (block.kind === 'paragraph') {
      for (const runs of wrapRuns(block.inline, width - 2)) {
        rows.push(el(t.Box, { flexDirection: 'row' }, bar(), el(t.Text, { italic: true }, ...inline(t, theme, runs))))
      }
    } else {
      rows.push(
        el(
          t.Box,
          { flexDirection: 'row' },
          bar(),
          el(t.Box, { flexDirection: 'column', width: width - 2 }, ...blocks(t, theme, [block], width - 2, true, 0)),
        ),
      )
    }
    if (i < inner.length - 1) {
      rows.push(el(t.Box, { flexDirection: 'row' }, bar()))
    }
  })
  return rows
}

const BULLETS = ['•', '◦', '▪']

function firstInline(item: ListItem): Run[] {
  const first = item.blocks[0]
  return first && (first.kind === 'paragraph' || first.kind === 'heading') ? first.inline : []
}

function list(
  t: T,
  theme: Theme,
  ordered: boolean,
  start: number,
  loose: boolean,
  items: ListItem[],
  width: number,
  depth: number,
): RenderElement[] {
  const gutter = ordered ? String(start + items.length - 1).length + 2 : 2
  const inner = Math.max(10, width - gutter)
  const bullet = BULLETS[Math.min(depth, BULLETS.length - 1)] ?? '•'
  // Items that wrap read better with a row between them, as a loose list
  // does; short items stay tight.
  const isLoose = loose || items.some(item => item.blocks.length > 1 || widthOf(plainOf(firstInline(item))) > inner)

  return items.map((item, i) => {
    const marker = ordered
      ? `${start + i}.`
      : item.checked === undefined
        ? bullet
        : item.checked
          ? '☑'
          : '☐'
    const props: Record<string, string | number> = { flexDirection: 'row' }
    if (isLoose && i < items.length - 1) {
      props.marginBottom = 1
    }
    return el(
      t.Box,
      props,
      el(t.Box, { width: gutter }, el(t.Text, { color: theme.accent }, marker)),
      el(t.Box, { flexDirection: 'column', width: inner }, ...blocks(t, theme, item.blocks, inner, !isLoose, depth + 1)),
    )
  })
}

function table(t: T, theme: Theme, align: Align[], header: Run[][], rows: Run[][][], width: number): RenderElement[] {
  const cols = header.length
  const gap = 2
  const natural = header.map((cell, c) =>
    Math.max(widthOf(plainOf(cell)), ...rows.map(row => widthOf(plainOf(row[c] ?? [])))),
  )
  const avail = Math.max(cols * 4, width - gap * (cols - 1))
  let widths = natural.map(w => Math.max(1, w))
  const total = widths.reduce((a, b) => a + b, 0)
  if (total > avail) {
    const scale = avail / total
    widths = widths.map(w => Math.max(4, Math.floor(w * scale)))
    let sum = widths.reduce((a, b) => a + b, 0)
    while (sum > avail) {
      const widest = widths.indexOf(Math.max(...widths))
      if ((widths[widest] ?? 0) <= 4) {
        break
      }
      widths[widest] = (widths[widest] ?? 0) - 1
      sum -= 1
    }
  }

  const row = (cells: Run[][], bold: boolean): RenderElement =>
    el(
      t.Box,
      { flexDirection: 'row', columnGap: gap },
      ...cells.map((cell, c) => {
        const w = widths[c] ?? 4
        const lines = wrapRuns(cell, w)
        return el(
          t.Box,
          { flexDirection: 'column', width: w },
          ...lines.map(runs => line(t, theme, runs, w, align[c] ?? 'left', bold)),
        )
      }),
    )

  const rule = el(t.Text, { dimColor: true }, widths.map(w => '─'.repeat(w)).join(' '.repeat(gap)))

  return [row(header, true), rule, ...rows.map(cells => row(cells, false))]
}

function block(t: T, theme: Theme, b: Block, width: number, depth: number): RenderElement[] {
  switch (b.kind) {
    case 'paragraph':
      return [paragraph(t, theme, b.inline)]
    case 'heading':
      return heading(t, theme, b.level, b.inline, width)
    case 'code':
      return [code(t, b.language, b.source)]
    case 'quote':
      return quote(t, theme, b.blocks, width)
    case 'list':
      return list(t, theme, b.ordered, b.start, b.loose, b.items, width, depth)
    case 'table':
      return table(t, theme, b.align, b.header, b.rows, width)
    case 'rule':
      return [el(t.Text, { dimColor: true }, '─'.repeat(width))]
  }
}

/**
 * Draws blocks in a column with the rhythm between them: one blank row
 * between blocks, none inside a tight list item, and one more before a
 * top-level heading that follows something.
 */
function blocks(t: T, theme: Theme, bs: Block[], width: number, tight: boolean, depth: number): RenderElement[] {
  return bs.map((b, i) => {
    const props: Record<string, string | number> = { flexDirection: 'column' }
    if (!tight && i < bs.length - 1) {
      props.marginBottom = 1
    }
    if (b.kind === 'heading' && b.level <= 2 && i > 0 && !tight) {
      props.marginTop = 1
    }
    return el(t.Box, props, ...block(t, theme, b, width, depth))
  })
}

export function register(on: On, options: PluginOptions) {
  const measure = Number(options.measure ?? 96)
  const theme: Theme = {
    accent: String(options.accent ?? '#d97757'),
    measure: Number.isFinite(measure) && measure >= 20 ? measure : 96,
  }

  on('ui.render', { component: 'AssistantMessage' }, ($, e, next) => {
    if (e.surface !== 'terminal') {
      return next(e)
    }

    const parsed = parse(e.props.text)
    if (parsed.length === 0) {
      return next(e)
    }

    const t = $.ui.resolve(e)
    const columns = e.viewport?.columns ?? 80
    const width = Math.max(20, Math.min(theme.measure, columns - 4))

    return el(
      t.Box,
      { flexDirection: 'row' },
      el(t.Box, { width: 2 }, el(t.Text, { color: theme.accent }, e.props.isFirstOfReply ? '●' : ' ')),
      el(t.Box, { flexDirection: 'column', width }, ...blocks(t, theme, parsed, width, false, 0)),
    )
  })
}
