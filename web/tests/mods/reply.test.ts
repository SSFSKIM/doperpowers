import { describe, expect, test, tier } from 'claude-code/testing'

import { INLINE_MAX_TOKENS, failureReply, isWhole, replyFor, textFileOf } from '../../hooks/mods/reply'
import { DIR, NOW, PDF_DIR, page, pageText, pdf } from './fixtures'

tier('user')

describe('R1 or R2: the page whole or its outline', () => {
  test('the estimate decides at INLINE_MAX_TOKENS: at it the page comes whole, one past it the outline', async () => {
    expect(INLINE_MAX_TOKENS).toBe(5000)
    expect(isWhole(page({ tokens: 5000 }))).toBe(true)
    expect(isWhole(page({ tokens: 5001 }))).toBe(false)

    const atCap = replyFor(page({ tokens: 5000 }), { now: NOW, isAsked: false, page: pageText() })
    expect(atCap).toContain('\n---\nline 1\n')
    expect(atCap).not.toContain('Outline (')

    const past = replyFor(page({ tokens: 5001 }), { now: NOW, isAsked: false, page: pageText() })
    expect(past).toContain('Outline (lines · ~tokens · images):')
    expect(past).not.toContain('line 1\n')
  })

  test('R1 is the header, then the page, its image links made absolute and nothing else touched', async () => {
    const reply = replyFor(page(), { now: NOW, isAsked: false, page: pageText() })
    const [head, body] = reply.split('\n---\n')
    expect(head).toBe([`Saved ${DIR}/page.md`, '"The guide" · Example · 800 words · 40 lines · ~1.8k tokens · 1 image', 'Fetched now', ''].join('\n'))
    expect(body).toContain(`See ![A diagram](${DIR}/assets/01.png) here.`)
    expect(body).toContain('A path in prose: assets/01.png stays as written.')
    expect(body!.split('\n')).toHaveLength(40)
  })

  test('R1 makes a saved image\'s destination absolute whatever follows it: a title, spacing, angle brackets', async () => {
    const lines = Array.from({ length: 40 }, (_, i) => `line ${i + 1}`)
    lines[21] = [
      '![A diagram](assets/01.png "A title")',
      "![A diagram](assets/01.png 'single')",
      '![A diagram]( assets/01.png )',
      '![A diagram](<assets/01.png>)',
      '![A diagram](assets/01.png)',
      'and [a link](assets/01.pngx) stays',
    ].join(' ')
    const body = replyFor(page(), { now: NOW, isAsked: false, page: lines.join('\n') }).split('\n---\n')[1]!
    expect(body.split('\n')[21]).toBe(
      [
        `![A diagram](${DIR}/assets/01.png "A title")`,
        `![A diagram](${DIR}/assets/01.png 'single')`,
        `![A diagram]( ${DIR}/assets/01.png )`,
        `![A diagram](${DIR}/assets/01.png)`,
        `![A diagram](${DIR}/assets/01.png)`,
        'and [a link](assets/01.pngx) stays',
      ].join(' '),
    )
  })

  test('R2 lists each section by its range, indented by level, with its size and images, then the images by absolute path', async () => {
    const reply = replyFor(page({ tokens: 13_000, words: 5701, lines: 1012 }), { now: NOW, isAsked: false })
    expect(reply).toBe(
      [
        `Saved ${DIR}/page.md`,
        '"The guide" · Example · 5,701 words · 1,012 lines · ~13k tokens · 1 image',
        'Fetched now',
        '',
        'Outline (lines · ~tokens · images):',
        '  L1–8    (frontmatter)',
        '  L9–12   (top)                    0.6k',
        '  L13–30  ## How it works          3.1k · 1 image',
        '  L20–30    ### Automatic caching  0.9k · 1 image',
        '  L31–40  ## Pricing               <0.1k',
        'Images (Read one to see it):',
        `  ${DIR}/assets/01.png  L22  "A diagram"`,
        '',
        'Read the sections you need: Read(file_path, offset=<first line>, limit=<line count>).',
      ].join('\n'),
    )
  })

  test('R2 never needs the page text, says when headings were left out, and lists images that were not saved with why', async () => {
    const reply = replyFor(
      page({
        tokens: 9000,
        outlineOmitted: 96,
        images: [
          { url: 'https://example.com/pixel.gif', alt: '', line: 5, error: 'under 1 KiB (42 bytes)' },
        ],
      }),
      { now: NOW, isAsked: false },
    )
    expect(reply).toContain('  (96 deeper headings left out to keep the outline short; Grep the file for "^#" to list them all)')
    expect(reply).toContain('  https://example.com/pixel.gif  L5  not saved: under 1 KiB (42 bytes)')
    expect(reply).toContain('~9.0k tokens · 0 images')
  })

  test('a page with no images says so', async () => {
    expect(replyFor(page({ tokens: 9000, images: [] }), { now: NOW, isAsked: false })).toContain('Images (Read one to see it): none')
  })
})

describe('the header', () => {
  test('a cached copy gives its age and how to refresh, a rendered one says so, and each note follows on its own line', async () => {
    const reply = replyFor(page({ tokens: 9000, cached: true, rendered: true, notes: ['first note', 'second note'] }), { now: NOW, isAsked: false })
    const lines = reply.split('\n')
    expect(lines[2]).toBe('Cached, fetched 3 h ago (refresh: true fetches again) · rendered in headless Chromium')
    expect(lines.slice(3, 5)).toEqual(['first note', 'second note'])
  })

  test('without a title or a site, the site is the final URL\'s host', async () => {
    const reply = replyFor(page({ tokens: 9000, title: undefined, site: undefined }), { now: NOW, isAsked: false })
    expect(reply.split('\n')[1]).toBe('example.com · 800 words · 40 lines · ~9.0k tokens · 1 image')
  })
})

describe('R3: the answer', () => {
  const header = { firstLine: 1, lastLine: 40, totalLines: 40 }

  test('the answer, then which model answered from which lines of which file', async () => {
    const reply = replyFor(page({ cached: true }), { now: NOW, isAsked: true, summary: { isAnswered: true, text: 'It is 1024 [L22].\n', model: 'haiku', header } })
    expect(reply).toBe(
      [
        'It is 1024 [L22].',
        '',
        `— Answered by haiku from ${DIR}/page.md (lines 1–40 of 40). Read cited lines to check them.`,
        '"The guide" · Example · 40 lines · 1 image · fetched 3 h ago',
      ].join('\n'),
    )
  })

  test('past the cap it says which lines were read and that the rest was not', async () => {
    const reply = replyFor(page({ lines: 90_000 }), { now: NOW, isAsked: true, summary: { isAnswered: true, text: 'A.', model: 'haiku', header: { firstLine: 1, lastLine: 41_234, totalLines: 90_000 } } })
    expect(reply).toContain('(lines 1–41,234 of 90,000: the rest was not read)')
  })

  test('a first line cut to fit says so', async () => {
    const reply = replyFor(page({ lines: 1 }), { now: NOW, isAsked: true, summary: { isAnswered: true, text: 'A.', model: 'haiku', header: { firstLine: 1, lastLine: 1, totalLines: 1, cut: true } } })
    expect(reply).toContain('(line 1 cut short, of 1: the rest was not read)')
  })

  test('when the summary failed, the reply is R1 or R2 opening with why', async () => {
    const short = replyFor(page(), { now: NOW, isAsked: true, summary: { isAnswered: false, why: 'api-error 529, overloaded' }, page: pageText() })
    expect(short.split('\n').slice(0, 3)).toEqual(['The answer could not be made (api-error 529, overloaded), so here is the page itself.', '', `Saved ${DIR}/page.md`])
    expect(short).toContain('\n---\nline 1\n')

    const long = replyFor(page({ tokens: 9000 }), { now: NOW, isAsked: true, summary: { isAnswered: false, why: 'timed out after 120 s' } })
    expect(long.split('\n')[0]).toBe('The answer could not be made (timed out after 120 s), so here is the page itself.')
    expect(long).toContain('Outline (lines · ~tokens · images):')
  })
})

describe('replies by kind', () => {
  test('text and json pages work on their main file, with no image list', async () => {
    const text = page({ kind: 'text', file: `${DIR}/page.txt`, tokens: 9000, images: [], outline: [{ level: 0, title: '(body)', line: 1, endLine: 40, tokens: 9000, images: 0 }] })
    expect(textFileOf(text)).toBe(`${DIR}/page.txt`)
    const reply = replyFor(text, { now: NOW, isAsked: false })
    expect(reply).toContain('  L1–40  (body)  9.0k')
    expect(reply).not.toContain('Images')
    expect(textFileOf(page({ kind: 'json', file: `${DIR}/page.json` }))).toBe(`${DIR}/page.json`)
  })

  test('a PDF with text: R1 or R2 over page.txt, one outline entry a page, naming page.pdf and how to read its pages', async () => {
    expect(textFileOf(pdf())).toBe(`${PDF_DIR}/page.txt`)
    const long = replyFor(pdf(), { now: NOW, isAsked: false })
    expect(long.split('\n').slice(0, 3)).toEqual([
      `Saved ${PDF_DIR}/page.txt`,
      `The PDF: ${PDF_DIR}/page.pdf; Read(file_path, pages: "N-M") shows its pages as rendered.`,
      'arxiv.org · PDF · 2 pages · 6,000 words · 801 lines · ~15k tokens',
    ])
    expect(long).toContain('  L1–60    page 1  1.2k')
    expect(long).toContain('  L61–120  page 2  1.1k')
    expect(long).not.toContain('Images')

    const short = replyFor(pdf({ tokens: 900 }), { now: NOW, isAsked: false, page: 'the text' })
    expect(short).toContain(`Saved ${PDF_DIR}/page.txt`)
    expect(short).toContain('\n---\nthe text')

    const capped = replyFor(pdf({ outlineOmitted: 220 }), { now: NOW, isAsked: false })
    expect(capped).toContain('  (220 more pages not listed)')
    expect(capped).toContain('PDF · 222 pages')
  })

  test('a PDF with text and a prompt is answered from page.txt', async () => {
    const reply = replyFor(pdf(), { now: NOW, isAsked: true, summary: { isAnswered: true, text: 'Eight heads [L300].', model: 'haiku', header: { firstLine: 1, lastLine: 801, totalLines: 801 } } })
    expect(reply).toContain(`— Answered by haiku from ${PDF_DIR}/page.txt (lines 1–801 of 801).`)
  })

  const note = 'no text extracted: the PDF has no text layer'
  const scan = () => pdf({ text: undefined, lines: undefined, tokens: undefined, outline: undefined, words: undefined, notes: [note] })

  test('a PDF without text: the header, the PDF, and how to read it by page; with a prompt, opening with why it cannot answer', async () => {
    expect(textFileOf(scan())).toBeUndefined()
    const lines = [
      'arxiv.org · PDF',
      'Fetched now',
      `Saved ${PDF_DIR}/page.pdf`,
      'No text extracted here (the PDF has no text layer); Read the PDF by page: Read(file_path, pages: "1-5").',
    ]
    expect(replyFor(scan(), { now: NOW, isAsked: false })).toBe(lines.join('\n'))
    expect(replyFor(scan(), { now: NOW, isAsked: true })).toBe(['Cannot answer from a PDF without its text.', ...lines].join('\n'))
  })

  const image = () =>
    page({ kind: 'image', file: `${DIR}/image.png`, contentType: 'image/png', title: undefined, site: undefined, words: undefined, lines: undefined, tokens: undefined, outline: undefined, images: [] })

  test('an image: the header and the file to Read; with a prompt, opening with why it cannot answer', async () => {
    const lines = ['example.com', 'Fetched now', `Image saved: ${DIR}/image.png. Read it to see it.`]
    expect(replyFor(image(), { now: NOW, isAsked: false })).toBe(lines.join('\n'))
    expect(replyFor(image(), { now: NOW, isAsked: true })).toBe(['A small model cannot read images.', ...lines].join('\n'))
  })

  const binary = () =>
    page({ kind: 'binary', file: `${DIR}/file.zip`, contentType: 'application/zip', bytes: 3_250_000, title: undefined, site: undefined, words: undefined, lines: undefined, tokens: undefined, outline: undefined, images: [] })

  test('a binary: the header and what was saved; with a prompt, opening with why it cannot answer', async () => {
    const lines = ['example.com', 'Fetched now', `Saved ${DIR}/file.zip (application/zip, 3.1 MB); not a page.`]
    expect(replyFor(binary(), { now: NOW, isAsked: false })).toBe(lines.join('\n'))
    expect(replyFor(binary(), { now: NOW, isAsked: true })).toBe(['Cannot answer from an application/zip file.', ...lines].join('\n'))
  })
})

describe('R4: the error', () => {
  test('names the URL, what failed, and what the site said', async () => {
    expect(failureReply({ ok: false, url: 'https://example.com/x', status: 404, error: 'HTTP 404 Not Found', bodySnippet: 'Not Found \\ Example' })).toBe(
      'fetch failed: https://example.com/x: HTTP 404 Not Found\nThe site\'s response began: "Not Found \\ Example"',
    )
    expect(failureReply({ ok: false, url: 'http://127.0.0.1:8080/', error: 'refused: 127.0.0.1 resolves to a non-public address (127.0.0.1); for a local server use curl through Bash' })).toBe(
      'fetch failed: http://127.0.0.1:8080/: refused: 127.0.0.1 resolves to a non-public address (127.0.0.1); for a local server use curl through Bash',
    )
  })
})
