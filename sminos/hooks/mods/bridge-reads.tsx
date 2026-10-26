import type { ConfigRow, EngineInterface, ToolInfo } from 'claude-code'

/**
 * The desk's reads of the session's own state (DX5 `read`, the desk control
 * surface spec's §5 and Interfaces; MW1): `usage`, `config`, `settings` and
 * `mcp`, each answered from `$` and cut to what the desk shows (§11). A read
 * leaves the machine uncoded, like a row, so nothing that could hold a
 * credential crosses: no `env`, no hook's command, no MCP server's
 * configuration, no plugin's free-text config value. The shapes are the lane
 * map's, path-neutral: what lane A cannot know exactly says so
 * (`permissionsExact`, `exact`) rather than leaving the field out.
 */

/** A read's answer, as an op's (`bridge-state.tsx` `Answer`). */
type ReadAnswer = { ok: true; result: Record<string, unknown> } | { ok: false; error: string }

/** The kinds this module serves. */
export const READ_KINDS = ['usage', 'config', 'settings', 'mcp'] as const

/** A permission rule as the engine's `PermissionRuleValue` holds it. */
export type Rule = { toolName: string; ruleContent?: string }
type RuleLists = { allow: Rule[]; ask: Rule[]; deny: Rule[] }
/** `read settings`'s source names: the engine's, with `flag` (`--settings`, the SDK's inline settings) spelled `cliArg`. */
export type SourceName = 'user' | 'project' | 'local' | 'policy' | 'cliArg'
export type SettingsRead = {
  permissionsExact: false
  permissions: RuleLists & { additionalDirectories: string[]; defaultMode: string | null; bySource: Record<SourceName, RuleLists> }
  hooks: Record<string, { matcher: string | null; commands: number }[]>
}
export type McpServer = { name: string; status: 'connected'; tools: number }

/** The engine's settings sources, each with the name the read gives it, lowest precedence first. */
export const SOURCES: readonly (readonly ['user' | 'project' | 'local' | 'flag' | 'policy', SourceName])[] = [
  ['user', 'user'], ['project', 'project'], ['local', 'local'], ['flag', 'cliArg'], ['policy', 'policy'],
]

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((s): s is string => typeof s === 'string') : [])

/** The index of the first (or last) `ch` no backslash escapes, or -1. */
function unescaped(text: string, ch: '(' | ')', last: boolean): number {
  const isFree = (i: number) => {
    let slashes = 0
    for (let j = i - 1; j >= 0 && text[j] === '\\'; j--) slashes++
    return slashes % 2 === 0
  }
  if (last) {
    for (let i = text.length - 1; i >= 0; i--) if (text[i] === ch && isFree(i)) return i
  } else {
    for (let i = 0; i < text.length; i++) if (text[i] === ch && isFree(i)) return i
  }
  return -1
}

/**
 * A settings file's rule string (`Bash(npm test:*)`) as the engine parses it
 * (2.1.310's rule parser): `Tool(content)`, the content's `\(`, `\)` and `\\`
 * unescaped; an empty or `*` content is the bare tool; a string that is not
 * that form is a tool name whole, as the engine reads it.
 */
export function ruleOf(text: string): Rule {
  if (!text.includes('(') && !text.includes(')')) return { toolName: text }
  const open = unescaped(text, '(', false)
  const close = unescaped(text, ')', true)
  const tool = open === -1 ? '' : text.slice(0, open)
  if (open === -1 || close <= open || close !== text.length - 1 || /[()]/.test(tool) || tool === '') return { toolName: text }
  const content = text.slice(open + 1, close)
  if (content === '' || content === '*') return { toolName: tool }
  return { toolName: tool, ruleContent: content.replaceAll('\\(', '(').replaceAll('\\)', ')').replaceAll('\\\\', '\\') }
}

const rulesOf = (permissions: Record<string, unknown>): RuleLists => ({
  allow: strings(permissions.allow).map(ruleOf),
  ask: strings(permissions.ask).map(ruleOf),
  deny: strings(permissions.deny).map(ruleOf),
})

/**
 * `read settings`: the permission rules (merged, and by source) and each
 * hook's event, matcher and how many commands it runs, from the settings
 * files as the engine merged them. Nothing else of the settings crosses: not
 * `env`, not a hook's command (the desk says *terminal: /hooks*), no other key.
 * A projection of the files, not the live session's rules (a `session`
 * allow, a `--allowedTools`), hence `permissionsExact: false`; plugins' hooks
 * are not in the settings and are not counted.
 */
export function settingsCut(merged: Record<string, unknown>, bySource: Partial<Record<SourceName, Record<string, unknown>>>): SettingsRead {
  const permissions = isRecord(merged.permissions) ? merged.permissions : {}
  const sources = {} as Record<SourceName, RuleLists>
  for (const [, name] of SOURCES) {
    const of = bySource[name]
    sources[name] = rulesOf(isRecord(of) && isRecord(of.permissions) ? of.permissions : {})
  }
  const hooks: SettingsRead['hooks'] = {}
  if (isRecord(merged.hooks)) {
    for (const [event, matchers] of Object.entries(merged.hooks)) {
      if (!Array.isArray(matchers)) continue
      hooks[event] = matchers.filter(isRecord).map((m) => ({
        matcher: typeof m.matcher === 'string' ? m.matcher : null,
        commands: Array.isArray(m.hooks) ? m.hooks.length : 0,
      }))
    }
  }
  return {
    permissionsExact: false,
    permissions: {
      ...rulesOf(permissions),
      additionalDirectories: strings(permissions.additionalDirectories),
      defaultMode: typeof permissions.defaultMode === 'string' ? permissions.defaultMode : null,
      bySource: sources,
    },
    hooks,
  }
}

/**
 * `read config`: `$.config.list()`'s rows in its order, each as the engine
 * gives it but a plugin's `text` row, whose `value` is left out (a plugin's
 * `userConfig` field may hold a credential). `isLocked` is the engine's
 * policy lock; `readOnly` is the desk's own: it writes no config (F1).
 */
export function configCut(rows: readonly ConfigRow[]): { rows: Record<string, unknown>[]; readOnly: true } {
  return {
    rows: rows.map((row) => {
      const { key, label, description, kind, value, options, provider, isLocked } = row
      const isPluginText = provider.plugin !== 'engine' && kind === 'text'
      return {
        key, label, ...(description !== undefined && { description }), kind,
        ...(!isPluginText && { value: Array.isArray(value) ? [...value] : value }),
        ...(options !== undefined && { options: [...options] }),
        provider: { ...provider },
        isLocked,
      }
    }),
    readOnly: true,
  }
}

/**
 * `read mcp`'s servers as lane A sees them: the MCP tools the model can call
 * now (`$.tool.list()`), grouped by the server their name gives
 * (`mcp__<server>__<tool>`, split as the engine splits it), each `connected`
 * with its tool count, in the order first listed. The server is named as its
 * tools spell it (`my server` is `my_server`). A server with no tool
 * connected, failed, pending or awaiting sign-in is not seen: `exact: false`;
 * the plane adds the ones the project disables.
 */
export function mcpServers(tools: readonly ToolInfo[]): McpServer[] {
  const servers = new Map<string, McpServer>()
  for (const tool of tools) {
    if (!tool.mcp || !tool.name.startsWith('mcp__')) continue
    const parts = tool.name.split('__')
    const name = parts[1]
    if (parts.length < 3 || name === undefined || name === '' || parts.slice(2).join('__') === '') continue
    const server = servers.get(name) ?? { name, status: 'connected' as const, tools: 0 }
    server.tools++
    servers.set(name, server)
  }
  return [...servers.values()]
}

/** `read usage`: `$.session.usage` with the breakdown asked for, the summary unless `full` (which calls the token-count API). */
async function usage($: EngineInterface, args: Record<string, unknown>): Promise<ReadAnswer> {
  const breakdown = args.breakdown ?? 'summary'
  if (breakdown !== 'summary' && breakdown !== 'full') {
    return { ok: false, error: "usage's breakdown is summary or full" }
  }
  const read = await $.session.usage({ breakdown })
  return { ok: true, result: { ...read, breakdownDetail: breakdown } }
}

async function settings($: EngineInterface): Promise<ReadAnswer> {
  const [merged, ...sources] = await Promise.all([$.settings.read(), ...SOURCES.map(([source]) => $.settings.read({ source }))])
  const bySource: Partial<Record<SourceName, Record<string, unknown>>> = {}
  SOURCES.forEach(([, name], i) => (bySource[name] = sources[i] as Record<string, unknown>))
  return { ok: true, result: settingsCut(merged as Record<string, unknown>, bySource) }
}

/** The answer to one of this module's kinds; undefined for a kind it does not serve. */
export function readKind($: EngineInterface, what: unknown, args: unknown): Promise<ReadAnswer> | undefined {
  const asked = isRecord(args) ? args : {}
  switch (what) {
    case 'usage':
      return usage($, asked)
    case 'config':
      return $.config.list().then((rows) => ({ ok: true, result: configCut(rows) }))
    case 'settings':
      return settings($)
    case 'mcp':
      return $.tool.list().then((tools) => ({ ok: true, result: { exact: false, servers: mcpServers(tools) } }))
    default:
      return undefined
  }
}
