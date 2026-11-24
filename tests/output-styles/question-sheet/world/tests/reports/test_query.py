from datetime import date

import pytest

from tally.reports.models import Report, ReportType
from tally.reports.query import count_rows, iter_rows


@pytest.fixture
def usage_report(seeded):
    return Report(id=1, account_id=seeded.account.id, type=ReportType.USAGE_MONTHLY,
                  period_start=date(2026, 10, 1), period_end=date(2026, 11, 1))


def test_rows_come_in_time_order(usage_report):
    times = [r["usage_events.occurred_at"] for r in iter_rows(usage_report)]
    assert times == sorted(times)


def test_count_matches_rows(usage_report):
    assert count_rows(usage_report) == sum(1 for _ in iter_rows(usage_report))


def test_invoice_summary_joins_contacts(seeded):
    report = Report(id=2, account_id=seeded.account.id, type=ReportType.INVOICE_SUMMARY,
                    period_start=date(2026, 10, 1), period_end=date(2026, 11, 1))
    row = next(iter_rows(report))
    assert row["billing_contacts.email"].endswith("@example.com")
