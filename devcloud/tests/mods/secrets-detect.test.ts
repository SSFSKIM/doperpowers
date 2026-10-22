import { describe, expect, test } from 'claude-code/testing'

import { detect } from '../../hooks/mods/secrets-detect'
import { anthropicKey, awsKey, chars, githubPat, pem, token } from './fake'

const ALNUM_URL = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'

const found = (text: string) => detect(text).map((s) => [s.kind, text.slice(s.start, s.end)])

describe('token-shaped strings', () => {
  test('a published prefix is found wherever it stands, its whole token taken', () => {
    const pat = githubPat()
    expect(found(`push failed: ${pat} rejected`)).toEqual([['github-pat', pat]])
    expect(found(`"${anthropicKey()}"`)).toEqual([['anthropic', anthropicKey()]])
    expect(found(`key=${awsKey()}.`)).toEqual([['aws-access-key', awsKey()]])
  })

  test('each published prefix has its rule', () => {
    const cases: [string, string][] = [
      ['openrouter', token(['sk-', 'or-', 'v1-'], 64, 2, '0123456789abcdef')],
      ['openai', token(['sk-', 'proj-'], 48, 3)],
      ['github-oauth', token(['gh', 'o_'], 36, 4)],
      ['github-app-token', token(['gh', 'u_'], 36, 5)],
      ['github-app-token', token(['gh', 's_'], 36, 6)],
      ['github-fine-grained-pat', token(['github', '_pat_'], 82, 7, 'abcdefghijklmnopqrstuvwxyz0123456789_')],
      ['tailscale', token(['ts', 'key-', 'auth-'], 30, 8)],
      ['slack', token(['xo', 'xb-'], 40, 9)],
      ['aws-access-key', token(['AS', 'IA'], 16, 10, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567')],
      ['gitlab-pat', token(['gl', 'pat-'], 20, 11)],
      ['huggingface', token(['h', 'f_'], 34, 12)],
      ['gcp-api-key', token(['AI', 'za'], 35, 13)],
      ['google-access-token', token(['ya', '29.', 'a0'], 160, 14, ALNUM_URL)],
      ['google-access-token', token(['ya', '29.', 'c.', 'c0'], 900, 15, ALNUM_URL)],
      ['google-refresh-token', token(['1/', '/0'], 100, 16, ALNUM_URL)],
    ]
    for (const [kind, value] of cases) expect(found(`x ${value} y`)).toEqual([[kind, value]])
  })

  test('a bare Google access token is found as gcloud prints it, alone on its line', () => {
    const access = token(['ya', '29.', 'a0'], 160, 17, ALNUM_URL)
    expect(found(`${access}\n`)).toEqual([['google-access-token', access]])
    expect(found(`token is ${access}.`)).toEqual([['google-access-token', access]])
  })

  test('a prefix inside a longer word is no token', () => {
    expect(found(`risk-${chars(30)}`)).toEqual([])
    expect(found(`task${githubPat()}`)).toEqual([])
  })

  test('a PEM private key block is found whole, raw or JSON-escaped', () => {
    const block = pem()
    expect(found(`key:\n${block}\nend`)).toEqual([['pem', block]])
    const escaped = JSON.stringify(block).slice(1, -1)
    expect(found(`{"private_key": "${escaped}"}`)).toEqual([['pem', escaped]])
  })
})

describe('assignments whose name says secret', () => {
  const value = chars(24, 21)

  test('the value of a secret-named assignment is found, its name and quotes left', () => {
    for (const line of [
      `GITHUB_TOKEN=${value}`,
      `export DB_PASSWORD="${value}"`,
      `client_secret: '${value}'`,
      `"api_key": "${value}"`,
      `apiKey = ${value}`,
      `Authorization: Bearer ${value}`,
      `PRIVATE_KEY=${value}`,
      `aws_credential=${value}`,
    ]) {
      expect(found(line)).toEqual([['assignment', value]])
    }
  })

  test('a name that only contains a secret word is no secret name', () => {
    expect(found(`TOKENIZER=${value}`)).toEqual([])
    expect(found(`secretary=${value}`)).toEqual([])
  })

  test('a short, low-entropy, or referenced value is left', () => {
    expect(found(`TOKEN=${chars(12)}`)).toEqual([])
    expect(found('PASSWORD=aaaaaaaaaaaaaaaaaaaaaaaa')).toEqual([])
    expect(found('PASSWORD=hunter2hunter2hunter2')).toEqual([])
    expect(found('GITHUB_TOKEN="$(cat ~/.config/gh/token-file-path)"')).toEqual([])
    expect(found('TOKEN_FILE=/home/someone/.config/service/token.txt')).toEqual([])
    expect(found('TOKEN_URL=https://example.com/oauth/token/endpoint')).toEqual([])
  })

  test('a handle is never read as a value', () => {
    expect(found('[secret:hosts.yml:github.com.oauth_token]')).toEqual([])
    expect(found('GITHUB_TOKEN=[secret:GITHUB_TOKEN]')).toEqual([])
    expect(found('token: [redacted:github-pat#abcd.1]')).toEqual([])
  })
})

describe('credential literals stay protected across data formats', () => {
  test('unknown quoted literals still redact across env, YAML, JSON, TOML and source code', () => {
    // No provider prefixes: only the assignment rule can protect these values.
    const values = [
      chars(32, 81),
      chars(32, 82, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'),
      'c7!Qz%4u*Fh9?Lw2@Jd6#Rb8',
      'APPLICATION_DEFAULT_CREDENTIALS',
      'oauth2_parameters.credentials',
      'config.browser?.isolatedToken',
    ]
    for (const value of values) {
      for (const line of [
        `export SERVICE_TOKEN="${value}"`,
        `password: '${value}'`,
        `{"client_secret": "${value}"}`,
        `api_key = '${value}'`,
        `const apiKey = "${value}";`,
      ]) expect(found(line)).toEqual([['assignment', value]])
    }
    for (let seed = 1; seed <= 100; seed++) {
      const value = chars(32, seed)
      expect(found(`SERVICE_TOKEN=${value}`)).toEqual([['assignment', value]])
    }
  })

  test('unquoted dotted credentials are not mistaken for numbered code references', () => {
    const jwt = `${btoa('{"alg":"HS256","typ":"JWT"}')}.${btoa('{"sub":"synthetic-test-123","iat":1234567890}')}.${chars(43, 84)}`
    for (const value of [jwt, 'Ab7cD9ef.G1h2I3jk.L4m5N6op', 'oauth2_parameters.credentials', 'Ab7cD9ef.G1h2I3jk+L4m5N6op']) {
      for (const line of [`SERVICE_TOKEN=${value}`, `password: ${value}`, `export API_KEY=${value}`]) {
        expect(found(line)).toEqual([['assignment', value]])
      }
    }
  })

  test('flow YAML and comma-separated logs do not establish source-expression context', () => {
    const jwt = `${btoa('{"alg":"HS256","typ":"JWT"}')}.${btoa('{"sub":"synthetic-test-123"}')}.${chars(43, 85)}`
    for (const value of ['Ab7cD9ef.G1h2I3jk+L4m5N6op', 'Ab7cD9ef.G1h2I3jk.L4m5N6op', jwt, chars(32, 86)]) {
      for (const line of [
        `{password: ${value}}`,
        `{user: sample, password: ${value}}`,
        `user=sample,password=${value}`,
        `{password: "${value}"}`,
        `user=sample,password='${value}'`,
      ]) expect(found(line)).toEqual([['assignment', value]])
    }
  })

  test('ambiguous bare fields remain eligible even when they resemble source expressions', () => {
    for (const value of ['usage2.cachedInputTokens??0', 'usage2.promptTokens+completionTokens', 'config2.clientSecret||fallbackValue']) {
      expect(found(`{token: ${value}}`)).toEqual([['assignment', value]])
    }
  })

  test('leading equals belongs to the credential in env and shell output', () => {
    const value = `=${chars(32, 87)}`
    for (const line of [`PASSWORD=${value}`, `export PASSWORD=${value}`, `PASSWORD = ${value}`, `PASSWORD="${value}"`]) {
      expect(found(line)).toEqual([['assignment', value]])
    }
  })

  test('opaque literals, including punctuation and alphabet-only values, still redact', () => {
    for (const value of [chars(32, 81), chars(32, 82, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'), 'c7!Qz%4u*Fh9?Lw2@Jd6#Rb8']) {
      expect(found(`password="${value}"`)).toEqual([['assignment', value]])
    }
  })
})

describe('what is not a secret', () => {
  test('a commit hash and a sha256 checksum are left', () => {
    const commit = chars(40, 31, '0123456789abcdef')
    const sum = chars(64, 32, '0123456789abcdef')
    expect(found(`commit ${commit}\nAuthor: someone`)).toEqual([])
    expect(found(`${sum}  release.tar.gz`)).toEqual([])
    expect(found(`sha256:${sum}`)).toEqual([])
    expect(found(`integrity: sha512-${chars(86, 33, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/')}==`)).toEqual([])
  })

  test('bare base64 without a prefix or a secret name is left', () => {
    expect(found(`data ${chars(60, 34)}`)).toEqual([])
  })
})

test('spans come in order and never overlap', () => {
  const text = `${githubPat(1)} and TOKEN=${githubPat(2)} then ${pem()}`
  const spans = detect(text)
  expect(spans.map((s) => s.kind)).toEqual(['github-pat', 'github-pat', 'pem'])
  for (let i = 1; i < spans.length; i++) expect(spans[i]!.start >= spans[i - 1]!.end).toBe(true)
})

describe('fix wave 1', () => {
  const value = chars(24, 71)

  test('#9 a reference in code is not a credential', () => {
    for (const line of [
      'const apiKey = process.env.API_KEY',
      'password = credentials.password',
      'const token = getAccessTokenFromVault(config)',
      'secret = os.environ["SERVICE_SECRET"]',
      'let password = userSuppliedPassword;',
      'TOKEN=${GITHUB_TOKEN_FOR_DEPLOYMENT}',
    ]) {
      expect(found(line)).toEqual([])
    }
  })

  test('#9 a credential literal is still found, quoted or not', () => {
    expect(found(`const apiKey = "${value}"`)).toEqual([['assignment', value]])
    expect(found(`API_KEY=${value}`)).toEqual([['assignment', value]])
    expect(found(`password: ${value}`)).toEqual([['assignment', value]])
  })

  test('#10 every separator the name grammar accepts reaches the detector', () => {
    for (const name of ['api-key', 'api.key', 'private-key', 'private.key']) expect(found(`${name}=${value}`)).toEqual([['assignment', value]])
  })
})
