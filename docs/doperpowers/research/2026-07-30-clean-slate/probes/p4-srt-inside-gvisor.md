# Probe P4 — srt-inside-gVisor (desk research, 2026-07-30)

**Status:** desk probe only. This host is macOS with no Linux kernel, no
gVisor/runsc, and no Kubernetes cluster available — **no command in this
document has been executed**. Everything below is drawn from live web
sources (cited inline) plus grep of this repo's own specs. The verdict is
preliminary and gated on the in-cluster probe in §2 the day a cluster
exists, per the round brief's live-probe-first rule
(`docs/doperpowers/research/2026-07-30-clean-slate/round-brief.md`).

**Question:** does a Linux userland sandbox in the style of Anthropic's
`sandbox-runtime` (srt — bubblewrap / user-namespace based bash
sandboxing) work *inside* a gVisor (`runsc`) pod, giving a second sandbox
layer inside the pod boundary?

---

## (a) Preliminary verdict

**Likely yes, in the default (non-Autopilot-restricted) case, with one
concrete failure mode already documented by Anthropic and an open
question about GKE's specific capability allowlist. Confidence: medium.**

### The mechanism srt needs, and what gVisor's docs say about each piece

srt's Linux backend is bubblewrap (`bwrap`) plus a `socat` network relay,
described by Anthropic as "the unprivileged sandboxing tool" — the whole
point of bubblewrap is that it does **not** require host-granted
capabilities. It gets its power from `unshare(CLONE_NEWUSER)` (and
typically `CLONE_NEWNS`/`CLONE_NEWPID`/`CLONE_NEWUTS`/`CLONE_NEWIPC` too),
which — since Linux 3.8 — any unprivileged process may call; the kernel
grants the caller a namespace-local root with capabilities that are valid
only inside that new namespace, not on the host
([Claude Code sandboxing docs](https://code.claude.com/docs/en/sandboxing);
[unshare(2) man page](https://man7.org/linux/man-pages/man2/unshare.2.html)).
It then does a fresh mount of `/proc`, bind-mounts the allowed paths, and
`pivot_root`s into that view before exec'ing the target command.

Every syscall this sequence touches is one gVisor's Sentry claims to
implement:

| syscall | gVisor amd64 compatibility status (per gvisor.dev, AI-summarized fetch — re-verify against the raw page, not this table) |
|---|---|
| `unshare` | Partial — only time and cgroup namespaces unsupported; user/mount/pid/net/uts/ipc are the ones bubblewrap uses |
| `clone` | Partial — only `CLONE_NEWTIME`/`CLONE_SYSVSEM` flagged unsupported |
| `setns` | Full |
| `mount` | Full |
| `pivot_root` | Full |
| `chroot` | Full |
| `seccomp` | Full |

(Source: [gVisor Linux/amd64 compatibility page](https://gvisor.dev/docs/user_guide/compatibility/linux/amd64/), fetched via WebFetch's summarizer — treat the table as directional, not verbatim; the in-cluster probe in §2 re-derives it from the actual sandbox, which is the only trustworthy source per this round's Class-C discipline.)

This is architecturally consistent with two independent pieces of
evidence, not just the compatibility table:

1. **gVisor's own rootless mode is built on the identical trick.**
   `runsc --rootless` re-execs itself into a *new user namespace* where
   the invoking (unprivileged) caller is mapped to root inside it — the
   exact same `unshare(CLONE_NEWUSER)` + UID-remap pattern bubblewrap
   uses ([gVisor Rootless docs](https://gvisor.dev/docs/user_guide/rootless/)).
   A mechanism gVisor relies on for its own privilege model is unlikely to
   be one its Sentry fails to emulate for a guest process.
2. **Docker-in-gVisor is an officially documented, working configuration**
   that nests exactly the same primitives (new user/mount/pid/net
   namespaces, a fresh `/proc`, `pivot_root`) one layer deeper than srt
   needs. The official tutorial requires either `--privileged` or a
   specific capability set added at the pod/container level (`sys_admin`,
   `sys_chroot`, `net_raw`, etc.), and is explicit that "gVisor *never*
   runs with capabilities on the host Linux kernel" — the capability
   check Docker's requested capabilities satisfy is entirely emulated
   inside the Sentry, not passed through to the real kernel
   ([Docker in gVisor tutorial](https://gvisor.dev/docs/tutorials/docker-in-gvisor/);
   [Docker in a GKE sandbox tutorial](https://gvisor.dev/docs/tutorials/docker-in-gke-sandbox/)).

Bubblewrap's route is narrower than Docker's: it does not ask the pod
spec for `SYS_ADMIN` at all — it earns namespace-local capabilities from
an unprivileged `unshare(CLONE_NEWUSER)` call, which is a self-service
Linux 3.8+ mechanism the Kubernetes/Autopilot admission controller has no
visibility into (it only gates `securityContext.capabilities.add` and
`privileged: true`, both of which GKE Sandbox and GKE Autopilot disallow
outright — [GKE Sandbox pod docs](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/sandbox-pods);
[GKE Autopilot security docs](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-security)
list the allowed capability set as `AUDIT_WRITE, CHOWN, DAC_OVERRIDE,
FOWNER, FSETID, KILL, MKNOD, NET_BIND_SERVICE, NET_RAW, SETFCAP, SETGID,
SETPCAP, SETUID, SYS_CHROOT, SYS_PTRACE` and explicitly blocks
`privileged: true`, `hostPath`, and adding `NET_RAW`/`SYS_ADMIN`). Because
srt doesn't need `SYS_ADMIN` granted from outside, the Autopilot
capability wall that would block Docker-in-gVisor's simple path is not
obviously a blocker for srt — this is the main reason the verdict leans
yes rather than a coin flip.

### The one concrete failure mode already on record

Anthropic's own sandboxing docs document exactly this class of problem —
not gVisor-specific, but the general "userland namespace sandbox nested
inside another container-shaped boundary" case — and ship a named escape
hatch for it:

> "**Bubblewrap fails to start inside a container**: in an unprivileged
> container, bubblewrap cannot mount a fresh `/proc` filesystem. Set
> `enableWeakerNestedSandbox` to `true` so the inner sandbox bind-mounts
> the container's existing `/proc` instead of a fresh mount. Only use this
> setting when the outer container already provides the isolation
> boundary you need, since it exposes process information to sandboxed
> commands that a fresh `/proc` mount would hide."
> — [Claude Code sandboxing docs, Troubleshooting](https://code.claude.com/docs/en/sandboxing)

And, separately, under Limitations:

> "the Linux implementation provides strong filesystem and network
> isolation but includes an `enableWeakerNestedSandbox` mode that enables
> it to work inside Docker environments without privileged namespaces, or
> on Linux hosts where unprivileged user namespaces are disabled by
> sysctl. This option considerably weakens security."

This is documented for Docker/runc-style unprivileged containers, not
verified for gVisor specifically — the underlying cause (fresh `/proc`
mount inside a new PID namespace failing when the outer boundary won't
let the inner process act as init of that namespace, or when the outer
seccomp/capability policy blocks `mount()`) is a generic "second layer of
namespace nesting" problem, and gVisor's per-syscall emulation model is
different enough from runc's host-seccomp-profile model that the same
failure is not guaranteed to reproduce — but it is the single most
concrete, citable data point that this exact shape of nesting has failed
before in a semantically similar context, which is why this stays
"medium" rather than "high" confidence, and why srt already ships the
`enableWeakerNestedSandbox` fallback as a first-class setting rather than
a stopgap.

### What this is *not*

This is a different question from gVisor-in-gVisor. GitHub issue
[google/gvisor#11091](https://github.com/google/gvisor/issues/11091)
("Nested gVisor does not work with `--directfs=false` and Yama mode 2")
fails with `panic: unable to initialize systrap source: unable to attach:
operation not permitted` — a `ptrace`-attach failure specific to gVisor's
own systrap platform trying to trace a process from *inside* another
namespace-isolated boundary, blocked by the Yama `ptrace_scope`
LSM restriction. Bubblewrap does not use `ptrace` at all — it sets up
namespaces and mounts, then directly `exec`s the target, so Yama's
ptrace-scope restriction is architecturally irrelevant to srt. Do not let
this issue's existence be read as evidence against P4; it is evidence
about a different mechanism (gVisor nesting itself via ptrace) hitting a
different wall (Yama).

---

## (b) In-cluster probe plan (run the day a cluster exists)

Goal: reproduce srt's own startup sequence (`bwrap` + a trivial sandboxed
command) inside a real GKE Sandbox (or self-hosted gVisor) pod, and
capture the exact syscall that fails if it fails.

### Prerequisites
- A GKE cluster with GKE Sandbox enabled (Standard: a node pool created
  with `--sandbox type=gvisor`; Autopilot: gVisor is on by default for
  all pods — confirm which cluster shape R2 lands on before running, since
  Autopilot's admission controller is stricter).
- A test pod manifest requesting the gVisor `RuntimeClass` (`gvisor` on
  Standard).

### Step 1 — bare capability check (no srt yet)

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: p4-userns-probe
spec:
  runtimeClassName: gvisor
  containers:
  - name: probe
    image: debian:12-slim
    command: ["sleep", "3600"]
    securityContext:
      runAsNonRoot: true
      runAsUser: 1000
      allowPrivilegeEscalation: false
```

```bash
kubectl apply -f p4-userns-probe.yaml
kubectl exec -it p4-userns-probe -- bash -c '
  apt-get update -qq && apt-get install -y -qq bubblewrap procps >/dev/null
  cat /proc/sys/user/max_user_namespaces 2>&1
  unshare --user --pid --mount-proc echo "unshare OK" 2>&1
  bwrap --unshare-all --ro-bind / / --tmpfs /tmp --proc /proc -- echo "bwrap OK" 2>&1
'
```

**Pass signal:** all three commands print their `OK` line with no
`Operation not permitted` / `EPERM` / `Permission denied`.
**Fail signal + what it tells you:**
- `unshare` itself fails (`clone` syscall EPERM) → the gVisor Sentry (or
  the pod's declared capability set) is blocking `CLONE_NEWUSER` outright;
  check `runsc` version/flags and whether `user.max_user_namespaces` is
  reachable inside the guest at all.
- `unshare` succeeds but the `--mount-proc` remount inside it fails →
  this is the exact `enableWeakerNestedSandbox` failure mode predicted in
  §(a); the fix is the bind-mount-existing-`/proc` fallback, not a dead
  end.
- `bwrap` fails with a `/proc` or mount-related error where the bare
  `unshare` succeeded → isolates the failure to bubblewrap's specific
  mount sequence (it does more remounting than a bare `unshare` test),
  still consistent with the same fallback.

### Step 2 — the real srt startup path

```bash
kubectl exec -it p4-userns-probe -- bash -c '
  npm install -g @anthropic-ai/sandbox-runtime 2>&1 | tail -5
  # Run a minimal sandboxed command through srt exactly as Claude Code would invoke it
  npx @anthropic-ai/sandbox-runtime exec -- echo "srt OK" 2>&1
'
```

**Pass signal:** `srt OK` printed, no bubblewrap panic in stderr.
**Fail signal:** capture the exact bubblewrap error text and cross-check
it against the "Bubblewrap fails to start inside a container" entry in
the [Claude Code sandboxing docs](https://code.claude.com/docs/en/sandboxing#troubleshooting) —
if it matches, retry Step 2 with `enableWeakerNestedSandbox: true` in the
srt config and confirm it now passes with the weaker guarantee.

### Step 3 — confirm the weaker mode's actual guarantee, if Step 2 needed it

```bash
kubectl exec -it p4-userns-probe -- bash -c '
  # with enableWeakerNestedSandbox on, confirm what the inner sandbox can now see
  npx @anthropic-ai/sandbox-runtime exec -- ps aux
'
```

**Signal to record:** does the inner sandboxed process see the *pod's*
full process list (expected/acceptable — it is still isolated from the
node and other pods by the gVisor boundary itself) or does it see
anything from outside the pod (would indicate the gVisor boundary itself
is leaking, a much bigger finding for R2 well beyond this probe).

### Step 4 (Autopilot variant, if R2 lands there)

Repeat Steps 1–3 on an Autopilot cluster instead of Standard+gVisor
node pool. Autopilot enforces a narrower capability allowlist via
admission control (see §(a)); confirm the probe's pass/fail signal is
unchanged, since bubblewrap's mechanism should not touch
`securityContext.capabilities` at all — if Autopilot's admission
controller rejects the pod spec for an unrelated reason (e.g. it
requires `runAsNonRoot` differently, or blocks the base image), record
that as a separate, non-srt-specific finding.

### What "resolved" looks like

Record, verbatim, for whichever cluster shape R2 picks:
1. The exact pass/fail outcome of Steps 1–2.
2. If failed, whether `enableWeakerNestedSandbox` recovers it (Step 2
   retry) and what Step 3 shows about the resulting isolation strength.
3. The `runsc` version and platform (`systrap` vs `kvm`) in use, since
   the compatibility table in §(a) is version-dependent and was not
   re-verified live.

---

## (c) Fallback design if the answer is no

This traces directly to the A0 spec's DL11
(`docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md:495-515`):
at 07-23, the execution-sidecar design (agent-loop container holding the
Anthropic key, separate execution-sidecar container running all
generated code with disjoint egress) was recorded as **inexpressible at
A0** because the substrate adapter (E2B) only offered a single
`sandboxId` create/exec/destroy contract with no multi-container or
shared-volume vocabulary — so srt-inside-the-one-sandbox was recorded as
the *interim in-sandbox approximation*, explicitly flagged as "an inner
defense layer only (same kernel as the adversary; its own docs flag
nested-container weakening and domain fronting) — the load-bearing
boundary stays the [substrate] VM egress allowlist."

**The 07-30 pivot changes the premise DL11 was reacting to.** Both tiers
are now k8s+gVisor, and Kubernetes pods are natively multi-container with
shared volumes — the constraint that made the sidecar "inexpressible" (a
single-sandboxId adapter) no longer exists at either tier. This means P4
is not gating whether defense-in-depth is *possible* at A0 scale anymore;
it is only gating which of two available shapes to prefer:

- **If srt-inside-gVisor works (this probe's likely-yes):** srt remains
  available as a *cheap second layer inside one container*, useful for
  workers where the two-container sidecar's per-run pod overhead isn't
  worth paying (e.g. short-lived implement-lane runs), while the
  sidecar pattern is still available for anything needing a hard
  separate-egress boundary. Two-layer defense, pick per run-class.

- **If srt-inside-gVisor does NOT work (or only works in the weaker,
  bind-mounted-`/proc` mode with materially reduced isolation):** the
  fallback is to make the **two-container execution-sidecar the default
  shape at both tiers**, not the exception — since the pivot already
  removed the substrate reason DL11 treated it as A0-inexpressible, this
  is a strictly available fallback, not a redesign. The gVisor pod
  boundary becomes the sole load-bearing isolation layer between the
  agent-loop container and the execution-sidecar container (both still
  inside the same gVisor sandbox, so this is container-to-container
  isolation within one Sentry instance, not host-kernel isolation — a
  materially weaker guarantee than two separate gVisor sandboxes, which
  R2 should weigh against the per-run cost of two full sandboxes per
  work unit). What is lost if srt-inside-gVisor fails outright: the
  option of a *cheap* inner layer for run-classes where a second full
  sandbox isn't justified; the *sole* remaining defense-in-depth lever
  for those run-classes reverts to the two-container-in-one-pod
  boundary, or — for the cheapest run-classes — no second layer at all,
  same as DL11's 07-23 status quo (load-bearing boundary = the sandbox's
  own egress allowlist, single layer).

Either way, DL11's own framing survives unchanged: srt (where available)
is *never* the load-bearing security boundary — that role stays with the
gVisor pod's own egress allowlist and virtual-key brokering (R2's
question, Class A's credential-substitutability principle). This probe
only decides whether srt is available as a *bonus* inner layer or not;
its absence is a defense-in-depth degradation, not a design blocker.
