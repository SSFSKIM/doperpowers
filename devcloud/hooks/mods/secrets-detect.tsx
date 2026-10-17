/**
 * The detector: where a text holds a token-shaped string. Pure, so the tests
 * pin it without a session. gitleaks' rule set is the reference for the
 * prefixes; a bare run of hex or base64 with neither a prefix nor a
 * secret-named assignment is never a span, or commit hashes and checksums
 * would drown the transcript.
 */

export type Span = { start: number; end: number; kind: string }

/**
 * The spans, taken in the order given, each kept unless it overlaps one
 * already kept; returned in text order. Linear in the spans' total length.
 */
export function keepFirst<T extends { start: number; end: number }>(spans: readonly T[], length: number): T[] {
  if (spans.length === 0) return []
  const taken = new Uint8Array(length)
  const kept: T[] = []
  for (const span of spans) {
    let isFree = true
    for (let i = span.start; i < span.end && isFree; i++) isFree = taken[i] === 0
    if (!isFree) continue
    taken.fill(1, span.start, span.end)
    kept.push(span)
  }
  return kept.sort((a, b) => a.start - b.start)
}

// In order: the first rule to claim a character keeps it. Each pattern opens
// with its literal prefix, which lets the engine skip ahead to it; that the
// token does not start inside a longer word (`risk-…` holds no `sk-` token) is
// checked after a match (NOT_LEAD), as a lookbehind would cost a test at every
// position of the text.
const RULES: readonly { kind: string; pattern: RegExp }[] = [
  // PEM blocks, raw or JSON-escaped (`\n` as two characters, as a key file prints).
  {
    kind: 'pem',
    pattern: /-----BEGIN ((?:[A-Z0-9]+ )*)PRIVATE KEY( BLOCK)?-----[\s\S]*?-----END \1PRIVATE KEY\2-----/g,
  },
  { kind: 'anthropic', pattern: /sk-ant-[A-Za-z0-9_-]{20,}/g },
  { kind: 'openrouter', pattern: /sk-or-v1-[A-Za-z0-9]{20,}/g },
  { kind: 'openai', pattern: /sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}/g },
  { kind: 'github-pat', pattern: /ghp_[A-Za-z0-9]{30,}/g },
  { kind: 'github-oauth', pattern: /gho_[A-Za-z0-9]{30,}/g },
  { kind: 'github-app-token', pattern: /gh[us]_[A-Za-z0-9]{30,}/g },
  { kind: 'github-refresh-token', pattern: /ghr_[A-Za-z0-9]{30,}/g },
  { kind: 'github-fine-grained-pat', pattern: /github_pat_[A-Za-z0-9_]{22,}/g },
  { kind: 'tailscale', pattern: /tskey-[A-Za-z0-9-]{16,}/g },
  { kind: 'slack', pattern: /xox[abprs]-[A-Za-z0-9-]{10,}/g },
  { kind: 'aws-access-key', pattern: /A(?:KIA|SIA)[0-9A-Z]{16}(?![0-9A-Za-z])/g },
  { kind: 'gitlab-pat', pattern: /glpat-[A-Za-z0-9_-]{20,}/g },
  { kind: 'huggingface', pattern: /hf_[A-Za-z0-9]{30,}/g },
  { kind: 'gcp-api-key', pattern: /AIza[0-9A-Za-z_-]{35}/g },
]
const NOT_LEAD = /[A-Za-z0-9_]/

// A name that says secret: one of these words as a whole part of the name,
// parts split at `_`, `-`, `.` and a camelCase boundary (`apiKey`).
const SECRET_WORDS = new Set(['token', 'tokens', 'secret', 'secrets', 'password', 'passwords', 'passwd', 'apikey', 'bearer', 'credential', 'credentials'])
const SECRET_PAIRS = new Set(['api key', 'private key'])

export function isSecretName(name: string): boolean {
  const parts = name
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .toLowerCase()
    .split(/[_.-]+/)
    .filter(Boolean)
  return parts.some((part, i) => SECRET_WORDS.has(part) || SECRET_PAIRS.has(`${part} ${parts[i + 1]}`))
}

// `NAME = value`, `NAME: value`, `"name": "value"`; and `Bearer value`. The
// value stops at whitespace, a quote, or punctuation no token carries. A name
// right after `[` is a handle's (`[secret:…]`), never an assignment.
const VALUE = `(["']?)([^\\s"'\`,;:{}()<>[\\]\\\\]+)`
const ASSIGNMENT = new RegExp(`(?<![A-Za-z0-9_[])(["']?)([A-Za-z_][A-Za-z0-9_.-]*)\\1[ \\t]*(?::=|=|:)[ \\t]*${VALUE}`, 'g')
const BEARER = new RegExp(`(?<![A-Za-z0-9_])(Bearer)[ \\t]+${VALUE}`, 'g')

const VALUE_MIN = 16
const ENTROPY_MIN = 3.5
// A reference, a path or an address: what names a value rather than holds one.
const NOT_A_VALUE = /^(?:\$|%|~|\.{0,2}\/|[a-z][a-z0-9+.-]*:\/\/)/i
// Unquoted, an expression in code rather than a literal: a dotted name
// (`process.env.API_KEY`, `credentials.password`) or a bare identifier with no
// digit (`userSuppliedPassword`); a credential almost always carries a digit.
const REFERENCE = /^[A-Za-z_$][A-Za-z_$]*(?:\.[A-Za-z_$][A-Za-z_$]*)*$/

/** Shannon entropy of the string's characters, in bits per character. */
export function entropy(text: string): number {
  const counts = new Map<string, number>()
  for (const c of text) counts.set(c, (counts.get(c) ?? 0) + 1)
  let bits = 0
  for (const n of counts.values()) {
    const p = n / text.length
    bits -= p * Math.log2(p)
  }
  return bits
}

// A line that may hold a secret-named assignment: only these are searched for
// one, so a long output of ordinary lines costs one quick test each.
// The separators match `isSecretName`'s split (`_`, `-`, `.`, or none).
const MAY_ASSIGN = /token|secret|passw|api[_.-]?key|private[_.-]?key|bearer|credential/i

function assignments(text: string): Span[] {
  const spans: Span[] = []
  let at = 0
  for (const line of text.split('\n')) {
    if (MAY_ASSIGN.test(line)) {
      for (const [pattern, nameAt, valueAt] of [[ASSIGNMENT, 2, 4], [BEARER, 1, 3]] as const) {
        for (const m of line.matchAll(pattern)) {
          const value = m[valueAt] ?? ''
          if (!isSecretName(m[nameAt] ?? '')) continue
          if (value.length < VALUE_MIN || NOT_A_VALUE.test(value) || entropy(value) < ENTROPY_MIN) continue
          // Unquoted and followed by a call or an index, or shaped as a name: code.
          const after = line[(m.index ?? 0) + m[0].length]
          if (!m[valueAt - 1] && (after === '(' || after === '[' || REFERENCE.test(value))) continue
          const end = at + (m.index ?? 0) + m[0].length
          spans.push({ start: end - value.length, end, kind: 'assignment' })
        }
      }
    }
    at += line.length + 1
  }
  return spans
}

/**
 * The token-shaped strings in `text`, in order and never overlapping: each
 * span the bytes a handle stands for, `kind` the rule that found it.
 */
export function detect(text: string): Span[] {
  const found: Span[] = []
  for (const { kind, pattern } of RULES) {
    for (const m of text.matchAll(pattern)) {
      const start = m.index ?? 0
      if (start > 0 && NOT_LEAD.test(text[start - 1]!)) continue
      found.push({ start, end: start + m[0].length, kind })
    }
  }
  found.push(...assignments(text))
  return keepFirst(found, text.length)
}
