"""The query behind a report: rows as dicts keyed "table.column"."""
from __future__ import annotations

from collections.abc import Iterator

from tally.db import conn
from tally.reports.models import Report

BATCH = 5000


def _select(report: Report, columns) -> tuple[str, list]:
    driving, *joined = report.sources
    cols = ", ".join(f'{t}.{c} AS "{t}.{c}"' for t, c, _ in columns)
    sql = [f"SELECT {cols} FROM {driving}"]
    for table in joined:
        on = f"{table}.account_id = {driving}.account_id"
        if table in ("invoice_lines", "payments", "dunning_steps") and driving == "invoices":
            on = f"{table}.invoice_id = invoices.id"
        if table == "products":
            on = "products.id = usage_events.product_id"
        if table == "users":
            on = "users.id = seats.user_id"
        sql.append(f"JOIN {table} ON {on}")
    time_col = {"usage_events": "occurred_at", "invoices": "issued_at", "seats": "assigned_at",
                "api_calls": "called_at"}[driving]
    sql.append(f"WHERE {driving}.account_id = %s AND {driving}.{time_col} >= %s AND {driving}.{time_col} < %s")
    sql.append(f"ORDER BY {driving}.{time_col}, {driving}.id")
    return "\n".join(sql), [report.account_id, report.period_start, report.period_end]


def count_rows(report: Report) -> int:
    sql, params = _select(report, report.columns[:1])
    with conn() as c:
        return c.execute(f"SELECT count(*) FROM ({sql}) q", params).fetchone()[0]


def iter_rows(report: Report, columns=None) -> Iterator[dict]:
    """The report's rows in display order, fetched BATCH at a time with a
    server-side cursor, so memory does not grow with the report."""
    sql, params = _select(report, columns or report.columns)
    with conn() as c, c.cursor(name=f"report_{report.id}") as cur:
        cur.itersize = BATCH
        cur.execute(sql, params)
        names = [d.name for d in cur.description]
        for rec in cur:
            yield dict(zip(names, rec))
