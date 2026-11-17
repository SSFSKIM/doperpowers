import { describe, expect, test, tier } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import { STEPS_FLOOR, liveBacktick, refusal, registerBackticks } from '../../hooks/mods/backticks'

tier('user')

// Every text here is invented: the shapes are those a scan of real calls found.
const B = '`'

/** Commands the guard refuses, each with the backtick span the shell would have run. */
const REFUSED: [string, string, string][] = [
  ['a double-quoted body', `sminos say "@peer the fix is in ${B}parse()${B}"`, 'parse()'],
  ['a bare word', `sminos say @peer ${B}ls${B}`, 'ls'],
  ['a send', `sminos send peer "run ${B}make check${B} first"`, 'make check'],
  ['a spawn task', `sminos spawn helper "read ${B}notes.md${B}" --brief "owns notes"`, 'notes.md'],
  ['a steer', `sminos steer peer "stop at ${B}main${B}"`, 'main'],
  ['an option value', `sminos spawn helper "x" --brief "owns ${B}docs/${B}"`, 'docs/'],
  ['the absolute path', `/home/u/.claude/plugins/cache/m/sminos/1.0.0/skills/sminos/scripts/sminos say "${B}rm -rf x${B}"`, 'rm -rf x'],
  ['a path with a parameter in it', `"$HOME/plugins/sminos/scripts/sminos" say "${B}date${B}"`, 'date'],
  ['the python script', `python3 /x/sminos.py say "${B}date${B}"`, 'date'],
  ['after an assignment', `SMINOS_HOME=/tmp/s sminos say "${B}date${B}"`, 'date'],
  ['the second command of a list', `cd /work && sminos say "@all see ${B}git log${B}"`, 'git log'],
  ['after a pipe', `true | sminos say "${B}x${B}"`, 'x'],
  ['inside a loop', `for p in a b; do sminos say "@$p see ${B}y${B}"; done`, 'y'],
  ['reached through another command', `devcloud vm ssh box -- sminos say "stop with ${B}svc stop${B} over ssh"`, 'svc stop'],
  ['through env', `env -i sminos say "${B}id${B}"`, 'id'],
  ['inside a $( )', `x=$(sminos say "${B}id${B}")`, 'id'],
  ['an unquoted heredoc feeding it', `sminos say - <<EOF\nthe fix is in ${B}parse()${B}\nEOF`, 'parse()'],
  ['a heredoc with <<-', `sminos say - <<-EOF\n\tsee ${B}a${B}\n\tEOF`, 'a'],
  ['a heredoc piped into it', `cat <<EOF | sminos say -\nsee ${B}b${B}\nEOF`, 'b'],
  ['a here-string', `sminos say - <<< "see ${B}c${B}"`, 'c'],
  ['an unclosed backtick: the span runs to the end', `sminos say "it is ${B}open"`, 'open"'],
  ['a multi-line body', `sminos say "line one\nline ${B}two${B}"`, 'two'],
  ['a second call after a clean one', `sminos list; sminos say "${B}w${B}"`, 'w'],
  ['a backtick in a ${...} default', `sminos say "\${X:-${B}id${B}}"`, 'id'],
  ['a call after a heredoc whose delimiter is a literal $WORD', `sminos say - <<$END\nfine\n$END\nsminos say "${B}w${B}"`, 'w'],
  ['a call after a heredoc whose terminator is joined at a backslash-newline', `sminos say - <<EOF\nfine\nE\\\nOF\nsminos say "${B}j${B}"`, 'j'],
  ['an unquoted body with a backslash-newline before its terminator', `sminos say - <<EOF\nsee ${B}k${B}\\\nEOF\nEOF`, 'k'],
]

/** Commands the guard lets run. */
const ALLOWED: [string, string][] = [
  ['single quotes', `sminos say '@peer the fix is in ${B}parse()${B}'`],
  ['escaped in double quotes', `sminos say "@peer the fix is in \\${B}parse()\\${B}"`],
  ['escaped bare', `sminos say @peer \\${B}x\\${B}`],
  ['an ANSI-C string', `sminos say $'see ${B}x${B}\\n'`],
  ['a quoted-delimiter heredoc', `sminos say - <<'EOF'\nthe fix is in ${B}parse()${B}, it's "done"\nEOF`],
  ['a double-quoted delimiter', `sminos send peer - <<"EOF"\n${B}x${B}\nEOF`],
  ['an escaped delimiter', `sminos say - <<\\EOF\n${B}x${B}\nEOF`],
  ['an escaped backtick in an unquoted heredoc', `sminos say - <<EOF\nsee \\${B}x\\${B}\nEOF`],
  ['$( ) interpolation', `sminos say "@peer at $(git rev-parse --short HEAD)"`],
  ['$(cat file)', `sminos say "$(cat /tmp/msg.txt)"`],
  ['a backtick inside a $( )', `sminos say "$(printf '%s' ${B}date${B})"`],
  ['a $(cat heredoc) with a quoted delimiter', `sminos say "$(cat <<'EOF'\nsee ${B}x${B} and it's fine\nEOF\n)"`],
  ['no backtick', `sminos say "@peer merged #12"`],
  ['a comment', `sminos say "done" # see ${B}x${B}`],
  ['another command of the list', `sminos list && echo "${B}date${B}"`],
  ['a backtick before the call', `echo "${B}date${B}"; sminos list`],
  ['a command the call pipes into', `sminos list | grep "${B}x${B}"`],
  ['an upstream argument', `printf '%s' "${B}x${B}" | sminos say -`],
  ['sminos inside another command\'s string', `git commit -m "teach sminos say with ${B}code${B}"`],
  ['sminos inside another command\'s heredoc', `cat > doc.md <<EOF\nrun sminos say "${B}x${B}"\nEOF`],
  ['sminos as an argument that is no call', `grep -rn sminos ${B}git ls-files${B}`],
  ['a word that only ends in sminos', `ls ./notsminos ${B}x${B}`],
  ['sminos in a quoted heredoc of another command', `cat <<'EOF'\nsminos say "${B}x${B}"\nEOF`],
  ['a heredoc of another command in the list', `sminos list; cat <<EOF\n${B}x${B}\nEOF`],
  ['a $\'…\' heredoc delimiter: the body is literal', `sminos say - <<$'EOF'\nsee ${B}x${B}\nEOF`],
  ['a command after a heredoc whose delimiter is a literal $WORD', `sminos say - <<$END\nfine\n$END\nprintf '%s' "${B}x${B}"`],
  ['a command after a heredoc whose terminator is joined at a backslash-newline', `sminos say - <<EOF\nfine\nE\\\nOF\nprintf '%s' "${B}x${B}"`],
  ['a quoted body: a backslash-newline joins nothing', `sminos say - <<'EOF'\nsee ${B}x${B}\\\nEOF\nEOF`],
  ['$\'…\' inside double quotes is a literal $', `sminos say "$'"; printf '%s\\n' '${B}x${B}'`],
  ['$"…" inside double quotes is a literal $', `sminos say "a$"; printf '%s' '${B}x${B}'`],
  ['not modelled, so not judged: a case inside $( )', `sminos say "$(case x in x) printf '%s' '${B}printf BAD${B}';; esac)"`],
  ['not modelled, so not judged: a $"…" heredoc delimiter', `sminos say - <<$"EOF"\nsee ${B}x${B}\nEOF`],
  ['not judged: a $( that never closes', `sminos say "$(echo ${B}x${B}"`],
  ['not judged: a $( in a heredoc body that never closes there', `sminos say - <<EOF\nsee $(\nEOF\nsminos say "${B}x${B}"`],
  ['a call with no arguments', 'sminos'],
  ['an empty command', ''],
]

describe('liveBacktick: the shell lexed', () => {
  for (const [name, command, span] of REFUSED) {
    test(`refused: ${name}`, () => {
      expect(liveBacktick(command)).toBe(span)
    })
  }
  for (const [name, command] of ALLOWED) {
    test(`allowed: ${name}`, () => {
      expect(liveBacktick(command)).toBeUndefined()
    })
  }
})

describe('the work bound', () => {
  test('a short malformed input that once made the lexer re-parse is given up quickly, and the call runs', () => {
    const command = 'sminos <<E\n$(\nE\n'.repeat(15)
    const started = performance.now()
    expect(liveBacktick(command)).toBeUndefined()
    expect(performance.now() - started).toBeLessThan(250)
  })

  test('a spent bound gives up, and the call runs', () => {
    const command = `sminos say "${B}x${B}"`
    expect(liveBacktick(command)).toBe('x')
    expect(liveBacktick(command, 3)).toBeUndefined()
  })

  test('nested heredocs and substitutions stay within the bound', () => {
    let command = `sminos say "${B}x${B}"`
    for (let n = 0; n < 40; n++) command = `sminos say - <<E${n}\n$(cat <<F${n}\n${command}\nF${n}\n)\nE${n}\n`
    const started = performance.now()
    liveBacktick(command)
    expect(performance.now() - started).toBeLessThan(250)
    expect(STEPS_FLOOR).toBeGreaterThan(0)
  })
})

describe('refusal', () => {
  test('says what the shell would have done, and the stdin form', () => {
    const text = refusal('docker desktop stop')
    expect(text).toContain('was not run')
    expect(text).toContain('would have run `docker desktop stop` as a command on this machine')
    expect(text).toContain("sminos say - <<'EOF'")
    expect(text).toContain('$(...)')
  })

  test('a long span is cut, its lines joined', () => {
    const text = refusal(`a\n${'b'.repeat(200)}`)
    expect(text).toContain('`a bbbb')
    expect(text).not.toContain('b'.repeat(100))
  })
})

describe('the hook', () => {
  type Handler = ($: EngineInterface, e: Record<string, unknown>, next: (e: Record<string, unknown>) => Promise<unknown>) => Promise<unknown>
  const hooks: { event: string; matcher: Record<string, unknown>; handler: Handler }[] = []
  const on = ((event: string, matcher: Record<string, unknown>, handler: Handler) => {
    hooks.push({ event, matcher, handler })
    return { catch: () => undefined }
  }) as unknown as On
  registerBackticks(on)

  const call = async (command: unknown) => {
    const ran: Record<string, unknown>[] = []
    const result = await hooks[0]!.handler({} as EngineInterface, { tool: 'Bash', tool_use_id: 'toolu_1', command }, async (e) => {
      ran.push(e)
      return { result: { stdout: 'ok' } }
    })
    return { result, ran }
  }

  test('it watches Bash alone', () => {
    expect(hooks.map((h) => [h.event, h.matcher])).toEqual([['tool.call', { tool: 'Bash' }]])
  })

  test('a live backtick in a sminos call is refused before it runs', async () => {
    const { result, ran } = await call(`sminos say "@peer see ${B}date${B}"`)
    expect(ran).toEqual([])
    expect(result).toEqual({ deny: refusal('date') })
  })

  test('any other command runs as it came', async () => {
    const { result, ran } = await call(`sminos say - <<'EOF'\n${B}date${B}\nEOF`)
    expect(ran).toEqual([{ tool: 'Bash', tool_use_id: 'toolu_1', command: `sminos say - <<'EOF'\n${B}date${B}\nEOF` }])
    expect(result).toEqual({ result: { stdout: 'ok' } })
  })

  test('a call with no command string runs', async () => {
    const { ran } = await call(undefined)
    expect(ran.length).toBe(1)
  })
})
