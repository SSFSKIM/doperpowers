// Rendering a page that only shows its content after its scripts run:
// headless Chromium driven over the DevTools protocol on a pipe, behind the
// filtering proxy, with the traffic a proxy setting does not cover (WebRTC's
// UDP, QUIC) switched off.
import { existsSync, readdirSync, statSync } from 'node:fs'
import { mkdtemp, open, readFile, rm } from 'node:fs/promises'
import { homedir, tmpdir } from 'node:os'
import { delimiter, join } from 'node:path'
import { launch, OVER_LIMIT } from './cdp.ts'
import type { Browser } from './cdp.ts'
import { USER_AGENT } from './http.ts'
import { startEgressProxy } from './proxy.ts'
import type { Boundary } from './netguard.ts'

/**
 * `closeReserveMs`: how far inside the limit the DOM is taken from a page still
 * loading. `settleMs`, `quietMs`, `stepMs`: the watch after the virtual-time
 * budget (see `settle`).
 */
export const RENDER_LIMITS = {
  timeoutMs: 30_000, virtualTimeBudgetMs: 10_000, closeReserveMs: 3_000,
  settleMs: 5_000, quietMs: 500, stepMs: 100, maxBytes: 50 * 1048576,
}

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
/** `unsettled`, beside a DOM, is the note saying the page was still loading when it was taken. */
export type RenderResult = { html: string; document?: ServedDocument; unsettled?: string } | { note: string }

/**
 * The page's DOM after its scripts ran, with the document Chromium's NetLog
 * says it was served (absent when the log names none), or a note saying why
 * there is none. The DOM alone cannot tell a page from a denial page.
 */
export async function renderDom(url: string, chrome: { path: string; headless: string }, timeoutMs: number, boundary: Boundary): Promise<RenderResult> {
  if (timeoutMs <= 0) return { note: 'rendering skipped: the time budget was spent; the plain fetch is kept' }
  let proxy
  try {
    proxy = await startEgressProxy(boundary)
  } catch (e) {
    return { note: `rendering skipped: its egress proxy could not start (${e instanceof Error ? e.message : e}); the plain fetch is kept` }
  }
  const profile = await mkdtemp(join(tmpdir(), 'clip-chrome-'))
  try {
    return await drive(chrome, url, profile, proxy.port, timeoutMs)
  } finally {
    await proxy.close()
    await rm(profile, { recursive: true, force: true }).catch(() => {})
  }
}

/** Without the proxy and egress flags Chromium does not run. */
export function chromeArgs(headless: string, profile: string, proxyPort: number): string[] {
  return [
    headless,
    `--log-net-log=${netLogPath(profile)}`,
    `--user-data-dir=${profile}`,
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
  ]
}

/**
 * One render, driven over the DevTools protocol. It waits as
 * `--dump-dom --virtual-time-budget` did, for the load event and then for the
 * virtual-time budget, during which the page's clock stands still while any
 * request is pending, and then lets the page settle (see `settle`). A request
 * held open for good (an event stream) stops that clock for good, and
 * `--dump-dom` never printed; here the DOM is taken as it stands at the cap, a
 * few seconds inside the render's limit so the browser can close its NetLog.
 */
async function drive(chrome: { path: string; headless: string }, url: string, profile: string, proxyPort: number, timeoutMs: number): Promise<RenderResult> {
  const started = Date.now()
  const endAt = started + timeoutMs
  const capMs = timeoutMs - Math.min(RENDER_LIMITS.closeReserveMs, timeoutMs / 4)
  const capAt = started + capMs
  const browser = launch(chrome.path, chromeArgs(chrome.headless, profile, proxyPort), 2 * RENDER_LIMITS.maxBytes)
  let timedOut = false
  const timer = setTimeout(() => { timedOut = true; browser.kill() }, timeoutMs)
  try {
    let page
    try {
      page = await dumpPage(browser, url, capAt)
    } catch (e) {
      if (timedOut) return { note: `rendering stopped after ${Math.round(timeoutMs / 1000)} s; the plain fetch is kept` }
      if (browser.failure() === OVER_LIMIT) return { note: TOO_BIG }
      const why = e instanceof Error ? e.message : String(e)
      const tail = why.startsWith('Chromium exited') && browser.stderr() ? ` (${lastLine(browser.stderr())})` : ''
      return { note: `rendering failed: ${why}${tail}; the plain fetch is kept` }
    }
    if (Buffer.byteLength(page.html) > RENDER_LIMITS.maxBytes) return { note: TOO_BIG }
    browser.send('Browser.close').catch(() => {})
    // A loaded machine can take seconds to close the log: the wait may run to the render's limit.
    const document = servedDocument(await closedNetLog(netLogPath(profile), browser.exited, endAt))
    return {
      html: page.html,
      ...(document ? { document } : {}),
      ...(page.settled ? {} : { unsettled: `the page was still loading after ${Math.round(capMs / 1000)} s; this is how headless Chromium had rendered it by then` }),
    }
  } finally {
    clearTimeout(timer)
    browser.kill()
  }
}

/**
 * The NetLog once Chromium has closed it, which it does within a moment of
 * Browser.close, though the process can take ten seconds more to exit; else
 * as it stands when the process has gone or `by` has come.
 */
async function closedNetLog(path: string, exited: Promise<void>, by: number): Promise<string> {
  let gone = false
  void exited.then(() => { gone = true })
  for (;;) {
    // A closed log ends its JSON object; until then each event ends in a comma.
    if (/\}\s*$/.test(await tail(path, 16))) {
      const text = await readFile(path, 'utf8').catch(() => '')
      try { JSON.parse(text); return text } catch {}
    }
    if (gone || Date.now() >= by) return readFile(path, 'utf8').catch(() => '')
    await new Promise(resolve => setTimeout(resolve, 25))
  }
}

async function tail(path: string, bytes: number): Promise<string> {
  let file
  try {
    file = await open(path)
    const { size } = await file.stat()
    const buf = Buffer.alloc(Math.min(bytes, size))
    await file.read(buf, 0, buf.length, size - buf.length)
    return buf.toString('utf8')
  } catch {
    return ''
  } finally {
    await file?.close()
  }
}

const TOO_BIG = 'rendering failed: the rendered page passed 50 MB; the plain fetch is kept'
const DUMP = "(document.doctype ? new XMLSerializer().serializeToString(document.doctype) + '\\n' : '') + document.documentElement.outerHTML"

/** The page's DOM, and whether it settled (loaded, spent its virtual-time budget, and settled) before `capAt`. */
async function dumpPage(browser: Browser, url: string, capAt: number): Promise<{ html: string; settled: boolean }> {
  const { targetId } = await browser.send('Target.createTarget', { url: 'about:blank' })
  const { sessionId } = await browser.send('Target.attachToTarget', { targetId, flatten: true })
  const send = (method: string, params?: object) => browser.send(method, params, sessionId)

  // What the waits below wait for is recorded as it arrives, from before the
  // command that causes it (see Browser.on).
  let navigating = false
  let budgetSpent = false
  let gone = false
  const loaded = new Set<string>()
  let recheck = () => {}
  browser.on('Page.lifecycleEvent', (p, sid) => {
    if (sid === sessionId && navigating && p.name === 'load') { loaded.add(p.frameId); recheck() }
  })
  browser.on('Emulation.virtualTimeBudgetExpired', (_p, sid) => {
    if (sid === sessionId) { budgetSpent = true; recheck() }
  })
  void browser.exited.then(() => { gone = true; recheck() })
  const until = (done: () => boolean) => new Promise<boolean>(resolve => {
    const finish = (v: boolean) => { clearTimeout(t); recheck = () => {}; resolve(v) }
    const t = setTimeout(() => finish(false), Math.max(0, capAt - Date.now()))
    recheck = () => { if (done() || gone) finish(!gone) }
    recheck()
  })

  await send('Page.enable')
  await send('Page.setLifecycleEventsEnabled', { enabled: true })
  navigating = true
  const nav = await send('Page.navigate', { url })
  if (nav.errorText) throw new Error(`the browser could not load the page (${nav.errorText})`)
  if (nav.isDownload) throw new Error('the browser took the page for a download')
  let settled = await until(() => loaded.has(nav.frameId))
  if (settled) {
    await send('Emulation.setVirtualTimePolicy', {
      policy: 'pauseIfNetworkFetchesPending', budget: RENDER_LIMITS.virtualTimeBudgetMs, maxVirtualTimeTaskStarvationCount: 9999,
    })
    settled = await until(() => budgetSpent) && await settle(send, capAt)
  } else {
    await send('Page.stopLoading')
  }
  const { result } = await send('Runtime.evaluate', { expression: DUMP, returnByValue: true })
  return { html: typeof result?.value === 'string' ? result.value : '', settled }
}

// How much there is on the page: elements, and characters of text.
const SHAPE = "document.getElementsByTagName('*').length + ':' + (document.body ? document.body.textContent.length : 0)"

/**
 * Content can still be on its way when the budget is spent, through what
 * virtual time does not wait for: a worker's request, the animation frame a
 * framework renders in, a timer it sets once data arrives. So the page's clock
 * runs on in steps of real time while its DOM is watched, and the DOM is taken
 * once it has not changed for `quietMs`, or `settleMs` after the budget (a page
 * that never stops changing). False when the cap came first.
 */
async function settle(send: (method: string, params?: object) => Promise<any>, capAt: number): Promise<boolean> {
  const { settleMs, quietMs, stepMs } = RENDER_LIMITS
  const end = Math.min(capAt, Date.now() + settleMs)
  let shape: unknown
  let since = Date.now()
  while (Date.now() < end) {
    // A failed read (the page navigating) counts as a change.
    const now = await send('Runtime.evaluate', { expression: SHAPE, returnByValue: true }).then(r => r?.result?.value, () => undefined)
    if (now === undefined || now !== shape) { shape = now; since = Date.now() } else if (Date.now() - since >= quietMs) return true
    await send('Emulation.setVirtualTimePolicy', { policy: 'pauseIfNetworkFetchesPending', budget: stepMs, maxVirtualTimeTaskStarvationCount: 9999 })
    await new Promise(resolve => setTimeout(resolve, stepMs))
  }
  return end < capAt
}
const lastLine = (s: string) => s.trim().split('\n').pop()!.slice(0, 200)

const netLogPath = (profile: string) => join(profile, 'netlog.json')

type NetLogEvent = { source?: { id?: number }; type?: number; params?: { url?: string; request_type?: string; headers?: string[] } }

/**
 * The main-frame document a NetLog records answering last: its URL after
 * redirects and its HTTP status. A page that reloads itself (a challenge
 * passed) is the later navigation, which is what the DOM holds. The log does
 * not say whether a response became the document, so one that could not have
 * (a redirect, 204/205, an attachment, an explicit type that is not HTML; a
 * missing type counts, since Chromium sniffs it) gives none: the DOM
 * is then some earlier document, of no known status.
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
      const [statusLine = '', ...fields] = e.params?.headers ?? []
      const status = Number(/^HTTP\/[\d.]+ (\d{3})/.exec(statusLine)?.[1])
      if (status) served = canBeDocument(status, fields) ? { url: urlOf.get(source)!, status } : undefined
    }
  }
  return served
}

function canBeDocument(status: number, fields: string[]): boolean {
  if (status < 200 || (status >= 300 && status < 400) || status === 204 || status === 205) return false
  const field = (name: string) => fields.find(f => f.toLowerCase().startsWith(name + ':'))?.slice(name.length + 1).trim().toLowerCase() ?? ''
  if (/^attachment\b/.test(field('content-disposition'))) return false
  // With no Content-Type Chromium sniffs the body and renders it as the document
  // (package.elm-lang.org serves its pages so); an explicit type must be HTML.
  const type = field('content-type')
  return type === '' || /^(text\/html|application\/xhtml\+xml)\b/.test(type)
}
