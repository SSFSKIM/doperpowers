"""What `devcloud vm adopt` runs as root on the machine it adopts (§6.5),
streamed there as `python3 - <command> ...` (standard library only, Python
3.9 or later), before anything of devcloud is on it:

  inspect             one JSON line: the OS (`ID`, `VERSION_ID`) and the
                      boot descriptor's name and adoption flag when there is
                      one
  preflight <user> <uid> <home>
                      one JSON line, {"problems": [...]}: each existing
                      account or home setup.sh would remove or take over to
                      make the profile's user (an account of that name, one
                      holding that uid, the home path). None: the verdict is
                      kept in /var/lib/devcloud-adopt/preflight.json, so a
                      resumed adoption is not refused for the account
                      setup.sh made on its first run.
  save-keys <login>   root's and <login>'s authorized_keys copied to
                      /var/lib/devcloud-adopt with the manifest keys.json
                      that release restores from: {"keys": [{"path",
                      "owner", "saved"}]}, `saved` the copy's file name or
                      null (there was none: release removes the file). Once
                      only: with keys.json present it changes nothing, so a
                      resumed adoption never saves the keys devcloud wrote.
  authorize <b64>     the driver keys (base64 of their lines) added to
                      root's authorized_keys, so the driver reaches root
  rollback            an adoption that never booted (no descriptor
                      installed) given back: every path the credential
                      ledger lists (the seed; refused, removing nothing, when
                      one that exists lies outside /etc/devcloud and
                      /var/lib/devcloud, which only `devcloud release`
                      removes), the staged descriptor, devcloud's units, the
                      saved authorized_keys restored, then the backup and
                      /var/lib/devcloud. The tools and the user setup.sh
                      made stay, as after a release.

The backup lives outside /var/lib/devcloud, whose existence setup.sh
refuses."""

import base64
import json
import os
import pathlib
import pwd
import shutil
import subprocess
import sys

ADOPT_DIR = "/var/lib/devcloud-adopt"
BOOT_ENV = "/etc/devcloud/boot.env"
STATE_DIR = "/var/lib/devcloud"
LEDGER = "/var/lib/devcloud/credentials.ledger"
STAGE_DIR = "/var/lib/devcloud-stage"
UNIT_DIR = "/etc/systemd/system"
# What an adoption writes as root before its boot; anything else the ledger
# lists is a boot's, in the user's home, which only the release removes (as the user).
ROLLBACK_SCOPE = ("/etc/devcloud/", "/var/lib/devcloud/")


class Refused(Exception):
    pass


def _under(root, path):
    return pathlib.Path(root) / str(path).lstrip("/")


def _env(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip().removeprefix("export ").strip()] = value.strip().strip('"').strip("'")
    return out


def inspect(root="/"):
    try:
        release = _env(_under(root, "/etc/os-release").read_text())
    except OSError:
        release = {}
    try:
        desc = _env(_under(root, BOOT_ENV).read_text())
        descriptor = {"name": desc.get("DEVCLOUD_NAME"), "adopted": desc.get("DEVCLOUD_ADOPTED") == "1"}
    except FileNotFoundError:
        descriptor = None
    return {"id": release.get("ID"), "version": release.get("VERSION_ID"), "descriptor": descriptor}


def preflight(user, uid, home, root="/", by_name=pwd.getpwnam, by_uid=pwd.getpwuid):
    """What setup.sh would remove or take over to make `user` (uid `uid`,
    home `home`): adopt never deletes or replaces an existing account, so
    any of them refuses the adoption before anything is changed."""
    verdict = _under(root, ADOPT_DIR) / "preflight.json"
    wanted = {"user": user, "uid": int(uid), "home": home}
    if verdict.exists():
        checked = json.loads(verdict.read_text())
        if checked == wanted:
            return []
        return [f"an earlier adoption here was checked for {checked['user']} (uid {checked['uid']}, home "
                f"{checked['home']}), and build.env now asks for {user} (uid {uid}, home {home})"]
    problems = []
    try:
        have = by_name(user)
        problems.append(f"an account named {user} already exists (uid {have.pw_uid}, home {have.pw_dir})")
    except KeyError:
        pass
    try:
        holder = by_uid(int(uid))
        if holder.pw_name != user:
            problems.append(f"uid {uid} belongs to {holder.pw_name} (home {holder.pw_dir})")
    except KeyError:
        pass
    if os.path.lexists(_under(root, home)):
        problems.append(f"{home} already exists")
    if not problems:
        verdict.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(verdict.parent, 0o700)
        verdict.write_text(json.dumps(wanted) + "\n")
    return problems


def _home(user, passwd):
    return pathlib.Path(passwd(user).pw_dir)


def save_keys(login, root="/", passwd=pwd.getpwnam):
    adopt = _under(root, ADOPT_DIR)
    manifest = adopt / "keys.json"
    if manifest.exists():
        return "already saved"
    adopt.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(adopt, 0o700)
    entries = []
    for owner in dict.fromkeys(("root", login)):
        path = _home(owner, passwd) / ".ssh" / "authorized_keys"
        source = _under(root, path)
        saved = None
        if source.exists():
            saved = f"{owner}.authorized_keys"
            copy = adopt / saved
            copy.write_bytes(source.read_bytes())
            os.chmod(copy, 0o600)
        entries.append({"path": str(path), "owner": owner, "saved": saved})
    staged = adopt / "keys.json.tmp"
    staged.write_text(json.dumps({"keys": entries}, indent=1) + "\n")
    os.chmod(staged, 0o600)
    os.replace(staged, manifest)
    return "saved " + ", ".join(e["path"] for e in entries)


def authorize(keys, root="/", passwd=pwd.getpwnam):
    ssh = _under(root, _home("root", passwd) / ".ssh")
    ssh.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = ssh / "authorized_keys"
    present = path.read_text().splitlines() if path.exists() else []
    missing = [k for k in keys if k.strip() and k.strip() not in {p.strip() for p in present}]
    if missing:
        text = "\n".join(present) + ("\n" if present else "") + "\n".join(missing) + "\n"
        path.write_text(text)
    os.chmod(path, 0o600)
    return f"authorized {len(missing)} key(s)"


def _remove(path):
    if not os.path.lexists(path):
        return
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)


def _systemctl(*args):
    subprocess.run(["systemctl", *args], check=True, capture_output=True, timeout=180)


def rollback(root="/", passwd=pwd.getpwnam, systemctl=_systemctl):
    """Gives back an adoption that never booted; returns what it did."""
    ledger = _under(root, LEDGER)
    listed = [line for line in ledger.read_text().splitlines() if line.startswith("/")] if ledger.exists() else []
    foreign = [path for path in listed if not path.startswith(ROLLBACK_SCOPE) and os.path.lexists(_under(root, path))]
    if foreign:
        raise Refused(f"the ledger lists {', '.join(foreign)}, which only `devcloud release` removes: this "
                      "machine booted as a host")
    for path in listed:
        _remove(_under(root, path))
    _remove(_under(root, STAGE_DIR))
    unit_dir = _under(root, UNIT_DIR)
    units = sorted(p.name for p in unit_dir.glob("devcloud-*") if p.suffix in (".service", ".timer"))
    if units:
        systemctl("disable", "--now", *units)
        for name in units:
            _remove(unit_dir / name)
            _remove(unit_dir / f"{name}.d")
        systemctl("daemon-reload")
    keys = _restore_keys(root, passwd)
    _remove(_under(root, STATE_DIR))
    return (f"removed {len(listed)} ledgered path(s), the staged descriptor and {', '.join(units) or 'no unit'}; "
            f"{keys}")


def _restore_keys(root, passwd):
    """Each saved authorized_keys back where save-keys found it (one it did not
    find removed), owned by its owner, then the backup."""
    adopt = _under(root, ADOPT_DIR)
    manifest = adopt / "keys.json"
    if not manifest.exists():
        _remove(adopt)      # at most the preflight's verdict: no key was saved, so none was changed
        return "nothing saved, nothing to restore"
    restored = []
    for entry in json.loads(manifest.read_text())["keys"]:
        target = _under(root, entry["path"])
        if entry.get("saved") is None:
            _remove(target)
            restored.append(f"{entry['path']} removed (there was none)")
            continue
        owner = passwd(entry["owner"])
        data = (adopt / entry["saved"]).read_bytes()
        if not target.parent.is_dir():
            target.parent.mkdir(mode=0o700, parents=True)
            os.chown(target.parent, owner.pw_uid, owner.pw_gid)
        _remove(target)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, data)
            os.fchown(fd, owner.pw_uid, owner.pw_gid)
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        restored.append(f"{entry['path']} restored")
    _remove(adopt)
    return "; ".join(restored)


def main(argv):
    if argv[:1] == ["inspect"]:
        print(json.dumps(inspect()))
    elif argv[:1] == ["preflight"] and len(argv) == 4 and argv[2].isdigit():
        print(json.dumps({"problems": preflight(*argv[1:])}))
    elif argv[:1] == ["save-keys"] and len(argv) == 2:
        print(save_keys(argv[1]))
    elif argv[:1] == ["authorize"] and len(argv) == 2:
        print(authorize(base64.b64decode(argv[1]).decode().splitlines()))
    elif argv == ["rollback"]:
        try:
            print(rollback())
        except (Refused, OSError, subprocess.SubprocessError) as error:
            print(f"rollback: {error}", file=sys.stderr)
            return 1
    else:
        print("usage: python3 - inspect | preflight <user> <uid> <home> | save-keys <login> | authorize <base64 keys>"
              " | rollback", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
