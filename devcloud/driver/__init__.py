"""The VM driver, `devcloud vm` (the driver spec, docs/doperpowers/specs/
2026-10-21-devcloud-vm-driver-design.md): one process per command on a Mac,
calling provider executables (I13), `ssh` and `sminos`. Lifecycle state lives
at the providers (labels), on the hosts (the authoritative lease) and in the
profile; the local files are the SSH key, its known_hosts and the reap log."""
