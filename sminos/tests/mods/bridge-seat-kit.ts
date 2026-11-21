// What the bridge's seat tests share (bridge-seat-*.test.ts, one per tier the
// kit loads sminos in): the real module, started as a session starts, with a
// stand-in for devcloud's guard as a person installs it. Not a test file:
// the kit takes `tier` once per file.
import { mock } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

const SID = '5b000001-0000-4000-8000-00000000005b'

/**
 * devcloud as a person installs it, in `user`: its loaded module answers a
 * read of its marker itself, as devcloud's does, and its unmatched
 * `tool.call` hook makes it a link of every call's chain. Each read its hook
 * hears it says in the debug log, with the plugin that raised it, so a test
 * can tell a read the engine kept from it from one it never heard.
 */
export const personsDevcloud = {
  name: 'devcloud',
  register: (on: On) => {
    on('state.get', { plugin: 'devcloud', key: 'secrets-guard' }, ($, _e, next) => {
      $.ui.log(`devcloud heard a read of its marker from ${next.origin.plugin}`, { to: 'debug' })
      return { value: { value: { owner: 'devcloud', version: 1 }, version: 0 } }
    })
    on('tool.call', (_$, e, next) => next(e))
  },
}

/**
 * A session started under the kit with sminos's real module: the bridge's
 * child says hello and every post is taken. `policy` is what the managed
 * settings hold and `user` what the user settings do, as `$.settings.read`
 * answers them. What the bridge toasts and logs is kept in `said`, in order,
 * and the body of every post in `posted`.
 */
export const startBridge = async ($: Engine, on: On, settings: { policy: Record<string, unknown>; user: Record<string, unknown> }) => {
  const said: string[] = []
  const posted: string[] = []
  mock.env(on, {})
  mock.clock(on)
  on('ui.toast', (_, e) => {
    said.push(e.text)
    return { value: undefined }
  })
  on('ui.log', (_, e) => {
    said.push(e.text)
    return { value: undefined }
  })
  on('settings.read', (_, e) => ({ value: e.source === 'policy' ? settings.policy : e.source === 'user' ? settings.user : {} }) as never)
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.version', () => ({ value: { version: '2.1.330' } }) as never)
  on('session.model', () => ({ value: 'm' }) as never)
  on('session.id', () => ({ value: SID }))
  on('session.messages', () => ({ value: [] }) as never)
  on('agent.list', () => ({ value: [] }) as never)
  on('command.list', () => ({ value: [] }) as never)
  on('config.list', () => ({ value: [] }) as never)
  on('fs.read', () => ({ value: '{}' }) as never)
  // The child: its hello, then it runs for the rest of the test.
  on('process.spawn', async function* () {
    yield { stream: 'stdout', text: `${JSON.stringify({ op: 'hello', session: SID, pid: 7, socket: '/tmp/s.sock', protocol: 1, nonce: 'n0' })}\n` }
    await new Promise<never>(() => undefined)
  } as never)
  on('http.fetch', (_, e) => {
    posted.push(String(e.init?.body ?? ''))
    return { value: { status: 200, ok: true, text: '{}', headers: {} } } as never
  })
  // The bottom of every tool call.
  on('tool.call', () => ({ result: 'ran' as never }))
  await $.session.start({ cwd: '/w', surface: null, isInteractive: false })
  return { said, posted }
}

export const COMMAND = 'cat notes.txt'

/** One Bash call through the plugins: the dispatch whose settling the bridge judges its place by. */
export const call = ($: Engine) => $.tool.call({ tool: 'Bash', command: COMMAND } as never)

/** Whether the bridge posted the call's result: it judged its place safe. */
export const isResultPosted = (posted: readonly string[]) => posted.some((body) => body.includes('"phase":"result"') && body.includes('"text":"ran"'))
