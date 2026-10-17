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
// stderr ends with `scanned <n> text files, <m> values`. Exit 0 when the scan
// ran; 2 on a usage error; 3 when an input could not be read (each named on
// stderr as `unreadable <path>`), so a scan never passes by reading nothing.
// Files holding a NUL in their first 8 KiB (binaries) and files past 64 MiB
// are skipped, as the guard never reads them as text.
import { existsSync, lstatSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { detect } from '../hooks/mods/secrets-detect.tsx'
import { Handles, SCRUB_MIN, spellings, type Known } from '../hooks/mods/secrets-handles.tsx'
import { CREDENTIAL_FILES, GCLOUD_DIR, GCLOUD_SKIP, STORE_DIR, storeValue } from '../hooks/mods/secrets-sources.tsx'

const MAX = 64 << 20
let files = 0
let unreadable = 0

function fail(path: string) {
  unreadable++
  console.error(`unreadable ${path}`)
}

function walk(dir: string, visit: (path: string, bytes: Buffer) => void) {
  let names: string[]
  try { names = readdirSync(dir) } catch { fail(dir); return }
  for (const name of names) {
    const path = join(dir, name)
    let stat
    try { stat = lstatSync(path) } catch { fail(path); continue }
    if (stat.isDirectory()) walk(path, visit)
    else if (stat.isFile() && stat.size > 0 && stat.size <= MAX) {
      let bytes: Buffer
      try { bytes = readFileSync(path) } catch { fail(path); continue }
      visit(path, bytes)
    }
  }
}

function knownValues(sources: string[], stores: string[]): Known[] {
  const known: Known[] = []
  for (const source of sources) {
    const parsed = JSON.parse(readFileSync(source === '-' ? 0 : source, 'utf8'))
    if (Array.isArray(parsed)) parsed.forEach((value, i) => known.push({ label: `value#${i + 1}`, value: String(value) }))
    else for (const [label, value] of Object.entries(parsed)) known.push({ label, value: String(value) })
  }
  for (const store of stores) {
    walk(store, (path, bytes) => {
      const rel = path.slice(store.length + 1)
      known.push({ label: `store:${rel}`, value: storeValue(bytes.toString('utf8')) })
    })
  }
  return known.filter((k) => k.value.length >= SCRUB_MIN)
}

function scan(target: string, known: Known[]) {
  // The guard's matcher decides; the spellings only pick which files to hand it.
  const handles = new Handles('scan')
  const internal = known.map((k, i) => ({ label: `k${i}`, value: k.value }))
  handles.setKnown(internal)
  const probes = internal.map((k) => spellings(k.value).map((s) => s.text))
  const visit = (path: string, bytes: Buffer) => {
    if (bytes.subarray(0, 8192).includes(0)) return
    files++
    const text = bytes.toString('utf8')
    for (const span of detect(text)) console.log(`pattern\t${path}\t${span.kind}\t${span.start}`)
    const hits = probes.flatMap((texts, i) => (texts.some((t) => text.includes(t)) ? [i] : []))
    if (hits.length === 0) return
    const scrubbed = handles.scrub(text)
    for (const i of hits) if (scrubbed.includes(`[secret:k${i}]`) || scrubbed.includes(`[secret:k${i}~`)) console.log(`known\t${path}\t${known[i].label}`)
  }
  if (target === '-') visit('<stdin>', readFileSync(0))
  else walk(target, visit)
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
console.error(`scanned ${files} text files, ${count} values`)
process.exit(unreadable ? 3 : 0)
