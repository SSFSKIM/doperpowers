# T3 Code Orchestrator V2 — architecture digest

Source: `pingdotgg/t3code` `main`, read 2026-10-06 (head `e65063cc`, nightly 0.0.46 line). Umbrella PR
#2829 (merged 2026-10-02) plus the `orchestration-v2`-scoped follow-ups. Files were read through the
GitHub tree API and raw URLs (the shallow clone failed mid-transfer); nothing from the repo was executed.
All paths are repo-relative. "Doc" means the repo's own design docs under `docs/orchestration-v2/`, which
describe themselves as "the target architecture"; where code and doc differ, the code is quoted.

Key files:

| Concern | Path |
|---|---|
| Wire schemas (entities, events, commands, RPC names) | `packages/contracts/src/orchestrationV2.ts` |
| Command processor | `apps/server/src/orchestration-v2/Orchestrator.ts` (415 KB) |
| Event log + projections + outbox commit | `apps/server/src/orchestration-v2/EventSink.ts`, `ProjectionStore.ts`, `EffectOutbox.ts`, `EffectWorker.ts` |
| Provider adapter contract | `apps/server/src/orchestration-v2/ProviderAdapter.ts`, `Adapters/*` |
| MCP tools agents get | `apps/server/src/mcp/toolkits/{orchestrator,thread,worktree,pullRequests}/tools.ts`, `apps/server/src/mcp/OrchestratorMcpService.ts` |
| Schema | `apps/server/src/persistence/Migrations/055_OrchestrationV2.ts` + `Migrations/OrchestrationV2/*.ts` |
| Design docs | `docs/orchestration-v2/*.md` |

---

## 1. Unit of work and its identity

### The entity graph

Doc (`docs/orchestration-v2/README.md`):

```text
AppThread
  Run 1
    root ExecutionNode
      tool ExecutionNode
      approval ExecutionNode
      subagent ExecutionNode
        ProviderThread
          child root ExecutionNode
  Run 2
    root ExecutionNode
```

"An app thread is the user-visible conversation. A run is the counted user-visible turn. Execution nodes
are the tree of work inside the run. Provider threads are provider-native conversation handles."
Invariants listed there include "App ids are primary. Provider ids are refs." and "Child execution
completion never closes the parent run."

All of these are Effect `Schema` structs in `packages/contracts/src/orchestrationV2.ts`:

- **`OrchestrationV2AppThread`** (id `ThreadId`): `projectId`, `providerInstanceId`, `modelSelection`,
  `runtimeMode`, `interactionMode`, `branch`, `worktreePath`, `linkedPullRequest`, `pullRequests`,
  `activeProviderThreadId`, `lineage {parentThreadId, relationshipToParent: "fork"|"subagent"|null,
  rootThreadId}`, `forkedFrom`, plus lifecycle stamps: `archivedAt`, `settledOverride:
  "settled"|"active"|null`, `settledAt`, `unsettledAt`, `snoozedUntil`, `snoozedAt`, `limitRecovery`,
  `pinnedAt`, `autoSettleDisabledAt`, `lastVisitedAt`, `rollbackFailure`, `deletedAt`. Creation provenance
  `createdBy: "user"|"agent"|"system"` and `creationSource` (`OrchestrationV2CreationFields`).
- **`OrchestrationV2Run`** (id `RunId`, `ordinal`): the counted turn.
  ```ts
  export const OrchestrationV2RunStatus = Schema.Literals([
    "preparing", "queued", "starting", "running", "waiting",
    "completed", "interrupted", "failed", "cancelled", "rolled_back",
  ]);
  ```
  Also `queuePosition`, `queueHeld` ("Restart recovery holds the queue until the user explicitly resumes
  it"), `restartContinuationOfRunId`, `workStartedAt` (set on wake runs), `delegatedCompletion` (the
  completion-delivery cohort, see §4), `workspacePreparation` (§7), `contextHandoffId`, `checkpointId`.
- **`OrchestrationV2RunAttempt`**: one provider execution of a run; `reason: "initial" |
  "steering_restart" | "retry" | "provider_recovery"`, status adds `"superseded"`.
- **`OrchestrationV2ExecutionNode`**: `kind` ∈ `root_turn, assistant_message, reasoning, plan, todo_list,
  tool_call, approval_request, user_input_request, subagent, hook, system`; status adds `"idle"`.
- **`OrchestrationV2ProviderThread`**: native handle with `nativeThreadRef` (`{driver, nativeId,
  strength: "strong"|"weak"|"none", fingerprint?, ordinal?}`), `status: not_loaded|idle|active|archived|
  closed|error`, `firstRunOrdinal/lastRunOrdinal` (coverage), `handoffIds`, `forkedFrom`,
  `pendingBackgroundTasks` (kinds `subagent|command|monitor|background_task`), `contextUsage`, `goal`.
- **`OrchestrationV2ProviderSession`**: live-or-recoverable process metadata, `status: starting|ready|
  running|waiting|stopped|error`, `capabilities`.
- **`OrchestrationV2ProviderTurn`**, **`OrchestrationV2RuntimeRequest`**, **`OrchestrationV2Subagent`**,
  **`OrchestrationV2CheckpointScope`/`Checkpoint`**, **`OrchestrationV2ContextTransfer`/`ContextHandoff`**,
  **`OrchestrationV2TurnItem`** (the ordered render stream; `visibleTurnItems` adds inherited/synthetic
  items for forks).

The read model a client receives is `OrchestrationV2ThreadProjection` (all of the above for one thread)
and, for lists, `OrchestrationV2ThreadShell` (summary row).

### There is no thread status enum

A thread has no stored status field. The shell's status is derived:

```ts
export const OrchestrationV2ShellThreadStatus = Schema.Union([
  Schema.Literal("idle"),
  OrchestrationV2RunStatus,
]);
```

plus `activityRunStatus: "preparing"|"starting"|"running"|"waiting"|null`, `pendingRuntimeRequest`,
`pendingBackgroundTasks`, `hasActionableProposedPlan`, `goal`. "Archived", "settled", "snoozed", "pinned"
are independent timestamp/override fields on the thread, not states of one machine.

### Settle / un-settle / snooze / wake

Commands (client-dispatchable unless noted), from `OrchestrationV2Command`:
`thread.settle`, `thread.unsettle {reason:"user"}`, `thread.snooze {snoozedUntil}`,
`thread.unsnooze {reason:"user"}`, `thread.auto-settle.set {enabled}`, `thread.archive`/`unarchive`,
`thread.pin`/`unpin`, and the server-internal `thread.auto-settle {snapshotAt}`:

> "Server-internal settlement (#8600): dispatched by the settlement sweep, never by clients. Rejected when
> the thread changed after `snapshotAt` or carries any explicit settled override, so automatic settlement
> can never race a user action or clobber an explicit un-settle."

- **Settle** = move a finished thread out of the active list (sets `settledAt`/`settledOverride`). Manual
  settle "dismisses unanswered async questions without sending an answer", closes idle terminals, removes
  the pin, and ends PR watches (`docs/user/thread-sidebar.md`; PR #16095).
- **Auto-settle** is a server sweep, `apps/server/src/orchestration-v2/ThreadSettlementService.ts`.
  `isAutoSettlementCandidate` rejects archived, overridden, pinned, auto-settle-disabled, a pending runtime
  request ("Blocked-on-you work must never park behind a settled override"), a live activity run,
  background work that "holds completion" (subagents and monitors do; a command left running such as a
  dev server does not — `packages/shared/src/orchestrationV2PendingBackgroundWork.ts`), or a queued turn
  start within 2 minutes. It settles after `sidebarAutoSettleAfterDays` of inactivity (default 3) or when
  a linked PR merged/closed after the user's last own message (`pullRequestSettles`).
- **Un-settle** = `settledOverride: "active"`; blocks auto-settlement "until new activity resumes the
  usual rules" (user doc).
- **Snooze** = hide until `snoozedUntil`. A snoozed thread that "woke early (error or completed work)" can
  auto-settle; one still parked keeps its snooze. **Wake** in the UI = `thread.unsnooze` (the "Wake"
  button / drag out of the snoozed shelf). `limitRecovery {runId, resetAt, autoResume, snooze}` is the
  "Snooze until reset" / "Resume at reset" record for usage-limit stops (`UsageLimitRecoveryWorker.ts`).
- **Wake (agent sense)** = a server-generated `message.dispatch` that starts a new run on the thread:
  background-task notifications, delegated-task results, PR-watch news, restart continuations. These carry
  `notification`/`delegatedCompletion`/`restartContinuationOfRunId`, and `wakeWorkStartedAt` keeps the
  original work's start time (`Orchestrator.ts`, "A wake does not start new work").

### Persistence

SQLite (`statev2.sqlite`, a one-time copy of V1's `state.sqlite` — `docs/user/thread-migration.md`).
Migration 055 (`Migrations/055_OrchestrationV2.ts` composing `Migrations/OrchestrationV2/*.ts`) creates:

- `orchestration_v2_events` — the append-only log: `sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id,
  command_id, thread_id, run_id, node_id, provider, raw_event_id, event_type, occurred_at, payload_json`.
- `orchestration_v2_command_receipts` — `command_id PK, thread_id, command_type, accepted_at,
  result_sequence, status, error` (idempotency).
- `orchestration_v2_effect_outbox` — durable side-effect queue (§8).
- Projection tables: `orchestration_v2_projection_{threads, runs, run_attempts, nodes, subagents,
  provider_sessions, provider_session_bindings, provider_threads, provider_turns, runtime_requests,
  messages, plans, turn_items, checkpoint_scopes, checkpoints, context_handoffs, context_transfers,
  metadata}` and `orchestration_v2_turn_item_positions`.
- `orchestration_v2_thread_launch_workflows` (launch saga with `setup_committed`, `thread_committed`,
  `message_committed` flags), `scheduled_tasks`, `scheduled_task_webhook_deliveries` (057).

### Is the V1 event-sourced decider model kept?

Yes in shape, rewritten in code. PR #14017 "delete the V1 decider, projector and V1-only repos"; the V1
command/event unions are gone ("V2 owns its event schema" — `docs/orchestration-v2/README.md`). V2 flow:

1. `OrchestratorV2.dispatch(command)` takes a per-thread lock: `threadDispatch.withLock(commandThreadId(
   command), …)`; `ThreadCommandExecutor` is a `KeyedLock<ThreadId>` ("serializing per-thread work without
   coupling unrelated identities to a process-wide mutex").
2. A duplicate `commandId` replays its receipt; otherwise `dispatchOnce` plans `{events, effects}` against
   the current projection (no provider I/O). Zero events = rejection (except `thread.stop` /
   `thread.background-work.settle`), recorded via `commitRejectedCommand`.
3. `EventSinkV2.commitCommand` appends events, applies them to projection tables
   (`projectionStore.apply`), records the receipt, and enqueues outbox effects in one `sql.withTransaction`.
   The dispatch result is `{sequence}` — the last committed event sequence.
4. Provider output enters through a second path: `ProviderEventIngestor` writes domain events with
   `eventSink.write(...)` (no command, no receipt), with guarded variants `writeIfRunCurrent` and
   `writeIfProviderThreadOwner` so late events from a superseded attempt cannot clobber newer state.

The event log is the ordering source (`sequence` is the snapshot/stream cursor), but reads go to the
projection tables; the V1 importer reads V1 projection rows, not V1 events (PR #2829 "V2 never replays the
V1 event log"). Domain event types (`OrchestrationV2DomainEvent`): `thread.created`, `thread.{archived,
unarchived,deleted,settled,unsettled,snoozed,unsnoozed,pinned,…,provider-switched}`, `run.created`,
`run.updated`, `run.background-work-cancelled`, `run-attempt.{created,updated}`, `node.updated`,
`subagent.updated`, `provider-session.{attached,updated,detached}`, `provider-thread.updated`,
`provider-turn.updated`, `runtime-request.updated`, `message.updated`, `turn-item.updated`,
`plan.updated`, `checkpoint-scope.created`, `checkpoint.captured`, `checkpoint.rollback-requested`,
`context-handoff.updated`, `context-transfer.{created,updated}`. Most carry the full entity as payload
(state-snapshot events rather than deltas).

## 2. The runtime: checkpoints, rollback, context handoff

**Checkpoint** = a hidden git ref snapshot of the workspace filesystem, attached to a `CheckpointScope`.
`CheckpointService.ts`: `const CHECKPOINT_REFS_PREFIX = "refs/t3/orchestration-v2/checkpoints"`;
`apps/server/src/checkpointing/CheckpointStore.ts`: "Owns hidden Git-ref checkpoint capture/restore and
diff computation … does not coordinate provider conversation rollback." Scope kinds `root_run | subagent |
tool | provider_thread | manual`; only `root_run` scopes have `advancesAppRunCount = true`. Capture runs as
the `checkpoint.capture` outbox effect after a run; a successful run sits in `waiting` until capture flips
it to `completed` (`orchestrationV2PendingBackgroundWork.ts` comment).

**Rollback rolls back both, optionally only the conversation.** Command
`checkpoint.rollback {scopeId, checkpointId, restoreFiles?: boolean}`.
`CheckpointRollbackService.execute`:
- refuses `restoreFiles` when the workspace is shared with another thread (`"shared-workspace"`,
  `CheckpointRestoreSafety.ts`);
- reopens the provider session, computes runs after the target ordinal, calls the adapter's
  `rollbackThread({providerThread, target: {type:"thread_start"} | {type:"provider_turn", providerTurn},
  providerThreadTurns})` (native conversation rollback; "A goal run can span several native turns; roll
  back to its last");
- then `checkpoints.restore({scope, checkpoint})` if `restoreFiles !== false`, deletes stale refs, and
  emits `run.updated` with `status: "rolled_back"` for later runs ("Rolled-back turns stay in the audit
  history"). Failure after retries is recorded via the internal `checkpoint.rollback.fail` command into
  `thread.rollbackFailure`.
- Capability gate: `checkpointing.providerCanRollbackConversation` (true for Codex and Claude, false for
  Cursor per their adapters).

**Context transfer / handoff.** One primitive for four features (`docs/orchestration-v2/
thread-lineage-and-context-transfer.md`):

```ts
OrchestrationV2ContextTransferType = Literals(["fork","provider_handoff","merge_back",
                                               "subagent_spawn","subagent_result"])
resolution: native_fork | portable_context | delta_context | fork_delta_context | checkpoint_context
status: pending | resolved_native | resolved_portable | failed | consumed | superseded
```

A `ContextHandoff` is the materialized payload (strategies `delta_since_target_last_seen |
fork_delta_summary | full_thread_summary | checkpoint_summary | manual_context`), with `history.messages`
(selected verbatim messages), `omittedItemIds`, and `delivery.status: pending|injected|inline`.

- **Provider switch within a thread** (`provider.switch {modelSelection}`, also `thread.model-selection.set`;
  `ProviderSwitchService.ts`, `ProviderSessionTransitionPolicy.ts`): `decideProviderSessionTransition`
  returns `reuse | switch_model_in_session | restart_and_resume | create_with_handoff | reject`. A
  different driver or continuation identity always yields `create_with_handoff`. The same app thread
  continues; a new or reactivated provider thread receives the handoff with the next run.
- **Handoff content** (`docs/user/portable-handoffs.md`, `ContextHandoffBudget.ts`): "a budgeted selection,
  not an agent-written summary" — intact recent messages plus the original request, references to omitted
  history the agent can fetch with `t3_thread_read`. Cap `T3CODE_CONTEXT_HANDOFF_TOKEN_CAP` (default
  16,000, clamped 1,024–64,000). Codex receives history via native injection (`injectHistory` on the
  adapter) "when its installed version supports that operation"; others get attributed context text.
- **Fork** (`thread.fork {sourceThreadId, targetThreadId, sourcePoint: latest_stable | run | checkpoint}`,
  `ThreadForkService.ts`): records lineage and a pending transfer; the first run on the fork resolves it
  by native fork (adapter `forkThread`) when the provider and capability allow, else portable context
  (`CommandPolicy.decideForkExecution` → `native_fork | portable_context`). In-progress and rolled-back
  runs are not forkable.
- **Merge-back** (`thread.merge_back`): a `merge_back` transfer carrying the fork's delta into the source
  thread's next run (`fork_delta_summary`).
- `threads set --provider`, `threads fork`, `merge-back` as CLI verbs are not in this repo; they belong
  to the external CLI (npm `@bvdm/t3code-cli` → `github.com/MajesteitBart/t3code-cli`), which drives the
  commands above.

## 3. Provider adapters

Registered V2 drivers (`apps/server/src/orchestration-v2/builtInProviderAdapterDrivers.ts`):
`CodexAdapterV2Driver, ClaudeAdapterV2Driver, CursorAdapterV2Driver, OpenCodeAdapterV2Driver,
GrokAdapterV2Driver, PiAdapterV2Driver, AcpRegistryAdapterV2Driver`. Adapter files in `Adapters/`: Codex
(app-server, generated schemas), Claude (Claude Agent SDK), Cursor (`@cursor/sdk`, not ACP),
OpenCode + `OpenCode2AdapterV2.ts`, Pi (`PiRpc.ts`, `pi --mode rpc`), and a shared ACP adapter
(`AcpAdapterV2.ts`) with flavors Grok, Antigravity (`AntigravityAdapterV2.ts`, `makeAcpAdapterV2({flavor:
makeAntigravityAcpAdapterFlavor(...)})`, built by `apps/server/src/provider/Drivers/AntigravityDriver.ts`),
Devin (`DevinAcp.ts`) and the generic ACP Registry. No Gemini adapter exists in the tree.

**Contract** (`ProviderAdapter.ts`):

```ts
interface ProviderAdapterV2Shape {
  instanceId; driver;
  getCapabilities(): Effect<OrchestrationV2ProviderCapabilities>;
  planSelectionTransition(input): Effect<ProviderSelectionTransitionPlan>;
  openSession(input: {threadId, providerSessionId, modelSelection, runtimePolicy,
                      resumeFromSession?, initialNativeThreadId?}): Effect<SessionRuntime, _, Scope>;
}
interface ProviderAdapterV2SessionRuntime {
  events: Stream<ProviderAdapterV2Event>; subscribeEvents?; hasPendingBackgroundWork?;
  ensureThread; resumeThread; injectHistory?; startTurn; compactThread?; steerTurn; interruptTurn;
  unloadThread?; respondToRuntimeRequest; readThreadSnapshot; uploadFeedback?;
  rollbackThread; forkThread;
}
```

Adapter events are normalized entity updates (`provider_thread.updated`, `provider_turn.updated`,
`node.updated`, `subagent.updated`, `message.updated`, `turn_item.updated`, `runtime_request.updated`,
`plan.updated`, `app_thread.created`) and `turn.terminal {status, failure, threadDisposition:
"reusable"|"broken"}`. Behavior differences are expressed through `OrchestrationV2ProviderCapabilities`
(sessions, threads, turns, streaming, tools, approvals, planning, subagents, context, checkpointing,
identity, `runtimePolicy.enforcement: "native"|"client-boundary"`), not provider names.

**Native session ↔ V2 thread mapping is not 1:1.** One app thread has one *active* provider thread
(`activeProviderThreadId`) but may accumulate several over time (provider switches, recovery), each with
run-ordinal coverage. One provider session may host several provider threads when
`supportsMultipleProviderThreadsPerSession` (true for Codex — "V2 shares Codex sessions across
orchestration threads"; false for Claude and Cursor). Session↔thread binding lives in
`orchestration_v2_projection_provider_session_bindings`.

**Resume.** `ProviderSessionManager` "owns live session residency: open sessions, idle release, explicit
shutdown … It intentionally does not resurrect persisted sessions"; sessions open lazily on the next
command (idle release after 30 min, deferred up to 4 h for pending background work —
`DEFAULT_IDLE_TIMEOUT_MS`, `DEFAULT_MAX_IDLE_PIN_MS`). Reopen passes `resumeFromSession` and
`initialNativeThreadId`; the adapter's `resumeThread` reattaches the native thread. For Codex, an
externally archived native session is unarchived (`thread/unarchive`) and the resume retried once
(PR #15389); if resume still fails, the turn-start path starts a fresh native session seeded with a
portable handoff. Archiving a T3 thread enqueues `provider-session.detach` with `revokeMcpCredential`.
Existing native Claude/Codex sessions on disk can be imported: `packages/contracts/src/agentSessions.ts`
(`AgentSessionSource = ["claudeAgent","codex"]`) and `thread.create.importedNativeThread {ref:{driver,
nativeId, strength:"strong"}}`.

## 4. Delegation and subagents

Agents get T3's tools through an authenticated HTTP MCP server `t3-code` at `http://127.0.0.1:<port>/mcp`,
injected per provider (Codex `-c mcp_servers.t3-code.url=…`, Claude `mcpServers` + `allowedTools:
["mcp__t3-code__*"]`, Cursor SDK `mcpServers`, ACP `session/new.mcpServers`, Pi via a generated
extension). Credentials are scoped to environment + parent thread + provider instance + provider session,
expire, and are revoked on session release (`McpSessionRegistry.ts`, `docs/orchestration-v2/
orchestrator-mcp-server.md`).

**Orchestrator toolkit** (`apps/server/src/mcp/toolkits/orchestrator/tools.ts`):
`orchestrator_capabilities`, `delegate_task`, `task_status`, `task_cancel`, `schedule_task`,
`list_scheduled_tasks`, `update_scheduled_task`, `delete_scheduled_task`, `request_secret`,
`create_threads`, `t3_thread_list`, `t3_thread_read`, `t3_thread_update`, `t3_thread_send`,
`t3_thread_wait`, `t3_thread_interrupt`.

`delegate_task` input (`packages/contracts/src/orchestratorMcp.ts`; doc shape):

```ts
{ task: string;
  target?: { providerInstanceId?; driverKind?; model? };
  title?; role?: "implementation"|"research"|"review"|"design"|"test"|"general";
  mode?: "async"|"wait"; timeoutMs?; clientRequestId?;
  runtimeMode?: "inherit"|"approval-required"|"auto-accept-edits"|"full-access";
  interactionMode?: "inherit"|"plan"|"default"; }
```

Result: `{taskId, childThreadId, childRunId, childNodeId, status, workState: "working" |
"waiting_for_children" | "result_available", hasPendingChildRuns, providerInstanceId, model, summary,
resultContextTransferId, latestTerminal*, waitTimedOut}`.

- The child is a new T3 thread (`lineage.relationshipToParent: "subagent"`) with only the task prompt:
  "Parent conversation history is not copied into the child." It becomes V2 command
  `delegated_task.request {parentThreadId, parentRunId, parentNodeId, task, modelSelection, runtimeMode,
  interactionMode, completionWake?: "always"|"settled_only"}`; it requires an active parent run owned by the
  calling MCP session. Mode and permission may only narrow (`runtime_mode_escalation_denied`,
  `interaction_mode_escalation_denied`).
- **Cross-provider** is the point of the tool: "Use this for any model missing from the native tool,
  including same-provider work, for cross-provider work". Any provider instance with a V2 adapter can run
  children (Codex, Claude, Cursor, Grok, ACP Registry, OpenCode, OpenCode 2, Pi, Antigravity). So a Codex
  parent launching Claude children is `delegate_task` with `target.driverKind`/`providerInstanceId`.
- **No task follow-up API.** "There is no task-level follow-up API for preserving the same reviewer
  session"; each review round is a new `delegate_task`. `t3_thread_send` to an app-owned child thread is
  allowed but "does not reopen a completed task". Provider-native subagent threads cannot take messages
  (`isProviderNativeSubagentThread`).
- **Stop**: `task_cancel` dispatches the internal `thread.stop` on the child ("interrupts its running
  turn, holds its queue, ends its pull request watches, and drops pending delegated-task wakes"), then
  stops every task the child delegated (`delegated-tasks.stop` effect).

**How completion reaches the parent.** Not a tool result (except `mode:"wait"`). The child's terminal run
finalizes the parent `subagent` record and node and writes a `subagent_result` context transfer. Then a
durable "mailbox" delivery (`Orchestrator.ts` `planDelegatedCompletionDelivery`,
`ProviderContinuationService.ts`, `NotificationMailbox.ts`): the parent run's `delegatedCompletion`
cohort allocates a message; per-task `completionDelivery.state` moves `pending → claimed → acknowledged
| delivered | disposed`. The orchestrator dispatches `message.dispatch` on the parent with a
`notification {source:{kind:"delegated_task", taskIds}}` and text:

> "Delegated task ${taskList} reached a terminal state. Use task_status with taskId ${taskList} to read
> the result."

It is "steered into active turns where supported or queued otherwise" (tool description). `completionWake:
"settled_only"` (wait-mode default) withholds the wake while the parent has a live run; `"always"` (async)
offers it regardless. Reading the result through `task_status` (or an untruncated `t3_thread_read` of the
child) acknowledges the delivery.

**Native subagents** (Claude Agent tool, Codex collab threads, Cursor `task`, OpenCode child sessions,
Grok task envelopes, Antigravity `start_subagent`) are projected by adapters into `OrchestrationV2Subagent`
records with `origin: "provider_native"` and, where the provider exposes them, child app threads
(`SubagentProjection.makeSubagentChildThread`). T3-delegated ones are `origin: "app_owned"`. A subagent's
approvals surface on the parent thread (`docs/user/thread-sidebar.md`).

**Lineage view** (`apps/web/src/components/chat/ThreadRelationshipsControl.tsx`, title `Lineage ·
N running`; graph from `packages/client-runtime/src/state/threadRelationships.ts`
`deriveThreadRelationshipGraph`). Edge kinds `"parent" | "fork" | "subagent" | "transfer"`, built from:
each shell's `lineage.parentThreadId` / `forkedFrom` (fork or subagent edges, status =
`activityRunStatus ?? status`), the open thread's `projection.subagents[].childThreadId`, and
`projection.contextTransfers` (transfer edges). Mobile: `ThreadAgentsSheet.tsx`, `SubagentStatusDot.tsx`.

**Reading a child's transcript**: yes — `t3_thread_read` "Read durable state and a paginated timeline from
any T3 thread in this environment" (`messages` or `activity` view, incremental `afterPosition`).

**Native `/goal`** (PR #15592): `OrchestrationV2ProviderGoal {objective, status: active|paused|blocked|
usage_limited|budget_limited|complete, tokensUsed?, tokenBudget?, timeUsedSeconds?, checks?, lastCheck?}`
on the provider thread and shell. Codex: `thread/goal/*` app-server methods; Codex's self-started
follow-up turns stay inside one run (so a run can span several provider turns —
`latestProviderTurnForAttempt`). Claude: goal state read from Claude's own messages. Stop pauses the goal
first.

## 5. Messaging between agents and with the human

**Agent → agent.** `t3_thread_send` "Send a message to any T3 thread in this environment"; the message
records `senderThreadId` and `createdBy: "agent"`, `creationSource: "mcp"`. Mode:

- `auto` "starts an idle thread, steers a fully active turn, or queues behind a turn that is not yet
  steerable";
- `queue` "creates a separate follow-up run after active work";
- `steer` "requires a steerable active provider turn";
- `restart` "requires an active provider turn and uses the orchestrator's interrupt-and-restart path".

"The target cannot have broader permission modes than the caller", and changing another thread needs the
caller's live run. `t3_thread_wait` polls a run to terminal; `t3_thread_interrupt` dispatches
`run.interrupt`. Server type: `ThreadManagementSendMode = "auto" | "queue" | "steer" | "restart"`
(`ThreadManagementService.ts`). The `--if-busy refuse|queue|steer|restart` flag is the external CLI's;
the server has no `refuse` mode.

**Human → thread.** Same command, `message.dispatch`, with `dispatchMode`: `start_immediately |
queue_after_active | steer_active {targetRunId} | restart_active {targetRunId} | defer_start
{workspaceStrategy?}`, or `deliveryIntent: "auto"|"steer"|"restart"` resolved under the thread lock by
`CommandPolicy.resolveMessageDispatchIntent`: with an active run, `auto` steers if
`supportsActiveSteering`, else queues if `supportsQueuedMessages`, else restarts if
`supportsSteeringByInterruptRestart`, else queues; a run still `preparing`/`starting` always queues.
Queue control commands: `queued-run.reorder|cancel|edit`, `queued-message.promote-to-steer`,
`queue.resume`. Queued messages are real runs with `status: "queued"` and `queuePosition` in the event log.
Interrupt: `run.interrupt {runId, reason?, holdQueue?}` — Stop sets `holdQueue`, which also "ends the
thread's pull request watches, and stops every delegated task under the thread".

**"Working" section** (beta, per-device toggle; `packages/client-runtime/src/state/threadInbox.ts`, used
by web `Sidebar.logic.ts` and mobile `threadListV2.ts`):

```ts
/** Threads busy with work that does not need the user fold into the Working
    section: a running run, or one stopped with background work that will wake
    it. Approvals, questions, plan prompts, and failures stay in the inbox. */
export function isThreadWorking(thread): boolean {
  if (thread.hasPendingApprovals || thread.hasPendingUserInput) return false;
  if (!threadRuntimeIsActive(thread.runtime) && thread.runtime?.status !== "idle") return false;
  …
  return !(thread.interactionMode === "plan" && thread.hasActionableProposedPlan && runSettled);
}
```

"Requires attention" therefore = a pending approval, a pending user-input question, an actionable
proposed plan in plan mode, or a non-active run (finished/failed). Active = run status `preparing|queued|
starting|running|waiting`, or runtime parked at `"idle"` because `pendingBackgroundTasks` hold completion
(subagent/monitor work that will wake the agent; `shellRuntime` in `packages/client-runtime/src/state/
models.ts`). A thread watching a PR stays in Working (PR #16204). The inbox orders threads "by when each
last came back to the user".

## 6. Scheduled tasks and triggers

`apps/server/src/scheduledTasks/ScheduledTaskService.ts`, `packages/contracts/src/scheduledTask.ts`,
table `scheduled_tasks`. A task = `{title, prompt, enabled, schedule, projectId, threadId | null,
workspaceStrategy, modelSelection, runtimeMode, interactionMode, nextRunAt, lastRunStatus: never|running|
succeeded|failed, runCount, webhook?}`. Schedule union: `interval {everyMs}` (≥1 min on write),
`fixed_time {timeOfDay, weekdays?}`, `webhook {signature: HMAC-SHA256 {header, encoding, prefix?,
secretRef} | null, maxDeliveryAgeMinutes?}`.

- **Clock**: `apps/server/src/scheduling/Scheduler.ts` — one 5-second tick for all registered due-work
  sources; sources "wait for startup recovery". A fixed-time run long past its slot is skipped and
  re-aimed ("Skipping missed schedule task run"), not fired late.
- **Dispatch**: `threadId === null` → `ThreadLaunchService.launch(...)` (fresh thread per run); bound task →
  `threadManagement.sendToThread({…, mode: "queue"})` ("Scheduled prompts must not interrupt tools in the
  bound thread"). Command id `scheduled-task:${taskId}:${epochMs}:${trigger}` (webhook:
  `scheduled-task:${taskId}:webhook:${deliveryId}`) makes each fire idempotent.
- **Webhooks**: each request to the task URL is one run; the prompt sees the request only through
  `{{body.path}}`, `{{headers.name}}`, `{{query.name}}`, `{{body}}`, `{{request}}` placeholders
  (`webhookTemplate.ts`, `webhookRoute.ts`, `webhookVerification.ts`). Public URL comes from T3 Connect's
  relay (`${relayHookBaseUrl}/${taskId}/${token}`); the relay holds requests up to 24 h for an offline
  environment (`MAX_WEBHOOK_DELIVERY_AGE_MINUTES`), with a per-delivery log table.
- **Agent surface**: `schedule_task` (default `bindToCurrentThread=true` in the caller's project: "suits an
  orchestrator that sees every trigger, delegates work, and can dedupe against what is in flight"),
  `run_scheduled_task_now`, list/update/delete. `schedules create …` is the external CLI's verb.
- **PR watching that wakes agents** (`PullRequestWatchReactor.ts`, `pullRequestWatch.ts`, PR #15057, later
  #16208): agent calls `watch_pull_request` (or the user toggles "Watch for changes"); the watch lives on
  the thread's PR link (`ThreadPullRequestLink.watch`). A pass every `SWEEP_MINUTES = 2` reads each watched
  PR once per project; `evaluatePullRequestWatch` reports a check failing, required checks passing, a
  comment/review by someone other than the agent's account, or a new base conflict. The wake and the
  recorded progress commit together in the internal command `thread.pull-request-watch.sync {watch, wake?:
  {messageId, text, notification}}`, rejected if the watch ended or the thread settled/archived. Ends on
  merge/close, settle/archive, user Stop, `unwatch_pull_request`, 8 consecutive non-rate-limit read
  failures, or 10 comment-only wakes in a row (`PULL_REQUEST_WATCH_WAKE_LIMIT`).
- Separately, `PullRequestSyncReactor.ts` discovers each unsettled thread's branch PR, feeding
  auto-settle-on-merge.

## 7. Workspaces and isolation

`ThreadLaunchService.ts` (also the `orchestration.launchThread` RPC and `t3_thread_launch` tool).
Strategy:

```ts
OrchestrationV2ThreadLaunchWorkspaceStrategy = Union([
  {type:"root", branch?}, {type:"existing_worktree", worktreePath, branch?},
  {type:"worktree", baseRef, branch?, startFromOrigin?} ])
```

- `worktree`: optional `git fetch origin <baseRef>`, then `git.createWorktree(...)` under a temporary
  branch `t3/<hash>` renamed in the background ("The server owns worktree naming"; prefix `t3/` per
  PR #16220). Progress is recorded as `prepared-run.progress {phase:"worktree"|"setup"}`; the project's
  setup script then runs via `ProjectSetupScriptRunner` in a terminal. The run sits in `preparing` until
  `prepared-run.release`.
- The thread records its workspace with `thread.metadata.update {branch, worktreePath}`; `AppThread.branch`
  and `worktreePath` are the binding, and `RuntimePolicy` uses `worktreePath ?? project.workspaceRoot` as
  the provider cwd. "Creating a worktree in the task prompt does not update this binding."
- **Retry** (PR #15326): runs store `workspacePreparation`; `prepared-run.retry` puts a failed run back into
  `preparing`, `ThreadLaunchService.retryPreparation` reruns it and reuses an already-created worktree.
  Failure items carry code `workspace_preparation_failed`.
- `ProviderTurnStartService` recreates a missing worktree at the thread's branch before a provider turn.
- Mid-thread move: `t3_worktree_handoff` (`WorktreeMcpService.ts`) creates a worktree, re-points the
  thread, detaches the live provider session, and optionally queues `continuationPrompt` as the next turn.
- Threads without a project run in `~/.t3/scratch/<date>-<words>-<id>` (`scratch: true`).
- **Dev server**: no per-workspace dev-server service in orchestration-v2. A dev server is either agent
  background work (`pendingBackgroundTasks` kind `command`, which does not hold completion or block
  settlement) or a terminal; Stop interrupts every live provider thread owning background work (PR #15355)
  and then `thread.background-work.settle` marks leftovers interrupted. Settling closes idle terminals but
  keeps ones running a command.
- Checkpoint restore is refused when the workspace is shared by another thread (§2), the only isolation
  check found between threads sharing a checkout.

## 8. Durability across server restart

Survives because it is in SQLite: the event log, projections (threads, runs incl. queued runs, subagents
and their `completionDelivery`, runtime requests, context transfers), command receipts, the effect outbox,
scheduled tasks, launch workflows, PR-watch state on PR links.

**Effect outbox** (`EffectOutbox.ts`, `EffectWorker.ts`): rows `{effect_id, command_id, thread_id,
effect_type, payload_json, status: pending|running|succeeded|failed|cancelled, attempt_count,
available_at, lease_owner, lease_expires_at, …}` claimed with a lease (default 30 s, 5 attempts). Effect
types split by restart safety:

```ts
REPLAY_SAFE_EFFECT_TYPES_AFTER_PROCESS_LOSS = ["provider-runtime.continue","provider-session.detach",
  "provider-thread.rollback","checkpoint.capture","terminal.cleanup","attachment.cleanup",
  "thread-title.generate","delegated-tasks.stop"]
PROCESS_BOUND_EFFECT_TYPES = ["provider-turn.start","provider-turn.interrupt","provider-turn.steer",
  "provider-turn.restart","runtime-request.respond"]
```

**Recovery** (`ProviderRuntimeRecoveryService.ts`, `RestartContinuation.ts`,
`docs/internals/server-updates.md` "Recovering interrupted threads", PR #15323):
- Process-bound effects tied to the lost process are retired; non-terminal runs are reconciled against
  provider inventory and terminalized; pending runtime requests become `responseCapability:
  {type:"not_resumable"}` ("server restarted before the provider work completed").
- Queued runs "never started, so recovery holds them" (`queueHeld`) until the user resumes
  (`queue.resume`).
- Restart continuation (environment preference, off by default) records intent as a
  `provider-runtime.continue` outbox effect; the handler rechecks preference, archive state, provider
  selection, newer user work, "a stop the user requested", and maintenance turns before dispatching a
  continuation run with stable ids. Background work the restart cancelled is told to the next provider
  turn once (`restartCancelledBackgroundWork`, `RestartBackgroundNote.ts`).
- Delegated tasks "are reconciled as their own threads"; the orchestrator's startup pass
  (`recoverDelegatedTasks`) settles child results and re-offers completion deliveries; a child with a
  pending continuation is not treated as a result yet.
- Stop intent survives via its command receipt and the receipt-keyed `thread.background-work.settle`.
- Schedulers wait for activation so they cannot start runs reconciliation would cancel.
- Stated limit: "two servers sharing one database remain out of scope" (PR #15323).

## 9. Permissions and safety

`RuntimeMode = ["approval-required","auto-accept-edits","auto","full-access"]`, default `full-access`
(`packages/contracts/src/providerPolicy.ts`). UI names (`docs/user/permission-modes.md`): Supervised /
Auto-accept edits / Auto / Full access. `RuntimePolicy.ts` passes `{runtimeMode, interactionMode, cwd}` to
the adapter; a mode the provider instance does not support runs as `approval-required`.

Mapping:
- **Codex** (`codexRuntimeModeTurnDefaults`, `CodexAdapterV2.ts`): approval-required → `approvalPolicy:
  "untrusted"`, sandbox `readOnly`; auto-accept-edits → `"on-request"`, `workspaceWrite`; auto →
  `"on-request"`, `approvalsReviewer: "auto_review"`, `workspaceWrite`; full-access → `"never"`,
  `dangerFullAccess`.
- **Claude** (`permissionModeForClaudeRuntimePolicy`, `ClaudeAdapterV2.ts`): plan interaction → `"plan"`;
  otherwise approval-required → `"default"`, auto-accept-edits → `"acceptEdits"`, auto → `"auto"`,
  full-access → `"bypassPermissions"` (with sandbox-policy overrides, e.g. read-only → `"dontAsk"`).
- Grok has no auto-accept-edits (runs Supervised); OpenCode and Antigravity fall back to asking under Auto;
  ACP Registry agents get answers to their approval requests per mode. Capability
  `runtimePolicy.enforcement` distinguishes `"native"` from `"client-boundary"` providers ("provider-owned
  execution is not confined").

Unattended threads get no auto-approval beyond the mode: a provider approval becomes a `RuntimeRequest`
(`kind` command/file-read/file-change/…, `status: pending`) answered by `runtime-request.respond
{decision?, answers?}`; it blocks auto-settlement and keeps the thread out of the Working section. A
native subagent's approval surfaces on its parent thread. Requests are respondable only while
`responseCapability.type === "live"`; after restart they are `not_resumable` (`pendingRequestsSurviveRestart:
false` for Codex, Claude, Cursor).

Privilege ceilings for agent-initiated work: delegated children and `t3_thread_send`/`configure` targets
may not exceed the caller's runtime or interaction mode; `t3_thread_launch` and `run_scheduled_task_now`
require "a full-access/default caller".

**Secret-request cards**: `request_secret` posts a `secret_request` turn item (`label, reason, placeholder,
secretStatus: pending|saved|declined|cancelled`) via the internal `secret_request.record` command
("Internal so no client can mark a request saved without the value being stored"); the tool blocks until
answered and returns only a one-use `secretRef` ("The value is kept by the app and NEVER returned to
you"), consumed e.g. by a webhook signature (`apps/server/src/secrets/SecretRequests.ts`).

## 10. RPC surface

WebSocket RPC (Effect `RpcGroup`), names in `ORCHESTRATION_V2_WS_METHODS`
(`packages/contracts/src/orchestrationV2.ts`), wired in `packages/contracts/src/rpc.ts`:

```ts
dispatchCommand: "orchestration.dispatchCommand",      // payload OrchestrationV2Command → {sequence}
getTurnDiff / getFullThreadDiff / searchThreads / getArchivedShellSnapshot /
getThreadProjection / getWorkflowScript / getTurnItem,
launchThread: "orchestration.launchThread",            // OrchestrationV2ThreadLaunchInput → {threadId, projection, resumed}
subscribeArchivedShell / subscribeShell / subscribeThread   // stream: snapshot then events after snapshotSequence
```

`OrchestrationV2ThreadLaunchInput = {commandId, creationSource?, threadId?, reuseExistingThread?,
projectId, title, generateTitle?, modelSelection, runtimeMode, interactionMode, workspaceStrategy,
initialMessage?: {messageId?, text, context?, attachments}}`. Internal commands
(`OrchestrationV2InternalCommand`: `thread.pull-request-watch.sync`, `checkpoint.rollback.fail`,
`thread.background-work.settle`, `thread.stop`, `secret_request.record`) "stay out of
`OrchestrationV2Command`, the `dispatchCommand` payload, so no client can send them."

**Protocol 2** (`packages/contracts/src/environment.ts`): `ORCHESTRATION_PROTOCOL_VERSION = 2`, query param
`orchestrationProtocol`, header `x-t3-orchestration-protocol`. `apps/server/src/ws.ts` rejects a `/ws`
upgrade lacking `?orchestrationProtocol=2` with HTTP 426 `{code: "orchestration_protocol_incompatible"}`.
The environment descriptor advertises `orchestrationProtocolVersion`.

**Scope middleware**: `RpcScopeAuthorization` (`RpcMiddleware.Service` in `rpc.ts`, applied to the whole
`WsRpcGroup`) checks the connection's session scopes against `RPC_REQUIRED_SCOPES`
(`apps/server/src/auth/RpcAuthorization.ts`): `dispatchCommand` and `launchThread` need
`orchestration:operate`; reads and subscriptions need `orchestration:read`. "Adding an RPC to `WsRpcGroup`
without choosing a scope is a type error."

The MCP endpoint (`McpHttpServer.ts`) is a second ingress for agents; it calls the same
`ThreadManagementService`/`OrchestratorV2`, never adapters directly ("The MCP server is a command ingress
into V2").

---

## What I could not determine from the source

- The exact semantics of shell status `"idle"` versus runtime parked at `"idle"` in `isThreadWorking`:
  the code lets `runtime.status === "idle"` count as working, and the comment ties it to background work,
  but I did not trace the server's `ProjectionStore` shell derivation to confirm that a plain idle thread
  never reaches that branch.
- `ProjectionStore.ts` (269 KB) and most of `Orchestrator.ts` (415 KB) were grepped, not read; per-command
  planning details (e.g. full `thread.stop`, `provider.switch`, fork resolution timing) are summarized from
  docs, comments, and the commands' schemas.
- Whether checkpoints are captured per subagent/tool scope in practice, or only `root_run`: the schema
  allows nested scopes; I saw only root-run capture paths.
- Mobile push/notification rules for "requires attention" beyond the shared `isThreadWorking` predicate.
- The external CLI (`@bvdm/t3code-cli`, `--if-busy`, `threads set --provider`, `schedules create`) is not
  in this repo; its mapping onto these commands was not verified.
- How many concurrent runs the effect worker executes across threads (lease/attempt defaults seen;
  concurrency setting not traced).
- Whether provider-native subagents can be forked into first-class threads today (`canForkSubagentThread`
  capability exists; no UI/command path traced).
