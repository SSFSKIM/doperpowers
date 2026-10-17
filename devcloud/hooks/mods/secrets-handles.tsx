import { detect } from './secrets-detect'

/**
 * Handles: the text that stands where a secret was, one per distinct byte
 * string, and the way back to those bytes. Pure: the hooks module feeds it the
 * known values it reads and calls it on every text it passes.
 *
 *   [secret:LABEL]              a known value: a store key (`KEY`, `KEY@global`
 *                               for a global value a project key shadows) or a
 *                               credential file's field (`hosts.yml:<field>`)
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

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const handleOf = (kind: 'secret' | 'superseded', label: string, enc: string) => `[${kind}:${label}${enc ? `~${enc}` : ''}]`

type Candidate = { start: number; end: number; rank: number; replace?: string; kind?: string }

export class Handles {
  /** The namespace of this process's pattern handles. */
  readonly ns: string
  private current = new Map<string, string>()
  private former = new Map<string, string>()
  private known = new Map<string, string>()
  private knownPattern: RegExp | undefined
  private issued = new Map<string, string>()
  private bytes = new Map<string, string>()

  constructor(ns: string) {
    this.ns = ns
  }

  /**
   * The values known now, in priority order (the first label to hold a value
   * keeps it). A label whose value changed or vanished leaves its old value
   * superseded, unless another label holds it now.
   */
  setKnown(list: readonly Known[]) {
    const next = new Map<string, string>()
    for (const { label, value } of list) if (!next.has(label)) next.set(label, value)
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
    const texts = [...this.known.keys()].sort((a, b) => b.length - a.length)
    this.knownPattern = texts.length ? new RegExp(texts.map(escape).join('|'), 'g') : undefined
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
  scrub(text: string): string {
    const candidates: Candidate[] = []
    for (const m of text.matchAll(HANDLE)) candidates.push({ start: m.index ?? 0, end: (m.index ?? 0) + m[0].length, rank: 0 })
    if (this.knownPattern) {
      for (const m of text.matchAll(this.knownPattern)) {
        candidates.push({ start: m.index ?? 0, end: (m.index ?? 0) + m[0].length, rank: 1, replace: this.known.get(m[0]) })
      }
    }
    for (const span of detect(text)) candidates.push({ ...span, rank: 2 })
    if (candidates.every((c) => c.rank === 0)) return text

    candidates.sort((a, b) => a.rank - b.rank || a.start - b.start)
    const kept: Candidate[] = []
    for (const c of candidates) if (!kept.some((k) => c.start < k.end && k.start < c.end)) kept.push(c)
    kept.sort((a, b) => a.start - b.start)

    let out = ''
    let at = 0
    for (const c of kept) {
      if (c.rank === 0) continue
      out += text.slice(at, c.start) + (c.replace ?? this.patternHandle(c.kind ?? 'pattern', text.slice(c.start, c.end)))
      at = c.end
    }
    return out + text.slice(at)
  }

  /** What a handle's text stands for now, or undefined when nothing it names can be restored. */
  private resolve(kind: string, body: string): string | undefined {
    if (kind === 'redacted') return this.bytes.get(`[redacted:${body}]`)
    if (kind !== 'secret') return undefined
    const tilde = body.lastIndexOf('~')
    const enc = tilde > 0 && ENCODING.has(body.slice(tilde + 1)) ? body.slice(tilde + 1) : ''
    const value = this.current.get(enc ? body.slice(0, tilde) : body)
    return value === undefined ? undefined : ENCODING.get(enc)!(value)
  }

  /** `text` with each handle this process can restore replaced by its bytes; the rest named. */
  restore(text: string): { text: string; unrestored: string[] } {
    const unrestored: string[] = []
    const restored = text.replace(HANDLE, (handle: string, kind: string, body: string) => {
      const value = this.resolve(kind, body)
      if (value !== undefined) return value
      if (!unrestored.includes(handle)) unrestored.push(handle)
      return handle
    })
    return { text: restored, unrestored }
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
