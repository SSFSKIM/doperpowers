import type { On } from 'claude-code'

/**
 * The backtick guard: a Bash call that passes sminos a live backtick is
 * refused before it runs. In a double-quoted message body the shell runs the
 * text between backticks as a command, on this machine, and puts its output
 * (or, failing, nothing) in its place, so the message arrives changed and a
 * command nobody meant ran. The refusal says so and gives the form that
 * carries any text verbatim: the body on stdin, `-`, from a heredoc whose
 * delimiter is quoted.
 *
 * The command is lexed as a shell reads it (quotes, escapes, comments,
 * substitutions, heredocs, command boundaries), never matched as text: a
 * refusal of a legitimate command stops a session's work, where a miss only
 * leaves the shell's behaviour as it was. Live: unescaped, bare or in double
 * quotes, in a word after the sminos word of the same simple command, or in
 * the body of an unquoted-delimiter heredoc (or a here-string) on that command
 * or on one piped into it. Not live: single quotes, `$'…'`, an escaped
 * backtick, a quoted delimiter's body, a comment. The inside of `$(…)` is
 * opaque (sessions interpolate on purpose), though a sminos call inside it is
 * judged on its own. A sminos call is a word naming `sminos` (or `sminos.py`)
 * by its last path part, as the command or followed by one of its verbs (so
 * `devcloud vm ssh box -- sminos say "…"` counts: the local shell substitutes
 * all the same); a mention inside another command's string or heredoc is no
 * word of its own.
 *
 * Anything the lexer does not foresee fails open: a hook that throws is
 * skipped and the call runs.
 */

/** The CLI's verbs (its parser's), which mark a sminos word that is no command word as a call. */
export const VERBS = new Set([
  'spawn', 'seat', 'fill', 'wake', 'resume', 'send', 'say', 'chat', 'charge', 'join', 'derive', 'name-due', 'record',
  'guide', 'project', 'daemon', 'hub', 'rpc-query', 'bridge', 'watch', 'steer', 'interrupt', 'stop', 'model', 'compact',
  'command', 'read', 'decide', 'answer', 'reply', 'sync', 'status', 'retire', 'access', 'share', 'remove', 'list',
  'find', 'who', 'projects', 'machines', 'chart', 'tui', 'attach', 'migrate', 'meta', 'help',
])

/** A word as the lexer read it: its text with every expansion as NUL, and the first live backtick span in it. */
type Word = { text: string; pure: boolean; quoted: boolean; live?: string; redirect?: boolean }
/** A simple command: its words in order, the live span of each body it is fed (heredoc, here-string), its pipeline. */
type Simple = { words: Word[]; bodies: (string | undefined)[]; pipe: number }

const BLANK = new Set([' ', '\t'])
const ENDS_WORD = new Set([' ', '\t', '\n', ';', '&', '|', '(', ')', '<', '>'])
const NAME_ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*\+?=/

class Lexer {
  i = 0
  readonly commands: Simple[] = []
  private pipes = 0
  private pipe = 0
  constructor(private readonly src: string) {}

  private simple(): Simple {
    const s: Simple = { words: [], bodies: [], pipe: this.pipe }
    this.commands.push(s)
    return s
  }

  /** A list of commands up to the end, or, with `nested`, up to the `)` that closes a `$(`, consumed. */
  script(nested: boolean) {
    const saved = this.pipe
    this.pipe = ++this.pipes
    const src = this.src
    const heredocs: { simple: Simple; delimiter: string; quoted: boolean; strip: boolean }[] = []
    let cur = this.simple()
    let depth = 0
    const after = (newPipeline: boolean) => {
      if (newPipeline) this.pipe = ++this.pipes
      cur = this.simple()
    }
    while (this.i < src.length) {
      const c = src[this.i]!
      const d = src[this.i + 1]
      if (BLANK.has(c)) {
        this.i++
      } else if (c === '\\' && d === '\n') {
        this.i += 2
      } else if (c === '\n') {
        this.i++
        for (const h of heredocs.splice(0)) h.simple.bodies.push(this.heredoc(h.delimiter, h.quoted, h.strip))
        after(true)
      } else if (c === '#') {
        while (this.i < src.length && src[this.i] !== '\n') this.i++
      } else if (c === ';') {
        this.i++
        after(true)
      } else if (c === '&' && d !== '>') {
        this.i += d === '&' ? 2 : 1
        after(true)
      } else if (c === '|') {
        this.i += d === '|' || d === '&' ? 2 : 1
        after(d === '|')
      } else if (c === '(') {
        this.i++
        depth++
        after(true)
      } else if (c === ')') {
        this.i++
        if (nested && depth === 0) break
        depth = Math.max(0, depth - 1)
        after(true)
      } else if ((c === '<' || c === '>') && d === '(') {
        cur.words.push(this.word())
      } else if (src.startsWith('<<<', this.i)) {
        this.i += 3
        this.blanks()
        const w = this.word()
        cur.words.push({ ...w, redirect: true })
        cur.bodies.push(w.live)
      } else if (src.startsWith('<<', this.i)) {
        this.i += 2
        const strip = src[this.i] === '-'
        if (strip) this.i++
        this.blanks()
        const w = this.word()
        heredocs.push({ simple: cur, delimiter: w.text, quoted: w.quoted, strip })
      } else if (c === '<' || c === '>' || c === '&') {
        this.i += 1
        while (this.i < src.length && '<>&|'.includes(src[this.i]!) && src[this.i + 1] !== '(') this.i++
        this.blanks()
        if (this.i < src.length && !ENDS_WORD.has(src[this.i]!)) cur.words.push({ ...this.word(), redirect: true })
      } else {
        cur.words.push(this.word())
      }
    }
    // Heredocs never closed by a newline (the command's last line) have no body.
    this.pipe = saved
  }

  private blanks() {
    while (this.i < this.src.length && BLANK.has(this.src[this.i]!)) this.i++
  }

  /** The inside of `$(`, `<(`, `>(`: lexed as commands of their own, its backticks no word's here. */
  private substitution() {
    this.script(true)
  }

  /** A backtick span from the opening backtick at `i`: its text, to the matching unescaped backtick or the end. */
  private backtick(): string {
    const src = this.src
    const start = ++this.i
    while (this.i < src.length && src[this.i] !== '`') this.i += src[this.i] === '\\' ? 2 : 1
    const span = src.slice(start, Math.min(this.i, src.length))
    this.i = Math.min(this.i + 1, src.length)
    return span
  }

  /** A live backtick span at `i`, consumed; the word keeps the first. */
  private live(w: Word) {
    const span = this.backtick()
    w.live ??= span
  }

  /** `${…}`, from after its `{`: to the matching `}`, quotes and substitutions read; a backtick in it is live. */
  private parameter(w: Word) {
    const src = this.src
    let depth = 1
    while (this.i < src.length) {
      const c = src[this.i]!
      if (c === '\\') this.i += 2
      else if (c === "'") this.single()
      else if (c === '"') this.double(w)
      else if (c === '`') this.live(w)
      else if (c === '$' && src[this.i + 1] === '(') {
        this.i += 2
        this.substitution()
      } else {
        this.i++
        if (c === '{') depth++
        else if (c === '}' && --depth === 0) return
      }
    }
  }

  private single(): string {
    const end = this.src.indexOf("'", this.i + 1)
    const text = this.src.slice(this.i + 1, end < 0 ? undefined : end)
    this.i = end < 0 ? this.src.length : end + 1
    return text
  }

  /** `$'…'`, from its `$`: backslash escapes, nothing live. */
  private ansi() {
    const src = this.src
    this.i += 2
    while (this.i < src.length && src[this.i] !== "'") this.i += src[this.i] === '\\' ? 2 : 1
    this.i = Math.min(this.i + 1, src.length)
  }

  /** A `$` expansion at `i`, read into `w` as NUL. */
  private dollar(w: Word) {
    const d = this.src[this.i + 1]
    w.text += '\0'
    w.pure = false
    if (d === '(') {
      this.i += 2
      this.substitution()
    } else if (d === '{') {
      this.i += 2
      this.parameter(w)
    } else if (d === "'") {
      this.ansi()
    } else {
      this.i++
    }
  }

  /** A double-quoted string from its opening quote. */
  private double(w: Word) {
    const src = this.src
    this.i++
    while (this.i < src.length) {
      const c = src[this.i]!
      if (c === '"') {
        this.i++
        return
      }
      if (c === '\\') {
        w.text += src[this.i + 1] === '\n' ? '' : src[this.i + 1] ?? ''
        this.i += 2
      } else if (c === '`') {
        this.live(w)
        w.text += '\0'
        w.pure = false
      } else if (c === '$') {
        this.dollar(w)
      } else {
        w.text += c
        this.i++
      }
    }
  }

  /** One word from `i`, to the first blank or operator outside quotes. */
  private word(): Word {
    const src = this.src
    const w: Word = { text: '', pure: true, quoted: false }
    while (this.i < src.length) {
      const c = src[this.i]!
      const d = src[this.i + 1]
      if ((c === '<' || c === '>') && d === '(') {
        this.i += 2
        this.substitution()
        w.text += '\0'
        w.pure = false
      } else if (ENDS_WORD.has(c)) {
        break
      } else if (c === '\\') {
        w.quoted = true
        if (d !== '\n') w.text += d ?? ''
        this.i += 2
      } else if (c === "'") {
        w.quoted = true
        w.text += this.single()
      } else if (c === '"') {
        w.quoted = true
        this.double(w)
      } else if (c === '`') {
        this.live(w)
        w.text += '\0'
        w.pure = false
      } else if (c === '$' && d === '"') {
        w.quoted = true
        this.i++
        this.double(w)
      } else if (c === '$') {
        this.dollar(w)
      } else {
        if (c === '*' || c === '?' || c === '[') w.pure = false
        w.text += c
        this.i++
      }
    }
    return w
  }

  /** A heredoc's body from `i` to its delimiter line, consumed: the first live span in it, unless its delimiter was quoted. */
  private heredoc(delimiter: string, quoted: boolean, strip: boolean): string | undefined {
    const src = this.src
    const start = this.i
    let end = src.length
    while (this.i < src.length) {
      const nl = src.indexOf('\n', this.i)
      const line = src.slice(this.i, nl < 0 ? undefined : nl)
      if ((strip ? line.replace(/^\t+/, '') : line) === delimiter) {
        end = this.i
        this.i = nl < 0 ? src.length : nl + 1
        break
      }
      this.i = nl < 0 ? src.length : nl + 1
    }
    if (quoted) return undefined
    // The body as a double-quoted string reads it, but for its quotes, which are text here.
    const resume = this.i
    let live: string | undefined
    this.i = start
    while (this.i < end && live === undefined) {
      const c = src[this.i]!
      if (c === '\\') this.i += 2
      else if (c === '`') live = this.backtick()
      else if (c === '$' && src[this.i + 1] === '(') {
        this.i += 2
        this.substitution()
      } else this.i++
    }
    this.i = resume
    return live
  }
}

/** Whether a word names the sminos CLI: its last path part, all of it literal. */
const isSminos = (w: Word) => {
  const name = w.text.slice(w.text.lastIndexOf('/') + 1)
  return name === 'sminos' || name === 'sminos.py'
}

/**
 * The first live backtick span a sminos call in `command` would hand the
 * shell, or undefined when there is none.
 */
export function liveBacktick(command: string): string | undefined {
  // A call names sminos in a word, so a command without the name is no call: most are never lexed.
  if (!command.includes('sminos')) return undefined
  const lexer = new Lexer(command)
  lexer.script(false)
  const commands = lexer.commands
  for (const [k, s] of commands.entries()) {
    const args = s.words.filter((w) => !w.redirect)
    const head = args.findIndex((w) => !NAME_ASSIGNMENT.test(w.text))
    const at = args.findIndex((w, j) => isSminos(w) && (j === head || (args[j + 1]?.pure === true && VERBS.has(args[j + 1]!.text))))
    if (at < 0) continue
    const own = s.words.slice(s.words.indexOf(args[at]!) + 1)
    const fed = commands.slice(0, k).filter((u) => u.pipe === s.pipe)
    const live = [...own.map((w) => w.live), ...s.bodies, ...fed.flatMap((u) => u.bodies)].find((span) => span !== undefined)
    if (live !== undefined) return live
  }
  return undefined
}

/** What a refused call reads: what the shell would have done, and the form that carries the text as written. */
export function refusal(span: string): string {
  const shown = span.replace(/\s+/g, ' ').trim()
  const command = shown.length > 80 ? `${shown.slice(0, 77)}...` : shown
  return [
    `sminos: this command was not run. A backtick in the sminos call's text is live: the shell would have run \`${command}\` as a command on this machine before sminos saw it, and sent its output, or nothing, in place of that text.`,
    'Give text that holds backticks, quotes, $ or several lines on standard input, as -, from a heredoc whose delimiter is quoted; the shell passes it as written:',
    '',
    "  sminos say - <<'EOF'",
    '  @alias the fix is in `parse()`',
    '  EOF',
    '',
    'send, spawn, steer, resume, fill and compact take - in the same place. If the substitution was meant, write it $(...).',
  ].join('\n')
}

export function registerBackticks(on: On) {
  // No `.catch`: a guard that fails is skipped and the call runs (fails open).
  on('tool.call', { tool: 'Bash' }, async (_$, e, next) => {
    const span = typeof e.command === 'string' ? liveBacktick(e.command) : undefined
    return span === undefined ? next(e) : { deny: refusal(span) }
  })
}
