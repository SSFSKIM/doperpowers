/**
 * Restoring a value into a shell command, by a rule that is safe by
 * construction (Decision Log, 2026-10-17): an inert value goes in as it is,
 * anywhere; any other value goes in only where the command's quoting can be
 * proved — a plain single-quoted string, a plain double-quoted string or an
 * unquoted word, in a command with none of the forms whose reading is hard to
 * prove — quoted for that one context. Everywhere else the handle stays. Pure.
 */

/**
 * Characters neither bash nor zsh treats specially in any context: letters,
 * digits, `_` `.` `/` `+` `:` `@` `-` (no expansion, glob, comment, history,
 * tilde, brace or extended-glob meaning in either shell), and `=` and `%` past
 * the first character (zsh expands a leading `=cmd`; a leading `%` names a job
 * in command position). Excluded: whitespace, quotes, `\`, `$`, backtick, `;`
 * `&` `|` `<` `>` `(` `)`, glob `* ? [ ]`, brace `{ } ,`, `~`, `!`, `#`, `^`.
 */
const INERT = /^[A-Za-z0-9_./+:@-][A-Za-z0-9_./+:@=%-]*$/

/** Whether `value` reaches either shell as its own bytes wherever it is written. */
export const isInert = (value: string) => INERT.test(value)

export type ShellContext = 'single' | 'double' | 'none'

// The forms whose reading the guard does not prove: command and parameter
// substitution, backticks, ANSI-C and locale quoting, heredocs and
// here-strings, line continuations.
const UNPROVED = /`|<<|\$[('"{]|\\\n/

/**
 * The quoting context of each position of `command` — inside a plain
 * single-quoted string, a plain double-quoted string, or an unquoted word —
 * or undefined when the command holds a form the guard does not read (a
 * comment included).
 */
export function shellContexts(command: string): ShellContext[] | undefined {
  if (UNPROVED.test(command)) return undefined
  const ctx = new Array<ShellContext>(command.length).fill('none')
  for (let i = 0; i < command.length; ) {
    const c = command[i]!
    if (c === "'") {
      const end = command.indexOf("'", i + 1)
      if (end === -1) return undefined
      ctx.fill('single', i, end + 1)
      i = end + 1
    } else if (c === '"') {
      let j = i + 1
      while (j < command.length && command[j] !== '"') j += command[j] === '\\' ? 2 : 1
      if (j >= command.length) return undefined
      ctx.fill('double', i, j + 1)
      i = j + 1
    } else if (c === '\\') {
      i += 2
    } else if (c === '#' && (i === 0 || /[\s;&|()]/.test(command[i - 1]!))) {
      return undefined
    } else i++
  }
  return ctx
}

/**
 * `value` written for `context`, or undefined where even that is not proved:
 * in double quotes a `!` is left out (history expansion in an interactive
 * shell).
 */
export function quoteFor(context: ShellContext, value: string): string | undefined {
  switch (context) {
    case 'single':
      return value.replace(/'/g, `'\\''`)
    case 'double':
      return value.includes('!') ? undefined : value.replace(/[$`"\\]/g, '\\$&')
    case 'none':
      return `'${value.replace(/'/g, `'\\''`)}'`
  }
}

/** Whether the handle at `at` directly follows `$` or a `$name`, so its bytes would extend an expansion. */
export const followsExpansion = (command: string, at: number) => /\$(?:[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-]?)$/.test(command.slice(Math.max(0, at - 256), at))
