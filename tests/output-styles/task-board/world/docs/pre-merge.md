# Before a pull request

1. `make preflight`: lint, types, and the audits (dependencies, docs, secrets,
   CI). Fix what is yours to fix; say the rest in the pull request.
2. `make smoke-staging`, when the change touches reports or the export: every
   report type for the five largest accounts of last night's snapshot.
3. `gh pr create --fill`. CODEOWNERS assigns the reviewers.
