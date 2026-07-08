# Self-hosted runner setup (PR review dispatch)

One-time setup of the machine that runs the daemon fleet (macOS assumed).
**Private repos only** — a `pull_request`-triggered workflow on a self-hosted
runner attached to a public repo can hand a stranger's fork PR a path onto
this machine. The workflow template's actor gate and no-checkout design are
defense in depth, not a substitute.

## 1. Install the runner

```bash
mkdir -p ~/actions-runner-<repo> && cd ~/actions-runner-<repo>
# latest version tag:
gh api repos/actions/runner/releases/latest -q .tag_name        # e.g. v2.321.0
curl -o runner.tar.gz -L \
  "https://github.com/actions/runner/releases/download/<TAG>/actions-runner-osx-arm64-<TAG-without-v>.tar.gz"
tar xzf runner.tar.gz
```

## 2. Register it (label: `claude-review`)

```bash
TOKEN="$(gh api -X POST repos/<OWNER>/<REPO>/actions/runners/registration-token -q .token)"
./config.sh --url "https://github.com/<OWNER>/<REPO>" --token "$TOKEN" \
  --labels claude-review --name "$(hostname -s)-claude" --unattended
```

## 3. Environment for the job

The runner builds the job PATH from a `.path` file and env from `.env` in
the runner directory. The dispatch script needs `gh`, `git`, `node`,
`python3`, and `claude` reachable:

```bash
echo "$PATH" > .path                       # snapshot a PATH that has them all
cat > .env <<'EOF'
DOPERPOWERS_HOME=/Users/<you>/.claude/plugins/marketplaces/doperpowers
EOF
```

## 4. Run as a service (launchd)

```bash
./svc.sh install && ./svc.sh start
./svc.sh status
```

Note: `svc.sh` installs a LaunchAgent — it runs while the user is logged in.
A PR opened while the machine is asleep queues on GitHub's side for up to
24h; beyond that the sweep cron below catches it.

## 5. Verify

```bash
gh api repos/<OWNER>/<REPO>/actions/runners \
  -q '.runners[] | "\(.name) \(.status) \(.labels|map(.name)|join(","))"'
# expect: <name> online ... claude-review
```

## 6. Sweep cron (self-heal)

```bash
# Find where the required CLIs live first:
command -v gh git python3 claude
crontab -e
# cron does NOT inherit your shell PATH (same reason step 3 wrote .path for
# the runner) — set it inline on the command, adjusted to the dirs found above:
*/30 * * * * PATH="/opt/homebrew/bin:/usr/local/bin:$PATH" LOCAL_REPO=/path/to/clone BOARD_REPO=<OWNER>/<REPO> $HOME/.claude/plugins/marketplaces/doperpowers/skills/reviewing-prs/scripts/review-dispatch.sh --sweep >> $HOME/Library/Logs/review-sweep.log 2>&1
```
