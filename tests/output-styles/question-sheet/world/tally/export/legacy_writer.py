"""The writer behind the print view's "Download" link (2019).

Builds the whole file in memory and returns it. Kept until the CSV export
replaces it (docs/specs/2026-11-20-csv-export.md, M2).
"""
import csv
import io


def render(rows, columns):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([label for _, _, label in columns])
    for row in rows:
        w.writerow([row.get(f"{t}.{c}", "") for t, c, _ in columns])
    return buf.getvalue()  # the whole export, in memory; 1M rows is about 380 MB
