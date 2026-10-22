#!/usr/bin/env bash
# Builds the stand-in configuration repository the fakes serve: main holds
# /fixtures/config as it is; each variant branch changes one thing for a
# failure case. Run in the fixtures container; the tests then commit to the
# work tree at /srv/work and push to change the profile. Beside it, two project
# repositories standing in for GitHub's: example/app, a small one carrying
# devenv/, and example/doperpowers, the checkout under test (mounted at /repo)
# with its commit as branch under-test.
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
# The synced settings of the Macs, in brief: the doperpowers marketplace declared
# (here the checkout under test, served as example/doperpowers), the function
# hooks on, devcloud enabled; and an apply step that adds the marketplace from
# the declared source and installs its plugins, as the real one does.
plugins_profile() {
  python3 - <<'PY'
import json
settings = json.load(open("settings.json"))
settings["env"]["CLAUDE_CODE_ENABLE_FUNCTION_HOOKS"] = "1"
settings["enabledPlugins"] = {"devcloud@doperpowers": True}
settings["extraKnownMarketplaces"] = {"doperpowers": {"source": {
    "source": "git", "url": "http://fixtures:8083/example/doperpowers.git"}}}
json.dump(settings, open("settings.json", "w"), indent=2)
PY
  cat >> sync/apply.py <<'PY'
import json
import subprocess
plugins_dir = pathlib.Path.home() / ".claude/plugins"
def known(name):
    try:
        return json.loads((plugins_dir / name).read_text())
    except (OSError, ValueError):
        return {}
declared = json.loads((pathlib.Path.home() / ".claude/settings.json").read_text())["extraKnownMarketplaces"]
with open(state / "apply.log", "a") as log:
    if "doperpowers" not in known("known_marketplaces.json"):
        add = subprocess.run(["claude", "plugin", "marketplace", "add", declared["doperpowers"]["source"]["url"]],
                             capture_output=True, text=True, timeout=300)
        log.write(f"marketplace add exited {add.returncode}\n")
    if "doperpowers" in known("known_marketplaces.json"):
        installed = known("installed_plugins.json").get("plugins", {})
        for plugin in ("to-human", "sminos", "doperpowers", "devcloud"):
            if f"{plugin}@doperpowers" not in installed:
                done = subprocess.run(["claude", "plugin", "install", f"{plugin}@doperpowers", "--scope", "user", "-y"],
                                      capture_output=True, text=True, timeout=300)
                log.write(f"install {plugin} exited {done.returncode}\n")
PY
}
variant plugins plugins_profile

# --- the project repositories ---------------------------------------------------
app=/srv/app-work
rm -rf "$app" /srv/git/example
mkdir -p "$app/devenv" /srv/git/example
cat > "$app/devenv/setup.sh" <<'SH'
#!/usr/bin/env bash
# devenv-inputs: app.lock
set -eu
state="$HOME/.local/state/devcloud-test"
mkdir -p "$state"
echo "setup as $(id -un) in $PWD api-key=${EXAMPLE_API_KEY:+set}" >> "$state/app-setup.log"
SH
echo v1 > "$app/app.lock"
git -C "$app" init -q -b main
git -C "$app" -c user.name=fixtures -c user.email=fixtures@example.com add -A
git -C "$app" -c user.name=fixtures -c user.email=fixtures@example.com commit -qm "app with devenv/"
git clone -q --bare "$app" /srv/git/example/app.git

if [ -e /repo/.git ]; then
  git config --global --add safe.directory '*'
  # A fetch of HEAD, which works whether the checkout is detached or shallow.
  git init -q --bare -b under-test /srv/git/example/doperpowers.git
  git -C /srv/git/example/doperpowers.git fetch -q --no-tags --update-shallow /repo +HEAD:refs/heads/under-test
fi
