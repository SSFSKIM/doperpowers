#!/usr/bin/env bash
# devcloud's host tests: the unit tests of the boot program's library, then
# the image built from image/Dockerfile and booted in containers against
# stand-ins (tests/integration.py). Needs Docker, Python 3.11+ and bun (the
# unit tests and the image scan run the secrets guard's detector). Every case
# prints "ok".
#
# DEVCLOUD_PART picks one part, for a CI gate each: `unit` is the unit tests
# alone; `image`, `host` and `systemd` are the image built and one part of the
# integration cases (integration.py's PARTS). Unset runs everything.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

DEVCLOUD_PART="${DEVCLOUD_PART:-all}"
case "$DEVCLOUD_PART" in all | unit | image | host | systemd) ;; *) echo "DEVCLOUD_PART is all, unit, image, host or systemd" >&2; exit 2 ;; esac
export DEVCLOUD_PART

if [ "$DEVCLOUD_PART" = all ] || [ "$DEVCLOUD_PART" = unit ]; then
  echo "== unit"
  python3 -m unittest discover -s devcloud/tests/unit
fi
[ "$DEVCLOUD_PART" = unit ] && exit 0

echo "== image"
image="devcloud-test:$$"
log="$(mktemp)"
trap 'docker rmi -f "$image" >/dev/null 2>&1 || true; rm -f "$log"' EXIT
# In a CI gate with ci-kit's build_cache, the layers come from the GitHub
# Actions cache, a scope per ISO week: packages.sh installs the latest releases,
# so a cache keyed on the files alone would never refresh them. Only a run on
# the default branch writes it (ci-kit sets CI_KIT_BUILD_CACHE_WRITE there: the
# weekly schedule in ci.yml seeds each week's scope, and a merge to main that
# changes the gates' paths seeds it again). Of the three gates that share the
# scope, only the image part writes it: the package layer does not build byte
# for byte the same, so each writer would upload its own copy, three per seed,
# into the repository's 10 GB. host and systemd read what it wrote. The layers
# are zstd, which the runner's daemon exports and unpacks faster than gzip.
cache=()
if [ "${CI_KIT_BUILD_CACHE:-}" = gha ]; then
  scope="devcloud-image-$(date -u +%G-W%V)"
  cache=(--output "type=image,compression=zstd,oci-mediatypes=true" --cache-from "type=gha,scope=$scope")
  if [ -n "${CI_KIT_BUILD_CACHE_WRITE:-}" ] && { [ "$DEVCLOUD_PART" = image ] || [ "$DEVCLOUD_PART" = all ]; }; then
    cache+=(--cache-to "type=gha,mode=min,scope=$scope,compression=zstd,ignore-error=true")
  fi
fi
if ! docker build --progress=plain ${cache[@]+"${cache[@]}"} -t "$image" -f devcloud/image/Dockerfile \
     --build-arg DEVCLOUD_USER=dev --build-arg DEVCLOUD_UID=1001 --build-arg DEVCLOUD_HOME=/Users/dev . >"$log" 2>&1; then
  tail -n 80 "$log"
  echo "FAIL the image does not build"
  exit 1
fi
echo "ok the image builds ($(docker image inspect -f '{{.Size}}' "$image" | awk '{printf "%.1f GB", $1 / 1e9}'))"
echo "  build steps${scope:+ (cache $scope)}:"
awk '
  /^#[0-9]+ \[/ { step[$1] = $0 }
  /^#[0-9]+ (CACHED|DONE)( |$)/ {
    id = $1
    if (id in step) { sub(/^#[0-9]+ /, ""); print "    " step[id] " " $0 }
  }
' "$log"

echo "== integration"
python3 devcloud/tests/integration.py "$image"
