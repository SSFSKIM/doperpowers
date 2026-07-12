# Worker host provisioning — body / soul / seeding

Runnable counterpart of `docs/doperpowers/2026-07-12-managed-agents-steals.md`
§2 (state-volume convention). One persistent Linux VM runs the whole board
pipeline: implement / review / land workers (detached processes under the
daemon registry), the Actions runner that turns board events into dispatches,
and nothing else. No Docker: workers are host processes keyed by
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
`worker` (uid 1010, home `/data/worker`, no sudo), installs git/jq/python3/
build-essential, Node LTS, `gh`, `codex` (global npm), `claude` (native
installer, as worker), Tailscale, and an 8G swapfile.

After boot:

```bash
tailscale up                          # then close public SSH:
ufw allow in on tailscale0; ufw allow ssh; ufw enable   # drop 'allow ssh' once tailscale login works
```

## 2. Seed the soul (once)

As `worker` (`sudo -iu worker`):

1. **Env file** — copy `env.example` → `~/.env`, fill it (see the file for
   the two-token scope split), `chmod 600 ~/.env`.
2. **codex auth** — from your logged-in machine:
   `scp ~/.codex/auth.json worker@host:~/.codex/auth.json` (portable by
   design; device-code flow is the fallback if the workspace enables it).
3. **claude auth** — nothing to do beyond `CLAUDE_CODE_OAUTH_TOKEN` in
   `~/.env` (generated locally with `claude setup-token`).
4. **Canonical clones, push scope wired into the remote** (steal 3) — one
   per consumer repo, using a contents-only fine-grained PAT that appears
   NOWHERE else:
   ```bash
   git clone https://oauth2:<PUSH_TOKEN>@github.com/OWNER/REPO.git ~/repos/REPO
   ```
   Worktrees share the parent's remote config, so worker `git push` works
   without the token ever entering worker env. Verify the split:
   `gh api repos/OWNER/REPO --jq .permissions` under `GH_TOKEN` must show
   push=false.
5. **doperpowers itself** — `git clone` this repo to `~/doperpowers`
   (dispatch scripts are invoked by path from here; workers get skills via
   vendoring / plugin install exactly as on the Mac).
6. **Actions runner** (event trigger, PRIVATE repos only — standing
   constraint): download the runner into `~/runner`, then
   `./config.sh --url https://github.com/OWNER/REPO --token <REG_TOKEN> --labels doper-worker`
   and as root `./svc.sh install worker && ./svc.sh start`. Runner jobs must
   only run the dispatch ritual (render → spawn --no-wait → bind) and exit;
   workers are detached processes outside the job, so job timeouts never
   touch them.

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
restart the runner service. Every parked session resumes — the registry's
stale pids are neutralized by host-aware liveness (metas carry `host`; a
foreign-host pid reads as dead). Nothing in layer 3 repeats, because nothing
in layer 3 lived on the body.

## 5. Not configured here, on purpose

- **Watchdog** — T1 tech-debt (import of Symphony's liveness sweep); when it
  exists it becomes a cron/timer on this host. Until then
  `review-dispatch.sh --sweep` on a timer is the available partial.
- **Feedback intake** (customer feedback → issue) — serverless territory
  (Cloudflare Worker → GitHub API), not this VM.
- **ufw auto-enable in cloud-init** — deliberate: enabling the firewall
  before Tailscale is joined can lock you out of a fresh body.
