"""The profile's reader side (Interfaces I8): `~/.claude/devcloud/` in the
person's configuration repository.

    managed-settings.json   written to /etc/claude-code/managed-settings.json
                            (Profile.host_settings); its env.ANTHROPIC_BASE_URL is
                            the gateway step 6 checks
    profile.env             KEY=value lines for /etc/devcloud/env; TZ also sets
                            the system time zone
    secrets.toml            the materializer's input (I3)
    home/                   files copied into the user's home, secret-free
    build.env               the image's user inputs, read where the image is built

Only managed-settings.json is required; an absent profile.env, secrets.toml or
home/ is nothing to do."""

import dataclasses
import json
import pathlib
import re

from . import envfile, plugins, secrets
from .secrets import ProfileError

# One public key per line (`<type> <base64> [comment]`), as authorized_keys takes it.
_PUBLIC_KEY = re.compile(r"(?:ssh-|ecdsa-|sk-)[A-Za-z0-9@.-]+ [A-Za-z0-9+/=]+(?: [^\n]*)?\Z")


@dataclasses.dataclass(frozen=True)
class Profile:
    dir: pathlib.Path
    managed_settings: bytes
    env: dict
    secrets: list
    home: pathlib.Path | None

    @property
    def gateway(self):
        try:
            value = json.loads(self.managed_settings)["env"]["ANTHROPIC_BASE_URL"]
        except (KeyError, TypeError):
            return None
        return value if isinstance(value, str) and value else None

    def host_settings(self, marketplace=None):
        """managed-settings.json as a host gets it. With `marketplace`, the
        root-owned copy of the doperpowers marketplace, its plugins are seated
        as the Macs seat them (plugins.managed: the bridge outside the guard,
        the driver's §10). Without one, an empty `prependPlugins` unless the
        profile sets its own: managed settings with any key seat the engine's
        security default (cc-plugin-sec-default@builtin) outermost unless
        managed `prependPlugins` is set and leaves it out, and the seated
        default passes the plugins a person installs over on classic hooks,
        the prompt's parts, compactions, and the rows the transcript keeps
        from attachments, hook context and compactions: the secrets guard and
        the sminos bridge among them (Design §6). An empty file is left as it
        is then: the engine counts no managed settings and seats nothing."""
        settings = json.loads(self.managed_settings)
        if marketplace is not None:
            return (json.dumps(plugins.managed(settings, marketplace), indent=2) + "\n").encode()
        if not settings or "prependPlugins" in settings:
            return self.managed_settings
        return (json.dumps({**settings, "prependPlugins": []}, indent=2) + "\n").encode()

    def driver_keys(self):
        """The public keys under `driver-keys/` (each driver Mac's
        `<machine>.pub`, Design §8.3), in name order, and how many lines were
        not keys; ([], 0) without the directory."""
        keys, skipped = [], 0
        directory = self.dir / "driver-keys"
        if not directory.is_dir():
            return keys, skipped
        for path in sorted(directory.glob("*.pub")):
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if _PUBLIC_KEY.match(line):
                    keys.append(line)
                else:
                    skipped += 1
        return keys, skipped


def read(claude_dir, base_env):
    """Reads and checks the profile; `base_env` is what profile.env's
    references expand against beyond its own earlier lines."""
    root = pathlib.Path(claude_dir) / "devcloud"
    if not root.is_dir():
        raise ProfileError("the configuration repository has no devcloud/ profile")
    try:
        managed = (root / "managed-settings.json").read_bytes()
    except FileNotFoundError:
        raise ProfileError("devcloud/managed-settings.json is absent") from None
    try:
        if not isinstance(json.loads(managed), dict):
            raise ValueError("not an object")
    except ValueError as error:
        raise ProfileError(f"devcloud/managed-settings.json is not a JSON object ({error})") from None

    env = {}
    env_path = root / "profile.env"
    if env_path.exists():
        try:
            env = envfile.parse(env_path.read_text(), base=base_env)
            envfile.format(env.items())
        except ValueError as error:
            raise ProfileError(f"devcloud/profile.env: {error}") from None

    toml_path = root / "secrets.toml"
    entries = secrets.parse(toml_path.read_text()) if toml_path.exists() else []
    clash = sorted({e.env for e in entries if e.env} & set(env))
    if clash:
        raise ProfileError(f"{', '.join(clash)} set by both profile.env and secrets.toml")

    home = root / "home"
    return Profile(dir=root, managed_settings=managed, env=env, secrets=entries,
                   home=home if home.is_dir() else None)
