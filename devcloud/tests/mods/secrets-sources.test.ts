import { describe, expect, test } from 'claude-code/testing'

import { CREDENTIAL_FILES, credentialFields, credentialLabels, projectSlug, rootFromGit, storeValue } from '../../hooks/mods/secrets-sources'
import { chars, githubPat, pem } from './fake'

const v = (seed: number) => chars(28, seed)

describe('credential files', () => {
  test("gh's hosts.yml: each token, by its path", () => {
    const text = `github.com:\n    git_protocol: https\n    users:\n        someone:\n            oauth_token: ${githubPat(1)}\n    oauth_token: "${githubPat(2)}"\n    user: someone\n`
    expect(credentialFields('yaml', text)).toEqual([
      { field: 'github.com.users.someone.oauth_token', value: githubPat(1) },
      { field: 'github.com.oauth_token', value: githubPat(2) },
    ])
  })

  test("a JSON credential file's secret-named strings, by their path", () => {
    const text = JSON.stringify({
      auth_mode: 'chatgpt',
      tokens: { id_token: v(1), access_token: v(2), refresh_token: v(3), account_id: 'acct' },
      last_refresh: '2026-10-01',
      mcpOAuth: { 'plugin:x|1': { serverUrl: 'https://example.com/mcp', accessToken: v(4) } },
    })
    expect(credentialFields('json', text)).toEqual([
      { field: 'tokens.id_token', value: v(1) },
      { field: 'tokens.access_token', value: v(2) },
      { field: 'tokens.refresh_token', value: v(3) },
      { field: 'mcpOAuth.plugin:x|1.accessToken', value: v(4) },
    ])
  })

  test("docker's auths and a gcloud key file", () => {
    expect(credentialFields('json', JSON.stringify({ auths: { 'registry.example': { auth: v(5) } }, credsStore: 'desktop' }))).toEqual([
      { field: 'auths.registry.example.auth', value: v(5) },
    ])
    const key = { type: 'service_account', private_key_id: chars(40, 6), private_key: pem(7), client_email: 'a@b', token_uri: 'https://oauth2.example/token' }
    expect(credentialFields('gcloud', JSON.stringify(key))).toEqual([{ field: 'private_key', value: pem(7) }])
    const user = { type: 'authorized_user', client_id: 'c', client_secret: v(8), refresh_token: v(9) }
    expect(credentialFields('gcloud', JSON.stringify(user))).toEqual([
      { field: 'client_secret', value: v(8) },
      { field: 'refresh_token', value: v(9) },
    ])
    expect(credentialFields('gcloud', JSON.stringify({ core: { project: 'p' }, token: v(10) }))).toEqual([])
  })

  test("hcloud's cli.toml: each context's token, by its name", () => {
    const text = `active_context = "one"\n\n[[contexts]]\n  name = "one"\n  token = "${v(11)}"\n\n[[contexts]]\n  token = "${v(12)}"\n  name = "two"\n`
    expect(credentialFields('toml', text)).toEqual([
      { field: 'contexts.one.token', value: v(11) },
      { field: 'contexts.two.token', value: v(12) },
    ])
  })

  test('.pgpass, .netrc, .git-credentials and .npmrc', () => {
    expect(credentialFields('pgpass', `# comment\ndb.example:5432:*:app:${v(13)}\nlocalhost:5432:main:me:pa\\:ss${v(14)}\n`)).toEqual([
      { field: 'db.example:5432:*:app', value: v(13) },
      { field: 'localhost:5432:main:me', value: `pa:ss${v(14)}` },
    ])
    expect(credentialFields('netrc', `machine api.example\n  login me\n  password ${v(15)}\ndefault login x password ${v(16)}\n`)).toEqual([
      { field: 'api.example.password', value: v(15) },
      { field: 'default.password', value: v(16) },
    ])
    expect(credentialFields('git-credentials', `https://me:${v(17)}@github.com\nhttps://x:a%40b${v(18)}@git.example/path\n`)).toEqual([
      { field: 'me@github.com', value: v(17) },
      { field: 'x@git.example/path', value: `a@b${v(18)}` },
    ])
    expect(credentialFields('npmrc', `registry=https://registry.npmjs.org/\n//registry.npmjs.org/:_authToken=${v(19)}\n`)).toEqual([
      { field: '//registry.npmjs.org/:_authToken', value: v(19) },
    ])
  })

  test('a file that does not parse gives nothing', () => {
    expect(credentialFields('json', '{ not json')).toEqual([])
    expect(credentialFields('gcloud', '[1, 2]')).toEqual([])
  })

  test('every well-known credential file has a format', () => {
    expect(CREDENTIAL_FILES.map((f) => f.path)).toEqual([
      '.config/gh/hosts.yml',
      '.pgpass',
      '.codex/auth.json',
      '.claude/.credentials.json',
      '.config/hcloud/cli.toml',
      '.docker/config.json',
      '.netrc',
      '.git-credentials',
      '.npmrc',
    ])
  })

  test("a label names a file by its basename, or by its path from home when two files share one", () => {
    expect(credentialLabels(['.config/gh/hosts.yml', '.config/gcloud/legacy_credentials/a/adc.json', '.config/gcloud/legacy_credentials/b/adc.json'])).toEqual(
      new Map([
        ['.config/gh/hosts.yml', 'hosts.yml'],
        ['.config/gcloud/legacy_credentials/a/adc.json', '.config/gcloud/legacy_credentials/a/adc.json'],
        ['.config/gcloud/legacy_credentials/b/adc.json', '.config/gcloud/legacy_credentials/b/adc.json'],
      ]),
    )
  })
})

describe('the store', () => {
  test('a value drops one trailing newline', () => {
    expect(storeValue('value\n')).toBe('value')
    expect(storeValue('value\n\n')).toBe('value\n')
    expect(storeValue('value')).toBe('value')
  })

  test('a project is named as Claude Code names its folder under ~/.claude/projects/', () => {
    expect(projectSlug('/Users/u/Developer/repo')).toBe('-Users-u-Developer-repo')
    const long = projectSlug(`/Users/u/${'a'.repeat(120)}/${'b'.repeat(100)}`)
    expect(long.length).toBe(207)
    expect(long.slice(0, 200)).toBe(`-Users-u-${'a'.repeat(120)}-${'b'.repeat(70)}`)
  })

  test("a worktree's project is its main checkout; a submodule's is its own top level", () => {
    expect(rootFromGit('/work/repo/.git', '/work/repo-wt')).toBe('/work/repo')
    expect(rootFromGit('/work/super/.git/modules/sub', '/work/super/sub')).toBe('/work/super/sub')
  })
})

describe('fix wave 1', () => {
  test('#5 .git-credentials: the repository path is part of the identity', () => {
    expect(credentialFields('git-credentials', `https://me:${v(30)}@github.com/org/one.git\nhttps://me:${v(31)}@github.com/org/two.git\n`)).toEqual([
      { field: 'me@github.com/org/one.git', value: v(30) },
      { field: 'me@github.com/org/two.git', value: v(31) },
    ])
  })

  test('#7 hcloud TOML: an inline comment and the quotes are not the value', () => {
    const text = `[[contexts]]\n  name = "one # not a comment"\n  token = "${v(32)}" # rotated\n[[contexts]]\n  name = 'two'\n  token = '${v(33)}'   # old\n`
    expect(credentialFields('toml', text)).toEqual([
      { field: 'contexts.one # not a comment.token', value: v(32) },
      { field: 'contexts.two.token', value: v(33) },
    ])
  })

  test('#8 .netrc: a quoted value is decoded, spaces and escapes included', () => {
    expect(credentialFields('netrc', `machine api.example login me password "${v(34)} with \\"space\\""\n`)).toEqual([
      { field: 'api.example.password', value: `${v(34)} with "space"` },
    ])
  })
})
