import type { EngineInterface, Hook, On } from 'claude-code'

import { Handles } from './secrets-handles'
import { PATTERN_READ, readNotice } from './secrets-reads'
import type { Read } from './secrets-reads'
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
 * sections, the first message's context blocks, each attachment as a request
 * carries it, and a compaction's instructions and summary. No call is refused for touching the store: a command
 * that prints a value is caught at its output. Handles in the input of a
 * Write, Edit, MultiEdit, NotebookEdit or Bash call are restored to their
 * bytes before it runs, so a file edited through a handle keeps its secret.
 *
 * The values known: those stored through `/secret` (`cua`'s store, read here,
 * Interfaces I1), those in well-known credential files, re-read when they
 * change, and token-shaped strings anywhere (secrets-detect).
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
  '[superseded:…] for a value that has since changed. Write a handle where its value belongs. In Write, Edit, ' +
  'MultiEdit and NotebookEdit it is restored to the exact bytes before the call runs, so a file edited through a ' +
  'handle keeps its secret. In Bash only a plain token in a plain position is restored ' +
  '(`Authorization: Bearer [secret:KEY]` inside double quotes, `--token=[secret:KEY]`); any other handle stays as ' +
  "written, and the tool's result names a read that works in its place. A [superseded:…] handle, or another " +
  "session's [redacted:…] one, is never restored, and the result says so."

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
// Where each store label's file is, from $HOME: the read a command can do in
// place of a handle the guard cannot restore into it.
// Each known label's source, as setKnown named it (`#2` and on included): the
// read a command can do in place of a handle the guard leaves in it.
const reads = new Map<string, Read>()

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

// The project tiers the store holds: each folder under `projects/`.
async function projectTiers($: EngineInterface, store: string): Promise<string[]> {
  try {
    return (await $.fs.list(`${store}/projects`)).filter((e) => e.kind === 'dir').map((e) => e.name)
  } catch {
    return []
  }
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
 * global key the project's shadows is `KEY@global`), then every other
 * project's tier (`KEY@<slug>`), then the credential files. A source that cannot be read adds nothing and stops nothing.
 */
async function refresh($: EngineInterface, isForced: boolean) {
  const now = Date.now()
  if (!isForced && now - refreshedAt < REFRESH_EVERY_MS) return
  refreshedAt = now
  home ??= await $.env.get('HOME')
  if (!home) return
  const store = `${home}/${STORE_DIR}`
  const own = projectSlug(await projectOf($))
  const projectKnown = await readTier($, `${store}/projects/${own}`, false)
  const shadowed = new Set(projectKnown.map((k) => k.label))
  const known: (Known & { read?: Read })[] = projectKnown.map((k) => ({ ...k, read: { kind: 'store', path: `${STORE_DIR}/projects/${own}/${k.label}` } }))
  for (const { label, value } of await readTier($, store, true)) {
    known.push({ label: shadowed.has(label) ? `${label}@global` : label, value, read: { kind: 'store', path: `${STORE_DIR}/${label}` } })
  }
  // Every other project's tier: a command can print any of them.
  for (const slug of await projectTiers($, store)) {
    if (slug === own) continue
    for (const { label, value } of await readTier($, `${store}/projects/${slug}`, false)) {
      known.push({ label: `${label}@${slug}`, value, read: { kind: 'store', path: `${STORE_DIR}/projects/${slug}/${label}` } })
    }
  }

  const files: { path: string; format: Format }[] = [...CREDENTIAL_FILES, ...(await gcloudFiles($, GCLOUD_DIR, 3)).map((path) => ({ path, format: 'gcloud' as const }))]
  const present: { path: string; format: Format; stat: { mtimeMs: number; size: number } }[] = []
  for (const file of files) {
    const stat = await statFile($, `${home}/${file.path}`)
    if (stat) present.push({ ...file, stat })
  }
  const labels = credentialLabels(present.map((f) => f.path))
  for (const { path, format, stat } of present) {
    const name = labels.get(path)!
    known.push(...(await readSource($, `${home}/${path}`, stat, (text) => credentialFields(format, text, path).map((f) => ({ label: `${name}:${f.field}`, value: f.value, read: f.read })))))
  }
  const names = handles.setKnown(known)
  reads.clear()
  names.forEach((name, i) => {
    const read = known[i]!.read
    if (read && !reads.has(name)) reads.set(name, read)
  })
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
  if (scrubbed === text) return
  // Handles can grow a file: the writer goes by the scrubbed size. Past what
  // `$.fs.write` takes, through a child's input into a file beside it (`.tmp`,
  // which the session store skips) renamed over it.
  if (new TextEncoder().encode(scrubbed).length <= READ_MAX) {
    await $.fs.write(path, scrubbed)
    return
  }
  const r = await $.process.run(['/bin/sh', '-c', 'umask 077 && cat > "$1.scrub.tmp" && mv -f "$1.scrub.tmp" "$1"', 'sh', path], { stdin: scrubbed, timeoutMs: 60_000 })
  if (r.exitCode !== 0) throw new Error('secrets: a persisted output could not be rewritten')
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

// A read that works in the command where a handle could not be restored.
function readInstead(handle: string): string {
  const { kind, label = '', enc } = handles.describe(handle)
  if (kind === 'redacted') return PATTERN_READ
  return readNotice(reads.get(label), enc, handles.valueOf(handle)?.endsWith('\n') ?? false)
}

// One line per handle left in a command: why, and the read to use instead.
const notQuoted = (unquotable: readonly string[]) =>
  unquotable.map(
    (h) => `secrets: ${h} was not restored into this command (the guard restores into a shell command only a plain value, at a plain position, in a plain command); ${readInstead(h)}.`,
  )

/**
 * Interfaces I9: devcloud's guard is in the session's chain exactly while this
 * module is loaded, and the guard marker says so. It is this module's answer
 * to a read, through a `state.get` hook, and never a value the host stores:
 * any plugin's `$.state.get({ plugin: 'devcloud', key: 'secrets-guard' })`
 * resolves to the marker at version 0 (where the host holds nothing) while the
 * module is loaded, and falls through to the host once it is gone (devcloud
 * disabled and the plugins reloaded), which then answers `undefined`. A marker
 * the host kept would outlive the module, and `cua`'s scrubbing, which stands
 * down on it, would leave the session with no guard (board #101). The engine runs a
 * `$` call through every hook on its event but the one that made the call,
 * the calling plugin's other hooks included: the read reaches this hook
 * whichever plugin sits outside the other, and a module that answered the
 * marker would read its own answer, so a guard that reads it to stand down
 * must never answer it. A child process (a
 * `claude` a tool call starts) has its own session and decides for itself.
 * Its type is the plugin's contract (types/devcloud.d.ts). Not a `globalThis`
 * symbol: the engine evaluates each plugin's module in a realm of its own
 * (probed 2026-10-17, 2.1.302).
 */
const MARKER_READ = { value: { value: { owner: 'devcloud', version: 1 }, version: 0 } } as const

// Taken with both matchers: an event is registered without one once per module.
const secretsStart: Hook<'session.start'> = async ($, e, next) => {
  project = undefined
  await projectOf($, e.cwd)
  await refresh($, true)
  return next(e)
}

export function registerSecrets(on: On) {
  on('session.start', { isInteractive: true }, secretsStart)
  on('session.start', { isInteractive: false }, secretsStart)
  on('state.get', { plugin: 'devcloud', key: 'secrets-guard' }, () => MARKER_READ).catch(() => MARKER_READ)

  // Unmatched, so this module is a link of every call's chain. sminos's
  // bridge relies on that: it reads `next.trace` after each call, and with
  // the marker live and no `devcloud` link beneath it, it takes itself to be
  // inside this guard and turns off. A matcher here would turn every placed
  // machine's bridge off on the calls it leaves out.
  on('tool.call', async ($, e, next) => {
    let input = e
    const notes: string[] = []
    if (RESTORED.has(e.tool)) {
      await refresh($, true)
      if (e.tool === 'Bash' && typeof e.command === 'string') {
        // The command alone, which a shell reads, by the safe rule: a value
        // goes in only where its bytes are proved to arrive as data.
        const shell = handles.restoreShell(e.command)
        if (shell.text !== e.command) input = { ...e, command: shell.text }
        if (shell.unrestored.length) notes.push(notRestored(shell.unrestored))
        notes.push(...notQuoted(shell.unquotable))
      } else {
        const args = Object.fromEntries(Object.entries(e).filter(([k]) => !RESERVED.has(k)))
        const restored = handles.restoreRecord(args)
        if (restored.value !== args) input = { ...e, ...restored.value }
        if (restored.unrestored.length) notes.push(notRestored(restored.unrestored))
      }
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
        return text === ran.text && notes.length === 0 ? ran : { deny: [text, ...notes].join('\n') }
      }
      const path = persistedPath(ran.result)
      if (path !== undefined) await scrubPersisted($, path)
      const result = handles.scrubRecord(ran.result)
      const context = notes.length ? [...(ran.context ?? []), ...notes] : ran.context
      if (result === ran.result && context === ran.context) return ran
      return { result, context }
    } catch {
      return { deny: WITHHELD }
    }
  }).catch((_, e, next) => (next.called ? { deny: WITHHELD } : { deny: 'secrets: the guard failed before the call ran, so it did not run.' }))

  // Every row the conversation keeps, whatever door it came in by. An engine
  // row cannot be refused: one the guard failed on is kept as it came.
  // Unmatched for sminos's bridge too, which judges its place from each row's
  // `next.trace` as from each call's (tool.call above): a matcher here would
  // turn a placed machine's bridge off on the rows it leaves out.
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
