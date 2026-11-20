// What the secrets guard's kit tests share: the fixtures, a session over a
// file system in memory, the bottom of `tool.call`, and the plugins that read
// devcloud's guard marker. Not a test file: `secrets.test.ts` and
// `secrets-outside.test.ts` import it (the kit takes `tier` once per file).
import { expect, mock } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import { chars } from './fake'

export const HOME = '/home/t'
export const STORE = `${HOME}/.config/claude-secrets`
// The project of a session in /work/repo/sub, a git repository whose main checkout is /work/repo.
export const PROJECT_STORE = `${STORE}/projects/-work-repo`
export const STORED = `sk-live-${chars(20, 51)}`
export const ok = (stdout = '') => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })

/**
 * A file system in memory beneath the plugins: `$.fs` reads, lists, stats
 * and writes it; `put` changes a file as another process would (a later
 * modification time).
 */
export const disk = (on: On, initial: Record<string, string>) => {
  let clock = 1_000
  const files = new Map<string, { text: string; mtimeMs: number }>()
  const put = (path: string, text: string) => files.set(path, { text, mtimeMs: (clock += 1_000) })
  for (const [path, text] of Object.entries(initial)) put(path, text)
  const isDir = (path: string) => [...files.keys()].some((f) => f.startsWith(`${path}/`))
  const missing = (path: string) => ({ deny: `ENOENT: ${path}` })
  on('fs.exists', (_, e) => ({ value: files.has(e.path) || isDir(e.path) }))
  on('fs.read', (_, e) => {
    const file = files.get(e.path)
    if (!file) return missing(e.path)
    return { value: file.text }
  })
  // As the engine: a write past 4 MiB is refused.
  on('fs.write', (_, e) => {
    if (e.text.length > 4 * 1024 * 1024) return { deny: `${e.text.length} bytes is over the 4194304-byte limit` }
    put(e.path, e.text)
    return { value: undefined }
  })
  on('fs.stat', (_, e) => {
    const file = files.get(e.path)
    if (file) return { value: { kind: 'file' as const, size: file.text.length, mtimeMs: file.mtimeMs, isLink: false } }
    if (isDir(e.path)) return { value: { kind: 'dir' as const, size: 0, mtimeMs: 0, isLink: false } }
    return missing(e.path)
  })
  on('fs.list', (_, e) => {
    if (!isDir(e.path)) return missing(e.path)
    const names = new Map<string, 'file' | 'dir'>()
    for (const path of files.keys()) {
      if (!path.startsWith(`${e.path}/`)) continue
      const rest = path.slice(e.path.length + 1)
      const name = rest.split('/')[0]!
      names.set(name, rest.includes('/') ? 'dir' : 'file')
    }
    return {
      value: [...names].map(([name, kind]) => {
        const file = files.get(`${e.path}/${name}`)
        return { name, kind, size: file?.text.length ?? 0, mtimeMs: file?.mtimeMs ?? 0, isLink: false }
      }),
    }
  })
  return { files, put }
}

export type Disk = ReturnType<typeof disk>
export type Run = (argv: readonly string[], fs: Disk, stdin?: string) => ReturnType<typeof ok>

/**
 * A headless session in /work/repo/sub over `initial`, started as a session
 * starts; `run` answers a process other than git.
 */
export const start = async ($: Engine, on: On, initial: Record<string, string>, run: Run = () => ok()) => {
  mock.env(on, { HOME })
  const fs = disk(on, initial)
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('process.run', (_, e) => (e.argv[0] === 'git' ? ok('/work/repo/.git\n/work/repo\n') : run(e.argv, fs, e.init?.stdin)))
  await $.session.start({ cwd: '/work/repo/sub', surface: null, isInteractive: false })
  return fs
}

/** The bottom of `tool.call`: records the input each call ran with and answers `answer(e)`. */
export const tool = (on: On, answer: (e: Record<string, unknown>) => unknown) => {
  const ran: Record<string, unknown>[] = []
  on('tool.call', (_, e) => {
    ran.push(e as Record<string, unknown>)
    return { result: answer(e as Record<string, unknown>) as never }
  })
  return ran
}

export const bash = (stdout: string, extra: Record<string, unknown> = {}) => ({ stdout, stderr: '', interrupted: false, ...extra })

/**
 * A second guard beside devcloud's, as Interfaces I9 asks one to behave
 * (cua's vendored copy): each hook reads devcloud's marker and passes the
 * event on untouched when it reads the marker at version 0, the loaded
 * module's answer; otherwise it acts, and marks what it touched. It loads as
 * cua does, a plugin a person installs, in the `user` tier; which side of
 * devcloud that is depends on the tier the test file gives devcloud. An
 * inline plugin's hooks run in a module of their own, so what they did is
 * read off what they return. A `Chain` tool call answers with the links
 * beneath its `tool.call` hook (`tier:plugin`, nearest first), so a test can
 * say where the guard sits.
 */
export const secondGuard = {
  name: 'cua',
  register: (on: On) => {
    on('tool.call', async ($, e, next) => {
      if ((e.tool as string) === 'Chain') {
        await next(e)
        return { result: next.trace.map((link) => `${link.tier}:${link.plugin}`) as never }
      }
      const { value, version } = await $.state.get({ plugin: 'devcloud', key: 'secrets-guard' })
      const ran = await next(e)
      return version === 0 && value?.owner === 'devcloud' && value.version === 1 ? ran : { result: 'second guard acted' as never }
    })
    on('session.append', async ($, e, next) => {
      const { value, version } = await $.state.get({ plugin: 'devcloud', key: 'secrets-guard' })
      if (version === 0 && value?.owner === 'devcloud' && value.version === 1) return next(e)
      return next({ ...e, message: { ...e.message, content: [{ type: 'text', text: 'second guard acted' }] } } as never)
    })
    on('session.compact', async ($, e, next) => {
      const { value, version } = await $.state.get({ plugin: 'devcloud', key: 'secrets-guard' })
      if (version === 0 && value?.owner === 'devcloud' && value.version === 1) return next(e)
      return next({ ...e, instructions: 'second guard acted' })
    })
    on('prompt.compose', async ($, e, next) => {
      const { value, version } = await $.state.get({ plugin: 'devcloud', key: 'secrets-guard' })
      const composed = await next(e)
      if (version === 0 && value?.owner === 'devcloud' && value.version === 1) return composed
      return { sections: [...composed.sections, { id: 'cua:acted', scope: 'session' as const, text: 'second guard acted' }] }
    })
    on('prompt.context', async ($, e, next) => {
      const { value, version } = await $.state.get({ plugin: 'devcloud', key: 'secrets-guard' })
      const context = await next(e)
      return version === 0 && value?.owner === 'devcloud' && value.version === 1 ? context : { ...context, blocks: [{ name: 'acted', text: 'second guard acted' }] }
    })
    on('prompt.attachment', async ($, e, next) => {
      const { value, version } = await $.state.get({ plugin: 'devcloud', key: 'secrets-guard' })
      const attached = await next(e)
      return version === 0 && value?.owner === 'devcloud' && value.version === 1 ? attached : { text: 'second guard acted' }
    })
  },
}

// Another plugin reading the marker: a Bash call answers with what it read.
export const markerReader = (tier: 'prepend' | 'user' | 'append') => ({
  name: 'reader',
  tier,
  register: (on: On) => {
    on('tool.call', async ($, e, next) => {
      await next(e)
      return { result: (await $.state.get({ plugin: 'devcloud', key: 'secrets-guard' })) as never }
    })
  },
})

/**
 * A session with a stored value, and every event the second guard hooks
 * raised once: each must come back as devcloud's scrub alone left it, the
 * second guard having passed it on untouched.
 */
export const devcloudAloneScrubs = async ($: Engine, on: On) => {
  tool(on, () => bash(STORED))
  const session = mock.session(on)
  let told: string | undefined
  on('session.compact', (_, e) => {
    told = e.instructions
    return { messages: [{ role: 'user' as const, text: `summary ${STORED}`, toolUses: [], handle: 'h1' }] }
  })
  on('prompt.compose', () => ({ sections: [{ id: 'other:notes', text: `use ${STORED}`, scope: 'session' as const }] }))
  on('prompt.context', () => ({ blocks: [{ name: 'claudeMd', text: `KEY=${STORED}` }] }))
  on('prompt.attachment', () => ({ text: `changed: ${STORED}` }))
  await start($, on, { [`${STORE}/API_KEY`]: STORED })
  expect((await $.tool.call({ tool: 'Bash', command: 'env' })).result).toEqual(bash('[secret:API_KEY]'))
  await $.session
    .append({
      message: { type: 'user', role: 'user', content: [{ type: 'text', text: `the key ${STORED}` }] },
      door: 'prompt',
      origin: { kind: 'engine' },
      uuid: 'row-1',
    } as never)
    .catch(() => undefined)
  expect(session.appended().map((row) => row.message.content)).toEqual([[{ type: 'text', text: 'the key [secret:API_KEY]' }]])
  const conversation = [{ role: 'user' as const, text: 'earlier', toolUses: [], handle: 'h0' }]
  const compacted = await $.session.compact({ trigger: 'manual', instructions: `keep ${STORED}`, messages: conversation } as never)
  expect(told).toBe('keep [secret:API_KEY]')
  expect('messages' in compacted && compacted.messages?.map((m) => m.text)).toEqual(['summary [secret:API_KEY]'])
  const composed = await $.prompt.compose({ model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits: [] })
  expect(composed.sections.map((s) => s.id)).toEqual(['other:notes', 'devcloud:secrets'])
  expect(composed.sections[0]?.text).toBe('use [secret:API_KEY]')
  expect((await $.prompt.context({ blocks: [] })).blocks).toEqual([{ name: 'claudeMd', text: 'KEY=[secret:API_KEY]' }])
  expect((await $.prompt.attachment({ type: 'edited_text_file', origin: { kind: 'engine' }, text: '' } as never)).text).toBe('changed: [secret:API_KEY]')
}

/** The links beneath the second guard's `tool.call` hook, `tier:plugin`, nearest first. */
export const beneathSecondGuard = async ($: Engine) => (await $.tool.call({ tool: 'Chain' } as never)).result as unknown as string[]
