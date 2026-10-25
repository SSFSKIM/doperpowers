import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { writeFile } from 'node:fs/promises'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { startServer, tmpCache, send, fixture } from './helpers.ts'

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
  assert.deepEqual(Object.keys(JSON.parse(bad.stdout)).sort(), ['bodySnippet', 'error', 'ok', 'status', 'url'])
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
