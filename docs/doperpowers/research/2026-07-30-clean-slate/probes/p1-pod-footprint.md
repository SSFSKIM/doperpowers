# Probe P1 — cc-harness pod footprint (2026-07-30)

Question: what does ONE cc-harness worker cost in memory and disk, as the
input to pod sizing?

Environment: macOS (Darwin 25.5.0, arm64), Node v24.18.0
(`/Users/new/.nvm/versions/node/v24.18.0/bin/node`). Repo under test:
`/Users/new/developer/github/codex_somersault/CC-to-SDK` (the cc-harness
source tree named in the round brief as Class C live truth). All commands
below were run directly against that tree; credentials were sourced from
its `.env` into the process environment and never echoed, printed, or
logged — only the variable *names* were inspected (`sed
's/=.*/=<redacted>/' .env`), which showed one active credential:
`CLAUDE_CODE_OAUTH_TOKEN` (an `ANTHROPIC_API_KEY` line exists but is
commented out).

**Top-line numbers for pod sizing:**

| Quantity | Value |
|---|---|
| Disk — harness dev install (`node_modules` incl. devDeps) | 414M |
| Disk — harness **prod-only** install (`npm ci --omit=dev`) | 312M |
| Disk — native `claude` CLI binary the SDK wraps (single Mach-O) | 245M (256,908,272 bytes exact) |
| Disk — harness build output (`dist/`) | 1.6M |
| Memory — harness wrapper process, idle | ~70–105 MB RSS |
| Memory — native `claude` subprocess, during one active turn | 350–413 MB RSS (climbing, did not plateau before erroring) |
| Node version | v24.18.0 (package.json requires `>=18`) |
| Native (compiled) deps in node_modules | 2 — both devDependency/build-time only (`fsevents`, `@rollup/rollup-darwin-arm64`), not shipped in a prod-only Linux install |

## (a) Disk

```
$ cd /Users/new/developer/github/codex_somersault/CC-to-SDK/harness
$ du -sh node_modules
414M	node_modules
$ du -sh dist
1.6M	dist
$ du -sh node_modules/@anthropic-ai/claude-agent-sdk
4.1M	node_modules/@anthropic-ai/claude-agent-sdk
$ du -sh node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64
245M	node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64
$ ls -la node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/
-rwxr-xr-x@ 1 new  staff  256908272  claude   # exact bytes
$ file node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude
node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude: Mach-O 64-bit executable arm64
```

The dominant disk cost by far is **not** JS/TS code — the harness's own
build output is 1.6M — it is the **native CLI binary** the SDK ships as a
platform-specific optional dependency
(`@anthropic-ai/claude-agent-sdk-darwin-arm64`, v0.3.220, 245M single
binary). `@anthropic-ai/claude-agent-sdk` (the JS wrapper package,
`sdk.mjs`/`sdk.d.ts`/`bridge.mjs`) is only 4.1M; it shells out to the
native binary as a subprocess (confirmed live in §b — the process tree
shows `node dist/cli/bin.js` spawning
`.../claude-agent-sdk-darwin-arm64/claude --output-format stream-json
--verbose --input-format stream-json --effort xhigh --model
claude-opus-4-8 --tools default --setting-sources=user,project,local
--permission-mode auto`).

**Dev vs prod-only install.** A clean `npm ci --omit=dev
--ignore-scripts` against the harness's own `package.json` +
`package-lock.json` (copied to a scratch dir, not touching the working
tree) drops the tree from 414M to 312M:

```
$ npm ci --omit=dev --ignore-scripts
added 147 packages, and audited 148 packages in 2s
$ du -sh node_modules
312M	node_modules
```

The 102M cut is devDependencies (`vitest`, `typescript`, `tsx`,
`ink-testing-library`, `@electric-sql/pglite`, `@types/*`). The 245M
native binary is a **production** dependency (it's what actually runs
turns) and survives the prod-only install — it, not JS tooling, is the
floor for a deployed pod's image size. Sibling packages in the monorepo
add further disk if co-located in the same image (not part of one
worker's footprint, listed for context only):
`app-server/node_modules` 352M, `Claude Code Src/node_modules` 166M,
`probes/node_modules` 317M — a pod running only the harness worker
should not need these.

## (b) Memory

Command (credentials sourced, never echoed):

```
$ cd .../CC-to-SDK/harness
$ set -a && source ../.env && set +a
$ node dist/cli/bin.js -p "reply with the single word: pong"
```

`ccx -p` is the smallest real one-shot invocation of the harness (per
`dist/cli/args.js`, `-p`/`--print` = one-turn print mode; `serve` is the
long-running daemon variant, also probed below for its idle baseline).

Sampling `ps -eo pid,ppid,rss,command` at 0.4–0.45s intervals from launch
(harness PID 39939, native CLI child PID 39949) gave:

| t (s from launch) | harness wrapper (`node dist/cli/bin.js`) RSS | native `claude` subprocess RSS |
|---|---|---|
| 0.00 (spawn) | 1,120 KB (just forked) | — (not yet spawned) |
| 0.44 | 104,256 KB (~102 MB) | 353,568 KB (~345 MB) |
| 0.89 | 104,640 KB (~102 MB) | 388,480 KB (~379 MB) |
| 1.34 | 104,640 KB (~102 MB) | 401,584 KB (~392 MB) |
| 1.81 | 104,688 KB (~102 MB) | 411,376 KB (~402 MB) |
| 2.28 (child exited) | — | — |

The run terminated with `ccx: Claude Code process exited with code 1`.
Running the native binary directly with the same sourced credentials
(`node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude -p
"reply with the single word: pong"`) surfaced the real cause on stderr:

```
You've hit your weekly limit · resets Aug 3 at 12am (Asia/Seoul)
```

The sourced `CLAUDE_CODE_OAUTH_TOKEN` is a subscription OAuth credential
already at its weekly quota in this environment, so **no successful
model turn was observed** — the reported "active turn" memory (350–413
MB, still climbing when the process errored out) reflects CLI process
startup, permission-rule loading, and request construction up to the
quota check, not a completed round-trip. This is a hint, not a ceiling:
a real active-turn RSS (with output-token buffering, tool-result
accumulation, and a fully generated response) should be **re-measured
in-cluster with a working credential** before it is used to size pod
memory limits — treat 400+ MB as a floor, not a peak.

This also independently corroborates R1's fleet-auth question in the
round brief ("API-key/LLM-gateway virtual keys, never OAuth
subscription") — a subscription OAuth token is unsuitable for unattended
fleet workers not just on policy grounds but because it visibly runs out
mid-probe on a single machine; a fleet of many workers would exhaust it
far faster.

**Idle baselines observed on the same box (context, not part of the
`-p` measurement):**
- A leftover `ccx serve` daemon from an earlier session on this machine
  (`node dist/cli/bin.js serve --listen ws://0.0.0.0:9711 ...`) sat at a
  steady **~69–71 MB RSS** with no active connections — this is the
  daemon-mode idle floor for the harness wrapper alone (no native CLI
  child spawned until a session is created).
- A separate persistent `/Users/new/.local/bin/claude daemon run`
  process (the installed Claude Code CLI's own daemon, unrelated to
  cc-harness but same native binary family) held steady at
  **~121–123 MB RSS** idle.

## (c) Node version and native deps

```
$ node -v
v24.18.0
$ cat harness/package.json | grep -A2 engines
  "engines": { "node": ">=18" }
$ find node_modules -name "*.node"
node_modules/fsevents/fsevents.node
node_modules/@rollup/rollup-darwin-arm64/rollup.darwin-arm64.node
```

Both native (compiled) addons are **devDependencies / build tooling**
(`fsevents` — file watching, dev-only; `@rollup/rollup-darwin-arm64` —
a platform-specific optional dep of a build dependency, likely pulled in
transitively). Neither ships in the `npm ci --omit=dev` prod install
measured above. The one genuinely load-bearing "native" artifact is the
245M `claude` Mach-O binary itself, which is a platform-specific npm
optional dependency (`@anthropic-ai/claude-agent-sdk-<platform>-<arch>`),
not a compiled addon linked into the Node process.

## macOS caveat — what a cluster environment must re-measure

Every number above was gathered on **macOS arm64**, and the round's
target pods are **Linux + gVisor** (per the 2026-07-30 pivot). Treat
these as directional inputs, not final sizing numbers. Specifically
re-verify in-cluster:

1. **Disk — different binary entirely.** The 245M figure is the
   `darwin-arm64` optional dependency. A Linux pod pulls
   `@anthropic-ai/claude-agent-sdk-linux-x64` (or an arm64/musl variant
   depending on base image) — a different binary with potentially
   different size; do not carry 245M forward without re-running `npm
   ci`/`du -sh` on the actual pod base image.
2. **Memory — gVisor overhead is unmeasured here.** gVisor (`runsc`)
   intercepts syscalls in userspace and is known to add both memory and
   CPU overhead per process/pod versus a native Linux container; none of
   that overhead is present in this macOS host measurement. Re-measure
   `ps`/`cgroup` RSS for the harness + native-CLI process pair *inside* a
   gVisor sandbox, not just inside a plain container.
3. **Memory — no completed turn was observed.** Because the sourced
   OAuth credential was already over its weekly quota, the "active turn"
   numbers here stop at request-construction, before any response
   tokens were generated or accumulated. In-cluster measurement needs a
   **non-quota-limited credential** (an API key or gateway virtual key,
   consistent with R1's fleet-auth stance) and should sample RSS through
   a full multi-turn session, including with tool calls (Bash/Read/
   Write), since those buffer additional output in the harness process.
4. **Concurrent workers on one pod vs one-worker-per-pod.** These
   numbers are for a single `-p` invocation. If the pod design runs
   multiple concurrent harness sessions per pod (vs. Agent Sandbox's
   claim-a-pod-per-run model under discussion in R2), multiply the
   ~400 MB/session working-set estimate accordingly and re-check for
   shared-page savings (the native binary's read-only segments should be
   shared across forks/execs of the same binary on Linux, unlike this
   ad hoc single-run macOS test).
5. **Baseline daemon overhead.** The idle `ccx serve` daemon (~70 MB)
   and the idle native-CLI daemon (~122 MB) were incidental
   observations from other processes already running on this dev
   machine, not a controlled measurement — re-run `ccx serve` cleanly
   in a container with no prior state to get a trustworthy idle-daemon
   number for the "warm pool" pod-sizing input R2 needs.

## Commands log (for reproducibility)

```bash
cd /Users/new/developer/github/codex_somersault/CC-to-SDK/harness
du -sh node_modules dist
du -sh node_modules/@anthropic-ai/claude-agent-sdk
du -sh node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64
stat -f%z node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude
file node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude
find node_modules -name "*.node"
node -v

# prod-only install size (scratch copy, not the working tree)
cp package.json package-lock.json <scratch>/ && cd <scratch>
npm ci --omit=dev --ignore-scripts && du -sh node_modules

# memory: idle + active-turn sampling (credentials sourced, never echoed)
set -a && source ../.env && set +a
(node dist/cli/bin.js -p "reply with the single word: pong" > out.log 2>&1 &)
# poll: ps -eo pid,ppid,rss,command | grep -E "dist/cli/bin\.js|claude-agent-sdk-.*-arm64/claude"

# root cause of the "exited with code 1": run native binary directly
node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude -p "reply with the single word: pong"
# -> "You've hit your weekly limit · resets Aug 3 at 12am (Asia/Seoul)"
```
