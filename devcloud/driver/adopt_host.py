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

The backup lives outside /var/lib/devcloud, whose existence setup.sh
refuses."""

import base64
import json
import os
import pathlib
import pwd
import sys

ADOPT_DIR = "/var/lib/devcloud-adopt"
BOOT_ENV = "/etc/devcloud/boot.env"


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


def main(argv):
    if argv[:1] == ["inspect"]:
        print(json.dumps(inspect()))
    elif argv[:1] == ["preflight"] and len(argv) == 4 and argv[2].isdigit():
        print(json.dumps({"problems": preflight(*argv[1:])}))
    elif argv[:1] == ["save-keys"] and len(argv) == 2:
        print(save_keys(argv[1]))
    elif argv[:1] == ["authorize"] and len(argv) == 2:
        print(authorize(base64.b64decode(argv[1]).decode().splitlines()))
    else:
        print("usage: python3 - inspect | preflight <user> <uid> <home> | save-keys <login> | authorize <base64 keys>",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
