import { test } from 'node:test'
import assert from 'node:assert/strict'
import { markdownWithFrontmatter, htmlFrontmatter, extractHtml, extractFull } from '../src/extract.ts'
import { fixture } from './helpers.ts'

const F = '2026-10-25T00:00:00.000Z'

test('served markdown without frontmatter gets title, source and fetched, the title from its first heading outside code', () => {
  const md = '```bash\n# a comment\n```\n\n# Real Title\n\nText.\n'
  const { text, title } = markdownWithFrontmatter(md, 'https://x.test/a.md', F)
  assert.equal(title, 'Real Title')
  assert.equal(text, `---\ntitle: "Real Title"\nsource: "https://x.test/a.md"\nfetched: ${F}\n---\n\n` + md)
})

test('served markdown with its own frontmatter keeps it, takes its title, and gains source and fetched', () => {
  const md = '---\ntitle: Prompt caching\nurl: https://x.test/p\n---\n\nBody.\n\n```text\n# Request 2 caches\n```\n'
  const { text, title } = markdownWithFrontmatter(md, 'https://x.test/p', F)
  assert.equal(title, 'Prompt caching')
  assert.equal(text, `---\ntitle: Prompt caching\nurl: https://x.test/p\nsource: "https://x.test/p"\nfetched: ${F}\n---\n\nBody.\n\n\`\`\`text\n# Request 2 caches\n\`\`\`\n`)
  assert.equal(markdownWithFrontmatter('---\ntitle: "Quoted \\"one\\""\n---\nx\n', 's', F).title, 'Quoted "one"')
})

test('a code block whose language sits on a wrapper (Sphinx, GitHub) keeps it as the fence tag', async () => {
  const words = '<p>' + 'Some prose around the code so the extractor keeps the article and its blocks. '.repeat(6) + '</p>'
  const html = `<html><body><article><h1>Code</h1>${words}
    <div class="highlight-python3 notranslate"><div class="highlight"><pre><span></span><span class="k">import</span> asyncio
</pre></div></div>${words}
    <div class="highlight highlight-source-shell notranslate position-relative overflow-auto"><pre>npm install defuddle</pre></div>${words}
    <pre><code class="language-rust">fn main() {}</code></pre>${words}
    <div class="highlight highlight-text-html-basic"><pre>&lt;p&gt;hi&lt;/p&gt;</pre></div>${words}
    <div class="highlight-default notranslate"><div class="highlight"><pre>plain words</pre></div></div>${words}
  </article></body></html>`
  const { body } = await extractHtml(html, 'https://x.test/code', fetch)
  assert.match(body, /```python\nimport asyncio\n```/)
  assert.match(body, /```shell\nnpm install defuddle\n```/)
  assert.match(body, /```rust\nfn main\(\) \{\}\n```/)
  assert.match(body, /```html\n<p>hi<\/p>\n```/)
  assert.match(body, /```\nplain words\n```/)
})

test("a script-drawn chart's <noscript> image is kept, and a <noscript> without an image stays out", async () => {
  // The Rust blog's survey posts draw each chart with a script and put its PNG in <noscript>;
  // an extraction that runs no script is the reader that fallback is for.
  const words = '<p>' + 'Survey prose that frames the chart below and keeps the article long enough to extract. '.repeat(6) + '</p>'
  const html = `<html><body><article><h1>Survey</h1>${words}
    <div><div class="bar-chart" id="what-ide-do-you-use"><noscript>
<img alt="what-ide-do-you-use" height="500" src="what-ide-do-you-use.png"/>
</noscript></div>
    <div style="display: flex;"><span>[<a href="what-ide-do-you-use.png">PNG</a>]</span>&nbsp;<span>[<a href="what-ide-do-you-use.svg">SVG</a>]</span>&nbsp;<span>[<a href="what-ide-do-you-use-wordcloud.png">Wordcloud of open answers</a>]</span></div></div>
    <noscript><p>Please enable JavaScript to view the comments.</p></noscript>${words}</article></body></html>`
  const ex = await extractHtml(html, 'https://blog.example/2024/survey/', fetch)
  assert.match(ex.body, /!\[what-ide-do-you-use\]\(https:\/\/blog\.example\/2024\/survey\/what-ide-do-you-use\.png\)/)
  assert.doesNotMatch(ex.body, /enable JavaScript/)
})

test('a <noscript> copy of a lazy image already on the page is not added twice', async () => {
  const words = '<p>' + 'Prose around a lazily loaded photo, long enough for the extractor to keep the article. '.repeat(6) + '</p>'
  const html = `<html><body><article><h1>Photo</h1>${words}
    <img class="lazy" data-src="https://cdn.example/photo.jpg" alt="the photo"><noscript><img src="https://cdn.example/photo.jpg" alt="the photo"></noscript>${words}</article></body></html>`
  const ex = await extractHtml(html, 'https://blog.example/post/', fetch)
  assert.equal(ex.body.match(/photo\.jpg/g)?.length, 1, ex.body)
})

test("a <noscript> chart is kept when the same image shows elsewhere on the page, as a nav thumbnail", async () => {
  const words = '<p>' + 'Prose about the chart below, long enough for the extractor to keep the article as the content. '.repeat(6) + '</p>'
  const html = `<html><body><nav><a href="/posts/survey"><img src="https://blog.example/chart.png" alt="thumbnail"></a> <a href="/">Home</a></nav>
    <article><h1>Survey</h1>${words}<div class="chart"><noscript><img src="https://blog.example/chart.png" alt="the chart"></noscript></div>${words}</article></body></html>`
  const ex = await extractHtml(html, 'https://blog.example/posts/survey', fetch)
  assert.match(ex.body, /!\[the chart\]\(https:\/\/blog\.example\/chart\.png\)/, ex.body)
})

test("a direct-child <noscript> chart is kept beside a nested nav thumbnail of the same image, in an article or the body", async () => {
  const words = '<p>' + 'Prose about the chart below, long enough for the extractor to keep the article as the content. '.repeat(6) + '</p>'
  const nav = '<nav><a href="/posts/survey"><img src="https://blog.example/chart.png" alt="thumbnail"></a> <a href="/">Home</a></nav>'
  const inArticle = `<html><body><article>${nav}<h1>Survey</h1>${words}<noscript><img src="https://blog.example/chart.png" alt="the chart"></noscript>${words}</article></body></html>`
  const inBody = `<html><body>${nav}<h1>Survey</h1>${words}<noscript><img src="https://blog.example/chart.png" alt="the chart"></noscript>${words}</body></html>`
  for (const html of [inArticle, inBody]) {
    const ex = await extractHtml(html, 'https://blog.example/posts/survey', fetch)
    assert.match(ex.body, /!\[the chart\]\(https:\/\/blog\.example\/chart\.png\)/, ex.body)
  }
})

test('a lazy image wrapped alone beside its <noscript> copy is shown once', async () => {
  const words = '<p>' + 'Prose around a lazily loaded photo, long enough for the extractor to keep the article. '.repeat(6) + '</p>'
  const html = `<html><body><article><h1>Photo</h1>${words}
    <span class="lazy-wrap"><img loading="lazy" src="https://cdn.example/photo.jpg" alt="the photo"></span><noscript><img src="https://cdn.example/photo.jpg" alt="the photo"></noscript>${words}</article></body></html>`
  const ex = await extractHtml(html, 'https://blog.example/post/', fetch)
  assert.equal(ex.body.match(/photo\.jpg/g)?.length, 1, ex.body)
})

test("a registry page keeps its labeled dates and the dates in its sentences, and its chrome stays out", async () => {
  // deps.dev's package page: Defuddle took "Published / May 22, 2023" for an article's
  // byline, and cut the <time> out of "Package metadata as of …." and "Project metadata as of …".
  const ex = await extractHtml(await fixture('registry.html'), 'https://deps.dev/pypi/requests/2.31.0', fetch)
  assert.match(ex.body, /\n### Published\n\nMay 22, 2023\n\n### Description\n/, ex.body)
  assert.match(ex.body, /\nPackage metadata as of February 11, 2026\.\n/)
  assert.match(ex.body, /\nScorecard as of August 24, 2026\.\n/)
  assert.match(ex.body, /\nProject metadata as of October 21, 2026\.\n$/)
  for (const chrome of ['cookies', 'Privacy', 'Newer version available', '[Overview]', 'Search for open source']) assert.ok(!ex.body.includes(chrome), chrome)
  assert.ok(!ex.body.includes('\u2063'))
  assert.equal(ex.meta.published, '2026-02-11T16:44:52.000Z')
})

test('a date labeled by its line ("Release date:") is kept, and an unlabeled byline date is still dropped', async () => {
  const prose = '<p>' + 'This release contains a variety of fixes from the previous version, and the notes below describe each of them. '.repeat(4) + '</p>'
  const notes = await extractHtml(`<html><body><div class="sect1"><h2>E.16. Release 16</h2><p><strong>Release date:&nbsp;</strong>2023-09-14</p>${prose}${prose}</div></body></html>`, 'https://www.postgresql.org/docs/16/release-16.html', fetch)
  assert.match(notes.body, /^## E\.16\. Release 16\n\n\*\*Release date:\*\* 2023-09-14\n\nThis release/, notes.body)
  const post = await extractHtml(`<html><head><title>Notes on Gardening</title></head><body><article><h1>Notes on Gardening</h1><p><time datetime="2024-05-03">May 3, 2024</time></p>
    <div class="byline">By <a href="/jane">Jane Doe</a> · <time datetime="2024-05-03">May 3, 2024</time> · 5 min read</div>${prose}${prose}</article></body></html>`, 'https://blog.example/notes', fetch)
  assert.ok(!/May 3|Jane Doe/.test(post.body), post.body)
  assert.equal(post.meta.published, '2024-05-03')
})

test("a date beside the title stays Defuddle's, so it reaches published, and a hidden <time> goes with its text", async () => {
  const prose = '<p>' + 'The notes below describe each fix in this release and the reasons behind it, one by one. '.repeat(4) + '</p>'
  for (const lead of ['<p>Published: May 3, 2024</p>', '<h2>Published</h2><p>May 3, 2024</p>']) {
    const ex = await extractHtml(`<html><body><article><h1>Release Notes</h1>${lead}${prose}${prose}</article></body></html>`, 'https://x.test/notes', fetch)
    assert.equal(ex.meta.published, '2024-05-03T00:00:00+00:00', lead)
  }
  const para = '<p>This paragraph carries enough words of its own to be prose that the extractor keeps in the body.</p>'
  const ex = await extractHtml(`<html><body><article><h1>Notes</h1>${para.repeat(4)}<p>The fix was released <time hidden datetime="2024-05-03">May 3, 2024</time><span>yesterday</span>, and it is live for every user.</p></article></body></html>`, 'https://x.test/notes', fetch)
  assert.match(ex.body, /\nThe fix was released yesterday, and it is live for every user\.\n$/, ex.body)
})

test('a page that leaves out <html>, <head> or <body> extracts like the same page with them', async () => {
  // Escaped markup in the title and an escaped entity in an attribute: the repair must not write them out and read them back.
  const head = '<meta charset="utf-8"><title>Gardens &amp; Beds &lt;/title&gt;&lt;script&gt;</title><meta name="description" content="Beds &amp;copy; paths">'
  const article = '<article><h1>Gardens &amp; Beds</h1><p>' + 'Raised beds drain well, warm early in spring, and keep the paths clear of mud for the gardener. '.repeat(5) + '</p><pre>a &lt; b</pre></article>'
  const full = await extractHtml(`<!doctype html><html lang="en"><head>${head}</head><body>${article}</body></html>`, 'https://x.test/beds', fetch)
  assert.ok(full.words > 50)
  for (const page of [
    `<!doctype html><html lang="en"><head>${head}</head>${article}</html>`, // no <body>
    `<html lang="en">${head}${article}</html>`, // no <head> or <body>
    `<!doctype html>${head}${article}`, // no tags at all, as HTML allows
    `<head>${head}</head><body>${article}</body>`, // no <html>
  ]) {
    const ex = await extractHtml(page, 'https://x.test/beds', fetch)
    assert.equal(ex.body, full.body, page.slice(0, 40))
    assert.equal(ex.meta.title, 'Gardens & Beds </title><script>', page.slice(0, 40))
    assert.equal(ex.meta.description, 'Beds &copy; paths', page.slice(0, 40))
    if (page.includes('lang="en"')) assert.equal(ex.meta.language, 'en', page.slice(0, 40))
  }
})

test('html frontmatter escapes quotes and backslashes and ends with fetched', () => {
  const fm = htmlFrontmatter({ title: 'A "quoted" \\ title', site: 'S' }, 12, 'https://x.test/', F)
  assert.equal(fm, `---\ntitle: "A \\"quoted\\" \\\\ title"\nsite: "S"\nsource: "https://x.test/"\nword_count: 12\nfetched: ${F}\n---\n\n`)
})

// The whole page (full.md): Defuddle reads its contentSelector only after its own two ways of
// picking the article, either of which would leave the sidebar and its chart out of "the whole page".
const sidebar = `<aside class="sidebar"><h2>Specifications</h2><dl><dt>Boost clock</dt><dd>2.51 GHz</dd><dt>Memory</dt><dd>12 GB GDDR7</dd></dl>
  <figure><img data-src="/charts/fps-1440p.png" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="Average fps at 1440p"></figure></aside>`

test("the whole page is the body, though the page's JSON-LD carries the article's text", async () => {
  const text = 'The card under test draws less power than the one it replaces and holds its clocks under load. '.repeat(30).trim()
  const html = `<!doctype html><html><head><title>Bench</title>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"NewsArticle","headline":"Bench","articleBody":${JSON.stringify(text)}}</script></head>
    <body><nav><a href="/">Home</a> <a href="/reviews">Reviews</a></nav><div class="layout"><article><h1>Bench</h1><p>${text}</p></article>${sidebar}</div></body></html>`
  const url = 'https://bench.example/reviews/card'
  assert.doesNotMatch((await extractHtml(html, url, fetch)).body, /Boost clock/)
  const full = extractFull(html, url)
  assert.match(full.body, /The card under test draws less power/)
  assert.match(full.body, /Boost clock\n\n2\.51 GHz/)
  // The lazy chart by its real address, made absolute.
  assert.ok(full.body.includes('![Average fps at 1440p](https://bench.example/charts/fps-1440p.png)'), full.body)
  assert.ok(full.body.indexOf('The card under test') < full.body.indexOf('Boost clock'))
})

test('the whole page is the body on a page a site extractor claims (Wikipedia, its #mw-content-text)', async () => {
  const words = '<p>' + 'Viking 1 was the first spacecraft to land on Mars successfully and return images of its surface. '.repeat(8) + '</p>'
  const html = `<!doctype html><html><head><title>Viking 1 - Wikipedia</title><meta property="og:title" content="Viking 1 - Wikipedia"></head>
    <body><div id="content"><h1 id="firstHeading">Viking 1</h1><div id="bodyContent"><div id="mw-content-text">${words}</div></div></div>
    ${sidebar}<div id="footer"><p>This page was last edited on 3 March 2026.</p></div></body></html>`
  const url = 'https://en.wikipedia.org/wiki/Viking_1'
  assert.doesNotMatch((await extractHtml(html, url, fetch)).body, /Boost clock/)
  const full = extractFull(html, url)
  assert.match(full.body, /Viking 1 was the first spacecraft/)
  assert.match(full.body, /Boost clock\n\n2\.51 GHz/)
  assert.ok(full.body.includes('![Average fps at 1440p](https://en.wikipedia.org/charts/fps-1440p.png)'), full.body)
  assert.match(full.body, /last edited on 3 March 2026/)
})
