#!/usr/bin/env bash
#
# bump-version.sh — bump one plugin's version across the files declared for
# it, with drift detection and a repo-wide audit for missed files.
#
# Usage:
#   bump-version.sh [--plugin NAME] <new-version>   Bump the plugin's declared files
#   bump-version.sh --check [--plugin NAME]         Report versions (detect drift); every plugin by default
#   bump-version.sh --audit [--plugin NAME]         Check + grep the plugin's tree for old version strings
#
# .version-bump.json lists the plugins, each with its files and a field in
# each; the first listed is the default plugin. A field is a dotted path
# whose parts are keys, array indexes, or `key[name=value]`, which selects
# the one array element whose `name` is `value` — how a marketplace entry is
# addressed, so a reordered marketplace never moves the wrong version.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="$REPO_ROOT/.version-bump.json"

if [[ ! -f "$CONFIG" ]]; then
  echo "error: .version-bump.json not found at $CONFIG" >&2
  exit 1
fi

# --- helpers ---

# A dotted field path as a jq path expression:
#   "version" -> .version
#   "plugins.0.version" -> .plugins[0].version
#   "plugins[name=devcloud].version" -> .plugins[] | select(.name == "devcloud") | .version
jq_path() {
  local field="$1" part expr="" IFS='.'
  local -a parts
  read -r -a parts <<<"$field"
  for part in "${parts[@]}"; do
    if [[ "$part" =~ ^([A-Za-z0-9_-]+)\[([A-Za-z0-9_-]+)=([^]]+)\]$ ]]; then
      expr+=".${BASH_REMATCH[1]}[] | select(.${BASH_REMATCH[2]} == \"${BASH_REMATCH[3]}\") | "
    elif [[ "$part" =~ ^[0-9]+$ ]]; then
      expr="${expr% | }[$part] | "
    else
      expr+=".$part | "
    fi
  done
  printf '%s' "${expr% | }" | sed 's/^| //'
}

# Read a field from a JSON file; fails unless the path finds exactly one value.
read_json_field() {
  local file="$1" field="$2" path count
  path=$(jq_path "$field")
  count=$(jq "[$path] | length" "$file") || return 1
  if [[ "$count" != "1" ]]; then
    echo "error: $field finds $count values in $file, not one" >&2
    return 1
  fi
  jq -r "$path" "$file"
}

# Write a field in a JSON file.
write_json_field() {
  local file="$1" field="$2" value="$3" path
  path=$(jq_path "$field")
  local tmp="${file}.tmp"
  jq --arg v "$value" "($path) |= \$v" "$file" >"$tmp" && mv "$tmp" "$file"
}

plugin_names() {
  jq -r '.plugins[].name' "$CONFIG"
}

# Fail unless the plugin is declared.
require_plugin() {
  if ! plugin_names | grep -qxF "$1"; then
    echo "error: no plugin '$1' in .version-bump.json (declared: $(plugin_names | paste -sd, -))" >&2
    exit 1
  fi
}

# The plugin's declared files, as lines of "path<TAB>field".
declared_files() {
  jq -r --arg p "$1" '.plugins[] | select(.name == $p) | .files[] | "\(.path)\t\(.field)"' "$CONFIG"
}

# The plugin's audit root (relative to the repo) and exclude patterns.
audit_root() {
  jq -r --arg p "$1" '.plugins[] | select(.name == $p) | .audit.root // "."' "$CONFIG"
}
audit_excludes() {
  jq -r --arg p "$1" '.plugins[] | select(.name == $p) | .audit.exclude[]?' "$CONFIG"
}

# Verify every declared manifest of the plugin is readable before writing
# any — a bump either lands everywhere or touches nothing.
preflight_manifests() {
  local plugin="$1" path field fullpath
  while IFS=$'\t' read -r path field; do
    fullpath="$REPO_ROOT/$path"
    if [[ ! -f "$fullpath" ]]; then
      echo "error: declared manifest missing: $path" >&2
      return 1
    fi
    if ! read_json_field "$fullpath" "$field" >/dev/null; then
      echo "error: cannot read declared manifest: $path ($field)" >&2
      return 1
    fi
  done < <(declared_files "$plugin")
}

# --- commands ---

check_plugin() {
  local plugin="$1" has_drift=0 path field fullpath ver
  local -a versions=()

  echo "Version check: $plugin"
  echo ""
  while IFS=$'\t' read -r path field; do
    fullpath="$REPO_ROOT/$path"
    if [[ ! -f "$fullpath" ]] || ! ver=$(read_json_field "$fullpath" "$field" 2>/dev/null); then
      printf "  %-60s  MISSING\n" "$path ($field)"
      has_drift=1
      continue
    fi
    printf "  %-60s  %s\n" "$path ($field)" "$ver"
    versions+=("$ver")
  done < <(declared_files "$plugin")
  echo ""

  local unique
  unique=$(printf '%s\n' "${versions[@]+"${versions[@]}"}" | sed '/^$/d' | sort -u | wc -l | tr -d ' ')
  if [[ "$unique" -gt 1 ]]; then
    echo "DRIFT DETECTED — versions are not in sync:"
    printf '%s\n' "${versions[@]}" | sort | uniq -c | sort -rn | while read -r count v; do
      echo "  $v ($count files)"
    done
    has_drift=1
  elif [[ "$unique" -eq 1 ]]; then
    echo "All declared files are in sync at ${versions[0]}"
  fi
  return $has_drift
}

cmd_check() {
  local plugin="${1:-}" has_drift=0 name
  if [[ -n "$plugin" ]]; then
    check_plugin "$plugin"
    return
  fi
  while IFS= read -r name; do
    check_plugin "$name" || has_drift=1
    echo ""
  done < <(plugin_names)
  return $has_drift
}

cmd_audit() {
  local plugin="$1"
  check_plugin "$plugin" || true
  echo ""

  # The current version: the most common across the plugin's declared files.
  local current_version
  current_version=$(
    while IFS=$'\t' read -r path field; do
      local fullpath="$REPO_ROOT/$path"
      [[ -f "$fullpath" ]] && read_json_field "$fullpath" "$field" 2>/dev/null
    done < <(declared_files "$plugin") | sort | uniq -c | sort -rn | head -1 | awk '{print $2}'
  )

  if [[ -z "$current_version" ]]; then
    echo "error: could not determine current version" >&2
    return 1
  fi

  local root rel
  rel="$(audit_root "$plugin")"
  root="$REPO_ROOT"
  [[ "$rel" == "." ]] || root="$REPO_ROOT/$rel"
  echo "Audit: scanning $rel for version string '$current_version'..."
  echo ""

  local -a exclude_args=()
  while IFS= read -r pattern; do
    exclude_args+=("--exclude=$pattern" "--exclude-dir=$pattern")
  done < <(audit_excludes "$plugin")
  exclude_args+=("--exclude-dir=.git" "--exclude-dir=node_modules" "--binary-files=without-match")

  local -a declared_paths=()
  while IFS=$'\t' read -r path _field; do
    declared_paths+=("$path")
  done < <(declared_files "$plugin")

  local found_undeclared=0
  while IFS= read -r match; do
    local match_file rel_path is_declared=0
    match_file=$(echo "$match" | cut -d: -f1)
    rel_path="${match_file#"$REPO_ROOT"/}"
    for dp in "${declared_paths[@]}"; do
      if [[ "$rel_path" == "$dp" ]]; then
        is_declared=1
        break
      fi
    done
    if [[ "$is_declared" -eq 0 ]]; then
      if [[ "$found_undeclared" -eq 0 ]]; then
        echo "UNDECLARED files containing '$current_version':"
        found_undeclared=1
      fi
      echo "  $match"
    fi
  done < <(grep -rn "${exclude_args[@]}" -F "$current_version" "$root" 2>/dev/null || true)

  if [[ "$found_undeclared" -eq 0 ]]; then
    echo "No undeclared files contain the version string. All clear."
  else
    echo ""
    echo "Review the above files — if they should be bumped, add them to .version-bump.json"
    echo "If they should be skipped, add them to the plugin's audit.exclude list."
  fi
}

cmd_bump() {
  local plugin="$1" new_version="$2"

  if ! echo "$new_version" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+'; then
    echo "error: '$new_version' doesn't look like a version (expected X.Y.Z)" >&2
    exit 1
  fi

  preflight_manifests "$plugin"

  echo "Bumping $plugin's declared files to $new_version..."
  echo ""

  local path field fullpath old_ver
  while IFS=$'\t' read -r path field; do
    fullpath="$REPO_ROOT/$path"
    old_ver=$(read_json_field "$fullpath" "$field")
    write_json_field "$fullpath" "$field" "$new_version"
    printf "  %-60s  %s -> %s\n" "$path ($field)" "$old_ver" "$new_version"
  done < <(declared_files "$plugin")

  echo ""
  echo "Done. Running audit to check for missed files..."
  echo ""
  cmd_audit "$plugin"
}

# --- main ---

plugin=""
command=""
version=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --plugin)
      [[ $# -ge 2 ]] || { echo "error: --plugin needs a name" >&2; exit 1; }
      plugin="$2"
      shift 2
      ;;
    --check | --audit)
      command="$1"
      shift
      ;;
    --help | -h)
      command="--help"
      shift
      ;;
    --*)
      echo "error: unknown flag '$1'" >&2
      exit 1
      ;;
    *)
      version="$1"
      shift
      ;;
  esac
done

[[ -z "$plugin" ]] || require_plugin "$plugin"

case "$command" in
  --check)
    cmd_check "$plugin"
    ;;
  --audit)
    cmd_audit "${plugin:-$(plugin_names | head -1)}"
    ;;
  *)
    if [[ "$command" == "--help" || -z "$version" ]]; then
      echo "Usage: bump-version.sh [--plugin NAME] <new-version> | --check [--plugin NAME] | --audit [--plugin NAME]"
      echo ""
      echo "  <new-version>  Bump the plugin's declared files to the given version"
      echo "  --check        Show current versions, detect drift (every plugin unless --plugin)"
      echo "  --audit        Check + scan the plugin's tree for undeclared version references"
      echo "  --plugin NAME  The plugin, as .version-bump.json names it; default: $(plugin_names | head -1)"
      exit 0
    fi
    cmd_bump "${plugin:-$(plugin_names | head -1)}" "$version"
    ;;
esac
