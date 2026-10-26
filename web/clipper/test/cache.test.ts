import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, readdir, readFile, utimes, stat } from 'node:fs/promises'
import { tmpdir, homedir } from 'node:os'
import { basename, join } from 'node:path'
import { cacheRoot, generationName, currentGeneration, readCurrent, recordCheck, beginBuild, publish, prune, readFailure, rememberFailure, FAILURE_MEMORY_MS } from '../src/cache.ts'

const tmp = () => mkdtemp(join(tmpdir(), 'clip-cache-'))

async function build(entry: string, fetchedAt: Date, opts: { now?: () => Date; rand?: () => string } = {}) {
  const t = await beginBuild(entry)
  await writeFile(join(t, 'page.md'), 'hello\n')
  return publish(t, entry, async dir => {
    await writeFile(join(t, 'meta.json'),JSON.stringify({ ok: true, dir, file: join(dir, 'page.md'), fetchedAt: fetchedAt.toISOString() }))
  }, opts)
}

test('the cache root is --cache-dir, else WEB_CACHE_DIR, else XDG_CACHE_HOME/claude-web, else ~/.cache/claude-web', () => {
  assert.equal(cacheRoot('/a', { WEB_CACHE_DIR: '/b' }), '/a')
  assert.equal(cacheRoot(undefined, { WEB_CACHE_DIR: '/b', XDG_CACHE_HOME: '/x' }), '/b')
  assert.equal(cacheRoot(undefined, { XDG_CACHE_HOME: '/x' }), '/x/claude-web')
  assert.equal(cacheRoot(undefined, {}), join(homedir(), '.cache', 'claude-web'))
})

test('a relative cache root, from the option or the environment, is made absolute', () => {
  assert.equal(cacheRoot('clips', {}), join(process.cwd(), 'clips'))
  assert.equal(cacheRoot(undefined, { WEB_CACHE_DIR: 'rel/web' }), join(process.cwd(), 'rel', 'web'))
  assert.equal(cacheRoot(undefined, { XDG_CACHE_HOME: 'xdg' }), join(process.cwd(), 'xdg', 'claude-web'))
})

test('generation names carry the UTC time to the millisecond and a random suffix', () => {
  assert.equal(generationName(new Date('2026-10-25T10:15:30.042Z'), 'a1f3'), '20261025T101530042Z-a1f3')
})

test('a published generation holds meta.json whose paths name it, and the build folder is gone', async () => {
  const entry = join(await tmp(), 'host', 'slug-12345678')
  const dir = await build(entry, new Date())
  const names = await readdir(entry)
  assert.deepEqual(names, [dir.split('/').pop()])
  const meta = JSON.parse(await readFile(join(dir, 'meta.json'), 'utf8'))
  assert.equal(meta.dir, dir)
  assert.equal(currentGeneration(entry), dir)
})

test('a refresh publishes a new generation, and the older one stays readable at its path', async () => {
  const entry = join(await tmp(), 'h', 'e')
  const first = await build(entry, new Date(), { now: () => new Date('2026-10-25T10:15:30.005Z') })
  const second = await build(entry, new Date(), { now: () => new Date('2026-10-25T10:15:30.006Z') })
  assert.notEqual(first, second)
  assert.equal(currentGeneration(entry), second)
  assert.equal(await readFile(join(first, 'page.md'), 'utf8'), 'hello\n')
})

test('two refreshes in the same second whose random suffixes sort in reverse leave the later one current', async () => {
  const entry = join(await tmp(), 'h', 'e')
  const earlier = await build(entry, new Date(), { now: () => new Date('2026-10-25T10:15:30.005Z'), rand: () => 'ffff' })
  const later = await build(entry, new Date(), { now: () => new Date('2026-10-25T10:15:30.009Z'), rand: () => '0000' })
  assert.ok(earlier.endsWith('-ffff') && later.endsWith('-0000'))
  assert.equal(currentGeneration(entry), later)
})

test('a name taken by another publish is not overwritten: the publish picks a new name', async () => {
  const entry = join(await tmp(), 'h', 'e')
  const fixed = () => new Date('2026-10-25T10:15:30.005Z')
  const a = await build(entry, new Date(), { now: fixed, rand: () => 'abcd' })
  let calls = 0
  const b = await build(entry, new Date(), { now: fixed, rand: () => (calls++ === 0 ? 'abcd' : 'abce') })
  assert.ok(a.endsWith('-abcd') && b.endsWith('-abce'))
  const metaA = JSON.parse(await readFile(join(a, 'meta.json'), 'utf8'))
  const metaB = JSON.parse(await readFile(join(b, 'meta.json'), 'utf8'))
  assert.equal(metaA.dir, a)
  assert.equal(metaB.dir, b)
})

test('two concurrent publishes both complete, and the newer is current', async () => {
  const entry = join(await tmp(), 'h', 'e')
  const [a, b] = await Promise.all([build(entry, new Date()), build(entry, new Date())])
  const gens = (await readdir(entry)).sort()
  assert.equal(gens.length, 2)
  for (const d of [a, b]) JSON.parse(await readFile(join(d, 'meta.json'), 'utf8'))
  assert.equal(currentGeneration(entry), join(entry, gens[1]))
})

test('the copy is the newest published generation, of any age, never a .tmp- folder', async () => {
  const entry = join(await tmp(), 'h', 'e')
  assert.equal(await readCurrent(entry), null)
  // Each generation is named by its own fetch time: two builds published in the
  // same millisecond would otherwise be ordered by their random suffixes.
  const old = new Date(Date.now() - 6 * 86400e3)
  const oldDir = await build(entry, old, { now: () => old })
  assert.equal((await readCurrent<{ dir: string }>(entry))?.meta.dir, oldDir)
  const recent = new Date(Date.now() - 3600e3)
  const dir = await build(entry, recent, { now: () => recent })
  // An interrupted build: a .tmp- folder newer than anything, with files in it.
  const t = await beginBuild(entry)
  await writeFile(join(t, 'page.md'), 'partial')
  const current = await readCurrent<{ fetchedAt: string; dir: string }>(entry)
  assert.equal(current?.meta.dir, dir)
  assert.equal(current?.generation, basename(dir))
  assert.equal(current?.checkedAt, undefined)
})

test('a check record counts for the generation it names, and a newer one replaces it', async () => {
  const entry = join(await tmp(), 'h', 'e')
  const first = await build(entry, new Date(Date.now() - 3 * 3600e3))
  const checkedAt = new Date(Date.now() - 60e3).toISOString()
  await recordCheck(entry, basename(first), checkedAt)
  assert.equal((await readCurrent(entry))?.checkedAt, checkedAt)
  const later = new Date().toISOString()
  await recordCheck(entry, basename(first), later)
  assert.equal((await readCurrent(entry))?.checkedAt, later)
  // A newer generation was not checked: the record names the one before it.
  await build(entry, new Date())
  assert.equal((await readCurrent(entry))?.checkedAt, undefined)
  // A record half written reads as none.
  await writeFile(join(entry, '.checked.json'), '{"generation":')
  const current = await readCurrent(entry)
  assert.ok(current)
  assert.equal(current.checkedAt, undefined)
})

test('prune deletes old generations, stale .tmp- folders and empty entries, keeps the rest, and stamps .pruned', async () => {
  const root = await tmp()
  const oldEntry = join(root, 'a.example', 'old-11111111')
  const liveEntry = join(root, 'b.example', 'live-22222222')
  await build(oldEntry, new Date(Date.now() - 8 * 86400e3))
  const oldGen = await build(liveEntry, new Date(Date.now() - 9 * 86400e3))
  const freshGen = await build(liveEntry, new Date(Date.now() - 86400e3))
  const staleTmp = await beginBuild(liveEntry)
  const hourAgo = new Date(Date.now() - 2 * 3600e3)
  await utimes(staleTmp, hourAgo, hourAgo)
  const activeTmp = await beginBuild(liveEntry)
  await writeFile(join(root, 'usage.jsonl'), '{}\n')

  const { removed } = await prune(root, { olderThanDays: 7 })
  assert.equal(removed, 3)
  const left = (await readdir(liveEntry)).sort()
  assert.deepEqual(left, [activeTmp.split('/').pop(), freshGen.split('/').pop()].sort())
  await assert.rejects(stat(oldGen))
  await assert.rejects(stat(join(root, 'a.example')))
  assert.ok((await stat(join(root, '.pruned'))).isFile())
  assert.ok((await stat(join(root, 'usage.jsonl'))).isFile())
})

test('a remembered failure answers under FAILURE_MEMORY_MS, is never taken for a generation, and a newer one replaces it', async () => {
  const entry = join(await tmp(), 'h', 'e')
  assert.equal(await readFailure(entry, FAILURE_MEMORY_MS), null)
  const now = Date.now()
  await rememberFailure(entry, { error: 'HTTP 404 Not Found', failedAt: new Date(now - 1000).toISOString() })
  assert.equal((await readFailure<{ error: string; failedAt: string }>(entry, FAILURE_MEMORY_MS, now))?.error, 'HTTP 404 Not Found')
  assert.equal(await readFailure(entry, FAILURE_MEMORY_MS, now + FAILURE_MEMORY_MS), null)
  assert.equal(currentGeneration(entry), null)
  await rememberFailure(entry, { error: 'HTTP 503 Service Unavailable', failedAt: new Date(now).toISOString() })
  assert.equal((await readFailure<{ error: string; failedAt: string }>(entry, FAILURE_MEMORY_MS, now))?.error, 'HTTP 503 Service Unavailable')
  // A file half written reads as no failure.
  await writeFile(join(entry, '.failed.json'), '{"error":')
  assert.equal(await readFailure(entry, FAILURE_MEMORY_MS, now), null)
})

test('concurrent failures of different lengths leave one whole record, and no file but it', async () => {
  const entry = join(await tmp(), 'h', 'e')
  for (let round = 0; round < 20; round++) {
    await Promise.all(Array.from({ length: 8 }, (_, i) =>
      rememberFailure(entry, { error: 'x'.repeat(1 + ((i * 997 + round * 31) % 4000)), failedAt: new Date().toISOString() })))
    const text = await readFile(join(entry, '.failed.json'), 'utf8')
    assert.doesNotThrow(() => JSON.parse(text), `round ${round}: ${text.length} bytes`)
  }
  assert.deepEqual(await readdir(entry), ['.failed.json'])
})

test('prune deletes a failure write a crash left before its rename once FAILURE_MEMORY_MS old, and the entry it leaves empty', async () => {
  const root = await tmp()
  const crashed = join(root, 'a.example', 'crash-11111111')
  const writing = join(root, 'b.example', 'writing-22222222')
  for (const entry of [crashed, writing]) {
    await mkdir(entry, { recursive: true })
    await writeFile(join(entry, '.failed-0123abcd.tmp'), '{"error":')
  }
  const before = new Date(Date.now() - FAILURE_MEMORY_MS - 60e3)
  await utimes(join(crashed, '.failed-0123abcd.tmp'), before, before)
  assert.deepEqual(await prune(root, { olderThanDays: 7 }), { removed: 0 })
  await assert.rejects(stat(join(root, 'a.example')))
  assert.deepEqual(await readdir(writing), ['.failed-0123abcd.tmp'])
})

test('prune deletes a failure no longer remembered, and the entry it leaves empty; a live one stays', async () => {
  const root = await tmp()
  const stale = join(root, 'a.example', 'gone-11111111')
  const live = join(root, 'b.example', 'down-22222222')
  await rememberFailure(stale, { failedAt: new Date(Date.now() - FAILURE_MEMORY_MS - 60e3).toISOString() })
  const before = new Date(Date.now() - FAILURE_MEMORY_MS - 60e3)
  await utimes(join(stale, '.failed.json'), before, before)
  await rememberFailure(live, { failedAt: new Date().toISOString() })
  assert.deepEqual(await prune(root, { olderThanDays: 7 }), { removed: 0 })
  await assert.rejects(stat(join(root, 'a.example')))
  assert.ok((await stat(join(live, '.failed.json'))).isFile())
})

test('prune deletes a check record whose generation is gone, and a check write a crash left; a record of a live generation stays', async () => {
  const root = await tmp()
  const gone = join(root, 'a.example', 'gone-11111111')
  const live = join(root, 'b.example', 'live-22222222')
  const oldGen = await build(gone, new Date(Date.now() - 9 * 86400e3))
  await recordCheck(gone, basename(oldGen), new Date(Date.now() - 8 * 86400e3).toISOString())
  const liveGen = await build(live, new Date(Date.now() - 86400e3))
  await recordCheck(live, basename(liveGen), new Date().toISOString())
  await writeFile(join(live, '.checked-0123abcd.tmp'), '{"generation":')
  const before = new Date(Date.now() - FAILURE_MEMORY_MS - 60e3)
  await utimes(join(live, '.checked-0123abcd.tmp'), before, before)
  assert.deepEqual(await prune(root, { olderThanDays: 7 }), { removed: 1 })
  await assert.rejects(stat(join(root, 'a.example')))
  assert.deepEqual((await readdir(live)).sort(), ['.checked.json', basename(liveGen)])
})

test('prune keeps a generation while the later of its fetch and its last check is within the age: a path a check handed out stays readable', async () => {
  const root = await tmp()
  const entry = join(root, 'a.example', 'checked-11111111')
  const unchecked = await build(entry, new Date(Date.now() - 10 * 86400e3))
  const checked = await build(entry, new Date(Date.now() - 9 * 86400e3))
  await recordCheck(entry, basename(checked), new Date(Date.now() - 86400e3).toISOString())
  // The record names one generation: an older one is pruned by its fetch time.
  assert.deepEqual(await prune(root, { olderThanDays: 7 }), { removed: 1 })
  assert.deepEqual((await readdir(entry)).sort(), ['.checked.json', basename(checked)])
  await assert.rejects(stat(unchecked))
  // Once its check is past the age too, it goes, and its record with it.
  assert.deepEqual(await prune(root, { olderThanDays: 7, now: Date.now() + 7 * 86400e3 }), { removed: 1 })
  await assert.rejects(stat(join(root, 'a.example')))
})

test('prune of a missing root removes nothing', async () => {
  const root = join(await tmp(), 'absent')
  assert.deepEqual(await prune(root, { olderThanDays: 7 }), { removed: 0 })
  await mkdir(root, { recursive: true })
})
