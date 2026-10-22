// Out-of-band Bun driver, never imported by the hooks. No source values or
// paths leave this process: stdout is the aggregate report alone.
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'
import { registerSecrets } from './secrets.tsx'
import { detect } from './secrets-detect.tsx'

const suffixes = new Set(['.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.json', '.py', '.txt', '.md', '.yaml', '.yml'])
const input = JSON.parse(fs.readFileSync(0, 'utf8'))
const indexed = new Map(input.indexed.map(([file, hash, size]) => [file, { hash, size }]))
const hooks = new Map()
registerSecrets((event, ...args) => {
  hooks.set(event, args.at(-1))
  return { catch() { return this } }
})
const signal = new AbortController().signal
const project = await mkdtemp(path.join(tmpdir(), 'guard-corpus-'))
const invoke = (event, e, result) => {
  const next = Object.assign(async x => result === undefined ? x : result, { signal })
  return hooks.get(event)($, e, next)
}
let verificationReason
const $ = {
  plugin: { root: path.resolve(import.meta.dir, '../..') },
  session: { cwd: async () => project },
  // No credential directories are read. The utility census is deliberately
  // independent of the synthetic credential regression/native acceptance.
  env: { get: async name => name === 'HOME' ? undefined : name === 'XDG_CACHE_HOME' ? input.cacheHome : undefined },
  clock: { sleep: (ms, options) => sleep(ms, undefined, options) },
  fs: {
    stat: async file => {
      const stat = await fs.promises.lstat(file)
      return { kind: stat.isFile() ? 'file' : 'dir', size: stat.size, mtimeMs: stat.mtimeMs }
    },
    read: file => fs.promises.readFile(file, 'utf8'),
  },
  process: { run: (argv, init = {}) => new Promise((resolve, reject) => {
    const child = spawn(argv[0], argv.slice(1), { cwd: project, env: { ...process.env, XDG_CACHE_HOME: input.cacheHome }, stdio: ['pipe', 'pipe', 'pipe'] })
    let stdout = '', stderr = ''
    const timer = setTimeout(() => { verificationReason = 'timeout'; child.kill('SIGKILL') }, init.timeoutMs ?? 5000)
    child.on('error', reject)
    child.stdout.on('data', data => { stdout += data })
    child.stderr.on('data', data => { stderr += data })
    child.on('close', code => {
      clearTimeout(timer)
      if (argv.includes('verify')) {
        try { verificationReason = JSON.parse(stdout).reason } catch { verificationReason ??= 'verifier_process' }
      }
      resolve({ stdout, stderr, exitCode: code ?? 1, isStdoutTruncated: false, isStderrTruncated: false })
    })
    child.stdin.end(init.stdin)
  }) },
}
// Independent fixture for the native 2.1.308 format, characterized by the
// native probe (including CRLF/tab-leading and partial Read). No claim that
// this driver itself is native acceptance.
function render(content, startLine) {
  return content.split('\n').map((line, i) => `${startLine + i}\t${line.replace(/\r$/, '')}`).join('\n')
}
function generics(text) { return detect(text).filter(span => span.kind === 'assignment') }
function counts(text) {
  const out = new Map()
  for (const span of generics(text)) {
    const value = text.slice(span.start, span.end)
    out.set(value, (out.get(value) ?? 0) + 1)
  }
  return out
}
function survivors(values, structured, appended) {
  const first = counts(structured), second = counts(appended), expected = new Map()
  for (const value of values) expected.set(value, (expected.get(value) ?? 0) + 1)
  let count = 0
  for (const [value, n] of expected) count += Math.min(n, first.get(value) ?? 0, second.get(value) ?? 0)
  return count
}
const corpora = {}
let call = 0
async function inspect(file, stats) {
  stats.files++
  let bytes
  try { bytes = fs.readFileSync(file) } catch { stats.unreadableFiles++; return }
  const source = bytes.toString('utf8')
  const matches = detect(source), generic = matches.filter(span => span.kind === 'assignment')
  stats.detectorMatches += matches.length
  stats.genericMatches += generic.length
  if (!generic.length) return
  const record = indexed.get(file)
  const original = record && record.size === bytes.length && record.hash === createHash('sha256').update(bytes).digest('hex')
  if (original) stats.originalContentMatches += generic.length
  // Supported offset/limit reads cover the census, not just the first page.
  // 64 KiB source pages fit below native Read's selected-byte limit. A single
  // overlong line is reported as a loss, never silently shortened or trusted.
  const lines = source.split('\n')
  let page = [], pageBytes = 0, startLine = 1, sourceOffset = 0, pageChars = 0
  const pageValues = (length) => generic.filter(span => span.start >= sourceOffset && span.end <= sourceOffset + length)
    .map(span => source.slice(span.start, span.end))
  const flush = async () => {
    if (!page.length) return
    const content = page.join('\n').replace(/\r\n/g, '\n').replace(/\r$/, '')
    // Track the original full-file matches, not new detections created by
    // cutting across a stronger multiline rule such as a PEM block.
    const values = pageValues(pageChars)
    const n = values.length
    if (n) {
      const id = `corpus_${++call}`
      const result = { type: 'text', file: { filePath: file, content, startLine, numLines: page.length, totalLines: lines.length } }
      const text = render(content, startLine)
      verificationReason = undefined
      const ran = await invoke('tool.call', { tool: 'Read', tool_use_id: id, file_path: file, offset: startLine, limit: page.length }, { result, text, ref: id })
      const finalContent = ran.result?.file?.content ?? ''
      const mapped = ran.ref === id ? text : render(finalContent, startLine)
      const row = await invoke('session.append', { door: 'tool-result', origin: { kind: 'tool', tool: 'Read' }, message: { type: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: mapped }] } })
      const kept = survivors(values, finalContent, row.message.content[0].content)
      stats.preservedBothPasses += kept
      if (kept < n) {
        const reason = !record ? 'not_indexed' : !original ? 'changed_bytes' : verificationReason ?? 'unsupported_rendering_or_stronger_detection'
        stats.losses[reason] = (stats.losses[reason] ?? 0) + n - kept
      }
      stats.readSlices++
    }
    startLine += page.length
    sourceOffset += pageChars
    page = []; pageBytes = 0; pageChars = 0
  }
  for (const line of lines) {
    const size = Buffer.byteLength(line) + 1
    if (pageBytes + size > 64 * 1024) await flush()
    if (size > 64 * 1024) {
      const n = pageValues(line.length).length
      if (n) stats.losses.read_slice_byte_limit = (stats.losses.read_slice_byte_limit ?? 0) + n
      sourceOffset += line.length + 1
      startLine++
      continue
    }
    page.push(line); pageBytes += size; pageChars += line.length + 1
  }
  await flush()
}
async function walk(dir, stats) {
  let entries
  try { entries = fs.readdirSync(dir, { withFileTypes: true }) } catch { stats.unreadableDirectories++; return }
  // Stable ordering makes successive reports directly comparable.
  entries.sort((a, b) => a.name.localeCompare(b.name))
  for (const entry of entries) {
    const file = path.join(dir, entry.name)
    if (entry.isDirectory()) await walk(file, stats)
    else if (entry.isFile() && suffixes.has(path.extname(entry.name))) await inspect(file, stats)
  }
}
try {
  await invoke('session.start', { cwd: project, isInteractive: false }, {})
  for (const [name, root] of Object.entries(input.roots)) {
    const stats = { files: 0, detectorMatches: 0, genericMatches: 0, originalContentMatches: 0, preservedBothPasses: 0, readSlices: 0, unreadableFiles: 0, unreadableDirectories: 0, losses: {} }
    corpora[name] = stats
    await walk(root, stats)
    if (stats.genericMatches !== stats.preservedBothPasses + Object.values(stats.losses).reduce((sum, n) => sum + n, 0)) {
      throw new Error('corpus accounting mismatch')
    }
    stats.preservationPercent = stats.genericMatches ? 100 * stats.preservedBothPasses / stats.genericMatches : null
  }
  console.log(JSON.stringify({ schemaVersion: 1, method: 'indexed-byte-equality-and-production-tool-append-hooks', slicePolicy: 'offset/limit pages at most 64 KiB; overlong lines counted as losses', credentialSources: 'excluded; tested separately with synthetic native acceptance', corpora }))
} catch {
  console.error('corpus pipeline failed (no file contents or paths logged)')
  process.exitCode = 1
} finally {
  await rm(project, { recursive: true, force: true })
}
