/**
 * Restoring a value into a shell command so the shell receives its exact
 * bytes: what quoting context each position of a command sits in, and how a
 * value is written there. Pure. A value of characters no context treats
 * specially (most tokens) is written as it is, in every context.
 */

export type ShellContext = 'none' | 'single' | 'double' | 'ansi' | 'heredoc' | 'heredoc-raw' | 'comment'

type Frame = { kind: 'none' | 'subst' | 'backtick' | 'double'; depth: number }

/**
 * The quoting context of each position of `command`: unquoted (`none`, inside
 * `$(…)` and backticks too), single-quoted, double-quoted, `$'…'`, a heredoc
 * body (`heredoc-raw` when its delimiter was quoted), or a comment.
 */
export function shellContexts(command: string): ShellContext[] {
  const n = command.length
  const ctx: ShellContext[] = new Array<ShellContext>(n).fill('none')
  const stack: Frame[] = [{ kind: 'none', depth: 0 }]
  const heredocs: { delim: string; isRaw: boolean; strip: boolean }[] = []
  const mark = (from: number, to: number, c: ShellContext) => {
    for (let k = from; k < to && k < n; k++) ctx[k] = c
  }
  let i = 0
  while (i < n) {
    const top = stack[stack.length - 1]!
    const c = command[i]!
    if (top.kind === 'double') {
      ctx[i] = 'double'
      if (c === '\\') mark(i, i + 2, 'double'), (i += 2)
      else if (c === '"') stack.pop(), i++
      else if (c === '$' && command[i + 1] === '(') mark(i, i + 2, 'double'), stack.push({ kind: 'subst', depth: 0 }), (i += 2)
      else if (c === '`') stack.push({ kind: 'backtick', depth: 0 }), i++
      else i++
      continue
    }
    if (c === '\\') {
      i += 2
    } else if (c === "'") {
      const end = command.indexOf("'", i + 1)
      const stop = end === -1 ? n : end + 1
      mark(i, stop, 'single')
      i = stop
    } else if (c === '$' && command[i + 1] === "'") {
      let j = i + 2
      while (j < n && command[j] !== "'") j += command[j] === '\\' ? 2 : 1
      mark(i, j + 1, 'ansi')
      i = j + 1
    } else if (c === '"') {
      ctx[i] = 'double'
      stack.push({ kind: 'double', depth: 0 })
      i++
    } else if (c === '$' && command[i + 1] === '(') {
      stack.push({ kind: 'subst', depth: 0 })
      i += 2
    } else if (c === '(' && top.kind === 'subst') {
      top.depth++
      i++
    } else if (c === ')' && top.kind === 'subst') {
      if (top.depth === 0) stack.pop()
      else top.depth--
      i++
    } else if (c === '`') {
      if (top.kind === 'backtick') stack.pop()
      else stack.push({ kind: 'backtick', depth: 0 })
      i++
    } else if (c === '#' && (i === 0 || /[\s;&|(]/.test(command[i - 1]!))) {
      const end = command.indexOf('\n', i)
      const stop = end === -1 ? n : end
      mark(i, stop, 'comment')
      i = stop
    } else if (c === '<' && command[i + 1] === '<' && command[i + 2] !== '<') {
      const m = /^<<(-?)[ \t]*(['"]?)([A-Za-z0-9_.-]+)\2/.exec(command.slice(i))
      if (m) {
        heredocs.push({ delim: m[3]!, isRaw: m[2] !== '', strip: m[1] === '-' })
        i += m[0].length
      } else i += 2
    } else if (c === '\n' && heredocs.length > 0) {
      i++
      for (const { delim, isRaw, strip } of heredocs.splice(0)) {
        while (i < n) {
          const end = command.indexOf('\n', i)
          const stop = end === -1 ? n : end
          const line = command.slice(i, stop)
          if ((strip ? line.replace(/^\t+/, '') : line) === delim) {
            i = stop + 1
            break
          }
          mark(i, stop, isRaw ? 'heredoc-raw' : 'heredoc')
          i = stop + 1
        }
      }
    } else i++
  }
  return ctx
}

// Characters no context treats specially: such a value is written as it is.
const PLAIN = /^[A-Za-z0-9_@%+=:,./-]*$/

/** `value` written where context `context` reads it, so the shell receives exactly its bytes. */
export function quoteFor(context: ShellContext, value: string): string {
  if (PLAIN.test(value)) return value
  switch (context) {
    case 'none':
      return `'${value.replace(/'/g, `'\\''`)}'`
    case 'single':
      return value.replace(/'/g, `'\\''`)
    case 'double':
      return value.replace(/[$`"\\]/g, '\\$&')
    case 'ansi':
      return value.replace(/[\\']/g, '\\$&')
    case 'heredoc':
      return value.replace(/[$`\\]/g, '\\$&')
    case 'heredoc-raw':
    case 'comment':
      return value
  }
}
