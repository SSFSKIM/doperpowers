// A page's SVG images drawn as PNGs, so Read can show them. Each SVG is drawn
// as an <img> from a data: URI on a blank document in the clipper's headless
// Chromium, launched as the render path launches it (the filtering proxy, its
// flags, a fresh profile), and screenshotted. Drawn as an image, an SVG runs
// no script and loads nothing it names except data: URIs, as on the page that
// showed it, so drawing makes no request at all; the proxy is a second wall.
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { launch } from './cdp.ts'
import { chromeArgs } from './render.ts'
import { startEgressProxy } from './proxy.ts'
import type { Boundary } from './netguard.ts'

/** Each SVG at twice its natural size, its long edge at most `maxEdge`; every SVG of a page within `timeoutMs`. */
export const DRAW_LIMITS = { timeoutMs: 20_000, scale: 2, maxEdge: 2000 }

export type Drawn = { png: string; bytes: number } | { error: string }

const page = (svg: Buffer) => '<!doctype html><html><head><style>html,body{margin:0;background:#fff}img{display:block}</style></head>'
  + `<body><img id="i" src="data:image/svg+xml;base64,${svg.toString('base64')}"></body></html>`
const MEASURE = "(async () => { const i = document.getElementById('i'); await i.decode(); return [i.naturalWidth, i.naturalHeight] })()"

/** Each SVG file drawn to a PNG beside it (its name, `.png`), or why it was not. */
export async function drawSvgs(files: string[], chrome: { path: string; headless: string }, timeoutMs: number, boundary: Boundary): Promise<Map<string, Drawn>> {
  const drawn = new Map<string, Drawn>()
  const rest = (error: string) => {
    for (const f of files) if (!drawn.has(f)) drawn.set(f, { error })
    return drawn
  }
  if (files.length === 0) return drawn
  if (timeoutMs <= 0) return rest('time budget')
  let proxy
  try {
    proxy = await startEgressProxy(boundary)
  } catch (e) {
    return rest(`its egress proxy could not start (${e instanceof Error ? e.message : e})`)
  }
  const profile = await mkdtemp(join(tmpdir(), 'clip-draw-'))
  const browser = launch(chrome.path, chromeArgs(chrome.headless, profile, proxy.port), 64 * 1048576)
  let timedOut = false
  const timer = setTimeout(() => { timedOut = true; browser.kill() }, timeoutMs)
  try {
    const { targetId } = await browser.send('Target.createTarget', { url: 'about:blank' })
    const { sessionId } = await browser.send('Target.attachToTarget', { targetId, flatten: true })
    const send = (method: string, params?: object) => browser.send(method, params, sessionId)
    const { frameTree } = await send('Page.getFrameTree')
    await send('Emulation.setDefaultBackgroundColorOverride', { color: { r: 255, g: 255, b: 255, a: 1 } })
    for (const file of files) {
      const svg = await readFile(file)
      await send('Page.setDocumentContent', { frameId: frameTree.frame.id, html: page(svg) })
      const measured = await send('Runtime.evaluate', { expression: MEASURE, awaitPromise: true, returnByValue: true })
      if (measured.exceptionDetails) { drawn.set(file, { error: 'the SVG could not be decoded' }); continue }
      const [w, h] = viewBoxSize(svg.toString('utf8')) ?? (measured.result.value as [number, number])
      if (!(w > 0 && h > 0)) { drawn.set(file, { error: 'the SVG has no size' }); continue }
      const scale = Math.min(DRAW_LIMITS.scale, DRAW_LIMITS.maxEdge / Math.max(w, h))
      const width = Math.max(1, Math.round(w * scale))
      const height = Math.max(1, Math.round(h * scale))
      // Drawn at the size wanted, not scaled up from a smaller one: an SVG stays sharp.
      await send('Runtime.evaluate', { expression: `document.getElementById('i').style.cssText = 'width:${width}px;height:${height}px'` })
      await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
      const shot = await send('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width, height, scale: 1 } })
      const png = Buffer.from(shot.data, 'base64')
      const pngFile = file.replace(/\.svg$/i, '') + '.png'
      await writeFile(pngFile, png)
      drawn.set(file, { png: pngFile, bytes: png.length })
    }
    return drawn
  } catch (e) {
    return rest(timedOut ? 'time budget' : `Chromium failed (${e instanceof Error ? e.message : e})`)
  } finally {
    clearTimeout(timer)
    browser.kill()
    await proxy.close()
    await rm(profile, { recursive: true, force: true }).catch(() => {})
  }
}

/**
 * The size a page lays out an SVG at when the SVG names no width, or a
 * percentage: its viewBox's. Chromium's natural size for it is a 300-pixel
 * default, too small to read a chart drawn for 800.
 */
export function viewBoxSize(svg: string): [number, number] | undefined {
  const root = /<svg\b[^>]*>/i.exec(svg.slice(0, 1048576))?.[0]
  if (!root) return undefined
  const width = /\swidth\s*=\s*(?:"([^"]*)"|'([^']*)')/i.exec(root)
  if (width && !/%\s*$/.test(width[1] ?? width[2])) return undefined
  const box = /\sviewBox\s*=\s*(?:"([^"]*)"|'([^']*)')/i.exec(root)
  const [, , w, h] = (box ? box[1] ?? box[2] : '').trim().split(/[\s,]+/).map(Number)
  return w > 0 && h > 0 ? [w, h] : undefined
}
