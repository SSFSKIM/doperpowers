from src.inventory import Inventory, Item


def test_add_merges_quantities():
    inv = Inventory()
    inv.add(Item("A1", "bolt", 3, 10))
    inv.add(Item("A1", "bolt", 2, 10))
    assert inv.total_value_cents() == 50


def test_low_stock():
    inv = Inventory()
    inv.add(Item("B2", "nut", 1, 5))
    assert [i.sku for i in inv.low_stock()] == ["B2"]
