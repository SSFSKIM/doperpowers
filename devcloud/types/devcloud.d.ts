/**
 * devcloud's contract: what other plugins may read of it.
 *
 * `secrets-guard` (Interfaces I9 of the devcloud design): whether devcloud's
 * secrets guard is in this session's chain. devcloud's loaded module answers
 * the read itself, through a `state.get` hook, and never stores the value: the
 * read resolves to the marker at version 0, where the host holds nothing, for
 * as long as the module is loaded, whichever plugin sits outside the other.
 * Once the module is gone (devcloud disabled and the plugins reloaded), the
 * read falls through to the host, which answers `undefined`, or, in a session
 * a devcloud before 0.5.0 started, the marker that one stored, at version 1:
 * a value that outlives its module. A plugin that scrubs secrets of its own
 * (`cua`) reads it at hook time and stands down only on the marker at
 * version 0, so one guard decides every handle and a guard always acts:
 *
 *   const { value, version } = await $.state.get({ plugin: 'devcloud', key: 'secrets-guard' })
 *   if (version === 0 && value?.owner === 'devcloud') return next(e)
 */
export type DevcloudSecretsGuard = { owner: 'devcloud'; version: 1 }

declare module 'claude-code' {
  interface PluginState {
    devcloud: { 'secrets-guard': DevcloudSecretsGuard }
  }
}
