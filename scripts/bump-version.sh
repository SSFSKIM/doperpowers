#!/usr/bin/env bash
#
# bump-version.sh — bump one plugin's version across the files declared for
# it, with drift detection and a repo-wide audit for missed files.
#
# Usage:
#   bump-version.sh [--plugin NAME] <new-version>   Bump the plugin's declared files
#   bump-version.sh --check [--plugin NAME]         Report versions (detect drift); every plugin by default
#   bump-version.sh --audit [--plugin NAME]         Check + grep the plugin's tree for old version strings
#   bump-version.sh --since BASE [HEAD]             Fail when a plugin's shipped files changed since BASE
#                                                   but its version is not above BASE's (HEAD: default the working tree)
#
# .version-bump.json lists the plugins, each with its files and a field in
# each; the first listed is the default plugin. A field is a dotted path
# whose parts are keys, array indexes, or `key[name=value]`, which selects
# the one array element whose `name` is `value` — how a marketplace entry is
# addressed, so a reordered marketplace never moves the wrong version.
# A plugin's `root` (default `.`) is the directory it owns, less any nested
# plugin's root; `unshipped` lists globs, relative to the root, of the files
# that never reach a session, whose changes need no bump (`*` crosses `/`).
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

# Succeeds when version $1 is above $2, comparing X.Y.Z numerically (a
# suffix such as -rc1 is ignored).
version_gt() {
  local -a a b
  local i
  IFS=. read -r -a a <<<"${1%%[!0-9.]*}"
  IFS=. read -r -a b <<<"${2%%[!0-9.]*}"
  for i in 0 1 2; do
    ((10#${a[i]:-0} > 10#${b[i]:-0})) && return 0
    ((10#${a[i]:-0} < 10#${b[i]:-0})) && return 1
  done
  return 1
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

# The plugin's root (relative to the repo), its unshipped globs, and its
# audit's exclude patterns.
plugin_root() {
  jq -r --arg p "$1" '.plugins[] | select(.name == $p) | .root // "."' "$CONFIG"
}
unshipped_globs() {
  jq -r --arg p "$1" '.plugins[] | select(.name == $p) | .unshipped[]?' "$CONFIG"
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
  rel="$(plugin_root "$plugin")"
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

  # The marketplace updates by version number alone: a number at or below one
  # already released never installs, and main may have moved since the pull.
  local path field fullpath old_ver
  while IFS=$'\t' read -r path field; do
    old_ver=$(read_json_field "$REPO_ROOT/$path" "$field")
    if ! version_gt "$new_version" "$old_ver"; then
      echo "error: $new_version is not above $old_ver in $path; a release under a number already used never installs — bump past the current version" >&2
      exit 1
    fi
  done < <(declared_files "$plugin")

  echo "Bumping $plugin's declared files to $new_version..."
  echo ""

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

# A declared field's value at a git revision, or in the working tree when the
# revision is empty; fails when the file or the field is absent there.
field_at() {
  local rev="$1" path="$2" field="$3"
  if [[ -z "$rev" ]]; then
    [[ -f "$REPO_ROOT/$path" ]] || return 1
    read_json_field "$REPO_ROOT/$path" "$field"
    return
  fi
  git -C "$REPO_ROOT" show "$rev:$path" >"$SINCE_TMP/blob" 2>/dev/null || return 1
  read_json_field "$SINCE_TMP/blob" "$field"
}

# The marketplace updates by version number alone, so a change to a plugin's
# shipped files installs only under a version above the one its base carried:
# fail for each plugin whose shipped files differ between BASE and HEAD (the
# working tree when HEAD is empty) unless every declared version at HEAD is
# above every one at BASE.
cmd_since() {
  local base="$1" head="$2" only="$3"
  local rev
  for rev in "$base" ${head:+"$head"}; do
    if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "$rev^{commit}" >/dev/null; then
      echo "error: '$rev' is not a commit in $REPO_ROOT" >&2
      exit 1
    fi
  done
  SINCE_TMP=$(mktemp -d)
  trap 'rm -rf "$SINCE_TMP"' EXIT

  # The plugins, a nested root before the root it sits in, so that a path
  # goes to the innermost plugin that owns it.
  local -a names=() roots=() globs=() counts=() samples=()
  local name root
  while IFS=$'\t' read -r root name; do
    names+=("$name")
    roots+=("$root")
    globs+=("$(unshipped_globs "$name")")
    counts+=(0)
    samples+=("")
  done < <(for name in $(plugin_names); do printf '%s\t%s\n' "$(plugin_root "$name")" "$name"; done | sort -r)

  # Into a file, not a process substitution, so a diff that fails fails the
  # check instead of reading as no change.
  git -C "$REPO_ROOT" diff --name-only --no-renames -z "$base" ${head:+"$head"} -- >"$SINCE_TMP/changed"
  # The working tree's new files are part of its change too.
  [[ -n "$head" ]] || git -C "$REPO_ROOT" ls-files -z --others --exclude-standard >>"$SINCE_TMP/changed"
  local path rel pat i matched
  while IFS= read -r -d '' path; do
    for i in "${!names[@]}"; do
      root=${roots[i]}
      if [[ "$root" == "." ]]; then
        rel=$path
      elif [[ "$path" == "$root/"* ]]; then
        rel=${path#"$root"/}
      else
        continue
      fi
      matched=0
      while IFS= read -r pat; do
        # shellcheck disable=SC2053 # the glob is the point
        if [[ -n "$pat" && "$rel" == $pat ]]; then
          matched=1
          break
        fi
      done <<<"${globs[i]}"
      if ((matched == 0)); then
        counts[i]=$((counts[i] + 1))
        if ((counts[i] <= 3)); then
          samples[i]+="${samples[i]:+, }$rel"
        fi
      fi
      break
    done
  done <"$SINCE_TMP/changed"

  local short failed=0 any=0 field hv bv head_min head_min_path base_max more
  short=$(git -C "$REPO_ROOT" rev-parse --short "$base")
  echo "Plugins whose shipped files changed since $short (to ${head:-the working tree}):"
  echo ""
  for i in "${!names[@]}"; do
    name=${names[i]}
    [[ -z "$only" || "$name" == "$only" ]] || continue
    ((counts[i] > 0)) || continue
    any=1
    head_min="" head_min_path="" base_max=""
    while IFS=$'\t' read -r path field; do
      if ! hv=$(field_at "$head" "$path" "$field"); then
        head_min="unreadable" head_min_path=$path
        break
      fi
      if [[ -z "$head_min" ]] || version_gt "$head_min" "$hv"; then
        head_min=$hv head_min_path=$path
      fi
      if bv=$(field_at "$base" "$path" "$field" 2>/dev/null); then
        if [[ -z "$base_max" ]] || version_gt "$bv" "$base_max"; then
          base_max=$bv
        fi
      fi
    done < <(declared_files "$name")

    more=""
    ((counts[i] <= 3)) || more=", …"
    if [[ "$head_min" == "unreadable" ]]; then
      printf "  %-12s  UNREADABLE: no version in %s\n" "$name" "$head_min_path"
      failed=1
    elif [[ -z "$base_max" ]]; then
      printf "  %-12s  %s, new since %s  (%s)\n" "$name" "$head_min" "$short" "${samples[i]}$more"
    elif version_gt "$head_min" "$base_max"; then
      printf "  %-12s  %s -> %s  (%s)\n" "$name" "$base_max" "$head_min" "${samples[i]}$more"
    else
      printf "  %-12s  NOT BUMPED: %s is %s, not above %s at %s  (%s)\n" \
        "$name" "$head_min_path" "$head_min" "$base_max" "$short" "${samples[i]}$more"
      failed=1
    fi
  done
  ((any)) || echo "  (none)"

  if ((failed)); then
    echo ""
    echo "A plugin's change installs only under a version above its base's: the marketplace"
    echo "updates by number alone, and reports a reused number already installed. Bump each"
    echo "plugin marked above with scripts/bump-version.sh [--plugin NAME] <version>. A path"
    echo "that never reaches a session belongs in that plugin's \"unshipped\" list in"
    echo ".version-bump.json instead."
    return 1
  fi
}

# --- main ---

plugin=""
command=""
since_base=""
arg="" # the version to bump to, or --since's HEAD
while [[ $# -gt 0 ]]; do
  case "$1" in
    --plugin)
      [[ $# -ge 2 ]] || { echo "error: --plugin needs a name" >&2; exit 1; }
      plugin="$2"
      shift 2
      ;;
    --since)
      [[ $# -ge 2 ]] || { echo "error: --since needs a base revision" >&2; exit 1; }
      command="--since"
      since_base="$2"
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
      arg="$1"
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
  --since)
    cmd_since "$since_base" "$arg" "$plugin"
    ;;
  *)
    if [[ "$command" == "--help" || -z "$arg" ]]; then
      echo "Usage: bump-version.sh [--plugin NAME] <new-version> | --check [--plugin NAME] | --audit [--plugin NAME]"
      echo "       | --since BASE [HEAD] [--plugin NAME]"
      echo ""
      echo "  <new-version>  Bump the plugin's declared files to the given version"
      echo "  --check        Show current versions, detect drift (every plugin unless --plugin)"
      echo "  --audit        Check + scan the plugin's tree for undeclared version references"
      echo "  --since BASE   Fail when a plugin's shipped files changed since BASE without a version"
      echo "                 above BASE's; HEAD defaults to the working tree (every plugin unless --plugin)"
      echo "  --plugin NAME  The plugin, as .version-bump.json names it; default: $(plugin_names | head -1)"
      exit 0
    fi
    cmd_bump "${plugin:-$(plugin_names | head -1)}" "$arg"
    ;;
esac
