# EN / G1 code map: `spawn --on`, `vm owner`, notices to a thread

> For the plan of child **EN**, group **G1**, of `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`.
> Read 2026-11-21 at doperpowers `origin/main` **`dba3f5e8`** (sminos 1.52.1, devcloud 0.17.3), worktree
> `.claude/worktrees/sminos-channels-en-docs`. `S/` = `sminos/skills/sminos/scripts/`, `D/` = `devcloud/`. Every line
> number is at that commit.
>
> **[read]** = seen in code at the place named. **[inf]** = inference. **[not found]** = looked, absent (where is said).
>
> **Copied into the tree on 2026-11-21** by the author of the plan it serves
> (`docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md`), who re-read against `origin/main` `5a5ec39d`
> every claim that plan leans on. `5a5ec39d` is one merge later (sminos 1.52.2: the bridge's mods alone), and no line
> cited here moved. What that reading changed is marked where it stands: **[corrected]** for a statement that was wrong
> or an inference the code settles, **[added]** for a fact the map did not hold. Nothing else was changed.
>
> Who read what: I read the notice path end to end (§5), the creator's storage on host and provider (§4, §6), the
> enrollment condition, `cmd_say`/`deliver_say`/tag resolution, and the `lease` verb's host channel. Four sonnet readers
> took spawn/machines/say fields (§1, §3, §8), the host and `vm up` (§2, §4), ownership/verbs/tests (§6, §7, §9) and the
> taught surface (§10). I re-read every citation the opening findings lean on.

## The findings to plan around

**1. A devcloud VM is a sminos machine only when `up` is given the MAWS project.** `compose.provisions` is
`bool(profile.maws_secret) and any(devenv_args(entry)[0].lower() == MAWS_PROJECT ...)`, `MAWS_PROJECT = "maws"`
[read `D/driver/compose.py:37,40-45`; called `D/driver/up.py:126`]. Without it the descriptor carries no
`DEVCLOUD_MAWS_*` keys [read `compose.py:72-74`], boot step 11 returns `"sminos: not enrolled, local-only"` and installs
no daemon [read `D/boot/devcloudlib/sminos_host.py:165-166`], and step 13 is skipped. A unit test pins it:
`test_a_vm_without_the_maws_project_is_not_enrolled` [read `D/tests/unit/test_driver_up.py:175-180`]. `up` neither
warns nor fails then. Consequences on such a VM: a `sminos spawn` run there makes a seat no other machine sees, and its
notices never reach sminos at all. `notices.deliver` runs `say` only `if program and sminos_host.cut_over(user, env)`,
otherwise journal and `wall` [read `D/boot/devcloudlib/notices.py:26,43-44`]. D4's "`--on new` runs `devcloud vm up` ...
sminos waits for the machine's enrollment" therefore holds only if `--on new` passes `--project maws` (or
`<owner>/MAWS`) and the profile has `[desk] provisioning_secret_v2` + `delegation_id` [read `D/driver/profile.py:218-231`].
Even then `up` may return with step 13 `deferred` and exit 0, printing `maws      deferred: <detail>`
[read `up.py:198-200`]. The host's `devcloud-enroll` service retries every 300 s [read `D/boot/devcloudlib/services.py:33,65`].
The skill's "on the tailnet and the desk" [read `D/skills/vm/SKILL.md:11`] is true only for such VMs.

**2. A notice moves to its fallback only on a non-zero exit of `say`, and a thread on another machine that is held
gives exit 0.** `deliver` goes `if d.creator and send([f"{d.creator} {text}"]) == 0: return`, then
`--project <creator_project>` (a live-only broadcast), then `--in` on exit 4 [read `notices.py:35-42`]. On the VM,
`cmd_say` → `deliver_say`. A recipient that is not local prints `remote_line(member) or "recorded (on <machine>)"`,
nudges the daemon and `continue`s [read `S/sminos.py:9075-9082`]. `cmd_say` then returns, so the exit is 0.
`remote_line` gives the X3 words for `held` with every `why`: `mode`, `transcript`, `cwd`, `config`, `protected`,
`failed`, `read-only` [read `S/sminos.py:6888-6902`, `HOLD_WORDS` 6914-6922]. So a notice to an owning thread its machine
will **not** wake is recorded and held there, and goes no further: no live member hears it. Only these exit non-zero and
fall back:
- an ended thread: `ended_refusal`, exit 4, via `unreachable_hint` [read 8226-8237];
- no member answering: `no_member`, exit 4 [read 8241-8261].

D4's "when that thread cannot be woken, devcloud's order holds as today" needs a signal `say` does not give today.

**3. The creator is stored in three places, in two forms, and nothing rewrites them after `up`.**
- Provider label `devcloud-creator=<8-hex short>`, alphabet `[a-z0-9-]{1,63}` [read `up.py:150,162`; `compose.py:171-177`; `D/driver/labels.py:10,16`].
- The host's descriptor `/etc/devcloud/boot.env`: `DEVCLOUD_CREATOR=@<short>` and `DEVCLOUD_CREATOR_PROJECT=<project name>` [read `compose.py:66-67,75-79`; parser `D/boot/devcloudlib/descriptor.py:35,178-180,228-231`].
- For an adopted machine, the Mac-local record's `creator` (bare short) and a descriptor `@short` with **no** creator project [read via reader: `D/driver/adopt.py:185,192,280-282`].

The host reads only its descriptor, and re-reads it every lease tick (`d = load()` under the lock,
`D/boot/devcloudlib/lease.py:256`; tick every 300 s, `services.py:33,63`). `owned-by` and `ls` read only the label or
record. So `vm owner` has to write the host (creator **and** creator project) and the label or record. The precedent is
`vm lease`: host first under its lock (`hostctl.lease_set` → `devcloud lease set` over ssh), then
`client.set_labels(..., merge=True)` with what the host printed [read `D/driver/ops.py:160-193`; `D/driver/hostctl.py:190-211`].
`set-labels` is a mandatory provider op, round-tripped by the conformance suite [read `D/driver/provider.py:228-234`;
`D/driver/conformance.py:131-139` via reader]. The host CLI has no verb that writes the creator; `set_expires` is the only
descriptor rewrite [read `D/boot/devcloud:14-21`; `descriptor.py:234-252`]. A host built from an older recipe will not
have a new host verb.

**4. Over ssh, the VM's `sminos spawn` has no spawner.** `caller_alias()` returns `desk_member()` when
`CLAUDE_CODE_SESSION_ID` is unset [read `S/sminos.py:4167-4174`]. So the preamble says "spawned by the operator", `joined.by`
is empty, and provenance is the VM machine's default owners with `origin {"kind":"sminos-spawn"}` and no `spawnerSession`
[read via reader: `render_preamble` 13615, `spawn_provenance` 14059]. `vm ssh` forwards no environment
[read `D/driver/ssh.py:47-57`]. Carrying the spawner (for the reply line and for reach) is new surface on both ends.

---

## 1. `sminos spawn` today

**Flags** [read `S/sminos.py:18760-18777`, `route_flags` 18751]:
- positionals: `alias`, `task` (`-` = stdin, read by `stdin_body` 19073-19092 before `cmd_spawn`; a tty gives exit 2 `"spawn -: the text is read from standard input; ..."`);
- `--role`, `--brief` (None ≠ empty, for a refill), `--cwd`, `--worktree`, `--stamp FIELD=VALUE` (repeatable; credential-shaped names refused, exit 2);
- `--permission-mode` (default `auto`), `--no-wait` (ignored), `--model`, `--settings`, `--effort`, `--wait`.

No `--project`, `--json` or `--on`. An argparse error exits 2.

**Where things come from** (`cmd_spawn` 14095, `spawn_fresh` 13775) [read]:
- cwd: `abspath(a.cwd or os.getcwd())`. A missing directory or a TCC refusal exits 2 (`cwd_or_die` ~13737).
- group: `derive_group(cwd)` (11694), the owning repo's basename (a worktree maps to its main checkout), else the cwd basename.
- project: `seat_project` (2168) → `resolve_project` (2136), always from the directory. In order: `.smns` up the tree; else on an enrolled machine the project the git remote derives; else the machine's own project; else `local-<dir>`.
- model: `a.model`. settings and effort: flag else `DAEMON_CLAUDE_SETTINGS` / `DAEMON_CLAUDE_EFFORT`.
- `--settings` is a *local file*, merged into `$SMINOS_HOME/settings/<sha>.json` (13656). A Mac path on a VM gives exit 2.
- No machine policy or ceiling is consulted by `cmd_spawn`. The ceiling applies only in RPC `admit_spawn` (`S/sminos_rpc.py:1599`).

**Order of writes** [read]:
1. seat lock;
2. refusals: filled seat exit 4; old occupant still answers exit 4; alias held by a human-opened member exit 4 (`"... its sessions are its human's to open — spawn under another alias"`);
3. `finish_thread`;
4. preamble + brief + task (`compose_task` 13628);
5. launch id + pending provenance;
6. `run_claude_bg` (12746): `claude --bg --permission-mode M -n <alias> [--worktree] [--model] [--settings] [--effort] <task>` with `cwd=cwd`, env = `launch_env` (12712; os.environ minus MAWS/SMINOS launch keys), stdin DEVNULL, timeout 300; the short id is parsed from `^backgrounded · ([0-9a-f]+)`;
7. provisional seat record, or a journaled refill;
8. `poll_uuid` (12853) via `claude agents --json --all`, about 60 s;
9. the record renamed to `<session uuid>.json` (seat id = first session id);
10. provenance bound;
11. `ensure_record`;
12. `threads.ensure` (thread record, `launch`);
13. project-log events under `<machine>/<uuid>`: `joined` (with `by`, `machine`, `cwd`, `repo`, `branch`), a displaced session's `retired replaced`, then `in-charge`. A failed append warns, exit stays 0;
14. `--wait` polls up to `DAEMON_TIMEOUT` (18000 s).

**Output** [read]: one stdout line, `seat spawned: <group>/<alias>  [<short> / <seat-id>]  status=<s>[  worktree=...]  (reply: sminos reply <short>)`.
A refill prints `seat re-filled:`, and `<seat-id>` is then the seat's, not the new session's. Exit codes:

| exit | meaning |
|---|---|
| 0 | spawned |
| 1 | banner not parsed (`"sminos: spawned failed — could not parse background id from:"`), uuid poll failed, watcher expired |
| 2 | usage, cwd, settings |
| 4 | seat refusals |

The existing machine parser is the desk RPC: `SEAT_RE = \[[0-9a-f]+ / ([0-9a-f-]{36})\]` plus `--stamp rpc_nonce=<op>` to find the seat by stamp [read `S/sminos_rpc.py:279,2332-2354`]. That is the precedent for a remote caller.

**What assumes this machine** [read]: `claude` on PATH and its `agents` list; local cwd/TCC; `$SMINOS_HOME` (seats, `locks/`, `settings/`, `threads/`, logs); `host_name()`/`boot_id()` in the record; the caller's `CLAUDE_CODE_SESSION_ID` (`by`, provenance); a local `--settings` file. No daemon is needed synchronously.

**Where `--on` enters, and what to carry** [inf]:
- Where: in the parser and at the top of `cmd_spawn`, before `cwd_or_die`/`derive_group`. By then `stdin_body` has turned `-` into text, so the task can be piped over ssh stdin. `ssh.run` sends `input=b""` to every probe [read `D/driver/ssh.py:59-66`], so `ops.ssh`'s lifecycle probe does not eat a piped stdin, and `interactive` inherits it [read 101-103].
- Carry: task (stdin); alias, role, brief, worktree, model, effort, permission mode; `--stamp` for correlation; a `--cwd` that is a **VM path**. The portable key is the project id. The VM-side id → checkout mapping exists as `policy.known_checkouts(project)` [read via reader `S/sminos_policy.py:131`]. Also the spawner's identity (finding 4) and settings as content, not a path.

## 2. Running sminos on a VM by hand today

**`devcloud vm ssh <name> [--root] -- cmd...`**:
- [read `D/driver/cli.py:148-151`; `ops.py:145-157`] `adopt.load` else `ctx.find` (lists every account). Unless `--root`, one probe `cat /var/lib/devcloud/status.json`; a departing/held/departed host is refused, exit 1.
- Quoting: one argument is passed as a shell line, several go through `shlex.join` [read `ops.py:156`]. A quoted `'~/x'` is not expanded on the host (`test_driver_cli.py:71-74`). Pass absolute paths, or one shell-line argument.
- [read `ssh.py:47-57,100-102`] `ssh -i <driver key> -o BatchMode=yes ... -o ServerAliveInterval=5 -o ServerAliveCountMax=3 -T|-t -- <DEVCLOUD_USER>@<vm-name> <line>`: `-t` when there is no command or stdin is a tty. Inherited stdio; the return is ssh's code (255 for an ssh failure).
- Driver failures exit 1-7 with `devcloud vm: <msg>` on stderr. They overlap with remote codes and are told apart only by text [inf].

**Host side**:
- [read via reader `D/image/setup.sh:54-57,100-113`] shell `zsh -c`, non-login, non-interactive. `/etc/zsh/zshenv` puts `~/.local/bin` on PATH and sources `/etc/devcloud/env`.
- `/usr/local/bin/sminos` → the marketplace copy's launcher, linked at step 11 because the profile's alias is interactive-only [read `sminos_host.py:127-148`]. That followed observation M4, `"command not found"` (`docs/doperpowers/specs/2026-10-21-devcloud-vm-driver-design.md:1926-1930`).
- cwd is `$HOME` (sshd's default) [inf]. The home path equals the Mac's by design (`setup.sh:8-10`).
- Repositories: `~/Developer/GitHub/<repo>`, via step 12's `devenv up` (`SKILL.md:12,64`; `lease.py:33`).

**sminos copy**: a root-owned clone `/var/lib/devcloud/marketplaces/doperpowers` [read via reader `D/boot/devcloudlib/plugins.py:30,75-114`]. It is reset to its declared source's head at boot/reconcile/config pull (30 min). No version check. **[corrected]** A pin is possible: `declared_source` reads an optional `ref` from the marketplace's declaration in the synced settings, and the clone and every fetch follow it (`plugins.py:64,101,105`). So the VM's sminos tracks that ref's head, and the default branch's when the settings declare none.

**Daemon**: installed and started only on a machine that is cut over or provisioning (finding 1) [read `sminos_host.py:158-200`].

**Enrollment and name**:
- [read via reader `D/boot/devcloudlib/maws_host.py:88-102`] step 13 pipes the code to `mawsd endpoint provision --name <DEVCLOUD_NAME> --wait 120`. The first welcome writes `$SMINOS_HOME/daemon/identity.json` (`cut_over`) [read `sminos_host.py:84-92`].
- Hostname = VM name (`hostnamectl`, `D/boot/devcloudlib/steps.py:151-163`). The sminos machine name = identity's `name`, else `DAEMON_HOST`, else the hostname [read `S/sminos.py:12626-12639`]. The endpoint may rename a machine, so VM name == machine name is [inf], with no check in code.

**`claude`**: talks to the person's gateway through managed `env.ANTHROPIC_BASE_URL`; no model credential on the host [read via reader `steps.py:677-710`]. No keychain issue on Linux [inf].

**`sminos spawn` over that ssh**: cwd `$HOME`, so project `@<vm>` (the machine project) unless `--cwd` names the checkout. That is why the skill passes `--cwd ~/Developer/GitHub/<repo>` [read `SKILL.md:65`]. No session id (finding 4).

**Practised path**:
- [read] skill `SKILL.md:62-71`.
- Acceptance 3 of 2026-10-21: `devcloud vm ssh <n> -- sminos spawn acc "reply ok and stop" --cwd ...`, then the seat seen from the MacBook in `sminos list --org`. It passed: "an operator prompt reached a seat as the human's words" (`docs/doperpowers/plans/2026-10-21-devcloud-vm-driver-report.md:40`). That was under the v1 desk enrollment, before MAWS v2 [inf].
- Acceptance 5 there: the lease warning reached the creating session after 8m22s (`:41`).
- [not found] Any end-to-end test of `vm ssh -- sminos spawn` in the tree; any friction note newer than M4.

## 3. Machines as sminos knows them

- **`sminos machines`** (`cmd_machines` `S/sminos.py:17773`) prints `MACHINE STATE LIVE PROJECTS` from `daemon/org.json`. That frame is restated only at a connection or an org change, and an age line appears past 60 s. Entries keep `{name, online, seen, retired}` [read via reader `S/sminos_uplink.py:446-463`]. **[added]** `online` says nothing: "The endpoint carries no presence (it sends every machine `online: false`, and `seen` only as of its last restatement)" (`cmd_machines`' docstring, `S/sminos.py:17777`), and the STATE column is `last event … ago`, from `seen` and the logs. Nothing a sender holds says whether another machine is connected. Not enrolled: `"this machine is not enrolled at a desk hub (mawsd endpoint enroll): it knows only itself"`.
- **Telling a VM from a Mac** [not found]: no platform, os, kind or devcloud field on a machine row, `org.json` entry, `joined`, presence frame (`S/sminos_hublog.py:635`) or `identity.json`. The Mac-side sources that do know which names are VMs:
  - `devcloud vm ls --json` (`name`, `creator`, `lifetime`, ...; it runs the reaper and ssh probes first) [read via reader `ops.py:77-123`];
  - `ctx.find` / `fleet`;
  - the adoption records `~/.local/state/devcloud/adopted/<name>.json`;
  - the label `devcloud-enroll=key` on a VM made to enroll [read `test_driver_up.py:171`].

  sminos maps no devcloud name to a machine name [not found].
- **"I am on a devcloud VM"**: `/etc/devcloud/boot.env` exists. devcloud tests exactly this three times, each printing `devcloud vm: this machine is a devcloud host; drive from a Mac` with exit 6 [read `D/driver/cli.py:29,145-147`; `D/boot/devcloud:60-62`; `D/bin/devcloud:41-45`]. sminos never tests it [not found: no `/etc/devcloud`, `boot.env` or `SESSION_MIRROR_HOST` under `sminos/`]. Its only devcloud signal is `owned-by` exit 6, read as none (`S/sminos_threads.py:2004-2040`). Exit 6 also means "no seed key" or "no driver in this copy" (`cli.py:158-160`; `D/boot/devcloud:67-69`), so it is not a VM test.
- **Every devcloud mention in sminos**:
  - docs strings (`sminos.py:27,135`, `SKILL.md:54`);
  - retire/end guards (`sminos.py:5073,16612-17047`);
  - `owned_by` and friends (`sminos_threads.py:1921-2294`);
  - the daemon's census and the env it forwards (`sminos_daemon.py:1409-1982,2647-2652`);
  - the bridge's secrets-guard marker (`hooks/mods/bridge.tsx:1717`);
  - a comment in `hooks/mods/backticks.tsx:23`;
  - the test isolation (`tests/devcloud_isolation.py`, `devcloud-isolation.sh`).
- **Enrollment, observably** [read via reader]:
  - On the VM: `identity.json` written at the first whole welcome (`S/sminos_rl10.py:371-394`), and a daemon.log line `rl10: cut over: this machine is <name> of org <org> ...`.
  - On the Mac: the name appears in `org.json` → `sminos machines` at the next `org` frame (lag up to that frame's age), and the VM's machine project `@<name>` appears in the directory. No event in any project log marks it.
  - On the new machine, the first `<machine>/human` append in a hub project is *queued* until the upstream's head is seen, printing `it waits in <project> for the upstream's head of <writer> (this machine's enrolment is new): ...` (`S/sminos.py:3057,3135,3231`). This bites a notice sent right after enrollment.
  - devcloud's driver already runs `sminos machines` (30 s timeout) and parses the table (`D/driver/context.py:324-358`) to avoid name clashes (`taken_names` 248-257).
- **Timing** [read via reader]: `up` total was 2m24s–5m12s across 2026-10-21/22 reports (`2026-10-21-devcloud-vm-driver-design.md:65-77,1823-1826,1981-2041`). [not found] Any timing for `--project maws` provisioning to welcome. The design says "within seconds" (`D/README.md:517`).

## 4. `devcloud vm up`

- **Flags** [read via reader `cli.py:50-62`]: `--label` (default `vm`), `--project` (repeatable `owner/repo[@ref]` or registry name), `--account --type --location --disk --spot --confirmed --dry-run`, and `--ttl D | --keep`.
- **From the cwd**: nothing but the first project's `devenv/host.toml`. It is read from a local checkout whose GitHub origin matches the project, else via `gh api` [read via reader `context.py:106`, `D/driver/hostfile.py:87-111`]. No label, project, branch or repository is derived from the directory (`up.py:125`). The VM clones each project's default branch unless `@<branch>` is given (`SKILL.md:33-37`).
- **Kept vs leased**: `lease = None if opts.keep else duration(opts.ttl) if opts.ttl else profile.caps.lease_default` [read via reader `up.py:89`]. The default is kept only while the profile's `[caps] lease_default` is unset (`profile.py:50-54`).
- **Caps** [read via reader `D/driver/caps.py:32-46`]:
  - limits: unconfirmed alive ≥ 3 (every account, kept and leased); vCPU > 8; added disk > 200 GB. Consent is `--confirmed` only (no prompt, no env).
  - A refusal prints the `account ...` and `caps      unconfirmed 3/3 over, ...` lines to stdout, then one stderr line with exit 4, e.g. `devcloud vm: over the count cap (3 unconfirmed alive, cap 3): ask the person, then pass --confirmed`.
  - A post-create `recount` can delete the VM just made and exit 4 (`up.py:211-233`).
- **Exit codes** (`D/driver/errors.py:3-10`; one stderr line `devcloud vm: <msg>`):

  | exit | meaning |
  |---|---|
  | 0 | ok |
  | 1 | failed, including boot failed, boot not finished in 15 min and key not in config repo; the VM is kept |
  | 2 | usage |
  | 3 | provider or cloud refused (quota, type unavailable) |
  | 4 | cap |
  | 6 | not a driver (host / no seed) |
  | 7 | provider unusable |
  | 130 / 143 | signals |
- **Success output**: stdout only, no `--json` [read `up.py:178,198-207`]. Lines: `created   <name> (id …) from …`, optionally `maws      deferred: …`, then `<name>  ready in <m>m<ss>s`, `  tailnet   <name>`, `  lease     none (keep)` and so on. The name is on `created` (as soon as the server exists) and on `ready in`.
- **When it returns**: `wait_boot` polls `status.json` until every step is recorded or one fails, within `BOOT_WAIT = 15*60` [read via reader `up.py:19-21,236-268`]. So on return the tailnet is attached, projects are cloned and set up, the daemon is started (finding 1's case), and step 13 is ok or deferred. Visibility in the Mac's `sminos machines` is not checked.
- **Creator**:
  - `Context.creator` → `session_creator(env)` runs `sminos who --session $CLAUDE_CODE_SESSION_ID` and matches `^Sminos-Session: (?:[^\n#]+#)?([0-9a-f]{8}) \(([^\s()]+) on [^\s()]+\)$`, giving `("@short", short, project)` [read `D/driver/context.py:99-101,361-379`].
  - No session id, or no CLI, or no match: `(None, None, None)` silently. The VM then has no creator label and no descriptor creator, so its notices go to journal and wall, and `owned-by` matches nothing [read `compose.py:66,176`].
  - The creator is not a flag: whoever runs `up` with a session id in env is the creator.

## 5. Notices, end to end

**On the VM**:
- The `lease` service (`devcloud lease tick`, every 300 s, persistent hosts only) [read `services.py:33,59-65`] loads the descriptor under the lifecycle lock each tick [read `lease.py:214-222,256`].
- The lease warning is due at `expires - 30 min`, once per lease value (`warned_for`) [read `lease.py:32,262-276`].
- The idle notice: `idle.observe`/`check` [read `D/boot/devcloudlib/idle.py:86-123`]. It is skipped for an adopted machine and for anything that is not a persistent vm (`idle.py:91,103`). Activity means any `~/.claude/projects/**/*.jsonl` written since the last check, a 15-minute load ≥ 0.5, or a loginctl session with a TTY (`idle.py:20-51`). Due after `INTERVAL = 3*86400` idle and again every 3 idle days (`idle.py:17,115-117`).
- Both notices go to `notices.deliver(user, d, text)` [read `idle.py:129`; `lease.py:306-309`].
- Texts [read]:
  - idle: `devcloud on {name}: idle {Nd Nh}; last active {iso}; {lease ends at … | runs until down}[; estimated cost so far X CUR]; unpushed: {…|none}; end it with devcloud vm down {name}` (`idle.py:71-82`);
  - lease: `devcloud on {name}: lease ends at {iso}; unpushed: {…|none}` (`lease.py:301-303`).

**`deliver`** [read `notices.py:9-44`]:
- Env: `/etc/devcloud/env` + the user's env with `CLAUDE_CODE_SESSION_ID` popped. Command: `/usr/bin/python3 <clone>/sminos.py say ...` as the user, cwd `$HOME`, timeout 120.
- Order:
  1. `say "@<short> <text>"`;
  2. if that is non-zero, `say --project <creator_project> <text>`;
  3. on exit 4 of that, `say --in <creator_project> <text>`;
  4. else print and `wall`.
- Only the exit code is read (stdout ignored). Nothing runs when the machine is not cut over.

**What that `say` does** [read `S/sminos.py:9228-9289`]:
- With no session: `sender, writer, kind = "human", writer_id(), "human"`. The writer is `<vm>/human`, or `<vm>/human~<digest>` for an audience stream (per the reader: `streams_for`/`keep_stream`). `home = caller_project()` from `$HOME`, which is the VM's machine project [inf].
- Tag resolution `_resolve_tag` [read 8288-8335]: a bare `@<8hex>` with a non-None home is tried as an alias in home, then `match_members(name, "", org_scope(), alias=False)`, i.e. **ids across every project the VM knows**. `id_reach` matches the session or its 8-char prefix, then `former_ids(m)`: `m.former` (continuations) + `m.thread_sessions` + the thread id [read 8048-8067]. So a former session's short reaches the thread's current session (X2), on the VM, from the VM's own projection of the owner's project log. The tag resolves to a session at send time and the event's `to` holds that session id. The Mac delivers only to `to` sessions (`_addressees` 6685-6694; `deliver_owed` `S/sminos_daemon.py:965-980`). If the VM's projection lags a session change, the event names the old session. **[corrected: read, no longer inferred]** Delivery is keyed by the session an event names, and nothing re-routes a `to`: `_owed` keeps an event only when `addressed_to(e, session)` (`S/sminos.py:6648-6661`), and `deliver_owed` passes over a member whose session is not in `to` (`S/sminos_daemon.py:966`). A session that was `retired` `continued` or `replaced` is no member, so such an event is owed to nobody: it is pushed to no process and wakes nothing. It stays in the log, and the thread's current session meets it at its next `sminos chat`, which reads by cursor and not by addressee (`cmd_chat`, 9378). A hand-off carries the chat cursor and the join override, not the delivery record (`carry_hand_off`, 5951-5958), so the successor's record starts empty and cannot tell an event that arrived after the change from one its predecessor was given.
- For a VM made before threads, the creator's session resolves through `m.former` (the `continued` chain) [read `former_ids`].
- The event goes into the creator's **project** log (the destination the tag reached), not the VM's.
- Sender's output: the remote branch of `deliver_say` [read 9075-9082] prints `<alias>: ` + one of:
  - `recorded (on <mac>): the session is stopped, and its machine wakes it with this` (`woken_line` 6882-6885);
  - a held line, `recorded and held on <mac>: the session is stopped and is not woken: <why>; ...` (`held_line` 6945-6960);
  - `recorded (on <mac>)`.

  Exit 0 in every case. An ended thread or no member: exit 4 (finding 2).

**On the owning Mac** (T1/T2 as built) [read]:
- The daemon's `deliver_owed` loops local members with events addressed to them [`S/sminos_daemon.py:926-986`] and calls `deliver_next` [`S/sminos.py:6980`].
- The event is kind `human`, so on a cut-over Mac the words gate decides. `words_route` [7340-7356] gives `"ask"` when the event carries the endpoint's `verified` (another machine's operator line), else `"unverified"`. `deliver_next` stops that writer and leaves the event owed for the uplink (`gated`), unless the session is held, in which case the outcome is `held:<why>` (checked first, 7066-7072).
- The uplink's verdict → `deliver_verdict` [7598-7656] → `holder_push`. For a session no process holds, `holder_push` wakes the thread first: `wake_member` [7216-7219] (T2's steps 1-3, `S/sminos_wake.py`, `resume_session` `S/sminos.py:15016`). With verdict `words` the notice is pushed **as the person's words** (bridge / supervisor reply), with `peer` as a peer frame, and with `refuse` it settles `refused-words` [7604-7607, 7640-7642].
- Events with `wake: true` (the `--project` broadcast fallback) never wake; they settle `recorded` for a stopped member [7072, 7216].
- Ended: `settle_ended_owed` [`S/sminos_daemon.py:953`].
- What MAWS answers to `words?` for a VM's operator line is outside this tree.

**X3 to the sender**: the VM reads `wake_of`/`why_of` from what the Mac published (`remote_line`). It is reported, not acted on (finding 2).

## 6. Ownership as built

**devcloud**: storage as in finding 3. `ls` has a `CREATOR` column, the bare short or `-` (`ops.py:99,110,125,137`).
- `down`, `lease`, `ssh` check no caller identity. `devcloud-by` (the driver Mac) is written and never read [read via reader `ops.py:210-247`; grep `devcloud-by`]. The reaper and caps never read the creator; caps count every unconfirmed VM across creators (`caps.py:23-26`).
- **`owned-by`** [read via reader `D/driver/owned.py:26-61`]:
  - names must match `_TAG` or `_SHORT`;
  - a match is `n in (short, "@"+short) or n.endswith("#"+short)`, whole, never a prefix;
  - rows: `{name, account, provider, creator:"@short"}`, adopted `{…, account:"adopted", provider:None, adopted:True}`;
  - prints one JSON line, exit 0; 6 on a host or with no seed.

**sminos** [read]:
- `owned_by(shorts)` `S/sminos_threads.py:2020-2074` is the only place devcloud is run. CLI search order `SMINOS_DEVCLOUD` → beside the plugin → marketplace clone → PATH (1962-1986). `DEVCLOUD_MIN=(0,17,2)` (1921). Exit 6 is none; anything else is unknown.
- `owned_vms(thread)` 2176-2181: `owned_among(owned_by(shorts_of(owner_sessions(thread))))`. `owner_sessions` 2154-2173 is `sessions + [current]`, plus for a seat its `history` occupants and the `joined`s naming the seat. **The thread id is not among them**: for a human-opened thread it is a minted UUID that names no host [inf]. A match needs `"@"+one of those shorts` (`_x9_whole` 2118-2123).
- Retire refusal [read via reader]: `owner_guard` `S/sminos.py:16676-16704` dies exit 1 with `"%s is not %s: %s"`. `owned_words` `S/sminos_threads.py:2226-2246` gives `it {made|adopted|made or adopted} hosts that still exist: <name> (<provider>, account <acct>)|<name> (an adopted machine), …; {deleting|releasing|…} a host is its owner's call: once nothing on it is needed, \`devcloud vm down <name>\` deletes it, and then it can be retired`. The unknown answer adds `devcloud could not tell whether it made a host that still exists: …`. A refusal names `sminos retire <name> --owner-unknown` for a person at a terminal. Tests pin "made" (`sminos/tests/test_threads_owner.py`).
- Census [read via reader `S/sminos_daemon.py:1359-1360,1500-1585,1871-1891,1979-2012`]: `THREAD_END_AFTER = 3 d`, `THREAD_END_EVERY = 3600`. `census.json` holds `{at, threads:[{thread,current,stopped,shorts}], answer, vms, unknown}`. An answer is taken if no older than one spacing (3600 s) and for the same thread/current/stopped. `end_stopped` does not re-ask. [inf] A census taken before a handover can say `none` for the thread that has just received a VM for up to an hour, so a thread past three days stopped could be ended while owning one. `retire` asks fresh.
- **The test that passes for the wrong reason** [read via reader]: `sminos/tests/test_threads_owner.py:466` `class Unknown(Owner)`, `rows()` 467, row at **527-530**:
  ```python
  ("a host with no provider that is no adopted machine", standin(stdout=json.dumps({
      "answer": "owned", "vms": [{"name": "dc-a-0001", "account": "main", "provider": None,
                                  "creator": "@abcd1234"}], "unknown": [], "listed": []}) + "\n"),
   "a malformed answer"),
  ```
  The thread under test has a `uuid4()` session (`test_threads_ended.py:111-113`), so `@abcd1234` is not among its shorts. `_x9_whole` fails at `v.get("creator") in tags` before it reaches the provider/adopted clause. The unit test that does cover the five forms is `test_a_host_is_of_one_form_a_provider_s_or_an_adopted_machine_with_none` (`test_threads_owner.py:571-580`), whose `reply()` asks `["abcd1234"]`.

## 7. Where `devcloud vm owner <vm> <thread>` would go

- **Verb table** (`D/driver/cli.py` parser 46-101, dispatch 104-126) [read via reader]:

  | verb | handler |
  |---|---|
  | `up` | `up.run` |
  | `adopt` | `adopt.run` |
  | `ls [--json]` | `ops.ls` |
  | `owned-by names*` | `owned.run` |
  | `ssh name [--root] -- …` | `ops.ssh` |
  | `lease name duration` | `ops.lease` |
  | `down name [--force]` | `ops.down` |
  | `image build/ls` | `images.*` |
  | `reap [--install]` | `reaper.*` |
  | `provider register/test` | `conformance.*` |

  The usage docstring is at 3-18.
- **Shape to copy**: `ops.lease` (finding 3). `adopt.load(ctx, name)` first, for adopted machines (host first, then `adopt.save` of the record: `adopt.lease`, `D/driver/adopt.py:323-330`); else `ctx.find(name)`, the first name match across usable accounts (failed listings skipped), else `"no VM named {name} in any usable account"` [read via reader `context.py:224-228`]. Error wording precedent: `"<host>'s departure has started; its lease stays as it is"` and `"...; its label is untouched"` (`hostctl.py:196-209`).
- **Tests**: `FakeRemote` matches host commands by substring [read via reader `D/tests/unit/driver_fixtures.py:~132-175`]. The fake provider replaces whole label sets (`D/tests/fixtures/provider:169-177`).
- **Authorization**: none exists in any verb. The only gate is `Client._owned` (the server still carries `devcloud`) (`provider.py:220-226`).
- **"A thread of the machine it is run on"**: sminos has no CLI that prints a thread's session ids [not found: no `thread(s)` verb in the subcommand list].
  - `sminos list --json` rows (`member_json` `S/sminos.py:4083-4107`) carry `session`, `short`, `former`, `thread`, `opened`, `machine`, `local`, not `thread_sessions`/`sessions` (`public_seat` strips them, `S/sminos_threads.py:67-68`). X1's statement holds.
  - `sminos who --session <sid>` takes a session id and prints the `Sminos-Session:` line devcloud already parses (`S/sminos.py:18536-18548`). **[added]** `main` runs a `who` that names no target before the migration and without the registry's lock (`S/sminos.py:19131-19135`: the address mod calls it ahead of a session's first request); a form of `who` that reads members has to leave that path.
  - In-process: `Member.thread_sessions` (`S/sminos.py:4056,6208-6230`), `sminos_threads.get`/`thread_of` (356, 421), `owner_sessions`.

  [inf] `local` + `machine` in `list --json` can tell a thread of this machine, and `session`/`short` give its current session. That is enough to write a current short, not to list every former one.
- **How the host learns its owner**: only by rewriting `/etc/devcloud/boot.env` (finding 3). The next tick picks it up. A notice already being sent uses the descriptor loaded before it (`lease.py:289-296`). An `owner` verb sent to a host whose recipe predates it gets the host CLI's usage exit 2 [inf]. **[added]** A host's descriptor parser refuses any key it does not know (`unknown key … in the boot descriptor`, `descriptor.py:95-97`), and `DEVCLOUD_CREATOR_PROJECT` entered the parser on 2026-10-27 (`a2fd403f`): written to a host built before then, it would make every later read of the descriptor fail, the lease service's among them. The driver never asks a host's recipe before a command (`images.py:45` compares only images).

## 8. X8: the notice marker

- **Fields of a `say` event** [read `S/sminos.py:9271-9283`; via reader `_append` 3238/3283, `ENDPOINT_ADDS` `S/sminos_hublog.py:125`]:
  - `ts`, `writer`, `seq`, `kind` (`say`/`human`), `from` (`human` with no session), `to` (`"*"` or `[{session, alias}]`), `text`;
  - optional `wake`, `scope`, `from_project`, `copy`;
  - added later by the endpoint: `verified`, `created`, `mac`, `sig`, `attest`, `audience`, `policyRev`.
  - `human` events under the machine's own writer get a private receipt `{seq, hash}`; the hash is the canonical event, so it covers any added field (3360-3375).
- **Settable by a caller**: the text (its leading tags), `--in`, the selector flags `--project --machine --state --org --here`. No `--from` (that is `send`), no kind flag.
- **Field pass-through**: `_append` takes any key. `as_uploaded` strips only `verified`; `refusal` checks `writer/seq/ts/kind`; `record_copy` copies everything else [read via reader]. So sminos passes an unknown field through; what MAWS does with it is out of scope.
- **Human writer**: `<machine>/human`, written whenever `CLAUDE_CODE_SESSION_ID` is unset (`writer_id()` `S/sminos.py:2818`; `cmd_say` 9244-9247). The VM's notices run exactly so (`notices.py:24`). The only marker today is the text prefix `devcloud on <name>:`, "since sminos labels a host-shell message as `from human`" (`D/README.md:497-498`).
- **Readers that treat these as the owner's words** [read]:
  - `owner_event` `S/sminos.py:2884-2891` (`kind == "human"` and a writer of `hub/…` or `…/human`). Used by:
    - `sminos_control.py:183-260`: the delivery route (bridge prompt / supervisor reply versus peer frame). **[added]** The route is chosen from the endpoint's verdict before the writer is looked at (`owner = words if words is not None else … S.owner_event(event)`, `:252`), so making `owner_event` false for a marked event does not keep one pushed under a verdict of `words` off the bridge. And a process that takes deliveries only with a receipt gets every one through the inbox, its receipt's marker first (the `marker` branch, `:240-241`), a person's words included: there the frame's sender is all that tells whose words a delivery is;
    - `ReachGate.applies` `S/sminos.py:7505-7512`;
    - the manager's `OwnerWords` `sminos/skills/manager/scripts/manager_window.py:143-150`.
  - `words_held`/`words_route`/`WordsGate` (7333-7356), `own_operator_event`/`receipted` (3385-3413), `sender_labels` (~7960-7986: `(unverified)` and friends).
  - `CHAT_KINDS = ("say","human")` (674): chat, the unread count, `hublog.addressed_to`, the TUI.
- **Candidate carriers**:
  - **A field on the event** (e.g. `notice`), set by `cmd_say`: the field is stored and hashed. Each reader above that should skip it must test it; `owner_event` is the one choke point for delivery and the manager.
  - **A `say` flag that sets it**: new parser surface on every machine, and devcloud's `notices.py` passes it. On a VM whose sminos predates the flag, argparse exits 2 and the notice falls to the next step [inf]. **[corrected]** Only if the next step does not pass the flag too. A marker belongs on every step, and then every step exits 2: the second step's exit is not 4, so the third is never tried, and the notice ends at the journal and `wall` (`notices.py:35-44`). **[added]** The host's integration stand-in plays `say` only with exactly one argument (`D/tests/fixtures/sminos.py:85`); any other shape is recorded as not played and exits 2.
  - **A new kind** (e.g. `notice`): drops out of `CHAT_KINDS`, `owner_event`, receipts and the words gate at once. That changes delivery from "the person's words, gated" to whatever the new kind gets, and every older reader skips it entirely (D7).
  - **Text only** (today's prefix): no reader can rely on it, and a sender line starting the same way is not escaped. Escaping exists only for `[sminos] ` (`sender_text`).
  - Any of these is forgeable by a person at that VM's terminal [inf]. The words gate, not the marker, decides authenticity.

## 9. Tests and gates

- **devcloud** [read via reader]:
  - `D/tests/run.sh` with `DEVCLOUD_PART=unit|image|host|systemd`. Unit is `unittest discover -s devcloud/tests/unit`; the rest build the image and run `integration.py` (Docker).
  - Driver tests: `DriverBase` (`driver_fixtures.py`) runs the real `provider.Client` against `fixtures/provider` (JSON state), with `FakeRemote` for ssh, `FakeSecrets`, `FakeTailnetApi`, a `Clock`, and `Context(creator=lambda: ("@abcd1234","abcd1234"), machine="testmac")`.
  - Shipped providers are tested against fake CLIs `fixtures/gcloud` and `fixtures/hcloud`.
  - Boot library tests (`test_lease.py`, `test_idle.py`, `test_notice_locking.py`, `test_sminos_host.py`, `test_descriptor*.py`) inject `call`, `say`, `now` and paths.
  - The integration sminos stand-in `fixtures/sminos.py` records `say` and exits 2 for any other verb.
- **sminos**: `sminos/tests/devcloud_standin.py` answers only `vm owned-by` (else exit 2, `"devcloud stand-in: only vm owned-by <short>..."`). It is configured by `$HOME/devcloud-standin.json` and logs to `devcloud-standin.calls`; `SMINOS_DEVCLOUD` points at it (`devcloud_isolation.py:21`, `devcloud-isolation.sh:6-7`). A new devcloud verb that sminos calls needs it extended.
- **Gates** (`.github/ci-kit.yml`):
  - devcloud: `devcloud-unit` (15 min timeout), `devcloud-image`/`-host`/`-systemd` (30 each), `devcloud-mods` (15), with paths `devcloud/**`; about 8.5 min serial per the file's comment.
  - sminos: `sminos` (core, 20), `sminos-suites` (30), `sminos-idle` (10, about 3 min), `sminos-mods` (15), with paths `sminos/**`; about 26 min serial on 2026-11-02 (core ~7, suites 18-20).
  - Every change: `version-bump` (5), `shell-lint` (it lints the extensionless `D/boot/devcloud` and provider scripts by shebang [inf]), `repo-checks`, `mods-types`.
  - [not found] A `sminos-channels` gate, which the CH1 plan names.
- **Recipe hash**: a change under `D/boot/**` or `D/image/**` changes `compose.recipe_hash`, so existing images stop matching and the next `up` takes the slow path until `image build` runs (`compose.py:188-203`). Driver-only changes do not.

## 10. Taught surface and versions

Sentences G1 makes false or incomplete [read via reader; quoted]:
- **`D/skills/vm/SKILL.md`**:
  - `:11` "on the tailnet and the desk" (true only with `--project maws`, finding 1);
  - `:45` "Within the caps a session creates a VM on its own" (`--on new` is a second way);
  - `:62-71` "Putting work on it", `devcloud vm ssh <name> -- sminos spawn <alias> "<task>" --cwd ~/Developer/GitHub/<repo>` and "give it your `@short` (from `sminos who`) when it should tell you" (`--on` replaces this);
  - `:75-82` "it sends the session that created it a sminos message ..." and "its creator gets a sminos message" (after `vm owner`: the owning thread, its current session, woken);
  - no line on `vm owner`; `devcloud/CLAUDE.md` keeps program-only verbs out of the skill, and `owner` is session-facing.
- **`sminos/skills/sminos/SKILL.md`**:
  - `:53-55` "not while a devcloud host of its own remains" ("of its own" now means owned, not made);
  - `:195` "the other verbs act on this machine's processes, so run them on its machine" (spawn with `--on` doesn't);
  - `:197-208` spawn usage without `--on`, and "in your project, or `--cwd`'s".
- **`sminos/skills/sminos/references/spawn-preamble.md`**:
  - `:1-3` "spawned by {{BY}}" (becomes "the operator" over ssh, finding 4);
  - `:16-18` "... for a last paragraph whose line opens "[sminos] ", which is your machine's note" (a marked notice is a second kind).
- Retire words "made" in `S/sminos.py:25-28,135-136,16612,16667-16690` and `S/sminos_threads.py:2226-2246` ("made"/"adopted", "and then it can be retired", which should now also offer `vm owner`). Tests pin them. `S/CLAUDE.md:51` says "devcloud names as a host's creator".
- `D/boot/devcloudlib/notices.py:10` "Try the creator, …"; `lease.py` `warn_creator`; `services.py:64` "warn its creator"; `descriptor.py:62` "the sminos tag the lease warning goes to".
- `D/README.md`:
  - `:497-498` the prefix as the automated-origin marker;
  - `:503-507` "Delivery tries the creating session, then its sminos project's live sessions ...";
  - `:596-603` the verb synopsis (no `owner`);
  - `:609-624` the `owned-by` paragraph's "creators".
- Root `README.md:77`, "`sminos spawn` starts a background session (a seat)" (local only). Its "Messages cross machines; these controls don't" stays true.
- Session-start guide (`guide_text` `S/sminos.py:18036-18090`): no spawn or VM line, so nothing false.

**Versions** [read `.version-bump.json`]: `devcloud` (root `devcloud`, files `devcloud/.claude-plugin/plugin.json` `version` + `.claude-plugin/marketplace.json` `plugins[name=devcloud].version`) and `sminos` (the same shape). Each has `unshipped` = `CLAUDE.md`, `*/CLAUDE.md`, `README.md`, `*/README.md`, `tests/*`, `types/*`. The `version-bump` gate runs `scripts/bump-version.sh --since <base> <head>`: each plugin with a shipped change must have every declared field above the base's. So G1 bumps both (`--plugin devcloud`, `--plugin sminos`).

---

## Where the design and the code disagree

1. **D4 "sminos waits for the machine's enrollment"** assumes `up` makes an enrolled machine. It does only with `--project maws` under a v2 profile, and may still return with step 13 deferred (finding 1).
2. **Delegated unknown (`--on new`), leaning "as `devcloud vm up` reads them from the directory it runs in"**: `up` reads nothing from its directory except `devenv/host.toml`. Label defaults to `vm`, projects are explicit, and the branch is only `@ref` on `--project` (§4).
3. **D4 notices, "when that thread cannot be woken, devcloud's order holds as today"**: today's order advances on a non-zero `say` exit. A thread on the Mac that is held, for any `why`, gives exit 0 and the notice stops there (finding 2). Only an ended thread or no member falls through.
4. **D4 "A VM that `--on new` makes is kept, which is devcloud's default"**: the default is the profile's `[caps] lease_default` when set (`up.py:89`). Kept is guaranteed only by passing `--keep`.
5. **D4 "devcloud records the creator ... as a tag naming the creating session"** and **X9 "A host holds its creator's short id and nothing else"**:
   - the host's descriptor also holds the creator's **project** (`DEVCLOUD_CREATOR_PROJECT`), which picks the notice's fallback audience;
   - adoption records hold no project;
   - a VM made by a process with no session id has no creator at all, and `up` says nothing.

   A handover that rewrites only the label leaves notices going to the old session and the old project.
6. **D4 "`devcloud vm owner` accepts only a thread of the machine it is run on"**: nothing in devcloud authorizes by caller (no verb checks the creator, `devcloud-by` is never read), and no sminos CLI resolves a thread to its sessions.
7. **D4 "written as it is today, by the VM's own `say` under the VM's human writer"**: true, kind `human`. That same fact makes every `owner_event` reader, delivery itself included, treat a notice as the owner's words today; it is pushed through the words gate as a person's words. With an audience split the writer is `<vm>/human~<digest>`; `owner_event` reduces it with `writer_base` (= `stream_of(writer)[0]`, `S/sminos.py:2852-2854`) before its test, so a stream still counts as the owner's [read].
8. **D4 "The first version reaches a VM over ssh ... as `devcloud vm ssh <name> -- sminos spawn` does by hand today"**: by hand, the spawned thread is "spawned by the operator" with the VM's default reach, not the spawner's (finding 4). The practised run (2026-10-21) predates MAWS v2 enrollment.

## Open choices for the plan

1. **Enrollment for `--on new`**:
   - (a) always add `--project maws` and refuse when the profile lacks `[desk]` v2; this clones MAWS and installs `mawsd` on every such VM;
   - (b) a devcloud change provisioning the endpoint without the MAWS project (boot steps 12-13, `compose.provisions`, recipe hash);
   - (c) refuse `--on new` unless the person's defaults already make an enrolled VM.
2. **Which projects and branch `--on new` passes**: the spawner's repository as `owner/repo@<branch>`. Refuse unpushed work? Fall back to the default branch? Or require `--project`-like flags on `spawn`? This touches `sminos spawn`'s parser and the derivation from `repo_branch`/remote.
3. **Waiting for enrollment**:
   - parse `up`'s `ready in` and `maws deferred` lines;
   - then poll the Mac's `sminos machines` for the name (lags with `org.json` age; `D/driver/context.py:324-358` already parses it);
   - or ask the VM directly over ssh (`identity.json`, `sminos hub show`);
   - and choose a bound: the deferral retry is 300 s.
4. **How the remote spawn runs**:
   - (a) `devcloud vm ssh <vm> -- sminos spawn <alias> - --cwd <abs VM path> --stamp …` with the task on stdin; exit codes are ambiguous between driver and remote;
   - (b) sminos's own ssh using devcloud's key/known_hosts (couples sminos to `D/driver/ssh.py` internals);
   - (c) a new `devcloud vm` verb that runs a command and reports the remote exit separately.

   Correlate by `--stamp` as the desk RPC does.
5. **Carrying the spawner**: a new `spawn` flag or env read on the VM for `by`/the reply line (`@<project>/<alias>`, `@short`), and whether provenance (owners/reach) is carried or stays the VM's default. That touches `caller_alias`, `render_preamble`, `spawn_provenance` and the RL10 reach the hub checks.
6. **What `vm owner` writes**:
   - the new thread's **current session short**: works with `owned_vms` and X2 as they are;
   - or its **thread id**: needs `owner_sessions` to include it. X2 already resolves a thread id's short through `former_ids`.

   And where it writes:
   - label + descriptor creator + descriptor project via a new host verb (template `lease set`, which an older host lacks);
   - or a raw `sed` over ssh like `host_expires`;
   - plus the adoption record (and adding its missing project).
7. **Validating "a thread of this machine"**: a new read-only sminos output (e.g. a `--json` form of `who` for a tag/thread, or `thread_sessions` exported); or `list --json`'s `local`/`machine`/`session` (current session only); or importing `sminos_threads` in-process.
8. **Notice fallback detection**:
   - a distinct `say` exit for "recorded and held" (changes every sender and the skill);
   - devcloud parsing `say`'s line (fragile);
   - a flag on `say` asking for exit-on-held;
   - a machine-readable `say` output.

   Each must keep working when the VM's sminos is older than the Mac's (the VM's copy tracks main; the Mac's may lag).
9. **The marker's carrier** (§8): a field set by a `say` flag, a kind, or the text. This decides how much of `owner_event`/`CHAT_KINDS`/the words gate changes in G1 versus CH.
10. **The refusals**:
    - `--on` from a VM: test `/etc/devcloud/boot.env` in sminos (what devcloud itself tests), or run devcloud and read exit 6 (ambiguous with no seed key).
    - `--on <a Mac>`: decide "a Mac" as "not a VM devcloud lists" (`ls --json`/`find`/adoption records; an adopted Linux server counts as a VM?), or by a property sminos does not publish today.
11. **Census race after a handover**: a fresh owned-by before `end_stopped` for a thread whose census is older than the handover, or accept the one-hour window.
12. **`--on new` from a terminal** (no session id): `up` makes an ownerless VM. Refuse, or name an owner.
13. **Test doubles**: extend `devcloud_standin.py` for any new devcloud verb sminos calls; `FakeRemote` rules for the host verb; and decide whether any end-to-end check on a real VM is in the plan's acceptance (cost: a few minutes and the VM's hourly price; nothing in CI does it).
