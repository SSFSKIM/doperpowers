#!/usr/bin/env bash
# The ask mod's search of a transcript too large to read whole, run for real:
# grep, with the arguments the mod builds (searchArgs), over a fixture
# transcript. What it finds must rebuild the asks a read of the whole file
# rebuilds. The mods' own tests cannot reach a process; bun runs the mod's
# pure functions directly.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cat > "$work/check.ts" <<TS
import { execFileSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { ASK_TOOL, ASYNC_RESULT, deliveryText, rebuildAsks, searchArgs } from '$root/hooks/mods/ask.tsx'

const answered = (q: string, a: string) => \`Your questions have been answered: "\${q}"="\${a}". You can now continue with these answers in mind.\`
const question = (q: string) => ({ question: q, header: 'H', multiSelect: false, options: [{ label: 'A', description: 'a' }, { label: 'B', description: 'b' }] })
const use = (id: string, q: string) => ({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'tool_use', id, name: ASK_TOOL, input: { questions: [question(q)], async: true } }] } })
const result = (id: string) => ({ type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: ASYNC_RESULT }] } })
const context = (hookName: string, content: string[]) => ({ type: 'attachment', attachment: { type: 'hook_additional_context', content, hookName } })
const rows = [
  use('t-first', 'Which backend?'), result('t-first'),
  use('t-tool', 'Which features?'), result('t-tool'),
  use('t-prompt', 'Which layout?'), result('t-prompt'),
  use('t-plugin', 'Which store?'), result('t-plugin'),
  use('t-open', 'Which port?'), result('t-open'),
  // A delivery opening the context, and one behind another hook's context on each route.
  context('tool.call', [deliveryText('t-first', answered('Which backend?', 'A'))]),
  context('tool.call', ['other context, "quoted"\\\\', deliveryText('t-tool', answered('Which features?', 'B'))]),
  context('prompt.submit', ['other context', deliveryText('t-prompt', answered('Which layout?', 'A'))]),
  { type: 'user', message: { role: 'user', content: \`The doperpowers plugin sent a message:\n\${deliveryText('t-plugin', answered('Which store?', 'B'))}\` } },
  // Rows the search must leave out: a prompt snapshot naming the tool, a human quoting a delivery.
  { type: 'attachment', attachment: { type: 'prompt_snapshot', tools: [{ name: ASK_TOOL, description: 'd' }] } },
  { type: 'user', message: { role: 'user', content: \`see \${deliveryText('t-open', 'quoted')}\` } },
]
const lines = rows.map((row) => JSON.stringify(row))
const path = '$work/transcript.jsonl'
writeFileSync(path, lines.join('\n') + '\n')
const [command, ...args] = searchArgs(path)
const found = execFileSync(command as string, args, { encoding: 'utf8' }).split('\n')
const whole = rebuildAsks(lines).map((a) => [a.id, a.status])
const searched = rebuildAsks(found).map((a) => [a.id, a.status])
const expected = [['t-first', 'answered'], ['t-tool', 'answered'], ['t-prompt', 'answered'], ['t-plugin', 'answered'], ['t-open', 'open']]
const leftOut = found.filter((line) => line.includes('prompt_snapshot') || line.includes('"see '))
let failed = 0
const check = (name: string, ok: boolean, detail: unknown) => {
  console.log(\`\${ok ? 'ok' : 'FAIL'}: \${name}\${ok ? '' : ' ' + JSON.stringify(detail)}\`)
  if (!ok) failed++
}
check('the full read rebuilds every ask', JSON.stringify(whole) === JSON.stringify(expected), whole)
check('the search rebuilds what the full read does', JSON.stringify(searched) === JSON.stringify(whole), searched)
check('the search leaves out the prompt snapshot and the human quote', leftOut.length === 0, leftOut)
process.exit(failed === 0 ? 0 : 1)
TS

cd "$work" && bun run check.ts
echo "ask search: all checks passed"
