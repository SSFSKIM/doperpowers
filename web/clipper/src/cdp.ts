// The DevTools protocol over --remote-debugging-pipe: Chromium reads commands
// on its fd 3 and writes replies and events on its fd 4, each one JSON message
// ended by a NUL byte. No port is opened, so nothing else on the machine (and
// no page) can reach the browser's controls.
import { spawn } from 'node:child_process'
import type { Readable, Writable } from 'node:stream'

/** `failure()` after a message passed `maxMessageBytes`. */
export const OVER_LIMIT = 'message over limit'

export type Browser = {
  /** A command's result; rejects with the protocol's error, or once the browser is gone. */
  send(method: string, params?: object, sessionId?: string): Promise<any>
  /**
   * Every later event of `method`. A reply and the event right after it can
   * arrive in one read and are dispatched together, before an `await` on the
   * reply resumes: listen before sending the command that causes the event.
   */
  on(method: string, listener: (params: any, sessionId?: string) => void): void
  /** Resolves once the browser process has exited. */
  exited: Promise<void>
  /** Why the browser went away, when it did on its own (a message over the limit, a spawn error). */
  failure(): string | undefined
  /** The tail of the browser's stderr. */
  stderr(): string
  /** Kills the browser's whole process group (it was spawned as a group leader). */
  kill(): void
}

export function launch(path: string, args: string[], maxMessageBytes: number): Browser {
  const child = spawn(path, [...args, '--remote-debugging-pipe'], { stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe'], detached: true })
  const toBrowser = child.stdio[3] as Writable
  const fromBrowser = child.stdio[4] as Readable
  const pending = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>()
  const listeners = new Map<string, ((params: any, sessionId?: string) => void)[]>()
  let nextId = 0
  let gone: string | undefined
  let failed: string | undefined
  let stderr = ''

  const end = (why: string) => {
    gone ??= why
    for (const p of pending.values()) p.reject(new Error(gone))
    pending.clear()
  }
  const kill = () => {
    if (child.pid) try { process.kill(-child.pid, 'SIGKILL') } catch {}
  }

  const exited = new Promise<void>(resolve => {
    child.on('exit', code => { end(`Chromium exited ${code}`); resolve() })
    child.on('error', e => { failed ??= e.message; end(e.message); resolve() })
  })
  child.stderr!.on('data', (d: Buffer) => { stderr = (stderr + d.toString()).slice(-400) })
  toBrowser.on('error', () => {})
  fromBrowser.on('error', () => {})

  let parts: Buffer[] = []
  let size = 0
  fromBrowser.on('data', (chunk: Buffer) => {
    if (gone) return
    let start = 0
    // A NUL never occurs inside a message: JSON escapes it, and no UTF-8 sequence holds one.
    for (let nul = chunk.indexOf(0); nul !== -1; nul = chunk.indexOf(0, start)) {
      parts.push(chunk.subarray(start, nul))
      const text = Buffer.concat(parts).toString('utf8')
      parts = []
      size = 0
      start = nul + 1
      dispatch(text)
    }
    if (start < chunk.length) {
      parts.push(chunk.subarray(start))
      size += chunk.length - start
      if (size > maxMessageBytes) {
        failed ??= OVER_LIMIT
        end(failed)
        kill()
      }
    }
  })

  function dispatch(text: string) {
    let m: { id?: number; method?: string; params?: unknown; sessionId?: string; result?: unknown; error?: { message?: string } }
    try { m = JSON.parse(text) } catch { return }
    if (typeof m.id === 'number') {
      const p = pending.get(m.id)
      pending.delete(m.id)
      if (m.error) p?.reject(new Error(m.error.message ?? 'protocol error'))
      else p?.resolve(m.result)
    } else if (m.method) {
      for (const l of listeners.get(m.method) ?? []) l(m.params, m.sessionId)
    }
  }

  return {
    send(method, params = {}, sessionId) {
      if (gone) return Promise.reject(new Error(gone))
      const id = ++nextId
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject })
        toBrowser.write(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }) + '\0')
      })
    },
    on(method, listener) {
      listeners.set(method, [...(listeners.get(method) ?? []), listener])
    },
    exited,
    failure: () => failed,
    stderr: () => stderr,
    kill,
  }
}
