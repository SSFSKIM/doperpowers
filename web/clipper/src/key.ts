// The cache key: one entry folder per requested URL.
import { createHash } from 'node:crypto'
import { join } from 'node:path'

/** Scheme and host lowercased, default port and fragment dropped, query kept. */
export function normalizeUrl(url: URL): string {
  const u = new URL(url.href) // the WHATWG parser already lowercases and drops default ports
  u.hash = ''
  return u.href
}

export function entryDir(root: string, url: URL): string {
  const key = normalizeUrl(url)
  const hash = createHash('sha256').update(key).digest('hex').slice(0, 8)
  const host = url.hostname.toLowerCase().replace(/[^a-z0-9.-]+/g, '_') + (url.port ? `_${url.port}` : '')
  const slug = url.pathname.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60).replace(/-+$/, '') || 'index'
  return join(root, host, `${slug}-${hash}`)
}
