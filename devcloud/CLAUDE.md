# devcloud/

A path here is named from `devcloud/` when it is the plugin's own file; `docs/`, `scripts/` and `devcloud/…` paths are the repository's. The secrets guard mod's detail is in `hooks/mods/CLAUDE.md`.

A second plugin in this marketplace (its entry found by name, versioned on its own: `scripts/bump-version.sh --plugin devcloud`), opt-in, design in `docs/doperpowers/specs/2026-10-15-devcloud-design.md`.

The host: `image/` (`setup.sh`, which runs `packages.sh` first; the `Dockerfile`, which runs `packages.sh` as four layers, one per part, keyed on that file alone, then the rest of `setup.sh`) and `boot/` (`devcloud-boot`, steps 1–12 in `devcloudlib/steps.py`, step 12's projects and mirror cache in `devcloudlib/projects.py`, step 11's sminos daemon on an enrolled persistent host in `devcloudlib/sminos_host.py`, the tailnet join with the Tailscale OAuth client in step 4; `devcloud` for status and the jobs; `devcloud-services`, the supervisor where PID 1 is not systemd), tested in containers by `devcloud/tests/run.sh` (the `devcloud-*` gates, one part each: `DEVCLOUD_PART`, the integration parts in `tests/integration.py`'s `PARTS`).

`skills/devenv/` writes a repository's `devenv/` from its CI, manifests and README and proves it with `devenv up`.

The VM driver: `driver/` (`devcloud vm`, run by `bin/devcloud`; the shipped providers in `driver/providers/`), design in `docs/doperpowers/specs/2026-10-21-devcloud-vm-driver-design.md`, unit-tested in `tests/unit/test_driver_*.py` and the providers' own tests; `skills/vm/` is what a session reads to use it.
