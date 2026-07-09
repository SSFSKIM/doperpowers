#!/usr/bin/env bash
# launchd 진입점. 스킬 디렉터리의 .env를 로드하고 Node 폴러(src/poll.ts)를 실행한다.
# 자세한 launchd plist/.env 예시는 ../references/setup.md 참고.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
set -a
[ -f "$here/.env" ] && . "$here/.env"
set +a
cd "$here" && exec npx tsx src/poll.ts
