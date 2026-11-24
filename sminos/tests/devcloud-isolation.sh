# shellcheck shell=bash
# devcloud kept out of the sminos tests (T1's M5): sourced by every runnable
# test script, so that a script run by itself is as hermetic as the suite.
# What would ask devcloud asks the stand-in, and none of devcloud's own
# variables (its seed key, its profile, read ahead of HOME) reaches anything.
# And git's variables that select a repository, which a hook or a git alias
# exports, are removed, so a fixture's git never acts on the caller's (#623).
SMINOS_DEVCLOUD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/devcloud_standin.py"
export SMINOS_DEVCLOUD
while IFS= read -r _devcloud_var; do unset "$_devcloud_var"; done < <(compgen -e | grep '^DEVCLOUD_' || true)
unset _devcloud_var
# shellcheck disable=SC2046 # git prints one name a line
unset $(git rev-parse --local-env-vars)
