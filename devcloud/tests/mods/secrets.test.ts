import { describe, expect, mock, test, tier } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import { chars, githubPat } from './fake'

tier('user')

const HOME = '/home/t'
const STORE = `${HOME}/.config/claude-secrets`
// The project of a session in /work/repo/sub, a git repository whose main checkout is /work/repo.
const PROJECT_STORE = `${STORE}/projects/-work-repo`
const STORED = `sk-live-${chars(20, 51)}`
const ok = (stdout = '') => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })

/**
 * A file system in memory beneath the plugins: `$.fs` reads, lists, stats
 * and writes it; `put` changes a file as another process would (a later
 * modification time).
 */
const disk = (on: On, initial: Record<string, string>) => {
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

type Disk = ReturnType<typeof disk>
type Run = (argv: readonly string[], fs: Disk, stdin?: string) => ReturnType<typeof ok>

/**
 * A headless session in /work/repo/sub over `initial`, started as a session
 * starts; `run` answers a process other than git.
 */
const start = async ($: Engine, on: On, initial: Record<string, string>, run: Run = () => ok()) => {
  mock.env(on, { HOME })
  const fs = disk(on, initial)
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('process.run', (_, e) => (e.argv[0] === 'git' ? ok('/work/repo/.git\n/work/repo\n') : run(e.argv, fs, e.init?.stdin)))
  await $.session.start({ cwd: '/work/repo/sub', surface: null, isInteractive: false })
  return fs
}

/** The bottom of `tool.call`: records the input each call ran with and answers `answer(e)`. */
const tool = (on: On, answer: (e: Record<string, unknown>) => unknown) => {
  const ran: Record<string, unknown>[] = []
  on('tool.call', (_, e) => {
    ran.push(e as Record<string, unknown>)
    return { result: answer(e as Record<string, unknown>) as never }
  })
  return ran
}

const bash = (stdout: string, extra: Record<string, unknown> = {}) => ({ stdout, stderr: '', interrupted: false, ...extra })

/**
 * A second guard beside devcloud's, as Interfaces I9 asks one to behave
 * (cua's vendored copy): each hook reads devcloud's marker and passes the
 * event on untouched when it reads the marker at version 0, the loaded
 * module's answer; otherwise it acts, and marks what it touched. In the
 * prepend tier it sits outside devcloud, in append inside it. An inline
 * plugin's hooks run in a module of their own, so what they did is read off
 * what they return.
 */
const secondGuard = (tier: 'prepend' | 'append') => ({
  name: 'cua',
  tier,
  register: (on: On) => {
    on('tool.call', async ($, e, next) => {
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
})

// Another plugin reading the marker: a Bash call answers with what it read.
const markerReader = {
  name: 'reader',
  tier: 'prepend' as const,
  register: (on: On) => {
    on('tool.call', async ($, e, next) => {
      await next(e)
      return { result: (await $.state.get({ plugin: 'devcloud', key: 'secrets-guard' })) as never }
    })
  },
}

describe("Interfaces I9: one guard per session, devcloud's while its module is loaded", () => {
  test("another plugin's read of the marker is the loaded module's answer, at version 0, and nothing is stored", { plugins: [markerReader] }, async ($, on) => {
    const set: unknown[] = []
    on('state.set', (_, e) => {
      set.push({ plugin: e.plugin, key: e.key, value: e.value })
      return { value: { isSet: true, version: 1 } }
    })
    tool(on, () => bash(''))
    await start($, on, {})
    expect((await $.tool.call({ tool: 'Bash', command: 'true' })).result).toEqual({ value: { owner: 'devcloud', version: 1 }, version: 0 })
    // Nothing for the host to keep, so nothing outlives the module (board #101).
    expect(set).toEqual([])
  })

  for (const [tier, place] of [['prepend', 'outside'], ['append', 'inside']] as const) {
    test(`a second guard ${place} devcloud passes every event on, and devcloud alone scrubs`, { plugins: [secondGuard(tier)] }, async ($, on) => {
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
    })
  }
})

describe('redact, never refuse', () => {
  test('a command that reads the store runs, and its output reaches the record as the handle', async ($, on) => {
    const ran = tool(on, () => bash(`${STORED}\n`))
    await start($, on, { [`${STORE}/API_KEY`]: `${STORED}\n` })
    const call = await $.tool.call({ tool: 'Bash', command: `cat ${STORE}/API_KEY` })
    expect(call.deny).toBeUndefined()
    expect(ran).toHaveLength(1)
    expect(call.result).toEqual(bash('[secret:API_KEY]\n'))
  })

  test('ls, mv and test -f on the store, and writing a new file in it, all run', async ($, on) => {
    const ran = tool(on, () => bash(''))
    await start($, on, { [`${STORE}/API_KEY`]: STORED })
    for (const command of [`ls ${STORE}`, `mv ${STORE}/API_KEY ${STORE}/OLD_KEY`, `test -f ${STORE}/OLD_KEY`]) {
      expect((await $.tool.call({ tool: 'Bash', command })).deny).toBeUndefined()
    }
    expect((await $.tool.call({ tool: 'Write', file_path: `${STORE}/NEW_KEY`, content: 'new-value-0123' })).deny).toBeUndefined()
    expect(ran).toHaveLength(4)
  })

  test('a token-shaped string in a tool result is redacted to a pattern handle', async ($, on) => {
    tool(on, () => bash(`token: ${githubPat(52)}`))
    await start($, on, {})
    const call = await $.tool.call({ tool: 'Bash', command: 'cat scratch.txt' })
    expect((call.result as { stdout: string }).stdout).toMatch(/^token: \[redacted:github-pat#[a-z2-7]{4}\.\d+\]$/)
  })

  test("a credential file's value is redacted to a handle naming its file and field", async ($, on) => {
    tool(on, () => bash(`oauth_token: ${githubPat(53)}`))
    await start($, on, { [`${HOME}/.config/gh/hosts.yml`]: `github.com:\n    oauth_token: ${githubPat(53)}\n` })
    const call = await $.tool.call({ tool: 'Bash', command: 'cat ~/.config/gh/hosts.yml' })
    expect(call.result).toEqual(bash('oauth_token: [secret:hosts.yml:github.com.oauth_token]'))
  })

  test("a subagent's tool result is scrubbed as the main loop's is", async ($, on) => {
    tool(on, () => bash(STORED))
    await start($, on, { [`${STORE}/API_KEY`]: STORED })
    const call = await $.tool.call({ tool: 'Bash', command: 'env', agentId: 'agent-1' } as never)
    expect(call.result).toEqual(bash('[secret:API_KEY]'))
  })
})

describe('rows the conversation keeps', () => {
  test('every row is scrubbed where a value appears in it whole, a tool result and the row after it alike', async ($, on) => {
    const session = mock.session(on)
    await start($, on, { [`${STORE}/API_KEY`]: STORED })
    await $.session
      .append({
        message: { type: 'user', role: 'user', content: [{ type: 'tool_result', tool_use_id: 't1', content: `Bearer ${STORED}` }] },
        door: 'tool-result',
        origin: { kind: 'tool', tool: 'Bash' },
        uuid: 'row-1',
      } as never)
      .catch(() => undefined)
    await $.session
      .append({
        message: { type: 'user', role: 'user', isMeta: true, content: [{ type: 'text', text: `the key ${STORED} again, half: ${STORED.slice(0, 10)}` }] },
        door: 'delivery',
        origin: { kind: 'engine' },
        uuid: 'row-2',
      } as never)
      .catch(() => undefined)
    const kept = JSON.stringify(session.appended().map((row) => row.message.content))
    expect(kept).not.toContain(STORED)
    expect(kept).toContain('Bearer [secret:API_KEY]')
    expect(kept).toContain(`the key [secret:API_KEY] again, half: ${STORED.slice(0, 10)}`)
  })

  test('the system prompt, the context blocks and an attachment the model reads are scrubbed', async ($, on) => {
    on('prompt.compose', () => ({ sections: [{ id: 'other:notes', text: `use ${STORED}`, scope: 'session' as const }] }))
    on('prompt.context', () => ({ blocks: [{ name: 'claudeMd', text: `KEY=${STORED}` }] }))
    on('prompt.attachment', () => ({ text: `changed: ${STORED}` }))
    await start($, on, { [`${STORE}/API_KEY`]: STORED })
    const composed = await $.prompt.compose({ model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits: [] })
    expect(composed.sections[0]?.text).toBe('use [secret:API_KEY]')
    expect(composed.sections.find((s) => s.id === 'devcloud:secrets')?.text).toContain('[secret:KEY]')
    const context = await $.prompt.context({ blocks: [] })
    expect(context.blocks[0]?.text).toBe('KEY=[secret:API_KEY]')
    const attachment = await $.prompt.attachment({ type: 'edited_text_file', origin: { kind: 'engine' }, text: '' } as never)
    expect(attachment.text).toBe('changed: [secret:API_KEY]')
  })
})

describe('a manual compaction', () => {
  test('its instructions reach the summarizer scrubbed, and its summary is kept scrubbed', async ($, on) => {
    let told: string | undefined
    on('session.compact', (_, e) => {
      told = e.instructions
      return { messages: [{ role: 'user' as const, text: `Summary: the key is ${STORED}.`, toolUses: [], handle: 'h1' }, { role: 'user' as const, text: 'clean', toolUses: [], handle: 'h2' }] }
    })
    await start($, on, { [`${STORE}/API_KEY`]: STORED })
    const conversation = [{ role: 'user' as const, text: 'earlier', toolUses: [], handle: 'h0' }]
    const compacted = await $.session.compact({ trigger: 'manual', instructions: `remember ${STORED}`, messages: conversation } as never)
    expect(told).toBe('remember [secret:API_KEY]')
    expect('messages' in compacted && compacted.messages?.map((m) => [m.text, m.handle])).toEqual([
      ['Summary: the key is [secret:API_KEY].', undefined],
      ['clean', 'h2'],
    ])
  })
})

describe('package code remains readable without trusting its path', () => {
  test('Read and Bash cat preserve references but redact stored, credential-file and prefixed values everywhere', async ($, on) => {
    const stored = 'config.browser?.isolatedToken'
    const credential = 'oauth2_parameters.credentials'
    const pat = githubPat(83)
    const source = [
      'const tokenInput = model_types_1.TokenInput',
      '{cacheReadInputTokens:e.cache_read_input_tokens??0}',
      `stored: ${stored}`,
      `fromFile: ${credential}`,
      `literal: ${pat}`,
    ].join('\n')
    tool(on, (e) => e.tool === 'Bash' ? bash(source) : {
      type: 'text', file: { filePath: e.file_path, content: source, numLines: 5, startLine: 1, totalLines: 5 },
    })
    await start($, on, {
      [`${STORE}/SAMPLE`]: stored,
      [`${HOME}/.config/gh/hosts.yml`]: `github.com:\n    oauth_token: ${credential}\n`,
    })
    // Synthetic package locations and an ordinary user file receive identical protection.
    for (const path of ['/work/repo/node_modules/example/index.js', '/opt/example/claude/cli.js', '/opt/example/google-cloud-sdk/lib/example.py', '/work/repo/src/example.ts']) {
      const read = (await $.tool.call({ tool: 'Read', file_path: path })).result as { file: { content: string } }
      const cat = (await $.tool.call({ tool: 'Bash', command: `cat ${path}` })).result as { stdout: string }
      for (const text of [read.file.content, cat.stdout]) {
        expect(text).toContain('const tokenInput = model_types_1.TokenInput\n{cacheReadInputTokens:e.cache_read_input_tokens??0}')
        expect(text).toContain('stored: [secret:SAMPLE]')
        expect(text).toContain('fromFile: [secret:hosts.yml:github.com.oauth_token]')
        expect(text).toContain('literal: [redacted:github-pat#')
        for (const value of [stored, credential, pat]) expect(text).not.toContain(value)
      }
    }
  })
})

describe('handles restore exact bytes on write', () => {
  test('an Edit whose strings carry a handle runs with the value, and its record is kept with the handle', async ($, on) => {
    const ran = tool(on, (e) => ({ filePath: e.file_path, oldString: e.old_string, newString: e.new_string, originalFile: `A=${STORED}\n`, structuredPatch: [], userModified: false, replaceAll: false }))
    await start($, on, { [`${STORE}/API_KEY`]: STORED })
    const call = await $.tool.call({ tool: 'Edit', file_path: '/work/repo/.env', old_string: 'A=[secret:API_KEY]', new_string: 'B=[secret:API_KEY]', replace_all: false })
    expect(ran[0]).toMatchObject({ old_string: `A=${STORED}`, new_string: `B=${STORED}` })
    expect(JSON.stringify(call.result)).not.toContain(STORED)
    expect(call.result).toMatchObject({ oldString: 'A=[secret:API_KEY]', newString: 'B=[secret:API_KEY]', originalFile: 'A=[secret:API_KEY]\n' })
  })

  test("a Bash command's handle is restored, a stored value's base64 spelling to its base64", async ($, on) => {
    const ran = tool(on, () => bash('ok'))
    await start($, on, { [`${STORE}/API_KEY`]: STORED })
    await $.tool.call({ tool: 'Bash', command: 'curl -H "Authorization: Bearer [secret:API_KEY]" -d [secret:API_KEY~b64] x' })
    expect(ran[0]?.command).toBe(`curl -H "Authorization: Bearer ${STORED}" -d ${btoa(STORED)} x`)
  })

  test("a project key shadows the global one: the global value gets its own handle and restores to the global bytes", async ($, on) => {
    const globalValue = `${STORED}-global`
    const ran = tool(on, (e) => (e.tool === 'Bash' ? bash(`${globalValue} ${STORED}`) : { type: 'create', filePath: e.file_path, content: e.content, structuredPatch: [] }))
    await start($, on, { [`${STORE}/API_KEY`]: globalValue, [`${PROJECT_STORE}/API_KEY`]: STORED })
    const printed = await $.tool.call({ tool: 'Bash', command: 'env' })
    expect(printed.result).toEqual(bash('[secret:API_KEY@global] [secret:API_KEY]'))
    await $.tool.call({ tool: 'Write', file_path: '/work/repo/x', content: '[secret:API_KEY@global]' })
    expect(ran[1]?.content).toBe(globalValue)
  })

  test("a pattern handle this process issued restores to its bytes", async ($, on) => {
    const pat = githubPat(54)
    const ran = tool(on, (e) => (e.tool === 'Bash' ? bash(`T=${pat}`) : { type: 'create', filePath: e.file_path, content: e.content, structuredPatch: [] }))
    await start($, on, {})
    const printed = (await $.tool.call({ tool: 'Bash', command: 'cat f' })).result as { stdout: string }
    const handle = printed.stdout.slice(2)
    await $.tool.call({ tool: 'Write', file_path: '/work/repo/f', content: `T=${handle}\n` })
    expect(ran[1]?.content).toBe(`T=${pat}\n`)
  })

  test('a handle that cannot be restored is written as is, and the result names it', async ($, on) => {
    const ran = tool(on, (e) => ({ type: 'create', filePath: e.file_path, content: e.content, structuredPatch: [] }))
    await start($, on, {})
    const call = await $.tool.call({ tool: 'Write', file_path: '/work/repo/f', content: 'T=[redacted:github-pat#zzzz.1] K=[secret:GONE]' })
    expect(ran[0]?.content).toBe('T=[redacted:github-pat#zzzz.1] K=[secret:GONE]')
    expect(call.context?.join('\n')).toContain('not restored')
    expect(call.context?.join('\n')).toContain('[redacted:github-pat#zzzz.1]')
    expect(call.context?.join('\n')).toContain('[secret:GONE]')
  })

  test("a Read's input is never rewritten", async ($, on) => {
    const ran = tool(on, () => ({ type: 'text', file: { filePath: '/x', content: '', numLines: 0, startLine: 1, totalLines: 0 } }))
    await start($, on, { [`${STORE}/API_KEY`]: STORED })
    await $.tool.call({ tool: 'Grep', pattern: '[secret:API_KEY]' } as never)
    expect(ran[0]?.pattern).toBe('[secret:API_KEY]')
  })
})

describe('a stored value that changes mid-session', () => {
  test('the old value reads superseded and is never restored; the key restores the new value', async ($, on) => {
    let stdout = STORED
    const ran = tool(on, (e) => (e.tool === 'Bash' ? bash(stdout) : { type: 'create', filePath: e.file_path, content: e.content, structuredPatch: [] }))
    const fs = await start($, on, { [`${STORE}/API_KEY`]: STORED })
    expect((await $.tool.call({ tool: 'Bash', command: 'a' })).result).toEqual(bash('[secret:API_KEY]'))
    fs.put(`${STORE}/API_KEY`, `${STORED}-rotated\n`)
    stdout = `${STORED} ${STORED}-rotated`
    expect((await $.tool.call({ tool: 'Bash', command: 'b' })).result).toEqual(bash('[superseded:API_KEY] [secret:API_KEY]'))
    const call = await $.tool.call({ tool: 'Write', file_path: '/work/repo/f', content: '[secret:API_KEY] [superseded:API_KEY]' })
    expect(ran.at(-1)?.content).toBe(`${STORED}-rotated [superseded:API_KEY]`)
    expect(call.context?.join('\n')).toContain('[superseded:API_KEY]')
  })
})

describe('an oversized output', () => {
  test('its persisted file holds handles before the call returns', async ($, on) => {
    const saved = `${HOME}/.claude/projects/-work-repo/s1/tool-results/b1.txt`
    tool(on, () => bash(`preview ${STORED}`, { persistedOutputPath: saved, persistedOutputSize: 90_000 }))
    const fs = await start($, on, { [`${STORE}/API_KEY`]: STORED, [saved]: `head ${STORED}\n${'x'.repeat(1000)}\ntail ${githubPat(55)}\n` })
    const call = await $.tool.call({ tool: 'Bash', command: 'big' })
    expect((call.result as { stdout: string }).stdout).toBe('preview [secret:API_KEY]')
    const file = fs.files.get(saved)!.text
    expect(file).not.toContain(STORED)
    expect(file).not.toContain(githubPat(55))
    expect(file.startsWith('head [secret:API_KEY]\n')).toBe(true)
  })

  test('one larger than a single read is read in pieces and rewritten whole', async ($, on) => {
    const saved = `${HOME}/.claude/projects/-work-repo/s1/tool-results/b2.txt`
    const MIB = 1024 * 1024
    const filler = 'y'.repeat(5 * MIB)
    tool(on, () => bash('preview', { persistedOutputPath: saved, persistedOutputSize: 6 * MIB }))
    // `dd … skip=<n> count=2 | base64` answered from the file in memory, and
    // `cat > <path>.scrub.tmp && mv …` writing it back from the child's input.
    const pieces: Run = (argv, disk, stdin) => {
      if (stdin !== undefined) {
        disk.put(argv[4]!, stdin)
        return ok()
      }
      const from = Number(argv[5]) * MIB
      return ok(btoa(disk.files.get(argv[4]!)!.text.slice(from, from + 2 * MIB)))
    }
    const fs = await start($, on, { [`${STORE}/API_KEY`]: STORED, [saved]: `${STORED}\n${filler}\n${STORED}\n` }, pieces)
    await $.tool.call({ tool: 'Bash', command: 'huge' })
    const file = fs.files.get(saved)!.text
    expect(file).toBe(`[secret:API_KEY]\n${filler}\n[secret:API_KEY]\n`)
  })
})

describe('fix wave 1', () => {
  test('#1 a Bash command gets a value with shell metacharacters as its exact bytes, not as code', async ($, on) => {
    const value = 'x$(printf INJECTED)y'
    const ran = tool(on, () => bash(''))
    await start($, on, { [`${STORE}/SHELL`]: value })
    await $.tool.call({ tool: 'Bash', command: 'printf "%s" "[secret:SHELL]"', description: 'print [secret:SHELL]' })
    // Since fix wave 3: a value that is not inert is never restored into a command.
    expect(ran[0]?.command).toBe('printf "%s" "[secret:SHELL]"')
    expect(ran[0]?.description).toBe('print [secret:SHELL]')
  })

  test('#2 a persisted output that handles grow past 4 MiB is still rewritten', async ($, on) => {
    const saved = `${HOME}/.claude/projects/-work-repo/s1/tool-results/b3.txt`
    const short = 'qz7Kp2'
    const original = `${short}\n`.repeat(300_000) // 2.1 MB, 16-character handles push it past 4 MiB
    const writes: Run = (argv, disk, stdin) => {
      if (stdin !== undefined) disk.put(argv[4]!, stdin)
      return ok()
    }
    tool(on, () => bash('preview', { persistedOutputPath: saved, persistedOutputSize: original.length }))
    const fs = await start($, on, { [`${STORE}/SHORT`]: short, [saved]: original }, writes)
    const call = await $.tool.call({ tool: 'Bash', command: 'many' })
    expect(call.deny).toBeUndefined()
    const file = fs.files.get(saved)!.text
    expect(file).not.toContain(short + '\n')
    expect(file.startsWith('[secret:SHORT]\n[secret:SHORT]\n')).toBe(true)
  })

  test("#3 another project's stored value is redacted under its own handle and restores to that tier's value", async ($, on) => {
    const other = `${STORED}-other`
    const ran = tool(on, (e) => (e.tool === 'Bash' ? bash(`${other}\n`) : { type: 'create', filePath: e.file_path, content: e.content, structuredPatch: [] }))
    await start($, on, { [`${STORE}/projects/-work-other/API_KEY`]: other, [`${STORE}/API_KEY`]: STORED })
    const printed = await $.tool.call({ tool: 'Bash', command: `cat ${STORE}/projects/-work-other/API_KEY` })
    expect(printed.result).toEqual(bash('[secret:API_KEY@-work-other]\n'))
    await $.tool.call({ tool: 'Write', file_path: '/work/repo/x', content: '[secret:API_KEY@-work-other]' })
    expect(ran[1]?.content).toBe(other)
  })
})

describe('fix wave 3', () => {
  test('#1 each handle a command keeps gets one line naming a read that works there', async ($, on) => {
    const ran = tool(on, (e) => (e.tool === 'Bash' ? bash(`${githubPat(90)}`) : { type: 'create', filePath: e.file_path, content: e.content, structuredPatch: [] }))
    await start($, on, {
      [`${STORE}/SHELL`]: 'a b;c',
      [`${PROJECT_STORE}/MINE`]: 'd e;f',
      [`${HOME}/.codex/auth.json`]: JSON.stringify({ tokens: { access_token: `tok;${chars(30, 91)}` } }),
      [`${HOME}/.pgpass`]: `db:5432:*:app:pw;${chars(20, 92)}\n`,
    })
    const pattern = ((await $.tool.call({ tool: 'Bash', command: 'cat f' })).result as { stdout: string }).stdout
    const handles = ['[secret:SHELL]', '[secret:MINE]', '[secret:SHELL~b64]', '[secret:auth.json:tokens.access_token]', '[secret:.pgpass:db:5432:*:app]', pattern]
    const command = `cat <<EOF\n${handles.join(' ')}\nEOF`
    const call = await $.tool.call({ tool: 'Bash', command })
    expect(ran[1]?.command).toBe(command)
    const lines = (call.context?.join('\n') ?? '').split('\n').filter((l) => l.startsWith('secrets:'))
    expect(lines).toHaveLength(handles.length)
    const line = (h: string) => lines.find((l) => l.startsWith(`secrets: ${h} `)) ?? ''
    expect(line('[secret:SHELL]')).toContain('"$(cat ~/.config/claude-secrets/SHELL)"')
    expect(line('[secret:MINE]')).toContain('"$(cat ~/.config/claude-secrets/projects/-work-repo/MINE)"')
    // Re-pinned in fix wave 4: an exact read piped into the encoding, jq -j, a command for .pgpass.
    expect(line('[secret:SHELL~b64]')).toContain(`"$(perl -pe 'chomp if eof' ~/.config/claude-secrets/SHELL | base64 | tr -d '\\n')"`)
    expect(line('[secret:auth.json:tokens.access_token]')).toContain(`"$(jq -j '.tokens.access_token' ~/.codex/auth.json)"`)
    expect(line('[secret:.pgpass:db:5432:*:app]')).toContain(`~/.pgpass db 5432 '*' app 0)"`)
    expect(line(pattern)).toContain('no source on disk')
    expect(line(pattern)).toContain('file tool')
  })
})

describe('fix wave 4', () => {
  test('#7 two credentials under one label each name their own read', async ($, on) => {
    tool(on, () => bash(''))
    await start($, on, { [`${HOME}/.config/hcloud/cli.toml`]: `[[contexts]]\n  name = "one"\n  token = "t;${chars(30, 93)}"\n[[contexts]]\n  name = "one"\n  token = "u;${chars(30, 94)}"\n` })
    const call = await $.tool.call({ tool: 'Bash', command: 'cat <<EOF\n[secret:cli.toml:contexts.one.token] [secret:cli.toml:contexts.one.token#2]\nEOF' })
    const lines = (call.context?.join('\n') ?? '').split('\n')
    expect(lines.find((l) => l.startsWith('secrets: [secret:cli.toml:contexts.one.token] '))).toContain(` contexts 0 token)"`)
    expect(lines.find((l) => l.startsWith('secrets: [secret:cli.toml:contexts.one.token#2] '))).toContain(` contexts 1 token)"`)
  })

  test('#8 the system prompt says only plain values restore in Bash', async ($, on) => {
    on('prompt.compose', () => ({ sections: [] }))
    await start($, on, {})
    const composed = await $.prompt.compose({ model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits: [] })
    const line = composed.sections.find((s) => s.id === 'devcloud:secrets')?.text ?? ''
    expect(line).toContain('In Bash only')
    expect(line).not.toContain('Write, Edit, MultiEdit, NotebookEdit and Bash it is restored')
  })
})
