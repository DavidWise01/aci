# HACI Torture Suite x2 for Validator v3.0

This package does **not** add HACI features.

It reruns x2 torture against `haci_project_validator_v3_0.py`:

1. Curated adversarial cases.
2. Seeded fuzz/property cases.

Both layers run:
- forward order
- reverse order

v3.0-specific expectations:
- same-file returns may not pair backward to later asks
- same-file suffix `>` before ask fails
- same-file suffix `!` before ask fails
- same-file suffix `?` before ask fails
- cross-file return/ask pairing remains order-independent

Run:

```bash
python torture_haci_v3_0_x2.py
```
