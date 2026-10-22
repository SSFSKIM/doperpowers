import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface } from 'claude-code'
import { catalogNow } from '../../hooks/mods/bridge-catalog'

tier('user')

describe('catalog skill membership from the engine', () => {
  test('joins summary skill names, not command origins, and fingerprints membership changes', async () => {
    // 2.1.308 live probe: user and plugin skills share command sources with ordinary commands;
    // the summary names plugin skills fully qualified. A markdown command is also a skill to the engine.
    const commands = [
      { name: 'user-skill', description: 'User fixture.', source: 'user' },
      { name: 'custom', description: 'Custom fixture.', source: 'user' },
      { name: 'catalog-probe:plugin-skill', description: 'Plugin fixture.', source: 'plugin', plugin: 'catalog-probe' },
      { name: 'ordinary-command', description: 'Not a skill', source: 'plugin', plugin: 'catalog-probe' },
    ]
    const names = ['user-skill', 'custom', 'catalog-probe:plugin-skill']
    const usageCalls: unknown[] = []
    const $ = {
      plugin: { name: 'sminos' },
      command: { list: async () => commands },
      config: { list: async () => [] },
      env: { get: async () => undefined },
      session: { usage: async (args: unknown) => {
        usageCalls.push(args)
        return { context: { breakdown: { skills: { totalSkills: names.length, includedSkills: names.length, tokens: 32,
          skillFrontmatter: names.map((name) => ({ name, source: name.includes(':') ? 'plugin' : 'userSettings', tokens: 10 })),
        } } } }
      } },
    } as unknown as EngineInterface
    const first = await catalogNow($, '2.1.308')
    expect(first).toMatchObject({ skills: ['user-skill', 'custom', 'catalog-probe:plugin-skill'] })
    expect(first.commands.map(({ name, source }) => ({ name, source }))).toEqual(commands.map(({ name, source }) => ({ name, source })))
    expect(usageCalls).toEqual([{ breakdown: 'summary' }]) // never full: no token-count API calls
    expect((await catalogNow($, '2.1.308')).fingerprint).toBe(first.fingerprint)
    names.pop() // skills can reload while the command list and models are unchanged
    expect((await catalogNow($, '2.1.308')).fingerprint === first.fingerprint).toBe(false)
  })

  test('a session with no listed skills advertises an empty list', async () => {
    const $ = { plugin: { name: 'sminos' }, command: { list: async () => [] }, config: { list: async () => [] },
      env: { get: async () => undefined }, session: { usage: async () => ({ context: { breakdown: {} } }) },
    } as unknown as EngineInterface
    expect(await catalogNow($, '2.1.308')).toMatchObject({ skills: [] })
  })
})

for (const [label, usage] of [
  ['rejected', async () => { throw new Error('host not bound') }],
  ['missing result', async () => undefined],
  ['missing context', async () => ({})],
  ['missing breakdown', async () => ({ context: {} })],
  ['missing listing', async () => ({ context: { breakdown: {} } })],
  ['malformed listing', async () => ({ context: { breakdown: { skills: { skillFrontmatter: {} } } } })],
] as const) {
  test(`an optional ${label} summary cannot suppress commands, models or aliases`, async () => {
    const $ = { plugin: { name: 'sminos' },
      command: { list: async () => [{ name: 'helper', description: 'User command', source: 'user' }] },
      config: { list: async () => [{ key: 'model', options: ['default', 'sonnet'] }] },
      env: { get: async (key: string) => key === 'ANTHROPIC_DEFAULT_SONNET_MODEL' ? 'my-sonnet' : undefined },
      session: { usage },
    } as unknown as EngineInterface
    expect(await catalogNow($, '2.1.308')).toMatchObject({ skills: [],
      commands: [{ name: 'helper', description: 'User command', source: 'user', route: { class: 'run-prompt', enabled: true } }],
      models: { options: ['default', 'sonnet'], aliases: { sonnet: 'my-sonnet', opus: null, haiku: null } },
    })
  })
}
