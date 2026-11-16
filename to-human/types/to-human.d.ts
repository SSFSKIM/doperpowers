/**
 * to-human's contract: the values it keeps in `$.state`, held by the host for
 * the session (they outlive a reload of the plugin's code and end with the
 * process).
 *
 * `folds`, `fold` and `foldLast`: the runs of working record the report folds, as the run
 * tracker (hooks/mods/folds.tsx) follows them from the rows the main
 * conversation keeps. The view (hooks/mods/to-human.tsx) reads the first two where it
 * draws a fold's button and finds the run of the row that draws it by the
 * rows' places in the transcript; a button that reads them is drawn again
 * when either is written. Only to-human writes them:
 *
 *   const FOLDS = { plugin: 'to-human', key: 'folds' } as const
 *   const { value } = await $.state.get(FOLDS)          // undefined at version 0, before the first run
 */

/** One run of working record as the tracker publishes it. */
export type FoldRun = {
  /** The run's first row; a tool call's row by its call's id. */
  first: string
  /** Its last row, once the run is closed (the open run's newest row is under `foldLast`). */
  last?: string
  /** The newest call's line, shown while the run is live; cleared when a summary settles. */
  line?: string
  /** The last summary made of it. */
  summary?: string
  /** Rows have joined since its last summary settled, or one is on its way. */
  isLive?: true
}
/** key `folds`: the closed runs, oldest first. */
export type Folds = { shape: 1; runs: FoldRun[] }
/** key `fold`: the open run, or null when there is none. */
export type OpenFold = FoldRun | null
/**
 * key `foldLast`: the open run's newest row, or null when there is none; no
 * drawing reads it, so a row that joins the open run without changing its
 * label (a note, a delivery) draws no button again. It bounds the open run for
 * a module that takes it up after a reload.
 */
export type OpenFoldLast = string | null

/**
 * The session's file, `to-human/folds/<session id>.json` in the
 * configuration directory: every run with a summary, as
 * `[first, last, summary]` (the ids as `FoldRun` gives them; the open run's
 * bounded by the last row its summary covered), oldest first. A contract a
 * client reads (MAWS): the mod writes the file by atomic replacement (a
 * temporary file in the same directory, then a rename over the file), and
 * before it writes it reads the file again and keeps every stored run its own
 * tracker does not hold (its own runs win where both hold one, by the run's
 * first id). A file kept so says `shape: 2`; releases before 0.9.0 wrote
 * shape 1, whole and in place from one process's memory, which the mod still
 * reads and a client does not.
 */
export type StoredFolds = { shape: 2; runs: [first: string, last: string, summary: string][] }

declare module 'claude-code' {
  interface PluginState {
    'to-human': { folds: Folds; fold: OpenFold; foldLast: OpenFoldLast }
  }
}
