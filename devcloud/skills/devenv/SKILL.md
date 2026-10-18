---
name: devenv
description: Use when a repository needs a devenv/ directory — asked to set up a repository's environment for devcloud hosts or the person's Macs, to make it work with `devenv up`, or when devenv reports "no devenv/" for it — or when an existing devenv/ needs a review.
---

# Writing a repository's devenv/

A repository describes its own environment in `devenv/` at its root. The
person's `devenv` runner reads it on their Macs and on devcloud hosts
(Ubuntu 24.04), so one directory has to work on both.

## The contract

- **`setup.sh`** (required) installs the dependencies. The runner runs it
  with bash from the repository root, as the user, with `env`'s values and
  secrets set. It runs again whenever the root's HEAD, anything under
  `devenv/`, or a file named by a leading `# devenv-inputs: <glob> ...` line
  (globs from the repository root) changes — so it must be safe to re-run,
  and the header names the lockfiles it installs from. One script for both
  platforms: pick the package manager by `uname -s` (Homebrew on macOS,
  `sudo apt-get` on Ubuntu — the host user has passwordless sudo) and install
  a system tool only when `command -v` lacks it. Hosts already carry git,
  git-lfs, build tools, Python 3 with venv, uv, Node LTS with npm, jq, tmux,
  zsh, gh, the gcloud CLI and the Docker client — but no Docker daemon, so a
  service the repository runs in a container (a compose database) needs
  another way to run there.
- **`start.sh`** (optional), only when the repository runs long-lived
  services: runs them in the foreground. `devenv start` keeps it in tmux
  session `<name>`; `devenv stop` ends its process group.
- **`validate.sh`** (optional): the quickest real check that the environment
  works — a lint, a fast test subset, a build — seconds, not the full suite.
- **`env`** (optional): `KEY=value` lines and `secret:KEY=<Secret Manager id>`
  lines. Values are literal — no `$VAR` expansion; one pair of surrounding
  quotes is dropped. Names starting `DEVENV_` are the runner's.

Install from the lockfile without rewriting it (`npm ci`,
`pnpm install --frozen-lockfile`, `uv sync --frozen`, `bundle install` with a
frozen config): a lockfile the install rewrites is an input that changed, so
every `devenv up` would install again, and a host should get what CI tested.

## Where it comes from

Write from what the repository already says, in this order — an install path
something already runs and tests beats one reconstructed from prose:

1. `.github/ci-kit.yml`, where the repository has adopted ci-kit: its `setup`
   and its gates' commands.
2. Otherwise its CI workflows: install steps, tool versions, service
   containers.
3. Manifests and lockfiles: they name the package manager and become the
   `devenv-inputs`.
4. Compose files: the services and their environment.
5. Bootstrap scripts and Makefile targets.
6. The README's setup section.

A value the repository needs that is a credential (an API key in
`.env.example`, a token a README says to ask someone for) becomes a `secret:`
line naming its Secret Manager id: the ids the person has are listed by
`gcloud secrets list --format='value(name)'`, which prints names only. Ask the
person for an id you cannot match. Never read or print a secret's value.
Non-secret defaults become plain lines.

## Prove it

Commit `devenv/` on a branch, then prove it against a fresh clone of that
branch, never the person's own checkout or registry:

    G=$(mktemp -d); export DEVENV_GH="$G" DEVENV_REGISTRY="$G/envs"
    devenv up <name> --url "$(git rev-parse --show-toplevel)" --ref <branch>
    devenv up <name> --url "$(git rev-parse --show-toplevel)" --ref <branch>   # "setup skipped (unchanged)"
    devenv validate <name>

A second run that sets up again means `setup.sh` changes one of its own
inputs; find which and stop it. Prove Linux in a devcloud sandbox container
when one is available (a descriptor naming the repository at the branch,
then `devcloud status`); otherwise say Linux is unproven. Without the
runner, run `setup.sh` twice and `validate.sh` in a fresh clone.

## An existing devenv/

Review it against the same sources and the contract, and fix what is wrong
or missing rather than rewriting what works.

Report the files, what each proof printed, and the secret ids you asked for.
