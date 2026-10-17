/**
 * Which handles go back into a Bash command as their bytes. Only what can be
 * shown safe (Decision Log, 2026-10-17): an inert value, standing in a plain
 * string or a plain word, in a command free of the constructs that read words
 * again. Nothing is ever quoted: a value that would need quoting is not
 * restored, and the result says how to read it in the command instead. Pure;
 * proved by executing restored commands under bash and zsh
 * (tests/mods/shell-exec.ts).
 */

/**
 * Inert: non-empty, of letters, digits and `_ . / + : @ -` (no expansion,
 * glob, comment, history, tilde, brace or extended-glob meaning in either
 * shell), with `=` and `%` past the first character (zsh expands a leading
 * `=cmd`; a leading `%` names a job). An `=` right after `=` or `:` starts an
 * `=cmd` expansion under zsh's MAGIC_EQUAL_SUBST, so it may only be part of a
 * trailing run of `=` and `:` (base64 padding), which zsh leaves alone.
 */
const ALPHABET = /^[A-Za-z0-9_./+:@-][A-Za-z0-9_./+:@=%-]*$/
const EQUALS_INSIDE = /[=:]=+(?=.*[^=:])/

export const isInert = (value: string) => ALPHABET.test(value) && !EQUALS_INSIDE.test(value)

// What reads a word again: heredocs and here-strings, backticks, arithmetic
// (`((`, `$[`, `[[`, `let`, `integer`, `float`), parameter expansion (`${`),
// any declaration with a flag (integer, float, nameref), line continuations.
const REREADS =
  /<<|`|\(\(|\$\[|\$\{|\[\[|\\\n|(?:^|[\s;&|(])(?:let|integer|float)\s|(?:^|[\s;&|(])(?:declare|typeset|local|export|readonly)\s+-/
// A comment: `#` where a word starts.
const COMMENT = /(?:^|[\s;&|()])#/

/** Whether the command holds none of the constructs that read a word again. */
export const isPlainCommand = (command: string) => !REREADS.test(command) && !COMMENT.test(command)

// Where words end, outside quotes.
const OPERATOR = /[\s;|&()<>]/
// What else a plain word may hold beside the handle (the inert alphabet).
const PLAIN_WORD = /^[A-Za-z0-9_./+:@=%-]*$/

/**
 * Whether a handle at `at` (`length` long), whose value is `value`, stands in
 * a plain string or word, so that its bytes, put there as they are, reach the
 * command unchanged: inside a `'…'` string; inside a `"…"` string that holds
 * no `$`, backtick, `\` or `!` besides; or in an unquoted word (between
 * whitespace and `; | & ( ) < >`) of the inert alphabet throughout, which,
 * restored, is inert as a whole (no leading `=` or `%`, no `==` or `:=`), and
 * which neither follows a redirection nor touches a `(` that opens a glob,
 * a qualifier or a function.
 */
export function isPlainPosition(command: string, at: number, length: number, value: string): boolean {
  // Which quoted string, if any, holds the handle.
  for (let i = 0; i < command.length; ) {
    const c = command[i]!
    if (c === '\\') {
      i += 2
      continue
    }
    if (c === "'" || c === '"') {
      let end = i + 1
      while (end < command.length && command[end] !== c) end += c === '"' && command[end] === '\\' ? 2 : 1
      if (end >= command.length) return false
      if (at > i && at + length <= end) {
        if (c === "'") return true
        const rest = command.slice(i + 1, at) + command.slice(at + length, end)
        return !/[$`\\!]/.test(rest)
      }
      if (at < end && at + length > i) return false
      i = end + 1
      continue
    }
    if (i >= at + length) break
    i++
  }
  // An unquoted word: from the operator before to the operator after.
  let start = at
  while (start > 0 && !OPERATOR.test(command[start - 1]!)) start--
  let end = at + length
  while (end < command.length && !OPERATOR.test(command[end]!)) end++
  const before = command.slice(start, at)
  const after = command.slice(at + length, end)
  if (!PLAIN_WORD.test(before) || !PLAIN_WORD.test(after) || !isInert(before + value + after)) return false
  // Not the target of a redirection (`>`, `<`, `>&`, `<&`, `&>`, `>|`).
  if (/[<>]\s*[&|]?\s*$/.test(command.slice(0, start))) return false
  // Not touching a `(` but one that opens a subshell or a substitution.
  if (command[end] === '(') return false
  if (command[start - 1] === '(' && !/(?:^|[\s;&|($=])$/.test(command.slice(0, start - 1))) return false
  return true
}
