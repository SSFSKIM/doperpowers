expect: doperpowers:execspec
note: design already approved and pasted; writing the spec is execspec
---
We finished the design discussion and I approved it. Write the spec for the design we agreed:

Design summary (approved):
- Add low-stock alerts to the shop scripts. A new module src/alerts.py exposes `check(inv, threshold=5) -> list[Alert]`, where Alert is a dataclass (sku, name, qty, threshold).
- Delivery is pluggable: a `Notifier` protocol with a `send(alerts)` method; v1 ships two notifiers, `StdoutNotifier` and `EmailNotifier` (SMTP settings from env vars SHOP_SMTP_HOST / SHOP_SMTP_USER / SHOP_SMTP_PASSWORD).
- Alerts are de-duplicated: the same sku is not re-alerted within 24 hours; state lives in a small JSON file at ~/.shop/alert-state.json.
- A CLI entry point `python -m src.alerts --notifier email --threshold 3` runs one check and exits; cron is the scheduler (no daemon).
- Out of scope for v1: supplier APIs, auto-reordering, a dashboard.
- Testing: unit tests per module, a fake Notifier for the CLI test, a temp-dir state file.
