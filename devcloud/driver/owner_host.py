"""What `devcloud vm owner` runs as root on the host it hands on (EN.G1's
plan, Interfaces §5), streamed there as `python3 -P - <mode> ...`. It uses
the host's own library, from beside the real path of its `devcloud`, so the
host's own parser decides what its descriptor may hold; nothing under boot/
changes for it, and a host made before the verb takes it.

  read                 one JSON line, {"tag", "project", "takes_project"}:
                       the descriptor's DEVCLOUD_CREATOR and
                       DEVCLOUD_CREATOR_PROJECT as the host's parser gives
                       them (null for none), and whether that parser knows
                       the project key. The lifecycle lock is held shared.
  write <tag> <project>
                       under the host's send lock (waited for, `--wait`
                       seconds) and then its lifecycle lock, in the order its
                       lease service takes the two: the first assignment of
                       DEVCLOUD_CREATOR replaced with <tag>, any later one
                       dropped, the line appended when there was none; the
                       same for DEVCLOUD_CREATOR_PROJECT with <project> where
                       the parser knows the key; every other line as it was.
                       The new text is parsed by the host's parser before it
                       is written, with the file's own mode, and read back as
                       `read` reads it, which is printed.

Exit: 0 the answer printed · 1 the descriptor cannot be read, or the new
text would not parse (nothing written) · 2 usage · 3 the host's departure has
started (nothing written) · 4 a notice is being sent, past the wait (nothing
written). Its paths and its wait are options with the host's defaults, so a
test runs this very text against a temporary host."""

import contextlib
import json
import os
import re
import sys

DEFAULTS = {"--devcloud": "/usr/local/bin/devcloud", "--descriptor": "/etc/devcloud/boot.env",
            "--lock": "/run/devcloud/lifecycle.lock", "--send-lock": "/run/devcloud/notices.lock",
            "--status": "/var/lib/devcloud/status.json", "--wait": "20"}
TAG, PROJECT = "DEVCLOUD_CREATOR", "DEVCLOUD_CREATOR_PROJECT"


def _args(argv):
    opts, words = dict(DEFAULTS), []
    while argv:
        word = argv.pop(0)
        if word in DEFAULTS and argv:
            opts[word] = argv.pop(0)
        elif word.startswith("--"):
            return None
        else:
            words.append(word)
    if words[:1] == ["read"] and len(words) == 1 or words[:1] == ["write"] and len(words) == 3:
        return words, opts
    return None


def assign(text, key, value):
    """`text` with the first assignment of `key` replaced by `key="value"`
    (envfile's quoting), any later one dropped, and the line appended when
    there was none; every other line as it was."""
    from devcloudlib import envfile
    line = f"{key}={envfile.quote(value)}\n"
    pattern = re.compile(r"\s*(?:export\s+)?" + re.escape(key) + "=")
    out, done = [], False
    for each in text.splitlines(keepends=True):
        if pattern.match(each):
            if not done:
                out.append(line)
                done = True
            continue
        out.append(each)
    if not done:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(line)
    return "".join(out)


def main(argv):
    parsed = _args(list(argv))
    if parsed is None:
        print("usage: owner_host.py read | write <tag> <project> [--descriptor P] [--lock P] [--send-lock P] "
              "[--status P] [--wait S] [--devcloud P]", file=sys.stderr)
        return 2
    words, opts = parsed
    sys.path.insert(0, os.path.dirname(os.path.realpath(opts["--devcloud"])))
    from devcloudlib import descriptor, lease, proc, status
    allow_http = os.environ.get("DEVCLOUD_ALLOW_HTTP") == "1"    # as the host's CLI sets it
    takes = PROJECT in descriptor.OPTIONAL
    path = opts["--descriptor"]

    def held():
        d = descriptor.load(path, allow_http=allow_http)
        return {"tag": d.creator, "project": getattr(d, "creator_project", None) if takes else None,
                "takes_project": takes}

    try:
        if words[0] == "read":
            with lease.locked(shared=True, path=opts["--lock"]):
                answer = held()
        else:
            tag, project = words[1], words[2]
            with contextlib.ExitStack() as sending:
                # The send lock first, as the lease service takes the two: a notice being sent finishes first.
                try:
                    sending.enter_context(lease.locked(path=opts["--send-lock"], timeout=float(opts["--wait"])))
                except TimeoutError:
                    print("devcloud owner: a notice is being sent; nothing was written", file=sys.stderr)
                    return 4
                with lease.locked(path=opts["--lock"]):
                    if status.departure_started(path=opts["--status"]):
                        print("devcloud owner: the departure has started; nothing was written", file=sys.stderr)
                        return 3
                    with open(path) as f:
                        text = f.read()
                    new = assign(text, TAG, tag)
                    if takes:
                        new = assign(new, PROJECT, project)
                    descriptor.parse(new, allow_http=allow_http)
                    mode = os.stat(path).st_mode & 0o7777
                    proc.write_file(path, new, mode=mode, dir_mode=0o755)
                    answer = held()
    except (OSError, descriptor.DescriptorError) as error:
        print(f"devcloud owner: {error}", file=sys.stderr)
        return 1
    print(json.dumps(answer), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
