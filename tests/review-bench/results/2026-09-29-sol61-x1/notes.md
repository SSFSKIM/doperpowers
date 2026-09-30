# sol61-x1: the review-code lane on GPT-6.1 Sol, low and medium (2026-09-29)

Engine: `skills/review-code/workflows/code-review.js` (byte-identical to
doperpowers `279842f9`, 7.128.0 "re-pin to GPT-6.1 Sol") on the harness's
native Workflow tool, run from an interactive session against materialized
scratch repos (`repo` arg, isolation off). `sol` now resolves through the
local gateway to GPT-6.1 Sol. Two single-reviewer rungs scored: **low** (one
reviewer, sol/high) and **medium** (one reviewer, sol/xhigh). Both use the
`doperpowers:reviewer-medium` agent body with the ladder's model and effort
overriding it per call. All ten runs ran concurrently on one Codex account.

Baseline: `2026-07-26-c2-codex-r3` (single codex, sol/xhigh): 17/17, FP 0,
promoted 3/3. Previous native run: `2026-09-09-native-x1` medium (one
reviewer, sol/xhigh, where sol was then GPT-5.6 Sol).

## Result

| | seeded | FP | promoted | full 20 | wall, 5 cases |
|---|---|---|---|---|---|
| codex baseline (single, 2026-07-26) | 17/17 | 0 | 3/3 | 20/20 | — |
| native medium, GPT-5.6 Sol xhigh (2026-09-09) | 17/17 | 0 | 3/3 | 20/20 | 2533 s* |
| **native low, GPT-6.1 Sol high** | **17/17** | **0** | **3/3** | **20/20** | **522 s** |
| **native medium, GPT-6.1 Sol xhigh** | **17/17** | **0** | **3/3** | **20/20** | **851 s** |

\* The 09-09 figures are `run-case.sh` wall time around a headless session
(case4: interactive), so they include session start. Today's are the
workflow's own duration. Treat the comparison as rough.

| secs | case1 | case2 | case3 | case4 | case5 |
|---|---|---|---|---|---|
| low | 92 | 93 | 79 | 128 | 130 |
| medium | 132 | 114 | 89 | 229 | 287 |
| 09-09 medium | 482 | 465 | 480 | 671 | 435 |

**low: PASS.** It equals the baseline on every axis. Its 20 findings are
exactly the 20 truth entries: every finding matches one entry, and no entry
is matched twice.

**medium: PASS.** It equals the baseline and the 09-09 native medium on every
axis. It also returns exactly the truth set.

Neither level flagged a bait. Several explanations say the reviewer checked a
bait and found it behaved as documented: case1's numeric-value tightening at
both levels, and case3-medium's empty-document export. The seeded set is now
saturated for the single-reviewer rungs. The codex baseline, both native
mediums, and today's low all score 20/20 with 0 FP, so X1's seeded cases can
no longer rank low against medium. Separating them would take the real-PR
cases or harder seeded ones. What still differs is evidence and severity, not
recall (see Mechanics).

## Adjudication

Each finding's truth entry is recorded in `scores.json`, under `mapping`. Four
L2 findings are anchored at the producer end of the broken contract, while
truth names the consumer file:

- case2-b2 at `rates.ts:50-51` (`baseRateFor`), with truth at `api.ts`
- case3-b2 at `store.py:122`, with truth at `app.py`
- case4-b4 at `snapshot.sh:114`, with truth at `prune.sh`
- case5-b4 at `cache.py:129`, with truth at `jobqueue.py`

These anchors appear at both levels. In each case the comment names the
consumer and describes the truth mechanism: `quickEstimate` formatting cents
as dollars, `handle_put_document` using the row count as the revision and
ETag, prune.sh's three-field read, and `cache_hit_rate()` reading the old
counter names. Under the README rule (mechanism is the criterion; file
overlap is only evidence), all four count as matches. The 09-09 medium was
credited with the same `store.py:122` and `snapshot.sh:114` anchors. A
file-matching scorer would have given 13/17 at both levels.

Promoted entries (case4-u1, case4-u2, case5-u1) are counted the same way as
09-09. They form a separate promoted recall (3 entries) outside the 17-entry
seeded denominator that the bar gates on. A finding that matches one is never
an FP. Seeded and promoted together give the "full 20" figure.

## Unseeded candidates (excluded from FP per the X1 rule)

None were raised at either level. None of the unseeded candidates adjudicated
in earlier runs came back:

- case1: `tenants.py` `max_value`/NaN validation; the explicit-null tenant entry
- case3: the page clamp at 10,000
- case4: the prune label truncated at the first hyphen; a `BACKUP_REMOTE`
  value beginning with `-`; `find` errors lost inside a process substitution
- case5: the keylock refcount leak on `CancelledError`

Some findings describe extra consequences of a matched mechanism. I ruled
these part of that finding's truth entry, not separate candidates:

- case1-b2: cumulative per-batch statistics
- case3-b3: the 200-entry cap returning 201
- case4-b3: an ordinary apostrophe breaking replication
- case4-u1 (low): a retry truncating an existing replica
- case5-b3: nested acquisition for a different key deadlocking, and callers
  blocked on the guard before their timeout applies

Under the strictest reading (every non-truth finding an FP), both levels still
score 0.

## Mechanics

- **case4-low's blocked checks did not change its findings.** Its reviewer
  made one end-to-end reproduction attempt: a bash script with a fake `ssh`
  on `PATH`, an injection proof that `touch`es a marker, and `rm -rf` of its
  temp dir. The Claude Code auto-mode classifier denied it ("Blocked by fast
  classifier"). The reviewer did not retry and concluded from the patch and
  its callers.
  - It still reported the same six mechanisms as medium: b1–b4, u1 and u2.
  - The only differences are u1's severity (P2 against medium's P1) and that
    medium's comments cite reproduced evidence, such as "a simulated
    interrupted transfer left a 16-byte .tar.gz".
  - Medium's reproduction took the same fake-`ssh` approach, wrapped in a
    Python harness with `TemporaryDirectory` cleanup, and was allowed. The
    classifier judges each command, so similar probes can go either way.
  - This was the only denial in the ten runs; the other nine executed all of
    their checks.
- **Severity (not scored).** Low rated case4-u1 and case5-b1 P2, where medium
  rated them P1. Every other finding has the same priority at both levels.
- **Speed.** Low took about 0.6× medium's wall time: 522 s against 851 s
  summed. This held even with all ten runs sharing one Codex account.
- **Gateway.** There were no stream errors or retries: every reviewer finished
  on attempt 1 with coverage `ok`.
- **Working trees.** All five scratch repos had a clean `git status` after
  the runs, so reviewers left the working trees unchanged.
- **Files.** Each findings file carries `secs`, `tokens` (the workflow's
  `totalTokens`), `run_id` (see `runs.tsv`) and the workflow `logs`.

## Scratch pins

The repos are ephemeral, under `/var/folders/c1/l4z5k02n2779byvnymzxsvth0000gn/T/`.
The base branch is `main` for every case.

| case | repo | baseCommit | headCommit |
|---|---|---|---|
| case1 | `review-bench.5sc0Kh` | `7c4234aaa1baf85aaa9070227be6de730dcec2a0` | `67d2f892214c86164de1edcd40a28e41c5e1a34d` |
| case2 | `review-bench.3PJcpH` | `73081d16298a40b05e555df23fa5b75446afe32e` | `9300bae2b691b9c6c2dc1e8575930779b8ba3e1d` |
| case3 | `review-bench.qKvI0q` | `7800cf9a62034a9c8789c792e4b8ea997f1c278a` | `1eb59af12446dc7ba99327b357a834f591d0e6d3` |
| case4 | `review-bench.Zetzaa` | `ba7b110d89355ff143e8d511757c9dde0ac63c41` | `8ebfbd6d186cd24ea425a1912d76964ea4556823` |
| case5 | `review-bench.2BWNAk` | `f1048f10e79d786759ccbcc1567273d391608f04` | `bbf7c0f8fabc652c8273baf5847f0c8108bec54b` |
