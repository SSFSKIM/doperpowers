/**
 * The detector: where a text holds a token-shaped string. Pure, so the tests
 * pin it without a session. gitleaks' rule set is the reference for the
 * prefixes; a bare run of hex or base64 with neither a prefix nor a
 * secret-named assignment is never a span, or commit hashes and checksums
 * would drown the transcript.
 */

export type Span = { start: number; end: number; kind: string }

// Not inside a longer word: `risk-…` holds no `sk-` token.
const LEAD = '(?<![A-Za-z0-9_])'

// In order: the first rule to claim a character keeps it.
const RULES: readonly { kind: string; pattern: RegExp }[] = [
  // PEM blocks, raw or JSON-escaped (`\n` as two characters, as a key file prints).
  {
    kind: 'pem',
    pattern: /-----BEGIN ((?:[A-Z0-9]+ )*)PRIVATE KEY( BLOCK)?-----[\s\S]*?-----END \1PRIVATE KEY\2-----/g,
  },
  { kind: 'anthropic', pattern: new RegExp(`${LEAD}sk-ant-[A-Za-z0-9_-]{20,}`, 'g') },
  { kind: 'openrouter', pattern: new RegExp(`${LEAD}sk-or-v1-[A-Za-z0-9]{20,}`, 'g') },
  { kind: 'openai', pattern: new RegExp(`${LEAD}sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}`, 'g') },
  { kind: 'github-pat', pattern: new RegExp(`${LEAD}ghp_[A-Za-z0-9]{30,}`, 'g') },
  { kind: 'github-oauth', pattern: new RegExp(`${LEAD}gho_[A-Za-z0-9]{30,}`, 'g') },
  { kind: 'github-app-token', pattern: new RegExp(`${LEAD}gh[us]_[A-Za-z0-9]{30,}`, 'g') },
  { kind: 'github-refresh-token', pattern: new RegExp(`${LEAD}ghr_[A-Za-z0-9]{30,}`, 'g') },
  { kind: 'github-fine-grained-pat', pattern: new RegExp(`${LEAD}github_pat_[A-Za-z0-9_]{22,}`, 'g') },
  { kind: 'tailscale', pattern: new RegExp(`${LEAD}tskey-[A-Za-z0-9-]{16,}`, 'g') },
  { kind: 'slack', pattern: new RegExp(`${LEAD}xox[abprs]-[A-Za-z0-9-]{10,}`, 'g') },
  { kind: 'aws-access-key', pattern: new RegExp(`${LEAD}(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Za-z])`, 'g') },
  { kind: 'gitlab-pat', pattern: new RegExp(`${LEAD}glpat-[A-Za-z0-9_-]{20,}`, 'g') },
  { kind: 'huggingface', pattern: new RegExp(`${LEAD}hf_[A-Za-z0-9]{30,}`, 'g') },
  { kind: 'gcp-api-key', pattern: new RegExp(`${LEAD}AIza[0-9A-Za-z_-]{35}`, 'g') },
]

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

function assignments(text: string): Span[] {
  const spans: Span[] = []
  for (const [pattern, nameAt, valueAt] of [[ASSIGNMENT, 2, 4], [BEARER, 1, 3]] as const) {
    for (const m of text.matchAll(pattern)) {
      const value = m[valueAt] ?? ''
      if (!isSecretName(m[nameAt] ?? '')) continue
      if (value.length < VALUE_MIN || NOT_A_VALUE.test(value) || entropy(value) < ENTROPY_MIN) continue
      const end = (m.index ?? 0) + m[0].length
      spans.push({ start: end - value.length, end, kind: 'assignment' })
    }
  }
  return spans
}

/**
 * The token-shaped strings in `text`, in order and never overlapping: each
 * span the bytes a handle stands for, `kind` the rule that found it.
 */
export function detect(text: string): Span[] {
  const claimed: Span[] = []
  const overlaps = (s: Span) => claimed.some((c) => s.start < c.end && c.start < s.end)
  for (const { kind, pattern } of RULES) {
    for (const m of text.matchAll(pattern)) {
      const span = { start: m.index ?? 0, end: (m.index ?? 0) + m[0].length, kind }
      if (!overlaps(span)) claimed.push(span)
    }
  }
  for (const span of assignments(text)) if (!overlaps(span)) claimed.push(span)
  return claimed.sort((a, b) => a.start - b.start)
}
