import { test } from 'node:test'
import assert from 'node:assert/strict'
import { markdownWithFrontmatter, htmlFrontmatter, extractHtml } from '../src/extract.ts'

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

test('html frontmatter escapes quotes and backslashes and ends with fetched', () => {
  const fm = htmlFrontmatter({ title: 'A "quoted" \\ title', site: 'S' }, 12, 'https://x.test/', F)
  assert.equal(fm, `---\ntitle: "A \\"quoted\\" \\\\ title"\nsite: "S"\nsource: "https://x.test/"\nword_count: 12\nfetched: ${F}\n---\n\n`)
})
