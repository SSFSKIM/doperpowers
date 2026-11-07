# Installing doperpowers

This repository is a Claude Code plugin marketplace. The three plugins the
[README](../README.md) describes install from it:

- `doperpowers`: the development methodology (skills, agents, hooks, and the
  `to-human` output style).
- `sminos`: the project family, sessions that see, message and hand work to
  each other. It stands alone.
- `to-human`: the report view for sessions under the `to-human` output style.
  It installs `sminos` with it.

The marketplace also carries `devcloud`, `web` and `ci-kit`, each opt-in and
documented in its own directory.

## Prerequisites

- **Claude Code with function hooks on.** sminos's bridge and question tool,
  the to-human view and doperpowers' own mods are function hooks, which load
  only where `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` is set. Without it the
  skills, agents, shell hooks and the sminos CLI still work.
- **Python 3.10 or later** as the first `python3` on `PATH`, for the sminos
  CLI (macOS's own `/usr/bin/python3` is 3.9).
- **GitHub CLI 2.53 or later** for the board (`issue-tracker`). It reads issue
  comments with `gh api --paginate --slurp`, and older versions reject
  `--slurp` outright. Nothing else needs it. Check with `gh --version`.

## Claude Code

```text
/plugin marketplace add SSFSKIM/doperpowers
/plugin install doperpowers@doperpowers
/plugin install sminos@doperpowers
/plugin install to-human@doperpowers
```

> **Add the marketplace with the `owner/repo` form above, not a raw URL to
> `marketplace.json`.** The doperpowers plugin's `source` is the repository
> root (`./`), so Claude Code has to clone the whole repository for that path
> to resolve. A direct URL downloads only the JSON file, and the install fails
> with "path not found".

Then, in `~/.claude/settings.json`:

```json
{
  "env": { "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1" },
  "prependPlugins": ["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"],
  "outputStyle": "doperpowers:to-human"
}
```

- `prependPlugins` sets the order of the plugins' hooks, outermost first: the
  report view sees every row before anything else draws it, and sminos's
  bridge sits outside every other plugin's hooks, a secrets guard's included.
  A plugin dependency cannot place them there; this list does.
- `outputStyle` is optional. Under `doperpowers:to-human` the session writes
  you a report through its message tool; without it you read the transcript
  as usual. It can also be set per launch.

sminos works within one machine as soon as it is installed. To span machines,
a project needs a git mirror, or the machine enrolled at the desk hub through its MAWS endpoint:
[sminos's setup guide](../sminos/skills/sminos/references/setup.md).

## Updating

```text
/plugin marketplace update doperpowers
/plugin install doperpowers@doperpowers
```

and likewise for `sminos@doperpowers` and `to-human@doperpowers`. With
auto-update on for this marketplace, doperpowers' reload hook applies an
update another session installed to every running session once it is idle,
so you don't run `/reload-plugins` in each.

## Coexisting with other marketplaces

A plugin's identity is `plugin@marketplace`, so `doperpowers@doperpowers`
installs beside any other skills plugin you have without colliding, and adding
this marketplace never replaces one you already registered.

## Codex

The skills also ship as a local Codex plugin manifest in
[`.codex-plugin/`](../.codex-plugin/), and the agent definitions have native
Codex ports with their own install guide in
[`codex/agents/`](../codex/agents/README.md). sminos and to-human are Claude
Code only.
