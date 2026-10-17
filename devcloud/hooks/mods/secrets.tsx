import type { EngineInterface, Hook, On } from 'claude-code'

import { Handles } from './secrets-handles'
import type { Known } from './secrets-handles'
import {
  CREDENTIAL_FILES,
  GCLOUD_DIR,
  GCLOUD_SKIP,
  KEY,
  PROJECTS,
  STORE_DIR,
  credentialFields,
  credentialLabels,
  projectSlug,
  rootFromGit,
  storeValue,
} from './secrets-sources'
import type { Format } from './secrets-sources'

/**
 * The secrets guard. Values are replaced by handles wherever its hooks reach
 * before text leaves the process: a tool's result as the model reads it and
 * as the transcript keeps it (`toolUseResult`), every row appended to the
 * conversation, an oversized output's persisted file, the system prompt's
 * sections, the first message's context blocks, and each attachment as a
 * request carries it. No call is refused for touching the store: a command
 * that prints a value is caught at its output. Handles in the input of a
 * Write, Edit, MultiEdit, NotebookEdit or Bash call are restored to their
 * bytes before it runs, so a file edited through a handle keeps its secret.
 *
 * The values known: those stored through `/secret` (`cua`'s store, read here,
 * Interfaces I1), those in well-known credential files, re-read when they
 * change, and token-shaped strings anywhere (secrets-detect).
 */

/**
 * Interfaces I9: from session start the session carries the guard marker in
 * `$.state`, under this plugin's name, and `cua`'s scrubbing stands down so
 * one guard decides every handle. Every plugin reads it; only devcloud writes
 * it; a child process (a `claude` a tool call starts) has its own session and
 * decides for itself. Its type is the plugin's contract (types/devcloud.d.ts).
 * Not a `globalThis` symbol: the engine evaluates each
 * plugin's module in a realm of its own (probed 2026-10-17, 2.1.302).
 */
// The tools whose input a handle is restored in before they run.
const RESTORED = new Set(['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Bash'])
// `tool.call`'s own keys beside the tool's arguments: never rewritten.
const RESERVED = new Set(['tool', 'tool_use_id', 'agentId', 'requestMeta', 'consent'])
// What one `$.fs.read` or a process's output carries at most.
const READ_MAX = 4 * 1024 * 1024
// How often the rows' hook may re-read the sources; a tool call always does.
const REFRESH_EVERY_MS = 1000

const PROMPT_LINE =
  'Secrets in what you read are replaced by handles: [secret:KEY] stands for a stored or credential-file value ' +
  '(~b64, ~hex, ~url and the like name an encoding of it), [redacted:<kind>#<id>] for a token-shaped string, ' +
  '[superseded:…] for a value that has since changed. Write a handle where its value belongs: in the input of ' +
  'Write, Edit, MultiEdit, NotebookEdit and Bash it is restored to the exact bytes before the call runs, so ' +
  '`Authorization: Bearer [secret:KEY]` works and a file edited through a handle keeps its secret. A [superseded:…] ' +
  "handle, or another session's [redacted:…] one, is written as is, and the tool's result says so."

// Four base32 characters, drawn when the module loads: this process's pattern handles.
function namespace(): string {
  const alphabet = 'abcdefghijklmnopqrstuvwxyz234567'
  return Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) => alphabet[b % 32]).join('')
}

const handles = new Handles(namespace())

// The session's project root, once resolved; $HOME; and each source file as
// last read, so a file is read again only when it changed.
let project: string | undefined
let home: string | undefined
const sources = new Map<string, { mtimeMs: number; size: number; known: Known[] }>()
let refreshedAt = 0

async function projectOf($: EngineInterface, cwd?: string): Promise<string> {
  if (project !== undefined) return project
  const dir = cwd ?? (await $.session.cwd())
  let root = dir
  try {
    const git = await $.process.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir', '--show-toplevel'], { cwd: dir, timeoutMs: 5000 })
    const [commonDir, topLevel] = git.stdout.trim().split('\n')
    // A git older than 2.31 echoes `--path-format=absolute` back as a line of
    // its own; only two absolute paths are an answer.
    if (git.exitCode === 0 && commonDir?.startsWith('/') && topLevel?.startsWith('/')) root = rootFromGit(commonDir, topLevel)
  } catch {}
  project = root
  return root
}

// A source file's known values: read again only when its time or size moved.
async function readSource($: EngineInterface, path: string, stat: { mtimeMs: number; size: number }, parse: (text: string) => Known[]): Promise<Known[]> {
  const cached = sources.get(path)
  if (cached && cached.mtimeMs === stat.mtimeMs && cached.size === stat.size) return cached.known
  let known: Known[] = []
  try {
    known = parse(await $.fs.read(path))
  } catch {}
  sources.set(path, { mtimeMs: stat.mtimeMs, size: stat.size, known })
  return known
}

// One tier of the store: each key's value, read from its own file.
async function readTier($: EngineInterface, dir: string, isGlobal: boolean): Promise<Known[]> {
  let entries: Awaited<ReturnType<EngineInterface['fs']['list']>>
  try {
    entries = await $.fs.list(dir)
  } catch {
    return []
  }
  const out: Known[] = []
  for (const entry of entries) {
    if (entry.kind !== 'file' || !KEY.test(entry.name) || (isGlobal && PROJECTS.test(entry.name))) continue
    out.push(...(await readSource($, `${dir}/${entry.name}`, entry, (text) => [{ label: entry.name, value: storeValue(text) }])))
  }
  return out
}

async function statFile($: EngineInterface, path: string) {
  try {
    const stat = await $.fs.stat(path)
    return stat.kind === 'file' ? stat : undefined
  } catch {
    return undefined
  }
}

// gcloud's JSON files, below its folder: where its key files live.
async function gcloudFiles($: EngineInterface, dir: string, depth: number): Promise<string[]> {
  let entries: Awaited<ReturnType<EngineInterface['fs']['list']>>
  try {
    entries = await $.fs.list(`${home}/${dir}`)
  } catch {
    return []
  }
  const out: string[] = []
  for (const entry of entries) {
    if (entry.kind === 'file' && entry.name.endsWith('.json')) out.push(`${dir}/${entry.name}`)
    else if (entry.kind === 'dir' && depth > 0 && !GCLOUD_SKIP.has(entry.name)) out.push(...(await gcloudFiles($, `${dir}/${entry.name}`, depth - 1)))
  }
  return out
}

/**
 * Reads what is known now: the store's project tier, then its global one (a
 * global key the project's shadows is `KEY@global`), then the credential
 * files. A source that cannot be read adds nothing and stops nothing.
 */
async function refresh($: EngineInterface, isForced: boolean) {
  const now = Date.now()
  if (!isForced && now - refreshedAt < REFRESH_EVERY_MS) return
  refreshedAt = now
  home ??= await $.env.get('HOME')
  if (!home) return
  const store = `${home}/${STORE_DIR}`
  const projectKnown = await readTier($, `${store}/projects/${projectSlug(await projectOf($))}`, false)
  const shadowed = new Set(projectKnown.map((k) => k.label))
  const known: Known[] = [...projectKnown]
  for (const { label, value } of await readTier($, store, true)) known.push({ label: shadowed.has(label) ? `${label}@global` : label, value })

  const files: { path: string; format: Format }[] = [...CREDENTIAL_FILES, ...(await gcloudFiles($, GCLOUD_DIR, 3)).map((path) => ({ path, format: 'gcloud' as const }))]
  const present: { path: string; format: Format; stat: { mtimeMs: number; size: number } }[] = []
  for (const file of files) {
    const stat = await statFile($, `${home}/${file.path}`)
    if (stat) present.push({ ...file, stat })
  }
  const labels = credentialLabels(present.map((f) => f.path))
  for (const { path, format, stat } of present) {
    const name = labels.get(path)!
    known.push(...(await readSource($, `${home}/${path}`, stat, (text) => credentialFields(format, text).map((f) => ({ label: `${name}:${f.field}`, value: f.value })))))
  }
  handles.setKnown(known)
}

// A file of more than one read's worth, in pieces through `dd`, base64 so no
// piece splits a character.
async function readLarge($: EngineInterface, path: string, size: number): Promise<string> {
  const MIB = 1024 * 1024
  const pieces: Uint8Array[] = []
  for (let mib = 0; mib * MIB < size; mib += 2) {
    const r = await $.process.run(['/bin/sh', '-c', 'dd if="$1" bs=1048576 skip="$2" count=2 2>/dev/null | base64', 'sh', path, String(mib)])
    if (r.exitCode !== 0 || r.isStdoutTruncated) throw new Error('secrets: a persisted output could not be read')
    pieces.push(Uint8Array.from(atob(r.stdout.replace(/\s+/g, '')), (c) => c.charCodeAt(0)))
  }
  const bytes = new Uint8Array(pieces.reduce((n, p) => n + p.length, 0))
  let at = 0
  for (const p of pieces) {
    bytes.set(p, at)
    at += p.length
  }
  return new TextDecoder().decode(bytes)
}

/**
 * An oversized output the engine wrote to the session's `tool-results/`
 * before any hook saw the result: rewritten in place, scrubbed, before the
 * call returns, so the session store's first copy of it holds handles.
 */
async function scrubPersisted($: EngineInterface, path: string) {
  const stat = await $.fs.stat(path)
  const text = stat.size <= READ_MAX ? await $.fs.read(path) : await readLarge($, path, stat.size)
  const scrubbed = handles.scrub(text)
  if (scrubbed !== text) await $.fs.write(path, scrubbed)
}

const persistedPath = (result: unknown): string | undefined => {
  if (result === null || typeof result !== 'object') return undefined
  const record = result as Record<string, unknown>
  return typeof record.persistedOutputPath === 'string' && record.persistedOutputPath && record.isImage !== true ? record.persistedOutputPath : undefined
}

// Withheld rather than passed on unread: the call ran, its result is not shown.
const WITHHELD = 'secrets: the guard could not scrub this result, so it is withheld.'

const notRestored = (unrestored: readonly string[]) =>
  `secrets: not restored, so written as is: ${unrestored.join(', ')} ` +
  "(a superseded value, a key no longer stored, or another session's redaction)."

// Taken with both matchers: an event is registered without one once per module.
const secretsStart: Hook<'session.start'> = async ($, e, next) => {
  await $.state.set({ plugin: 'devcloud', key: 'secrets-guard' }, { owner: 'devcloud', version: 1 })
  project = undefined
  await projectOf($, e.cwd)
  await refresh($, true)
  return next(e)
}

export function registerSecrets(on: On) {
  on('session.start', { isInteractive: true }, secretsStart)
  on('session.start', { isInteractive: false }, secretsStart)

  on('tool.call', async ($, e, next) => {
    await refresh($, true)
    let input = e
    let unrestored: string[] = []
    if (RESTORED.has(e.tool)) {
      const args = Object.fromEntries(Object.entries(e).filter(([k]) => !RESERVED.has(k)))
      const restored = handles.restoreRecord(args)
      if (restored.value !== args) input = { ...e, ...restored.value }
      unrestored = restored.unrestored
    }
    const ran = await next(input)
    try {
      await refresh($, true)
      if (ran.deny !== undefined) {
        const deny = handles.scrub(ran.deny)
        return deny === ran.deny ? ran : { deny }
      }
      if (ran.isError) {
        const text = handles.scrub(ran.text ?? '')
        return text === ran.text && unrestored.length === 0 ? ran : { deny: unrestored.length ? `${text}\n${notRestored(unrestored)}` : text }
      }
      const path = persistedPath(ran.result)
      if (path !== undefined) await scrubPersisted($, path)
      const result = handles.scrubRecord(ran.result)
      const context = unrestored.length ? [...(ran.context ?? []), notRestored(unrestored)] : ran.context
      if (result === ran.result && context === ran.context) return ran
      return { result, context }
    } catch {
      return { deny: WITHHELD }
    }
  }).catch((_, e, next) => (next.called ? { deny: WITHHELD } : { deny: 'secrets: the guard failed before the call ran, so it did not run.' }))

  // Every row the conversation keeps, whatever door it came in by.
  on('session.append', async ($, e, next) => {
    await refresh($, false)
    let isChanged = false
    const content = e.message.content.map((block) => {
      if (block.type === 'text' && typeof block.text === 'string') {
        const text = handles.scrub(block.text)
        if (text === block.text) return block
        isChanged = true
        return { ...block, text }
      }
      if (block.type === 'tool_result') {
        const inner = handles.scrubRecord(block.content)
        if (inner === block.content) return block
        isChanged = true
        return { ...block, content: inner }
      }
      return block
    })
    return isChanged ? next({ ...e, message: { ...e.message, content } }) : next(e)
    // An engine row cannot be refused: one the guard failed on is kept as it came.
  }).catch((_, e, next) => next(e))

  // A compaction's instructions (the text after `/compact`) go to the
  // summarizer, and its summary rows are kept without passing `session.append`.
  on('session.compact', async ($, e, next) => {
    await refresh($, false)
    const instructions = e.instructions === undefined ? undefined : handles.scrub(e.instructions)
    const compacted = await next(instructions === e.instructions ? e : { ...e, instructions })
    if (!('messages' in compacted) || compacted.messages === undefined) return compacted
    let isChanged = false
    const messages = compacted.messages.map((m) => {
      const text = handles.scrub(m.text)
      if (text === m.text) return m
      isChanged = true
      // Without its handle: a message the engine reads as built, not its own.
      const { handle: _, ...rest } = m
      return { ...rest, text }
    })
    return isChanged ? { ...compacted, messages } : compacted
  }).catch((_, e, next) => next(e))

  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    await refresh($, false)
    const sections = composed.sections.map((s) => {
      const text = handles.scrub(s.text)
      return text === s.text ? s : { ...s, text }
    })
    return { sections: [...sections, { id: 'devcloud:secrets', scope: 'session' as const, text: PROMPT_LINE }] }
  })

  on('prompt.context', async ($, e, next) => {
    const context = await next(e)
    await refresh($, false)
    return { ...context, blocks: context.blocks.map((b) => ({ ...b, text: handles.scrub(b.text) })) }
  })

  on('prompt.attachment', async ($, e, next) => {
    const attached = await next(e)
    if (attached.text === null) return attached
    await refresh($, false)
    return { text: handles.scrub(attached.text) }
  })
}
