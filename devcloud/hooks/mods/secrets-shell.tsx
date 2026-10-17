/**
 * Which handles go back into a Bash command as their bytes. Only what can be
 * shown safe (Decision Log, 2026-10-17): an inert value, at a plain position,
 * in a command free of the constructs that read words again. Nothing is ever
 * quoted: a value that would need quoting is not restored, and the result says
 * how to read it in the command instead. Pure; proved by executing restored
 * commands under bash and zsh (tests/mods/shell-exec.ts).
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
// (`((`, `$[`, `let`, `[[`, an integer declaration), line continuations.
const REREADS = /<<|`|\(\(|\$\[|\[\[|\\\n|(?:^|[\s;&|(])(?:let|integer)\s|(?:^|[\s;&|(])(?:declare|typeset|local|export|readonly)\s+(?:-\w*\s+)*-\w*i/
// A comment: `#` where a word starts.
const COMMENT = /(?:^|[\s;&|()])#/

// What may stand right before and right after a handle.
const BEFORE = /[\s'"=:/,@.\-+_A-Za-z0-9]/
const AFTER = /[\s'";|&)/:,.\-=@A-Za-z0-9]/
// Where a word ends, for a value whose last character is `=` or `:`.
const WORD_END = /[\s'";|&)]/

/** Whether the command holds none of the constructs that read a word again. */
export const isPlainCommand = (command: string) => !REREADS.test(command) && !COMMENT.test(command)

/** Whether the value an inert handle at `at` (`length` long) stands for may go in as it is. */
export function isPlainPosition(command: string, at: number, length: number, value: string): boolean {
  const before = command.slice(Math.max(0, at - 256), at)
  if (before !== '' && !BEFORE.test(before[before.length - 1]!)) return false
  // Never after `$` or a `$name` (the bytes would extend it), nor after an `=`
  // that follows `=` or `:` (zsh's `=cmd`).
  if (/\$(?:[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-]?)$/.test(before) || /[=:]=$/.test(before)) return false
  const after = command[at + length]
  if (after !== undefined && !AFTER.test(after)) return false
  if (/[=:]$/.test(value) && after !== undefined && !WORD_END.test(after)) return false
  return true
}
