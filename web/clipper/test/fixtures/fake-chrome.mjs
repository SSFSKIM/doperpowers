#!/usr/bin/env node
// A stand-in for Chromium on --remote-debugging-pipe, for the driver's tests
// on machines with no Chromium: it answers the commands a render sends, and
// the navigated URL's path picks how the page behaves, and a drawn SVG's text
// how its drawing goes. Each reply goes out in one write with the event that
// follows it, as Chromium's own often arrive.
import { appendFileSync, createReadStream, writeFileSync, writeSync } from 'node:fs'

const out = (...messages) => writeSync(4, messages.map(m => JSON.stringify(m) + '\0').join(''))
let mode = ''
let svg = ''
let buf = ''
createReadStream('', { fd: 3 }).on('data', chunk => {
  buf += chunk
  for (let i = buf.indexOf('\0'); i !== -1; i = buf.indexOf('\0')) {
    const { id, method, params, sessionId } = JSON.parse(buf.slice(0, i))
    buf = buf.slice(i + 1)
    const reply = result => ({ id, result, ...(sessionId ? { sessionId } : {}) })
    const event = (name, p) => ({ method: name, params: p, sessionId })
    if (method === 'Target.createTarget') out(reply({ targetId: 'T1' }))
    else if (method === 'Target.attachToTarget') out(reply({ sessionId: 'S1' }))
    else if (method === 'Page.navigate') {
      mode = new URL(params.url).pathname.slice(1)
      if (mode === 'fails') out(reply({ frameId: 'T1', loaderId: 'L1', errorText: 'net::ERR_TUNNEL_CONNECTION_FAILED' }))
      else out(reply({ frameId: 'T1', loaderId: 'L1' }), event('Page.lifecycleEvent', { frameId: 'T1', loaderId: 'L1', name: 'load' }))
    } else if (method === 'Emulation.setVirtualTimePolicy') {
      // A page that keeps a request open never spends its budget.
      if (mode === 'stalls') out(reply({ virtualTimeTicksBase: 1 }))
      else out(reply({ virtualTimeTicksBase: 1 }), event('Emulation.virtualTimeBudgetExpired', {}))
    } else if (method === 'Page.getFrameTree') out(reply({ frameTree: { frame: { id: 'T1' } } }))
    else if (method === 'Page.setDocumentContent') {
      svg = Buffer.from(/base64,([^"]*)/.exec(params.html)[1], 'base64').toString()
      out(reply({}))
    } else if (method === 'Runtime.evaluate' && params.expression.includes('decode()')) {
      if (!svg.includes('hangs')) out(reply({ result: { type: 'object', value: [100, 50] } }))
    } else if (method === 'Emulation.setDeviceMetricsOverride' && svg.includes('rejected')) {
      out({ id, error: { code: -32602, message: 'Invalid parameters' }, ...(sessionId ? { sessionId } : {}) })
    } else if (method === 'Page.captureScreenshot') out(reply({ data: Buffer.from('a drawing').toString('base64') }))
    else if (method === 'Runtime.evaluate') {
      out(reply({ result: { type: 'string', value: `<html><body><p>${mode} page</p></body></html>` } }))
    } else if (method === 'Browser.close') {
      out(reply({}))
      if (mode !== 'slowlog') process.exit(0)
      // A loaded machine: the NetLog's last events and its close land seconds after Browser.close.
      const log = process.argv.find(a => a.startsWith('--log-net-log='))?.slice('--log-net-log='.length)
      const url = 'http://fake.test/slowlog'
      writeFileSync(log, JSON.stringify({ constants: { logEventTypes: { URL_REQUEST_START_JOB: 1, HTTP_TRANSACTION_READ_RESPONSE_HEADERS: 2 } } }).slice(0, -1)
        + ',"events":[\n' + JSON.stringify({ source: { id: 1 }, type: 1, params: { url, request_type: 'main frame' } }) + ',\n')
      setTimeout(() => {
        appendFileSync(log, JSON.stringify({ source: { id: 1 }, type: 2, params: { headers: ['HTTP/1.1 200 OK', 'content-type: text/html'] } }) + ']}\n')
        process.exit(0)
      }, 3500)
    } else out(reply({}))
  }
})
