// Made-up secrets for the tests, built at run time so that no file in the
// repository holds a token-shaped string a scanner would flag. Deterministic:
// the same seed gives the same characters.
const ALNUM = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'

export function chars(length: number, seed = 1, alphabet = ALNUM): string {
  let x = seed * 2654435761 >>> 0
  let out = ''
  for (let i = 0; i < length; i++) {
    x = (x * 1103515245 + 12345) >>> 0
    out += alphabet[(x >>> 16) % alphabet.length]
  }
  return out
}

/** A token-shaped string: `prefix` (split so it is never written whole) and `length` random characters. */
export const token = (prefix: readonly string[], length: number, seed = 1, alphabet = ALNUM) => prefix.join('') + chars(length, seed, alphabet)

export const githubPat = (seed = 1) => token(['gh', 'p_'], 36, seed)
export const anthropicKey = (seed = 1) => token(['sk-', 'ant-', 'api03-'], 93, seed, ALNUM + '-_')
export const awsKey = (seed = 1) => token(['AK', 'IA'], 16, seed, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567')
export const pem = (seed = 1) =>
  ['-----BEGIN ', 'PRIVATE KEY-----\n', chars(64, seed), '\n', chars(64, seed + 1), '\n-----END ', 'PRIVATE KEY-----'].join('')
