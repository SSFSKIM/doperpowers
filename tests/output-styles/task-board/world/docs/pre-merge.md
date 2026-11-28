# Before a pull request

1. `make preflight`: lint, types, and the audits (dependencies, changelog,
   secrets, CI, packaging, style). Fix what is yours to fix.
2. `make smoke-staging`, when the change touches reports or the export: every
   report type for the five largest accounts of last night's snapshot.
3. `gh pr create --fill`. CODEOWNERS assigns the reviewers.
