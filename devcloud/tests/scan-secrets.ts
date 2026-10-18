// Acceptance 6's scanner, built from the secrets guard's own parts. It never
// prints a value: a finding names a path, a rule or a label, and an offset.
//
//   bun scan-secrets.ts scan <dir|-> [--values <file|->]... [--store <dir>]...
//       Pattern detections (the guard's detect()) and known values (the guard's
//       matcher, fed the values in-process, every spelling it scrubs) in every
//       regular file under <dir>, or in stdin with `-`:
//         pattern <path> <kind> <offset>
//         known   <path> <label>
//       --values reads a JSON array of strings (labels value#1, value#2, ...)
//       or an object of label -> value; --store reads a secret store's files
//       (both tiers), labelled by key.
//   bun scan-secrets.ts credential-files <root>
//       Each credential file the guard knows (and the secret store) present
//       under any home in <root>/etc/passwd:  credential-file <path>
//
// stderr ends with `scanned <n> files, <m> values`. Exit 0 when the scan ran;
// 2 on a usage error; 3 when an input could not be read (each named on stderr
// as `unreadable <path>`), so a scan never passes by reading nothing.
// Known values are looked for in every byte of every regular file: binaries
// too, and files of any size, read in chunks that overlap by the longest
// spelling. Pattern detection, as the guard reads text, skips files holding a
// NUL in their first 8 KiB and files past 64 MiB.
import { closeSync, existsSync, lstatSync, openSync, readdirSync, readFileSync, readSync } from 'node:fs'
import { join } from 'node:path'
import { detect } from '../hooks/mods/secrets-detect.tsx'
import { Handles, SCRUB_MIN, spellings, type Known } from '../hooks/mods/secrets-handles.tsx'
import { CREDENTIAL_FILES, GCLOUD_DIR, GCLOUD_SKIP, STORE_DIR, storeValue } from '../hooks/mods/secrets-sources.tsx'

const MAX = 64 << 20
const CHUNK = 16 << 20
let files = 0
let unreadable = 0

function fail(path: string) {
  unreadable++
  console.error(`unreadable ${path}`)
}

// Every non-empty regular file under `dir`, with its size.
function walk(dir: string, visit: (path: string, size: number) => void) {
  let names: string[]
  try { names = readdirSync(dir) } catch { fail(dir); return }
  for (const name of names) {
    const path = join(dir, name)
    let stat
    try { stat = lstatSync(path) } catch { fail(path); continue }
    if (stat.isDirectory()) walk(path, visit)
    else if (stat.isFile() && stat.size > 0) visit(path, stat.size)
  }
}

function readWhole(path: string): Buffer | null {
  try { return readFileSync(path) } catch { fail(path); return null }
}

function knownValues(sources: string[], stores: string[]): Known[] {
  const known: Known[] = []
  for (const source of sources) {
    const parsed = JSON.parse(readFileSync(source === '-' ? 0 : source, 'utf8'))
    if (Array.isArray(parsed)) parsed.forEach((value, i) => known.push({ label: `value#${i + 1}`, value: String(value) }))
    else for (const [label, value] of Object.entries(parsed)) known.push({ label, value: String(value) })
  }
  for (const store of stores) {
    walk(store, (path) => {
      const bytes = readWhole(path)
      if (bytes) known.push({ label: `store:${path.slice(store.length + 1)}`, value: storeValue(bytes.toString('utf8')) })
    })
  }
  return known.filter((k) => k.value.length >= SCRUB_MIN)
}

function scan(target: string, known: Known[]) {
  // The guard's matcher decides: a byte search for each spelling it scrubs
  // finds where to look, and the text around a hit goes to Handles.scrub,
  // which must answer with that value's handle.
  const handles = new Handles('scan')
  const internal = known.map((k, i) => ({ label: `k${i}`, value: k.value }))
  handles.setKnown(internal)
  const probes = internal.map((k) => spellings(k.value).map((s) => Buffer.from(s.text, 'utf8')))
  const longest = Math.max(0, ...probes.flat().map((b) => b.length))

  const confirmed = (bytes: Buffer, at: number, length: number, i: number) => {
    const window = bytes.subarray(Math.max(0, at - 64), at + length + 64).toString('utf8')
    const scrubbed = handles.scrub(window)
    return scrubbed.includes(`[secret:k${i}]`) || scrubbed.includes(`[secret:k${i}~`)
  }
  // The values found in `bytes`, by index.
  const knownIn = (bytes: Buffer, found: Set<number>) => {
    probes.forEach((spelled, i) => {
      if (found.has(i)) return
      for (const probe of spelled) {
        for (let at = bytes.indexOf(probe); at >= 0; at = bytes.indexOf(probe, at + 1)) {
          if (confirmed(bytes, at, probe.length, i)) { found.add(i); return }
        }
      }
    })
  }
  const report = (path: string, found: Set<number>) => {
    for (const i of [...found].sort((a, b) => a - b)) console.log(`known\t${path}\t${known[i].label}`)
  }

  const whole = (path: string, bytes: Buffer) => {
    files++
    const found = new Set<number>()
    knownIn(bytes, found)
    report(path, found)
    if (bytes.length <= MAX && !bytes.subarray(0, 8192).includes(0)) {
      for (const span of detect(bytes.toString('utf8'))) console.log(`pattern\t${path}\t${span.kind}\t${span.start}`)
    }
  }
  const streamed = (path: string) => {
    let fd: number
    try { fd = openSync(path, 'r') } catch { fail(path); return }
    const found = new Set<number>()
    try {
      const overlap = Math.max(0, longest - 1)
      let carry = Buffer.alloc(0)
      const chunk = Buffer.alloc(CHUNK)
      for (;;) {
        const n = readSync(fd, chunk, 0, CHUNK, null)
        if (n === 0) break
        const bytes = Buffer.concat([carry, chunk.subarray(0, n)])
        knownIn(bytes, found)
        carry = Buffer.from(bytes.subarray(Math.max(0, bytes.length - overlap)))
      }
      files++
    } catch {
      fail(path)
    } finally {
      closeSync(fd)
    }
    report(path, found)
  }

  if (target === '-') whole('<stdin>', readFileSync(0))
  else walk(target, (path, size) => {
    if (size > MAX) return streamed(path)
    const bytes = readWhole(path)
    if (bytes) whole(path, bytes)
  })
}

function credentialFiles(root: string) {
  let passwd: string
  try { passwd = readFileSync(join(root, 'etc/passwd'), 'utf8') } catch { fail(join(root, 'etc/passwd')); return }
  const homes = new Set(passwd.split('\n').map((line) => line.split(':')[5]).filter((home) => home && home !== '/'))
  for (const home of homes) {
    const base = join(root, home)
    files++
    const present = (rel: string) => existsSync(join(base, rel)) && console.log(`credential-file\t${join(home, rel)}`)
    for (const { path } of CREDENTIAL_FILES) present(path)
    present(STORE_DIR)
    const gcloud = join(base, GCLOUD_DIR)
    if (existsSync(gcloud)) {
      walk(gcloud, (path) => {
        const rel = path.slice(gcloud.length + 1)
        if (path.endsWith('.json') && !GCLOUD_SKIP.has(rel.split('/')[0])) console.log(`credential-file\t${path.slice(root.length)}`)
      })
    }
  }
}

const [mode, target, ...rest] = process.argv.slice(2)
const values: string[] = []
const stores: string[] = []
for (let i = 0; i < rest.length; i += 2) {
  if (rest[i] === '--values' && rest[i + 1]) values.push(rest[i + 1])
  else if (rest[i] === '--store' && rest[i + 1]) stores.push(rest[i + 1])
  else { console.error(`unknown argument ${rest[i]}`); process.exit(2) }
}
let count = 0
if (mode === 'scan' && target) {
  const known = knownValues(values, stores)
  count = known.length
  scan(target, known)
} else if (mode === 'credential-files' && target) {
  credentialFiles(target)
} else {
  console.error('usage: bun scan-secrets.ts scan <dir|-> [--values <file|->]... [--store <dir>]... | credential-files <root>')
  process.exit(2)
}
console.error(`scanned ${files} files, ${count} values`)
process.exit(unreadable ? 3 : 0)
