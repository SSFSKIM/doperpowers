import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import type { ChildProcess } from 'node:child_process'
import { readFile, writeFile, realpath } from 'node:fs/promises'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { FULL_LIMITS } from '../src/clip.ts'
import { startServer, tmpCache, send, fixture, entryContents } from './helpers.ts'

const CLI = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'cli.ts')
let server: Awaited<ReturnType<typeof startServer>>

before(async () => {
  server = await startServer({ '/article': send('text/html', await fixture('article.html')) })
})
after(() => server.close())

function run(args: string[], env: NodeJS.ProcessEnv = {}) {
  return new Promise<{ code: number; stdout: string; stderr: string }>(resolve => {
    execFile(process.execPath, [CLI, ...args], { env: { ...process.env, WEB_CHROME: 'none', ...env } }, (err, stdout, stderr) =>
      resolve({ code: err ? (err as { code?: number }).code ?? 1 : 0, stdout, stderr }))
  })
}

test('fetch prints exactly one JSON object and exits 0, for a page and for a failure', async () => {
  const cacheDir = await tmpCache()
  const env = { WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` }
  const good = await run(['fetch', `${server.origin}/article`, '--cache-dir', cacheDir], env)
  assert.equal(good.code, 0, good.stderr)
  const result = JSON.parse(good.stdout)
  assert.equal(result.ok, true)
  assert.equal(good.stdout.trim().split('\n').length, 1)

  const cached = await run(['fetch', `${server.origin}/article`, '--cache-dir', cacheDir], env)
  assert.equal(JSON.parse(cached.stdout).cached, true)
  const refreshed = await run(['fetch', '--refresh', `${server.origin}/article`, '--cache-dir', cacheDir], env)
  assert.equal(JSON.parse(refreshed.stdout).cached, false)

  const bad = await run(['fetch', `${server.origin}/missing`, '--cache-dir', cacheDir], env)
  assert.equal(bad.code, 0)
  assert.deepEqual(Object.keys(JSON.parse(bad.stdout)).sort(), ['bodySnippet', 'error', 'ok', 'permanent', 'status', 'url'])
})

test('a host that does not resolve is a failure result with exit 0, not a crash', async () => {
  const cacheDir = await tmpCache()
  const r = await run(['fetch', 'http://clipper-review-nxdomain.invalid/', '--cache-dir', cacheDir])
  assert.equal(r.code, 0, r.stderr)
  assert.equal(r.stderr, '')
  const result = JSON.parse(r.stdout)
  assert.equal(result.ok, false)
  assert.match(result.error, /^network error: .*clipper-review-nxdomain\.invalid/)
  assert.deepEqual((await entryContents(cacheDir)).map(p => p.split('/')[1]), ['.failed.json'])
})

test('a relative --cache-dir still gives absolute paths', async () => {
  const cwd = await tmpCache()
  const r = await new Promise<string>(resolve => execFile(process.execPath, [CLI, 'fetch', `${server.origin}/article`, '--cache-dir', 'clips'],
    { cwd, env: { ...process.env, WEB_CHROME: 'none', WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}` } }, (_e, stdout) => resolve(stdout)))
  const result = JSON.parse(r)
  assert.ok(result.dir.startsWith(join(await realpath(cwd), 'clips') + '/') || result.dir.startsWith(join(cwd, 'clips') + '/'), result.dir)
  assert.ok(result.file.startsWith('/'))
})

test('the cache root falls back to WEB_CACHE_DIR', async () => {
  const cacheDir = await tmpCache()
  const r = await run(['fetch', `${server.origin}/article`], { WEB_ALLOW_HOSTS: `127.0.0.1:${server.port}`, WEB_CACHE_DIR: cacheDir })
  assert.ok(JSON.parse(r.stdout).dir.startsWith(cacheDir + '/'))
})

test('numbered prints its header line, then the numbered lines up to the cap', async () => {
  const file = join(await tmpCache(), 'page.md')
  await writeFile(file, Array.from({ length: 50 }, (_, i) => `line ${i + 1} ` + 'x'.repeat(36)).join('\n') + '\n')
  const r = await run(['numbered', file, '--max-tokens', '120', '--reserve', '20'])
  assert.equal(r.code, 0, r.stderr)
  const [head, ...rest] = r.stdout.split('\n')
  const header = JSON.parse(head)
  assert.equal(header.firstLine, 1)
  assert.equal(header.totalLines, 50)
  assert.ok(header.lastLine > 0 && header.lastLine < 50)
  assert.equal(rest.filter(Boolean).length, header.lastLine)
  assert.match(rest[0], /^1\| line 1 /)
})

test('prune prints the count it removed', async () => {
  const r = await run(['prune', '--cache-dir', await tmpCache(), '--older-than-days', '7'])
  assert.equal(r.code, 0, r.stderr)
  assert.deepEqual(JSON.parse(r.stdout), { removed: 0 })
})

test('a usage error exits non-zero with the reason on stderr', async () => {
  const r = await run(['frobnicate'])
  assert.notEqual(r.code, 0)
  assert.match(r.stderr, /usage/i)
})

test("full.md's 5 s rule reads the article extraction's CPU time: a clipper stopped mid-extraction, as a loaded machine stops it, still saves full.md", async t => {
  // A page whose article takes about a second of CPU to extract (4,000 paragraphs; Defuddle grows faster than the page), and a sidebar outside it.
  const para = '<p>' + 'The garden log records each bed, what was sown there, when it sprouted, and how much it gave at harvest. '.repeat(3) + '</p>'
  const html = `<!doctype html><html><head><title>Log</title></head><body><nav><a href="/">Home</a></nav><main><article><h1>Log</h1>${para.repeat(4_000)}</article></main>`
    + `<aside><h2>Facts</h2><p>${'The shed holds the seed tins and the watering timer. '.repeat(12)}</p></aside></body></html>`
  let child: ChildProcess | undefined
  const timers: NodeJS.Timeout[] = []
  const site = await startServer({
    '/log': (_req, res) => {
      res.writeHead(200, { 'content-type': 'text/html' })
      // Once the page is sent, the clipper is extracting it: stopped there for longer than the limit, wall
      // time passes and CPU time does not, as when a busy machine leaves the process waiting for a core.
      res.end(html, () => timers.push(
        setTimeout(() => child?.kill('SIGSTOP'), 300),
        setTimeout(() => child?.kill('SIGCONT'), 300 + FULL_LIMITS.skipAfterMs + 700),
      ))
    },
  })
  t.after(async () => { for (const x of timers) clearTimeout(x); child?.kill('SIGCONT'); await site.close() })
  const cacheDir = await tmpCache()
  const out = await new Promise<string>(resolve => {
    child = execFile(process.execPath, [CLI, 'fetch', `${site.origin}/log`, '--cache-dir', cacheDir],
      { env: { ...process.env, WEB_CHROME: 'none', WEB_ALLOW_HOSTS: `127.0.0.1:${site.port}` } }, (_e, stdout) => resolve(stdout))
  })
  const result = JSON.parse(out)
  assert.equal(result.ok, true, out)
  assert.deepEqual(result.notes, [])
  assert.ok(result.full, out.slice(0, 600))
  assert.match(await readFile(result.full.file, 'utf8'), /The shed holds the seed tins/)
})
