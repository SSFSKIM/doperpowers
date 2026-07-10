# 운영 환경 설정 (operator setup)

`triaging-feedback` 폴러를 한 대의 맥(또는 상시 켜진 머신)에 붙이기 위한
일회성 설정. `scripts/feedback-poll.sh`를 launchd로 주기 실행시키고, 그
안에서 `src/poll.ts`가 pending 피드백 행을 찾아 read-only Codex-SDK 워커를
돌립니다. 워커는 코드를 쓰지 않습니다 — 진단하고 티켓을 저작할 뿐이며,
수정은 보드 파이프라인(implementing-tickets → reviewing-prs)의 몫입니다.

## 0. 전제조건 — 피드백 트리아지 마이그레이션(p86)이 먼저 적용돼 있어야 함

이 폴러는 `feedback.triage_state`/`feedback.host`/`feedback.triage_lease`
컬럼이 있다고 가정합니다(claim·writeback이 이 컬럼에 쓴다). ida-solution
쪽에서 `sql/p86_*.sql`(feedback triage 컬럼 + `triage_state` CHECK + 과거 행
`skipped` 백필 + partial index)이 Supabase에 적용되지 않은 상태로 폴러를
돌리면 매 tick마다 DB 에러로 실패합니다. 먼저 그 마이그레이션이 라이브인지
확인하십시오. (티켓-온리 재설계 이후 `'fixed'` 상태값과 `triage_pr_url`
컬럼은 불필요 — 아직 미적용이므로 DDL에서 빼고, 대신 `triage_lease UUID`를
넣어 작성하십시오: claim이 lease를 새기고 writeback이 그 lease를 조건으로
걸어 리클레임 이중 기록을 막습니다.)

## 1. 워크트리 잡음 방지 (`.gitignore`)

`git.ts`의 `addWorktree`는 매 피드백마다 `TRIAGE_REPO_PATH` 안쪽
`.triage-worktrees/<id>`에 detached 워크트리를 만듭니다(진단용 깨끗한
스냅샷 — 빌드하지 않으므로 `node_modules`도 필요 없음). 피드백 처리 중에는
베이스 체크아웃(ida-solution)의 `git status`에 untracked 디렉터리로 잡혀
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
OPENAI_API_KEY=...                   # Codex SDK 인증
TRIAGE_REPO_PATH=/absolute/path/to/ida-solution   # 대상 레포 베이스 체크아웃
TRIAGE_BASE_BRANCH=feat/m4.5-polish  # 진단 스냅샷 기준 통합 브랜치 (main 아님)
TRIAGE_BOARD_SCRIPTS_DIR=/absolute/path/to/doperpowers/skills/issue-tracker/scripts
```

선택(기본값 있음):

```
TRIAGE_MODEL=gpt-5.6-terra # 워커 모델 — 명시 고정. ~/.codex/config.toml의 대화용 기본값과 무관.
                           # 워크호스 티어로 충분(진단+티켓 저작) — 플래그십(sol)은 과사양
TRIAGE_EFFORT=high         # minimal|low|medium|high|xhigh — 작은 모델 + 높은 effort 조합
TRIAGE_TRUSTED_ROLES=admin # 이 role(서버가 조회한 스냅샷 — 위조 불가)의 피드백은 developer 신뢰:
                           # 본문을 지시로 읽고, 아이디어/개선도 ready-for-agent 가능. 콤마 구분.
TRIAGE_DEV_CODE=           # (선택) 시크릿 코드 — 본문이 `#<code>`로 시작하면 developer 신뢰.
                           # 코드는 처리 전에 본문에서 제거되어 티켓/프롬프트에 노출되지 않음.
                           # 누출이 의심되면 즉시 로테이트.
TRIAGE_K=3               # tick당 처리할 최대 행 수 (처음엔 1로 시작 권장 — 아래 5번)
TRIAGE_TIMEOUT_MS=1200000        # 20분 — 워커 턴(turn) 타임아웃(AbortController로 배선됨)
TRIAGE_RECLAIM_MS=5400000        # 90분 — claimed인데 멈춘 행을 회수하는 기준
TRIAGE_ENABLED=true      # false면 poll.ts가 즉시 exit 0 (킬 스위치)
```

**`TRIAGE_RECLAIM_MS`는 반드시 최악 디스패치 시간보다 커야 하며, 이제
`loadConfig`가 강제합니다**(`TRIAGE_TIMEOUT_MS` + 등록 예산 10분보다 작으면
로드 시점에 throw). `TRIAGE_TIMEOUT_MS`를 늘리면 `TRIAGE_RECLAIM_MS`도 함께
늘리십시오. 추가 방어선: claim이 행에 lease 토큰을 새기고 writeback이 그
lease를 조건으로 걸므로, 설령 리클레임이 일어나도 구 워커의 늦은 기록이 신
워커의 결과를 덮어쓰지 못하며, 등록 직전의 2차 멱등 확인이 중복 티켓 창을
좁힙니다.

**전제: 폴러는 머신당 launchd 단일 label 1개만 등록합니다.** 이 문서의
리클레임 설계(atomic claim + 위 창 확대)는 동시성 안전을 launchd의 "같은
label은 동시 실행하지 않는다" 직렬화에 의존합니다. 같은 머신에 같은 잡을
여러 label로 중복 등록하거나 수동으로 병행 실행하지 마십시오(lease/heartbeat
같은 별도 조율 장치는 v1에서 의도적으로 두지 않았습니다 — 과설계로 판단).

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
gh label create "source:dev-feedback" --color 0E8A16 --description "developer 신뢰 피드백에서 자동 파일링됨"
gh label create "type:question" --color D4C5F9 --description "사용자 질문 — 사람 답변 필요"
```

## 5. `TRIAGE_K=1`로 시작해 티켓 품질을 관찰

처음 붙일 때는 `TRIAGE_K=1`로 시작해 첫 티켓들을 직접 확인하십시오:
분류가 맞는지, 진단이 `file:line`으로 grounding됐는지, birth state 추천이
정직한지(`ready-for-agent`가 남발되지 않는지), park 노트가 "사람이 무엇을
결정해야 하는지"를 실제로 말하는지. 이 워커의 산출물은 곧
implementing-tickets 루프의 입력이므로, 티켓 품질이 신뢰를 얻은 뒤 `K`를
올립니다. (v1의 `TRIAGE_FIX_ENABLED` 섀도 모드는 사라졌습니다 — 티켓-온리가
최종 형태라 더 위험한 모드로의 승격 자체가 없습니다.)

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
확인하십시오. `feedback <id> → ticketed` 같은 줄이 보이면 정상 동작
중입니다.

## 8. `failed`는 터미널 상태 — 자동 재시도 없음

`db.ts`의 `findActionable`/`claim`은 `pending`이거나 리클레임 창을 넘긴
`claimed` 행만 고릅니다. `failed`로 쓰인 행은 이 predicate에 절대 걸리지
않으므로 다음 tick에도, 그다음 tick에도 재시도되지 않습니다(재시도 카운터
같은 별도 장치는 두지 않았습니다). 원인(로그 확인)을 고치고 다시 돌리려면
운영자가 Supabase에서 해당 행의 `triage_state`를 `pending`으로 직접
리셋해야 합니다.
