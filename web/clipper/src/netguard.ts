// The network boundary: every request the tool makes, and every request a
// page makes it make, goes to a public internet address only. A host is
// resolved, every address checked, and the connection pinned to the checked
// addresses, so a DNS answer that changes in between cannot slip through.
import { lookup as dnsLookup } from 'node:dns/promises'
import { isIP } from 'node:net'
import type { LookupFunction } from 'node:net'

export type Address = { address: string; family: number }

export class RefusedError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'RefusedError'
  }
}

/** The test seam: `WEB_ALLOW_HOSTS`, a comma-separated list of host:port exempted from the check. */
export function allowedHosts(env: NodeJS.ProcessEnv = process.env): Set<string> {
  return new Set((env.WEB_ALLOW_HOSTS ?? '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean))
}

export type ResolveOptions = {
  allow?: Set<string>
  resolve?: (host: string) => Promise<Address[]>
}

/** Resolves a host to the addresses a connection may use, or throws RefusedError. */
export async function resolveChecked(hostname: string, port: number, opts: ResolveOptions = {}): Promise<Address[]> {
  const host = hostname.replace(/^\[|\]$/g, '').toLowerCase()
  const allow = opts.allow ?? allowedHosts()
  const literal = isIP(host)
  const addresses: Address[] = literal
    ? [{ address: host, family: literal }]
    : await (opts.resolve ?? defaultResolve)(host)
  if (allow.has(`${hostname.toLowerCase()}:${port}`)) return addresses
  const bad = addresses.find(a => !isPublicAddress(a.address))
  if (bad) throw new RefusedError(`refused: ${host} resolves to a non-public address (${bad.address}); for a local server use curl through Bash`)
  if (addresses.length === 0) throw new Error(`no address for ${host}`)
  return addresses
}

async function defaultResolve(host: string): Promise<Address[]> {
  return (await dnsLookup(host, { all: true, verbatim: true })).map(a => ({ address: a.address, family: a.family }))
}

/** A connection lookup that answers only with the addresses already checked. */
export function pinnedLookup(addresses: Address[]): LookupFunction {
  return ((_host: string, options: { all?: boolean }, callback: (...args: unknown[]) => void) => {
    if (options?.all) callback(null, addresses)
    else callback(null, addresses[0].address, addresses[0].family)
  }) as unknown as LookupFunction
}

export function isPublicAddress(ip: string): boolean {
  const kind = isIP(ip)
  if (kind === 4) return publicV4(v4Bytes(ip))
  if (kind === 6) return publicV6(v6Bytes(ip))
  return false
}

// [first octets, prefix length]
const V4_REFUSED: [number[], number][] = [
  [[0], 8], [[10], 8], [[100, 64], 10], [[127], 8], [[169, 254], 16], [[172, 16], 12],
  [[192, 0, 0], 24], [[192, 0, 2], 24], [[192, 88, 99], 24], [[192, 168], 16], [[198, 18], 15],
  [[198, 51, 100], 24], [[203, 0, 113], 24], [[224], 4], [[240], 4],
]

function v4Bytes(ip: string): number[] {
  return ip.split('.').map(Number)
}

function inPrefix(bytes: number[], prefix: number[], bits: number): boolean {
  for (let i = 0; bits > 0; i++, bits -= 8) {
    const mask = bits >= 8 ? 0xff : (0xff << (8 - bits)) & 0xff
    if ((bytes[i] & mask) !== ((prefix[i] ?? 0) & mask)) return false
  }
  return true
}

function publicV4(b: number[]): boolean {
  return !V4_REFUSED.some(([p, bits]) => inPrefix(b, p, bits))
}

function v6Bytes(ip: string): number[] {
  let s = ip.replace(/%.*$/, '')
  let tail: number[] = []
  const dotted = /(\d+\.\d+\.\d+\.\d+)$/.exec(s)
  if (dotted) {
    tail = v4Bytes(dotted[1])
    s = s.slice(0, -dotted[1].length) + '0:0'
  }
  const [head, rest] = s.includes('::') ? s.split('::') : [s, undefined]
  const h = head ? head.split(':') : []
  const r = rest !== undefined && rest !== '' ? rest.split(':') : []
  const groups = rest === undefined ? h : [...h, ...Array(8 - h.length - r.length).fill('0'), ...r]
  const bytes = groups.flatMap(g => { const n = parseInt(g || '0', 16); return [n >> 8, n & 0xff] })
  if (tail.length) bytes.splice(12, 4, ...tail)
  return bytes
}

function publicV6(b: number[]): boolean {
  const zero = (from: number, to: number) => b.slice(from, to).every(x => x === 0)
  if (zero(0, 16)) return false // ::
  if (zero(0, 15) && b[15] === 1) return false // ::1
  if (zero(0, 10) && b[10] === 0xff && b[11] === 0xff) return publicV4(b.slice(12)) // ::ffff:a.b.c.d
  if (zero(0, 12)) return publicV4(b.slice(12)) // ::a.b.c.d (IPv4-compatible)
  if (inPrefix(b, [0x00, 0x64, 0xff, 0x9b], 32) && zero(4, 12)) return publicV4(b.slice(12)) // 64:ff9b::/96 NAT64
  if (inPrefix(b, [0x20, 0x02], 16)) return publicV4(b.slice(2, 6)) // 2002::/16 6to4
  if (inPrefix(b, [0xfc], 7)) return false // unique local
  if (inPrefix(b, [0xfe, 0x80], 10)) return false // link-local
  if (inPrefix(b, [0xfe, 0xc0], 10)) return false // site-local (deprecated)
  if (inPrefix(b, [0xff], 8)) return false // multicast
  if (inPrefix(b, [0x20, 0x01, 0x0d, 0xb8], 32)) return false // documentation
  if (inPrefix(b, [0x01, 0x00], 64)) return false // discard-only 100::/64
  return true
}
