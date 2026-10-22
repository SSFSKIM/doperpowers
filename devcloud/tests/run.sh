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
if ! docker build --progress=plain -t "$image" -f devcloud/image/Dockerfile \
     --build-arg DEVCLOUD_USER=dev --build-arg DEVCLOUD_UID=1001 --build-arg DEVCLOUD_HOME=/Users/dev . >"$log" 2>&1; then
  tail -n 80 "$log"
  echo "FAIL the image does not build"
  exit 1
fi
echo "ok the image builds ($(docker image inspect -f '{{.Size}}' "$image" | awk '{printf "%.1f GB", $1 / 1e9}'))"

echo "== integration"
python3 devcloud/tests/integration.py "$image"
