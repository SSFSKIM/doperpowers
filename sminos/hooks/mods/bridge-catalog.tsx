import type { EngineInterface } from 'claude-code'
import { catalogRoutes, measuredFor } from './bridge-commands'
import type { Route } from './bridge-routes'

export type Catalog = {
  fingerprint: string
  commands: { name: string; description: string; source: string; plugin?: string; route: Route; withArgs?: Route }[]
  models: { options: string[]; aliases: Record<string, string | null> }
  measured: string
}

/** A session's live listing, not a global cache: late skills and prompt-only MCP servers appear here too. */
export async function catalogNow($: EngineInterface, engine: string): Promise<Catalog> {
  const [listed, config, sonnet, opus, haiku] = await Promise.all([
    $.command.list(), $.config.list(),
    $.env.get('ANTHROPIC_DEFAULT_SONNET_MODEL'),
    $.env.get('ANTHROPIC_DEFAULT_OPUS_MODEL'),
    $.env.get('ANTHROPIC_DEFAULT_HAIKU_MODEL'),
  ])
  const body = {
    commands: listed.map(({ name, description, source, plugin }) => ({
      name, description, source, ...(plugin !== undefined && { plugin }),
      ...catalogRoutes(engine, { name, source, plugin }, $.plugin.name),
    })),
    models: { options: [...(config.find((r) => r.key === 'model')?.options ?? [])], aliases: { sonnet: sonnet ?? null, opus: opus ?? null, haiku: haiku ?? null } },
    measured: measuredFor(engine),
  }
  // A cache identity, never an authentication digest (the daemon rechecks every op).
  let hash = 0xcbf29ce484222325n
  for (const byte of new TextEncoder().encode(JSON.stringify(body))) {
    hash = BigInt.asUintN(64, (hash ^ BigInt(byte)) * 0x100000001b3n)
  }
  const fingerprint = hash.toString(16).padStart(16, '0')
  return { fingerprint, ...body }
}
