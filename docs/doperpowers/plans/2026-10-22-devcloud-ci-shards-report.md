# devcloud CI shards: report (board #113)

Branch `devcloud-ci-shards`, off main at c3310869. The statement of work is board ticket #113's body.

## What changed

- `devcloud/tests/run.sh` takes `DEVCLOUD_PART`, following sminos's `SMINOS_PART`. `unit` runs the unit tests only. `image`, `host` and `systemd` each build the image and run one part of the integration cases. Unset, it runs everything, as before. An unknown value exits 2.
- `devcloud/tests/integration.py` used to run each case from its decorator at import time. Now each case is registered under the group of cases that share its container:
  - `image`: the image check; it boots no container.
  - `host`: the one container booted once, with about twenty checks in sequence.
  - `systemd`: the systemd container, plus the image built for it, which the spot and adopted cases also boot.
  - `projects` and `one-shot`: cases that each boot a throwaway container of their own.

  `PARTS` maps each part to whole groups. `__main__` runs the selected cases in definition order. The stand-ins start once, before the first case that needs them, and a failed start ends the run. With no part, the output is the old sequence line for line.
- `.github/ci-kit.yml`: the `devcloud` gate becomes `devcloud-unit`, `devcloud-image`, `devcloud-host` and `devcloud-systemd`, all over the old paths. Only the unit and image gates install bun, because only the unit tests and the image scan use it.
- Docs: `devcloud/CLAUDE.md` and `devcloud/README.md` name the new gates. The TECH-DEBT entry "The devcloud CI gate runs in series" is removed.
- Fix exposed by the sharding: `leaking_apply_is_scrubbed` grepped for the original `gh-token` value. In the serial run, the host group's rotation case had already replaced that token in the store, so the grep could never find it and the case passed whatever the logs held. The case now greps for the token the stand-in currently serves, so it checks for real in every order.

## Measurement before the cut

Taken from the per-line timestamps of main's run 39662033753, where the integration took 4m54s in total:

| group | cases | time |
|---|---|---|
| image (planted check, fails closed, image holds no secret) | 3 | 104 s (the scan alone: 96 s) |
| host (boot … stop_and_restart) | 19 | 56 s |
| systemd (under_systemd … held departure, spot, adopted) | 9 | 67 s |
| projects | 2 | 23 s |
| one-shot (sandbox identity, seated, setup.sh refusal, 7 failure paths) | 10 | 42 s |
| stand-ins start | setup | 1 s |

The parts: `image` alone (104 s), `host` = host + one-shot (about 99 s), `systemd` = systemd + projects (about 91 s). A fourth integration part would save at most about 6 s, because the 96 s image scan cannot be split without changing `check_image`.

## Result (run 39703626947, all gates side by side on one commit)

| gate | job | setup | unit | image build | integration |
|---|---|---|---|---|---|
| devcloud-all (the unsharded run, a throwaway gate) | 8m38s | 4 s | 71 s | 148 s | 289 s |
| devcloud-unit | 1m21s | 4 s | 70 s (615 tests) | – | – |
| devcloud-image | 4m29s | 3 s | – | 150 s | 104 s |
| devcloud-host | 4m30s | 6 s | – | 153 s | 101 s |
| devcloud-systemd | 4m25s | 11 s | – | 148 s | 101 s |

Wall time for the devcloud gate set went from 8m38s to 4m30s. The PR body carries the times from the PR's own first green run.

**Every case still runs exactly once.** The unsharded gate printed 44 case lines and the three parts together printed 45. The one extra line is "the stand-ins start", setup that runs in each part that boots containers (host and systemd). Without that line, the two lists hold the same 43 cases, sorted equal, with no duplicate and no failure. The unsharded run's sequence is also identical, line for line, to main's reference run (`diff` empty). Locally, before CI, an import of `integration.py` confirmed that the parts partition the 43 registered cases.

## Decisions

- **Part names are semantic** (`image`, `host`, `systemd`) instead of the ticket's example `int-1..3`. A gate's name then says what it covers, and rebalancing changes only `PARTS`.
- **No image cache.** The Dockerfile is one `RUN` that bind-mounts all of `devcloud/`, so any change under `devcloud/`, which is exactly when these gates run, invalidates the only layer. A cache would also need the GHA cache backend, and ci-kit's `run` steps don't get `ACTIONS_RUNTIME_TOKEN`. The ticket made the cache conditional on stable early layers, and there are none, so it is in the residue.
- **No version bump.** The change touches only tests and CI, and earlier test-only devcloud commits don't bump either.
- The coordinator checked that main's ruleset requires no named status check, so dropping the `devcloud` gate name breaks nothing.

## Review

`doperpowers:reviewer-medium` reviewed c3310869..cc1c5176, pointed at cross-part state dependencies and the exactly-once property. Result: no material findings, verdict correct. The README commit after it is docs only.

## Residue

1. **Split `setup.sh`'s package layer out of the image's single RUN.** Today every change under `devcloud/` rebuilds the whole image: about 150 s in each of three gates. With the apt/toolchain layer separate and keyed on its own inputs, a cache could serve it. The catch: `setup.sh` is also the VM builder's recipe.
2. **ci-kit: a build cache for gates.** `run` steps don't see `ACTIONS_RUNTIME_TOKEN`/`ACTIONS_RESULTS_URL`, so `docker buildx --cache-from type=gha` is unreachable from a gate. This needs either a ci-kit `cache` option that exports them, or a registry-cache credential. It belongs in ci-kit's repo.
3. **The image scan sets the floor.** `image_is_clean` takes 96 s, and the image part can't get shorter than that plus the build. Running the scan in parallel per top-level directory in `check_image` would lower the gate set's wall time further.

## Friction

None that blocked anything. `gh api …/jobs/<id>/logs` refuses output with escape sequences unless given `--allow-escape-sequences`; `gh run view --log --job` worked instead.
