"""The structural check of a builder before it becomes an image (§7): no boot
descriptor, an empty seed directory, none of the credential files the
secrets guard knows (the parent's check 6(b)), no sminos enrollment, and none
of the state a boot or the driver leaves.

The driver streams this file's source to the builder (`python3 - /`), so it
imports nothing but the standard library. Each finding is one line,
`forbidden <path>`; the exit is 0 when there is none, 1 otherwise."""

import os
import pathlib
import sys

# The guard's credential files, relative to a home (devcloud/hooks/mods/secrets-sources.tsx,
# CREDENTIAL_FILES, STORE_DIR, GCLOUD_DIR, GCLOUD_SKIP; a unit test keeps the two equal).
CREDENTIAL_FILES = (".config/gh/hosts.yml", ".pgpass", ".codex/auth.json", ".claude/.credentials.json",
                    ".config/hcloud/cli.toml", ".docker/config.json", ".netrc", ".git-credentials", ".npmrc")
STORE_DIR = ".config/claude-secrets"
GCLOUD_DIR = ".config/gcloud"
GCLOUD_SKIP = ("logs", "cache", "configurations", "surface_data", "virtenv")
# A sminos enrollment ($SMINOS_HOME/daemon/, its default under each home).
SMINOS_DAEMON = ".claude/sminos/daemon"
# What only a booted host, or the driver's first contact, holds.
HOST_PATHS = ("/etc/devcloud/boot.env", "/etc/devcloud/enroll-code", "/var/lib/devcloud", "/var/lib/devcloud-stage")
SEED_DIR = "/etc/devcloud/seed"


def _homes(root):
    try:
        lines = (root / "etc/passwd").read_text().splitlines()
    except FileNotFoundError:
        return []
    homes = []
    for line in lines:
        fields = line.split(":")
        if len(fields) > 5 and fields[5].startswith("/") and fields[5] != "/" and fields[5] not in homes:
            homes.append(fields[5])
    return homes


def findings(root="/"):
    """Every forbidden path under `root`, as the host would name it."""
    root = pathlib.Path(root)

    def there(path):
        return root / path.lstrip("/")

    found = [path for path in HOST_PATHS if os.path.lexists(there(path))]
    seed = there(SEED_DIR)
    if seed.is_dir():
        found += [f"{SEED_DIR}/{name}" for name in sorted(os.listdir(seed))]
    elif os.path.lexists(seed):
        found.append(SEED_DIR)
    for home in _homes(root):
        base = home.rstrip("/")
        for rel in CREDENTIAL_FILES + (STORE_DIR, SMINOS_DAEMON):
            if os.path.lexists(there(f"{base}/{rel}")):
                found.append(f"{base}/{rel}")
        gcloud = there(f"{base}/{GCLOUD_DIR}")
        if gcloud.is_dir():
            for path in sorted(gcloud.rglob("*.json")):
                rel = path.relative_to(gcloud)
                if rel.parts[0] not in GCLOUD_SKIP:
                    found.append(f"{base}/{GCLOUD_DIR}/{rel.as_posix()}")
    return found


def main(argv):
    found = findings(argv[0] if argv else "/")
    for path in found:
        print(f"forbidden {path}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
