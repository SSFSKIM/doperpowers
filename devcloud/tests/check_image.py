#!/usr/bin/env python3
"""Acceptance 6: no credential and no per-host input is baked into a devcloud
image. Three parts:

  (a) known values — none of the given values appears anywhere in the image's
      filesystem or `docker history`, in any spelling the guard scrubs. The
      values go to the guard's own matcher in-process (tests/scan-secrets.ts)
      and are never printed;
  (b) credential files — none of the files the guard reads credentials from
      exists under any home in the image, nor the secret store, nor
      /etc/devcloud/boot.env;
  (c) patterns — the guard's detector finds nothing outside package-owned
      trees: files a Debian package installed that `dpkg --verify` finds
      unchanged, npm's node_modules, and the Claude Code and gcloud install
      trees, where vendored code and fixtures match token shapes by the
      thousand.

    python3 devcloud/tests/check_image.py <image> --home <user home> \\
        [--values <json file>|-] [--store <secret store dir>]...

Values come as a JSON array of strings or an object of label -> value, from a
file or stdin (`-`), and from secret stores (`--store`, labelled by key); M2's
tests pass made-up ones, M5 the person's own. Output names parts, paths and
labels only. Exit 0 clean, 1 when a part found something, 2 when the check
itself could not run (an export, a scan that failed or read nothing).
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCANNER = ["bun", str(HERE / "scan-secrets.ts")]


class CheckError(Exception):
    """The check could not run, so it proves nothing."""


def export(image, root):
    """The image's filesystem, as a container of it holds it before any boot,
    unpacked into `root` and made readable to this user."""
    exporter = subprocess.Popen(["docker", "run", "--rm", "--entrypoint", "tar", image, "-C", "/", "-cf", "-",
                                 "--exclude=./proc", "--exclude=./sys", "--exclude=./dev", "."],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    extractor = subprocess.run(["tar", "-xf", "-", "-C", str(root), "--no-same-owner", "--no-same-permissions"],
                               stdin=exporter.stdout, capture_output=True)
    exporter.stdout.close()
    exported_err = exporter.stderr.read()
    if exporter.wait() != 0:
        raise CheckError(f"exporting {image} failed: {exported_err.decode(errors='replace')[-400:]}")
    if extractor.returncode != 0:
        raise CheckError(f"unpacking {image} failed: {extractor.stderr.decode(errors='replace')[-400:]}")
    subprocess.run(["chmod", "-R", "u+rwX", str(root)], check=True)
    if not (root / "etc/passwd").is_file():
        raise CheckError(f"the export of {image} holds no /etc/passwd")


def scanner_output(args, values_json, scanner=None):
    """Runs the scanner; its findings, or CheckError when it failed or read nothing."""
    result = subprocess.run((scanner or SCANNER) + args, input=values_json.encode(), capture_output=True)
    err = result.stderr.decode(errors="replace")
    if result.returncode != 0:
        raise CheckError(f"the scanner exited {result.returncode}: {err.strip()[-600:]}")
    scanned = re.search(r"scanned (\d+) files", err)
    if not scanned or int(scanned.group(1)) == 0:
        raise CheckError(f"the scanner read nothing: {err.strip()[-300:]}")
    return result.stdout.decode().splitlines()


# `dpkg --verify` lines: nine check characters, an optional `c` (a conffile), the path.
VERIFY_LINE = re.compile(r"^[?.0-9A-Za-z]{9} +(?:c +)?(/.*)$")
NOT_OWNED = re.compile(r"^dpkg-query: no path found matching pattern ")
BATCH = 300


def _in(container, argv):
    return subprocess.run(["docker", "exec", container, *argv], capture_output=True, text=True, timeout=900)


def _package_pristine(image, paths):
    """Of `paths`, those a Debian package installed and `dpkg --verify` finds
    unchanged. Each tool runs on its own and its result is read: a listing of
    differences or of unowned paths is an answer; any other failure is
    CheckError, never an empty answer."""
    if not paths:
        return set()
    container = subprocess.run(["docker", "run", "-d", "--rm", "--entrypoint", "sleep", image, "infinity"],
                               capture_output=True, text=True)
    if container.returncode != 0:
        raise CheckError(f"cannot start {image} for dpkg: {container.stderr.strip()[-300:]}")
    name = container.stdout.strip()
    try:
        verify = _in(name, ["dpkg", "--verify"])
        if verify.returncode not in (0, 1):
            raise CheckError(f"dpkg --verify exited {verify.returncode}: {verify.stderr.strip()[-300:]}")
        lines = verify.stdout.splitlines()
        if verify.returncode == 1 and not lines:
            raise CheckError(f"dpkg --verify exited 1 without listing a difference: {verify.stderr.strip()[-300:]}")
        modified = set()
        for line in lines:
            match = VERIFY_LINE.match(line)
            if not match:
                raise CheckError(f"dpkg --verify printed a line it should not: {line[:200]!r}")
            modified.add(match.group(1))
        owned = set()
        wanted = sorted(paths)
        for k in range(0, len(wanted), BATCH):
            batch = wanted[k:k + BATCH]
            # A path is a pattern to dpkg-query: its wildcard characters are escaped.
            query = _in(name, ["dpkg-query", "-S", *(re.sub(r"([*?\[\\])", r"\\\1", path) for path in batch)])
            stray = [line for line in query.stderr.splitlines() if line and not NOT_OWNED.match(line)]
            if query.returncode not in (0, 1) or stray or (query.returncode == 1 and not query.stderr.strip()):
                raise CheckError(f"dpkg-query -S exited {query.returncode}: {(stray or [query.stderr])[0][:300]}")
            for line in query.stdout.splitlines():
                if line.startswith(("diversion by ", "local diversion ")):
                    continue
                packages, sep, path = line.partition(": /")
                if not sep:
                    raise CheckError(f"dpkg-query -S printed a line it should not: {line[:200]!r}")
                owned.add("/" + path)
        return (owned - modified) & set(paths)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def check(image, home, values=None, stores=(), scanner=None):
    """Runs the three parts; returns {"known", "credential", "pattern"}
    findings and the count of allowed pattern detections."""
    values_json = json.dumps(values if values is not None else [])
    work = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-image-"))
    try:
        root = work / "rootfs"
        root.mkdir()
        export(image, root)
        history = subprocess.run(["docker", "history", "--no-trunc", "--format", "{{.CreatedBy}}", image],
                                 capture_output=True, text=True)
        if history.returncode != 0 or not history.stdout.strip():
            raise CheckError(f"docker history of {image} failed")
        (work / "history").mkdir()
        (work / "history/docker-history").write_text(history.stdout)
        store_args = [a for store in stores for a in ("--store", str(store))]
        lines = scanner_output(["scan", str(root), "--values", "-", *store_args], values_json, scanner)
        lines += scanner_output(["scan", str(work / "history"), "--values", "-", *store_args], values_json, scanner)
        credential = [line.split("\t")[1] for line in
                      scanner_output(["credential-files", str(root)], "", scanner)]
        if (root / "etc/devcloud/boot.env").exists():
            credential.append("/etc/devcloud/boot.env")

        def where(path):
            if path.startswith(str(root)):
                return path[len(str(root)):]
            return "docker history" if path.startswith(str(work / "history")) else path
        known = sorted({f"{where(f[1])}\t{f[2]}" for f in (line.split("\t") for line in lines) if f[0] == "known"})
        patterns = [(where(f[1]), f[2]) for f in (line.split("\t") for line in lines) if f[0] == "pattern"]
        trees = ("/usr/lib/google-cloud-sdk/", f"{home.rstrip('/')}/.local/share/claude/")
        loose = {p for p, _ in patterns if "/node_modules/" not in p and not p.startswith(trees)}
        pristine = _package_pristine(image, {p for p in loose if p.startswith("/")})
        flagged = sorted({f"{p}\t{kind}" for p, kind in patterns if p in loose and p not in pristine})
        allowed = sum(1 for p, _ in patterns if p not in loose or p in pristine)
        return {"known": known, "credential": sorted(credential), "pattern": flagged, "allowed": allowed}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("image")
    parser.add_argument("--home", required=True, help="the image user's home (DEVCLOUD_HOME)")
    parser.add_argument("--values", help="a JSON file of values, or - for stdin")
    parser.add_argument("--store", action="append", default=[], help="a secret store directory")
    args = parser.parse_args(argv)
    values = None
    if args.values:
        values = json.load(sys.stdin if args.values == "-" else open(args.values))
    try:
        found = check(args.image, args.home, values, args.store)
    except CheckError as error:
        print(f"the check could not run: {error}")
        return 2
    print(f"(a) known values: {len(found['known'])} found")
    for line in found["known"]:
        print(f"    {line}")
    print(f"(b) credential files and boot.env: {len(found['credential'])} found")
    for line in found["credential"]:
        print(f"    {line}")
    print(f"(c) pattern detections outside package-owned trees: {len(found['pattern'])} "
          f"({found['allowed']} inside them)")
    for line in found["pattern"][:100]:
        print(f"    {line}")
    return 1 if found["known"] or found["credential"] or found["pattern"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
