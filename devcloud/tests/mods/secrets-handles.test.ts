import { describe, expect, test } from 'claude-code/testing'

import { Handles, spellings } from '../../hooks/mods/secrets-handles'
import { isInert } from '../../hooks/mods/secrets-shell'
import { chars, githubPat, pem } from './fake'

const STORED = `sk-live-${chars(20, 41)}`
const b64 = (s: string) => btoa(String.fromCharCode(...new TextEncoder().encode(s)))

const withStored = (known: Record<string, string> = { API_KEY: STORED }) => {
  const handles = new Handles('abcd')
  handles.setKnown(Object.entries(known).map(([label, value]) => ({ label, value })))
  return handles
}

describe('known values', () => {
  test('a stored value and each of its encodings get their own handle', () => {
    const h = withStored()
    const hex = Array.from(new TextEncoder().encode(STORED), (b) => b.toString(16).padStart(2, '0')).join('')
    expect(h.scrub(`a ${STORED} b`)).toBe('a [secret:API_KEY] b')
    expect(h.scrub(b64(STORED))).toBe('[secret:API_KEY~b64]')
    expect(h.scrub(hex)).toBe('[secret:API_KEY~hex]')
    expect(h.scrub(hex.toUpperCase())).toBe('[secret:API_KEY~HEX]')
    expect(h.scrub(encodeURIComponent(`${STORED}/x y`))).toBe(encodeURIComponent(`${STORED}/x y`).replace(encodeURIComponent(STORED), '[secret:API_KEY]'))
  })

  test('every spelling names a distinct byte string', () => {
    for (const value of [STORED, 'a/b+c=?d e&f', 'line one\nline "two"']) {
      const all = spellings(value)
      expect(new Set(all.map((s) => s.text)).size).toBe(all.length)
      expect(new Set(all.map((s) => s.enc)).size).toBe(all.length)
    }
  })

  test('a value under six characters is not scrubbed', () => {
    expect(withStored({ SHORT: 'abc12' }).scrub('abc12 abc12')).toBe('abc12 abc12')
  })

  test('a value is replaced in one pass: a handle is never scrubbed again', () => {
    const h = withStored({ WORD: 'secret', API_KEY: STORED })
    expect(h.scrub(`${STORED} secret`)).toBe('[secret:API_KEY] [secret:WORD]')
  })

  test('a shadowed global value and a credential-file value keep their own label', () => {
    const h = withStored({ API_KEY: STORED, 'API_KEY@global': `${STORED}-global`, 'hosts.yml:github.com.oauth_token': githubPat() })
    expect(h.scrub(`${STORED}-global ${STORED} ${githubPat()}`)).toBe('[secret:API_KEY@global] [secret:API_KEY] [secret:hosts.yml:github.com.oauth_token]')
  })

  test('a known value is a known handle, not a pattern one', () => {
    const h = withStored({ 'hosts.yml:github.com.oauth_token': githubPat() })
    expect(h.scrub(`TOKEN=${githubPat()}`)).toBe('TOKEN=[secret:hosts.yml:github.com.oauth_token]')
  })

  test("a known value's JSON spelling is its own encoding", () => {
    const key = pem(3)
    const h = withStored({ 'key.json:private_key': key })
    expect(h.scrub(JSON.stringify({ private_key: key }))).toBe('{"private_key":"[secret:key.json:private_key~json]"}')
    expect(h.restore('[secret:key.json:private_key~json]').text).toBe(JSON.stringify(key).slice(1, -1))
  })
})

describe('restoring', () => {
  test('a known handle restores to the current value in the named spelling', () => {
    const h = withStored()
    expect(h.restore('Authorization: Bearer [secret:API_KEY]')).toEqual({ text: `Authorization: Bearer ${STORED}`, unrestored: [] })
    expect(h.restore('[secret:API_KEY~b64]').text).toBe(b64(STORED))
  })

  test('after a rotation a known handle restores to the new value, and the old one reads superseded', () => {
    const h = withStored()
    h.setKnown([{ label: 'API_KEY', value: `${STORED}-rotated` }])
    expect(h.restore('[secret:API_KEY]').text).toBe(`${STORED}-rotated`)
    expect(h.scrub(`${STORED}-rotated / ${STORED} / ${b64(STORED)}`)).toBe('[secret:API_KEY] / [superseded:API_KEY] / [superseded:API_KEY~b64]')
    expect(h.restore('[superseded:API_KEY]')).toEqual({ text: '[superseded:API_KEY]', unrestored: ['[superseded:API_KEY]'] })
  })

  test('a removed key reads superseded and its handle is not restored', () => {
    const h = withStored()
    h.setKnown([])
    expect(h.scrub(STORED)).toBe('[superseded:API_KEY]')
    expect(h.restore('x [secret:API_KEY] y')).toEqual({ text: 'x [secret:API_KEY] y', unrestored: ['[secret:API_KEY]'] })
  })

  test('a value moved to another label is current, not superseded', () => {
    const h = withStored()
    h.setKnown([
      { label: 'API_KEY', value: `${STORED}-project` },
      { label: 'API_KEY@global', value: STORED },
    ])
    expect(h.scrub(STORED)).toBe('[secret:API_KEY@global]')
  })

  test('a pattern handle restores to exactly its bytes in the process that issued it', () => {
    const h = withStored({})
    const pat = githubPat(7)
    const scrubbed = h.scrub(`token ${pat} and again ${pat}, another ${githubPat(8)}`)
    expect(scrubbed).toBe('token [redacted:github-pat#abcd.1] and again [redacted:github-pat#abcd.1], another [redacted:github-pat#abcd.2]')
    expect(h.restore(scrubbed).text).toBe(`token ${pat} and again ${pat}, another ${githubPat(8)}`)
  })

  test("another process's pattern handle is left as written and named", () => {
    const earlier = withStored({})
    const old = earlier.scrub(githubPat(9))
    const resumed = new Handles('wxyz')
    resumed.scrub(githubPat(10))
    expect(resumed.restore(`echo ${old}`)).toEqual({ text: `echo ${old}`, unrestored: [old] })
  })

  test('text with no handle is returned as it is', () => {
    expect(withStored().restore('plain [not a handle] text')).toEqual({ text: 'plain [not a handle] text', unrestored: [] })
  })
})

describe('scrubbing whole records', () => {
  test('every string of a record is scrubbed, an unchanged record kept as the same object', () => {
    const h = withStored()
    const record = { stdout: `key ${STORED}`, nested: [{ text: githubPat(11) }], n: 3 }
    expect(h.scrubRecord(record)).toEqual({ stdout: 'key [secret:API_KEY]', nested: [{ text: '[redacted:github-pat#abcd.1]' }], n: 3 })
    const clean = { stdout: 'nothing here' }
    expect(h.scrubRecord(clean)).toBe(clean)
  })

  test("an image's base64 is left alone", () => {
    const h = withStored()
    const image = { type: 'image', source: { type: 'base64', media_type: 'image/png', data: `AKIA${'A'.repeat(16)}${STORED}` } }
    expect(h.scrubRecord(image)).toBe(image)
  })

  test('restoring a record restores each string and gathers what was not restored', () => {
    const h = withStored()
    const { value, unrestored } = h.restoreRecord({ file_path: '/x', old_string: '[secret:API_KEY]', new_string: '[superseded:OLD]' })
    expect(value).toEqual({ file_path: '/x', old_string: STORED, new_string: '[superseded:OLD]' })
    expect(unrestored).toEqual(['[superseded:OLD]'])
  })
})

test("a 6 MB output is scrubbed well within a hook's 10 s budget", () => {
  const h = withStored(Object.fromEntries(Array.from({ length: 20 }, (_, i) => [`KEY_${i}`, chars(i % 2 ? 64 : 1900, 60 + i)])))
  const text = `${'filler line '.padEnd(76, '.')}\n`.repeat(80_000) + `KEY_1 ${chars(64, 61)} and ${githubPat(62)}\n`
  const started = Date.now()
  const scrubbed = h.scrub(text)
  expect(Date.now() - started < 2_000).toBe(true)
  expect(scrubbed.endsWith('KEY_1 [secret:KEY_1] and [redacted:github-pat#abcd.1]\n')).toBe(true)
})

describe('fix wave 1', () => {
  test('#4 a label with spaces, brackets or tildes round-trips through its handle', () => {
    const label = 'cli.toml:contexts.my ctx]~x%.token'
    const h = withStored({ [label]: STORED })
    const handle = h.scrub(STORED)
    expect(handle).toMatch(/^\[secret:[^\]\s]+\]$/)
    expect(h.restore(`a ${handle} b`)).toEqual({ text: `a ${STORED} b`, unrestored: [] })
    expect(h.restore(h.scrub(btoa(STORED))).text).toBe(btoa(STORED))
  })

  test('#4 a handle-like text that cannot be parsed is named as not restored', () => {
    expect(withStored().restore('k=[secret:foo bar] [secret:API_KEY]')).toEqual({ text: `k=[secret:foo bar] ${STORED}`, unrestored: ['[secret:foo bar]'] })
  })

  test('#5 two distinct values under one label are both redacted and both restore', () => {
    const h = new Handles('abcd')
    h.setKnown([
      { label: 'x:y', value: `${STORED}-one` },
      { label: 'x:y', value: `${STORED}-two` },
    ])
    const one = h.scrub(`${STORED}-one`)
    const two = h.scrub(`${STORED}-two`)
    expect(one).not.toBe(two)
    expect(two).toMatch(/^\[secret:/)
    expect([h.restore(one).text, h.restore(two).text]).toEqual([`${STORED}-one`, `${STORED}-two`])
  })

  test("#6 a value's pgpass spelling (\\: and \\\\ escaped) is its own encoding", () => {
    const value = `pa:ss\\${STORED}`
    const h = withStored({ '.pgpass:db:5432:*:app': value })
    const printed = `db:5432:*:app:pa\\:ss\\\\${STORED}`
    expect(h.scrub(printed)).toBe('db:5432:*:app:[secret:.pgpass:db:5432:*:app~pgpass]')
    expect(h.restore('[secret:.pgpass:db:5432:*:app~pgpass]').text).toBe(`pa\\:ss\\\\${STORED}`)
  })
})

describe('fix wave 2', () => {
  test('#2 two labels holding the same value both restore; the bytes display as the first', () => {
    const h = withStored({ A: STORED, B: STORED })
    expect(h.scrub(STORED)).toBe('[secret:A]')
    expect(h.restore('[secret:A] [secret:B]').text).toBe(`${STORED} ${STORED}`)
  })

  test("#2 a label that rotates to another label's value still restores its already-issued handle", () => {
    const h = withStored({ A: STORED, B: `${STORED}-b` })
    expect(h.scrub(`${STORED}-b`)).toBe('[secret:B]')
    h.setKnown([
      { label: 'A', value: STORED },
      { label: 'B', value: STORED },
    ])
    expect(h.restore('[secret:B]').text).toBe(STORED)
    expect(h.scrub(`${STORED}-b`)).toBe('[superseded:B]')
  })
})

describe('fix wave 3', () => {
  test('#1 the inert alphabet: no = right after = or :, but a trailing run (base64 padding) is plain', () => {
    for (const value of [STORED, 'abcDEF012_./+:@-', 'YWJj+/9=', 'YWJjZA==', 'a=b', 'x%41', 'a:=', githubPat(80)]) expect(isInert(value)).toBe(true)
    for (const value of ['', '=cmd', '%1', '~root', 'foo==printf', 'a:=printf', 'a b', 'a;b', 'a$b', 'a`b', "a'b", 'a"b', 'a\\b', 'a\nb', 'a*', 'a?', 'a[b]', 'a{b,c}', 'a!b', 'a#b', 'a^b', 'a~b', 'a(b)', 'a<b', 'a>b', 'a|b', 'a&b', 'a,b']) {
      expect(isInert(value)).toBe(false)
    }
  })

  test('#1 a value that is not inert is never restored into a command, whatever its quoting', () => {
    const h = withStored({ V: 'a b' })
    for (const command of ["printf %s '[secret:V]'", 'printf %s "[secret:V]"', 'printf %s [secret:V]', 'x=[secret:V]']) {
      expect(h.restoreShell(command)).toEqual({ text: command, unrestored: [], unquotable: ['[secret:V]'] })
    }
  })

  test('#1 an inert value is restored at a plain position of a plain command', () => {
    const h = withStored({ SAFE: STORED })
    // Since fix wave 4, `a,[secret:SAFE].b` (a `,` in the word) and `"$(printf %s [secret:SAFE])"` (a `$` in the string) are left.
    for (const command of ['echo [secret:SAFE]', "printf %s '[secret:SAFE]'", 'curl -H "Authorization: Bearer [secret:SAFE]" x', 'X=[secret:SAFE] cmd', 'export X=[secret:SAFE]; echo "$(printf %s ok)"', 'echo x[secret:SAFE]y']) {
      expect(h.restoreShell(command)).toEqual({ text: command.split('[secret:SAFE]').join(STORED), unrestored: [], unquotable: [] })
    }
  })

  test('#1 an inert value is left as the handle in a command or at a position the rule does not admit', () => {
    const h = withStored({ SAFE: STORED, PAD: 'YWJjZA==' })
    for (const command of [
      "cat <<'EOF'\n[secret:SAFE]\nEOF",
      'cat <<< [secret:SAFE]',
      'x=`echo [secret:SAFE]`',
      ': # [secret:SAFE]',
      'echo \\\n[secret:SAFE]',
      '(( x = [secret:SAFE] ))',
      'echo $(( [secret:SAFE] ))',
      'echo $[ [secret:SAFE] ]',
      'let x=[secret:SAFE]',
      '[[ [secret:SAFE] -eq 1 ]]',
      'typeset -i x=[secret:SAFE]',
      'echo ${[secret:SAFE]}',
      'echo ${X:-[secret:SAFE]}',
      'echo \\[secret:SAFE]',
      'echo "\\[secret:SAFE]"',
      'echo {a,[secret:SAFE]}',
      'echo *[secret:SAFE]',
      'echo $[secret:SAFE]',
      'echo $X[secret:SAFE]',
      'echo x==[secret:SAFE]',
      'echo x:=[secret:SAFE]',
      'echo [secret:PAD]x',
    ]) {
      const r = h.restoreShell(command)
      expect([command, r.text, r.unquotable.length > 0]).toEqual([command, command, true])
    }
  })
})

describe('fix wave 4', () => {
  test('#1 the common shapes still restore: a plain quoted string, a plain word', () => {
    for (const value of ['hunter2abcdef', 'tok12345', 'abcdef12', 'sk-live-x9', 'ghp_x9abc', 'AKIAX9ABC']) {
      const h = withStored({ K: value })
      for (const command of [
        'curl -H "Authorization: Bearer [secret:K]" https://x',
        "printf %s 'a [secret:K] b'",
        'cmd --token=[secret:K]',
        'X=[secret:K] cmd',
        'git push https://user:[secret:K]@github.com/o/r.git',
      ]) {
        expect(h.restoreShell(command)).toEqual({ text: command.replace('[secret:K]', value), unrestored: [], unquotable: [] })
      }
    }
  })

  test('#1 a word or string the rule does not admit keeps the handle', () => {
    const h = withStored({ K: 'habcdef12' })
    for (const command of [
      'printf %s $USER:[secret:K]',
      'printf %s "$USER:[secret:K]"',
      'git push https://$USER:[secret:K]@github.com/o/r.git',
      'printf %s $1:[secret:K]',
      'printf %s ${USER}:[secret:K]',
      'printf %s =[secret:K]',
      "printf %s ''=[secret:K]",
      'a=( =[secret:K] ); printf %s "$a"',
      'printf %s {a,=[secret:K],b}',
      'typeset -F x=[secret:K]',
      'local -F x=[secret:K]',
      'float x=[secret:K]',
      'export -n X=[secret:K]',
      'printf %s ${a[ [secret:K] ]}',
      'printf %s ${X: [secret:K] }',
      'printf %s ${X/a[secret:K]/Q}',
      'printf %s ok >& [secret:K]',
      'printf %s ok > [secret:K]',
      'printf %s {x[secret:K]y}',
      'printf %s *(.[secret:K])',
      'printf %s a,[secret:K]',
      'printf %s "a$b[secret:K]"',
      'printf %s "a!b[secret:K]"',
      'printf %s "\\[secret:K]"',
    ]) {
      const r = h.restoreShell(command)
      expect([command, r.text, r.unquotable]).toEqual([command, command, ['[secret:K]']])
    }
  })

  test('#7 setKnown names each entry, a second value under a taken label #2', () => {
    const h = new Handles('abcd')
    expect(h.setKnown([
      { label: 'f:one', value: `${STORED}-1` },
      { label: 'f:one', value: `${STORED}-2` },
      { label: 'g', value: `${STORED}-1` },
    ])).toEqual(['f:one', 'f:one#2', 'g'])
  })
})
