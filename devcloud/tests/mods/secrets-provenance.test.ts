import { describe, expect, mock, test, tier } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'
import { ReadReceipts, textRead, verifyRead } from '../../hooks/mods/secrets-provenance'
import { detect } from '../../hooks/mods/secrets-detect'
import { Handles } from '../../hooks/mods/secrets-handles'
import { chars, githubPat, pem } from './fake'

tier('user')

const HOME = '/home/fixture'
const CACHE = '/cache/fixture'
const ROOT = '/opt/fixture/lib/node_modules'
const PATH = `${ROOT}/example/source.js`
const ROOTS = `${CACHE}/devcloud/guard-provenance/v1/roots.json`
const GENERIC = chars(32, 401)
const SOURCE = `const password = "${GENERIC}";`
const ok = (stdout = '') => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
const digest = async (s: string) => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s))), b => b.toString(16).padStart(2, '0')).join('')
const native = (content = SOURCE, startLine = 1, extra = {}) => ({ type: 'text', file: { filePath: PATH, content, startLine, numLines: content.split('\n').length, totalLines: startLine + content.split('\n').length - 1, ...extra } })
// Explicit native-format fixtures, not the production rendering adapter. The
// engine test kit does not map replacement results; the native probe does.
const numbered = (s: string, start = 1, separator = '\t') => s.split('\n').map((line, i) => `${start + i}${separator}${line.replace(/\r$/, '')}`).join('\n')
const block = (id: string, text: unknown, extra = {}) => ({ type: 'tool_result', tool_use_id: id, content: text, ...extra })
const deferred = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const verified = async (request: Record<string, unknown>, source = SOURCE) => ({
  status: 'verified', schemaVersion: 1, policyVersion: 1, generation: 'fixture-generation', canonicalPath: PATH,
  fileSha256: await digest(source), byteSize: new TextEncoder().encode(source).length,
  sliceSha256: await digest(source), startLine: request.startLine, lineCount: request.lineCount,
  contentBytes: request.contentBytes, newline: request.newline,
})

async function start($: Engine, on: On, source = SOURCE, options: {
  result?: unknown; text?: string; verify?: (request: Record<string, unknown>) => unknown;
  process?: (request: Record<string, unknown>, timeout: number | undefined) => Promise<ReturnType<typeof ok>>;
  rootsRead?: () => Promise<string>; rootsStat?: () => Promise<unknown>;
  probe?: ($: EngineInterface) => Promise<unknown>;
} = {}) {
  const clock = mock.clock(on)
  mock.env(on, { HOME, XDG_CACHE_HOME: CACHE })
  const files = new Map<string, string>()
  let stamp = 1
  on('fs.list', (_, e) => ({ value: [...files].filter(([p]) => p.startsWith(`${e.path}/`) && !p.slice(e.path.length + 1).includes('/')).map(([p, text]) => ({ name: p.slice(e.path.length + 1), kind: 'file' as const, size: text.length, mtimeMs: stamp, isLink: false })) }))
  on('fs.stat', async (_, e) => {
    if (e.path === ROOTS) return { value: options.rootsStat ? await options.rootsStat() as never : { kind: 'file' as const, size: 150, mtimeMs: 1, isLink: false } }
    const text = files.get(e.path)
    return text === undefined ? { deny: 'missing' } : { value: { kind: 'file' as const, size: text.length, mtimeMs: stamp, isLink: false } }
  })
  on('fs.read', async (_, e) => {
    if (e.path === ROOTS) return { value: options.rootsRead ? await options.rootsRead() : JSON.stringify({ schemaVersion: 1, policyVersion: 1, generation: 'fixture-generation', roots: [ROOT] }) }
    return files.has(e.path) ? { value: files.get(e.path)! } : { deny: 'missing' }
  })
  const requests: Record<string, unknown>[] = []
  const timeouts: number[] = []
  on('process.run', async (_, e) => {
    if (e.argv[0] === 'git') return ok('/work/project/.git\n/work/project\n')
    expect(e.argv.slice(0, 2)).toEqual(['python3', '-I'])
    expect(e.argv[2]?.endsWith('/hooks/mods/secrets-provenance.py')).toBe(true)
    expect(e.argv.slice(3)).toEqual(['verify', '--timeout-ms', String(e.init?.timeoutMs)])
    expect(e.init?.stdin).not.toContain(GENERIC)
    const request = JSON.parse(e.init?.stdin ?? '{}')
    requests.push(request)
    timeouts.push(e.init?.timeoutMs ?? 0)
    if (options.process) return options.process(request, e.init?.timeoutMs)
    const answer = options.verify ? await options.verify(request) : await verified(request, source)
    return ok(JSON.stringify(answer))
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  let answer = { result: options.result ?? native(source), text: options.text ?? numbered(source), ref: 71 }
  on('tool.call', async (engine, e) => options.probe && e.tool === 'Bash' ? { result: await options.probe(engine) as never } : answer as never)
  const session = mock.session(on)
  await $.session.start({ cwd: '/work/project', surface: null, isInteractive: false })
  return {
    requests, timeouts, session, clock,
    setAnswer(result: unknown, text: string) { answer = { result, text, ref: 71 } },
    put(path: string, value: string) { files.set(path, value); stamp++ },
    async read(id = 'call', agentId?: string) { return $.tool.call({ tool: 'Read', file_path: PATH, tool_use_id: id, agentId } as never) },
    async append(content: unknown[], envelope = {}) {
      await $.session.append({ message: { type: 'user', role: 'user', content }, door: 'tool-result', origin: { kind: 'tool', tool: 'Read' }, uuid: `row-${session.appended().length}`, ...envelope } as never)
      return session.appended().slice(-1)[0]!.message.content
    },
  }
}

describe('distribution Read provenance through both guard passes', () => {
  test('preserves verified constants, the original ref and only the matching numbered body', async ($, on) => {
    const text = `${numbered(SOURCE)}\n<system-reminder>password="${GENERIC}"</system-reminder>`
    const s = await start($, on, SOURCE, { text, result: native(SOURCE, 1, { truncatedByTokenCap: true, totalLines: 900 }) })
    const ran = await s.read()
    expect(ran.result).toEqual(native(SOURCE, 1, { truncatedByTokenCap: true, totalLines: 900 }))
    expect(ran.ref).toBe(71)
    expect(s.requests).toHaveLength(1)
    const row = await s.append([block('call', text), { type: 'text', text: SOURCE }])
    expect(JSON.stringify(row[0])).toContain(GENERIC)
    expect((row[0] as any).content.split('\n')[1]).toContain('[redacted:assignment#')
    expect(JSON.stringify(row[1])).not.toContain(GENERIC)
    expect(JSON.stringify(await s.append([block('call', text)]))).not.toContain(GENERIC)
  })

  test('strong detections win inside original distribution content and force a new result without ref', async ($, on) => {
    const stored = chars(25, 402), credential = chars(25, 403), provider = githubPat(404), privateKey = pem(405)
    const source = [SOURCE, `stored="${stored}"`, `credential="${credential}"`, provider, privateKey].join('\n')
    const s = await start($, on, source)
    s.put(`${HOME}/.config/claude-secrets/EXAMPLE`, stored)
    s.put(`${HOME}/.config/gh/hosts.yml`, `example.invalid:\n  oauth_token: ${credential}\n`)
    const ran = await s.read()
    expect(ran.ref).toBeUndefined()
    const content = (ran.result as any).file.content
    expect(content).toContain(GENERIC)
    for (const value of [stored, credential, provider, privateKey]) expect(content).not.toContain(value)
    expect(content).toContain('[secret:EXAMPLE]')
    expect(content).toContain('[redacted:pem#')
    const row = await s.append([block('call', numbered(content))])
    expect(JSON.stringify(row)).toContain(GENERIC)
    for (const value of [stored, credential, provider, privateKey]) expect(JSON.stringify(row)).not.toContain(value)
  })

  for (const [label, source, startLine, sep] of [
    ['partial', SOURCE, 31, '\t'], ['CRLF', `// fixture\r\n${SOURCE}\r\n`, 5, '\t'],
    ['tab-aware', `\t${SOURCE}\nnext`, 8, ':'], ['legacy tabs', `\t${SOURCE}\nnext`, 8, '\t'],
  ] as const) test(`${label} binds native line numbers and the positional slice`, async ($, on) => {
    const s = await start($, on, source, { result: native(source, startLine), text: numbered(source, startLine, sep) })
    const ran = await s.read()
    expect((ran.result as any).file.content).toBe(source)
    expect(s.requests[0]?.startLine).toBe(startLine)
    expect(JSON.stringify(await s.append([block('call', [{ type: 'text', text: numbered(source, startLine, sep) }])]))).toContain(GENERIC)
  })

  for (const mismatch of ['id', 'agent', 'door', 'origin', 'tool', 'error', 'rendering', 'duplicate', 'multi-block'] as const) {
    test(`${mismatch} cannot borrow a Read receipt`, async ($, on) => {
      const s = await start($, on)
      await s.read()
      const envelope = mismatch === 'agent' ? { agentId: 'worker' } : mismatch === 'door' ? { door: 'note' } : mismatch === 'origin' ? { origin: { kind: 'engine' } } : mismatch === 'tool' ? { origin: { kind: 'tool', tool: 'Bash' } } : {}
      const body = mismatch === 'multi-block' ? [{ type: 'text', text: numbered(SOURCE) }, { type: 'text', text: 'note' }] : numbered(SOURCE) + (mismatch === 'rendering' ? '\nchanged' : '')
      const b = block(mismatch === 'id' ? 'other' : 'call', body, mismatch === 'error' ? { is_error: true } : {})
      const row = await s.append(mismatch === 'duplicate' ? [b, b] : [b], envelope)
      expect(JSON.stringify(row)).not.toContain(GENERIC)
      if (mismatch !== 'id' && mismatch !== 'agent') expect(JSON.stringify(await s.append([block('call', numbered(SOURCE))]))).not.toContain(GENERIC)
    })
  }

  test('unknown provenance and unsupported rendering retain full detection without denying the Read', async ($, on) => {
    const s = await start($, on, SOURCE, { verify: () => ({ status: 'unknown', reason: 'changed_bytes' }) })
    expect(JSON.stringify((await s.read()).result)).not.toContain(GENERIC)
    expect(JSON.stringify(await s.append([block('call', numbered(SOURCE))]))).not.toContain(GENERIC)
    s.setAnswer(native(), `1→${SOURCE}`)
    expect(JSON.stringify((await s.read('unsupported')).result)).not.toContain(GENERIC)
  })
})

describe('bounded verification and one-use receipt lifecycle', () => {
  for (const stalled of ['roots-read', 'roots-stat', 'process'] as const) test(`${stalled} shares the stage deadline and a late answer cannot issue authority`, async ($, on) => {
    const pending = deferred<any>()
    const s = await start($, on, SOURCE, {
      ...(stalled === 'roots-read' ? { rootsRead: () => pending.promise } : {}),
      ...(stalled === 'roots-stat' ? { rootsStat: () => pending.promise } : {}),
      ...(stalled === 'process' ? { process: () => pending.promise } : {}),
    })
    const call = s.read()
    await s.clock.settle()
    await s.clock.advance(1500)
    const ran = await call
    expect(ran.deny).toBeUndefined()
    expect(JSON.stringify(ran.result)).not.toContain(GENERIC)
    if (stalled === 'process') {
      expect(s.requests).toHaveLength(1)
      expect(s.timeouts[0]! > 0 && s.timeouts[0]! <= 1500).toBe(true)
      pending.resolve(ok(JSON.stringify(await verified(s.requests[0]!))))
    } else if (stalled === 'roots-read') pending.resolve(JSON.stringify({ schemaVersion: 1, policyVersion: 1, generation: 'fixture-generation', roots: [ROOT] }))
    else pending.resolve({ kind: 'file' as const, size: 150, mtimeMs: 1, isLink: false })
    await s.clock.settle()
    expect(s.requests.length).toBe(stalled === 'process' ? 1 : 0)
    expect(JSON.stringify(await s.append([block('call', numbered(SOURCE))]))).not.toContain(GENERIC)
  })

  test('preflight spends the process budget, instead of restarting it at spawn', async ($, on) => {
    const s = await start($, on, SOURCE, { rootsRead: async () => {
      const until = performance.now() + 35
      while (performance.now() < until) { /* deterministic elapsed preflight work */ }
      return JSON.stringify({ schemaVersion: 1, policyVersion: 1, generation: 'fixture-generation', roots: [ROOT] })
    } })
    expect((await s.read()).ref).toBe(71)
    expect(s.timeouts[0]! < 1470 && s.timeouts[0]! > 0).toBe(true)
  })

  test('at most four processes run, saturation falls back and out-of-order main/worker results stay distinct', async ($, on) => {
    const pending: ReturnType<typeof deferred<ReturnType<typeof ok>>>[] = []
    const s = await start($, on, SOURCE, { process: async () => {
      const p = deferred<ReturnType<typeof ok>>()
      pending.push(p)
      return p.promise
    } })
    const calls = [s.read('same'), s.read('same', 'worker-a'), s.read('same', 'worker-b'), s.read('four')]
    await s.clock.settle()
    expect(pending).toHaveLength(4)
    expect(JSON.stringify((await s.read('saturated')).result)).not.toContain(GENERIC)
    expect(pending).toHaveLength(4)
    for (const i of [2, 0, 3, 1]) {
      pending[i]!.resolve(ok(JSON.stringify(await verified(s.requests[i]!))))
      expect((await calls[i]!).ref).toBe(71)
    }
    for (const agentId of ['worker-b', undefined, 'worker-a']) {
      expect(JSON.stringify(await s.append([block('same', numbered(SOURCE))], { agentId }))).toContain(GENERIC)
    }
    expect(JSON.stringify(await s.append([block('saturated', numbered(SOURCE))]))).not.toContain(GENERIC)
  })

  test('a timed-out process keeps its slot until settlement and cannot reappear as a receipt', async ($, on) => {
    const pending: ReturnType<typeof deferred<ReturnType<typeof ok>>>[] = []
    const s = await start($, on, SOURCE, { process: () => {
      const p = deferred<ReturnType<typeof ok>>()
      pending.push(p)
      return p.promise
    } })
    const calls = Array.from({ length: 4 }, (_, i) => s.read(`call-${i}`))
    await s.clock.settle()
    await s.clock.advance(1500)
    for (const call of calls) expect(JSON.stringify((await call).result)).not.toContain(GENERIC)
    expect(JSON.stringify((await s.read('extra')).result)).not.toContain(GENERIC)
    expect(pending).toHaveLength(4)
    for (const p of pending) p.reject(new Error('process killed at timeout'))
    await s.clock.settle()
    const next = s.read('after-kill')
    await s.clock.settle()
    expect(pending).toHaveLength(5)
    pending[4]!.resolve(ok(JSON.stringify(await verified(s.requests[4]!))))
    expect((await next).ref).toBe(71)
  })

  test('abort abandons unsettled provenance and never starts a verifier afterwards', async ($, on) => {
    const pending = deferred<string>()
    const controller = new AbortController()
    const s = await start($, on, SOURCE, {
      rootsRead: () => pending.promise,
      probe: async engine => {
        expect(await verifyRead(engine, PATH, textRead(native())!, numbered(SOURCE), SOURCE, '/work/project', controller.signal)).toBeUndefined()
        return 'unknown'
      },
    })
    const proof = $.tool.call({ tool: 'Bash', command: 'fixture' })
    await s.clock.settle()
    controller.abort()
    expect((await proof).result).toBe('unknown')
    pending.resolve(JSON.stringify({ schemaVersion: 1, policyVersion: 1, generation: 'fixture-generation', roots: [ROOT] }))
    await s.clock.settle()
    expect(s.requests).toHaveLength(0)
  })

  test('new known values between passes override a still-valid receipt', async ($, on) => {
    const s = await start($, on)
    await s.read()
    s.put(`${HOME}/.config/claude-secrets/NEW`, GENERIC)
    // Another call forces the existing known-value refresh (append throttles it).
    await s.read('refresh-only')
    const row = await s.append([block('call', numbered(SOURCE))])
    expect(JSON.stringify(row)).not.toContain(GENERIC)
    expect(JSON.stringify(row)).toContain('[secret:NEW]')
  })

  test('a failed reused call and session start each discard the earlier receipt', async ($, on) => {
    const s = await start($, on)
    await s.read()
    s.setAnswer({ type: 'text', file: { filePath: PATH, content: SOURCE } }, numbered(SOURCE))
    await s.read()
    expect(JSON.stringify(await s.append([block('call', numbered(SOURCE))]))).not.toContain(GENERIC)
    s.setAnswer(native(), numbered(SOURCE))
    await s.read('reset')
    await $.session.start({ cwd: '/work/project', surface: null, isInteractive: false })
    expect(JSON.stringify(await s.append([block('reset', numbered(SOURCE))]))).not.toContain(GENERIC)
  })

  test('capacity eviction removes the oldest call rather than exempting an unbounded history', async ($, on) => {
    const s = await start($, on)
    for (let i = 0; i < 257; i++) await s.read(`call-${i}`)
    expect(JSON.stringify(await s.append([block('call-0', numbered(SOURCE))]))).not.toContain(GENERIC)
    expect(JSON.stringify(await s.append([block('call-1', numbered(SOURCE))]))).toContain(GENERIC)
    expect(JSON.stringify(await s.append([block('call-256', numbered(SOURCE))]))).toContain(GENERIC)
  })

  test('receipt expiry, reload loss and tuple keys never reconstruct authority', () => {
    let now = 100
    const receipts = new ReadReceipts(() => now)
    const evidence = { generation: 'fixture-generation', digest: 'a'.repeat(64), ranges: [{ start: 0, end: 1 }] }
    receipts.issue({ tool_use_id: 'a:b', agentId: 'c' }, evidence)
    receipts.issue({ tool_use_id: 'b', agentId: 'c:a' }, evidence)
    expect(receipts.take({ tool_use_id: 'a:b', agentId: 'c' })).toBeDefined()
    expect(receipts.take({ tool_use_id: 'b', agentId: 'c:a' })).toBeDefined()
    receipts.issue({ tool_use_id: 'expires' }, evidence)
    now += 60_000
    expect(receipts.take({ tool_use_id: 'expires' })).toBeUndefined()
    receipts.issue({ tool_use_id: 'reload' }, evidence)
    expect(new ReadReceipts(() => now).take({ tool_use_id: 'reload' })).toBeUndefined()
  })
})

describe('unknown and unsupported forms remain fully guarded', () => {
  for (const field of ['schemaVersion', 'policyVersion', 'generation', 'canonicalPath', 'fileSha256', 'byteSize', 'sliceSha256', 'startLine', 'lineCount', 'contentBytes', 'newline'] as const) {
    test(`malformed verifier ${field} cannot grant an exception`, async ($, on) => {
      const s = await start($, on, SOURCE, { verify: async request => ({ ...await verified(request), [field]: field === 'sliceSha256' ? '0'.repeat(64) : null }) })
      expect(JSON.stringify((await s.read()).result)).not.toContain(GENERIC)
      expect(JSON.stringify(await s.append([block('call', numbered(SOURCE))]))).not.toContain(GENERIC)
    })
  }
  for (const mode of ['missing-python', 'truncated', 'invalid-json', 'nonzero', 'missing-roots', 'bad-roots', 'oversized-roots'] as const) {
    test(`${mode} is ordinary detection, never a withheld Read`, async ($, on) => {
      const s = await start($, on, SOURCE, {
        ...(mode === 'missing-roots' ? { rootsRead: async () => { throw new Error('missing') } } : {}),
        ...(mode === 'bad-roots' ? { rootsRead: async () => '{' } : {}),
        ...(mode === 'oversized-roots' ? { rootsStat: async () => ({ kind: 'file' as const, size: 40_000, mtimeMs: 1, isLink: false }) } : {}),
        process: async request => {
          if (mode === 'missing-python') throw new Error('ENOENT')
          const answer = ok(mode === 'invalid-json' ? '{' : JSON.stringify(await verified(request)))
          if (mode === 'truncated') answer.value.isStdoutTruncated = true
          if (mode === 'nonzero') answer.value.exitCode = 1
          return answer
        },
      })
      const ran = await s.read()
      expect(ran.deny).toBeUndefined()
      expect(JSON.stringify(ran.result)).not.toContain(GENERIC)
    })
  }
  test('metadata, Bash, changed renderings and non-source formats gain no exception', async ($, on) => {
    const s = await start($, on)
    s.setAnswer({ ...native(), note: SOURCE }, numbered(SOURCE))
    const ran = await s.read()
    expect((ran.result as any).file.content).toBe(SOURCE)
    expect((ran.result as any).note).not.toContain(GENERIC)
    expect(ran.ref).toBeUndefined()
    expect(JSON.stringify((await $.tool.call({ tool: 'Bash', command: 'cat fixture' })).result)).not.toContain(GENERIC)
    for (const text of [`1→${SOURCE}`, `${numbered(SOURCE)}\n${numbered(SOURCE)}`, `1\t${SOURCE.slice(0, -1)}…`]) {
      s.setAnswer(native(), text)
      expect(JSON.stringify((await s.read()).result)).not.toContain(GENERIC)
    }
    for (const result of [{ type: 'notebook', file: { filePath: PATH, content: SOURCE } }, { type: 'text', file: { ...native().file, numLines: 2 } }, { type: 'unchanged', content: SOURCE }]) {
      s.setAnswer(result, numbered(SOURCE))
      expect(JSON.stringify((await s.read()).result)).not.toContain(GENERIC)
    }
  })
  test('only complete generic spans are omitted; strong and known spans cross range boundaries', () => {
    const provider = githubPat(500), key = pem(501)
    const text = `${SOURCE}\n${provider}\n${key}`
    const full = [{ start: 0, end: text.length }]
    expect(detect(text, full).map(s => s.kind)).toEqual(['github-pat', 'pem'])
    const generic = detect(SOURCE)[0]!
    expect(detect(SOURCE, [{ start: generic.start + 1, end: generic.end }]).map(s => s.kind)).toEqual(['assignment'])
    const handles = new Handles('fixture')
    handles.setKnown([{ label: 'KNOWN', value: GENERIC }])
    const scrubbed = handles.scrub(text, full)
    for (const value of [GENERIC, provider, key]) expect(scrubbed).not.toContain(value)
  })
})

test('a singleton text block grants no exemption to its other fields', async ($, on) => {
  const s = await start($, on)
  await s.read()
  const row = await s.append([block('call', [{ type: 'text', text: numbered(SOURCE), note: SOURCE }])])
  expect((row[0] as any).content[0].text).toContain(GENERIC)
  expect((row[0] as any).content[0].note).not.toContain(GENERIC)
})

test('a second simultaneous append cannot use a receipt while the first awaits hashing', async ($, on) => {
  const s = await start($, on)
  await s.read()
  await Promise.all([s.append([block('call', numbered(SOURCE))]), s.append([block('call', numbered(SOURCE))])])
  const rows = s.session.appended().map(row => JSON.stringify(row.message.content))
  expect(rows.filter(row => row.includes(GENERIC))).toHaveLength(1)
  expect(rows.filter(row => row.includes('[redacted:assignment#'))).toHaveLength(1)
})

test('roots are reread only after stat changes, and a new screen never inherits old coverage', async ($, on) => {
  let reads = 0, stamp = 1, root = ROOT
  const s = await start($, on, SOURCE, {
    rootsStat: async () => ({ kind: 'file' as const, size: 150, mtimeMs: stamp, isLink: false }),
    rootsRead: async () => { reads++; return JSON.stringify({ schemaVersion: 1, policyVersion: 1, generation: 'fixture-generation', roots: [root] }) },
  })
  await s.read('one')
  await s.read('two')
  expect(reads).toBe(1)
  stamp++
  root = '/opt/another-installation'
  const ran = await s.read('changed')
  expect(reads).toBe(2)
  expect(s.requests).toHaveLength(2)
  expect(JSON.stringify(ran.result)).not.toContain(GENERIC)
})

test('multibyte source uses UTF-8 digest lengths and character-based rendering ranges', async ($, on) => {
  const source = `// λ and a supplementary character: \u{10400}\n${SOURCE}`
  const s = await start($, on, source)
  const ran = await s.read()
  expect((ran.result as any).file.content).toBe(source)
  expect(s.requests[0]!.contentBytes).toBe(new TextEncoder().encode(source).length)
  expect(JSON.stringify(await s.append([block('call', numbered(source))]))).toContain(GENERIC)
})

test('oversized source and Reads without generic detections never start verification', async ($, on) => {
  const s = await start($, on)
  s.setAnswer(native('ordinary code'), numbered('ordinary code'))
  expect((await s.read()).ref).toBe(71)
  const large = SOURCE + '\n' + 'x'.repeat(16 * 1024 * 1024)
  s.setAnswer(native(large), numbered(large))
  const ran = await s.read('large')
  expect((ran.result as any).file.content).not.toContain(GENERIC)
  expect(s.requests).toHaveLength(0)
})
