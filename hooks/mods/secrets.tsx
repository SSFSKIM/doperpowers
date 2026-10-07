import type { EngineInterface, Hook, On } from 'claude-code'

/**
 * `/secret KEY` opens a field in a pane; the value typed there is drawn as
 * bullets, stored as `~/.config/claude-secrets/KEY` (mode 600), and the model
 * sees only the key. The value never passes through the prompt box, so neither
 * the prompt history nor the transcript can hold it; a stored value that turns
 * up in a tool's output reaches neither the model nor the transcript file.
 *
 * Not the prompt box: when the last keys and Enter arrive in one read (mosh,
 * a slow link), the editor inserts and submits them before a `prompt.edit`
 * answer lands, so they reach the history raw. The box still masks a value
 * typed there out of habit, and the command refuses it.
 */

// A file per key, not the Keychain: a session under ssh, mosh or a daemon
// finds the login keychain locked and cannot raise its unlock dialog.
export const DIR = '.config/claude-secrets'
export const MASK = '•'
// `/secret KEY ` or `/secret KEY=`: the value starts after the one character
// that ends the key.
const PREFIX = /^\/secret[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t=]/
const ARGS = /^([A-Za-z_][A-Za-z0-9_]*)[ \t=]([\s\S]*)$/
// The echo of a `/secret` run as the conversation keeps it.
const ECHO = /(<command-name>\/secret<\/command-name>[\s\S]*?<command-args>[ \t]*[A-Za-z_][A-Za-z0-9_]*[ \t=])([\s\S]*?)(<\/command-args>)/g
// Shorter values would scrub ordinary words out of everything the model reads.
const SCRUB_MIN = 6

const PANE = 'secret'
const FIELD = 'secret-value'

// What is typed lives only in this module's memory, never in `$.state` (which
// every plugin can read): `drafted` behind the prompt box's bullets, `typed`
// behind the field's, for the key in `pending`.
let drafted = ''
let typed = ''
let pending: string | undefined
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

/**
 * The field's text read back against what it held: bullets for the characters
 * kept, then whatever was typed since the last redraw (several characters when
 * they arrived together, Enter among them). Undefined for an edit inside the
 * bullets, which cannot be placed.
 */
export function readField(held: string, value: string): string | undefined {
  const kept = value.length - value.replace(/^•+/, '').length
  const added = value.slice(kept)
  if (kept > held.length || added.includes(MASK)) return undefined
  return held.slice(0, kept) + added
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

function usage(key: string): string {
  return `"$(cat ~/${DIR}/${key})"`
}

async function storeField($: EngineInterface, key: string, value: string) {
  if (value === '') return
  // The bullets hide a mistyped character, an input method left on.
  if (/[^\x20-\x7e]/.test(value)) {
    typed = ''
    $.ui.toast('secret: a character outside printable ASCII (an input method on?); type it again')
    return
  }
  // The value goes in on stdin, so no process's arguments carry it, and is
  // created under umask 077 (`$.fs.write` sets no mode).
  const dir = `${await $.env.get('HOME')}/${DIR}`
  const added = await $.process.run(
    ['/bin/sh', '-c', 'umask 077 && mkdir -p "$1" && chmod 700 "$1" && cat > "$1/$2" && chmod 600 "$1/$2"', 'sh', dir, key],
    { stdin: value },
  )
  if (added.exitCode !== 0) {
    $.ui.toast(`secret: not stored, ${added.stderr.trim().split('\n')[0] || 'the write failed'}`)
    return
  }
  known.set(key, value)
  typed = ''
  pending = undefined
  await $.ui.close({ id: PANE })
  $.ui.toast(`secret: stored ${key}`)
  await $.session.append({
    message: {
      type: 'user',
      content: [
        {
          type: 'text',
          text: `The person stored a secret under ${key}. You never see its value. In a shell command, read it as ${usage(key)}, never printing it.`,
        },
      ],
    },
  })
}

// Taken with both matchers below: the other mods register session.start too,
// and an event is registered without one once per module.
const secretsStart: Hook<'session.start'> = async ($, e, next) => {
  await $.command.register({
    name: 'secret',
    description: 'Store a secret that the model sees only by its key; the value goes in the field it opens',
    argumentHint: 'KEY',
  })
  const dir = `${await $.env.get('HOME')}/${DIR}`
  if (await $.fs.exists(dir)) {
    for (const entry of await $.fs.list(dir)) {
      if (entry.kind === 'file' && /^[A-Za-z_][A-Za-z0-9_]*$/.test(entry.name)) {
        known.set(entry.name, await $.fs.read(`${dir}/${entry.name}`))
      }
    }
  }
  return next(e)
}

export function registerSecrets(on: On) {
  on('session.start', { isInteractive: true }, secretsStart)
  on('session.start', { isInteractive: false }, secretsStart)

  // Masks a value typed into the box out of habit; the command refuses it.
  on('prompt.edit', async (_, e, next) => {
    const masked = maskEdit(drafted, e)
    drafted = masked.held
    return masked.box ?? next(e)
  })

  on('command.run', { command: 'secret' }, async ($, e) => {
    const args = e.args.trim()
    if (args === '') {
      return { text: known.size ? `Stored: ${[...known.keys()].join(', ')}` : 'No secrets stored.' }
    }
    const parsed = ARGS.exec(args)
    drafted = ''
    if (parsed) {
      return {
        text:
          'Not stored: type `/secret KEY` alone and the value in the field it opens. ' +
          'A value typed in the prompt box may be in the prompt history (~/.claude/history.jsonl), whole or in part.',
      }
    }
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(args)) return { text: 'Usage: /secret KEY (letters, digits and _)' }
    pending = args
    typed = ''
    await $.ui.open({ id: PANE, title: `secret ${args}`, focus: true, closeOnEscape: true, rows: 2 })
    return { text: `Type the value of ${args} in the field of the pane it opened: Enter stores it, Escape cancels.` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, ($, e) => {
    if (e.surface === 'mobile') {
      const { Text } = $.ui.resolve(e)
      return <Text>The mobile app draws no field: type the value from a terminal, the desktop app or VS Code.</Text>
    }
    const { Box, Input, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        <Input
          key={FIELD}
          label={`${pending ?? ''} `}
          value={MASK.repeat(typed.length)}
          placeholder="value"
          submitLabel="store"
          autoFocus
          onSubmit={() => {}}
        />
        <Text dimColor>Escape cancels. Stored in ~/{DIR}/{pending ?? ''}, mode 600.</Text>
      </Box>
    )
  })

  // Taken here rather than in the element's closures, which have no `$`.
  on('ui.input', { element: FIELD }, async ($, e) => {
    const value = readField(typed, e.value)
    typed = value ?? ''
    if (value === undefined) $.ui.toast('secret: edit at the end of the field; it was cleared')
    $.ui.invalidate('ui.render')
    if (e.kind === 'submit' && value !== undefined && pending !== undefined) await storeField($, pending, value)
    return { element: e.element, value: MASK.repeat(typed.length) }
  })

  on('ui.close', { id: PANE }, (_, e, next) => {
    typed = ''
    pending = undefined
    return next(e)
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
            'Secrets the person stored, one file each. You see only their keys; ' +
            'read a value inside the shell command that uses it, never printing it:\n' +
            lines.join('\n'),
        },
      ],
    }
  })
}
