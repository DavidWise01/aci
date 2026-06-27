# HACI Torture Suite x2 for Validator v2.8

This package does **not** add HACI features.

It reruns x2 torture against `haci_project_validator_v2_8.py`:

1. Curated adversarial cases.
2. Seeded fuzz/property cases.

Both layers run:
- forward order
- reverse order

v2.8-specific expectations:
- payload-specific suffix `?` return-question pairs with matching ask
- return-question does not complete ask
- later suffix `>` or `!` completes it
- ambiguous return-question fails closed
- zero-score return-question fails closed
- late return-question after completed answer fails strict

Run:

```bash
python torture_haci_v2_8_x2.py
```
