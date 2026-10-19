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

from . import envfile, secrets
from .secrets import ProfileError


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

    @property
    def host_settings(self):
        """managed-settings.json as a host gets it: with an empty
        `prependPlugins` unless the profile sets its own. Managed settings
        with any key seat the engine's security default
        (cc-plugin-sec-default@builtin) outermost unless managed
        `prependPlugins` is set and leaves it out, and the seated default
        passes the plugins a person installs over on classic hooks, the
        prompt's parts, compactions, and the rows the transcript keeps from
        attachments, hook context and compactions: the secrets guard and the
        sminos bridge among them (Design §6). An empty file is left as it is:
        the engine counts no managed settings then and seats nothing."""
        settings = json.loads(self.managed_settings)
        if not settings or "prependPlugins" in settings:
            return self.managed_settings
        return (json.dumps({**settings, "prependPlugins": []}, indent=2) + "\n").encode()


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
