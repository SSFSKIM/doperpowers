import { describe, expect, test, tier } from 'claude-code/testing'

import { simpleCommands } from '../../hooks/mods/backticks'
import { attribute, notification, reducedName, statusOf, taskBandLine } from '../../hooks/mods/tasks-model'

tier('user')

// Every id, name and text here is invented.
const ID = 'a1b2c3d4e5f60718'
const FLAG = `--asker-agent ${ID} --asker-name reviewer`

describe('the lexer keeps where a literal word stands', () => {
  const spans = (command: string) =>
    simpleCommands(command)?.map((c) => c.words.map((w) => (w.span === undefined ? null : command.slice(w.span[0], w.span[1]))))

  test('a literal word, in the outer command and in a list, is its own bytes', () => {
    expect(spans('task assign-human --title x')).toEqual([['task', 'assign-human', '--title', 'x']])
    expect(spans('a && task assign-human; b')).toEqual([['a'], ['task', 'assign-human'], ['b']])
  })

  test('a word with a quote, an escape, an expansion or a continuation in it has no place', () => {
    expect(spans(`task "assign"-human 'x' a\\b $V\nc\\\nd`)).toEqual([['task', null, null, null, null], [null]])
  })

  test('nothing inside a substitution or a heredoc body has a place', () => {
    expect(spans('x $(task assign-human) y')).toEqual([['x', null, 'y'], [null, null]])
    const heredoc = spans('cat <<EOF\n$(task assign-human)\nEOF\nz')
    expect(heredoc?.flat().filter((w) => w !== null)).toEqual(['cat', 'z'])
  })

  test('a command the lexer gives up on gives no commands', () => {
    expect(simpleCommands('x $(case a in a) b;; esac)')).toBeUndefined()
    expect(simpleCommands('x'.repeat(100), 10)).toBeUndefined()
    expect(simpleCommands('x'.repeat(100))).toBeDefined()
  })
})

describe('attribute', () => {
  const changed: [string, string, string][] = [
    ['a plain call', 'task assign-human --class blocking --title "Log in"', `task assign-human ${FLAG} --class blocking --title "Log in"`],
    [
      'one with a heredoc body',
      "task assign-human --class needed --title T --body-file - <<'EOF'\nOpen the console.\nEOF",
      `task assign-human ${FLAG} --class needed --title T --body-file - <<'EOF'\nOpen the console.\nEOF`,
    ],
    ['one in a list', 'cd w && task assign-human --title T && echo ok', `cd w && task assign-human ${FLAG} --title T && echo ok`],
    [
      'two assigns in one command',
      'task assign-human --title A; sminos task assign --title B',
      `task assign-human ${FLAG} --title A; sminos task assign ${FLAG} --title B`,
    ],
    [
      "the verb's text repeated inside a quoted argument",
      'task assign-human --title "task assign-human"',
      `task assign-human ${FLAG} --title "task assign-human"`,
    ],
    ['a trailing comment', 'task assign-human --title T # task assign-human', `task assign-human ${FLAG} --title T # task assign-human`],
    ['a path-qualified task', '~/.local/bin/task assign-human --title T', `~/.local/bin/task assign-human ${FLAG} --title T`],
    ['sminos by its script', 'python3 x; /p/sminos.py task assign --title T', `python3 x; /p/sminos.py task assign ${FLAG} --title T`],
    ['under time, and after an assignment', 'time X=1 task assign-human --title T', `time X=1 task assign-human ${FLAG} --title T`],
    ['in an if', 'if task assign-human --title T; then echo ok; fi', `if task assign-human ${FLAG} --title T; then echo ok; fi`],
    ['a redirect before the verb', 'task >/dev/null assign-human --title T', `task >/dev/null assign-human ${FLAG} --title T`],
  ]
  for (const [what, command, expected] of changed) {
    test(`${what}: the flag after the verb`, () => {
      expect(attribute(command, ID, 'reviewer')).toBe(expected)
    })
  }

  const unchanged: [string, string][] = [
    ["a quoted `task assign-human` inside an echo", 'echo "task assign-human --title T"'],
    ['a verb split by a quote', 'task assign-"human" --title T'],
    ['a verb split by a continuation', 'task assign-\\\nhuman --title T'],
    ['a command inside $( … )', 'id=$(task assign-human --title T)'],
    ['a command in a heredoc body', 'cat <<EOF\n$(sminos task assign --title T)\nEOF'],
    ['a command that already carries the flag', `task assign-human --asker-agent other --title T`],
    ['one that carries it abbreviated', `sminos task assign --asker-ag=other --title T`],
    ['the verb behind another command', 'env task assign-human --title T'],
    ['another verb', 'task assign --title T; sminos task revise t1 --title T'],
    ['a command the lexer gives up on', 'task assign-human --title "$(case a in a) b;; esac)"'],
    ['no assign at all', 'ls -la'],
  ]
  for (const [what, command] of unchanged) {
    test(`${what}: unchanged`, () => {
      expect(attribute(command, ID, 'reviewer')).toBeUndefined()
    })
  }

  test("a teammate's id, and no name: the id alone", () => {
    expect(attribute('task assign-human --title T', 'fixer@team-1', undefined)).toBe('task assign-human --asker-agent fixer@team-1 --title T')
  })

  test('an id that fails the pattern, or reads as an option: unchanged', () => {
    for (const id of ['', 'a b', 'a;rm', 'x'.repeat(129), '-a', 'a\n']) {
      expect(attribute('task assign-human --title T', id, 'reviewer')).toBeUndefined()
    }
  })

  test('a name with spaces and quotes is reduced', () => {
    expect(attribute('task assign-human --title T', ID, `Fix "the" bug's tests`)).toBe(`task assign-human --asker-agent ${ID} --asker-name Fix-the-bug-s-tests --title T`)
  })
})

describe('reducedName', () => {
  test('any other run a dash, none at either end, at most 64, left out when nothing remains', () => {
    expect(reducedName('Review the diff (M4)')).toBe('Review-the-diff-M4')
    expect(reducedName('--help')).toBe('help')
    expect(reducedName('x'.repeat(80))).toBe('x'.repeat(64))
    expect(reducedName('日本語')).toBeUndefined()
    expect(reducedName('')).toBeUndefined()
    expect(reducedName(undefined)).toBeUndefined()
  })
})

describe('statusOf', () => {
  const status = { v: 1, seq: 14, open: { count: 2, blocking: 1 }, mine: [{ id: 't7', title: 'Log in', born: 9 }], board: { url: 'http://x' } }

  test("the command's answer", () => {
    expect(statusOf(`${JSON.stringify(status)}\n`)).toEqual({ seq: 14, open: { count: 2, blocking: 1 }, mine: [{ id: 't7', title: 'Log in', born: 9 }], board: { url: 'http://x' } })
    expect(statusOf(JSON.stringify({ ...status, board: null }))?.board).toBeNull()
  })

  test('anything else is no answer', () => {
    for (const bad of ['', 'nope', '[]', JSON.stringify({ ...status, v: 2 }), JSON.stringify({ ...status, seq: -1 }), JSON.stringify({ ...status, open: { count: 1 } }),
      JSON.stringify({ ...status, mine: [{ id: '7', title: 'x', born: 1 }] }), JSON.stringify({ ...status, mine: [{ id: 't7', born: 1 }] }), JSON.stringify({ ...status, board: { url: 3 } })]) {
      expect(statusOf(bad)).toBeUndefined()
    }
  })
})

describe('taskBandLine', () => {
  test('none, open, blocking, and with a board', () => {
    expect(taskBandLine({ count: 0, blocking: 0 }, null)).toBeUndefined()
    expect(taskBandLine({ count: 1, blocking: 0 }, null)).toBe('1 task for the human · sminos task list')
    expect(taskBandLine({ count: 2, blocking: 1 }, null)).toBe('2 tasks for the human (1 blocking) · sminos task list')
    expect(taskBandLine({ count: 2, blocking: 1 }, { url: 'http://tasks.localhost:47590/board' })).toBe('2 tasks for the human (1 blocking) · http://tasks.localhost:47590/board')
  })

  test("a board's address is drawn on one line", () => {
    expect(taskBandLine({ count: 1, blocking: 1 }, { url: 'http://x/\n\u001b[2Jy' })).toBe('1 task for the human (1 blocking) · http://x/ [2Jy')
  })
})

describe('notification', () => {
  test("a blocking task's title, on one line", () => {
    expect(notification('Log in to the console')).toBe('A blocking task for you: Log in to the console')
    expect(notification('a\tb\u0007')).toBe('A blocking task for you: a b')
  })
})
