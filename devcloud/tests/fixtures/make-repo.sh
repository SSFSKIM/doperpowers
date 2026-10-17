#!/usr/bin/env bash
# Builds the stand-in configuration repository the fakes serve: main holds
# /fixtures/config as it is; each variant branch changes one thing for a
# failure case. Run in the fixtures container; the tests then commit to the
# work tree at /srv/work and push to change the profile.
set -euo pipefail

work=/srv/work
rm -rf /srv/git/config.git "$work"
git init -q --bare -b main /srv/git/config.git
cp -R /fixtures/config "$work"
mv "$work/gitignore" "$work/.gitignore"
cd "$work"
git init -q -b main
git config user.name fixtures
git config user.email fixtures@example.com
git add -A
git commit -qm "stand-in profile"
git remote add origin /srv/git/config.git
git push -q origin main

variant() {
  git checkout -q -B "$1" main
  "${@:2}"
  git commit -qam "$1"
  git push -q origin "$1"
  git checkout -q main
}
add_secret() { printf '\n[[secret]]\nname = "%s"\nstore = "%s"\n%s\n' "$1" "$2" "${3:-}" >> devcloud/secrets.toml; }
variant optional-missing add_secret not-uploaded-yet LATER "optional = true"
variant required-missing add_secret not-uploaded-yet LATER
variant gateway-down sed -i 's#http://fixtures:8084#http://fixtures:9#' devcloud/managed-settings.json
# An apply step that prints a materialized secret, plain and base64, then fails.
leak_apply() {
  cat >> sync/apply.py <<'PY'
import base64
import sys
value = (pathlib.Path.home() / ".config/claude-secrets/GH_TOKEN").read_text()
print("leaking", value)
print("leaking b64", base64.b64encode(value.encode()).decode(), file=sys.stderr)
sys.exit(1)
PY
}
variant apply-leaks leak_apply
