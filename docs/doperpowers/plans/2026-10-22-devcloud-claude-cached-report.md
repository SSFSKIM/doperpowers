# devcloud: the native Claude release from a cached layer (board ticket 120)

Branch `devcloud-claude-cached`, off main at `22952efb`. Changes through `1d749808`; devcloud
0.9.2 (`scripts/bump-version.sh --plugin devcloud 0.9.2`). PR: #346. Built by a plan-executor run
on astra, at the person's instruction to keep subagents off the Claude weekly limits. The
coordinating session wrote this file from the run's final report, because the astra role does not
write report files.

## The installer question, answered first

Sources read on 2026-10-22: Anthropic's installer (`https://claude.ai/install.sh`), the native
installation documentation (`https://code.claude.com/docs/en/setup`), and `claude install --help`
on 2.1.308.

The installer downloads from `https://downloads.claude.ai/claude-code-releases`:
1. It resolves `/latest`.
2. It reads `<version>/manifest.json` and takes `platforms.<platform>.checksum`.
3. It downloads `<version>/<platform>/claude` and verifies its SHA256.
4. It runs that binary's `install [target]`.

The CLI takes a channel or a version, plus `--force`. It has no documented flag for installing from
a local file or offline.

Two experiments, both as a non-root dev user in a container with `--network=none`:
- **The verified binary alone.** `claude install 2.1.308` exits 1 with `getaddrinfo EAI_AGAIN
  downloads.claude.ai`. Fetching the binary does not make its `install` work offline
  (run 39751967988).
- **The binary seeded at the documented native path first.** With it placed at
  `~/.local/share/claude/versions/2.1.308`, `install 2.1.308` succeeds offline. `claude doctor` then
  reports `Config install method: native` and `Auto-updates: enabled` (run 39752354478).

The implementation therefore seeds only the version file. The binary's own installer creates the
launcher, the configuration and the shell integration. Installer metadata is not written by hand,
the updater is not disabled, and npm is not used. This short circuit is current installer behavior,
not a documented offline flag. The network-disabled setup step and the integration check catch a
future change to it.

## What changed

- `devcloud/image/fetch-claude.sh`:
  - fetches the native Linux x64 or arm64 release into `/usr/local/lib/claude-code`;
  - validates the version, the checksum's format and the downloaded SHA256 before it publishes the
    bytes;
  - bounds each transfer's timeout and retries;
  - takes `DEVCLOUD_CLAUDE_RELEASE_URL` to point controlled tests at another release base.
- `devcloud/image/Dockerfile`:
  - a layer that mounts only `fetch-claude.sh`, placed before the user and home build arguments and
    the broad `devcloud/` mount, so an unrelated host change reuses the verified release;
  - the setup step runs with `--network=none`.
- `devcloud/image/setup.sh`:
  - a VM bake or an adopt runs the same fetch after the packages; Docker uses its cached fetch;
  - setup copies the verified release into the dev user's native versions directory and runs that
    binary's `install VERSION` as the user;
  - it checks the launcher by running `--version`, keeps the final installed check, and removes the
    system staging copy.
- `devcloud/tests/unit/test_claude_fetch.py`: six behavioral tests. They cover both architectures, a
  refusing endpoint, a corrupt binary, a missing checksum, an invalid version and an unsupported
  architecture. They ran red before the downloader existed and green after.
- `devcloud/tests/integration.py`, in a container with no network:
  - the native path;
  - the user's ownership;
  - writable launcher and versions directories;
  - native install metadata;
  - the updater enabled.
- `devcloud/tests/run.sh`: a successful build prints each named BuildKit step's `DONE` duration
  beside the cache hits. A slow build is explained instead of hidden.
- `devcloud/README.md`: documents:
  - the cache;
  - native ownership;
  - offline setup;
  - where a cold build fails.

## Outage proof

Two scratch-ref runs passed all three real devcloud gate parts: 39753080538 first, then 39753584703
with step timings. Each runner did the following:
1. **A healthy build.** It first built against a local release endpoint that redirected to the real
   downloads.
2. **The release cut off.** It switched that same endpoint to HTTP 403, without changing its URL or
   the fetch cache key.
3. **Setup forced to rebuild.** An unrelated boot-file change invalidated the broad setup layer.
4. **Warm gates.** The image, host and systemd parts all passed. Their fetch step was `CACHED`, and
   setup ran again with no network. The endpoint counted zero release requests during each warm
   gate.
5. **A cold fetch.** A neutral change to the fetch step forced a cache miss while the package layers
   were reused. Every resulting build failed visibly at the fetch, on HTTP 403.

Main's cache was not touched by these runs, and the scratch refs and branches were removed. After
the merge, the image gate seeds the new release layer.

## Timings

Cold numbers are from the PR's own run (39754671318); warm numbers are from the outage proof.

| Gate | Cold fetch | Cold setup | Cold image build | Warm fetch | Warm setup | Warm image build |
|---|---:|---:|---:|---|---:|---:|
| devcloud-image | 5.9 s | 5.4 s | 39.2 s | CACHED | 6.8 s | 9.9 s |
| devcloud-host | 5.6 s | 5.4 s | 35.7 s | CACHED | 6.8 s | 9.9 s |
| devcloud-systemd | 13.3 s | 6.6 s | 41.6 s | CACHED | 6.8 s | 10.1 s |

"Cold" here means the new release layer missed while the package layers came from main's cache.
The warm numbers reuse a runner's local cache, so a fresh runner importing the remote cache also
pays the transfer and unpacking. The full PR gates took 2m02s, 2m02s and 1m59s.

## Live proof on GCE (2026-10-22)

1. **The bake.** `devcloud vm image build --account gce` used the default GCE account explicitly, so
   no Hetzner builder ran. The builder produced image `dc-img-8deeaabc4fd8-202610220911` (recipe
   `8deeaabc4fd8`) and was deleted automatically.
2. **The VM.** `devcloud vm up --account gce --label ccache --ttl 1h --project
   SSFSKIM/doperpowers@devcloud-claude-cached` made `dc-ccache-0194` from that image, ready in
   3m33s.
3. **The checks.** `devcloud status` showed all 12 steps `ok`, projects included. As the dev user:
   - the launcher and versions directories were writable;
   - `claude --version` printed `2.1.308 (Claude Code)`;
   - `claude doctor` reported native execution, the native install method, the updater enabled and
     the channel latest.
4. **Cleanup.** `devcloud vm down` departed and deleted the VM, and the image was deleted through
   GCE. At 09:20Z the builder, the host and the image were all absent.

## Review and CI

- doperpowers:review-code at the medium rung, on `22952efb..3c50493a`: no material findings. On the
  timing-only delta `3c50493a..1d749808`: no material findings.
- The first implementation run was 39752862643, green 8/8. The final head's ci-gate was 39754033433,
  green 8/8, including 715 unit tests and the native offline integration. The PR's own run,
  39754671318, was green.
- CI-opt has the PR and the measurements.

## Friction

- The MacBook's local Docker daemon was not running (`/var/run/docker.sock` absent), so every Linux
  experiment ran on GitHub Actions. The check is `docker info`.
- The claude.ai rate-limit row in friction tracker #304 now holds only for a cold release fetch.
  Warm builds make no request to the release service, while a cold fetch still needs it and fails
  closed.

## Residue

None.
