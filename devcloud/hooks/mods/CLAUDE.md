# devcloud/hooks/mods/ — the devcloud plugin's secrets guard

A path here is named from `devcloud/` when it is the plugin's own file; `devcloud/…` paths are the repository's.

Today its secrets guard mod, `hooks/mods/secrets.tsx` (pure parts beside it: `secrets-detect.tsx` the token detector, `secrets-handles.tsx` the handles and their restoration, `secrets-sources.tsx` the store layout and credential-file parsers, `secrets-shell.tsx` when a value may be restored into a Bash command — inert, in a plain string or word, in a plain command, never quoted — and `secrets-reads.tsx` the exact read a notice names where it is not, both proved by `devcloud/tests/mods/shell-exec.ts` under bash and zsh): stored `/secret` values (cua's store, read here), credential-file values and token-shaped strings become handles (`[secret:KEY]`, `[redacted:<kind>#<ns>.<n>]`, ...) in tool results and their records, every appended row, oversized outputs' `tool-results/` files, the system prompt's sections, context blocks, attachments and compactions; handles in Write/Edit/MultiEdit/NotebookEdit/Bash input are restored to their bytes before the call runs; nothing is refused. Its guard marker (`devcloud.secrets-guard`, typed in `types/devcloud.d.ts`) is the loaded module's own answer to a `$.state.get` (a `state.get` hook, at version 0), never a stored value, so `cua`'s vendored copy stands down exactly while devcloud's module is in the chain and acts once it is gone (board #101). What it does not reach is listed in `devcloud/README.md`. Tests `devcloud/tests/mods/run.sh` (the `devcloud-mods` gate).

Installed-source provenance is split between `secrets-provenance.py` (explicit
public-artifact indexing, SQLite cache, bounded local verification) and
`secrets-provenance.tsx` (whole-stage deadline, native Read rendering binding,
module-private one-use append receipts). `devcloud guard index --fetch` is the
manual refresh; a supported unchanged Read skips only generic assignments in
its verified source slice. Stronger detections still apply. Unchanged results
retain core's `ref` and pagination companion; rewritten results remap without
it. Missing evidence loses preservation, not the Read. gcloud evidence uses
the exact public SDK release and component archive, not equality with local
component build stamps; those snapshots remain freshness markers.

`secrets-provenance-corpus.mjs` is an out-of-band Bun driver for
`guard report-corpus` / `guard index --report-corpus`: it runs the production
tool and append hooks over supported partial-read fixtures and prints only
aggregate coverage/loss counts. It is not imported by the hooks. Actual native
mapping, pagination, transcript storage and process timeout/abort cleanup are
proved by `devcloud/tests/mods/provenance_probe.py`, using an isolated synthetic
session and a loopback endpoint under a macOS network sandbox. The Python
index/report regressions live in `devcloud/tests/mods/provenance_index_test.py`.
