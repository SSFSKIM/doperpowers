// Rendering a page that only shows its content after its scripts run:
// headless Chromium with --dump-dom, behind the filtering proxy, with the
// traffic a proxy setting does not cover (WebRTC's UDP, QUIC) switched off.
import { spawn } from 'node:child_process'
import { existsSync, readdirSync, statSync } from 'node:fs'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { homedir, tmpdir } from 'node:os'
import { delimiter, join } from 'node:path'
import { USER_AGENT } from './http.ts'
import { startEgressProxy } from './proxy.ts'

export const RENDER_LIMITS = { timeoutMs: 30_000, virtualTimeBudgetMs: 10_000, maxBytes: 50 * 1048576 }

export type Chrome = { path: string; headless: string } | { note: string }

const UNAVAILABLE = 'rendering unavailable on this machine: '

const isExecutable = (p: string) => { try { return statSync(p).isFile() } catch { return false } }

/**
 * The Chromium to render with. `WEB_CHROME`, when set, is the only candidate;
 * unset: the newest Playwright headless shell, Google Chrome on macOS, then
 * chromium or google-chrome on PATH.
 */
export function findChrome(env: NodeJS.ProcessEnv, platform: NodeJS.Platform = process.platform): Chrome {
  const set = env.WEB_CHROME
  if (set !== undefined && set !== '') {
    if (set === 'none') return { note: UNAVAILABLE + 'turned off by WEB_CHROME=none' }
    if (!isExecutable(set)) return { note: UNAVAILABLE + `WEB_CHROME=${set} does not exist` }
    return { path: set, headless: set.includes('headless-shell') ? '--headless' : '--headless=new' }
  }
  const cache = env.PLAYWRIGHT_BROWSERS_PATH && env.PLAYWRIGHT_BROWSERS_PATH !== '0'
    ? env.PLAYWRIGHT_BROWSERS_PATH
    : platform === 'darwin' ? join(env.HOME || homedir(), 'Library', 'Caches', 'ms-playwright') : join(env.HOME || homedir(), '.cache', 'ms-playwright')
  const shells = safeList(cache)
    .map(name => ({ name, rev: Number(/^chromium_headless_shell-(\d+)$/.exec(name)?.[1] ?? NaN) }))
    .filter(s => !Number.isNaN(s.rev))
    .sort((a, b) => b.rev - a.rev)
  for (const { name } of shells) {
    for (const sub of safeList(join(cache, name)).filter(s => s.startsWith('chrome-headless-shell-'))) {
      const bin = join(cache, name, sub, 'chrome-headless-shell')
      if (isExecutable(bin)) return { path: bin, headless: '--headless' }
    }
  }
  if (platform === 'darwin') {
    const app = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if (isExecutable(app)) return { path: app, headless: '--headless=new' }
  }
  for (const cmd of ['chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable']) {
    for (const dir of (env.PATH ?? '').split(delimiter).filter(Boolean)) {
      if (isExecutable(join(dir, cmd))) return { path: join(dir, cmd), headless: '--headless=new' }
    }
  }
  return { note: UNAVAILABLE + 'no Chromium found (set WEB_CHROME)' }
}

function safeList(dir: string): string[] {
  try { return existsSync(dir) ? readdirSync(dir) : [] } catch { return [] }
}

/** The document the browser was served: where it ended up and with what status. */
export type ServedDocument = { url: string; status: number }
export type RenderResult = { html: string; document?: ServedDocument } | { note: string }

/**
 * The page's DOM after its scripts ran, with the document Chromium's NetLog
 * says it was served (absent when the log names none), or a note saying why
 * there is none. The DOM alone cannot tell a page from a denial page.
 */
export async function renderDom(url: string, chrome: { path: string; headless: string }, timeoutMs: number, allow: Set<string>): Promise<RenderResult> {
  if (timeoutMs <= 0) return { note: 'rendering skipped: the time budget was spent; the plain fetch is kept' }
  let proxy
  try {
    proxy = await startEgressProxy(allow)
  } catch (e) {
    return { note: `rendering skipped: its egress proxy could not start (${e instanceof Error ? e.message : e}); the plain fetch is kept` }
  }
  const profile = await mkdtemp(join(tmpdir(), 'clip-chrome-'))
  try {
    const out = await runChrome(chrome, url, profile, proxy.port, timeoutMs)
    if ('note' in out) return out
    const document = servedDocument(await readFile(netLogPath(profile), 'utf8').catch(() => ''))
    return document ? { ...out, document } : out
  } finally {
    await proxy.close()
    await rm(profile, { recursive: true, force: true }).catch(() => {})
  }
}

/** Without the proxy and egress flags Chromium does not run. */
export function chromeArgs(headless: string, profile: string, proxyPort: number, url: string): string[] {
  return [
    headless,
    '--dump-dom',
    `--log-net-log=${netLogPath(profile)}`,
    `--user-data-dir=${profile}`,
    `--virtual-time-budget=${RENDER_LIMITS.virtualTimeBudgetMs}`,
    `--proxy-server=http://127.0.0.1:${proxyPort}`,
    '--proxy-bypass-list=<-loopback>',
    '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
    '--disable-quic',
    `--user-agent=${USER_AGENT}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-default-apps',
    '--disable-sync',
    '--mute-audio',
    '--hide-scrollbars',
    url,
  ]
}

function runChrome(chrome: { path: string; headless: string }, url: string, profile: string, proxyPort: number, timeoutMs: number): Promise<RenderResult> {
  return new Promise(resolve => {
    const child = spawn(chrome.path, chromeArgs(chrome.headless, profile, proxyPort, url), { stdio: ['ignore', 'pipe', 'pipe'], detached: true })
    const out: Buffer[] = []
    let size = 0
    let stderr = ''
    let settled = false
    const finish = (r: RenderResult) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      killGroup(child.pid)
      resolve(r)
    }
    const timer = setTimeout(() => finish({ note: `rendering stopped after ${Math.round(timeoutMs / 1000)} s; the plain fetch is kept` }), timeoutMs)
    child.stdout.on('data', (d: Buffer) => {
      size += d.length
      if (size > RENDER_LIMITS.maxBytes) finish({ note: 'rendering failed: the rendered page passed 50 MB; the plain fetch is kept' })
      else out.push(d)
    })
    child.stderr.on('data', (d: Buffer) => { stderr = (stderr + d.toString()).slice(-400) })
    child.on('error', e => finish({ note: `rendering failed: ${e.message}; the plain fetch is kept` }))
    child.on('close', code => {
      const html = Buffer.concat(out).toString('utf8')
      if (code === 0 && html.trim()) finish({ html })
      else finish({ note: `rendering failed: Chromium exited ${code}${stderr ? ` (${lastLine(stderr)})` : ''}; the plain fetch is kept` })
    })
  })
}

const lastLine = (s: string) => s.trim().split('\n').pop()!.slice(0, 200)

const netLogPath = (profile: string) => join(profile, 'netlog.json')

type NetLogEvent = { source?: { id?: number }; type?: number; params?: { url?: string; request_type?: string; headers?: string[] } }

/**
 * The main-frame document a NetLog records answering last: its URL after
 * redirects and its HTTP status. A page that reloads itself (a challenge
 * passed) is the later navigation, which is what the DOM holds.
 */
export function servedDocument(netLog: string): ServedDocument | undefined {
  let log: { constants?: { logEventTypes?: Record<string, number> }; events?: NetLogEvent[] }
  try { log = JSON.parse(netLog) } catch { return undefined }
  const types = log.constants?.logEventTypes ?? {}
  const startJob = types.URL_REQUEST_START_JOB
  const responseHeaders = types.HTTP_TRANSACTION_READ_RESPONSE_HEADERS
  const urlOf = new Map<number, string>() // main-frame request → its current URL
  let served: ServedDocument | undefined
  for (const e of log.events ?? []) {
    const source = e.source?.id
    if (source === undefined) continue
    if (e.type === startJob && e.params?.url) {
      if (e.params.request_type === 'main frame') urlOf.set(source, e.params.url)
    } else if (e.type === responseHeaders && urlOf.has(source)) {
      const status = Number(/^HTTP\/[\d.]+ (\d{3})/.exec(e.params?.headers?.[0] ?? '')?.[1])
      if (status) served = { url: urlOf.get(source)!, status }
    }
  }
  return served
}

function killGroup(pid: number | undefined) {
  if (!pid) return
  try { process.kill(-pid, 'SIGKILL') } catch {}
}
