import { describe, expect, test } from 'claude-code/testing'

import { readNotice } from '../../hooks/mods/secrets-reads'

describe('fix wave 4: a read that works in place of a handle', () => {
  test('a store key reads with cat; one ending in a newline is piped, as "$(…)" would drop it', () => {
    const store = { kind: 'store', path: '.config/claude-secrets/K' } as const
    expect(readNotice(store, '', false)).toBe('use "$(cat ~/.config/claude-secrets/K)" in the command')
    expect(readNotice(store, '', true)).toContain("perl -pe 'chomp if eof' ~/.config/claude-secrets/K | <command>")
    expect(readNotice(store, '', true)).toContain("<(perl -pe 'chomp if eof' ~/.config/claude-secrets/K)")
  })

  test('an encoded spelling pipes the exact read straight into its encoding', () => {
    expect(readNotice({ kind: 'store', path: '.config/claude-secrets/K' }, 'b64', false)).toBe(
      `use "$(perl -pe 'chomp if eof' ~/.config/claude-secrets/K | base64 | tr -d '\\n')" in the command`,
    )
  })

  test('a JSON field reads with jq -j, which adds no newline; a PEM key that ends in one is piped', () => {
    const json = { kind: 'json', path: '.config/gcloud/key.json', keys: ['private_key'] } as const
    expect(readNotice(json, '', false)).toBe(`use "$(jq -j '.private_key' ~/.config/gcloud/key.json)" in the command`)
    expect(readNotice(json, '', true)).toContain(`jq -j '.private_key' ~/.config/gcloud/key.json | <command>`)
  })

  test('a non-JSON credential file gets a command that undoes its own escaping', () => {
    expect(readNotice({ kind: 'pgpass', path: '.pgpass', match: ['h', '5432', '*', 'u'], nth: 0 }, '', false)).toMatch(/^use "\$\(python3 -c '.*' ~\/\.pgpass h 5432 '\*' u 0\)" in the command \(it undoes \.pgpass's backslash escapes\)$/)
    expect(readNotice({ kind: 'git-credentials', path: '.git-credentials', id: 'me@h/p', nth: 0 }, '', false)).toContain('URL-decodes')
    expect(readNotice({ kind: 'netrc', path: '.netrc', machine: 'm', nth: 0 }, '', false)).toContain('netrc quoting')
    expect(readNotice({ kind: 'toml', path: '.config/hcloud/cli.toml', table: 'contexts', index: 1, key: 'token' }, '', false)).toContain('tomllib')
    expect(readNotice({ kind: 'gh', host: 'github.com', user: 'me' }, '', false)).toBe('use "$(gh auth token --hostname github.com --user me)" in the command')
  })
})
