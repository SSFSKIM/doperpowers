# devcloud image layers and a faster image check: report (board #116)

Branch `devcloud-image-layers`, off main at 53b6587f (devcloud 0.8.0, #337). The ticket body (board #116) is the statement of work.

## What changed

- **Cut 1, the package layer.** The apt packages, package repositories and release tools moved out of `devcloud/image/setup.sh` into a new `devcloud/image/packages.sh`, which takes no input. setup.sh still runs it, after checking its inputs and before making the user, so `devcloud vm image build` and adopt still run a single recipe. The Dockerfile runs packages.sh as its own `RUN`, bind-mounting only that file and placed before the `ARG`s, so the layer's cache key is packages.sh alone (plus the base image). It then runs setup.sh with `DEVCLOUD_PACKAGES=installed`. The apt cache cleanup moved into packages.sh with the installs; setup.sh still removes the root and user caches. devcloud is bumped to 0.8.1 because the recipe changed (recipe hash `dee63a031ef3`).
- **Cut 2, the image check.** Profiling showed that the ticket's premise did not hold: the scan was not the cost. `check_image.export` now copies the image's filesystem inside a container of the image, onto a bind mount at a random path that it excludes, then chowns the copy back to the caller. The scan is not sharded (see the measurements below).
- **Rebalance.** With the image group down to about 25 s, `PARTS` became `image` = image + one-shot, `host` = host + projects, `systemd` = systemd.
- Docs: `devcloud/README.md` and `devcloud/CLAUDE.md` describe the two layers.

## Profile (CI runner: 4 vCPU AMD EPYC 7763, Docker 29.4; image 0.7 GB, 69k files, 1.95 GB unpacked)

Run 39716683368 (instrumented scanner, throwaway commit):

| phase of `image_is_clean` | time |
|---|---|
| export: `docker run <image> tar -c / \| tar -x` | 82.3 s |
| the bun scan, all of it | 9.6 s (detect 4.3, known-value search 3.0, reads 0.9, files over 64 MiB 0.9, walk 0.4) |
| dpkg verify of the one loose path | 4.4 s |
| docker history scan, credential files | under 0.1 s |

The ticket's open question was walking versus matching. The answer is neither: the export took 85% of the case.

Run 39717304822 compared export methods (and ran out of runner disk in its last step, after every number below):

| export method | time |
|---|---|
| A: today's `docker run tar` streamed out and unpacked | 83.0 s |
| D: the same stream into /dev/null | 76.8 s (the cost is docker's attach stream) |
| B: `docker create` + `docker export` and unpack | 19.8 s (listing differs: /etc/hosts, hostname and resolv.conf are empty placeholders, plus /dev/console) |
| E: tar inside a container onto a bind mount, then chown | **5.8 s**; listing equal to A (71,934 entries, same type and size) |
| scan sharded 2 / 4 / 8 ways | 6.4 / 4.8 / 5.5 s against 9.5 s single, findings equal |

Decision: E. Sharding would save about 5 s more, and it would add a second way for a fail-closed security check to scan less than the image holds. That is not worth 5 s; the image part is no longer the slowest.

## Result: run 39718389395 (all devcloud gates on ed5e6fdf, plus a throwaway unsharded `devcloud-all`)

| gate | job | build | integration | cases |
|---|---|---|---|---|
| devcloud-unit | 1m29s | – | – (79 s, 677 tests) | – |
| devcloud-image | 3m30s | 126 s | 65 s (was 96–104) | 14 |
| devcloud-host | 3m55s | 132 s | 87 s (was 101–108) | 22 |
| devcloud-systemd | 3m08s | 117 s | 65 s (was 88–101) | 10 |
| devcloud-all (unsharded, throwaway) | 7m33s | 149 s | 215 s (was 289) | 44 |

`image_is_clean` alone went from 96 s to 16 s. The devcloud set's wall time went from 4m50s (#336's PR run) to 3m55s. The slowest integration part is now host at 87 s, against 108 s before.

## The PR's run

PR #340, run (39719781323 on 2ed14dc1, all green): devcloud-unit 1m19s; devcloud-image 4m01s (build 146 s, integration 70 s, `image_is_clean` 16 s); devcloud-host 4m05s (build 138 s, integration 87 s); devcloud-systemd 3m12s (build 115 s, integration 67 s). The set's wall time was 4m05s, against 4m50s for #336's PR run. Build variance between runners (115–146 s) now sets the slowest gate, and the build is what the layer cache addresses.

**Every case still runs exactly once.** The unsharded run printed 44 case lines and the three parts 46. Without "the stand-ins start", which each part that boots containers runs once (now all three), both lists hold the same 43 cases, sorted equal, with no duplicate and no failure. The one-shot cases now run without the host group before them, and pass.

## The layer cache (throwaway gate `devcloud-cache`, one runner, BuildKit's local cache)

Run 39719236090: three builds of the branch's Dockerfile in sequence on one runner.

| build | packages.sh step | setup.sh step | image export | total |
|---|---|---|---|---|
| from nothing | 53.2 s | 10.8 s | 48.9 s | 118 s |
| after a change under `devcloud/boot` | **CACHED** | 11.5 s | 8.3 s | **20 s** |
| after a change to `packages.sh` | 49.8 s (FROM cached) | 10.5 s | 50.6 s | 112 s |

The package layer's key is packages.sh: a change elsewhere in `devcloud/` reuses it, and a change to packages.sh rebuilds it. With a cache across runs (ci-kit #88), a typical devcloud change's image build would drop from about 120–150 s to about 20 s in each of the three integration gates.

## Live proof (default GCE account, 2026-10-22)

- `devcloud vm image build --account gce` from db0710ab: builder `dc-bake-7715` (e2-highcpu-2), image `dc-img-dee63a031ef3-202610220332`, 7m17s, builder deleted.
- `devcloud vm up --label layers --project SSFSKIM/doperpowers@devcloud-image-layers --ttl 2h`, created from that image and ready in 3m39s. `devcloud status`: all 12 steps `ok`, projects included (`SSFSKIM/doperpowers@devcloud-image-layers ok`). gh, gcloud, tailscale, docker, node, uv, hcloud, claude and zsh were on PATH, and the en_US.UTF-8 locale was present. `devcloud vm down`: departed and deleted.
- No adopt, as the brief directed. The container integration runs setup.sh on a plain host.
- Cleanup the same day: the VM was deleted by `down`, and the image deleted with `gcloud compute images delete`. No other devcloud image existed on the account (the listing before the deletion held only this one), so the driver's retention, newest two, had nothing older to remove. `devcloud vm image ls` and `devcloud vm ls` now show no image and no VM of this work.

## Review

`doperpowers:reviewer-medium` reviewed 53b6587f..ed5e6fdf: no material findings, verdict correct. It checked that the package commands are unchanged, that all 43 cases are assigned exactly once, and how failures propagate through the export's shell. It could not run Docker; the CI runs above cover that. Later commits change only comments, timings and this report.

## Ticket and handoff

PR #340 (no `Closes`: the board is the api binding). The PR and its times went to CI-opt by `sminos say`. The board transition to in-review is the dispatching session's: this executor does not write the board.

## Residue

1. **ci-kit build cache (CI-opt, ci-kit #88).** The layer split pays off only when a gate can reach a cache. On one runner, a rebuild after a change outside packages.sh took 29 s against 137 s (above). Sent to CI-opt with the PR.
2. **A frozen package layer goes stale.** packages.sh installs "latest" from release URLs (uv, hcloud, Node LTS, the apt repositories). With a cross-run cache keyed on the file alone, CI would test the package set from the cache's first build until packages.sh changes or the entry expires, while VMs bake fresh. ci-kit's cache design should bound an entry's age (a weekly key, for one) when it lands.
3. **`check_image` on a Mac with colima.** The export bind-mounts a temporary directory. Docker Desktop shares macOS's temp directories, but colima shares only $HOME by default, and there the check fails closed with a hint, not silently. If the person runs the check locally with colima, the work directory should move under $HOME.
