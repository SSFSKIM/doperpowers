/**
 * Where known values come from, read without `$`: the secret store's layout
 * (Interfaces I1, as `cua`'s `src/secrets/store.mjs` documents it) and the
 * well-known credential files, each parsed into its secret fields. The hooks
 * module lists and reads the files; this one says what they hold.
 */

export type Field = { field: string; value: string }
export type Format = 'yaml' | 'json' | 'gcloud' | 'toml' | 'pgpass' | 'netrc' | 'git-credentials' | 'npmrc'

/** The secret store, relative to $HOME: one value per file, a folder per project under `projects/`. */
export const STORE_DIR = '.config/claude-secrets'
export const KEY = /^[A-Za-z_][A-Za-z0-9_]*$/
// The global tier's folder of the project tiers, so never a key (in any case:
// macOS's file system would open PROJECTS for projects).
export const PROJECTS = /^projects$/i

/** The credential files read at fixed paths, relative to $HOME, with the format each is parsed as. */
export const CREDENTIAL_FILES: readonly { path: string; format: Format }[] = [
  { path: '.config/gh/hosts.yml', format: 'yaml' },
  { path: '.pgpass', format: 'pgpass' },
  { path: '.codex/auth.json', format: 'json' },
  { path: '.claude/.credentials.json', format: 'json' },
  { path: '.config/hcloud/cli.toml', format: 'toml' },
  { path: '.docker/config.json', format: 'json' },
  { path: '.netrc', format: 'netrc' },
  { path: '.git-credentials', format: 'git-credentials' },
  { path: '.npmrc', format: 'npmrc' },
]
/** gcloud's folder, whose JSON key files (service account, authorized user) are read too. */
export const GCLOUD_DIR = '.config/gcloud'
// Its folders that hold no key file, left unwalked.
export const GCLOUD_SKIP = new Set(['logs', 'cache', 'configurations', 'surface_data', 'virtenv'])

// A field whose name says it holds a credential, and the names that only
// point at one (an address, an id, a kind).
const SECRET_FIELD = /token|secret|password|passwd|private_?key|api_?key|credential|^auth$/i
const NOT_SECRET_FIELD = /(?:uri|url|_id|Id|type|mode)$/i
// Shorter strings are flags and kinds, not credentials.
const FIELD_MIN = 8

const isSecretField = (name: string, value: string) =>
  SECRET_FIELD.test(name) && !NOT_SECRET_FIELD.test(name) && value.length >= FIELD_MIN && !/^[a-z][a-z0-9+.-]*:\/\//i.test(value)

function jsonFields(value: unknown, path: string[] = [], out: Field[] = []): Field[] {
  if (Array.isArray(value)) value.forEach((item, i) => jsonFields(item, [...path, String(i)], out))
  else if (value !== null && typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) {
      if (typeof v === 'string') {
        if (isSecretField(k, v)) out.push({ field: [...path, k].join('.'), value: v })
      } else jsonFields(v, [...path, k], out)
    }
  }
  return out
}

const unquote = (text: string) => {
  const t = text.trim()
  return /^(["']).*\1$/.test(t) ? t.slice(1, -1) : t
}

function yamlFields(text: string): Field[] {
  const out: Field[] = []
  const stack: { indent: number; key: string }[] = []
  for (const line of text.split('\n')) {
    const m = /^(\s*)(?:-\s+)?([^:#\s][^:#]*?):(?:\s+(.*))?$/.exec(line)
    if (!m) continue
    const indent = (m[1] ?? '').length
    while (stack.length && stack[stack.length - 1]!.indent >= indent) stack.pop()
    const key = m[2]!.trim()
    const value = unquote((m[3] ?? '').replace(/\s+#.*$/, ''))
    if (value === '') stack.push({ indent, key })
    else if (isSecretField(key, value)) out.push({ field: [...stack.map((s) => s.key), key].join('.'), value })
  }
  return out
}

// A TOML value as the file means it: a basic string's escapes decoded, a
// literal string as written, a bare value up to an inline comment.
function tomlValue(raw: string): string {
  const quote = raw[0]
  if (quote === "'") {
    const end = raw.indexOf("'", 1)
    return end === -1 ? raw.slice(1) : raw.slice(1, end)
  }
  if (quote === '"') {
    let out = ''
    for (let i = 1; i < raw.length; i++) {
      const c = raw[i]!
      if (c === '"') return out
      if (c !== '\\') {
        out += c
        continue
      }
      const e = raw[++i] ?? ''
      if (e === 'u' || e === 'U') {
        const n = e === 'u' ? 4 : 8
        out += String.fromCodePoint(parseInt(raw.slice(i + 1, i + 1 + n), 16))
        i += n
      } else out += ({ n: '\n', t: '\t', r: '\r', b: '\b', f: '\f' } as Record<string, string>)[e] ?? e
    }
    return out
  }
  return raw.replace(/\s+#.*$/, '').trim()
}

function tomlFields(text: string): Field[] {
  const out: Field[] = []
  type Block = { prefix: string; isArray: boolean; index: number; entries: [string, string][] }
  const counts = new Map<string, number>()
  let block: Block = { prefix: '', isArray: false, index: 0, entries: [] }
  const flush = () => {
    const name = block.entries.find(([k]) => k === 'name')?.[1]
    const base = block.isArray ? `${block.prefix}.${name ?? block.index}` : block.prefix
    for (const [k, v] of block.entries) if (isSecretField(k, v)) out.push({ field: base ? `${base}.${k}` : k, value: v })
  }
  for (const line of text.split('\n')) {
    const table = /^\s*(\[\[?)\s*([^\]]+?)\s*\]\]?\s*$/.exec(line)
    if (table) {
      flush()
      const prefix = table[2]!
      const isArray = table[1] === '[['
      const index = counts.get(prefix) ?? 0
      if (isArray) counts.set(prefix, index + 1)
      block = { prefix, isArray, index, entries: [] }
      continue
    }
    const kv = /^\s*([A-Za-z0-9_.-]+)\s*=\s*(.+?)\s*$/.exec(line)
    if (kv) block.entries.push([kv[1]!, tomlValue(kv[2]!)])
  }
  flush()
  return out
}

function pgpassFields(text: string): Field[] {
  const out: Field[] = []
  for (const line of text.split('\n')) {
    if (line.trim() === '' || line.startsWith('#')) continue
    const parts = line.split(/(?<!\\):/)
    if (parts.length !== 5) continue
    const value = parts[4]!.replace(/\\(.)/g, '$1')
    if (value) out.push({ field: parts.slice(0, 4).join(':'), value })
  }
  return out
}

// A .netrc's tokens: whitespace-separated, a double-quoted token taken whole
// with its backslash escapes decoded.
function netrcTokens(text: string): string[] {
  const words: string[] = []
  for (let i = 0; i < text.length; ) {
    while (i < text.length && /\s/.test(text[i]!)) i++
    if (i >= text.length) break
    let word = ''
    if (text[i] === '"') {
      for (i++; i < text.length && text[i] !== '"'; i++) word += text[i] === '\\' ? (text[++i] ?? '') : text[i]
      i++
    } else for (; i < text.length && !/\s/.test(text[i]!); i++) word += text[i]
    words.push(word)
  }
  return words
}

function netrcFields(text: string): Field[] {
  const out: Field[] = []
  const words = netrcTokens(text)
  let machine = ''
  for (let i = 0; i < words.length; i++) {
    const word = words[i]
    if (word === 'machine') machine = words[++i] ?? ''
    else if (word === 'default') machine = 'default'
    else if (word === 'password' && words[i + 1] !== undefined) out.push({ field: `${machine}.password`, value: words[++i]! })
    else if (word === 'login' || word === 'account') i++
  }
  return out
}

function gitCredentialFields(text: string): Field[] {
  const out: Field[] = []
  const decode = (s: string) => {
    try {
      return decodeURIComponent(s)
    } catch {
      return s
    }
  }
  for (const line of text.split('\n')) {
    // The repository path is part of the identity: one user may hold a
    // credential per repository on one host.
    const m = /^[a-z][a-z0-9+.-]*:\/\/([^:@/]*):([^@/]+)@([^/\s]+)(\/\S*)?/i.exec(line.trim())
    if (m) out.push({ field: `${decode(m[1]!)}@${m[3]}${m[4] ?? ''}`, value: decode(m[2]!) })
  }
  return out
}

function npmrcFields(text: string): Field[] {
  const out: Field[] = []
  for (const line of text.split('\n')) {
    const m = /^\s*([^=#;\s][^=]*?)\s*=\s*(.+?)\s*$/.exec(line)
    if (m && /(?:^|:)(?:_authToken|_auth|_password|token)$/i.test(m[1]!) && m[2]!.length >= FIELD_MIN) out.push({ field: m[1]!, value: unquote(m[2]!) })
  }
  return out
}

/** The secret fields of a credential file's text, by its format; nothing for one that does not parse. */
export function credentialFields(format: Format, text: string): Field[] {
  try {
    switch (format) {
      case 'json':
        return jsonFields(JSON.parse(text))
      case 'gcloud': {
        // A key file only: a service account's or an authorized user's.
        const parsed = JSON.parse(text) as Record<string, unknown> | null
        const kind = parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed.type : undefined
        return kind === 'service_account' || kind === 'authorized_user' ? jsonFields(parsed) : []
      }
      case 'yaml':
        return yamlFields(text)
      case 'toml':
        return tomlFields(text)
      case 'pgpass':
        return pgpassFields(text)
      case 'netrc':
        return netrcFields(text)
      case 'git-credentials':
        return gitCredentialFields(text)
      case 'npmrc':
        return npmrcFields(text)
    }
  } catch {
    return []
  }
}

/**
 * The name each credential file goes by in its handles: its basename, or its
 * path from $HOME where two of the files share a basename (gcloud keeps an
 * `adc.json` per account), so that no two files' fields share a label.
 */
export function credentialLabels(paths: readonly string[]): Map<string, string> {
  const base = (path: string) => path.slice(path.lastIndexOf('/') + 1)
  const count = new Map<string, number>()
  for (const path of paths) count.set(base(path), (count.get(base(path)) ?? 0) + 1)
  return new Map(paths.map((path) => [path, count.get(base(path))! > 1 ? path : base(path)]))
}

/** A stored value as the store reads it: exactly one trailing newline dropped (a file written by `echo`). */
export const storeValue = (text: string) => (text.endsWith('\n') ? text.slice(0, -1) : text)

// Claude Code cuts a slug at this length and adds a hash of the whole path.
const SLUG_MAX = 200

/**
 * A project's path as Claude Code names its folder under ~/.claude/projects/:
 * every character other than an ASCII letter or digit becomes '-', and a slug
 * longer than 200 characters keeps its first 200 and gains '-' and a base-36
 * hash of the path. `cua`'s store carries the same.
 */
export function projectSlug(path: string): string {
  const slug = path.replace(/[^a-zA-Z0-9]/g, '-')
  if (slug.length <= SLUG_MAX) return slug
  let hash = 0
  for (let i = 0; i < path.length; i++) hash = ((hash << 5) - hash + path.charCodeAt(i)) | 0
  return `${slug.slice(0, SLUG_MAX)}-${Math.abs(hash).toString(36)}`
}

/**
 * The project root from `git rev-parse --path-format=absolute
 * --git-common-dir --show-toplevel`'s two lines: the main checkout's root
 * (the parent of its `.git`, which every linked worktree shares), or the
 * repository's top level where the common directory is no `.git` folder (a
 * submodule's).
 */
export function rootFromGit(commonDir: string, topLevel: string): string {
  return /\/\.git$/.test(commonDir) ? commonDir.slice(0, -'/.git'.length) || '/' : topLevel
}
