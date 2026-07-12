# Installing doperpowers

`doperpowers` is a two-track software-development methodology for coding agents:
a human-gated controlled track (brainstorm → plan → subagent-driven-TDD → review)
plus an autonomous board loop (`issue-tracker`, `implementing-tickets`,
`reviewing-prs`, `orchestrating-daemons`) for well-scoped, unattended work.

It ships as its own Claude Code plugin from a self-hosted marketplace in this repo,
so it installs **side by side** with any other skills marketplace you use.

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

## Coexisting with other marketplaces

Plugin identity is namespaced as `plugin@marketplace`, so `doperpowers@doperpowers`
installs alongside any other skills plugin you already have without colliding.
Adding this marketplace never replaces one you already registered.
