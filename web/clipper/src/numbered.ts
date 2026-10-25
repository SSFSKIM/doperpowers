// The summary's text: the file's lines from the first, each prefixed with
// its number, until the next line would push the estimate of what was
// printed plus the question's reserve past the cap.
import { TokenCounter } from './estimate.ts'
import { splitLines } from './measure.ts'

export function numbered(text: string, maxTokens: number, reserve: number): { header: { firstLine: number; lastLine: number; totalLines: number }; body: string } {
  const lines = splitLines(text)
  const counter = new TokenCounter()
  const out: string[] = []
  for (let i = 0; i < lines.length; i++) {
    const line = `${i + 1}| ${lines[i].replace(/\r$/, '')}\n`
    if (counter.peek(line) + reserve > maxTokens) break
    counter.add(line)
    out.push(line)
  }
  return { header: { firstLine: 1, lastLine: out.length, totalLines: lines.length }, body: out.join('') }
}
