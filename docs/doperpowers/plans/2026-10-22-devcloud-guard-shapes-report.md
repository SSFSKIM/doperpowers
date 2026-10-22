# devcloud guard: package-tree noise (board ticket 87)

Branch `devcloud-guard-shapes`, off main and rebased onto `2297f647`. Final head `4a75ace9`. PR:
#349. Built by a plan-executor run on astra, at the person's instruction to keep subagents off the
Claude weekly limits. The coordinating session wrote this file from the run's final report, because
the astra role does not write report files.

The run was dispatched for #87 together with #102. #102's Google-token rules had already shipped in
PR #274 (devcloud 0.4.2), but the ticket was never closed. It was closed against that PR and left
out of this change.

## Outcome

This PR changes no runtime behavior. It ships regression tests and a Decision Log entry in the
devcloud spec. Narrowing the detector's rules by content was abandoned:
- broader versions of the narrowing exposed unknown credentials;
- the one safe version left removed 25 of 1,906 matches (1.3%).

The detector and both plugin manifests are byte-identical to main. So devcloud's version doesn't
change and cua's vendored copy needs no resync. The runtime noise problem moves whole to a
follow-up ticket: an exemption based on where a Read's file verifiably comes from.

## Measurements

The census read the installed sources without following symlinks. It covered:
- JavaScript, TypeScript, JSON, Python, text, Markdown and YAML files;
- printable runs of at least 16 characters in the installed Claude Code executable.

| Corpus | Files | Matches | From the generic assignment rule |
| --- | ---: | ---: | ---: |
| Global npm packages | 58,463 | 1,124 | 1,094 |
| gcloud SDK library | 23,324 | 284 | 269 |
| gcloud SDK platform | 2,885 | 197 | 155 |
| Claude Code executable | 1 | 301 | 301 |

These count matches. Not every match is a false positive.

## Why content narrowing failed

Narrowing looked attractive because it would cover both Read and Bash output. Positive-case probes
and the medium review exposed overlaps:
- Numbered dotted references overlap with JWTs and opaque dotted credentials.
- Member expressions overlap with credentials that contain dots and `+`.
- Braces and commas appear in flow YAML and in logs, not only in source code.
- A doubled equals sign can be a valid assignment of a password that starts with `=`.

After one fix wave, only exclusions in a declaration's context were left. They took npm from 1,124
to 1,099 matches and changed neither gcloud tree nor the executable. The coordinating session had
set a stopping rule for this case, and it was applied: every detector change was reverted.

## The path layer, considered and deferred

A Read exemption for install trees that hold no user data would have cleared far more. Two findings
make a path-only version unsafe:
- A global npm package was a symlink into a live development checkout. Matching install roots by
  their path would exempt the person's own source.
- `session.append` scrubs the recorded tool result a second time, without the file's path. An
  exemption applied only to the immediate Read result would be undone there, and carrying the call's
  provenance through that pass is an architectural change.

## The tests kept

All credentials in the tests are synthetic. They lock in:
- quoted literals in env, YAML, JSON, TOML and source files;
- unquoted assignments, JWTs and dotted opaque values;
- flow YAML and comma-separated logs;
- passwords that start with `=`;
- tool results, rows appended on their own, and exact Write restoration;
- protection of stored values, credential-file values, provider-prefixed tokens and generic
  assignments, under both package paths and ordinary project paths.

## Review and CI

- doperpowers:review-code at the medium rung, on the final range: correct, with no material
  findings. The first review found two credential leaks in the narrowing. Restoring the base detector
  removed them.
- `ci-gate --gates devcloud-mods,mods-types` on `4a75ace9` (run 39764851697) passed:
  - devcloud-mods: 101 tests in five files, no failures;
  - the shell checks: 164 restored and run under nine shells, 4,036 kept unrestored, 200 reads, no
    failures;
  - mods-types.

## Friction

Friction tracker #304 has one row from this run. Write once refused to overwrite a file the agent
had already read, and reading it again cleared the refusal. It cost one call and lost no data.

## Residue

Board ticket #124, "devcloud guard: preserve installed-package constants using verified read
provenance". It owns all of #87's runtime noise. Its baseline is the generic-rule matches above:
- npm 1,094;
- gcloud 424, across both trees;
- the executable 301.
