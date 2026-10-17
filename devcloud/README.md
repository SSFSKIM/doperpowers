# devcloud

A second plugin in the doperpowers marketplace, installed on its own
(`claude plugin install devcloud@doperpowers`): doperpowers stays the
workflow plugin, and a person opts into devcloud. Today it carries the
secrets guard; the host image and boot program that make any Linux userland
work like the person's Mac, and the `devenv` skill, follow (design:
`docs/doperpowers/specs/2026-10-15-devcloud-design.md`).

## The secrets guard (`hooks/mods/secrets.tsx`)

A mod (a function hooks module, loaded under
`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`) that keeps secrets out of what the
model reads and what the transcript keeps. It redacts and never refuses: no
tool call is denied for touching the secret store, so `cat`, `ls`, `mv`,
`test -f` and writes there all run, and a value a command prints is caught
in its output.

**What it knows.** Three sources, read again whenever a file changes:

- the values stored through `cua`'s `/secret` (`~/.config/claude-secrets/KEY`
  for every project, `~/.config/claude-secrets/projects/<slug>/KEY` for one;
  one trailing newline dropped), the project being the main checkout of the
  git repository around the session;
- the secret fields of well-known credential files under `$HOME`: gh's
  `hosts.yml`, `~/.pgpass`, gcloud's service-account and authorized-user key
  files under `~/.config/gcloud/`, `~/.codex/auth.json`,
  `~/.claude/.credentials.json`, hcloud's `cli.toml`, `~/.docker/config.json`'s
  auths, `~/.netrc`, `~/.git-credentials`, `~/.npmrc`;
- token-shaped strings anywhere (`hooks/mods/secrets-detect.tsx`, a pure
  `detect(text)`): published prefixes after gitleaks' rules (`sk-ant-`,
  `sk-or-v1-`, `sk-`, `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`,
  `tskey-`, `xox[abprs]-`, `AKIA`/`ASIA`, `glpat-`, `hf_`, `AIza`), PEM
  private-key blocks raw or JSON-escaped, and assignments whose name says
  secret (`TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`, `APIKEY`,
  `PRIVATE_KEY`, `BEARER`, `CREDENTIAL`, any case, as a whole part of the
  name split at `_`, `-`, `.` or a camelCase boundary; `Bearer <value>` too)
  whose value is at least 16 characters of at least 3.5 bits of entropy per
  character. Bare hex or base64 is never a token: commit hashes and checksums
  stay readable.

**Handles.** Each distinct redacted byte string gets its own:

    [secret:KEY]                  a stored value (the project's, where both tiers hold KEY)
    [secret:KEY@global]           a global value a project key of the same name shadows
    [secret:<file>:<field>]       a credential file's value (the file's basename, or its
                                  path from $HOME where two files share one)
    ...~<enc>]                    an encoded spelling of any of those: ~b64, ~b64np (no
                                  padding), ~b64u, ~b64up, ~hex, ~HEX, ~url, ~json
    [superseded:<label>]          a value a label held earlier in this process
    [redacted:<kind>#<ns>.<n>]    a pattern detection; <ns> is drawn when the module loads

Before a Write, Edit, MultiEdit, NotebookEdit or Bash call runs, each handle
in its input is replaced by its bytes: a known handle by the credential's
current value in the named spelling, a pattern handle by exactly the bytes
it replaced, if this process issued it. So a file edited through a handle
keeps its secret, and `Authorization: Bearer [secret:KEY]` in a command works
like `"$(cat ~/.config/claude-secrets/KEY)"`. A handle that cannot be
restored — `[superseded:…]`, a key no longer stored, another process's (or a
resumed session's earlier) pattern handle — is written as is, and the tool's
result carries a line naming it. The transcript keeps the call as the model
wrote it, handles and all. One system-prompt section tells the model this.

**Where it reaches** (the guarantee): a tool's result as the model reads it
and as the transcript keeps it (`toolUseResult`), in the main loop and in
subagents; every row appended to the conversation (the person's prompt, a
background command's notification, a subagent's result); an oversized
output's file in the session's `tool-results/`, rewritten before the call
returns (in place, or past 4 MiB through a `.tmp` file renamed over it) (the session store ships such a file only once it has held
still for 3 s); the system prompt's composed sections; the first message's
context blocks (`CLAUDE.md`); each attachment's text as a request carries
it; a compaction's instructions and its summary.

**Where it does not** (probed 2026-10-17 on Claude Code 2.1.302):

- an attachment row's own payload in the transcript file: a changed file the
  model had read, and the files the engine attaches again after a compaction
  (a background command's output file among them), keep their content there
  beside the scrubbed text the model reads, so the session store's copy holds
  it too;
- system-prompt text given with `--system-prompt` or `--append-system-prompt`,
  which the engine adds after composing the sections: every request carries
  it, and the transcript's `prompt_snapshot` and `api-request-shape` rows keep
  it;
- a background command's own output file in the engine's temporary
  directory (local, never shipped; the model reads it only through a tool,
  scrubbed);
- the call a restored handle runs in: the permission dialog shows it; in
  auto mode, a call the mode sends to its classifier is judged with its
  values in place, and the classifier is a model request of its own (observed
  for a Write; the permission check's input is pinned, so no hook can hand it
  the handles); and a command's arguments are visible to the machine's other
  processes while it runs;
- where an organization manages Claude Code, a plugin a person installs does
  not get `prompt.compose`, `prompt.context`, `prompt.attachment` or
  `session.compact`: the system prompt, context blocks, attachments and
  compactions are then not covered;
- a value the model slices, reverses or transforms on purpose; a secret
  inside an image; an oversized output whose process is killed between the
  engine writing it and the guard rewriting it.

**With `cua`.** `/secret` — the command, its masked pane, the store and the
system-prompt section listing the stored keys — stays in `cua`. When a
session starts, devcloud sets its guard marker in `$.state`
(`{ plugin: 'devcloud', key: 'secrets-guard' }` → `{ owner: 'devcloud',
version: 1 }`, typed in `types/devcloud.d.ts`): every plugin in the session
reads it, only devcloud writes it, and a `claude` a tool call starts has a
session of its own. `cua`'s scrubbing stands down while it is set, so one
guard decides every handle. (A `globalThis` symbol does not work: the engine
evaluates each plugin's module in a realm of its own.)

## Developing

    devcloud/tests/mods/run.sh                                 # the mod's tests
    claude plugin validate devcloud/.claude-plugin/plugin.json
    npx -p typescript@5 tsc -p devcloud/hooks/mods/tsconfig.json
    claude --plugin-dir devcloud                               # the working tree as the plugin

Typechecking reads `.claude/types/claude-code.d.ts` at the repository root,
as doperpowers' own mods do. Versions: `scripts/bump-version.sh --plugin
devcloud <version>` moves devcloud's `plugin.json` and its marketplace entry,
never doperpowers'.
