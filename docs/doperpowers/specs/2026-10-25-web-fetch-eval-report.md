# Web fetch eval report — 20261025T114934Z-final

Overall: **PASS** (192 runs of 192 expected; A = WebFetch only, B = mcp__web__fetch only; sol at xhigh; graded by opus).

## Pass criteria

- **PASS 1** — B not worse overall: mean d +0.000, 90% interval [+0.000, +0.000] over 24 tasks (10,000 resamples, seed 20261025); passes at a lower bound of -0.05 or above.
- **PASS 2** — category tripwire (B at most one correct run fewer than A): exact-detail 12/12, table 12/12, code 12/12, image 12/12, js 12/12, pdf 12/12, gist 12/12, synthesis 12/12 (A/B correct runs).
- **PASS 3** — no B tool error the tool caused: 0 found
- **PASS 4** — gist median main-model tokens: B 10,739 vs A 16,016 = 0.67x (at most 1.5x).

## By category

| Category | Config | Correct | Partial | Wrong | Median tokens | Median cost (USD) | Median duration (s) | Fetch calls (mean) |
|---|---|---|---|---|---|---|---|---|
| exact-detail | A | 12 | 0 | 0 | 10,399 | 0.040 | 15 | 1.3 |
| exact-detail | B | 12 | 0 | 0 | 10,664 | 0.033 | 15 | 1.0 |
| table | A | 12 | 0 | 0 | 10,831 | 0.040 | 16 | 1.3 |
| table | B | 12 | 0 | 0 | 11,620 | 0.035 | 15 | 1.0 |
| code | A | 12 | 0 | 0 | 10,573 | 0.039 | 21 | 1.3 |
| code | B | 12 | 0 | 0 | 16,005 | 0.039 | 16 | 1.3 |
| image | A | 12 | 0 | 0 | 23,326 | 0.053 | 29 | 2.0 |
| image | B | 12 | 0 | 0 | 19,204 | 0.049 | 12 | 1.0 |
| js | A | 12 | 0 | 0 | 18,037 | 0.049 | 29 | 5.3 |
| js | B | 12 | 0 | 0 | 19,378 | 0.045 | 31 | 3.8 |
| pdf | A | 12 | 0 | 0 | 66,639 | 0.174 | 39 | 15.9 |
| pdf | B | 12 | 0 | 0 | 26,254 | 0.058 | 23 | 1.1 |
| gist | A | 12 | 0 | 0 | 16,016 | 0.069 | 53 | 1.9 |
| gist | B | 12 | 0 | 0 | 10,739 | 0.041 | 27 | 1.0 |
| synthesis | A | 12 | 0 | 0 | 10,584 | 0.048 | 20 | 1.3 |
| synthesis | B | 12 | 0 | 0 | 16,260 | 0.031 | 20 | 1.0 |

Tokens are the main model's input, output, cache read and cache creation together; "n/a" counts runs whose usage is unavailable (killed at the limit before a result line). Cost is what the run output reports (sol is priced by Claude Code as an unknown model, and B's summary calls are outside it; see the usage notes in the design).

## Runs not fully correct

- none

## Development rounds

### Round 1 (20261025T104937Z-dev)

- **PASS 1** — B not worse overall: mean d +0.000, 90% interval [+0.000, +0.000] over 16 tasks (10,000 resamples, seed 20261025); passes at a lower bound of -0.05 or above.
- **PASS 2** — category tripwire (B at most one correct run fewer than A): exact-detail 4/4, table 4/4, code 4/4, image 4/4, js 4/4, pdf 4/4, gist 4/4, synthesis 4/4 (A/B correct runs).
- **PASS 3** — no B tool error the tool caused: 0 found
- **PASS 4** — gist median main-model tokens: B 9,983 vs A 14,669 = 0.68x (at most 1.5x).

### Round 2 (20261025T110553Z-dev)

- **PASS 1** — B not worse overall: mean d +0.000, 90% interval [+0.000, +0.000] over 16 tasks (10,000 resamples, seed 20261025); passes at a lower bound of -0.05 or above.
- **PASS 2** — category tripwire (B at most one correct run fewer than A): exact-detail 4/4, table 4/4, code 4/4, image 4/4, js 4/4, pdf 4/4, gist 4/4, synthesis 4/4 (A/B correct runs).
- **PASS 3** — no B tool error the tool caused: 0 found
- **PASS 4** — gist median main-model tokens: B 9,950 vs A 11,960 = 0.83x (at most 1.5x).

### Round 3 (20261025T113040Z-dev)

- **PASS 1** — B not worse overall: mean d +0.000, 90% interval [+0.000, +0.000] over 16 tasks (10,000 resamples, seed 20261025); passes at a lower bound of -0.05 or above.
- **PASS 2** — category tripwire (B at most one correct run fewer than A): exact-detail 4/4, table 4/4, code 4/4, image 4/4, js 4/4, pdf 4/4, gist 4/4, synthesis 4/4 (A/B correct runs).
- **PASS 3** — no B tool error the tool caused: 0 found
- **PASS 4** — gist median main-model tokens: B 10,009 vs A 12,894 = 0.78x (at most 1.5x).

