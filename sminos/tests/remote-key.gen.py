"""Writes remote-key.json: the vectors of a repository's remote key and the id of
the project it derives (docs/doperpowers/specs/2026-10-19-smns-remote-identity-design.md
§1), which remote_key_parity.py pins sminos to.

Every key and name here is written by hand from §1's rules, never computed by
sminos: the file is the contract the CLI is held to. Only the id is computed, as
§1 defines it — a UUID v5 in the URL namespace of `smns-repo:<org>:<key>` — so a
second producer (a hub, a desk) can be held to the same file.

    python3 remote-key.gen.py > remote-key.json
"""

import json
import uuid

ORG = "ssfskim"
# (url, key, name, why); key "" for a URL that derives no project.
CASES = [
    ("git@github.com:SSFSKIM/MAWS.git", "github.com/ssfskim/maws", "MAWS", "scp-like, the owner's MacBook's spelling"),
    ("https://github.com/ssfskim/maws", "github.com/ssfskim/maws", "maws", "https, the mini's spelling: the same key"),
    ("ssh://git@github.com/ssfskim/maws.git/", "github.com/ssfskim/maws", "maws", "ssh://, a trailing / then .git"),
    ("https://user:token@git.example.org:8443/a/b.git", "git.example.org:8443/a/b", "b",
     "https with userinfo dropped and a non-default port kept"),
    ("https://github.com:443/SSFSKIM/ci-kit", "github.com/ssfskim/ci-kit", "ci-kit", "https's default port dropped"),
    ("http://git.example.org:80/team/tool.git", "git.example.org/team/tool", "tool", "http's default port dropped"),
    ("ssh://git@git.example.org:22/team/tool.git", "git.example.org/team/tool", "tool", "ssh's default port dropped"),
    ("ssh://git@git.example.org:2222/team/tool.git", "git.example.org:2222/team/tool", "tool", "a non-default ssh port kept"),
    ("git://git.example.org/team/tool.git", "git.example.org/team/tool", "tool", "git://"),
    ("git://git.example.org:9418/team/tool", "git.example.org/team/tool", "tool", "git's default port dropped"),
    ("git+ssh://git@git.example.org/team/tool", "git.example.org/team/tool", "tool", "git+ssh://, ssh by another name"),
    ("HTTPS://GitHub.COM//SSFSKIM//Doperpowers.GIT", "github.com/ssfskim/doperpowers", "Doperpowers",
     "mixed case, repeated / and an upper-case .git"),
    ("https://gitlab.com/group/sub/repo.git", "gitlab.com/group/sub/repo", "repo", "a GitLab subgroup kept"),
    ("git@gitlab.com:Group/Sub/Repo", "gitlab.com/group/sub/repo", "Repo", "the same subgroup, scp-like"),
    ("github.com:ssfskim/cua", "github.com/ssfskim/cua", "cua", "scp-like without a user"),
    ("https://github.com/ssfskim/x.git.git", "github.com/ssfskim/x.git", "x.git", "one trailing .git removed, not two"),
    ("ssh://git@[2001:db8::1]:2200/team/tool", "[2001:db8::1]:2200/team/tool", "tool", "an IPv6 host and a port"),
    ("/srv/x.git", "", "", "an absolute path: a local remote"),
    ("../y", "", "", "a relative path: a local remote"),
    ("./sub:dir", "", "", "a / before the first colon: git reads a path"),
    ("file:///srv/x.git", "", "", "file://: a local remote"),
    ("ssh://git@github.com:SSFSKIM/MAWS.git", "", "", "scp-like path behind ssh://: no port, unparsable"),
    ("persistent-https::https://github.com/ssfskim/maws", "", "", "a transport helper's address"),
    ("s3://bucket/repo", "", "", "a scheme git's network transports do not speak"),
    ("https://github.com/", "", "", "no repository path"),
    ("github.com:", "", "", "scp-like with no path"),
    ("", "", "", "no url at all"),
]


def main():
    vectors = []
    for url, key, name, why in CASES:
        v = {"org": ORG, "url": url, "key": key, "name": name, "why": why}
        if key:
            v["hashed"] = "smns-repo:%s:%s" % (ORG, key)
            v["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, v["hashed"]))
        vectors.append(v)
    other = {"org": "org-1", "url": "git@github.com:SSFSKIM/MAWS.git", "key": "github.com/ssfskim/maws", "name": "MAWS",
             "why": "the same remote in another org: another project"}
    other["hashed"] = "smns-repo:org-1:github.com/ssfskim/maws"
    other["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, other["hashed"]))
    vectors.append(other)
    print(json.dumps({"about": "A repository's remote key and the id of the project it derives (the sminos remote "
                               "identity design, §1), written by remote-key.gen.py beside this file; see its docstring.",
                      "namespace": str(uuid.NAMESPACE_URL), "vectors": vectors}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
