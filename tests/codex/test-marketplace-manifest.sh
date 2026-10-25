#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MARKETPLACE="$REPO_ROOT/.agents/plugins/marketplace.json"

python3 - "$MARKETPLACE" "$REPO_ROOT" <<'PY'
import json
import sys
from pathlib import Path

marketplace_path = Path(sys.argv[1])
repo_root = Path(sys.argv[2])

if not marketplace_path.exists():
    raise AssertionError(".agents/plugins/marketplace.json must exist")

marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))

def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")

assert_equal(marketplace.get("name"), "doperpowers-dev", "marketplace name")
assert_equal(
    marketplace.get("interface", {}).get("displayName"),
    "Doperpowers Dev",
    "marketplace display name",
)

plugins = marketplace.get("plugins")
if not isinstance(plugins, list):
    raise AssertionError("plugins must be a list")

matching_plugins = [plugin for plugin in plugins if plugin.get("name") == "doperpowers"]
assert_equal(len(matching_plugins), 1, "doperpowers plugin entry count")

plugin = matching_plugins[0]
assert_equal(plugin.get("source"), {"source": "url", "url": "./"}, "plugin source")
assert_equal(
    plugin.get("policy"),
    {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "plugin policy",
)
assert_equal(plugin.get("category"), "Developer Tools", "plugin category")

plugin_manifest = repo_root / ".codex-plugin" / "plugin.json"
if not plugin_manifest.exists():
    raise AssertionError(".codex-plugin/plugin.json must exist")

manifest = json.loads(plugin_manifest.read_text(encoding="utf-8"))
assert_equal(manifest.get("name"), plugin.get("name"), "plugin manifest name")
assert_equal(
    manifest.get("hooks"),
    None,
    "Codex manifest ships no hooks",
)

print("Codex marketplace manifest looks good")
PY

# The Claude Code marketplace: each plugin this repository ships (a relative
# source) is found by its name, never its place in the list, and its entry
# names the version its own plugin.json carries.
python3 - "$REPO_ROOT" <<'PY'
import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
marketplace = json.loads((repo_root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
plugins = marketplace.get("plugins")
if not isinstance(plugins, list):
    raise AssertionError("plugins must be a list")

def entry(name):
    found = [p for p in plugins if p.get("name") == name]
    if len(found) != 1:
        raise AssertionError(f"{name}: expected one marketplace entry, found {len(found)}")
    return found[0]

expected_sources = {"doperpowers": "./", "devcloud": "./devcloud", "sminos": "./sminos", "web": "./web"}
for name, source in expected_sources.items():
    if entry(name).get("source") != source:
        raise AssertionError(f"{name}: source {entry(name).get('source')!r}, expected {source!r}")

for plugin in plugins:
    source = plugin.get("source")
    if not isinstance(source, str):
        continue  # another repository's plugin (a URL source) carries its own version
    manifest = json.loads((repo_root / source / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    name = plugin.get("name")
    if manifest.get("name") != name:
        raise AssertionError(f"{name}: plugin.json at {source} is named {manifest.get('name')!r}")
    if manifest.get("version") != plugin.get("version"):
        raise AssertionError(f"{name}: marketplace version {plugin.get('version')!r}, plugin.json {manifest.get('version')!r}")

print("Claude marketplace manifest looks good")
PY
