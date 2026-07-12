# Worker host provisioning — body / soul / seeding

Runnable counterpart of `docs/doperpowers/2026-07-12-managed-agents-steals.md`
§2 (state-volume convention). One persistent Linux VM runs the whole board
pipeline: implement / review / land workers (detached processes under the
daemon registry), the Actions runner that turns board events into dispatches,
and the feedback-triage poller (a separate unix user — see §5), and nothing
else. No Docker: workers are host processes keyed by
(host, pid, session) in the registry, codex brings its own Landlock sandbox
on a real kernel, and single-tenant reproducibility comes from cloud-init,
not images.

Everything splits by lifetime:

| layer | what | lives |
|---|---|---|
| 1 — body | OS, packages, CLIs, runner binary | disposable; `cloud-init.yaml` recreates it |
| 2 — soul | registry, sessions, auth files, clones, worktrees | `/data` volume = the worker user's `$HOME` |
| 3 — seeding | tokens, codex auth.json, runner registration, clones | by hand, ONCE per soul (never per body) |

## 1. Create the body

Hetzner (CX43, Ubuntu 24.04, one Volume) — adjust names to taste:

```bash
hcloud volume create --name doper-data --size 40 --location fsn1
hcloud server create --name doper-worker-1 --type cx43 --image ubuntu-24.04 \
  --location fsn1 --volume doper-data --user-data-from-file cloud-init.yaml \
  --ssh-key <your-key>
```

First boot formats the volume ONLY if blank, mounts it at `/data`, creates
`worker` (uid 1010, home `/data/worker`, no sudo) and `triage` (uid 1011,
home `/data/triage`, no sudo — see §5 for why they are separate), installs
git/jq/python3/build-essential, Node LTS, `gh`, `codex` (global npm),
`claude` (native installer, as worker), Tailscale, an 8G swapfile, and the
`doper-triage` systemd timer (armed but inert until §5's seeding). It also
sets the hostname to `doper-worker-<machine-id prefix>` — unique per body,
which is what makes the registry's host-aware pid liveness hold across
rebuilds (the Hetzner server *name* can stay `doper-worker-1`; only the OS
hostname matters to the registry).

After boot:

```bash
cloud-init status --long              # must be done/no errors — the runcmd hard
                                      # gate aborts here if /data didn't mount
tailscale up                          # then close public SSH:
ufw allow in on tailscale0; ufw allow ssh; ufw enable   # drop 'allow ssh' once tailscale login works
```

## 2. Seed the soul (once)

As `worker` (`sudo -iu worker`):

1. **Env file** — copy `env.example` → `~/.env`, fill it (see the file for
   the two-token scope split), `chmod 600 ~/.env`.
2. **codex auth** — `worker` is deliberately not SSH-reachable (locked
   password, no authorized keys), so copy through your login account (root
   on Hetzner) and install with ownership and mode set from birth:
   ```bash
   ssh root@host 'install -d -m 700 -o worker -g worker /data/worker/.codex'
   ssh root@host 'install -m 600 -o worker -g worker /dev/stdin /data/worker/.codex/auth.json' \
     < ~/.codex/auth.json
   ```
   (auth.json is portable by design; device-code flow is the fallback if
   the workspace enables it.)
3. **claude auth** — nothing to do beyond `CLAUDE_CODE_OAUTH_TOKEN` in
   `~/.env` (generated locally with `claude setup-token`).
4. **Canonical clones, push scope wired into the remote** (steal 3) — one
   per consumer repo, using a contents-only fine-grained PAT that appears
   NOWHERE else:
   ```bash
   git clone https://oauth2:<PUSH_TOKEN>@github.com/OWNER/REPO.git ~/repos/REPO
   ```
   Worktrees share the parent's remote config, so worker `git push` works
   without the token ever entering worker env. Be honest about what that
   buys: any process running as `worker` — including PR-derived code — can
   still read the token (`git remote get-url origin`), so workers ARE
   contents-write principals on the consumer repos. The containment is the
   token's shape, not its hiding place: contents-only scope, consumer repos
   only, and **branch protection on main/integration branches (require
   PRs)** so the token cannot rewrite protected refs. Enable that protection
   before the first worker runs. Verify the env-token split:
   `gh api repos/OWNER/REPO --jq .permissions` under `GH_TOKEN` must show
   push=false.
   Seed the commit identity in the same sitting — a fresh volume has none,
   and the implementation protocol's first commit dies with "Author identity
   unknown" (git refuses to auto-detect from the machine-id hostname):
   ```bash
   git config --global user.name  "doper-worker"
   git config --global user.email "<your-bot-or-noreply address>"
   ```
   Lives in `~/.gitconfig` on the volume — once per soul, like everything
   else in this layer.
5. **doperpowers itself** — `git clone` this repo to `~/doperpowers`
   (dispatch scripts are invoked by path from here; workers get skills via
   vendoring / plugin install exactly as on the Mac).
6. **Actions runner** (event trigger, PRIVATE repos only — standing
   constraint): download the runner into `~/runner`, then
   `./config.sh --url https://github.com/OWNER/REPO --token <REG_TOKEN> --labels claude-review`
   — the label must be `claude-review`: the shipped `pr-review-dispatch.yml`
   selects `runs-on: [self-hosted, claude-review]`, and a runner registered
   under any other label leaves those jobs queued forever. Runner jobs read
   env from `~/runner/.env` and PATH from `~/runner/.path`, NOT from
   `.bashrc` (non-login shells; Ubuntu's stock `.bashrc` early-returns for
   non-interactive). From a worker login shell where
   `command -v gh git node python3 claude` all resolve:
   ```bash
   grep -Ev '^\s*(#|$)' ~/.env > ~/runner/.env   # runner .env is bare KEY=VALUE
   echo "DOPERPOWERS_HOME=/data/worker/doperpowers" >> ~/runner/.env
   chmod 600 ~/runner/.env                       # holds the same tokens as ~/.env
   echo "$PATH" > ~/runner/.path
   ```
   Then as root `cd /data/worker/runner && ./svc.sh install worker &&
   ./svc.sh start`. Runner jobs must only run the dispatch ritual (render →
   spawn --no-wait → bind) and exit; workers are detached processes outside
   the job. What actually makes that true is not nohup/--bg but the spawn
   paths stripping `RUNNER_TRACKING_ID` (daemon-spawn / daemon-resume /
   `_codex_launch`) — the runner's post-job cleanup kills any surviving
   process whose environ still carries that job marker, detached or not.

## 3. Verification gate (before trusting it)

The rituals were shakedown-tested on macOS; this is the Linux pass. Run one
dogfood cell end-to-end on the VM and check, in order:

1. `codex exec` smoke turn — auth.json accepted, Landlock sandbox active
   (kernel ≥5.13; Ubuntu 24.04 is 6.8).
2. Nested-codex TLS — `SSL_CERT_FILE` resolves (`_codex_launch` and
   `review-engine.sh` probe `/etc/ssl/certs/ca-certificates.crt` since
   2026-07-12); a review-engine call from inside a worker completes.
3. Board write under env `GH_TOKEN` — a `board-transition.sh` against a test
   issue; push from a worktree uses the remote-wired credential.
4. Full cell: dispatch an implement worker on a toy ticket → PR → review
   worker → verdict. The claude-engine branch counts double here
   (TECH-DEBT #3: untested by the original shakedown).

## 4. Rebuild drill (why this layout exists)

Body loss is a non-event: create a new server with the same
`cloud-init.yaml`, attach the same volume, re-run layer-1's `tailscale up`,
and reinstall the runner service — its registration and config survive in
`/data/worker/runner`, but the systemd unit `svc.sh install` wrote lived on
the discarded root filesystem, so there is nothing to merely "restart":
`cd /data/worker/runner && sudo ./svc.sh install worker && sudo ./svc.sh start`.
Every parked session resumes — the registry's stale pids are neutralized by
host-aware liveness (metas carry `host`; the rebuilt body's machine-id
suffix gives it a NEW hostname, so every old meta reads foreign and its pid
as dead). Nothing else in layer 3 repeats, because nothing else in layer 3
lived on the body. The triage tenant needs no step at all: the
timer is re-armed by cloud-init and its `ExecCondition` finds the seeded
`.env` already on the volume.

## 5. Triage tenant (`skills/triaging-feedback` poller)

The first production tenant, and deliberately the burn-in one: real value
from day one (24/7 feedback triage instead of a sleep-prone Mac's launchd),
minimal blast radius (ticket-only — the poller diagnoses and files tickets;
it never writes code or pushes). It has **no soul on this host**: all durable
state lives in Supabase (`feedback.triage_state`/`triage_lease`) and GitHub
(tickets), so unlike the workers it doesn't even need the state volume — it
sits on it only because `$HOME` does.

**Why a separate unix user.** The dispatcher env holds
`SUPABASE_SERVICE_ROLE_KEY` (RLS bypass — the strongest secret here), while
`worker` runs implement/review workers that execute PR-derived code. User
separation (uid 1011, mode-600 `.env`) is the cheap wall between them.

Seed as `triage` (`sudo -iu triage`; step 4 is the exception — it runs from
the admin shell) — prerequisites first: the p86
migration must be live in Supabase and the descriptive labels created on
ida-solution (`references/setup.md` §0/§4):

1. **Clones** — `git clone` doperpowers to `~/doperpowers`; clone
   ida-solution to `~/repos/ida-solution` with a contents-READ-only
   fine-grained PAT in the remote URL (the poller fetches origin every tick,
   never pushes).
2. **Deps** — `cd ~/doperpowers/skills/triaging-feedback && npm ci`.
3. **Env** — copy `env.triage.example` → that same skill dir's `.env`,
   fill it, `chmod 600`. Keep `TRIAGE_K=1` until ticket quality is trusted
   (`references/setup.md` §5).
4. **Verify one tick** — from the ADMIN/root shell, not the triage shell
   (`triage` has no sudo, a locked password, and cannot read the system
   journal): `systemctl start doper-triage.service`, then
   `journalctl -u doper-triage.service -f`. The timer (installed by
   cloud-init, 10-minute cadence) takes over from there.
5. **Mac handoff** — once a VM tick has filed a correct ticket, unload the
   Mac's launchd label (`references/setup.md` §6). Atomic claim + lease
   makes the overlap window safe, but two pollers is a config smell, not a
   feature.

## 6. Not configured here, on purpose

- **Watchdog** — T1 tech-debt (import of Symphony's liveness sweep); when it
  exists it becomes a cron/timer on this host. Until then
  `review-dispatch.sh --sweep` on a timer is the available partial.
- **Feedback intake** (in-app 피드백 → Supabase `feedback` table) — that is
  the product's own write path; this host only polls the table. No
  serverless intake layer is needed for triage.
- **ufw auto-enable in cloud-init** — deliberate: enabling the firewall
  before Tailscale is joined can lock you out of a fresh body.
