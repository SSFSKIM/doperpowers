# Web fetch screening — hard-screen-dev, hard-screen-final

Configuration A only (A = WebFetch); 44 runs of 44 expected; sol at xhigh; graded by opus.

## By task

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

## Runs not fully correct

- long-pdf-h1 A rep 1: wrong — The agent gave no figures, saying it could not retrieve the PDF, so none of the four values were stated.
- search-h7 A rep 1: wrong — timed out after 600 s
- verbatim-h4 A rep 1: wrong — The agent declined to quote the section verbatim and gave only a paraphrased summary, so none of the three verbatim passages were reproduced.

