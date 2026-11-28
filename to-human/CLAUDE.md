# to-human/

A path here is named from `to-human/` when it is the plugin's own file; `docs/`, `scripts/` and `to-human/…` paths are the repository's.

A third plugin in this marketplace (versioned on its own: `scripts/bump-version.sh --plugin to-human`): the report view of a session under the `to-human` output style, the message tool, the notification for each message, and the reminders of how a message is sent. Mechanism lives in each module's docblocks; this file is the map, the contracts and the traps.

## Where it sits

- **A plugin of its own** because the engine runs none of a plugin's render hooks on a row that plugin submitted (the debug log's `ui.render skipped: re-entry`), and sminos and doperpowers both submit prompts (the bridge's deliveries, the ask's answers, the compact mod's resume prompt) that the view must draw.
- **Outermost.** Its place outside sminos and doperpowers comes from the owner's `prependPlugins`, not from `plugin.json`'s `dependencies` (which only installs and enables sminos with it): a dependency would seat the dependent outside its dependency only within one rank. Outermost, it sees the ask mod's rows before the ask draws them, and a step it answers reaches no hook beneath.

## Modules (`hooks/mods/`)

- `message.tsx`: the message tool, `mcp__to-human__message` (`{text, final}`, result `sent`). Its name, input, result, refusals and the log event sminos writes for it are a contract MAWS and the desk build on (design `docs/doperpowers/specs/2026-10-20-to-human-message-tool-design.md`). Registered only under the `doperpowers:to-human` style, read once at start (`getsTool`). A final message ends the turn with no request after it: `turn.step` answers the next step itself with `FINAL_ANSWER` (`registerMessage`, `endsOnFinal`, `STANDING_ATTACHMENTS`).
- `to-human.tsx`: the view, the style's consumer on every surface: marked spans drawn as the report, each run of working record between two rows the human reads folded behind one button, `/to-human-dump` for a fold drawn wrong (it writes the view's state under the configuration directory's `to-human/dumps/`).
- `folds.tsx`: the run tracker: what a fold's button reads (the live call's line, then a haiku summary; design `docs/doperpowers/specs/2026-11-12-fold-summaries-design.md`).
- `edits.tsx`: folds a run of `Edit`/`Write`/`NotebookEdit` rows into one summary line; registered from the view (`registerEdits`), beneath its hooks.
- `notify.tsx`: a `$.ui.notify` for each message sent, which the person's `Notification` hooks read as `plugin_notification`.
- `reminder.tsx`: `REMINDER` beside the first prompt past each of `REMIND_AT` (150k / 300k / 450k, the owner's points, kept rare on purpose), and `STYLE_FINAL` appended to the engine's per-request `output_style` attachment.

## Contracts with other programs

- **`MAWS_NATIVE_TO_HUMAN`**, the MAWS contract version a launch advertises, is read by four modules, each its own way: the tool registers in an interactive session unless it is a number below 8 (MAWS then registers `mcp__maws__message`), in a headless one only at 8 or more, so a session never has two message tools or none; the view steps aside off the terminal for any non-empty value that is not a number of 9 or more (`isMawsDrawing`); notifications are off for any non-empty value (MAWS is the notification surface); summaries are asked at a terminal or under a client at 8 or more, never under a set value below 8 or one that is no number (`MAWS_READS_FOLDS_FROM`, `isAsking`). Unset or empty is no MAWS.
- **`maws-surface.json`** declares `drawsFrom` to a client that reads it without running the plugin; it must equal `MAWS_DRAWS_FROM` (`tests/mods/maws-surface.ts` holds the two together).
- **A client's own rows**: a row the transcript holds no record of is asked under `<anchor>~<tag>`, placed right after its anchor (`anchorOf`, `placeAt`); `<anchor>~turn` draws only while its turn's run is unfolded and in the full transcript.
- **`$.state`** (`folds`, `fold`, `foldLast`) and **the folds file**, `to-human/folds/<session id>.json` in the configuration directory, typed in `types/to-human.d.ts` (`StoredFolds`). MAWS reads the file: it is written by atomic replacement and merged with what another process stored (`merged`), at `shape: 2`.
- **`tests/mods/fold-label-cases.json`**, which run a fold's button reads, is copied byte for byte by a client and pinned by its sha256 in `fold-label-cases.ts`: a change of the rule is a change of that file, and of the pin, first.
- **Settings**: `TO_HUMAN_FOLD_MODEL` names another summary model; `TO_HUMAN_FOLD_SUMMARIES=off` (exactly `off`) stops the asking and nothing else.

## Engine traps

- **Row ids.** A kept row and its drawing are matched by the first 24 characters of the id (`rowKey`): once a message holds more than one block, the engine draws later rows under a derived id. Any table keyed by a row's id goes through `rowKey`.
- **Draw budget.** The engine allows a draw 10 s and unloads a plugin whose draws twice overrun it, deaf to their signal; so no draw waits on I/O for long (the start-up read waits at most `START_WAIT_MS`), and a transcript search must stay cheap on a file of hundreds of MB.
- **Attachment answers are cached process-wide by UUID**, and a fork inherits main's, so a `prompt.attachment` answer cannot depend on which loop asked (`STYLE_FINAL`; the compact mod keeps the same rule).
- **The loader refuses a module that keeps the value of a function it hands `on`**, which is why the view registers `edits.tsx` and `folds.tsx` rather than taking their state back.
- **System notices** (`Prompt dropped by a hook: ...`, a plugin's `$.ui.log` line) pass through no plugin's render hook, so the view cannot hide one, and a resume draws each again; that is why the reload mod reports a reload by a toast.

## Tests

`to-human/tests/mods/run.sh` is the `to-human-mods` gate: the kit's tests, then under bun the checks a kit test cannot make (`session-places.ts`, `maws-surface.ts`, `fold-label-cases.ts`). The live checks (`live-message-check.py`, `live-final-check.py`, `live-maws-check.py`, `live-resume-check.py`, `live-reload-check.py`, `live-folds-check.py`) each drive an isolated session in a tmux pane; they are run by hand, since they spend model calls (haiku, through the gateway keys in the environment). Each file's docstring says what it pins.
