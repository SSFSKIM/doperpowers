import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer, get } from 'node:http'
import { isPublicAddress, resolveChecked, allowedHosts, boundaryOf, deniedHosts, isDenied, pinnedLookup, RefusedError } from '../src/netguard.ts'

test('IPv4 addresses outside the public internet are refused', () => {
  for (const ip of [
    '127.0.0.1', '127.255.0.9', '0.0.0.0', '0.1.2.3', '10.1.2.3', '172.16.0.1', '172.31.255.255',
    '192.168.1.1', '169.254.169.254', '100.64.0.1', '100.127.255.254', '224.0.0.1', '239.1.1.1',
    '240.0.0.1', '255.255.255.255', '192.0.2.5', '198.18.0.1', '198.51.100.7', '203.0.113.9', '192.0.0.8',
  ]) assert.equal(isPublicAddress(ip), false, ip)
})

test('public IPv4 addresses pass, including neighbors of the refused ranges', () => {
  for (const ip of ['8.8.8.8', '1.1.1.1', '172.15.255.255', '172.32.0.1', '100.63.255.255', '100.128.0.1', '169.253.1.1', '93.184.216.34'])
    assert.equal(isPublicAddress(ip), true, ip)
})

test('IPv6 loopback, unique-local, link-local, multicast and the mapped forms of refused IPv4 are refused', () => {
  for (const ip of [
    '::1', '::', 'fc00::1', 'fd12:3456::1', 'fe80::1', 'febf::1', 'ff02::1',
    '::ffff:127.0.0.1', '::ffff:7f00:1', '::ffff:169.254.169.254', '::ffff:10.0.0.1', '::127.0.0.1',
    '64:ff9b::a9fe:a9fe', '2002:7f00:1::1', '2001:db8::1',
  ]) assert.equal(isPublicAddress(ip), false, ip)
})

test('public IPv6 addresses pass', () => {
  for (const ip of ['2606:4700::6810:84e5', '2001:4860:4860::8888', '::ffff:8.8.8.8'])
    assert.equal(isPublicAddress(ip), true, ip)
})

test('a host resolving to a public and a private address is refused, naming the private one', async () => {
  const resolve = async () => [{ address: '93.184.216.34', family: 4 }, { address: '10.0.0.7', family: 4 }]
  await assert.rejects(resolveChecked('mixed.example', 443, { resolve, boundary: boundaryOf({}) }), (e: unknown) => {
    assert.ok(e instanceof RefusedError)
    assert.equal(e.message, 'refused: mixed.example resolves to a non-public address (10.0.0.7); for a local server use curl through Bash')
    return true
  })
})

test('an IP literal is checked without a lookup', async () => {
  const resolve = async () => { throw new Error('no lookup expected') }
  await assert.rejects(resolveChecked('169.254.169.254', 80, { resolve, boundary: boundaryOf({}) }), /^RefusedError: refused: 169\.254\.169\.254/)
  assert.deepEqual(await resolveChecked('8.8.8.8', 80, { resolve, boundary: boundaryOf({}) }), [{ address: '8.8.8.8', family: 4 }])
})

test('a connection made with the pinned lookup goes to the checked address and never asks DNS', async () => {
  const server = createServer((_q, res) => res.end('pinned'))
  await new Promise<void>(r => server.listen(0, '127.0.0.1', r))
  const port = (server.address() as { port: number }).port
  try {
    // .invalid never resolves: reaching the server proves the pinned address was used.
    const body = await new Promise<string>((resolve, reject) => {
      get({ hostname: 'pinned.invalid', port, path: '/', agent: false, lookup: pinnedLookup([{ address: '127.0.0.1', family: 4 }]) }, res => {
        let b = ''
        res.on('data', d => { b += d })
        res.on('end', () => resolve(b))
      }).on('error', reject)
    })
    assert.equal(body, 'pinned')
  } finally {
    server.close()
  }
})

test('WEB_ALLOW_HOSTS exempts exactly the listed host:port pairs', async () => {
  const allow = allowedHosts({ WEB_ALLOW_HOSTS: '127.0.0.1:4100, localhost:4101' })
  assert.deepEqual([...allow], ['127.0.0.1:4100', 'localhost:4101'])
  assert.deepEqual(await resolveChecked('127.0.0.1', 4100, { boundary: { allow, deny: [] } }), [{ address: '127.0.0.1', family: 4 }])
  await assert.rejects(resolveChecked('127.0.0.1', 4102, { boundary: { allow, deny: [] } }), RefusedError)
  assert.equal(allowedHosts({}).size, 0)
})

test('WEB_DENY_HOSTS names hosts exactly, and *. names every host under one but not the host itself', () => {
  const deny = deniedHosts({ WEB_DENY_HOSTS: ' Example.COM , *.tracker.test., [::1], 예시.kr, , *. ' })
  assert.deepEqual(deny, ['example.com', '*.tracker.test', '::1', 'xn--vv4b11d.kr'])
  for (const host of ['example.com', 'EXAMPLE.com.', 'a.tracker.test', 'a.b.tracker.test', '[::1]', 'xn--vv4b11d.kr'])
    assert.equal(isDenied(host, deny), true, host)
  for (const host of ['www.example.com', 'notexample.com', 'tracker.test', 'eviltracker.test', 'example.org'])
    assert.equal(isDenied(host, deny), false, host)
  assert.deepEqual(deniedHosts({}), [])
})

test('a deny rule and a host are compared in the URL parser\'s form, so an IP literal or a name written another way still matches', async () => {
  const deny = deniedHosts({ WEB_DENY_HOSTS: '[2606:4700:4700:0:0:0:0:1111], 2130706433, ::FFFF:127.0.0.2, 예시.KR, not a host' })
  assert.deepEqual(deny, ['2606:4700:4700::1111', '127.0.0.1', '::ffff:7f00:2', 'xn--vv4b11d.kr', 'not a host'])
  for (const host of ['[2606:4700:4700::1111]', '2606:4700:4700:0000:0000:0000:0000:1111', '127.0.0.1', '0x7f.1', '017700000001', '[::ffff:127.0.0.2]', '예시.kr', 'NOT A HOST'])
    assert.equal(isDenied(host, deny), true, host)
  for (const host of ['[2606:4700:4700::1112]', '127.0.0.3', '::ffff:127.0.0.3'])
    assert.equal(isDenied(host, deny), false, host)
  // The URL from the review: the rule in full form, the URL's host in the parser's.
  const boundary = boundaryOf({ WEB_DENY_HOSTS: '[2606:4700:4700:0:0:0:0:1111]' })
  const url = new URL('https://[2606:4700:4700::1111]/')
  await assert.rejects(resolveChecked(url.hostname, 443, { boundary }), /^RefusedError: refused: 2606:4700:4700::1111 is on the deny list \(WEB_DENY_HOSTS\)$/)
})

test('a denied host is refused before any lookup, even one WEB_ALLOW_HOSTS exempts', async () => {
  const resolve = async () => { throw new Error('no lookup expected') }
  const boundary = boundaryOf({ WEB_ALLOW_HOSTS: 'cdn.blocked.test:443', WEB_DENY_HOSTS: '*.blocked.test' })
  await assert.rejects(resolveChecked('cdn.blocked.test', 443, { boundary, resolve }), (e: unknown) => {
    assert.ok(e instanceof RefusedError)
    assert.equal(e.message, 'refused: cdn.blocked.test is on the deny list (WEB_DENY_HOSTS)')
    assert.equal(e.brief, 'on the deny list')
    return true
  })
})
