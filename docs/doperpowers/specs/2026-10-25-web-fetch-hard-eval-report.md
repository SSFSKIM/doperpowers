# Web fetch eval report — the hard set (board #132)

The first suite showed that `mcp__web__fetch` (B) is not worse than
`WebFetch` (A). Every run was correct either way, so it could not show B
better. The hard set was built to show either. Its final round ran on web
0.3.0 (`5c468e73`): 24 final tasks × A and B × 4 runs, `sol` at `xhigh` as
runner and grader. Third-party readers were denied in both configurations.

**Result: B answered better, with confidence.** The mean per-task
difference in correct runs is d = +0.115, with a 90% interval of
[+0.031, +0.208] over the 24 tasks. B was ahead on 5 tasks, level on 19,
and behind on none. It did this at a third of A's cost and time.

The round reads **NOT PASSED** as a gate on one count: criterion 3, a B
tool error. The clipper's 30 s download limit ran out once on a 17.6 MB PDF.
B refetched and answered; see "Criterion 3" below.

## Beside the first suite

| Suite (final runs) | A correct | B correct | d, 90% interval | Median cost A / B | Median time A / B | Fetch calls A / B (mean) |
|---|---|---|---|---|---|---|
| First suite (`tasks.json`, 24 tasks) | 96/96 | 96/96 | +0.000 [+0.000, +0.000] | $0.049 / $0.041 | 29 s / 20 s | 3.8 / 1.4 |
| Hard set (`tasks-hard.json`, 24 tasks) | 81/96 | 92/96 | +0.115 [+0.031, +0.208] | $0.189 / $0.061 | 93 s / 32 s | 10.8 / 2.5 |

- Costs are the runs' reported USD. In total, A spent $31.94 against B's
  $8.61. B's summaries and the search tool are outside those figures.
- A timed out twice at the 10-minute limit; B never did.
- The first suite was graded by opus and the hard set by sol at xhigh. On
  the 43 screening runs both graded, sol agreed with opus on 42 verdicts.

## Each task's d, and the mechanism behind it

The 5 tasks where B was ahead:

| Task | Mechanism | A | B | d | Why A lost |
|---|---|---|---|---|---|
| search-h1 | over-10mb | 0/4 | 4/4 | +1.00 | NASA's FY2025 budget justification is a 30 MB PDF. WebFetch refuses anything over 10 MB, and A found no other edition. In Phase 1 it got in only by rasterizing pages through a third-party image proxy, now denied. |
| long-pdf-h1 | over-10mb | 1/4 | 4/4 | +0.75 | The IEA's World Energy Outlook 2024 is 17.6 MB, over the same cap. A's one success found a SlideShare re-upload of the report and read the table's page there as an image. |
| search-h7 | over-10mb | 2/4 | 4/4 | +0.50 | The Bank of Korea's 2024 annual report is 11.5 MB, behind a signed CDN redirect. A's two failures were the 10-minute limit, reached while hunting for a way in. |
| long-pdf-h6 | pdf-table-reading | 3/4, 1 partial | 4/4 | +0.25 | A dense 9-column table read from a page image: A read 1987's 39.4 as 33.4. B reads the PDF's text. |
| long-pdf-h7 | pdf-table-reading | 3/4, 1 partial | 4/4 | +0.25 | A 12-year-wide table read from a page image: A gave 2,800, a neighbouring cell, for 2028's 1,483. |

The other 19 tasks are level. Each task's d is in the round's by-task table
below, and the mean d per mechanism in its by-mechanism table.

## What the set can show, and what it cannot

It can show:

- **B answers correctly where WebFetch cannot reach the document.** All
  three tasks whose PDF is over 10 MB favour B (d +0.75 on average).
- **B reads dense tables more faithfully than WebFetch's page images.**
  Both table-reading tasks favour B.
- **B was never worse than A** on any of the 24 tasks.
- **B costs much less on hard pages.** A works around WebFetch's limits
  with other editions, parallel `offset` calls and many retries: 10.8
  fetch calls a run against 2.5, and three times the time and cost.
- **A future regression in B on these mechanisms would show.** The PDF
  text layer, large downloads, and the outline over long pages are
  examples.

It cannot show:

- **That B reads ordinary pages better.** The set was screened to tasks
  where A can fail, so +0.115 is the gap on that kind of task, not on
  everyday use. The interval resamples these 24 tasks only.
- **A broad fidelity win.** Most of d is reach: 3 of the 5 tasks are the
  10 MB cap, a hard limit of WebFetch rather than a reading error. Fidelity
  rests on 2 tasks, each one partial run out of 4.
- **That WebFetch's other limits hurt answers.** On the quote rule, the
  100k-character windows, the 1 MB HTML cut, hidden images and PDF
  navigation, A matched B on every task. `sol` at `xhigh` routes around
  them, so they cost A time and tokens, not answers. A less resourceful
  runner might do worse; this round did not test one.
- **The result with third-party readers allowed.** Agents could otherwise
  use services such as `r.jina.ai`. With them allowed in screening, A
  passed search-h1 once and image-h2 twice, so the gap would be narrower.
- **Anything from image-h2.** Both configurations failed it 4/4, so it
  carries no signal until B is fixed (next section).

## B's own failures

- **image-h2: Defuddle drops the page's benchmark charts.** Tom's
  Hardware's RTX 5070 page comes back as 318 words with 0 images. The
  roughly 70 charts, which share one alt text in a gallery, are not taken
  as content, so B never sees the chart, just as A never does (the
  article starts past WebFetch's 1 MB HTML cut). This is the weakness the
  code diagnosis predicted for content outside the article.
- **Criterion 3: the 30 s download limit.** In long-pdf-h1 B rep 2, the
  clipper's fetch timed out at 30 s on the 17.6 MB IEA PDF, on a machine
  at load 120–250. The second listed error is the same failure replayed
  by the clipper's negative cache ("Not fetched again: this URL failed 4 s
  ago") when the runner asked again.
  - The runner then passed `refresh: true` and answered correctly.
  - By the design's rule, a timeout of the clipper's own is the tool's
    error, so the gate reads NOT PASSED.
  - The finding: a fixed 30 s limit is tight for documents this large.

## Notes on the run

- **One A run was retried.** Its first attempt ended with the gateway's
  `400 Codex tool results cannot contain PDF/document files`: the runner
  had `Read` a whole PDF without `pages`, and `sol` through the gateway
  cannot take a document block. Per the design, a run that fails outside
  the agent is retried on resume.
- **Spend.** $41.65 reported (runner $40.55, grader $1.10). Outside that
  figure, at list prices, about $13: B's summaries (1.5M haiku input
  tokens) and the search tool (6.0M haiku input tokens, 428 web searches).
  About $55 in all, under the $70 approved; the projection at the quarter
  mark was $34.
- **The round's record** is `web/evals/runs/hard-final` (ignored). How the
  set was screened, and every change on the way, is in
  `docs/doperpowers/specs/2026-10-25-web-fetch-hard-screening.md`.

## The round, as report.py renders it

Overall: **NOT PASSED** (192 runs of 192 expected; A = WebFetch only, B = mcp__web__fetch only; sol at xhigh; graded by sol at xhigh).

### Pass criteria

- **PASS 1** — B not worse overall: mean d +0.115, 90% interval [+0.031, +0.208] over 24 tasks (10,000 resamples, seed 20261025); passes at a lower bound of -0.05 or above. B better with confidence (lower bound above 0): yes.
- **PASS 2** — category tripwire (B at most one correct run fewer than A): image 16/16, verbatim 20/20, long-page 20/20, long-pdf 15/20, search 10/16 (A/B correct runs).
- **FAIL 3** — no B tool error the tool caused: 2 found
  - long-pdf-h1 rep 2: fetch failed: https://iea.blob.core.windows.net/assets/140a0470-5b90-4922-a0e9-838b3ac6918c/WorldEnergyOutlook2024.pdf: timed out after 30 s
  - long-pdf-h1 rep 2: fetch failed: https://iea.blob.core.windows.net/assets/140a0470-5b90-4922-a0e9-838b3ac6918c/WorldEnergyOutlook2024.pdf: timed out after 30 s / Not fetched again: this URL failed 4 s ago (refresh: true tries again).
- **N/A 4** — gist tokens: the set has no gist tasks.

### By category

| Category | Config | Correct | Partial | Wrong | Median tokens | Median cost (USD) | Median duration (s) | Fetch calls (mean) |
|---|---|---|---|---|---|---|---|---|
| image | A | 16 | 0 | 4 | 39,766 | 0.113 | 37 | 6.3 |
| image | B | 16 | 0 | 4 | 21,264 | 0.041 | 21 | 6.6 |
| verbatim | A | 20 | 0 | 0 | 40,246 | 0.125 | 100 | 8.5 |
| verbatim | B | 20 | 0 | 0 | 15,980 | 0.050 | 18 | 1.2 |
| long-page | A | 20 | 0 | 0 | 61,769 | 0.215 | 108 | 15.2 |
| long-page | B | 20 | 0 | 0 | 29,222 | 0.065 | 36 | 1.2 |
| long-pdf | A | 15 | 2 | 3 | 99,328 | 0.272 | 62 | 11.4 |
| long-pdf | B | 20 | 0 | 0 | 45,258 | 0.085 | 41 | 1.2 |
| search | A | 10 | 0 | 6 | 332,840 | 0.902 | 384 | 12.6 |
| search | B | 16 | 0 | 0 | 37,575 | 0.088 | 52 | 2.3 |

Tokens are the main model's input, output, cache read and cache creation together; "n/a" counts runs whose usage is unavailable (killed at the limit before a result line). Cost is what the run output reports (sol is priced by Claude Code as an unknown model, and B's summary calls are outside it; see the usage notes in the design).

### By task

| Task | Category | Mechanism | A correct/partial/wrong | B correct/partial/wrong | d (B − A) |
|---|---|---|---|---|---|
| verbatim-h2 | verbatim | quote-limit | 4/0/0 | 4/0/0 | +0.00 |
| verbatim-h3 | verbatim | quote-limit | 4/0/0 | 4/0/0 | +0.00 |
| verbatim-h5 | verbatim | quote-limit | 4/0/0 | 4/0/0 | +0.00 |
| verbatim-h6 | verbatim | quote-limit | 4/0/0 | 4/0/0 | +0.00 |
| verbatim-h7 | verbatim | quote-limit | 4/0/0 | 4/0/0 | +0.00 |
| long-page-h1 | long-page | window-scan | 4/0/0 | 4/0/0 | +0.00 |
| long-page-h2 | long-page | window-scan | 4/0/0 | 4/0/0 | +0.00 |
| long-page-h3 | long-page | html-1mb-cut | 4/0/0 | 4/0/0 | +0.00 |
| long-page-h5 | long-page | html-1mb-cut | 4/0/0 | 4/0/0 | +0.00 |
| long-page-h6 | long-page | window-scan | 4/0/0 | 4/0/0 | +0.00 |
| long-pdf-h1 | long-pdf | over-10mb | 1/0/3 | 4/0/0 | +0.75 |
| long-pdf-h4 | long-pdf | pdf-navigation | 4/0/0 | 4/0/0 | +0.00 |
| long-pdf-h5 | long-pdf | pdf-navigation | 4/0/0 | 4/0/0 | +0.00 |
| long-pdf-h6 | long-pdf | pdf-table-reading | 3/1/0 | 4/0/0 | +0.25 |
| long-pdf-h7 | long-pdf | pdf-table-reading | 3/1/0 | 4/0/0 | +0.25 |
| image-h1 | image | image-unlinked | 4/0/0 | 4/0/0 | +0.00 |
| image-h2 | image | html-1mb-cut | 0/0/4 | 0/0/4 | +0.00 |
| image-h3 | image | image-many | 4/0/0 | 4/0/0 | +0.00 |
| image-h5 | image | image-relative | 4/0/0 | 4/0/0 | +0.00 |
| image-h6 | image | pdf-figure | 4/0/0 | 4/0/0 | +0.00 |
| search-h1 | search | over-10mb | 0/0/4 | 4/0/0 | +1.00 |
| search-h3 | search | pdf-navigation | 4/0/0 | 4/0/0 | +0.00 |
| search-h4 | search | html-1mb-cut | 4/0/0 | 4/0/0 | +0.00 |
| search-h7 | search | over-10mb | 2/0/2 | 4/0/0 | +0.50 |

### By mechanism

| Mechanism | Tasks | A correct | B correct | Mean d (B − A) |
|---|---|---|---|---|
| quote-limit | 5 | 20/20 | 20/20 | +0.00 |
| window-scan | 3 | 12/12 | 12/12 | +0.00 |
| html-1mb-cut | 4 | 12/16 | 12/16 | +0.00 |
| over-10mb | 3 | 3/12 | 12/12 | +0.75 |
| pdf-navigation | 3 | 12/12 | 12/12 | +0.00 |
| pdf-table-reading | 2 | 6/8 | 8/8 | +0.25 |
| image-unlinked | 1 | 4/4 | 4/4 | +0.00 |
| image-many | 1 | 4/4 | 4/4 | +0.00 |
| image-relative | 1 | 4/4 | 4/4 | +0.00 |
| pdf-figure | 1 | 4/4 | 4/4 | +0.00 |

A mechanism is what the task was built to make `WebFetch` fail on (`tasks-hard.json`).

### Runs not fully correct

- image-h2 A rep 1: wrong — The answer omitted both the average frame rate of 86.1 fps and the 1% low of 69 fps.
- image-h2 A rep 2: wrong — The answer provides neither the average of 86.1 fps nor the 1% low of 69 fps.
- image-h2 A rep 3: wrong — The answer omits both the average frame rate of 86.1 fps and the 1% low of 69 fps.
- image-h2 A rep 4: wrong — The answer omitted both the average of 86.1 fps and the 1% low of 69 fps.
- image-h2 B rep 1: wrong — The answer omitted both the average frame rate of 86.1 fps and the 1% low of 69 fps.
- image-h2 B rep 2: wrong — The answer provides neither the average of 86.1 fps nor the 1% low of 69 fps.
- image-h2 B rep 3: wrong — The answer omitted both the average of 86.1 fps and the 1% low of 69 fps.
- image-h2 B rep 4: wrong — The answer omitted both the average frame rate of 86.1 fps and the 1% low of 69 fps.
- long-pdf-h1 A rep 2: wrong — The answer omits all four requested numerical values.
- long-pdf-h1 A rep 3: wrong — The answer omits all four requested figures: 11, 61 and 118 Mt H2 equivalent for water electrolysis, and 2 423 Mt CO2 for Southeast Asia.
- long-pdf-h1 A rep 4: wrong — The answer omits all four requested figures: 11, 61 and 118 Mt H2 equivalent for water electrolysis, and 2 423 Mt CO2 for Southeast Asia.
- long-pdf-h6 A rep 1: partial — Direct Federal Government payments in 1987 were 39.4 billion chained 2024 dollars, not 33.4 billion.
- long-pdf-h7 A rep 2: partial — The supplementary medical insurance trust fund excise estimate for 2028 is $1,483 million, not $2,800 million.
- search-h1 A rep 1: wrong — The answer omitted all three requested amounts: ARC base rent of $12,942,927, KSC total estimated lease collections of $13,063,605, and NASA-wide total estimated lease collections of $44,132,035.
- search-h1 A rep 2: wrong — The answer omits all three requested amounts: ARC base rent of $12,942,927, KSC total estimated lease collections of $13,063,605, and NASA-wide total estimated lease collections of $44,132,035.
- search-h1 A rep 3: wrong — The answer omits all three requested amounts: ARC base rent of $12,942,927, KSC total estimated lease collections of $13,063,605, and NASA-wide total estimated lease collections of $44,132,035.
- search-h1 A rep 4: wrong — The answer omits all three requested figures: ARC base rent of $12,942,927, KSC total estimated lease collections of $13,063,605, and NASA-wide total estimated lease collections of $44,132,035.
- search-h7 A rep 3: wrong — timed out after 600 s
- search-h7 A rep 4: wrong — timed out after 600 s
