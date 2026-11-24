"""Reports: what a report is, where its rows come from, and who may open it."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date

from tally.auth.roles import Role


class ReportType(str, enum.Enum):
    USAGE_MONTHLY = "usage_monthly"
    USAGE_YEARLY = "usage_yearly"
    INVOICE_SUMMARY = "invoice_summary"
    BILLING_OVERVIEW = "billing_overview"
    DUNNING_STATUS = "dunning_status"
    SEATS = "seats"
    API_CALLS = "api_calls"


# The tables a report's query reads, in join order. The first is the driving
# table; the rest are joined on account_id (and invoice_id where both have it).
REPORT_SOURCES: dict[ReportType, tuple[str, ...]] = {
    ReportType.USAGE_MONTHLY: ("usage_events", "products"),
    ReportType.USAGE_YEARLY: ("usage_events", "products"),
    ReportType.INVOICE_SUMMARY: ("invoices", "invoice_lines", "billing_contacts"),
    ReportType.BILLING_OVERVIEW: ("invoices", "payments", "billing_contacts"),
    ReportType.DUNNING_STATUS: ("invoices", "dunning_steps", "billing_contacts"),
    ReportType.SEATS: ("seats", "users"),
    ReportType.API_CALLS: ("api_calls",),
}

# Columns each report shows, in display order: (table, column, label).
REPORT_COLUMNS: dict[ReportType, tuple[tuple[str, str, str], ...]] = {
    ReportType.USAGE_MONTHLY: (
        ("usage_events", "occurred_at", "Time"),
        ("products", "name", "Product"),
        ("usage_events", "quantity", "Quantity"),
        ("usage_events", "unit_price", "Unit price"),
        ("usage_events", "currency", "Currency"),
    ),
    ReportType.USAGE_YEARLY: (
        ("usage_events", "occurred_at", "Time"),
        ("products", "name", "Product"),
        ("usage_events", "quantity", "Quantity"),
    ),
    ReportType.INVOICE_SUMMARY: (
        ("invoices", "number", "Invoice"),
        ("invoices", "issued_at", "Issued"),
        ("invoice_lines", "description", "Line"),
        ("invoice_lines", "amount", "Amount"),
        ("invoices", "currency", "Currency"),
        ("billing_contacts", "name", "Billing contact"),
        ("billing_contacts", "email", "Contact email"),
        ("billing_contacts", "phone", "Contact phone"),
    ),
    ReportType.BILLING_OVERVIEW: (
        ("invoices", "number", "Invoice"),
        ("invoices", "total", "Total"),
        ("payments", "paid_at", "Paid"),
        ("payments", "method", "Method"),
        ("billing_contacts", "name", "Billing contact"),
        ("billing_contacts", "email", "Contact email"),
    ),
    ReportType.DUNNING_STATUS: (
        ("invoices", "number", "Invoice"),
        ("invoices", "due_at", "Due"),
        ("dunning_steps", "step", "Step"),
        ("dunning_steps", "sent_at", "Reminder sent"),
        ("billing_contacts", "email", "Contact email"),
        ("billing_contacts", "phone", "Contact phone"),
    ),
    ReportType.SEATS: (
        ("users", "name", "User"),
        ("users", "email", "Email"),
        ("seats", "plan", "Plan"),
        ("seats", "assigned_at", "Assigned"),
    ),
    ReportType.API_CALLS: (
        ("api_calls", "called_at", "Time"),
        ("api_calls", "endpoint", "Endpoint"),
        ("api_calls", "status", "Status"),
        ("api_calls", "latency_ms", "Latency (ms)"),
    ),
}


@dataclass(frozen=True)
class Report:
    id: int
    account_id: int
    type: ReportType
    period_start: date
    period_end: date
    title: str = ""
    pinned_by: tuple[int, ...] = field(default=())

    def visible_to(self, role: Role) -> bool:
        """Every member of the account may open every report of the account:
        viewer, member, finance and admin alike (product decision, #97)."""
        return role in (Role.VIEWER, Role.MEMBER, Role.FINANCE, Role.ADMIN)

    @property
    def columns(self) -> tuple[tuple[str, str, str], ...]:
        return REPORT_COLUMNS[self.type]

    @property
    def sources(self) -> tuple[str, ...]:
        return REPORT_SOURCES[self.type]
