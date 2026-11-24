"""Nightly dump of every account's invoice_summary for finance's warehouse load
(cron: 02:10 UTC, see deploy/cron.yaml). Owner: the finance-data team."""
from tally.export.legacy_writer import render
from tally.reports.models import Report, ReportType
from tally.reports.query import iter_rows
from tally.storage import put_object


def run(accounts, period):
    for account in accounts:
        report = Report(id=0, account_id=account.id, type=ReportType.INVOICE_SUMMARY,
                        period_start=period.start, period_end=period.end)
        body = render(iter_rows(report), report.columns)
        put_object(f"finance-dump/{period.start:%Y-%m}/{account.slug}.csv", body.encode())
