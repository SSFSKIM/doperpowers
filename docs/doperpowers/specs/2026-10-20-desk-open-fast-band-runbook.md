# desk-open-fast: the band runbook (2026-10-21)

How the 100–300 band for the [desk-open-fast spec](2026-10-20-desk-open-fast-design.md)'s
acceptance was run on an isolated Linux host, for board #108's re-run. The
scripts are kept here because their working copies under `/tmp/dsk-scripts/`
on the MacBook do not last. Their figures and what they showed are in the
spec's Surprises & Discoveries (board #108).

The host is one GCE Spot c2d-standard-16 in us-east4-c, in a VPC of its own.
It has one firewall rule, which admits SSH from the operator's IP only, an
SSH key made for the run, and no service account. It deletes itself after
8 h (`--max-run-duration`), but the teardown is run anyway and its listing
read. It is never enrolled at a hub: every bench runs `--hub local`, the
hub's own Worker on a local runtime. The API key reaches the host only
through ssh's stdin, into a 0600 file.

## The order

On the MacBook, with gcloud's default account and project:

1. `mk-tars.sh`: the `git archive` tarballs of doperpowers origin/main and
   MAWS origin/master, plus a `CODE` line naming both shas.
2. `01-create.sh <this Mac's public IP>`, then `02-wait-ssh.sh`.
3. Copy the tarballs, `CODE`, `host-setup.sh` and `host/` to
   `/home/bench/`. Then run `03-secrets.sh` and `host/auth-test.sh`, which
   checks the key with `GET /v1/models` and spends nothing.
4. On the host:
   - `sudo bash host-setup.sh`;
   - `bash host/prep.sh` (autogroup off, MAWS's install, bench_index's
     transcript);
   - `bash host/mk-gateway-env.sh`;
   - `bash host/mk-hb-copy.sh`, which is only needed for A4's sized pair.
5. Run each load point detached, as
   `setsid nohup bash /home/bench/host/band.sh <label> <workers> [runs…] &`.
   The order used:
   - `base0` with no load: smoke, the A4 calibration, and the unloaded
     A1, A2, A6 and A3;
   - `p150` at 150, the first run's list plus `bufcap-1048576
     a4hb-held-6000ms-9s-6m bufrestore`;
   - `p150n`, the control, with `STRESS_NICE=19`;
   - `diag-a4.sh`;
   - `p280` at 280, the list plus `bufcap-1048576 a4hb-auto-6m bufrestore`;
   - `p280n`.

   `wait-band.sh <label>` returns when a point ends, so nothing polls.
6. Copy `results/` back and run `99-teardown.sh`. Its listing of every
   `dof-band` name must print nothing under any heading.

To run it again, rename the instance (`N`) in `01-create.sh` and
`99-teardown.sh`, and the tarball names in `host-setup.sh`.

## The load method

- stress-ng is started by the same script as the benches, so both share
  one cgroup.
- `kernel.sched_autogroup_enabled=0`. With autogroup on, the local hub,
  which starts in a session of its own, would get a CPU share apart from
  the workers.
- Each load point ramps until load1 ≥ 0.9 N.
- Before each run, `band.sh` records `uptime` and a probe. The probe times
  a 0.200 CPU-s busy loop in wall seconds, which gives one thread's CPU
  share.
- A `STRESS_NICE=19` point is the control: load1 does not change, but the
  benches get their CPU back.

## A4's sized pair

The pair as written (`--pause-stream 4 --backlog 16m`) cannot block a hub
write on a loaded host, for two reasons:

- The default loopback buffers absorbed a 12 MiB backlog whole; of the
  sizes tried, only 16 MiB blocked.
- At load the 16 MiB upload outlasts any pause below the local hub's 6 s
  silence bound.

`bufcap-1048576` caps the loopback's TCP buffers at 1 MiB, so a 6 MiB
backlog blocks. `bufrestore` restores the defaults. `a4hb-*` runs the pair
from `doperpowers-hb`, a copy of the tree whose `bench_rig.py` passes
`BENCH_HUB_HEARTBEAT_MS` on as the local command's `--heartbeat-ms`. The
longer heartbeat lets the pause outlast the upload.

`a4hb-auto-<B>` sizes the pause and heartbeat from that point's 16 MiB
upload: the estimated upload of the backlog plus 3 s, under the hub's 10 s
write bound. A 256 KiB cap stalls the stream about 2.9 s after the resume,
so it is not used.

## The scripts (MacBook)

### mk-tars.sh

```zsh
#!/bin/zsh
# The code the band host runs, as git archives: doperpowers origin/main (the band-rerun worktree's base) and MAWS origin/master.
set -euo pipefail
D=/tmp/dsk-scripts/band2
mkdir -p $D/tar
cd /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/band-rerun
DP=$(git rev-parse origin/main)
git archive --format=tar.gz --prefix=doperpowers/ -o $D/tar/doperpowers-${DP[1,8]}.tar.gz $DP
cd /Users/new/Developer/GitHub/MAWS
MW=$(git rev-parse origin/master)
git archive --format=tar.gz --prefix=MAWS/ -o $D/tar/maws-${MW[1,9]}.tar.gz $MW
print -r -- "doperpowers $DP"
print -r -- "MAWS $MW"
print -r -- "doperpowers $DP (origin/main), MAWS $MW (origin/master)" > $D/tar/CODE
ls -la $D/tar
```

### 01-create.sh

```zsh
#!/bin/zsh
# Creates the second band host (board #108): an isolated VPC, a firewall admitting SSH from this Mac's IP only,
# and one Spot c2d-standard-16 (Ubuntu 24.04, x86_64) with a key made for this run, as the first band's 01-create.sh.
# The instance deletes itself after 8 h whatever happens (max-run-duration, termination DELETE).
set -euo pipefail
N=dof-band-20261021
Z=us-east4-c
R=us-east4
D=/tmp/dsk-scripts/band2
MYIP="$1"
[[ -f $D/key/id_dof ]] || ssh-keygen -q -t ed25519 -N '' -f $D/key/id_dof -C $N
print -r -- "bench:$(cat $D/key/id_dof.pub)" > $D/key/ssh-keys.meta

gcloud compute networks create $N --subnet-mode=custom \
  --description="desk open-fast band re-run (board 108, smns-erb), temporary"
gcloud compute networks subnets create $N --network=$N --region=$R --range=10.208.0.0/24
gcloud compute firewall-rules create $N-ssh --network=$N --direction=INGRESS --action=ALLOW \
  --rules=tcp:22 --source-ranges="$MYIP/32" --target-tags=$N
gcloud compute instances create $N --zone=$Z --machine-type=c2d-standard-16 \
  --provisioning-model=SPOT --instance-termination-action=DELETE --max-run-duration=8h \
  --subnet=$N --tags=$N \
  --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
  --boot-disk-size=60GB --boot-disk-type=pd-balanced \
  --metadata=block-project-ssh-keys=TRUE,enable-oslogin=FALSE \
  --metadata-from-file=ssh-keys=$D/key/ssh-keys.meta \
  --no-service-account --no-scopes --labels=purpose=dof-band,owner=smns-erb

IP="$(gcloud compute instances describe $N --zone=$Z --format='value(networkInterfaces[0].accessConfigs[0].natIP)')"
cat > $D/key/ssh_config <<CFG
Host dof
  HostName $IP
  User bench
  IdentityFile $D/key/id_dof
  IdentitiesOnly yes
  UserKnownHostsFile $D/key/known_hosts
  StrictHostKeyChecking accept-new
  ServerAliveInterval 30
  ServerAliveCountMax 10
  ConnectTimeout 15
CFG
print -r -- "created $N at $IP; created at $(date -u +%FT%TZ)" | tee -a $D/key/created.txt
```

### 02-wait-ssh.sh

```zsh
#!/bin/zsh
# Waits up to 5 minutes for SSH on the band host.
for i in {1..60}; do
  if ssh -F /tmp/dsk-scripts/band2/key/ssh_config -o BatchMode=yes dof 'echo up; uname -m; nproc; lsb_release -ds' 2>/dev/null; then
    exit 0
  fi
  sleep 5
done
echo "no ssh after 5 minutes" >&2
exit 1
```

### 03-secrets.sh

```zsh
#!/bin/zsh
# Puts ANTHROPIC_API_KEY on the band host as /home/bench/.bench/secrets.env (0600), through ssh's stdin:
# the value is on no command line and never printed.
set -euo pipefail
v="$(cat ~/.config/claude-secrets/ANTHROPIC_API_KEY)"
print -r -- "export ANTHROPIC_API_KEY=${(q)v}" | ssh -F /tmp/dsk-scripts/band2/key/ssh_config dof \
  'umask 077; mkdir -p /home/bench/.bench; chmod 700 /home/bench/.bench; cat > /home/bench/.bench/secrets.env; chmod 600 /home/bench/.bench/secrets.env; stat -c "%a %U %s bytes %n" /home/bench/.bench/secrets.env'
```

### wait-band.sh

```zsh
#!/bin/zsh
# Returns when the named load point's band.sh has ended on the host (one notification, no polling here),
# then prints its host notes and each run's summary lines.
L="$1"
ssh -F /tmp/dsk-scripts/band2/key/ssh_config dof "while pgrep -f '^bash /home/bench/host/band.sh $L ' >/dev/null; do sleep 15; done; cat /home/bench/results/$L/host.txt; for f in /home/bench/results/$L/*.log; do echo \"=== \$f\"; grep -E '^# (uptime before|exit|probe)|\"summary\"|\"complete\"|^(cold|save|loaded|warm) |\"moment\"|^built|\"hub_write_blocked\"|\"role\"' \"\$f\" | cut -c1-1200; done"
```

### 99-teardown.sh

```zsh
#!/bin/zsh
# Deletes everything 01-create.sh made (instance and its boot disk, firewall rule, subnet, network),
# each only if it exists, then lists what of it remains through the API (every dof-band name, the first run's too).
N=dof-band-20261021
Z=us-east4-c
R=us-east4
if gcloud compute instances describe $N --zone=$Z --format='value(name)' >/dev/null 2>&1; then
  gcloud compute instances delete $N --zone=$Z --delete-disks=all --quiet
fi
if gcloud compute firewall-rules describe $N-ssh --format='value(name)' >/dev/null 2>&1; then
  gcloud compute firewall-rules delete $N-ssh --quiet
fi
if gcloud compute networks subnets describe $N --region=$R --format='value(name)' >/dev/null 2>&1; then
  gcloud compute networks subnets delete $N --region=$R --quiet
fi
if gcloud compute networks describe $N --format='value(name)' >/dev/null 2>&1; then
  gcloud compute networks delete $N --quiet
fi
print -r -- "--- what remains (each list should be empty) at $(date -u +%FT%TZ)"
print -r -- "instances:";  gcloud compute instances list --filter="name~^dof-band" --format='value(name,zone,status)'
print -r -- "disks:";      gcloud compute disks list --filter="name~^dof-band" --format='value(name,zone)'
print -r -- "firewalls:";  gcloud compute firewall-rules list --filter="name~^dof-band" --format='value(name)'
print -r -- "subnets:";    gcloud compute networks subnets list --filter="name~^dof-band" --format='value(name,region)'
print -r -- "networks:";   gcloud compute networks list --filter="name~^dof-band" --format='value(name)'
print -r -- "addresses:";  gcloud compute addresses list --filter="name~^dof-band" --format='value(name)'
```

## The scripts (host)

### host-setup.sh (as root)

```bash
#!/bin/bash
# Run as root on the band host: unpack the code, run the devcloud image setup, add pnpm, stress-ng and py-spy.
set -euo pipefail
W=/home/bench/w
install -d -o bench -g bench $W
runuser -u bench -- tar -xzf /home/bench/doperpowers-aec6f74c.tar.gz -C $W
runuser -u bench -- tar -xzf /home/bench/maws-909a1e5bd.tar.gz -C $W
install -o bench -g bench -m 644 /home/bench/CODE $W/CODE
DEVCLOUD_USER=bench DEVCLOUD_UID="$(id -u bench)" DEVCLOUD_HOME=/home/bench \
  $W/doperpowers/devcloud/image/setup.sh
# The host stays isolated: no devcloud boot at a reboot.
systemctl disable devcloud-boot.service || true
apt-get update
apt-get install -y --no-install-recommends stress-ng python3-pip
pip3 install --break-system-packages --quiet py-spy
npm install -g pnpm@11.23.0
echo "setup done: python $(python3 --version) node $(node --version) pnpm $(pnpm --version) claude $(runuser -u bench -- /usr/local/bin/claude --version) stress-ng $(stress-ng --version | head -1) py-spy $(py-spy --version)"
```

### host/prep.sh

```bash
#!/bin/bash
# On the band host, as bench: the scheduler made flat (no autogroup: a setsid'd child would otherwise get its own
# share beside stress-ng), MAWS's install for the local hub, and bench_index's synthetic transcript.
set -euo pipefail
sudo sysctl -w kernel.sched_autogroup_enabled=0
echo "cgroup controllers: $(cat /sys/fs/cgroup/cgroup.subtree_control)"
cd /home/bench/w/MAWS
ELECTRON_SKIP_BINARY_DOWNLOAD=1 CI=1 pnpm install --frozen-lockfile 2>&1 | tail -15
ls /home/bench/w/MAWS/node_modules/.bin/wrangler
mkdir -p /home/bench/synth
python3 -I /home/bench/host/gen-transcript.py /home/bench/synth/0f0f0f0f-1111-4222-8333-444455556666.jsonl
echo "prep done"
```

### host/gen-transcript.py

```python
"""The bench_index input: bench_scale's synthetic large transcript, made by the same call bench_scale makes
(bench_rig.synthetic_transcript, 15,000 rows, seed 7), at the path given."""
import os
import sys
import uuid

sys.path.insert(0, "/home/bench/w/doperpowers/sminos/tests")
import bench_rig  # noqa: E402

path = sys.argv[1]
sid = os.path.basename(path).removesuffix(".jsonl")
uuid.UUID(sid)
bench_rig.synthetic_transcript(path, 15000, "/home/bench/synth-cwd", sid)
print("%s: %d bytes, %d lines" % (path, os.path.getsize(path), sum(1 for _ in open(path))))
```

### host/auth-test.sh

```bash
#!/bin/bash
# On the band host: which auth header the key in secrets.env is accepted with (GET /v1/models,
# which spends nothing), and the model ids it lists. Prints no part of the key.
set -u
. /home/bench/.bench/secrets.env
for mode in x-api-key bearer; do
  if [ "$mode" = x-api-key ]; then hdr="x-api-key: $ANTHROPIC_API_KEY"; else hdr="Authorization: Bearer $ANTHROPIC_API_KEY"; fi
  code=$(printf '%s\n' "$hdr" | curl -s -o "/home/bench/.bench/models.$mode.json" -w '%{http_code}' -H @- \
    -H 'anthropic-version: 2023-06-01' 'https://api.anthropic.com/v1/models?limit=100')
  echo "$mode: HTTP $code"
  python3 -I - "/home/bench/.bench/models.$mode.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print("  unreadable answer:", type(e).__name__); sys.exit()
if "data" in d:
    print("  models:", " ".join(m["id"] for m in d["data"]))
else:
    print("  error:", (d.get("error") or {}).get("type"), "-", (d.get("error") or {}).get("message", "")[:160])
PY
done
```

### host/mk-gateway-env.sh

```bash
#!/bin/bash
# On the band host: the keys bench_open --live reads (live-bridge-check's GATEWAY_KEYS), pointed straight at the
# Anthropic API with the key from secrets.env (accepted as a bearer token: auth-test.sh), into a 0600 file the
# run scripts source. Prints no part of the key.
set -euo pipefail
. /home/bench/.bench/secrets.env
umask 077
{
  echo "ANTHROPIC_BASE_URL=https://api.anthropic.com"
  printf 'ANTHROPIC_AUTH_TOKEN=%q\n' "$ANTHROPIC_API_KEY"
  echo "ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-haiku-5-5"
  echo "ANTHROPIC_DEFAULT_SONNET_MODEL=claude-sonnet-5-5"
  echo "ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-5-5"
  echo "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=0"
} > /home/bench/.bench/gateway.env
chmod 600 /home/bench/.bench/gateway.env
stat -c "%a %U %s bytes %n" /home/bench/.bench/gateway.env
```

### host/mk-hb-copy.sh

```bash
#!/bin/bash
# A copy of main's tree whose bench_rig.py passes BENCH_HUB_HEARTBEAT_MS on to the local hub as --heartbeat-ms
# (the local command's own flag; default 2000, deployed 15000). Nothing else differs: the diff is kept.
set -euo pipefail
W=/home/bench/w
rm -rf $W/doperpowers-hb
cp -a $W/doperpowers $W/doperpowers-hb
python3 -I - $W/doperpowers-hb/sminos/tests/bench_rig.py <<'PY'
import sys
p = sys.argv[1]
src = open(p).read()
old = 'os.path.join(rig.root, "hubstate"), "--port", str(port)]'
new = ('os.path.join(rig.root, "hubstate"), "--port", str(port)]'
       ' + (["--heartbeat-ms", os.environ["BENCH_HUB_HEARTBEAT_MS"]] if os.environ.get("BENCH_HUB_HEARTBEAT_MS") else [])')
assert src.count(old) == 1, "the line to patch is not there once"
open(p, "w").write(src.replace(old, new))
print("patched", p)
PY
mkdir -p /home/bench/results
diff -r $W/doperpowers $W/doperpowers-hb > /home/bench/results/hb-patch.diff || true
cat /home/bench/results/hb-patch.diff
```

### host/band.sh

```bash
#!/bin/bash
# On the band host: one load point. band.sh <label> <cpu-workers> [run-name ...]
# stress-ng holds the load; every run is preceded by uptime and a per-thread CPU-share probe and recorded whole
# under results/<label>/. With no run names, every run in the report's order. cpu-workers 0 = no load.
# STRESS_NICE=<n> starts stress-ng under `nice -n <n>` (the control: load1 unchanged, the benches' share restored).
# A run named a4-held-<P>s-<B> is A4's pair with --pause-stream <P> --backlog <B> (a4-held alone: 4 s, 16m).
set -u
L=$1; CPU=$2; shift 2
NICE=${STRESS_NICE:-0}
OUT=/home/bench/results/$L
mkdir -p "$OUT"
D=/home/bench/w/doperpowers
M=/home/bench/w/MAWS
S=$D/sminos/skills/sminos/scripts
T=/home/bench/synth/0f0f0f0f-1111-4222-8333-444455556666.jsonl
CODE=$(cat /home/bench/w/CODE)
set -a; . /home/bench/.bench/gateway.env; set +a
cd "$D"

{
  echo "label $L; stress-ng --cpu $CPU --cpu-method matrixprod; stress-ng nice $NICE"
  echo "code $CODE"
  echo "nproc $(nproc)"
  echo "kernel $(uname -r); autogroup $(cat /proc/sys/kernel/sched_autogroup_enabled)"
  echo "cgroup of this script: $(cat /proc/self/cgroup)"
  echo "cpu: $(lscpu | sed -n 's/^Model name: *//p')"
} > "$OUT/host.txt"

( while true; do echo "$(date -u +%s) $(cut -d' ' -f1-3 /proc/loadavg)"; sleep 5; done ) > "$OUT/loadavg.txt" &
LS=$!
SP=
cleanup() { [ -n "$SP" ] && kill "$SP" 2>/dev/null; wait "$SP" 2>/dev/null; kill "$LS" 2>/dev/null; }
trap cleanup EXIT

if [ "$CPU" -gt 0 ]; then
  nice -n "$NICE" stress-ng --cpu "$CPU" --cpu-method matrixprod --timeout 0 --quiet &
  SP=$!
  sleep 1
  echo "stress-ng pid $SP, cgroup $(cat /proc/$SP/cgroup), nice $(ps -o ni= -p $SP | tr -d ' ')" >> "$OUT/host.txt"
  # Ramp: load1 is a one-minute moving average; wait until it is within 10% of the workers (at most 5 min).
  target=$(( CPU * 9 / 10 ))
  for i in $(seq 60); do
    sleep 5
    awk -v t="$target" '{exit !($1 >= t)}' /proc/loadavg && break
  done
  echo "ramped after $(( i * 5 )) s: $(uptime)" >> "$OUT/host.txt"
fi

probe() {
  python3 -I -c '
import time
c, w = time.thread_time(), time.perf_counter()
n = 0
while time.thread_time() - c < 0.2:
    n += 1
cpu, wall = time.thread_time() - c, time.perf_counter() - w
print("probe: %.3f CPU-s took %.3f s wall (one thread gets %.3f of a CPU)" % (cpu, wall, cpu / wall))'
}
# What a bridge child's start costs here: the import of the modules `sminos bridge` runs, CPU and wall.
import_probe() {
  /usr/bin/time -f "import probe (sminos, sminos_bridge): %e s wall, %U user + %S sys CPU-s" \
    python3 -I -c "import sys; sys.path.insert(0, '$S'); import sminos, sminos_bridge" 2>&1 | tail -1
}
probe >> "$OUT/host.txt"
for i in 1 2 3; do import_probe >> "$OUT/host.txt"; done

inband() { awk '{exit !($1 >= 100 && $1 <= 300)}' /proc/loadavg; }

run() {
  local name=$1; shift
  local f="$OUT/$name.log"
  if [ "$CPU" -gt 0 ]; then
    for i in $(seq 36); do inband && break; sleep 5; done
  fi
  {
    echo "# run: $name   (load point $L: stress-ng --cpu $CPU, nice $NICE)"
    echo "# code: $CODE"
    echo "# nproc: $(nproc)"
    echo "# uptime before: $(uptime)"
    echo "# $(probe)"
    echo "# cmd: $*"
    echo "# start: $(date -u +%FT%TZ) ($(date -u +%s))"
  } > "$f"
  "$@" >> "$f" 2>&1
  local rc=$?
  {
    echo "# exit: $rc"
    echo "# end: $(date -u +%FT%TZ) ($(date -u +%s))"
    echo "# uptime after: $(uptime)"
  } >> "$f"
}

BO="python3 sminos/tests/bench_open.py --uplink --hub local --maws $M"
[ $# -eq 0 ] && set -- a1-idle a2-mid-message a2-long-answer a2-after-prompt a4-held a6-kill a3-scale a3-index smoke-idle
for name in "$@"; do
  case "$name" in
    a1-idle)         run "$name" $BO --live --scenario idle --opens 10 ;;
    a2-mid-message)  run "$name" $BO --live --thinking --scenario mid-message --opens 5 ;;
    a2-long-answer)  run "$name" $BO --live --thinking --scenario long-answer --opens 3 ;;
    a2-after-prompt) run "$name" $BO --live --scenario after-prompt --opens 5 ;;
    a4-held)         run "$name" $BO --scenario held --pause-stream 4 --backlog 16m ;;
    a4-held-*s-*)
      spec=${name#a4-held-}; P=${spec%%s-*}; B=${spec#*s-}
      run "$name" $BO --scenario held --pause-stream "$P" --backlog "$B" ;;
    a6-kill)         run "$name" $BO --live --scenario kill --opens 3 ;;
    a3-scale)        run "$name" python3 sminos/tests/bench_scale.py opens sminos/skills/sminos/scripts --live 40 --large 6 ;;
    a3-index)        run "$name" python3 sminos/tests/bench_index.py "$T" ;;
    smoke-idle)      run "$name" $BO --live --scenario idle --opens 2 ;;
    # A4's pair with a longer pause under a longer local-hub heartbeat (its silence bound and lease are three of
    # them): a4hb-held-<HB>ms-<P>s-<B>, run from doperpowers-hb, main's tree with only bench_rig.py patched to pass
    # BENCH_HUB_HEARTBEAT_MS on as the local command's --heartbeat-ms (mk-hb-copy.sh).
    a4hb-held-*ms-*s-*)
      rest=${name#a4hb-held-}; HB=${rest%%ms-*}; r2=${rest#*ms-}; P=${r2%%s-*}; B=${r2#*s-}
      run "$name" env BENCH_HUB_HEARTBEAT_MS="$HB" python3 /home/bench/w/doperpowers-hb/sminos/tests/bench_open.py \
        --uplink --hub local --maws "$M" --scenario held --pause-stream "$P" --backlog "$B" ;;
    # The same, sized from this load point's a4-held (16m) upload: a4hb-auto-<B>, B in MiB ("6m"): the pause P is
    # the estimated upload of B plus 3 s, the heartbeat max(6 s, (P + 4) / 3) so the silence bound stays above P.
    a4hb-auto-*)
      B=${name#a4hb-auto-}
      t16=$(python3 -I -c '
import json, sys
for l in open(sys.argv[1]):
    if l.startswith("{") and "steps" in l:
        for s in json.loads(l)["steps"]:
            if s.get("step") == "upload answered 200":
                print(s["seconds"]); raise SystemExit
print("")' "$OUT/a4-held.log")
      read P HB < <(python3 -I -c 'import math, sys; t, b = float(sys.argv[1]), float(sys.argv[2].rstrip("m")); p = math.ceil(t * b / 16 + 3); print(p, max(6000, math.ceil((p + 4) / 3) * 1000))' "${t16:-30}" "$B")
      echo "$name: a4-held's 16m upload took ${t16:-unknown} s here, so pause $P s, heartbeat $HB ms" >> "$OUT/host.txt"
      run "a4hb-held-${HB}ms-${P}s-$B" env BENCH_HUB_HEARTBEAT_MS="$HB" python3 /home/bench/w/doperpowers-hb/sminos/tests/bench_open.py \
        --uplink --hub local --maws "$M" --scenario held --pause-stream "$P" --backlog "$B" ;;
    # The loopback's TCP buffers capped (bufcap-<max bytes>, bufcap alone 262144), restored by bufrestore.
    bufcap*)
      cap=${name#bufcap}; cap=${cap#-}; cap=${cap:-262144}
      sudo sysctl -q -w net.ipv4.tcp_rmem="4096 131072 $cap" net.ipv4.tcp_wmem="4096 16384 $cap"
      echo "bufcap at $(date -u +%FT%TZ): tcp_rmem $(sysctl -n net.ipv4.tcp_rmem | tr '\t' ' '); tcp_wmem $(sysctl -n net.ipv4.tcp_wmem | tr '\t' ' ')" >> "$OUT/host.txt" ;;
    bufrestore)
      sudo sysctl -q -w net.ipv4.tcp_rmem="4096 131072 33554432" net.ipv4.tcp_wmem="4096 16384 4194304"
      echo "bufrestore at $(date -u +%FT%TZ): tcp_rmem $(sysctl -n net.ipv4.tcp_rmem | tr '\t' ' '); tcp_wmem $(sysctl -n net.ipv4.tcp_wmem | tr '\t' ' ')" >> "$OUT/host.txt" ;;
    *)               echo "unknown run $name" >> "$OUT/host.txt" ;;
  esac
done
echo "band $L done $(date -u +%FT%TZ)" >> "$OUT/host.txt"
```

### host/diag-a4.sh

```bash
#!/bin/bash
# Diagnostic (not a band figure): where the uplink's main thread spends the wait of A4's open made 1 s after the
# resume, at load 150. The sized pair (loopback buffers capped at 1 MiB, heartbeat 6 s, pause 9 s, backlog 6m)
# run with --keep while py-spy dumps the uplink's threads (non-blocking) about every 0.2 s, each dump stamped;
# the kept daemon.log then times the open line, and the dumps before it say what the main thread was doing.
set -u
OUT=/home/bench/results/diag-a4
mkdir -p "$OUT"
M=/home/bench/w/MAWS
cd /home/bench/w/doperpowers-hb
( while true; do echo "$(date -u +%s) $(cut -d' ' -f1-3 /proc/loadavg)"; sleep 5; done ) > "$OUT/loadavg.txt" &
LS=$!
stress-ng --cpu 150 --cpu-method matrixprod --timeout 0 --quiet &
SP=$!
restore() {
  sudo sysctl -q -w net.ipv4.tcp_rmem="4096 131072 33554432" net.ipv4.tcp_wmem="4096 16384 4194304"
  kill $SP $LS 2>/dev/null; wait $SP 2>/dev/null
}
trap restore EXIT
for i in $(seq 60); do sleep 5; awk '{exit !($1 >= 135)}' /proc/loadavg && break; done
{
  echo "ramped: $(uptime)"
  python3 -I -c '
import time
c, w = time.thread_time(), time.perf_counter()
while time.thread_time() - c < 0.2:
    pass
cpu, wall = time.thread_time() - c, time.perf_counter() - w
print("probe: %.3f CPU-s took %.3f s wall (one thread gets %.3f of a CPU)" % (cpu, wall, cpu / wall))'
} > "$OUT/host.txt"
sudo sysctl -q -w net.ipv4.tcp_rmem="4096 131072 1048576" net.ipv4.tcp_wmem="4096 16384 1048576"
echo "bufcap: tcp_rmem $(sysctl -n net.ipv4.tcp_rmem | tr '\t' ' '); tcp_wmem $(sysctl -n net.ipv4.tcp_wmem | tr '\t' ' ')" >> "$OUT/host.txt"
echo "start $(date -u +%FT%TZ) ($(date -u +%s))" >> "$OUT/host.txt"
BENCH_HUB_HEARTBEAT_MS=6000 python3 sminos/tests/bench_open.py --uplink --hub local --maws "$M" \
  --scenario held --pause-stream 9 --backlog 6m --keep > "$OUT/held.log" 2>&1 &
BP=$!
UP=
for i in $(seq 240); do UP=$(pgrep -n -f "bench_rig.py _uplink"); [ -n "$UP" ] && break; sleep 0.5; done
echo "uplink pid $UP" >> "$OUT/host.txt"
while kill -0 "$BP" 2>/dev/null; do
  { echo "=== dump at $(date -u +%s.%N)"; sudo py-spy dump --pid "$UP" --nonblocking 2>&1 | head -80; } >> "$OUT/dumps.txt"
  sleep 0.2
done
wait "$BP"
echo "bench exit $? at $(date -u +%FT%TZ)" >> "$OUT/host.txt"
ROOT=$(sed -n 's/^kept: //p' "$OUT/held.log" | tail -1)
echo "root $ROOT" >> "$OUT/host.txt"
if [ -n "$ROOT" ] && [ -d "$ROOT" ]; then
  find "$ROOT" -name daemon.log -exec cp {} "$OUT/daemon.log" \;
  rm -rf "$ROOT"
fi
echo "diag-a4 done $(date -u +%FT%TZ)" >> "$OUT/host.txt"
```
