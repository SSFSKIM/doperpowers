# devcloud package layer split: report (board #119)

Branch `devcloud-package-split`, off main at 706821dd (devcloud 0.9.0). The ticket body (board #119) is the statement of work. devcloud is bumped to 0.9.1.

## What changed

- **`devcloud/image/packages.sh` in three parts.** `apt` holds the Ubuntu archive's packages and the locale. `gcloud` is the Google Cloud CLI from its repository. `tools` covers the GitHub CLI, Tailscale, the Docker CLI and Node LTS from their repositories, plus uv and hcloud from their releases. Each part runs its own `apt-get update`, and every invocation ends with apt's lists and caches removed. With no argument the script runs every part in order, so setup.sh on a VM builder and adopt still run one recipe with the same result. An unknown part exits 2 before anything runs.
- **`devcloud/image/Dockerfile`** has one `RUN` per part, each bind-mounting `packages.sh` alone, so every package layer's cache key is still that one file. A warm build pulls the three layers from the GitHub Actions cache side by side instead of as one 436 MB stream.
- **`devcloud/image/setup.sh`: the Claude Code install (outside the ticket's scope, found by the live proof).** It was `curl … | bash` without pipefail. During a burst of HTTP 429s from claude.ai the fetch piped nothing to bash, and setup.sh carried on. A GCE image baked that way had no `claude`, and an `up` from it failed at step apply. Now any failure, of the fetch or of the installer's own download, is retried after 15, 30, 60 and 120 s, then fails the run. setup.sh also checks at the end that `/usr/local/bin/claude` is executable. The coordinator asked for the retry. The window grew from 90 s (22de7103) to almost 4 min (5d0ccc3a) because a CI runner saw 429 on all four tries over 110 s.
- Docs: `devcloud/README.md`, `devcloud/CLAUDE.md` and the image files' comments describe the three layers.

## Measurement first (scratch ref `ci/measure-package-split`, since deleted, with its caches)

Runners: 4 vCPU, Docker 29.4.2, buildx 0.38.0, the docker driver with the containerd snapshotter. The gates' `run` was swapped for a script that ran each build with `--progress=plain` and timed it. Runs 39738132790 (cold, writing a private scope) and 39738953047 (warm read), 3 runners each:

| | what was measured | time |
|---|---|---|
| current recipe, warm from main's W43 scope | the 436.59 MB zstd package layer's download, one stream | 13.0–38.1 s (11–34 MB/s) |
| | then its extraction | 6.1–11.2 s |
| prototype split (4 package layers), every step CACHED | the whole build | 16.6 / 19.3 / 26.3 s |
| | 6 blobs (148, 142, 129, 123, 29.8, 23 MB) downloaded in parallel | 7.7–13.1 s (45–77 MB/s combined) |
| | unpacking every layer into the image store, one after another | 14.8–23.5 s |

The pull was bound by the single stream, not by bandwidth, so the split pays. Compressed sizes per family: apt 148 MB, gcloud 142 MB, the repositories' CLIs and Node 123 MB, uv + hcloud 23 MB. The last two went into one `tools` layer (about 146 MB), which gives three layers of similar size. What remains of the warm time is the sequential unpack at export, which more layers would not shorten.

## Warm proof before merge (same ci/ ref, run.sh's real flow)

ci-kit writes the cache only on main, and each `ci-gate` call gets a new ref, so a PR cannot read its own cache. Instead, the branch's commit cb208b8d was pushed to the scratch ref twice. The first push wrapped the gates with `CI_KIT_BUILD_CACHE_WRITE=1` (run 39739620268, cold with a cache write: 152–258 s). The second was unchanged (run 39740406055), so its gates read the first run's cache as main's will after the seed. In the second run, all four steps (`apt`, `gcloud`, `tools`, setup.sh) printed CACHED and every case passed:

| gate | warm image build before (run 39736552512) | warm, three package layers (run 39740406055) |
|---|---|---|
| devcloud-image | 48.7 s | **21.8 s** |
| devcloud-host | 29.6 s | **20.4 s** |
| devcloud-systemd | 32.0 s | **20.6 s** |

The ticket's target was ≤ ~30 s per gate, and every gate met it. The final warm proof on main follows CI-opt's seed after the merge (`gh workflow run ci.yml --ref main -f gates=devcloud-image`). setup.sh's retry changes its step's cache key but not the package layers'.

Cold builds on the PR's own gate runs (no cache) took 112–154 s (run 39740786292), against 126–139 s before.

## Live proof on GCE (default account, 2026-10-22 UTC)

| When | What | Result |
|---|---|---|
| 07:19–07:26 | `vm image build` (no `--account`: every account) on cb208b8d | both bakes failed at setup with `curl: (22) … 429`; each builder was deleted by the driver (one GCE, one Hetzner) |
| 07:28–07:40 | `vm image build --account gce` on cb208b8d | image `dc-img-4c911d624c98-…`; it baked **without claude** (the silent install) |
| 07:40–07:42 | `vm up --label pks --account gce --ttl 1h` | `dc-pks-8fb9`; steps identity through home ok, **apply failed**: `claude: not found`. Every package tool (gcloud, gh, node, tailscale, docker, uv, hcloud) was present |
| 07:43–07:44 | `vm down dc-pks-8fb9` | the first try dropped its connection before the departure's logout ("the outcome is unknown, and the VM is kept"); the second said it no longer answered over the tailnet; `--force` deleted it. The driver warned the desk may still list it in Machines |
| 07:44 | that image deleted by hand | |
| 07:45–07:53 | bake on fb73cbd6 (pipefail and the check) | succeeded, then deleted by hand, superseded by the retry commit |
| 07:54–08:01 | bake on 22de7103 | image `dc-img-f7dea6d6e8c3-202610220759` |
| 08:01–08:04 | `vm up --label pks --account gce --ttl 1h` | `dc-pks-0046`, ready in 3m05s; `devcloud status`: every step ok, projects skipped (none named); claude 2.1.308 and every package tool on PATH |
| 08:06 | `vm down dc-pks-0046`, the image deleted | "departed and deleted"; GCE lists no `dc-` instance or `dc-img` image; `vm ls` shows no throwaway |

The live image was baked from 22de7103. The final commit 5d0ccc3a changes only the retry delays (15/30/45 to 15/30/60/120 s), which the gates ran.

## Review

doperpowers:review-code, medium rung (reviewer-medium), two passes: cb208b8d, then the setup.sh follow-ups through 22de7103. Both found nothing material. The second pass tested the retry loop with a mocked shell: success on each try, exhaustion, the backoff and pipeline failure propagation. 5d0ccc3a changes only the delay list. Its loop was simulated locally: it passes on the first and the fifth try and fails after five.

## CI

- cb208b8d (run 39739620199): RED 2/8. devcloud-image failed on the installer's 429, and devcloud-host on the silent install (`claude: not found`). That is the bug fixed since. A re-run of the three image gates (39740786292) was GREEN.
- fb73cbd6 (run 39742676183): GREEN.
- 22de7103 (run 39742780145): RED 1/8. devcloud-systemd hit 429 on all four tries over 110 s, which led to the longer window.
- 5d0ccc3a (run 39745378623): GREEN 8/8.

## Friction

The claude.ai 429 bursts are logged in the repository's friction tracker (#304) as conditional.

## Residue

- **Builds depend on claude.ai being reachable.** Every image build without a warm cache installs Claude Code from claude.ai. A burst longer than about 4 minutes still fails the build, now loudly. A mirrored copy or a pinned version cached in CI would remove the dependency.
- **`vm down` on a host whose boot failed at apply.** The first `down` dropped its connection mid-departure and left the outcome unknown, and only `--force` deleted the VM. `dc-pks-8fb9` may still be listed in the desk's Machines.
