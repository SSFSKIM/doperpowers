# 운영 환경 설정 (operator setup)

`triaging-feedback` 폴러를 한 대의 맥(또는 상시 켜진 머신)에 붙이기 위한
일회성 설정. `scripts/feedback-poll.sh`를 launchd로 주기 실행시키고, 그
안에서 `src/poll.ts`가 pending 피드백 행을 찾아 Codex-SDK 워커를 돌립니다.

## 0. 전제조건 — Plan A(p86 마이그레이션)가 먼저 적용돼 있어야 함

이 폴러는 `feedback.triage_state`/`feedback.host` 컬럼이 있다고 가정합니다
(claim·writeback이 이 컬럼에 쓴다). ida-solution 쪽에서 `sql/p86_*.sql`
(feedback triage 컬럼 + `triage_state` CHECK + 과거 행 `skipped` 백필 +
partial index)이 Supabase에 적용되지 않은 상태로 폴러를 돌리면 매 tick마다
DB 에러로 실패합니다. 먼저 그 마이그레이션이 라이브인지 확인하십시오.

## 1. 베이스 체크아웃에 `node_modules` 설치

`git.ts`의 `addWorktree`는 매 피드백마다 새 `git worktree`를 만들고, 그 안에
`npm install`을 다시 돌리는 대신 **베이스 체크아웃(`TRIAGE_REPO_PATH`)의
`node_modules`를 심볼릭 링크**로 공유합니다(워크트리는 `node_modules`가
gitignore돼 있어 비어 있음). 따라서:

- `TRIAGE_REPO_PATH`가 가리키는 ida-solution 체크아웃에서 미리
  `npm install`을 한 번 실행해 `node_modules`가 존재해야 합니다.
- 이후 그 디렉터리에서 `npm install`을 다시 돌릴 때마다(의존성 변경 시)
  워크트리들이 최신 상태로 링크를 따라가므로 별도 동기화는 필요 없습니다.
- `git.ts`의 `addWorktree`는 워크트리를 `TRIAGE_REPO_PATH` 안쪽
  `.triage-worktrees/<id>`에 만듭니다. 그 결과 피드백 처리 중에는 베이스
  체크아웃(ida-solution)의 `git status`에 untracked 디렉터리로 잡혀
  사람/에이전트가 같은 체크아웃에서 작업할 때 잡음이 됩니다 — 미리
  `TRIAGE_REPO_PATH` 체크아웃의 `.gitignore`에 `.triage-worktrees/`를
  추가하십시오(예: 그 체크아웃에서 `echo '.triage-worktrees/' >> .gitignore`).

## 2. `.env` 파일 (커밋 금지)

`skills/triaging-feedback/.env`에 아래 변수를 채웁니다(`.gitignore`에 이미
`.env`가 포함돼 있음 — 실수로도 커밋되지 않습니다). 필수(`loadConfig`가 없으면
throw):

```
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...        # service-role, RLS 우회 — 절대 클라이언트에 노출 금지
OPENAI_API_KEY=...                   # 또는 CODEX_API_KEY — Codex SDK 인증
TRIAGE_REPO_PATH=/absolute/path/to/ida-solution   # 베이스 체크아웃(위 1번)
TRIAGE_BASE_BRANCH=feat/m4.5-polish  # fix PR의 base. main 아님 — 통합 브랜치
TRIAGE_BOARD_SCRIPTS_DIR=/absolute/path/to/doperpowers/skills/issue-tracker/scripts
```

선택(기본값 있음):

```
TRIAGE_K=3               # tick당 처리할 최대 행 수
TRIAGE_TIMEOUT_MS=1200000        # 20분 — 워커 턴 타임아웃
TRIAGE_RECLAIM_MS=1800000        # 30분 — claimed인데 멈춘 행을 회수하는 기준
TRIAGE_ENABLED=true      # false면 poll.ts가 즉시 exit 0 (킬 스위치)
TRIAGE_FIX_ENABLED=false # 아래 5번 — 섀도 모드 시작 값
```

## 3. `BOARD_REPO`는 반드시 ida-solution을 가리켜야 함

`registerTicket`은 `TRIAGE_BOARD_SCRIPTS_DIR/board-register.sh`를 **cwd =
`cfg.repoPath`(ida-solution 체크아웃)** 로 실행합니다(`sideEffects.ts`). 그
board 스크립트들의 `_lib.sh`는 `BOARD_REPO`를 (env로 명시돼 있지 않다면) 현재
작업 디렉터리의 git remote로부터 추론합니다. 즉 `cfg.repoPath`가
doperpowers가 아니라 **ida-solution 체크아웃**을 가리키기만 하면, 폴러가
만드는 티켓은 자동으로 ida-solution의 이슈 보드에 등록됩니다(doperpowers
쪽 보드로 잘못 파일링되지 않음). `BOARD_REPO`를 env로 강제 지정하려면
`.env`에 `BOARD_REPO=IDA-solution/ida-solution` 같은 값을 추가해도 되지만,
`TRIAGE_REPO_PATH`가 올바르면 보통 불필요합니다.

## 4. 디스크립티브 라벨 1회 생성

디스패처가 티켓에 붙이는 설명용 라벨이 저장소에 미리 존재해야 합니다(없으면
`gh issue edit --add-label`이 실패하지는 않지만 라벨이 색 없이 임의 생성됨 —
깔끔하게 하려면 미리 만들어 둡니다):

```bash
gh label create "source:user-feedback" --color BFD4F2 --description "in-app 피드백에서 자동 파일링됨"
gh label create "type:question" --color D4C5F9 --description "사용자 질문 — 사람 답변 필요"
```

## 5. 섀도 모드로 시작 (`TRIAGE_FIX_ENABLED=false`)

처음 붙일 때는 `.env`에 `TRIAGE_FIX_ENABLED=false`로 시작하십시오. 이
값이면 `dispatch.ts`의 `wantsFix`가 항상 거짓이 되어, 버그로 진단된 행도
**코드 쓰기 없이** 진단이 담긴 사람 티켓으로만 남습니다(PR은 절대 열리지
않음). 며칠간 티켓 품질(분류가 맞는지, 진단이 근거 있는지)을 지켜본 뒤
신뢰가 쌓이면 `TRIAGE_FIX_ENABLED=true`로 올려 실제 fix PR 경로를 켭니다.
`TRIAGE_ENABLED=false`는 더 상위의 완전 정지 스위치입니다(폴러 자체가
아무 행도 읽지 않고 exit 0).

## 6. launchd 등록 (10분 주기)

`~/Library/LaunchAgents/kr.ida.feedback-poll.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>kr.ida.feedback-poll</string>
  <key>ProgramArguments</key>
  <array>
    <string>/absolute/path/to/doperpowers/skills/triaging-feedback/scripts/feedback-poll.sh</string>
  </array>
  <key>StartInterval</key><integer>600</integer>
  <key>StandardOutPath</key><string>/tmp/feedback-poll.out.log</string>
  <key>StandardErrorPath</key><string>/tmp/feedback-poll.err.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
```

등록/해제:

```bash
launchctl load ~/Library/LaunchAgents/kr.ida.feedback-poll.plist
launchctl unload ~/Library/LaunchAgents/kr.ida.feedback-poll.plist
```

`feedback-poll.sh`는 스킬 디렉터리의 `.env`를 로드하고
`npx tsx src/poll.ts`를 실행합니다 — launchd 프로세스는 로그인 셸의 PATH를
상속하지 않을 수 있으니, `npx`/`node`가 launchd 환경에서 안 잡히면 plist의
`ProgramArguments`를 절대경로(`/usr/local/bin/npx` 등)로 바꾸거나
`EnvironmentVariables`에 `PATH`를 명시하십시오.

## 7. 동작 확인

로그를 보며 첫 몇 번의 tick을 지켜봅니다:

```bash
tail -f /tmp/feedback-poll.out.log /tmp/feedback-poll.err.log
```

`TRIAGE_ENABLED=false — skip`만 계속 찍히면 `.env`의 `TRIAGE_ENABLED`를
확인하십시오. `feedback <id> → ticketed` / `→ fixed` 같은 줄이 보이면
정상 동작 중입니다.
