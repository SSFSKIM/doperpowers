"""Plain-text stock report."""
from .inventory import Inventory


def render(inv: Inventory) -> str:
    lines = ["SKU     NAME            QTY"]
    for item in sorted(inv._items.values(), key=lambda i: i.sku):
        lines.append(f"{item.sku:<7} {item.name:<15} {item.qty}")
    lines.append(f"Total value: ${inv.total_value_cents() / 100:.2f}")
    return "\n".join(lines)
