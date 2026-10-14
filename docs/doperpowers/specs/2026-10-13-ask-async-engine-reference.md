# AskUserQuestion dialog: the engine's reference (Claude Code 2.1.292, checked against 2.1.296)

Source: `~/claude-code-bundle/2.1.292/cli.pretty.js` (beautified bundle). Citations are `L<line>` in that
file, with the owning chunk named where it helps. Raw minified chunks are in `modules/<chunk>.js`.

Legend: **[read]** means the fact comes straight from code. **[inferred]** means I derived it from code I
did not trace end to end, or it depends on runtime behaviour (terminal, focus manager, zod wording).
Unmarked statements are [read].

## 0. Version status (2.1.296)

The running engine is 2.1.296. I diffed the minified code token by token, with short identifiers
normalized, against the 2.1.296 binary (`~/.local/share/claude/versions/2.1.296`):

- **Dialog component region** (tab bar → review page → result builders, `"answered "` …
  `(No answer provided)`): identical apart from renamed identifiers (ratio 0.9985, and every diff is a
  rename).
- **Multi-select component**: identical. **Select key handling** and the **input ("Type something") row**
  are also identical.
- **Select render** has one addition in 2.1.296: the Select container now carries
  `textEntry: <cond> ? true : undefined`. The likely effect is that printable keys (such as `j`, `k`, digits)
  go to the "Type something" input and skip the keybinding layer [inferred].
- **Tool definition**: `prompt()` now receives `tools`. The "Plan mode note" paragraph is dropped when
  the plan-mode tools are unavailable: `lrr(n) ? <base without plan note> : <base with note>`.
  Everything else is identical, including the result texts, schemas and admission rules.
- Every UI string listed in this document is present in the 2.1.296 binary.

The wording `User has answered your questions: …` does not appear in any bundled version (2.1.220 and later). The
current wording is in §8.

---

## 1. Pipeline in one paragraph

The tool is `w8` (L837888, chunk-qcgmsy8g). `checkPermissions` always returns
`{behavior:"ask", message:"Answer questions?", updatedInput:K(input)}` (L838020). `K` keeps
`title`/`metadata`, strips `answers`/`annotations`, and adds `kind:"choice"` in extended mode (L837885).
The permission layer maps the tool to the dialog kind `permission_ask_user_question` (`wue`, L205812). The
payload builder `So` (L206078) parses the questions and adds `metadataSource` and `isEngineConfirm`. The
dialog host `tke` (L319074) mounts `LSe` (L314652), which raises the mod event `ui.render` for component
`"AskUserQuestion"` with props `{tool, questions, metadataSource}`. A rewrite may relabel only
(L314699-314732). `LSe` then draws `ESe` (L314733), the state machine. `ESe` renders one of:

- `OJ`: the **standard layout** (L314346)
- `_J`: the **preview layout** (L314040), which `OJ` delegates to
- `FJ`: the **review/submit page** (L314493)

The result goes back as `allow` + `updatedInput {…input, answers, annotations, afkTimeoutMs?}` (`VJ`,
L315068), or as `deny` (Esc) / `deny + feedback` ("Chat about this", `o7e`, L315078). `call()`
(L838022) produces `{questions, answers, response?, annotations?, afkTimeoutMs?, followUp?}`.
`mapToolResultToToolResultBlockParam` (L838029) turns that into the text the model reads.

Wrapper behaviours:

- **Input grace period.** `wouldTakeAnswer` refuses any answer within **150 ms** of the dialog being
  shown (`lc(...)`, `J2 = 150`, L24477-24483; used in `tke` L319080-319087). Every answer path checks it,
  so keys typed ahead are dropped.
- **Height lock.** `ESe` wraps everything in `YK` (L990684), whose default `lock:"always"` keeps a
  `minHeight` equal to the tallest height drawn so far. The dialog never shrinks while open (it re-measures
  on terminal resize). A shorter question leaves blank rows at the bottom.

---

## 2. Theme keys, colours and glyphs

### 2.1 Theme keys used by the dialog

| Theme key | dark (default) | light | dark-ansi | light-ansi | dark-daltonized | light-daltonized |
|---|---|---|---|---|---|---|
| `text` | rgb(255,255,255) | rgb(0,0,0) | whiteBright | black | rgb(255,255,255) | rgb(0,0,0) |
| `inactive` | rgb(153,153,153) | rgb(102,102,102) | white | blackBright | rgb(153,153,153) | rgb(102,102,102) |
| `permission` | rgb(177,185,249) | rgb(87,105,247) | blueBright | blue | rgb(153,204,255) | rgb(51,102,255) |
| `suggestion` | rgb(177,185,249) | rgb(87,105,247) | blueBright | blue | rgb(153,204,255) | rgb(51,102,255) |
| `success` | rgb(78,186,101) | rgb(44,122,57) | greenBright | green | rgb(51,153,255) | rgb(0,102,153) |
| `warning` | rgb(255,193,7) | rgb(150,108,30) | yellowBright | yellow | rgb(255,204,0) | rgb(255,153,0) |
| `inverseText` | rgb(0,0,0) | rgb(255,255,255) | black | white | rgb(0,0,0) | rgb(255,255,255) |
| `userMessageBackground` (hover tint) | rgb(55,55,55) | rgb(240,240,240) | blackBright | white | rgb(55,55,55) | rgb(220,220,220) |

The tables are at L639873; the name → table switch `r1` is at L639874. Unknown names fall back to dark.
`dimColor` means SGR 2 (faint) and combines with the colour.

### 2.2 Glyphs (`ee`, L405201, chunk-bqr68tt9)

There are two tables. The unicode one is used everywhere except Windows consoles that lack unicode support
and `TERM=linux`; the predicate is `r()`, L405195-405200.

| name | unicode | fallback |
|---|---|---|
| `pointer` | `❯` U+276F | `>` |
| `tick` | `✔` U+2714 | `√` |
| `checkboxOn` | `☒` U+2612 | `[×]` |
| `checkboxOff` | `☐` U+2610 | `[ ]` |
| `arrowRight` / `arrowLeft` / `arrowUp` / `arrowDown` | `→ ← ↑ ↓` | same |
| `bullet` | `●` U+25CF | |
| `warning` | `⚠` U+26A0 | `‼` |
| divider char `M6` | `─` U+2500 (L671480) | |
| preview box chars `zd` | `┌ ┐ └ ┘ ─ │ ├ ┤` (L313864) | |
| truncation ellipsis | `…` U+2026 | |

Notes:

- The tab bar's answered/unanswered glyphs are `☒` / `☐`. The Submit tab always shows `✔` (the tick,
  not a checkbox).
- The multi-select checkbox is built literally as `"[" + (checked ? "✔" : " ") + "]"`, so it reads
  `[✔]` / `[ ]`. It does not use `checkboxOn`/`checkboxOff`.

### 2.3 Shared building blocks

- **Divider `Sl`** (L209691): `─` repeated across the full terminal width (`ke().columns`) in the given
  colour. The dialog always passes `color:"inactive"`, so it is not dimmed. In screen-reader mode it
  renders nothing (`TL`).
- **Tab chip `pw`** (L45673): `Text{backgroundColor: color, color: color ? "inverseText" : undefined}`
  with one space of padding on each side, i.e. `" " + content + " "`.
- **Title `o8`** (L845734): `Text{bold:true, color:"text"}` (the dialog always passes `"text"`).
- **Gutter `ci`** (L524914): used when `needsGutter`, meaning the text contains `\n` or is wider than 80
  columns (`nS`, L22177). The content then sits in a Box with only a left border, `borderStyle:"single"`,
  `borderDimColor`, `paddingLeft:1`. The result is `│ ` followed by the text, with the bar dimmed.
- **Key hint `G`** (L616218-616340) renders `<key> to <action>`. Key names (default style): `enter`→`Enter`,
  `escape`→`Esc`, `tab`→`Tab`, `["up","down"]`→`↑/↓`, `ctrl+g`→`ctrl+g`, `n`→`n`.
- **Hint joiner `Se`** (L915098): drops empty children and joins the rest with a dim ` · `.
- **Key-hint footer line**: `Text{color:"inactive", dimColor:true}` containing the joined hints.

---

## 3. Standard layout (`OJ`, L314346-314492): single-select

This layout is used when the question is multi-select, when no option carries a usable preview, or in
screen-reader mode.

### 3.1 Row structure (top to bottom)

```
[plan mode only]  ────────…   (inactive divider)                       L314443
[plan mode only]  Planning: <plan file path>   (inactive; path is a file link)
────────────────────────────────────────…  (inactive, full width)      L314448
<tab bar row>                                                          KS, marginBottom 1
(blank)
<question title>   bold, color "text"; gutter if multi-line/>80 cols   L314458-314463
(blank)                                                                Box marginTop 1
<option rows …>                                                        Select, layout "compact-vertical"
<"Type something." row>
────────────────────────────────────────…  (inactive divider)          L314468
  N. Chat about this
(blank)                                                                marginTop 1
Enter to select · ↑/↓ to navigate · Esc to cancel   (inactive + dim)
[AFK row, 1 line, right-aligned, only if AFK enabled]                  §7
[plugin notice row, only if a plugin set one]                          L315042-315066
```

The root Box has `marginTop:0` (L314471). The first row is the divider. Whether the dialog host adds a
blank row above it, I did not verify.

### 3.2 Worked example (two questions, focus on option 1, 80 columns)

```
────────────────────────────────────────────────────────────────────────────────
←  ☐ Purpose  ☐ Surfaces  ✔ Submit  →

What is this tool for?

❯ 1. Internal tool
     Used only by the team
  2. Public product
     Shipped to customers
  3. Type something.
────────────────────────────────────────────────────────────────────────────────
  4. Chat about this

Enter to select · Tab/Arrow keys to navigate · Esc to cancel
```

Colours in the example:

- `←` is `inactive` because the first tab is active.
- `" ☐ Purpose "` has background `permission` and foreground `inverseText`.
- `" ☐ Surfaces "` and `" ✔ Submit "` use the default colour.
- `" →"` uses the default colour.
- `❯` is `suggestion`.
- `1.` is dim.
- `Internal tool` is `suggestion`.
- Its description is dim plus `suggestion`.
- Unfocused labels use the default colour; their descriptions are dim with the default colour.
- `3.` is dim and `Type something.` is `inactive`.

### 3.3 Tab bar (`KS`, L313958-314039)

Layout: one row, `marginBottom:1`, with the children concatenated and no gaps:

1. **Left arrow**: `Text("← ")`, colour `inactive` when on the first tab, otherwise the default colour.
   It is hidden when there is exactly one question and the Submit tab is hidden.
2. **One chip per question**: `pw(color: active ? "permission" : undefined, padded)`. The content is
   `glyph + " " + header`, where the glyph is `☒` if `answers[question]` is truthy and `☐` otherwise.
   In screen-reader mode an answered chip reads `☒ answered <header>` (`n8e = "answered "`, L313957).
3. **Submit chip**: `pw(color: index === questions.length ? "permission" : undefined)` with content
   `"✔ Submit"`. It is hidden when `hideSubmitTab`.
4. **Right arrow**: `Text(" →")`, `inactive` when the Submit tab is active (`index === questions.length`).
   It is hidden under the same condition as the left arrow.

Since every chip is padded, the literal row is `←  ☐ Purpose  ☐ Surfaces  ✔ Submit  →` (two spaces
between items).

**Header text.** The header is `displayHeader`. When it is empty or zero-width, the chip shows `Q<n>`
(1-based). `displayHeader = Bte(header)` (L22354): sanitised, whitespace collapsed, JSON-quoted if it
begins or ends with `"` (or fails a safety check), then truncated to **48 columns** with `…` (`wze = 48`,
L22293). The 12-character limit in the schema description is **not enforced** anywhere.

**Narrow-terminal truncation** (L313961-314000):

- `avail = columns − width("← ") − width(" →") − width(" ✔ Submit ")`. That is `columns − 14`, or
  `columns − 4` when the Submit tab is hidden.
- If `avail ≤ 0`, only the active chip's text is truncated to 3 columns. The other chips get `""`, which
  then falls back to the full header because of an `||` (a quirk).
- Otherwise, if `Σ(4 + width(header)) ≤ avail`, every header is shown in full.
- Otherwise the active chip gets a budget of `min(4 + width, avail/2)`. Each other chip gets
  `max(6, floor((avail − activeBudget)/(n−1)))`. Each header is truncated with `…` to `budget − 4`
  columns.

### 3.4 Question line

`o8{title, color:"text"}` gives **bold** text in the `text` colour.

- The text is `Pi(question)` (L22375): capped at 2000 code units plus `…`, tabs become a space, and
  unsafe control/format characters become `U+FFFD` or are removed.
- If the result has a newline or is wider than 80 columns, it is wrapped in the dim left-bar gutter
  (§2.3).
- `displayBody` is non-empty only for engine-originated confirms (tool_use_id prefix `confirm_`,
  L513594). For those, the text after the first blank line becomes a body of runs drawn in `inactive`,
  with `[label](file:///abs)` turned into file links (`bOo`, L205943; `iJ`, L313800-313854). Ordinary
  model calls never get a body.

### 3.5 Option rows (Select `Ue` → `Qi`, layout `"compact-vertical"`, L851186-851218)

The options are `[...options.map(oso), OtherInput]`. In screen-reader mode a `"__chat__"` text option is
added for single-select (L314429-314432). `oso` (L314337) is
`{type:"text", value: rawLabel, label: displayLabel, description: gi(displayDescription)}`.

Each row is drawn by `wC` (L849421) as a Box row with **gap 1**:

```
[pointer col, 1 cell] ␣ [n.] ␣ [label] [␣ ✔ if this is the committed answer]
```

- **Pointer column** (`oi`, L849495):
  - `❯` in `suggestion` when focused.
  - Otherwise a dim `↓` on the last visible row when more rows are below.
  - Otherwise a dim `↑` on the first visible row when more rows are above.
  - Otherwise a space. While the Select is disabled (chat row focused) every row shows a space.
- **Number**: `` `${n}.`.padEnd(digits+1) `` drawn dim. `digits` is the digit count of the total row count,
  which is always 1 here, so the number is `1.` with no trailing space; the Box gap supplies the space.
- **Label colour**: `success` if it is the committed answer for this question, otherwise `suggestion`
  if focused, otherwise the default colour. It is not bold. Long labels wrap inside their flex item, so
  continuation lines align under the label [inferred: standard Ink wrapping].
- **Trailing `✔`** (`success`, after one gap): shown only on the committed answer (`selectedValue`),
  i.e. when you come back to an answered question.
- **Description**: on its own line(s), in a Box with `paddingLeft: digits + 4` (= 5), so it starts in the
  same column as the label. It is `dimColor:true` with colour `success`/`suggestion`/default, the same
  rule as the label. Newlines inside a description are replaced by `U+FFFD` (`gi`, L22496), so a
  description is effectively one paragraph that wraps.
- There is no blank line between options.

**Label normalisation** (`BJ`, L314632-314637): `gi(Pi(label).text).replace(/\s+/g," ").trim()`. Then
`M1`/`HMe` (L22309) disambiguate labels that become identical after normalisation (NFC). Duplicates are
shown JSON-quoted with non-ASCII `\uXXXX`-escaped, plus a ` (#2)`, ` (#3)` suffix. Answers are recorded
as these display labels (§8.2).

**Scroll window**: `visibleOptionCount = min(5, floor((terminalRows − 8)/2))` (L851303-851307).
Options plus the Other row number at most 5, so the list only scrolls on terminals shorter than 18 rows.
Then the pointer column shows the `↓`/`↑` markers. Scrolling moves the window one row at a time
(reducer `oc`, L850828).

**Mouse**: rows are clickable (`onClick`). A click selects an option, or focuses the input row. Hover
tints the row background with `userMessageBackground`, or uses inverse on 16-colour terminals (`kSe`,
L849373) [read; applies when mouse reporting is on].

### 3.6 The "Type something." row (Other)

The option is `{type:"input", value:"__other__", label:"Other", placeholder:"Type something.",
initialValue: questionStates[q].textInputValue}` (L314412-314426). Multi-select uses the placeholder
`"Type something"` with no period. It is drawn by `ASe` (L850456):

```
[pointer] ␣ "N. " (dim, padEnd(digits+2)) [content]
```

- **Not focused**: the content is the typed text in the default colour, or `Type something.` in
  `inactive` when empty. The label "Other" is never shown.
- **Focused**: it becomes a live text input (`cr`). It is `multiline`, shows a cursor, and wraps at
  `columns − 5` (`Er`, L850452).
  - When empty, the placeholder shows the first character inverted (block cursor) and the rest dim:
    `[T]ype something.` (`Xe`, L634528-634538).
  - **Shift+Enter / Meta+Enter**, or a trailing `\` followed by Enter, inserts a newline (`jt`,
    L188395).
  - **Esc** shows "Esc again to clear" when the field is non-empty, and a second Esc within 800 ms clears
    it (L188315-188338). In this dialog, though, Esc is first caught by the Select's `select:cancel`
    binding, which declines the whole dialog (§7) [inferred from capture-phase dispatch; verify live].
- Focusing the row puts the dialog in "text input mode" (`onTextInputFocus(true)`, L314355-314359). That
  turns off the Tabs bindings, so ←/→ move the cursor instead of switching questions.
- The footer gains `ctrl+g to edit in <Editor>` while this row is focused and an editor resolves.
  The editor comes from the `editor` setting or `$VISUAL`/`$EDITOR`; its display name comes from `db()`,
  L269642.
- **ctrl+g** (`chat:externalEditor`) opens the editor on the current text.
- **ctrl+v** (`chat:imagePaste`, or alt+v on Windows/WSL) pastes an image. The image appears as an
  `[Image #N]` chip under the row with a dim `(↓ to select)` hint. In attachment mode the keys are
  ←/→ (next/prev), Backspace/Delete (remove) and Esc/↓ (exit) (L850515-850635).
- **Enter**:
  - With non-blank text (or a pasted image), it commits the answer: the text, or text + ` (Image
    attached)`, or `(Image attached)` alone (L314894-314898).
  - With an **empty** field, it calls the Select's `onCancel`, which **declines the whole dialog**:
    `if (text.trim() || images || allowEmptySubmitToCancel) onChange(value); else onCancel()`, L851202-851207.

### 3.7 Divider and "Chat about this"

Drawn only outside screen-reader mode (L314468):

```
────────────────…  (inactive, full width)        — no blank line before it
[❯|␣] ␣ "N. Chat about this"
```

- `N = options.length + 2`. With 3 options it is `5.`, because Other takes 4.
- The whole text `N. Chat about this` is one Text. It is `suggestion` when focused (pointer `❯` in
  `suggestion`) and the default colour otherwise. The number is **not** dimmed, unlike the option rows.

### 3.8 Footer

`marginTop:1`, `Text{color:"inactive", dimColor:true}`, with hints joined by ` · `:

| Situation | Footer |
|---|---|
| one question | `Enter to select · ↑/↓ to navigate · Esc to cancel` |
| several questions | `Enter to select · Tab/Arrow keys to navigate · Esc to cancel` |
| plus: Other focused and an editor known | `… · ctrl+g to edit in <Editor> · Esc to cancel` (inserted before Esc) |

The hints are hard-coded chords. They do not follow user rebindings in `keybindings.json`, even though
the actual Tabs and Select bindings can be rebound.

### 3.9 Single question vs several

- **Exactly one single-select question** (`Nr = questions.length === 1 && !multiSelect`, L314822):
  - `hideSubmitTab` is true. The tab bar shows **just the one chip** (`" ☐ Header "`, active colours),
    with no arrows and no Submit chip. **The tab bar is still drawn.**
  - Choosing an option (or Enter on non-empty Other) **submits immediately** (L314900-314914). There
    is no review page.
  - Tab navigation is capped at index 0.
- **One multi-select question**: full tab bar (`←  ☐ H  ✔ Submit  →`). The Submit button leads to the
  **review page**.
- **Two or more questions**: answering a single-select question records the answer and **advances** to
  the next question. After the last one the index becomes `questions.length`, which is the review page
  (L314560-314564).

---

## 4. Multi-select layout (`rB` → `me`, L9989-10085; keys `de`, L9860-9983)

The options are `[...options, OtherInput]`. No chat row is ever added to the list, even in screen-reader
mode.

```
❯ 1. [ ] Auth
         Login and sessions
  2. [✔] Billing
  3. [ ] Type something
     Next
────────────────────────────────────────…
  5. Chat about this

Enter to select · ↑/↓ to navigate · Esc to cancel
```

**Option row** (L10060). This is `wC` with gap 1 over three flex children:

- the number, `` `${n}.`.padEnd(digits) `` drawn dim (`1.`);
- the checkbox `"[" + (checked ? "✔" : " ") + "]"`, coloured `success` when checked;
- a column containing the label and, below it, the description.

Colours:

- The label is `suggestion` when focused and the default colour otherwise. A checked option's label is
  **not** green; only the checkbox is.
- The description is `inactive` (**not** dim) and never takes the focus colour.

Columns: pointer 0, number 2-3, checkbox 5-7, label and description from column 9.

**Other row** (L10052-10058): `ASe` with the child `"[" + (checked ? "✔" : " ") + "] "` (with a trailing
space), so it reads `  3. [ ] Type something`.

- Typing text **auto-checks** the row. Clearing the text unchecks it (`updateInputValue`,
  L9881-9896).
- The input wraps at `columns − 9` (`extraChromeWidth:4`).

**Submit/Next button** (L10071-10076), always present in this dialog:

- The row is a Box with gap 1: pointer cell (`❯` `suggestion` when the button is focused, otherwise a
  space), then a Box with `marginLeft:3` holding a **bold** Text (`suggestion` when focused).
- The text sits at column 5, aligned with the checkboxes.
- The label is `"Submit"` on the last question and `"Next"` otherwise (L314477). Both advance the index:
  "Next" moves to the next question and "Submit" opens the review page.
- There is no blank line above it.

**Answer recording** happens on every toggle (L314471-314476):

- `answers[q] = Fut(selected.map(displayLabel) + [otherText if Other is checked])`.
- `Fut` (L837611) joins with `", "`. Any element that contains `", "` or `"` is written as a JSON string
  (`JSON.stringify`) first.
- An empty selection gives `""`, which counts as unanswered (`☐`).
- Toggling never advances.

**Visible rows**: `min(5, floor((rows−8)/2))` when any option has a description, otherwise
`min(5, rows−8)`.

---

## 5. Preview layout (`_J`, L314040-314333)

**When it is used** (L314433): `!multiSelect && options.some(o => o.preview !== undefined) &&
!screenReader`. This is decided **per question**, on processed previews.

**Preview processing** (`BJ`, L314635):

| Raw preview | Processed |
|---|---|
| absent | absent |
| longer than 2000 characters (`j4e`) | `{kind:"withheld"}` |
| empty or invisible after sanitising (`!HN`) | dropped (absent) |
| unsafe control/bidi content (`CH`) | `{kind:"withheld"}` |
| otherwise | `{kind:"full", markdown: nrt(preview)}` (sanitised raw markdown) |

A question whose previews were all dropped falls back to the standard layout.

### 5.1 Rows

```
(blank)                                          root marginTop 1 (the standard layout has 0)
────────────────────────────────────────…        inactive divider
←  ☐ Layout  ✔ Submit  →                         same tab bar (KS)
(blank)
Which layout should the dashboard use?           bold "text", gutter rule as §3.4 (no body)
(blank)                                          marginTop 1
❯ 1. Sidebar                  ␣␣␣␣┌────────────────────────────────────────┐
  2. Top bar ✔                    │ +------+-------------------+           │
  3. Tabs                         │ | nav  | content           │           │
                                  └────────────────────────────────────────┘
                                  (blank)
                                  Notes: press n to add notes
(blank)                                          marginTop 1
────────────────────────────────────────…        inactive divider
  Chat about this                                (no number)
(blank)
Enter to select · ↑/↓ to navigate · n to add notes · Tab to switch questions · Esc to cancel
```

The option list and the preview column sit in a row Box with `gap:4` (L314263).

**Option list**: a Box `width:30`, column direction. Each row is a Box row with **no gap**
(L314221-314223):

```
[❯ suggestion | " "] + Text(dim, " " + n + ".") + Text(" " + label) + [Text(success, " ✔") if committed]
```

- The label Text is `bold` when focused. Its colour is `success` if committed, otherwise `suggestion` if
  focused, otherwise the default colour.
- **Descriptions are not shown in this layout.**
- **There is no "Type something." row**; free text is replaced by Notes.
- Labels wrap inside the 30-column list [inferred: Ink wrapping].

**Preview column**: a Box column with `flexGrow:1` holding the preview box, then the Notes row.

### 5.2 Preview box (`uJ` → `Lye`, L313865-313946)

The content is the focused option's processed markdown. When the focused option has no preview, it is
`"No preview available"`. A withheld preview shows `"(preview cannot be shown in full — compare the
option labels and descriptions instead)"` (`Eye`, L313856).

1. Render the markdown to ANSI with the engine's terminal markdown renderer `B0t(md, theme, highlighter)`
   (L472876). This is the same renderer used for assistant text:
   - **headings** are bold; h1 is bold + italic + underline;
   - **lists** use the engine's bullets and numbering;
   - **tables** become `| a | b |` with a `|---|` rule;
   - **inline code** and the text of **fenced code with no language** take the `permission` colour
     (L472904, L472911);
   - **fenced code with a language** is syntax-highlighted, unless syntax highlighting is disabled in
     settings;
   - **blockquotes** get a dim `▎` and italic text;
   - **hr** renders as `---`.

   There is no wrapper font: "monospace" just means the terminal grid.
2. Split into lines. Tabs are expanded (`wQ`). Lines wider than `maxWidth − 4` are hard-wrapped.
3. `maxWidth = columns − 30 − 4`. `maxLines = max(1, rows − 26)`.
4. `minWidth` is the widest rendered preview line across **all** options of **all** questions, with a floor
   of **40** (`d9e`, L314631, L314745-314758). This keeps the box width stable while you move between
   options.
5. Box width `W = max(4, min(max(minWidth, widestLine) + 4, maxWidth))`. Inner width is `W − 4`.
6. Draw, with all box-drawing characters **dim**:
   - top: `┌` + `─`×(W−2) + `┐`;
   - each line: dim `│ ` + content (ANSI-styled; an over-long line is truncated with `…`) + spaces to the
     inner width + dim ` │`;
   - bottom: `└` + `─`×(W−2) + `┘`.
7. **Overflow.** If there are more than `maxLines` lines, the first `maxLines` are kept. Before the
   bottom edge a separator line is added in the **`warning`** colour (not dim):
   `├─── ✂ ─── N lines hidden ` + `─` fill + `┤`.
8. There is no minimum height, so the box height follows the option. The dialog height lock (§1)
   absorbs the change.

### 5.3 Notes

The Notes row (L314249-314253) is a Box row with `marginTop:1` and `gap:1`:

- `Text{color:"suggestion"}("Notes:")`.
- When not editing: `Text{dimColor, italic}` showing the notes text, or `press n to add notes` when
  empty.
- When editing (after pressing `n`): a text input with placeholder `Add notes on this design…`,
  `columns:60`, a cursor, and `disableEscapeDoublePress`. ctrl+g opens the external editor; the footer
  then also shows `ctrl+g to edit in <Editor>`.

Notes are stored per question in `questionStates[q].textInputValue`; for preview questions that slot holds
notes, not Other text.

**Enter inside Notes** (L314126-314136) first exits notes mode, then:

1. If the notes are non-blank and the highlight has **moved** since the question was entered (or since it
   was last re-entered), it selects the **highlighted** option and answers.
2. Otherwise, if an option was already chosen, it re-answers with that option, now carrying the notes.
3. Otherwise, if the notes are non-blank, the answer is the sentinel `(notes only)` (`iLt`, L837881).
4. Otherwise it only leaves notes mode.

**Esc inside Notes** leaves notes mode and keeps the text. Up/down navigation is ignored while in notes
mode.

### 5.4 Chat row and footer

- **Chat row** (L314271-314284): a Box column with `marginTop:1` holding the inactive divider, then a row
  with gap 1: `❯`/space plus `Text("Chat about this")` (`suggestion` when focused). It has **no number**,
  and there is no digit shortcut for it in this layout.
- **Footer** (L314287-314316), with optional items in brackets:
  `Enter to select · ↑/↓ to navigate · n to add notes [· Tab to switch questions] [· ctrl+g to edit in
  <Editor>] · Esc to cancel`. "Tab to switch questions" appears only when there are 2 or more questions.
  The ctrl+g hint appears only in notes mode.
- In plan mode, the "Planning: …" line is **not** shown in this layout, because `_J` does not receive
  `planFilePath`.

---

## 6. Review / submit page (`FJ`, L314493-314548)

**When it appears**: `currentQuestionIndex === questions.length`. That happens in these cases:

- after answering the last of 2 or more questions;
- after pressing Submit/Next on the last multi-select question (including a single multi-select
  question);
- after pressing Tab/→ past the last question.

It is never reachable for a single single-select question.

```
(blank)                                    marginTop 1
────────────────────────────────────────…  inactive divider
←  ☒ Purpose  ☐ Surfaces  ✔ Submit  →      Submit chip active (permission bg); " →" inactive
(blank)
Review your answers                        bold, "text"
(blank)                                    marginTop 1
⚠ You have not answered all questions      only if some are unanswered; ⚠ + text in "warning"; then blank
 ● What is this tool for?                  one block per ANSWERED question, in order
   → Internal tool                         "→ answer" in "success"
(blank)                                    marginBottom 1 after the list
Ready to submit your answers?              "inactive"
(blank)                                    marginTop 1
❯ 1. Submit answers
  2. Cancel
```

- Each answered block (L314516-314519) is a Box with `marginLeft:1`:
  - the question line: `Cm` draws a 2-cell `●` column, then the question's display text in the default
    colour, wrapped in the gutter if multi-line;
  - the answer line: a Box with `marginLeft:2` holding `Text{color:"success"}("→ " + answer)`.
- Answers appear exactly as stored, so multi-select shows the comma-joined string.
- Between "Ready to submit…" and the answers, `dw` (L525568) would draw the permission decision reason.
  For this tool it is normally empty.
- The Box declares `borderTop` with no `borderStyle`, so no border is drawn: borders need a valid
  `borderStyle` (L357289).
- **Buttons**: `Xn` (L1108031) is a Select (`compact` layout) with `[{label:"Submit answers",
  value:"confirm"}, {label:"Cancel", value:"cancel"}]`, focus on Submit.
  - Rows: `❯ 1. Submit answers` / `  2. Cancel`. The number is dim; the focused label is `suggestion`.
  - Digits 1/2 choose directly.
  - **Submit answers** allows even when questions are unanswered; it sends only the answered ones.
  - **Cancel**, or **Esc**, declines the dialog (same as §7 Esc).
- There is no key-hint footer on this page. ←/Tab/Shift+Tab/→ still switch tabs.

---

## 7. Key map

### 7.1 How keys are dispatched

The global keybinding dispatcher runs in the **capture phase** (`onKeyDownCapture`, L428491, `Zt`
L428289). When a key matches an active binding that has a registered handler, the handler runs and the
event is stopped with `preventDefault()` + `stopImmediatePropagation()` (`it`, L428493). Only unmatched
keys reach the components' `onKeyDown`, which bubbles from the focused element: Select → `OJ`/`_J` root
Box.

One exemption: a single printable character typed while a text-entry element has focus skips the bindings
(L428402).

Default bindings that matter here (L650393). All of them can be rebound by the user.

| Context | Bindings |
|---|---|
| `Tabs` | `tab`→next, `shift+tab`→previous, `right`→next, `left`→previous |
| `Select` | `up`/`k`/`ctrl+p`→previous, `down`/`j`/`ctrl+n`→next, `home`→first, `end`→last, `enter`→accept, `escape`→cancel (pageup/pagedown are handled in `onKeyDown`) |
| `Chat` | `ctrl+g`→externalEditor; `ctrl+v` (alt+v on Windows/WSL) →imagePaste |

When the Tabs handlers are active (L314957-314968):

- **Active** unless the dialog is in text-input mode (Other focused or Notes open) on a question page.
  On the review page they are always active.
- `previous` works only when `index > 0`. `next` works only when `index < last`, where `last` is
  `questions.length`, or `0` for a single single-select question. **Nothing wraps.**
- Switching resets text-input mode. The Select remounts per question (`key = question`), so focus returns
  to the **first** row. Committed answers and typed Other/notes text are kept.

### 7.2 Standard layout, single-select

| Key | Effect |
|---|---|
| ↑ / k / ctrl+p | Previous row. On the first row it wraps to the last row (the "Type something." row), unless the focus manager can move focus spatially upward [inferred: nothing focusable is above in this dialog] (L850668-850679, reducer L850846-850863). |
| ↓ / j / ctrl+n | Next row. **On the last row (Other) it moves focus to the "Chat about this" row** (`onDownFromLastItem`, L314364-314368, L850721-850730). |
| Home / End, PgUp / PgDn | First / last row; page by the window size. |
| Enter | On an option: commit it. With one question this **submits the dialog**; otherwise it records the answer and advances to the next question or the review page. On Other: §3.6. |
| 1-9 (full-width digits too, `U9` L62454) | `n ≤ options.length`: commit that option immediately, as Enter would. `n = options.length+1` (Other): submit if it has text, otherwise focus it. `n = options.length+2`: **Chat about this** (handled by `OJ` L314378-314382; not while Other is focused and not in screen-reader mode). Other digits and `0`: nothing. |
| Space | Nothing (outside the Other input). |
| Tab / Shift+Tab / → / ← | Next/previous question tab (when not in Other). |
| Esc | **Decline the dialog** (`select:cancel` → `onCancel`). The binding stays registered while Other is focused, so Esc in the text field also declines [inferred; see §3.6]. |
| ctrl+g / ctrl+v | In Other: external editor / paste image. |
| Chat row focused | ↑ or ctrl+p: back to the list, with the Select re-enabled and the previous focus kept. Enter or the chat digit: **Chat about this**. Esc: decline. ←/→/Tab still switch questions. All other keys are ignored (the Select is disabled). |

### 7.3 Multi-select

All of these keys are handled in the component's `onKeyDown`. The Select-context bindings are not used.

| Key | Effect |
|---|---|
| ↑ / k / ctrl+p | Previous option; wraps at the top. From the Submit button: back to the last option (Other). |
| ↓ / j / ctrl+n | Next option. On the last option (Other): focus the **Submit/Next button**. On the button: focus the **Chat** row. |
| Space or Enter on an option | Toggle it. |
| Enter on Submit/Next | Advance: next question, or the review page. |
| ctrl+Enter inside Other | Submit/advance. |
| 1-9 | Toggle option n, where `options.length+1` is Other. `options.length+2` is **Chat about this** (via `OJ`). |
| Tab / Shift+Tab | Switch question tabs. The bindings win in the capture phase, so the component's own Tab handling (Tab = Submit focus) is shadowed. It is reachable only while Other is focused, where Tabs are off: Tab on the last option then focuses Submit [inferred from dispatch order]. |
| Esc | Decline the dialog. |
| Inside Other | Printable keys type. ↑/↓/Tab/Esc/Enter still reach the list handler. **Enter inside Other toggles the Other checkbox**: the input's own submit is a no-op, and the event bubbles to the list handler, which toggles the focused row (L9908-9973). Since typing has already checked it, Enter unchecks it, and the typed text drops out of the answer [read from code; looks like a bug; verify live]. |

### 7.4 Preview layout (`_J` key handler, L314154-314194)

| Key | Effect |
|---|---|
| ↑ / ctrl+p | Previous option; **stops at the top** (no wrap). |
| ↓ / ctrl+n | Next option. From the last option: the Chat row. |
| Enter | Commit the highlighted option; submits if there is one question, otherwise advances. |
| 1-9 | **Move the highlight only** (does not commit, unlike the standard layout). |
| n (no ctrl/meta) | Enter Notes. |
| Esc | Decline the dialog. In Notes: leave Notes. |
| Tab / Shift+Tab / → / ← | Switch questions (not in Notes, not on the Chat row). |
| Chat row focused | ↑ or ctrl+p: back. Enter: Chat about this. Esc: decline. |
| j / k | **Not** navigation here: no Select is mounted, and `_J` checks only `up`/`down`. |

### 7.5 What each exit does

| Action | Permission result | What the model sees |
|---|---|---|
| Commit or submit | `{behavior:"allow", updatedInput:{…input, answers, annotations, afkTimeoutMs?}, contentBlocks?}` (`VJ`, L315068-315077) | §8 result text, plus any pasted images |
| **Esc / Cancel / Enter on empty Other** | `{behavior:"deny"}` (L314824-314831) | The tool_result (`is_error`) is `The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). STOP what you are doing and wait for the user to tell you how to proceed.` and **the turn is aborted** (`cancelAndAbort`, L205856-205859; text `wk`, L813635). In a subagent the text is instead `Permission for this tool use was denied. … Try a different approach or report the limitation to complete your task.` and nothing is aborted. |
| **Chat about this** | `{behavior:"deny", feedback, contentBlocks?}` (`o7e`, L315078-315087) | The tool_result is `Y0` + feedback, i.e. `The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). To tell you how to proceed, the user said:\n` followed by the clarify text below. **The turn continues**: with feedback present there is no abort. In a subagent the prefix is `Permission for this tool use was denied. … The user said:\n`. When the gate `tengu_amber_prism` is on, both deny texts get a memory-hint suffix (`JB`/`Jot`, L813630, L935297). |
| AFK timeout | allow, with `afkTimeoutMs` set | §8 AFK text |

Clarify feedback, verbatim (the 4-space indentation is literal):

```
The user wants to clarify these questions.
    This means they may have additional information, context or questions for you.
    Take their response into account and then reformulate the questions if appropriate.
    Start by asking them what they would like to clarify.

    Questions asked:
- "<question display text>"
  Answer: <recorded answer>          ← or "  (No answer provided)"
  User notes: <trimmed notes>        ← only for preview questions with notes
- "<next question>"
  …
```

Questions are joined with `\n` (`Tio`, L315088-315097). Partial answers recorded so far are included.

### 7.6 AFK auto-continue (`sSe`, L314587-314609; `OSe`, L315024-315041)

- **Enabled** when all of these hold (L314970-314971): not screen-reader mode, no external racer
  (bridge/channel), not a background session, and either the `askUserQuestionTimeout` setting is
  `60s`/`5m`/`10m` (`B4r`, L267729) or `CLAUDE_AFK_TIMEOUT_MS` is set. The default setting is `never`.
- **Timeout** = `CLAUDE_AFK_TIMEOUT_MS`, otherwise the setting, otherwise 60000.
- **Countdown window** = `min(CLAUDE_AFK_COUNTDOWN_MS ?? 20000, timeout)`.
- **Idle** is measured from `max(lastInteractionTime, dialogOpened)`. **While the terminal window has
  focus the clock keeps resetting** (`terminalFocus() === true`, L314599-314600), so it only runs out
  while the window is unfocused, where focus reporting exists.
- **Row**: when enabled there is always a 1-row Box below the dialog (`height:1`,
  `justifyContent:"flex-end"`). Within the countdown window it shows, right-aligned, `auto-continue in
  <n>s · any key to stay` in `inactive` + dim.
- **On timeout** it submits the answers recorded so far, with `afkTimeoutMs`. If the user interacted or
  focused the terminal while the result was being built, the auto-advance is aborted.

### 7.7 Background sessions (`Ake`, L321921-321945)

In a background session, with the dialog open, a typed prompt that does not start with `!` or `/`
answers the **first** question. A case-insensitive match against an option label becomes that label;
anything else is taken as free text.

---

## 8. The answer the model receives

### 8.1 `updatedInput` written back into the tool input (`VJ`, L315068-315077)

```ts
{ ...originalInput,          // questions (+ metadata, title if extended)
  answers: { [questionText]: string },     // only answered questions
  annotations: { [questionText]: { preview?: string; notes?: string } },
  afkTimeoutMs?: number }    // AFK path only
```

- **Keys** are the raw `question` strings.
- **Single-select**: the option's **display label** (§3.5; equal to the raw label for ordinary labels).
  Free text from Other is the typed text, `<text> (Image attached)`, or `(Image attached)`.
- **Multi-select**: `Fut(labels + otherText)`, i.e. `"A, B, my text"`. An element containing `", "` or
  `"` is JSON-quoted: `"A, \"x, y\""`.
- **Preview questions** get the selected option's label, or `(notes only)`.
- **annotations** exist only for non-screen-reader, **single-select preview questions**:
  - `preview` holds the selected option's *processed markdown* (the sanitised raw markdown, not ANSI),
    present only when that preview is `full`;
  - `notes` holds the trimmed notes, present only when non-empty.
- When a `ui.render` rewrite relabeled the options, answers are mapped back to the **original** labels
  (`f9e`, L314681-314698).
- **Pasted images** (from any question's Other input) travel as `contentBlocks`; they are not written into
  `answers`.

### 8.2 `call()` output (L838022-838028)

```ts
{ questions /* options defaulted to [] */, answers, response?, annotations?, afkTimeoutMs?, followUp? }
```

### 8.3 Result text (`mapToolResultToToolResultBlockParam`, L838029-838079), verbatim

**Summary.** For each question that has a real answer, or notes (unanswered questions are omitted), the
fragments are joined with `" "`:

```
"<question>"="<answer>"           ← or "<question>"=(no option selected)   when answer is absent or (notes only)
selected preview:\n<preview>      ← only if annotations[q].preview
notes: <notes>                    ← only if annotations[q].notes
```

The entries are joined with `", "`. Quotes inside questions or answers are **not** escaped. Example:
`"Layout?"="Sidebar" selected preview:\n+--+\n|  |\n+--+ notes: wider nav`.

**Final content**, first match wins:

1. **AFK**: `No response after <round(ms/1000)>s — the user may be away from keyboard. Proceed using your
   best judgment based on the context so far; you can re-ask this question later if it's still
   relevant.` If the summary is non-empty, add `\n\nBefore going idle the user had selected:
   <summary>.`
2. **followUp: true**, with a summary: `The user asked for more questions before you proceed. So far they
   answered: <summary>.<also> Call AskUserQuestion again with follow-up questions that build on these
   answers (do not repeat these); do not start the task yet.` Without one: `The user asked for more
   questions before answering.<also> Call AskUserQuestion again now with further questions about this
   decision (do not repeat these); do not proceed with the task yet.` Here `<also>` is
   ` They also wrote: "<response>".` when `response` is non-blank, otherwise empty.
3. **response non-blank**: `The user responded: <response>`
4. **Summary non-empty and every question "clean"**: `Your questions have been answered: <summary>. You
   can now continue with these answers in mind.` A question is clean when it has no notes and its answer
   is one of: absent; `(notes only)`; an exact option label; for multi-select, a comma list that
   round-trips through the quote-aware parser `D` (L837614) and contains only known labels; for
   extended `number`, a finite decimal within min..max. Extended `text` answers are never clean.
5. **Summary non-empty otherwise** (Other free text, any notes): `The user answered: <summary>. Read the
   answers carefully — they may request clarification, changes, or that you not proceed — and follow
   what they actually say.`
6. **Nothing**: `The user did not answer the questions.`

Consequences:

- **One real answer and three skipped questions still produce the "clean" wording.**
- A preview selection **without notes** is clean but still includes `selected preview:` with the whole
  markdown.

The auto-mode classifier sees the result as `[User answered AskUserQuestion]: <text>`. A follow-up result
is replaced there by `The user asked for more questions before answering; this is a request for another
round, not an answer.` (L732070).

### 8.4 The newer output-schema fields

| Field | Origin |
|---|---|
| `kind: "choice"\|"text"\|"number"`, plus `title`, per-question `description`, `placeholder`, `min`/`max`/`step`/`defaultValue`/`unit` | **Extended questions.** On only when `CLAUDE_CODE_QUESTION_EXTENDED` is set **and** the entrypoint is an embedding one (`sdk-ts`, `sdk-py`, `sdk-cli`, `local-agent`, `claude-desktop`, `claude-desktop-3p`) or the client is `remote`. Then the input schema is `be()` (L837881) and the prompt gains the "Extended questions" paragraph. The **terminal dialog has no text box or number control**: it draws every question as choice-style rows. A text/number question has `options: []`, so only the "Type something." and Chat rows would show [inferred]. |
| `afkTimeoutMs` | Set only by the terminal AFK path (§7.6). Absent on every human-resolved path. |
| `followUp` | Never set by the terminal dialog. It is admitted only from an external host answer, and only when every shown question carries an explicit `kind` (extended mode) (`ue`, L837753-837758). It selects the follow-up wording. |
| `response` | Never set by the terminal dialog. It is free text a host returns *instead of* structured answers (≤ 8192 chars), giving `The user responded: …`. |

**External answer admission** (`admitCardAnswer` = `L`/`ue`, L837661-837764). This applies when a host
answers through the SDK permission-prompt path in a "strict" session (`Y6o`, L777452; L371683). An answer
may **only add** `answers`, `annotations`, `response` and `followUp` to the shown input. Each
violation is refused, and the call then does not run (`The permission answer changed the tool call, and
this session runs a call only as it was asked. Nothing ran.`, L777448). Rules:

- the answer is an object;
- `afkTimeoutMs` is refused (it is a host field);
- shown fields cannot change;
- answer keys must be shown question texts;
- string answers are ≤ 8192;
- array answers are allowed only for multi-select, with at most `optionCount + 1` items, and are joined by
  `Fut`;
- `annotations[q]` may contain only `preview`, which must equal a shown preview (raw, or processed with
  ≤ 2000 chars and safe), and `notes` (≤ 8192);
- `response` is ≤ 8192;
- `followUp` must be a boolean and requires extended mode;
- total text is ≤ 32768 characters, and text plus keys stays under the result-size budget.

### 8.5 Transcript rows after resolution (chunk-se94er0s, L919759-919860)

- **Answered**: `⏺ User answered Claude's questions:`, then under a dim `  ⎿  ` one row per answer:
  `· <question> → <answer>` in `inactive`.
- **Follow-up**: the heading is `User asked Claude for more questions` or `… (so far):`. A response
  renders as `· <response>`.
- **AFK**: `⏺ Claude asked:`, the answer rows, then a dim `⏺ No response after <n>s — continued with the
  answers selected so far` (or `continued without an answer`).
- **Declined**: `⏺ User declined to answer questions`, then `· <question> (<opt> / <opt>)` in
  `inactive`.
- While pending, the tool has no tool-use row: `renderToolUseMessage → null` and `userFacingName → ""`.

---

## 9. Input validation and its errors

The schema (L837822-837881) is zod. The top-level object is **strict** (`Ge` = object with
`catchall: never`, L29585). Question and option objects are non-strict, so unknown keys there are
silently stripped.

| Constraint | Rule |
|---|---|
| `questions` | array, **min 1, max 4** |
| `options` | array, **min 2, max 4** |
| `question`, `header`, `label` | required strings, no length limit (header is truncated to 48 columns for display; the "max 12 chars" is only in the description) |
| `description` | required string in an ordinary terminal session. It is optional (lenient schema `ge()`) only when `CLAUDE_CODE_QUESTION_OPTIONAL_DESCRIPTIONS` is set under an embedding entrypoint |
| `preview` | optional string |
| `multiSelect` | boolean, default false |
| `answers` | optional; `record<string, string>`, where an array of strings is coerced by `", "`-joining **without** quoting (`we`, L837863-837877) |
| `annotations` | optional; `record<string, {preview?, notes?}>` |
| `metadata` | optional; `{source?}` |
| refinement | **question texts unique**, and **option labels unique within each question**: `Question texts must be unique, option labels must be unique within each question` |

**Error text format** (`vV`, L752079; wrapper L758973):

```
<tool_use_error>InputValidationError: [<steer>\n\n]AskUserQuestion failed due to the following issue[s]:
<issue lines></tool_use_error>
```

Issue lines take one of these shapes:

- `The required parameter `questions[0].header` is missing`
- `An unexpected parameter `foo` was provided`
- `The parameter `x` type is expected as `string` but provided as `number``
- `The parameter `questions[0].options` is invalid: <zod message>`
- for the uniqueness refinement: `The input is invalid: Question texts must be unique, option labels must
  be unique within each question`

At most 20 issues are listed, followed by `(N more issues not listed)`. The `<zod message>` wording (for
example "Too small: expected array to have >=2 items") comes from zod, and the exact phrasing is
[inferred].

**Steer** prepended when any question has fewer than 2 options (`validationErrorSteer`, L837912-837940),
verbatim:

> This call included a question with fewer than 2 options, so it was rejected and the person never saw it. A question with a single option has no decision in it. Do not retry this call and do not invent a filler second option. Instead, state the one path you were going to offer as the approach you are taking, then continue with the task. If this call also contained questions with 2 to 4 options (each with distinct labels), you may re-ask those questions alone in a new call. Ask a question only when the person has at least two genuinely distinct choices.

The extended-mode variant is at L837939.

**Extended-mode refinements** (L837826-837850) produce these messages:

- `<field> applies only to "<kind>" questions.`
- `A choice question needs 2-4 options; use kind "text" for an open-ended question.`
- `A "<kind>" question takes no options; …`
- `multiSelect applies only to choice questions, not "<kind>".`
- `A number question needs numeric min and max with min < max.`
- `defaultValue must lie within min..max.`

**`validateInput`** (L838010-838019) runs only when the preview format is `html`, which is the
SDK/desktop setting; the terminal default is `markdown`. It reports
`Option "<label>" in question "<question>": <reason>` for:

- a full document;
- `<script>`/`<style>`;
- no HTML tag.

The reason texts are at L838080-838090.

**Tool availability** (`isEnabled` → `dV`, L714208): the tool is disabled when `Ee()` holds and either
channels are active or there is no permission-prompt tool. `Ee()` is most likely "non-interactive / `-p`"
[inferred]. The 2.1.287 spec reads it the same way.

---

## 10. Plugin-facing touchpoints (pointers, not traced in full)

- **`ui.render` on component `"AskUserQuestion"`** (props `{tool, questions, metadataSource}`; d.ts
  `modules/claude-code.d.ts-5e522846.txt` L9688-9707; engine L314664-314676):
  - A hook may **rewrite** `questions` to relabel them. A rewrite cannot change the question count,
    option labels, previews, multi-select flags or uniqueness. Otherwise the engine draws the original
    and logs `ui.render (AskUserQuestion): a rewrite may relabel the questions but not …`.
  - The hook can also return its own tree instead of `next(e)`. In that case **the engine's `ESe` is not
    mounted**, so none of the key handling or answering above runs. A plugin-drawn form must then answer
    the permission itself; I did not trace the mod answer channel (`useRenderAnswer`/`submittedBy`,
    L567555-567590).
- **`$.ui.ask(question, options)`** (d.ts L2405-2418): opens this same dialog through `tool.call`. It pads
  a single option with Yes/No, truncates the header to 12 characters, and refuses more than 4 options.
- **Plugin notice row**: a per-tool-call notice (`A7e.noticesStore`, keyed by tool_use_id) is drawn under
  the dialog as one dim, right-aligned line `<plugin>: <text>` (L315042-315066).
- **Hooks answering the dialog.** The changelog says PreToolUse hooks can satisfy the call by returning
  `permissionDecision:"allow"` with an `updatedInput` that contains `answers`. In the PermissionRequest
  hook path, an `allow` **without** `updatedInput` is ignored for this tool, because
  `requiresUserInteraction` is true (L205866-205869). I did not trace the PreToolUse path.

---

## 11. What makes a cell-exact reproduction hard

1. **The markdown renderer.** The preview box shows the engine's full markdown-to-ANSI rendering: syntax
   highlighting, tables, list bullets, link handling, theme colours. A faithful copy needs that
   renderer, or an equivalent, plus the same highlighter.
2. **Ink layout semantics.** Fragment children become separate flex items. Gaps supply the
   `"❯ 1. Label"` spaces. Wrapping of long labels and descriptions is Ink's.
3. **Monotonic height lock** (`YK`), the **150 ms input grace**, and the **always-present AFK row** all
   affect the frame without being visible as content.
4. **Capture-phase keybindings.** Tab/←/→ and Select keys are user-rebindable and pre-empt the
   components, while digits, Space, `n` and the chat digit go through bubbling `onKeyDown`. The
   interaction (for example, Tab being shadowed in multi-select, and Esc in "Type something" declining the
   dialog) only reproduces with the same ordering.
5. **Layout switches per question**: standard vs preview (per question), single vs multi, and screen-reader
   variants (a different Select, a chat option inside the list, `answered` labels, no dividers).
6. **Quirks a faithful copy would inherit**, all from code and worth confirming live:
   - Enter on an empty "Type something." declines the whole dialog.
   - Enter inside multi-select Other toggles (unchecks) it.
   - Digit keys commit in the standard layout but only move the highlight in the preview layout.
   - j/k navigate in the standard and multi-select layouts, but not in the preview layout.
   - The header chip is always drawn, even for a single question.
   - The answered chip glyph is ☒, not ✔.
   - One answered question plus skipped ones still yields "Your questions have been answered".
