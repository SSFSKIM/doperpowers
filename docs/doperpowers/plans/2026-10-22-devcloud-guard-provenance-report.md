# devcloud guard: installed-package provenance (board ticket 124)

Branch `devcloud-guard-provenance`, rebased onto main's `6d75245c`; final head `647c4b58` before this
report; devcloud 0.10.0. PR: #354. The spec is
`docs/doperpowers/specs/2026-10-22-devcloud-guard-provenance-design.md`. It holds the full record:
Progress, Surprises, the Decision Log and the Outcomes.

Who did what:
- **Design.** An astra agent researched and drafted the spec.
- **Spec review.** One adversarial review, whose decisions the coordinating session settled.
- **Build.** A plan-executor on astra, at the person's instruction to keep subagents off the Claude
  weekly limits.

The coordinating session wrote this file from the run's final report, because the astra role does
not write report files.

## What shipped

The guard can now keep generic token-shaped constants readable when a Read's file is byte-identical
to its published package. The person builds the index explicitly, with
`devcloud guard index --fetch`, from exact-version public artifacts:
- **npm:** the public registry's `dist.integrity` for that name@version;
- **gcloud:** the exact SDK release's public component checksums.

During a Read, a bounded local verifier checks the file's current bytes and the Read's slice against
the index. The verdict reaches the second scrub, at `session.append`, as a module-local receipt that
expires and can be used once. The receipt binds the exact rendered result.

Stored values, credential-file values, provider-shaped tokens and private-key blocks stay redacted
everywhere. Each of these gets today's full detection:
- missing evidence;
- unsupported text;
- an expired deadline;
- a receipt that doesn't match.

An unchanged result keeps the engine's reference, so the pagination notice survives. The index is
refreshed by hand, as the person chose. Hooks never fetch or discover anything.

## Measured result

The earlier census was reproduced exactly. Every generic match sits in a file the index verified
byte for byte.

| Corpus | Files | All matches | Generic matches | Indexed by original bytes | Kept through both scrubs |
|---|---:|---:|---:|---:|---:|
| npm | 58,463 | 1,124 | 1,094 | 1,094 | 1,049 (95.9%) |
| gcloud library | 23,324 | 284 | 269 | 269 | 269 |
| gcloud platform | 2,885 | 197 | 155 | 155 | 155 |
| Total | 84,672 | 1,605 | 1,518 | 1,518 | 1,473 (97.0%) |

All 45 losses are npm, and both causes are deliberate fallbacks:
- 43 sit on lines longer than the 64 KiB slice the verifier supports;
- 2 are in files with control bytes.

These count detector matches. They don't claim that every kept value is harmless.

The author's Mac indexes 88,238 npm files across 1,621 packages and 28,106 gcloud files across 12
components.

## Decisions made during execution

Each is recorded in the spec's Decision Log. None loosens the proof, which is byte equality with a
publicly checksummed artifact.
- **"Detected source checkout" stops at the installation boundary.** A Node version manager installed
  as a git clone had blocked every npm file.
- **gcloud origin is the exact release, the component, the public checksum and member byte
  equality.** The local component version objects aren't part of it, because gcloud stamps the core
  build number into installed snapshots.
- **Ambiguous archive members are excluded one by one.** These are link members, anything beneath
  them, and every duplicated name. An archive that escapes or exceeds its bounds is still rejected
  whole.
- **Accepted losses.** The 45 npm losses are kept as a bounded fallback.

## Verification

- **Focused suites.** The Python index and report suite passed 37 tests, and the two-pass engine-kit
  suite passed 52. Each new behavior was shown red before it went green.
- **Native acceptance, on macOS with engine 2.1.308.** Eight Read cases passed:
  - partial and automatically paginated Reads;
  - the immediate result, the structured record and the appended text;
  - the pagination notice.

  A timed-out or interrupted verifier left no child behind, while the engine kept running.
- **How the probe ran.** Synthetic fixtures, isolated configuration and cache, a scripted loopback
  endpoint, and an OS sandbox that denied every non-loopback connection. No personal session and no
  live inference were used.
- **Not claimed.** Linux native acceptance.
- **CI.** `ci-gate --gates devcloud-mods,mods-types` on `647c4b58` (run 39791975351), and the PR's
  full matrix (run 39792589475), both green.

## Review

- **The spec.** One adversarial round, with three findings:
  - dpkg metadata authorizes locally built packages;
  - the deadline didn't cover the work before verification;
  - the pagination notice.

  The settled decisions are in the spec. dpkg moved out to board ticket 126, and the pre-existing
  notice loss became board ticket 125.
- **The milestones.** Each milestone's review converged.
- **The whole branch.** doperpowers:review-code at the high rung, on `6d75245c..320d46a8`: correct,
  with no material findings. Its scope included the three decisions above.
- **Debt.** Two small findings from M1 are on board ticket 11, the tech-debt tracker:
  - `guard status` raises on index metadata shaped as an array;
  - one test's sentinel isn't present in its fixture.

## Friction

The run updated friction tracker #304 for:
- the native test CLI having no single-file selector;
- the meaning of gcloud's evidence;
- Edit losing its read state;
- GitHub's run and check records disagreeing until they reconciled.

## Residue

- **The cua resync**, to register against the merge commit and devcloud 0.10.0.
  - **What it carries:** the changed detector, handles and guard; the new `secrets-provenance.tsx`,
    `secrets-provenance.py` and `secrets-provenance-corpus.mjs`; their tests; the vendoring headers;
    and indexing instructions for users who have cua alone. The helper resolves relative to its own
    plugin and works without devcloud on PATH.
  - **What it keeps:** cua's marker stand-down and its prompt-section id.
  - **What it tests:** cua alone, and devcloud outside cua, inside cua, and removed or reloaded.
- **Board ticket 125:** a rewritten Read loses the pagination notice. This predates the change.
- **Board ticket 126:** dpkg provenance from the archive's signed chain.
