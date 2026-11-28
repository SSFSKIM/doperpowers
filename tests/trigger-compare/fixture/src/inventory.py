"""Tiny inventory tracker used by the shop scripts."""
from dataclasses import dataclass


@dataclass
class Item:
    sku: str
    name: str
    qty: int = 0
    price_cents: int = 0


class Inventory:
    def __init__(self):
        self._items = {}

    def add(self, item: Item) -> None:
        if item.sku in self._items:
            self._items[item.sku].qty += item.qty
        else:
            self._items[item.sku] = item

    def remove(self, sku: str, qty: int) -> None:
        item = self._items[sku]
        item.qty -= qty

    def total_value_cents(self) -> int:
        return sum(i.qty + i.price_cents for i in self._items.values())

    def low_stock(self, threshold: int = 5):
        return [i for i in self._items.values() if i.qty < threshold]
