import type { EngineInterface, ToolResultOf } from 'claude-code'
import type { CharacterRange } from './secrets-detect'

const MAX_BYTES = 16 * 1024 * 1024
const STAGE_MS = 1500
const HEX = /^[a-f0-9]{64}$/
const absolute = (s: unknown): s is string => typeof s === 'string' && s.startsWith('/') && !s.includes('\0')
const inside = (path: string, root: string) => path === root || path.startsWith(`${root.replace(/\/$/, '')}/`)
const utf8 = (s: string) => new TextEncoder().encode(s)
const sha256 = async (s: string) => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', utf8(s))), b => b.toString(16).padStart(2, '0')).join('')

type TextRead = Extract<ToolResultOf<'Read'>, { type: 'text' }>

/** Shape compatibility, not an engine-version allowlist. */
export function textRead(result: unknown): TextRead | undefined {
  if (!result || typeof result !== 'object') return
  const r = result as TextRead
  const f = r.file
  if (r.type !== 'text' || !f || !absolute(f.filePath) || typeof f.content !== 'string' || !f.content ||
      !Number.isSafeInteger(f.startLine) || f.startLine < 1 || !Number.isSafeInteger(f.numLines) || f.numLines < 1 ||
      !Number.isSafeInteger(f.totalLines) || f.totalLines < f.startLine + f.numLines - 1 ||
      f.content.length > MAX_BYTES || f.content.split('\n').length !== f.numLines) return
  return r
}

function numbered(content: string, startLine: number, tabAware: boolean): string {
  const sep = tabAware && (content.startsWith('\t') || content.includes('\n\t')) ? ':' : '\t'
  return content.split('\n').map((line, i) => `${startLine + i}${sep}${line.replace(/\r$/, '')}`).join('\n')
}

/** Bind exactly one complete native numbered body, leaving wrappers guarded. */
export function bindReadRendering(read: TextRead, text: string, finalContent: string): { text: string; ranges: CharacterRange[] } | undefined {
  const matches: { start: number; end: number; tabAware: boolean }[] = []
  const seen = new Set<string>()
  for (const tabAware of [false, true]) {
    const body = numbered(read.file.content, read.file.startLine, tabAware)
    if (seen.has(body)) continue
    seen.add(body)
    for (let at = text.indexOf(body); at !== -1; at = text.indexOf(body, at + 1)) {
      const end = at + body.length
      if ((at === 0 || text[at - 1] === '\n') && (end === text.length || text[end] === '\n')) matches.push({ start: at, end, tabAware })
    }
  }
  if (matches.length !== 1) return
  const { start, end, tabAware } = matches[0]!
  const body = numbered(finalContent, read.file.startLine, tabAware)
  return { text: text.slice(0, start) + body + text.slice(end), ranges: [{ start, end: start + body.length }] }
}

type Roots = { generation: string; roots: string[] }
const rootsCache = new Map<string, { size: number; mtimeMs: number; value: Roots }>()
let running = 0

type ReadEvidence = { generation: string; digest: string; ranges: CharacterRange[] }

/**
 * All awaited provenance work shares this deadline, even an fs/env call that
 * never settles. Each continuation checks liveness before another host call.
 * process.run has no per-call signal: its remaining timeout kills the child,
 * and the engine also propagates the hook's abort signal. Keep its concurrency
 * slot until the process promise settles, even if the stage has been abandoned.
 */
export async function verifyRead($: EngineInterface, inputPath: string, read: TextRead, text: string,
  finalContent: string, projectRoot: string | undefined, signal: AbortSignal): Promise<ReadEvidence | undefined> {
  const deadline = performance.now() + STAGE_MS
  if (running >= 4 || signal.aborted || !absolute(inputPath) || !absolute(projectRoot)) return
  let live = true
  const active = () => live && !signal.aborted && performance.now() < deadline
  const timer = new AbortController()
  let abort!: () => void
  const stopped = new Promise<undefined>(resolve => { abort = () => { live = false; resolve(undefined) } })
  signal.addEventListener('abort', abort, { once: true })
  // Start before even the roots-file location is requested. This is not the
  // engine hook budget, which excludes in-flight filesystem/process calls.
  const timeout = $.clock.sleep(STAGE_MS, { signal: timer.signal }).then(() => { live = false; return undefined }, () => undefined)
  const work = async (): Promise<ReadEvidence | undefined> => {
    const binding = bindReadRendering(read, text, finalContent)
    if (!binding) return
    const contentBytes = utf8(read.file.content).length
    if (contentBytes > MAX_BYTES) return
    const xdg = await $.env.get('XDG_CACHE_HOME')
    if (!active()) return
    let caches: string[]
    if (absolute(xdg)) caches = [xdg]
    else {
      const home = await $.env.get('HOME')
      if (!active() || !absolute(home)) return
      // There is no platform noun in the hook API. Screening either standard
      // location is harmless: only the helper's platform cache grants evidence.
      caches = [`${home}/Library/Caches`, `${home}/.cache`]
    }
    let roots: Roots | undefined
    for (const cache of caches) {
      if (!active()) return
      const path = `${cache}/devcloud/guard-provenance/v1/roots.json`
      try {
        const stat = await $.fs.stat(path)
        if (!active()) return
        if (stat.kind !== 'file' || stat.size > 32 * 1024) continue
        const cached = rootsCache.get(path)
        let candidate = cached?.size === stat.size && cached.mtimeMs === stat.mtimeMs ? cached.value : undefined
        if (!candidate) {
          const raw = await $.fs.read(path)
          if (!active()) return
          if (raw.length > 32 * 1024) continue
          const r = JSON.parse(raw)
          if (r.schemaVersion !== 1 || r.policyVersion !== 1 || typeof r.generation !== 'string' || !r.generation || r.generation.length > 128 ||
              !Array.isArray(r.roots) || r.roots.length > 64 || !r.roots.every((root: unknown) => absolute(root) && root.length <= 4096)) continue
          candidate = { generation: r.generation, roots: r.roots }
          rootsCache.set(path, { size: stat.size, mtimeMs: stat.mtimeMs, value: candidate })
        }
        if (candidate.roots.some(root => inside(inputPath, root) && inside(read.file.filePath, root))) { roots = candidate; break }
      } catch { if (!active()) return }
    }
    if (!roots || !active() || running >= 4) return
    const request = {
      inputPath, filePath: read.file.filePath, projectRoot,
      startLine: read.file.startLine, lineCount: read.file.numLines, contentBytes,
      newline: read.file.content.includes('\r\n') ? 'preserve' : 'lf',
    }
    const stdin = JSON.stringify(request)
    if (utf8(stdin).length > 16 * 1024) return
    const remaining = Math.floor(deadline - performance.now())
    if (remaining < 1) return
    running++
    let answer
    try {
      answer = await $.process.run(['python3', '-I', `${$.plugin.root}/hooks/mods/secrets-provenance.py`, 'verify', '--timeout-ms', String(remaining)], { stdin, timeoutMs: remaining })
    } finally { running-- }
    if (!active() || answer.exitCode !== 0 || answer.isStdoutTruncated || answer.isStderrTruncated || answer.stdout.length > 16 * 1024) return
    const result = JSON.parse(answer.stdout)
    if (result.status !== 'verified' || result.schemaVersion !== 1 || result.policyVersion !== 1 || result.generation !== roots.generation ||
        !absolute(result.canonicalPath) || !roots.roots.some(root => inside(result.canonicalPath, root)) ||
        typeof result.fileSha256 !== 'string' || !HEX.test(result.fileSha256) || typeof result.sliceSha256 !== 'string' || !HEX.test(result.sliceSha256) ||
        !Number.isSafeInteger(result.byteSize) || result.byteSize < contentBytes || result.byteSize > MAX_BYTES ||
        result.startLine !== request.startLine || result.lineCount !== request.lineCount || result.contentBytes !== contentBytes || result.newline !== request.newline) return
    if (await sha256(read.file.content) !== result.sliceSha256 || !active()) return
    const digest = await sha256(binding.text)
    return active() ? { generation: result.generation, digest, ranges: binding.ranges } : undefined
  }
  try { return await Promise.race([work().catch(() => undefined), timeout, stopped]) }
  finally {
    live = false
    timer.abort()
    signal.removeEventListener('abort', abort)
  }
}

type Call = { agentId?: string; tool_use_id?: string }
export type ReadReceipt = ReadEvidence & { expires: number }
const keyOf = (call: Call) => typeof call.tool_use_id === 'string' && call.tool_use_id ? JSON.stringify([call.agentId ?? null, call.tool_use_id]) : undefined

/** Ephemeral authority only. Neither source text nor secret values are kept. */
export class ReadReceipts {
  private entries = new Map<string, ReadReceipt>()
  constructor(private now: () => number = () => performance.now()) {}
  reset() { this.entries.clear() }
  take(call: Call): ReadReceipt | undefined {
    const key = keyOf(call)
    if (!key) return
    const receipt = this.entries.get(key)
    this.entries.delete(key)
    return receipt && receipt.expires > this.now() ? receipt : undefined
  }
  issue(call: Call, evidence: ReadEvidence) {
    const key = keyOf(call)
    if (!key) return
    this.entries.delete(key)
    if (this.entries.size >= 256) this.entries.delete(this.entries.keys().next().value!)
    this.entries.set(key, { ...evidence, expires: this.now() + 60_000 })
  }
}

/** Unsupported tool-result representations never gain a range exception. */
export function resultText(content: unknown): string | undefined {
  if (typeof content === 'string') return content
  if (Array.isArray(content) && content.length === 1 && content[0]?.type === 'text' && typeof content[0].text === 'string') return content[0].text
}

export async function receiptRanges(receipt: ReadReceipt | undefined, text: string | undefined): Promise<readonly CharacterRange[] | undefined> {
  if (!receipt || text === undefined || performance.now() >= receipt.expires) return
  try { return await sha256(text) === receipt.digest && performance.now() < receipt.expires ? receipt.ranges : undefined }
  catch { return undefined }
}
