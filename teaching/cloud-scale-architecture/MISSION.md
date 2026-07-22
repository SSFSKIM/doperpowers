# Mission

## Why

나(운영자)는 board pipeline(implementer/review workers + ticket board)의
설계자이자 유일한 인간 오퍼레이터다. 2026-07-23에 에이전트 리서치 2라운드를
거쳐 엔터프라이즈 스케일(프로젝트당 시간당 수백~수천 런, 멀티 호스트)용
레퍼런스 아키텍처 스펙이 확정됐다:
`docs/doperpowers/specs/2026-07-23-cloud-scale-reference-architecture-design.md`.

나는 이 스펙을 **검토**했지만, 아직 **소유**하지는 못했다. 목표는 이
아키텍처를 남에게 설명하고, 방어하고, 미래의 설계 결정(플랜 리뷰, 스파이크
판정, 벤더 선택 재심)에서 스스로 판단할 수 있는 수준의 내면화다.

## Success looks like

- 화이트보드 앞에서 세 SSOT 플레인과 same-transaction 타이브레이커를
  아무것도 안 보고 설명할 수 있다.
- "왜 Temporal이 아니라 Postgres인가", "왜 Firecracker 스냅샷을 버렸나",
  "왜 Linear는 미러인가"에 숫자를 들어 답할 수 있다.
- 스파이크 S1–S4 결과가 나왔을 때 승격/폐기 판정을 스스로 내릴 수 있다.
- 의미층 수정 3건(★)이 무엇을 바꾸고 무엇을 지키는지 경계를 정확히 안다.

## Grounding

모든 레슨은 스펙과 그 증거 기반(`docs/doperpowers/2026-07-23-cloud-scale-research.md`,
`docs/doperpowers/research/2026-07-23-cloud-scale/`)에 근거한다. 파라메트릭
지식보다 이 문서들과 그 1차 출처가 우선.

## Curriculum (working plan, ~8 lessons)

1. Three planes of truth — 독트린 분열과 same-transaction 타이브레이커
2. Board service — 서버측 전이 강제, conditional UPDATE, Linear 미러
3. Dispatch plane — lease/fencing, progress-as-heartbeat, reconcile controller
4. Compute plane — gVisor, NVMe 경제학, warm state는 디스크 문제
5. Environment layer — 인증 게이트, hash-keyed drift-by-construction, mock fence
6. Credentials — scoping이 아니라 structural unreachability
7. Review & merge — 4층 권한, TAP vs SubmitQueue, verifier stage
8. Economics & observability — 앵커, 동시성≠처리량, circuit breakers
