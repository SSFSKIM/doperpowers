import type { Hook, On } from 'claude-code'

/**
 * `/secret KEY <value>` (or `KEY=<value>`): the value is typed masked in the
 * prompt box, stored in the macOS Keychain, and the model sees only the key.
 * The prompt history and the transcript keep bullets; a stored value that
 * turns up in a tool's output reaches neither the model nor the transcript
 * file. The masking needs the terminal's prompt box: on another surface the
 * value would arrive in the clear, so it is refused.
 */

export const SERVICE = 'claude-secrets'
export const MASK = '•'
// `/secret KEY ` or `/secret KEY=`: the value starts after the one character
// that ends the key.
const PREFIX = /^\/secret[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t=]/
const ARGS = /^([A-Za-z_][A-Za-z0-9_]*)[ \t=]([\s\S]*)$/
// The echo of a `/secret` run as the conversation keeps it.
const ECHO = /(<command-name>\/secret<\/command-name>[\s\S]*?<command-args>[ \t]*[A-Za-z_][A-Za-z0-9_]*[ \t=])([\s\S]*?)(<\/command-args>)/g
// Shorter values would scrub ordinary words out of everything the model reads.
const SCRUB_MIN = 6
const STORE_KEYS = 'secrets.keys'

// The value being typed. It lives only in this module's memory, never in
// `$.state` (which every plugin can read) or the prompt box.
let held = ''
// Every stored secret, key to value, so that no row the model reads carries one.
const known = new Map<string, string>()

type Edit = { text: string; start: number; end: number; inputText: string }
type Masked = { held: string; box?: { text: string; cursor: number } }

/**
 * One edit of the prompt box, given the value held so far. While the draft
 * reads `/secret KEY ` (or `KEY=`), what follows is kept in `held` and the box
 * shows one bullet per character; `box` absent means the edit is not ours.
 */
export function maskEdit(held: string, e: Edit): Masked {
  const before = PREFIX.exec(e.text)?.[0].length
  const isMasked = before !== undefined && e.text.slice(before) === MASK.repeat(held.length)
  const cursor = e.start + e.inputText.length

  if (isMasked && e.start < before) {
    // An edit to `/secret KEY ` itself drops the value, so a moved boundary
    // between key and value can never show part of it.
    const prefix = e.text.slice(0, before)
    return { held: '', box: { text: prefix.slice(0, e.start) + e.inputText + prefix.slice(Math.min(e.end, before)), cursor } }
  }

  const real = isMasked ? e.text.slice(0, before) + held : e.text
  const spliced = real.slice(0, e.start) + e.inputText + real.slice(e.end)
  const after = PREFIX.exec(spliced)?.[0].length
  if (after === undefined) return { held: '' }
  const value = spliced.slice(after)
  return { held: value, box: { text: spliced.slice(0, after) + MASK.repeat(value.length), cursor } }
}

/** A `/secret` echo with its value masked, for one typed where nothing masked it. */
export function maskEcho(text: string): string {
  return text.replace(ECHO, (_, head: string, value: string, tail: string) => head + MASK.repeat(value.length) + tail)
}

function scrub(text: string): string {
  let out = maskEcho(text)
  for (const [key, value] of known) {
    if (value.length >= SCRUB_MIN) out = out.split(value).join(`[secret:${key}]`)
  }
  return out
}

// A tool's record, every string in it scrubbed; the same object when none changed.
function scrubRecord(value: unknown): unknown {
  if (typeof value === 'string') return scrub(value)
  if (Array.isArray(value)) {
    const items = value.map(scrubRecord)
    return items.some((item, i) => item !== value[i]) ? items : value
  }
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value).map(([k, v]) => [k, scrubRecord(v)] as const)
    return entries.some(([k, v]) => v !== (value as Record<string, unknown>)[k]) ? Object.fromEntries(entries) : value
  }
  return value
}

function hex(text: string): string {
  return Array.from(new TextEncoder().encode(text), (b) => b.toString(16).padStart(2, '0')).join('')
}

function usage(key: string): string {
  return `"$(security find-generic-password -s ${SERVICE} -a ${key} -w)"`
}

// Taken with both matchers below: the other mods register session.start too,
// and an event is registered without one once per module.
const secretsStart: Hook<'session.start'> = async ($, e, next) => {
  await $.command.register({
    name: 'secret',
    description: 'Store a secret in the Keychain, typed masked: /secret KEY <value>',
    argumentHint: 'KEY value',
  })
  const keys = ((await $.store.get(STORE_KEYS)) ?? []) as string[]
  for (const key of keys) {
    const found = await $.process.run(['security', 'find-generic-password', '-s', SERVICE, '-a', key, '-w'])
    if (found.exitCode === 0) known.set(key, found.stdout.replace(/\n$/, ''))
  }
  return next(e)
}

export function registerSecrets(on: On) {
  on('session.start', { isInteractive: true }, secretsStart)
  on('session.start', { isInteractive: false }, secretsStart)

  on('prompt.edit', async (_, e, next) => {
    const masked = maskEdit(held, e)
    held = masked.held
    return masked.box ?? next(e)
  })

  on('command.run', { command: 'secret' }, async ($, e) => {
    if (e.args.trim() === '') {
      return { text: known.size ? `Stored: ${[...known.keys()].join(', ')}` : 'No secrets stored.' }
    }
    const parsed = ARGS.exec(e.args.trimStart())
    if (!parsed) return { text: 'Usage: /secret KEY <value>' }
    const [, key = '', typed = ''] = parsed
    const value = held
    held = ''
    if (value === '' || value.includes(MASK) || typed !== MASK.repeat(value.length)) {
      return {
        text:
          "Not stored: the value has to be typed in this terminal's prompt box after `/secret KEY `, where it is masked. " +
          'Typed in the clear, it stays in the prompt history (~/.claude/history.jsonl): treat it as exposed.',
      }
    }
    // The mask hides a mistyped character (an input method left on), and
    // `security ... -w` hands back a value outside printable ASCII as hex.
    if (/[^\x20-\x7e]/.test(value)) {
      return {
        text: 'Not stored: the value has a character outside printable ASCII (is a Korean or other input method on?). Type it again.',
      }
    }

    // The value goes in on stdin, as hex, so no process's arguments carry it.
    const added = await $.process.run(['security', '-i'], {
      stdin: `add-generic-password -U -s ${SERVICE} -a ${key} -X ${hex(value)}\n`,
    })
    if (added.exitCode !== 0) return { text: `Not stored: the Keychain refused (${added.stderr.trim().split('\n')[0]}).` }

    known.set(key, value)
    await $.store.set(STORE_KEYS, [...known.keys()])
    return {
      text: `Stored ${key} in the Keychain (service ${SERVICE}).`,
      context: [
        `The person stored a secret under ${key}. You never see its value. ` +
          `In a shell command, read it as ${usage(key)}, never printing it.`,
      ],
    }
  })

  // The tool's own record is what the transcript file keeps beside the row the
  // model reads (`toolUseResult`), and `session.append` cannot reach it.
  on('tool.call', async (_, e, next) => {
    const ran = await next(e)
    if (ran.deny !== undefined || known.size === 0) return ran
    const result = scrubRecord(ran.result)
    if (result === ran.result) return ran
    return ran.isError ? { deny: scrub(ran.text ?? '') } : { result, context: ran.context }
  })

  // The last line of defence: a stored value that turns up in any row the
  // conversation keeps (a tool's output, an echo) is replaced by its key.
  on('session.append', async (_, e, next) => {
    let isChanged = false
    const content = e.message.content.map((block) => {
      if (block.type === 'text' && typeof block.text === 'string') {
        const text = scrub(block.text)
        if (text === block.text) return block
        isChanged = true
        return { ...block, text }
      }
      if (block.type === 'tool_result') {
        const inner = scrubRecord(block.content)
        if (inner === block.content) return block
        isChanged = true
        return { ...block, content: inner }
      }
      return block
    })
    return isChanged ? next({ ...e, message: { ...e.message, content } }) : next(e)
  })

  on('prompt.compose', async (_, e, next) => {
    const composed = await next(e)
    if (known.size === 0) return composed
    const lines = [...known.keys()].map((key) => `- ${key}: ${usage(key)}`)
    return {
      sections: [
        ...composed.sections,
        {
          id: 'doperpowers:secrets',
          scope: 'session',
          text:
            'Secrets the person stored in the macOS Keychain. You see only their keys; ' +
            'read a value inside the shell command that uses it, never printing it:\n' +
            lines.join('\n'),
        },
      ],
    }
  })
}
