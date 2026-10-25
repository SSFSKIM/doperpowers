// One deadline for a whole fetch: each stage takes the lesser of its own
// limit and the time left.

export const CLIP_DEADLINE_MS = 150_000

export class Deadline {
  private readonly end: number

  constructor(ms: number) {
    this.end = Date.now() + ms
  }

  remaining(): number {
    return Math.max(0, this.end - Date.now())
  }

  expired(): boolean {
    return this.remaining() === 0
  }

  /** A stage's time: its own limit, or the time left when that is less. */
  limit(ms: number): number {
    return Math.min(ms, this.remaining())
  }
}
