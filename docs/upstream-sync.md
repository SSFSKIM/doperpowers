# Taking commits from upstream

This fork takes upstream's commits one by one and never merges or rebases
`upstream/main` (the rule and its reason are in the root `CLAUDE.md`).

```
origin    → https://github.com/SSFSKIM/doperpowers.git   (this fork)
upstream  → https://github.com/obra/superpowers.git      (the source project)
```

```bash
git fetch upstream --tags
git log --oneline HEAD..upstream/main                    # what's outstanding
git rev-list --left-right --count upstream/main...HEAD   # behind / ahead
git diff $(git merge-base upstream/main HEAD) HEAD -- <path>   # has the fork touched this file?
```

Triage each candidate commit: files still byte-identical to the merge base can be
taken wholesale; files the fork rewrote need a re-graft or a decline. Rebrand on
import (`superpowers:` → `doperpowers:`, `.superpowers/` → `.doperpowers/`,
`docs/superpowers/` → `docs/doperpowers/`) and grep for residual `superpowers`
afterward. Commits touching mechanisms this fork removed — the `hooks/` bootstrap,
the Gemini CLI adapter, Codex portal packaging, the other harness adapters — are
irrelevant.
