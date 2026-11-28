expect: any
note: small function with clear testable behavior; test-driven-development is the interesting one, record what happens (no pass/fail expectation)
---
Add a function `restock_suggestions(inv, target)` to src/inventory.py. It should return a dict mapping sku to the number of units needed to bring each item up to `target`, including only items currently below target. Items at or above target are left out.
