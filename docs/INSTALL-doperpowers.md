# Installing doperpowers

`doperpowers` is a personal fork of [Superpowers](https://github.com/obra/superpowers)
by Jesse Vincent (MIT-licensed), with fork-specific skills such as
`orchestrating-daemons`, `issue-register`, `codebase-design`, and `domain-modeling`
on top of the full brainstorm → plan → subagent-driven-TDD → review methodology.

It ships as its own Claude Code plugin from a self-hosted marketplace in this repo,
so it installs **side by side** with upstream Superpowers.

## Claude Code

```text
/plugin marketplace add SSFSKIM/doperpowers
/plugin install doperpowers@doperpowers
```

> **Add via the `owner/repo` form above — not a raw URL to `marketplace.json`.**
> The plugin's `source` is the repo root (`./`), so Claude must clone the whole
> repository for that relative path to resolve. A direct URL downloads only the
> JSON file and the install fails with "path not found".

Update later:

```text
/plugin marketplace update doperpowers
/plugin install doperpowers@doperpowers
```

## Coexisting with upstream

Plugin identity is namespaced as `plugin@marketplace`, so `doperpowers@doperpowers`
and any upstream `superpowers@superpowers-marketplace` (or
`superpowers@claude-plugins-official`) can both be installed at once without
colliding. The marketplace name (`doperpowers`) is distinct from upstream's
`superpowers-dev`, so adding this one never replaces upstream's.
