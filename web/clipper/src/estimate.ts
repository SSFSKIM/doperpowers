// The one size estimate every figure in the tool uses: one token per four
// ASCII characters, plus one token per non-ASCII character. It runs high on
// purpose, so a cap set in it holds for Korean or Chinese pages too.

export class TokenCounter {
  private ascii = 0
  private other = 0

  add(text: string): void {
    const [a, o] = count(text)
    this.ascii += a
    this.other += o
  }

  /** The estimate if `text` were added, without adding it. */
  peek(text: string): number {
    const [a, o] = count(text)
    return Math.ceil((this.ascii + a) / 4) + this.other + o
  }

  get value(): number {
    return Math.ceil(this.ascii / 4) + this.other
  }
}

export function estimateTokens(text: string): number {
  const [a, o] = count(text)
  return Math.ceil(a / 4) + o
}

function count(text: string): [number, number] {
  let ascii = 0
  let other = 0
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i)
    if (c < 0x80) ascii++
    else {
      other++
      // A surrogate pair is one character.
      if (c >= 0xd800 && c <= 0xdbff && i + 1 < text.length) {
        const d = text.charCodeAt(i + 1)
        if (d >= 0xdc00 && d <= 0xdfff) i++
      }
    }
  }
  return [ascii, other]
}

/** Words as Defuddle counts them: each CJK character is a word. */
export function countWords(text: string): number {
  let words = 0
  let inWord = false
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i)
    const cjk = (c >= 0x3040 && c <= 0x30ff) || (c >= 0x3400 && c <= 0x4dbf) || (c >= 0x4e00 && c <= 0x9fff)
      || (c >= 0xf900 && c <= 0xfaff) || (c >= 0xac00 && c <= 0xd7af)
    if (cjk) { words++; inWord = false }
    else if (c <= 32) inWord = false
    else if (!inWord) { words++; inWord = true }
  }
  return words
}
