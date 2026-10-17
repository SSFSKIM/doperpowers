#!/usr/bin/env bash
# devcloud's host tests: the unit tests of the boot program's library, then
# the image built from image/Dockerfile and booted in containers against
# stand-ins (tests/integration.py). Needs Docker, Python 3.11+ and bun (the
# image scan runs the secrets guard's detector). Every case prints "ok".
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

echo "== unit"
python3 -m unittest discover -s devcloud/tests/unit

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
