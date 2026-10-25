# Web fetch hard set — screening record (board #132)

The hard set (`web/evals/tasks-hard.json`; the design's "The hard set") was
screened by running configuration A (`WebFetch` only) alone, so B's success
plays no part in what the set holds. Both rounds are below: Phase 1 as it
was rendered then, with readers allowed and opus grading, then the re-screen
under the rules the final round runs by.

## What changed after Phase 1

- **Third-party readers are denied in both configurations.** Phase 1 found
  10 of 44 A runs reading through one (`r.jina.ai` in all 10; also
  `wsrv.nl`, Google's document viewer, `translate.goog`, archive.org), 8 of
  them correct. The human ruled that a reader is a route around the fetch
  tool, like Bash, so both configurations load `web/evals/deny-readers/`.
- **The grader is `sol` at `xhigh`** (the human's "all sol-xhigh"). Re-grading
  copies of the 43 Phase 1 runs still in the set, sol agreed with opus on 42
  verdicts, at about $0.006 a grade against opus's $0.009. The one
  disagreement was a fact asking for more than its question.
- **That fact and six like it were trimmed** to what their questions ask:
  long-pdf-h3 f4, long-page-h4 f1, long-page-h3 f3, long-page-h2 f3,
  image-h7 f1 and f2, search-h5 f1. Their evidence is unchanged.
- **verbatim-h4 was dropped.** A's one failure there was the runner
  declining to quote PKWARE's APPNOTE after reading "All Rights Reserved".
  Counting B's verbatim copy of it as a quality win would reward bypassing
  a copyright safeguard. Its Phase 1 row stays below, as it was.
- **The unversioned pages were re-checked** on 2026-10-25 (the Fed's
  `BulletinCharts.pdf`, curl's and OpenSSH's changelogs, Tom's Hardware's
  RTX 5070 page and its chart, NVIDIA's Blackwell whitepaper). Each still
  matched its evidence, the two PDFs byte for byte, so no key changed.

## Re-screen: readers denied, graded by sol at xhigh

The five tasks A had passed through a reader, once each:

Configuration A only (A = WebFetch); 5 runs of 5 expected; sol at xhigh; graded by sol at xhigh.

### By task

| Task | Category | Mechanism | A correct/partial/wrong | Median tokens | Median duration (s) | Fetch calls (mean) |
|---|---|---|---|---|---|---|
| image-h1 | image | image-unlinked | 1/0/0 | 57,233 | 77 | 8.0 |
| image-h2 | image | html-1mb-cut | 0/0/1 | 100,192 | 177 | 28.0 |
| search-h1 | search | over-10mb | 0/0/1 | 901,354 | 532 | 14.0 |
| search-h4 | search | html-1mb-cut | 1/0/0 | 151,915 | 349 | 15.0 |
| search-h6 | search | html-1mb-cut | 1/0/0 | 469,715 | 459 | 20.0 |

### Runs not fully correct

- image-h2 A rep 1: wrong — The answer omitted both the average of 86.1 fps and the 1% low of 69 fps.
- search-h1 A rep 1: wrong — The answer omits all three requested amounts: ARC base rent of $12,942,927, KSC total estimated lease collections of $13,063,605, and NASA-wide total estimated lease collections of $44,132,035.

Of the three that still passed: image-h1 by guessing the chart's URL on the
site's image host; search-h4 through `unicode-org.github.io` and the
Unicode site's own files; search-h6 through arXiv's own HTML (`ar5iv`) and
two third-party arXiv renderers (`arxiv-vanity.com`, `alphaxiv.org`), which
serve only arXiv papers and are left outside the rule. On image-h2 the
runner queried Google, Bing and DuckDuckGo through `WebFetch`; B's fetch
tool can do the same, so that is left too. The two failures: image-h2
never found the chart (its article starts past WebFetch's 1 MB HTML cut),
and search-h1 found no way into NASA's 30 MB PDF.

## Phase 1: readers allowed, graded by opus

Configuration A only (A = WebFetch); 44 runs of 44 expected; sol at xhigh; graded by opus.

### By task

| Task | Category | Mechanism | A correct/partial/wrong | Median tokens | Median duration (s) | Fetch calls (mean) |
|---|---|---|---|---|---|---|
| verbatim-h1 | verbatim | quote-limit | 1/0/0 | 12,216 | 30 | 1.0 |
| verbatim-h2 | verbatim | quote-limit | 1/0/0 | 24,853 | 55 | 4.0 |
| verbatim-h3 | verbatim | quote-limit | 2/0/0 | 41,867 | 99 | 5.5 |
| verbatim-h4 | verbatim | quote-limit | 0/0/1 | 16,510 | 72 | 2.0 |
| verbatim-h5 | verbatim | quote-limit | 1/0/0 | 42,126 | 88 | 6.0 |
| verbatim-h6 | verbatim | quote-limit | 2/0/0 | 75,526 | 187 | 9.0 |
| verbatim-h7 | verbatim | quote-limit | 1/0/0 | 10,640 | 26 | 1.0 |
| long-page-h1 | long-page | window-scan | 1/0/0 | 30,356 | 100 | 9.0 |
| long-page-h2 | long-page | window-scan | 1/0/0 | 40,480 | 63 | 17.0 |
| long-page-h3 | long-page | html-1mb-cut | 2/0/0 | 72,006 | 138 | 12.5 |
| long-page-h4 | long-page | window-scan | 1/0/0 | 26,562 | 82 | 7.0 |
| long-page-h5 | long-page | html-1mb-cut | 2/0/0 | 82,878 | 160 | 21.0 |
| long-page-h6 | long-page | window-scan | 2/0/0 | 99,246 | 144 | 8.5 |
| long-page-h7 | long-page | window-scan | 2/0/0 | 112,839 | 209 | 29.5 |
| long-pdf-h1 | long-pdf | over-10mb | 0/0/1 | 270,973 | 396 | 41.0 |
| long-pdf-h2 | long-pdf | over-10mb | 1/0/0 | 59,206 | 70 | 6.0 |
| long-pdf-h3 | long-pdf | pdf-navigation | 1/0/0 | 112,352 | 85 | 1.0 |
| long-pdf-h4 | long-pdf | pdf-navigation | 2/0/0 | 174,499 | 110 | 1.0 |
| long-pdf-h5 | long-pdf | pdf-navigation | 1/0/0 | 95,803 | 58 | 1.0 |
| long-pdf-h6 | long-pdf | pdf-table-reading | 1/0/0 | 25,622 | 49 | 3.0 |
| long-pdf-h7 | long-pdf | pdf-table-reading | 1/0/0 | 76,346 | 53 | 1.0 |
| image-h1 | image | image-unlinked | 2/0/0 | 67,985 | 110 | 10.5 |
| image-h2 | image | html-1mb-cut | 2/0/0 | 103,133 | 150 | 10.5 |
| image-h3 | image | image-many | 1/0/0 | 25,353 | 28 | 2.0 |
| image-h4 | image | image-unlinked | 1/0/0 | 45,412 | 83 | 5.0 |
| image-h5 | image | image-relative | 1/0/0 | 24,185 | 28 | 2.0 |
| image-h6 | image | pdf-figure | 1/0/0 | 37,935 | 26 | 1.0 |
| image-h7 | image | pdf-figure | 1/0/0 | 36,314 | 38 | 1.0 |
| search-h1 | search | over-10mb | 1/0/0 | 634,958 | 384 | 25.0 |
| search-h3 | search | pdf-navigation | 1/0/0 | 260,299 | 100 | 1.0 |
| search-h4 | search | html-1mb-cut | 2/0/0 | 59,978 | 136 | 7.0 |
| search-h5 | search | html-1mb-cut | 1/0/0 | 167,334 | 259 | 16.0 |
| search-h6 | search | html-1mb-cut | 1/0/0 | 198,882 | 317 | 17.0 |
| search-h7 | search | over-10mb | 0/0/1 | 767,269 | 600 | 28.0 |

### Runs not fully correct

- long-pdf-h1 A rep 1: wrong — The agent gave no figures, saying it could not retrieve the PDF, so none of the four values were stated.
- search-h7 A rep 1: wrong — timed out after 600 s
- verbatim-h4 A rep 1: wrong — The agent declined to quote the section verbatim and gave only a paraphrased summary, so none of the three verbatim passages were reproduced.
