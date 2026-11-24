# CSV export for reports

Status: approved 2026-11-20. Owner: the product lead.

Reports gain a CSV export. Today a report can only be viewed in the browser
or printed; finance and the larger customers have asked for a file they can
load into their own tools (ticket #188, #201).

## Milestones

Each milestone is its own pull request.

### M1 The query layer

`tally.export.columns.export_columns(user, report)` returns the columns the
export writes, in the report's display order, keeping only the columns the
requesting user can read (`tally.auth.permissions.readable_columns`). A column
the user cannot read is left out of the file, not blanked.

### M2 The streaming writer

`tally.export.writer.write_csv(rows, columns, out)` writes rows to CSV as they
arrive from the query, without holding the export in memory.

- An export holds at most 1,000,000 rows (`MAX_EXPORT_ROWS`). The cap bounds
  memory: the legacy writer (`tally/export/legacy_writer.py`) builds the whole
  file in memory, and the API pods have 512 MB. A report over the cap fails
  with `ExportTooLarge` and the message names the cap.
- Timestamps are written in the account's time zone (`accounts.timezone`),
  ISO 8601 with the offset (`2026-11-20T14:05:00+01:00`).
- Money is written as a decimal string in the invoice's currency, with the
  currency code in its own column.
- The header row holds the columns' display labels.

The legacy writer is deleted in M2; nothing else should call it.

### M3 The export endpoint

`GET /reports/<id>/export.csv` starts an export job and returns its id;
`GET /exports/<job>` reports its state and, when done, the download link.
The query is cached in Redis for 10 minutes per (report, user).

### M4 The UI

An Export button on each report and a progress toast that links the file
when it is ready.

## Out of scope

Excel and JSON formats; scheduled exports; exports across accounts.
