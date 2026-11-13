/**
 * to-human's contract: the values it keeps in `$.state`, held by the host for
 * the session (they outlive a reload of the plugin's code and end with the
 * process).
 *
 * `folds` and `fold`: the runs of working record the report folds, as the run
 * tracker (hooks/mods/folds.tsx) follows them from the rows the main
 * conversation keeps. The view (hooks/mods/to-human.tsx) reads both where it
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
  /** Its last row: of a closed run, the last that joined it; of the open run, the newest so far. */
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

declare module 'claude-code' {
  interface PluginState {
    'to-human': { folds: Folds; fold: OpenFold }
  }
}
