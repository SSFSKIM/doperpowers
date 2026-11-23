# Articles — design law

Explainer articles written by doperpowers:present. One self-contained HTML file each, Korean unless asked otherwise.

## Stance (adopted from the two articles of 2026-09)

Printed and tonal: warm paper ground, near-black ink, one teal accent. Dense reading matter, low energy, no motion. The accent marks navigation, section kickers and the fill of a data bar; it never decorates a heading, a card or a diff.

## Tokens (defined once in each file's `:root`)

`--paper #faf8f3`, `--ink #1b1b1f`, `--mute #6b6f7a`, `--line #d9d4c7`, `--card #ffffff`, `--accent #0e7c7b`, `--soft #eef3f3`, `--code-ground #f3f1ea`, `--code-dark #1d2026`. Status pairs: `--del-bg #fdecec` with `--del-ink #b3261e`, `--ins-bg #e9f6ee` with `--ins-ink #1a6b3c` (each ink is over 5:1 on its ground). No color literal outside `:root`.

## Type

The system Korean stack for prose (19px, 1.65), a mono stack for code and diffs only. `word-break: keep-all` on prose; `overflow-wrap: anywhere` inside diffs.

## Composition

One column, 980px at most, prose capped near 780px. A cover (kicker, title, one-sentence deck, fact chips, table of contents), then numbered chapters separated by a hairline. Figures run the full column.

## Components

- **Diff figure.** Caption bar with the file path and the hunk's name and counts; one row per line with a gutter sign (+, −) and a tinted ground. The sign carries the state, the tint repeats it. Whole replaced blocks use a line diff (`git diff --patience`); a file whose paragraphs are single lines uses a word diff, removed words struck through and added words underlined.
- **Bars** for a handful of shares, the number printed at the right.
- **Tiles** in two columns for a before/after summary; one column under 700px.
- **Callout** for one aside per chapter at most: amber for context, red for a failure that remains.

## Content

Real figures, real diffs and real command output only. Terms are explained before first use; file paths stay in captions and code, out of sentences.
