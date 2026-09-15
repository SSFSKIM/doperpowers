# markdown

Draws every assistant message with the plugin's own markdown typography
instead of the engine's. A plugin of function hooks (a "mod"), so it loads
only where `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` is set, and only on the
terminal surface; the desktop and mobile keep their own drawing.

## What it draws

The `AssistantMessage` site hands the hook the block's markdown; the hook
parses it (`hooks/markdown.ts`, pure) and returns a tree:

- A measured column: at most `measure` cells wide (default 96), narrower on a
  narrow terminal, indented under the reply's bullet.
- One blank row between blocks, one more before a level 1 or 2 heading.
- Headings by weight and color: level 1 bold in the accent with a rule under
  it, level 2 bold in the accent, level 3 bold, deeper bold and dim. Size
  is not available in a cell grid.
- Bullets in the accent with a hanging indent (`•`, `◦`, `▪` by depth),
  numbered lists with an aligned gutter, task boxes `☐` and `☑`. A list
  whose items wrap gets a blank row between items; short items stay tight.
- Bold, italic, strikethrough, inline code in cyan, links as OSC 8
  hyperlinks in the accent (an href the engine would refuse draws as
  underlined text).
- Block quotes in italic behind an accent bar on every wrapped row.
- Tables with a bold header, a rule, column alignment from the delimiter
  row, and cells wrapped when the table is wider than the column. Hangul
  and CJK count as two cells.
- Fenced code through the engine's `Code` element (syntax highlighting).
- Rules as a dim line.

A message still streaming re-renders as it grows: an unclosed fence runs to
the end, an unmatched emphasis marker draws as itself.

## Options

Set in `/config` (or `pluginConfigs.markdown.options` in settings):

| Option | Default | What it is |
| --- | --- | --- |
| `measure` | 96 | Widest column the text takes, in cells |
| `accent` | `#d97757` | Color of headings, bullets, rules and links: a name or a hex value |

## Running it

```
claude --plugin-dir mods/markdown --debug
claude plugin validate mods/markdown
claude plugin test mods/markdown
npx -p typescript@5 tsc -p mods/markdown/tsconfig.json
```

Typechecking reads `.claude/types/claude-code.d.ts`, which `/plugin-types`
writes (gitignored); regenerate it after a Claude Code update.

## Known limits

- Setext headings (`Title\n=====`), reference-style links, footnotes and raw
  HTML are drawn as text.
- The `ctrl+o` detailed transcript runs the same hook, so it draws the same.
- With the `to-human` mod loaded as well, whichever registered first wraps
  the other; both drawing `AssistantMessage` is a composition still to design.
