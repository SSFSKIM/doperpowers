import { describe, expect, test, tier } from 'claude-code/testing'
import type { ConfigRow, EngineInterface, ToolInfo } from 'claude-code'
import { CONTROL_KEYS, STANDING, controlsOf, notInVersion } from '../../hooks/mods/bridge-controls'
import { configCut, mcpServers, readKind, ruleOf, settingsCut } from '../../hooks/mods/bridge-reads'

tier('user')

// Engine-shaped rows, as 2.1.310's declarations type them (`ConfigRow`, whose
// `provider` is an `Origin`: the engine's rows `{plugin: "engine", tier: "core"}`).
const ENGINE = { plugin: 'engine', tier: 'core' } as const
const ROWS: ConfigRow[] = [
  { key: 'model', label: 'Model', kind: 'choice', value: 'default', options: ['default', 'sonnet', 'opus'], provider: ENGINE, isLocked: false },
  { key: 'autoCompactEnabled', label: 'Auto-compact', description: 'Compact when the window fills', kind: 'boolean', value: true, provider: ENGINE, isLocked: true },
  { key: 'language', label: 'Language', kind: 'text', value: 'English', provider: ENGINE, isLocked: false },
  { key: 'probe.apiToken', label: 'API token', kind: 'text', value: 'sk-secret-123', provider: { plugin: 'probe', tier: 'user' }, isLocked: false },
  { key: 'probe.region', label: 'Region', kind: 'choice', value: 'eu', options: ['eu', 'us'], provider: { plugin: 'probe', tier: 'user' }, isLocked: false },
  { key: 'probe.retries', label: 'Retries', kind: 'number', value: 3, provider: { plugin: 'probe', tier: 'user' }, isLocked: false },
]

describe('read config', () => {
  test("keeps the engine's rows whole and in order, and leaves out a plugin text row's value", () => {
    const cut = configCut(ROWS)
    expect(cut.readOnly).toBe(true)
    expect(cut.rows.map((r) => r.key)).toEqual(ROWS.map((r) => r.key))
    expect(cut.rows[0]).toEqual({ ...ROWS[0] })
    expect(cut.rows[1]).toEqual({ ...ROWS[1] })
    expect(cut.rows[2]).toEqual({ ...ROWS[2] }) // an engine text row keeps its value
    expect(cut.rows[3]).toEqual({ key: 'probe.apiToken', label: 'API token', kind: 'text', provider: { plugin: 'probe', tier: 'user' }, isLocked: false })
    expect(JSON.stringify(cut)).not.toContain('sk-secret-123')
    expect(cut.rows[4]).toEqual({ ...ROWS[4] }) // a plugin's choice and number rows keep theirs
    expect(cut.rows[5]).toEqual({ ...ROWS[5] })
  })
})

describe('read settings', () => {
  test('a rule string parses as the engine parses it', () => {
    expect(ruleOf('Bash')).toEqual({ toolName: 'Bash' })
    expect(ruleOf('Bash(npm test:*)')).toEqual({ toolName: 'Bash', ruleContent: 'npm test:*' })
    expect(ruleOf('Bash()')).toEqual({ toolName: 'Bash' })
    expect(ruleOf('Bash(*)')).toEqual({ toolName: 'Bash' })
    expect(ruleOf('Bash(echo \\(hi\\))')).toEqual({ toolName: 'Bash', ruleContent: 'echo (hi)' })
    expect(ruleOf('Bash(a\\\\b)')).toEqual({ toolName: 'Bash', ruleContent: 'a\\b' })
    expect(ruleOf('mcp__probe__tool')).toEqual({ toolName: 'mcp__probe__tool' })
    expect(ruleOf('Read(./x) trailing')).toEqual({ toolName: 'Read(./x) trailing' }) // malformed: the whole string
  })

  test('answers the rules merged and by source, cliArg for flag, and hooks as event, matcher and count, nothing else', () => {
    const hookCommand = 'curl -H "Authorization: Bearer hook-secret" x'
    const merged = {
      env: { TOKEN: 'env-secret' },
      apiKeyHelper: 'helper-secret',
      permissions: {
        allow: ['Bash(npm test:*)', 'Read', 7],
        ask: ['WebFetch(domain:example.com)'],
        deny: ['Bash(rm -rf:*)'],
        additionalDirectories: ['/extra'],
        defaultMode: 'acceptEdits',
      },
      hooks: {
        PreToolUse: [{ matcher: 'Bash', hooks: [{ type: 'command', command: hookCommand }, { type: 'command', command: 'b' }] }],
        Stop: [{ hooks: [{ type: 'command', command: 'c' }] }],
        Broken: 'not a list',
      },
    }
    const cut = settingsCut(merged, {
      user: { permissions: { allow: ['Read'] }, env: { X: 'env-secret' } },
      local: { permissions: { allow: ['Bash(npm test:*)'], deny: ['Bash(rm -rf:*)'] } },
      cliArg: { permissions: { ask: ['WebFetch(domain:example.com)'] } },
    })
    expect(cut).toEqual({
      permissionsExact: false,
      permissions: {
        allow: [{ toolName: 'Bash', ruleContent: 'npm test:*' }, { toolName: 'Read' }],
        ask: [{ toolName: 'WebFetch', ruleContent: 'domain:example.com' }],
        deny: [{ toolName: 'Bash', ruleContent: 'rm -rf:*' }],
        additionalDirectories: ['/extra'],
        defaultMode: 'acceptEdits',
        bySource: {
          user: { allow: [{ toolName: 'Read' }], ask: [], deny: [] },
          project: { allow: [], ask: [], deny: [] },
          local: { allow: [{ toolName: 'Bash', ruleContent: 'npm test:*' }], ask: [], deny: [{ toolName: 'Bash', ruleContent: 'rm -rf:*' }] },
          policy: { allow: [], ask: [], deny: [] },
          cliArg: { allow: [], ask: [{ toolName: 'WebFetch', ruleContent: 'domain:example.com' }], deny: [] },
        },
      },
      hooks: { PreToolUse: [{ matcher: 'Bash', commands: 2 }], Stop: [{ matcher: null, commands: 1 }] },
    })
    const text = JSON.stringify(cut)
    for (const secret of ['env-secret', 'helper-secret', 'hook-secret', 'Authorization']) {
      expect(text).not.toContain(secret)
    }
  })

  test('settings with no permissions or hooks read empty, the default mode null', () => {
    expect(settingsCut({}, {})).toMatchObject({
      permissions: { allow: [], ask: [], deny: [], additionalDirectories: [], defaultMode: null, bySource: { user: { allow: [] } } },
      hooks: {},
    })
  })

  test('reads the merge and each of the five sources from the engine', async () => {
    const asked: unknown[] = []
    const $ = { settings: { read: async (args?: { source?: string }) => {
      asked.push(args)
      return args?.source === 'flag' ? { permissions: { allow: ['Edit'] } } : {}
    } } } as unknown as EngineInterface
    const answer = await readKind($, 'settings', undefined)
    expect(asked).toEqual([undefined, { source: 'user' }, { source: 'project' }, { source: 'local' }, { source: 'flag' }, { source: 'policy' }])
    expect(answer).toMatchObject({ ok: true, result: { permissions: { bySource: { cliArg: { allow: [{ toolName: 'Edit' }] } } } } })
  })
})

describe('read mcp', () => {
  const tool = (name: string, mcp = true): ToolInfo => ({ name, description: '', mcp })
  test("groups the MCP tools by the server their name gives, in the order listed, the server spelled as its tools spell it", () => {
    const tools = [tool('Bash', false), tool('mcp__probe__one'), tool('mcp__my_server__a__b'), tool('mcp__probe__two'), tool('mcp__probe__'), tool('mcp__x'), tool('mcp__fake__t', false)]
    expect(mcpServers(tools)).toEqual([
      { name: 'probe', status: 'connected', tools: 2 },
      { name: 'my_server', status: 'connected', tools: 1 },
    ])
  })

  test('says it is not exact: lane A sees only connected servers with tools', async () => {
    const $ = { tool: { list: async () => [tool('mcp__probe__one')] } } as unknown as EngineInterface
    expect(await readKind($, 'mcp', undefined)).toEqual({ ok: true, result: { exact: false, servers: [{ name: 'probe', status: 'connected', tools: 1 }] } })
  })
})

describe('read usage', () => {
  const usage = (calls: unknown[]) => ({ session: { usage: async (args: unknown) => {
    calls.push(args)
    return { startedAt: 1, context: { tokens: 10, window: 200000, percent: 0, breakdown: { totalTokens: 10 } }, rateLimits: [{ kind: 'five_hour', percentUsed: 23.5 }], cost: { usd: 0.01 } }
  } } } as unknown as EngineInterface)

  test('reads the summary unless the full count is asked for, and says which it is', async () => {
    const calls: unknown[] = []
    const $ = usage(calls)
    expect(await readKind($, 'usage', undefined)).toEqual({ ok: true, result: {
      startedAt: 1, context: { tokens: 10, window: 200000, percent: 0, breakdown: { totalTokens: 10 } },
      rateLimits: [{ kind: 'five_hour', percentUsed: 23.5 }], cost: { usd: 0.01 }, breakdownDetail: 'summary',
    } })
    expect(await readKind($, 'usage', { breakdown: 'full' })).toMatchObject({ ok: true, result: { breakdownDetail: 'full' } })
    expect(calls).toEqual([{ breakdown: 'summary' }, { breakdown: 'full' }])
  })

  test('refuses any other breakdown, and calls nothing', async () => {
    const calls: unknown[] = []
    expect(await readKind(usage(calls), 'usage', { breakdown: 'exact' })).toEqual({ ok: false, error: "usage's breakdown is summary or full" })
    expect(calls).toEqual([])
  })

  test('a kind it does not serve is left to the caller', () => {
    expect(readKind({} as EngineInterface, 'status', undefined)).toBeUndefined()
  })
})

describe('capabilities.controls', () => {
  test("carries every key of the lane map: the controls before the wave and MW1's reads available, the rest with a reason", () => {
    const map = controlsOf('9.9.9')
    expect(Object.keys(map)).toEqual([...CONTROL_KEYS])
    expect(CONTROL_KEYS).toHaveLength(20)
    const available = CONTROL_KEYS.filter((k) => map[k].available)
    expect(available).toEqual(['read.usage', 'read.config', 'read.settings', 'read.mcp', 'compact', 'model', 'mcp.enable', 'mcp.disable', 'mcp.reconnect', 'decide'])
    for (const key of ['btw', 'decide.scope', 'decide.addDirectory', 'stop-agent', 'tell', 'media'] as const) {
      expect(map[key]).toEqual({ available: false, reason: notInVersion('9.9.9') })
    }
    for (const key of ['decide.interrupt', 'forget', 'rewind-files', 'elicitation.answer'] as const) {
      expect(map[key]).toEqual({ available: false, reason: STANDING[key] })
    }
    expect(notInVersion('9.9.9')).toContain('9.9.9')
  })
})
