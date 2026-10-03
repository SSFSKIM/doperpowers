# Validating a doperpowers change

- [ ] `scripts/lint-shell.sh` passes for the shell files you changed.
- [ ] `cd application-agents/triaging-feedback && npm test` passes if you touched that directory.
- [ ] `tests/mods/run-mods-tests.sh` passes if you touched `hooks/mods/` or `tests/mods/`.
- [ ] `tests/sminos/run-sminos-tests.sh` passes if you touched `skills/sminos/`.
- [ ] A changed skill was exercised (`doperpowers:writing-skills`), and its area's tests under
      `tests/` pass.
- [ ] The version is bumped with `scripts/bump-version.sh` when the plugin's content changed.
