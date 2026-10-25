// The summary's text: the file's lines from the first, each prefixed with
// its number, until the next line would push the estimate of what was
// printed plus the question's reserve past the cap. A first line that alone
// would pass it is printed cut to fit, and the header says so.
import { TokenCounter } from './estimate.ts'
import { splitLines } from './measure.ts'

export type NumberedHeader = { firstLine: number; lastLine: number; totalLines: number; cut?: true }

export function numbered(text: string, maxTokens: number, reserve: number): { header: NumberedHeader; body: string } {
  const lines = splitLines(text)
  const counter = new TokenCounter()
  const out: string[] = []
  for (let i = 0; i < lines.length; i++) {
    const line = `${i + 1}| ${lines[i].replace(/\r$/, '')}\n`
    if (counter.peek(line) + reserve > maxTokens) {
      if (i === 0) {
        const cut = cutToFit(lines[0].replace(/\r$/, ''), maxTokens - reserve)
        if (cut !== null) return { header: { firstLine: 1, lastLine: 1, totalLines: lines.length, cut: true }, body: cut }
      }
      break
    }
    counter.add(line)
    out.push(line)
  }
  return { header: { firstLine: 1, lastLine: out.length, totalLines: lines.length }, body: out.join('') }
}

/** `1| ` and as much of the line as fits in `budget` tokens, whole characters only; null when not even the prefix fits. */
function cutToFit(line: string, budget: number): string | null {
  const counter = new TokenCounter()
  counter.add('1| \n')
  if (counter.value > budget) return null
  let end = 0
  for (const ch of line) {
    if (counter.peek(ch) > budget) break
    counter.add(ch)
    end += ch.length
  }
  return `1| ${line.slice(0, end)}\n`
}
