# Web fetch: pages as files, answers that cite their lines

Today an agent reads the web through Claude Code's built-in `WebFetch`. It
fetches a URL, converts the page to markdown, and hands the agent only what
a small fast model says in answer to the agent's prompt. The agent never
sees the page itself. Exact parameter names, table values and code are
paraphrased or dropped, the page's images never reach it, it cannot go back
to a section without fetching again, and it cannot check the small model's
claim. After this change, agents fetch with a new tool, `mcp__web__fetch`,
which saves every page as a clean markdown file in the shape Obsidian Web
Clipper produces: frontmatter with title, author, site and source, the
article body, and its images downloaded beside it. The agent then picks one
of two modes per call:

- **With a `prompt`**: a small fast model answers it, as `WebFetch` does,
  but cites the saved file's line numbers, so the agent can check a claim
  with one `Read`.
- **Without a `prompt`**: a short page comes back whole. A long one comes
  back as its path and an outline (each heading's line range, size and
  images), so the agent reads only the sections it needs. It can view any
  image with `Read`, and it can hand the path to another agent.

Pages that only render with JavaScript are rendered in headless Chromium
when a plain fetch finds no content. Once evals show agents do at least as
well with the new tool as with `WebFetch`, `WebFetch` is turned off for
every session and subagent.

To see it working: start a session with the plugin
(`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 claude --plugin-dir web`) and ask it
to read a long documentation page. The agent gets the saved file's path and
outline, reads two sections of it with `Read`, and opens one of the page's
diagrams as an image (acceptance 6–8).

The human approved the design on 2026-10-25 in session
`web-fetch-replacement` (doperpowers on macbook), with these four choices:
one adaptive tool rather than two tools; `WebFetch` turned off with a
settings deny rule, but only after the evals pass; a headless-browser
fallback in v1, with logged-in pages left out; and a cache shared by every
session on the machine.

## Progress

- [x] (2026-10-25) Design closed and approved in the authoring session; the
  four choices above settled by the human. Spikes run: Defuddle 0.19.6 on
  three pages, a bundled Defuddle + linkedom script, and headless-shell
  `--dump-dom` on three JavaScript pages (Surprises & Discoveries).
- [x] (2026-10-25) Spec review round 1 (adversarial design review and
  buildability review): 9 findings, all applied (Decision Log).
- [x] (2026-10-25) The human confirmed the stricter eval gate, with the
  runs on `sol` at `xhigh` (Decision Log).
- [x] (2026-10-25) Spec review round 2: 2 findings, both applied (WebRTC
  egress, generation ordering). Converged: the findings narrowed to
  mechanisms with tests, so no round 3.
- [x] (2026-10-25) M1 — the clipper (`d6b71b78`, fix `40e1f6eb`), reviewed
  clean: 77 tests; acceptance 1–5 held live on this Mac. One review
  finding deferred as minor (image notation inside a code span that
  crosses a line break is taken for an image).
- [x] (2026-10-25) M2 — the tool: the `web` plugin and its mod (`61db8306`,
  `9e010af2`, fix `0c83c23f`), reviewed clean: 48 mod tests, the `web`
  gate green in CI; acceptance 6–8 held live in `claude -p` sessions.
- [ ] M3 — the evals, and acceptance 1–9.
- [ ] Branch review (doperpowers:review-code, high), merge.
- [ ] M4 — the switch-over, after the merge (acceptance 10).

## Acceptance

Each item is behavior a person can check. Commands run from the repository
root unless stated otherwise.

1. **A page becomes a file with its images.**
   `node web/bin/clip.mjs fetch https://www.anthropic.com/engineering/building-effective-agents`
   prints one JSON object with `"ok": true`. The folder it names holds
   `page.md`, whose frontmatter carries `title: "Building effective AI agents"`
   and `source:` with the URL, and an `assets/` folder holding at least 8
   images. Every image link in `page.md` points at `assets/…`. Opening
   `assets/01.*` with `Read` in a session shows a diagram.
2. **The cache answers repeat requests.** The same command again prints
   `"cached": true` within one second, and makes no network request. With
   `--refresh` it fetches again and prints `"cached": false` and a new
   `dir`. The first `dir` is still there.
3. **Pages that need JavaScript are rendered.** For `https://excalidraw.com/`,
   which a plain fetch extracts to 0 words, the result has `"rendered": true`
   and more than 20 words. With no Chromium findable
   (`WEB_CHROME=/nonexistent PLAYWRIGHT_BROWSERS_PATH=$(mktemp -d)`), the
   same command still returns `"ok": true`, with a note saying rendering was
   unavailable on this machine.
4. **PDFs are saved for Read.** An arXiv PDF URL (for example
   `https://arxiv.org/pdf/1706.03762v7`) gives `"kind": "pdf"`, a `page.pdf`,
   a `page.txt` holding its text where `pdftotext` exists, and an outline
   with one entry per PDF page.
5. **Failures say what failed and are not cached.** A URL that answers 404
   gives `"ok": false, "status": 404`, and nothing is left in the cache for
   it. `http://127.0.0.1:8080/` and `http://169.254.169.254/` each give
   `"ok": false` with an error that opens `refused:`, without a request
   being made.
6. **The tool replies in the shape the page needs.** In a session started
   with `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 claude --plugin-dir web`:
   - `mcp__web__fetch` is in the model's tool list.
   - Called without `prompt` on a short page, it returns the whole page,
     with image links rewritten to absolute paths.
   - Called on a long page
     (`https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching`),
     it returns the path and an outline. Each outline entry's first line, read
     from `page.md`, is that entry's heading.
7. **Prompted answers cite real lines.** Called with
   `prompt: "What is the minimum cacheable prompt length for each model?"`
   on the prompt-caching page, it returns an answer whose `[L…]` citations
   point at lines in `page.md` that hold the quoted values, and the reply
   carries the path.
8. **Subagents have it.** A subagent spawned in that session calls
   `mcp__web__fetch` and gets the same kind of reply.
9. **The evals pass.** `docs/doperpowers/specs/2026-10-25-web-fetch-eval-report.md`
   is committed and shows all four pass criteria met on the held-out final
   set (The evals, below).
10. **WebFetch is gone.** After the switch-over, a new session on this Mac
    has no `WebFetch` in its tool list. Its `mcp__web__fetch` runs without a
    permission prompt in the default mode. The claude-config repository
    (`~/.claude`) holds the commit making the change, which its sync carries
    to the other machines.

## Design

### Why the agent should get the page, not a paraphrase

`WebFetch` puts a small model between the agent and the page, and that model
sees only the prompt the agent wrote before it knew what the page held. The
agent cannot check the answer, and asking a second question costs a second
fetch. Prior art makes the opposite trade. The reference MCP `fetch` server
returns raw markdown in pages of 5,000 characters (`start_index`,
`max_length`). Anthropic's server-side web-fetch tool returns the full
document. ptc's `web_fetch` already returns the whole page to Python. A
file on disk improves on raw chunks: `Read` with an offset, `Grep`, the
image files, and handing a path to another agent all work on it with no new
tool surface. The outline makes the file navigable without reading it
whole.

The summary mode stays because it is the right tool for a page that is only
a means: "does this library support X", "what is the latest version".
Requiring line citations from it is the improvement. Anthropic's server-side
tools return citations for the same reason: a claim with a location can be
checked.

### The tool

`mcp__web__fetch`, registered by the `web` plugin's mod. Input:

```json
{
  "type": "object",
  "properties": {
    "url": { "type": "string", "format": "uri", "description": "The page to fetch (http or https)." },
    "prompt": { "type": "string", "description": "A question for a small fast model to answer from the page, citing its lines. Leave out to get the page itself." },
    "refresh": { "type": "boolean", "description": "Fetch again even when a copy saved in the last 24 hours exists." }
  },
  "required": ["url"]
}
```

Its description (what the model reads; M3's evals may change the wording,
and the Decision Log records each change):

```
Fetches a web page and saves it as a clean markdown file (images downloaded
beside it) in a cache every session and subagent on this machine shares.

- With `prompt`: a small fast model answers from the page, citing line
  numbers in the saved file. Use it when a gist or one fact is enough; Read
  the cited lines when the exact text matters.
- Without `prompt`: a short page comes back whole. A long one comes back as
  its path and an outline of line ranges and sizes; Read the sections you
  need. Use it for exact text, code, tables, or the whole argument.
- Images are files: Read one to see it.
- Pages that render with JavaScript are rendered in a headless browser.
  PDFs are saved for Read, by page.
- A copy saved in the last 24 hours is reused; `refresh: true` fetches again.
- Pages behind a login cannot be fetched. Local and private-network
  addresses are refused; use curl through Bash for a local server.
```

It is registered with `isDeferred: false`, so its schema is in the prompt's
tool list from the first turn. An agent doing research should reach for it
without a `ToolSearch` round trip first. The cost is its description, about
200 tokens per session. The alternative, deferring it as the engine defers
`WebFetch` in these sessions, was rejected because a tool meant to replace a
habit should be in sight. Subagents get it as they get every mod tool. A
subagent's call is served like the main session's.

**Replies.** The page's size estimate decides between the first two shapes.
Every size in this design is the same estimate: one token per four ASCII
characters, plus one token per non-ASCII character. It runs high on
purpose. Bytes divided by four would undercount Korean or Chinese text by
two to three times, and the summary's cap has to hold for those pages too.
Replies show it with `~`, because it is an approximation. The constant is
`INLINE_MAX_TOKENS = 5000`.

- **R1, the whole page** (no `prompt`, estimate ≤ 5,000): a header, then
  the main file's text. Image links are rewritten to absolute paths so
  `Read` takes them as they stand.

  ```
  Saved /Users/new/.cache/claude-web/simonwillison.net/2024-dec-19-one-shot-python-tools-1c9e04aa/page.md
  "Building Python tools with a one-shot prompt …" · simonwillison.net · 798 words · 61 lines · ~1.8k tokens · 1 image
  Fetched now

  ---
  <page.md, image links absolute>
  ```

- **R2, the outline** (no `prompt`, estimate > 5,000):

  ```
  Saved /Users/new/.cache/claude-web/docs.anthropic.com/en-docs-build-with-claude-prompt-caching-5b0e7d21/page.md
  "Prompt caching" · docs.anthropic.com · 5,701 words · 1,012 lines · ~13k tokens · 0 images
  Cached, fetched 3 h ago (refresh: true fetches again)

  Outline (lines · ~tokens · images):
    L1–12       (frontmatter)
    L13–40      (top)                                   0.6k
    L41–188     ## How prompt caching works             3.1k
    L60–102       ### Automatic caching                 0.9k
    …
  Images (Read one to see it): none

  Read the sections you need: Read(file_path, offset=<first line>, limit=<line count>).
  ```

  An entry is indented by its heading level. A section's range runs to the
  line before the next heading of the same or a higher level, so a parent's
  range contains its children's, and its token figure counts them too. The
  image list gives each image's file, the line it sits on, and its alt text
  when it has one. Past 80 outline entries, the deepest level is dropped
  until the outline fits, and a closing line says how many headings were
  left out. A page with no headings gets one entry for the whole body.
- **R3, the answer** (`prompt` given): the model's answer, then
  ```
  — Answered by haiku from <path> (lines 1–1,012 of 1,012). Read cited lines to check them.
  "Prompt caching" · docs.anthropic.com · 1,012 lines · 0 images · fetched 3 h ago
  ```
  When the page was longer than the summary's cap, the parenthesis says
  `lines 1–N of M: the rest was not read`. When the summary call fails, the
  reply is R2 (or R1) with a first line saying the answer could not be made
  and why (`api-error 529`, `timed out`). The agent still gets the page.
- **R4, the error**: the fetch failed. The text names the URL, the HTTP
  status or the network error, and up to 300 characters of the body when
  the site sent one. It reaches the model as an error result. M2 verifies
  which mechanism yields one: a hook that throws, or `{ deny }` with text
  that opens `fetch failed:`. The Decision Log records which was used.

Headers say `Fetched now`, or `Cached, fetched <age> ago (refresh: true
fetches again)`, and add `· rendered in headless Chromium` when the render
path produced the page. Each note the clipper returns (I1 `notes`) follows
the header as one line.

**Replies by kind.** R1–R3 work on the result's text file: the main file
for `html`, `markdown`, `text` and `json`, and `page.txt` for a `pdf` whose
text was extracted. The other cases never send binary content to the
model or to Haiku:

| Kind | Without `prompt` | With `prompt` |
|---|---|---|
| `pdf` with text | R1 or R2 over `page.txt`, the outline one entry per PDF page; the header also names `page.pdf` and says `Read(page.pdf, pages: "N-M")` shows the pages as rendered | R3 over `page.txt` |
| `pdf` without text | The header, the `page.pdf` path, and `No text extracted here (<the note>); Read the PDF by page: Read(file_path, pages: "1-5").` | The same, opening with `Cannot answer from a PDF without its text.` |
| `image` | The header and `Image saved: <path>. Read it to see it.` | The same, opening with `A small model cannot read images.` |
| `binary` | The header and `Saved <path> (<content type>, <size>); not a page.` | The same, opening with `Cannot answer from a <content type> file.` |

For these kinds, `lines`, `tokens` and `outline` are absent from I1, and
the header leaves them out.

### The cache

The cache root is the clipper's `--cache-dir` when given, else
`$WEB_CACHE_DIR`, else `${XDG_CACHE_HOME:-$HOME/.cache}/claude-web`. Each
requested URL gets one entry folder, and each fetch of that URL writes a
new generation folder inside it:

```
<root>/<host>/<slug>-<hash8>/            the entry: one per requested URL
  <generation>/                          one per fetch; the name is <UTC yyyymmddThhmmssSSSZ>-<4 random hex>,
                                         the time taken just before the publishing rename, to the millisecond
    page.md | page.txt | page.json | page.pdf (+ page.txt) | image.<ext> | file.<ext>
    assets/01.png, 02.jpg, …
    meta.json
  .tmp-<random>/                         a generation being built
<root>/.pruned                           stamp of the last prune
```

- **Key.** The URL as requested, normalized: scheme and host lowercased,
  default port and fragment dropped, query kept. `hash8` is the first 8 hex
  digits of its SHA-256, and `slug` is the path lowercased with each run of
  other characters than `a-z0-9` turned into one `-`, trimmed, at most 60
  characters (`index` for an empty path). The final URL after redirects
  is recorded in `meta.json`, not keyed: a page reached by two URLs is saved
  twice, which costs disk and nothing else.
- **Reuse.** The entry's current generation is the newest one by name
  that does not start with `.tmp-`. The name's millisecond timestamp
  orders generations by when they were published. Only two generations
  published in the same millisecond fall back to the random suffix, and
  those are equally fresh, so either may be current. A timestamp in whole
  seconds would let a refresh lose to the copy it replaced, by the luck of
  the suffix. When its `meta.json` `fetchedAt` is
  under 24 hours old, it answers without a request, unless `refresh` is
  set. The age goes into
  the header so the agent can judge staleness. 24 hours rather than
  `WebFetch`'s 15 minutes, because the cache is shared and the documentation
  and articles agents fetch rarely change within a day. `refresh` covers the
  page that just changed.
- **Writes publish whole generations.** The clipper builds a generation
  in `.tmp-<random>/` inside the entry, writes `meta.json` last, and then
  renames the folder to its generation name. That name never exists
  beforehand, so the rename is atomic. A rename onto an existing non-empty
  folder fails with `ENOTEMPTY` on macOS and Linux, which is why a
  generation never replaces another (Surprises & Discoveries).
  - A reader sees only complete generations.
  - Two agents fetching the same URL at once each publish their own, and
    the newer one becomes current.
  - An interrupted fetch leaves only a `.tmp-` folder, which nothing reads.
  - A refresh leaves the older generation in place, so a path an agent
    already cited or handed on stays readable until the prune.
  - The alternative, deleting the old folder and then renaming the new
    one in, lost because it leaves a moment with no copy at all, and an
    interrupted publish there destroys the copy that worked.
- **Pruning.** `clip.mjs prune` deletes generations whose `fetchedAt` is
  over 7 days old, `.tmp-` folders over an hour old, and entries left
  empty. The mod starts it at session start, without awaiting it, when
  `.pruned` is over a day old.
- Failed fetches (R4) are never cached.

The shared machine cache won over a per-session temporary folder (no
sharing, so a research subagent could not hand its parent a path) and over a
folder in the person's Obsidian vault (clips pile up where they keep their
own notes). The human chose it.

### The network boundary

The tool reaches public internet addresses only. Every request it makes
must resolve to a public address, and so must every request the page
makes it make:

- the agent's URL and each redirect hop;
- each image download;
- every request headless Chromium makes while rendering.

**Refused ranges:**
- IPv4: loopback `127.0.0.0/8`; `0.0.0.0/8`; private `10/8`, `172.16/12`
  and `192.168/16`; link-local `169.254/16`, which includes cloud metadata;
  CGNAT `100.64/10`, which is where Tailscale addresses live; multicast and
  reserved ranges;
- IPv6: `::1`, `fc00::/7`, `fe80::/10`, and the IPv4-mapped forms of all
  of the above.

Without this, a public page could put `http://127.0.0.1:…`, a tailnet
address or a metadata URL in an image or a redirect. The clipper would then
request it on its own, with no agent decision and no permission check in
between. The person's machines run local services (the sminos daemon, the
gateway relay) and tailnet hosts. `WebFetch` never downloads a page's
images, and it hands cross-host redirects back, so this tool widens the
exposure, and the boundary closes it.

- **The clipper's own requests** resolve the host first, check every
  address it resolves to, and connect to the address that was checked, by
  pinning it in the request's connection lookup. A DNS answer that changes
  between the check and the connection cannot slip a private address
  through.
- **Chromium's requests** go through a filtering HTTP proxy that the
  clipper runs in-process on `127.0.0.1` for the render's lifetime.
  - Chromium is launched with `--proxy-server` pointing at it and
    `--proxy-bypass-list="<-loopback>"`, which removes Chromium's built-in
    exemption for loopback addresses.
  - The proxy applies the same check to every plain HTTP request and every
    `CONNECT`, and connects to the address it checked.
  - **Traffic a proxy setting does not cover is switched off.** The proxy
    governs HTTP, HTTPS and WebSocket only. WebRTC opens UDP sockets
    directly: round-2 review reproduced a rendered page sending packets to
    a loopback UDP trap past the proxy. So Chromium also gets
    `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` and
    `--disable-quic`.
  - **The tests decide whether rendering ships at all.** They hold every
    egress channel the page can open to a trap: an `<img>`, a script's
    `fetch`, a WebSocket, and an `RTCPeerConnection` aimed at a UDP trap.
    They run against the Playwright headless shell installed here. If
    any channel reaches its trap with these flags, the flags are
    insufficient, the clipper ships with rendering off, and the Decision
    Log says why.
  - If the proxy cannot start, the page is not rendered, and a note says
    so. Rendering never runs unguarded.
- **A refused agent URL** is R4:
  `refused: <host> resolves to a non-public address (<address>); for a local server use curl through Bash`.
  A refused redirect is R4 too. A refused image keeps its remote link, with
  the error `refused: non-public address`.
- **Tests** need local servers, so `WEB_ALLOW_HOSTS` (a comma-separated
  list of `host:port`) exempts exactly those. It is a test seam, documented
  as such. The tests serve the page from an allowed port and a trap
  endpoint from a port not on the list, then assert the trap received
  nothing.

Restoring `WebFetch`'s per-domain permission prompts would not close this
hole, because the requests in question are the page's, not the agent's.

### From URL to file

The clipper is a Node script. One call runs these steps, each a module of
its own:

1. **Fetch.**
   - Node's `fetch` sends a current desktop-Chrome `User-Agent` and
     `Accept: text/markdown;q=1.0, text/html;q=0.9, */*;q=0.8`, so a site
     that serves markdown hands it over unconverted.
   - A 406 is retried once with a browser's default `Accept`.
   - Redirects are followed, at most 10 hops, and the final URL is
     recorded. `WebFetch` hands a redirect to another host back to the
     agent, but only because its permissions are per domain. This tool's are
     not.
   - Limits: 30 seconds and 50 MB. A status of 400 or above is R4.
2. **Route by content type** (the header, else a sniff of the first bytes):

   | Type | Main file | Then |
   |---|---|---|
   | `text/html`, `application/xhtml+xml` | `page.md` | Extract (step 3) |
   | `text/markdown`, `text/x-markdown` | `page.md` | Frontmatter prepended (title from the first `#` heading, `source`, `fetched`). Images (step 5) |
   | `text/plain`, `text/csv`, XML, feeds | `page.txt` | As served |
   | `application/json` | `page.json` | Pretty-printed |
   | `application/pdf` | `page.pdf` | `page.txt` from `pdftotext -layout` when it is on `PATH`, else a note. The outline has one entry per PDF page: `pdftotext` ends each page with a form feed |
   | `image/*` | `image.<ext>` | A note to Read it |
   | anything else | `file.<ext>` | A note naming the type and size |
3. **Extract.**
   - Defuddle parses the HTML on a linkedom document and returns markdown
     plus metadata. Defuddle is the extraction library Obsidian Web
     Clipper is built on, and linkedom is a DOM implementation for Node
     that Defuddle supports. Mozilla Readability lost because Defuddle
     keeps footnotes, math, code blocks and schema.org metadata
     consistently, and its output is the clipper format the human asked
     for.
   - The frontmatter carries the fields Defuddle's `--frontmatter` mode
     writes (title, author, site, source, domain, language, description,
     published, word_count), plus `fetched`.
4. **Render when the plain fetch found no content.** When the extracted
   body has fewer than 50 words, the page is rendered and extracted again,
   and the result with more words is kept.
   - **How it renders:** the Chromium binary runs headless with `--dump-dom`
     (it prints the page's DOM after its scripts ran), a fresh temporary
     `--user-data-dir` (so a running Chrome's profile lock never matters),
     `--virtual-time-budget=10000` and a 30-second timeout. It also gets
     the proxy and egress flags from "The network boundary", without
     which it does not run.
   - **Finding the binary:** `$WEB_CHROME`, when set, is the only
     candidate. An explicit setting is authoritative: a path that does not
     exist, or the value `none`, turns rendering off, and the note names
     `WEB_CHROME`. Unset, the clipper tries the newest
     `chromium_headless_shell-*` in the Playwright cache
     (`$PLAYWRIGHT_BROWSERS_PATH`, else `~/Library/Caches/ms-playwright` on
     macOS and `~/.cache/ms-playwright` on Linux); then Google Chrome at
     its macOS application path with `--headless=new`; then `chromium` or
     `google-chrome` on `PATH`.
   - With none found, the plain result stands, with the note
     `rendering unavailable on this machine: no Chromium found (set WEB_CHROME)`.
   - Driving the binary directly won over the Playwright library: it adds
     no dependency, and the spike showed `--dump-dom` is enough
     (Surprises & Discoveries).
5. **Images.**
   - **What is downloaded:** every image link in the extracted markdown,
     made absolute against the final URL, `data:` URIs included. Six at a
     time, 20 seconds and 15 MB each, at most 40 per page. Duplicates are
     saved once.
   - **Naming:** files are named by first appearance, `assets/01.<ext>`,
     with the extension taken from the response's content type.
   - **Links:** each link is rewritten to its local file. An image that
     fails to download, or comes back under 1 KiB (tracking pixels, spacer
     GIFs), keeps its remote link, and the image list records the error.
   - **SVGs** are saved as `.svg`. `Read` cannot display one, which is a
     known gap.
6. **Measure and write.** The line count, the size estimate and the outline
   are computed over the text file as written: the main file, or `page.txt`
   for a PDF. Frontmatter is included, so an outline line number is the line
   `Read` shows. Headings inside fenced code blocks are not headings. Then
   `meta.json` is written, and the generation is published (The cache).

**One deadline.** A whole `fetch` runs within `CLIP_DEADLINE_MS = 150000`.
Each stage takes the lesser of its own limit and the time left. Once the
page itself is in hand, the clipper always publishes it:

- downloads still pending at the deadline are abandoned, and their images
  keep remote links with the error `not downloaded: time budget`;
- a render the deadline cuts short leaves the plain result, with a note.

The mod's 180-second process limit sits 30 seconds above the deadline, so
it fires only on a clipper bug. Without the shared deadline, the stage
limits as written sum past it: 30 s fetch, 30 s render, and 40 images at
six at a time and 20 s each, which is 140 s.

### The summary

The mod answers a `prompt` with `$.model.complete({ model: 'haiku', … })`,
the session's own API client, so no key is needed. Like `WebFetch`'s small
model, it is text only. The model is given the system text below, the main
file with every line prefixed by its number (`12| …`), and then the
question:

```
You answer one question about a web page for another AI agent, from the page
text below, whose lines are numbered.
- Answer only from the page. If it does not answer the question, say so, and
  say what it does cover that comes closest.
- Quote exact names, values, numbers, code and commands verbatim; never
  paraphrase them.
- After each claim, cite the lines it rests on, as [L12] or [L12–18].
- Be as brief as the question allows.
```

Numbering the lines is what lets the citations be exact. Asking for
citations is the improvement over `WebFetch`.

- **Limits:** `maxTokens: 2048` and `timeoutMs: 120000`.
- **The cap:** lines are taken from the top until the estimated size of
  the numbered lines plus the question reaches
  `SUMMARY_MAX_TOKENS = 150000`, which leaves headroom in Haiku's context
  window. M2 checks the window of the model `haiku` resolves to, and the
  Decision Log records the figure. Lines past the cap are not sent, and R3
  says so.
- **Where the text comes from:** the mod gets it from the clipper
  (`clip.mjs numbered`, I1), not from `$.fs.read`. That call rejects any
  file over 4 MiB whole and has no offset, and a text page can be larger
  than that. The numbered excerpt is at most about 600 KB at the cap,
  within `$.process.run`'s 4 MiB stdout.
- **When the cap was not enough:** if the API still answers that the
  prompt is too long, the mod retries once at half the cap.
- **Usage log:** each call's `usage` is appended as one JSON line to
  `<cache root>/usage.jsonl`, with the time, the URL and the model. A
  completion's cost stays out of the session's cost total (the engine's
  documented behavior), and the evals add it back from this file.

### Packaging

The work splits in two because a mod has no Node and no DOM. It reaches the
outside world only through `$`, so Defuddle cannot run inside it.

- **`web/clipper/`** is a TypeScript package (its own `package.json` and
  lockfile) built by esbuild into one file, `web/bin/clip.mjs`, which is
  committed. A session therefore installs nothing and needs only `node` (20
  or later) on `PATH`. The Macs have Node 22, and devcloud hosts install
  NodeSource's LTS. A bundle built on first use into the plugin's data
  folder lost: it adds a network dependency and a failure mode to the first
  call on every machine. The bundle was 2.7 MB unminified in the spike, and
  minified it should come out around 1–2 MB. Rebuilding it from the lockfile
  is deterministic, and the `web` gate checks that the committed file
  matches its source.
- **`web/hooks/mods/`** is the mod. It registers the tool, runs
  `node <plugin root>/bin/clip.mjs fetch …` through `$.process.run` (no
  shell; `$.plugin.root` names the folder), turns the JSON into a reply,
  calls Haiku for `prompt`, and starts the prune.
  - When `node` cannot start, the reply is R4 naming the fix
    (`node not found on PATH`).
  - The mod's `timeoutMs` for the process is 180000, 30 seconds past the
    clipper's own deadline (From URL to file).
- Any agent can also run the clipper from Bash, including Codex, a ptc
  kernel, and a session without the mod. That keeps the conversion logic
  testable without a session.

The plugin is a new one in this marketplace, `web`, versioned on its own
like `to-human` and `sminos`, so the model sees the tool as
`mcp__web__fetch`. Placing the mod in the doperpowers plugin lost because
it would name the tool `mcp__doperpowers__fetch`, and it would tie a piece
of web infrastructure to the methodology plugin's releases.

### The evals

The switch-over waits for them: the human made passing evals the
condition. They compare two configurations on the same research tasks. The
eval also tests the tool's description, since that text decides whether an
agent chooses `prompt` or the file at the right times.

- **Tasks.** `web/evals/tasks.json` holds 40 tasks, 5 in each of 8
  categories.
  - **Split:** each category's tasks are split 2 for development and 3
    held out for the final gate (`"set": "dev" | "final"`).
  - **Development tasks** are what the tool and its description are built
    and tuned against.
  - **Final tasks** run once, on the frozen tool, and nothing is tuned
    against them. Tuning against the same tasks that decide the switch
    would select for this suite rather than for the web.
  - **Categories:**

  | Category | What the task needs |
  |---|---|
  | `exact-detail` | an exact name, value or limit deep in a long documentation page |
  | `table` | a value read out of a table |
  | `code` | a code example, verbatim |
  | `image` | a fact shown only in a diagram or chart |
  | `js` | content of a page that renders only with JavaScript |
  | `pdf` | a detail from a PDF |
  | `gist` | a quick gist, where a summary is enough |
  | `synthesis` | facts from two distant sections of one long page |

  - **Pages:** stable ones, such as versioned docs, arXiv versions, GitHub
    files at a commit SHA, and dated posts. At least 2 tasks are on
    Korean-language pages, since the human's agents read them.
  - **Questions:** each one names its URL, so the eval measures fetching
    and not searching.
  - **Answer keys:** each task carries 1–4 facts. The author checks each
    fact against the page's source, not only against the clipper's output,
    so a clipper bug cannot shape its own answer key, and records where it
    stands.
  - **Category checks:** an `image` fact must be absent from the page's
    text and alt attributes. A `js` page must extract to under 50 words with
    a plain fetch.
- **Configurations and runs.**
  - Configuration A has `WebFetch` only: the plugin loaded,
    `mcp__web__fetch` disallowed.
  - Configuration B has `mcp__web__fetch` only, with `WebFetch` disallowed.
  - In both, `Read`, `Grep` and `Glob` are allowed, and `Bash`, `WebSearch`
    and `Agent` are not, so neither configuration can route around its
    fetch tool with `curl`.
  - **The model:** every run uses `--model sol --effort xhigh`, the model
    and effort of the person's `sol-xhigh` worker agents. The human chose
    it on 2026-10-25, in place of the Sonnet and Opus runs first proposed.
    The tool is judged on the model the person's agents use.
  - On the final set, each task runs 4 times per configuration:
    24 × 2 × 4 = 192 runs.
  - On the development set, a round is 2 runs per configuration:
    16 × 2 × 2 = 64 runs.
  - Every run is `claude -p --output-format stream-json --verbose` in a
    temporary `HOME` and working directory, so no user instructions,
    plugins, hooks or cache bleed in. It runs with
    `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` and `--plugin-dir web`.
  - `sol` is served through the person's local model gateway, so the
    temporary `HOME`'s `settings.json` gets the gateway's keys copied from
    the `env` of the person's `~/.claude/settings.json`, and nothing else:
    `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, the
    `ANTHROPIC_DEFAULT_*_MODEL` mappings,
    `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY`,
    `CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING`, `ENABLE_TOOL_SEARCH`,
    and the two stream idle timeouts. The token is copied file to file and
    never printed.
  - Both configurations' small model (`WebFetch`'s and the mod's `haiku`)
    resolves through the same `ANTHROPIC_DEFAULT_HAIKU_MODEL` mapping, so
    the summary model is the same in both.
  - Each run also sets `PLAYWRIGHT_BROWSERS_PATH` to the real Playwright
    cache, since the temporary `HOME` hides it.
  - Six runs go at once, each with a 10-minute limit.
- **Grading.**
  - The grader sees the question, the answer key and the run's final text,
    with absolute paths and tool names masked so it cannot tell the
    configurations apart. It runs as `claude -p` on `opus`, through the
    same gateway environment, with no tools, and returns
    `{ "verdict": "correct" | "partial" | "wrong", "facts": { "<id>": true | false }, "note": "…" }`.
    The grader is from a different model family than the runner, so no
    model grades its own answers.
  - "Correct" means every key fact is present and right. "Partial" means
    some are.
- **Measures**, per run, from the stream:
  - the verdict;
  - the main model's tokens: input, output, cache read and cache creation,
    from the result line's per-model usage, which M3 verifies against the
    real output;
  - the fetch tool's calls and errors;
  - turns, duration and cost;
  - for B, the Haiku usage from `usage.jsonl`.
- **Pass**, judged on the final set. All four must hold:
  1. **B is not worse overall, with confidence.**
     - For each task, `d` = B's share of correct runs minus A's (each out
       of 4 runs).
     - The gate is the mean of `d` over the 24 tasks, with a 90% bootstrap
       interval: 10,000 resamples of tasks, seeded, so the report
       reproduces.
     - It passes when the interval's lower bound is at least −0.05, so B
       is at most 5 points worse at 90% confidence. The task is the
       resampling unit, because runs of one task are not independent.
     - A positive mean whose lower bound falls below −0.05 is
       *inconclusive*, not a pass. 16 more final tasks (2 per category,
       authored the same way) are added, run, and the gate is recomputed
       over all 40. If it is still inconclusive, the decision goes to the
       human.
  2. **No category trips the tripwire:** B has at most one fewer correct
     run than A, out of 12 each. Three tasks a category cannot bound a
     category's regression statistically, so this is a tripwire that
     catches a gross one. A trip is a fail, reported with the category's
     transcripts.
  3. No B run has a tool error the tool caused: an exception, an
     unparseable clipper result, or a timeout. Errors that are the site's
     own, such as an HTTP status, do not count.
  4. In `gist`, B's median main-model tokens are at most 1.5× A's.

  Cost and duration are reported per category and do not gate.
- **The pilot first.** Before any full round, 3 development tasks × 2
  configurations × 1 run project the cost of a development round and of
  the final run.
  - The projection covers tokens per model (the runner's `sol`, the
    grader's `opus`, the summaries' `haiku`) and the USD that the run
    output reports. `claude -p` may price a gateway model at nothing, so
    the projection says which figures are real.
  - It also confirms that `--model sol --effort xhigh` resolves in the
    temporary `HOME`. If it does not, the work stops and says why.
  - The projection goes up the dispatch chain to the main session, which
    tells the human before the spend.
  - Up to $150 of reported spend for one development round plus the final
    run, the work proceeds. Above that, it waits for the human's answer.
- **Development rounds.** Run a development round, read its transcripts,
  and fix what they show. The fix may touch the tool, its description or
  its constants (`INLINE_MAX_TOKENS`, the render threshold). Then run the
  whole development set again; a single category rerun would let noise
  pass. The tool is frozen when a development round meets criteria 2–4
  and shows B's mean `d` at 0 or above, or after three rounds. The Decision
  Log records the freeze and the commit.
- **The final run** goes once, on the frozen commit. If it fails, the work
  stops, and the report and transcripts go to the human. A fix followed by
  a second final run on the same tasks would be tuning against the gate,
  so that call is the human's.
- **Report.** `web/evals/report.py` writes
  `docs/doperpowers/specs/2026-10-25-web-fetch-eval-report.md`. It has:
  - a table per category and configuration: correct, partial and wrong;
    median tokens, cost and duration; fetch calls;
  - each criterion with its numbers and verdict, criterion 1 with its mean
    `d` and interval;
  - the runs that failed, each with a one-line reason;
  - a summary of each development round.

  Raw runs stay in `web/evals/runs/<UTC stamp>/`, which is gitignored.

### The switch-over

After the evals pass and the branch is merged (M4):

- In `~/.claude/settings.json`:
  - `WebFetch` goes into `permissions.deny`. A blanket deny removes a tool
    from the model's list: `NotebookEdit` is denied there today and is
    absent from sessions' tools.
  - `mcp__web__fetch` goes into `permissions.allow`.
  - `web@doperpowers` goes into `enabledPlugins`.
- The plugin is installed on this Mac, and claude-config's
  `sync/plugins.manifest.json` lists it so the other machines install it.
- The "For research, native WebSearch/WebFetch" line in
  `~/.claude/CLAUDE.md` names the new tool instead.
- `~/.claude` is the claude-config repository: committing there and letting
  its sync push it carries the change to the Mac mini and the devcloud
  hosts, which pull it.
- The human made passing evals the condition, so the switch is made
  without a further approval, and the numbers are reported.

### What it is not, and what waits

- **Not a browser.** It does not click, log in, or fill forms. That is
  `playwright-cli`'s job.
- **Not a crawler.** One URL per call.
- **Not search.** `WebSearch` stays as it is.
- **Logged-in pages:** clipping from the person's logged-in Chrome through
  the Playwright extension was offered and left out of v1, because agents
  would read pages with the person's credentials. It is a backlog ticket.
- **Prompt injection:** in the file mode, an agent reads raw page text with
  no small model in between, so an injected instruction reaches it. This is
  the same exposure as `curl` through `Bash`, and auto mode's classifier
  still reviews the agent's next actions.
- **Backlog tickets, filed at finish:**
  - Chromium headless shell and `poppler-utils` on the devcloud image.
    Hosts degrade with notes until then.
  - MAWS drawing `mcp__web__fetch` calls in its web cell, as it draws
    `WebFetch`.
  - SVG rasterizing.
  - The logged-in mode.

## Execution

### Constraints that bind every milestone

- Node 20 or later is the clipper's runtime. Its dependencies are
  `defuddle` and `linkedom`, plus esbuild and TypeScript to build. Nothing
  else ships without a Decision Log line saying why.
- The mod follows the conventions in `hooks/mods/CLAUDE.md` and
  `to-human/CLAUDE.md`:
  - `$` is the only way out of the module;
  - it is typechecked against the declarations the engine lays;
  - it is tested with `claude plugin test`.
- The plugin starts at `0.1.0`, written into its manifest and marketplace
  entry when they are created. After that, the version moves only through
  `scripts/bump-version.sh --plugin web`, in the same commit as the change
  it ships.
- A map row orients; detail goes beside the code. The root `CLAUDE.md`
  gets a one-sentence `web/` row, and `web/CLAUDE.md` carries the detail.
- Agent-facing text is behavior: the tool description, the reply shapes
  and the summary's system text. Change it only with the reason in the
  Decision Log. M3's evals are its pressure test.

### Plan of Work

#### M1 — the clipper

At its end, `node web/bin/clip.mjs fetch <url>` turns any page into a cache
folder and prints the I1 result, and `clip.mjs prune` cleans the cache.
Acceptance 1–5 hold on this Mac.

- **Touches:** `web/clipper/` (package, sources, tests, build script) and
  `web/bin/clip.mjs` (the committed bundle).
- **Produces:** I1 (the CLI and its result) and I2 (the cache layout and
  `meta.json`).
- **Decisions of its own:**
  - Each pipeline step in "From URL to file" is a module with its own tests.
  - Tests run on saved HTML fixtures, served from a local HTTP server
    started by the test, so they run offline and deterministically:
    - an article with images, including lazy `data-src` and `srcset`
      variants and a 1×1 pixel;
    - a JavaScript-shell page;
    - markdown, JSON, plain-text and PDF responses;
    - a redirect chain;
    - a 404 and a 406;
    - a page over 80 headings;
    - a heading inside a fenced code block.
  - Live checks against real sites are acceptance commands, not tests.
  - **Pitfalls seen while designing:**
    - Defuddle drops fenced-code language tags (seen in the spike). Keep
      them if Defuddle's options or a small post-pass allow; otherwise
      accept the loss and log it.
    - Next.js pages proxy images through `/_next/image?url=…`. Those URLs
      download as they are.
    - Image extensions come from the content type, not the URL.
- **Does not touch:** anything outside `web/clipper/` and `web/bin/`. No
  plugin manifest yet.
- **Proves:** acceptance 1–5. Its tests must also pin:
  - outline ranges nest and count frontmatter lines;
  - the 80-entry cap drops the deepest level first;
  - an image under 1 KiB keeps its remote link;
  - the token estimate counts a non-ASCII character as one token;
  - generations:
    - a refresh over an existing entry publishes a new generation, and
      the older one stays readable at the path already returned;
    - two concurrent fetches of one URL publish two complete generations,
      and the newer one is current;
    - two refreshes in the same second whose random suffixes sort in
      reverse order leave the later one current;
    - an interrupted build leaves only a `.tmp-` folder, which reuse
      ignores and prune removes;
    - a failed fetch publishes nothing;
  - the network boundary:
    - an agent URL, a redirect and an image pointing at a non-public
      address are each refused, with the trap endpoint receiving nothing;
    - a rendered page whose `<img>`, script `fetch`, WebSocket and
      `RTCPeerConnection` (aimed at a UDP trap) target non-public
      addresses gets nothing through to any trap;
    - a host that resolves to both a public and a private address is
      refused;
  - the deadline: a page whose 40 images all stall is still published
    before `CLIP_DEADLINE_MS`, its images marked `not downloaded: time budget`;
  - `numbered` stops at its cap and reports the last line it included;
  - `WEB_CHROME=none` turns rendering off, with the note.

#### M2 — the tool: the `web` plugin and its mod

At its end, a session started with the plugin has `mcp__web__fetch` and
gets R1–R4 from it, and the plugin is wired into the marketplace, the
version bump, the typecheck and CI.

- **Touches:**
  - the plugin itself: `web/.claude-plugin/plugin.json`,
    `web/hooks/hooks.json`, `web/hooks/mods/`, `web/tsconfig.json`,
    `web/CLAUDE.md`, `web/tests/`;
  - the repository's wiring: `.claude-plugin/marketplace.json` (the entry),
    `.version-bump.json` (a `web` plugin entry, and `web` excluded from the
    doperpowers audit), `tests/mods/typecheck.sh` (`web` in its plugin
    list), `.github/ci-kit.yml` (a `web` gate running the clipper tests,
    the bundle check and the mod tests; `web/**` paths in `mods-types`),
    and the root `CLAUDE.md` (the map row).
- **Consumes:** I1 and I2.
- **Produces:** I3 (the tool and its replies).
- **Decisions of its own:**
  - The reply formatting is a pure function of the clipper result plus the
    summary outcome, with no `$` in it, so it is tested without an engine.
  - Registered at `session.start` for interactive and headless sessions
    alike: the evals run headless. M2 verifies that the mod loads under
    `claude -p --plugin-dir`, since the evals depend on it, and records
    the evidence.
  - The summary's numbered page goes in `prompt`, after the fixed system
    text.
- **Pitfalls:**
  - A `tool.call` hook's own time is budgeted, but the `$.process.run` and
    `$.model.complete` it awaits are not.
  - `$.process.run` caps stdout at 4 MiB. The clipper's result is small
    because it never prints the page.
  - `$.fs.read` rejects files over 4 MiB. The mod reads a file with it only
    for R1, where `INLINE_MAX_TOKENS` keeps the file small. The summary's
    text comes from `clip.mjs numbered`.
- **Does not touch:** `~/.claude`, and the clipper's behavior. A clipper
  fix found here goes back into `web/clipper/` with its test.
- **Proves:** acceptance 6–8. Its tests must also pin:
  - the choice between R1 and R2 at `INLINE_MAX_TOKENS`;
  - absolute image paths in R1 only;
  - R3 when the summary fails (an R2 or R1 reply opening with the failure);
  - the cap's `lines 1–N of M` wording, with a text file over 4 MiB
    summarized through the real mod;
  - the half-cap retry on a prompt-too-long answer;
  - every row of "Replies by kind", with and without `prompt`;
  - a clipper killed by the process limit gives R4, not a hang;
  - each summary call appends one line to `usage.jsonl`;
  - prune started only when the stamp is a day old.
- **Records** in the Decision Log which mechanism gives R4 its error
  result, the context window of the model `haiku` resolves to, and the
  evidence that the mod loads under `claude -p --plugin-dir`.

#### M3 — the evals, and acceptance 1–9

At its end, the eval suite exists, has run in full, and its report shows the
pass criteria met. Any fixes it forced are in, and acceptance 1–9 have been
run as written.

- **Touches:** `web/evals/` (`tasks.json`, `run.py`, `grade.py` or the
  grader prompt, `report.py`, `.gitignore` for `runs/`), the eval report
  under `docs/doperpowers/specs/`, whatever the failures show needs fixing
  in `web/`, and the root `.gitignore`. Its unanchored `evals/` rule, meant
  for the separately cloned harness at the root, also ignores `web/evals/`.
  Anchor it as `/evals/`, then check with `git check-ignore` that the
  suite's sources are tracked and `web/evals/runs/` is ignored.
- **Consumes:** I3, and the plugin as M2 built it.
- **Produces:** I4 (the task and result formats) and the report.
- **Decisions of its own:**
  - The scripts are Python 3 standard library only, run with `python3 -I`.
  - The runner resumes: a run whose result file exists is skipped, so an
    interrupted suite continues.
  - Task authoring records, for every key fact, the line where it stands in
    the page's source or a description of the image that shows it.
  - Report the pilot's projection up the dispatch chain before the full run
    (The evals).
- **Pitfalls:**
  - The temporary `HOME` hides the Playwright cache and the person's
    gateway settings. Set `PLAYWRIGHT_BROWSERS_PATH`, and write the gateway
    keys listed under "Configurations and runs" into the temporary
    `settings.json`. Never print `ANTHROPIC_AUTH_TOKEN`; copy it file to
    file.
  - The gateway listens on this Mac's loopback interface, so the suite
    runs on this Mac.
  - The masked text the grader sees must not reveal the configuration
    through paths such as `.cache/claude-web`.
- **Does not touch:** `~/.claude`.
- **Proves:** acceptance 9. Then run acceptance 1–8 as written and record
  what they showed in Surprises & Discoveries, or in Progress when there
  was no surprise.

#### M4 — the switch-over (after the merge)

The main session runs this after the branch review and the merge, not the
plan executor, because it changes the person's configuration on every
machine. At its end, acceptance 10 holds.

- **Touches:** `~/.claude/settings.json`, `~/.claude/CLAUDE.md` and
  `~/.claude/sync/plugins.manifest.json`, all in the claude-config
  repository.
- **Steps:**
  - `claude plugin marketplace update doperpowers`, then
    `claude plugin install web@doperpowers --scope user`.
  - The settings edits from "The switch-over" above, and the CLAUDE.md line.
  - Commit in `~/.claude`.
  - A fresh `claude -p` session shows the result (Concrete Steps).
- **Proves:** acceptance 10.

### Concrete Steps

From the worktree root (`.claude/worktrees/web-fetch`):

```
# M1
cd web/clipper && npm ci && npm test && npm run build && cd ../..
git diff --exit-code web/bin/clip.mjs            # bundle matches source
node web/bin/clip.mjs fetch https://www.anthropic.com/engineering/building-effective-agents | python3 -m json.tool | head -30
#   "ok": true, "kind": "html", "cached": false, "images": [ … 8 entries with "file" … ]
node web/bin/clip.mjs fetch https://www.anthropic.com/engineering/building-effective-agents | grep -o '"cached": *true'
node web/bin/clip.mjs fetch https://excalidraw.com/ | grep -o '"rendered": *true'
WEB_CHROME=/nonexistent PLAYWRIGHT_BROWSERS_PATH="$(mktemp -d)" node web/bin/clip.mjs fetch --refresh https://excalidraw.com/ | grep -o 'rendering unavailable[^"]*'
node web/bin/clip.mjs fetch https://arxiv.org/pdf/1706.03762v7 | grep -o '"kind": *"pdf"'
node web/bin/clip.mjs fetch https://www.anthropic.com/this-page-does-not-exist | grep -o '"status": *404'
node web/bin/clip.mjs fetch http://127.0.0.1:8080/ | grep -o '"error": *"refused:[^"]*'
node web/bin/clip.mjs fetch http://169.254.169.254/ | grep -o '"error": *"refused:[^"]*'

# M2
bash web/tests/run.sh                            # clipper tests, bundle check, claude plugin test web
bash tests/mods/typecheck.sh --lay               # every plugin, web included
CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 claude -p --plugin-dir web --allowedTools=mcp__web__fetch \
  "Call mcp__web__fetch on https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching with no prompt and print its reply verbatim."
#   Saved …/page.md, "Prompt caching" …, Outline (lines · ~tokens · images): …

# M3
python3 -I web/evals/run.py --pilot              # 6 runs; prints the projected cost of a dev round and of the final run
python3 -I web/evals/run.py --set dev            # one development round, 64 runs, resumable
python3 -I web/evals/run.py --set final          # once, on the frozen commit: 192 runs, resumable
python3 -I web/evals/report.py web/evals/runs/<final stamp> --dev web/evals/runs/<dev stamp>... \
  > docs/doperpowers/specs/2026-10-25-web-fetch-eval-report.md
#   PASS 1 mean d +0.xx, 90% interval [-0.0x, +0.xx] … PASS 2 … PASS 3 … PASS 4 …

# M4 (main session, after merge; ~/.claude is claude-config)
claude plugin marketplace update doperpowers && claude plugin install web@doperpowers --scope user
claude -p "List the names of your tools that fetch web pages, one per line."
#   mcp__web__fetch   (and no WebFetch)
```

### Interfaces and Dependencies

**I1 — the clipper CLI.** Three subcommands:

- `node web/bin/clip.mjs fetch <url> [--refresh] [--cache-dir <dir>]`
  prints exactly one JSON object on stdout and exits 0, both when it
  succeeds and when the site fails or the network boundary refuses.
- `node web/bin/clip.mjs numbered <text file> [--max-tokens <n>] [--reserve <n>]`
  prints one JSON line, `{ "firstLine": 1, "lastLine": <n>, "totalLines": <m> }`,
  then the file's lines from the first, each prefixed `<number>| `, until
  the next line would push the estimate of what was printed plus
  `--reserve` (the question's estimate) past `--max-tokens`. When the first
  line alone would pass it, that line is printed cut to fit and the JSON
  line adds `"cut": true`, so a page of one huge line (minified XML, a
  one-line text file) still gives the summary something to read.
- `node web/bin/clip.mjs prune [--older-than-days 7] [--cache-dir <dir>]`
  prints `{ "removed": <n> }`, the number of generations and `.tmp-`
  folders it deleted.

A non-zero exit from any of them means a bug in the clipper, and its stack
is on stderr. The mod turns that into R4, naming the clipper failure.

Environment: `WEB_CACHE_DIR`, `XDG_CACHE_HOME`, `WEB_CHROME`,
`PLAYWRIGHT_BROWSERS_PATH`, and the test seam `WEB_ALLOW_HOSTS` (The
network boundary).

```ts
type ClipResult =
  | {
      ok: true
      dir: string            // absolute generation folder
      file: string           // absolute main file (page.md, page.txt, page.json, page.pdf, image.<ext>, file.<ext>)
      text?: string          // absolute page.txt beside a page.pdf, when extracted
      kind: 'html' | 'markdown' | 'text' | 'json' | 'pdf' | 'image' | 'binary'
      url: string            // as requested
      finalUrl: string
      status: number
      contentType: string
      fetchedAt: string      // ISO 8601, UTC
      cached: boolean
      rendered: boolean
      title?: string; site?: string; author?: string; published?: string; description?: string
      words?: number
      bytes: number          // of the main file
      // The next three describe the text file (the main file, or page.txt
      // for a PDF) and are absent when there is none: a PDF without
      // extracted text, an image, a binary.
      lines?: number
      tokens?: number        // the estimate: ceil(ASCII chars / 4) + non-ASCII chars
      outline?: OutlineEntry[]
      outlineOmitted?: number // headings the 80-entry cap left out; absent when 0
      images: ImageEntry[]
      notes: string[]        // one human-readable line each
    }
  | { ok: false; url: string; status?: number; error: string; bodySnippet?: string }

type OutlineEntry = { level: number; title: string; line: number; endLine: number; tokens: number; images: number }
// level 0 = the frontmatter or the text before the first heading; for a PDF, level 1 per page, title "page N"
type ImageEntry = { file?: string; url: string; alt: string; line: number; bytes?: number; error?: string }
```

**I2 — the cache.** The layout in "The cache". `meta.json` is the
`ok: true` result as written at fetch time, with `cached` absent. A
`fetch` answered from the cache prints it with `cached: true`. Its paths
are absolute and name the generation, which is never moved or rewritten
after it is published, so they stay valid until prune deletes the
generation.

**I3 — the tool.** `mcp__web__fetch`, with the input schema and
description in "The tool", replying R1–R4. Constants in the mod:
`INLINE_MAX_TOKENS = 5000`, `SUMMARY_MAX_TOKENS = 150000`, the summary
model `haiku`, `maxTokens 2048`, the process `timeoutMs 180000`.

**I4 — eval files.**

```ts
// web/evals/tasks.json
type Task = {
  id: string                      // "exact-detail-1"
  set: 'dev' | 'final'
  category: 'exact-detail' | 'table' | 'code' | 'image' | 'js' | 'pdf' | 'gist' | 'synthesis'
  lang: string                    // BCP 47, "en", "ko"
  url: string
  question: string                // names the URL
  facts: { id: string; claim: string; evidence: string }[]
}
// web/evals/runs/<stamp>/<task>.<arm A|B>.<model>.<rep>.json
type Run = {
  task: string; arm: 'A' | 'B'; model: 'sol'; effort: 'xhigh'; rep: number
  finalText: string; verdict?: 'correct' | 'partial' | 'wrong'; facts?: Record<string, boolean>; note?: string
  mainTokens: { input: number; output: number; cacheRead: number; cacheCreation: number }
  haikuUsage?: unknown[]          // B: the usage.jsonl lines of this run
  fetchCalls: number; fetchErrors: { text: string; toolCaused: boolean }[]
  turns: number; durationMs: number; costUsd: number
}
```

**Dependencies:**
- `defuddle` (0.19.x; the extraction Obsidian Web Clipper uses) and
  `linkedom` (its DOM in Node), bundled;
- `esbuild` and `typescript`, to build only;
- `pdftotext` (poppler), optional at run time;
- a Chromium binary, optional at run time (found as in step 4);
- the engine's `$.tool.register`, `$.process.run`, `$.model.complete`,
  `$.fs.read` and `$.plugin.root`.

## Surprises & Discoveries

- Observation: Defuddle 0.19.6's own CLI turns real pages into
  clipper-shaped markdown with frontmatter in 0.6–2 s. Images keep their
  remote URLs, and code fences lose their language tag.
  Evidence: `defuddle parse <url> --markdown --frontmatter` on simonwillison.net (7 KB, 1 image, 0.6 s), Anthropic's prompt-caching docs (52 KB, code blocks intact, 2.1 s), github.com/kepano/defuddle (14 KB, 1.4 s).
- Observation: Defuddle and linkedom bundle into one Node file that runs
  with no installed modules.
  Evidence: `bun build clip.mjs --target=node` → `clip.bundle.mjs 2.72 MB`; on anthropic.com/engineering/building-effective-agents it extracted 2,688 words and 8 image links (all `/_next/image?url=…`, empty alt).
- Observation: the Chromium headless shell that Playwright already
  downloaded renders JavaScript-only pages with `--dump-dom`, and pages
  that don't need it extract the same either way.
  Evidence: excalidraw.com 0 → 51 words; notion.notion.site public page 0 → 28 words (9.7 s at `--virtual-time-budget=10000`); vitejs.dev/guide 1,341 = 1,341 words.
- Observation: renaming a finished folder over an existing non-empty one
  fails on macOS. Replacing a cache folder in place therefore cannot be
  atomic, which is why each fetch publishes a new generation.
  Evidence: both spec reviewers' Node experiments on this Mac, 2026-10-25: `rename` → `ENOTEMPTY` (errno 66, `Directory not empty`), old folder kept.
- Observation: devcloud hosts have Node (NodeSource LTS) but neither
  Chromium nor poppler, so rendering and PDF text extraction degrade there,
  with notes, until the image adds them.
  Evidence: `devcloud/image/packages.sh` installs `nodejs` and no browser or `poppler-utils`.
- Observation: the R2 example's page is not what the spec drew.
  docs.anthropic.com redirects to `platform.claude.com/docs/…` and, to the
  clipper's `Accept`, serves `text/markdown` with its own frontmatter and
  MDX components. The prompt-caching page is 3,330 lines (~40.6k tokens),
  not 1,012, and its one image is an SVG. M2 and M3 expect that shape.
  Evidence: M1's live acceptance run, 2026-10-25 (task-1 report).
- Observation: the render egress proxy plus the WebRTC/QUIC flags hold.
  Evidence: M1's trap test, 3 of 3 runs on the Playwright headless shell:
  without the proxy, 5 TCP connections and UDP packets reached the traps;
  with the proxy but without the flags, 1–3 UDP packets reached the UDP
  trap; with the clipper's flags, 0 and 0. The UDP channel only shows when
  the page holds the render open (the test keeps a 2 s held request).
  Rendering ships on.
- Observation: Defuddle logs with `console.log`, onto stdout, where I1's one
  JSON object goes. The CLI routes `console.*` to stderr.
- Observation: acceptance 3's "no Chromium" `--refresh` leaves the unrendered
  copy current for 24 hours on a machine that can render. Harmless in use;
  whoever reruns the acceptance refreshes afterwards.
- Observation: npm on this Mac blocks dependency install scripts
  (`esbuild` postinstall); esbuild still works, its platform binary arriving
  as an optional dependency.
- Observation: the size estimate can run low. On digit-dense ASCII (a
  70,000-line file of row numbers and five-digit values) the API counted
  202,984 input tokens where the estimate said under 150,000, about 1.35×.
  Harmless with Haiku 5.5's 1M window; against a 200k model the half-cap
  retry is the backstop.
  Evidence: M2's live over-4 MiB summary run (task-2 report).
- Observation: a generation published before a clipper fix stays current
  for 24 hours. The eval runs each get their own cache through the
  temporary `HOME`, so this does not touch M3.
- Observation: R1 shows `---` twice in a row (the reply's separator, then
  `page.md`'s own frontmatter). Kept as drawn; M3's transcripts decide.

## Decision Log

- Decision: the verification for this spec. It gets one independent design
  review (`doperpowers:adversarial-reviewer`, since the spec is
  technical-heavy), and in the same round a buildability review of the
  execution section by `doperpowers:adversarial-reviewer`, because it has
  more than one milestone. The branch gets doperpowers:review-code at
  **high** before the merge. The stakes set the rung: once switched over,
  this tool is how every agent on every machine reads the web.
  Rationale: execspec's default, raised one rung for reach.
  Date/Author: 2026-10-25, authoring session (web-fetch-replacement).
- Decision: spec review round 1 applied (design review and buildability
  review, both "needs attention"). Changes:
  - generation folders replace in-place folder replacement (The cache);
  - a network boundary covers every request the tool and the page cause
    (new section);
  - one 150 s deadline replaces stage limits that summed to 200 s;
  - replies are defined per non-text kind;
  - the summary's text comes from `clip.mjs numbered` instead of
    `$.fs.read`, which rejects files over 4 MiB;
  - a token estimate that counts non-ASCII characters as one token each;
  - `WEB_CHROME` is authoritative when set, so acceptance 3 can turn
    rendering off;
  - the root `.gitignore`'s `evals/` rule is anchored so `web/evals/` is
    tracked.
  Rationale: each finding was checked against the code or by experiment
  and held. The rejected alternatives are named in the sections changed.
  Date/Author: 2026-10-25, authoring session.
- Decision: the eval gate changes from the approved count rule to
  three things: a held-out final set (40 tasks: 16 development, 24 final),
  a task-level bootstrap bound with a 5-point non-inferiority margin, and
  the per-category count kept as a tripwire (The evals).
  Rationale: the design review computed that the approved rule passes
  about 57.5% of the time when B is truly 10 points worse in a category
  (exact binomial, 12 runs, 90% vs 80%), and that fixing against the same
  tasks that gate selects for the suite. The alternative was the approved
  rule unchanged: cheaper, and it cannot tell "as good" from noise. The
  human confirmed the stricter bar on 2026-10-25, adding that the runs use
  `sol` at `xhigh` instead of Sonnet and Opus.
  Date/Author: 2026-10-25, authoring session; confirmed by the human.
- Decision: the eval runs go through the person's model gateway, with its
  keys copied into the temporary `HOME`, instead of `ANTHROPIC_API_KEY`.
  The grader stays `opus`.
  Rationale: `sol` is served only through the gateway, which follows from
  the human's choice of model. The grader is kept on another model family
  so `sol` does not grade its own answers. That is a reading of "use
  sol-xhigh as models" as the runs' model; if the human meant the grader
  too, it changes here.
  Date/Author: 2026-10-25, authoring session.
- Decision: spec review round 2 applied.
  - Rendering adds `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`
    and `--disable-quic`, and a trap test per egress channel decides
    whether rendering ships.
  - Generation names carry milliseconds, not seconds.

  Rationale: the reviewer reproduced WebRTC UDP reaching a loopback trap
  past the proxy with the installed headless shell. It also showed that
  whole-second names order same-second refreshes by their random suffix.
  The alternative for WebRTC, removing `RTCPeerConnection` with an
  injected script, lost because a page's own script can run before it.
  Date/Author: 2026-10-25, authoring session.
- Decision: execution pre-flight. M1 → M2 → M3 each consume the one
  before, so each is reviewed clean before the next dispatches. M3 is
  dispatched in two parts: the suite, the task authoring and the pilot,
  returning with the projection; then, once the projection has gone up
  the dispatch chain and the $150 rule allows it, the development rounds,
  the freeze, the final run and acceptance 1–8. A milestone executor
  cannot reach the main session itself, and the spec's pilot rule needs the
  projection to travel before the spend. Tests that need Chromium or
  `pdftotext` skip with a printed reason where those are absent (the CI
  runner has neither); the rendering egress tests are run on this Mac,
  where the Playwright headless shell is installed, and their output is
  the evidence that rendering ships.
  Rationale: the spec's pilot rule and the CI runner's environment.
  Date/Author: 2026-10-25, plan executor.
- Decision: M1's own decisions that later work reads (the full list of 26
  is in M1's commit `d6b71b78` and its task report):
  - Requests go through `node:http`/`https` with a pinned `lookup`, not the
    global `fetch`, which takes a lookup only through the `undici` package.
  - Defuddle's site extractors (YouTube transcripts and others) stay on,
    fetching through the guarded client, so they stay inside the boundary.
  - I1 gains `outlineOmitted` (headings the cap left out), which R2's
    closing line needs.
  - The cap drops the deepest level while more than one level remains;
    a single level still over 80 keeps its first 80. Level-0 entries are
    never dropped. A PDF of more than 80 pages therefore gets its first 80
    pages and `outlineOmitted`, rather than "one entry per PDF page"
    literally: an R2 of 300 page lines would defeat the outline's purpose.
  - Level-0 entries are `(frontmatter)`, `(top)` (only when the text before
    the first heading has a non-blank line) and `(body)`. `text` and `json`
    files are never read for headings.
  - Saved images are numbered contiguously by first appearance, so
    `assets/01.*` is always the first saved image. An unsaved image's link
    becomes its absolute URL. The image `Accept` leaves out AVIF, which
    `Read` cannot show.
  - Served markdown with its own frontmatter keeps that block and gains
    `source` and `fetched` in it; its title comes from there, else the first
    `#` heading outside code.
  - Reference-style images (`![a][ref]`) are found through their
    definitions and rewritten in place as inline images, leaving the
    definition alone (a link elsewhere may share it). Image notation in
    fences, inline code and escapes is not an image.
  - DNS and other connection failures are `ok: false` with
    `network error: …`, exit 0. Cache roots resolve to absolute paths.
  - A pre-pass copies fence languages from Sphinx/GitHub `highlight-*`
    wrappers onto the code block, recovering most of what Defuddle drops.
  - Text decodes by the declared charset (header, then `<meta>`), so EUC-KR
    pages read correctly.
  - A PDF whose text is only whitespace drops `page.txt`, with the note
    `no text extracted: the PDF has no text layer`, so the mod's "pdf
    without text" row applies.
  - Tests run under `node --test` with Node's type stripping (Node ≥ 22.18
    to run the tests; the bundle still targets Node 20), `tsc` as their
    type gate. The bundle is minified for whitespace and syntax only
    (2.1 MB), keeping identifiers readable in a stack.
  Rationale: each follows the spec's intent where it did not reach; see the
  task report for the alternatives.
  Date/Author: 2026-10-25, M1 executor, folded by the plan executor.
- Decision: `numbered` cuts an over-long first line to fit rather than
  printing nothing, and says so with `"cut": true` (I1). The whole-line rule
  left a page of one huge line (minified XML, a feed) with an empty summary.
  M2's R3 parenthesis names the cut (`line 1 cut short`).
  Rationale: an answer from most of a line beats no answer; the flag keeps
  it honest.
  Date/Author: 2026-10-25, plan executor, from M1's executor concern.
- Decision: M2's records and its own decisions.
  - **R4 is `{ deny }`** with text opening `fetch failed:`. It reaches the
    model as `is_error: true`, wrapped in `<tool_use_error>`, with no
    permission wording. A throwing hook is not a mechanism: the engine
    skips it and the call fails with the engine's text. The registration's
    `.catch` turns a step that throws before the page is in hand into the
    same deny. A summary request that throws is a failed summary, not a
    failed fetch: it gives R1 or R2 opening with why, as R3 promises
    (corrected after M2's review, 2026-10-25).
  - **`haiku` resolves to Haiku 5.5 with a 1M window** on this Mac
    (`ANTHROPIC_DEFAULT_HAIKU_MODEL` = `claude-haiku-5-5[1m]`, through the
    gateway); a live summary of 202,984 input tokens succeeded.
    `SUMMARY_MAX_TOKENS` stays 150,000.
  - **The mod loads under `claude -p --plugin-dir web`** (2.1.310): the
    init line lists `web` and `mcp__web__fetch`, the model called it on
    its first turn without `ToolSearch`, and all six live acceptance runs
    were `-p` runs. The Concrete Steps' `--allowedTools` needs its `=`
    form: spaced, it swallows the prompt (fixed above).
  - The mod is `fetch.tsx` (everything that takes `$`), `reply.ts` (the
    pure reply formatting) and `summary.ts` (the summary's text and pure
    steps). Its tests are staged in their own folder, since `claude plugin
    test web` would sweep the clipper's `node --test` files.
    `web/tsconfig.json` is the engine's file and is gitignored, like the
    other plugins'; the mod's own config is `web/hooks/mods/tsconfig.json`.
  - The summary request's `prompt` is `<page>…</page>` then
    `Question: …`; `--reserve` covers the system text, the frame and the
    question. A prompt-too-long answer is a 400 `invalid_request` (the
    engine passes no error text); the retry re-runs `numbered` at 75,000
    and skips the second ask when the half cap gives the same lines.
  - `usage.jsonl` gets one line per summary call, failed ones included,
    appended by `node -e` with `O_APPEND` (`$.fs` has no append), carrying
    `session` and, for a subagent, `agentId`.
  - The reply wording the spec left open is pinned by exact-text tests
    (task-2 report, decision 11); R3's cut case reads
    `(line 1 cut short, of M: the rest was not read)`.
  - **The CI `web` gate runs with `WEB_CHROME=none`**, so its Chromium
    tests skip with their reason: a runner's own Chrome sandbox would make
    the gate depend on the runner image, the shipping evidence comes from
    the Playwright headless shell on the Macs (M1's trap tests, rerun in
    M2's full local suite), and the render test once hit its 30 s limit
    under heavy load.
  Rationale: the spec's M2 records, and its intent where it left the
  wording open.
  Date/Author: 2026-10-25, M2 executor, folded by the plan executor.

## Outcomes & Retrospective

Pending — written at finish.
