import type { ClipOk } from '../../hooks/mods/reply'

export const DIR = '/cache/claude-web/example.com/docs-guide-1a2b3c4d/20261025T080000000Z-ab12'
export const FETCHED_AT = '2026-10-25T08:00:00.000Z'
export const NOW = Date.parse(FETCHED_AT) + 3 * 3600_000

/** A clipper result (I1) for an html page, the fields a test changes given over it. */
export function page(over: Partial<ClipOk> = {}): ClipOk {
  return {
    ok: true,
    dir: DIR,
    file: `${DIR}/page.md`,
    kind: 'html',
    url: 'https://example.com/docs/guide',
    finalUrl: 'https://example.com/docs/guide',
    status: 200,
    contentType: 'text/html; charset=utf-8',
    fetchedAt: FETCHED_AT,
    cached: false,
    rendered: false,
    title: 'The guide',
    site: 'Example',
    words: 800,
    bytes: 6000,
    lines: 40,
    tokens: 1800,
    outline: [
      { level: 0, title: '(frontmatter)', line: 1, endLine: 8, tokens: 60, images: 0 },
      { level: 0, title: '(top)', line: 9, endLine: 12, tokens: 600, images: 0 },
      { level: 2, title: 'How it works', line: 13, endLine: 30, tokens: 3100, images: 1 },
      { level: 3, title: 'Automatic caching', line: 20, endLine: 30, tokens: 900, images: 1 },
      { level: 2, title: 'Pricing', line: 31, endLine: 40, tokens: 40, images: 0 },
    ],
    images: [{ file: 'assets/01.png', bytes: 20000, url: 'https://example.com/a.png', alt: 'A diagram', line: 22 }],
    notes: [],
    ...over,
  }
}

/** A page.md of 40 lines whose line 22 holds the image link. */
export function pageText(): string {
  const lines = Array.from({ length: 40 }, (_, i) => `line ${i + 1}`)
  lines[21] = 'See ![A diagram](assets/01.png) here.'
  lines[25] = 'A path in prose: assets/01.png stays as written.'
  return lines.join('\n')
}

export const PDF_DIR = '/cache/claude-web/arxiv.org/pdf-1706-03762v7-0f0f0f0f/20261025T080000000Z-cd34'

export function pdf(over: Partial<ClipOk> = {}): ClipOk {
  return page({
    dir: PDF_DIR,
    file: `${PDF_DIR}/page.pdf`,
    text: `${PDF_DIR}/page.txt`,
    kind: 'pdf',
    contentType: 'application/pdf',
    title: undefined,
    site: undefined,
    url: 'https://arxiv.org/pdf/1706.03762v7',
    finalUrl: 'https://arxiv.org/pdf/1706.03762v7',
    words: 6000,
    bytes: 2_200_000,
    lines: 801,
    tokens: 14_900,
    outline: [
      { level: 1, title: 'page 1', line: 1, endLine: 60, tokens: 1200, images: 0 },
      { level: 1, title: 'page 2', line: 61, endLine: 120, tokens: 1100, images: 0 },
    ],
    images: [],
    ...over,
  })
}
