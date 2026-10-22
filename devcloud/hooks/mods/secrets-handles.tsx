import { detect, keepFirst } from './secrets-detect'
import type { CharacterRange } from './secrets-detect'
import { isInert, isPlainCommand, isPlainPosition } from './secrets-shell'

/**
 * Handles: the text that stands where a secret was, one per distinct byte
 * string, and the way back to those bytes. Pure: the hooks module feeds it the
 * known values it reads and calls it on every text it passes.
 *
 *   [secret:LABEL]              a known value: a store key (`KEY`, `KEY@global`
 *                               for a global value a project key shadows,
 *                               `KEY@<slug>` for another project's) or a
 *                               credential file's field (`hosts.yml:<field>`);
 *                               whitespace, `[`, `]`, `~` and `%` in a label
 *                               are written %XX, and a second value under a
 *                               label already taken is `LABEL#2`, `#3`, ...
 *   [secret:LABEL~<enc>]        an encoded spelling of it
 *   [superseded:LABEL]          a value LABEL held earlier in this process
 *   [redacted:<kind>#<ns>.<n>]  a pattern detection, bound to this process
 *
 * A known handle names a credential, so it restores to the credential's
 * current value; a pattern handle stands for exactly the bytes it replaced,
 * and only the process that issued it (its namespace) can restore it.
 */

export type Known = { label: string; value: string }
export type Spelling = { enc: string; text: string }

// Shorter values would scrub ordinary words out of everything the model reads.
export const SCRUB_MIN = 6

const HANDLE = /\[(secret|superseded|redacted):([^\]\s]+)\]/g
// What looks like a handle, parsable or not: one that is not is named as not
// restored rather than passed over.
const HANDLE_LIKE = /\[(secret|superseded|redacted):([^\]\n]*)\]/g
const PARSABLE = /^[^\]\s]+$/

// A label's characters the handle grammar reserves, written %XX (UTF-8).
const RESERVED = /[\s[\]~%]|[^\x21-\x7e]/gu
export const encodeLabel = (label: string) =>
  label.replace(RESERVED, (c) => Array.from(utf8(c), (b) => `%${b.toString(16).toUpperCase().padStart(2, '0')}`).join(''))
const decodeLabel = (body: string): string | undefined => {
  try {
    return decodeURIComponent(body.replace(/%(?![0-9A-Fa-f]{2})/g, '%25'))
  } catch {
    return undefined
  }
}

const utf8 = (value: string) => new TextEncoder().encode(value)
const base64 = (value: string) => {
  let binary = ''
  for (const byte of utf8(value)) binary += String.fromCharCode(byte)
  return btoa(binary)
}
const hex = (value: string) => Array.from(utf8(value), (b) => b.toString(16).padStart(2, '0')).join('')

// The spellings a command prints a value in by accident, each its own
// encoding name; a spelling that equals an earlier one is the earlier one.
const ENCODINGS: readonly [string, (value: string) => string][] = [
  ['', (v) => v],
  ['b64', (v) => base64(v)],
  ['b64np', (v) => base64(v).replace(/=+$/, '')],
  ['b64u', (v) => base64(v).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_')],
  ['b64up', (v) => base64(v).replace(/\+/g, '-').replace(/\//g, '_')],
  ['hex', (v) => hex(v)],
  ['HEX', (v) => hex(v).toUpperCase()],
  ['url', (v) => encodeURIComponent(v)],
  // As a JSON string's body prints it: a key file's PEM with `\n` escapes.
  ['json', (v) => JSON.stringify(v).slice(1, -1)],
  // As a .pgpass line prints it: `\` and `:` escaped with a backslash.
  ['pgpass', (v) => v.replace(/[\\:]/g, '\\$&')],
]
const ENCODING = new Map(ENCODINGS)

/** Every distinct spelling of `value`, the value itself first (`enc` ''). */
export function spellings(value: string): Spelling[] {
  const seen = new Set<string>()
  const out: Spelling[] = []
  for (const [enc, encode] of ENCODINGS) {
    const text = encode(value)
    if (seen.has(text)) continue
    seen.add(text)
    out.push({ enc, text })
  }
  return out
}

const handleOf = (kind: 'secret' | 'superseded', label: string, enc: string) => `[${kind}:${encodeLabel(label)}${enc ? `~${enc}` : ''}]`

type Candidate = { start: number; end: number; rank: number; replace?: string; kind?: string }

export class Handles {
  /** The namespace of this process's pattern handles. */
  readonly ns: string
  private current = new Map<string, string>()
  private former = new Map<string, string>()
  private known = new Map<string, string>()
  private issued = new Map<string, string>()
  private bytes = new Map<string, string>()

  constructor(ns: string) {
    this.ns = ns
  }

  /**
   * The values known now, in priority order (the first label to hold a value
   * keeps it). A distinct value under a label already taken gets `#2`, `#3`,
   * ...; none is dropped. Returns the name each entry got, in order. A label whose value changed or vanished leaves its old
   * value superseded, unless another label holds it now.
   */
  setKnown(list: readonly Known[]): string[] {
    // Every label stays resolvable, two holding the same bytes included; only
    // which handle the bytes display as goes to the first (below).
    const next = new Map<string, string>()
    const names: string[] = []
    for (const { label, value } of list) {
      let name = label
      for (let n = 2; next.has(name) && next.get(name) !== value; n++) name = `${label}#${n}`
      next.set(name, value)
      names.push(name)
    }
    for (const [label, value] of this.current) if (next.get(label) !== value) this.former.set(value, label)
    this.current = next
    this.known = new Map()
    for (const [label, value] of next) {
      if (value.length < SCRUB_MIN) continue
      for (const { enc, text } of spellings(value)) if (!this.known.has(text)) this.known.set(text, handleOf('secret', label, enc))
    }
    const current = new Set(next.values())
    for (const [value, label] of this.former) {
      if (current.has(value) || value.length < SCRUB_MIN) continue
      for (const { enc, text } of spellings(value)) if (!this.known.has(text)) this.known.set(text, handleOf('superseded', label, enc))
    }
    return names
  }

  private patternHandle(kind: string, text: string): string {
    let handle = this.issued.get(text)
    if (handle === undefined) {
      handle = `[redacted:${kind}#${this.ns}.${this.issued.size + 1}]`
      this.issued.set(text, handle)
      this.bytes.set(handle, text)
    }
    return handle
  }

  /**
   * `text` with every known value, superseded value and token-shaped string
   * replaced by its handle, in one pass: a handle already in the text is kept
   * as it is, and nothing the pass wrote is read again.
   */
  scrub(text: string, genericExceptions: readonly CharacterRange[] = []): string {
    const candidates: Candidate[] = []
    for (const m of text.matchAll(HANDLE)) candidates.push({ start: m.index ?? 0, end: (m.index ?? 0) + m[0].length, rank: 0 })
    // `indexOf` per spelling: far quicker over a long output than one
    // alternation of every spelling, tried at each position.
    for (const [spelling, handle] of this.known) {
      for (let at = text.indexOf(spelling); at !== -1; at = text.indexOf(spelling, at + spelling.length)) {
        candidates.push({ start: at, end: at + spelling.length, rank: 1, replace: handle })
      }
    }
    for (const span of detect(text, genericExceptions)) candidates.push({ ...span, rank: 2 })
    if (candidates.every((c) => c.rank === 0)) return text

    // A handle in the text first, then known values (the longest where two
    // start together), then patterns; each kept unless it overlaps one kept.
    candidates.sort((a, b) => a.rank - b.rank || a.start - b.start || b.end - a.end)
    const kept = keepFirst(candidates, text.length)

    let out = ''
    let at = 0
    for (const c of kept) {
      if (c.rank === 0) continue
      out += text.slice(at, c.start) + (c.replace ?? this.patternHandle(c.kind ?? 'pattern', text.slice(c.start, c.end)))
      at = c.end
    }
    return out + text.slice(at)
  }

  /** The bytes a handle restores to now, or undefined. */
  valueOf(handle: string): string | undefined {
    const m = /^\[(secret|superseded|redacted):([^\]\s]+)\]$/.exec(handle)
    return m ? this.resolve(m[1]!, m[2]!) : undefined
  }

  /** What a handle names: its kind, and for a known one its label and encoding (`''` for the value itself). */
  describe(handle: string): { kind: string; label?: string; enc: string } {
    const m = /^\[(secret|superseded|redacted):([^\]\s]+)\]$/.exec(handle)
    if (!m) return { kind: 'unparsed', enc: '' }
    const body = m[2]!
    const tilde = body.lastIndexOf('~')
    const enc = tilde > 0 && ENCODING.has(body.slice(tilde + 1)) ? body.slice(tilde + 1) : ''
    return { kind: m[1]!, label: decodeLabel(enc ? body.slice(0, tilde) : body), enc }
  }

  /** What a handle's text stands for now, or undefined when nothing it names can be restored. */
  private resolve(kind: string, body: string): string | undefined {
    if (kind === 'redacted') return this.bytes.get(`[redacted:${body}]`)
    if (kind !== 'secret') return undefined
    const tilde = body.lastIndexOf('~')
    const enc = tilde > 0 && ENCODING.has(body.slice(tilde + 1)) ? body.slice(tilde + 1) : ''
    const label = decodeLabel(enc ? body.slice(0, tilde) : body)
    const value = label === undefined ? undefined : this.current.get(label)
    return value === undefined ? undefined : ENCODING.get(enc)!(value)
  }

  /**
   * `text` with each handle this process can restore replaced by its bytes;
   * every other handle-like text, parsable or not, left as it is and named.
   */
  restore(text: string): { text: string; unrestored: string[] } {
    const { unquotable: _, ...restored } = this.restoreWith(text, (value) => value)
    return restored
  }

  // Each handle resolved and written through `write`; one `write` declines is
  // named in `unquotable`, one nothing resolves in `unrestored`.
  private restoreWith(text: string, write: (value: string, at: number, length: number) => string | undefined): { text: string; unrestored: string[]; unquotable: string[] } {
    const unrestored: string[] = []
    const unquotable: string[] = []
    const restored = text.replace(HANDLE_LIKE, (handle: string, kind: string, body: string, at: number) => {
      const value = PARSABLE.test(body) ? this.resolve(kind, body) : undefined
      if (value === undefined) {
        if (!unrestored.includes(handle)) unrestored.push(handle)
        return handle
      }
      const written = write(value, at, handle.length)
      if (written !== undefined) return written
      if (!unquotable.includes(handle)) unquotable.push(handle)
      return handle
    })
    return { text: restored, unrestored, unquotable }
  }

  /**
   * A shell command with its handles restored where that is shown safe
   * (secrets-shell): an inert value, at a plain position, in a plain command.
   * Every other handle stays as written and is named in `unquotable`.
   */
  restoreShell(command: string): { text: string; unrestored: string[]; unquotable: string[] } {
    const isPlain = isPlainCommand(command)
    return this.restoreWith(command, (value, at, length) => (isPlain && isInert(value) && isPlainPosition(command, at, length, value) ? value : undefined))
  }

  /** A record with every string scrubbed (an image's bytes left); the same object when none changed. */
  scrubRecord<T>(value: T): T {
    return mapStrings(value, (s) => this.scrub(s)) as T
  }

  /** A record with every string's handles restored, and the handles left as written. */
  restoreRecord<T>(value: T): { value: T; unrestored: string[] } {
    const unrestored: string[] = []
    const out = mapStrings(value, (s) => {
      const r = this.restore(s)
      for (const h of r.unrestored) if (!unrestored.includes(h)) unrestored.push(h)
      return r.text
    }) as T
    return { value: out, unrestored }
  }
}

// Each string of a JSON-like value mapped; the same object where none changed.
function mapStrings(value: unknown, map: (s: string) => string): unknown {
  if (typeof value === 'string') return map(value)
  if (Array.isArray(value)) {
    const items = value.map((item) => mapStrings(item, map))
    return items.some((item, i) => item !== value[i]) ? items : value
  }
  if (value !== null && typeof value === 'object') {
    const record = value as Record<string, unknown>
    if (record.type === 'image' || record.type === 'base64') return value
    const entries = Object.entries(record).map(([k, v]) => [k, mapStrings(v, map)] as const)
    return entries.some(([k, v]) => v !== record[k]) ? Object.fromEntries(entries) : value
  }
  return value
}
