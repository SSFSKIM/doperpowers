#!/usr/bin/env bash
# The ask mod's search of a transcript too large to read whole, run for real:
# perl, and grep where perl does not start, with the arguments the mod builds
# (searchArgs, grepArgs), over a fixture transcript. What each finds must
# rebuild the asks a read of the whole file rebuilds, and the two must find
# the same lines. The mods' own tests cannot reach a process; bun runs the mod's
# pure functions directly.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cat > "$work/check.ts" <<TS
import { execFileSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { ASK_TOOL, ASYNC_RESULT, deliveryText, grepArgs, rebuildAsks, searchArgs } from '$root/hooks/mods/ask.tsx'

const answered = (q: string, a: string) => \`Your questions have been answered: "\${q}"="\${a}". You can now continue with these answers in mind.\`
const question = (q: string) => ({ question: q, header: 'H', multiSelect: false, options: [{ label: 'A', description: 'a' }, { label: 'B', description: 'b' }] })
const use = (id: string, q: string, name = ASK_TOOL) => ({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'tool_use', id, name, input: { questions: [question(q)], async: true } }] } })
// The tool and its delivery under the plugin the ask moves to: a transcript holds either.
const SMINOS_TOOL = 'mcp__sminos__AskUserQuestion'
const SMINOS_PROMPT = 'The sminos plugin sent a message:\\n'
const result = (id: string) => ({ type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: ASYNC_RESULT }] } })
const context = (hookName: string, content: string[]) => ({ type: 'attachment', attachment: { type: 'hook_additional_context', content, hookName } })
const rows = [
  use('t-first', 'Which backend?'), result('t-first'),
  use('t-tool', 'Which features?'), result('t-tool'),
  use('t-prompt', 'Which layout?'), result('t-prompt'),
  use('t-plugin', 'Which store?'), result('t-plugin'),
  use('t-open', 'Which port?'), result('t-open'),
  use('t-sminos', 'Which queue?', SMINOS_TOOL), result('t-sminos'),
  use('t-sminos-open', 'Which region?', SMINOS_TOOL), result('t-sminos-open'),
  // A delivery opening the context, and one behind another hook's context on each route.
  context('tool.call', [deliveryText('t-first', answered('Which backend?', 'A'))]),
  context('tool.call', ['other context, "quoted"\\\\', deliveryText('t-tool', answered('Which features?', 'B'))]),
  context('prompt.submit', ['other context', deliveryText('t-prompt', answered('Which layout?', 'A'))]),
  { type: 'user', message: { role: 'user', content: \`The doperpowers plugin sent a message:\n\${deliveryText('t-plugin', answered('Which store?', 'B'))}\` } },
  { type: 'user', message: { role: 'user', content: \`\${SMINOS_PROMPT}\${deliveryText('t-sminos', answered('Which queue?', 'A'))}\` } },
  // Rows the search must leave out: a prompt snapshot naming the tool, a human quoting a delivery.
  { type: 'attachment', attachment: { type: 'prompt_snapshot', tools: [{ name: ASK_TOOL, description: 'd' }, { name: SMINOS_TOOL, description: 'd' }] } },
  { type: 'user', message: { role: 'user', content: \`see \${deliveryText('t-open', 'quoted')}\` } },
]
// One conversation, each row the child of the one before it, as the engine stores them.
const lines = rows.map((row, i) => JSON.stringify({ parentUuid: i === 0 ? null : \`u\${i - 1}\`, uuid: \`u\${i}\`, ...row }))
const path = '$work/transcript.jsonl'
writeFileSync(path, lines.join('\n') + '\n')
const run = ([command, ...args]: string[], env?: NodeJS.ProcessEnv) =>
  execFileSync(command as string, args, { encoding: 'utf8', env: env ? { ...process.env, ...env } : process.env }).split('\n')
const found = run(searchArgs(path))
const grepped = run(grepArgs(path))
const whole = rebuildAsks(lines).map((a) => [a.id, a.status])
const searched = rebuildAsks(found, { isWholeFile: false }).map((a) => [a.id, a.status])
const expected = [['t-first', 'answered'], ['t-tool', 'answered'], ['t-prompt', 'answered'], ['t-plugin', 'answered'], ['t-open', 'open'], ['t-sminos', 'answered'], ['t-sminos-open', 'open']]
const leftOut = found.filter((line) => line.includes('prompt_snapshot') || line.includes('"see '))
let failed = 0
const check = (name: string, ok: boolean, detail: unknown) => {
  console.log(\`\${ok ? 'ok' : 'FAIL'}: \${name}\${ok ? '' : ' ' + JSON.stringify(detail)}\`)
  if (!ok) failed++
}
check('the full read rebuilds every ask', JSON.stringify(whole) === JSON.stringify(expected), whole)
check('the search rebuilds what the full read does', JSON.stringify(searched) === JSON.stringify(whole), searched)
check('the search leaves out the prompt snapshot and the human quote', leftOut.length === 0, leftOut)
check('grep finds the lines perl does', JSON.stringify(grepped) === JSON.stringify(found), grepped)
// perl's output bytes are grep's whatever PERL_UNICODE says: with S it would put a :utf8 layer on STDOUT and
// double-encode the non-ASCII text of every line it prints.
const koreanPath = '$work/korean.jsonl'
writeFileSync(koreanPath, JSON.stringify({ uuid: 'k0', ...use('t-ko', '어떤 백엔드를 쓸까요? \u00e9')}) + '\n')
const [grepCommand, ...grepRest] = grepArgs(koreanPath)
const koreanGrep = execFileSync(grepCommand as string, grepRest)
const koreanPerl = execFileSync('perl', searchArgs(koreanPath).slice(1), { env: { ...process.env, PERL_UNICODE: 'S' } })
check('perl prints a line of non-ASCII text as grep does under PERL_UNICODE=S', koreanPerl.length > 0 && koreanPerl.equals(koreanGrep), [koreanPerl.toString(), koreanGrep.toString()])
// Exit codes are grep's: 1 when no line holds a form, 2 when the file cannot be read.
const status = (argv: string[]) => {
  try {
    execFileSync(argv[0] as string, argv.slice(1), { stdio: 'ignore' })
    return 0
  } catch (error) {
    return (error as { status: number }).status
  }
}
writeFileSync('$work/none.jsonl', JSON.stringify(rows[rows.length - 1]) + '\n')
check('a file with no form exits 1', status(searchArgs('$work/none.jsonl')) === 1, status(searchArgs('$work/none.jsonl')))
check('a missing file exits 2', status(searchArgs('$work/missing.jsonl')) === 2, status(searchArgs('$work/missing.jsonl')))
process.exit(failed === 0 ? 0 : 1)
TS

cd "$work" && bun run check.ts
echo "ask search: all checks passed"
