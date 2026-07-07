# ExecPlan — 보드 close-candidate 파생 신호 (v7.7.0)

This plan is a self-contained, living document. A fresh session with no
conversation history must be able to implement it end-to-end from this file
alone. Keep Progress, Surprises & Discoveries, and the Decision Log current at
every stopping point.

## Purpose / Big Picture

issue-tracker 보드(v7: GitHub Issues = SSOT)의 실사용 보드(ida-solution)에서
**열린 티켓 15개 중 8개(53%)가 "연결된 PR이 전부 머지/닫힘" 상태**로 확인됐다
(2026-07-07 실측). 이슈 본문에 `Closes #N`이 없는 PR은 머지돼도 이슈를
자동으로 닫지 않으므로, 사실상 완료된 티켓이 ready-for-agent 컬럼에 남아
"진짜 해야 할 일"과 섞인다. 디스패치 루프(맨 위 ELIGIBLE을 집는다)가 이런
티켓을 집으면 낭비다.

이 작업은 **close candidate**라는 파생(derived) 신호를 추가한다: 열린
티켓인데 연결 PR이 1개 이상 있고 전부 MERGED/CLOSED이며 그중 최소 1개가
MERGED인 티켓. 라벨이 아니다 — 스냅샷을 만들 때마다 이미 가져오는 PR 상태
데이터(v7.4.0의 `closedByPullRequestsReferences` + cross-ref)에서 순수
계산한다. 신호는 큐잉까지만: 닫을지 판단은 사람/오케스트레이터의 몫이다
(자동 닫기 금지 — 아래 Decision Log D2의 #81 반례).

완료 시 사용자가 보는 것: 칸반 뷰에 "close-candidate" 컬럼이 생겨 닫기
후보가 자기 상태 컬럼에서 빠져나와 모이고, `board-list.sh` 행에 `CLOSE?`
태그, `board-lint.sh`에 후보 WARN, BOARD.md 표와 상세 패널에 표시가 붙는다.

## Constraints & context

- 로컬 doperpowers `main`은 다른 세션이 diverge 상태로 사용 중 — 모든 작업은
  `origin/main`(bd3382c, v7.6.0)에서 딴 worktree
  `.claude/worktrees/close-candidate`(브랜치 `close-candidate`)에서 하고,
  완료 시 origin/main에 머지한다. 이 포크는 직접 커밋/머지 허용,
  `Co-Authored-By` 금지.
- 새 GraphQL 필드 없음 → 소비자 워크플로우 토큰 권한 변경 없음
  (`pull-requests: read`는 v7.5.1에서 이미 추가됨). references/ 두 템플릿은
  건드릴 필요 없다.
- 관리 라벨 패밀리(status/priority)는 늘리지 않는다. 라벨 생성·스왑·lint
  invariant 어느 것도 이 신호에는 없다.
- 테스트는 `tests/issue-tracker/test-board-scripts.sh` + `mock-gh/gh` 모크.
  모크는 이미 `closesPRs`/`xrefPRs` 시드 리스트로 PR 연동을 표현한다(v7.4.0)
  — 새 모크 계약 불필요. 테스트 파일은 순차 상태를 공유하므로 새 픽스처는
  파일 끝(finalize 섹션 뒤)에 새 이슈 번호로 추가한다.
- 버전: `scripts/bump-version.sh 7.7.0`(minor — 순수 추가, 파괴 변경 없음),
  RELEASE-NOTES.md 항목, 태그 `v7.7.0`.
- 머지 전 Codex 리뷰 1회 통과: `/codex:rescue --model gpt-5.5 --effort high`
  (스폰 실패 시 Claude Opus 4.8 high로 자체 리뷰). 발견은 검증 후 수정,
  재리뷰 1회.
- 릴리스 후 소비자(ida-solution)의 `.github/workflows/board-pages.yml`
  `PLUGIN_REF`를 v7.7.0 SHA로 범프(현재 v7.5.0 SHA — v7.6.0 priority 표시도
  이 범프로 함께 배포된다), 배포 확인.

## Decision Log

- **D1 — 파생 신호, 라벨 아님** (인간 파트너 승인, 2026-07-07). 제안은
  'close candidate' 태그(라벨)였으나 파생으로 확정. 근거: (a) 데이터가 이미
  스냅샷에 있다, (b) 쓰인 라벨은 새 PR이 열리는 순간 거짓이 되고 lint
  규칙·정리 책임이 생긴다, (c) v7 철학 — 결정(status/priority)은 라벨,
  GitHub 상태에서 도출 가능한 사실(done, close-candidate)은 파생.
- **D2 — 자동 닫기 없음, 후보 큐잉만** (인간 파트너의 원래 프레이밍 유지).
  반례 실존: ida-solution #81(출시 주 온콜)은 PR 전부 머지됐지만 티켓은
  정당히 진행 중. 신호는 triage 큐를 만들 뿐, 닫는 판단은 사람 몫.
- **D3 — 조건에 "최소 1개 MERGED" 포함** (구현자 결정). 연결 PR이 전부
  CLOSED(unmerged)뿐이면 시도가 버려진 것이지 일이 배달된 게 아니다 —
  ida-solution #157(CLOSED 1건뿐)이 그 예. 후보 아님. 기각 대안: "전부
  머지/닫힘"만 보는 단순 조건 — 버려진 티켓을 닫기 후보로 오분류한다.
- **D4 — 활성 상태(in-progress, in-review)는 컬럼 이동·lint WARN 제외**
  (구현자 결정). 작업 중 티켓은 1부 PR 머지·2부 진행이 일상이라 신호가
  잡음이 된다(#81, #117이 실례). 활성 티켓은 제자리에서 `CLOSE?` 표시만
  받고, 칸반 재배치와 lint WARN은 비활성 상태(ready-for-agent, untracked,
  blocked, needs-info, deferred, conflict)에만 적용. `_board.py`에
  `ACTIVE = ("in-progress", "in-review")` 상수로 명문화.
- **D5 — eligibility 의미 불변** (구현자 결정). 후보를 ELIGIBLE에서 빼면
  디스패치 기계(eligible(), 스윕, 워커 프로토콜)에 파급된다. 대신
  board-list가 `CLOSE?` 태그를 달고, SKILL.md 디스패치 1단계가 "맨 위
  픽이 CLOSE?면 스폰 전에 먼저 검증·닫기"를 지시한다. 기각 대안:
  close candidate는 not-eligible — 기계 변경 리스크 대비 이득 없음.
- **D6 — lint는 WARN, FAIL 아님** (구현자 결정). 스키마 위반이 아니라
  triage 프롬프트다 — priority 백필 WARN과 같은 부류. FIX 한 줄 명령은
  없다(ready-for-agent → done 직행은 합법 전이가 아니므로 판단 경로만
  안내: landed면 done으로 걸어가고, superseded면 wontfix).

## Progress

- [ ] M1: `_board.py` — `ACTIVE` 상수 + 노드 필드 `close_candidate` 파생
- [ ] M2: 표면 — board-list `CLOSE?` 태그 · board-lint WARN(비활성만) ·
      board-map MD 표 표시 + 페이로드 필드 · 템플릿(칸반 close-candidate
      컬럼, 카드 표시, 상세 행, 헤더 카운트) · SKILL.md 갱신
      (board-show는 노드 dict 전체를 덤프하므로 자동 포함 — 무변경)
- [ ] M3: 테스트 — 파일 끝에 close-candidate 섹션: 후보/전부-CLOSED
      비후보/OPEN-PR 비후보/활성-상태 WARN 제외 픽스처 + list·lint·map
      단언; 전체 스위트 그린
- [ ] M4: 실데이터 검증 — ida-solution 스냅샷으로 BOARD.html 렌더, 후보
      7건(#60·61·79·80은 컬럼 이동, #81·116·117 처리 D3/D4대로) 확인
- [ ] M5: Codex 리뷰 → 검증·수정 → 재리뷰 통과
- [ ] M6: bump 7.7.0 + RELEASE-NOTES + 회고 작성 → origin/main 머지 + 태그
      + 로컬 플러그인 갱신
- [ ] M7: ida-solution PLUGIN_REF → v7.7.0 SHA 범프, 배포 후 호스팅 보드
      확인

## Concrete steps

1. **_board.py** (스냅샷 정규화 블록, `prs` 계산 직후):
   `ACTIVE = ("in-progress", "in-review")` 상수를 상태 어휘 블록에 추가.
   노드 dict에
   `"close_candidate": state not in TERMINAL and bool(pr_list) and
   all(p["state"] in ("MERGED","CLOSED") for p in pr_list) and
   any(p["state"] == "MERGED" for p in pr_list)` —
   state는 이미 계산된 derive_state 결과를 지역변수로 받아 쓴다.
2. **board-list.sh**: 태그 조립 뒤 `if n.get("close_candidate"):
   tags.append("CLOSE?")` (상태 무관 — 리스트에선 사실 표시, 잔소리는
   lint가 D4 범위로).
3. **board-lint.sh**: priority 블록 뒤에
   `if n.get("close_candidate") and n["state"] not in B.ACTIVE: warn(...)`
   — 문구는 "all N linked PR(s) merged/closed — verify & close (done if
   landed / wontfix if superseded), or re-scope".
4. **board-map.sh**: `state_label()` 대신 MD 행 조립에서 state 셀에
   `" · CLOSE?"` 접미(후보일 때); 페이로드 노드에
   `"close_candidate": n.get("close_candidate", False)`.
5. **템플릿**: (a) `STATE_CLS`에 `"close-candidate": "s_cand"` + `.s_cand`
   팔레트(시안 계열) 추가, (b) `KB_STATES`의 in-review 뒤에
   `"close-candidate"` 삽입, (c) 칸반 라우팅 — `colOf(n) =
   n.close_candidate && n.state !== "in-progress" && n.state !== "in-review"
   ? "close-candidate" : n.state`; 컬럼 필터를 `n.state === s`에서
   `colOf(n) === s`로, (d) 그래프/칸반 카드 meta bits와 상세 패널에
   `CLOSE?` 표시, (e) 헤더 카운트에 close-candidate 수.
6. **SKILL.md**: 디스패치 1단계에 CLOSE? triage 문장, board-list/lint
   툴킷 행 갱신, Edge cases에 close-candidate 정의 한 항목.
7. **테스트**: 파일 끝에 "close-candidate" 섹션 — register로 신규 티켓
   3~4장, 모크 상태에 closesPRs/xrefPRs 주입, list/lint/map 출력 단언,
   활성 전이 후 WARN 사라짐 단언. `tests/issue-tracker/test-board-scripts.sh`
   전체 실행 그린.
8. **실데이터**: `BOARD_REPO=IDA-solution/ida-solution board-map.sh --write`
   (읽기 + 로컬 렌더만) → 후보 분류가 실측과 일치하는지 눈으로 확인.
9. Codex 리뷰 → 수정 → 재리뷰. 10. 릴리스(M6). 11. 소비자 범프(M7).

## Surprises & Discoveries

None yet. 예상 리스크: (a) 칸반 라우팅 변경이 chips(상태 필터)와 상호작용
— 숨긴 상태의 후보가 close-candidate 컬럼에 남는 것은 의도된 동작으로
문서화, (b) 테스트 파일의 순차 상태 공유 — 새 섹션은 기존 이슈 번호를
건드리지 않는다, (c) 빈 prs에 `all()`이 True인 파이썬 함정 — `bool(pr_list)`
선행 조건 필수.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-07: 최초 작성 (그릴 = 본 세션의 실측 assessment + 인간 파트너의
  "동의한다. 진행하자" 승인; D1·D2가 인간 결정, D3–D6는 위임된 구현자 결정).
